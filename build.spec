# PyInstaller spec for DJ Transition Companion
# Run: .venv/bin/pyinstaller build.spec   (Linux)
#      pyinstaller build.spec             (Windows, inside venv)

import os
import sys as _sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ── Data files ────────────────────────────────────────────────────────────────
app_datas = [
    ('src/ui/graph.html',          'src/ui'),
    ('src/ui/force-graph.min.js',  'src/ui'),
]

librosa_datas, librosa_bins, librosa_hidden   = collect_all('librosa')
numba_datas,   numba_bins,   numba_hidden     = collect_all('numba')
llvmlite_datas, llvmlite_bins, llvmlite_hidden = collect_all('llvmlite')

datas    = app_datas + librosa_datas + numba_datas + llvmlite_datas
binaries = librosa_bins + numba_bins + llvmlite_bins

# Bundle fpcalc.exe on Windows (system package on Linux)
if _sys.platform == 'win32' and os.path.exists('fpcalc.exe'):
    binaries += [('fpcalc.exe', '.')]

# ── Hidden imports ────────────────────────────────────────────────────────────
hidden_imports = (
    librosa_hidden + numba_hidden + llvmlite_hidden + [
        'essentia',
        'essentia.standard',
        'pyacoustid',
        'mutagen',
        'mutagen.mp3',
        'mutagen.id3',
        'resampy',
        'soundfile',
        'scipy.signal',
        'scipy.fft',
        'scipy.special',
        'sklearn',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
        'PySide6.QtNetwork',
        'sqlite3',
    ]
)

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_fpcalc.py'],
    excludes=['tkinter', 'matplotlib', 'IPython', 'notebook'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Executable ────────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DJCompanion',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

# ── Collect into dist/DJCompanion/ ───────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='DJCompanion',
)
