try:
    import os as _os, sys as _sys
    _fd = _sys.stderr.fileno()
    _saved = _os.dup(_fd)
    _null = _os.open(_os.devnull, _os.O_WRONLY)
    _os.dup2(_null, _fd)
    _os.close(_null)
    import essentia.standard as es
    _os.dup2(_saved, _fd)
    _os.close(_saved)
    del _os, _sys, _fd, _saved, _null
    _ESSENTIA_AVAILABLE = True
except Exception:
    _ESSENTIA_AVAILABLE = False

import numpy as np
import librosa
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError
import os
import sys

# Krumhansl-Schmuckler key profiles (pitch class order: C C# D D# E F F# G G# A A# B)
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_CHROMA_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _key_from_chroma(chroma_mean: np.ndarray) -> tuple[str, str, float]:
    best_key, best_scale, best_r = "C", "major", -2.0
    for i, key_name in enumerate(_CHROMA_KEYS):
        rotated = np.roll(chroma_mean, -i)
        for profile, scale in ((_KS_MAJOR, "major"), (_KS_MINOR, "minor")):
            r = float(np.corrcoef(rotated, profile)[0, 1])
            if r > best_r:
                best_r, best_key, best_scale = r, key_name, scale
    return best_key, best_scale, (best_r + 1.0) / 2.0

_ANALYSIS_DURATION = 60.0   # seconds of audio to analyse
_SAMPLE_RATE = 44100

OPEN_KEY_MAP: dict[tuple[str, str], str] = {
    # 1
    ("C",  "major"): "1d",  ("A",  "minor"): "1m",
    # 2
    ("G",  "major"): "2d",  ("E",  "minor"): "2m",
    # 3
    ("D",  "major"): "3d",  ("B",  "minor"): "3m",
    # 4
    ("A",  "major"): "4d",  ("F#", "minor"): "4m",
                             ("Gb", "minor"): "4m",
    # 5
    ("E",  "major"): "5d",  ("C#", "minor"): "5m",
                             ("Db", "minor"): "5m",
    # 6
    ("B",  "major"): "6d",  ("G#", "minor"): "6m",
    ("Cb", "major"): "6d",  ("Ab", "minor"): "6m",
    # 7
    ("F#", "major"): "7d",  ("D#", "minor"): "7m",
    ("Gb", "major"): "7d",  ("Eb", "minor"): "7m",
    # 8
    ("Db", "major"): "8d",  ("Bb", "minor"): "8m",
    ("C#", "major"): "8d",  ("A#", "minor"): "8m",
    # 9
    ("Ab", "major"): "9d",  ("F",  "minor"): "9m",
    ("G#", "major"): "9d",
    # 10
    ("Eb", "major"): "10d", ("C",  "minor"): "10m",
    ("D#", "major"): "10d",
    # 11
    ("Bb", "major"): "11d", ("G",  "minor"): "11m",
    ("A#", "major"): "11d",
    # 12
    ("F",  "major"): "12d", ("D",  "minor"): "12m",
}

# Essentia uses "major"/"minor" — normalize aliases
_SCALE_ALIASES = {"maj": "major", "min": "minor"}


def analyze_audio(path: str) -> dict:
    result: dict = {"bpm": None, "key_open": None, "key_strength": None,
                    "energy": None, "spectral_centroid": None}

    if _ESSENTIA_AVAILABLE:
        try:
            audio = es.MonoLoader(filename=path, sampleRate=_SAMPLE_RATE)()
            max_samples = int(_ANALYSIS_DURATION * _SAMPLE_RATE)
            if len(audio) > max_samples:
                audio = audio[:max_samples]
        except Exception:
            return result

        try:
            bpm_val, *_ = es.RhythmExtractor2013(method="multifeature")(audio)
            result["bpm"] = int(round(float(bpm_val)))
        except Exception:
            pass

        try:
            key, scale, strength = es.KeyExtractor()(audio)
            scale = _SCALE_ALIASES.get(scale, scale)
            result["key_open"] = to_open_key(key, scale)
            result["key_strength"] = float(strength)
        except Exception:
            pass

        try:
            result["energy"] = float(np.sqrt(np.mean(audio ** 2)))
        except Exception:
            pass

        try:
            spectrum = es.Spectrum()(audio)
            result["spectral_centroid"] = float(es.Centroid(range=_SAMPLE_RATE / 2)(spectrum))
        except Exception:
            pass
    else:
        try:
            y, sr = librosa.load(path, sr=_SAMPLE_RATE, duration=_ANALYSIS_DURATION, mono=True)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            # librosa 0.11 returns tempo as a 1-D array; float() on a non-0-d
            # numpy array raises under numpy 2.x, so pull out the scalar.
            result["bpm"] = int(round(float(np.atleast_1d(tempo)[0])))
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            key, scale, strength = _key_from_chroma(chroma.mean(axis=1))
            result["key_open"] = to_open_key(key, scale)
            result["key_strength"] = strength
            result["energy"] = float(librosa.feature.rms(y=y).mean())
            result["spectral_centroid"] = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
        except Exception as exc:
            print(f"analysis failed for {path}: {exc}", file=sys.stderr)

    return result


def to_open_key(key: str, scale: str) -> str | None:
    return OPEN_KEY_MAP.get((key, scale))


def _clean_artifact(s: str) -> str:
    return s.replace("(esmp3.cc)", "").strip()


def read_metadata(path: str) -> dict:
    title = None
    artist = None
    try:
        audio = MP3(path)
        tags = audio.tags
        if tags:
            title = str(tags.get("TIT2", "")).strip() or None
            artist = str(tags.get("TPE1", "")).strip() or None
    except (ID3NoHeaderError, Exception):
        pass

    if not title or not artist:
        basename = os.path.splitext(os.path.basename(path))[0]
        cleaned = _clean_artifact(basename)

        if " - " in cleaned:
            left, _, right = cleaned.partition(" - ")
            parsed_artist = left.strip() or None
            parsed_title = right.strip() or None

            if not artist:
                artist = parsed_artist
            if not title:
                title = parsed_title

        if not title:
            title = cleaned or basename

    # Strip "Artist - " prefix that got embedded in the title
    if title and artist:
        prefix = artist + " - "
        if title.startswith(prefix):
            title = title[len(prefix):]
    if title:
        title = _clean_artifact(title)

    return {"title": title, "artist": artist}


