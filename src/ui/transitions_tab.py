import sqlite3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QGroupBox, QSplitter, QMessageBox,
)
from PySide6.QtCore import Qt

from src.db.queries import (
    get_all_tracks, add_transition, get_transitions_for_track,
)

TRANSITION_COLUMNS = ["Direction", "Track", "BPM", "Key", "Rating", "Notes"]


class TransitionsTab(QWidget):
    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self._conn = conn
        self._track_map: dict[str, str] = {}   # id → display name
        self._build_ui()
        self._load_tracks()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Create transition form ──────────────────────────────────────────
        form_box = QGroupBox("Add Transition")
        form_layout = QFormLayout(form_box)
        form_layout.setSpacing(6)

        self._from_combo = QComboBox()
        self._from_combo.setMinimumWidth(300)
        self._from_combo.currentIndexChanged.connect(self._on_from_changed)
        form_layout.addRow("From:", self._from_combo)

        self._to_combo = QComboBox()
        self._to_combo.setMinimumWidth(300)
        form_layout.addRow("To:", self._to_combo)

        self._rating = QSpinBox()
        self._rating.setRange(1, 5)
        self._rating.setValue(3)
        form_layout.addRow("Rating (1–5):", self._rating)

        self._notes = QTextEdit()
        self._notes.setMaximumHeight(60)
        self._notes.setPlaceholderText("Optional notes about this transition…")
        form_layout.addRow("Notes:", self._notes)

        save_btn = QPushButton("Save Transition")
        save_btn.clicked.connect(self._save_transition)
        form_layout.addRow("", save_btn)

        splitter.addWidget(form_box)

        # ── Existing transitions table ──────────────────────────────────────
        view_box = QGroupBox("Transitions for selected track")
        view_layout = QVBoxLayout(view_box)

        self._table = QTableWidget()
        self._table.setColumnCount(len(TRANSITION_COLUMNS))
        self._table.setHorizontalHeaderLabels(TRANSITION_COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        view_layout.addWidget(self._table)

        splitter.addWidget(view_box)
        splitter.setSizes([200, 400])
        layout.addWidget(splitter)

    def _load_tracks(self) -> None:
        tracks = get_all_tracks(self._conn)
        self._track_map = {}

        self._from_combo.blockSignals(True)
        self._to_combo.blockSignals(True)
        self._from_combo.clear()
        self._to_combo.clear()

        for t in tracks:
            artist = t["artist"] or ""
            title = t["title"] or ""
            display = f"{artist} — {title}" if artist else title
            self._track_map[t["id"]] = display
            self._from_combo.addItem(display, userData=t["id"])
            self._to_combo.addItem(display, userData=t["id"])

        self._from_combo.blockSignals(False)
        self._to_combo.blockSignals(False)

        self._refresh_transitions_table()

    def _on_from_changed(self) -> None:
        self._refresh_transitions_table()

    def _refresh_transitions_table(self) -> None:
        track_id = self._from_combo.currentData()
        if not track_id:
            self._table.setRowCount(0)
            return

        data = get_transitions_for_track(self._conn, track_id)
        self._table.setRowCount(0)

        def add_row(direction: str, other_title: str, other_artist: str, row: sqlite3.Row) -> None:
            r = self._table.rowCount()
            self._table.insertRow(r)
            display = f"{other_artist} — {other_title}" if other_artist else other_title
            track_row = self._conn.execute(
                "SELECT bpm, key_open FROM tracks WHERE id = ?",
                (row["to_track"] if direction == "→" else row["from_track"],)
            ).fetchone()
            bpm = str(track_row["bpm"]) if track_row and track_row["bpm"] else ""
            key = track_row["key_open"] if track_row else ""
            values = [direction, display, bpm, key or "", str(row["rating"]), row["notes"] or ""]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._table.setItem(r, col, item)

        for row in data["outgoing"]:
            add_row("→", row["to_title"], row["to_artist"] or "", row)
        for row in data["incoming"]:
            add_row("←", row["from_title"], row["from_artist"] or "", row)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

    def _save_transition(self) -> None:
        from_id = self._from_combo.currentData()
        to_id = self._to_combo.currentData()

        if not from_id or not to_id:
            QMessageBox.warning(self, "Missing tracks", "Select both a From and To track.")
            return
        if from_id == to_id:
            QMessageBox.warning(self, "Invalid", "From and To tracks must be different.")
            return

        add_transition(
            self._conn,
            from_id,
            to_id,
            self._rating.value(),
            self._notes.toPlainText().strip(),
        )
        self._notes.clear()
        self._refresh_transitions_table()

    def set_from_track(self, track_id: str) -> None:
        idx = self._from_combo.findData(track_id)
        if idx >= 0:
            self._from_combo.setCurrentIndex(idx)

    def refresh(self) -> None:
        self._load_tracks()
