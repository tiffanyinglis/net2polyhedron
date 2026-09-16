# Stretchy-mesh solver (`src/utils/inflate_polyhedron/stretchy_mesh.py`)

For nets that can't stay rigid+flat (faces sharing >1 edge — geometrically forces coplanarity,
no dihedral fold possible). See `docs/algorithm.md` for full scientific writeup; this is the
Claude-facing state summary. **Keep both in sync when changing the physics.**

## Format & winding
Vertex-loop JSON, no coords: `{"name","faces":[[v,v,v,...],...]}`. CCW from outside. Shared edge
= `v->w` one face, `w->v` other. `load_stretchy_mesh` only rejects a DUPLICATE directed edge —
an edge with no reverse partner is a valid open boundary (mesh need not be closed 2-manifold).

## Pipeline
1. `random_initial_positions` — iid uniform noise, no meaning.
2. `relax_initial_configuration` (Level 0, "Relax" button) — PLAIN LINEAR spring only, no
   pressure. Needs mesh pre-triangulated (fan about centroid) or it's a floppy mechanism.
   Orientation not guaranteed: uniform inside-out fixed free via centroid reflection; mixed
   result passed on to pressure stage as-is.
3. Promote to Level 1 (same topology, no re-subdivide needed).
4. `relax_once` ("Inflate") — pressure-driven, HARDENING spring (see below). One call =
   fixed pressure; app recalibrates pressure fresh every Inflate click.
5. `mesh_levels.subdivide_once` ("Subdivide", up to MAX_LEVEL=3) — quarters triangles via
   midpoints; positions interpolated from current (stretched) mesh, rest lengths derived from
   ORIGINAL flat unit-edge geometry (not current positions) so target shape doesn't drift across
   levels.

## Force model
- **Level 0** (`_spring_only_force`): plain Hooke, `f = stretch`. Deliberately NOT hardening —
  no pressure to resist there, hardening's smaller tuned step size only slowed it down and,
  combined with the kick mechanism, caused false "stuck" jiggling. Own step constant
  `LEVEL0_STEP_MAX_MULTIPLIER = 0.2`.
- **Level 1+** (`_relax_force`): HARDENING spring, `f = stretch + c*stretch^3`,
  `c = HARDENING_CUBIC_COEFFICIENT = 0.5`. Added because plain linear can't hold pressure past a
  critical value (pressure push ~area~length^2, linear spring pull only ~length) — real rubber
  avoids this via strain-stiffening (two-balloon experiment), this is the model analogue. Was
  pure quartic (`stretch^3` alone) briefly — reverted for `+ c*stretch^3` because pure cubic
  decays as a power law near rest (slow), not exponentially like linear. `c=0.5` chosen as
  compromise (was 1.0). Own step constant `STEP_MAX_MULTIPLIER = 0.05` (re-verified stable
  after `c` changed 1.0->0.5, boundary barely moved).
  - **No hacky terms rule**: don't add a volume/target-volume term or a stretch clamp to this
    force model without the user explicitly asking. Both were tried before, both papered over
    a symptom (rejected — see git history). The hardening term above is allowed because the
    user explicitly asked for exactly it.
