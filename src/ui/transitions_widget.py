import sqlite3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QTextEdit, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QSplitter, QMessageBox, QTabWidget,
    QListWidget, QLineEdit, QCompleter,
)
from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import QAction

from src.db.queries import (
    get_all_tracks, add_transition, get_transitions_for_track,
    delete_transition, update_transition, transition_exists,
    get_track, get_track_tags, tag_track, untag_track, get_all_tag_names,
)
from src.graph.scoring import transition_score, DEFAULT_WEIGHTS, DEFAULT_RATING_SCORES
from src.ui.options_tab import load_settings

TRANSITION_COLUMNS = ["Direction", "Track", "BPM", "Key", "Rating", "Notes"]


class TransitionsWidget(QWidget):
    transitions_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, readonly_from: bool = False, tabbed: bool = False):
        super().__init__()
        self._conn = conn
        self._readonly_from = readonly_from
        self._tabbed = tabbed
        self._from_id: str | None = None
        self._track_map: dict[str, str] = {}   # id → display name
        self._build_ui()
        self._load_tracks()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        form_widget = self._build_form_widget()
        table_widget = self._build_table_widget()

        if self._tabbed:
            self._selected_track_label = QLabel()
            self._selected_track_label.setStyleSheet("font-weight: bold; padding: 2px 2px;")
            layout.addWidget(self._selected_track_label)

            self.tab_widget = QTabWidget()
            self.tab_widget.addTab(form_widget, "Add transition")
            self.tab_widget.addTab(table_widget, "See transitions")
            self.tab_widget.addTab(self._build_track_info_widget(), "Track info")
            self.tab_widget.addTab(self._build_next_track_widget(), "Next track")
            layout.addWidget(self.tab_widget)
        else:
            splitter = QSplitter(Qt.Orientation.Vertical)
            splitter.addWidget(form_widget)
            splitter.addWidget(table_widget)
            splitter.setSizes([200, 400])
            layout.addWidget(splitter)

    def _build_form_widget(self) -> QWidget:
        form_box = QWidget()
        form_layout = QFormLayout(form_box)
        form_layout.setSpacing(6)

        if not self._readonly_from:
            self._from_combo = QComboBox()
            self._from_combo.setMinimumWidth(300)
            self._from_combo.currentIndexChanged.connect(self._on_from_changed)
            form_layout.addRow("From:", self._from_combo)

        self._to_combo = QComboBox()
        self._to_combo.setMinimumWidth(300)
        form_layout.addRow("To:", self._to_combo)

        self._rating = QSpinBox()
        self._rating.setRange(1, 3)
        self._rating.setValue(2)
        form_layout.addRow("Rating (1–3):", self._rating)

        self._notes = QTextEdit()
        self._notes.setMaximumHeight(60)
        self._notes.setPlaceholderText("Optional notes about this transition…")
        form_layout.addRow("Notes:", self._notes)

        self._both_ways_cb = QCheckBox("Add in both ways")
        form_layout.addRow("", self._both_ways_cb)

        save_btn = QPushButton("Save Transition")
        save_btn.clicked.connect(self._save_transition)
        form_layout.addRow("", save_btn)

        return form_box

    def _build_table_widget(self) -> QWidget:
        view_box = QWidget()
        view_layout = QVBoxLayout(view_box)

        self._table = QTableWidget()
        self._table.setColumnCount(len(TRANSITION_COLUMNS))
        self._table.setHorizontalHeaderLabels(TRANSITION_COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked)
        self._table.cellChanged.connect(self._on_transition_edited)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        delete_action = QAction("Delete transition", self._table)
        delete_action.triggered.connect(self._delete_selected_transition)
        self._table.addAction(delete_action)
        view_layout.addWidget(self._table)

        return view_box

    def _build_track_info_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(4)
        self._info_bpm = QLabel("—")
        self._info_key = QLabel("—")
        form.addRow("BPM:", self._info_bpm)
        form.addRow("Key:", self._info_key)
        layout.addLayout(form)

        layout.addWidget(QLabel("Tags:"))
        self._tag_list = QListWidget()
        self._tag_list.currentItemChanged.connect(
            lambda cur, _: self._tag_remove_btn.setEnabled(cur is not None)
        )
        layout.addWidget(self._tag_list)

        self._tag_remove_btn = QPushButton("Remove selected")
        self._tag_remove_btn.setEnabled(False)
        self._tag_remove_btn.clicked.connect(self._on_tag_remove)
        layout.addWidget(self._tag_remove_btn)

        add_row = QHBoxLayout()
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("Add tag…")
        self._tag_input.returnPressed.connect(self._on_tag_add)
        self._tag_completer_model = QStringListModel()
        completer = QCompleter(self._tag_completer_model, self._tag_input)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._tag_input.setCompleter(completer)
        add_row.addWidget(self._tag_input)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_tag_add)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        layout.addStretch()
        return w

    def _build_next_track_widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        self._next_table = QTableWidget()
        self._next_table.setColumnCount(3)
        self._next_table.setHorizontalHeaderLabels(["Track", "Score", "Factor"])
        self._next_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._next_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._next_table.setAlternatingRowColors(True)
        self._next_table.verticalHeader().setVisible(False)
        h = self._next_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._next_table)
        return w

    _FACTOR_LABELS = {"key": "Key", "bpm": "BPM", "tags": "Tags", "rating": "Rating", "previous": "Previous"}

    def _refresh_next_track(self) -> None:
        if not hasattr(self, '_next_table'):
            return
        self._next_table.setRowCount(0)
        if not self._from_id:
            return

        settings = load_settings()
        weights = settings.get("graph_weights", DEFAULT_WEIGHTS)
        include_ratings = bool(settings.get("include_user_ratings", False))
        raw_mults = settings.get("rating_scores", {})
        rating_scores = (
            {int(k): v for k, v in raw_mults.items()} if raw_mults else DEFAULT_RATING_SCORES
        )

        current_row = self._conn.execute("""
            SELECT t.*, GROUP_CONCAT(tg.name, ', ') AS tags
            FROM tracks t
            LEFT JOIN track_tags tt ON tt.track_id = t.id
            LEFT JOIN tags tg ON tg.id = tt.tag_id
            WHERE t.id = ?
            GROUP BY t.id
        """, (self._from_id,)).fetchone()
        if not current_row:
            return

        incoming = self._conn.execute(
            "SELECT from_track AS track_id, rating FROM transitions WHERE to_track = ?",
            (self._from_id,)
        ).fetchall()
        outgoing = self._conn.execute(
            "SELECT to_track AS track_id, rating FROM transitions WHERE from_track = ?",
            (self._from_id,)
        ).fetchall()
        # Build map: track_id → (rating, factor_key); outgoing takes priority
        rating_map: dict[str, tuple[int, str]] = {}
        for row in incoming:
            rating_map[row["track_id"]] = (row["rating"], "previous")
        for row in outgoing:
            rating_map[row["track_id"]] = (row["rating"], "rating")

        candidates = self._conn.execute("""
            SELECT t.*, GROUP_CONCAT(tg.name, ', ') AS tags
            FROM tracks t
            LEFT JOIN track_tags tt ON tt.track_id = t.id
            LEFT JOIN tags tg ON tg.id = tt.tag_id
            WHERE t.id != ? AND t.is_available = 1
            GROUP BY t.id
        """, (self._from_id,)).fetchall()

        def parse_tags(row) -> list[str]:
            raw = row["tags"] or ""
            return [t.strip() for t in raw.split(",") if t.strip()]

        current_dict = dict(current_row)
        current_dict["tags"] = parse_tags(current_row)

        results = []
        for c in candidates:
            c_dict = dict(c)
            c_dict["tags"] = parse_tags(c)
            entry = rating_map.get(c["id"])
            user_rating = entry[0] if entry else None
            score, dominant, _ = transition_score(
                current_dict, c_dict, user_rating, weights,
                include_user_ratings=include_ratings,
                rating_scores=rating_scores,
            )
            factor = entry[1] if entry and include_ratings else dominant
            artist = c["artist"] or ""
            title = c["title"] or ""
            display = f"{artist} — {title}" if artist else title
            results.append((score, display, self._FACTOR_LABELS.get(factor, factor)))

        results.sort(key=lambda x: x[0], reverse=True)
        for score, display, factor_label in results[:5]:
            r = self._next_table.rowCount()
            self._next_table.insertRow(r)
            for col, val in enumerate([display, f"{score:.0%}", factor_label]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._next_table.setItem(r, col, item)

    def _refresh_track_info(self) -> None:
        if not hasattr(self, '_info_bpm') or not self._from_id:
            return
        track = get_track(self._conn, self._from_id)
        if track:
            self._info_bpm.setText(str(track["bpm"]) if track["bpm"] is not None else "—")
            self._info_key.setText(track["key_open"] or "—")
        else:
            self._info_bpm.setText("—")
            self._info_key.setText("—")
        self._reload_tag_list()

    def _reload_tag_list(self) -> None:
        self._tag_list.clear()
        if self._from_id:
            for name in get_track_tags(self._conn, self._from_id):
                self._tag_list.addItem(name)
        self._tag_remove_btn.setEnabled(False)
        self._tag_completer_model.setStringList(get_all_tag_names(self._conn))

    def _on_tag_add(self) -> None:
        name = self._tag_input.text().strip()
        if not name or not self._from_id:
            return
        tag_track(self._conn, self._from_id, name)
        self._tag_input.clear()
        self._reload_tag_list()
        self.transitions_changed.emit()

    def _on_tag_remove(self) -> None:
        item = self._tag_list.currentItem()
        if item is None or not self._from_id:
            return
        untag_track(self._conn, self._from_id, item.text())
        self._reload_tag_list()
        self.transitions_changed.emit()

    def _load_tracks(self) -> None:
        tracks = get_all_tracks(self._conn)
        self._track_map = {}

        self._to_combo.blockSignals(True)
        self._to_combo.clear()

        if not self._readonly_from:
            self._from_combo.blockSignals(True)
            self._from_combo.clear()

        for t in tracks:
            artist = t["artist"] or ""
            title = t["title"] or ""
            display = f"{artist} — {title}" if artist else title
            self._track_map[t["id"]] = display
            if not self._readonly_from:
                self._from_combo.addItem(display, userData=t["id"])
            self._to_combo.addItem(display, userData=t["id"])

        self._to_combo.blockSignals(False)
        if not self._readonly_from:
            self._from_combo.blockSignals(False)

        self._refresh_transitions_table()
        self._refresh_next_track()

    def _on_from_changed(self) -> None:
        self._refresh_transitions_table()

    def _refresh_transitions_table(self) -> None:
        track_id = self._from_id if self._readonly_from else self._from_combo.currentData()
        self._table.blockSignals(True)
        if not track_id:
            self._table.setRowCount(0)
            self._table.blockSignals(False)
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
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if col not in (4, 5):
                    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self._table.setItem(r, col, item)

        for row in data["outgoing"]:
            add_row("→", row["to_title"], row["to_artist"] or "", row)
        for row in data["incoming"]:
            add_row("←", row["from_title"], row["from_artist"] or "", row)

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.blockSignals(False)

    def _on_transition_edited(self, row: int, col: int) -> None:
        if col not in (4, 5):
            return
        id_item = self._table.item(row, 0)
        if id_item is None:
            return
        transition_id = id_item.data(Qt.ItemDataRole.UserRole)
        if transition_id is None:
            return

        rating_item = self._table.item(row, 4)
        notes_item = self._table.item(row, 5)

        try:
            rating = max(1, min(3, int(rating_item.text())))
        except (ValueError, AttributeError):
            rating = 1

        notes = notes_item.text() if notes_item else ""

        self._table.blockSignals(True)
        rating_item.setText(str(rating))
        self._table.blockSignals(False)

        update_transition(self._conn, transition_id, rating, notes)
        self.transitions_changed.emit()

    def _save_transition(self) -> None:
        from_id = self._from_id if self._readonly_from else self._from_combo.currentData()
        to_id = self._to_combo.currentData()

        if not from_id or not to_id:
            QMessageBox.warning(self, "Missing tracks", "Select both a From and To track.")
            return
        if from_id == to_id:
            QMessageBox.warning(self, "Invalid", "From and To tracks must be different.")
            return
        if transition_exists(self._conn, from_id, to_id):
            QMessageBox.warning(self, "Duplicate", "A transition from this track to the selected track already exists.")
            return

        notes = self._notes.toPlainText().strip()
        rating = self._rating.value()
        add_transition(self._conn, from_id, to_id, rating, notes)
        if self._both_ways_cb.isChecked() and not transition_exists(self._conn, to_id, from_id):
            add_transition(self._conn, to_id, from_id, rating, notes)
        self._notes.clear()
        self._refresh_transitions_table()
        self.transitions_changed.emit()

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
            self._refresh_transitions_table()
            self.transitions_changed.emit()

    def set_from_track(self, track_id: str) -> None:
        if self._readonly_from:
            self._from_id = track_id
            name = self._track_map.get(track_id, track_id)
            if hasattr(self, '_selected_track_label'):
                self._selected_track_label.setText(name)
            self._refresh_transitions_table()
            self._refresh_track_info()
            self._refresh_next_track()
        else:
            idx = self._from_combo.findData(track_id)
            if idx >= 0:
                self._from_combo.setCurrentIndex(idx)

    def refresh(self) -> None:
        self._load_tracks()
