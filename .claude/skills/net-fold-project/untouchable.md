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
  back into `self.seed_var` in `_finish_relax` — `interactive_inflater_app` untouched at the
  time, still called plain `relax_initial_configuration` (its own signature/behavior unchanged by
  this). (2026-10-01: `interactive_inflater_app` now uses the retry too — see the dedicated
  entry below.)
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
  "polyhedron_inflater" nickname — still active). Lighting/shading ported from
  `interactive_inflater_app` (2026-09-30, explicit — "add the shading from interactive_inflater
  to polyhedron_inflater"): new `_setup_plotter_lighting` helper + `SMOOTH_SHADING`/`MATERIAL_*`/
  `KEY_LIGHT_*`/`FILL_LIGHT_*` constants, wired into both plotter-construction sites and both
  `add_mesh` call sites (Level panels + Viewer quadrants). See `apps.md`.

`interactive_inflater_app/app.py`: MODULARIZATION (2026-09-30, explicit — "apply [the
stretchy_mesh.py-style] refactoring... to interactive_inflater_app", 10 named pieces). New
`src/apps/interactive_inflater_app/logic/` package: `face_indexer`, `edge_indexer`,
`face_selecter`, `edge_selecter`, `flat_face_attacher`, `club_member_classifier`,
`inflation_type_chooser`, `edge_modifier`, `face_modifier`, `reinflater` — see `apps.md`'s own
section for what each owns. `app.py`'s own methods became thin wrappers calling these (most
aliased to their old underscored names at import time, so behavior/call sites are unchanged);
duplicate pure functions (`fine_group_boundary_edges`/`rim_vertex_chain` vs.
`edge_indexer.group_boundary_edge_set`/`base_edge_vertex_chain`) were deduped onto the new
canonical copy. Verified via `tests/unit/interactive_inflater_app/` (new) plus an in-process
smoke test (place/connect/flat-attach/anchor-delete/diff-remove through `CombinedApp` without
`mainloop()`) — not asked to re-verify every existing hand-tested behavior beyond that.

