# Apps

4 Tkinter entry points. `src/apps/common/` (paths, ui_theme, bounding_box) + `src/apps/ui/`
(tooltip, cullable_face) hold code shared across >1 app — not domain logic.

`common/paths.py` is the only place computing cross-app locations (`STRETCHY_NETS_DIR`); an app
one level under `src/apps/` bootstraps `sys.path` via `import common.paths` before importing
`utils.*`.

## inflate_polyhedron_app (`src/apps/inflate_polyhedron_app/app.py`)
The solver viewer. See `physics.md` for the actual algorithm; this is UI wiring.

- **Net picker** (`on_select_net`) → runs a raw loaded net through `self_join_triangulator` first
  (splits any self-joined face -- see that module's own docstring; guards a hand-authored file
  that wasn't already expanded by `interactive_builder_app`'s own Save-time equivalent) → Level 0
  (random start, fan-triangulated). **Relax** → `relax_initial_configuration`
  to convergence → auto-promotes to Level 1 (no re-subdivide, same topology). **Inflate**
  recalibrates pressure FRESH every click (`on_inflate_clicked`, via `_run_background`) —
  pressure is never stored/reused across clicks; the calibration search's own starting guess comes
  from `_guess_pressure_from_history` (nearest-in-target prior level's own calibrated pressure when
  one exists, else `estimate_pressure_for_target_stretch`'s generic area-based guess — see
  physics.md's Pressure calibration section). There is no separate "real" inflate pass — the
  calibration search's own WINNING trial's already-computed result IS the Inflate outcome; that
  winning trial is also topped up to real convergence inside `estimate_pressure_for_target_stretch`
  itself if `max_nfev_per_trial` (a search-time budget, not a stopping criterion) cut it off first.
  `estimate_pressure_for_target_stretch(capture_frames=True)` captures the winning trial's own
  `(positions, cumulative_steps_taken)` every `CONVERGENCE_CHECK_INTERVAL` steps, and
  `_on_pressure_calibrated` replays those (`_start_frame_replay`/`_replay_step`/
  `_finish_frame_replay`) at `REPLAY_FPS`, advancing `REPLAY_FRAME_STRIDE` captured frames per
  tick (always landing exactly on the true final frame) once a pressure is found.
  `self.iteration_count` (the "Steps" column) advances during the ACTUAL computation, not replay:
  `estimate_pressure_for_target_stretch`'s own `on_progress` reports a running total across every
  trial attempted (never resets mid-search), bridged to the main thread via `_run_background`;
  `_on_pressure_calibrated` snaps both `iteration_count` and `self.last_stats` (hence Convergence/
  RMS/Max Stretch) to their true final values BEFORE replay starts, and neither changes again
  during replay — only `self.positions` (the 3D panel) keeps moving frame by frame.
  "RMS Stretch %" and "Pressure" both show "--" for the whole Computing phase, only revealed the
  instant the real result is known. Level 0's own row shows its actual RMS Stretch % same as every
  other level, and its own "Pressure" column shows `level0_jiggle_distance` — the fixed
  burst/jiggle displacement Level 0 actually uses (see physics.md), not a literal calibrated
  pressure, but the closest analogue that column has for "how strong was the burst" at Level 0.
  **Every level (0-3) shares ONE camera state** (rotation/zoom/pan): `self._level_camera_state` (a
  `{"rotation", "zoom", "pan"}` dict). `_level_camera(level)` returns it regardless of `level`
  (kept as a param purely for a uniform call shape); `_camera_group_levels(level)` likewise
  always returns every built level. `SessionStateModel`'s `level_*` fields hold the one shared
  state on save; `level0_*` fields are still WRITTEN (same values, file-format compat) but never
  read back on load.
  Each "Level 1"/"Level 2"/"Level 3" panel (Level 0 excluded) has its own bottom status-message
  Label (`self.level_message_labels`), left-anchored with a `padx` computed per-message from its
  own rendered text width (`_set_level_message`). Shows "Computing"/"Replaying" plus a shared
  0-3-dot cycle while each phase runs, clearing to "" once replay finishes or calibration is
  stopped. The panel's own IMAGE while Computing is a single flat background-color placeholder
  rendered once, not regenerated per dot-tick — `_render_level_pv` skips a level entirely while
  it's showing this. A Stop click during replay jumps straight to the final frame. Level 0's
  Relax is unchanged — it redraws live every progress tick, since there's only ever one run
  there to throw away.
  The steps-vs-convergence radio buttons (`self.iterate_mode_var`/`steps_var`) no longer affect
  Inflate at all (each calibration trial always runs to its own fixed `max_nfev_per_trial`) — left
  in place, inert; never affected Relax.
  **Subdivide** up to `MAX_LEVEL=3`, carries forward current (stretched) shape.
- **Stop**: `self.stop_event` is created and the frontier button turned into "Stop" BEFORE
  calibration starts (not just after), and forwarded into the calibration call itself, so Stop
  actually interrupts a calibration search in progress.
- **Auto**: one Relax/Inflate attempt per level (`_auto_attempted_level`), no retry-loop (see
  physics.md). Button reads "Run Simulation" idle / "Stop Simulation" while running
  (`_update_auto_button`).
- **Measured-value display precision**: RMS Stretch % (measured, not the "(target: ...)" spinner
  value) is `.1f`, Pressure is `.2f`, Max Stretch % (a different metric) stays `.2f`.
- **Convergence History table**: one row/level. "Convergence" cell shows `optimality op gtol
  mark` — a generic display that doesn't hardcode what `optimality` measures (currently
  displacement, see physics.md). Release-mode columns: "Max Stretch %" is debug-only;
  "Simulation Time"/"Cumulative Time" show in both modes. "--" (not "n/a") for Level 0's own
  pressure (the only level whose pressure is ever `None`) and for any unset `mm:ss` time. Level
  1+ shows Precomp alone (no separate "sim" phase — pressure calibration's winning trial IS the
  result); Level 0 shows Sim alone. `LevelHistoryRecordModel` persists `precomp_time_s`/
  `sim_time_s` so a loaded session still shows Simulation Time.
  Row coloring is 3-state: `self._level_running` makes the CURRENT frontier level's row
  `"running"` (a dedicated bright `RUNNING_ROW_COLOR`) instead of `"not_converged"` (red) while
  a run is actively in progress — red is reserved for an ACTUAL failure (step cap or Stop), never
  just "still going". `running_now` also requires `rec["optimality"] is None` (not just
  `self._level_running` — which stays `True` through the purely-visual replay after a real
  result is already known), so a row turns green the moment `optimality` is real. The
  Convergence CELL TEXT shows `"--"` whenever `optimality is None`, covering both "never run" and
  "actively computing".
