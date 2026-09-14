# Debugging history — inflate_polyhedron_app / stretchy_mesh.py

Detailed incident narratives behind the rules in `SKILL.md`. Read only the
section you actually need.

## Removed force-model terms (see "No hacky terms" in SKILL.md)

- **Target/reference-volume pressure term**: removed because it silently
  followed wherever the mesh currently was, compounding stretch across
  repeated Subdivide-then-Inflate cycles even at the same nominal pressure.
- **Per-edge soft stretch limit** (quadratic stiffening past 2x/0.5x rest
  length): added because plain Hooke's-law springs can't hold pressure
  past a critical value (pressure ~ area ~ length², a spring's pull only
  grows linearly, so past some pressure there's no equilibrium and the
  mesh inflates without bound). Removed once
  `estimate_pressure_for_target_stretch` made calibrating pressure per net
  up front the real fix, rather than clamping a badly-chosen one after
  the fact.

## Pressure calibration: bracket-then-bisect

Added after a user reported calibration failing to reach a 60% RMS
stretch target on `hippo.json` at Level 1. Traced the single-rescale-only
algorithm's failure: pressure 0.165 gave 9.55% stretch; naive rescale
(ratio ≈6.3x, clamped to `_PRESSURE_RATIO_CLAMP`'s max of 5x) jumped to
0.827, which DIVERGED (70,185% — a real numerical blow-up); the next
rescale (ratio ≈0.00086, clamped to min 0.2x) landed back near the
ORIGINAL 0.165 — repeating forever, since one multiplicative rescale
can't remember "seen one too low, one too high" and narrow the gap.

Fix: track an explicit bracket (`lo_pressure`: largest sane pressure at or
under target; `hi_pressure`: smallest insane/over-target pressure). Once
both exist, every trial bisects the midpoint instead of rescaling — the
only way to converge once the mesh's pressure response turns out sharply
nonlinear. Before a bracket exists, behavior is unchanged from the
original (rescale-by-ratio). Verified: doesn't regress the well-behaved
10%-target case on all 5 Platonic solids + `three_squares.json`; the
reported `hippo.json` 60% case reaches 56.13% at pressure 0.434
(previously stuck oscillating at 9.55%).

Also tracks whichever SANE trial landed closest to target, not just the
last one — a trial's rescale assumes more pressure means more stretch,
false on `three_squares.json` (stretches LESS as pressure rises, a real
property of that topology), so without tracking the best result that case
would escalate pressure forever chasing a target moving away from it.

## Explicit step size scaling

`dt = min(STEP_MAX_MULTIPLIER * scale, STEP_MAX_FRACTION * scale /
max_force)`, both terms scaled by `scale` (current rest-edge-length
scale). Without the `scale` factor, a fixed absolute cap represents a
shrinking fraction of edge length as the mesh subdivides finer (rest
lengths halve each level) but a growing one as it coarsens.

Missing until a user reported a single concave vertex sometimes stuck
failing to "pop out." Investigation found `STEP_MAX_MULTIPLIER = 0.05`
(unscaled) was already ~28% of an edge length at Level 3 (`scale≈0.18`
for a cube) vs. the intended "5%" at Level 0/1 (`scale≈1`) — stable at
Level 3 by coincidence, needlessly tiny (slow to correct) at coarser
levels. Verified stable through `STEP_MAX_MULTIPLIER=0.3` (6x old value)
on cube/tetrahedron/icosahedron at pressures 1 and 3; a genuine 2-cycle
reappears at 0.4+. Settled on **0.2**. (icosahedron at pressure=5
diverges regardless of step size — pre-existing behavior, not a
regression.)

`STALL_WINDOW` raised 200 → 2000 for the same report: a genuinely slow
but real correction could plateau-trigger the old stall criterion before
actually finishing. Kept ≤ `INFLATE_CHUNK_MAX` for `KICK_WINDOW` but
deliberately raised PAST `INFLATE_CHUNK_MAX=200` for `STALL_WINDOW` — a
chunked in-app run can no longer coincidentally fill exactly one window.
`INFLATE_SAFETY_STEP_CAP` raised 5000 → 20000 alongside it.

## Rigid-motion removal

Spring forces are torque-free by construction; a CLOSED mesh's pressure
forces are too (hydrostatic identity), but an OPEN net's aren't and CAN
accumulate net torque — verified near-zero torque on `cube.json` (closed)
vs. large persistent torque on `hippo_torso.json` (open, 13 boundary
edges) — matching a user's report of the mesh spinning in place mid-
Inflate with no shape change. Fixed via Kabsch/orthogonal-Procrustes
best-fit rigid alignment to the previous step's frame (SVD of centered
cross-covariance, with `det`-sign correction against reflection).
Verified: never affects stretch/convergence (rigid transform = isometry,
`max_stretch_pct` matches to ~10 significant figures with/without the
fix); recovers a synthetic known rotation+translation+deformation;
end-to-end on `hippo_torso.json`, a tracked reference direction drifts
noticeably less with the fix. Cost: one `(N,3)x(N,3)` product + one 3x3
SVD per step, negligible next to the force computation.

