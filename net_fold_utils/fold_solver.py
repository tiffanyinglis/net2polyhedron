"""Solve for the dihedral fold angle at every net hinge that closes the net
into the target solid.

The net's spanning-tree edges (hinges) leave one rotation angle free per
non-root face -- folding the tree alone is consistent with infinitely many
shapes. The EXTRA edges (polyhedron edges that exist in the solid but are
not physical hinges in the flat net) pin those angles down: at t=1 each
EXTRA edge's two faces must meet exactly along that edge in 3D. We solve for
the hinge angles that satisfy all of those closure constraints at once.

A fully edge-constrained net can still have more than one algebraic
solution: besides the intended convex solid, the same equations are often
also satisfied by a "collapsed" self-intersecting immersion (e.g. an
icosahedron net can close into a smaller, pentagram-like shape that
coincidentally matches every edge equation). We reject those by checking
that no two non-adjacent vertices end up closer together than one edge
length, which a genuine convex, unit-edge solid never allows.
"""
import numpy as np
from scipy.optimize import least_squares

from .net_fold_core import fold, distinct_vertices, precompute_subtree_map
from .polygon_geom import EDGE_LENGTH

CLOSE_TOL = 1e-6
COLLISION_TOL = 1e-3


def _residual(theta, net, root, hinges, extra_edges, edge_map, subtree_map):
    fold_angles = {h["child"]: theta[i] for i, h in enumerate(hinges)}
    verts = fold(net, root, hinges, fold_angles, t=1.0, subtree_map=subtree_map)
    res = []
    for f1, f2 in extra_edges:
        i1, i2 = edge_map.edge_index(f1, f2), edge_map.edge_index(f2, f1)
        a1, b1 = verts[f1][i1], verts[f1][(i1 + 1) % len(verts[f1])]
        a2, b2 = verts[f2][i2], verts[f2][(i2 + 1) % len(verts[f2])]
        # the two edges must coincide, traversed in opposite directions
        res.append(a1 - b2)
        res.append(b1 - a2)
    return np.concatenate(res) if res else np.zeros(0)


def _is_embeddable(theta, net, root, hinges, subtree_map):
    """Reject collapsed/self-intersecting branches: in a genuine convex,
    unit-edge solid no two distinct vertices are ever closer than one
    edge length."""
    fold_angles = {h["child"]: theta[i] for i, h in enumerate(hinges)}
    verts = fold(net, root, hinges, fold_angles, t=1.0, subtree_map=subtree_map)
    pts = np.array(distinct_vertices(verts))
    if len(pts) < 2:
        return True
    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    return d.min() > EDGE_LENGTH * (1 - COLLISION_TOL)


def _try_guesses(guesses, net, root, hinges, extra_edges, edge_map, subtree_map):
    """Run least_squares from each initial guess, returning
    (valid_candidates, best_err) where valid_candidates is a list of
    (sum_of_angles, theta) for every guess that converged to a genuine,
    embeddable closure."""
    lo, hi = 1e-3, np.pi - 1e-3
    valid_candidates = []
    best_err = np.inf
    for x0 in guesses:
        sol = least_squares(_residual, x0, bounds=(lo, hi),
                             args=(net, root, hinges, extra_edges, edge_map, subtree_map))
        err = np.max(np.abs(sol.fun)) if sol.fun.size else 0.0
        best_err = min(best_err, err)
        if err < CLOSE_TOL and _is_embeddable(sol.x, net, root, hinges, subtree_map):
            valid_candidates.append((np.sum(sol.x), sol.x))
    return valid_candidates, best_err


def solve_fold_angles(net, root, hinges, extra_edges, edge_map, seed=0):
    """Return {child_face_id: fold_angle_radians} satisfying every EXTRA
    edge's closure constraint at t=1, filtered to genuinely embeddable
    (non-self-intersecting) solutions."""
    n = len(hinges)
    if not extra_edges:
        raise ValueError("no EXTRA edges given; the fold is underdetermined "
                          "(any hinge angle would be consistent with the "
                          "net alone)")

    # The hinge tree's shape (which faces are in which hinge's subtree)
    # never changes across the whole solve -- only the angles do -- so
    # derive it once here instead of letting fold() re-derive it on every
    # one of the many thousands of calls the optimizer makes below.
    subtree_map = precompute_subtree_map(hinges)

    # A sweep of evenly-spaced, all-hinges-equal starting guesses is enough
    # to find every algebraic closure branch for the symmetric solids this
    # targets (verified: it finds both the true and the "collapsed" branch
    # for the icosahedron, for instance) -- so it's tried first, alone.
    # Random per-hinge restarts are a fallback for the rare/asymmetric case
    # where a uniform guess doesn't land in any solution's basin, not a way
    # to find additional branches once the sweep already has one.
    sweep = [np.full(n, np.radians(d)) for d in range(10, 180, 10)]
    valid_candidates, best_err = _try_guesses(
        sweep, net, root, hinges, extra_edges, edge_map, subtree_map)

    if not valid_candidates:
        rng = np.random.default_rng(seed)
        lo, hi = 1e-3, np.pi - 1e-3
        fallback = [rng.uniform(lo, hi, n) for _ in range(40)]
        valid_candidates, fallback_err = _try_guesses(
            fallback, net, root, hinges, extra_edges, edge_map, subtree_map)
        best_err = min(best_err, fallback_err)

    if not valid_candidates:
        raise ValueError(
            f"could not fold the net into a consistent, non-self-"
            f"intersecting solid (best closure error {best_err:.2e}); "
            f"check that FACES/NET/EXTRA describe a valid, rigid polyhedron")

    # Prefer the least-folded (smallest total rotation) valid solution --
    # for the solids this targets, that is the unique convex realization.
    valid_candidates.sort(key=lambda c: c[0])
    theta = valid_candidates[0][1]
    return {h["child"]: theta[i] for i, h in enumerate(hinges)}
