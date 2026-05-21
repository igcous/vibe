# DJ Playlist System — Structured Transition + Similarity Model

## Overview

This system models music playback using two complementary layers:

1. **DJ Transition Graph (behavioral truth)**
2. **Structured Song Similarity (musical prior)**

The goal is to generate playlists that reflect **user-defined DJ taste**, while using musical structure to generalize and fill gaps.

---

# 1. Song Representation (Feature Space)

Each song is described by intrinsic musical attributes:

- BPM (continuous)
- Key (categorical / harmonic)
- Tags (user-defined categorical labels)

These features are used for similarity, not transitions.

---

# 2. Structured Song Similarity Model

Similarity is not learned implicitly — it is explicitly defined as a weighted combination of musical rules.

## 2.1 Tag similarity (primary signal)

```math
S_{tag}(i,j) = \frac{|tags_i \cap tags_j|}{|tags_i \cup tags_j|}
```

- Strongest similarity factor
- Encodes semantic / user-defined meaning

---

## 2.2 Key similarity (harmonic structure)

```math
S_{key}(i,j) = e^{-d(k_i, k_j)}
```

Where:
- \(d(k_i, k_j)\) is harmonic distance (e.g., circle of fifths)

- Same key → high similarity
- Related keys → moderate similarity

---

## 2.3 BPM similarity (thresholded energy constraint)

```math
S_{bpm}(i,j) = e^{-\max(0, |bpm_i - bpm_j| - \tau)}
```

Where:
- τ ≈ 5–10 BPM tolerance window

- Small differences → negligible effect
- Large differences → penalized

---

## 2.4 Final similarity function

```math
S(i,j) = w_1 S_{tag}(i,j) + w_2 S_{key}(i,j) + w_3 S_{bpm}(i,j)
```

Recommended weights:
- w₁ (tags): 0.5–0.7
- w₂ (key): 0.2–0.4
- w₃ (BPM): 0.05–0.2

---

## Interpretation

Similarity encodes:

> “How musically compatible are two songs based on human-defined structure?”

It is:
- symmetric
- dense
- non-authoritative

---

# 3. DJ Transition Graph (Truth Layer)

This is the core behavioral model.

```math
T(i,j) = user-rated transition quality from i → j
```

Properties:
- directed
- sparse
- authoritative
- reflects DJ intent

---

## Interpretation

The transition graph encodes:

> “What does the DJ believe flows well?”

This is the primary decision layer for playlist generation.

---

# 4. Similarity-Guided Transition Inference

Similarity is used to generalize sparse DJ knowledge.

## Neighbor set

```math
N(i) = top-k most similar songs to i
```

## Inferred transition strength

```math
\hat{T}(i,j) = \sum_{k \in N(i)} S(i,k) \cdot T(k,j)
```

---

## Final transition score

```math
Score(i,j) = T(i,j) + \lambda \hat{T}(i,j)
```

Where:
- λ controls influence of similarity (typically 0.1–0.4)

---

## Interpretation

Final score combines:

- direct DJ judgment (truth)
- structured musical generalization (support)

---

# 5. System Layers Summary

| Layer | Type | Role |
|------|------|------|
| Song Features | BPM, Key, Tags | Raw musical attributes |
| Similarity S(i,j) | weighted rule-based | musical compatibility |
| Transition Graph T(i,j) | user-rated edges | DJ truth / behavior |
| Inference Layer | propagation model | smoothing & generalization |

---

# 6. Design Principles

## 1. DJ-first system
User ratings define the ground truth of transitions.

## 2. Separation of concerns
- Similarity ≠ transition quality
- Features ≠ sequencing logic

## 3. Structured similarity (not learned geometry)
Similarity is explicitly defined using musical rules.

## 4. Sparse-data robustness
Similarity is used only to fill gaps in transition knowledge.

---

# 7. System Behavior

## Playlist generation flow

1. Prefer direct transition T(i,j)
2. If missing, use similarity-guided inference
3. Fall back to structured similarity only if needed

---

# 8. Outcome

The system behaves as:

> A DJ-authored transition network grounded in explicit musical rules, where similarity acts as a controlled generalization mechanism rather than a decision engine.
```