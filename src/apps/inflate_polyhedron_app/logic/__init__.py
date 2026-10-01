"""Pure logic modules factored out of inflate_polyhedron_app/app.py (2026-09-30 modularization
-- same spirit as the sibling interactive_inflater_app's own `logic/` package). Every module
here exports plain functions over explicit arguments -- no Tkinter/VTK/`self` -- so `app.py`'s
`InflaterPane`/`ViewerPane` keep only widget/actor/thread wiring and call into these for the
actual computations. See apps.md's own inflate_polyhedron_app section for what each module owns.
"""
