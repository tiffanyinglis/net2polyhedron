"""Cache the (expensive) result of solving a .poly net's fold angles into a
.fold file, so re-loading an unchanged net is just a fast text parse
instead of a full combinatorial + numerical solve.

A .fold file has the same shape as the legacy explicit-coordinate net
format (see net_io.parse_net_body): computed vertex positions and fold
angles, spelled out plainly, plus a CHECKSUM line recording a hash of the
source .poly file it was generated from. If the source changes, the
checksum no longer matches and the cache is treated as stale and rebuilt.

Cache files live in a top-level fold_cache/ directory, kept separate from
the human-authored nets/ directory -- nets/ is what you hand-edit,
fold_cache/ is entirely computed/disposable output.
"""
import hashlib
import os

import numpy as np

from .net_fold_core import Net
from .net_io import load_polyhedron_net, parse_net_body

CHECKSUM_ALGO = "sha256"


def cache_path_for(poly_path, cache_dir=None):
    """Where the .fold cache for a given .poly source lives. Defaults to
    <project root>/fold_cache/<basename>.fold, where <project root> is the
    parent of the .poly file's own directory (i.e. the parent of nets/)."""
    poly_path = os.path.abspath(poly_path)
    if cache_dir is None:
        project_root = os.path.dirname(os.path.dirname(poly_path))
        cache_dir = os.path.join(project_root, "fold_cache")
    base = os.path.splitext(os.path.basename(poly_path))[0]
    return os.path.join(cache_dir, base + ".fold")


def source_checksum(poly_path):
    with open(poly_path, "rb") as f:
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


def load_with_cache(poly_path, cache_path=None):
    """Load a .poly net, reusing a cached .fold file if it's still valid
    for the current contents of poly_path; otherwise solve fresh and
    (re)write the cache."""
    cache_path = cache_path or cache_path_for(poly_path)
    checksum = source_checksum(poly_path)

    cached = read_fold_cache(cache_path)
    if cached is not None and cached[0] == checksum:
        _, net, root, hinges, fold_angles, name = cached
        return net, root, hinges, fold_angles, name

    net, root, hinges, fold_angles, name = load_polyhedron_net(poly_path)
    write_fold_cache(cache_path, checksum, net, root, hinges, fold_angles, name)
    return net, root, hinges, fold_angles, name
