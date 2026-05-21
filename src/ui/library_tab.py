import sqlite3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QStyledItemDelegate, QScrollArea, QPushButton, QFrame,
    QMenu, QMessageBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from src.db.queries import (
    get_track, update_track_metadata, get_track_tags,
    filter_tracks, get_all_tag_names, delete_tag,
)
from src.ui.tag_editor import TagEditorDialog

COLUMNS = ["Title", "Artist", "BPM", "Key", "Tags"]

_UNAVAILABLE_COLOR = QColor("#cc4444")

_TAG_BTN_STYLE = """
    QPushButton { border: 1px solid palette(mid); border-radius: 3px; padding: 2px 8px; }
    QPushButton:checked { background-color: palette(highlight); color: palette(highlighted-text); border-color: palette(highlight); }
"""


class _TitleArtistDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() not in (0, 1):
            return None
        return super().createEditor(parent, option, index)


def _write_tags_to_file(path: str, title: str, artist: str) -> None:
    try:
        from mutagen.mp3 import MP3
        from mutagen.easyid3 import EasyID3
        audio = MP3(path, ID3=EasyID3)
        audio["title"] = [title]
        audio["artist"] = [artist]
        audio.save()
    except Exception:
        pass


class LibraryTab(QWidget):
    track_selected = Signal(str, str)  # track_id, display_name

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self._conn = conn
        self._track_ids: list[str] = []
        self._loading = False
        self._tag_buttons: dict[str, QPushButton] = {}
        self._build_ui()
        self._rebuild_tag_filter()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by title or artist…")
        self._search.textChanged.connect(self._on_search)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("All tags:"))

        tag_scroll = QScrollArea()
        tag_scroll.setWidgetResizable(True)
        tag_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tag_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tag_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tag_scroll.setFixedHeight(34)

        self._tag_btn_widget = QWidget()
        self._tag_btn_layout = QHBoxLayout(self._tag_btn_widget)
        self._tag_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._tag_btn_layout.setSpacing(4)
        tag_scroll.setWidget(self._tag_btn_widget)
        tag_row.addWidget(tag_scroll, 1)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(48)
        clear_btn.clicked.connect(self._clear_tag_filter)
        tag_row.addWidget(clear_btn)
        layout.addLayout(tag_row)

        self._table = QTableWidget()
        self._table.setColumnCount(len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self._table.setItemDelegate(_TitleArtistDelegate(self._table))
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._table)

    def _rebuild_tag_filter(self) -> None:
        selected = {name for name, btn in self._tag_buttons.items() if btn.isChecked()}
        while self._tag_btn_layout.count():
            item = self._tag_btn_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._tag_buttons.clear()
        for name in get_all_tag_names(self._conn):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setStyleSheet(_TAG_BTN_STYLE)
            if name in selected:
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, n=name, b=btn: self._on_tag_context_menu(n, b.mapToGlobal(pos))
            )
            btn.toggled.connect(self._on_tag_filter_changed)
            self._tag_btn_layout.addWidget(btn)
            self._tag_buttons[name] = btn
        self._tag_btn_layout.addStretch()

    def _on_tag_context_menu(self, tag_name: str, global_pos) -> None:
        menu = QMenu(self)
        delete_action = menu.addAction(f'Delete tag "{tag_name}"')
        if menu.exec(global_pos) != delete_action:
            return
        reply = QMessageBox.question(
            self,
            "Delete tag",
            f'Delete tag "{tag_name}" from all tracks?\nThis cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_tag(self._conn, tag_name)
            self._rebuild_tag_filter()
            self.refresh()

    def _clear_tag_filter(self) -> None:
        for btn in self._tag_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self._on_tag_filter_changed()

    def _on_tag_filter_changed(self, _=None) -> None:
        self.refresh()

    def reload_connection(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._rebuild_tag_filter()
        self.refresh()

    def refresh(self) -> None:
        query = self._search.text().strip()
        selected_tags = [n for n, btn in self._tag_buttons.items() if btn.isChecked()] or None
        rows = filter_tracks(self._conn, query, selected_tags)
        self._populate(rows)

    def _on_search(self) -> None:
        self.refresh()

    def _populate(self, rows: list) -> None:
        self._loading = True
        try:
            self._table.setRowCount(0)
            self._track_ids = []

            for row in rows:
                r = self._table.rowCount()
                self._table.insertRow(r)
                self._track_ids.append(row["id"])

                available = bool(row["is_available"])
                values = [
                    row["title"] or "",
                    row["artist"] or "",
                    str(row["bpm"]) if row["bpm"] is not None else "",
                    row["key_open"] or "",
                    row["tags"] or "",
                ]
                for col, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                    if not available:
                        item.setForeground(_UNAVAILABLE_COLOR)
                    self._table.setItem(r, col, item)

            self._table.resizeColumnsToContents()
            self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        finally:
            self._loading = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        col = item.column()
        if col not in (0, 1):
            return
        row = item.row()
        if row < 0 or row >= len(self._track_ids):
            return
        track_id = self._track_ids[row]
        title = self._table.item(row, 0).text()
        artist = self._table.item(row, 1).text()
        update_track_metadata(self._conn, track_id, title, artist)
        track = get_track(self._conn, track_id)
        if track and track["path"] and track["is_available"]:
            _write_tags_to_file(track["path"], title, artist)

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        if col != 4 or row < 0 or row >= len(self._track_ids):
            return
        track_id = self._track_ids[row]
        dlg = TagEditorDialog(self._conn, track_id, parent=self)
        dlg.exec()
        self._refresh_row_tags(row, track_id)
        self._rebuild_tag_filter()

    def _refresh_row_tags(self, row: int, track_id: str) -> None:
        tags = get_track_tags(self._conn, track_id)
        tag_str = ", ".join(tags)
        self._loading = True
        try:
            item = self._table.item(row, 4)
            if item is not None:
                item.setText(tag_str)
            else:
                new_item = QTableWidgetItem(tag_str)
                new_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._table.setItem(row, 4, new_item)
        finally:
            self._loading = False

    def _on_selection_changed(self) -> None:
        rows = self._table.selectedItems()
        if not rows:
            return
        row_idx = self._table.currentRow()
        if row_idx < 0 or row_idx >= len(self._track_ids):
            return
        track_id = self._track_ids[row_idx]
        title = self._table.item(row_idx, 0).text()
        artist = self._table.item(row_idx, 1).text()
        display = f"{artist} — {title}" if artist else title
        self.track_selected.emit(track_id, display)

    def selected_track(self) -> tuple[str, str] | None:
        row_idx = self._table.currentRow()
        if row_idx < 0 or row_idx >= len(self._track_ids):
            return None
        track_id = self._track_ids[row_idx]
        title = self._table.item(row_idx, 0).text()
        artist = self._table.item(row_idx, 1).text()
        display = f"{artist} — {title}" if artist else title
        return track_id, display
