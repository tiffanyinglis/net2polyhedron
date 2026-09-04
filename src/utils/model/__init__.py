"""model: the object model for the rigid pipeline.

Modules:
  face           -- Face: one polygon face of the flat, pre-fold 2D net
                     layout (2D coordinates + color); no 3D knowledge
  hinge          -- Hinge: one fold hinge, identified by its child face id
  polyhedral_net -- PolyhedralNet: the flat net + hinge tree + fold angles
                     (pre-fold); PolyhedralNet.load() is the public loading
                     entry point; PolyhedralNet.fold(t) produces a Polyhedron
  polyhedron     -- Polyhedron: pure 3D solid geometry -- shared, indexed
                     vertices, CCW vertex-index faces, derived edges. Knows
                     nothing about nets, hinges, roots, fold progress, or
                     color -- see its own docstring.
"""
from .face import Face
from .hinge import Hinge
from .polyhedron import Polyhedron
from .polyhedral_net import PolyhedralNet

__all__ = ["Face", "Hinge", "Polyhedron", "PolyhedralNet"]
