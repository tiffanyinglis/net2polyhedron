"""Loader + solver for STRETCHY meshes: a closed polyhedron-like net whose
faces are combinatorially valid (every edge shared by exactly two faces)
but that cannot necessarily be realized with perfectly RIGID, FLAT faces
-- e.g. two faces glued together along more than one shared edge, which
forces them into the same plane if both stay flat and rigid (three or
more shared, non-collinear points determine a single plane, so any two
flat polygons sharing that many points must lie in it -- there's no
dihedral fold left to make them distinct faces of a solid).

Rather than a hinge-tree-plus-fold-angles model (which assumes every face
stays flat), a stretchy mesh is specified directly as VERTEX loops -- the
standard "indexed face set" representation (like an .obj file): shared
vertices ARE the adjacency, so faces sharing multiple edges need no
special-casing, and there's no "flat 2D net" or "fold angle" concept to
derive at all. JSON shape:

    {
      "name": "...",
      "faces": [
        [0, 1, 2, 3, 4],
        [3, 2, 1, 0, 5],
        [0, 4, 3, 5]
      ]
    }

WINDING CONVENTION: each face is a loop of vertex ids (ints, 0..N-1,
referenced -- not separately declared; N is inferred as 1 + the largest
id used) listed COUNTERCLOCKWISE as seen from OUTSIDE the finished
solid. Concretely: for any edge (v, w) shared by two faces, one face's
loop contains it as v -> w and the other's contains it as w -> v --
never the same direction twice. load_stretchy_mesh checks exactly that
(every directed edge matched by exactly one reverse partner in some
other face) and raises a clear error naming the offending edge(s) if
it's violated.

That check alone can't catch every possible mistake, though: flipping
EVERY face at once (a full mirror image) is just as valid a loop
structure as the original. A subtler problem can still reach the
solver even so: solve_wireframe's plain edge-length fit has many
solutions for a well-connected mesh, and some of them fold one face
inside-out relative to the rest even though the abstract loops are
perfectly consistent. solve_wireframe checks for this too (see
_is_orientation_consistent) and specifically searches for a consistent
embedding; if it truly can't find one after many attempts, it raises
ValueError with a suggestion to double check face winding.

solve_wireframe() then finds SOME 3D position for every vertex that
keeps every edge close to unit length, without requiring individual
faces to stay flat -- letting edges stretch a little and faces bend is
exactly what makes an otherwise-rigid-impossible net (like
data/input/stretchy_nets/two_pentagons_and_a_square.json) realizable at
all. It works equally well on an ordinary closed solid (see
data/input/stretchy_nets/{tetrahedron,cube,octahedron,icosahedron,dodecahedron}.json)
-- those settle with only a few percent stretch, puffed out into a
rounded, convex, plushie-like shape via an outward "inflation" pressure
(literally the same idea as stuffing/blowing up a plush toy or balloon
until the fabric's own tension stops it).

Design notes (the "why" behind choices that would otherwise look
arbitrary -- kept here rather than repeated across every function that
touches them, per this project's docstring convention in skills.md):

- **relax_once is a genuine force balance, walked step by step -- no
  volume anywhere** (_relax_force): each edge is a Hooke's-law spring;
  each face applies a real outward force, `pressure * area * normal`,
  split across its own vertices. Each call moves every vertex a small
  step along its OWN net force (explicit relaxation), not a
  least_squares solve: a Newton-style solver re-linearizes the whole
  mesh and can jump straight past the physically-reachable equilibrium
  to a distant, spurious one (verified directly -- a plain cube at
  pressure=1 landed on a doubled-size, 99%-stretched "solution" in 5
  solver evaluations; at pressure=3 on a subdivided cube it likewise
  imploded to near-zero volume without any face ever flipping, since a
  uniform implosion never disagrees with itself -- both are real zeros
  of the same equations, just not the one a physical process starting
  nearby would ever walk to). Explicit small steps can't teleport past
  the reachable equilibrium the way a linearized jump can. Step size is
  self-normalizing (STEP_MAX_FRACTION of the mesh's own rest edge
  length, divided by the largest current force) so it adapts to
  whatever pressure/mesh scale is in play without a fixed constant.
  Direction vectors use _safe_unit_vectors (a fixed fallback at an exact
  zero vector) instead of a naive division: without it, "every vertex
  exactly coincident" is a real zero of the force (every edge and face
  vanishes together) the relaxation could still land exactly on instead
  of the intended shape.

- **Ramping + accept-or-reject in _inflate**: applying full pressure
  cold, or from a random start, makes least_squares fail to converge at
  all rather than inflate cleanly. INFLATION_WEIGHTS ramps up gradually,
  re-seeding each step from the last ACCEPTED one, and stops (keeping the
  last good result) the moment a step's edge stretch would exceed
  STRETCH_CAP -- self-limiting for a topology that genuinely can't hold
  much pressure instead of stretching it into a mess.

- **Why solve_wireframe retries whole attempts, not per-ramp-step
  orientation checks**: gating _inflate's ramp on orientation consistency
  at every step was tried and made things worse -- the icosahedron's ramp
  reliably passes through a couple of genuinely inconsistent intermediate
  weights before self-correcting at higher pressure, so stopping early
  would mean it never reaches the weight where it recovers. Consistency
  is instead checked only on each WHOLE attempt's final result;
  solve_wireframe retries a fresh random stage-1 start (up to
  MAX_ORIENTATION_ATTEMPTS) rather than second-guessing individual ramp
  steps, and keeps the first attempt that succeeds without comparing
  further ones (repeated successes land on essentially the same result
  once a mesh inflates at all).
"""
import collections
import json

