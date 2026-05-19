import json
import sqlite3
import threading
from pathlib import Path

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Signal, Slot, QUrl, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout

from src.graph.builder import build_graph_data
from src.graph.scoring import DEFAULT_WEIGHTS
from src.db.schema import init_db

_HTML = Path(__file__).parent / "graph.html"


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
    def __init__(self, db_path: str):
        super().__init__()
        self._db_path = db_path
        self._page_ready = False
        self._pending_json: str | None = None
        self._compute_sig: _ComputeSignal | None = None  # kept alive during compute

        self._view = QWebEngineView()
        self._bridge = _Bridge()
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        self._bridge.graph_ready.connect(self._on_page_ready)
        self._bridge.node_clicked.connect(self._on_node_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._view.load(QUrl.fromLocalFile(str(_HTML.resolve())))

    # ── Public ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Recompute graph data and push to JS. Safe to call at any time."""
        if self._page_ready:
            self._start_compute()
        # If not ready yet, _on_page_ready triggers the initial compute.

    # ── Internal ────────────────────────────────────────────────────────────

    def _on_page_ready(self) -> None:
        self._page_ready = True
        if self._pending_json is not None:
            self._run_js(self._pending_json)
            self._pending_json = None
        else:
            self._start_compute()

    def _start_compute(self) -> None:
        from src.ui.options_tab import load_settings
        weights = load_settings().get("graph_weights", DEFAULT_WEIGHTS)
        db_path = self._db_path

        sig = _ComputeSignal()
        sig.done.connect(self._on_compute_done, Qt.ConnectionType.QueuedConnection)
        self._compute_sig = sig  # prevent GC before the signal fires

        def worker() -> None:
            try:
                conn = init_db(db_path)
                data = build_graph_data(conn, weights)
                conn.close()
                result = json.dumps(data)
            except Exception as exc:
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
        pass  # reserved for future use (e.g. sync selection to Library tab)
