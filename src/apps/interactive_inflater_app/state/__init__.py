"""Stateful (not pure) modules supporting interactive_inflater_app/app.py (2026-09-30), as
opposed to logic/'s pure functions and app.py's own Tkinter/VTK orchestration: `session_state.py`
(the .hippie session's own pydantic schema -- the serialized state of a session on disk),
`camera_controller.py` (the 3D panel's live camera + gesture state), `background_worker.py` (the
generic worker-thread/queue mechanism bridging a background computation's state back to the main
thread), `mesh_snapshot.py` (the Stop/revert mesh-state capture). See apps.md's own
interactive_inflater_app section for what each owns.
"""