import numpy as np
from scipy.optimize import least_squares

from ..geometry.polyhedron import Polyhedron

EDGE_LENGTH = 1.0

# Bump whenever solve_wireframe's algorithm changes enough to produce a
# meaningfully different result for the same mesh (e.g. adding the
# inflation stage) -- stretchy_cache folds this into its cache key, so a
# solver change invalidates every existing cache entry even though the
# source .json files themselves haven't changed at all.
ALGORITHM_VERSION = 6


def _face_edges(face):
    """The directed edges (v, w) of one CCW face loop."""
    k = len(face)
    return [(face[i], face[(i + 1) % k]) for i in range(k)]


def load_stretchy_mesh(path):
    """path: a vertex-loop stretchy-mesh .json (see module docstring).
    Returns (faces, name), faces a list of vertex-id lists. Raises
    ValueError if any directed edge isn't matched by exactly one
    reverse-direction partner (faces don't close into a 2-manifold)."""
    with open(path) as f:
        spec = json.load(f)

    faces = spec.get("faces") or []
    if not faces:
        raise ValueError(f"{path}: no faces declared")
    for face in faces:
        if len(face) < 3:
            raise ValueError(f"{path}: a face needs at least 3 vertices, got {face}")

    directed = [e for face in faces for e in _face_edges(face)]
    counts = {}
    for e in directed:
        counts[e] = counts.get(e, 0) + 1
    problems = []
    for (v, w), c in counts.items():
        if c > 1:
            problems.append(f"edge {v}->{w} appears {c} times (need exactly once)")
        if (w, v) not in counts:
            problems.append(f"edge {v}->{w} has no reverse partner {w}->{v} in any face")
    if problems:
        raise ValueError(f"{path}: not a closed, consistently-oriented mesh:\n  " +
                          "\n  ".join(problems))

    name = spec.get("name") or path
    return faces, name


def mesh_edges(faces):
    """faces: vertex-id loops. Returns the mesh's unique undirected edges
    as a sorted list of (a, b) with a < b."""
    edges = {tuple(sorted(e)) for face in faces for e in _face_edges(face)}
    return sorted(edges)


def mesh_to_polyhedron(positions, faces, name=None):
    """positions: {vertex_id: np.ndarray(3,)}; faces: vertex-id loops
    (ids need not be contiguous from 0). Wraps a solved stretchy mesh into
    a Polyhedron, remapping vertex ids to Polyhedron's own dense 0..N-1
    index space."""
    vertex_ids = sorted(positions)
    idx = {v: i for i, v in enumerate(vertex_ids)}
    vertices = [positions[v] for v in vertex_ids]
    remapped_faces = [tuple(idx[v] for v in face) for face in faces]
    return Polyhedron(vertices=vertices, faces=remapped_faces, name=name)


def _pair_index_arrays(pairs, idx):
    """pairs: (a, b) vertex-id pairs; idx: {vertex_id: flat-array position}.
    Returns two int arrays (a_idx, b_idx) of their positions, for
    vectorized pairwise-distance residuals instead of a per-pair Python
    loop."""
    if not pairs:
        return np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    a_idx = np.array([idx[a] for a, b in pairs])
    b_idx = np.array([idx[b] for a, b in pairs])
    return a_idx, b_idx


def _volume_indices(faces, idx):
    """faces/idx: as above. Precomputed fan-triangulation index arrays
    for _mesh_volume: each face fan-triangulated from its own first
    vertex, flattened into three parallel int arrays (v0, v1, v2).
    Built once per solve rather than re-derived on every _residual call."""
    v0s, v1s, v2s = [], [], []
    for face in faces:
        face_idx = [idx[v] for v in face]
        for i in range(1, len(face_idx) - 1):
            v0s.append(face_idx[0])
            v1s.append(face_idx[i])
            v2s.append(face_idx[i + 1])
    return (np.array(v0s, dtype=int), np.array(v1s, dtype=int), np.array(v2s, dtype=int))


def _face_volume_group(faces, idx):
    """Like _volume_indices, but also returns a parallel `face_ids` array
    naming each flattened fan-triangle's source face (0..len(faces)-1).
    Lets _per_face_volumes recover one volume PER face via np.bincount,
    not just the mesh total _mesh_volume gives."""
    v0s, v1s, v2s, face_ids = [], [], [], []
    for face_id, face in enumerate(faces):
        face_idx = [idx[v] for v in face]
        for i in range(1, len(face_idx) - 1):
            v0s.append(face_idx[0])
            v1s.append(face_idx[i])
            v2s.append(face_idx[i + 1])
            face_ids.append(face_id)
    return (np.array(v0s, dtype=int), np.array(v1s, dtype=int), np.array(v2s, dtype=int),
            np.array(face_ids, dtype=int), len(faces))


def _per_face_volumes(pts, face_volume_group):
    """pts: (N,3) vertex positions; face_volume_group: _face_volume_group's
    precomputed structure. Returns an array of length n_faces, each face's
    own signed volume contribution (via np.bincount over its fan-triangles),
    rather than _mesh_volume's single grand total."""
    v0_idx, v1_idx, v2_idx, face_ids, n_faces = face_volume_group
    if len(v0_idx) == 0:
        return np.zeros(n_faces)
    v0 = pts[v0_idx]
    v1 = pts[v1_idx]
    v2 = pts[v2_idx]
    tetra_volumes = np.einsum('ij,ij->i', v0, np.cross(v1, v2)) / 6.0
    return np.bincount(face_ids, weights=tetra_volumes, minlength=n_faces)


