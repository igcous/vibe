# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands must be run from the project root using the local venv:

```bash
# Launch the UI
.venv/bin/python main.py

# Scan a music folder into the DB (overwrites library.db)
.venv/bin/python main.py ./tracks

# Install dependencies
pip install -r requirements.txt   # into active venv
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
without it every track is silently skipped (now surfaced as an `fpcalc not found`
error). Get it from <https://acoustid.org/chromaprint> (extract `fpcalc.exe` from
the `chromaprint-fpcalc-*-windows-*.zip`) or `choco install chromaprint`, then
either drop `fpcalc.exe` in the **project root** (auto-discovered by
`src/audio/fingerprint.py`), add it to PATH, or set the `FPCALC` env var to its
full path. Essentia is optional on every platform — `src/audio/analysis.py` falls
back to a librosa key estimator when it is missing.

`settings.json` is untracked (machine-specific paths/profiles); each machine
generates its own on first run.

## Architecture

This is a desktop DJ library app built with PySide6 + SQLite. The core idea is that **tracks are nodes and transitions are edges** in a graph of DJ decisions.

### Data flow

1. `src/audio/scanner.py` — walks a folder, feeds each MP3 through the pipeline
2. `src/audio/fingerprint.py` — generates a stable track ID via Chromaprint (`fpcalc`, force-enabled with `force_fpcalc=True`)
3. `src/audio/analysis.py` — BPM via librosa, key via Essentia, converts to Open Key notation (`1m`–`12m` / `1d`–`12d`)
4. `src/db/queries.py` — upserts into SQLite; tracks missing from disk are marked `is_available=0` but never deleted

### Track identity

Tracks are identified by their **Chromaprint fingerprint**, not by filename or path. Renaming or moving a file preserves all transitions and metadata — the scanner re-links by fingerprint on the next scan.

### DB schema (SQLite, `library.db`)

- `tracks` — fingerprint as PK, path, title, artist, bpm, key_open, key_strength, is_available
- `tags` / `track_tags` — many-to-many tagging
- `transitions` — from_track, to_track, rating (1–5), notes

### UI (`src/ui/`)

- `main_window.py` — QMainWindow with a QTabWidget; holds the shared `sqlite3.Connection`; syncs Library selection → Transitions "from" field on tab switch
- `library_tab.py` — searchable QTableWidget; emits `track_selected(track_id, display_name)` signal
- `transitions_tab.py` — create/view transitions; `set_from_track(id)` can be called externally to pre-select a track

### Open Key mapping

`OPEN_KEY_MAP` in `src/audio/analysis.py` covers all enharmonic variants Essentia may output (e.g. `Ab minor` = `G# minor` = `6m`). If a new unmapped key appears, add both enharmonic spellings to the dict.

## Design doc

Full architecture and phased roadmap at `docs/dj_transition_companion_design_document.md`. Phase 2 adds a suggestion engine; Phase 3 adds a graph view.
