import sqlite3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction

from src.db.queries import get_all_transitions, delete_transition


class ListTab(QWidget):
    transitions_changed = Signal()

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self._conn = conn
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by title or artist…")
        self._search.textChanged.connect(self.refresh)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["From", "To", "Rating"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        delete_action = QAction("Delete transition", self._table)
        delete_action.triggered.connect(self._delete_selected_transition)
        self._table.addAction(delete_action)
        layout.addWidget(self._table)

    def reload_connection(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.refresh()

    def refresh(self) -> None:
        rows = get_all_transitions(self._conn, self._search.text().strip())
        self._table.setRowCount(0)
        for row in rows:
            from_display = f"{row['from_artist']} — {row['from_title']}" if row['from_artist'] else row['from_title']
            to_display = f"{row['to_artist']} — {row['to_title']}" if row['to_artist'] else row['to_title']
            r = self._table.rowCount()
            self._table.insertRow(r)
            stars = "★" * row['rating'] + "☆" * (3 - row['rating'])
            for col, val in enumerate([from_display, to_display, stars]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row['id'])
                self._table.setItem(r, col, item)

    def _delete_selected_transition(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        transition_id = self._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if transition_id is None:
            return
        confirm = QMessageBox.question(
            self, "Delete transition",
            "Delete this transition?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            delete_transition(self._conn, transition_id)
            self.refresh()
            self.transitions_changed.emit()
