"""Level 0's "Relax" step: turns a fresh net's random starting point
(stretchy_mesh.random_initial_positions) into a well-separated 3D shape
using PURE SPRING forces plus all-pairs repulsion -- no pressure at all,
since there's nothing yet for pressure to push against. See physics.md's
Pipeline section for where this sits relative to relax_once (Level 1+'s
real pressure-based inflation, which takes over once this has produced a
usable starting shape) and its own Force model section for why this uses
a plain LINEAR spring rather than relax_once's hardening one.

Shares stretchy_mesh's own low-level primitives (_edge_setup,
_face_index_groups, repulsion_force, _vertex_outward_normals,
_safe_unit_vectors, _explicit_relax_loop) -- this module depends on
stretchy_mesh, not the other way around, so stretchy_mesh never needs to
import this module."""
import numpy as np

from .stretchy_mesh import (
    _edge_setup, _face_index_groups, _safe_unit_vectors, _vertex_outward_normals,
    _explicit_relax_loop, repulsion_force, random_initial_positions, _orientation_signs,
)
from .convergence_checker import CONVERGENCE_GTOL
from .mesh_stretch_checker import positions_and_stretch
from .seed_selecter import SeedSelecter, DEFAULT_MAX_ATTEMPTS, DEFAULT_MAX_SEARCH_TIME

# relax_initial_configuration's OWN step-size cap, separate from relax_once's
# STEP_MAX_MULTIPLIER -- since _spring_only_force is a plain LINEAR spring, not the hardening
# one STEP_MAX_MULTIPLIER is tuned for, sharing that smaller value would needlessly throttle a
# force law that never needed it. See physics.md's Force model section for the current value.
LEVEL0_STEP_MAX_MULTIPLIER = 0.1


def _spring_only_force(pts, edge_ai, edge_bi, edge_length):
    """Pure Hooke's-law LINEAR spring force for relax_initial_configuration
    -- deliberately NOT the hardening term relax_once's own _relax_force
    uses (see stretchy_mesh's module docstring and physics.md's Force
    model section): with pressure=0, there's no outward force for a
    hardening term to guard against, and plain linear settles faster
    near rest. Faces aren't expected to be flat or non-self-intersecting
    at this stage; the only goal is a well-separated, edge-length-
    plausible starting point to hand off to the real per-face pressure
    model afterward."""
    n = pts.shape[0]
    force = np.zeros((n, 3))
    diff = pts[edge_bi] - pts[edge_ai]
    dist = np.linalg.norm(diff, axis=1)
    direction = _safe_unit_vectors(diff)
    stretch = (dist - edge_length) / edge_length
    spring_on_a = stretch[:, None] * direction
    np.add.at(force, edge_ai, spring_on_a)
    np.add.at(force, edge_bi, -spring_on_a)
    return force


# Periodic "jiggle": a single bounded DISPLACEMENT kick along each vertex's own outward normal
# (_vertex_outward_normals, same winding-based convention the repulsion gate above uses), meant
# to jog a locally-stuck/folded region loose. Gated by should_jiggle_next (see its own comment in
# relax_initial_configuration): a jiggle only fires while the mesh hasn't yet been reported
# converged by the MOST RECENT CONVERGENCE_CHECK_INTERVAL-cadence check (fixed at 200 steps, not
# adjustable here) -- doing it unconditionally forever would mean the check could never see a
# genuinely settled mesh. Evenly divides CONVERGENCE_CHECK_INTERVAL (200), so a jiggle never
# lands ON the check step itself (fires at step_count % interval == 1, the check at step_count %
# 200 == 0) -- see should_jiggle_next's own comment for why that matters.
LEVEL0_JIGGLE_INTERVAL_STEPS = 50

# Fixed DISPLACEMENT (not force) magnitude per jiggle, as a fraction of the mesh's own `scale`
# (_edge_setup's own representative rest-length scalar) -- deliberately bounded independent of
# current geometry (unlike a pressure force, whose magnitude scales with CURRENT face area), so
# no separate warmup delay is needed before the first jiggle. Converted to an equivalent one-step
# FORCE (jiggle_distance / dt) inside force_fn, since _explicit_relax_loop only accepts a force
# to apply, not a direct position nudge.
LEVEL0_JIGGLE_DISTANCE_FRACTION = 0.4


