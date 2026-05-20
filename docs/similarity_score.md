# Graph-Based Song Similarity (Diffusion + Cosine Embedding)

## Overview

This system computes **song-to-song similarity** from a fully connected weighted transition graph.

Each song is represented not just by its direct transitions, but by its **diffused connectivity pattern**, capturing both local and multi-step relationships in the graph.

The goal is to measure:

> “How similar are two songs in terms of their transition behavior in the playlist graph?”

---

## Input

We start with a directed weighted graph:

```text
M[i][j] = transition score from song i → song j
```

Where:
- `M[i][j] ∈ [0, 1]`
- all pairs are defined (dense graph)
- values represent transition quality (musical compatibility)

---

## Step 1 — Graph Diffusion

We expand each node’s representation using multi-hop transitions.

A lightweight diffusion is used:

```math
Z = M + α M² + α² M³
```

Where:
- `Z[i]` becomes the feature vector of song `i`
- `α ∈ (0,1)` is a decay factor (recommended: 0.3–0.6)
- higher-order terms capture indirect transitions

### Intuition

After diffusion:
- each song encodes not just direct transitions
- but also “where it leads over time in the graph”

---

## Step 2 — Node Embedding Interpretation

Each row becomes a vector:

```text
Z[i] = [similarity of i to all other songs via paths]
```

So:
- row `Z[i]` is a behavioral fingerprint of song `i`
- it encodes how i interacts with the entire catalog

---

## Step 3 — Similarity Computation

Similarity between songs is computed using cosine similarity:

:contentReference[oaicite:0]{index=0}

This produces:
- values in `[0, 1]` (after normalization)
- symmetric similarity: `sim(i,j) = sim(j,i)`

---

## Interpretation

Two songs are similar if:

> they connect strongly to the same regions of the transition graph

Example:
- A → C = 1
- B → C = 1

Then:
- A and B share strong structural context
- therefore `sim(A,B)` is high

---

## Properties

### 1. Structural similarity
Captures shared transition neighborhoods, not just direct edges.

### 2. Multi-hop awareness
Indirect relationships (A → B → C) influence similarity.

### 3. Smooth clustering behavior
Songs with similar flow patterns naturally group together.

### 4. Dense graph compatibility
Works well even when every pair has a score.

---

## Output

A symmetric similarity matrix:

```text
S[i][j] ∈ [0, 1]
```

Where:
- 1 = identical transition behavior
- 0 = unrelated behavior

---

## Use Cases

This similarity matrix can be used for:

- “Songs like this” recommendations
- clustering songs into vibe groups
- initializing playlists from seed tracks
- retrieval of compatible transitions
- pre-filtering candidates for playlist generation

---

## Notes

- Diffusion depth should remain shallow (≤ 3 hops recommended)
- α controls how far influence propagates
- cosine similarity ensures stable scaling across songs
- normalization may be applied per-row of Z if needed
