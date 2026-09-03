"""Cache the (expensive) result of solve_wireframe()-ing a stretchy .json
mesh, so re-loading an unchanged net is just a fast JSON parse instead of
a full least-squares relaxation -- the same idea as fold_cache.py for the
rigid pipeline, just a plain JSON file instead of the FACES/ROOT/FOLD
text format (there's no hinge tree or fold angle here to write out, just
per-vertex 3D positions and the summary stats solve_wireframe returns).

A cache file records the settled `positions`, the `stats` dict
(max/rms stretch, residual), and a CHECKSUM of the source .json it was
solved from, combined with stretchy_mesh.ALGORITHM_VERSION -- so either
the source .json changing OR solve_wireframe's algorithm itself changing
(see ALGORITHM_VERSION's docstring) makes the checksum no longer match,
and the cache is treated as stale and rebuilt.

Cache files live in a top-level stretchy_cache/ directory, kept separate
from the human-authored stretchy_nets/ directory, mirroring fold_cache/
vs nets/.

The cache always stores solve_wireframe's seed=0 result -- the one
canonical "this net's cached wireframe" answer. stretchy_polyhedron_init.py's
"Recompute Wireframe" button, which deliberately asks for a *different*
random embedding (solve_wireframe's underdetermined system has many valid
solutions), bypasses the cache entirely rather than overwriting it: the
cache is meant to make the ordinary "pick a net" path instant, not to
track whichever alternate embedding was last explored.
"""
import glob
import json
import os
import time

import numpy as np

from .fold_cache import source_checksum as _file_checksum
from .stretchy_mesh import load_stretchy_mesh, solve_wireframe, ALGORITHM_VERSION


def source_checksum(net_path):
    """The source .json's own content hash, combined with the current
    solve_wireframe ALGORITHM_VERSION -- see this module's docstring for
    why the version needs to be part of the cache key too, not just the
    file's bytes."""
    return f"{_file_checksum(net_path)}+algo{ALGORITHM_VERSION}"


def cache_path_for(net_path, cache_dir=None):
    """Where the cache for a given stretchy .json source lives. Defaults
    to <project root>/stretchy_cache/<basename>.json, where <project
    root> is the parent of the .json file's own directory (i.e. the
    parent of stretchy_nets/)."""
    net_path = os.path.abspath(net_path)
    if cache_dir is None:
        project_root = os.path.dirname(os.path.dirname(net_path))
        cache_dir = os.path.join(project_root, "stretchy_cache")
    base = os.path.splitext(os.path.basename(net_path))[0]
    return os.path.join(cache_dir, base + ".json")


def read_stretchy_cache(cache_path):
    """Returns (checksum, positions, stats, name), or None if the file
    doesn't exist or can't be parsed as a valid cache. positions is
    {vertex_id: np.array([x, y, z])}, same shape solve_wireframe returns."""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path) as f:
            data = json.load(f)
        checksum = data["checksum"]
        positions = {int(vid): np.array(xyz) for vid, xyz in data["positions"].items()}
        stats = data["stats"]
        name = data.get("name")
        if not positions:
            return None
        return checksum, positions, stats, name
    except (KeyError, ValueError, OSError, json.JSONDecodeError):
        return None


def write_stretchy_cache(cache_path, checksum, positions, stats, name):
    data = {
        "checksum": checksum,
        "name": name,
        "positions": {str(vid): [float(c) for c in xyz] for vid, xyz in positions.items()},
        "stats": stats,
    }
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def is_cached(net_path, cache_path=None):
    """True if a valid, up-to-date cache already exists for net_path --
    i.e. loading it would be a fast parse, not a solve. A read-only
    check: never deletes anything, so it's safe to call just to decide
    how to render a net (e.g. in the app's net list)."""
    cache_path = cache_path or cache_path_for(net_path)
    cached = read_stretchy_cache(cache_path)
    return cached is not None and cached[0] == source_checksum(net_path)


def _valid_cache_or_clear_stale(cache_path, checksum):
    """Read the cache; if present but its checksum no longer matches (the
    source .json was edited since), it no longer applies to anything, so
    delete it -- otherwise a failed re-solve would leave a stale cache
    file behind that looks like a real, current one. Returns the parsed
    cache tuple if it's still valid, else None."""
    cached = read_stretchy_cache(cache_path)
    if cached is None:
        return None
    if cached[0] != checksum:
        os.remove(cache_path)
        return None
    return cached


def load_with_cache(net_path, cache_path=None):
    """Load a stretchy .json net and its solved wireframe, reusing a
    cached result if it's still valid for the current contents of
    net_path; otherwise solve fresh (seed=0) and (re)write the cache.
    Returns (faces, positions, stats, name)."""
    faces, name = load_stretchy_mesh(net_path)
    cache_path = cache_path or cache_path_for(net_path)
    checksum = source_checksum(net_path)

    cached = _valid_cache_or_clear_stale(cache_path, checksum)
    if cached is not None:
        _, positions, stats, cached_name = cached
        return faces, positions, stats, cached_name or name

    positions, stats = solve_wireframe(faces, seed=0)
    write_stretchy_cache(cache_path, checksum, positions, stats, name)
    return faces, positions, stats, name


def build_all(nets_dir, force=False, on_progress=None):
    """Compute/refresh the cache for every stretchy .json net in
    nets_dir.

    Shared by build_stretchy_cache.py's CLI and the "Compute All
    Wireframes" button in stretchy_polyhedron_init.py, so both report
    progress the same way and stay in sync with how caching actually
    works.

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
            faces, name = load_stretchy_mesh(path)
            positions, stats = solve_wireframe(faces, seed=0)
        except ValueError as e:
            if on_progress:
                on_progress(i, n, label, "failed")
            results.append((path, False, str(e)))
            continue
        write_stretchy_cache(cache_path, checksum, positions, stats, name)
        elapsed = time.time() - start
        if on_progress:
            on_progress(i, n, label, "done", elapsed)
        results.append((path, True, f"solved in {elapsed:.2f}s"))

    return results