# Burst phase: a few steps of the plain-linear spring above PLUS a small amount of real
# per-face PRESSURE (_pressure_only_force), run BEFORE repulsion ever starts -- repulsion has
# no notion of which way is "outward" at all, but pressure's direction is tied directly to
# each face's own declared winding, so doing this FIRST biases the mesh toward a winding-
# consistent (non-self-folded) starting shape while pressure is the only shaping force in
# play. Diagnosed/tuned 2026-09-30 against several shipped nets' own worst seeds (see
# physics.md's Level 0 orientation-retry section) -- reduces how often Level 0 lands in a
# genuinely MIXED (locally self-folded) orientation, but doesn't eliminate it, which is why
# relax_initial_configuration_with_orientation_retry (below) exists as the backstop. Small
# enough, and the hardening term is NOT used here (see _pressure_only_force's own docstring),
# to stay numerically safe even applied directly to raw, not-yet-relaxed random noise.
LEVEL0_BURST_PRESSURE = 0.05
LEVEL0_BURST_STEPS = 200


def _pressure_only_force(pts, all_face_groups, pressure):
    """The pure per-face pressure term of stretchy_mesh._relax_force --
    `pressure * area * outward_normal`, split per vertex -- with NO spring
    term at all. Used only by the burst phase above/below; kept separate
    from _spring_only_force so the burst can combine plain-LINEAR spring
    (matching the rest of Level 0) with real pressure, rather than using
    _relax_force's own HARDENING spring, whose cubic term explodes when
    combined with real pressure on raw, not-yet-relaxed random noise (see
    git history, 2026-09-30)."""
    n = pts.shape[0]
    force = np.zeros((n, 3))
    if not pressure:
        return force
    for n_sides, group_idx in all_face_groups.items():
        face_pts = pts[group_idx]
        next_pts = np.roll(face_pts, -1, axis=1)
        area_vector = 0.5 * np.cross(face_pts, next_pts).sum(axis=1)
        per_vertex_force = pressure * area_vector / n_sides
        np.add.at(force, group_idx.ravel(), np.repeat(per_vertex_force, n_sides, axis=0))
    return force


def level0_jiggle_distance(faces, edge_length, edges=None):
    """The actual jiggle displacement magnitude relax_initial_configuration
    applies at Level 0 (LEVEL0_JIGGLE_DISTANCE_FRACTION * scale -- see
    that constant's own comment for what `scale` is), exposed here purely
    for DISPLAY (the Convergence History table's own "Pressure" column,
    which otherwise reads "--" for Level 0 since Level 0 never calibrates
    a real pressure the way relax_once does). This is a length (same
    units as `edge_length`), not literally a pressure -- shown there
    anyway since it's the closest analogue "how strong was the burst"
    has for Level 0."""
    _, _, _, _, _, _, _, scale = _edge_setup(faces, edge_length, edges)
    return LEVEL0_JIGGLE_DISTANCE_FRACTION * scale


