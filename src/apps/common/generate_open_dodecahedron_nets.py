"""One-off generator: writes data/input/nets/half_dodecahedron.json and
data/input/nets/dodecahedron_minus_one.json from the ready-built OPEN
model.Polyhedron objects in sample_polyhedra.py (this directory) --
Polyhedron specs whose faces are a subset of the full dodecahedron's,
that don't fold up into a closed solid. They exist to exercise/validate
the apps against nets that stay open at t=1, which polyhedron_unfolder's
backface culling (ui.cullable_face._CullableFace) must NOT be applied to
(checked via utils.net_unfolder.is_closed).

    python src/apps/common/generate_open_dodecahedron_nets.py
"""
import os

from paths import NETS_DIR
from sample_polyhedra import OPEN_SAMPLE_POLYHEDRA
from utils.persistence.polyhedron_spec import write_polyhedron_spec


def main():
    for name, open_cls in OPEN_SAMPLE_POLYHEDRA.items():
        polyhedron = open_cls()
        out_path = os.path.join(NETS_DIR, f"{name}.json")
        write_polyhedron_spec(out_path, polyhedron.vertices, polyhedron.faces,
                               name=polyhedron.name)
        print(f"wrote {out_path}  ({len(polyhedron.faces)} faces kept, {len(polyhedron.vertices)} vertices)")


if __name__ == "__main__":
    main()
