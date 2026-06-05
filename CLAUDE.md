# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands must be run from the project root using the local venv:

```bash
# Launch the UI (also starts the companion API server)
.venv/bin/python main.py

# Incremental scan of a music folder into the active profile's DB
.venv/bin/python main.py ./tracks

# Install dependencies
pip install -r requirements.txt   # into active venv
.venv/bin/pip install essentia    # optional, for better BPM/key analysis
```

The system dependency `fpcalc` (Chromaprint) must be installed separately:
```bash
sudo apt install libchromaprint-tools
```

### Windows (run from source)

```bat
:: from the project root, inside the venv
.venv\Scripts\python main.py            :: launch the UI
.venv\Scripts\python main.py .\tracks   :: scan a folder
pip install -r requirements.txt
```

`fpcalc.exe` is **not** a pip package and is the only hard scanning dependency —
without it every track is skipped (surfaced as an `fpcalc not found` error). Get
it from <https://acoustid.org/chromaprint> (extract `fpcalc.exe` from the
`chromaprint-fpcalc-*-windows-*.zip`) or `choco install chromaprint`, then either
drop `fpcalc.exe` in the **project root** (auto-discovered by
`src/audio/fingerprint.py`), add it to PATH, or set the `FPCALC` env var to its
full path. Essentia is optional on every platform — `src/audio/analysis.py` falls
back to a librosa estimator when it is missing.

`settings.json` is untracked (machine-specific paths/profiles); each machine
generates its own on first run.

## Architecture

This is a desktop DJ library app built with **PySide6 + SQLite**, plus a small
**Flask** companion server for logging transitions from a phone. The core idea is
that **tracks are nodes and transitions are edges** in a graph of DJ decisions; a
rule-based similarity model fills in suggestions for pairs you haven't rated.

`main.py` is the entry point: `python main.py` launches the UI and starts the
companion API server; `python main.py <folder>` runs a CLI scan instead.

### Data flow on scan

1. `src/audio/scanner.py` — walks a folder, feeds each MP3 through the pipeline.
   Scanning is **incremental**: already-analyzed tracks are skipped and re-linked
   by fingerprint.
2. `src/audio/fingerprint.py` — generates a stable track ID via Chromaprint
   (`fpcalc`, force-enabled with `force_fpcalc=True`).
3. `src/audio/analysis.py` — `analyze_audio()` extracts BPM, key (Open Key
   notation `1m`–`12m` / `1d`–`12d`), energy, and spectral centroid. Essentia is
   the primary engine for BPM and key; a librosa path is used as fallback.
4. `src/db/queries.py` — upserts into SQLite. Tracks missing from disk are marked
   `is_available=0` but never deleted.

### Track identity

Tracks are identified by their **Chromaprint fingerprint**, not by filename or
path. Renaming or moving a file preserves all transitions and metadata — the
scanner re-links by fingerprint on the next scan.

### Scoring & inference (`src/graph/`)

- `scoring.py` — symmetric, rule-based `similarity()` between two tracks: a
  weighted blend of tag (Jaccard), key (circle-of-fifths decay), BPM (half/double
  aware), energy (dB), and spectral-centroid components. Defaults:
  `DEFAULT_WEIGHTS = {tags 0.5, key 0.2, bpm 0.1, energy 0.1, centroid 0.1}`,
  `DEFAULT_LAMBDA = 0.3`, `DEFAULT_K = 5`.
- `builder.py` — builds the graph data and the next-track scores. Direct ratings
  win; for unrated pairs, ratings are propagated through the *k* most similar
  tracks, scaled by λ.

Weights, λ, and *k* are tunable live in the Graph tab.

### Companion server (`src/api/`)

`server.py` runs a Flask app (port 5000) that serves
`static/companion.html` — a phone web page for logging transitions over local
WiFi. Saved transitions appear in the desktop **List** tab via a 5 s auto-refresh
timer in `main_window.py`.

### DB schema (SQLite, per-profile `*.db`)

- `tracks` — `id` (fingerprint, PK), `path`, `title`, `artist`, `bpm`,
  `key_open`, `key_strength`, `energy`, `spectral_centroid`, `is_available`,
  `last_seen`
- `tags` / `track_tags` — many-to-many tagging
- `transitions` — `from_track`, `to_track`, `rating` (1–3), `notes`,
  `created_at`; `UNIQUE(from_track, to_track)`

Each profile has its own database; profiles are managed in `options_tab.py`
(`get_active_db_path`, `_migrate_settings`).

### UI (`src/ui/`)

`main_window.py` — `QMainWindow` with a four-tab `QTabWidget` (**Library**,
**Graph**, **List**, **Options**); holds the shared `sqlite3.Connection`, handles
profile switching (reconnects every tab), and wires live refresh signals between
tabs.

- `library_tab.py` — searchable / tag-filterable `QTableWidget`; emits
  `track_selected(track_id, display_name)`.
- `graph_tab.py` — force-directed transition graph (QtWebEngine, `graph.html` +
  `force-graph.min.js`); side panel tunes similarity weights and inference params.
- `list_tab.py` — flat list of all transitions; auto-refreshes.
- `options_tab.py` — profile management and library scans (with progress,
  auto-scan-on-startup, folder auto-tagger).
- `transitions_widget.py` — per-track add / view / info / next-track panel.
- `tag_editor.py` — tag-editing dialog.

### Open Key mapping

`OPEN_KEY_MAP` in `src/audio/analysis.py` covers all enharmonic variants Essentia
may output (e.g. `Ab minor` = `G# minor` = `6m`). If a new unmapped key appears,
add both enharmonic spellings to the dict.

## Further reading

`README.md` is the canonical, full description of the architecture, scoring model,
and usage.
