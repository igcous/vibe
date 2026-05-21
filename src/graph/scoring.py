import math

DEFAULT_WEIGHTS = {"tags": 0.5, "key": 0.2, "bpm": 0.1, "energy": 0.1, "centroid": 0.1}
DEFAULT_LAMBDA = 0.3
DEFAULT_K = 5

_BPM_TAU = 5.0
_ENERGY_TAU_DB = 3.0
_CENTROID_TAU_HZ = 500.0


def tag_similarity(tags_a: list[str], tags_b: list[str]) -> float:
    if not tags_a and not tags_b:
        return 0.0
    sa, sb = set(tags_a), set(tags_b)
    return len(sa & sb) / len(sa | sb)


def key_similarity(key_a: str | None, key_b: str | None) -> float:
    if not key_a or not key_b:
        return 0.5
    try:
        num_a = int(key_a[:-1])
        num_b = int(key_b[:-1])
    except (ValueError, IndexError):
        return 0.5
    d = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
    return math.exp(-d)


def bpm_similarity(bpm_a: int | None, bpm_b: int | None) -> float:
    if bpm_a is None or bpm_b is None:
        return 0.5
    diff = abs(bpm_a - bpm_b)
    diff = min(diff, abs(bpm_a * 2 - bpm_b), abs(bpm_a - bpm_b * 2))
    return math.exp(-max(0.0, diff - _BPM_TAU))


def energy_similarity(e_a: float | None, e_b: float | None) -> float:
    if e_a is None or e_b is None:
        return 0.5
    db_a = 20 * math.log10(max(e_a, 1e-9))
    db_b = 20 * math.log10(max(e_b, 1e-9))
    return math.exp(-max(0.0, abs(db_a - db_b) - _ENERGY_TAU_DB))


def centroid_similarity(c_a: float | None, c_b: float | None) -> float:
    if c_a is None or c_b is None:
        return 0.5
    return math.exp(-max(0.0, abs(c_a - c_b) - _CENTROID_TAU_HZ))


def similarity(
    track_a: dict,
    track_b: dict,
    weights: dict[str, float] | None = None,
) -> tuple[float, str, dict[str, float]]:
    """Returns (score 0-1, dominant_component, raw_component_scores)."""
    w = weights or DEFAULT_WEIGHTS
    s_tag      = tag_similarity(track_a.get("tags", []), track_b.get("tags", []))
    s_key      = key_similarity(track_a.get("key_open"), track_b.get("key_open"))
    s_bpm      = bpm_similarity(track_a.get("bpm"), track_b.get("bpm"))
    s_energy   = energy_similarity(track_a.get("energy"), track_b.get("energy"))
    s_centroid = centroid_similarity(track_a.get("spectral_centroid"), track_b.get("spectral_centroid"))

    weighted = {
        "tags":     w.get("tags",     DEFAULT_WEIGHTS["tags"])     * s_tag,
        "key":      w.get("key",      DEFAULT_WEIGHTS["key"])      * s_key,
        "bpm":      w.get("bpm",      DEFAULT_WEIGHTS["bpm"])      * s_bpm,
        "energy":   w.get("energy",   DEFAULT_WEIGHTS["energy"])   * s_energy,
        "centroid": w.get("centroid", DEFAULT_WEIGHTS["centroid"]) * s_centroid,
    }
    score = sum(weighted.values())
    dominant = max(weighted, key=weighted.__getitem__)
    return score, dominant, {
        "tags": s_tag, "key": s_key, "bpm": s_bpm,
        "energy": s_energy, "centroid": s_centroid,
    }
