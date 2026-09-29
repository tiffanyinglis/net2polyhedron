# Apps

3 Tkinter entry points. `src/apps/common/` (paths, ui_theme, bounding_box) + `src/apps/ui/`
(tooltip, cullable_face) hold code shared across >1 app — not domain logic.

`common/paths.py` is the only place computing cross-app locations (`STRETCHY_NETS_DIR`); an app
one level under `src/apps/` bootstraps `sys.path` via `import common.paths` before importing
`utils.*`.

## inflate_polyhedron_app (`src/apps/inflate_polyhedron_app/app.py`)
The solver viewer. See `physics.md` for the actual algorithm; this is UI wiring.

- **Net picker** → Level 0 (random start, fan-triangulated). **Relax** → `relax_initial_configuration`
  to convergence → auto-promotes to Level 1 (no re-subdivide, same topology). **Inflate**
  recalibrates pressure FRESH every click (`on_inflate_clicked`, via `_run_background`) —
  pressure is never stored/reused across clicks; the calibration search's own starting guess comes
  from `_guess_pressure_from_history` (nearest-in-target prior level's own calibrated pressure when
  one exists, else `estimate_pressure_for_target_stretch`'s generic area-based guess — see
  physics.md's Pressure calibration section). There is no separate "real" inflate pass — the
  calibration search's own WINNING trial's already-computed result IS the Inflate outcome (no
  duplicated `relax_once` re-run at the found pressure); that winning trial is also topped up to
  real convergence inside `estimate_pressure_for_target_stretch` itself if `max_nfev_per_trial`
  (a search-time budget, not a stopping criterion) cut it off first, so "Precomp" time already
  includes any such continuation.
  `estimate_pressure_for_target_stretch(capture_frames=True)` captures the winning trial's own
  `(positions, cumulative_steps_taken)` every `CONVERGENCE_CHECK_INTERVAL` steps, and
  `_on_pressure_calibrated` replays those (`_start_frame_replay`/`_replay_step`/
  `_finish_frame_replay`) at `REPLAY_FPS`, advancing `REPLAY_FRAME_STRIDE` captured frames per
  tick (always landing exactly on the true final frame) once a pressure is found.
  `self.iteration_count` (the "Steps" column) advances during the ACTUAL computation, not replay:
  `estimate_pressure_for_target_stretch`'s own `on_progress` reports a running total across every
  trial attempted (never resets mid-search, so the counter never appears to go backwards), bridged
  to the main thread via `_run_background`; `_on_pressure_calibrated` snaps both `iteration_count`
  and `self.last_stats` (hence Convergence/RMS/Max Stretch) to their true final values the instant
  the real result comes back, BEFORE replay starts, and neither changes again during replay —
  only `self.positions` (the 3D panel) keeps moving frame by frame.
  **"RMS Stretch %" and "Pressure" both show "--" for the whole Computing phase**, only revealed
  the instant the real result is known: `on_inflate_clicked` snapshots `self.last_stats`/
  `self.pressure_value` and blanks them to `None` at the start of a click (restored verbatim if
  Stopped); `_record_level_history` doesn't default `rms_stretch_pct` to `0.0` the way it does
  `max_stretch_pct`, so `None` survives into `level_history` for `_refresh_history_table` to show
  as `"--"`. The "(target: N.N)" suffix is debug-mode-only. Level 0's own row shows its actual RMS
  Stretch % same as every other level (2026-09-28, explicit user request; previously always "--"
  there), and its own "Pressure" column shows `level0_jiggle_distance` -- the fixed burst/jiggle
  displacement Level 0 actually uses (see physics.md), not a literal calibrated pressure, but the
  closest analogue that column has for "how strong was the burst" at Level 0.
  **Every level (0-3) shares ONE camera state** (rotation/zoom/pan, 2026-09-28, explicit user
  request — was previously split, Level 0 independent from Levels 1-3, since an early
  random-start Level 0 looked very different from a settled solid; reverted since dragging one
  panel now rotates/pans/zooms all of them together): `self._level_camera_state` (a
  `{"rotation", "zoom", "pan"}` dict). `_level_camera(level)` returns it regardless of `level`
  (kept as a param purely for a uniform call shape); `_camera_group_levels(level)` likewise
  always returns every built level now. `SessionStateModel`'s `level_*` fields hold the one
  shared state on save; `level0_*` fields are still WRITTEN (same values, for file-format/
  backward-compat reasons) but never read back on load.
  Each "Level 1"/"Level 2"/"Level 3" panel (Level 0 excluded) has its own bottom status-message
  Label (`self.level_message_labels`), left-anchored with a `padx` computed per-message from its
  own rendered text width (`_set_level_message`, via a real `tkfont.Font`) rather than one fixed
  pad, since a pad tuned for one message length reads off-center for another. Shows "Computing"/
  "Replaying" plus a shared 0-3-dot cycle (`_tick_computing_animation`/`_replay_step`, the latter's
  dot count derived from wall-clock time) while each phase runs, clearing to "" once replay
  finishes or calibration is stopped. The panel's own IMAGE while Computing is a single flat
  background-color placeholder rendered once, not regenerated per dot-tick — `_render_level_pv`
  skips a level entirely while it's showing this, so a drag-rotate/resize can't paint over it. A
  Stop click during replay jumps straight to the final frame. Level 0's Relax is unchanged — it
  redraws live every progress tick, since there's only ever one run there to throw away.
  The steps-vs-convergence radio buttons (`self.iterate_mode_var`/`steps_var`) no longer affect
  Inflate at all (each calibration trial always runs to its own fixed `max_nfev_per_trial`) — left
  in place, inert, pending a decision on whether to repurpose or drop them; never affected Relax.
  **Subdivide** up to `MAX_LEVEL=3`, carries forward current (stretched) shape.
- **Stop**: `self.stop_event` is created and the frontier button turned into "Stop" BEFORE
  calibration starts (not just after), and forwarded into the calibration call itself, so Stop
  actually interrupts a calibration search in progress.
- **Auto**: one Relax/Inflate attempt per level (`_auto_attempted_level`), no retry-loop (see
  physics.md). Button reads "Run Simulation" idle / "Stop Simulation" while running
  (`_update_auto_button`).
- **Measured-value display precision**: RMS Stretch % (measured, not the "(target: ...)" spinner
  value) is `.1f`, Pressure is `.2f`, Max Stretch % (a different metric) stays `.2f` — every
  history table cell and status message uses these, formatted straight from the stored/loaded
  float either way.
- **Convergence History table**: one row/level. "Convergence" cell shows `optimality op gtol
  mark` — a generic display that doesn't hardcode what `optimality` measures (currently
  displacement, see physics.md). Release-mode columns: "Max Stretch %" is debug-only;
  "Simulation Time"/"Cumulative Time" show in both modes. "--" (not "n/a") for Level 0's own
  pressure (the only level whose pressure is ever `None`) and for any unset `mm:ss` time. Level
  1+ shows Precomp alone (no separate "sim" phase — pressure calibration's winning trial IS the
  result); Level 0 shows Sim alone. `LevelHistoryRecordModel` persists `precomp_time_s`/
  `sim_time_s` so a loaded session still shows Simulation Time.
  Row coloring is 3-state: `self._level_running` makes the CURRENT frontier level's row
  `"running"` (a dedicated bright `RUNNING_ROW_COLOR`, not the muddier `STATUS_COLORS["warn"]`)
  instead of `"not_converged"` (red) while a run is actively in progress — red is reserved for an
  ACTUAL failure (step cap or Stop), never just "still going". `running_now` also requires
  `rec["optimality"] is None` (not just `self._level_running` — which stays `True` through the
  purely-visual replay after a real result is already known), so a row turns green the moment
  `optimality` is real rather than staying yellow through the whole replay animation. The
  Convergence CELL TEXT shows `"--"` (not `"n/a"`) whenever `optimality is None`, covering both
  "never run" and "actively computing". Level 0's own Convergence column also shows "--" for the
  whole time Relax is running (`_apply_relax_progress` stashes the real value in
  `self._pending_relax_stats` until `_finish_relax` reveals it) — `max_stretch_pct`/
  `rms_stretch_pct` are unaffected, updating live throughout. Exactly three row colors exist
  (`converged`/`not_converged`/`running`, each with its own `tag_configure`) — no other
  combination is reachable.
