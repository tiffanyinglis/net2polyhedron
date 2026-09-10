"""inflate_polyhedron: everything specific to the stretchy (non-rigid)
mesh pipeline behind the inflate_polyhedron_app -- solving and flat net
layout. Nothing here is shared with the subdivisions pipeline (see
utils.geometry for what is, including Polyhedron itself, which lives
there rather than here despite being used only by this pipeline -- see
utils.geometry's own docstring for why).

Modules:
  stretchy_mesh       -- the stretchy mesh solver: random-start-plus-
                          spring-relax initial configuration
                          (relax_initial_configuration), then interactive
                          pressure-based inflation (relax_once)
  hull_to_spec        -- derive a Polyhedron (utils.geometry.Polyhedron)
                          from a convex solid's raw 3D vertices
  stretchy_net_layout -- flat 2D layout for a stretchy (vertex-loop) mesh
  mesh_levels         -- interactive, incremental nested-level subdivision
                          for inflate_polyhedron_app's "Subdivide" button
"""
from .stretchy_mesh import (
    load_stretchy_mesh, relax_initial_configuration, random_initial_positions, relax_once,
    mesh_to_polyhedron,
)
from .hull_to_spec import polyhedron_from_vertices
from .stretchy_net_layout import build_stretchy_net_layout

__all__ = [
    "load_stretchy_mesh", "relax_initial_configuration", "random_initial_positions", "relax_once",
    "mesh_to_polyhedron",
    "polyhedron_from_vertices",
    "build_stretchy_net_layout",
]
