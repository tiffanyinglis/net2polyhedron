"""Cache the computed spanning tree + flat layout + fold angles for a
NetUnfolder, so re-loading an unchanged net is just a fast JSON parse
instead of recomputing them. Solving is now direct (see net_unfolder.py's
docstring -- fold angles are read off the given geometry, nothing is
numerically solved for), so this is more "avoid redundant recomputation"
than "avoid an expensive solve" -- but the contract mirrors this
project's other caches: a checksum of the source .json file (or, via
content_checksum, of an in-memory Polyhedron's own data when there's no
source file) decides whether the cache still applies.

Cache files live in whichever app needs them's own cache/ folder (e.g.
src/apps/polyhedron_unfolder/cache/) -- never data/, and never shared
between apps. Callers pass that cache directory explicitly via
cache_path_for's `cache_dir` param, since it's not simply a sibling of
net_path's own parent directory.
"""
import glob
import hashlib
import json
import os
import time

import numpy as np

from ..model.polyhedron import Polyhedron
from .hinge import Hinge

CHECKSUM_ALGO = "sha256"


def cache_path_for(net_path, cache_dir=None):
    """Where the cache for a given .json source lives. Defaults to
    <project root>/net_unfolder_cache/<basename>.json, where <project
    root> is the parent of the .json file's own directory (i.e. the
    parent of nets/)."""
    net_path = os.path.abspath(net_path)
    if cache_dir is None:
        project_root = os.path.dirname(os.path.dirname(net_path))
        cache_dir = os.path.join(project_root, "net_unfolder_cache")
    base = os.path.splitext(os.path.basename(net_path))[0]
    return os.path.join(cache_dir, base + ".json")


def content_checksum(polyhedron):
    """A checksum of an in-memory Polyhedron's own vertex/face data --
    used by NetUnfolder.for_polyhedron, which (unlike .load) has no
    source file to hash."""
    h = hashlib.new(CHECKSUM_ALGO)
    for v in polyhedron.vertices:
        h.update(np.round(np.asarray(v, dtype=float), 9).tobytes())
    for face in polyhedron.faces:
        h.update((",".join(map(str, face)) + ";").encode())
    return f"{CHECKSUM_ALGO}:{h.hexdigest()}"


def read_cache(cache_path):
    """The raw cache dict, or None if missing/corrupt -- doesn't need a
    Polyhedron, just the parsed JSON payload (so is_cached can stay a
    cheap, read-only check)."""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path) as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def is_cached(net_path, cache_path=None):
    """True if a valid, up-to-date cache already exists for net_path --
    i.e. loading it would be a fast parse, not a recompute. A read-only
    check: never deletes anything, so it's safe to call just to decide
    how to render a net (e.g. in the app's net list)."""
    from ..persistence.checksums import source_checksum
    cache_path = cache_path or cache_path_for(net_path)
    data = read_cache(cache_path)
    return data is not None and data.get("checksum") == source_checksum(net_path)


def _net_unfolder_from_cache(data, polyhedron):
    """Build a NetUnfolder from a valid cache dict + the (already parsed)
    source Polyhedron -- local import, see net_unfolder.py's own local
    import of this module for why."""
    from .net_unfolder import NetUnfolder

    flat_vertices = [np.array([x, y, 0.0]) for x, y in data["flat_vertices"]]
    flat_faces = [tuple(face) for face in data["flat_faces"]]
    flat = Polyhedron(vertices=flat_vertices, faces=flat_faces, name=polyhedron.name)
    hinges = [Hinge(parent_id=h["parent"], child_id=h["child"],
                     parent_edge_idx=h["parent_edge_idx"], child_edge_idx=h["child_edge_idx"],
                     angle=np.radians(h["angle_deg"]))
              for h in data["hinges"]]
    return NetUnfolder(polyhedron, data["root"], hinges, flat)


