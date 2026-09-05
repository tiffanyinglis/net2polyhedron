"""geometry3d: stretchy-mesh solving and coordinate derivation.

Modules:
  stretchy_mesh  -- the stretchy (non-rigid) mesh solver: edge-length fit +
                     pressure-based inflation, plus the interactive relax_once
  hull_to_spec   -- derive a Polyhedron from a convex polyhedron's 3D vertices
  polyhedron     -- Polyhedron: pure 3D solid geometry (shared, indexed
                     vertices; CCW faces; derived edges; is_closed()) -- no
                     awareness of nets, hinges, fold progress, or color.
                     The rigid fold engine that used to sit alongside this
                     lived in utils.polyhedron_unfolder; it's been removed
                     now that the sibling polyhedron-unfolder project owns
                     rigid unfolding, but this general-purpose solid-geometry
                     class is still useful here on its own.

The 5 Platonic solids, the truncated icosahedron, and two open
dodecahedron-derived nets used to be hand-authored/generated into
data/input/nets/*.json; that data and its loader (persistence.polyhedron_spec)
were removed along with the rigid pipeline. Nothing in this project currently
needs a sample solid's real vertices except hull_to_spec's own tests, which
inline the coordinates they need directly.
"""
from .stretchy_mesh import load_stretchy_mesh, solve_wireframe, relax_once, mesh_to_polyhedron
from .hull_to_spec import polyhedron_from_vertices
from .polyhedron import Polyhedron

__all__ = [
    "load_stretchy_mesh", "solve_wireframe", "relax_once", "mesh_to_polyhedron",
    "polyhedron_from_vertices", "Polyhedron",
]
