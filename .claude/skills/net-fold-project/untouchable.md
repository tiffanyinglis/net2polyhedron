# Untouchable files

Every file that existed before `interactive_builder_app` work started is untouchable — user
considers it DONE. Don't edit (even "just cleanup") w/o asking first, naming file + change.

```
src/utils/geometry/{polygon_geom,polyhedron,__init__}.py
src/utils/inflate_polyhedron/{__init__,hull_to_spec,mesh_levels,stretchy_mesh,stretchy_net_layout}.py
src/utils/subdivisions/{__init__,polygon_subdivisions,mesh_subdivide}.py
src/utils/__init__.py
src/apps/ui/{tooltip,cullable_face,__init__}.py
src/apps/common/{bounding_box,ui_theme,paths,__init__}.py
src/apps/polygon_subdivision_app/app.py
src/apps/inflate_polyhedron_app/app.py
data/input/stretchy_nets/*.json
docs/{README,algorithm}.md
.gitignore, requirements.txt, pytest.ini, .claude/settings.local.json, this skill dir
tests/run_tests.py + every unit/ test file that already existed
```

Rule: task needs touching one of these for a NEW reason -> stop, ask, name file + change. Don't
work around it silently. Once user explicitly grants a change (by name or unambiguous
description), that's a standing exception for that specific thing, not a general loosening.

Exceptions granted so far (don't re-ask for these, but don't extend past what's listed):
- `stretchy_mesh.py` + its test: open-net support (boundary edges ok); `gtol` param on
  `estimate_pressure_for_target_stretch`; hardening spring + tuning; adaptive-step-term removal,
  stall-check removal, chunking removal, displacement-based convergence check — all explicit,
  all currently-active experiments (see `physics.md`).
- `inflate_polyhedron_app/app.py`: repeatedly, each time one named feature — net-layout display
  from `interactive_builder_app` saves, setup-row horizontal layout, "(stalled)" label (since
  removed — see physics.md), debug-only Validate Mesh/Show normals, Auto retry-loop removal,
  tolerance default changes, stop-during-calibration fix. See `apps.md`.

`bounding_box.py`, `cullable_face.py`: unused (written for now-deleted rigid pipeline). Stay on
the list anyway — don't delete.

Rigid-unfolding pipeline (`polyhedron_unfolder` app+utils, `persistence/`, `data/input/nets/`) is
DELETED from this repo entirely — lives in sibling `polyhedron-unfolder` project. Don't
resurrect here; don't treat references to it in git history as still-live code.

`polygon_subdivision_app` / `utils/subdivisions/` — separate, finished, unrelated 2D demo. Not
part of the stretchy pipeline.
