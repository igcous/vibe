import sqlite3
from collections import defaultdict

from src.graph.scoring import transition_score, DEFAULT_WEIGHTS, DEFAULT_RATING_MULTIPLIERS


def build_graph_data(
    conn: sqlite3.Connection,
    weights: dict[str, float] | None = None,
    score_threshold: float = 0.5,
    max_neighbors: int = 10,
    include_user_ratings: bool = False,
    rating_multipliers: dict[int, float] | None = None,
) -> dict:
    weights = weights or DEFAULT_WEIGHTS

    rows = conn.execute("""
        SELECT t.id, t.title, t.artist, t.bpm, t.key_open,
               GROUP_CONCAT(tg.name, ',') AS tag_str
        FROM tracks t
        LEFT JOIN track_tags tt ON tt.track_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE t.is_available = 1
        GROUP BY t.id
    """).fetchall()

    user_ratings = {
        (r["from_track"], r["to_track"]): r["rating"]
        for r in conn.execute(
            "SELECT from_track, to_track, MAX(rating) AS rating "
            "FROM transitions GROUP BY from_track, to_track"
        ).fetchall()
    }

    tracks = []
    for row in rows:
        tags = [s.strip() for s in (row["tag_str"] or "").split(",") if s.strip()]
        tracks.append({
            "id": row["id"],
            "title": row["title"] or "",
            "artist": row["artist"] or "",
            "bpm": row["bpm"],
            "key_open": row["key_open"],
            "tags": tags,
        })

    nodes = [
        {
            "id": t["id"],
            "label": (f"{t['artist']} — {t['title']}".strip(" —")
                      if t["artist"] else t["title"]) or t["id"][:8],
            "key": t["key_open"] or "",
            "bpm": t["bpm"],
            "tags": t["tags"],
        }
        for t in tracks
    ]

    n = len(tracks)
    pair_scores: dict[tuple, tuple] = {}
    for i in range(n):
        for j in range(i + 1, n):
            a, b = tracks[i], tracks[j]
            rating = (user_ratings.get((a["id"], b["id"]))
                      or user_ratings.get((b["id"], a["id"])))
            score, dominant, components = transition_score(a, b, rating, weights, include_user_ratings, rating_multipliers)
            if score >= score_threshold:
                pair_scores[(a["id"], b["id"])] = (score, dominant, components)

    # Keep top max_neighbors per node
    neighbor_scores: dict[str, list] = defaultdict(list)
    for (a_id, b_id), (score, dominant, components) in pair_scores.items():
        neighbor_scores[a_id].append((score, b_id, dominant, components))
        neighbor_scores[b_id].append((score, a_id, dominant, components))

    kept: set[tuple] = set()
    for node_id, neighbors in neighbor_scores.items():
        neighbors.sort(reverse=True)
        for score, other_id, _dom, _comp in neighbors[:max_neighbors]:
            kept.add((min(node_id, other_id), max(node_id, other_id)))

    edges = []
    for (a_id, b_id) in kept:
        score, dominant, components = pair_scores[(a_id, b_id)]
        edges.append({
            "source": a_id,
            "target": b_id,
            "score": round(score, 3),
            "dominant": dominant,
            "scores": {k: round(v, 2) for k, v in components.items()},
        })

    return {"nodes": nodes, "edges": edges}
