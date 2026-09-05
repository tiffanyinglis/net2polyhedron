"""geometry3d: 3D fold engine, stretchy-mesh solving, and coordinates.

Modules:
  net_fold_core  -- the rigid fold engine (Net, fold(), fold_transforms(),
                     flatten_net(), cluster_faces_into_mesh(),
                     distinct_vertices(), face_normal(), is_closed_solid())
  stretchy_mesh  -- the stretchy (non-rigid) mesh solver: edge-length fit +
                     pressure-based inflation, plus the interactive relax_once
  hull_to_spec   -- derive a face spec from a convex polyhedron's 3D vertices

Canonical sample-solid coordinates now live as model.Polyhedron
subclasses in apps/common/sample_polyhedra.py (e.g. Cube, Dodecahedron)
-- demo/sample content the apps consume, not reusable geometry3d logic --
not here. See that module's docstring.
"""
from .net_fold_core import (
    fold, fold_transforms, flatten_net, distinct_vertices, face_normal, is_closed_solid)
from .stretchy_mesh import load_stretchy_mesh, solve_wireframe, relax_once
from .hull_to_spec import polyhedron_from_vertices

__all__ = [
    "fold", "fold_transforms", "flatten_net", "distinct_vertices", "face_normal", "is_closed_solid",
    "load_stretchy_mesh", "solve_wireframe", "relax_once",
    "polyhedron_from_vertices",
]
