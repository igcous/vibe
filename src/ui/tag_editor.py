import sqlite3
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QLineEdit, QCompleter,
)
from PySide6.QtCore import Qt, QStringListModel

from src.db.queries import get_track_tags, tag_track, untag_track, get_all_tag_names


class TagEditorDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, track_id: str, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._track_id = track_id
        self.setWindowTitle("Edit Tags")
        self.setMinimumWidth(320)
        self.setModal(True)
        self._build_ui()
        self._reload_list()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Tags:"))
        self._tag_list = QListWidget()
        layout.addWidget(self._tag_list)

        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._on_remove)
        layout.addWidget(self._remove_btn)

        self._tag_list.currentItemChanged.connect(
            lambda cur, _: self._remove_btn.setEnabled(cur is not None)
        )

        add_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Add tag…")
        self._input.returnPressed.connect(self._on_add)
        self._completer_model = QStringListModel(get_all_tag_names(self._conn))
        completer = QCompleter(self._completer_model, self._input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._input.setCompleter(completer)
        add_row.addWidget(self._input)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _reload_list(self) -> None:
        self._tag_list.clear()
        for name in get_track_tags(self._conn, self._track_id):
            self._tag_list.addItem(name)
        self._remove_btn.setEnabled(False)

    def _on_add(self) -> None:
        name = self._input.text().strip()
        if not name:
            return
        tag_track(self._conn, self._track_id, name)
        self._input.clear()
        self._completer_model.setStringList(get_all_tag_names(self._conn))
        self._reload_list()

    def _on_remove(self) -> None:
        item = self._tag_list.currentItem()
        if item is None:
            return
        untag_track(self._conn, self._track_id, item.text())
        self._reload_list()
