import json
import os
import re
import sys
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QFileDialog, QProgressBar, QGroupBox,
    QComboBox, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QObject

# Project root — three levels up from this file (src/ui/options_tab.py).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _app_data_dir() -> str:
    """User data directory — platform-standard when bundled, project root in dev."""
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base = os.path.join(os.path.expanduser("~"), ".local", "share")
        d = os.path.join(base, "dj-companion")
        os.makedirs(d, exist_ok=True)
        return d
    return _PROJECT_ROOT


_DATA_DIR = _app_data_dir()
SETTINGS_PATH = os.path.join(_DATA_DIR, "settings.json")

_PROFILE_KEYS = {"scan_folder", "auto_scan", "auto_tagger"}


# ── Raw config I/O ────────────────────────────────────────────────────────────

def _load_raw_config() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_raw_config(config: dict) -> None:
    with open(SETTINGS_PATH, "w") as f:
        json.dump(config, f, indent=2)


# ── Migration ─────────────────────────────────────────────────────────────────

def _migrate_settings() -> None:
    """One-time upgrade: wrap flat settings into a Default profile."""
    config = _load_raw_config()
    if "profiles" in config:
        return
    profile_data = {
        "db_path": os.path.join(_DATA_DIR, "library.db"),
        "scan_folder": config.pop("scan_folder", ""),
        "auto_scan": config.pop("auto_scan", False),
    }
    config["profiles"] = {"Default": profile_data}
    config["current_profile"] = "Default"
    _save_raw_config(config)


# ── Public settings API (backward-compatible) ─────────────────────────────────

def load_settings() -> dict:
    """Returns merged global + active profile settings."""
    config = _load_raw_config()
    profile_name = config.get("current_profile", "Default")
    profile_data = config.get("profiles", {}).get(profile_name, {})
    result = {k: v for k, v in config.items() if k not in ("profiles", "current_profile")}
    result.update(profile_data)
    return result


def save_settings(settings: dict) -> None:
    """Routes per-profile keys into the active profile; global keys stay at top level."""
    config = _load_raw_config()
    profile_name = config.get("current_profile", "Default")
    profiles = config.setdefault("profiles", {})
    profile = profiles.setdefault(profile_name, {})
    for k, v in settings.items():
        if k in _PROFILE_KEYS:
            profile[k] = v
        else:
            config[k] = v
    _save_raw_config(config)


