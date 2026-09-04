"""
Parser for the simple net text-file format (used both for hand-authored
legacy nets and for the .fold cache written by fold_cache.py):

    # optional comment / name
    CHECKSUM <algo>:<hex>            <- optional, only meaningful to fold_cache.py
    FACES
    0: x,y x,y x,y ...      <- polygon 0's vertices, in order, net-space coords
    1: x,y x,y ...
    ...

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

There's no ROOT line: the unfold root is always the first (lowest-id)
face present -- net_fold_core.Net.build_tree(root=None) derives it that
way directly from the FACES block, so it never needs to be spelled out
separately (see polyhedron_spec.py's module docstring for why any face
works equally well as root).

Loading a net (.json spec or this legacy .txt format) into the actual
object model is model.PolyhedralNet.load() -- this module only holds the
shared text-parsing plumbing that both PolyhedralNet and persistence.fold_cache
build on.
"""


def parse_net_body(f):
    """Parse the FACES/FOLD body shared by the legacy .txt format and the
    .fold cache format. Returns (faces_raw, fold_angles_deg, name,
    checksum) -- checksum is None unless a CHECKSUM line was present.
    faces_raw is a list of (face_id, points) pairs, ids strictly
    increasing but not necessarily contiguous."""
    faces_raw = []
    last_fid = None
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

    return faces_raw, fold_angles_deg, name, checksum