def _face_index_groups(faces, idx):
    """faces/idx: as elsewhere. Groups EVERY face's vertex indices by
    side count (3..8) -- {n: array of shape (num_faces_with_n_sides, n)}
    -- for vectorized per-face area/outward-normal computation (see
    _relax_force). Includes triangles, unlike _planarity_groups."""
    groups = {}
    for face in faces:
        n = len(face)
        groups.setdefault(n, []).append([idx[v] for v in face])
    return {n: np.array(rows, dtype=int) for n, rows in groups.items()}


def _planarity_groups(faces, idx):
    """faces/idx: as above. Precomputed per-face-size index arrays for
    _face_planarity_residual: {n: array of shape (num_n_vertex_faces, n)}
    for every face with 4+ vertices (triangles are always exactly planar
    and excluded). Lets same-size faces batch into one SVD call."""
    groups = {}
    for face in faces:
        n = len(face)
        if n < 4:
            continue
        groups.setdefault(n, []).append([idx[v] for v in face])
    return {n: np.array(rows, dtype=int) for n, rows in groups.items()}


def _face_planarity_residual(pts, planarity_groups):
    """pts: (N,3) vertex positions; planarity_groups: _planarity_groups'
    result (triangles already excluded). Returns each (4+-vertex) face's
    points' signed distance from that face's own best-fit plane (via SVD),
    one batched call per distinct face size."""
    if not planarity_groups:
        return np.zeros(0)
    parts = []
    for group_idx in planarity_groups.values():
        face_pts = pts[group_idx]  # (num_faces, n, 3)
        centered = face_pts - face_pts.mean(axis=1, keepdims=True)
        normals = np.linalg.svd(centered, full_matrices=False)[2][:, -1, :]  # (num_faces, 3)
        parts.append(np.einsum('fij,fj->fi', centered, normals).ravel())
    return np.concatenate(parts)


def _mesh_volume(pts, volume_indices):
    """pts: (N,3) vertex positions; volume_indices: _volume_indices'
    precomputed (v0,v1,v2) index arrays. Returns the mesh's signed
    enclosed volume via the divergence theorem (fan-triangulated,
    summed against the origin) -- smooth and singularity-free, so usable
    as a least_squares term even from a poorly-conditioned start."""
    v0_idx, v1_idx, v2_idx = volume_indices
    if len(v0_idx) == 0:
        return 0.0
    v0 = pts[v0_idx]
    v1 = pts[v1_idx]
    v2 = pts[v2_idx]
    return float(np.einsum('ij,ij->i', v0, np.cross(v1, v2)).sum() / 6.0)


def _total_rest_area(faces, edge_length):
    """Exact total REST surface area from the mesh's own rest edge
    lengths: closed-form regular-polygon area for a uniform scalar
    `edge_length`, else Heron's formula per triangle (every dict-keyed
    mesh here is all-triangle) -- correct even with mixed rest lengths,
    unlike assuming one (e.g. the smallest) edge length for every face."""
    if not isinstance(edge_length, dict):
        n_sum = sum((k / 4.0) / np.tan(np.pi / k) for k in (len(f) for f in faces))
        return n_sum * edge_length ** 2
    total = 0.0
    for a, b, c in faces:
        la, lb, lc = (edge_length[tuple(sorted(e))] for e in ((b, c), (a, c), (a, b)))
        s = (la + lb + lc) / 2
        total += max(0.0, s * (s - la) * (s - lb) * (s - lc)) ** 0.5
    return total


def _sphere_bound_volume(faces, edge_length):
    """Volume of the sphere with the mesh's own total rest surface area
    (see _total_rest_area) -- an optimistic, normally-unreachable
    inflation target, scaled to the mesh's own size. See module
    docstring's Design notes for how this is used as a pressure target."""
    total_area = _total_rest_area(faces, edge_length)
    r = np.sqrt(total_area / (4 * np.pi))
    return (4 / 3) * np.pi * r ** 3


def _edge_and_planarity_parts(pts, edge_ai, edge_bi, edge_length, planarity_weight, planarity_groups):
    """Shared residual pieces for _residual (relax_once uses _relax_force instead, see its docstring): RELATIVE
    edge-length error `(actual - rest) / rest` for every edge (always
    first, so callers can slice it out), plus an optional planarity term.
    `edge_length` may be a scalar or a per-edge array (see
    mesh_subdivide.py for why a subdivided mesh needs the latter)."""
    parts = [(np.linalg.norm(pts[edge_ai] - pts[edge_bi], axis=1) - edge_length) / edge_length]
    if planarity_weight:
        parts.append(planarity_weight * _face_planarity_residual(pts, planarity_groups))
    return parts


