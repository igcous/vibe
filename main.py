import sys
from src.db.schema import init_db
from src.db.queries import get_all_tracks
from src.audio.scanner import scan_folder
from src.ui.options_tab import _migrate_settings, get_active_db_path

_migrate_settings()
DB_PATH = get_active_db_path()


def run_scan(folder: str) -> None:
    print(f"Scanning: {folder}")

    def progress(current, total, path):
        print(f"[{current}/{total}] {path}")

    scan_folder(folder, DB_PATH, progress_callback=progress)

    conn = init_db(DB_PATH)
    tracks = get_all_tracks(conn)
    conn.close()

    print(f"\n{len(tracks)} track(s) in library:")
    for t in tracks:
        print(f"  {t['artist'] or '?'} — {t['title']}  BPM:{t['bpm']}  Key:{t['key_open']}")


def run_ui() -> None:
    from PySide6.QtWidgets import QApplication
    from src.ui.main_window import MainWindow
    from src.api.server import start_api_server

    conn = init_db(DB_PATH)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    start_api_server(DB_PATH)
    window = MainWindow(conn, DB_PATH)
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] != "--ui":
        run_scan(sys.argv[1])
    else:
        run_ui()
