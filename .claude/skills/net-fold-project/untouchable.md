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

`docs/algorithm.md`, `stretchy_mesh.py`, `pre_inflation_relaxer.py` (2026-10-01, explicit — "try
getting rid of the cubic term and just use linear springs", then "get rid of cubic term in
spring, update docs"): the Level 1+ hardening spring (§4.1, `_relax_force`) reverted to plain
Hooke's-law linear, matching Level 0's `_spring_only_force` exactly — `HARDENING_CUBIC_COEFFICIENT`
removed entirely (no other code referenced it; confirmed by grep). `docs/algorithm.md` abstract,
§3.3, §4.1, §4.2, §4.4 updated to describe the current plain-linear force law while keeping the
hardening term's own math/motivation as explicit history (what it was, why it was tried, why it
was removed, and what to watch for if plain linear ever proves insufficient — the hardening term
is named as the fix to reintroduce in that case, not a new volume/clamp term). `pre_inflation_
relaxer.py`'s docstrings/comments that contrasted Level 0's linear spring against Level 1's
hardening one updated to note both now share the same force law. `physics.md` updated the same
way. Full test suite: still only the same 4 pre-existing unrelated failures (verified via
`git stash` before/after).

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

`tests/unit/inflate_polyhedron/test_stretchy_mesh.py`, `test_stretchy_net_layout.py` (2026-10-01,
explicit: "remove failed tests" -- the 4 failures every change this session had been reporting as
"pre-existing unrelated", confirmed stale via `git stash` before removing anything). Two separate
root causes, both genuinely pre-existing, neither caused by this session's own cubic-term removal:
- `data/input/stretchy_nets/two_pentagons_one_square.poly` doesn't exist on disk (confirmed, not
  just un-globbed) -- `test_mesh_edges_deduplicates_and_sorts` (the `PENTAGONS_AND_SQUARE` kept by
  the entry above) DELETED, `PENTAGONS_AND_SQUARE` removed too (no longer used by anything);
  `"two_pentagons_one_square"` removed from `test_stretchy_net_layout.py`'s own `NETS` list
  (`test_every_face_gets_placed`/`test_every_placed_face_keeps_unit_edge_length` still run
  parametrized over the other 5 shipped nets, unaffected).
- `test_relax_once_continues_from_the_given_positions_not_from_scratch` (plus its own leading
  "relax_once" section-comment, which only existed for it) DELETED -- a real numeric assertion
  failure (`max_stretch < 0.1` off by over 10x), unrelated to any missing file; its own comment
  already stated the HARDENING-spring assumption this session's cubic-term removal (see the
  dedicated physics entry above) invalidated anyway, so re-tuning it post-removal wasn't
  attempted, per the explicit "remove" instruction.
Full suite: 293 passed, 0 failed (previously 293 passed / 4 failed) -- these were the only 4
failures in the suite.

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

Bug fix/feature (2026-10-01, explicit: "for level 0, don't show the initial random state at the
start. the app should start with all the levels empty. stuff is only shown after simulation
done and it's showing the replay"). `draw()`'s own live-panel branch (`level ==
self.subdivision_level`) now special-cases level 0: draws empty (faces=positions=face_of_fine=
None) unless `self._level_frames.get(0)` is already populated -- i.e. unless at least one Relax
run has actually finished and been replayed this net-load. Previously this branch always showed
`self.positions` live, which right after `on_select_net` was still `random_initial_positions`'s
own raw noise cloud. Only affects this general redraw path -- the replay animation itself
(`_replay_step`) draws Level 0's panel directly, bypassing `draw()` entirely, and the
"Computing..." placeholder already blanks the panel on its own regardless. Verified: captured
Level 0's own panel image right after `on_select_net` and confirmed it's a single flat
background color (no mesh, not the random cloud) via a unique-color-count check and a visual
render; a second check confirms the panel shows real content again once a Relax run completes.

Feature (2026-10-01, explicit: "In polyhedron_inflater, add a Colour menu. items include:
Polygon-specific, Multi-colour, Randomize..." -- clarified via follow-up questions: "Rainbow" was
a typo for "Multi-colour" (just two radio options), and Multi-colour colors per INDIVIDUAL base
face, not per Polygon-Fold group). `inflate_polyhedron_app` only -- `interactive_inflater_app`'s
own version is a separate, later entry below.

New "Colour" menu (`_build_menu`): `Polygon-specific`/`Multi-colour` radiobuttons
(`self.color_mode_var`, a `tk.StringVar`) + a separator + `Randomize`, enabled only in
Multi-colour mode (`_update_colour_menu_state`, via `self._colour_menu.entryconfig`) since
Polygon-specific has no random element to reroll.

- **Polygon-specific** is the app's PRE-EXISTING coloring, unchanged: `_face_colors_by_group`,
  one color per Polygon-Fold group (`source_polygon_id`).
- **Multi-colour** is new: one random color per INDIVIDUAL base face (not per group), from the
  same `FACE_COLORS` palette, chosen to avoid matching an adjacent (edge-sharing) base face's
  own color wherever the palette allows it ("trying our best", not a hard guarantee -- a greedy
  algorithm, not globally optimal). Reuses `_draw_level_panel`'s EXISTING per-group add_mesh
  grouping completely unchanged by setting `self.group_of_base_face` to the identity mapping
  (every face its own "group") -- no rendering-path change needed at all.
- New shared pieces (explicit: "shared code should be moved to utils", so built reusable from
  the start rather than app-local, with Phase 2/`interactive_inflater_app`'s own future needs in
  mind):
  - `utils/graph_face_coloring.py`: `random_graph_coloring(n, neighbors, palette, rng=None)` --
    fully generic randomized graph coloring (processes items in random order, picks a random
    palette entry excluding ones already used by colored neighbors, falls back to the full
    palette if every entry is excluded). Not inflate_polyhedron-specific -- `neighbors` is
    caller-supplied, so a DIFFERENT adjacency notion (e.g. "pieces that could end up connected")
    can reuse it unchanged.
  - `utils/inflate_polyhedron/mesh_topology.py`: new `base_face_neighbors(base_faces,
    face_edge_ids)` -- the base-face adjacency graph (edges shared by 2+ base faces), the
    complement of the already-shared `open_base_edges` (edges used by exactly 1); both now
    derive from a new shared `_edge_owners` helper instead of duplicating that scan.
  - `inflate_polyhedron_app/logic/coloring.py`: new `random_face_colors(base_faces,
    face_edge_ids, rng=None)` composes the two above (`base_face_neighbors` +
    `random_graph_coloring` over `FACE_COLORS`) -- the one actually inflate_polyhedron-specific
    piece (which palette, which adjacency source), kept app-local since Phase 2's own equivalent
    needs a DIFFERENT adjacency notion entirely (see below) and isn't a mechanical reuse of this
    exact function.
- **Toggling without Randomize never changes Multi-colour's own colors** (explicit requirement):
  `self.multi_colors` (the actual persisted color list) is generated lazily, only when missing
  or the wrong length for the current net (`_apply_color_mode`) -- re-selecting Multi-colour
  after visiting Polygon-specific reuses the SAME list; only `_on_randomize_colors_clicked`
  (Colour > Randomize) forces a fresh `random.Random()`-seeded reroll.
- **Persistence** ("these colours persist via Save/Load, even into different app, if the target
  app supports it"): `SessionStateModel` gains `color_mode: str = "polygon"` and
  `face_colors: Optional[List[str]] = None` (the actual per-base-face list; None for
  Polygon-specific, which needs nothing persisted since it's re-derived fresh from
  `source_polygon_id` every time). `_write_session`/`on_load_session_clicked` read/write both;
  `_apply_color_mode`'s own lazy-regenerate path transparently covers a missing/stale
  `face_colors` (older session, or a mismatched net) the same way a fresh net's `None` is
  covered. A field with this exact name/shape in ANY OTHER app's own session schema can read it
  back the same way without understanding anything else in the file -- an app that doesn't
  support Colour mode at all just leaves both fields at their defaults, like any other
  unfamiliar-but-present field; a Phase 2 entry below gives `interactive_inflater_app`'s own
  schema the same two field names for exactly this reason.
- **ViewerPane** also honors a saved Multi-colour session's exact `face_colors` (was previously
  a simpler, deliberately-not-group-aware `FACE_COLORS[base_face % len(FACE_COLORS)]` fallback,
  documented as fine for a finished mesh -- Polygon-specific's own Viewer rendering is
  UNCHANGED, still that same simplification, since Multi-colour's colors are the one case where
  "whatever was actually saved" is the only meaningful answer, there being no deterministic
  group to re-derive from).
New tests: `tests/unit/test_graph_face_coloring.py`, `tests/unit/inflate_polyhedron/
test_base_face_neighbors.py`, plus two new cases in `tests/unit/inflate_polyhedron_app/logic/
test_coloring.py`. Verified with in-process smoke tests: default mode is Polygon-specific with
Randomize disabled; switching to Multi-colour generates colors and enables Randomize; toggling
back to Polygon-specific and back to Multi-colour WITHOUT Randomize reproduces the exact same
colors; clicking Randomize changes them; a real net's own generated colors show 0 neighbor
clashes; a full Save-then-Load round trip (fresh `InflatePolyhedronApp` instance) restores
`color_mode`/`multi_colors`/live `self.colors` exactly and re-enables Randomize correctly;
ViewerPane reading that same saved file reports the identical `color_mode`/`face_colors`.

Cleanup (2026-10-01, explicit: "look for more opportunities to clean up code"). Removed `import
matplotlib.colors as mcolors` from `inflate_polyhedron_app/app.py` -- dead leftover from this
session's logic extraction: `_midpoint_color`/`_darken_color`/`_face_colors_by_group` (the only
callers) moved to `logic/coloring.py`, which has its own `mcolors` import; `app.py` no longer
uses the name at all (verified: zero other references). A broader scout of both apps' `app.py`/
`logic`/`state`, the shared solver lib, and this session's new files found no other confident
dead code, duplication, or stale-reference issues -- the modularization work was already clean.

