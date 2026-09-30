# Stretchy-mesh solver (`src/utils/inflate_polyhedron/`)

Split across several files (2026-09-30, explicit modularization request): `stretchy_mesh.py`
holds the loader, mesh geometry helpers, shared low-level force primitives, and `relax_once`
(Level 1+). `pre_inflation_relaxer.py` holds Level 0's `relax_initial_configuration`.
`multi_trial_inflater.py` holds pressure calibration (`estimate_pressure_for_target_stretch`).
`convergence_checker.py` holds the periodic stopping check. `mesh_stretch_checker.py` holds
solved-positions -> max/RMS stretch %. `self_join_triangulator.py` splits a self-joined face at
net-load time (currently wired into `inflate_polyhedron_app` only, not `interactive_inflater_app`
-- see apps.md). Each of the first five depends on `stretchy_mesh.py` for shared primitives, not
the other way around, so `stretchy_mesh.py` never imports any of them. The rest of this doc
refers to function names without repeating which file each now lives in.

For nets that can't stay rigid+flat (faces sharing >1 edge — geometrically forces coplanarity,
no dihedral fold possible). See `docs/algorithm.md` for full scientific writeup; this is the
Claude-facing state summary. **Keep both in sync when changing the physics.**

## Format & winding
Vertex-loop JSON, no coords: `{"faces":[[v,v,v,...],...]}`. CCW from outside. Shared edge =
`v->w` one face, `w->v` other. `load_stretchy_mesh` only rejects a DUPLICATE directed edge — an
edge with no reverse partner is a valid open boundary (mesh need not be closed 2-manifold).

## Pipeline
1. `random_initial_positions` — iid uniform noise, no meaning.
2. `relax_initial_configuration` (Level 0, "Relax" button) — PLAIN LINEAR spring only, no
   pressure. Needs mesh pre-triangulated (fan about centroid) or it's a floppy mechanism.
   Repulsion is gated per vertex per step: a vertex's own repulsion force is zeroed whenever it
   dots negative against that vertex's own outward normal (`_vertex_outward_normals` —
   face-winding-based, same convention `_relax_force`'s pressure term uses). No global
   orientation fix-up — orientation is left exactly as the physics settles it.
   A periodic "jiggle" (`LEVEL0_JIGGLE_INTERVAL_STEPS`/`LEVEL0_JIGGLE_DISTANCE_FRACTION`) nudges
   every vertex along its own outward normal to jog a locally-stuck region loose; gated so it
   never fires on the same step as a convergence check.
3. Promote to Level 1 (same topology, no re-subdivide needed).
4. `relax_once` ("Inflate") — pressure-driven, HARDENING spring (see below). One call = fixed
   pressure; app recalibrates pressure fresh every Inflate click.
5. `mesh_levels.subdivide_once` ("Subdivide", up to MAX_LEVEL=3) — quarters triangles via
   midpoints; positions interpolated from current (stretched) mesh, rest lengths derived from
   ORIGINAL flat unit-edge geometry (not current positions) so target shape doesn't drift across
   levels.

## Force model
- **Level 0** (`_spring_only_force`): plain Hooke, `f = stretch`. Deliberately NOT hardening —
  no pressure to resist there, and plain linear settles faster. Own step constant
  `LEVEL0_STEP_MAX_MULTIPLIER = 0.1`.
- **Level 1+** (`_relax_force`): HARDENING spring, `f = stretch + c*stretch^3`,
  `c = HARDENING_CUBIC_COEFFICIENT = 0.5`. Needed because plain linear can't hold pressure past a
  critical value (pressure push ~area~length^2, linear spring pull only ~length) — real rubber
  avoids this via strain-stiffening, this is the model analogue. Own step constant
  `STEP_MAX_MULTIPLIER = 0.05`.
  - **No hacky terms rule**: don't add a volume/target-volume term or a stretch clamp to this
    force model without the user explicitly asking — both were tried and rejected (papered over
    a symptom instead of the physics). The hardening term and the adaptive step-shrink removal
    (Integration, below) are both settled/current; don't reintroduce a step-shrink term or a
    calibration-only step multiplier without new explicit permission.
