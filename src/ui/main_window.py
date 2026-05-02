import sqlite3
from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar
from PySide6.QtCore import Qt

from src.ui.library_tab import LibraryTab
from src.ui.transitions_tab import TransitionsTab


class MainWindow(QMainWindow):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self._conn = conn
        self.setWindowTitle("DJ Transition Companion")
        self.resize(1100, 700)

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._library = LibraryTab(conn)
        self._transitions = TransitionsTab(conn)

        self._tabs.addTab(self._library, "Library")
        self._tabs.addTab(self._transitions, "Transitions")

        self._library.track_selected.connect(self._on_track_selected)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._update_status()

    def _on_track_selected(self, track_id: str, display_name: str) -> None:
        self._status.showMessage(f"Selected: {display_name}")

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            # Sync library selection → transitions "from" selector
            sel = self._library.selected_track()
            if sel:
                self._transitions.set_from_track(sel[0])
            self._transitions.refresh()
        self._update_status()

    def _update_status(self) -> None:
        count = self._conn.execute(
            "SELECT COUNT(*) FROM tracks WHERE is_available = 1"
        ).fetchone()[0]
        self._status.showMessage(f"{count} tracks in library")
