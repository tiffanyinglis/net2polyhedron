"""model: pure 3D solid geometry, shared across the rigid and stretchy
pipelines.

Modules:
  polyhedron -- Polyhedron: shared, indexed vertices; faces as CCW
                vertex-index tuples; derived edges. Knows nothing about
                nets, hinges, roots, fold progress, or color -- see its
                own docstring. Unfolding logic/objects (Hinge, NetUnfolder)
                live in utils.net_unfolder, not here.

Sample Polyhedron instances (the 5 Platonic solids, the truncated
icosahedron, and a couple of open dodecahedron-derived nets) live in
apps/common/sample_polyhedra.py, not here -- they're demo/sample content
the apps and their generator scripts consume, not reusable fold-pipeline
domain logic, so utils/ (which apps/ depends on, never the reverse) is
the wrong place for them.
"""
from .polyhedron import Polyhedron

__all__ = ["Polyhedron"]
