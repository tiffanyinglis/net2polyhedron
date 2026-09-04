"""subdivisions: split a polygon (or a whole net's faces) into a fine
triangular mesh.

Modules:
  polygon_subdivisions -- hardcoded coarse split of a single n-gon (n=3..8)
                           into triangles, refined to any resolution
  mesh_subdivide        -- applies polygon_subdivisions to every face of a
                            stretchy net at once, merging shared coarse
                            edges into one connected fine mesh
"""
from .polygon_subdivisions import SUBDIVISIONS, DEFAULT_RESOLUTION, subdivide, resolution_for
from .mesh_subdivide import subdivide_mesh, solve_fabric_mesh, load_fabric_spec

__all__ = [
    "SUBDIVISIONS", "DEFAULT_RESOLUTION", "subdivide", "resolution_for",
    "subdivide_mesh", "solve_fabric_mesh", "load_fabric_spec",
]
