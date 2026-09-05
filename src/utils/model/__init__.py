"""model: pure 3D solid geometry, shared across the rigid and stretchy
pipelines.

Modules:
  polyhedron         -- Polyhedron: shared, indexed vertices; faces as CCW
                        vertex-index tuples; derived edges. Knows nothing
                        about nets, hinges, roots, fold progress, or color
                        -- see its own docstring. Unfolding logic/objects
                        (Hinge, NetUnfolder) live in utils.net_unfolder,
                        not here.
  platonic_polyhedra -- Polyhedron subclasses for the 5 Platonic solids
                        plus the truncated icosahedron (Tetrahedron, Cube,
                        Octahedron, Icosahedron, Dodecahedron,
                        TruncatedIcosahedron), each instantiable directly
                        (e.g. `Cube()`) with vertices/faces already
                        derived via hull_to_spec -- see its own docstring.
"""
from .polyhedron import Polyhedron
from .platonic_polyhedra import (
    PlatonicPolyhedron, Tetrahedron, Cube, Octahedron, Icosahedron,
    Dodecahedron, TruncatedIcosahedron, PLATONIC_SOLIDS)

__all__ = [
    "Polyhedron",
    "PlatonicPolyhedron", "Tetrahedron", "Cube", "Octahedron", "Icosahedron",
    "Dodecahedron", "TruncatedIcosahedron", "PLATONIC_SOLIDS",
]
