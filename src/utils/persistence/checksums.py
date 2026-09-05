"""A shared, tiny utility: hash a source file's bytes for cache-staleness
checks. Used by both net_unfolder/cache.py (the rigid pipeline) and
stretchy_cache.py (the stretchy pipeline) -- neither pipeline's cache
concept is specific to the other, so this lives here instead of inside
either one."""
import hashlib

CHECKSUM_ALGO = "sha256"


def source_checksum(path):
    with open(path, "rb") as f:
        digest = hashlib.new(CHECKSUM_ALGO, f.read()).hexdigest()
    return f"{CHECKSUM_ALGO}:{digest}"
