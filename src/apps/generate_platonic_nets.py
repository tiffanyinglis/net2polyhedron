"""One-off generator: writes data/input/nets/<solid>.json for each of the 5
Platonic solids, deriving face degrees and adjacency straight from
canonical 3D vertex coordinates.

    python src/apps/generate_platonic_nets.py
"""
import os

from paths import NETS_DIR
from utils.geometry3d.solid_coords import SOLIDS
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from utils.combinatorics.spanning_tree import split_spanning_tree
from utils.persistence.polyhedron_spec import write_polyhedron_spec


def main():
    for name, coord_fn in SOLIDS.items():
        degrees, edges, _ = polyhedron_from_vertices(coord_fn())
        net_edges, extra_edges = split_spanning_tree(len(degrees), edges, root=0)
        out_path = os.path.join(NETS_DIR, f"{name}.json")
        write_polyhedron_spec(out_path, degrees, net_edges, extra_edges,
                               root=0, name=name.capitalize())
        print(f"wrote {out_path}  ({len(degrees)} faces, "
              f"{len(net_edges)} net edges, {len(extra_edges)} extra edges)")


if __name__ == "__main__":
    main()
