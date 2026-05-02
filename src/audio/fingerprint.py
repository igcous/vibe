import acoustid


def fingerprint(path: str) -> str | None:
    try:
        duration, fp = acoustid.fingerprint_file(path, force_fpcalc=True)
        return fp.decode() if isinstance(fp, bytes) else fp
    except acoustid.FingerprintGenerationError:
        return None
    except Exception:
        return None
