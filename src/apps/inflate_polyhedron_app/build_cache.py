"""Precompute and cache the wireframe solve for every net in
data/input/stretchy_nets/, so inflate_polyhedron_app never has to run the
(potentially slow) least-squares relaxation at load time -- it just reads
back the cached result in this app's own cache/ folder (next to this
file) if the source .json is unchanged.

    python src/apps/inflate_polyhedron_app/build_cache.py            # only nets whose cache is stale
    python src/apps/inflate_polyhedron_app/build_cache.py --force     # recompute every net

The same logic backs the "Compute All Wireframes" button in app.py (see
utils.inflate_polyhedron.stretchy_cache.build_all). This cache is this
app's own -- not shared with any other app.
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import argparse
import os

from common.paths import STRETCHY_NETS_DIR
from utils.inflate_polyhedron.stretchy_cache import build_all

CACHE_DIR = Path(__file__).resolve().parent / "cache"


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

    results = build_all(STRETCHY_NETS_DIR, cache_dir=CACHE_DIR, force=args.force,
                         on_progress=_print_progress)
    if not results:
        print(f"no .json nets found in {STRETCHY_NETS_DIR}")
        return

    for path, ok, message in results:
        if not ok:
            print(f"{os.path.basename(path)}: {message}")


if __name__ == "__main__":
    main()
