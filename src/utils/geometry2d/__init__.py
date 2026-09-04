"""geometry2d: flat 2D polygon geometry and net layout.

Modules:
  polygon_geom        -- regular polygon vertices + rigid 2D edge attachment
  net_layout          -- flat 2D net layout from a spanning tree of faces
  stretchy_net_layout -- flat 2D layout for a stretchy (vertex-loop) mesh
"""
from .polygon_geom import EDGE_LENGTH, regular_polygon_vertices, attach_polygon
from .net_layout import build_net_layout
from .stretchy_net_layout import build_stretchy_net_layout

__all__ = [
    "EDGE_LENGTH", "regular_polygon_vertices", "attach_polygon",
    "build_net_layout", "build_stretchy_net_layout",
]
