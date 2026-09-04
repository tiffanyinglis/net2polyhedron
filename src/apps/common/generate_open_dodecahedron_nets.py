"""One-off generator: writes data/input/nets/half_dodecahedron.json and
data/input/nets/dodecahedron_minus_one.json -- OPEN nets (see
polyhedron_spec.py's module docstring) that don't fold up into a closed
solid, derived by marking a face subset of the full dodecahedron's
combinatorics as omitted. They exist to exercise/validate the apps against
nets that stay open at t=1, which polyhedron_unfolder's backface culling
(ui.cullable_face._CullableFace) must NOT be applied to (see
utils.geometry3d.is_closed_solid, which it checks first).

    python src/apps/common/generate_open_dodecahedron_nets.py
"""
import os

from paths import NETS_DIR
from utils.geometry3d.solid_coords import dodecahedron
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from utils.combinatorics.spanning_tree import split_spanning_tree
from utils.persistence.polyhedron_spec import write_polyhedron_spec


def _write_open_subset(degrees, edges, keep_faces, root, name):
    """Write a net spec for just `keep_faces` of the full dodecahedron
    (global face ids, kept as-is -- NOT remapped to 0..k-1), marking
    every other face "omit". Splits `edges` into net/extra (a spanning
    tree over keep_faces, using only edges between two kept faces) and
    hidden (everything else: any edge touching an omitted face) --
    see polyhedron_spec.py for why hidden edges still have to be
    listed."""
    keep_faces = set(keep_faces)
    omitted = set(range(len(degrees))) - keep_faces
    kept_edges = [(a, b) for a, b in edges if a in keep_faces and b in keep_faces]
    hidden_edges = [(a, b) for a, b in edges if a in omitted or b in omitted]

    # split_spanning_tree needs a dense 0..k-1 node range, so remap just
    # for this call, then map its result straight back to the original
    # (global, gappy) face ids that the rest of the spec uses.
    local_of = {g: i for i, g in enumerate(sorted(keep_faces))}
    global_of = {i: g for g, i in local_of.items()}
    local_edges = [(local_of[a], local_of[b]) for a, b in kept_edges]
    net_local, extra_local = split_spanning_tree(
        len(keep_faces), local_edges, root=local_of[root])
    net_edges = [(global_of[a], global_of[b]) for a, b in net_local]
    extra_edges = [(global_of[a], global_of[b]) for a, b in extra_local]

    out_path = os.path.join(NETS_DIR, f"{name}.json")
    write_polyhedron_spec(out_path, degrees, net_edges, extra_edges, root=root,
                           name=name.replace("_", " ").title(),
                           omitted=omitted, hidden_edges=hidden_edges)
    print(f"wrote {out_path}  ({len(keep_faces)} faces kept, {len(omitted)} omitted, "
          f"{len(net_edges)} net edges, {len(extra_edges)} extra edges, "
          f"{len(hidden_edges)} hidden edges)")


def main():
    degrees, edges, _ = polyhedron_from_vertices(dodecahedron())
    adj = {f: set() for f in range(len(degrees))}
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)

    # half_dodecahedron: one face plus its 5 neighbors -- a symmetric
    # 6-face "cap" (a pentagon surrounded by its ring of neighbors),
    # open all the way around where the other 6 faces would be, like a
    # shallow bowl.
    center = 0
    half_faces = {center} | adj[center]
    _write_open_subset(degrees, edges, half_faces, center, "half_dodecahedron")

    # dodecahedron_minus_one: every face but one -- an almost-closed
    # solid with a single pentagon-shaped hole where that face was.
    removed = 0
    all_but_one = set(range(len(degrees))) - {removed}
    new_root = min(all_but_one)
    _write_open_subset(degrees, edges, all_but_one, new_root, "dodecahedron_minus_one")


if __name__ == "__main__":
    main()
