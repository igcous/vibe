import math

DEFAULT_WEIGHTS = {"key": 0.5, "bpm": 0.3, "tags": 0.2}
DEFAULT_RATING_MULTIPLIERS = {1: 1.25, 2: 1.5, 3: 2.0}


def key_score(key_a: str | None, key_b: str | None) -> float:
    if not key_a or not key_b:
        return 0.5
    try:
        num_a, type_a = int(key_a[:-1]), key_a[-1]
        num_b, type_b = int(key_b[:-1]), key_b[-1]
    except (ValueError, IndexError):
        return 0.5

    if num_a == num_b and type_a == type_b:
        return 1.0
    if num_a == num_b:
        return 0.8  # relative major/minor

    dist = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
    if dist == 1 and type_a == type_b:
        return 0.9  # Camelot-adjacent, same mode
    if dist == 1:
        return 0.55  # adjacent, cross-mode
    if dist == 2 and type_a == type_b:
        return 0.35
    return max(0.0, 0.25 - (dist - 2) * 0.07)


def bpm_score(bpm_a: int | None, bpm_b: int | None) -> float:
    if bpm_a is None or bpm_b is None:
        return 0.5
    diff = abs(bpm_a - bpm_b)
    # Also check double/half tempo
    diff = min(diff, abs(bpm_a * 2 - bpm_b), abs(bpm_a - bpm_b * 2))
    return math.exp(-(diff / 8.0) ** 1.5)


def tag_score(tags_a: list[str], tags_b: list[str]) -> float:
    if not tags_a or not tags_b:
        return 0.5
    sa, sb = set(tags_a), set(tags_b)
    jaccard = len(sa & sb) / len(sa | sb)
    return 0.5 + jaccard * 0.5


def transition_score(
    track_a: dict,
    track_b: dict,
    user_rating: int | None,
    weights: dict[str, float],
    include_user_ratings: bool = False,
    rating_multipliers: dict[int, float] | None = None,
) -> tuple[float, str, dict[str, float]]:
    """Returns (total_score 0-1, dominant_component, raw_component_scores)."""
    k = key_score(track_a.get("key_open"), track_b.get("key_open"))
    b = bpm_score(track_a.get("bpm"), track_b.get("bpm"))
    t = tag_score(track_a.get("tags", []), track_b.get("tags", []))

    wk = weights.get("key", DEFAULT_WEIGHTS["key"])
    wb = weights.get("bpm", DEFAULT_WEIGHTS["bpm"])
    wt = weights.get("tags", DEFAULT_WEIGHTS["tags"])

    weighted = {"key": wk * k, "bpm": wb * b, "tags": wt * t}
    base_score = sum(weighted.values())
    dominant = max(weighted, key=weighted.__getitem__)

    if include_user_ratings and user_rating is not None:
        mults = rating_multipliers or DEFAULT_RATING_MULTIPLIERS
        mult = mults.get(user_rating, 1.0)
        score = min(1.0, base_score * mult)
    else:
        score = base_score

    return score, dominant, {"key": k, "bpm": b, "tags": t}
