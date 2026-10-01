# Untouchable files

`paper/` (the Bridges 2027 LaTeX paper, incl. `paper.tex`, `bridges.sty`, `figures/`) — user
writes/edits this by hand. Never edit any file under `paper/` without explicit permission naming
the file + change first, even for something that looks like a typo fix. Compiling it (running
pdflatex, cleaning up aux/log/out files) is fine without asking.

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
- `stretchy_mesh.py`, `mesh_levels.py`, `inflate_polyhedron_app/app.py`, `__init__.py`, + the
  stretchy_mesh test: MODULARIZATION (2026-09-30, explicit — "modularize things more, split out
  functionalities", 5 named pieces). `stretchy_mesh.py` split into `pre_inflation_relaxer.py`
  (`relax_initial_configuration`), `multi_trial_inflater.py`
  (`estimate_pressure_for_target_stretch`), `convergence_checker.py` (periodic stopping check),
  `mesh_stretch_checker.py` (positions -> stretch %), and a new `self_join_triangulator.py` (see
  physics.md's own header note) — `__init__.py` and the test file's import lines updated as a
  direct, necessary consequence, same as prior renames. `inflate_polyhedron_app/app.py`'s
  `on_select_net` also gained a new self-join check/split on load (explicit, scoped to THIS app
  only — user said "do it for inflate_polyhedron_app for now" — not `interactive_inflater_app`,
  whose own import lines were updated only mechanically to keep working, no new behavior there).
- `multi_trial_inflater.py` (post-split): new `InsideOutChecker` (2026-09-30, explicit — user
  diagnosed the tetrahedron weird-inflation bug, a burst-of-inflation-at-Level-0 experiment to
  test their own theory showed no effect, then user asked to pursue "the volume-sign-flip
  detection idea" instead, explicitly naming the class `InsideOutChecker` — see physics.md).
  `estimate_pressure_for_target_stretch`'s bracket loop now excludes an inside-out trial from
  best-candidacy and always escalates pressure in response to one, regardless of its own
  rms_stretch reading.
- `inflate_polyhedron_app/app.py`: View > Inflater/Viewer (2026-09-30, explicit — "Create a
  hippo viewer app... basically it reads all the hippo files in output/ and shows it in a sort
  of photo viewer...", built first as its own standalone `hippo_viewer_app`, then explicitly
  folded in: "instead of a whole separate app, make it just a view in the polyhedron_inflater
  app. So add a View menu with two item: Inflater and Viewer"). Wrapped every existing
  top-level widget in a new `self._inflater_frame` (packed/hidden by the View menu, no other
  change to any of it); added `self._viewer_frame` and its own `_viewer_*`-prefixed
  methods/state — see apps.md's own section for the full behavior. Also added this app's first
  `WM_DELETE_WINDOW` handler (`_on_quit_request`), scoped to the Viewer pane's own dirty files
  only — Inflater mode still has no save-prompt-on-close of its own, unchanged.
  Follow-up, same session, explicit: square window for Viewer mode (`VIEWER_WINDOW_GEOMETRY`,
  captures/restores Inflater's own geometry around the switch), a visible outline on the
  drawing area, Prev/Next replaced by filled-triangle Canvas buttons (`_make_viewer_nav_
  triangle`) flanking the panel, the Save button removed entirely, and the save-prompt
  (`_viewer_confirm_discard_unsaved`) now also fires when switching back to View > Inflater,
  not just on quit — cancelling that prompt reverts `view_mode_var` to "viewer".
  Second follow-up, same session, explicit: Level buttons/single-level switching removed
  entirely — all 4 levels now show at once in a 2x2 grid (4 plotters/image Labels,
  `self._viewer_plotters`/`_image_labels`/`_centers`/`_halves`, one set per level) synced to
  the SAME per-file camera; Prev/Next moved from toolbar buttons to anti-aliased (PIL+LANCZOS)
  filled-triangle Labels overlaid via `place()` at the vertical middle of the drawing area's
  edges (a plain `tk.Canvas` polygon version was tried first and had to be fixed — no
  anti-aliasing, and `pack()`-ing it was clipping the right one off-screen entirely); the file-
  position counter moved from the toolbar into a new margin strip below the grid.
  Third follow-up, same session, explicit: on-screen Prev/Next triangles removed entirely
  (`_make_viewer_nav_triangle` deleted, along with the now-unused `VIEWER_NAV_TRIANGLE_SIZE`/
  `ImageDraw` import) and the status label removed entirely (its only uses were a redundant
  file-name message and a "Saved" confirmation the title's own "*" already covers) — navigation
  is keyboard-only now. Added "A"/"a"/"D" as Prev/Next (alongside the existing Left/Right);
  lowercase "d" dispatches through a new `_on_key_d` by `view_mode_var` instead of binding
  straight to `_on_toggle_debug_mode`, since "d" already meant "toggle debug mode" in Inflater
  mode before any of this — only Viewer mode's own "d" means "next file".
- `pre_inflation_relaxer.py`, `inflate_polyhedron_app/app.py` (post-split): Level-0 orientation
  fix (2026-09-30, explicit — user confirmed the InsideOutChecker fix alone was insufficient
  since "if level 0 starts out inverted then it still ends up inverted", proposed burst-at-
  Level-0 and/or a Level-0 check, then explicitly said "do the 5 retries and use the best one.
  change the seed in the UI to reflect the one actually used"). `relax_initial_configuration`
  gained a mandatory burst phase (`LEVEL0_BURST_PRESSURE`/`LEVEL0_BURST_STEPS`, see physics.md)
  before repulsion starts. New `relax_initial_configuration_with_orientation_retry`
  (`LEVEL0_ORIENTATION_MAX_RETRIES=5`) is the seed-retry backstop; `app.py`'s `_run_relax_stream`
  now calls it instead of `relax_initial_configuration` directly and writes the actual seed used
  back into `self.seed_var` in `_finish_relax` — `interactive_inflater_app` untouched, still
  calls plain `relax_initial_configuration` (its own signature/behavior unchanged by this).
  Corrected the SAME session (still 2026-09-30, explicit, user reported the fix didn't work and
  provided the exact failing seed): the orientation check was reading the fan-triangulated mesh,
  not the macro polygons, and missed a real "caved-in" case entirely (see physics.md) — added a
  `base_faces` param, checked instead when given; `app.py`'s call site passes
  `base_faces=self.base_faces`. Also removed the uniform-flip-gets-a-free-mirror shortcut
  (`_mirror_z`, deleted) after the user pointed out concavity is reflection-invariant — a
  uniform flip is now just another retry candidate, same as a mixed one.
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