def _residual(flat, edge_ai, edge_bi, volume_indices, planarity_groups, edge_length,
              inflation_weight=0.0, inflation_target=0.0, planarity_weight=0.0):
    """The automatic-ramp objective (_inflate/solve_wireframe): edge-length
    + planarity + a TARGET-based inflation pressure term (`inflation_weight
    * (inflation_target - volume)`, see module docstring). relax_once uses
    _relax_force instead, which has no target -- see its docstring."""
    pts = flat.reshape(-1, 3)
    parts = _edge_and_planarity_parts(pts, edge_ai, edge_bi, edge_length, planarity_weight, planarity_groups)
    if inflation_weight:
        vol = _mesh_volume(pts, volume_indices)
        parts.insert(1, np.array([inflation_weight * (inflation_target - vol)]))
    return np.concatenate(parts)


def _safe_unit_vectors(vecs):
    """vecs: (M,3), possibly containing exact zero vectors. Returns unit
    vectors: the true direction where resolvable, or a fixed (1,0,0)
    fallback at an exact zero vector -- picking one fixed convention
    there, rather than letting a naive `v/norm(v)` division silently
    shrink toward the zero vector as `norm(v)` shrinks toward it, is what
    keeps a genuinely-zero *force* from a magnitude that was never
    actually zero (see module docstring's Design notes)."""
    norms = np.linalg.norm(vecs, axis=1)
    ok = norms > 1e-9
    unit = np.zeros_like(vecs)
    unit[ok] = vecs[ok] / norms[ok, None]
    unit[~ok] = (1.0, 0.0, 0.0)
    return unit


# Ratio (current length / rest length) beyond which an edge starts
# fighting back much harder than plain Hooke's law -- generous enough to
# never engage during ordinary inflation, only once something is already
# badly over- or under-stretched.
SOFT_LIMIT_HI = 2.0
SOFT_LIMIT_LO = 0.5

# How hard the soft limit pushes back per unit of excess-past-the-bound,
# SQUARED (see _soft_limit_stretch) -- squared specifically because plain
# Hooke's law force only grows linearly with edge length, while outward
# pressure grows QUADRATICALLY with it (pressure * area, and area grows
# with length^2): past some pressure, no amount of ordinary spring
# stiffness can ever catch up, and the mesh inflates without bound (see
# module docstring's Design notes). A force growing quadratically in the
# excess grows CUBICALLY in overall edge length for a badly-stretched
# edge, which is fast enough to guarantee some finite equilibrium exists
# no matter how high pressure is set, rather than just delaying the same
# runaway to a higher pressure.
SOFT_LIMIT_STIFFNESS = 50.0


def _soft_limit_stretch(dist, edge_length):
    """dist/edge_length: as in _relax_force. Returns (extra_stretch,
    max_excess): extra_stretch is added on top of plain Hooke's-law
    stretch -- zero inside [SOFT_LIMIT_LO, SOFT_LIMIT_HI] x rest length,
    growing with the SQUARE of how far outside it the edge is (see
    SOFT_LIMIT_STIFFNESS for why squared), signed the same way plain
    stretch already is (positive = pull together, negative = push
    apart). max_excess (0 if none engaged) lets relax_once pick a safe
    step size only once this term actually matters (see
    STEP_MAX_MULTIPLIER_STIFF)."""
    ratio = dist / edge_length
    excess_hi = np.maximum(0.0, ratio - SOFT_LIMIT_HI)
    excess_lo = np.maximum(0.0, SOFT_LIMIT_LO - ratio)
    max_excess = float(np.max(excess_hi + excess_lo)) if len(ratio) else 0.0
    return SOFT_LIMIT_STIFFNESS * (excess_hi ** 2 - excess_lo ** 2), max_excess


def _relax_force(pts, edge_ai, edge_bi, all_face_groups, planarity_groups, edge_length,
                  pressure=0.0, planarity_weight=0.0):
    """relax_once's per-step force: a genuine mechanical force balance.
    Each edge is a Hooke's-law spring (relative stretch (dist-rest)/rest
    along the edge direction) PLUS a soft limit (see _soft_limit_stretch)
    that sharply stiffens an edge stretched past SOFT_LIMIT_HI or
    compressed past SOFT_LIMIT_LO of its own rest length; each face
    applies a real outward pressure force, `pressure * area *
    outward_normal` -- area and normal computed together straight from
    its own vertex loop via `0.5 * sum_i cross(p_i, p_{i+1})` (Newell's
    method) -- split evenly across its own vertices; each 4+-gon face
    also pulls its own vertices a little towards its best-fit plane (see
    _face_planarity_residual -- same SVD normal, used here as a
    restoring direction instead of a scalar residual). Returns
    ((N,3) net force on every vertex, max_excess) -- relax_once walks a
    small step along the force (see module docstring's Design notes for
    why edge directions need _safe_unit_vectors rather than a naive
    division) and uses max_excess to pick how small a step is safe (see
    STEP_MAX_MULTIPLIER_STIFF)."""
    n = pts.shape[0]
    force = np.zeros((n, 3))

    diff = pts[edge_bi] - pts[edge_ai]
    dist = np.linalg.norm(diff, axis=1)
    direction = _safe_unit_vectors(diff)
    soft_limit_stretch, max_excess = _soft_limit_stretch(dist, edge_length)
    stretch = (dist - edge_length) / edge_length + soft_limit_stretch
    spring_on_a = stretch[:, None] * direction
    np.add.at(force, edge_ai, spring_on_a)
    np.add.at(force, edge_bi, -spring_on_a)

    if pressure:
        for n_sides, group_idx in all_face_groups.items():
            face_pts = pts[group_idx]                                   # (F, n_sides, 3)
            next_pts = np.roll(face_pts, -1, axis=1)
            area_vector = 0.5 * np.cross(face_pts, next_pts).sum(axis=1)  # (F, 3): area * outward normal
            per_vertex_force = pressure * area_vector / n_sides
            np.add.at(force, group_idx.ravel(),
                      np.repeat(per_vertex_force, n_sides, axis=0))

    if planarity_weight and planarity_groups:
        for group_idx in planarity_groups.values():
            face_pts = pts[group_idx]  # (F, n, 3)
            centered = face_pts - face_pts.mean(axis=1, keepdims=True)
            normals = np.linalg.svd(centered, full_matrices=False)[2][:, -1, :]  # (F, 3)
            signed_dist = np.einsum('fij,fj->fi', centered, normals)  # (F, n)
            pull = -planarity_weight * signed_dist[..., None] * normals[:, None, :]  # (F, n, 3)
            np.add.at(force, group_idx.ravel(), pull.reshape(-1, 3))

    return force, max_excess


