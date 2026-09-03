"""Precompute and cache the fold for every net in nets/, so the app never
has to run the (potentially slow) combinatorial + numerical solve at load
time -- it just reads back the cached result in fold_cache/ if the source
.poly is unchanged.

    python build_fold_cache.py            # only nets whose cache is stale
    python build_fold_cache.py --force     # recompute every net
"""
import argparse
import glob
import os
import time

from net_fold_utils.net_io import load_polyhedron_net
from net_fold_utils.fold_cache import (
    cache_path_for, source_checksum, read_fold_cache, write_fold_cache,
)

NETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nets")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                         help="recompute even if the cache looks up to date")
    args = parser.parse_args()

    paths = sorted(glob.glob(os.path.join(NETS_DIR, "*.poly")))
    if not paths:
        print(f"no .poly nets found in {NETS_DIR}")
        return

    for i, path in enumerate(paths, 1):
        label = os.path.basename(path)
        tag = f"[{i}/{len(paths)}] {label}"
        cache_path = cache_path_for(path)
        checksum = source_checksum(path)

        if not args.force:
            cached = read_fold_cache(cache_path)
            if cached is not None and cached[0] == checksum:
                print(f"{tag}: up to date, skipping")
                continue

        print(f"{tag}: solving...", flush=True)
        start = time.time()
        try:
            net, root, hinges, fold_angles, name = load_polyhedron_net(path)
        except ValueError as e:
            print(f"{tag}: FAILED -- {e}")
            continue
        write_fold_cache(cache_path, checksum, net, root, hinges, fold_angles, name)
        elapsed = time.time() - start
        print(f"{tag}: done in {elapsed:.2f}s -> {os.path.relpath(cache_path)}")


if __name__ == "__main__":
    main()