`interactive_inflater_app/app.py`, second pass (2026-09-30, explicit — "see how the front end
can be refactored similar to the logic"): three STATEFUL (not pure) helper classes pulled out as
new files — `camera_controller.CameraController` (camera + rotate/pan/zoom gesture state),
`background_worker.run_in_background` (generalized `_run_background`, error path now an injected
callback), `mesh_snapshot.MeshSnapshotManager` (formalizes `_snapshot_mesh_state`/
`_restore_mesh_state`). `app.py`'s own methods became thin wrappers; unused `queue`/
`scipy.spatial.transform.Rotation` imports removed after the move. Rendering and the 2D canvas
gesture were explicitly reviewed and left alone (see `apps.md`'s own note on why). Verified via
new unit tests (`test_camera_controller.py`, `test_background_worker.py`,
`test_mesh_snapshot.py`) plus in-process smoke tests through `CombinedApp` with a real
`mainloop()` (interactive camera drag/pan/zoom/reset, and a full real relax/calibrate background
run reaching `is_fully_inflated=True`).
Third, same session, explicit follow-up ("put all the non-app files in a folder, appropriately
categorized/named"): the three classes above plus the pre-existing `session_state.py` moved into
a new `state/` subpackage (`git mv` for the tracked `session_state.py`, preserving history) —
named for what unifies all four: each manages mutable/transient state, as opposed to `logic/`'s
pure functions or `app.py`'s own orchestration. Every import updated (`app.py` + the three new
test files); no behavior change. Re-verified: full test suite green, `CombinedApp` still builds
and the `state.*` imports resolve.

Bug fix (2026-09-30, explicit bug report: "if i choose File > New, then place a piece, nothing
shows up in the 3d view") — PRE-EXISTING (confirmed present as far back as commit `93cdb25`,
before any of today's refactoring), not a regression from the modularization. `refresh_diff_
eligibility`'s "club emptied" branch cleared `self.faces`/etc. but never reset `self.
last_shapes_snapshot`/`last_connections_snapshot`/`last_anchor_snapshot`/`last_source_polygon_id`/
`last_root_to_vertex_id`/`last_pressure`/`level_history` — so after File > New (or deleting every
shape), the next piece placed got `classify_change`d against the STALE pre-New snapshot, came
back `"complex"`, and neither Full nor Diff Inflate ever auto-fired. Fix: that branch now also
resets all seven fields to their `__init__` defaults, so an emptied canvas behaves exactly like a
freshly started session. Verified via a scripted repro (inflate something, File > New, place one
piece, confirm `self.faces` populates) before and after the fix.

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

`pre_inflation_relaxer.py`, `interactive_inflater_app/app.py` (2026-10-01, explicit — "create a
class called seed_selecter that chooses the best seed from our 5 attempts. first, this logic
should apply to interactive_inflater as well when running full inflate. second... a time cutoff,
say 10s (max_search_time)... up to 5... (max_attempts) attempts"). New
`utils/inflate_polyhedron/seed_selecter.py` (`SeedSelecter`, `DEFAULT_MAX_ATTEMPTS=5`,
`DEFAULT_MAX_SEARCH_TIME=10.0`s) — a generic, mesh-agnostic time/count-bounded "try N seeded
attempts, keep the best" policy; `relax_initial_configuration_with_orientation_retry` refactored
to delegate its own attempt loop to it (own `attempt_fn`/`score_fn`/print diagnostics supplied,
behavior otherwise unchanged — verified against the known tetrahedron seed-19 case, still
retries to seed 20). New `max_search_time` param on that function
(`LEVEL0_ORIENTATION_MAX_SEARCH_TIME`, aliasing `SeedSelecter`'s own default) — see physics.md's
own Level 0 orientation retry section for the exact time-budget semantics.
`interactive_inflater_app/app.py`'s `on_full_inflate_clicked` now calls
`relax_initial_configuration_with_orientation_retry` (new `_run_level0_relax_with_seed_retry`
helper, `LEVEL0_SEED=0` as the fixed starting seed — this app has no seed display/entry of its
own) instead of calling `relax_initial_configuration` directly with no retry at all; the
now-unused `self.positions = random_initial_positions(...)` pre-assignment and the `relax_
initial_configuration`/`random_initial_positions` imports it was the last user of were removed.
Verified via new `tests/unit/inflate_polyhedron/test_seed_selecter.py` (6 tests: early accept,
exhausts attempts keeping least-bad, time-cutoff-to-one-attempt, runs-all-when-fast,
on_attempt callback, should_stop) plus in-process smoke tests with a real `mainloop()` for both
apps (tetrahedron seed 19 retry in isolation; a full `interactive_inflater_app` Full Inflate run
reaching `is_fully_inflated=True` with seed 0→1 retry logged; `inflate_polyhedron_app`'s own
Relax still works unchanged).

`inflate_polyhedron_app/app.py`, `interactive_inflater_app/app.py`: shading lighting retune
(2026-10-01, explicit bug report: "there's a possible bug with the shading. it seems like every
face, regardless of how it's subdivided and inflated, all get one phong lighting? shouldn't the
individual subdivisions get different lighting/shading (try tetrahedron for example)").
Investigated thoroughly before touching anything — NOT a shading-computation bug: direct
inspection confirmed VTK's per-vertex normals and Phong interpolation were already both correct
(real normal variation up to 50+ degrees measured within one subdivided macro face; an isolated
high-res render of one face showed a clean gradient). Root cause: `KEY_LIGHT_POSITION` (0.55,
0.7, 0.85) sat close enough to the camera's own view axis ("camera light" space has the camera
at (0, 0, 1)) that lighting a roughly dome-shaped inflated face from nearly the angle it's
VIEWED from produces a radially-symmetric "glow" (bright center fading evenly toward the rim in
every direction) rather than a directional gradient — reads as "basically flat plus a highlight
blob" at a small panel size even though the underlying shading is genuinely varying. Fix (both
apps, identical constants in each — same as the original shading port): `KEY_LIGHT_POSITION` ->
`(1.3, 0.2, -0.3)` (genuinely off-axis/grazing), `KEY_LIGHT_INTENSITY` 1.0->1.1,
`FILL_LIGHT_POSITION` -> `(-1.0, -0.3, 0.6)`, `FILL_LIGHT_INTENSITY` 0.35->0.45,
`MATERIAL_AMBIENT` 0.25->0.18 (more shadow depth/contrast). Verified via a real tetrahedron
Full-Inflate/Auto run in both apps, screenshotted before and after — before: each face reads as
one soft radial glow; after: each face shows an obviously directional, clearly-per-subdivision
gradient. No constant/behavior other than these five touched.
Follow-up, same day, explicit ("might be because you didn't implement diffuse lighting. so try
adding lighting that depends on face normals. turn off phong for now"): `SMOOTH_SHADING`
True->False (flat per-face shading -- each triangle lit by its OWN true face normal, no per-
vertex interpolation across neighbors) and `MATERIAL_SPECULAR` 0.35->0.0 (drops the specular
term -- the actual "Phong" part of the Blinn-Phong model; ambient+diffuse alone is plain
Lambertian) in both apps. Verified via the same tetrahedron Full-Inflate/Auto run, screenshotted
at both debug resolution and the app's own native small panel size: produces an obviously
faceted, triangle-by-triangle brightness step rather than a smooth gradient -- a stronger
"every subdivision clearly shaded differently" effect, at the cost of the smoothly-curved-
surface look `SMOOTH_SHADING` was originally added for. Revert `SMOOTH_SHADING`/
`MATERIAL_SPECULAR` to `True`/`0.35` in both apps to go back to smooth Phong shading.
Follow-up, same day, explicit ("make things a tad brighter"): `MATERIAL_AMBIENT` 0.18->0.26,
`KEY_LIGHT_INTENSITY` 1.1->1.25, `FILL_LIGHT_INTENSITY` 0.45->0.55, in both apps -- raises the
floor/overall brightness a bit without flattening the per-facet contrast the flat-shading
change above was for.
Follow-up, same day, explicit ("make the phong lighting brighter"): `MATERIAL_SPECULAR`
0.0->0.5 in both apps -- the specular term is literally the "Phong" part of Blinn-Phong
(ambient+diffuse alone is plain Lambertian, see the flat-shading entry above), so this brings
back a glossy per-facet highlight (brighter than the original pre-"turn off phong" 0.35) while
`SMOOTH_SHADING` stays False -- still flat per-face normals, not a return to smooth
interpolation.
Follow-up, same day, explicit ("i still want the diffuse and phong lighting to be brighter"):
`MATERIAL_DIFFUSE` 0.85->1.0 (its max) and `MATERIAL_SPECULAR` 0.5->0.75 in both apps --
`MATERIAL_AMBIENT`/light intensities left alone since the request named diffuse and Phong
(specular) specifically.
Follow-up, same day, explicit ("it's not actually brighter. maybe what i want is for the light
source to be more from the viewer's eyes" -- the diffuse/specular bump above wasn't visibly
brighter). Root cause: KEY_LIGHT/FILL_LIGHT sit at a deliberate side/grazing angle (see their own
comment, added to fix a prior "all one flat shade" bug), so the diffuse dot-product against a
camera-FACING surface is small regardless of the material's diffuse coefficient -- raising the
coefficient alone can't fix a weak incidence angle. Added a third light, `HEADLIGHT_POSITION =
(0.0, 0.0, 1.0)` / `HEADLIGHT_INTENSITY = 0.6`, essentially AT the camera (camera-light space has
the camera at (0, 0, 1) looking at the origin), in both apps' `_setup_plotter_lighting`. Kept
separate from, not a replacement for, KEY/FILL -- those still provide the off-axis directional
gradient that makes individual subdivisions read as differently-shaded; HEADLIGHT only adds
overall brightness on top. Verified with an off-screen icosphere render: front-facing surface is
visibly brighter while the side lights' directional facet gradient is still clearly visible.
Follow-up, same day, explicit ("now let's a bit too bright. make the other headlights less
intense" -- HEADLIGHT pushed overall brightness past where the user wanted). `KEY_LIGHT_INTENSITY`
1.25->1.0 and `FILL_LIGHT_INTENSITY` 0.55->0.4 in both apps; `HEADLIGHT_INTENSITY` left at 0.6.
Verified with the same off-screen icosphere render: toned down from the prior screenshot but
still brighter overall than before HEADLIGHT was added, directional gradient still intact.
Follow-up, same day, explicit ("drop key light to 0.4"): `KEY_LIGHT_INTENSITY` 1.0->0.4 in both
apps; `FILL_LIGHT_INTENSITY`/`HEADLIGHT_INTENSITY` left unchanged.
Follow-up, same day, explicit ("change fill_light to 0.2"): `FILL_LIGHT_INTENSITY` 0.4->0.2 in
both apps; `KEY_LIGHT_INTENSITY`/`HEADLIGHT_INTENSITY` left unchanged.
Follow-up, same day, explicit ("lower diffuse and specular to before"): `MATERIAL_DIFFUSE` and
`MATERIAL_SPECULAR` reverted 1.0/0.75 -> their pre-bump 0.85/0.5 in both apps, now that HEADLIGHT
plus the KEY/FILL retuning above actually address overall brightness -- the earlier material
bump (see its own entry) is no longer wanted on top of it.
Follow-up, same day, explicit ("lower ambient"): `MATERIAL_AMBIENT` reverted 0.26 -> its own
pre-bump 0.18 in both apps, same reasoning as the diffuse/specular revert above.
Follow-up, same day, explicit ("ok now bump up the key_light, fill_light, headlight"):
`KEY_LIGHT_INTENSITY` 0.4->0.6, `FILL_LIGHT_INTENSITY` 0.2->0.3, `HEADLIGHT_INTENSITY` 0.6->0.9,
all in both apps.
Follow-up, same day, explicit ("undo the bumping for fill light and key light"):
`KEY_LIGHT_INTENSITY` and `FILL_LIGHT_INTENSITY` reverted 0.6/0.3 -> 0.4/0.2 in both apps;
`HEADLIGHT_INTENSITY` stays at 0.9 (not mentioned, not touched).
Follow-up, same day, explicit ("can you move the phong lights closer?", clarified via follow-up
question -- "Narrow the angle a bit"). Position DISTANCE is a no-op for `light_type="camera
light"` lights (VTK Positional=False by default -- directional, only the direction to the
position matters, never how far away it is), confirmed by rendering with the position scaled to
30% of its length and diffing pixel output (identical). Instead narrowed the ANGLE: both
`KEY_LIGHT_POSITION` and `FILL_LIGHT_POSITION` blended 30% of the way toward `(0, 0, 1)` (the
camera's own position in camera-light space) -- KEY's off-axis angle ~103 -> ~84 degrees, FILL's
~60 -> ~45 degrees. `KEY_LIGHT_POSITION` (1.3, 0.2, -0.3) -> (0.9, 0.15, 0.1); `FILL_LIGHT_
POSITION` (-1.0, -0.3, 0.6) -> (-0.7, -0.2, 0.7), both apps. Verified with an off-screen
icosphere render: brighter overall with the bright patch shifted toward the viewer, directional
per-subdivision gradient still clearly visible (not reverted to the earlier "uniform glow" bug).
Follow-up, same day, explicit ("ok looks now. now dim all the key/fill/headlights a bit"):
`KEY_LIGHT_INTENSITY` 0.4->0.3, `FILL_LIGHT_INTENSITY` 0.2->0.15, `HEADLIGHT_INTENSITY` 0.9->0.75,
all in both apps.

Feature (2026-10-01, explicit: "allow undo/redo in Viewer mode for the current model you're
adjusting. if you switch to a new model, then the undo stack resets", `inflate_polyhedron_app`
only -- `interactive_inflater_app` has no equivalent Viewer mode). Camera (rotation/pan/zoom) is
the only thing Viewer mode lets the user change, so undo/redo covers that. A SINGLE stack
(`ViewerPane._viewer_undo_stack`/`_viewer_redo_stack`), not one per file, per the user's own
framing ("for the current model") -- cleared by a new `_viewer_reset_undo_stack` whenever the
file on screen changes: `_on_viewer_prev_clicked`/`_on_viewer_next_clicked`, and a file-changing
`_viewer_rescan` (current file deleted from disk, falls back to index 0). Each stack entry is a
camera-state snapshot (`_viewer_camera_snapshot`) from BEFORE one change: a whole drag/pan
gesture collapses to ONE undo step, captured at `_on_viewer_drag_start`/`_on_viewer_pan_start`
into `_viewer_gesture_start_camera` and only actually pushed at `_on_viewer_drag_end`/
`_on_viewer_pan_end` (`_viewer_commit_gesture_undo`) if the camera ended up different -- not one
per motion tick, and a click-without-moving leaves no undo entry. A scroll-wheel zoom tick and
the middle-click pan-reset each push their own single step directly, since those are already one
discrete action. Bound to Ctrl+Z (undo) / Ctrl+Y (redo), `root.bind_all` same as the existing
Left/Right/A/D viewer navigation, same `view_mode_var` guard inside the handlers so they no-op
in Inflater mode. Verified with an in-process smoke test: a scroll-zoom + a multi-tick drag
gesture each produce exactly one undo step; undoing unwinds rotation then zoom independently;
redoing restores both; switching to the next file resets both stacks to empty.

Bug fix (2026-10-01, explicit bug report: "in HIPPO Viewer, i can't switch between images" with
an `AttributeError: 'ViewerPane' object has no attribute 'view_mode_var'` traceback from
`_on_viewer_next_clicked`). A regression from the `ViewerPane` extraction (see its own entry
above): `_on_viewer_prev_clicked`/`_on_viewer_next_clicked` read `self.view_mode_var` (a guard
against the globally-bound Left/Right/A/D keys firing while Inflater mode is showing, since
Inflater mode never binds those keys itself) — moved verbatim into `ViewerPane` without also
moving (or otherwise supplying) `view_mode_var` itself, which stayed on the shell
`InflatePolyhedronApp`. Fixed by passing the shell's own `view_mode_var` (a `tk.StringVar`) into
`ViewerPane.__init__` and storing it as `self.view_mode_var`, same attribute name, just now
constructor-injected instead of living on the enclosing class. Audited every other `self.*`
reference inside `ViewerPane` for the same class of bug (grep of the whole class body) — this
was the only one. Verified: Right/Left navigation actually advances/returns the current file,
and the guard still correctly no-ops while in Inflater mode.

Bug fix (2026-10-01, explicit bug report: "when switching back to Inflater mode, the window
size should change", user-confirmed symptom: "Stays at the Viewer's square size"). `_on_view_
mode_changed` captured `self._inflater_geometry = self.root.geometry()` before switching to
Viewer and replayed that string when switching back — but `wm geometry()` can report stale
(pre-maximize) dimensions while the window is zoomed (a known Tk/Windows gap), so a maximized
Inflater window's captured geometry could be a small, stale, near-square string instead of its
real maximized size. Fixed by also recording `self._inflater_was_zoomed = self.root.state() ==
"zoomed"` alongside the geometry capture, explicitly `self.root.state("normal")` before applying
`VIEWER_WINDOW_GEOMETRY`, and on the way back re-zooming via `self.root.state("zoomed")` instead
of replaying the captured geometry string whenever `_inflater_was_zoomed` is set (falls back to
the old geometry-string replay otherwise, unchanged for the non-maximized case). Verified via an
in-process smoke test simulating `root.state("zoomed")` before switching: Viewer mode correctly
un-maximizes to the square geometry, and switching back correctly restores `state() == "zoomed"`
at the original maximized dimensions; a separate smoke test confirms the plain manual-resize
(non-maximized) path still round-trips the captured geometry string exactly as before.