def _orientation_signs(pts, faces, idx):
    """pts: (N,3) vertex positions; faces/idx: as above. Returns each
    face's normal sign (+1/-1, or 0 if degenerate) relative to "pointing
    outward from the mesh's overall centroid". A genuinely embedded,
    consistently-wound mesh has every face agree; a mix means some face
    has folded through the mesh (see _is_orientation_consistent)."""
    centroid = pts.mean(axis=0)
    signs = []
    for face in faces:
        face_pts = pts[[idx[v] for v in face]]
        normal = np.cross(face_pts[1] - face_pts[0], face_pts[2] - face_pts[0])
        normal_len = np.linalg.norm(normal)
        outward = face_pts.mean(axis=0) - centroid
        outward_len = np.linalg.norm(outward)
        if normal_len < 1e-9 or outward_len < 1e-9:
            signs.append(0)
        else:
            signs.append(float(np.sign(np.dot(normal / normal_len, outward / outward_len))))
    return signs


def _is_orientation_consistent(pts, faces, idx):
    """True iff every face's normal sign (see _orientation_signs) agrees
    AND points outward (+1) -- i.e. the mesh hasn't folded through
    itself, and hasn't turned inside-out either (all faces agreeing on
    -1 is still a single self-consistent sign, but the wrong one). Used
    by solve_wireframe to judge a fresh, unconstrained candidate embedding
    (see its own docstring)."""
    signs = {s for s in _orientation_signs(pts, faces, idx) if s != 0}
    return signs <= {1.0}


def _min_pairwise_separation(pts):
    """pts: (N,3) vertex positions. Returns the smallest distance between
    any two distinct points (inf if fewer than 2)."""
    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    return d.min() if len(pts) > 1 else np.inf


def _overall_3d_extent(pts):
    """The point cloud's smallest principal-axis extent (via SVD) -- near
    zero means the whole mesh has landed flat in a single plane."""
    centered = pts - pts.mean(axis=0)
    return np.linalg.svd(centered, compute_uv=False)[-1]


CONVERGE_TOL = 1e-4  # max |edge length error| to call a plain edge-length solve "converged"
STRETCH_CAP = 0.08  # max |edge length error| _inflate will tolerate before backing off
MIN_3D_EXTENT = 0.1  # fraction of edge_length; below this, call the whole result "flat"

# fraction of edge_length; a final result with two DISTINCT (non-shared)
# vertices closer than this is rejected as degenerate even if
# _is_orientation_consistent didn't flag it (that check is blind to two
# unrelated vertices landing on almost the same point).
MIN_SEPARATION_FRACTION = 0.15

# A gradually increasing "pressure" ramp -- see module docstring's Design
# notes for why this needs to ramp rather than jump to full strength.
INFLATION_WEIGHTS = (0.1, 0.2, 0.4, 0.8, 1.5, 3.0)

# How strongly to prefer each face staying close to flat, in the final
# polish pass -- low, since inflation already tends to leave faces close
# to flat on its own.
PLANARITY_WEIGHT = 0.1


def _edge_stretch(residual, n_edges):
    """The max |edge-length error| among the first n_edges entries of a
    _residual result."""
    return np.max(np.abs(residual[:n_edges])) if n_edges else 0.0


def _inflate(pts0, faces, edge_ai, edge_bi, idx, edge_length, volume_indices, volume_target=None):
    """pts0: an already edge-length-valid point cloud (N,3); faces/edge_ai/
    edge_bi/idx/edge_length/volume_indices: mesh structure (see
    solve_wireframe). Gradually ramps inflation pressure (INFLATION_WEIGHTS,
    see module docstring's Design notes), re-seeding from the last accepted
    step and stopping at the first step exceeding STRETCH_CAP. Returns
    (pts, edge_stretch, inflation_weight_reached) -- the last of which the
    caller can reuse for a final planarity pass at the same pressure.
    `volume_target` overrides the target derived from faces/edge_length
    (needed for a subdivided fabric mesh, see mesh_subdivide.py)."""
    n_edges = len(edge_ai)
    target = volume_target if volume_target is not None else _sphere_bound_volume(faces, edge_length)
    cur = pts0
    cur_err = _edge_stretch(
        np.linalg.norm(pts0[edge_ai] - pts0[edge_bi], axis=1) - edge_length, n_edges)
    weight_used = 0.0
    for w in INFLATION_WEIGHTS:
        sol = least_squares(_residual, cur.flatten(),
                             args=(edge_ai, edge_bi, volume_indices, None, edge_length, w, target))
        pts = sol.x.reshape(-1, 3)
        err = _edge_stretch(sol.fun, n_edges)
        if err > STRETCH_CAP:
            break
        cur, cur_err, weight_used = pts, err, w
    return cur, cur_err, weight_used


