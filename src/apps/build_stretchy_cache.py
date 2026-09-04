"""Precompute and cache the wireframe solve for every net in
data/input/stretchy_nets/, so stretchy_polyhedron_init.py never has to run
the (potentially slow) least-squares relaxation at load time -- it just
reads back the cached result in data/cache/stretchy_cache/ if the source
.json is unchanged.

    python src/apps/build_stretchy_cache.py            # only nets whose cache is stale
    python src/apps/build_stretchy_cache.py --force     # recompute every net

The same logic backs the "Compute All Wireframes" button in
stretchy_polyhedron_init.py (see utils.persistence.stretchy_cache.build_all).
"""
import argparse
import os

from paths import STRETCHY_NETS_DIR, STRETCHY_CACHE_DIR
from utils.persistence.stretchy_cache import build_all


def _print_progress(i, n, label, status, elapsed=None):
    tag = f"[{i}/{n}] {label}"
    if status == "skip":
        print(f"{tag}: up to date, skipping")
    elif status == "start":
        print(f"{tag}: solving...", flush=True)
    elif status == "done":
        print(f"{tag}: done in {elapsed:.2f}s")
    elif status == "failed":
        print(f"{tag}: FAILED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                         help="recompute even if the cache looks up to date")
    args = parser.parse_args()

    results = build_all(STRETCHY_NETS_DIR, cache_dir=STRETCHY_CACHE_DIR, force=args.force,
                         on_progress=_print_progress)
    if not results:
        print(f"no .json nets found in {STRETCHY_NETS_DIR}")
        return

    for path, ok, message in results:
        if not ok:
            print(f"{os.path.basename(path)}: {message}")


if __name__ == "__main__":
    main()
