"""utils: the reusable geometry/topology/persistence library behind every
app in src/apps/.

Sub-packages, grouped by concern:
  geometry2d    -- flat 2D polygon geometry and net layout
  geometry3d    -- 3D fold solving, stretchy-mesh solving, coordinates
  subdivisions  -- fine-triangle-mesh subdivision (2D preview + 3D fabric)
  combinatorics -- face-adjacency graph algorithms (edge maps, spanning trees)
  persistence   -- parse/load/write/cache the on-disk .json/.fold formats

Import from the specific sub-package rather than this top-level package,
e.g. `from utils.geometry3d import fold` -- there is no flattened
top-level re-export here on purpose, to keep each sub-package's own
__init__ the single source of truth for what it exports.
"""
