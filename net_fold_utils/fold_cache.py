"""Cache the (expensive) result of solving a .json net's fold angles into a
.fold file, so re-loading an unchanged net is just a fast text parse
instead of a full combinatorial + numerical solve.

A .fold file has the same shape as the legacy explicit-coordinate net
format (see net_io.parse_net_body): computed vertex positions and fold
angles, spelled out plainly, plus a CHECKSUM line recording a hash of the
source .json file it was generated from. If the source changes, the
checksum no longer matches and the cache is treated as stale and rebuilt.

Cache files live in a top-level fold_cache/ directory, kept separate from
the human-authored nets/ directory -- nets/ is what you hand-edit,
fold_cache/ is entirely computed/disposable output.
"""
import glob
import hashlib
import os
import time

import numpy as np

from .net_fold_core import Net
from .net_io import load_polyhedron_net, parse_net_body

CHECKSUM_ALGO = "sha256"


def cache_path_for(net_path, cache_dir=None):
    """Where the .fold cache for a given .json source lives. Defaults to
    <project root>/fold_cache/<basename>.fold, where <project root> is the
    parent of the .json file's own directory (i.e. the parent of nets/)."""
    net_path = os.path.abspath(net_path)
    if cache_dir is None:
        project_root = os.path.dirname(os.path.dirname(net_path))
        cache_dir = os.path.join(project_root, "fold_cache")
    base = os.path.splitext(os.path.basename(net_path))[0]
    return os.path.join(cache_dir, base + ".fold")


def source_checksum(net_path):
    with open(net_path, "rb") as f:
        digest = hashlib.new(CHECKSUM_ALGO, f.read()).hexdigest()
    return f"{CHECKSUM_ALGO}:{digest}"


def read_fold_cache(cache_path):
    """Returns (checksum, net, root, hinges, fold_angles, name), or None if
    the file doesn't exist or can't be parsed as a valid cache."""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path) as f:
            faces_raw, root, fold_angles_deg, name, checksum = parse_net_body(f)
        if root is None or checksum is None or not faces_raw:
            return None
        net = Net()
        for pts in faces_raw:
            net.add_face(pts)
        root_id, hinges = net.build_tree(root=root)
        fold_angles = {fid: np.radians(deg) for fid, deg in fold_angles_deg.items()}
        if any(h["child"] not in fold_angles for h in hinges):
            return None
        return checksum, net, root_id, hinges, fold_angles, name
    except (ValueError, OSError):
        return None


def write_fold_cache(cache_path, checksum, net, root, hinges, fold_angles, name):
    lines = []
    if name:
        lines.append(f"# {name}")
    lines.append(f"CHECKSUM {checksum}")
    lines.append("FACES")
    for fid in sorted(net.faces):
        coords = " ".join(f"{p[0]:.6f},{p[1]:.6f}" for p in net.faces[fid])
        lines.append(f"{fid}: {coords}")
    lines.append("")
    lines.append(f"ROOT {root}")
    lines.append("")
    for h in hinges:
        child = h["child"]
        lines.append(f"FOLD {child} {np.degrees(fold_angles[child]):.6f}")
    lines.append("")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        f.write("\n".join(lines))


def is_cached(net_path, cache_path=None):
    """True if a valid, up-to-date .fold cache already exists for
    net_path -- i.e. loading it would be a fast parse, not a solve. A
    read-only check: never deletes anything, so it's safe to call just to
    decide how to render a net (e.g. in the app's net list)."""
    cache_path = cache_path or cache_path_for(net_path)
    cached = read_fold_cache(cache_path)
    return cached is not None and cached[0] == source_checksum(net_path)


def _valid_cache_or_clear_stale(cache_path, checksum):
    """Read the cache; if present but its checksum no longer matches (the
    source .json was edited since), it no longer applies to anything, so
    delete it -- otherwise a failed re-solve would leave a stale .fold file
    behind that looks like a real, current cache. Returns the parsed cache
    tuple if it's still valid, else None."""
    cached = read_fold_cache(cache_path)
    if cached is None:
        return None
    if cached[0] != checksum:
        os.remove(cache_path)
        return None
    return cached


def load_with_cache(net_path, cache_path=None):
    """Load a .json net, reusing a cached .fold file if it's still valid
    for the current contents of net_path; otherwise solve fresh and
    (re)write the cache."""
    cache_path = cache_path or cache_path_for(net_path)
    checksum = source_checksum(net_path)

    cached = _valid_cache_or_clear_stale(cache_path, checksum)
    if cached is not None:
        _, net, root, hinges, fold_angles, name = cached
        return net, root, hinges, fold_angles, name

    net, root, hinges, fold_angles, name = load_polyhedron_net(net_path)
    write_fold_cache(cache_path, checksum, net, root, hinges, fold_angles, name)
    return net, root, hinges, fold_angles, name


def build_all(nets_dir, force=False, on_progress=None):
    """Compute/refresh the .fold cache for every .json net in nets_dir.

    Shared by the build_fold_cache.py CLI and the "Compute Folding
    Pattern" button in polygon_fold_app.py, so both report progress the
    same way and stay in sync with how caching actually works.

    on_progress(i, n, label, status, elapsed=None), if given, is called
    once per net with status one of "skip", "start", "done", "failed".
    Returns a list of (path, ok, message) tuples.
    """
    paths = sorted(glob.glob(os.path.join(nets_dir, "*.json")))
    n = len(paths)
    results = []
    for i, path in enumerate(paths, 1):
        label = os.path.basename(path)
        cache_path = cache_path_for(path)
        checksum = source_checksum(path)

        # Deletes the cache as a side effect if it exists but its source
        # .json has since been edited (checksum mismatch) -- that cache no
        # longer describes anything real, so it shouldn't survive a failed
        # re-solve below.
        cached = _valid_cache_or_clear_stale(cache_path, checksum)
        if cached is not None and not force:
            if on_progress:
                on_progress(i, n, label, "skip")
            results.append((path, True, "up to date"))
            continue

        if on_progress:
            on_progress(i, n, label, "start")
        start = time.time()
        try:
            net, root, hinges, fold_angles, name = load_polyhedron_net(path)
        except ValueError as e:
            if on_progress:
                on_progress(i, n, label, "failed")
            results.append((path, False, str(e)))
            continue
        write_fold_cache(cache_path, checksum, net, root, hinges, fold_angles, name)
        elapsed = time.time() - start
        if on_progress:
            on_progress(i, n, label, "done", elapsed)
        results.append((path, True, f"solved in {elapsed:.2f}s"))

    return results
