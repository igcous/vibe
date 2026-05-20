import sqlite3
from datetime import datetime
from typing import Any


def upsert_track(conn: sqlite3.Connection, track: dict[str, Any]) -> None:
    conn.execute("""
        INSERT INTO tracks (id, path, title, artist, bpm, key_open, key_strength, is_available, last_seen)
        VALUES (:id, :path, :title, :artist, :bpm, :key_open, :key_strength, 1, :last_seen)
        ON CONFLICT(id) DO UPDATE SET
            path         = excluded.path,
            title        = excluded.title,
            artist       = excluded.artist,
            bpm          = excluded.bpm,
            key_open     = excluded.key_open,
            key_strength = excluded.key_strength,
            is_available = 1,
            last_seen    = excluded.last_seen
    """, {**track, "last_seen": track.get("last_seen", datetime.now().isoformat())})
    conn.commit()


def get_track(conn: sqlite3.Connection, track_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()


def get_all_tracks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM tracks ORDER BY artist, title").fetchall()


def get_all_tracks_with_tags(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("""
        SELECT t.*, GROUP_CONCAT(tg.name, ', ') AS tags
        FROM tracks t
        LEFT JOIN track_tags tt ON tt.track_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        GROUP BY t.id
        ORDER BY t.artist, t.title
    """).fetchall()


def search_tracks(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    like = f"%{query}%"
    return conn.execute("""
        SELECT t.*, GROUP_CONCAT(tg.name, ', ') AS tags
        FROM tracks t
        LEFT JOIN track_tags tt ON tt.track_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE t.title LIKE ? OR t.artist LIKE ?
        GROUP BY t.id
        ORDER BY t.artist, t.title
    """, (like, like)).fetchall()


def filter_tracks(
    conn: sqlite3.Connection,
    query: str = "",
    tag_names: list[str] | None = None,
) -> list[sqlite3.Row]:
    params: list = []
    where_parts: list[str] = []

    if query:
        where_parts.append("(t.title LIKE ? OR t.artist LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])

    if tag_names:
        placeholders = ",".join("?" * len(tag_names))
        where_parts.append(
            f"t.id IN ("
            f"SELECT tt.track_id FROM track_tags tt "
            f"JOIN tags tg ON tg.id = tt.tag_id "
            f"WHERE tg.name IN ({placeholders}) "
            f"GROUP BY tt.track_id "
            f"HAVING COUNT(DISTINCT tg.name) = ?"
            f")"
        )
        params.extend(tag_names)
        params.append(len(tag_names))

    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return conn.execute(f"""
        SELECT t.*, GROUP_CONCAT(tg.name, ', ') AS tags
        FROM tracks t
        LEFT JOIN track_tags tt ON tt.track_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        {where}
        GROUP BY t.id
        ORDER BY t.artist, t.title
    """, params).fetchall()


def update_track_metadata(conn: sqlite3.Connection, track_id: str, title: str, artist: str) -> None:
    conn.execute(
        "UPDATE tracks SET title = ?, artist = ? WHERE id = ?",
        (title, artist, track_id),
    )
    conn.commit()


def mark_unavailable(conn: sqlite3.Connection, track_id: str) -> None:
    conn.execute("UPDATE tracks SET is_available = 0 WHERE id = ?", (track_id,))
    conn.commit()


def mark_all_unavailable(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE tracks SET is_available = 0")
    conn.commit()


def track_exists_analyzed(conn: sqlite3.Connection, track_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM tracks WHERE id = ? AND bpm IS NOT NULL AND key_open IS NOT NULL",
        (track_id,),
    ).fetchone()
    return row is not None


def touch_track(conn: sqlite3.Connection, track_id: str, path: str) -> None:
    conn.execute(
        "UPDATE tracks SET path = ?, is_available = 1, last_seen = ? WHERE id = ?",
        (path, datetime.now().isoformat(), track_id),
    )
    conn.commit()


def get_or_create_tag(conn: sqlite3.Connection, name: str) -> int:
    name = name.strip().lower()
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def tag_track(conn: sqlite3.Connection, track_id: str, tag_name: str) -> None:
    tag_id = get_or_create_tag(conn, tag_name)
    conn.execute(
        "INSERT OR IGNORE INTO track_tags (track_id, tag_id) VALUES (?, ?)",
        (track_id, tag_id),
    )
    conn.commit()


def untag_track(conn: sqlite3.Connection, track_id: str, tag_name: str) -> None:
    tag_id = get_or_create_tag(conn, tag_name)
    conn.execute(
        "DELETE FROM track_tags WHERE track_id = ? AND tag_id = ?",
        (track_id, tag_id),
    )
    still_used = conn.execute(
        "SELECT 1 FROM track_tags WHERE tag_id = ?", (tag_id,)
    ).fetchone()
    if still_used is None:
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.commit()


def get_track_tags(conn: sqlite3.Connection, track_id: str) -> list[str]:
    rows = conn.execute("""
        SELECT t.name FROM tags t
        JOIN track_tags tt ON tt.tag_id = t.id
        WHERE tt.track_id = ?
        ORDER BY t.name
    """, (track_id,)).fetchall()
    return [r["name"] for r in rows]


def get_all_tag_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def delete_tag(conn: sqlite3.Connection, tag_name: str) -> None:
    conn.execute("DELETE FROM tags WHERE name = ?", (tag_name,))
    conn.commit()


def delete_transition(conn: sqlite3.Connection, transition_id: int) -> None:
    conn.execute("DELETE FROM transitions WHERE id = ?", (transition_id,))
    conn.commit()


def update_transition(conn: sqlite3.Connection, transition_id: int, rating: int, notes: str) -> None:
    conn.execute(
        "UPDATE transitions SET rating = ?, notes = ? WHERE id = ?",
        (rating, notes, transition_id),
    )
    conn.commit()


def add_transition(
    conn: sqlite3.Connection,
    from_id: str,
    to_id: str,
    rating: int,
    notes: str = "",
) -> int:
    cur = conn.execute(
        "INSERT INTO transitions (from_track, to_track, rating, notes) VALUES (?, ?, ?, ?)",
        (from_id, to_id, rating, notes),
    )
    conn.commit()
    return cur.lastrowid


def transition_exists(conn: sqlite3.Connection, from_id: str, to_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM transitions WHERE from_track = ? AND to_track = ?",
        (from_id, to_id),
    ).fetchone()
    return row is not None


def get_all_transitions(conn: sqlite3.Connection, query: str = "") -> list[sqlite3.Row]:
    sql = """
        SELECT
            tr.id,
            t1.artist AS from_artist, t1.title AS from_title,
            t2.artist AS to_artist,   t2.title AS to_title,
            tr.rating
        FROM transitions tr
        JOIN tracks t1 ON tr.from_track = t1.id
        JOIN tracks t2 ON tr.to_track   = t2.id
    """
    params: list = []
    if query:
        like = f"%{query}%"
        sql += " WHERE (t1.title LIKE ? OR t1.artist LIKE ? OR t2.title LIKE ? OR t2.artist LIKE ?)"
        params = [like, like, like, like]
    sql += " ORDER BY t1.artist, t1.title, t2.artist, t2.title"
    return conn.execute(sql, params).fetchall()


def get_transitions_for_track(conn: sqlite3.Connection, track_id: str) -> dict[str, list[sqlite3.Row]]:
    outgoing = conn.execute("""
        SELECT tr.*, t.title AS to_title, t.artist AS to_artist
        FROM transitions tr
        JOIN tracks t ON t.id = tr.to_track
        WHERE tr.from_track = ?
        ORDER BY tr.rating DESC
    """, (track_id,)).fetchall()

    incoming = conn.execute("""
        SELECT tr.*, t.title AS from_title, t.artist AS from_artist
        FROM transitions tr
        JOIN tracks t ON t.id = tr.from_track
        WHERE tr.to_track = ?
        ORDER BY tr.rating DESC
    """, (track_id,)).fetchall()

    return {"outgoing": outgoing, "incoming": incoming}
