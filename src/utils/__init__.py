"""utils: the reusable geometry/topology/persistence library behind every
app in src/apps/.

Sub-packages, grouped by concern:
  geometry2d    -- flat 2D polygon geometry
  geometry3d    -- the rigid fold engine, stretchy-mesh solving, coordinates
  subdivisions  -- fine-triangle-mesh subdivision (2D preview + 3D fabric)
  model         -- Polyhedron: pure 3D solid geometry, no unfolding knowledge
  net_unfolder  -- NetUnfolder: derives a net (spanning tree, flat layout,
                    fold angles) from a Polyhedron; NetUnfolder.load() is
                    the public loading entry point for the rigid pipeline
  persistence   -- parse/write the on-disk .json formats, plus shared
                    checksum utilities

Import from the specific sub-package rather than this top-level package,
e.g. `from utils.geometry3d import fold` -- there is no flattened
top-level re-export here on purpose, to keep each sub-package's own
__init__ the single source of truth for what it exports.
"""
