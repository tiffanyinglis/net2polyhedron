"""
Parser for the simple net text-file format:

    # optional comment / name
    FACES
    0: x,y x,y x,y ...      <- polygon 0's vertices, in order, net-space coords
    1: x,y x,y ...
    ...

    ROOT <face_id>

    FOLD <face_id> <angle_degrees>   <- one line per non-root face
    FOLD <face_id> <angle_degrees>
    ...

Faces must be declared in order 0, 1, 2, ... (the id is just for readability
and cross-checked against declaration order). FOLD gives the rotation (in
degrees, from flat/180-degrees-coplanar) applied at that face's hinge to its
parent -- i.e. how far it swings when fully folded (t=1).
"""
import numpy as np
from net_fold_core import Net


def load_net_txt(path):
    faces_raw = []
    root = None
    fold_angles_deg = {}
    name = None

    with open(path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                if name is None:
                    name = line.lstrip("#").strip()
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
            if fid != len(faces_raw):
                raise ValueError(f"{path}: faces must be declared in order "
                                  f"(expected id {len(faces_raw)}, got {fid})")
            pts = [tuple(map(float, c.split(","))) for c in coords_str.strip().split()]
            faces_raw.append(pts)

    if root is None:
        raise ValueError(f"{path}: missing ROOT line")

    net = Net()
    for pts in faces_raw:
        net.add_face(pts)

    root_id, hinges = net.build_tree(root=root)
    fold_angles = {fid: np.radians(deg) for fid, deg in fold_angles_deg.items()}

    missing = [h["child"] for h in hinges if h["child"] not in fold_angles]
    if missing:
        raise ValueError(f"{path}: missing FOLD angle for face(s) {missing}")

    return net, root_id, hinges, fold_angles, (name or path)
