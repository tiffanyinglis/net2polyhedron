"""common: shared helpers used by more than one app in src/apps/.

Modules:
  paths      -- shared, cross-app filesystem locations (input nets, output
                saves) -- NOT per-app caches, see each app's own folder for
                that (e.g. src/apps/polyhedron_unfolder/cache/)
  ui_theme   -- shared Tkinter/matplotlib look-and-feel constants and the
                "Compute" button's tooltip text
"""
