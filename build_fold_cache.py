"""Precompute and cache the fold for every net in nets/, so the app never
has to run the (potentially slow) combinatorial + numerical solve at load
time -- it just reads back the cached result in fold_cache/ if the source
.poly is unchanged.

    python build_fold_cache.py            # only nets whose cache is stale
    python build_fold_cache.py --force     # recompute every net

The same logic backs the "Compute Folding Pattern" button in
polygon_fold_app.py (see net_fold_utils.fold_cache.build_all).
"""
import argparse
import os

from net_fold_utils.fold_cache import build_all

NETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nets")


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

    results = build_all(NETS_DIR, force=args.force, on_progress=_print_progress)
    if not results:
        print(f"no .poly nets found in {NETS_DIR}")
        return

    for path, ok, message in results:
        if not ok:
            print(f"{os.path.basename(path)}: {message}")


if __name__ == "__main__":
    main()
