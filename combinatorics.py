"""Derive a polyhedron's full combinatorial edge structure from a plain
face-adjacency graph: which polygon-edge of each face glues to which
polygon-edge of its neighbor.

Given only "face A touches face B" pairs, a convex polyhedron's graph is
3-connected and planar, so by Whitney's uniqueness theorem its planar
embedding -- and therefore the cyclic order of edges around every face -- is
determined up to a single global mirror choice. That cyclic order is exactly
the order in which a face's polygon edges meet its neighbors, so it tells us
which edge-index of one face glues to which edge-index of the other, with no
need for the input to spell that out.
"""
import networkx as nx


class EdgeMap:
    """face -> ordered list of neighbors, index = that face's polygon edge
    index (edge i runs from polygon vertex i to vertex i+1)."""

    def __init__(self, degrees, edges):
        n = len(degrees)
        edge_set = {frozenset(e) for e in edges}
        if len(edge_set) != len(edges):
            raise ValueError("duplicate edge in the edge list")
        if any(len(e) != 2 for e in edge_set):
            raise ValueError("an edge must join two distinct faces")

        graph = nx.Graph()
        graph.add_nodes_from(range(n))
        graph.add_edges_from(edges)

        for f in range(n):
            deg = graph.degree(f)
            if deg != degrees[f]:
                raise ValueError(
                    f"face {f} is a {degrees[f]}-gon but appears in {deg} "
                    f"edge(s); every polygon edge must be glued to exactly "
                    f"one neighbor (check NET + EXTRA edges)")

        is_planar, embedding = nx.check_planarity(graph)
        if not is_planar:
            raise ValueError("face-adjacency graph is not planar; "
                              "this is not a valid polyhedron")

        self.degrees = degrees
        self.neighbor_order = embedding.get_data()  # face -> [neighbors...]
        self._edge_idx = {(f, nb): i
                           for f, nbrs in self.neighbor_order.items()
                           for i, nb in enumerate(nbrs)}

    def edge_index(self, face, neighbor):
        """Polygon edge index on `face` that borders `neighbor`."""
        return self._edge_idx[(face, neighbor)]

    def neighbor_at(self, face, edge_idx):
        """The face glued to polygon edge `edge_idx` of `face`."""
        return self.neighbor_order[face][edge_idx]
