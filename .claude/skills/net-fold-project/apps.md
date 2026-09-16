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
  comparison, kept as the source of truth anyway rather than assumed.
- **3D panels**: PyVista off-screen render blitted into a Tk Label per level (`pv.Plotter(
  off_screen=True)` + `PIL.ImageTk`) — needed because meshes here are routinely non-convex/
  self-intersecting mid-relax, which plain mplot3d/backface-culling can't draw correctly. One
  shared camera angle across all "Level N" panels (drag any → all rotate together). "Net" panel
  (flat undeformed layout) is still matplotlib, own independent zoom.
  If the loaded net has `net_layout` (saved by `interactive_builder_app`), the Net panel shows
  that EXACT flat arrangement (with a Y-flip: Tk canvas Y-down vs matplotlib Y-up) instead of a
  fresh BFS spanning-tree layout. When that same file also has `builder_connections`
  (`self.target_connections`), each one's bezier curve (module-level `_connection_curve_points`/
  `_placed_edge_frame`) is drawn on top of the faces too — same curve `interactive_builder_app`
  shows, rescaled/Y-flipped like everything else in this panel — but never its two handles (this
  panel is read-only).
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

**File > Save** writes the stretchy vertex-loop JSON format + this app's own `net_layout`
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
