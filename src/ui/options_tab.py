import json
import os
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QProgressBar, QGroupBox,
    QDoubleSpinBox,
)
from PySide6.QtCore import Qt, Signal, QObject

SETTINGS_PATH = "settings.json"


def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(settings: dict) -> None:
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


class _ScanSignals(QObject):
    progress = Signal(int, int, str)
    finished = Signal()
    error = Signal(str)


_WEIGHT_LABELS = [
    ("key",  "Key compatibility"),
    ("bpm",  "BPM match"),
    ("tags", "Tag similarity"),
    ("user", "User transitions"),
]
_DEFAULT_WEIGHTS = {"key": 0.45, "bpm": 0.25, "tags": 0.15, "user": 0.15}


class OptionsTab(QWidget):
    scan_finished = Signal()
    weights_changed = Signal()

    def __init__(self, db_path: str):
        super().__init__()
        self._db_path = db_path
        self._settings = load_settings()
        self._scanning = False
        self._signals: _ScanSignals | None = None
        self._weight_inputs: dict[str, QDoubleSpinBox] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        group = QGroupBox("Library Scan")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(10)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Music folder:"))
        self._folder_input = QLineEdit()
        self._folder_input.setPlaceholderText("Select a folder to scan…")
        self._folder_input.setText(self._settings.get("scan_folder", ""))
        self._folder_input.textChanged.connect(self._on_folder_changed)
        folder_row.addWidget(self._folder_input, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(browse_btn)
        group_layout.addLayout(folder_row)

        self._auto_scan_cb = QCheckBox("Scan automatically on start-up")
        self._auto_scan_cb.setChecked(bool(self._settings.get("auto_scan", False)))
        self._auto_scan_cb.toggled.connect(self._on_auto_scan_toggled)
        group_layout.addWidget(self._auto_scan_cb)

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setFixedWidth(80)
        self._scan_btn.clicked.connect(self._on_scan)
        group_layout.addWidget(self._scan_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        group_layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        group_layout.addWidget(self._status_label)

        layout.addWidget(group)
        layout.addWidget(self._build_weights_group())
        layout.addStretch()

    def _build_weights_group(self) -> QGroupBox:
        group = QGroupBox("Graph Weights")
        form = QFormLayout(group)
        form.setSpacing(8)
        saved = self._settings.get("graph_weights", _DEFAULT_WEIGHTS)
        for key, label in _WEIGHT_LABELS:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(saved.get(key, _DEFAULT_WEIGHTS[key]))
            spin.valueChanged.connect(self._on_weight_changed)
            form.addRow(label + ":", spin)
            self._weight_inputs[key] = spin
        self._weight_sum_label = QLabel(self._weight_sum_text())
        self._weight_sum_label.setStyleSheet("color: #888;")
        form.addRow("", self._weight_sum_label)
        return group

    def _weight_sum_text(self) -> str:
        total = sum(s.value() for s in self._weight_inputs.values()) if self._weight_inputs else 1.0
        return f"Sum: {total:.2f}  (aim for 1.00)"

    def _on_weight_changed(self) -> None:
        weights = {k: round(s.value(), 2) for k, s in self._weight_inputs.items()}
        self._weight_sum_label.setText(self._weight_sum_text())
        self._settings["graph_weights"] = weights
        save_settings(self._settings)
        self.weights_changed.emit()

    def _on_browse(self) -> None:
        start = self._folder_input.text() or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder", start)
        if folder:
            self._folder_input.setText(folder)

    def _on_folder_changed(self, text: str) -> None:
        self._settings["scan_folder"] = text
        save_settings(self._settings)

    def _on_auto_scan_toggled(self, checked: bool) -> None:
        self._settings["auto_scan"] = checked
        save_settings(self._settings)

    def _on_scan(self) -> None:
        if self._scanning:
            return
        folder = self._folder_input.text().strip()
        if not folder or not os.path.isdir(folder):
            self._status_label.setText("Please select a valid folder first.")
            return
        self._start_scan(folder)

    def trigger_auto_scan(self) -> None:
        if not self._settings.get("auto_scan"):
            return
        folder = self._settings.get("scan_folder", "").strip()
        if folder and os.path.isdir(folder):
            self._start_scan(folder)

    def _start_scan(self, folder: str) -> None:
        self._scanning = True
        self._scan_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._status_label.setText("Scanning…")

        signals = _ScanSignals()
        signals.progress.connect(self._on_progress)
        signals.finished.connect(self._on_scan_done)
        signals.error.connect(self._on_scan_error)
        self._signals = signals  # keep alive for the duration of the scan

        db_path = self._db_path

        def run() -> None:
            try:
                from src.audio.scanner import scan_folder
                scan_folder(folder, db_path, progress_callback=signals.progress.emit)
                signals.finished.emit()
            except Exception as exc:
                signals.error.emit(str(exc))

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, current: int, total: int, path: str) -> None:
        self._progress_bar.setMaximum(max(total, 1))
        self._progress_bar.setValue(current)
        self._status_label.setText(f"[{current}/{total}] {os.path.basename(path)}")

    def _on_scan_done(self) -> None:
        self._scanning = False
        self._scan_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_label.setText("Scan complete.")
        self.scan_finished.emit()

    def _on_scan_error(self, message: str) -> None:
        self._scanning = False
        self._scan_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._status_label.setText(f"Error: {message}")
