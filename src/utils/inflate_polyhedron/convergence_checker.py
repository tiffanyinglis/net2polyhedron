"""Periodic convergence check shared by relax_once and
relax_initial_configuration's own explicit-relaxation driver
(stretchy_mesh._explicit_relax_loop) -- checked only every `interval`
steps (not every step), comparing the worst vertex's own displacement
over that whole interval against `interval * gtol`. See physics.md's
Convergence section for the current cadence/tolerance and the rationale
for checking in blocks rather than every step."""
import numpy as np

# The stopping check's own tolerance: a step counts as "at rest" once every vertex's own net
# force drops below this. See physics.md's Convergence section for the current value/rationale.
CONVERGENCE_GTOL = 1e-4

# How often the stopping condition above is actually checked, in steps, rather than every
# single step (see physics.md's Convergence section).
CONVERGENCE_CHECK_INTERVAL = 200


def remove_rigid_motion(pts_before, pts_after):
    """Re-expresses `pts_after` in the SAME rigid frame (rotation +
    translation) `pts_before` was in, via the standard Kabsch/orthogonal-
    Procrustes best-fit alignment -- removes whatever GLOBAL rigid
    rotation/translation happened to appear between the two, leaving only
    the genuine shape change (a rigid transform is an isometry, so this
    never affects stretch stats, convergence, or anything else the
    physics actually cares about).

    A free-floating spring/pressure system has no preferred orientation
    of its own -- rotating the WHOLE mesh about its own center of mass
    costs zero spring/pressure energy, so it's an exactly-flat direction
    the relaxation can drift along for free. This isn't only numerical
    noise: an ASYMMETRIC net can have a genuine, physically-driven
    rotational component to its own gradient-descent path, which
    compounds block over block since nothing in the force law objects to
    it. check_convergence calls this against a FIXED reference (the
    state at the very start of the run), not a rolling one -- a rolling
    reference only cancels drift WITHIN each block, doing nothing to stop
    a genuine per-block rotational component from compounding across many
    blocks."""
    c_before = pts_before.mean(axis=0)
    c_after = pts_after.mean(axis=0)
    a = pts_before - c_before
    b = pts_after - c_after
    h = b.T @ a
    u, _, vt = np.linalg.svd(h)
    # Guards against a reflection (det -1) rather than a pure rotation --
    # the SVD solution to this least-squares problem is only guaranteed
    # proper (det +1) with this sign correction; an unflipped mirror
    # image would silently invert the mesh instead of just rotating it.
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    r = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    return (r @ b.T).T + c_before


def check_convergence(pts, pts_at_run_start, pts_at_last_check, interval, gtol):
    """pts: current (N,3) positions; pts_at_run_start: the run's own
    FIXED starting positions (never updated -- see remove_rigid_motion's
    own docstring for why); pts_at_last_check: positions at the START of
    this interval-length block; interval/gtol: as this module's own
    constants, but always passed explicitly (a caller's own tolerance,
    not a hardcoded default). Realigns `pts` against `pts_at_run_start`
    (remove_rigid_motion) and compares the worst vertex's own
    displacement since `pts_at_last_check` to `interval * gtol`.

    Returns (pts, optimality, converged): `pts` is the realigned
    positions -- the current mesh configuration, with whatever rigid
    drift this block introduced stripped out; `optimality` is that same
    displacement divided back down by `interval` so it's directly
    comparable to a bare `gtol`; `converged` is True once it drops below
    threshold."""
    pts = remove_rigid_motion(pts_at_run_start, pts)
    block_displacement = float(np.linalg.norm(pts - pts_at_last_check, axis=1).max())
    optimality = block_displacement / interval
    converged = block_displacement < interval * gtol
    return pts, optimality, converged
