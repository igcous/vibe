import sqlite3
from collections import defaultdict

from src.graph.scoring import similarity, DEFAULT_WEIGHTS, DEFAULT_LAMBDA, DEFAULT_K


def _fetch_tracks(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT t.id, t.title, t.artist, t.bpm, t.key_open,
               GROUP_CONCAT(tg.name, ',') AS tag_str
        FROM tracks t
        LEFT JOIN track_tags tt ON tt.track_id = t.id
        LEFT JOIN tags tg ON tg.id = tt.tag_id
        WHERE t.is_available = 1
        GROUP BY t.id
    """).fetchall()
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
    return tracks


def _fetch_ratings(conn: sqlite3.Connection) -> dict[tuple, int]:
    return {
        (r["from_track"], r["to_track"]): r["rating"]
        for r in conn.execute(
            "SELECT from_track, to_track, MAX(rating) AS rating "
            "FROM transitions GROUP BY from_track, to_track"
        ).fetchall()
    }


def build_graph_data(
    conn: sqlite3.Connection,
    weights: dict[str, float] | None = None,
    score_threshold: float = 0.35,
    max_neighbors: int = 10,
    include_transitions: bool = True,
) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    tracks = _fetch_tracks(conn)
    user_ratings = _fetch_ratings(conn) if include_transitions else {}

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
            direction = "none"
            has_rating = False
            if include_transitions:
                fwd = user_ratings.get((a["id"], b["id"]))
                bwd = user_ratings.get((b["id"], a["id"]))
                if fwd and bwd:   direction = "both"
                elif fwd:         direction = "forward"
                elif bwd:         direction = "backward"
                has_rating = (fwd is not None) or (bwd is not None)
            score, dominant, comps = similarity(a, b, weights)
            if score >= score_threshold or has_rating:
                pair_scores[(a["id"], b["id"])] = (score, dominant, comps, direction)

    neighbor_scores: dict[str, list] = defaultdict(list)
    for (a_id, b_id), (score, dominant, components, _dir) in pair_scores.items():
        neighbor_scores[a_id].append((score, b_id, dominant, components))
        neighbor_scores[b_id].append((score, a_id, dominant, components))

    kept: set[tuple] = set()
    for node_id, neighbors in neighbor_scores.items():
        neighbors.sort(reverse=True)
        for score, other_id, _dom, _comp in neighbors[:max_neighbors]:
            kept.add((min(node_id, other_id), max(node_id, other_id)))

    # Rated transitions always shown — only when include_transitions
    if include_transitions:
        for (a_id, b_id), (_score, _dom, _comps, direction) in pair_scores.items():
            if direction != "none":
                kept.add((min(a_id, b_id), max(a_id, b_id)))

    edges = []
    for (a_id, b_id) in kept:
        score, dominant, components, direction = pair_scores[(a_id, b_id)]
        edges.append({
            "source": a_id,
            "target": b_id,
            "score": round(score, 3),
            "dominant": dominant,
            "scores": {k: round(v, 2) for k, v in components.items()},
            "direction": direction,
        })

    return {"nodes": nodes, "edges": edges}


def get_next_track_scores(
    conn: sqlite3.Connection,
    from_track_id: str,
    weights: dict[str, float] | None = None,
    lam: float = DEFAULT_LAMBDA,
    k: int = DEFAULT_K,
    include_transitions: bool = True,
) -> list[tuple[dict, float, str]]:
    """Return [(track_dict, score, factor_str), ...] sorted by score desc."""
    weights = weights or DEFAULT_WEIGHTS
    tracks = _fetch_tracks(conn)

    from_track = next((t for t in tracks if t["id"] == from_track_id), None)
    if from_track is None:
        return []

    # Similarity from source to all others
    sim_from: dict[str, tuple[float, str]] = {}
    for t in tracks:
        if t["id"] == from_track_id:
            continue
        s, dominant, _ = similarity(from_track, t, weights)
        sim_from[t["id"]] = (s, dominant)

    results = []

    if include_transitions:
        # Normalize user ratings (1-3) to [0, 1]
        all_ratings = _fetch_ratings(conn)
        def t_ij(src_id: str, dst_id: str) -> float | None:
            r = all_ratings.get((src_id, dst_id))
            return r / 3.0 if r is not None else None

        # N(i) = top-k most similar to source
        neighbors = sorted(sim_from.items(), key=lambda x: x[1][0], reverse=True)[:k]

        for t in tracks:
            if t["id"] == from_track_id:
                continue

            t_direct = t_ij(from_track_id, t["id"])
            s_ij, dominant = sim_from[t["id"]]

            # Inferred transition: T̂(i,j) = Σ_{m ∈ N(i)} S(i,m) * T(m,j)
            t_hat = 0.0
            for nb_id, (s_im, _) in neighbors:
                t_mj = t_ij(nb_id, t["id"])
                if t_mj is not None:
                    t_hat += s_im * t_mj

            if t_direct is not None:
                score = min(1.0, t_direct + lam * t_hat)
                factor = "direct"
            elif t_hat > 0:
                score = min(1.0, s_ij + lam * t_hat)
                factor = "inferred"
            else:
                score = s_ij
                factor = dominant

            results.append((t, score, factor))
    else:
        for t in tracks:
            if t["id"] == from_track_id:
                continue
            s_ij, dominant = sim_from[t["id"]]
            results.append((t, s_ij, dominant))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