def relax_initial_configuration(positions, faces, edge_length,
                                 max_nfev=None, stop_event=None, gtol=CONVERGENCE_GTOL, rng=None,
                                 on_progress=None, edges=None, rms_exclude_edges=None,
                                 pressure_exclude_faces=None):
    """positions/faces/edge_length/edges/rms_exclude_edges: as relax_once,
    but `positions` is typically random_initial_positions' output here,
    not a meaningful embedding -- this is what turns it into one, WITHOUT
    ever touching pressure: pure Hooke's-law springs (_spring_only_force)
    plus an all-pairs repulsion between EVERY vertex (repulsion_force) --
    the repulsion is the only thing here that has any opinion about a
    pair of vertices with no edge between them at all, and only at short
    range. Nothing here fixes overall position/scale, so the result can
    end up anywhere in space, at any scale, and self-intersecting --
    fine, since the only goal is a well-separated, edge-length-plausible
    starting point for relax_once's real per-face pressure model
    afterward. A plain polyhedron wireframe needs to already be
    subdivided into all-triangle faces (see mesh_levels.subdivide_once)
    before this can find a well-defined 3D shape at all: an unbraced
    quad/pentagon face is a genuine mechanism, not a rigid one, so
    springs alone can't stop it flexing arbitrarily.

    Same stopping rule as relax_once (see stretchy_mesh._explicit_relax_loop /
    physics.md's Convergence section): `gtol` on the worst vertex's own
    last-step displacement, or `max_nfev`/`stop_event`. `rng`, as in
    relax_once, opts into an occasional random perturbation when stuck
    oscillating (`None` -- the default -- is fully deterministic).
    `on_progress`, as in relax_once, is called every CONVERGENCE_CHECK_
    INTERVAL steps with this function's own return shape.

    Each vertex's own repulsion force is discarded entirely whenever it
    points INWARD -- dot(repulsion_force_at_v, outward_normal_at_v) < 0
    -- rather than letting repulsion push a vertex further into a fold.
    See _vertex_outward_normals' own docstring for what "outward" means
    here and why a vertex with no well-defined outward direction (the
    zero vector) leaves its repulsion force untouched instead of risking
    suppressing it on an arbitrary fallback axis.

    Every LEVEL0_JIGGLE_INTERVAL_STEPS steps, every vertex also gets a
    one-step kick along its own outward normal (see
    LEVEL0_JIGGLE_INTERVAL_STEPS/LEVEL0_JIGGLE_DISTANCE_FRACTION's own
    comments) -- meant to jog a locally-stuck/folded region loose
    periodically, not to shape the final result. Convergence is always
    checked BEFORE that block's own jiggle, never after -- a block's own
    convergence check and a jiggle NEVER land in the same block, so a
    genuinely at-rest mesh is reported converged (and the loop stops) at
    the very next check, without depending on a kick having fully
    re-settled first. See should_jiggle_next's own comment below for how.

    `pressure_exclude_faces`: as _face_index_groups -- an OPEN wedge
    triangle contributes NOTHING to the JIGGLE's own per-vertex outward
    normal (matching Level 1+'s own rule that an open wedge doesn't
    experience inflation forces; the jiggle IS a kind of inflation
    force). Does NOT affect the repulsion-gate's own outward normal,
    which still considers every face -- that gate has no established
    open/closed distinction of its own, so this only narrows what the
    jiggle itself reads. A vertex touching ONLY open faces gets the zero
    vector for the jiggle's own normal and so contributes nothing to that
    step's jiggle; a vertex touching at least one CLOSED face still gets
    a perfectly good normal from that face alone.

    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    optimality, converged) -- exactly relax_once's own return shape."""
    vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, length_arr, scale = \
        _edge_setup(faces, edge_length, edges)
    # A SEPARATE, possibly-narrower group than all_face_groups above -- only used for the
    # jiggle's own outward normal (see this function's own docstring on why the repulsion-gate
    # deliberately keeps using the unrestricted all_face_groups instead).
    inflating_face_groups = (all_face_groups if pressure_exclude_faces is None
                              else _face_index_groups(faces, idx, pressure_exclude_faces))
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)

    # Burst phase (see LEVEL0_BURST_PRESSURE's own comment) -- runs BEFORE repulsion, using the
    # SAME step size as the rest of Level 0. Bounded by LEVEL0_BURST_STEPS regardless of
    # `max_nfev`/`gtol` (it's a fixed head start, not itself a convergence target), but still
    # honors `stop_event` so a Stop mid-burst aborts promptly rather than running it to
    # completion first.
    def burst_force_fn(pts):
        return (_spring_only_force(pts, edge_ai, edge_bi, length_arr)
                + _pressure_only_force(pts, all_face_groups, LEVEL0_BURST_PRESSURE))

    pts0, _burst_steps, _burst_optimality, _burst_converged = _explicit_relax_loop(
        pts0, scale, burst_force_fn, LEVEL0_BURST_STEPS, stop_event, gtol,
        step_max_multiplier=LEVEL0_STEP_MAX_MULTIPLIER)

    jiggle_distance = LEVEL0_JIGGLE_DISTANCE_FRACTION * scale
    jiggle_dt = LEVEL0_STEP_MAX_MULTIPLIER * scale
    # Mutable (not a plain int) so force_fn -- called fresh each step by _explicit_relax_loop,
    # with no step-number argument of its own -- can advance it via closure.
    step_count = [0]
    # Whether the FIRST step of the block about to start should jiggle -- set only by on_check,
    # from that check's own `converged` result, which _explicit_relax_loop always computes
    # BEFORE calling on_check and before deciding whether to break. False for the very first
    # block (nothing has been checked yet); once a check reports converged, this is set False
    # too, but by then the loop is about to break anyway -- so it's really only ever True for the
    # block immediately following a NOT-yet-converged check.
    should_jiggle_next = [False]

    def force_fn(pts):
        step_count[0] += 1
        repulsion = repulsion_force(pts)
        outward = _vertex_outward_normals(pts, all_face_groups)
        inward = np.einsum('ij,ij->i', repulsion, outward) < 0
        repulsion[inward] = 0.0
        force = _spring_only_force(pts, edge_ai, edge_bi, length_arr) + repulsion
        if should_jiggle_next[0] and step_count[0] % LEVEL0_JIGGLE_INTERVAL_STEPS == 1:
            jiggle_outward = (outward if inflating_face_groups is all_face_groups
                               else _vertex_outward_normals(pts, inflating_face_groups))
            force = force + (jiggle_distance / jiggle_dt) * jiggle_outward
        return force

    def on_check(check_pts, check_steps, check_optimality, check_converged):
        should_jiggle_next[0] = not check_converged
        if on_progress is not None:
            check_positions, check_max_stretch, check_rms_stretch = positions_and_stretch(
                check_pts, vertex_ids, edges, length_arr, rms_exclude_edges)
            on_progress(check_positions, check_steps, check_max_stretch, check_rms_stretch,
                        check_optimality, check_converged)

    # Always passed now (not conditional on on_progress), since should_jiggle_next needs
    # updating every check regardless of whether the caller wants progress reports too.
    pts, steps_taken, optimality, converged = _explicit_relax_loop(
        pts0, scale, force_fn, max_nfev, stop_event, gtol, rng,
        step_max_multiplier=LEVEL0_STEP_MAX_MULTIPLIER,
        on_check=on_check)

    new_positions, max_stretch, rms_stretch = positions_and_stretch(
        pts, vertex_ids, edges, length_arr, rms_exclude_edges)
    return new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged


