import json
import sqlite3
import threading
from pathlib import Path

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt, QStringListModel, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSplitter, QGroupBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QLabel, QToolButton, QLineEdit, QCompleter,
)

from src.graph.builder import build_graph_data
from src.graph.scoring import DEFAULT_WEIGHTS, DEFAULT_RATING_SCORES
from src.db.schema import init_db
from src.ui.options_tab import load_settings, save_settings
from src.ui.transitions_widget import TransitionsWidget

_HTML = Path(__file__).parent / "graph.html"


class _BottomPanel(TransitionsWidget):
    """TransitionsWidget that reports zero minimum size so the splitter can fully collapse it."""
    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

_WEIGHT_LABELS = [
    ("key",  "Key compatibility"),
    ("bpm",  "BPM match"),
    ("tags", "Tag similarity"),
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

        self._view = QWebEngineView()
        self._bridge = _Bridge()
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        self._bridge.graph_ready.connect(self._on_page_ready)
        self._bridge.node_clicked.connect(self._on_node_clicked)
        self._bridge.toggle_config.connect(self._toggle_config_panel)

        self._weight_inputs: dict[str, QDoubleSpinBox] = {}
        self._rating_multiplier_inputs: dict[int, QDoubleSpinBox] = {}
        self._include_ratings_cb: QCheckBox
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

        weights_box = QGroupBox("Graph Weights")
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

        self._include_ratings_cb = QCheckBox("Include user ratings")
        self._include_ratings_cb.setChecked(
            bool(settings.get("include_user_ratings", False))
        )
        self._include_ratings_cb.toggled.connect(self._on_include_ratings_toggled)
        layout.addWidget(self._include_ratings_cb)

        saved_mults = settings.get("rating_scores", {})
        _MULT_LABELS = [(1, "★"), (2, "★★"), (3, "★★★")]
        mults_box = QGroupBox("Rating Scores")
        mults_form = QFormLayout(mults_box)
        mults_form.setSpacing(6)
        for rating, label in _MULT_LABELS:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            default = DEFAULT_RATING_SCORES[rating]
            spin.setValue(float(saved_mults.get(str(rating), default)))
            spin.valueChanged.connect(self._on_rating_multiplier_changed)
            mults_form.addRow(label + ":", spin)
            self._rating_multiplier_inputs[rating] = spin
        layout.addWidget(mults_box)

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

    def _on_include_ratings_toggled(self, checked: bool) -> None:
        settings = load_settings()
        settings["include_user_ratings"] = checked
        save_settings(settings)

    def _on_rating_multiplier_changed(self) -> None:
        settings = load_settings()
        settings["rating_scores"] = {
            str(r): round(s.value(), 2)
            for r, s in self._rating_multiplier_inputs.items()
        }
        save_settings(settings)

    def _on_redo_clicked(self) -> None:
        if self._page_ready:
            self._start_compute()

    # ── Public ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Recompute graph data and push to JS. Safe to call at any time."""
        self._load_search_tracks()
        if self._page_ready:
            self._start_compute()

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
        include_user_ratings = self._include_ratings_cb.isChecked() if hasattr(self, '_include_ratings_cb') else False
        rating_scores = {r: round(s.value(), 2) for r, s in self._rating_multiplier_inputs.items()} if self._rating_multiplier_inputs else DEFAULT_RATING_SCORES
        db_path = self._db_path

        sig = _ComputeSignal()
        sig.done.connect(self._on_compute_done, Qt.ConnectionType.QueuedConnection)
        self._compute_sig = sig

        def worker() -> None:
            try:
                conn = init_db(db_path)
                data = build_graph_data(conn, weights, include_user_ratings=include_user_ratings, rating_scores=rating_scores)
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

    def _close_bottom_panel(self) -> None:
        self._bottom_panel.hide()

    def _toggle_config_panel(self) -> None:
        sizes = self._hsplit.sizes()
        total = sum(sizes)
        if sizes[1] == 0:
            self._hsplit.setSizes([total - 220, 220])
        else:
            self._hsplit.setSizes([total, 0])