- **3D panels**: PyVista off-screen render blitted into a Tk Label per level (`pv.Plotter(
  off_screen=True)` + `PIL.ImageTk`) — needed because meshes here are routinely non-convex/
  self-intersecting mid-relax, which plain mplot3d/backface-culling can't draw correctly. One
  shared camera angle across all "Level N" panels (drag any → all rotate together). "Net" panel
  (flat undeformed layout) is still matplotlib, own independent zoom, drawn on `fig_net.
  add_axes([0, 0, 1, 1])` rather than `add_subplot` (whose default margins waste space
  `_style_2d_axis`'s `set_axis_off()` never uses) — `_draw_target_faces` pre-stretches its own
  `half_range` to the panel's own aspect ratio before `set_xlim`/`set_ylim` so `set_aspect(
  "equal")` never has anything left to shrink, the same idea `_render_level_pv`'s own
  `camera.parallel_scale` term uses for the "Level N" panels.
  If the loaded net has `net_layout` (saved by `interactive_builder_app`), the Net panel shows
  that EXACT flat arrangement (with a Y-flip: Tk canvas Y-down vs matplotlib Y-up) instead of a
  fresh BFS spanning-tree layout, plus `builder_connections`' own bezier curves
  (`_connection_curve_points`/`_placed_edge_frame`) drawn solid white on top — same curve
  `interactive_builder_app` shows, but never its handles (this panel is read-only). No fine-mesh
  subdivision overlay — just the plain base faces + connection curves.
- **Coloring/grouping by `source_polygon_id`** (Polygon Fold, see `interactive_builder_app`'s own
  section): `self.colors` (flat, per-base-face-index, as before) is built by
  `_face_colors_by_group`, keyed by `source_polygon_id[i]` when the loaded file has one, else `i`
  itself (unchanged behavior for any file without it) — every base face sharing a source polygon
  gets the SAME color. `self.color_by_group`/`self.group_of_base_face` are the same grouping keyed
  by group id instead of face index, for `_draw_level_panel`'s per-group `add_mesh` grouping
  (below, grouped by this instead of raw `face_of_fine`) and `_draw_target_faces`'s per-entry color
  lookup (`self.target_layout`'s own keys ARE group ids — see `_layout_from_net_layout`'s
  shape-id-keyed format). `_net_layout_is_new_format` gates whether a `net_layout` needs the old
  face-count-match check (legacy) or is trusted unconditionally (new, shape-id-keyed, can
  legitimately have fewer entries than `"faces"` once a fold exists).
- **"Level N" panel wireframe edge color**: PER-BASE-FACE (the color halfway between white and the
  polygon color), not one fixed `PLOT_THEME["fg"]` for every edge. `_draw_level_panel` does one
  `add_mesh` call per base-face GROUP (see above) rather than one call for the whole mesh, since
  VTK's `edge_color` is a single uniform color per call; still one scene/depth buffer, so
  cross-group occlusion works the same as a single-call version would. `_midpoint_color(a, b)` is
  the plain RGB average of two matplotlib-recognized colors.
- **Pan/zoom**: right-click-drag pans. Level panels share ONE pan (`self.level_pan`, a 2D NDC
  offset applied via `vtkCamera.SetWindowCenter` — a pure post-projection viewport shift, not
  added to focal_point/position, which would otherwise desync panels of different scale and move
  the camera's own orbit center). `_level_half` is a proper bounding-SPHERE radius
  (`norm(points - center, axis=1).max()`, bounding the shape from every viewing angle) — an
  earlier half-of-largest-world-axis-extent version underestimated a shape's true on-screen extent
  from an oblique angle. `_level_zoom_fill(level)` is each panel's own default fill fraction at
  zoom=1.0 (`LEVEL_ZOOM_FILL_LEVEL_0=0.5`, `_LEVELS_1_3=0.90` — Level 0's spread-out random start
  needs more headroom than Levels 1-3's settled solid) — the sole authoritative fill fraction (a
  now-removed second "margin" constant, `WIREFRAME_VIEW_FILL`, used to compound with it into
  >90% and clip the panel edge).
  A fixed reference framing shared across Levels 1-3 (derived from Level 1's own converged state)
  was tried and reverted the same day it shipped: it made camera framing bit-for-bit identical
  across levels, but this app's own per-level target RMS % tapers down, so the converged mesh's
  absolute size genuinely shrinks level to level — a literally fixed camera then just displays
  that real shrinkage, reading as "inconsistent sizes" rather than the consistent LOOK wanted.
  Reverted to each level auto-fitting its own current bounding box; rotation/pan/zoom stay shared
  across Levels 1-3 regardless (a separate, still-current mechanism, above).
  "Level N" panels are ALL the same width (2026-09-28, explicit user request — Level 0's used to
  be 60% of Levels 1-3's own width; `LEVEL_PANEL_WIDTH_LEVEL_0`/`_LEVELS_1_3`,
  `_level_panel_size(level)` returns the right pair; height unchanged for every panel; kept as a
  per-level lookup rather than a bare constant in case of a future re-split). The Net panel keeps
  its own separate, unchanged
  `NET_PANEL_SIZE`. `self.net_pan` is the Net panel's own 2D data-space offset — its y-sign is
  OPPOSITE x's (Tk pixels grow downward, this axes' data y grows upward). Middle-click resets pan,
  zoom, and (level panels only) rotation together, back to `_initial_level_rotation()` (the
  deliberately non-axis-aligned default view, not identity). `level_zoom` clamps to 30%..400%;
  `net_zoom` to 30%..800% (its own bounding box can be much larger relative to its faces than any
  "Level N" panel's ever is, since a bezier connection can sweep well past its two faces' extent).
- **Setup row**: "Choose a net" combo width halved; wide gaps between net/target-RMS/tolerance/auto
  groups; each `target_rms_vars[level]`/`self.tolerance_spin` is a plain `ttk.Entry` (not a
  Spinbox, whose up/down arrows never gated free typing anyway) — `_register_numeric_entry`/
  `_is_valid_numeric_partial` reject a keystroke outright if it wouldn't leave a
  number-or-prefix-of-one behind (tolerance's own entry additionally allows an exponent, e.g.
  "1e-03"). Target RMS also clamps into [0, 100] on commit (truncated to the nearest extreme, not
  rejected); `_get_tolerance` falls back to `DEFAULT_TOLERANCE` for anything unparseable.
- **Target RMS entries, "%" suffix + whole numbers**: `target_rms_vars[level]` (a plain float,
  read everywhere else unchanged) rounds to the nearest whole number on commit. The entry is bound
  to a SEPARATE `self.target_rms_display_vars[level]` StringVar — shows "N%" while unfocused
  (`_sync_target_rms_display`, a trace on the raw var, so it stays correct after a change from
  elsewhere too) and the bare number while being edited.
- **Level panel action buttons**: natural text width (not a full-width bar), debug-mode-only
  (`_apply_mode_visibility` packs/`pack_forget`s them) — `_auto_step` drives Relax/Inflate/
  Subdivide by calling the click handlers directly, never `button.invoke()`, so hiding them
  doesn't affect Auto.
- **Window height re-fits per mode** (`_refit_window_height`): `root.geometry()` reset to
  `winfo_reqheight()` on every genuine mode change (init, debug toggle, session load) — never on a
  plain net switch, which would otherwise fight a manual window resize.
- **Status text**: `self.status_frame` (the warning/error/progress row) is debug-mode-only.
- **No loading spinner**: the running-state text ("Computing...", "Replaying...", live Steps/Time
  columns) already conveys "something is happening" without one.
- **Uniform font, matched to "Choose a net"**: `self.LEVEL_TITLE_FONT`/`LEVEL_MESSAGE_FONT` and the
  File menu's own font are all computed once (`_init_ui_fonts`) from
  `tkfont.nametofont("SunValleyBodyFont").actual()` — the same named font sv_ttk routes a plain
  `ttk.Label` through, so they now genuinely match its real rendered family/size. Replaces a
  `("TkDefaultFont", ...)` tuple that was a real bug, not just a mismatch: passing a named font's
  NAME as a plain tuple's family silently falls back to Arial in Tk.
- **Window width**: `window_width` is computed from the actual panel widths + padding, not a
  hardcoded literal (every row here packs flush LEFT, so a too-big literal leaves an uneven blank
  margin on the right).
- **Net panel bounding box** (`_draw_target_faces`) includes every connection curve's own sampled
  points, not just polygon vertices — a bezier bulging past its two faces' combined extent would
  otherwise get clipped/off-center at the panel edge.
- **No button under the Net panel** — `net_panel_frame.pack(..., fill=tk.Y)` stretches it to the
  row's own height instead of a disabled spacer `ttk.Button` matching the "Level N" panels' own
  action-button height.
- **Debug mode** ("d" key): adds steps-vs-convergence radio (inert for Inflate, above — still left
  in place) and three arrow toggles for checking whether the CURRENT shape faces outward:
  **Show face normals** (one per face, from its centroid), **Show vertex normals** (one per
  vertex, averaged from its touching faces — catches a disagreement a per-face check alone can
  miss), and **Show repulsive forces** (Level 0's own per-vertex repulsion force, see
  physics.md's Force model section — magnitude-scaled against the max among drawn vertices, not
  unit-length, so a weakened/zeroed force is visibly shorter/absent). Release mode and debug
  mode are otherwise IDENTICAL — don't add new
  differences w/o asking. Precomp/Simulation Time update live via each background poll loop's own
  100ms cycle even without a progress callback of their own to drive them; `poll()` keeps only the
  LATEST queued progress message per cycle (discarding older ones) so a burst of messages can't
  make rendering fall behind and back up into a growing backlog.
- **Convergence History column widths are proportional, not fixed**: `self._history_column_weights`
  is a per-column RATIO; `_rescale_history_columns(available_width)` turns that into pixel widths
  that always sum to exactly `available_width` (summed only over the columns currently shown,
  release vs. debug), bound to `<Configure>` plus called directly after any `displaycolumns`
  change. `ttk.Treeview`'s own `stretch=True` distributes leftover space evenly PER COLUMN
  regardless of configured width, not proportionally — every column here is `stretch=False`
  instead, widths set explicitly.
- **No caching, no chunking**: solve starts fresh each session; UI progress synced to
  `on_progress` callback fired by the solver itself every `CONVERGENCE_CHECK_INTERVAL` steps
  (see physics.md) — not an app-side chunk schedule.
- **File > Save/Load session** (`session_state.py`'s `SessionStateModel`) carries the camera view —
  `level_zoom`/`level_pan`/`level_rotation` (every level's shared camera, see above) and
  `net_zoom`/`net_pan`. `level_rotation` is a scipy `Rotation`'s `.as_quat()` (JSON has no
  quaternion type) — `None` falls back to `_initial_level_rotation()` on load. `net_file` (the raw
  parsed net JSON, embedded wholesale) already carries `interactive_builder_app`'s own bezier
  connection data through save/load for free.
- **Session file extension is `.hippo`** (`SESSION_FILE_EXTENSION`), not `.json` — content is
  unchanged (still `SessionStateModel.model_dump_json()`); File > Load's dialog still ALSO accepts
  plain `*.json` so a session saved before this change still opens.
- **Window title is `APP_TITLE`** — "HIPPO — Hierarchical Inflatable Phabric Polyhedron
  Optimizer", a backronym named AFTER `.hippo` (the session extension) rather than the other way
  around; " (debug mode)" appended in debug mode.
- **Reads `*.poly` net files too, alongside `*.json`** (`refresh_net_list`, matching
  `interactive_builder_app`'s own save extension): both globbed and merged under
  `data/input/stretchy_nets/` (content, not extension, is all `load_stretchy_mesh` ever cared
  about). A `.json` and `.poly` sharing the same basename collide in the combo's own label→path
  map (second one wins — the two extensions replace one another per net, not coexist).
  `DEFAULT_NET_BASENAME` matches by basename, not a hardcoded `+ ".json"` path — all 11 shipped
  nets are `.poly` now.

## interactive_inflater_app (`src/apps/interactive_inflater_app/app.py`)
Combines `interactive_builder_app`'s canvas (left) with a simplified one-panel solver viewer
(right) — build a net by hand and inflate it immediately, no save/load round trip.

**Club terminology** (2026-09-28, explicit): the anchor's own connected component is the **club**;
every shape in it is a **member**; a member with 0 or 1 connections is a **guest** (0 = the first
piece ever placed, nothing to connect to yet; flat-attached or just placed, never touches
relax/inflate); a member with ≥2 connections is an **insider** (inflation only ever involves
insiders); a shape not connected to the anchor at all is an **outsider**. `self.
is_fully_inflated` tracks whether the insiders currently reflect a real relax/inflate result.
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
not drag — a drag design was tried and reverted per explicit request). Every corner shown as
`(shape_id, corner_index)`, not a shared vertex-id — that identity is only computed at Save
(union-find over connections), never live, since live merging surprised the user once (a
transitively-implied merge blocked an unrelated, individually-correct connection).

Every connection is a cubic bezier, not a line segment (2026-09-16, explicit) — two adjustable
control points, one per end, stored as `{"t","n"}` world-length offsets along that END'S OWN
edge frame (tangent/outward-normal, `_shape_edge_frame`), not an absolute point or an offset from
the other end, so a handle tracks its own shape's move/rotate for free, no update step needed.
Fresh connection defaults to dead straight (`_default_connection_handles` — colinear thirds).
Handles only ever drawn/clickable (thin red line + filled red dot, `_draw_bezier_handles`/
`_hit_test_bezier_handle`) for the ONE currently-selected connection, which only happens in Join
mode — dragging one is a single undo step, connection stays selected throughout.

**File > Save** writes the stretchy vertex-loop JSON format (as `.poly` now, `NET_FILE_EXTENSION`
— 2026-09-16, explicit; still plain JSON content, and File > Load still ALSO accepts plain
`.json`) + this app's own `net_layout`/`builder_connections`/`view` extension fields — any other
reader (incl. the solver) ignores the extra keys except `source_polygon_id` (below), which
`inflate_polyhedron_app` reads for coloring. Validation (self-loop / duplicate-directed-edge) runs
ONLY at Save, never live while editing — an edge can only be joined once (enforced live), but
transitive vertex identity is only finalized at export. **File > Load** replays `net_layout`
exactly if present; otherwise BFS-spanning-tree-lays-out fresh (same algorithm as
`stretchy_net_layout.build_stretchy_net_layout`, reimplemented locally with a gap parameter that
function doesn't have).

**Polygon Fold tool (2026-09-18, explicit)**: third real toolbar mode (`[P]`, alongside Move/Join)
— same click-click edge-handle gesture as Join, but restricted to two DIFFERENT EDGES OF THE SAME
SHAPE (`_hit_test_any_edge_handle`'s `require_shape_id`/`exclude_edge_index` params) instead of two
different shapes, modeling a polygon folded onto itself. A flat n-gon can't literally glue two of
its own edges together (a face with a repeated vertex) — `_expand_folded_shapes` resolves this at
Save/live-validation time by triangulating any shape with ≥1 such connection into `n` triangles
fanned from a fresh centroid vertex (same winding as `mesh_levels._fan_level_0_to_1`'s own Level
0→1 fan), rewriting every connection touching that shape's edge `i` onto triangle `i`'s own outer
edge, and adding the `n` spoke connections gluing the fan together — the existing
`_validate_shapes_connections`/`_faces_from_shapes`/`_edges_from_shapes`/`_face_edge_ids_from_shapes`
needed NO changes, only feeding them this expanded form instead of the raw shapes. In the app
itself, a folded shape's `n` triangles are never individually selectable/movable/deletable and
their internal spoke edges are never exposed at all — purely a Save-time (and
`_refresh_vme_state`-time) transformation.

Since a folded shape's triangles no longer align 1:1 with placed shapes, `net_layout`/
`builder_connections` are keyed by each shape's own stable id now (`"shape_id"`/`"a_shape_id"`/
`"b_shape_id"`, plus `"n"` on each `net_layout` entry so a reader can reconstruct the original
polygon's outline without stitching triangles back together) instead of by position/index into
`"faces"` — a `net_layout` entry with no `"shape_id"` is legacy, index-aligned data (any file saved
before this), handled as a fully separate branch in `_load_faces`/`inflate_polyhedron_app`'s
`_layout_from_net_layout` (`_net_layout_is_new_format`). A new `"source_polygon_id"` list, parallel
to `"faces"`, names the original placed shape each exported face came from (identical for every
triangle of one fan) — a pure downstream display aid, never read by `stretchy_mesh.py`/
`mesh_levels.py`.

## polygon_subdivision_app (`src/apps/polygon_subdivision_app/app.py`)
Unrelated 2D-only demo: splits a regular n-gon into a fine triangular mesh, preview only, no
solving. Two-stage hardcoded/closed-form split (`utils/subdivisions/`): coarse centroid-fan
(`SUBDIVISIONS`) then barycentric refinement (`_subdivide_triangle`). Uses
`FABRIC_APP_RESOLUTION=3` (matches what the real stretchy pipeline solves over), not the
generic `DEFAULT_RESOLUTION=10`.
