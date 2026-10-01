"""Pure logic modules factored out of interactive_inflater_app/app.py (2026-09-30 modularization
-- same spirit as utils/inflate_polyhedron's own split of stretchy_mesh.py). Every module here
exports plain functions over explicit arguments (mesh arrays, shape/connection lists, snapshots)
-- no Tkinter, no VTK, no `self` -- so InflaterPane/BuilderPane keep only widget/actor/thread
wiring and call into these for the actual decisions/computations. See apps.md's own
interactive_inflater_app section for what each module owns.
"""