- Each face: `pressure * area * outward_normal` (Newell's method), split across vertices.
  4+-gon faces get a weak SVD-best-fit-plane restoring pull (planarity regularizer).

## Integration
`dt = step_max_multiplier * scale` (`scale` = mesh's own rest edge length). Originally
`min(step_max_multiplier*scale, 0.2*scale/max_force)` (adaptive shrink when force large) — the
adaptive half is CURRENTLY REMOVED as an active experiment (flat `dt` only). `STEP_MAX_FRACTION`
constant (the removed term's own numerator) was deleted as dead code once nothing referenced it.
Explicit stepping (not Newton/least_squares) deliberately — a linearized solver can jump to a
spurious equilibrium (doubled-size stretched "solution", near-zero-volume implosion) a real
small-step walk would never reach.

`_remove_rigid_motion` (Kabsch alignment) runs every step — a free-floating system has no fixed
orientation, and an OPEN net (unlike closed) can accumulate real net torque, causing visible
spinning with no real shape change. Isometry, so never affects stretch/convergence stats.

## Convergence
Checked only every `CONVERGENCE_CHECK_INTERVAL = 200` steps (not every step) — CURRENTLY AN
ACTIVE EXPERIMENT, easy to revert to every-step. Compares the worst vertex's own displacement
since the last check against `200 * gtol` (also an active experiment: was comparing worst-vertex
FORCE against `gtol` every step; renamed the reported value from `max_force` to `optimality`
since it's no longer necessarily force). `CONVERGENCE_GTOL = 1e-4` (module default).

**Stall/plateau shortcut REMOVED entirely** (was: converge if `max_stretch_pct` range over 2000
steps < 1%). Removed because it was `gtol`-independent — at a tight gtol (e.g. 1e-5) it declared
"converged" early (~4600 steps, every level), well before the real target was reached. Only ways
a run now ends: real gtol check, `stop_event`, or hitting `max_nfev`/`INFLATE_SAFETY_STEP_CAP`
(app-level hard cap, currently 50000 — judged sufficient alone as the non-gtol exit).

`rng` param (`KICK_WINDOW=150, KICK_STALL_RATIO=0.5, KICK_MAGNITUDE_FRACTION=0.3`): opt-in random
perturbation when a vertex's force hasn't dropped by half in 150 steps (escapes a genuine
local-minimum "dimple", e.g. a weakly-braced degree-2 vertex). App currently passes `rng=None`
(disabled) for Relax/Inflate — found to interact badly with a genuinely slow (not stuck)
relaxation, re-disturbing it right as it converged.

## Progress callback (no more app-side chunking)
`relax_once`/`relax_initial_configuration` take `on_progress(positions, steps, max_stretch,
rms_stretch, optimality, converged)`, called every `CONVERGENCE_CHECK_INTERVAL` steps via
`_explicit_relax_loop`'s own `on_check` hook — same cadence the stopping condition itself is
checked at. Replaced an earlier scheme where `inflate_polyhedron_app` called these functions
repeatedly in a growing sequence of small chunks (5,10,20,...200) purely to get SOME point to
redraw at, unrelated to the solver's real convergence cadence (caused a reported "converges at
515 steps" artifact — 5+10+20+40+80+160=315, +200=515, the earliest the old chunk-boundary-gated
check could ever fire, not the mesh's real behavior). Now one call per run.

## Pressure calibration (`estimate_pressure_for_target_stretch`)
Initial guess `pressure = k * (target_pct/100) / total_rest_area`, `k ≈ 25`
(`_PRESSURE_AREA_PRODUCT_ESTIMATE`, from bisecting 10%-stretch pressure on the 5 Platonic
solids — re-verified unaffected by the `c=1.0->0.5` hardening change, since at ~10% stretch the
cubic term is negligible). Refines via bracket-then-bisect once both a sane-under-target and an
insane-or-over-target trial exist; before that, rescales by `target/achieved` clamped to
`[0.2x, 5x]` per step. Keeps whichever SANE trial got closest to target (not just the last) since
stretch isn't always monotonic in pressure (`three_squares.json` stretches LESS as pressure
rises). `max_nfev_per_trial = 5000` (was 20000). `stop_event` now forwarded and actually
interrupts calibration (see apps.md — this was a real bug: Stop used to do nothing during
calibration since no `stop_event` existed yet at that point).

## Defaults (current)
- `LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 80.0, 2: 40.0, 3: 10.0}` (app, per-level spinner default)
- `DEFAULT_TOLERANCE = 1e-4` (app's Tolerance spinner default)
- `CONVERGENCE_GTOL = 1e-4` (module default when no gtol passed)
- `INFLATE_SAFETY_STEP_CAP = 50000` (app, hard per-attempt step cap)
- `HARDENING_CUBIC_COEFFICIENT = 0.5`, `STEP_MAX_MULTIPLIER = 0.05`, `LEVEL0_STEP_MAX_MULTIPLIER = 0.2`
- `CONVERGENCE_CHECK_INTERVAL = 200`

## Auto (app)
One Relax/Inflate attempt per level (`_auto_attempted_level` tracks this) — NOT retried with a
fresh pressure recalibration on failure (removed: recalibrating pressure from scratch on every
retry was wasted work when the mesh just needed more time at the SAME pressure). If the one
attempt (up to `INFLATE_SAFETY_STEP_CAP`) doesn't converge, Auto stops and reports it plainly.