Feature (2026-10-01, explicit: "in level 0, when it's computing, it should say Computing... like
the other levels. then when it's done, it should replay like the other levels. and debug mode
should have the replay slider", `inflate_polyhedron_app` only). Level 0's own Relax previously
kept redrawing live throughout (a deliberate earlier design choice, since it has no pressure-
calibration phase with discarded trials the way Levels 1-3 do) -- now shows the same
"Computing..." placeholder and does the same post-run replay, to look consistent with Levels 1-3.
- `on_relax_clicked` now calls `_start_computing_animation(0)` (same helper Levels 1-3 use) and
  seeds `self._level0_relax_frames = [(self.positions, self.iteration_count)]`, fresh every
  click -- only the MOST RECENT Relax click's own run is ever replayed/scrubbable, matching how
  Levels 1-3's own `self._level_frames[level]` gets overwritten by each new Inflate click, not
  accumulated across clicks.
- `_apply_relax_progress` no longer calls `_draw_level_panel(0, ...)` directly (the Computing
  placeholder owns the panel now) -- instead appends `(positions, iteration_count)` to
  `self._level0_relax_frames` on every progress tick.
- `_start_frame_replay`/`_replay_step`/`_finish_frame_replay` (previously Inflate-only)
  generalized to take `apply_final`/`on_finished` callbacks instead of a hardcoded Inflate-
  specific `final_result` tuple + a hardcoded call to `_finish_inflate` -- real deduplication,
  not just reorganization: both Inflate's own winning-trial replay (`_on_pressure_calibrated`,
  updated to pass a small `apply_final` closure + `self._finish_inflate`) and Level 0's new one
  now share the exact same replay engine.
- `_finish_relax` split: the was-Stopped branch returns early exactly as before (no replay for a
  run that didn't finish, matching `_on_pressure_calibrated`'s own stopped branch); the
  converged/step-cap branch instead plays back `self._level0_relax_frames` via
  `_start_frame_replay`, populating `self._level_frames[0]`/`self._level_scrub_index[0]` first
  (so the slider is usable immediately, same as Levels 1-3) and handing the old promotion/report
  logic to a new `_finish_relax_report` (split out the same way Inflate's own
  `_on_pressure_calibrated`/`_finish_inflate` already were) -- called once replay finishes.
- Level 0's own replay scrubber: previously never built at all (`__init__` only created
  `level_replay_sliders[level]` `if level > 0`) -- now built for every level 0..MAX_LEVEL, so
  debug mode's existing generic pack/forget logic picks it up automatically, no other UI wiring
  needed.
- Updated three stale docstrings/comments that had explicitly documented the OLD "Level 0 stays
  live" behavior as deliberate (`on_relax_clicked`, `on_inflate_clicked`,
  `_start_computing_animation`) to describe the new shared behavior instead.
- Verified with in-process smoke tests: `_computing_level` is 0 immediately after a Relax click
  (before any background work runs); a Stop click issued before the run has a chance to progress
  correctly skips replay entirely, leaves `subdivision_level` at 0, and leaves
  `self._level_frames[0]` unset; a run that converges correctly populates
  `self._level_frames[0]`/the Level 0 slider (range/enabled state correct, scrubbing to an
  earlier frame works) and promotes to Level 1 afterward, exactly as Levels 1-3's own Inflate
  does.

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

Shared-code consolidation (2026-10-01, explicit: "also make sure they are using shared code
whenever possible. shared code should be moved to utils" -- REVERSES this project's own prior
"duplicate rather than cross-import between the two sibling apps" convention referenced
throughout this file and `apps.md`; a scout agent catalogued every genuine duplicate first, user
confirmed scope including the larger camera-math item via follow-up question). Five pieces of
byte-identical (or near-identical) logic moved out of both `inflate_polyhedron_app/app.py` and
`interactive_inflater_app/app.py` into `src/utils/`, each re-exported/aliased under its old name
so every existing call site is unchanged:
- `utils/inflate_polyhedron/plotter_lighting.py`: `SMOOTH_SHADING`/`MATERIAL_*`/`KEY_LIGHT_*`/
  `FILL_LIGHT_*`/`HEADLIGHT_*` constants (including their entire multi-entry tuning-history
  comment, previously copy-pasted verbatim in both files) + `setup_plotter_lighting(plotter)`.
  `interactive_inflater_app`'s own `_setup_plotter_lighting(self)` method now just calls
  `setup_plotter_lighting(self.plotter)`.