MAX_ORIENTATION_ATTEMPTS = 60  # hard cap on stage-1 restarts spent seeking a usable one
CANDIDATES_PER_ROUND = 8  # how many stage-1 starts to try inflating before giving up a round


def _inflate_from(pts0, faces, edge_ai, edge_bi, idx, edge_length, n_edges,
                   volume_indices, planarity_groups, volume_target=None, scale=None):
    """Runs _inflate from one stage-1 starting point, then (if it inflated
    at all) a light final planarity pass at the same pressure. Returns
    (pts, edge_stretch, weight_reached) -- weight_reached is 0.0 if the
    very first pressure step was rejected. `scale`, if given, replaces
    `edge_length` for the MIN_3D_EXTENT check (needed when edge_length is
    a per-edge array)."""
    if scale is None:
        scale = edge_length
    pts, residual, weight = _inflate(pts0, faces, edge_ai, edge_bi, idx, edge_length,
                                      volume_indices, volume_target)
    if weight:
        target = volume_target if volume_target is not None else _sphere_bound_volume(faces, edge_length)
        sol = least_squares(_residual, pts.flatten(),
                             args=(edge_ai, edge_bi, volume_indices, planarity_groups, edge_length,
                                   weight, target, PLANARITY_WEIGHT))
        polished = sol.x.reshape(-1, 3)
        err = _edge_stretch(sol.fun, n_edges)
        if (err < STRETCH_CAP and _overall_3d_extent(polished) > MIN_3D_EXTENT * scale
                and _is_orientation_consistent(polished, faces, idx)):
            pts, residual = polished, err
    return pts, residual, weight


def solve_wireframe(faces, edge_length=EDGE_LENGTH, seed=0, n_restarts=CANDIDATES_PER_ROUND,
                     volume_target=None):
    """faces: vertex-id loops (see module docstring for the winding
    convention). edge_length: scalar rest length, or a {(a,b): length}
    dict for a non-uniform (e.g. subdivided fabric) mesh -- in which case
    `volume_target` must be given explicitly too, since there's no single
    edge length for _sphere_bound_volume to use.

    Randomly restarts edge-length-fit-then-inflate (see _inflate_from)
    from stage-1 starting points, up to MAX_ORIENTATION_ATTEMPTS, keeping
    the FIRST result that's orientation-consistent (see
    _is_orientation_consistent) and has no two distinct vertices closer
    than MIN_SEPARATION_FRACTION * edge_length. See module docstring's
    Design notes for why whole attempts are retried rather than
    individual ramp steps second-guessed.

    Raises ValueError if MAX_ORIENTATION_ATTEMPTS is exhausted with no
    consistent, well-separated result -- usually a winding-convention bug
    (see this module's docstring).

    Returns (positions, stats): positions is {vertex_id: np.array([x, y,
    z])}, stats has "max_stretch_pct"/"rms_stretch_pct" (how far settled
    edges ended up from `edge_length`) and "residual" (raw max error)."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    edges = mesh_edges(faces)
    if not edges:
        raise ValueError("mesh has no edges")
    n = len(vertex_ids)
    edge_ai, edge_bi = _pair_index_arrays(edges, idx)
    n_edges = len(edges)
    # Built once here rather than re-derived on every _residual call --
    # see _residual's docstring for why that matters.
    volume_indices = _volume_indices(faces, idx)
    planarity_groups = _planarity_groups(faces, idx)

    if isinstance(edge_length, dict):
        if volume_target is None:
            raise ValueError("volume_target must be given explicitly when edge_length is a dict")
        length_arr = np.array([edge_length[e] for e in edges])
        scale = float(np.min(length_arr))
    else:
        length_arr = edge_length
        scale = float(edge_length)

    rng = np.random.default_rng(seed)
    best = None  # (pts, residual)
    attempted = 0
    budget = n_restarts
    while best is None and attempted < MAX_ORIENTATION_ATTEMPTS:
        for _ in range(min(budget, MAX_ORIENTATION_ATTEMPTS - attempted)):
            x0 = rng.normal(scale=scale, size=3 * n)
            sol = least_squares(_residual, x0,
                                 args=(edge_ai, edge_bi, volume_indices, planarity_groups, length_arr))
            pts0 = sol.x.reshape(-1, 3)
            attempted += 1

            pts, residual, weight = _inflate_from(
                pts0, faces, edge_ai, edge_bi, idx, length_arr, n_edges,
                volume_indices, planarity_groups, volume_target=volume_target, scale=scale)
            if (weight and _is_orientation_consistent(pts, faces, idx)
                    and _min_pairwise_separation(pts) > MIN_SEPARATION_FRACTION * scale):
                # the first success is kept as-is, not compared against
                # further candidates: repeated runs land on essentially
                # the same result once one succeeds at all (see module
                # docstring's Design notes), so searching further just
                # costs time for no real gain -- stop immediately.
                best = (pts, residual)
                break
        budget *= 2

    if best is None:
        raise ValueError(
            f"could not find a non-self-intersecting, inflatable embedding in {attempted} "
            f"attempts: every candidate either folded a face inside-out relative to the "
            f"others (see _is_orientation_consistent) or couldn't inflate at all before "
            f"hitting that. This usually means the mesh's faces aren't consistently "
            f"wound -- every face's vertex list should go counterclockwise as seen from "
            f"the outside of the solid, matching how its neighbors reference the same "
            f"shared vertices (see this module's docstring for the convention and "
            f"stretchy_nets/two_pentagons_and_a_square.json for a worked example); "
            f"double-check each face's vertex order.")
    pts, residual = best

    positions = {v: pts[i] for i, v in enumerate(vertex_ids)}

    lengths = np.array([np.linalg.norm(positions[a] - positions[b]) for a, b in edges])
    stretch_pct = 100 * (lengths - length_arr) / length_arr
    stats = dict(residual=residual,
                 max_stretch_pct=float(np.max(np.abs(stretch_pct))),
                 rms_stretch_pct=float(np.sqrt(np.mean(stretch_pct ** 2))))
    return positions, stats


def _edge_setup(faces, edge_length):
    """faces/edge_length: as solve_wireframe. Shared setup for relax_once:
    vertex/edge index arrays plus the precomputed structures
    _relax_force needs (built once here, not per call). Returns
    (vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups,
    planarity_groups, length_arr, scale)."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    edges = mesh_edges(faces)
    edge_ai, edge_bi = _pair_index_arrays(edges, idx)
    all_face_groups = _face_index_groups(faces, idx)
    planarity_groups = _planarity_groups(faces, idx)
    if isinstance(edge_length, dict):
        length_arr = np.array([edge_length[e] for e in edges])
        scale = float(np.min(length_arr)) if len(length_arr) else 1.0
    else:
        length_arr = edge_length
        scale = float(edge_length)
    return (vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, planarity_groups,
            length_arr, scale)


