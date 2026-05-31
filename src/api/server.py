import os
import sqlite3
import threading

from flask import Flask, jsonify, request, send_from_directory

from src.db.schema import init_db
from src.db.queries import (
    filter_tracks,
    get_track,
    add_transition,
    transition_exists,
    get_transitions_for_track,
)

app = Flask(__name__)
_db_path: str = ""


def _get_conn() -> sqlite3.Connection:
    return init_db(_db_path)


@app.errorhandler(Exception)
def _handle_unexpected(e):
    return jsonify({"error": "internal server error"}), 500


@app.get("/")
def companion_ui():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return send_from_directory(static_dir, "companion.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/tracks")
def tracks():
    q = request.args.get("q", "")
    conn = _get_conn()
    try:
        rows = filter_tracks(conn, query=q)
        return jsonify({
            "tracks": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "artist": r["artist"],
                    "bpm": r["bpm"],
                    "key_open": r["key_open"],
                }
                for r in rows
            ]
        })
    finally:
        conn.close()


@app.post("/transitions")
def create_transition():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "invalid JSON"}), 422

    from_id = body.get("from_track", "")
    to_id = body.get("to_track", "")
    if not from_id or not to_id:
        return jsonify({"error": "from_track and to_track are required"}), 422

    rating = body.get("rating")
    if not isinstance(rating, int) or not (1 <= rating <= 3):
        return jsonify({"error": "rating must be an integer 1-3"}), 422

    notes = body.get("notes", "") or ""

    conn = _get_conn()
    try:
        if get_track(conn, from_id) is None:
            return jsonify({"error": "track not found", "missing": from_id}), 404
        if get_track(conn, to_id) is None:
            return jsonify({"error": "track not found", "missing": to_id}), 404
        if transition_exists(conn, from_id, to_id):
            return jsonify({"error": "transition already exists"}), 409
        new_id = add_transition(conn, from_id, to_id, rating, notes)
        return jsonify({"id": new_id}), 201
    finally:
        conn.close()


@app.get("/transitions")
def list_transitions():
    q = request.args.get("q", "")
    sql = """
        SELECT
            tr.id,
            tr.from_track AS from_track_id,
            tr.to_track   AS to_track_id,
            t1.artist AS from_artist, t1.title AS from_title,
            t2.artist AS to_artist,   t2.title AS to_title,
            tr.rating
        FROM transitions tr
        JOIN tracks t1 ON tr.from_track = t1.id
        JOIN tracks t2 ON tr.to_track   = t2.id
    """
    params: list = []
    if q:
        like = f"%{q}%"
        sql += " WHERE (t1.title LIKE ? OR t1.artist LIKE ? OR t2.title LIKE ? OR t2.artist LIKE ?)"
        params = [like, like, like, like]
    sql += " ORDER BY t1.artist, t1.title, t2.artist, t2.title"
    conn = _get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return jsonify({
            "transitions": [dict(r) for r in rows]
        })
    finally:
        conn.close()


@app.get("/transitions/<track_id>")
def track_transitions(track_id):
    conn = _get_conn()
    try:
        data = get_transitions_for_track(conn, track_id)
        return jsonify({
            "outgoing": [
                {
                    "id": r["id"],
                    "track_id": r["to_track"],
                    "artist": r["to_artist"],
                    "title": r["to_title"],
                    "rating": r["rating"],
                    "notes": r["notes"],
                }
                for r in data["outgoing"]
            ],
            "incoming": [
                {
                    "id": r["id"],
                    "track_id": r["from_track"],
                    "artist": r["from_artist"],
                    "title": r["from_title"],
                    "rating": r["rating"],
                    "notes": r["notes"],
                }
                for r in data["incoming"]
            ],
        })
    finally:
        conn.close()


def start_api_server(db_path: str, port: int = 5000) -> None:
    global _db_path
    _db_path = db_path
    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False, debug=False),
        daemon=True,
        name="flask-api",
    )
    t.start()
