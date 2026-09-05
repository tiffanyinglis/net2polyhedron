"""One-off generator: writes data/input/nets/<solid>.json for each of the 5
Platonic solids (plus the truncated icosahedron), deriving each face's
vertex-index loop straight from canonical 3D vertex coordinates.
NetUnfolder (src/utils/net_unfolder/) derives its own spanning tree/flat
layout/fold angles at load time, so nothing about the net itself needs
deriving here -- this just writes out the polyhedron's own geometry.

    python src/apps/common/generate_platonic_nets.py
"""
import os

from paths import NETS_DIR
from utils.geometry3d.solid_coords import SOLIDS
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from utils.persistence.polyhedron_spec import write_polyhedron_spec


def main():
    for name, coord_fn in SOLIDS.items():
        vertices = coord_fn()
        _, _, face_loops = polyhedron_from_vertices(vertices)
        out_path = os.path.join(NETS_DIR, f"{name}.json")
        write_polyhedron_spec(out_path, vertices, face_loops, name=name.capitalize())
        print(f"wrote {out_path}  ({len(vertices)} vertices, {len(face_loops)} faces)")


if __name__ == "__main__":
    main()
