import json
import sqlite3
import sys
import threading
from pathlib import Path

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt, QStringListModel, QSize, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSplitter, QGroupBox, QDoubleSpinBox, QSpinBox,
    QPushButton, QLabel, QToolButton, QLineEdit, QCompleter,
)

from src.graph.builder import build_graph_data
from src.graph.scoring import DEFAULT_WEIGHTS, DEFAULT_LAMBDA, DEFAULT_K
from src.db.schema import init_db
from src.ui.options_tab import load_settings, save_settings
from src.ui.transitions_widget import TransitionsWidget

if getattr(sys, "frozen", False):
    _HTML = Path(sys._MEIPASS) / "src" / "ui" / "graph.html"
else:
    _HTML = Path(__file__).parent / "graph.html"


class _BottomPanel(TransitionsWidget):
    """TransitionsWidget that reports zero minimum size so the splitter can fully collapse it."""
    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

_WEIGHT_LABELS = [
    ("tags", "Tag similarity"),
    ("key",  "Key compat."),
    ("bpm",  "BPM match"),
]


class _Bridge(QObject):
    graph_ready = Signal()
    node_clicked = Signal(str)
    toggle_config = Signal()

    @Slot()
    def on_ready(self) -> None:
        self.graph_ready.emit()

    @Slot(str)
    def on_node_clicked(self, track_id: str) -> None:
        self.node_clicked.emit(track_id)

    @Slot()
    def on_toggle_config(self) -> None:
        self.toggle_config.emit()


class _ComputeSignal(QObject):
    """Created on the main thread; emits from the worker thread via QueuedConnection."""
    done = Signal(str)


