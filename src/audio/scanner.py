import os
import sqlite3
from datetime import datetime
from typing import Callable

from src.db.schema import init_db
from src.db.queries import upsert_track, mark_all_unavailable, get_all_tracks, track_exists_analyzed, touch_track
from src.audio.fingerprint import fingerprint
from src.audio.analysis import analyze_audio, read_metadata


def scan_folder(
    folder_path: str,
    db_path: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    conn = init_db(db_path)

    mp3_files = _find_mp3s(folder_path)
    total = len(mp3_files)

    # Mark all existing tracks unavailable; re-mark available as we find them
    mark_all_unavailable(conn)

    for i, path in enumerate(mp3_files, start=1):
        if progress_callback:
            progress_callback(i, total, path)
        _process_file(conn, path)

    conn.close()


def _find_mp3s(folder_path: str) -> list[str]:
    results = []
    for root, _, files in os.walk(folder_path):
        for name in files:
            if name.lower().endswith(".mp3"):
                results.append(os.path.join(root, name))
    return results


def _process_file(conn: sqlite3.Connection, path: str) -> None:
    fp = fingerprint(path)
    if not fp:
        return

    if track_exists_analyzed(conn, fp):
        touch_track(conn, fp, path)
        return

    metadata = read_metadata(path)
    analysis = analyze_audio(path)

    upsert_track(conn, {
        "id": fp,
        "path": path,
        "title": metadata["title"],
        "artist": metadata["artist"],
        **analysis,
        "last_seen": datetime.now().isoformat(),
    })
