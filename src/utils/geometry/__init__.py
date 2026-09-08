"""geometry: general-purpose 2D/3D geometry helpers with no domain-specific
algorithm content.

Modules:
  polygon_geom -- regular polygon vertices + rigid 2D edge attachment,
                  shared by both the subdivisions pipeline (polygon
                  preview layout) and the inflate_polyhedron pipeline
                  (net layout, attaching polygons edge to edge)
  polyhedron   -- Polyhedron: pure 3D solid geometry (shared, indexed
                  vertices; CCW faces; derived edges; is_closed()) --
                  currently only used by inflate_polyhedron, but kept
                  here since it's general-purpose geometry, not specific
                  to the stretchy-mesh algorithm itself
"""
from .polygon_geom import EDGE_LENGTH, regular_polygon_vertices, attach_polygon
from .polyhedron import Polyhedron, face_normal

__all__ = [
    "EDGE_LENGTH", "regular_polygon_vertices", "attach_polygon",
    "Polyhedron", "face_normal",
]
