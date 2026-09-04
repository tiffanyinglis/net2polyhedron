"""geometry3d: 3D fold solving, stretchy-mesh solving, and coordinates.

Modules:
  net_fold_core  -- the rigid fold engine (Net, fold(), fold_transforms(),
                     cluster_faces_into_mesh(), distinct_vertices(),
                     face_normal(), is_closed_solid())
  fold_solver    -- solve rigid hinge fold angles from closure constraints
  stretchy_mesh  -- the stretchy (non-rigid) mesh solver: edge-length fit +
                     pressure-based inflation, plus the interactive relax_once
  solid_coords   -- canonical vertex coordinates for the Platonic solids
  hull_to_spec   -- derive a face spec from a convex polyhedron's 3D vertices
"""
from .net_fold_core import (
    fold, fold_transforms, distinct_vertices, face_normal, is_closed_solid)
from .fold_solver import solve_fold_angles
from .stretchy_mesh import load_stretchy_mesh, solve_wireframe, relax_once
from .solid_coords import SOLIDS
from .hull_to_spec import polyhedron_from_vertices

__all__ = [
    "fold", "fold_transforms", "distinct_vertices", "face_normal", "is_closed_solid",
    "solve_fold_angles",
    "load_stretchy_mesh", "solve_wireframe", "relax_once",
    "SOLIDS", "polyhedron_from_vertices",
]
