import os
import sys

import acoustid


def _discover_fpcalc() -> None:
    """If the FPCALC env var is unset, point it at a co-located fpcalc binary.

    Lets a user drop fpcalc(.exe) into the project root (or the PyInstaller bundle
    dir) and have it found without editing PATH. A bare `fpcalc` on PATH still
    works as acoustid's default when nothing is found here.
    """
    if os.environ.get("FPCALC"):
        return

    name = "fpcalc.exe" if sys.platform == "win32" else "fpcalc"
    # Project root is three levels up from this file (src/audio/fingerprint.py).
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates = [os.path.join(project_root, name)]
    if getattr(sys, "frozen", False):
        candidates.insert(0, os.path.join(getattr(sys, "_MEIPASS", ""), name))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            os.environ["FPCALC"] = candidate
            return


_discover_fpcalc()


def fingerprint(path: str) -> str | None:
    try:
        duration, fp = acoustid.fingerprint_file(path, force_fpcalc=True)
        return fp.decode() if isinstance(fp, bytes) else fp
    except acoustid.NoBackendError as exc:
        # fpcalc executable not found — fatal for the whole scan, so surface it
        # instead of silently skipping every track.
        raise RuntimeError(
            "fpcalc not found. Install Chromaprint and put fpcalc on PATH, "
            "place fpcalc.exe in the project root, or set the FPCALC env var. "
            "See https://acoustid.org/chromaprint"
        ) from exc
    except acoustid.FingerprintGenerationError:
        # Genuinely unreadable/unanalyzable file — skip just this one.
        return None
    except Exception:
        return None
