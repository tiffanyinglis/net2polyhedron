"""common: shared helpers used by more than one app in src/apps/.

Modules:
  paths        -- shared, cross-app filesystem locations (currently just
                   the human-authored stretchy nets directory) -- NOT
                   per-app caches, see each app's own folder for that
  ui_theme     -- shared Tkinter/matplotlib look-and-feel constants and
                   the "Compute" button's tooltip text
  bounding_box -- bounding_box(vertices): a rendering helper for the
                   apps, not fold-pipeline domain logic (currently unused
                   -- see its own module for why it's kept anyway)

There used to be a sample_polyhedra.py here (Platonic-solid Polyhedron
subclasses, e.g. Cube, Dodecahedron, plus open-net variants) feeding a
handful of generate_*.py scripts that derived vertex data and wrote it
out as .json net specs. All of that is gone now: the .json files under
data/input/ are hand-authored/settled inputs in their own right, not
regenerated artifacts -- see git history if the old generation approach
is ever needed again (e.g. a genuinely new solid with no existing .json).
"""
