"""common: shared helpers used by more than one app in src/apps/.

Modules:
  paths        -- shared, cross-app filesystem locations (input nets,
                   output saves) -- NOT per-app caches, see each app's
                   own folder for that (e.g. src/apps/polyhedron_unfolder/cache/)
  ui_theme     -- shared Tkinter/matplotlib look-and-feel constants and
                   the "Compute" button's tooltip text
  bounding_box -- bounding_box(vertices): a rendering helper for the
                   apps, not fold-pipeline domain logic

There used to be a sample_polyhedra.py here (Platonic-solid Polyhedron
subclasses, e.g. Cube, Dodecahedron, plus open-net variants) feeding a
handful of generate_*.py scripts that wrote data/input/nets/*.json and
data/input/stretchy_nets/*.json from them. Both are gone now: those
.json files are hand-authored/settled inputs in their own right, so
anything that needs one of these solids loads it straight from its .json
via persistence.polyhedron_spec.load_polyhedron_spec instead of
re-deriving it from raw coordinates -- see git history if the old
generation approach is ever needed again (e.g. a genuinely new solid with
no existing .json).
"""
