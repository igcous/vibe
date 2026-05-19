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
- **Edge score (0–1)** = transition quality (key, BPM, tags, user rating)

---

## Key Design Principle

> **Layout shows structure. Interaction shows score.**

Do **not** encode transition score in node distance.

---

## Layout (at rest)

- Force-directed layout
- Nodes group into **clusters** based on compatibility threshold
- Edges are **faint or hidden**
- User sees **vibe islands**, not spaghetti

---

## Node Visuals

- Rectangle with song name
- Border color = vibe cluster

**Hover →** show song details (key, BPM, tags)

---

## Edge Visuals (only on interaction)

Edges become meaningful **on hover/focus** of a node:

| Score | Thickness | Opacity |
|------:|-----------|---------|
| High  | Thick     | Strong  |
| Medium| Medium    | Visible |
| Low   | Thin      | Faint   |
| Very low | Hidden | —       |

**Edge color = reason for compatibility**

- Key match
- BPM friendly
- Tag similarity
- User-defined transition (gold)

**Hover edge →** tooltip with score breakdown.

---

## Zoom Levels

- **Zoomed out**: only nodes, clusters visible
- **Medium zoom**: faint edges appear
- **Hover/focus**: strong edges highlighted with score encoding

---

## Interactions

1. **Pan/zoom** like a map
2. **Hover node** → reveal best transitions
3. **Click node** → focus mode (radial next-track view)
4. **Drag A → B** → add custom transition
5. **Select A and B** → highlight best path (playlist builder)

---

## Mental Model for User

- At rest → *“Where songs live (vibes)”*
- On hover → *“How well this connects”*
- On click → *“What should I play next”*

---

## Implementation Fit

Works well with force-graph libraries that support:

- Dynamic edge styling
- Zoom-based rendering
- Force layouts