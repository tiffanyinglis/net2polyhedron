"""Cache the (expensive) result of solve_wireframe()-ing a stretchy .json
mesh, so re-loading an unchanged net is just a fast JSON parse instead of
a full least-squares relaxation -- the same idea as fold_cache.py for the
rigid pipeline, just a plain JSON file instead of the FACES/FOLD text
format (there's no hinge tree or fold angle here to write out, just
per-vertex 3D positions and the summary stats solve_wireframe returns).

A cache file records the settled `positions`, the `stats` dict
(max/rms stretch, residual), and a CHECKSUM of the source .json it was
solved from, combined with stretchy_mesh.ALGORITHM_VERSION -- so either
the source .json changing OR solve_wireframe's algorithm itself changing
(see ALGORITHM_VERSION's docstring) makes the checksum no longer match,
and the cache is treated as stale and rebuilt.

Cache files live in inflate_polyhedron_app's own cache/ folder (next to
its app.py) -- never data/, and never shared with any other app's cache
(e.g. polyhedron_unfolder's rigid fold cache is a completely separate
pipeline and directory). Callers pass that cache directory explicitly via
cache_path_for's `cache_dir` param, since it's not simply a sibling of
net_path's own parent directory (see cache_path_for's docstring for the
default derivation still used when cache_dir is omitted, e.g. in tests).

The cache always stores seed=0's result -- the one canonical "this net's
cached wireframe" answer -- via `_solve` (see below), which is
solve_wireframe(faces, seed) for an ordinary net, or
mesh_subdivide.solve_fabric_mesh(coarse_faces, resolution, seed) for a
fabric-subdivided one (see mesh_subdivide.load_fabric_spec and
generate_subdivided_stretchy_nets.py) -- plain solve_wireframe on a
subdivided mesh's fine faces, at its usual uniform edge_length=1.0, was
tried first and either takes a very long time or settles into a
generic, unrecognizable rounded blob (see mesh_subdivide.py's
docstring), so a fabric net needs the coarse-solve-then-drape approach
instead. inflate_polyhedron_app's "Recompute Wireframe" button,
which deliberately asks for a *different* random embedding (the
underlying system has many valid solutions), bypasses the cache entirely
rather than overwriting it: the cache is meant to make the ordinary
"pick a net" path instant, not to track whichever alternate embedding
was last explored.
"""
import glob
import json
import os
import time

import numpy as np

from .fold_cache import source_checksum as _file_checksum
from ..geometry3d.stretchy_mesh import load_stretchy_mesh, solve_wireframe, ALGORITHM_VERSION
from ..subdivisions.mesh_subdivide import load_fabric_spec, solve_fabric_mesh


def _solve(net_path, faces, seed):
    """Solve a stretchy net for caching -- solve_fabric_mesh (drape the
    fine mesh over the coarse net's own correctly-shaped, correctly-
    rounded solve) for a fabric-subdivided net (one with "coarse_faces",
    see mesh_subdivide.load_fabric_spec and
    tools/generate_subdivided_stretchy_nets.py), else plain
    solve_wireframe at the usual uniform edge_length=1.0. Both return
    (positions, stats); solve_fabric_mesh's extra (fine_faces,
    face_of_fine) are discarded here since they're already stored
    verbatim in the net's own JSON (deterministically reproducible from
    the same coarse_faces/resolution, so there's no risk of drift)."""
    coarse_faces, resolution, _ = load_fabric_spec(net_path)
    if coarse_faces is not None:
        _, _, positions, stats = solve_fabric_mesh(coarse_faces, resolution, seed=seed)
        return positions, stats
    return solve_wireframe(faces, seed=seed)


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

    positions, stats = _solve(net_path, faces, seed=0)
    write_stretchy_cache(cache_path, checksum, positions, stats, name)
    return faces, positions, stats, name


def build_all(nets_dir, cache_dir=None, force=False, on_progress=None):
    """Compute/refresh the cache for every stretchy .json net in
    nets_dir.

    Shared by inflate_polyhedron_app's build_cache.py CLI and its
    "Compute All Wireframes" button, so both report progress the same
    way and stay in sync with how caching actually works.

    cache_dir, if given, overrides where each net's cache is looked up/
    written (see cache_path_for) -- needed whenever the cache directory
    isn't simply a sibling of nets_dir's own parent directory.

    on_progress(i, n, label, status, elapsed=None), if given, is called
    once per net with status one of "skip", "start", "done", "failed".
    Returns a list of (path, ok, message) tuples.
    """
    paths = sorted(glob.glob(os.path.join(nets_dir, "*.json")))
    n = len(paths)
    results = []
    for i, path in enumerate(paths, 1):
        label = os.path.basename(path)
        cache_path = cache_path_for(path, cache_dir)
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
            positions, stats = _solve(path, faces, seed=0)
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