def _positions_and_stretch(pts, vertex_ids, edges, length_arr):
    """pts: (N,3) flat solved positions; vertex_ids/edges/length_arr: as
    from _edge_setup. Returns (positions dict, max_stretch_pct,
    rms_stretch_pct)."""
    positions = {v: pts[i] for i, v in enumerate(vertex_ids)}
    lengths = np.array([np.linalg.norm(positions[a] - positions[b]) for a, b in edges])
    stretch_pct = 100 * (lengths - length_arr) / length_arr
    return positions, float(np.max(np.abs(stretch_pct))), float(np.sqrt(np.mean(stretch_pct ** 2)))


# relax_once's convergence check: a step counts as "at rest" once every
# vertex's own net force drops below this. Compared directly against the
# force computed by _relax_force -- unlike the old scipy `optimality`
# measure, this is just "how far from equilibrium is the worst vertex",
# so it's meaningful on its own rather than needing scipy's internals to
# interpret.
CONVERGENCE_GTOL = 1e-4

# Explicit relaxation step size: the vertex with the largest net force
# moves this fraction of the mesh's own rest edge length in one
# iteration; every other vertex moves proportionally less (force is
# normalized by its own max each step). Keeps steps small and stable
# (a real physical walk, not a linearized jump that can overshoot the
# reachable equilibrium -- see module docstring's Design notes) while
# adapting automatically to whatever pressure or mesh scale is in play.
STEP_MAX_FRACTION = 0.2

# The `.../max_force` half of STEP_MAX_FRACTION's step is only meant to
# shrink the step when force is LARGE (about to overshoot); left alone it
# also GROWS the step without bound as force shrinks near equilibrium,
# which stalls convergence (verified: pressure=1 on a plain cube ran the
# full MAX_UNBOUNDED_STEPS without ever settling below gtol, oscillating
# rather than damping down). Capping the per-step multiplier keeps this
# from an undamped-oscillator's back-and-forth.
#
# Two tiers, not one: a large force doesn't mean a large SAFE step once
# SOFT_LIMIT_STIFFNESS's much steeper near-the-limit force is involved
# (force changes fast with position right there), so that regime needs a
# much smaller cap (_STIFF) -- verified 0.1/0.02/0.005 each oscillate
# forever at high pressure (60) on a plain cube, while 0.001 converges
# there (88 steps), agreeing with 0.0005 on the same final shape (a real
# fixed point, not step noise). But applying _STIFF everywhere makes
# ordinary low-pressure inflation (which never nears the soft limit)
# take ~100x more steps than it needs -- verified pressure=1 on a plain
# cube didn't even finish 100,000 steps under a flat 0.001, having
# converged in ~1,300 under 0.1 when nothing was clamped. relax_once
# switches to _STIFF only on a step where _relax_force reports the soft
# limit actually engaged (max_excess > 0), so ordinary inflation keeps
# the fast, generous step size.
#
# _BASE itself needed lowering from 0.1 to 0.05: a denser mesh has more
# springs meeting at each vertex, which raises that vertex's EFFECTIVE
# combined stiffness even with no soft limit involved at all -- verified
# a level-3-subdivided cube at pressure=1 (194 vertices) settles into an
# exact, undamped 2-cycle under 0.1 (max_stretch_pct alternates between
# ~18.9% and ~24.4% forever, never converging), while 0.05/0.02/0.01 all
# converge cleanly to the SAME ~8.5% fixed point.
STEP_MAX_MULTIPLIER_BASE = 0.05
STEP_MAX_MULTIPLIER_STIFF = 0.001

# Hard cap on iterations when max_nfev=None (run-to-convergence): explicit
# steps have no scipy-style internal budget of their own, so this stands
# in for one.
MAX_UNBOUNDED_STEPS = 200_000

