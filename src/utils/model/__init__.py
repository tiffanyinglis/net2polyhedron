"""model: the object model tying a polyhedron net's faces, hinges, and
vertices into one shared representation, replacing the ad hoc tuples/
dicts (Net.faces, hinge dicts, verts3d dicts, a position-zipped color
list) passed between the free functions in geometry2d/geometry3d/
combinatorics/persistence.

Modules:
  face           -- Face: one polygon face, 2D and/or 3D coordinates + color
  hinge          -- Hinge: one fold hinge, identified by its child face id
  vertex         -- Vertex: one distinct 3D corner of a folded Polyhedron
  polyhedral_net -- PolyhedralNet: the flat net + hinge tree + fold angles
                     (pre-fold); PolyhedralNet.load() replaces the old
                     net_io.load_net()/load_polyhedron_net()/load_net_txt()
  polyhedron     -- Polyhedron: a realized 3D solid at some fold state t,
                     produced by PolyhedralNet.fold(t)
"""
from .face import Face
from .hinge import Hinge
from .vertex import Vertex
from .polyhedron import Polyhedron
from .polyhedral_net import PolyhedralNet

__all__ = ["Face", "Hinge", "Vertex", "Polyhedron", "PolyhedralNet"]
