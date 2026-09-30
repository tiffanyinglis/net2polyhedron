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
    _explicit_relax_loop, repulsion_force,
)
from .convergence_checker import CONVERGENCE_GTOL
from .mesh_stretch_checker import positions_and_stretch

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