# Second convergence path, alongside gtol: some meshes settle into a
# tiny persistent wobble or a very long, slow tail -- force stays above
# gtol (sometimes indefinitely) while max_stretch_pct has effectively
# stopped moving. Every vertex's force being individually near-zero is a
# stricter demand than "the shape has stopped changing", the thing this
# app and its user actually care about -- so relax_once also declares
# convergence once max_stretch_pct's range over the last STALL_WINDOW
# steps stays under STALL_TOL_PCT, mirroring scipy's own ftol/xtol (a
# plateau check ALONGSIDE its gtol, not instead of it) that the old
# least_squares-based relax_once used to get for free. STALL_TOL_PCT=1.0
# (a full percentage point of stretch, not a fraction of one) is
# deliberately generous -- verified across cube/tetrahedron/octahedron/
# icosahedron/dodecahedron/three_squares/two_pentagons_and_a_square at
# several pressures, plus a level-3-subdivided cube, that this still
# lands within a point or two of what a strict gtol-only run reaches.
STALL_WINDOW = 200
STALL_TOL_PCT = 1.0


def mesh_volume(positions, faces):
    """positions: {vertex_id: [x,y,z]}; faces: vertex-id loops. Returns
    the mesh's current total enclosed volume (see _mesh_volume), for
    callers that don't want to build the private index-array structures
    themselves."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    pts = np.array([positions[v] for v in vertex_ids])
    return _mesh_volume(pts, _volume_indices(faces, idx))


def per_face_volumes(positions, faces):
    """positions: {vertex_id: [x,y,z]}; faces: vertex-id loops. Returns
    each face's own volume contribution (see _per_face_volumes) -- a
    general per-face-geometry utility."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    pts = np.array([positions[v] for v in vertex_ids])
    return _per_face_volumes(pts, _face_volume_group(faces, idx))


def is_orientation_consistent(positions, faces):
    """positions: {vertex_id: [x,y,z]}; faces: vertex-id loops. True iff
    every face still agrees on outward orientation (see
    _is_orientation_consistent) -- a general-purpose public wrapper
    around it."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    pts = np.array([positions[v] for v in vertex_ids])
    return _is_orientation_consistent(pts, faces, idx)


def relax_once(positions, faces, edge_length, pressure=0.0,
                planarity_weight=PLANARITY_WEIGHT, max_nfev=None, stop_event=None,
                gtol=CONVERGENCE_GTOL):
    """positions: {vertex_id: [x,y,z]} starting point; faces/edge_length:
    as solve_wireframe. Runs ONE relaxation pass at a fixed `pressure` --
    no automatic ramp, no random restarts (that's solve_wireframe's job);
    call again with the result to keep steering it. Each iteration moves
    every vertex a small step along its own net force from _relax_force
    (see module docstring's Design notes for why this walks explicitly
    rather than handing the force balance to a Newton-style solver) --
    `pressure` is a real per-face outward force, with no volume or
    remembered state anywhere in it.

    `max_nfev` caps the number of steps; None runs until convergence
    (capped at MAX_UNBOUNDED_STEPS as a runaway guard), via EITHER of two
    criteria: every vertex's force drops below `gtol`, or max_stretch_pct
    stops moving for STALL_WINDOW steps (see STALL_WINDOW's comment for
    why both exist). `stop_event` (a threading.Event), if given, is
    checked before each step and aborts at the next one, returning
    whatever position was last reached.

    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    max_force, converged). `max_force` is the worst vertex's net force at
    the returned position (compare against `gtol`), None if stopped
    before a single step ran. `converged` is True only if one of the two
    criteria above (not the step cap or a stop request) is what stopped
    it."""
    vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, planarity_groups, length_arr, scale = \
        _edge_setup(faces, edge_length)
    pts = np.array([positions[v] for v in vertex_ids], dtype=float)
    step_cap = max_nfev if max_nfev is not None else MAX_UNBOUNDED_STEPS

    steps_taken = 0
    converged = False
    max_force = None
    recent_max_stretch = collections.deque(maxlen=STALL_WINDOW)
    for steps_taken in range(1, step_cap + 1):
        if stop_event is not None and stop_event.is_set():
            steps_taken -= 1
            break
        force, max_excess = _relax_force(pts, edge_ai, edge_bi, all_face_groups, planarity_groups,
                                          length_arr, pressure, planarity_weight)
        max_force = float(np.linalg.norm(force, axis=1).max())
        if max_force < gtol:
            converged = True
            break
        dist = np.linalg.norm(pts[edge_bi] - pts[edge_ai], axis=1)
        recent_max_stretch.append(float(np.max(np.abs(100 * (dist - length_arr) / length_arr))))
        if (len(recent_max_stretch) == STALL_WINDOW
                and max(recent_max_stretch) - min(recent_max_stretch) < STALL_TOL_PCT):
            converged = True
            break
        step_mult = STEP_MAX_MULTIPLIER_STIFF if max_excess > 0 else STEP_MAX_MULTIPLIER_BASE
        dt = min(step_mult, STEP_MAX_FRACTION * scale / max_force)
        pts = pts + dt * force

    new_positions, max_stretch, rms_stretch = _positions_and_stretch(pts, vertex_ids, edges, length_arr)
    return new_positions, steps_taken, max_stretch, rms_stretch, max_force, converged
