"""geometry2d: flat 2D polygon geometry.

Modules:
  polygon_geom        -- regular polygon vertices + rigid 2D edge attachment
                          (rigid_transform_2d/apply_rigid also back
                          net_unfolder.py's flat-layout construction)
  stretchy_net_layout -- flat 2D layout for a stretchy (vertex-loop) mesh
"""
from .polygon_geom import EDGE_LENGTH, regular_polygon_vertices, attach_polygon
from .stretchy_net_layout import build_stretchy_net_layout

__all__ = [
    "EDGE_LENGTH", "regular_polygon_vertices", "attach_polygon",
    "build_stretchy_net_layout",
]
