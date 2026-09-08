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

- **Per-face, target-free pressure in relax_once** (_relax_residual):
  _residual's pressure term (`inflation_weight * (target - volume)`) is a
  two-sided penalty that plateaus once volume nears its fixed target --
  right for the automatic solve_wireframe ramp (which needs to know when
  to stop), backwards for a human turning a pressure dial who expects
  "more pressure = more inflated". relax_once instead uses ONE
  `pressure * exp(-v_f / reference_volume)` term PER FACE, not a single
  global term for the mesh: a single global term gives a many-faced mesh
  a cheap way to "satisfy" it by folding one small patch through itself
  (spiking the naive signed-volume sum) while leaving everything else
  untouched -- verified to happen immediately on cube_res3.json (110
  vertices) even under a gradual ramp. Splitting it per face closes that
  loophole (folding one face's patch only hurts that face's own
  residual) and happens to match real pressure's physics better too
  (dV/d(extrusion) = area, so this term's gradient is naturally a
  force-per-area quantity). `reference_volume` (per_face_volumes on the
  mesh's OWN starting shape) normalizes each face's volume against the
  mesh's own scale, since raw volume differs by orders of magnitude
  between e.g. a cube and a dodecahedron at the same edge length.

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
ALGORITHM_VERSION = 5


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


def _sphere_bound_volume(faces, edge_length):
    """Volume of the sphere with the same total surface area as `faces`
    (each assumed a regular polygon of `edge_length` sides) -- an
    optimistic, normally-unreachable inflation target, scaled to the
    mesh's own size. See module docstring's Design notes for how
    _inflate uses this as its pressure target."""
    total_area = sum((k / 4.0) / np.tan(np.pi / k) for k in (len(f) for f in faces))
    total_area *= edge_length ** 2
    r = np.sqrt(total_area / (4 * np.pi))
    return (4 / 3) * np.pi * r ** 3


def _edge_and_planarity_parts(pts, edge_ai, edge_bi, edge_length, planarity_weight, planarity_groups):
    """Shared residual pieces for _residual/_relax_residual: RELATIVE
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
    _relax_residual instead, which has no target -- see its docstring."""
    pts = flat.reshape(-1, 3)
    parts = _edge_and_planarity_parts(pts, edge_ai, edge_bi, edge_length, planarity_weight, planarity_groups)
    if inflation_weight:
        vol = _mesh_volume(pts, volume_indices)
        parts.insert(1, np.array([inflation_weight * (inflation_target - vol)]))
    return np.concatenate(parts)


def _relax_residual(flat, edge_ai, edge_bi, face_volume_group, planarity_groups, edge_length,
                     pressure=0.0, planarity_weight=0.0, reference_volume=1.0):
    """relax_once's objective: edge-length + planarity plus a TARGET-FREE,
    PER-FACE pressure term `pressure * exp(-v_f / reference_volume)` --
    see module docstring's Design notes for why per-face and why no
    target. `reference_volume` (scalar or per-face array) normalizes each
    face's own volume against the mesh's characteristic scale."""
    pts = flat.reshape(-1, 3)
    parts = _edge_and_planarity_parts(pts, edge_ai, edge_bi, edge_length, planarity_weight, planarity_groups)
    if pressure:
        face_volumes = _per_face_volumes(pts, face_volume_group)
        parts.insert(1, pressure * np.exp(-face_volumes / reference_volume))
    return np.concatenate(parts)


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
    (ignoring degenerate 0s) -- i.e. the mesh hasn't folded through
    itself anywhere."""
    return len({s for s in _orientation_signs(pts, faces, idx) if s != 0}) <= 1


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
    _residual/_relax_residual result."""
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
    _relax_residual needs (built once here, not per call). Returns
    (vertex_ids, idx, edges, edge_ai, edge_bi, face_volume_group,
    planarity_groups, length_arr, scale)."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    edges = mesh_edges(faces)
    edge_ai, edge_bi = _pair_index_arrays(edges, idx)
    face_volume_group = _face_volume_group(faces, idx)
    planarity_groups = _planarity_groups(faces, idx)
    if isinstance(edge_length, dict):
        length_arr = np.array([edge_length[e] for e in edges])
        scale = float(np.min(length_arr)) if len(length_arr) else 1.0
    else:
        length_arr = edge_length
        scale = float(edge_length)
    return (vertex_ids, idx, edges, edge_ai, edge_bi, face_volume_group, planarity_groups,
            length_arr, scale)


def _positions_and_stretch(pts, vertex_ids, edges, length_arr):
    """pts: (N,3) flat solved positions; vertex_ids/edges/length_arr: as
    from _edge_setup. Returns (positions dict, max_stretch_pct,
    rms_stretch_pct)."""
    positions = {v: pts[i] for i, v in enumerate(vertex_ids)}
    lengths = np.array([np.linalg.norm(positions[a] - positions[b]) for a, b in edges])
    stretch_pct = 100 * (lengths - length_arr) / length_arr
    return positions, float(np.max(np.abs(stretch_pct))), float(np.sqrt(np.mean(stretch_pct ** 2)))


# scipy.optimize.least_squares' own default gtol -- passed explicitly so
# relax_once's caller can always know and display the exact tolerance an
# `optimality` value is being compared against.
CONVERGENCE_GTOL = 1e-8

# Status codes least_squares returns when it stopped because ITS OWN
# tolerance (gtol/ftol/xtol) was satisfied, as opposed to exhausting
# max_nfev (0) or a Stop request cutting it off early.
_CONVERGED_STATUSES = (1, 2, 3, 4)


class RelaxStopped(Exception):
    """Raised internally by relax_once's residual wrapper when the given
    stop_event is set -- never escapes relax_once itself."""


def mesh_volume(positions, faces):
    """positions: {vertex_id: [x,y,z]}; faces: vertex-id loops. Returns
    the mesh's current total enclosed volume (see _mesh_volume), for
    callers that don't want to build the private index-array structures
    themselves. Use per_face_volumes instead for relax_once's
    `reference_volume` (its pressure term is per-face, not a single total)."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    pts = np.array([positions[v] for v in vertex_ids])
    return _mesh_volume(pts, _volume_indices(faces, idx))


def per_face_volumes(positions, faces):
    """positions: {vertex_id: [x,y,z]}; faces: vertex-id loops. Returns
    each face's own volume contribution (see _per_face_volumes) -- pass
    this on the mesh's own STARTING shape (once per net) to get the
    `reference_volume` array relax_once's pressure term needs."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    pts = np.array([positions[v] for v in vertex_ids])
    return _per_face_volumes(pts, _face_volume_group(faces, idx))


def is_orientation_consistent(positions, faces):
    """positions: {vertex_id: [x,y,z]}; faces: vertex-id loops. True iff
    every face still agrees on outward orientation (see
    _is_orientation_consistent). Exposed as a cheap safety net for a
    caller like inflate_polyhedron_app's interactive Inflate loop, which
    (unlike solve_wireframe) has no random-restart search of its own to
    fall back on if one incremental step folds the mesh through itself."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    pts = np.array([positions[v] for v in vertex_ids])
    return _is_orientation_consistent(pts, faces, idx)


def relax_once(positions, faces, edge_length, pressure=0.0,
                planarity_weight=PLANARITY_WEIGHT, max_nfev=None, stop_event=None,
                gtol=CONVERGENCE_GTOL, reference_volume=1.0):
    """positions: {vertex_id: [x,y,z]} starting point; faces/edge_length:
    as solve_wireframe. Runs ONE relaxation pass at a fixed `pressure` --
    no automatic ramp, no random restarts (that's _inflate/solve_wireframe's
    job); the caller picks the pressure and how much work to do, and can
    call this again with the result to keep steering it. Uses
    _relax_residual (target-free, per-face pressure -- see module
    docstring's Design notes), NOT _residual.

    `reference_volume` should be computed ONCE per net (via
    per_face_volumes on its starting shape) and reused across calls, so a
    given pressure keeps meaning the same thing across repeated clicks --
    recomputing it from the evolving mesh would drag the target along
    with the user's own pressure dial.

    `max_nfev` caps solver evaluations, used as a practical stand-in for
    "how many steps" (scipy's trust-region solvers expose no cleaner
    "N iterations" knob); None runs to `gtol` instead. `stop_event`
    (a threading.Event), if given, is checked every evaluation and aborts
    at the next one, returning whatever position was last evaluated.

    Returns (new_positions, nfev, max_stretch_pct, rms_stretch_pct,
    optimality, converged). `optimality` is scipy's first-order optimality
    measure (compare against `gtol`), None if stopped before scipy
    returned a result. `converged` is True only if scipy's own tolerance
    (not the step cap or a stop request) is what stopped it."""
    vertex_ids, idx, edges, edge_ai, edge_bi, face_volume_group, planarity_groups, length_arr, _ = \
        _edge_setup(faces, edge_length)
    x0 = np.array([positions[v] for v in vertex_ids]).flatten()

    last_x = [x0]
    raw_calls = [0]

    def wrapped_residual(x, *args):
        raw_calls[0] += 1
        last_x[0] = x
        if stop_event is not None and stop_event.is_set():
            raise RelaxStopped()
        return _relax_residual(x, *args)

    try:
        sol = least_squares(wrapped_residual, x0,
                             args=(edge_ai, edge_bi, face_volume_group, planarity_groups, length_arr,
                                   pressure, planarity_weight, reference_volume),
                             max_nfev=max_nfev, gtol=gtol)
        pts = sol.x.reshape(-1, 3)
        # scipy's own nfev -- NOT wrapped_residual's raw call count, which
        # can run well past max_nfev's nominal value before scipy checks
        # the cap again (e.g. mid Jacobian estimate): using sol.nfev here
        # keeps a "N steps" request corresponding to roughly N reported
        # steps.
        reported_nfev = sol.nfev
        optimality = float(sol.optimality)
        converged = sol.status in _CONVERGED_STATUSES
    except RelaxStopped:
        # scipy never returned, so there's no sol.nfev -- fall back to the
        # wrapper's own raw call count, capped at max_nfev (the caller's
        # declared step budget) so a Stop doesn't look like it consumed
        # far more "steps" than the caller actually asked for.
        pts = last_x[0].reshape(-1, 3)
        reported_nfev = min(raw_calls[0], max_nfev) if max_nfev is not None else raw_calls[0]
        optimality = None
        converged = False

    new_positions, max_stretch, rms_stretch = _positions_and_stretch(pts, vertex_ids, edges, length_arr)
    return new_positions, reported_nfev, max_stretch, rms_stretch, optimality, converged