- Each face: `pressure * area * outward_normal` (Newell's method), split across vertices. No
  planarity regularizer — the app's own pipeline fan-triangulates every face before Level 0/1
  ever run, so no face reaching `_relax_force` is ever 4+-gon in practice.
- **All-pairs repulsion** (`repulsion_force`, `REPULSION_STRENGTH`/`MIN_REPULSION_DISTANCE`):
  inverse-square, used by every relax force. Weak relative to spring stiffness — only
  meaningfully pushes vertices already close together. `repulsion_vertex_ids` can restrict it to
  a fixed small subset (app passes Level 0's own vertices at every level, to keep cost from
  growing with subdivision); `repulsion_vertex_multipliers` can weaken it per-vertex.
- **`pressure_exclude_faces`** (`_face_index_groups`): an "open" wedge triangle (outer edge not
  glued to another polygon) gets no pressure force at all — still fully present for
  edges/repulsion/convergence. Also excludes those faces from the Level-0 jiggle's own normal.

## Integration
`dt = step_max_multiplier * scale` (`scale` = mesh's own rest edge length) — the whole step size,
no adaptive shrink term. Explicit stepping (not Newton/least_squares) deliberately — a
linearized solver can jump to a spurious equilibrium (doubled-size stretched "solution",
near-zero-volume implosion) a real small-step walk would never reach.

`_remove_rigid_motion` (Kabsch alignment) runs every step against the run's FIXED starting
positions (not a rolling reference) — a free-floating system has no fixed orientation, and an
OPEN net can accumulate real net torque over many blocks if aligned only against the previous
block. Isometry, so never affects stretch/convergence stats.

## Convergence
Checked only every `CONVERGENCE_CHECK_INTERVAL = 200` steps (not every step). Compares the worst
vertex's own displacement since the last check against `200 * gtol`. `CONVERGENCE_GTOL = 1e-4`
(module default). No stall/plateau shortcut — a run ends only via the real gtol check,
`stop_event`, or `max_nfev`/`INFLATE_SAFETY_STEP_CAP` (app-level hard cap, currently 50000).

`rng` param (`KICK_WINDOW=150, KICK_STALL_RATIO=0.5, KICK_MAGNITUDE_FRACTION=0.3`): opt-in random
perturbation when a vertex's force hasn't dropped by half in 150 steps (escapes a genuine
local-minimum "dimple"). App currently passes `rng=None` (disabled) for Relax/Inflate — found to
interact badly with a genuinely slow (not stuck) relaxation.

## Progress callback
`relax_once`/`relax_initial_configuration` take `on_progress(positions, steps, max_stretch,
rms_stretch, optimality, converged)`, called every `CONVERGENCE_CHECK_INTERVAL` steps via
`_explicit_relax_loop`'s own `on_check` hook — same cadence the stopping condition itself is
checked at. One call per run (no app-side chunking).

## Pressure calibration (`estimate_pressure_for_target_stretch`)
Initial guess `pressure = k * (target_pct/100) / total_rest_area`, `k ≈ 25`
(`_PRESSURE_AREA_PRODUCT_ESTIMATE`, from bisecting 10%-stretch pressure on the 5 Platonic
solids). Refines via bracket-then-bisect once both a sane-under-target and an insane-or-over-
target trial exist; before that, rescales by `target/achieved` clamped to `[0.2x, 5x]` per step.
Keeps whichever SANE trial got closest to target (not just the last), since stretch isn't always
monotonic in pressure (`three_squares.poly` stretches LESS as pressure rises).
`max_nfev_per_trial = 5000` is a search-time budget only — the WINNING trial, once chosen, is
topped up with one further uncapped `relax_once` call (capped by `MAX_UNBOUNDED_STEPS`) if it
hadn't actually converged yet. `stop_event` is forwarded and interrupts calibration, including
the top-up.

Every trial uses the EXACT same step size/budget a real Inflate run would use — no
calibration-only step multiplier. A trial that diverges numerically
(`_remove_rigid_motion`'s SVD raising `LinAlgError` on NaN/Inf positions) is caught and treated
as an ordinary insane/over-target trial (`_DIVERGED_SENTINEL_STRETCH_PCT`) rather than crashing.

**Initial guess from prior-level history**: `estimate_pressure_for_target_stretch` takes an
`initial_pressure_guess` param that, when given, replaces the generic geometric guess (which
only scales with `target_pct`, not subdivision level, so on its own it under-guesses every level
past the first). `inflate_polyhedron_app`'s `_guess_pressure_from_history` computes this from
whichever PRIOR level's own recorded `(pressure, rms_stretch_pct)` pair landed CLOSEST to the
new target, scaled by `2^(level difference)` (each Subdivide roughly doubles the pressure needed
for the same target RMS). Not a `new_target / prior_achieved` rescale — that ratio explodes when
a prior level's own achieved stretch is ~0.

**Unresponsive-mesh stall detection.** If `_STALL_TRIAL_LIMIT` (2) consecutive rescale-phase
trials land within `_STALL_DELTA_PCT` (1e-6) of each other despite pressure being rescaled by up
to 5x, the mesh is judged unresponsive to pressure at this level (e.g. a ravioli-paired mesh
whose two identical, opposite-wound faces cancel pressure exactly) and the search gives up
rather than escalating pressure without bound. Return value gains `pressure_found` (False in
this case, though `converged` can still be True) so `_guess_pressure_from_history` can exclude
this level's pressure from later levels' starting guess.

## Defaults (current)
- `LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 5.0, 2: 5.0, 3: 5.0}` (app, per-level spinner default);
  `DEFAULT_TARGET_RMS_STRETCH_PCT = 5.0` (module's own fallback, same value)
- `DEFAULT_TOLERANCE = 1e-4` (app's Tolerance spinner default)
- `CONVERGENCE_GTOL = 1e-4` (module default when no gtol passed)
- `INFLATE_SAFETY_STEP_CAP = 50000` (app, hard per-attempt step cap)
- `HARDENING_CUBIC_COEFFICIENT = 0.5`, `STEP_MAX_MULTIPLIER = 0.05`, `LEVEL0_STEP_MAX_MULTIPLIER = 0.1`
- `CONVERGENCE_CHECK_INTERVAL = 200`

## Auto (app)
One Relax/Inflate attempt per level (`_auto_attempted_level` tracks this) — NOT retried with a
fresh pressure recalibration on failure. If the one attempt (up to `INFLATE_SAFETY_STEP_CAP`)
doesn't converge, Auto stops and reports it plainly.
