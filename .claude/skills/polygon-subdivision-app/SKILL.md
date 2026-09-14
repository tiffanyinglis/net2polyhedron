---
name: polygon-subdivision-app
description: Details on `polygon_subdivision_app` (`src/apps/polygon_subdivision_app/app.py`) and `src/utils/subdivisions/` — the 2D-only demo that splits a regular n-gon into a fine triangular mesh, unrelated to folding. Load before making non-trivial changes to this app or `utils/subdivisions/`.
---

See the `net-fold-project` skill for the untouchable-files list, directory
layout, and testing conventions shared across this whole repo — this file
covers only `polygon_subdivision_app` specifics.

## Polygon subdivision demo (`polygon_subdivision_app`, `utils/subdivisions/`)

Unrelated to folding — a standalone 2D demo splitting a regular n-gon
(triangle..8-gon) into a fine triangular mesh, e.g. as a preview of the
mesh a fabric/cloth simulation would use. Two-stage, both
hardcoded/closed-form (no runtime search):

1. `polygon_subdivisions.SUBDIVISIONS` — a hardcoded coarse split of each
   n-gon into a centroid fan (n congruent isoceles triangles, n=4..8,
   exactly equilateral at n=6). n=4 used to be a diagonal split (2
   triangles, no centroid) until that gave a cube's mesh asymmetric
   valence at some corners.
2. `resolution_for(n, base_resolution)` picks a per-n-gon resolution so
   every n-gon's fine triangles end up roughly the same size — the coarse
   triangle count doesn't scale exactly with area, so a shared literal
   resolution would leave bigger-sided polygons coarser. Matches
   fine-triangle AREA against `base_n=4` (the square) via the closed-form
   regular-polygon area formula.
3. `_subdivide_triangle` splits each coarse triangle into `resolution**2`
   small ones via a regular barycentric grid (geodesic/icosphere-style).
   `subdivide()` merges results from all coarse triangles — shared points
   land on bit-for-bit identical barycentric coordinates and merge rather
   than duplicating.

The app's layout pairs a small n-gon with a big one per column and gives
every subplot the same fixed axis range (sized to the largest n-gon), so
triangle sizes are directly comparable by eye.

It deliberately uses `FABRIC_APP_RESOLUTION`
(`mesh_subdivide.DEFAULT_RESOLUTION`, 3) as `base_resolution`, not
`subdivisions.DEFAULT_RESOLUTION` (10, a denser generic-preview default)
— this demo previews exactly what the real stretchy fabric nets (e.g.
`cube_res3.json`) actually solve.

