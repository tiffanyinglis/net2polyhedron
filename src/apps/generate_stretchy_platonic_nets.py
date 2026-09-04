"""One-off generator: writes data/input/stretchy_nets/<solid>.json for each
of the 5 Platonic solids, in the vertex-loop format
utils/geometry3d/stretchy_mesh.py expects (see its module docstring) --
reusing hull_to_spec.py's `polyhedron_from_vertices`, which already
derives each face's CCW, outward-oriented vertex loop straight from the
solid's canonical 3D coordinates (utils/geometry3d/solid_coords.py).
That's the SAME source generate_platonic_nets.py builds the rigid
data/input/nets/*.json specs from; this is just a different (and, for
genuinely rigid/closed solids like these, strictly simpler -- no spanning
tree, no root, no fold angles to solve for) serialization of the same
combinatorial structure.

    python src/apps/generate_stretchy_platonic_nets.py

These are here to check the stretchy pipeline against nets we already
know the RIGID answer for: since a Platonic solid's faces genuinely can
stay flat and unit-edge, solve_wireframe() should find each one with
~0% stretch and every face landing essentially exactly flat -- unlike
data/input/stretchy_nets/two_pentagons_and_a_square.json, which needs
real bending. See tests/unit/geometry3d/test_stretchy_mesh.py.
"""
import json
import os

from paths import STRETCHY_NETS_DIR
from utils.geometry3d.solid_coords import SOLIDS
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices

PLATONIC_SOLIDS = ["tetrahedron", "cube", "octahedron", "icosahedron", "dodecahedron"]


def main():
    for name in PLATONIC_SOLIDS:
        _, _, face_loops = polyhedron_from_vertices(SOLIDS[name]())
        faces = [[int(v) for v in loop] for loop in face_loops]
        spec = {"name": name.capitalize(), "faces": faces}
        out_path = os.path.join(STRETCHY_NETS_DIR, f"{name}.json")
        with open(out_path, "w") as f:
            json.dump(spec, f, indent=2)
            f.write("\n")
        print(f"wrote {out_path}  ({len(faces)} faces)")


if __name__ == "__main__":
    main()
