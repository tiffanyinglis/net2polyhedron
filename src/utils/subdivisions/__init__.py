"""subdivisions: split a polygon into a fine triangular mesh.

Modules:
  polygon_subdivisions -- hardcoded coarse split of a single n-gon (n=3..8)
                           into triangles, refined to any resolution
  mesh_subdivide        -- reads a legacy fabric-subdivided stretchy net's
                            "coarse_faces" field (load_fabric_spec) -- see
                            that module's own docstring
"""
from .polygon_subdivisions import (
    SUBDIVISIONS, DEFAULT_RESOLUTION, MAX_LEVEL, subdivide, resolution_for,
    subdivide_at_level,
)
from .mesh_subdivide import load_fabric_spec

__all__ = [
    "SUBDIVISIONS", "DEFAULT_RESOLUTION", "MAX_LEVEL", "subdivide", "resolution_for",
    "subdivide_at_level",
    "load_fabric_spec",
]
