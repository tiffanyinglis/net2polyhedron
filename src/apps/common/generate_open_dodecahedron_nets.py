"""One-off generator: writes data/input/nets/half_dodecahedron.json and
data/input/nets/dodecahedron_minus_one.json -- OPEN nets (a Polyhedron spec
whose faces are a subset of the full dodecahedron's) that don't fold up
into a closed solid. They exist to exercise/validate the apps against nets
that stay open at t=1, which polyhedron_unfolder's backface culling
(ui.cullable_face._CullableFace) must NOT be applied to (checked via
model.Polyhedron.is_closed).

    python src/apps/common/generate_open_dodecahedron_nets.py
"""
import os

from paths import NETS_DIR
from utils.model.platonic_polyhedra import Dodecahedron
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from utils.persistence.polyhedron_spec import write_polyhedron_spec


def _write_face_subset(vertices, face_loops, keep_faces, name):
    """Write a net spec containing only `keep_faces` (indices into
    face_loops) of the full dodecahedron -- remapped to reference only the
    vertices those faces actually use (an unreferenced vertex would still
    count toward Polyhedron.bounding_box(), silently enlarging it around a
    point nothing renders). NetUnfolder derives face adjacency/spanning
    tree/fold angles from whichever faces are present -- no separate
    omit/hidden-edge bookkeeping needed."""
    kept_loops = [face_loops[f] for f in sorted(keep_faces)]
    used = sorted({v for loop in kept_loops for v in loop})
    remap = {old: new for new, old in enumerate(used)}
    out_vertices = [vertices[v] for v in used]
    out_faces = [[remap[v] for v in loop] for loop in kept_loops]

    out_path = os.path.join(NETS_DIR, f"{name}.json")
    write_polyhedron_spec(out_path, out_vertices, out_faces,
                           name=name.replace("_", " ").title())
    print(f"wrote {out_path}  ({len(out_faces)} faces kept, {len(out_vertices)} vertices)")


def main():
    vertices = Dodecahedron.raw_vertices()
    _, edges, face_loops = polyhedron_from_vertices(vertices)
    adj = {f: set() for f in range(len(face_loops))}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)

    # half_dodecahedron: one face plus its 5 neighbors -- a symmetric
    # 6-face "cap" (a pentagon surrounded by its ring of neighbors),
    # open all the way around where the other 6 faces would be, like a
    # shallow bowl.
    center = 0
    half_faces = {center} | adj[center]
    _write_face_subset(vertices, face_loops, half_faces, "half_dodecahedron")

    # dodecahedron_minus_one: every face but one -- an almost-closed
    # solid with a single pentagon-shaped hole where that face was.
    removed = 0
    all_but_one = set(range(len(face_loops))) - {removed}
    _write_face_subset(vertices, face_loops, all_but_one, "dodecahedron_minus_one")


if __name__ == "__main__":
    main()
