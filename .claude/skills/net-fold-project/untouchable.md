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
data/input/stretchy_nets/*.json, *.poly
docs/{README,algorithm}.md
.gitignore, requirements.txt, pytest.ini, .claude/settings.local.json, this skill dir
tests/run_tests.py + every unit/ test file that already existed
```

Rule: task needs touching one of these for a NEW reason -> stop, ask, name file + change. Don't
work around it silently. Once user explicitly grants a change (by name or unambiguous
description), that's a standing exception for that specific thing, not a general loosening.

Exceptions granted so far (don't re-ask for these, but don't extend past what's listed):
- `stretchy_mesh.py` + its test: open-net support (boundary edges ok); `gtol` param on
  `estimate_pressure_for_target_stretch`; hardening spring + tuning; adaptive-step-term removal
  (now PERMANENT, re-declined 2026-09-16 — see physics.md), stall-check removal, chunking
  removal, displacement-based convergence check — all explicit. `relax_once`'s
  `step_max_multiplier` param + `PRESSURE_CALC_STEP_MULTIPLIER`/diverged-trial handling in
  `estimate_pressure_for_target_stretch` (2026-09-16, explicit), tried at 2x/3x/4x and various
  coarse-to-fine schedules, then REMOVED entirely, also explicit (2026-09-16 — "just 1x, no
  multipliers"; `relax_once` no longer has this param at all) — see physics.md's Pressure
  calibration section for the history. `estimate_pressure_for_target_stretch`'s new
  `initial_pressure_guess` param (2026-09-16, explicit — history-based guess, see physics.md) —
  this one's still active/current, not removed.
- `inflate_polyhedron_app/app.py`: repeatedly, each time one named feature — net-layout display
  from `interactive_builder_app` saves, setup-row horizontal layout, "(stalled)" label (since
  removed — see physics.md), debug-only Validate Mesh/Show normals, Auto retry-loop removal,
  tolerance default changes, stop-during-calibration fix, debug-only "Pressure calc step ×"
  spinner (2026-09-16, since REMOVED, also explicit), Convergence History's debug-only "Precomp
  time"/"Sim time" columns (2026-09-16, explicit, still active), Net panel drawing
  `interactive_builder_app`'s saved bezier connection curves (self.target_connections, no
  handles — read-only panel; 2026-09-16, explicit, still active), Net panel's subdivision overlay
  removed (2026-09-16, explicit — "too busy"), connection curve color changed to white
  (2026-09-16, explicit), right-click-drag pan on Net panel + all "Level N" panels with
  middle-click reset (2026-09-16, explicit, still active), `NET_ZOOM_MIN` lowered from 0.2 to 0.1
  to match every "Level N" panel's own 10%..1000% range (2026-09-16, explicit), `refresh_net_list`
  reading `*.poly` alongside `*.json` (2026-09-16, explicit, still active). Polygon Fold support
  (2026-09-18, explicit — the feature's own description named this file's coloring behavior
  directly): reads a new `"source_polygon_id"` field and colors/groups same-source-polygon fine
  triangles as one unit (`_face_colors_by_group`, `_draw_level_panel`'s per-group `add_mesh`
  grouping, `_draw_target_faces`'s `color_by_group` lookup); `_layout_from_net_layout` and both
  `on_select_net`/`on_load_session_clicked` net_layout-length guards updated for
  `interactive_builder_app`'s new shape-id-keyed `net_layout`/`builder_connections` format (see
  `apps.md`'s own `interactive_builder_app` section) — still active. Each "Level N" panel's own
  `add_mesh` call now also sets `backface_params=dict(color=_darken_color(face_color))` (new
  `_darken_color`/`INSIDE_FACE_DARKEN_FACTOR=0.65`, alongside `_midpoint_color`) so a face's
  INSIDE renders darker than its outside (2026-09-19, explicit, named this app by its
  "polyhedron_inflater" nickname — still active). See `apps.md`.

`bounding_box.py`, `cullable_face.py`: unused (written for now-deleted rigid pipeline). Stay on
the list anyway — don't delete.

`docs/README.md`: `.poly` extension mentions added alongside every existing `.json` one (2026-09-16,
explicit — "update docs too", asked directly after the `.poly`-extension change itself).
`docs/algorithm.md` had nothing to update (no `.json`/net-file-extension mentions in it at all).

`data/input/stretchy_nets/*.json`: all 11 shipped nets renamed `.json` -> `.poly` via `git mv`
(2026-09-16, explicit — "change the json files in stretchy_nets/ to .poly files") — content
byte-for-byte unchanged, extension only. Every test file that hardcoded one of these 11 exact
paths (`tests/unit/inflate_polyhedron/test_stretchy_mesh.py`, `test_stretchy_net_layout.py`,
`tests/unit/interactive_builder_app/test_app.py`'s own `SHIPPED_NET_PATHS` glob) updated to match
-- a DIRECT, necessary consequence of the rename (the suite would otherwise fail to find the
files / silently stop testing any shipped net at all via an empty glob), not separate scope
creep.

`tests/unit/inflate_polyhedron/test_stretchy_mesh.py`: `test_load_pentagons_and_square_example`/
`test_load_three_squares_example` DELETED entirely (2026-09-16, explicit — "i don't [care] about
that. delete those tests", re: their own pre-existing, unrelated-to-anything-this-session
title-case-vs-underscored `"name"` field mismatch). `THREE_SQUARES` (now-unused after the delete)
removed too; `PENTAGONS_AND_SQUARE` kept -- still used by `test_mesh_edges_deduplicates_and_sorts`.

Rigid-unfolding pipeline (`polyhedron_unfolder` app+utils, `persistence/`, `data/input/nets/`) is
DELETED from this repo entirely — lives in sibling `polyhedron-unfolder` project. Don't
resurrect here; don't treat references to it in git history as still-live code.

`polygon_subdivision_app` / `utils/subdivisions/` — separate, finished, unrelated 2D demo. Not
part of the stretchy pipeline.
