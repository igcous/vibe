# DJ Transition Companion

A desktop app for DJs who want to **remember which tracks flow into which** — and discover new transitions they haven't tried yet.

The core idea: **tracks are nodes, transitions are edges.** As you play, you rate the transitions that work. Over time you build a personal, directed graph of "what mixes into what," grounded in your own ears rather than a generic recommendation engine. A rule-based similarity model fills the gaps, suggesting compatible next tracks even for pairs you've never rated.

Built with **PySide6 + SQLite**, with an optional phone companion so you can log transitions mid-set without touching the laptop.

---

## Features

- **Fingerprint-based library** — every track is identified by its [Chromaprint](https://acoustid.org/chromaprint) audio fingerprint, not its filename. Rename, move, or re-tag a file and all its transitions and metadata survive the next scan.
- **Automatic analysis** — BPM, musical key (in Open Key `1m`–`12m` / `1d`–`12d` notation), energy (loudness), and spectral brightness, extracted on scan.
- **Transition graph** — an interactive force-directed graph of your library. Edges show both your rated transitions and rule-based similarity, weighted however you like.
- **Next-track suggestions** — pick a track and get a ranked shortlist of where to go next, blending your direct ratings with similarity-guided inference.
- **Tagging** — free-form tags per track, with an optional auto-tagger that tags tracks by their folder name. Filter the library by any combination of tags.
- **Profiles** — keep multiple independent libraries (e.g. per genre or per gig), each with its own database.
- **Phone companion** — a lightweight web page served over your local WiFi lets you log transitions from your phone during a set; the desktop picks them up within seconds.

---

## The four tabs

| Tab | What it does |
|---------|--------------|
| **Library** | Searchable, tag-filterable table of every track. Edit title/artist inline (written back to the file's ID3 tags); double-click the Tags cell to edit tags. Tracks missing from disk show in red. |
| **Graph** | The force-directed transition graph. Tune similarity weights and inference parameters in the side panel. Click any node to open a panel for that track: **Add transition**, **See transitions**, **Track info**, and **Next track** suggestions. |
| **List** | A flat list of every transition (From → To, with star rating). Right-click to delete. Auto-refreshes so companion-added transitions appear live. |
| **Options** | Manage profiles and run library scans (with progress), including auto-scan-on-startup and the folder auto-tagger. |

---

## Requirements

- **Python 3.10+** (developed on 3.12)
- **fpcalc** (Chromaprint command-line tool) — required for fingerprinting:
  ```bash
  sudo apt install libchromaprint-tools      # Debian / Ubuntu
  ```
- Python packages (see `requirements.txt`): `librosa`, `pyacoustid`, `mutagen`, `PySide6`, `flask`.
- **Essentia** *(optional, recommended)* — used as the primary analysis engine for more accurate BPM/key detection. If it isn't installed, the app automatically falls back to a librosa-only path.

---

## Installation

```bash
# 1. Clone and enter the project
git clone <repo-url> vibe && cd vibe

# 2. Create a virtual environment
python3 -m venv .venv

# 3. Install dependencies
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install essentia          # optional, for better analysis

# 4. Install the system fingerprinting tool
sudo apt install libchromaprint-tools
```

---

## Usage

All commands run from the project root using the local venv.

### Launch the app

```bash
.venv/bin/python main.py
```

This opens the UI **and** starts the companion web server in the background.

### Scan a music folder from the command line

```bash
.venv/bin/python main.py /path/to/your/mp3s
```

Walks the folder recursively, fingerprints and analyzes every `.mp3`, and upserts it into the active profile's database. Scanning is incremental: already-analyzed tracks are skipped and simply re-linked, so re-scanning after adding a few files is fast. (You can also scan from the **Options** tab inside the app.)

> Tracks are never deleted. A track whose file is missing on the next scan is marked unavailable (shown in red) but keeps all its transitions and metadata.

### Phone companion (log transitions mid-set)

With the desktop app running and your phone on the same WiFi network:

1. Find your laptop's IP: `hostname -I` (use the first address).
2. On your phone, open `http://<laptop-ip>:5000`.
3. Search a track to set it as the "From" track, then add the transition (rating + optional notes).

Transitions saved on the phone appear in the desktop **List** tab within ~5 seconds. See [`companion_tutorial.txt`](companion_tutorial.txt) for the full walkthrough, including adding it to your phone's home screen.

---

## How the scoring works

The system has two layers:

### 1. Structured similarity *(musical prior)*

A symmetric, rule-based score for how compatible any two tracks are. It's an explicit weighted blend of musical features — never a learned black box:

| Component | How it's measured |
|-----------|-------------------|
| **Tags** | Jaccard overlap of the two tracks' tags |
| **Key** | Exponential decay over distance on the Open Key wheel (circle of fifths) |
| **BPM** | Thresholded decay on tempo difference (with half-time / double-time awareness) |
| **Energy** | Thresholded decay on loudness difference (in dB) |
| **Brightness** | Thresholded decay on spectral-centroid difference (in Hz) |

```
S(i, j) = w_tags·S_tags + w_key·S_key + w_bpm·S_bpm + w_energy·S_energy + w_brightness·S_brightness
```

Weights are adjustable live in the Graph tab (defaults: tags 0.5, key 0.2, BPM 0.1, energy 0.1, brightness 0.1).

### 2. Transition graph *(behavioral truth)*

Your rated transitions form a **directed, sparse, authoritative** graph: `T(i, j)` = how well *i → j* actually worked, on a ★ / ★★ / ★★★ scale.

### Inference — generalizing your taste

To suggest next tracks for pairs you've never rated, the system propagates your ratings through similarity. Over the *k* most similar tracks `N(i)` to your current track:

```
T̂(i, j) = Σ_{m ∈ N(i)}  S(i, m) · T(m, j)

Score(i, j) = T(i, j) + λ · T̂(i, j)
```

So a direct rating always wins; where there's none, musically similar tracks lend their experience, scaled by λ. Both *k* and λ are tunable in the UI.

---

## Architecture

```
main.py                      Entry point — scan (CLI) or launch the UI + API server
build.spec                   PyInstaller build configuration
pyi_rth_fpcalc.py            Runtime hook to locate fpcalc in a bundled build
requirements.txt
companion_tutorial.txt       Phone-companion walkthrough
src/
  audio/
    fingerprint.py           Chromaprint fingerprint  → stable track identity
    analysis.py              BPM, key (Open Key), energy, brightness; Essentia→librosa fallback
    scanner.py               Folder walk → fingerprint → analyze → upsert
  db/
    schema.py                SQLite schema + connection
    queries.py               All database reads and writes
  graph/
    scoring.py               Similarity components and weighting
    builder.py               Graph data + next-track scoring
  api/
    server.py                Flask companion server (port 5000)
    static/companion.html    The phone web app
  ui/
    main_window.py           Tabs, shared DB connection, live auto-refresh
    library_tab.py           Searchable / taggable track table
    graph_tab.py             Force-directed graph (QtWebEngine)
    list_tab.py              Flat transition list
    options_tab.py           Profiles + scan settings
    transitions_widget.py    Per-track add / view / info / next-track panel
    tag_editor.py            Tag-editing dialog
    graph.html               Graph front-end
    force-graph.min.js       Force-directed graph renderer
```

### Data flow on scan

`scanner.py` walks the folder → `fingerprint.py` derives a stable ID via Chromaprint → `analysis.py` extracts BPM/key/energy/brightness and reads ID3 metadata (falling back to parsing `Artist - Title` from the filename) → `queries.py` upserts into SQLite.

### Database schema (`library.db`)

- **`tracks`** — `id` (fingerprint, PK), `path`, `title`, `artist`, `bpm`, `key_open`, `key_strength`, `energy`, `spectral_centroid`, `is_available`, `last_seen`
- **`tags`** / **`track_tags`** — many-to-many tagging
- **`transitions`** — `from_track`, `to_track`, `rating` (1–3), `notes`, `created_at`; unique per `(from, to)` pair

The database lives in the project root during development, and in the platform user-data directory (`~/.local/share/dj-companion` on Linux, `%APPDATA%\dj-companion` on Windows) for a bundled build. Each profile has its own `*.db` file.

### Open Key mapping

`OPEN_KEY_MAP` in `src/audio/analysis.py` maps every key/scale Essentia might output — including enharmonic spellings (e.g. `Ab minor` = `G# minor` = `6m`) — to Open Key notation. If an unmapped key ever appears, add both enharmonic spellings to the dict.

---

## Building a standalone app

The project ships a [PyInstaller](https://pyinstaller.org/) spec that bundles the Qt UI, the analysis stack, and the companion server into a single distributable:

```bash
.venv/bin/pyinstaller build.spec
```

The result lands in `dist/DJCompanion/`. On Windows, place `fpcalc.exe` in the project root before building so it gets bundled; on Linux, `fpcalc` is expected as a system package.

---

## Notes

- The `.gitignore` deliberately excludes your `library.db`, the `tracks/` folder, and build artifacts — your music and personal transition data never get committed.
- This is a personal/standalone tool: the companion server binds to your local network only and has no authentication, so run it on a trusted WiFi network.
