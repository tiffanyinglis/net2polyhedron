"""utils: the reusable geometry/subdivision/solving library behind every
app in src/apps/.

Sub-packages, grouped by concern:
  geometry            -- general-purpose 2D/3D geometry helpers with no
                          domain-specific algorithm content (regular
                          polygons, Polyhedron)
  subdivisions        -- fine-triangle-mesh subdivision (2D preview + 3D fabric)
  inflate_polyhedron  -- the stretchy (non-rigid) mesh pipeline: solving,
                          flat net layout, disk cache

Import from the specific sub-package rather than this top-level package,
e.g. `from utils.geometry import Polyhedron` -- there is no flattened
top-level re-export here on purpose, to keep each sub-package's own
__init__ the single source of truth for what it exports.
"""