- **3D panels**: PyVista off-screen render blitted into a Tk Label per level (`pv.Plotter(
  off_screen=True)` + `PIL.ImageTk`) — needed because meshes here are routinely non-convex/
  self-intersecting mid-relax, which plain mplot3d/backface-culling can't draw correctly. One
  shared camera angle across all "Level N" panels (drag any → all rotate together). "Net" panel
  (flat undeformed layout) is still matplotlib, own independent zoom, drawn on `fig_net.
  add_axes([0, 0, 1, 1])` rather than `add_subplot` — `_draw_target_faces` pre-stretches its own
  `half_range` to the panel's own aspect ratio before `set_xlim`/`set_ylim` so `set_aspect(
  "equal")` never has anything left to shrink.
  If the loaded net has `net_layout` (saved by `interactive_builder_app`), the Net panel shows
  that EXACT flat arrangement (with a Y-flip: Tk canvas Y-down vs matplotlib Y-up) instead of a
  fresh BFS spanning-tree layout, plus `builder_connections`' own bezier curves
  (`_connection_curve_points`/`_placed_edge_frame`) drawn solid white on top — same curve
  `interactive_builder_app` shows, but never its handles (this panel is read-only). No fine-mesh
  subdivision overlay — just the plain base faces + connection curves.
- **Coloring/grouping by `source_polygon_id`** (Polygon Fold, see `interactive_builder_app`'s own
  section): `self.colors` (flat, per-base-face-index) is built by `_face_colors_by_group`, keyed
  by `source_polygon_id[i]` when the loaded file has one, else `i` itself (unchanged behavior for
  any file without it) — every base face sharing a source polygon gets the SAME color.
  `self.color_by_group`/`self.group_of_base_face` are the same grouping keyed by group id instead
  of face index, for `_draw_level_panel`'s per-group `add_mesh` grouping (below, grouped by this
  instead of raw `face_of_fine`) and `_draw_target_faces`'s per-entry color lookup
  (`self.target_layout`'s own keys ARE group ids). `_net_layout_is_new_format` gates whether a
  `net_layout` needs the old face-count-match check (legacy) or is trusted unconditionally (new,
  shape-id-keyed, can legitimately have fewer entries than `"faces"` once a fold exists).
- **"Level N" panel wireframe edge color**: PER-BASE-FACE (halfway between white and the polygon
  color), not one fixed `PLOT_THEME["fg"]` for every edge. `_draw_level_panel` does one
  `add_mesh` call per base-face GROUP (see above) rather than one call for the whole mesh, since
  VTK's `edge_color` is a single uniform color per call; still one scene/depth buffer, so
  cross-group occlusion works the same as a single-call version would.
- **Pan/zoom**: right-click-drag pans. Level panels share ONE pan (`self.level_pan`, a 2D NDC
  offset applied via `vtkCamera.SetWindowCenter` — a pure post-projection viewport shift, not
  added to focal_point/position, which would otherwise desync panels of different scale and move
  the camera's own orbit center). `_level_half` is a proper bounding-SPHERE radius
  (`norm(points - center, axis=1).max()`). `_level_zoom_fill(level)` is each panel's own default
  fill fraction at zoom=1.0 (`LEVEL_ZOOM_FILL_LEVEL_0=0.9`, `_LEVELS_1_3=0.90`) — the sole
  authoritative fill fraction. Each level auto-fits its own current bounding box (its per-level
  target RMS % tapers down, so the converged mesh's absolute size genuinely shrinks level to
  level — a fixed camera would just display that as "inconsistent sizes"); rotation/pan/zoom stay
  shared across Levels 1-3 regardless. Middle-click resets pan, zoom, and (level panels only)
  rotation together, back to `_initial_level_rotation()`. `level_zoom` clamps to 30%..400%;
  `net_zoom` to 30%..800% (its own bounding box can be much larger relative to its faces than any
  "Level N" panel's ever is, since a bezier connection can sweep well past its two faces' extent).
- **Setup row**: "Choose a net" combo; net/target-RMS/tolerance/auto groups. Each
  `target_rms_vars[level]`/`self.tolerance_spin` is a plain `ttk.Entry` (not a Spinbox, whose
  up/down arrows never gated free typing anyway) — `_register_numeric_entry`/
  `_is_valid_numeric_partial` reject a keystroke outright if it wouldn't leave a
  number-or-prefix-of-one behind (tolerance's own entry additionally allows an exponent, e.g.
  "1e-03"). Target RMS clamps into [0, 100] on commit; `_get_tolerance` falls back to
  `DEFAULT_TOLERANCE` for anything unparseable. `target_rms_vars[level]` rounds to the nearest
  whole number on commit and is bound to a SEPARATE `self.target_rms_display_vars[level]`
  StringVar — shows "N%" while unfocused, the bare number while being edited.
- **Level panel action buttons**: natural text width, debug-mode-only — `_auto_step` drives
  Relax/Inflate/Subdivide by calling the click handlers directly, never `button.invoke()`, so
  hiding them doesn't affect Auto.
- **Debug mode** ("d" key): adds steps-vs-convergence radio (inert for Inflate) and three arrow
  toggles for checking whether the CURRENT shape faces outward: **Show face normals** (one per
  face, from its centroid), **Show vertex normals** (one per vertex, averaged from its touching
  faces — catches a disagreement a per-face check alone can miss), and **Show repulsive forces**
  (Level 0's own per-vertex repulsion force, see physics.md's Force model section — magnitude-
  scaled against the max among drawn vertices, not unit-length, so a weakened/zeroed force is
  visibly shorter/absent). Release mode and debug mode are otherwise IDENTICAL.
- **No caching, no chunking**: solve starts fresh each session; UI progress synced to
  `on_progress` callback fired by the solver itself every `CONVERGENCE_CHECK_INTERVAL` steps
  (see physics.md) — not an app-side chunk schedule.
- **File > Save/Load session** (`session_state.py`'s `SessionStateModel`) carries the camera view —
  `level_zoom`/`level_pan`/`level_rotation` (every level's shared camera) and `net_zoom`/`net_pan`.
  `level_rotation` is a scipy `Rotation`'s `.as_quat()` (JSON has no quaternion type) — `None`
  falls back to `_initial_level_rotation()` on load. `net_file` (the raw parsed net JSON, embedded
  wholesale) already carries `interactive_builder_app`'s own bezier connection data through
  save/load for free.
- **Session file extension is `.hippo`** (`SESSION_FILE_EXTENSION`), not `.json` — content is
  unchanged (still `SessionStateModel.model_dump_json()`); File > Load's dialog still ALSO accepts
  plain `*.json` so a session saved before this change still opens.
- **Window title is `APP_TITLE`** — "HIPPO — Hierarchical Inflatable Phabric Polyhedron
  Optimizer", a backronym named AFTER `.hippo` (the session extension); " (debug mode)" appended
  in debug mode.
- **Reads `*.poly` net files too, alongside `*.json`** (`refresh_net_list`, matching
  `interactive_builder_app`'s own save extension): both globbed and merged under
  `data/input/stretchy_nets/` (content, not extension, is all `load_stretchy_mesh` ever cared
  about). A `.json` and `.poly` sharing the same basename collide in the combo's own label→path
  map (second one wins).
- **View > Inflater/Viewer** (2026-09-30, explicit — originally built as its own standalone app,
  then explicitly folded in here instead: "instead of a whole separate app, make it just a view
  in the polyhedron_inflater app"): a radiobutton pair (`self.view_mode_var`) toggling which of
  two top-level frames is packed — `self._inflater_frame` (everything above, unchanged) or
  `self._viewer_frame` (a read-only photo-viewer-style browser for `data/output/*.hippo`
  sessions, every method/attribute prefixed `_viewer_` to keep its state completely separate
  from Inflater mode's own).
  - **Viewer mode's window is SQUARE** (`VIEWER_WINDOW_GEOMETRY`, 2026-09-30, explicit) --
    `_on_view_mode_changed` captures Inflater's own current geometry (`self._inflater_geometry`,
    whatever it actually was, including a manual resize) before switching away, resizes to
    `VIEWER_WINDOW_GEOMETRY` for Viewer, and restores the captured one on the way back.
  - Viewer mode **rescans `SESSION_OUTPUT_DIR` fresh every time it's entered** (`_viewer_rescan`,
    called from `_on_view_mode_changed`), not just once at startup — a `.hippo` file saved
    earlier in the SAME session (File > Save, or Run All) shows up immediately, without losing
    any already-cached session/camera state for files already viewed.
  - **Shows all 4 levels AT ONCE, in a 2x2 grid, synced to ONE shared camera** (2026-09-30,
    explicit — "let's split the drawing area into 2x2 and show all 4 views, synced", no more
    Level buttons/switching) — each quadrant is its own small PyVista plotter
    (`self._viewer_plotters[level]`, `VIEWER_SUBPANEL_SIZE`) auto-fitting its OWN current
    bounding box (`self._viewer_centers`/`_halves`, same per-level-auto-fit idea as Inflater's
    own "Level N" panels), but every quadrant reads the SAME per-file camera
    (`self._viewer_cameras[path]`) — `_viewer_draw_level_panel` builds one quadrant's mesh
    scene (called once per file, on navigation), `_viewer_render_all`/
    `_viewer_render_level_camera` reposition+blit all 4 (called on every drag/pan/zoom tick).
    A level the file never reached draws as a blank quadrant.
  - **No on-screen Prev/Next arrows, no status label at all** (2026-09-30, explicit — tried as
    overlaid anti-aliased filled triangles first, then explicitly removed along with the
    file-name status message: "get rid of the on-screen arrows. remove the file name
    message"). Navigation is keyboard-only: Left/Right arrow, or A/D (`_on_key_d` dispatches
    "d"/"D" by `view_mode_var` — lowercase "d" is ALSO Inflater mode's own debug-mode toggle,
    so it only navigates in Viewer mode; "a"/"A"/"D" have no such collision and bind directly).
    The window title already shows the current file's own name, so no separate message repeats
    it; a save's own confirmation is just the title's "*" disappearing.
  - **Each quadrant's own drawing area has a visible flat outline**
    (`VIEWER_OUTLINE_COLOR`/`_WIDTH`, via the image Label's own
    `highlightthickness`/`highlightbackground` — a plain border, not `relief`'s 3D bevel look).
  - **A small margin strip directly below the 2x2 grid holds the "m / n" file-position
    counter** (2026-09-30, explicit) — the only thing left in that strip now that the
    status label is gone.
  - Mouse on ANY quadrant (left-drag rotate / right-drag pan / scroll zoom / middle-click
    reset) reuses the exact same math/constants as the "Level N" panels above
    (`LEVEL_DRAG_SENSITIVITY`/`LEVEL_ZOOM_STEP`/`_MIN`/`_MAX`/`LEVEL_ZOOM_FILL_LEVELS_1_3`/
    `_initial_level_rotation`), updating the one shared camera and re-rendering all 4 quadrants
    together. Only edits each file's own shared camera (`level_rotation`/`level_zoom`/
    `level_pan`, via the SAME `SessionStateModel` this app already uses) — never the mesh data.
  - **No explicit Save button** (2026-09-30, explicit — removed): saving now only happens via
    a single prompt covering every dirty file at once, triggered by EITHER quitting the whole
    app OR switching back to View > Inflater (`_on_view_mode_changed`'s own "inflater" branch
    calls `_viewer_confirm_discard_unsaved` BEFORE actually switching; cancelling reverts
    `view_mode_var` back to "viewer" and leaves Viewer mode untouched) — same
    `_viewer_confirm_discard_unsaved`/askyesnocancel helper `_on_quit_request` uses, covering
    every file touched this session, not just whichever is on screen (pattern established by
    `interactive_builder_app`'s own `_on_quit_request`). Ctrl+S (`_on_control_s`) still saves
    the CURRENT file on demand, unaffected by the button's removal — only the explicit button
    was asked to go.
  - Window title while active is `"<filename>[* if dirty] -- HIPPO Viewer"`
    (`_update_viewer_title`, dispatched from `_update_window_title`) — a completely different
    scheme from Inflater mode's own `APP_TITLE`.
  - Coloring is by `face_of_fine` (the ORIGINAL base-face index) alone, not
    `source_polygon_id`-aware grouping (`_face_colors_by_group`) — a deliberate simplification,
    since a saved/finished mesh never needs to represent an in-progress Polygon Fold.

## interactive_inflater_app (`src/apps/interactive_inflater_app/app.py`)
Combines `interactive_builder_app`'s canvas (left) with a simplified one-panel solver viewer
(right) — build a net by hand and inflate it immediately, no save/load round trip.

**Club terminology**: the anchor's own connected component is the **club**; every shape in it is
a **member**; a member with 0 or 1 connections is a **guest** (0 = the first piece ever placed,
nothing to connect to yet; flat-attached or just placed, never touches relax/inflate); a member
with ≥2 connections is an **insider** (inflation only ever involves insiders); a shape not
connected to the anchor at all is an **outsider**. `self.is_fully_inflated` tracks whether the
insiders currently reflect a real relax/inflate result.
Rules: (1) inflation only involves insiders, guests are attached flatly; (2) `is_fully_inflated`
resets to False whenever the club empties, set True after a real Full Inflate; (3) a change to
insiders (membership or their internal connections) triggers Diff Inflate if `is_fully_inflated`
else Full Inflate; (4) undo/redo fall under the same rules for free, via the same `on_change` hook
every edit funnels through. Status messages always say which pipeline (Full/Diff Inflate) and
level is running (`_pipeline_label`), including when Diff Inflate redirects into a real Full
Inflate because the insiders were never really solved yet.

## interactive_builder_app (`src/apps/interactive_builder_app/app.py`)
Unrelated 2D shape-placement canvas, no relation to solving. Palette of regular polygons
(triangle..8-gon) → click to drop instances → drag/select/delete/rotate(right-drag)/pan
(right-drag on empty). Click a handle then another shape's handle to connect them (click-click,
not drag). Every corner shown as `(shape_id, corner_index)`, not a shared vertex-id — that
identity is only computed at Save (union-find over connections), never live (a transitively-
implied merge would otherwise block an unrelated, individually-correct connection).

Only two toolbar modes: **Move** and **Join**. Join's click-click edge-handle gesture handles
both an ordinary cross-shape connection AND a "Polygon Fold" (completing onto a second edge of
the SAME shape, modeling a polygon folded onto itself, e.g. a pinched leg) — there is no separate
Polygon Fold mode/button.

Every connection is a cubic bezier, not a line segment — two adjustable control points, one per
end, stored as `{"t","n"}` world-length offsets along that END'S OWN edge frame (tangent/outward-
normal, `_shape_edge_frame`), not an absolute point or an offset from the other end, so a handle
tracks its own shape's move/rotate for free, no update step needed. Fresh connection defaults to
dead straight (`_default_connection_handles` — colinear thirds). Handles only ever drawn/
clickable (thin red line + filled red dot, `_draw_bezier_handles`/`_hit_test_bezier_handle`) for
the ONE currently-selected connection, which only happens in Join mode — dragging one is a single
undo step, connection stays selected throughout.

**File > Save** writes the stretchy vertex-loop JSON format (as `.poly`, `NET_FILE_EXTENSION` —
still plain JSON content, and File > Load still ALSO accepts plain `.json`) + this app's own
`net_layout`/`builder_connections`/`view` extension fields — any other reader (incl. the solver)
ignores the extra keys except `source_polygon_id` (below), which `inflate_polyhedron_app` reads
for coloring. Validation (self-loop / duplicate-directed-edge) runs ONLY at Save, never live
while editing — an edge can only be joined once (enforced live), but transitive vertex identity is
only finalized at export. **File > Load** replays `net_layout` exactly if present; otherwise
BFS-spanning-tree-lays-out fresh (same algorithm as
`stretchy_net_layout.build_stretchy_net_layout`, reimplemented locally with a gap parameter that
function doesn't have).

**Polygon Fold export**: a flat n-gon can't literally glue two of its own edges together (a face
with a repeated vertex) — `_expand_folded_shapes` resolves this at Save/live-validation time by
triangulating any shape with ≥1 such connection into `n` triangles fanned from a fresh centroid
vertex (same winding as `mesh_levels._fan_level_0_to_1`'s own Level 0→1 fan), rewriting every
connection touching that shape's edge `i` onto triangle `i`'s own outer edge, and adding the `n`
spoke connections gluing the fan together — the existing
`_validate_shapes_connections`/`_faces_from_shapes`/`_edges_from_shapes`/`_face_edge_ids_from_shapes`
need NO changes, only feeding them this expanded form instead of the raw shapes. In the app
itself, a folded shape's `n` triangles are never individually selectable/movable/deletable and
their internal spoke edges are never exposed at all — purely a Save-time (and
`_refresh_vme_state`-time) transformation.

Since a folded shape's triangles no longer align 1:1 with placed shapes, `net_layout`/
`builder_connections` are keyed by each shape's own stable id (`"shape_id"`/`"a_shape_id"`/
`"b_shape_id"`, plus `"n"` on each `net_layout` entry so a reader can reconstruct the original
polygon's outline without stitching triangles back together) instead of by position/index into
`"faces"` — a `net_layout` entry with no `"shape_id"` is legacy, index-aligned data (any file saved
before this format), handled as a fully separate branch in `_load_faces`/`inflate_polyhedron_app`'s
`_layout_from_net_layout` (`_net_layout_is_new_format`). A `"source_polygon_id"` list, parallel to
`"faces"`, names the original placed shape each exported face came from (identical for every
triangle of one fan) — a pure downstream display aid, never read by `stretchy_mesh.py`/
`mesh_levels.py`.

## polygon_subdivision_app (`src/apps/polygon_subdivision_app/app.py`)
Unrelated 2D-only demo: splits a regular n-gon into a fine triangular mesh, preview only, no
solving. Two-stage hardcoded/closed-form split (`utils/subdivisions/`): coarse centroid-fan
(`SUBDIVISIONS`) then barycentric refinement (`_subdivide_triangle`). Uses
`FABRIC_APP_RESOLUTION=3` (matches what the real stretchy pipeline solves over), not the
generic `DEFAULT_RESOLUTION=10`.
