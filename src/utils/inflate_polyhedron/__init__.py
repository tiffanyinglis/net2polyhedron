"""inflate_polyhedron: everything specific to the stretchy (non-rigid)
mesh pipeline behind the inflate_polyhedron_app -- solving, flat net
layout, and disk caching. Nothing here is shared with the subdivisions
pipeline (see utils.geometry for what is, including Polyhedron itself,
which lives there rather than here despite being used only by this
pipeline -- see utils.geometry's own docstring for why).

Modules:
  stretchy_mesh       -- the stretchy mesh solver: edge-length fit +
                          pressure-based inflation, plus the interactive
                          relax_once
  hull_to_spec        -- derive a Polyhedron (utils.geometry.Polyhedron)
                          from a convex solid's raw 3D vertices
  stretchy_net_layout -- flat 2D layout for a stretchy (vertex-loop) mesh
  mesh_levels         -- interactive, incremental nested-level subdivision
                          for inflate_polyhedron_app's "Subdivide" button
  checksums           -- source_checksum(path), used by stretchy_cache
  stretchy_cache      -- checksummed JSON cache for stretchy nets

stretchy_cache is NOT re-exported here (import it directly, e.g.
`from utils.inflate_polyhedron.stretchy_cache import load_with_cache`):
it imports ..subdivisions.mesh_subdivide, which imports back into this
package's own stretchy_mesh module -- importing stretchy_cache eagerly at
package-init time would make that a genuine circular import whenever
utils.subdivisions happens to be the first of the two packages loaded.
"""
from .stretchy_mesh import load_stretchy_mesh, solve_wireframe, relax_once, mesh_to_polyhedron
from .hull_to_spec import polyhedron_from_vertices
from .stretchy_net_layout import build_stretchy_net_layout

__all__ = [
    "load_stretchy_mesh", "solve_wireframe", "relax_once", "mesh_to_polyhedron",
    "polyhedron_from_vertices",
    "build_stretchy_net_layout",
]