def _clear_stale_cache(cache_path, checksum):
    """Cheap, Polyhedron-free check: read the cache; if present but its
    checksum no longer matches, it no longer applies to anything, so
    delete it -- otherwise a failed recompute would leave a stale cache
    file behind that looks current. Returns the raw cache dict if it's
    still valid, else None. Used by build_all, which (unlike
    NetUnfolder.load/for_polyhedron) doesn't need a reconstructed
    NetUnfolder for a cache hit, just to know whether to skip -- so this
    doesn't require the source to have parsed successfully first."""
    data = read_cache(cache_path)
    if data is None:
        return None
    if data.get("checksum") != checksum:
        os.remove(cache_path)
        return None
    return data


def _valid_cache_or_clear_stale(cache_path, checksum, polyhedron):
    """Same staleness check as _clear_stale_cache, but returns a ready
    NetUnfolder (reconstructed against the given, already-parsed
    Polyhedron) instead of the raw cache dict -- what NetUnfolder.load/
    for_polyhedron need for an actual cache hit."""
    data = _clear_stale_cache(cache_path, checksum)
    if data is None:
        return None
    try:
        return _net_unfolder_from_cache(data, polyhedron)
    except (KeyError, ValueError):
        return None


def write_cache(cache_path, checksum, net):
    data = {
        "checksum": checksum,
        "name": net.polyhedron.name,
        "root": net.root,
        "flat_vertices": [[round(float(x), 6), round(float(y), 6)]
                           for x, y, _ in net.flat.vertices],
        "flat_faces": [list(face) for face in net.flat.faces],
        "hinges": [{"parent": h.parent_id, "child": h.child_id,
                     "parent_edge_idx": h.parent_edge_idx, "child_edge_idx": h.child_edge_idx,
                     "angle_deg": round(float(np.degrees(h.angle)), 6)}
                    for h in net.hinges],
    }
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)


def build_all(nets_dir, cache_dir=None, force=False, on_progress=None):
    """Compute/refresh the cache for every .json net in nets_dir.

    Shared by polyhedron_unfolder's build_cache.py CLI and its "Compute
    Folding Pattern" button, so both report progress the same way and
    stay in sync with how caching actually works.

    on_progress(i, n, label, status, elapsed=None), if given, is called
    once per net with status one of "skip", "start", "done", "failed".
    Returns a list of (path, ok, message) tuples.
    """
    from ..persistence.polyhedron_spec import load_polyhedron_spec
    from ..persistence.checksums import source_checksum
    from .net_unfolder import NetUnfolder

    paths = sorted(glob.glob(os.path.join(nets_dir, "*.json")))
    n = len(paths)
    results = []
    for i, path in enumerate(paths, 1):
        label = os.path.basename(path)
        cache_path = cache_path_for(path, cache_dir)
        checksum = source_checksum(path)

        # Deletes the cache as a side effect if it exists but its source
        # .json has since been edited (checksum mismatch) -- checked
        # before parsing, so a source that's been edited into invalidity
        # still correctly loses its now-inapplicable stale cache below.
        cached = _clear_stale_cache(cache_path, checksum)
        if cached is not None and not force:
            if on_progress:
                on_progress(i, n, label, "skip")
            results.append((path, True, "up to date"))
            continue

        try:
            vertices, faces, name = load_polyhedron_spec(path)
        except ValueError as e:
            if on_progress:
                on_progress(i, n, label, "failed")
            results.append((path, False, str(e)))
            continue
        polyhedron = Polyhedron(vertices=vertices, faces=faces, name=name)

        if on_progress:
            on_progress(i, n, label, "start")
        start = time.time()
        try:
            net = NetUnfolder._compute(polyhedron, root=0)
        except ValueError as e:
            if on_progress:
                on_progress(i, n, label, "failed")
            results.append((path, False, str(e)))
            continue
        write_cache(cache_path, checksum, net)
        elapsed = time.time() - start
        if on_progress:
            on_progress(i, n, label, "done", elapsed)
        results.append((path, True, f"solved in {elapsed:.2f}s"))

    return results