# relax_initial_configuration_with_orientation_retry's own retry budget -- see its docstring.
# Kept as aliases of seed_selecter.py's own defaults (2026-10-01) so existing callers/docs
# naming this constant keep working; the actual budget now lives in SeedSelecter.
LEVEL0_ORIENTATION_MAX_RETRIES = DEFAULT_MAX_ATTEMPTS
LEVEL0_ORIENTATION_MAX_SEARCH_TIME = DEFAULT_MAX_SEARCH_TIME


def _orientation_signs_of(positions, faces):
    """positions/faces: as elsewhere. Builds the idx/pts arrays
    _orientation_signs itself needs and returns its per-face +1/-1/0
    list, for relax_initial_configuration_with_orientation_retry's own
    use below (see stretchy_mesh.is_orientation_consistent for the same
    pattern's plain True/False wrapper)."""
    vertex_ids = sorted(positions)
    idx = {v: i for i, v in enumerate(vertex_ids)}
    pts = np.array([positions[v] for v in vertex_ids])
    return _orientation_signs(pts, faces, idx)


def _fraction_flipped(signs_list):
    """signs_list: _orientation_signs_of's own per-face +1/-1/0 list, for
    a result already known to be MIXED (both signs present) -- ranks two
    such results against each other, smaller is better (closer to a
    single clean, fully-consistent shape). Degenerate (0) faces are
    excluded from both the numerator and denominator, same as
    stretchy_mesh._is_orientation_consistent's own treatment of them."""
    nonzero = [s for s in signs_list if s != 0]
    if not nonzero:
        return 0.0
    return sum(1 for s in nonzero if s < 0) / len(nonzero)