class GraphTab(QWidget):
    bottom_panel_transitions_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, db_path: str):
        super().__init__()
        self._conn = conn
        self._db_path = db_path
        self._page_ready = False
        self._pending_json: str | None = None
        self._compute_sig: _ComputeSignal | None = None
        self._tab_visible = False
        self._graph_data_received = False
        self._initial_fit_done = False

        self._view = QWebEngineView()
        self._bridge = _Bridge()
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        self._bridge.graph_ready.connect(self._on_page_ready)
        self._bridge.node_clicked.connect(self._on_node_clicked)
        self._bridge.toggle_config.connect(self._toggle_config_panel)

        self._weight_inputs: dict[str, QDoubleSpinBox] = {}
        self._lambda_input: QDoubleSpinBox
        self._k_input: QSpinBox
        self._search_track_map: dict[str, str] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._search_model = QStringListModel(self)
        self._search_bar = QLineEdit()
        self._search_bar.setPlaceholderText("Filter by title or artist…")
        completer = QCompleter(self._search_model, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)
        self._search_bar.setCompleter(completer)
        completer.activated.connect(self._on_search_activated)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(8, 8, 8, 6)
        search_row.setSpacing(6)
        search_row.addWidget(QLabel("Search:"))
        search_row.addWidget(self._search_bar)
        outer.addLayout(search_row)

        # ── Left column: graph on top, bottom panel below ────────────────────
        self._vsplit = QSplitter(Qt.Orientation.Vertical)
        self._vsplit.addWidget(self._view)

        self._bottom_panel = _BottomPanel(self._conn, readonly_from=True, tabbed=True)
        self._bottom_panel.transitions_changed.connect(self.bottom_panel_transitions_changed)
        self._bottom_panel.track_selected.connect(self._on_next_track_selected)
        # λ and k are wired after _build_side_panel runs; default values suffice for now

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close panel")
        close_btn.clicked.connect(self._close_bottom_panel)
        self._bottom_panel.tab_widget.setCornerWidget(close_btn, Qt.Corner.TopRightCorner)

        self._vsplit.addWidget(self._bottom_panel)
        self._bottom_panel.hide()

        # ── Outer: left column + side panel (full height on right) ───────────
        self._hsplit = QSplitter(Qt.Orientation.Horizontal)
        self._hsplit.addWidget(self._vsplit)
        self._hsplit.addWidget(self._build_side_panel())
        self._hsplit.setSizes([900, 220])

        outer.addWidget(self._hsplit)

        # Sync inference params to bottom panel after side panel is built
        self._bottom_panel.set_inference(
            lam=self._lambda_input.value(),
            k=self._k_input.value(),
        )

        self._load_search_tracks()
        self._view.load(QUrl.fromLocalFile(str(_HTML.resolve())))

    # ── Side panel ───────────────────────────────────────────────────────────

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(180)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        settings = load_settings()
        saved_weights = settings.get("graph_weights", DEFAULT_WEIGHTS)

        weights_box = QGroupBox("Similarity Weights")
        form = QFormLayout(weights_box)
        form.setSpacing(6)
        for key, label in _WEIGHT_LABELS:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(saved_weights.get(key, DEFAULT_WEIGHTS[key]))
            spin.valueChanged.connect(self._on_weight_changed)
            form.addRow(label + ":", spin)
            self._weight_inputs[key] = spin
        self._weight_sum_label = QLabel(self._weight_sum_text())
        self._weight_sum_label.setStyleSheet("color: #888;")
        form.addRow("", self._weight_sum_label)
        layout.addWidget(weights_box)

        infer_box = QGroupBox("Inference")
        infer_form = QFormLayout(infer_box)
        infer_form.setSpacing(6)

        self._lambda_input = QDoubleSpinBox()
        self._lambda_input.setRange(0.0, 1.0)
        self._lambda_input.setSingleStep(0.05)
        self._lambda_input.setDecimals(2)
        self._lambda_input.setValue(float(settings.get("inference_lambda", DEFAULT_LAMBDA)))
        self._lambda_input.valueChanged.connect(self._on_inference_changed)
        infer_form.addRow("λ weight:", self._lambda_input)

        self._k_input = QSpinBox()
        self._k_input.setRange(1, 20)
        self._k_input.setValue(int(settings.get("inference_k", DEFAULT_K)))
        self._k_input.valueChanged.connect(self._on_inference_changed)
        infer_form.addRow("Neighbors k:", self._k_input)

        layout.addWidget(infer_box)

        redo_btn = QPushButton("Redo Graph")
        redo_btn.clicked.connect(self._on_redo_clicked)
        layout.addWidget(redo_btn)

        layout.addStretch()
        return panel

    def _weight_sum_text(self) -> str:
        total = sum(s.value() for s in self._weight_inputs.values()) if self._weight_inputs else 1.0
        return f"Sum: {total:.2f}  (aim for 1.00)"

    def _on_weight_changed(self) -> None:
        self._weight_sum_label.setText(self._weight_sum_text())
        settings = load_settings()
        settings["graph_weights"] = {k: round(s.value(), 2) for k, s in self._weight_inputs.items()}
        save_settings(settings)

    def _on_inference_changed(self) -> None:
        settings = load_settings()
        settings["inference_lambda"] = round(self._lambda_input.value(), 2)
        settings["inference_k"] = self._k_input.value()
        save_settings(settings)
        self._bottom_panel.set_inference(
            lam=self._lambda_input.value(),
            k=self._k_input.value(),
        )

    def _on_redo_clicked(self) -> None:
        if self._page_ready:
            self._start_compute()

    # ── Public ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Recompute graph data and push to JS. Safe to call at any time."""
        self._load_search_tracks()
        if self._page_ready:
            self._start_compute()

    def reload_connection(self, conn: sqlite3.Connection, db_path: str) -> None:
        self._conn = conn
        self._db_path = db_path
        self._initial_fit_done = False
        self._graph_data_received = False
        self._tab_visible = False
        self.refresh()

    def on_tab_shown(self) -> None:
        """Called each time the Graph tab becomes visible."""
        self._tab_visible = True
        if not self._initial_fit_done and self._graph_data_received:
            self._initial_fit_done = True
            QTimer.singleShot(300, self.fit_view)

    def fit_view(self) -> None:
        if self._page_ready:
            self._view.page().runJavaScript("window.fitAll()")

    def _load_search_tracks(self) -> None:
        rows = self._conn.execute(
            "SELECT id, artist, title FROM tracks WHERE is_available=1 ORDER BY artist, title"
        ).fetchall()
        self._search_track_map = {}
        names = []
        for r in rows:
            artist = r[1] or ""
            title = r[2] or ""
            name = f"{artist} — {title}" if artist else title
            self._search_track_map[name] = r[0]
            names.append(name)
        self._search_model.setStringList(names)

    def _on_search_activated(self, text: str) -> None:
        track_id = self._search_track_map.get(text)
        if track_id:
            self._search_bar.clear()
            if self._page_ready:
                safe_id = track_id.replace("'", "\\'")
                self._view.page().runJavaScript(f"window.selectNode('{safe_id}')")
            self._on_node_clicked(track_id)

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_page_ready(self) -> None:
        self._page_ready = True
        if self._pending_json is not None:
            self._run_js(self._pending_json)
            self._pending_json = None
        else:
            self._start_compute()

    def _start_compute(self) -> None:
        weights = {k: round(s.value(), 2) for k, s in self._weight_inputs.items()} if self._weight_inputs else DEFAULT_WEIGHTS
        db_path = self._db_path

        sig = _ComputeSignal()
        sig.done.connect(self._on_compute_done, Qt.ConnectionType.QueuedConnection)
        self._compute_sig = sig

        def worker() -> None:
            try:
                conn = init_db(db_path)
                data = build_graph_data(conn, weights)
                conn.close()
                result = json.dumps(data)
            except Exception:
                result = json.dumps({"nodes": [], "edges": []})
            sig.done.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    @Slot(str)
    def _on_compute_done(self, json_str: str) -> None:
        self._compute_sig = None
        if self._page_ready:
            self._run_js(json_str)
        else:
            self._pending_json = json_str
        self._graph_data_received = True
        if not self._initial_fit_done and self._tab_visible:
            self._initial_fit_done = True
            QTimer.singleShot(1200, self.fit_view)
        self._bottom_panel._refresh_next_track()

    def _run_js(self, json_str: str) -> None:
        self._view.page().runJavaScript(f"window.setGraphData({json_str})")

    def _on_node_clicked(self, track_id: str) -> None:
        if self._bottom_panel.isHidden():
            self._bottom_panel.show()
            total = self._vsplit.height()
            self._vsplit.setSizes([int(total * 0.6), int(total * 0.4)])
        self._bottom_panel.set_from_track(track_id)
        self._bottom_panel.refresh()

    def _on_next_track_selected(self, track_id: str) -> None:
        if self._page_ready:
            safe_id = track_id.replace("'", "\\'")
            self._view.page().runJavaScript(f"window.selectNode('{safe_id}')")
        self._on_node_clicked(track_id)

    def _close_bottom_panel(self) -> None:
        self._bottom_panel.hide()

    def _toggle_config_panel(self) -> None:
        sizes = self._hsplit.sizes()
        total = sum(sizes)
        if sizes[1] == 0:
            self._hsplit.setSizes([total - 220, 220])
        else:
            self._hsplit.setSizes([total, 0])