## The "kick" (escaping a local minimum)

Follow-up to rigid-motion removal, same "head not popping out" report.
Tracked the worst vertex's force on `hippo_head.json` over 30,000 steps:
oscillating in a fixed band, never trending down — a genuine local-
minimum "dimple," not a slow correction. Disproved the user's own
hypothesis (bigger step size) directly: tried multipliers 0.2–1.5x edge
length, got worse; raising pressure just diverges past a critical value
(same divergence with unmodified code, ruling out a regression). Root
cause: the worst vertex has DEGREE 2 (only 2 triangles) — confirmed
across all 8 tested seeds; confirmed this mesh is a cut-out piece of
`hippo.json`, which has no degree-2 vertices (min degree 4) and converges
cleanly in 69 steps — the weak bracing is an artifact of testing the
piece standalone.

Chosen fix (over "add integrator momentum" or "fix the net data"): when
`max_force` hasn't dropped to `KICK_STALL_RATIO` (0.5) of its value
`KICK_WINDOW` steps ago, nudge every vertex by Gaussian noise scaled by
`KICK_MAGNITUDE_FRACTION * scale` (0.3), weighted by that vertex's own
force relative to the worst one. `KICK_WINDOW` (150) deliberately kept ≤
`INFLATE_CHUNK_MAX` (200) — a first draft at 500 fired zero kicks over
20,000 chunked steps through the app's actual UI, since a bigger window
can never fill within one chunk; 150 fired ~100.

Honesty check: does NOT fully rescue `hippo_head.json` standalone even
after the fix — that vertex is weakly-braced enough that no reachable
nearby configuration is a real equilibrium. It DOES work for a vertex
that's stuck but has some reachable escape. The reliable fix for this
class of problem is testing the full assembled net, not a cut-out piece.

## Orientation/fold check removed from the interactive loop

