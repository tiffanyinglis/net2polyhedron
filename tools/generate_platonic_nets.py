"""One-off generator: writes nets/<solid>.poly for each of the 5 Platonic
solids, deriving face degrees and adjacency straight from canonical 3D
vertex coordinates.

    python tools/generate_platonic_nets.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from netfold.solid_coords import SOLIDS
from netfold.hull_to_spec import polyhedron_from_vertices
from netfold.spanning_tree import split_spanning_tree
from netfold.polyhedron_spec import write_polyhedron_spec

NETS_DIR = os.path.join(os.path.dirname(__file__), "..", "nets")


def main():
    for name, coord_fn in SOLIDS.items():
        degrees, edges, _ = polyhedron_from_vertices(coord_fn())
        net_edges, extra_edges = split_spanning_tree(len(degrees), edges, root=0)
        out_path = os.path.join(NETS_DIR, f"{name}.poly")
        write_polyhedron_spec(out_path, degrees, net_edges, extra_edges,
                               root=0, name=name.capitalize())
        print(f"wrote {out_path}  ({len(degrees)} faces, "
              f"{len(net_edges)} net edges, {len(extra_edges)} extra edges)")


if __name__ == "__main__":
    main()
