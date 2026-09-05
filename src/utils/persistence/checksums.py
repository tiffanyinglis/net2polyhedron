"""A tiny utility: hash a source file's bytes for cache-staleness checks.
Used by stretchy_cache.py (the rigid pipeline has no cache of its own --
see utils.polyhedron_unfolder's module docstring)."""
import hashlib

CHECKSUM_ALGO = "sha256"


def source_checksum(path):
    with open(path, "rb") as f:
        digest = hashlib.new(CHECKSUM_ALGO, f.read()).hexdigest()
    return f"{CHECKSUM_ALGO}:{digest}"