An earlier `_run_inflate_stream` rejected a chunk whenever
`is_orientation_consistent` failed. False-positived on non-convex/open
nets — `two_pentagons_and_a_square.json` subdivided to level 1 flagged as
"folded" even at rest. A more targeted reference-based replacement
(comparing each internal edge's fold sign against a known-good start)
fixed the at-rest false positive but still rejected the net a few real
steps into inflation (some folds sit nearly flat at rest, a consequence
of two faces sharing >1 edge, so a normal step tips one across zero).
Letting `relax_once` run with no check reaches a stable, sensible result
(positive volume, reasonable stretch) — though that patch does stay
locally self-intersecting forever. The user inspected the result and was
fine with it, so the check was removed entirely.

## Validate Mesh: two checks, only one gates pass/fail

An earlier version used the geometric, centroid-relative test as the SOLE
check — a user caught it as wrong: a freshly-loaded cube at Level 0
(pure random noise, before Relax) read as "inconsistent" for no
structural reason, then the SAME UNCHANGED `faces` read as "consistent"
once Relax gave it a coherent shape — i.e. it tracked the current
embedding, not the structural property it claimed to check, even though
winding consistency is a property of `faces` alone (provably unchanged
between Level 0 and 1). Fixed by making the combinatorial check
authoritative and demoting the geometric one to a labeled, non-gating
side note.

## Debug mode vs. release mode: unified to one difference

The two modes used to have substantially different layouts (separate
Net/Subdivide/Inflate frame sets, a "Sync rotation" checkbox only in one,
workflow enforcement only in the other, the success message suppressed
only in one). All unified away at the user's request down to the ONE
remaining difference: whether "Iterate for N steps" is offered.
`_apply_mode_visibility` is now just showing/hiding `self.mode_row` and
resetting `iterate_mode_var` to `"convergence"` when leaving debug mode.

Also consolidated: one action button per level (not two — an earlier
design had a top Inflate/Relax button plus a separate bottom
Subdivide/DONE button); no separate Stop button (the frontier level's own
button turns into Stop for the run's duration); no "Sync rotation"
checkbox (rotation is just always synced via one shared
azim/elev); the green "success" status message is always suppressed
(redundant with the per-level button state / Convergence History table).

## Convergence History: per-row target/gtol snapshot

A user reported every row showing the SAME "(target: N)" — because the
table read `self.target_rms_var.get()` LIVE for every row instead of each
row's value at calibration time. Fixed the same way `self._current_gtol`
already was: `self._current_target_rms_pct` is set wherever the spinner
value is set to a level default (and again in `on_inflate_clicked` in
case the user edited it first), threaded through `level_history`, and
read per-row instead of from the live spinner.

## Performance

Vectorizing `_mesh_volume`/`_per_face_volumes` (precomputed flat index
arrays, `np.bincount` grouping, instead of a per-face Python loop with a
dict lookup rebuilt every force evaluation) gave a single `relax_once`
call on a level-3 mesh (hundreds of variables) a ~50x speedup, down to a
few hundredths of a second.

## Auto button state machine

`_auto_step` (called once to start, then again from the tail of
`_finish_relax`/`_finish_inflate` every time a step it started actually
finishes — a no-op on a plain manual click) drives: not yet converged at
current level → retry Relax/Inflate there (`_auto_try`, bounded by
`AUTO_MAX_RETRIES_PER_LEVEL=10` so a genuinely unreachable target doesn't
retry forever); just converged, below `MAX_LEVEL` → Subdivide then
immediately re-enter `_auto_step` in the same call (Subdivide is
synchronous, schedules no callback of its own); just converged at
`MAX_LEVEL` → done. `self._auto_retry_level` tracks which level the retry
count applies to, compared at the top of every call, rather than
resetting the counter by hand at each of the several places the level
changes.

The button becomes "Stop Auto" and stays enabled through the run despite
the blanket control-disable (added to that disable's own widget
exception list, mirroring the frontier per-level button's exception).
`on_auto_stop_clicked` and a direct per-level Stop click both call
`_abort_auto` — clicking Stop directly while Auto is running halts the
whole sequence, not just the current step. Also called from both
worker-thread failure paths, so a genuine exception doesn't leave the
button stuck reading "Stop Auto" forever.

Verified headless on `cube.json`: one `on_auto_clicked` call converges
cleanly to Level 3 with no further interaction; `on_auto_stop_clicked`
mid-run updates state synchronously without waiting for the interrupted
background run to finish.

## PyVista rendering gotchas

- **Title centering**: `add_text(..., position="upper_edge")` returns a
  `vtkCornerAnnotation`, which despite the name left-justifies starting
  AT the horizontal center (visibly off-center right). Fixed with a plain
  text actor at a normalized-viewport position plus an explicit
  `SetJustification(vtk.VTK_TEXT_CENTERED)` call.
- **`parallel_scale` aspect ratio**: it only directly controls vertical
  half-height, so left uncorrected the shape's wider dimension gets
  cropped on this app's portrait-shaped panels — multiply by
  `panel_height/panel_width` to correct. `LEVEL_ZOOM_FILL=0.6` then
  shrinks the shape within the guaranteed-fitting frame per user request.
- Chosen over mplot3d/`_CullableFace` because a mid-solve mesh is
  routinely self-intersecting/non-convex, which neither mplot3d's
  painter's-algorithm sort nor the old exact-normal culling (valid only
  for closed convex solids) could draw correctly — PyVista's real GPU
  depth buffer handles arbitrary triangle soups.
- Rendered off-screen (`pv.Plotter(off_screen=True)`, `.screenshot`
  wrapped in `PIL.ImageTk.PhotoImage` on a plain `tk.Label`) rather than
  an embedded live VTK widget, to keep the app on one interaction toolkit.

## Removed UI elements (no longer present, don't resurrect without asking)

- A bottom-of-figure text annotation repeating level/iteration/stretch —
  redundant with the Convergence History table.
- A standalone "Auto" (calibrate-without-inflating) button and a
  Pressure readout label — removed once Inflate itself started
  calibrating pressure, and the history table started showing it.
- A "Save" button writing positions/stats + a PNG under
  `data/output/Save/`.
