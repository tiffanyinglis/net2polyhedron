"""combinatorics: graph algorithms over a polyhedron's face-adjacency
structure, independent of any 2D/3D geometry.

Modules:
  edge_map       -- face-adjacency graph -> per-face edge index map (EdgeMap)
  spanning_tree  -- split a full edge list into a spanning tree + extra edges
"""
from .edge_map import EdgeMap
from .spanning_tree import split_spanning_tree

__all__ = ["EdgeMap", "split_spanning_tree"]