- `utils/inflate_polyhedron/pressure_history_guess.py`: `guess_pressure_from_history` -- was
  each app's own `logic/reinflater.py` (now deleted from both); both apps import the shared
  module AS `reinflater` (`from utils.inflate_polyhedron import pressure_history_guess as
  reinflater`), so every `reinflater.guess_pressure_from_history(...)` call site is unchanged.
  The two apps' own duplicate test files (`tests/unit/inflate_polyhedron_app/logic/test_
  pressure_history_guess.py`, `tests/unit/interactive_inflater_app/test_reinflater.py`)
  consolidated into one shared `tests/unit/inflate_polyhedron/test_pressure_history_guess.py`.
- `utils/inflate_polyhedron/mesh_normals.py`: `vertex_normals` -- was duplicated in
  `inflate_polyhedron_app/logic/geometry.py` and inlined as `interactive_inflater_app`'s own
  module-level `_vertex_normals`. `logic/geometry.py` re-exports it under the same name.
- `utils/inflate_polyhedron/mesh_topology.py` (NEW -- distinct from, and not to be confused
  with, `inflate_polyhedron_app/logic/mesh_topology.py`, which still holds the NON-duplicated
  `fan_level_edges`/`layout_from_net_layout`/`net_layout_is_new_format`/
  `INTERACTIVE_BUILDER_EDGE_LENGTH`): `build_level1_topology`/`open_base_edges` -- were
  duplicated in `inflate_polyhedron_app/logic/mesh_topology.py` and inlined as
  `interactive_inflater_app`'s own `_build_level1_topology`/`_open_base_edges`. The app-local
  `logic/mesh_topology.py` re-exports both under the same names.
- `utils/numeric_entry_validation.py`: `is_valid_numeric_partial` -- was
  `inflate_polyhedron_app`'s own `_is_valid_numeric_partial` @staticmethod and
  `interactive_inflater_app`'s own module-level `_is_valid_numeric_partial`; both now import the
  shared function directly under the same aliased name (the staticmethod itself was removed,
  not kept as a wrapper, since nothing else referenced it as a bound method).
- `utils/camera_trackball.py`: `initial_rotation`/`rotate`/`pan`/`zoom` -- the pure trackball-
  rotate/NDC-pan/clamped-zoom math, confirmed duplicated THREE times total: `inflate_polyhedron_
  app`'s own `_initial_level_rotation`/`_on_level_motion`/`_on_level_pan_motion`/
  `_on_level_scroll` (InflaterPane's level-panel camera), that SAME file's `_on_viewer_drag_
  motion`/`_on_viewer_pan_motion`/`_on_viewer_scroll` (ViewerPane's own quadrant camera -- a
  second, previously-undetected internal duplicate within the same file), and
  `interactive_inflater_app/state/camera_controller.py`'s own `initial_rotation`/`CameraController.
  drag_motion`/`pan_motion`/`scroll`. All three call sites now delegate to the shared functions;
  `CameraController` re-exports `initial_rotation` under the same name so its own module-level
  call sites are unchanged.
New direct test coverage added for the two modules that had none before this move (the
inflate_polyhedron-specific ones were already covered via the app-local re-export tests, which
still pass unchanged): `tests/unit/test_camera_trackball.py`, `tests/unit/
test_numeric_entry_validation.py`.

Verified: full test suite passes (249 base + the new/consolidated tests, same 4 pre-existing
unrelated failures as every other change this session); an in-process smoke test constructing
both apps, loading a net, toggling debug mode, and switching Viewer/Inflater modes in
`inflate_polyhedron_app` succeeds; a second smoke test exercises every camera call site directly
(level-panel drag/pan/scroll, Viewer-quadrant drag/scroll, and `interactive_inflater_app`'s own
`CameraController` drag/pan/scroll) and confirms each one's rotation/pan/zoom actually changes as
expected; a third smoke test types `"1e-03"` into `inflate_polyhedron_app`'s Tolerance spinbox
and confirms the shared numeric-entry validator still accepts it live through Tk's own
`validatecommand` registration.

Consistency fix (2026-10-01, explicit: "look for inconsistencies between the related apps and
ask me before fixing them" -- a scout agent found one confident gap, user approved fixing it).
`inflate_polyhedron_app` has had a Ctrl+S shortcut for Save (`_on_control_s`, bound via
`root.bind_all`, with `accelerator="Ctrl+S"` shown in its File menu) since before this session;
`interactive_inflater_app`'s own `CombinedApp` had the identical conceptual "Save Session..."
File-menu item but no keyboard shortcut at all. Added the same pattern there: `root.bind_all`
for both `<Control-s>`/`<Control-S>` (case-insensitive, same Shift/Caps-Lock reasoning as the
sibling app's own comment) calling `self.inflater.on_save_session_clicked()` directly, plus
`accelerator="Ctrl+S"` on the "Save Session..." menu item. Deliberately a PLAIN `bind_all`, not
`BuilderPane`'s own guarded `_bind_all_guarded` (used for its real text-editing shortcuts,
Ctrl+C/V/Z/Y, which must stand down inside a text-entry widget) -- Ctrl+S isn't a text-editing
keystroke, same reasoning `inflate_polyhedron_app`'s own unguarded Ctrl+S binding already relies
on. Verified with an in-process smoke test: both `<Control-s>` and `<Control-S>` correctly
invoke `on_save_session_clicked`, and the File menu's "Save Session..." entry reports
`accelerator == "Ctrl+S"`.

Feature (2026-10-01, explicit: "add a Colour menu [to inflate_polyhedron_app]... once that's
done, add the same thing for interactive_inflater" -- this is the second half, for
`interactive_inflater_app`; see its own earlier entry above for the inflate_polyhedron_app half).
Same radio Polygon-specific/Multi-colour + Randomize menu, but colors are tracked per 2D BUILDER
SHAPE (`InflaterPane.shape_colors: {shape_id: color}`), not per 3D base face -- a shape can be
given a color before it's ever inflated (new `logic/coloring.py`'s own module docstring has the
full reasoning). "Polygon-specific" is this app's PRE-EXISTING POLYGON_COLORS-by-side-count
coloring, completely unchanged. "Multi-colour" colors each inflated base face by its own shape's
`shape_colors` entry (a Polygon-Fold shape's several fan triangles all get the SAME color, unlike
inflate_polyhedron_app's own per-individual-triangle version -- deliberate, since colors are
assigned per PIECE here, before fold-expansion even exists).
- `CombinedApp._assign_colors_for_new_shapes` (new `self._known_shape_ids` set) diffs the
  builder's current shape ids against every one already seen on EVERY builder edit and load,
  calling `InflaterPane.ensure_shape_color` for each brand-new one -- addresses the user's own
  complication: "when a user picks up a piece, we don't know where they're going to place it
  yet... give the new piece a colour that's not used or at least not the colour of a piece that
  it could be connected to." `ensure_shape_color` picks via `coloring.pick_color_for_new_shape`,
  avoiding the colors of every shape with at least one still-open edge (`coloring.
  shapes_with_open_edges` -- the only available proxy for "could end up connected to this" before
  any real connection/mesh adjacency exists), falling back to any unused color, then the whole
  palette -- "our best effort", explicitly not guaranteed (the user's own words: "if that's not
  possible, it's ok, because Randomize will fix that").
- `InflaterPane._apply_color_mode` (called at the top of every `_render`) lazily fills in a color
  for any shape_id the CURRENT mesh's groups reference but doesn't have one yet (a loaded net
  with no saved colors, etc.) -- never touches an already-assigned shape's color, so toggling
  Polygon-specific/Multi-colour without Randomize never changes Multi-colour's own colors, same
  rule as the sibling app.
- `on_randomize_colors_clicked` re-rolls EVERY currently-inflated shape's color from scratch,
  using the REAL mesh adjacency now available (new `coloring.shape_group_neighbors` -- maps
  `utils.inflate_polyhedron.mesh_topology.base_face_neighbors`' own group-level adjacency through
  `source_polygon_id` to shape-level -- + `coloring.random_shape_colors`, a thin shape_id-keyed
  wrapper around `utils.graph_face_coloring.random_graph_coloring`), a strictly better-informed
  pick than the placement-time guess since real connections exist by then.
- Menu built by a new `CombinedApp._build_colour_menu`, called AFTER `self.builder`/
  `self.inflater` are constructed (needs `self.inflater.color_mode_var` to exist) -- `_build_menu`
  (called earlier in `__init__`, before either pane exists) now just stashes `self._menubar`/
  `self._menu_kwargs` for it to reuse.
- Persistence: `InflaterSessionStateModel` gains the SAME `color_mode`/`face_colors` field names
  as inflate_polyhedron_app's own `SessionStateModel` (`face_colors` a flat list parallel to
  `base_faces`, one entry per group -- NOT per shape_id) -- `on_save_session_clicked` derives it
  from `shape_colors` via `_multi_color_for_group`; `_apply_loaded_session` rebuilds
  `shape_colors` from it keyed by the SAME remapped `source_polygon_id` every other loaded field
  already goes through (so a `.hippie` whose shapes get fresh live ids on load still lines colors
  up with the right shape -- verified: colors stayed matched to the correct shape across a
  save/load round trip even though the ids themselves changed, same remap every other field
  here already relies on). `_load_hippo_session` passes a loaded `.hippo`'s own `color_mode`/
  `face_colors` straight through too, since that sibling app's session format already uses the
  identical field-name/shape convention (2026-10-01, explicit: "these colours persist via
  Save/Load, even into different app, if the target app supports it").
New shared logic module `interactive_inflater_app/logic/coloring.py` (`shapes_with_open_edges`,
`pick_color_for_new_shape`, `shape_group_neighbors`, `random_shape_colors`), reusing
`utils.graph_face_coloring.random_graph_coloring`/`utils.inflate_polyhedron.mesh_topology.
base_face_neighbors` rather than duplicating either. New tests:
`tests/unit/interactive_inflater_app/test_interactive_inflater_coloring.py` (named to avoid a
pytest basename collision with inflate_polyhedron_app's own `logic/test_coloring.py` -- this
project's tests have no `__init__.py` anywhere, so pytest requires every test file's bare
filename to be unique project-wide). Verified: full test suite green (same 4 pre-existing
unrelated failures as every other change this session); in-process smoke tests confirm colors
are assigned the moment a shape is placed, toggling modes without Randomize reproduces the exact
same colors, Randomize changes them, and a real Full-Inflate-then-save-then-load round trip
preserves each shape's own color correctly through the live-id remap.

Feature (2026-10-01, explicit: "multi_colour should apply to the 2d view as well",
`interactive_inflater_app` only). `BuilderPane._draw_shape` (the 2D canvas's own per-shape draw,
already overridden there to dim disconnected shapes) now also overrides `fill_hex` from
`InflaterPane.shape_colors[shape["id"]]` whenever `color_mode_var == "multi"`, BEFORE the
disconnected-dimming check -- `shape_colors` already has an entry for every placed shape
regardless of inflation state (`CombinedApp._assign_colors_for_new_shapes` assigns one the moment
a shape is placed), so this needs no new state, just reading it. `on_color_mode_changed`/
`on_randomize_colors_clicked` (InflaterPane) now also call `builder._redraw()` (previously only
`self._render()`, the 3D side) so the 2D canvas updates immediately on a mode toggle or Randomize
click; `CombinedApp._assign_colors_for_new_shapes` also redraws the builder when it assigns a
color to a brand-new shape while already in Multi-colour mode, so a freshly placed shape never
flashes its old Polygon-specific color for one frame. Polygon-specific mode unaffected (still
`POLYGON_COLORS[n]`, `fill_hex` left untouched when not in "multi").

Feature (2026-10-01, explicit: "Put Undo/Redo in an Edit menu. It should be able to undo/redo
colour changes"). New `CombinedApp._build_edit_menu` adds an Edit menu (Undo/Redo, "Ctrl+Z"/
"Ctrl+Y" accelerator labels, display-only same as every other accelerator here) calling the
SAME `BuilderPane.on_undo_key`/`on_redo_key` the icon buttons/keyboard shortcuts already did --
built right after `self.builder`/`self.inflater` exist (same timing reason as
`_build_colour_menu`, moved into the same block). `CombinedApp._update_edit_menu_state`, wired
to a new `InflaterPane.on_undo_redo_state_changed` callback fired from the existing
`_refresh_undo_redo_buttons`, keeps the menu's own enabled state in sync with the icon buttons'.
- To make color changes ACTUALLY undoable: `BuilderPane._snapshot_state`/`_restore_snapshot`
  (overriding `InteractiveBuilderApp`'s own undo/redo primitives) now carry `color_mode`/
  `shape_colors` (a plain shallow copy -- every value's a hex-string color) alongside
  shapes/connections in the SAME snapshot dict every existing undo/redo call site already uses
  -- so a shape placement that also picks up its own first color undoes/redoes together with the
  shape, no separate tracking needed. `_restore_snapshot`'s own addition also calls
  `InflaterPane._render()` when `base_faces` is set, since a color-only undo/redo (see below)
  changes nothing `classify_change` would ever notice (shapes/connections untouched), so nothing
  else would otherwise redraw the 3D panel with the just-restored colors.
- `InflaterPane.on_color_mode_changed`/`on_randomize_colors_clicked` each now push their own
  undo snapshot. Randomize is the simple case (`builder._push_undo()` right before mutating
  `self.shape_colors`, since nothing's changed it yet at that point). The mode-toggle radio
  buttons are trickier: a Tk `Radiobutton`'s `variable` is already set to the NEW value by the
  time its own `command` fires, so `_snapshot_state()`'s own live read would otherwise capture
  the new mode as if it were the "before" state -- worked around with a new
  `InflaterPane._last_color_mode` (the previous value, read before `_apply_color_mode()` runs,
  updated after), used to OVERRIDE the snapshot's own `color_mode` field before recording it.
  Kept in sync by `_restore_snapshot` too, so undoing/redoing past a mode change doesn't leave it
  stale.
Verified with an in-process smoke test: placing a shape, switching to Multi-colour, then
Randomize each push their OWN separate undo step; three Undos cleanly peel off Randomize's own
color change, then the mode switch, then the shape placement, in that order, each leaving every
OTHER piece of state exactly as it was at that point; three Redos restore all three again in
order; the Edit menu's own Undo/Redo entries track the icon buttons' enabled state throughout.

Feature (2026-10-01, explicit follow-up: "it should apply to polyhedron_inflater too (in both
views). There, the undo/redo stack applies to colours, roatations/scale/zoom" -- the second half
of the Edit-menu-undo/redo feature above, now for `inflate_polyhedron_app`). New Edit menu (File/
Run/Edit/Colour/View ordering) with Undo/Redo, `accelerator="Ctrl+Z"`/`"Ctrl+Y"`, dispatching by
`view_mode_var` (`_on_edit_undo`/`_on_edit_redo`, same pattern `_on_control_s` already uses for
Ctrl+S) to whichever view is actually showing:
- **Viewer mode**: dispatches straight to the PRE-EXISTING `ViewerPane._on_viewer_undo`/
  `_on_viewer_redo` (camera-only, see that feature's own earlier entry) -- unchanged behavior,
  just now also reachable from a menu, not only Ctrl+Z/Ctrl+Y. Its own `bind_all("<Control-z>"
  /...)` calls, previously set inside `ViewerPane.__init__` itself, were REMOVED from there and
  centralized into `InflatePolyhedronApp._build_menu` instead (binding the SAME key sequence
  from two separate `bind_all` calls would silently have the later one win outright -- Tk's
  bind_all keeps only the latest registration per sequence+tag, it doesn't chain callbacks), now
  calling `_on_edit_undo`/`_on_edit_redo` so either view's own stack can fire depending on
  `view_mode_var` at the moment the key is actually pressed.
- **Inflater mode**: brand new `_on_inflater_undo`/`_on_inflater_redo` + a new single stack
  (`self._inflater_undo_stack`/`_redo_stack`) -- Colour-menu state (`color_mode`/`multi_colors`)
  and the shared Level camera (rotation/zoom/pan) are the only two things this view lets the
  user change (no 2D canvas/net edits here, unlike `interactive_inflater_app`'s own equivalent),
  so `_inflater_snapshot`/`_inflater_apply_snapshot` bundle both into ONE entry rather than two
  separate undo systems. Net panel's own independent `net_zoom`/`net_pan` (2D, matplotlib,
  genuinely separate state from the Level panels' shared 3D camera) is deliberately NOT included
  -- the user's own "rotations/scale/zoom" never named it, and it has no rotation to begin with,
  so folding it in would mix two conceptually different "zoom" axes into one stack for no asked-
  for reason; easy to add later if wanted.
  - `_on_level_drag_start`/`_on_level_pan_start` capture a snapshot (`self.
    _inflater_gesture_start_snapshot`); `_on_level_drag_end`/`_on_level_pan_end` push it via
    `_inflater_commit_gesture_undo` (ONE step per whole drag gesture, not per motion tick, and
    only if the camera actually ended up different) -- same pattern as `ViewerPane.
    _viewer_commit_gesture_undo`. `_on_level_scroll`/`_on_level_pan_reset` each push directly
    (already single discrete actions).
  - `_on_color_mode_changed`/`_on_randomize_colors_clicked` push their own steps -- same Tk-
    Radiobutton-variable-already-flipped workaround (`self._last_color_mode`) as
    `interactive_inflater_app`'s own identical feature; see that entry's own explanation.
Verified with an in-process smoke test: Colour mode switch + Randomize each push their own undo
step and undo/redo correctly in order (mirroring the interactive_inflater_app verification);
a mouse-wheel zoom tick and a full rotate-drag gesture each produce exactly one undo step, with
a click-that-never-moved producing none; undo/redo correctly restores/reapplies rotation; Ctrl+Z/
Ctrl+Y dispatch correctly to Viewer mode's own pre-existing stack with no crash when
`view_mode_var` is "viewer". Full suite green (same 4 pre-existing unrelated failures).

Bug fix (2026-10-01, explicit bug report: "Polyhedron-specific colouring is wrong. It should use
the colour scheme in interactive_inflater, where triangles are green, and as n increases, it
gradually goes to blue then purple"). `inflate_polyhedron_app`'s "Polygon-specific" Colour mode
(both the live Inflater view and the Viewer's own rendering) was coloring each Polygon-Fold
GROUP with an arbitrary `FACE_COLORS` entry cycled by first-seen group order -- never actually
keyed by the polygon's own side count at all, unlike `interactive_builder_app`/
`interactive_inflater_app`'s identical-sounding "Polygon-specific" mode, which really does use
`POLYGON_COLORS` (triangle green -> ... -> octagon purple).
- New shared `utils/polygon_colors.py` (`POLYGON_NS`, `POLYGON_COLORS`, `hls_hex`) -- moved OUT
  of `interactive_builder_app/app.py` (where it used to live alone) rather than having
  `inflate_polyhedron_app` import that whole Tkinter app just for one constant table (those two
  apps have otherwise always stayed deliberately decoupled -- see this file's own module-list
  section); per the "shared code should be moved to utils" convention from earlier this session.
  `interactive_builder_app/app.py` now imports `POLYGON_NS`/`POLYGON_COLORS` from there under
  the same names (every existing call site unchanged); `interactive_inflater_app/app.py`'s own
  import (already cross-importing `interactive_builder_app`) is unaffected -- it still gets the
  same values, just one hop further upstream now.
- `inflate_polyhedron_app/logic/coloring.py`: new `polygon_n_of_group(source_polygon_id,
  net_layout)` -- `{group: that group's ORIGINAL polygon's own side count}`, reading
  `net_layout`'s own `"shape_id"`/`"n"` entries (written by `interactive_builder_app`'s Save) --
  needed because a Polygon-Fold shape's own base face(s) are fan-TRIANGULATED, so
  `len(base_faces[group])` alone would read every one of its fold-triangles as a plain triangle
  instead of its real source polygon (same reasoning as `interactive_inflater_app`'s own
  `face_indexer.group_polygon_n`). `face_colors_by_group` (signature changed: takes `base_faces`
  directly, not just a face COUNT, since it now needs each face's own vertex count too) now
  colors by `POLYGON_COLORS.get(n, ...)` where `n` comes from the new `n_by_group` param when
  available, else `len(base_faces[i])` -- correct whenever there's no Polygon-Fold at all.
  Falls back further to the old `FACE_COLORS`-cycling behavior only for an `n` with no
  `POLYGON_COLORS` entry (> 8 sides).
- `InflatePolyhedronApp._apply_color_mode`'s own "polygon" branch now builds `n_by_group` from
  `self._source_polygon_id` + the loaded net's own `net_layout` before calling
  `_face_colors_by_group`.
- `ViewerPane._viewer_show_current` now computes `polygon_color_by_group` ONCE per file (same
  pure `_face_colors_by_group`/`polygon_n_of_group`, fed `session.base_faces`/`net_file`'s own
  `source_polygon_id`/`net_layout`) and passes it to every level's own `_viewer_draw_level_panel`
  call -- that method's own Polygon-specific branch (previously `FACE_COLORS[base_face %
  len(FACE_COLORS)]`, the exact same bug, just a second independent copy of it) now reads this
  dict instead, falling back to the old modulo scheme only if a `base_face` is somehow missing
  from it.
- A pre-existing, UNRELATED limitation surfaced while verifying this (not introduced by this
  fix, not fixed by it either -- out of scope for this bug report): a net needing
  `self_join_triangulator` at load time (e.g. `goose.poly`, `hoodie.poly`, `spider_leg.poly`) has
  its own `source_polygon_id` discarded entirely (`on_select_net`'s own pre-existing guard --
  the triangulator changes both the face count and vertex-id space, so a pre-triangulation
  `source_polygon_id` list can no longer line up), so any Polygon-Fold group in THAT specific net
  falls back to `len(base_faces[i])` (post-triangulation, i.e. 3) instead of its real original
  side count -- reads as green instead of its true color. Every net WITHOUT a self-join (the
  common case -- verified against the real `hippo.hippo` output file's own 42 groups, spanning
  squares/pentagons/hexagons/7-gons/8-gons, zero mismatches) colors correctly.
Updated tests: `tests/unit/inflate_polyhedron_app/logic/test_coloring.py`'s two existing
`face_colors_by_group` tests (now exercising real differently-sized `base_faces`, asserting
actual `POLYGON_COLORS` values instead of just "some color"), plus new cases for
`polygon_n_of_group` (shape_id->n mapping, empty without `source_polygon_id`/`net_layout`, empty
for a legacy index-aligned `net_layout` with no `"shape_id"` entries) and a folded-shape/`n_by_
group` case. Verified: full suite green (same 4 pre-existing unrelated failures); an in-process
smoke test against the real `hippo.hippo` saved session (Viewer mode) found zero color/side-
count mismatches across all 42 of its groups.

Feature + bug fix (2026-10-01, explicit: "use multi-colour as default", then "make sure the
specific colours and the colour mode are saved/loaded appropriately"). `color_mode_var`'s own
LIVE starting value changed `"polygon"` -> `"multi"` in both `inflate_polyhedron_app` and
`interactive_inflater_app` (`_last_color_mode` likewise); `SessionStateModel.color_mode`/
`InflaterSessionStateModel.color_mode`'s own field DEFAULT deliberately left at `"polygon"` --
that default only matters for a file saved before the Colour menu existed, which never saved
any `multi_colors`/`face_colors` either, so defaulting ITS read-back to `"multi"` would show
freshly-randomized colors instead of reproducing what was actually on screen when it was saved.

Auditing the save/load paths for the default change surfaced a real, pre-existing latent bug in
BOTH apps: `on_load_session_clicked`/`_apply_loaded_session` each set `color_mode_var` from the
loaded file but never updated `self._last_color_mode` to match -- harmless as long as the live
default and every loaded file happened to agree, but with "multi" now the live default, loading
an older/explicitly-"polygon" session left `_last_color_mode` stuck at "multi" (or whatever it
was before the load). The FIRST Colour-menu mode toggle after such a load would then record the
WRONG "before" state in its own undo entry (see the Edit-menu-undo/redo feature above) --
`_last_color_mode = state.color_mode` (`inflate_polyhedron_app`) / `_last_color_mode = color_mode`
(`interactive_inflater_app`) added right alongside each one's existing `color_mode_var.set(...)`
call. Verified with an in-process smoke test, specifically reproducing the stale-tracking
scenario (a FRESH app, live default "multi", loading a session explicitly saved in "polygon"
mode): confirms `_last_color_mode` now correctly reads "polygon" right after that load (not the
fresh app's own stale "multi" default), and that undoing a subsequent mode-toggle-to-"multi"
correctly lands back on "polygon", not "multi" -- in both apps. Also re-verified (not a new
finding, just re-confirmed intact after the default change) that Multi-colour's own specific
per-face/per-shape colors round-trip correctly through a real save/load in both apps -- in
`interactive_inflater_app`'s case, matched by shape IDENTITY/placement order rather than raw id
(a `.hippie` load always reassigns fresh live shape ids, same remap every other field there
already relies on -- see that feature's own earlier entry). Full suite green throughout (same 4
pre-existing unrelated failures).

Feature + bug fix (2026-10-01, explicit: "colour changes should apply in Viewer mode as well,
and they should factor into the undo/redo stack" -- `inflate_polyhedron_app` only; Viewer mode
has no equivalent in `interactive_inflater_app`). Previously the Colour menu only ever affected
Inflater mode's own live net -- clicking it while Viewer mode was showing silently changed
hidden Inflater-view state with zero visible effect. Now the SAME menu (one set of widgets,
shared by both views) actually edits the CURRENTLY VIEWED `.hippo` file while Viewer mode is
active, and that edit is undoable via the SAME `_viewer_undo_stack`/`_viewer_redo_stack` the
pre-existing camera undo/redo already uses.
- `ViewerPane.__init__` now takes a third `app` param (the owning `InflatePolyhedronApp`
  instance -- `self.viewer = ViewerPane(self.root, self.view_mode_var, self)`), since the
  Colour menu itself (`color_mode_var`/`_colour_menu`/`_update_colour_menu_state`) lives on
  `app`, not `ViewerPane` -- needed so Viewer-mode Colour edits can read/drive it.
- `_viewer_show_current` (called on every file navigation) now RESYNCS `app.color_mode_var`/
  `app._last_color_mode` to the file actually on screen (`session.color_mode`) -- while Viewer
  mode is active, that same StringVar the menu's radiobuttons are bound to displays/controls
  whichever file is showing, instead of Inflater mode's own live value.
- `InflatePolyhedronApp._on_view_mode_changed` now snapshots `color_mode_var`/`_last_color_mode`
  into `_inflater_color_mode_snapshot`/`_inflater_last_color_mode_snapshot` right before
  entering Viewer mode (same capture-before-overwrite idea the method already used for window
  geometry), and restores them on the way back out -- so a trip into Viewer mode never leaks
  into Inflater mode's own remembered Colour state.
- New `ViewerPane._on_viewer_color_mode_changed(new_mode)`/`_on_viewer_randomize_colors_clicked`
  -- `InflatePolyhedronApp._on_color_mode_changed`/`_on_randomize_colors_clicked` (the menu's
  own command handlers) now dispatch to these by `view_mode_var`, same pattern `_on_control_s`/
  `_on_edit_undo` already use. New `_viewer_ensure_multi_colors`/`_viewer_color_face_edge_ids`
  mirror Inflater mode's own `_apply_color_mode`/`on_select_net` lazy-generate logic, just
  reading/writing the CURRENT file's own `session.face_colors`/`session.base_faces`/
  `session.net_file` instead.
- Undo/redo: `_viewer_camera_snapshot`/`_viewer_apply_camera_snapshot` (camera-only) are joined
  by new `_viewer_state_snapshot`/`_viewer_apply_state_snapshot`, which bundle a file's camera
  AND its `color_mode`/`face_colors` into ONE snapshot dict -- every push/apply call site
  (`_on_viewer_undo`/`_on_viewer_redo`, the drag/pan gesture start capture, `_on_viewer_pan_
  reset`/`_on_viewer_scroll`'s own direct pushes) now uses the bundled version, so a Colour
  change and a camera adjustment share the exact same stack/ordering, undo-able/redo-able
  individually in the order they actually happened. `_viewer_gesture_start_camera` renamed
  `_viewer_gesture_start_state` throughout to match (still camera-only in practice -- a drag/pan
  gesture never touches Colour state -- but the TYPE it holds is now the bundled snapshot).
  `_on_viewer_undo`/`_on_viewer_redo` now call `_viewer_show_current()` (a full rebuild) instead
  of `_viewer_render_all()` (camera-only reposition), since undoing a Colour change needs the
  mesh's own colors rebuilt, not just the camera repositioned.
- `_viewer_mark_dirty` now also compares `session.color_mode`/`face_colors` against a new
  `_viewer_saved_colors[path]` (the ON-DISK values, same lifecycle as the pre-existing
  `_viewer_saved_cameras`) -- seeded in `_viewer_get_session`, refreshed in `_viewer_save_path`
  (which needs no separate copy-over step for the colors themselves: Colour edits already
  mutate `session` directly, unlike the camera which lives in a separate always-copied-over
  dict).
- Bug fix, caught while building this (and found to affect ALL THREE existing "toggle Colour
  mode" undo implementations equally -- `inflate_polyhedron_app`'s own Inflater-mode handler,
  this new Viewer-mode one, and `interactive_inflater_app`'s): each one's undo snapshot was
  taken AFTER calling its own lazy-generate/-fill step (`_apply_color_mode`/
  `_viewer_ensure_multi_colors`), so the snapshot captured the FRESHLY GENERATED colors as if
  they were already "the before state" -- undoing back out of Multi-colour then left those
  colors sitting around (and the file/net spuriously marked dirty) instead of truly returning
  to the pristine pre-click state. Fixed in all three by snapshotting BEFORE the generate/fill
  step runs, not after. Verified directly: a full undo of "switch to Multi-colour" (with no
  intervening Randomize) now correctly restores `face_colors`/`multi_colors`/`shape_colors` to
  their exact pre-click value (`None` for a file/net that never had any) and clears the dirty
  flag, in both inflate_polyhedron_app's Viewer mode and interactive_inflater_app.
Verified with in-process smoke tests: the Colour menu's own display (`color_mode_var`) tracks
whichever Viewer file is on screen across navigation; switching a Viewer file's mode/Randomizing
correctly dirties it; three full undos (Randomize -> mode switch -> back to the file's original
on-disk state) leave it exactly as it was on disk (not dirty); three redos restore all three
steps in order; returning to Inflater mode restores ITS own Colour state untouched; a real
save-to-disk/reload-fresh round trip in Viewer mode preserves the edited color_mode/face_colors
exactly. Full suite green throughout (same 4 pre-existing unrelated failures).

Bug fix (2026-10-01, explicit bug report: "Polygon-specific colours are not working in Viewer
view" -- items 2/3 of the same report, re Inflater mode's own Colour state persisting across a
Viewer excursion and Viewer's own mode following whichever file is on screen, were verified
ALREADY correct as designed in the entry above; only item 1 was a real bug). Root cause:
`logic/coloring.polygon_n_of_group` returned its `{group: n}` dict keyed by `enumerate`'s own
POSITIONAL index into `source_polygon_id`, but its only consumer, `face_colors_by_group`, looks
`n_by_group` up by `g` -- the actual GROUP id (`source_polygon_id[i]`, a 2D-builder shape_id,
NOT a position). The two only happened to agree for a net where every shape_id coincidentally
equalled its own 0-based placement order (no deletions, authored in a single session, etc.) --
`hippo.hippo`/`cube.hippo`/`turtle.hippo`/`goose.hippo` all happened to satisfy that by luck,
which is why this session's own earlier "verified: zero mismatches" check on `hippo.hippo`
missed it entirely. `hoodie.hippo` (shape_ids 1/2/3, a folded square fanned into 4 triangles)
didn't, and showed a hexagon-shaped group colored as if it were a pentagon. This affected BOTH
Inflater mode's own `_apply_color_mode` and the new Viewer-mode rendering equally (both feed
through the exact same `face_colors_by_group` call) -- confirmed broken in Inflater mode too
once traced, not just Viewer.
- Fixed `polygon_n_of_group` to key its result by the group id itself (every `source_polygon_id`
  value already IS the group id `face_colors_by_group` wants -- no position bookkeeping needed
  at all: `{g: n_by_shape_id[g] for g in set(source_polygon_id) if g in n_by_shape_id}`).
- Also fixed a SEPARATE instance of the identical positional-vs-group-id confusion in
  `ViewerPane._viewer_show_current`/`_viewer_draw_level_panel`: Polygon-specific's own color was
  being looked up as `color_by_group[base_face]`, treating `base_face` (a plain position) as if
  it were a group id -- changed to use `face_colors_by_group`'s FIRST return value (`colors`,
  already a flat list correctly indexed by plain position) directly instead, sidestepping the
  group-id indirection entirely for this lookup.
- New tests catching this specific class of bug (a group id that doesn't match its own
  position) rather than letting each function's unit tests mock around it independently:
  `test_polygon_n_of_group_keyed_by_group_id_not_position`,
  `test_polygon_n_of_group_only_includes_groups_actually_present`, and a true end-to-end
  `test_polygon_n_of_group_and_face_colors_by_group_integrate_correctly` (feeds
  `polygon_n_of_group`'s own real output straight into `face_colors_by_group`, with a
  hoodie-shaped net whose shape_ids 1/2/3 deliberately don't match their own position).
Verified: all three of `hoodie.hippo`/`goose.hippo`/`spider_leg.hippo` (every shipped file with
a genuine Polygon-Fold group) now color correctly in BOTH Inflater and Viewer mode -- re-checked
against every `net_layout` entry's own `"n"` directly (not just internal self-consistency),
zero mismatches across all 6 test files' groups; rendered PyVista actor colors confirmed to
match the expected `POLYGON_COLORS` hex values exactly. Full suite green (same 4 pre-existing
unrelated failures).

Feature (2026-10-01, explicit: "let P, M, R be the keyboard shortcuts for Polygon-specific,
Multi-colour, and Randomize" -- both apps). `accelerator="P"`/`"M"`/`"R"` added to the Colour
menu's own three items (display-only, same convention as every other accelerator label here);
actual key handling via new `bind_all` calls, dispatching through a new `_on_color_mode_key(
mode)` helper (sets `color_mode_var` then calls the existing `_on_color_mode_changed` exactly as
the menu's own radiobutton click would -- same undo-push/Viewer-vs-Inflater dispatch, no
separate logic needed) for P/M, and straight to the existing Randomize handler for R.
- `inflate_polyhedron_app`: both cases bound for all three (`p`/`P`, `m`/`M`, `r`/`R`) -- no
  conflicts with anything already bound there.
- `interactive_inflater_app`: same, all three both-cased -- despite the base
  `InteractiveBuilderApp` binding plain "m" to Move-tool-mode, `BuilderPane`'s own `_build_ui`
  override (used here instead) never actually registers that binding at all -- this app has no
  separate Move/Join tool modes, just Edit (bound to "e") -- confirmed directly (`root.bind_all(
  "<KeyPress-m>")` returns empty before this change), so "m" was genuinely free, no Shift-only
  workaround needed.
Verified with synthetic `<KeyPress-...>` events (after `root.focus_force()` -- Tk requires real
window focus for `event_generate` to actually dispatch through `bind_all`, confirmed by a first
attempt without it silently not firing) in both apps: P/M/Shift+M correctly switch Colour mode;
R correctly re-rolls Multi-colour's own colors; "e" (Edit tool mode) in interactive_inflater_app
still works unaffected by the new "m"/"M" bindings. Full suite green (same 4 pre-existing
unrelated failures).

Bug fix + feature (2026-10-01, explicit: "in Viewer view, choose File > Save As should try to
save the currently loaded file, not the one in Inflater mode. Also Run All should be disabled in
this view", `inflate_polyhedron_app` only).
- File > "Save..." menu item's own `command` was `self.on_save_session_clicked` directly --
  always the Inflater-mode save dialog, regardless of which view was actually showing (unlike
  Ctrl+S, which already dispatched correctly via `_on_control_s`). Changed to
  `command=self._on_control_s` -- the exact same dispatch Ctrl+S already used, so the menu item
  and the shortcut now always agree.
- New `_update_run_menu_state` (disables Run > "Run All" whenever `view_mode_var` is "viewer",
  re-enables otherwise) -- called once right after the Run menu is built, and again from both
  branches of `_on_view_mode_changed` (entering/leaving Viewer mode). `on_run_all_clicked` itself
  also gained a `view_mode_var.get() == "viewer"` guard as defense in depth, alongside its
  existing `_run_all_active`/`_auto_active`/`not self.label_to_path` no-op checks.
Verified with an in-process smoke test: Run All's own menu entry is "normal" in Inflater mode,
"disabled" in Viewer mode, and back to "normal" on returning; `on_run_all_clicked` itself no-ops
while Viewer mode is showing even if called directly; File > Save...'s own command, triggered
while Viewer mode is active, saves the CURRENTLY VIEWED file (confirmed: the file's own dirty
flag clears) and never calls Inflater's own `on_save_session_clicked` at all. Full suite green
(same 4 pre-existing unrelated failures).

Bug fix (2026-10-01, reported crash: `KeyError: 6` from `_draw_target_faces` loading
`cannoli_open_tri` -- a `source_polygon_id`/net_layout shape_id space of `[1..6]`, not `[0..5]`).
Root cause: `_draw_target_faces` indexed `self.color_by_group[face_idx]` using `self.target_layout`'s
own keys, assuming they're always the SAME id space as whatever color mode is active. True for
Polygon-specific (`color_by_group` keyed by `source_polygon_id`, same as a saved net_layout's own
shape_id) and for the BFS-fallback target_layout (keyed by base-face position, same as
Polygon-specific's own `i`-fallback) -- but Multi-colour's `color_by_group` is ALWAYS keyed by
base-face POSITION (`_apply_color_mode`'s `"multi"` branch), which only coincidentally matches a
saved net_layout's shape_ids when they happen to equal `0..N-1` in file order. `color_mode_var`
defaults to `"multi"`, so this crashed on first load, not just after a manual mode switch.
Fix: `net_loading.target_layout_and_connections` now also returns `target_group_of_face` (a
`base_faces`-parallel list, same id space as `target_layout`'s own keys -- `source_polygon_id`
when a new-format net_layout was used, else base-face position); stored as `self.
target_group_of_face` alongside `target_layout`/`target_connections` at both call sites
(`on_select_net`, `on_load_session_clicked`). `_draw_target_faces` now rebuilds a
`target_color_by_group` fresh each draw from `target_group_of_face`/the flat, mode-agnostic
`self.colors` list, instead of indexing `self.color_by_group` (whose key space depends on the
active color mode) directly. `tests/unit/inflate_polyhedron_app/logic/test_net_loading.py`
updated for the new 3-tuple return + asserts on `target_group_of_face` itself. Verified: the
synthetic `[0,1]`-keyed `color_by_group[6]` crash reproduced and confirmed fixed by re-running
`cannoli_open_tri`'s own net-loading path standalone (`target_group_of_face == [1,2,3,4,5,6]`,
matching the file's own shape_ids, no KeyError building the per-draw color lookup); full suite
green (same 4 pre-existing unrelated failures).

Terminology rename (2026-10-01, explicit user request -- replacing the club/member/outsider/
insider/guest naming introduced 2026-09-28 with: anchor's connected component is now the ACTIVE
GROUP (was club); every shape in it is a REACHABLE NODE (was member); a reachable node with 0-1
connections is a TERMINAL NODE (was guest); a reachable node with >=2 connections is a JUNCTION
NODE (was insider); a shape not in the active group is an UNREACHABLE NODE (was outsider/
non-member). "owner"/"central node" was given as part of the new mapping too, but the codebase
never actually used "owner" as a term for the anchor (it's called "anchor" throughout, unrelated
to `camera_controller.py`'s own unrelated "OWNER" comment about object ownership) -- nothing
renamed for that half of the mapping. `interactive_inflater_app/logic/club_member_classifier.py`
renamed to `node_classifier.py` (`git mv`, preserving history); its test file renamed
`tests/unit/interactive_inflater_app/test_club_member_classifier.py` ->
`test_node_classifier.py`. Every prose mention (docstrings/comments), status-message string
("Insider added" -> "Junction node added", "Guest(s) added/deleted" -> "Terminal node(s)
added/deleted", "Outsider(s) added/deleted/modified" -> "Unreachable node(s)
added/deleted/modified", "Insider modified" -> "Junction node modified", the
"Placed directly: no insiders yet..." status), and identifier (`self._last_outsider_ids` ->
`self._last_unreachable_node_ids`, `current_outsider_ids` -> `current_unreachable_node_ids`,
`guest_word` -> `terminal_node_word`, the local `insiders` list in `plan_anchor_deletion` ->
`junction_nodes`) updated across `app.py` and every `logic/` module that referenced the old
terms (`edge_modifier.py`, `edge_selecter.py`, `flat_face_attacher.py`,
`inflation_type_chooser.py`, `coloring.py`). Direct quotes of the user's own PAST words (e.g.
"Guests are members with 0 or 1 connections", "if the user tries to delete the anchor and it
splits the club into two...") deliberately left verbatim inside quotation marks -- renaming
those would misrepresent what was actually said at the time; only the surrounding descriptive
prose was updated to the new terms. `apps.md`'s own `interactive_inflater_app` section ("Club
terminology" paragraph + the `logic/` file list) updated to match, since that section describes
CURRENT state, not a historical log.
