import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable

from src.db.schema import init_db
from src.db.queries import upsert_track, mark_all_unavailable, get_all_tracks, track_exists_analyzed, touch_track, tag_track
from src.audio.fingerprint import fingerprint
from src.audio.analysis import analyze_audio, read_metadata


def scan_folder(
    folder_path: str,
    db_path: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
    auto_tag: bool = False,
) -> None:
    conn = init_db(db_path)

    mp3_files = _find_mp3s(folder_path)
    total = len(mp3_files)

    # Mark all existing tracks unavailable; re-mark available as we find them
    mark_all_unavailable(conn)

    for i, path in enumerate(mp3_files, start=1):
        if progress_callback:
            progress_callback(i, total, path)
        _process_file(conn, path, auto_tag=auto_tag)

    conn.close()


def _find_mp3s(folder_path: str) -> list[str]:
    results = []
    for root, _, files in os.walk(folder_path):
        for name in files:
            if name.lower().endswith(".mp3"):
                results.append(os.path.join(root, name))
    return results


def _process_file(conn: sqlite3.Connection, path: str, auto_tag: bool = False) -> None:
    fp = fingerprint(path)
    if not fp:
        return

    if track_exists_analyzed(conn, fp):
        touch_track(conn, fp, path)
        if auto_tag:
            _apply_folder_tag(conn, fp, path)
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

    if auto_tag:
        _apply_folder_tag(conn, fp, path)


def _apply_folder_tag(conn: sqlite3.Connection, track_id: str, path: str) -> None:
    folder_tag = Path(path).parent.name.strip()
    if folder_tag:
        tag_track(conn, track_id, folder_tag)
