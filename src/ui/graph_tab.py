import json
import sqlite3
import threading
from pathlib import Path

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSplitter, QGroupBox, QDoubleSpinBox, QCheckBox,
    QPushButton, QLabel, QToolButton,
)

from src.graph.builder import build_graph_data
from src.graph.scoring import DEFAULT_WEIGHTS
from src.db.schema import init_db
from src.ui.options_tab import load_settings, save_settings

_HTML = Path(__file__).parent / "graph.html"

_WEIGHT_LABELS = [
    ("key",  "Key compatibility"),
    ("bpm",  "BPM match"),
    ("tags", "Tag similarity"),
]


class _Bridge(QObject):
    graph_ready = Signal()
    node_clicked = Signal(str)

    @Slot()
    def on_ready(self) -> None:
        self.graph_ready.emit()

    @Slot(str)
    def on_node_clicked(self, track_id: str) -> None:
        self.node_clicked.emit(track_id)


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

        self._weight_inputs: dict[str, QDoubleSpinBox] = {}
        self._include_ratings_cb: QCheckBox

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._vsplit = QSplitter(Qt.Orientation.Vertical)

        # ── Top: graph + side panel ──────────────────────────────────────────
        self._hsplit = QSplitter(Qt.Orientation.Horizontal)
        self._hsplit.addWidget(self._view)
        self._hsplit.addWidget(self._build_side_panel())
        self._hsplit.setSizes([900, 220])
        self._vsplit.addWidget(self._hsplit)

        # ── Bottom: transitions panel (hidden until a node is clicked) ───────
        from src.ui.transitions_tab import TransitionsTab
        self._bottom_panel = TransitionsTab(self._conn)
        self._bottom_panel.transitions_changed.connect(self.bottom_panel_transitions_changed)

        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        header = QWidget()
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(8, 4, 4, 4)
        header_row.addStretch()
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close panel")
        close_btn.clicked.connect(self._close_bottom_panel)
        header_row.addWidget(close_btn)
        bottom_layout.addWidget(header)
        bottom_layout.addWidget(self._bottom_panel)

        self._vsplit.addWidget(bottom_container)
        self._vsplit.setSizes([700, 0])

        outer.addWidget(self._vsplit)

        self._view.load(QUrl.fromLocalFile(str(_HTML.resolve())))

    # ── Side panel ───────────────────────────────────────────────────────────

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(180)
        panel.setMaximumWidth(280)
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

    def _on_redo_clicked(self) -> None:
        if self._page_ready:
            self._start_compute()

    # ── Public ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Recompute graph data and push to JS. Safe to call at any time."""
        if self._page_ready:
            self._start_compute()

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
        db_path = self._db_path

        sig = _ComputeSignal()
        sig.done.connect(self._on_compute_done, Qt.ConnectionType.QueuedConnection)
        self._compute_sig = sig

        def worker() -> None:
            try:
                conn = init_db(db_path)
                data = build_graph_data(conn, weights, include_user_ratings=include_user_ratings)
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

    def _run_js(self, json_str: str) -> None:
        self._view.page().runJavaScript(f"window.setGraphData({json_str})")

    def _on_node_clicked(self, track_id: str) -> None:
        sizes = self._vsplit.sizes()
        if sum(sizes) > 0 and sizes[1] == 0:
            total = sum(sizes)
            self._vsplit.setSizes([int(total * 0.6), int(total * 0.4)])
        self._bottom_panel.set_from_track(track_id)
        self._bottom_panel.refresh()

    def _close_bottom_panel(self) -> None:
        total = sum(self._vsplit.sizes())
        self._vsplit.setSizes([total, 0])
