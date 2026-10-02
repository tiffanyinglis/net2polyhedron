# Stretchy-mesh solver (`src/utils/inflate_polyhedron/`)

Split across several files (2026-09-30, explicit modularization request): `stretchy_mesh.py`
holds the loader, mesh geometry helpers, shared low-level force primitives, and `relax_once`
(Level 1+). `pre_inflation_relaxer.py` holds Level 0's `relax_initial_configuration`.
`multi_trial_inflater.py` holds pressure calibration (`estimate_pressure_for_target_stretch`).
`convergence_checker.py` holds the periodic stopping check. `mesh_stretch_checker.py` holds
solved-positions -> max/RMS stretch %. `self_join_triangulator.py` splits a self-joined face at
net-load time (currently wired into `inflate_polyhedron_app` only, not `interactive_inflater_app`
-- see apps.md). `inside_out_checker.py` holds `InsideOutChecker` (below). Each of these depends
on `stretchy_mesh.py` for shared primitives, not the other way around, so `stretchy_mesh.py`
never imports any of them. The rest of this doc refers to function names without repeating which
file each now lives in.

**Inside-out detection (`InsideOutChecker`, 2026-09-30, explicit).** Diagnosed on
tetrahedron.poly: at Level 2+, some seeds have a genuine, converged but globally INVERTED
equilibrium at LOW pressure (signed volume flips sign; stretch % roughly FLAT across a wide
low-pressure range instead of scaling with pressure -- a spurious branch, not real physics) with
a real, correctly-oriented equilibrium reachable only at meaningfully higher pressure. Before
this fix, such a trial read as an ordinary sane-but-over-target trial, so the bracket search
LOWERED pressure in response -- driving it deeper into the spurious branch and never finding the
correct one. `estimate_pressure_for_target_stretch` now builds one `InsideOutChecker` per call
(reference = the search's own starting `positions`) and checks every sane trial's result against
it; an inside-out trial is excluded from best-candidacy and always forces pressure UP (bisecting
against a confirmed hi_pressure if one exists, else `pressure *= _PRESSURE_RATIO_CLAMP[1]`)
rather than trusting its own rms_stretch reading to pick a direction. A burst of real pressure at
the very start of Level 0 (tried and rejected the same day) had no effect -- Level 0/1 were
already orientation-consistent for every seed tested, and the flip reproduced fresh, inside
Level 2's own relax_once call, regardless.

Separately noted, NOT yet fixed: some already-correctly-oriented seeds still land far from a 5%
target (e.g. ~30% stretch) because the geometric initial pressure guess overshoots and the
halving-only pre-bracket search has no way to try pressure HIGHER than that first guess once it
reads as over-target -- a different, pre-existing limitation of the bracket search, out of scope
for the inside-out fix above.

**Level 0 orientation retry (2026-09-30, explicit).** The InsideOutChecker fix above only
catches a flip introduced AFTER Level 0 -- if Level 0 itself already converges to a bad
orientation, every later level inherits it uncaught (`InsideOutChecker`'s own reference is
whatever Level 0 produced). Confirmed real: Level 0's spring+repulsion relax can converge to a
genuinely MIXED (both +1 and -1 present -- a real, locally self-folded shape) orientation for
several shipped nets (tetrahedron seed 19, cube seed 8, octahedron seed 4, ravioli seeds
1/2/4/10/15-19 -- ravioli especially prone, ~45% of seeds tried, since its own cancelling-
pressure pathology gives springs+repulsion nothing to push it toward a consistent fold). Two
pieces, in `pre_inflation_relaxer.py`:
- **Burst** (2026-10-01, standardized name -- see below for both uses): a shot of outward-biased
  force/displacement meant to nudge the mesh toward a winding-consistent, non-self-folded shape.
  Two flavors, both in `pre_inflation_relaxer.py`:
  - **Initial burst** (`LEVEL0_INITIAL_BURST_PRESSURE=0.1`, raised from 0.05 2026-10-01 explicit
    "make the Level 0 bursts stronger"; `LEVEL0_INITIAL_BURST_STEPS=200`): a
    few steps of plain-linear spring + a small amount of real PRESSURE (`_pressure_only_force`,
    NOT the hardening spring -- that explodes combined with pressure on raw random noise), run
    ONCE, before repulsion ever starts inside `relax_initial_configuration` itself. Pressure's
    direction is tied to each face's own winding, unlike repulsion (no outward notion at all), so
    this biases Level 0 toward a winding-consistent shape. Reduces the failure rate (fixed 2 of 5
    worst-case seeds tested alone) but doesn't eliminate it -- ravioli's pressure-cancellation
    pathology defeats it structurally.
  - **Periodic burst** (`LEVEL0_PERIODIC_BURST_INTERVAL_STEPS=50`,
    `LEVEL0_PERIODIC_BURST_DISTANCE_FRACTION=0.6`, raised from 0.4 2026-10-01 explicit "make the
    Level 0 bursts stronger"): after the initial burst, Level 0 runs
    spring + gated repulsion only, but every 50 steps every vertex gets a one-step DISPLACEMENT
    kick along its own outward normal -- gated so it only fires while the mesh hasn't yet been
    reported converged by the most recent check, i.e. convergence is always tested BEFORE a
    periodic burst can fire, never after (this gating was previously called a "jiggle";
    standardized to "burst" to match the initial one, same underlying idea, just repeated instead
    of one-time).
- **Seed retry backstop** (`relax_initial_configuration_with_orientation_retry`,
  `LEVEL0_ORIENTATION_MAX_RETRIES=5`): runs Level 0 up to 5 times from fresh seeds (seed,
  seed+1, ...), accepting the first fully-consistent result. If every attempt stays bad, keeps
  whichever had the fewest disagreeing faces. Returns a 7th value, `seed_used`, since the result
  can come from a different seed than requested -- callers that display/store a seed
  (`inflate_polyhedron_app`'s own Seed field) must update it to this value.

  **Time-bounded + shared with `interactive_inflater_app`** (2026-10-01, explicit: "create a
  class called seed_selecter... this logic should apply to interactive_inflater as well when
  running full inflate... have a time cutoff, say 10s"). The attempt-budget loop itself was
  factored out into `seed_selecter.SeedSelecter` (`select(seed, attempt_fn, score_fn,
  on_attempt=, should_stop=)`) — a generic, mesh-agnostic "try N seeded attempts, keep the best,
  stop early on a good-enough score or a time/count budget" policy; `relax_initial_configuration_
  with_orientation_retry` supplies the orientation-specific `attempt_fn`/`score_fn`/print
  diagnostics and is otherwise unchanged. New `max_search_time` param
  (`LEVEL0_ORIENTATION_MAX_SEARCH_TIME=5.0`s, aliasing `SeedSelecter`'s own default, lowered from
  10.0s on 2026-10-01): the FIRST attempt always runs in full regardless of duration, but attempt
  2+ only starts if cumulative time so far is still under budget — a model slow enough for one
  attempt to approach 5s gets exactly one attempt. Deliberate, not just a safety valve: a bigger/more-braced mesh is
  empirically unlikely to hit the all-faces-flipped failure mode this retry targets, so spending
  MORE search time on the inputs that need it least would be wasted. `interactive_inflater_app`'s
  own `on_full_inflate_clicked` now calls this same function (`LEVEL0_SEED=0` as the fixed
  starting seed — that app has no seed display/entry of its own) instead of calling
  `relax_initial_configuration` directly with no retry at all, as it did before.

  **Checks the BASE (macro) faces, not the fan-triangulated ones** (`base_faces` param, checked
  instead of `faces` when given). Diagnosed 2026-09-30: checking the fan-triangulated mesh
  directly is unreliable -- a macro face's own fan HUB vertex (added purely so a spring-only
  relax has something rigid to work with) can bulge outward on its own, making every one of that
  face's fine sub-triangles read "points away from centroid" even while the ACTUAL macro polygon
  (the plane through its real, non-hub corners) is caved INWARD -- a small pointy bump poking out
  of an otherwise inside-out shell, reported as a user-visible "caved-in tetrahedron" bug. Both
  the per-face check AND `mesh_volume`'s own sign were fooled by this on the fan mesh; checking
  `base_faces` (same vertex ids, no remapping needed) catches it correctly.

  **A UNIFORMLY flipped result (all -1, no local disagreement) is NOT fixed via a mirror** --
  tried, then reverted the same day: concavity is reflection-INVARIANT (mirroring a caved-in
  shape gives another, equally caved-in shape, just chirality-flipped), so a uniform -1 reading
  isn't reliable evidence the shape is otherwise a genuinely non-concave "just backwards"
  embedding -- it can just as easily mean a real caved-in shape that happens to uniformly fail
  this check. Uniform and mixed failures are both just retried.

  Verified: the tetrahedron seed that originally surfaced the caved-in bug (1395581472) reads
  "uniformly flipped" for 3 straight attempts before landing on a genuinely consistent one at
  attempt 4. Separately, re-scanning the ORIGINAL 5 worst-case seeds (tetrahedron/cube/
  octahedron/ravioli) with the CORRECTED macro-face check still resolves all 5 cleanly.

  **Discarded attempts never reach the UI** (2026-09-30, explicit -- "you don't need to replay
  the failed seeds"): `on_progress` is never forwarded live while an attempt is still just a
  candidate -- each attempt's own progress calls are buffered in memory instead, and only
  replayed through the real `on_progress` once that attempt is settled on (accepted outright, or
  kept as the least-bad fallback). The returned `steps_taken` is that ONE attempt's own count,
  never a sum across every attempt tried -- a caller's step counter (`inflate_polyhedron_app`'s
  own "Steps" column) never counts work that was silently discarded.

  **Not yet solved**: the real crochet-animal nets (giraffe, goose, hoodie, cannoli variants) fail
  this check on EVERY one of 5 retries, consistently (30-67% of macro faces flipped each time,
  same seed base) -- unlike the simple closed Platonic solids, 5 random reseeds isn't remotely
  enough for these; the failure rate per seed looks close to universal for this seed range, not a
  rare fluke. Needs a different approach (stronger/longer burst, per-face local repair, or
  something else) -- flagged, not fixed.

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
   calibrated pressure. Needs mesh pre-triangulated (fan about centroid) or it's a floppy
   mechanism. Runs an INITIAL burst (200 steps of spring + small fixed pressure) once, before
   repulsion ever starts; after that, spring + gated all-pairs repulsion only, with a PERIODIC
   burst (a one-step outward-normal displacement kick) every 50 steps, gated so it only fires
   while the mesh hasn't yet been reported converged by the most recent check. Repulsion is
   gated per vertex per step: a vertex's own repulsion force is zeroed whenever it dots negative
   against that vertex's own outward normal (`_vertex_outward_normals` — face-winding-based,
   same convention `_relax_force`'s pressure term uses). No global orientation fix-up —
   orientation is left exactly as the physics settles it.
3. Promote to Level 1 (same topology, no re-subdivide needed).
4. `relax_once` ("Inflate") — pressure-driven, HARDENING spring (see below). One call = fixed
   pressure; app recalibrates pressure fresh every Inflate click.
5. `mesh_levels.subdivide_once` ("Subdivide", up to MAX_LEVEL=3) — quarters triangles via
   midpoints; positions interpolated from current (stretched) mesh, rest lengths derived from
   ORIGINAL flat unit-edge geometry (not current positions) so target shape doesn't drift across
   levels.

## Force model
- **Level 0** (`_spring_only_force`): plain Hooke, `f = stretch`. Deliberately NOT hardening —
  plain linear settles faster, and the hardening term's cubic can explode combined with
  `_pressure_only_force` on raw random noise. Own step constant `LEVEL0_STEP_MAX_MULTIPLIER = 0.1`.
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
  edges/repulsion/convergence. Also excludes those faces from the Level-0 periodic burst's own
  normal.

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

**Stall detection removed (2026-10-01, explicit -- "stall detection confirmed not needed. you can
delete it now").** Previously, 2 consecutive rescale-phase trials landing within 1e-6 pct of each
other (e.g. a ravioli-paired mesh whose two identical, opposite-wound faces cancel pressure
exactly) would make the search give up early with `pressure_found=False`. Now the rescale phase
just keeps rescaling by `target/achieved` (clamped to `[0.2x, 5x]`) for the full `max_iterations`
budget regardless -- an unresponsive mesh just burns through its iteration budget rather than
bailing out early. `pressure_found` is now False only when every trial within `max_iterations`
was insane.

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
