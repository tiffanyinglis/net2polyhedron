"""One-off generator: writes data/input/stretchy_nets/<solid>.json for each
of the 5 Platonic solids, in the vertex-loop format
utils/geometry3d/stretchy_mesh.py expects (see its module docstring) --
reusing the CCW, outward-oriented face loops that each
sample_polyhedra.py (this directory) solid already derives (via
hull_to_spec.polyhedron_from_vertices) at construction time. That's the
SAME source generate_platonic_nets.py builds the rigid
data/input/nets/*.json specs from; this is just a different (and, for
genuinely rigid/closed solids like these, strictly simpler -- no spanning
tree, no root, no fold angles to solve for) serialization of the same
combinatorial structure.

    python src/apps/common/generate_stretchy_platonic_nets.py

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
from sample_polyhedra import (
    Tetrahedron, Cube, Octahedron, Icosahedron, Dodecahedron)

PLATONIC_SOLIDS = {
    "tetrahedron": Tetrahedron,
    "cube": Cube,
    "octahedron": Octahedron,
    "icosahedron": Icosahedron,
    "dodecahedron": Dodecahedron,
}


def main():
    for name, solid_cls in PLATONIC_SOLIDS.items():
        polyhedron = solid_cls()
        faces = [[int(v) for v in face] for face in polyhedron.faces]
        spec = {"name": name.capitalize(), "faces": faces}
        out_path = os.path.join(STRETCHY_NETS_DIR, f"{name}.json")
        with open(out_path, "w") as f:
            json.dump(spec, f, indent=2)
            f.write("\n")
        print(f"wrote {out_path}  ({len(faces)} faces)")


if __name__ == "__main__":
    main()
