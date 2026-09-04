"""
Parser for the simple net text-file format (used both for hand-authored
legacy nets and for the .fold cache written by fold_cache.py):

    # optional comment / name
    CHECKSUM <algo>:<hex>            <- optional, only meaningful to fold_cache.py
    FACES
    0: x,y x,y x,y ...      <- polygon 0's vertices, in order, net-space coords
    1: x,y x,y ...
    ...

    ROOT <face_id>

    FOLD <face_id> <angle_degrees>   <- one line per non-root face
    FOLD <face_id> <angle_degrees>
    ...

Face ids must strictly increase top to bottom (mostly for readability and
to catch an out-of-order/duplicate id) but need not be contiguous -- an
OPEN net's .fold cache (see polyhedron_spec.py's module docstring) has
gaps where its omitted faces would be, since those are never built into
geometry. FOLD gives the rotation (in degrees, from flat/180-degrees-
coplanar) applied at that face's hinge to its parent -- i.e. how far it
swings when fully folded (t=1).
"""
import numpy as np
from ..geometry3d.net_fold_core import Net
from .polyhedron_spec import load_polyhedron_spec
from ..combinatorics.edge_map import EdgeMap
from ..geometry2d.net_layout import build_net_layout
from ..geometry3d.fold_solver import solve_fold_angles


def parse_net_body(f):
    """Parse the FACES/ROOT/FOLD body shared by the legacy .txt format and
    the .fold cache format. Returns (faces_raw, root, fold_angles_deg, name,
    checksum) -- checksum is None unless a CHECKSUM line was present.
    faces_raw is a list of (face_id, points) pairs, ids strictly
    increasing but not necessarily contiguous."""
    faces_raw = []
    last_fid = None
    root = None
    fold_angles_deg = {}
    name = None
    checksum = None

    for raw_line in f:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if name is None:
                name = line.lstrip("#").strip()
            continue
        if line.startswith("CHECKSUM"):
            checksum = line.split()[1]
            continue
        if line.startswith("FACES"):
            continue
        if line.startswith("ROOT"):
            root = int(line.split()[1])
            continue
        if line.startswith("FOLD"):
            _, fid, ang = line.split()
            fold_angles_deg[int(fid)] = float(ang)
            continue
        # face line: "<id>: x,y x,y x,y ..."
        fid_str, coords_str = line.split(":", 1)
        fid = int(fid_str.strip())
        if last_fid is not None and fid <= last_fid:
            raise ValueError(f"faces must be declared in strictly increasing "
                              f"id order (got {fid} after {last_fid})")
        last_fid = fid
        pts = [tuple(map(float, c.split(","))) for c in coords_str.strip().split()]
        faces_raw.append((fid, pts))

    return faces_raw, root, fold_angles_deg, name, checksum


def load_net_txt(path):
    with open(path) as f:
        faces_raw, root, fold_angles_deg, name, _ = parse_net_body(f)

    if root is None:
        raise ValueError(f"{path}: missing ROOT line")

    net = Net()
    for fid, pts in faces_raw:
        net.add_face(pts, fid=fid)

    root_id, hinges = net.build_tree(root=root)
    fold_angles = {fid: np.radians(deg) for fid, deg in fold_angles_deg.items()}

    missing = [h["child"] for h in hinges if h["child"] not in fold_angles]
    if missing:
        raise ValueError(f"{path}: missing FOLD angle for face(s) {missing}")

    return net, root_id, hinges, fold_angles, (name or path)


def load_polyhedron_net(path):
    """Load the abstract JSON faces/edges spec format (see
    polyhedron_spec.py) and derive everything else: the 2D net layout and
    every fold angle. This is the slow path -- it runs the full
    combinatorial + numerical solve; see fold_cache.py for a checksummed
    cache that avoids repeating it.

    For an OPEN net (some faces marked "omit"), edge_map is built from
    every edge -- including "hidden" ones touching an omitted face -- so
    the faces that ARE present still recover their correct polygon-edge
    index (see polyhedron_spec.py's module docstring), but only net_edges
    and extra_edges (never hidden_edges) go on to actually build geometry
    or constrain the fold, since an omitted face has neither."""
    degrees, net_edges, extra_edges, hidden_edges, omitted, root, name = \
        load_polyhedron_spec(path)
    edge_map = EdgeMap(degrees, net_edges + extra_edges + hidden_edges)
    net, hinges = build_net_layout(degrees, net_edges, edge_map, root, omitted)
    fold_angles = solve_fold_angles(net, root, hinges, extra_edges, edge_map)
    return net, root, hinges, fold_angles, name


def load_net(path, cache_dir=None):
    """Dispatch to the right loader by file extension: .json for the
    abstract combinatorial spec (via the .fold cache, see fold_cache.py),
    .txt for the legacy explicit-coordinate format.

    cache_dir, if given, overrides where the .fold cache is looked up/written
    (see fold_cache.cache_path_for) -- needed whenever the cache directory
    isn't simply a sibling of path's own parent directory."""
    if path.endswith(".json"):
        from .fold_cache import load_with_cache, cache_path_for
        cache_path = cache_path_for(path, cache_dir) if cache_dir else None
        return load_with_cache(path, cache_path=cache_path)
    return load_net_txt(path)
