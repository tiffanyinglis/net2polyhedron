"""net_fold_utils: build and fold polyhedral nets.

Reusable library modules:
  polygon_geom     -- regular polygon vertices + rigid 2D attachment
  combinatorics    -- face-adjacency graph -> per-face edge index map
  net_layout       -- flat 2D net layout from a spanning tree of faces
  fold_solver      -- solve hinge fold angles from closure constraints
  net_fold_core    -- the fold engine (Net, fold(), distinct_vertices())
  polyhedron_spec  -- parse/write the FACES/NET/EXTRA .poly format
  net_io           -- load_net(): dispatches .poly / legacy .txt loaders
  fold_cache       -- checksummed .fold cache so a solve only runs once
  spanning_tree    -- split a full edge list into tree + extra edges
  hull_to_spec     -- derive a spec from a convex polyhedron's 3D vertices
  solid_coords     -- canonical vertex coordinates for the Platonic solids

The most common entry points are re-exported here for convenience.
"""
from .net_io import load_net, load_polyhedron_net, load_net_txt
from .net_fold_core import fold, distinct_vertices
from .fold_cache import load_with_cache

__all__ = [
    "load_net", "load_polyhedron_net", "load_net_txt", "load_with_cache",
    "fold", "distinct_vertices",
]
