import sqlite3


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tracks (
            id          TEXT PRIMARY KEY,
            path        TEXT,
            title       TEXT,
            artist      TEXT,
            bpm         INTEGER,
            key_open    TEXT,
            key_strength REAL,
            is_available BOOLEAN NOT NULL DEFAULT 1,
            last_seen   TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tags (
            id   INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS track_tags (
            track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (track_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS transitions (
            id         INTEGER PRIMARY KEY,
            from_track TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            to_track   TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            rating     INTEGER CHECK (rating BETWEEN 1 AND 5),
            notes      TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
