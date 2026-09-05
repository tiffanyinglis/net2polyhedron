"""model: pure 3D solid geometry, shared across the rigid and stretchy
pipelines.

Modules:
  polyhedron -- Polyhedron: shared, indexed vertices; faces as CCW
                vertex-index tuples; derived edges. Knows nothing about
                nets, hinges, roots, fold progress, or color -- see its
                own docstring. Unfolding logic/objects (Hinge, NetUnfolder)
                live in utils.net_unfolder, not here.
"""
from .polyhedron import Polyhedron

__all__ = ["Polyhedron"]
