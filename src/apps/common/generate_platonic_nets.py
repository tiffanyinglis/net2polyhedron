"""One-off generator: writes data/input/nets/<solid>.json for each of the 5
Platonic solids (plus the truncated icosahedron), from the ready-built
model.Polyhedron objects in utils/model/platonic_polyhedra.py.
NetUnfolder (src/utils/net_unfolder/) derives its own spanning tree/flat
layout/fold angles at load time, so nothing about the net itself needs
deriving here -- this just writes out each polyhedron's own geometry.

    python src/apps/common/generate_platonic_nets.py
"""
import os

from paths import NETS_DIR
from utils.model.platonic_polyhedra import PLATONIC_SOLIDS
from utils.persistence.polyhedron_spec import write_polyhedron_spec


def main():
    for name, solid_cls in PLATONIC_SOLIDS.items():
        polyhedron = solid_cls()
        out_path = os.path.join(NETS_DIR, f"{name}.json")
        write_polyhedron_spec(out_path, polyhedron.vertices, polyhedron.faces,
                               name=name.capitalize())
        print(f"wrote {out_path}  ({len(polyhedron.vertices)} vertices, {len(polyhedron.faces)} faces)")


if __name__ == "__main__":
    main()