def relax_initial_configuration_with_orientation_retry(
        faces, edge_length, seed, base_faces=None, max_retries=LEVEL0_ORIENTATION_MAX_RETRIES,
        max_search_time=LEVEL0_ORIENTATION_MAX_SEARCH_TIME,
        max_nfev=None, stop_event=None, gtol=CONVERGENCE_GTOL, rng=None, on_progress=None,
        edges=None, rms_exclude_edges=None, pressure_exclude_faces=None):
    """Runs relax_initial_configuration up to `max_retries` times (via a `SeedSelecter`, see its
    own docstring for the exact time/count budget), each from a FRESH random start
    (random_initial_positions at seed, seed + 1, seed + 2, ...), stopping at the first attempt
    that comes back fully orientation-consistent (stretchy_mesh._orientation_signs all +1).

    Time-bounded by `max_search_time` seconds (2026-10-01, explicit -- shared by BOTH apps' own
    Full Inflate, see this module's own header note): the first attempt always runs in full
    regardless of its own duration, but a SECOND (or later) attempt only starts if the
    cumulative time spent so far is still under budget -- so a model big/slow enough for one
    attempt to approach `max_search_time` gets exactly one attempt, never more. This is
    deliberate, not just a safety valve: a bigger/more-braced mesh is empirically unlikely to hit
    the all-faces-flipped failure mode this retry exists for in the first place, so spending
    MORE search time on exactly the inputs that need it least would be wasted effort.

    A UNIFORMLY flipped attempt (all -1, no local disagreement) is
    treated as a normal retry candidate, NOT fixed for free via a
    reflection -- tried, then reverted (2026-09-30): concavity/caving-in
    is itself reflection-INVARIANT (mirroring a caved-in shape gives
    another, equally caved-in shape -- chirality flipped, but the actual
    dimple is still there), so a uniform -1 reading isn't reliable
    evidence the shape is otherwise a genuinely non-concave "just
    backwards" embedding -- it can just as easily mean a real caved-in
    shape that happens to uniformly fail this centroid-relative check.
    Only a genuinely non-concave embedding is worth accepting at all, and
    the only way this module can tell the difference is by trying a
    FRESH random start, not by reflecting a shape whose own concavity
    reflecting can't fix.

    `base_faces`, if given, is checked INSTEAD of `faces` for orientation
    purposes only (the relax itself still runs on `faces`, the fan-
    triangulated mesh) -- vertex ids in `base_faces` must be a subset of
    `faces`' own (true for the ORIGINAL, pre-fan-triangulation polygon
    ids, which every base_faces caller here has). Diagnosed 2026-09-30:
    checking the fan-triangulated `faces` directly is NOT reliable -- a
    single macro polygon's own fan HUB vertex (added purely so a
    spring-only relax has something rigid to work with, see
    mesh_levels.py's own docstring) can independently bulge outward from
    its own 2 rim corners, making every one of that macro face's own fine
    sub-triangles read "points away from centroid" even while the ACTUAL
    macro polygon -- the plane through its real, non-hub corners -- is
    caved INWARD relative to the rest of the shape (a small pointy bump
    poking out of an otherwise inside-out shell). `base_faces` names the
    ORIGINAL (pre-fan) polygons directly, immune to this: reusing the
    exact ids `faces` was itself fanned from, so no extra remapping is
    needed to read their positions out of the very same `positions` dict
    the fan-triangulated relax already produces. `faces` itself is still
    used as the fallback when `base_faces` is omitted (e.g. a caller with
    no macro-polygon structure of its own to check against).

    Diagnosed 2026-09-30: even with LEVEL0_BURST_PRESSURE's own burst
    phase (which reduces how often this happens but doesn't eliminate
    it), some seeds converge Level 0 to a genuine, fully-settled MIXED
    orientation for some shipped nets (ravioli.poly's own cancelling-
    pressure pathology is especially prone to it -- see physics.md's
    Pressure calibration section) -- previously, this bad shape would
    just carry forward silently into every later level (see this
    function's own git history for the tetrahedron/cube/octahedron/
    ravioli seeds that first surfaced it, and for the macro-vs-fine
    discrepancy above).

    If every attempt comes back genuinely mixed, keeps whichever had the
    FEWEST disagreeing faces (_fraction_flipped) as the least-bad result,
    rather than always just the last attempt tried.

    Returns relax_initial_configuration's own 6-value result PLUS a 7th:
    `seed_used` -- the actual seed (one of seed..seed + max_retries - 1)
    the returned positions came from. A caller that displays/stores a
    seed (e.g. inflate_polyhedron_app's own seed field) should update it
    to THIS value, not whatever it originally requested, since a retry
    means the result doesn't necessarily match a plain
    relax_initial_configuration call at the ORIGINAL seed.

    `on_progress`, if given, is NEVER forwarded live while an attempt is
    still just a CANDIDATE (its own progress is buffered instead, in
    memory) -- a caller watching Level 0 relax should never see a
    discarded (mixed/uniformly-flipped) attempt's shape appear on
    screen, even briefly, only to be thrown away a moment later. Once an
    attempt is settled on (either accepted outright, or kept as the
    least-bad fallback after every attempt in `max_retries` failed), its
    own buffered progress calls are replayed through `on_progress` in
    one go, and `steps_taken`/the final return are that ONE attempt's
    own values -- never a sum across every attempt tried, so a step
    counter never counts work that was silently discarded."""
    orientation_faces = base_faces if base_faces is not None else faces
    selecter = SeedSelecter(max_attempts=max_retries, max_search_time=max_search_time)

    def attempt_fn(attempt_seed):
        pos0 = random_initial_positions(faces, seed=attempt_seed)
        buffered_progress = [] if on_progress is not None else None

        def _buffer_progress(*progress_args):
            buffered_progress.append(progress_args)

        relax_result = relax_initial_configuration(
            pos0, faces, edge_length, max_nfev=max_nfev, stop_event=stop_event, gtol=gtol,
            rng=rng, on_progress=_buffer_progress if on_progress is not None else None,
            edges=edges, rms_exclude_edges=rms_exclude_edges,
            pressure_exclude_faces=pressure_exclude_faces)
        signs_list = _orientation_signs_of(relax_result[0], orientation_faces)
        return relax_result, buffered_progress, signs_list

    def score_fn(attempt_result):
        _relax_result, _buffered_progress, signs_list = attempt_result
        signs = set(signs_list) - {0.0}
        accepted = bool(signs) and signs <= {1.0}
        return accepted, _fraction_flipped(signs_list)

    def on_attempt(attempt_index, attempt_seed, attempt_result, accepted, fraction):
        _relax_result, _buffered_progress, signs_list = attempt_result
        if accepted:
            print(f"Level 0 orientation: attempt {attempt_index + 1}/{max_retries}, "
                  f"seed={attempt_seed} -> consistent, using this seed")
            return
        signs = set(signs_list) - {0.0}
        description = "uniformly flipped" if signs == {-1.0} else "MIXED"
        next_step = "retrying" if attempt_index + 1 < max_retries else "no attempts left"
        print(f"Level 0 orientation: attempt {attempt_index + 1}/{max_retries}, "
              f"seed={attempt_seed} -> {description} ({fraction:.0%} of faces flipped), "
              f"{next_step}")

    def should_stop():
        return stop_event is not None and stop_event.is_set()

    (relax_result, buffered_progress, signs_list), seed_used, accepted, _attempts_tried = \
        selecter.select(seed, attempt_fn, score_fn, on_attempt=on_attempt, should_stop=should_stop)

    if not accepted:
        fraction = _fraction_flipped(signs_list)
        print(f"Level 0 orientation: every attempt stayed mixed, using least-bad "
              f"seed={seed_used} ({fraction:.0%} of faces flipped)")
    if on_progress is not None:
        for progress_args in buffered_progress:
            on_progress(*progress_args)
    return relax_result + (seed_used,)
