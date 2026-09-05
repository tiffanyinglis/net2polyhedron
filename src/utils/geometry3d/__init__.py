"""geometry3d: 3D fold engine, stretchy-mesh solving, coordinates, and the
Polyhedron solid-geometry class.

Modules:
  polyhedron     -- Polyhedron: shared, indexed vertices; faces as CCW
                     vertex-index tuples; derived edges. Knows nothing
                     about nets, hinges, roots, fold progress, or color
                     -- see its own docstring. Unfolding logic/objects
                     (Hinge, NetUnfolder) live in utils.polyhedron_unfolder,
                     not here. (Used to live in its own utils/model/
                     package -- folded in here since geometry3d was its
                     only real dependency and model/ had nothing else in
                     it.)
  net_fold_core  -- the rigid fold engine (Net, fold(), fold_transforms(),
                     flatten_net(), cluster_faces_into_mesh(),
                     distinct_vertices(), face_normal(), is_closed_solid())
  stretchy_mesh  -- the stretchy (non-rigid) mesh solver: edge-length fit +
                     pressure-based inflation, plus the interactive relax_once
  hull_to_spec   -- derive a face spec from a convex polyhedron's 3D vertices

The 5 Platonic solids, the truncated icosahedron, and two open
dodecahedron-derived nets are hand-authored/generated once into
data/input/nets/*.json (see persistence.polyhedron_spec) -- there is no
sample-solid-generating code left in this project; those .json files ARE
the canonical source now, loaded directly wherever one of these solids is
needed (apps, tests) via persistence.polyhedron_spec.load_polyhedron_spec.
"""
from .polyhedron import Polyhedron
from .net_fold_core import (
    fold, fold_transforms, flatten_net, distinct_vertices, face_normal, is_closed_solid)
from .stretchy_mesh import load_stretchy_mesh, solve_wireframe, relax_once
from .hull_to_spec import polyhedron_from_vertices

__all__ = [
    "Polyhedron",
    "fold", "fold_transforms", "flatten_net", "distinct_vertices", "face_normal", "is_closed_solid",
    "load_stretchy_mesh", "solve_wireframe", "relax_once",
    "polyhedron_from_vertices",
]
