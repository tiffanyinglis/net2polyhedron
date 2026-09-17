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
  recalibrates pressure FRESH every click (`on_inflate_clicked`: calibrate via `_run_background`,
  then stream via `_run_inflate_stream`) — pressure is never stored/reused across clicks, but the
  calibration search's own STARTING guess now is: `_guess_pressure_from_history` extrapolates
  from the nearest prior level's own already-calibrated `(pressure, achieved rms_stretch_pct)` in
  `self.level_history` when one exists, else falls back to `estimate_pressure_for_target_stretch`'s
  own generic guess — see physics.md's Pressure calibration section.
  **Subdivide** up to `MAX_LEVEL=3`, carries forward current (stretched) shape.
- **Stop**: `self.stop_event` now created and the frontier button turned into "Stop" BEFORE
  calibration starts (was: only after, in `_on_pressure_calibrated`) — fixed a real bug where
  clicking Stop during calibration did nothing (no `stop_event` existed yet, and calibration's
  own `estimate_pressure_for_target_stretch` call wasn't given one either). `stop_event` now
  forwarded into that calibration call too.
- **Auto**: one Relax/Inflate attempt per level (`_auto_attempted_level`), no retry-loop (see
  physics.md). Button becomes "Stop Auto" while running.
- **Convergence History table**: one row/level. "Convergence" cell shows `optimality op gtol
  mark` — generic display, doesn't hardcode what `optimality` measures (currently displacement,
  see physics.md), so it stays correct if that changes again. No more "(stalled)" case possible
  (the mechanism producing it was removed) — `converged` now always agrees with the plain
  comparison, kept as the source of truth anyway rather than assumed. Release-mode columns
  (2026-09-16, explicit — was max_stretch shown/elapsed+cumulative hidden, now the reverse):
  "Max Stretch %" is debug-only, "Elapsed Time"/"Cumulative Time" show in BOTH modes (all three
  stay DEFINED regardless of mode either way, see `history_columns`/`_release_mode_history_
  columns`). "--" (not "n/a") for Level 0's own pressure (the only level whose pressure is ever
  None) and for `_format_mmss(None)`; an Elapsed Time row with only ONE of precomp/sim done shows
  just that one `mm:ss` alone, not `"mm:ss + --"` (`_refresh_history_table`).
  `LevelHistoryRecordModel` now saves `precomp_time_s`/`sim_time_s` too (2026-09-16, explicit — a
  loaded session showed no Elapsed Time at all, since these two used to be silently dropped as
  "extra" fields pydantic ignores, from an earlier "diagnostic, not persistent" call made back
  when the columns were debug-only; them being release-mode-visible now is what actually changed).
  Row coloring is 3-state now (2026-09-16, explicit — "should be yellow, not red" while running):
  `self._level_running` (set/cleared in lockstep with `_set_level_action_button_running`, the
  per-level button's own "Stop" state) makes the CURRENT frontier level's row `"running"` instead
  of `"not_converged"` (red) while a run is actively in progress for it — red is reserved for an
  ACTUAL failure (step cap reached, or Stop clicked), never just "hasn't converged yet, still
  going". A different level's row is never colored `"running"`, even while the frontier level is
  (`_finish_relax`/`_finish_inflate` both flip it back to `False` on the way out, whichever way
  the run actually ended). `"running"`'s own color is `RUNNING_ROW_COLOR = "#e0b400"`, a dedicated
  module constant, NOT `STATUS_COLORS["warn"]` (tried first, but that's a muddy dark goldenrod
  tuned for warning TEXT elsewhere in this app, not a bright row highlight — explicit follow-up
  request for something brighter).
  `_history_column_weights` rebalanced (2026-09-16, explicit — "take some of the extra space from
  the last 4 columns (especially convergence) and distribute them to the first 3"): level/
  pressure/steps 55/80/65 → 70/100/85; rms_stretch/elapsed_time/cumulative_time/convergence
  155/150/140/185 → 150/145/135/145 (convergence gave up the most, 185 → 145).
- **Validate Mesh** (`_validate_mesh`, debug-only): returns `"PASS: all N faces are consistently
  oriented."` or `"FAIL: B/N faces are inconsistently oriented."` (2026-09-16, explicit — was
  "Structural winding: ..." prose) plus the same per-edge detail lines as before when it fails;
  `B` is the count of DISTINCT faces touching any conflicting edge, not the edge count itself.
- **3D panels**: PyVista off-screen render blitted into a Tk Label per level (`pv.Plotter(
  off_screen=True)` + `PIL.ImageTk`) — needed because meshes here are routinely non-convex/
  self-intersecting mid-relax, which plain mplot3d/backface-culling can't draw correctly. One
  shared camera angle across all "Level N" panels (drag any → all rotate together). "Net" panel
  (flat undeformed layout) is still matplotlib, own independent zoom. `self.ax2d` is `fig_net.
  add_axes([0, 0, 1, 1])`, not `add_subplot` (2026-09-16, explicit — "the drawing area for net is
  much smaller than... level 0-3"): `add_subplot`'s own default margins reserved room for axis
  ticks/labels `_style_2d_axis`'s `set_axis_off()` never draws anyway, wasting ~23% of the figure
  on each side that every "Level N" panel's own PyVista viewport (no such margin concept) never
  lost. `set_aspect("equal")`'s own default `adjustable="box"` was STILL shrinking whichever axis
  had proportionally less content relative to the panel's own aspect ratio (net still read as
  margin-thicker than Level 0-3 even after the add_axes fix, 2026-09-16, explicit follow-up) --
  `_draw_target_faces` now pre-stretches `half_range` to the panel's own aspect ratio
  (`LEVEL_PANEL_SIZE[0] / LEVEL_PANEL_SIZE[1]`, since this panel's figure size already matches it
  exactly) BEFORE calling `set_xlim`/`set_ylim`, the same "grow the tighter-fitting axis to match,
  don't let either end up short" idea `_render_level_pv`'s own `camera.parallel_scale` term
  (`max(1.0, panel_height / panel_width)`) already uses for the "Level N" panels -- verified
  directly: the axes bounding box is exactly `(0, 0, 1, 1)` in figure fraction now, not `~0.8`
  height like before.
  If the loaded net has `net_layout` (saved by `interactive_builder_app`), the Net panel shows
  that EXACT flat arrangement (with a Y-flip: Tk canvas Y-down vs matplotlib Y-up) instead of a
  fresh BFS spanning-tree layout. When that same file also has `builder_connections`
  (`self.target_connections`), each one's bezier curve (module-level `_connection_curve_points`/
  `_placed_edge_frame`) is drawn on top of the faces too, solid white — same curve
  `interactive_builder_app` shows, rescaled/Y-flipped like everything else in this panel — but
  never its two handles (this panel is read-only). Net panel no longer shows a fine-mesh
  subdivision overlay (2026-09-16, explicit — "too busy"); just the plain base faces + connection
  curves.
- **"Level N" panel wireframe edge color**: PER-BASE-FACE now (2026-09-16, explicit — "don't use
  white... use the color half way between white and the polygon color"), not one fixed
  `PLOT_THEME["fg"]` for every edge regardless of face. `_draw_level_panel` now does one
  `add_mesh` call PER base face (grouped via `face_of_fine`) instead of one call for the whole
  mesh with a per-cell "colors" scalar array — VTK's own `edge_color` is a single uniform color
  per `add_mesh` call, so a different edge color per face needs a separate call per face group;
  still one scene/depth buffer (`plotter.clear()` once, not between these calls), so cross-group
  occlusion still works exactly like the old single-call version did. `_midpoint_color(a, b)`
  (module-level) is the plain RGB average of two matplotlib-recognized colors.
- **Pan/zoom (2026-09-16, explicit)**: right-click-drag pans. Level panels share ONE pan
  (`self.level_pan`, a 2D NDC offset applied via `vtkCamera.SetWindowCenter` in
  `_render_level_pv` — a pure post-projection viewport shift, NOT added to focal_point/position).
  A first version used a 3D world-space offset added to focal_point/position instead — had two
  real bugs, both from that same choice: (1) each level has its own bounding-box scale, so an
  identical world-space offset produced a DIFFERENT pixel shift per panel (translation looked
  unsynced); (2) moving focal_point moves the camera's own orbit center, so rotating after
  panning no longer orbited the object's true center. `SetWindowCenter` fixes both — same NDC
  value = same pixel shift on every panel (they all render at `LEVEL_PANEL_SIZE`), and
  focal_point/position are computed exactly as if pan didn't exist, so rotation always still
  orbits the real center. The Net panel has its own separate 2D data-space offset (`self.net_pan`,
  `_on_net_pan_motion`, added to `_draw_target_faces`' own bounding-box center) — its y-sign is
  OPPOSITE x's (`+dy`, not `-dy`) since Tk pixels grow downward while this axes' data y grows
  upward; an earlier version used `-dy` and panned vertically backwards. Middle-click resets
  pan AND zoom AND (level panels only) rotation all back to their defaults in one click
  (`_on_level_pan_reset`/`_on_net_pan_reset`, 2026-09-16 explicit — used to reset pan alone);
  `_initial_level_rotation()` is what rotation resets to, not identity, since the default view is
  deliberately non-axis-aligned (`LEVEL_DEFAULT_ELEV`/`_AZIM`). `level_zoom` clamped to 30%..400%
  (`LEVEL_ZOOM_MIN/MAX`); `net_zoom` clamped to 30%..800% (`NET_ZOOM_MIN/MAX`) — its own MAX raised
  from 400% (2026-09-16, explicit, "the net can be zoomed in a bit more without getting cut off"),
  decoupled from `LEVEL_ZOOM_MAX` again since the Net panel's own bounding box (see below) can be
  much larger, relative to the faces themselves, than any "Level N" panel's own bounding box ever
  is -- a bezier connection can sweep well past its two faces' combined extent.
- **Setup row (2026-09-16, explicit)**: `self.combo` ("Choose a net") width halved (30→15). Gap
  between net/target-RMS/tolerance/auto groups widened to `padx=(96, 0)` each (24 → 32 → 96,
  2026-09-16, explicit twice over — "put some space between", then "3x the current amount").
  Each "Level N:" label WITHIN target_group also widened, `padx=(8, 2)` → `(20, 2)` (2026-09-16,
  explicit — separates "Target RMS stretch:" from Level 1's own entry, and each level's entry
  from the next level's label, not just the whole group from its neighbors).
  Each `target_rms_vars[level]`/`self.tolerance_spin` is a plain `ttk.Entry` now, not a
  `ttk.Spinbox` (the up/down arrows only ever gated THEMSELVES, never free typing) —
  `_register_numeric_entry`/`_is_valid_numeric_partial` reject a keystroke outright (Tk's
  `validate="key"`/`%P`) if it wouldn't leave a number-or-prefix-of-one behind; tolerance's own
  entry additionally allows an exponent (`allow_exponent=True`, its own text is scientific
  notation, e.g. "1e-03"). Target RMS ALSO clamps into [0, 100] on `<Return>`/`<FocusOut>`
  (`_commit_target_rms_entry`) — truncated to the nearest extreme, not rejected; tolerance has no
  such clamp (only a range was ever requested for target RMS), `_get_tolerance` already falls
  back to `DEFAULT_TOLERANCE` for anything unparseable. Each level's own label reads "Level N:",
  not "LN:" (2026-09-16, explicit).
- **Target RMS entries, "%" suffix + whole numbers (2026-09-16, explicit)**: `target_rms_vars
  [level]` (a plain float, read everywhere else in the app unchanged) now rounds to the nearest
  WHOLE number on commit (`_commit_target_rms_entry`), no decimal place. The entry itself is bound
  to a SEPARATE `self.target_rms_display_vars[level]` StringVar, not `target_rms_vars[level]`
  directly — shows "N%" while unfocused (`_sync_target_rms_display`, a trace on the raw var, so it
  stays correct even after a change from elsewhere, e.g. session load) and the bare number alone
  while being edited (`_begin_edit_target_rms`, on `<FocusIn>` — the "%" is appended once a number
  is entered, never typed by the user). `_register_numeric_entry` gained `allow_decimal` (default
  True, False for target RMS) alongside its existing `allow_exponent`.
- **Level panel action buttons**: no longer `fill=tk.X` (2026-09-16, explicit — read as an
  oversized bar spanning the whole 320px panel); left at natural text width, centered under the
  panel by pack's own default anchor. Debug-mode-only now too (2026-09-16, explicit — "release
  mode will just use auto"): `_apply_mode_visibility` packs/`pack_forget`s each one, same pattern
  as `mode_row`/`status_frame`. Only hidden, never destroyed or disabled-differently — `_auto_step`
  drives Relax/Inflate/Subdivide by calling `on_relax_clicked`/`on_inflate_clicked`/`on_subdivide_
  clicked` directly, never `button.invoke()`, so it's unaffected either way.
- **Window height re-fits per mode** (`_refit_window_height`, 2026-09-16, explicit — release mode
  used to keep debug mode's own taller height, leaving dead space below the hidden rows):
  `root.geometry()` reset to `winfo_reqheight()` (width read back from `winfo_width()`, untouched).
  Called from exactly 3 places, each a genuine MODE change: end of `__init__` (AFTER `on_select_
  net()`'s own `draw()` — BEFORE that, a "Level N" panel's image Label has ~zero natural height
  pre-first-PhotoImage, so fitting early would squeeze every panel once images appear), `_on_
  toggle_debug_mode`, and `on_load_session_clicked`'s tail (a loaded session can carry its own
  `debug_mode`). Deliberately NOT called from plain `on_select_net` (same mode, different net) —
  would otherwise fight a manual window resize on every net switch.
- **Status text / animated "waiting" indicator (2026-09-16, explicit)**: `self.status_frame` (the
  warning/error/progress TEXT row) is debug-mode-only now (`_apply_mode_visibility` packs/
  `pack_forget`s it) — used to be visible in both modes. `self.progress` (the indeterminate
  Progressbar itself) moved OUT of that frame entirely, into `auto_group` next to the Auto button,
  so it keeps animating/showing in release mode regardless of status_frame's own visibility —
  same widget, same pack/start / pack_forget/stop call sites as before, just a different parent.
  `self.progress` is a `_SpinnerCanvas` (module-level class), not a `ttk.Progressbar`, now
  (2026-09-16, explicit — "a spinning circle... instead" of the horizontal bouncing bar) — a
  drop-in replacement exposing only `start(interval_ms)`/`stop()` (mirroring ttk.Progressbar's own
  names/signature) over a `tk.Canvas` rotating arc, animated via a self-rescheduling `self.after`
  chain (`_tick`) that `stop()` halts by clearing `self._running`, no `after_cancel` needed.
- **Window width**: `window_width = LEVEL_PANEL_SIZE[0] * (MAX_LEVEL + 2) + 28` (computed, not a
  bigger hardcoded literal — 2026-09-16, explicit: the previous 1700 left an uneven blank margin
  on the right, since every row here packs its own content flush LEFT rather than centering).
  `+28` is `2 * 14`, view_frame's own left/right `padx`.
- **Net panel bounding box** (`_draw_target_faces`): now includes every connection curve's own
  sampled points, not just the polygon vertices (2026-09-16, explicit — a bezier bulging past its
  two faces' combined extent was getting clipped/off-center at the panel edge; feeding its points
  into the same `all_pts` the faces already use fixes both centering and framing at once).
- **No button under the Net panel** (2026-09-16, explicit — used to be a disabled blank
  `ttk.Button`, purely to match the "Level N" panels' own action-button height so the row stayed
  aligned): `net_panel_frame.pack(..., fill=tk.Y)` stretches it to the row's own height instead,
  no spacer widget needed; the net canvas (already `fill=tk.BOTH, expand=True`) grows into
  whatever extra height that leaves.
- **Debug mode** ("d" key): adds steps-vs-convergence radio, **Validate Mesh** (combinatorial
  winding check only — geometric inside/out check is informational, not gating), **Show
  normals** (draws each face's outward normal, live equivalent of Validate Mesh's info note),
  and the Convergence History table's own **"Elapsed Time"** column (below). A
  **"Pressure calc step ×"** spinner briefly existed here too (overrode
  `stretchy_mesh.PRESSURE_CALC_STEP_MULTIPLIER` per Inflate click) — REMOVED entirely (2026-09-16,
  explicit user request, along with the multiplier mechanism itself — see physics.md's Pressure
  calibration section); don't re-add without new explicit permission.
  Release mode and debug mode are otherwise IDENTICAL — don't add new differences w/o asking.
- **Convergence History "Elapsed Time"/"Cumulative Time" columns** (debug mode only, 2026-09-16,
  explicit user request): "Elapsed Time" shows `"{precomp} + {sim}"` (each independently
  `_format_mmss`-formatted, "n/a" if that phase hasn't run at this level yet, e.g.
  `"12:34 + n/a"` once calibration finishes but Inflate's own streamed run hasn't started/updated
  yet) — EXCEPT Level 0, which has no precomputation phase at all (`relax_initial_configuration`
  is pure springs, no pressure to calibrate), so its row shows just the one (Sim) value, not
  `"n/a + mm:ss"`. "Cumulative Time" (added right after, same request) is a running total, in
  level order, of every row's own Elapsed Time seconds so far (both phases, Level 0's single one
  included) — a level that hasn't run yet contributes 0 to it, not "n/a" (the total UP TO that
  row is still a real known number). Both wall-clock (`time.perf_counter()`) times are tracked
  separately as `self._current_precomp_time_s`/`_current_sim_time_s` (see their own comment in
  `__init__`) and only combined/summed at DISPLAY time in `_refresh_history_table` (a single
  `cumulative_seconds` running total carried across that method's own level loop, which always
  visits levels 0, 1, 2, ... in order). "Elapsed Time" was originally two separate columns
  ("Precomp time"/"Sim time"), merged into one per explicit user request. Both stay DEFINED in
  both modes (`self.history_tree`'s own `displaycolumns`, toggled in `_apply_mode_visibility`),
  just hidden in release mode. Sim updates LIVE on every progress callback
  (`_apply_inflate_progress`/`_apply_relax_progress`) then again at the phase's own finish, same
  cadence as `iteration_count`. Precomp ALSO updates live (2026-09-16, explicit user request) even
  though `estimate_pressure_for_target_stretch` has no progress callback of its own to drive
  it — `_run_background`'s own 100ms poll loop (which already exists to check whether the
  background calibration thread has finished) recomputes
  `self._current_precomp_time_s = time.perf_counter() - self._precomp_start_time` and calls
  `_record_level_history()` on every tick where the result queue is still empty, ticking the
  clock forward even though there's no real progress data behind it — same wall-clock-not-solver-
  progress idea "Sim time" already used, just driven by a poll interval instead of a genuine
  on_progress callback. Cumulative Time updates live for free alongside it, since it's recomputed
  fresh from `precomp_time_s`/`sim_time_s` every single `_refresh_history_table` call (including
  the ones `_record_level_history` triggers from this poll tick), not cached separately. The
  underlying `precomp_time_s`/`sim_time_s` reset to `None` anywhere
  `iteration_count` itself resets (fresh net load, Subdivide, Level 0→1 promotion). NOT
  saved/restored by session save/load (`LevelHistoryRecordModel` doesn't define these fields, so
  they're silently dropped on save and read back as `None`/"n/a" on load) —
  timing is a live-session diagnostic, not persistent state.
- **Convergence History column widths — proportional, not fixed** (2026-09-16, explicit user
  request, after two earlier attempts: plain fixed widths left blank space or overflowed; only
  the last column stretching left the others un-resized): `self._history_column_weights` is a
  per-column RATIO (not a pixel width); `_rescale_history_columns(available_width)` turns that
  into actual pixel widths that always sum to exactly `available_width`, every column scaled by
  the same factor, summed only over the columns CURRENTLY shown (release mode's 6 vs debug
  mode's 8 have different total weight, so a column's own share of the width differs by mode
  too). Bound to `self.history_tree`'s own `<Configure>` (fires on every resize) and called
  directly from `_apply_mode_visibility` right after a `displaycolumns` change (switching modes
  doesn't itself resize the widget, so no `<Configure>` would otherwise fire for that case).
  `ttk.Treeview`'s own `stretch=True` does NOT do this — verified directly it distributes any
  leftover space evenly PER COLUMN regardless of each one's own configured width, ballooning a
  narrow column (e.g. "Level") exactly as much as a wide one (e.g. "RMS Stretch %") instead of
  proportionally; every column here is `stretch=False`, widths set explicitly instead. Also
  verified directly: `self.history_tree.cget("displaycolumns")` after setting `"#all"` reads
  back as the TUPLE `('#all',)`, not the bare string `"#all"` — `_rescale_history_columns`
  checks against the tuple form.
- **No caching, no chunking**: solve starts fresh each session; UI progress synced to
  `on_progress` callback fired by the solver itself every `CONVERGENCE_CHECK_INTERVAL` steps
  (see physics.md) — not an app-side chunk schedule.
- **File > Save/Load session** (`session_state.py`'s `SessionStateModel`): also carries each
  panel's own camera view now (2026-09-16, explicit — "update save/load file formats now that we
  have all these new changes") — `level_zoom`/`level_pan`/`level_rotation` (all 3 "Level N" panels
  share one camera, see their own __init__ comments) and `net_zoom`/`net_pan`. `level_rotation` is
  `self.level_rotation.as_quat()` (a scipy `Rotation`, JSON has no quaternion type) — `None` (an
  older session file, or the new field genuinely never set) falls back to `_initial_level_
  rotation()` on load, not a baked-in quaternion in the model, since that method is the one place
  this app's own non-axis-aligned default view is actually defined; all 5 fields default to the
  ORIGINAL always-reset-to-default values, so an older session file still loads exactly as it used
  to. `net_file` (the raw parsed net JSON, embedded wholesale) already carries `interactive_
  builder_app`'s own bezier `a_handle`/`b_handle` connection data through save/load for free —
  no schema change needed there, unlike the camera view.
- **Session file extension is `.hippo`** (`SESSION_FILE_EXTENSION`, 2026-09-16, explicit user
  request), not `.json` — content is unchanged (still `SessionStateModel.model_dump_json()`), the
  extension just distinguishes a saved session from an ordinary `.json` (e.g. a hand-authored net
  under `data/input/stretchy_nets/`) at a glance. File > Load's own dialog still ALSO accepts plain
  `*.json` (a second `filetypes` entry) so a session saved before this change still opens.
- **Window title is `APP_TITLE`** (2026-09-16, explicit user request) — "HIPPO — Hierarchical
  Inflatable Phabric Polyhedron Optimizer", a backronym named AFTER `.hippo` (the session
  extension, above) rather than the other way around. Set in `_apply_mode_visibility` (plus
  " (debug mode)" in debug mode, same as always). Module docstring's own first line and the
  save/load `filetypes` label text still say "Inflate Polyhedron" — not touched, out of scope for
  what was actually asked (just the window title).
- **Reads `*.poly` net files too, alongside `*.json`** (`refresh_net_list`, 2026-09-16, explicit —
  `interactive_builder_app`'s own new save extension, see its own section below): both globbed
  and merged under `data/input/stretchy_nets/`; `load_stretchy_mesh`/`json.load` never cared about
  the extension, only content, so no further change was needed to actually read one. A `.json` and
  a `.poly` sharing the same basename collide in the combo's own label→path map (second one wins,
  not handled specially — the two extensions are meant to replace one another per net, not
  coexist under the same name). `DEFAULT_NET_BASENAME`'s own default-net lookup matches by
  BASENAME now (`os.path.splitext`), not one hardcoded `+ ".json"` path string — all 11 shipped
  nets (including `cube`) are `.poly` now (2026-09-16, explicit — see below), so the old exact-path
  check would otherwise silently stop finding it and fall back to "first net alphabetically".

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
`.json`) + this app's own `net_layout`
(`{cx,cy,rotation}` per face) and `view` (`{scale}`) extension fields — any other reader (incl.
the solver) ignores the extra keys. Validation (self-loop / duplicate-directed-edge) runs ONLY
at Save, never live while editing — an edge can only be joined once (enforced live), but
transitive vertex identity is only finalized at export. **File > Load** replays `net_layout`
exactly if present; otherwise BFS-spanning-tree-lays-out fresh (same algorithm as
`stretchy_net_layout.build_stretchy_net_layout`, reimplemented locally with a gap parameter that
function doesn't have).

## polygon_subdivision_app (`src/apps/polygon_subdivision_app/app.py`)
Unrelated 2D-only demo: splits a regular n-gon into a fine triangular mesh, preview only, no
solving. Two-stage hardcoded/closed-form split (`utils/subdivisions/`): coarse centroid-fan
(`SUBDIVISIONS`) then barycentric refinement (`_subdivide_triangle`). Uses
`FABRIC_APP_RESOLUTION=3` (matches what the real stretchy pipeline solves over), not the
generic `DEFAULT_RESOLUTION=10`.
