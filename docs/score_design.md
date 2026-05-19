# DJ Transition Graph — UI Design Summary

## Goal

Create a **2D interactive graph** that helps DJs:

- See **vibe clusters** in their library
- Instantly know **what song works next**
- Discover **creative transitions**
- Build **paths/playlists** between songs

---

## Core Model

- **Node (rectangle)** = song
- **Edge (line)** = possible transition
- **Edge score (0–1)** = transition quality
- Score is computed from multiple weighted components:
  - Key compatibility (most important)
  - BPM compatibility (soft constraint)
  - Tag similarity (vibe match)
  - User-defined transitions (strong signal)

---

## Transition Score Model

Each edge has a final score:

score =
a * key_score +
b * bpm_score +
c * tag_score +
d * user_score


### Component Breakdown

#### 1. Key Compatibility (highest weight)

Based on Camelot wheel distance.

- Same key → near perfect score (1.0)
- Adjacent Camelot keys → high compatibility (~0.8–0.9)
- Relative major/minor → medium-high (~0.7–0.85)
- Distant keys → low score

**Purpose:** Ensures harmonic mixing works.

---

#### 2. BPM Compatibility (soft constraint)

Uses smooth decay based on BPM difference:

- 0–3 BPM difference → near 1.0
- 5 BPM → still good
- 10 BPM → acceptable threshold
- >15 BPM → rapidly decreases

**Purpose:** Reflects mixability without being too strict.

---

#### 3. Tag Similarity (vibe matching)

Computed via set similarity (e.g. Jaccard index):

tag_score = intersection(tagsA, tagsB) / union(tagsA, tagsB)


- High overlap → similar vibe
- Low overlap → different energy / genre

**Purpose:** Captures emotional / stylistic compatibility.

---

#### 4. User Transition Score (most important learned signal)

Derived from DJ behavior:

- Manual transitions (A → B) rated 1–3
- Normalized to 0–1

user_score = rating / 3


- Strongest indicator of real-world success
- Can override weak mathematical signals

**Purpose:** Injects DJ taste and experience into the system.

---

## Key Design Principle

> **Layout shows structure. Interaction shows score.**

Do **not** encode full score visually at all times.

---

## Layout (at rest)

- Force-directed layout
- Nodes group into **clusters based on compatibility threshold**
- Edges are **faint or hidden**
- User sees **vibe islands**, not clutter

---

## Node Visuals

- Rectangle with song name
- Border color = dominant tag/vibe cluster

**Hover →** show song metadata:
- Key
- BPM
- Tags

---

## Edge Visuals (on interaction only)

Edges become meaningful **when hovering a node or edge**:

| Score | Thickness | Opacity |
|------:|-----------|---------|
| High  | Thick     | Strong  |
| Medium| Medium    | Visible |
| Low   | Thin      | Faint   |
| Very low | Hidden | — |

### Edge Color = Reason for Compatibility

- Purple → Key match dominant
- Blue → BPM similarity dominant
- Green → Tag similarity dominant
- Gold → User-defined transition

**Hover edge → tooltip shows full score breakdown**

---

## Zoom Levels

- **Zoomed out**: only nodes, cluster structure visible
- **Medium zoom**: faint edges appear
- **Hover/focus**: strong edges highlighted with scoring info

---

## Interactions

1. **Pan/zoom** like a map
2. **Hover node** → highlight best transitions
3. **Click node** → focus mode (radial “next track” view)
4. **Drag A → B** → create custom transition (user edge)
5. **Select A and B** → compute best path (playlist builder)

---

## Mental Model for User

- At rest → *“Where songs live (vibes)”*
- On hover → *“How well this connects”*
- On click → *“What should I play next”*

---

## Implementation Fit

Works well with graph libraries supporting:

- Force-directed layouts
- Dynamic edge styling
- Zoom-based rendering
- Interactive hover states