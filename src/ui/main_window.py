import sqlite3
from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar
from PySide6.QtCore import Qt, QTimer

from src.ui.library_tab import LibraryTab
from src.ui.graph_tab import GraphTab
from src.ui.list_tab import ListTab
from src.ui.options_tab import OptionsTab


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection, db_path: str):
        super().__init__()
        self._conn = conn
        self.setWindowTitle("DJ Transition Companion")

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._library = LibraryTab(conn)
        self._graph = GraphTab(conn, db_path)
        self._list = ListTab(conn)
        self._options = OptionsTab(db_path)

        self._tabs.addTab(self._library, "Library")
        self._tabs.addTab(self._graph, "Graph")
        self._tabs.addTab(self._list, "List")
        self._tabs.addTab(self._options, "Options")

        self._library.track_selected.connect(self._on_track_selected)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._options.scan_finished.connect(self._on_scan_finished)
        self._options.profile_switched.connect(self._on_profile_switched)
        self._graph.bottom_panel_transitions_changed.connect(self._graph.refresh)
        self._graph.bottom_panel_transitions_changed.connect(self._library.refresh)
        self._graph.bottom_panel_transitions_changed.connect(self._list.refresh)
        self._list.transitions_changed.connect(self._graph.refresh)
        self._list.transitions_changed.connect(self._library.refresh)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._update_status()

        QTimer.singleShot(0, self._options.trigger_auto_scan)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._list.refresh)
        self._refresh_timer.start()

    def _on_profile_switched(self) -> None:
        from src.ui.options_tab import get_active_db_path
        from src.db.schema import init_db
        self._conn.close()
        new_db = get_active_db_path()
        new_conn = init_db(new_db)
        self._conn = new_conn
        self._library.reload_connection(new_conn)
        self._graph.reload_connection(new_conn, new_db)
        self._list.reload_connection(new_conn)
        self._options.reload_db_path(new_db)
        self._update_status()
        self._options.trigger_auto_scan()

    def _on_scan_finished(self) -> None:
        self._library.refresh()
        self._library._rebuild_tag_filter()
        self._list.refresh()
        self._graph.refresh()
        self._update_status()

    def _on_track_selected(self, track_id: str, display_name: str) -> None:
        self._status.showMessage(f"Selected: {display_name}")

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:  # Graph
            self._graph.on_tab_shown()
        self._update_status()

    def _update_status(self) -> None:
        count = self._conn.execute(
            "SELECT COUNT(*) FROM tracks WHERE is_available = 1"
        ).fetchone()[0]
        self._status.showMessage(f"{count} tracks in library")
