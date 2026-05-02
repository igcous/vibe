# DJ Transition Companion – Design Document

## 1. Overview
A cross-platform desktop application (Windows/Linux) built in Python using PySide6 that helps DJs manage their music library, analyze tracks, and design high-quality transitions between songs.

The system treats music not just as a playlist, but as a **graph of transitions**, where:
- Nodes = tracks
- Edges = user-defined transitions
- Metadata = BPM, musical key (Open Key), tags

The long-term goal is to enable discovery of new transitions through clustering and graph inference.

---

## 2. Core Principles

- Offline-first (no external DJ software dependency)
- Track identity is independent of filename (audio fingerprint-based)
- Transitions are first-class objects (more important than playlists)
- Lightweight but extensible architecture
- All analysis happens locally

---

## 3. Tech Stack

### UI
- PySide6 (Qt for Python)

### Audio Analysis
- librosa → BPM detection
- Essentia → key detection
- Chromaprint (AcoustID) → audio fingerprinting

### Storage
- SQLite (embedded local database)

### Architecture
- Modular Python backend
- QThread-based background processing for analysis

---

## 4. Data Model

### 4.1 Tracks
```sql
tracks (
    id TEXT PRIMARY KEY,          -- audio fingerprint (stable ID)
    path TEXT,                    -- current file path
    title TEXT,
    artist TEXT,
    bpm INTEGER,
    key_open TEXT,                -- e.g. '8m'
    key_strength REAL,
    is_available BOOLEAN,
    last_seen TIMESTAMP
)
```

### 4.2 Tags
```sql
tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)
```

### 4.3 Track-Tags (many-to-many)
```sql
track_tags (
    track_id TEXT,
    tag_id INTEGER
)
```

### 4.4 Transitions
```sql
transitions (
    id INTEGER PRIMARY KEY,
    from_track TEXT,
    to_track TEXT,
    rating INTEGER,
    notes TEXT,
    created_at TIMESTAMP
)
```

---

## 5. Track Identification System

### Problem
Tracks may change name or location.

### Solution
Use audio fingerprinting via Chromaprint:
- Generates unique ID from audio content
- Stable across renames or moves

### Behavior
- If file disappears: mark `is_available = false`
- Never delete historical data
- Re-link by fingerprint when found again

---

## 6. Audio Analysis Pipeline

Triggered when a new or modified file is detected.

### Step 1: Fingerprint
- Generate stable track ID

### Step 2: BPM Detection (librosa)
```python
tempo = beat_track(audio)
bpm = round(tempo)
```

### Step 3: Key Detection (Essentia)
Outputs:
- key (e.g. A)
- scale (major/minor)
- strength

### Step 4: Convert to Open Key
Mapping:
- 1–12 cycle
- m = minor
- d = major

Example:
- A minor → 1m
- D major → 3d

### Step 5: Store in DB

---

## 7. Open Key System

### Format
```
1m ... 12m
1d ... 12d
```

### Compatibility Rules
- Same key = perfect match
- ±1 step = harmonic neighbor
- Relative major/minor = compatible energy shift

This enables deterministic transition scoring later.

---

## 8. UI Design

Built with tab-based layout:

### Tab 1: Library
- Table view of all tracks
- Columns:
  - Title
  - Artist
  - BPM
  - Key (Open Key)
  - Tags
  - Availability
- Search bar:
  - text search (title/artist)
  - tag filtering
  - BPM/key filtering

### Tab 2: Transitions
- Create transition between two tracks
- Show existing transitions for selected track
- Display rating + notes

### Tab 3: Suggestions
- Auto-generated potential transitions
- Based on:
  - BPM similarity
  - Key compatibility
  - Tag similarity
  - Graph proximity (future)

### Tab 4: Graph View (future)
- Visual network of tracks and transitions

---

## 9. Transition System

### Transition object
- from_track
- to_track
- rating (1–5)
- notes

### Core idea
Transitions are more important than tracks.
They represent DJ knowledge.

### UI Behavior
When selecting a track:
- Show outgoing transitions
- Show incoming transitions
- Show stats (avg rating, most common tag pairs)

---

## 10. Suggestion Engine (Phase 2)

### Inputs
- BPM distance
- Open Key distance
- Shared tags
- Existing transition graph

### Heuristic scoring
```text
score(A → B) =
    BPM similarity
  + key compatibility
  + tag overlap
  + graph proximity (A→X→B patterns)
```

### Key insight
If A→B and B→C are good, then A→C is likely valid.

This is a **graph inference problem**.

---

## 11. Background Processing

Implemented using QThread:

- Folder scanning
- Audio analysis
- Metadata updates

Never blocks UI.

---

## 12. Folder Scanning Strategy

### On startup:
- Fast scan of directory structure
- Compare modification timestamps

### Continuous:
- Watcher (optional Phase 2)
- Update only changed files

---

## 13. Future Extensions

### Phase 2
- Graph-based recommendation engine
- Transition auto-suggestions
- Smart playlist generation

### Phase 3
- Visual graph editor
- Drag-and-drop mix building
- Set simulation tool

### Phase 4
- Beat energy curve modeling
- Automatic set ordering

---

## 14. Key Design Decisions Summary

- Audio fingerprint = permanent identity
- Open Key replaces Camelot
- Transitions are first-class data
- Analysis is fully offline
- Graph model is core abstraction

---

## 15. Minimal Viable Product (MVP)

To build first:

1. Folder scan + fingerprinting
2. BPM + Key analysis
3. Library UI
4. Tagging system
5. Create/view transitions
6. SQLite persistence

Everything else is optional after this works.

---

## 16. Core Mental Model

This app is not a playlist tool.

It is:

> A growing graph of DJ decisions that learns your mixing style over time.