def get_active_db_path() -> str:
    config = _load_raw_config()
    profile_name = config.get("current_profile", "Default")
    db_path = config.get("profiles", {}).get(profile_name, {}).get("db_path", "library.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(_DATA_DIR, db_path)
    # Self-heal a stale absolute path from another machine (e.g. a Linux path
    # carried to Windows): if its directory can't exist here, fall back to the
    # data dir keeping just the filename.
    parent = os.path.dirname(db_path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            db_path = os.path.join(_DATA_DIR, os.path.basename(db_path))
    return db_path


# ── DB filename helpers ───────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "profile"


def _unique_db_path(name: str, existing_paths: set[str]) -> str:
    base = _slugify(name)
    candidate = os.path.join(_DATA_DIR, f"{base}.db")
    n = 2
    while candidate in existing_paths or os.path.exists(candidate):
        candidate = os.path.join(_DATA_DIR, f"{base}_{n}.db")
        n += 1
    return candidate


# ── Scan signals ─────────────────────────────────────────────────────────────

class _ScanSignals(QObject):
    progress = Signal(int, int, str)
    finished = Signal()
    error = Signal(str)


# ── Options tab ───────────────────────────────────────────────────────────────

class OptionsTab(QWidget):
    scan_finished = Signal()
    profile_switched = Signal()

    def __init__(self, db_path: str):
        super().__init__()
        self._db_path = db_path
        self._settings = load_settings()
        self._scanning = False
        self._signals: _ScanSignals | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Profiles ─────────────────────────────────────────────────────────
        profiles_box = QGroupBox("Profiles")
        profiles_layout = QVBoxLayout(profiles_box)
        profiles_layout.setSpacing(8)

        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel("Active profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        combo_row.addWidget(self._profile_combo, 1)
        profiles_layout.addLayout(combo_row)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("New Profile…")
        new_btn.clicked.connect(self._on_new_profile)
        btn_row.addWidget(new_btn)
        self._delete_btn = QPushButton("Delete Profile…")
        self._delete_btn.clicked.connect(self._on_delete_profile)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        profiles_layout.addLayout(btn_row)

        layout.addWidget(profiles_box)

        # ── Library scan ─────────────────────────────────────────────────────
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

        self._auto_tagger_cb = QCheckBox("Auto-tagger (tag tracks by folder name)")
        self._auto_tagger_cb.setChecked(bool(self._settings.get("auto_tagger", False)))
        self._auto_tagger_cb.setToolTip("Assigns the immediate parent folder name as a tag to each scanned track.")
        self._auto_tagger_cb.toggled.connect(self._on_auto_tagger_toggled)
        group_layout.addWidget(self._auto_tagger_cb)

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
        layout.addStretch()

        self._populate_profile_combo()

    # ── Profile combo helpers ─────────────────────────────────────────────────

    def _populate_profile_combo(self) -> None:
        config = _load_raw_config()
        current = config.get("current_profile", "Default")
        names = list(config.get("profiles", {}).keys())

        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for name in names:
            self._profile_combo.addItem(name)
        idx = self._profile_combo.findText(current)
        if idx >= 0:
            self._profile_combo.setCurrentIndex(idx)
        self._profile_combo.blockSignals(False)

        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        self._delete_btn.setEnabled(len(names) > 1)

    def _on_profile_selected(self, index: int) -> None:
        name = self._profile_combo.itemText(index)
        if not name:
            return
        config = _load_raw_config()
        config["current_profile"] = name
        _save_raw_config(config)

        self._db_path = get_active_db_path()
        self._settings = load_settings()

        # Refresh scan UI fields to reflect new profile
        self._folder_input.blockSignals(True)
        self._folder_input.setText(self._settings.get("scan_folder", ""))
        self._folder_input.blockSignals(False)
        self._auto_scan_cb.blockSignals(True)
        self._auto_scan_cb.setChecked(bool(self._settings.get("auto_scan", False)))
        self._auto_scan_cb.blockSignals(False)
        self._auto_tagger_cb.blockSignals(True)
        self._auto_tagger_cb.setChecked(bool(self._settings.get("auto_tagger", False)))
        self._auto_tagger_cb.blockSignals(False)

        self._delete_btn.setEnabled(len(config.get("profiles", {})) > 1)
        self.profile_switched.emit()

    # ── New / delete profile ──────────────────────────────────────────────────

    def _on_new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        name = name.strip()
        if not ok or not name:
            return
        config = _load_raw_config()
        profiles = config.get("profiles", {})
        if name in profiles:
            QMessageBox.warning(self, "Duplicate", f'A profile named "{name}" already exists.')
            return
        existing_paths = {p.get("db_path", "") for p in profiles.values()}
        db_path = _unique_db_path(name, existing_paths)
        profiles[name] = {"db_path": db_path, "scan_folder": "", "auto_scan": False}
        config["profiles"] = profiles
        config["current_profile"] = name
        _save_raw_config(config)

        self._db_path = db_path
        self._settings = load_settings()

        # Rebuild combo and select new profile without triggering _on_profile_selected
        self._profile_combo.currentIndexChanged.disconnect(self._on_profile_selected)
        self._profile_combo.blockSignals(True)
        self._profile_combo.addItem(name)
        self._profile_combo.setCurrentText(name)
        self._profile_combo.blockSignals(False)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)

        self._folder_input.blockSignals(True)
        self._folder_input.setText("")
        self._folder_input.blockSignals(False)
        self._auto_scan_cb.blockSignals(True)
        self._auto_scan_cb.setChecked(False)
        self._auto_scan_cb.blockSignals(False)
        self._auto_tagger_cb.blockSignals(True)
        self._auto_tagger_cb.setChecked(False)
        self._auto_tagger_cb.blockSignals(False)

        self._delete_btn.setEnabled(len(config["profiles"]) > 1)
        self.profile_switched.emit()

    def _on_delete_profile(self) -> None:
        config = _load_raw_config()
        profiles = config.get("profiles", {})
        if len(profiles) <= 1:
            return
        name = config.get("current_profile", "")
        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f'Delete profile "{name}"?\n\nThis will permanently remove all tracks and transitions in its library.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        db_file = profiles[name].get("db_path", "")
        del profiles[name]
        new_current = next(iter(profiles))
        config["current_profile"] = new_current
        _save_raw_config(config)

        if db_file and os.path.exists(db_file):
            try:
                os.remove(db_file)
            except OSError:
                pass

        self._db_path = get_active_db_path()
        self._settings = load_settings()

        self._profile_combo.currentIndexChanged.disconnect(self._on_profile_selected)
        self._profile_combo.blockSignals(True)
        idx = self._profile_combo.findText(name)
        if idx >= 0:
            self._profile_combo.removeItem(idx)
        self._profile_combo.setCurrentText(new_current)
        self._profile_combo.blockSignals(False)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)

        self._folder_input.blockSignals(True)
        self._folder_input.setText(self._settings.get("scan_folder", ""))
        self._folder_input.blockSignals(False)
        self._auto_scan_cb.blockSignals(True)
        self._auto_scan_cb.setChecked(bool(self._settings.get("auto_scan", False)))
        self._auto_scan_cb.blockSignals(False)
        self._auto_tagger_cb.blockSignals(True)
        self._auto_tagger_cb.setChecked(bool(self._settings.get("auto_tagger", False)))
        self._auto_tagger_cb.blockSignals(False)

        self._delete_btn.setEnabled(len(profiles) > 1)
        self.profile_switched.emit()

    # ── Scan UI ───────────────────────────────────────────────────────────────

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

    def _on_auto_tagger_toggled(self, checked: bool) -> None:
        self._settings["auto_tagger"] = checked
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
        self._settings = load_settings()
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
        self._signals = signals

        db_path = self._db_path

        auto_tag = bool(self._settings.get("auto_tagger", False))

        def run() -> None:
            try:
                from src.audio.scanner import scan_folder
                scan_folder(folder, db_path, progress_callback=signals.progress.emit, auto_tag=auto_tag)
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

    def reload_db_path(self, db_path: str) -> None:
        self._db_path = db_path
        self._settings = load_settings()
