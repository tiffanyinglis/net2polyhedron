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
  pressure is never stored/reused across clicks, but the calibration search's own STARTING guess
  now is: `_guess_pressure_from_history` extrapolates from the nearest prior level's own
  already-calibrated `(pressure, achieved rms_stretch_pct)` in `self.level_history` when one
  exists, else falls back to `estimate_pressure_for_target_stretch`'s own generic guess — see
  physics.md's Pressure calibration section.
  **No separate "real" inflate pass any more** (2026-09-17, explicit user request — removed
  `_run_inflate_stream`/`_apply_inflate_progress` entirely): the calibration search's own WINNING
  trial's already-computed result IS the Inflate outcome. There used to be a second `relax_once`
  call at the found pressure right after calibration, purely to have something to show
  frame-by-frame — pure duplicated work, since that trial starts from the exact same positions,
  at the same pressure/gtol/rng calibration already used, so it retraced an already-computed
  trajectory step for step. The winning trial is also topped up to REAL convergence inside
  `estimate_pressure_for_target_stretch` itself now, if `max_nfev_per_trial` (5000, a search-time
  budget, not a stopping criterion) cut it off first — an uncapped `relax_once` continuation from
  wherever it left off, at the same pressure/gtol/rng, folded into the SAME `steps_taken`/frame
  sequence (2026-09-17, explicit user request: calibration used to just hand back a part-finished
  trial). Since this all happens inside the one `estimate_pressure_for_target_stretch` call the app
  already times as "Precomp", the continuation's own wall-clock time is included for free, no
  separate app-side timer needed. Skipped entirely if the winning trial already converged, no sane
  trial was ever found, or `stop_event` fired.
  `estimate_pressure_for_target_stretch(capture_frames=True)` captures the winning trial's own
  `(positions, cumulative_steps_taken)` every `CONVERGENCE_CHECK_INTERVAL` steps (its own
  `relax_once` call's `on_progress`, not exposed to callers otherwise) — INCLUDING the top-up, one
  continuous sequence — and `_on_pressure_calibrated` replays THOSE (`_start_frame_replay`/
  `_replay_step`/`_finish_frame_replay`) at `REPLAY_FPS=30` (was 10, then 20, then 32, then 60, then
  30 — each an explicit user bump/change; a target, not a guarantee, see `REPLAY_FRAME_INTERVAL_MS`'s
  own comment: a dense mesh's own per-frame render cost can exceed it), advancing
  `REPLAY_FRAME_STRIDE=4` CAPTURED frames per tick rather than 1 (2026-09-17, explicit user request
  — e.g. shows step 800, 1600, ... instead of every 200) so the same captured sequence plays back
  ~4x faster in wall-clock time at the same tick rate, `_replay_step` clamping so the very LAST
  captured frame always gets its own tick even when the stride would otherwise overshoot past it
  (verified directly: index sequence `0, 4, 8, ..., 88, 92, 93` for a 93-frame run — lands exactly
  on the true final frame, never skips it) once a pressure is found.
  `self.iteration_count` (the "Steps" column) now advances during the ACTUAL computation, not
  replay (2026-09-17, explicit user request, superseding an earlier version that moved it during
  replay instead): `estimate_pressure_for_target_stretch`'s own `on_progress` param (separate from
  `capture_frames`) reports a running total of steps computed across EVERY trial attempted, not
  reset per trial (a live counter dropping backwards every new trial would read as broken, not as
  progress) — bridged to the main thread via `_run_background`'s own `on_progress` param (new,
  coalesced the same way `_run_chunked_relax_stream`'s poll already was) into
  `_on_calibration_progress`. That running total is NOT necessarily the same number the row ends up
  showing (the winning trial isn't always the last one attempted), so `_on_pressure_calibrated`
  snaps BOTH `iteration_count` AND `self.last_stats` (hence the Convergence/RMS/Max Stretch
  History columns too — 2026-09-17, explicit user request: "the convergence column should be
  updated [when the sim converges], it doesn't need to wait for the replay to finish") to their
  TRUE final values the instant the real result comes back, BEFORE replay starts — a single
  correction at the Computing→Replay transition, not a drift visible mid-count. Neither changes
  again during replay itself; only `self.positions` (hence the 3D panel) keeps moving,
  frame by frame, until the animation reaches the end.
  `_run_background`'s own poll had a real bug here too (caught directly, 2026-09-17): "Precomp
  time"/"Cumulative Time" only ticked on an `else` branch alongside `on_progress`, so with
  progress messages arriving on nearly every 100ms poll during calibration, the timer tick almost
  never actually ran — "Simulation Time" visibly stopped updating for Level 1-3 specifically (the
  only case with a live `on_progress` at all). Both now happen unconditionally every poll cycle.
  **"RMS Stretch %" also shows "--" for the whole Computing phase** (2026-09-17, explicit user
  request — "don't calculate RMS stretch % until convergence or step 5000... show RMS stretch % as
  -- [while computing], only update the value at the end"): `on_inflate_clicked` snapshots
  `self.last_stats` (`self._pre_computing_last_stats`, to restore verbatim if Stopped) and blanks
  `rms_stretch_pct` to `None` right at the start of a click, before `_start_computing_animation`
  even runs; `_record_level_history` no longer defaults it to `0.0` (unlike `max_stretch_pct`,
  left alone) so `None` survives into `level_history`, and `_refresh_history_table` shows `"--"`
  for that specific sentinel. `_on_pressure_calibrated`'s normal path overwrites it with the real
  final number the same moment it snaps `last_stats`/`iteration_count` (see above) — verified
  directly: 194 consecutive "--" readings during one Hippo/80% run, then exactly one transition to
  the real number, never a stale pre-click leftover shown as if live. The "(target: N.N)" suffix
  is debug-mode-only now too (`self.debug_mode` gate added to the same `if`, 2026-09-17 explicit
  user request — release mode never shows it, regardless of whether the row's own RMS is known).
  Level 0's own row shows "--" for RMS Stretch % ALWAYS, not just during a run (2026-09-17, further
  explicit user request) — `_refresh_history_table` forces it regardless of `rec["rms_stretch_pct"]`;
  `last_stats`/`level_history` still get the real number from `_apply_relax_progress` under the
  hood (not worth threading a "don't compute" flag down into it for one already-cheap stat sharing
  its own `_positions_and_stretch` call with `max_stretch_pct`, which Level 0 still shows), it's
  just never surfaced in this one column. "Pressure" gets the exact same "--"-during-Computing
  treatment as RMS Stretch % (2026-09-17, explicit user request — "the pressure should also be --
  until things converge"): `self.pressure_value` (already `Optional`-shaped in practice, `_refresh_
  history_table`'s own `pressure_str` already handled `None` as "--" for Level 0's own pre-existing
  "no pressure at all" case) is snapshotted and blanked to `None` alongside `last_stats` at the same
  point, restored the same way if Stopped.
  **Level 0 and Levels 1-3 now have INDEPENDENT camera state** (rotation/zoom/pan, 2026-09-17,
  explicit user request — "separate the zoom/rotation/translation of level 0 from level 1-3 since
  they look so different"): `self._level0_camera`/`self._level13_camera` (each a `{"rotation",
  "zoom", "pan"}` dict) replace the single shared `self.level_rotation`/`level_zoom`/`level_pan`
  every level used to read/write. `_level_camera(level)` returns the right dict;
  `_camera_group_levels(level)` returns which panels need re-rendering when it changes (`[0]` or
  `[1, 2, 3]`); `_render_camera_group(level)` does that re-render. Every drag/pan/scroll handler
  now determines WHICH level (hence which group) triggered it via `self._level_of_label` (image
  Label -> level, populated in `_build_level_pv_panel`) — captured ONCE at press time for a drag/
  pan (`_level_drag_group_level`/`_level_pan_group_level`, since Tk's own button-1 grab keeps
  motion/release routed to the originally-pressed widget anyway) or read directly for a single-
  event scroll/middle-click. `SessionStateModel` gained `level0_zoom`/`level0_pan`/
  `level0_rotation` (all `Optional`, same "fall back to `_initial_level_rotation()`" pattern as
  the pre-existing `level_*` fields) — those EXISTING `level_*` field names were kept, now meaning
  specifically "the Levels 1-3 shared group," so an older session file (from before the split, when
  Level 0 shared that same state too) still loads with no migration; only Level 0 itself falls back
  to a fresh default in that case, not the old file's one shared camera. Verified directly: dragging
  Level 1's own panel leaves `_level0_camera["rotation"]` bit-for-bit unchanged while
  `_level13_camera["rotation"]` changes.
  Each "Level 1"/"Level 2"/"Level 3" panel (Level 0 excluded — see `_set_level_message`'s own
  comment on why it's still BUILT, just never populated, there too) has its own bottom status-
  message Label (`self.level_message_labels`, 2026-09-17 explicit user request) — LEFT-anchored
  (`anchor=tk.W`, set once at construction) rather than `tk.CENTER`, so the text's own start
  position never re-anchors from scratch the way true centering would. `padx` is NOT a fixed
  constant, though (tried first, then explicitly reported as looking off-center) — a single pad
  tuned for one message family reads noticeably wrong for another very-different-length one
  ("Computing", no dots yet, vs. the original "Replay frame 27 / 93" wording, since replaced —
  see below). `_set_level_message` instead measures each specific string's own rendered width
  (`self._level_message_font`, a real `tkfont.Font` object — `LEVEL_MESSAGE_FONT` itself is just
  the `(family, size)` tuple Tk widgets take, which has no `.measure()`) and computes the `padx`
  that would ACTUALLY center it — verified directly: every message tested lands within half a
  pixel of the panel's true horizontal center, while the pad only shifts a few pixels between
  calls within the same message family (never a full re-center). Shows "Computing" + a 0-3-dot
  cycle (`_tick_computing_animation`, every `COMPUTING_DOT_INTERVAL_MS`) while calibration
  searches, "Replaying" + the SAME 0-3-dot cycle during replay (`_replay_step`, dot count derived
  from `time.perf_counter()` rather than a separate timer, at the same pace — went through
  "Replay frame N / M" then "Replaying - N%" first, both since replaced, 2026-09-17 explicit user
  request each time), and clears to "" once replay finishes (`_finish_frame_replay`) or
  calibration is stopped (`_stop_computing_animation`). The
  panel's own IMAGE, while calibration is searching, is a single flat `LEVEL_PANEL_SIZE`-sized
  background-color PIL image, rendered ONCE at the start (`_start_computing_animation`) rather than
  regenerated every dot-tick — an earlier version drew the "Computing..." text directly INTO that
  image instead of using this separate message Label, which is why the image needed regenerating
  every tick; now the image never changes at all during Computing, only the (far cheaper) message
  Label does. `_render_level_pv` is the single choke point that skips a level entirely while it's
  the one showing this blank placeholder (`self._computing_level`), so a drag-rotate or resize
  can't paint over it. A Stop click during replay jumps straight to the final frame (`_replay_step`'s
  own `skip_ahead` check) rather than interrupting nothing. Level 0's Relax is UNCHANGED — it still
  redraws live every progress tick, since there's only ever one run there, nothing to throw away
  (though see the Convergence History bullet below for its OWN 2026-09-17 live-timer fix).
  The steps-vs-convergence radio buttons (`self.iterate_mode_var`/`steps_var`) no longer affect
  Inflate at all now that there's no second pass for them to bound (each calibration trial always
  runs up to its own fixed `max_nfev_per_trial`) — left in place, inert, pending a decision on
  whether to repurpose or drop them. They never affected Relax either (see `on_relax_clicked`'s
  own docstring).
  **Subdivide** up to `MAX_LEVEL=3`, carries forward current (stretched) shape.
- **Stop**: `self.stop_event` now created and the frontier button turned into "Stop" BEFORE
  calibration starts (was: only after, in `_on_pressure_calibrated`) — fixed a real bug where
  clicking Stop during calibration did nothing (no `stop_event` existed yet, and calibration's
  own `estimate_pressure_for_target_stretch` call wasn't given one either). `stop_event` now
  forwarded into that calibration call too.
- **Auto**: one Relax/Inflate attempt per level (`_auto_attempted_level`), no retry-loop (see
  physics.md). Button reads "Run Simulation" idle / "Stop Simulation" while running (renamed
  2026-09-18, explicit user request — see `_update_auto_button`).
- **Measured-value display precision (2026-09-18, explicit user request)**: RMS Stretch %
  (measured, not the "(target: ...)" spinner value) is `.1f`, Pressure is `.2f` — every history
  table cell and status-message mention of `rms_stretch`/`pressure` uses these (Max Stretch % is a
  DIFFERENT metric, untouched, still `.2f`). No separate handling needed for an old `.hippo` file's
  own higher-precision stored values — `_refresh_history_table` (and every status message) format
  straight from the loaded float, so loading one just rounds it the same as a freshly-computed one.
- **Convergence History table**: one row/level. "Convergence" cell shows `optimality op gtol
  mark` — generic display, doesn't hardcode what `optimality` measures (currently displacement,
  see physics.md), so it stays correct if that changes again. No more "(stalled)" case possible
  (the mechanism producing it was removed) — `converged` now always agrees with the plain
  comparison, kept as the source of truth anyway rather than assumed. Release-mode columns
  (2026-09-16, explicit — was max_stretch shown/elapsed+cumulative hidden, now the reverse):
  "Max Stretch %" is debug-only, "Simulation Time" (renamed from "Elapsed Time" 2026-09-17,
  explicit — column id `elapsed_time` → `simulation_time` too, `LevelHistoryRecordModel`'s own
  field names `precomp_time_s`/`sim_time_s` untouched, so an older saved session still loads with
  no migration)/"Cumulative Time" show in BOTH modes (all three stay DEFINED regardless of mode
  either way, see `history_columns`/`_release_mode_history_columns`). "--" (not "n/a") for Level
  0's own pressure (the only level whose pressure is ever None) and for `_format_mmss(None)`; a
  Simulation Time row with only ONE of precomp/sim done shows just that one `mm:ss` alone, not
  `"mm:ss + --"` (`_refresh_history_table`). Level 1+ no longer has a separate "sim" phase at all
  (2026-09-17 — see the Inflate flow's own note above: pressure calibration's winning trial IS the
  result now), so every Level 1+ row shows Precomp alone; Level 0 still shows Sim alone (no
  precomputation phase there either). `LevelHistoryRecordModel` saves `precomp_time_s`/
  `sim_time_s` too (2026-09-16, explicit — a loaded session showed no Simulation Time at all,
  since these two used to be silently dropped as "extra" fields pydantic ignores, from an earlier
  "diagnostic, not persistent" call made back when the columns were debug-only; them being
  release-mode-visible now is what actually changed).
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
  request for something brighter). `running_now` is now gated on `rec["optimality"] is None` TOO,
  not `self._level_running` alone (2026-09-17, explicit user request — "during replay, the text...
  is yellow, it should be green because it's already reached convergence"): `self._level_running`
  stays `True` for the WHOLE Inflate click including the purely-visual replay after a real result
  is already known (see `_on_pressure_calibrated`'s own comment on when `optimality`/`last_stats`
  actually get set), so without this the row stayed yellow through the entire replay animation even
  though the real converged/not_converged answer was already sitting right there — "running" now
  means "still waiting on a result", ending the moment `optimality` is real, not once the replay
  animation finishes. The Convergence CELL TEXT itself shows `"--"` (not the historical `"n/a"`,
  2026-09-17 explicit user request — "any cell that doesn't have a value yet should be -- and not
  n/a") whenever `optimality is None` — covering both "never run at this level yet" and "actively
  computing right now" (`optimality` is reset to `None` at the start of every Inflate click, same
  sentinel treatment "RMS Stretch %"/"Pressure" get — see `on_inflate_clicked`'s own comment).
  Verified directly: 193 "--" readings through Computing, 4 real readings once the result is known
  (spanning the Computing→Replay transition), tags consistently `("converged",)` (green) for every
  one of those 4, never `("running",)` (yellow). Three colors ONLY (2026-09-17, explicit user
  request -- "red is only used when convergence is not reached at the end...; yellow is used while
  simulation going on, no checks or x's; green is used when convergence is reached at the end,
  always with a check; it's never any other colour"): the `else` branch's own leftover `if
  running_now: tags = ("running",)` was DEAD CODE by this point (`running_now` requires `optimality
  is None`, but that branch only runs when it's NOT `None`) -- removed, simplifying to `tags =
  ("converged",) if converged else ("not_converged",)`, so this cell is structurally incapable of
  showing yellow with a check/X, or any color the three `tag_configure` calls (`converged`/
  `not_converged`/`running`) don't define.
  **Level 0's own Convergence column ALSO shows "--" for the whole time Relax is running**
  (2026-09-17, explicit user request — "only show the convergence value after simulation is done"),
  not just Levels 1-3's Computing phase: `_apply_relax_progress` (its own live per-checkpoint
  update) now stashes the real `optimality`/`converged` in `self._pending_relax_stats` instead of
  writing them into `self.last_stats` directly -- `last_stats["optimality"]` stays `None` (hence
  "--", same sentinel) for every checkpoint while Relax runs. `_finish_relax` is what actually
  reveals it, copying the real value back out of that stash into `last_stats` the moment Relax
  ends -- regardless of whether it converged, was Stopped, or hit its own step cap, all three count
  as "simulation is done" for this purpose. `max_stretch_pct`/`rms_stretch_pct` are UNCHANGED by
  this -- they still update live every checkpoint like before; only optimality/convergence hide
  until the end. Verified directly: 5 "--"/`("running",)` readings through Relax, then a clean
  transition to the real value with `("converged",)` tags.
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
  orbits the real center.
  **A FIXED reference framing shared across Levels 1-3, derived from Level 1's own converged
  state, was tried and REVERTED same-day** (2026-09-18, explicit user request, then explicit
  reversal after seeing the result): `_draw_level_panel` briefly used one captured `{"center",
  "half"}` (from Level 1's own convergence, in `_finish_frame_replay`) for every Level 1-3 draw
  instead of each level's own current bounding box. The camera framing itself was verified
  bit-for-bit identical across levels this way -- but a real net showed why that alone doesn't
  give "consistent sizes": this app's own per-level target RMS % TAPERS down (80/40/10 by
  default), and the converged mesh's own ABSOLUTE size can genuinely shrink a lot as a result (a
  Dodecahedron net's own half-extent measured 2.36 -> 1.79 -> 1.41 across levels 1-3) -- a
  literally fixed camera then just honestly displays that real shrinkage, which reads as
  "inconsistent sizes" rather than the consistent LOOK actually wanted. Reverted back to each
  level auto-fitting to its OWN current bounding box -- rotation/pan/zoom (`self._level13_camera`)
  stay SHARED across Levels 1-3 regardless, since that's a separate, still-current mechanism (see
  above) this reversal never touched.
  **`_level_half` is now a proper bounding-SPHERE radius, and `WIREFRAME_VIEW_FILL` was removed
  entirely** (2026-09-18, explicit user request, immediately after the reversal above — "90% zoom
  means both width and height are at most 90%" — real renders were clipping past the top/bottom
  edge despite `_level_zoom_fill` claiming 90%): two compounding bugs, both in `_draw_level_panel`/
  `_render_level_pv`. (1) `_level_half` used `(hi-lo).max()/2` -- half of the largest single WORLD-
  AXIS extent -- which UNDERESTIMATES a shape's true on-screen extent when viewed from an oblique
  angle (a shape's diagonal reaches further across the screen than any one axis's own half-length
  does); switched to `norm(points - center, axis=1).max()`, the true bounding-sphere radius, which
  bounds the shape from EVERY direction regardless of the shared rotation's current angle. (2)
  `WIREFRAME_VIEW_FILL = 0.8` (an older, separate "margin" constant, predating `_level_zoom_fill`)
  was still being multiplied into `_level_half` on top of `_level_zoom_fill` dividing it again in
  `_render_level_pv` -- two independently-tuned "how much fill" knobs COMPOUNDING as `_level_zoom_
  fill / WIREFRAME_VIEW_FILL` = 0.9/0.8 = 112.5% instead of just being 90%, which is the OTHER
  reason it was overshooting into clipping. Removed `WIREFRAME_VIEW_FILL` entirely (only usage);
  `_level_zoom_fill` is now the sole, authoritative fill fraction. Verified directly (Dodecahedron,
  all three levels): the panel's own NARROWER dimension (width, for these portrait panels) lands at
  EXACTLY 90.0%, the taller dimension (height) at 72.6% -- comfortably under 90%, never over,
  matching `_render_level_pv`'s own aspect-ratio handling (`max(1, panel_height/panel_width)`
  giving the taller dimension EXTRA slack rather than less). Level 0 checked too: 90.0% width,
  38.4% height (an even more portrait panel, so even more height slack).
  **"Level N" panels are no longer all the same width** (2026-09-18, explicit user request — "make
  the level 0 drawing area and label 60% of its current width... distribute [the other 40%] evenly
  to level1-3 so they are wider"): `LEVEL_PANEL_WIDTH_LEVEL_0 = round(320 * 0.6) = 192`,
  `LEVEL_PANEL_WIDTH_LEVELS_1_3 = round(320 + (320 - 192) / 3) = 363` (height unchanged for every
  panel, `LEVEL_PANEL_HEIGHT = 450`) — `_level_panel_size(level)` returns the right pair, replacing
  every level-panel use of the old single `LEVEL_PANEL_SIZE` constant (the PyVista plotter's own
  `window_size`, `_render_level_pv`'s aspect/parallel_scale calc, `_on_level_pan_motion`'s NDC
  conversion — using `_level_panel_size(self._level_pan_group_level)`, since Level 0's and Levels
  1-3's panels are now different sizes too — `_set_level_message`'s centering calc, and the
  Computing placeholder's own blank image size). The Net panel's own size is UNCHANGED and now
  has its own separate `NET_PANEL_SIZE = (320, 450)` constant (the user only asked about "the
  level 0 drawing area", not Net) — `window_width` in `__init__` sums all three distinct widths
  (`NET_PANEL_SIZE[0] + LEVEL_PANEL_WIDTH_LEVEL_0 + LEVEL_PANEL_WIDTH_LEVELS_1_3 * MAX_LEVEL`)
  instead of the old `LEVEL_PANEL_SIZE[0] * (MAX_LEVEL + 2)` (every panel-the-same-width
  shorthand). `LEVEL_ZOOM_FILL_LEVEL_0` raised to match, `0.5 -> 0.9` (same request, "then make
  the object fill 90%") — both levels now fill the SAME 90% of their own (differently-sized)
  panels.
  The Net panel has its own separate 2D data-space offset (`self.net_pan`,
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
  is -- a bezier connection can sweep well past its two faces' combined extent. `level_zoom` itself
  (the mouse-wheel MULTIPLIER, shared across every "Level N" panel) is separate from each panel's
  own DEFAULT fill fraction at `level_zoom=1.0` -- `_level_zoom_fill(level)` (2026-09-17, explicit
  user request: "level 0 should default to filling 50%... level 1-3 should default to filling
  95%", the latter adjusted down to 90% by explicit follow-up request) returns
  `LEVEL_ZOOM_FILL_LEVEL_0=0.5` for level 0, `LEVEL_ZOOM_FILL_LEVELS_1_3=0.90` for everything
  else, replacing the single shared `LEVEL_ZOOM_FILL=0.36` constant both used before --
  Level 0's own random-start/relax result is often widely spread before it settles, so a smaller
  default leaves room to see it without every edge crowding the panel; Levels 1-3 show an actual
  settling/settled solid, worth filling most of the panel by default. Used in `_render_level_pv`'s
  own `camera.parallel_scale` formula, in place of the old flat `LEVEL_ZOOM_FILL`.
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
- **Status text (2026-09-16, explicit)**: `self.status_frame` (the warning/error/progress TEXT
  row) is debug-mode-only now (`_apply_mode_visibility` packs/`pack_forget`s it) — used to be
  visible in both modes.
- **Spinner removed entirely (2026-09-18, explicit — "get rid of the loading/spinning icon"
  next to the Auto button)**: `self.progress` (a `_SpinnerCanvas`, a `tk.Canvas` rotating-arc
  widget replacing an even earlier `ttk.Progressbar`) and every one of its
  pack/start/pack_forget/stop call sites (Level 0 Relax, Inflate's pressure-calibration
  `_run_background`, its replay) are gone — the running-state text ("Computing...",
  "Replaying...", live Steps/Time columns) already conveys "something is happening" without it.
  `_SpinnerCanvas` itself was deleted from the module (no other caller).
- **Uniform font, matched to "Choose a net" (2026-09-18, explicit — "make sure the font size is
  uniform. also that the font is uniform. I like the size and font of 'Choose a net'")**:
  `self.LEVEL_TITLE_FONT`/`self.LEVEL_MESSAGE_FONT` (panel titles, bottom status messages) and the
  File menu's own font (`_build_menu`) are all computed once in `_init_ui_fonts` (called right
  after `_scale_ui_fonts`, in `__init__`) from `tkfont.nametofont("SunValleyBodyFont").actual()`
  — the SAME named font sv_ttk routes a plain, no-`font=`-override `ttk.Label` (like "Choose a
  net") through, so they now genuinely match its real rendered family/size, not just its size.
  Replaces a `("TkDefaultFont", round(11 * UI_FONT_SCALE))` module-level tuple that was a real
  BUG, not just a mismatch: passing a named font's NAME as a plain tuple's family element makes Tk
  treat it as a literal (nonexistent) family and silently fall back to Arial — verified directly
  (`tkfont.Font(font=("TkDefaultFont", 14)).actual()` -> `{'family': 'Arial', ...}`) — so those
  labels never actually rendered in the UI's real Segoe UI Variable Text look despite being scaled
  by the same `UI_FONT_SCALE`. The File menu's own font used to independently reuse `TkMenuFont`'s
  family at its own hardcoded size (`round(11 * UI_FONT_SCALE)` = 14pt "Segoe UI") — also fixed,
  since that read both mismatched (different family from the labels) AND "a tad" oversized next to
  the rest of the UI once actually compared side by side.
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
- **Debug mode** ("d" key): adds steps-vs-convergence radio (now inert for Inflate, see the
  Inflate flow's own note above — still left in place), **Validate Mesh** (combinatorial
  winding check only — geometric inside/out check is informational, not gating), and **Show
  normals** (draws each face's outward normal, live equivalent of Validate Mesh's info note). A
  **"Pressure calc step ×"** spinner briefly existed here too (overrode
  `stretchy_mesh.PRESSURE_CALC_STEP_MULTIPLIER` per Inflate click) — REMOVED entirely (2026-09-16,
  explicit user request, along with the multiplier mechanism itself — see physics.md's Pressure
  calibration section); don't re-add without new explicit permission.
  Release mode and debug mode are otherwise IDENTICAL — don't add new differences w/o asking.
  ("Simulation Time"/"Cumulative Time" are release-mode columns now, not debug-only — see the
  Convergence History bullet above; Precomp updates live via `_run_background`'s own 100ms poll
  loop even though calibration has no progress callback of its own to drive it. Level 0's own Sim
  time now updates the SAME way — `_run_chunked_relax_stream`'s own poll loop, 2026-09-17 explicit
  user request — since `relax_initial_configuration`'s on_progress only fires every
  `CONVERGENCE_CHECK_INTERVAL` steps, which left the displayed time visibly frozen for a while in
  between; before this it only ticked on an actual progress event, not on wall-clock alone.
  `_apply_relax_progress`'s own per-tick redraw was ALSO switched from a full `draw()` to a
  targeted `_draw_level_panel(0, ...)` (same fix as Inflate's own replay, see `_replay_step`'s own
  comment) — a full draw() measured at ~0.3-0.5s, slower than the poll's own 80ms interval, so
  `poll()`'s `while True: get_nowait()` drain (processing EVERY queued progress message, oldest
  first) meant a backlog only ever grew, each render taking longer than the interval it was trying
  to keep up with — visible as "stalls, then jumps by several seconds" (2026-09-17, explicit user
  report) even after the wall-clock tick above landed, since that tick lives in the SAME poll()
  and was starved right along with everything else. The real fix was coalescing: `poll()` now
  keeps only the LATEST queued "progress" message per cycle and renders just that one, discarding
  older ones as wasted work nobody would ever see — bounds each poll() call to at most one render,
  so the backlog can no longer accumulate.)
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
