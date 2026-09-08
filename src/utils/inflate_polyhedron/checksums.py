"""A tiny utility: hash a source file's bytes for cache-staleness checks.
Used by stretchy_cache.py."""
import hashlib

CHECKSUM_ALGO = "sha256"


def source_checksum(path):
    """path: file to hash. Returns f"{algo}:{hexdigest}" of its raw bytes."""
    with open(path, "rb") as f:
        digest = hashlib.new(CHECKSUM_ALGO, f.read()).hexdigest()
    return f"{CHECKSUM_ALGO}:{digest}"
