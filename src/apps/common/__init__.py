"""common: shared helpers used by more than one app in src/apps/.

Modules:
  paths            -- shared, cross-app filesystem locations (input nets,
                       output saves) -- NOT per-app caches, see each app's
                       own folder for that (e.g. src/apps/polyhedron_unfolder/cache/)
  ui_theme         -- shared Tkinter/matplotlib look-and-feel constants and
                       the "Compute" button's tooltip text
  bounding_box     -- bounding_box(vertices): a rendering helper for the
                       apps, not fold-pipeline domain logic
  sample_polyhedra -- ready-to-use model.Polyhedron sample solids
                       (Tetrahedron, Cube, ..., TruncatedIcosahedron) and
                       open nets (HalfDodecahedron, DodecahedronMinusOne),
                       each instantiable directly (e.g. `Cube()`) -- demo
                       content the generate_*.py scripts and tests consume
"""
