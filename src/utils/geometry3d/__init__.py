"""geometry3d: stretchy-mesh solving and coordinate derivation.

Modules:
  stretchy_mesh  -- the stretchy (non-rigid) mesh solver: edge-length fit +
                     pressure-based inflation, plus the interactive relax_once
  hull_to_spec   -- derive a face spec from a convex polyhedron's 3D vertices

The rigid fold engine and the Polyhedron solid-geometry class live in
utils.polyhedron_unfolder now, not here -- see that package's own
docstring.

The 5 Platonic solids, the truncated icosahedron, and two open
dodecahedron-derived nets are hand-authored/generated once into
data/input/nets/*.json (see persistence.polyhedron_spec) -- there is no
sample-solid-generating code left in this project; those .json files ARE
the canonical source now, loaded directly wherever one of these solids is
needed (apps, tests) via persistence.polyhedron_spec.load_polyhedron_spec.
"""
from .stretchy_mesh import load_stretchy_mesh, solve_wireframe, relax_once
from .hull_to_spec import polyhedron_from_vertices

__all__ = [
    "load_stretchy_mesh", "solve_wireframe", "relax_once",
    "polyhedron_from_vertices",
]
