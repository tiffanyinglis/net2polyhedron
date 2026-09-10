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
structure as the original. A subtler problem can still reach the pipeline
even so: relax_initial_configuration's random-start-plus-spring relax
(see its own docstring) has no notion of "outward" at all, so it can just
as easily land globally inside-out, or (rarer, and not fixed for free)
genuinely mixed -- some faces each way. See _orientation_signs/
_is_orientation_consistent for how a caller can check this, and
relax_initial_configuration's own docstring for what it does about it.

The overall pipeline this module supports (used by inflate_polyhedron_app,
see its own module docstring): random_initial_positions gives a fresh net
a starting point that isn't even a meaningful embedding yet;
relax_initial_configuration pulls that into a well-separated 3D shape
using pure spring forces (no pressure); relax_once then takes over for
interactive, pressure-based "inflation" -- letting edges stretch a little
and faces bend to round the shape out, exactly what makes an
otherwise-rigid-impossible net (like
data/input/stretchy_nets/two_pentagons_and_a_square.json) realizable at
all, and what puffs an ordinary closed solid (see
data/input/stretchy_nets/{tetrahedron,cube,octahedron,icosahedron,dodecahedron}.json)
into a rounded, convex, plushie-like shape (literally the same idea as
stuffing/blowing up a plush toy or balloon until the fabric's own tension
stops it).

Design notes (the "why" behind choices that would otherwise look
arbitrary -- kept here rather than repeated across every function that
touches them, per this project's docstring convention in
.claude/skills/net-fold-project/SKILL.md):

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

- **No runaway guard on pressure, deliberately.** Plain Hooke's-law
  springs can't hold arbitrarily high pressure -- past some critical
  value there's no equilibrium at all, since pressure's push grows with
  `area` (~edge_length^2) while a spring's pull only grows linearly. A
  per-edge stretch limit was tried here to force an equilibrium to exist
  at any pressure, and removed again: the actual fix for "what pressure
  should I use" is estimate_pressure_for_target_stretch calibrating a
  modest, appropriate pressure per net in the first place (see its own
  docstring), not clamping a badly-chosen one after the fact -- a
  correctly-calibrated pressure never gets near the critical value this
  would have guarded against. See .claude/skills/net-fold-project/SKILL.md
  for this project's general stance on adding a term like that.
"""
import collections
import json

import numpy as np

from ..geometry.polyhedron import Polyhedron

EDGE_LENGTH = 1.0


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
    vertex, flattened into three parallel int arrays (v0, v1, v2)."""
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
    _relax_force's planarity pull: {n: array of shape (num_n_vertex_faces,
    n)} for every face with 4+ vertices (triangles are always exactly
    planar and excluded). Lets same-size faces batch into one SVD call."""
    groups = {}
    for face in faces:
        n = len(face)
        if n < 4:
            continue
        groups.setdefault(n, []).append([idx[v] for v in face])
    return {n: np.array(rows, dtype=int) for n, rows in groups.items()}


def _mesh_volume(pts, volume_indices):
    """pts: (N,3) vertex positions; volume_indices: _volume_indices'
    precomputed (v0,v1,v2) index arrays. Returns the mesh's signed
    enclosed volume via the divergence theorem (fan-triangulated, summed
    against the origin)."""
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


def _relax_force(pts, edge_ai, edge_bi, all_face_groups, planarity_groups, edge_length,
                  pressure=0.0, planarity_weight=0.0):
    """relax_once's per-step force: a genuine mechanical force balance.
    Each edge is a Hooke's-law spring (relative stretch (dist-rest)/rest
    along the edge direction); each face applies a real outward pressure
    force, `pressure * area * outward_normal` -- area and normal computed
    together straight from its own vertex loop via `0.5 * sum_i
    cross(p_i, p_{i+1})` (Newell's method) -- split evenly across its own
    vertices; each 4+-gon face also pulls its own vertices a little
    towards its own best-fit plane (SVD normal, used here as a restoring
    direction). Returns the (N,3) net force on every vertex -- relax_once
    walks a small step along it (see module docstring's Design notes for
    why edge directions need _safe_unit_vectors rather than a naive
    division)."""
    n = pts.shape[0]
    force = np.zeros((n, 3))

    diff = pts[edge_bi] - pts[edge_ai]
    dist = np.linalg.norm(diff, axis=1)
    direction = _safe_unit_vectors(diff)
    stretch = (dist - edge_length) / edge_length
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

    return force


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
    -1 is still a single self-consistent sign, but the wrong one)."""
    signs = {s for s in _orientation_signs(pts, faces, idx) if s != 0}
    return signs <= {1.0}


# How strongly to prefer each face staying close to flat, in the final
# polish pass -- low, since inflation already tends to leave faces close
# to flat on its own.
PLANARITY_WEIGHT = 0.1


def _edge_setup(faces, edge_length):
    """faces: vertex-id loops (see module docstring for the winding
    convention); edge_length: scalar rest length, or a {(a,b): length}
    dict for a non-uniform (e.g. subdivided) mesh. Shared setup for
    relax_once/relax_initial_configuration: vertex/edge index arrays plus
    the precomputed structures _relax_force needs (built once here, not
    per call). Returns (vertex_ids, idx, edges, edge_ai, edge_bi,
    all_face_groups, planarity_groups, length_arr, scale)."""
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
# Needed lowering from 0.1 to 0.05: a denser mesh has more springs
# meeting at each vertex, which raises that vertex's EFFECTIVE combined
# stiffness -- verified a level-3-subdivided cube at pressure=1 (194
# vertices) settles into an exact, undamped 2-cycle under 0.1
# (max_stretch_pct alternates between ~18.9% and ~24.4% forever, never
# converging), while 0.05/0.02/0.01 all converge cleanly to the SAME
# ~8.5% fixed point.
STEP_MAX_MULTIPLIER = 0.05

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


def _explicit_relax_loop(pts, edge_ai, edge_bi, length_arr, scale, force_fn,
                          max_nfev, stop_event, gtol):
    """Shared explicit-relaxation driver for relax_once and
    relax_initial_configuration -- the only thing that varies between
    them is the force itself (`force_fn(pts) -> (N,3)`); the walking
    logic (step size, stopping criteria) is identical, so it lives here
    once rather than being kept in sync by hand in two places.

    Repeatedly nudges `pts` a small step along `force_fn(pts)` (see
    STEP_MAX_FRACTION/STEP_MAX_MULTIPLIER) until EITHER every vertex's
    force drops below `gtol`, or max_stretch_pct stops moving for
    STALL_WINDOW steps (see STALL_WINDOW's own comment for why both
    exist), or `max_nfev`/`stop_event` cuts it off first. Returns (pts,
    steps_taken, max_force, converged) -- callers each compute their own
    final positions/stretch stats from `pts`."""
    step_cap = max_nfev if max_nfev is not None else MAX_UNBOUNDED_STEPS
    steps_taken = 0
    converged = False
    max_force = None
    recent_max_stretch = collections.deque(maxlen=STALL_WINDOW)
    for steps_taken in range(1, step_cap + 1):
        if stop_event is not None and stop_event.is_set():
            steps_taken -= 1
            break
        force = force_fn(pts)
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
        dt = min(STEP_MAX_MULTIPLIER, STEP_MAX_FRACTION * scale / max_force)
        pts = pts + dt * force
    return pts, steps_taken, max_force, converged


def relax_once(positions, faces, edge_length, pressure=0.0,
                planarity_weight=PLANARITY_WEIGHT, max_nfev=None, stop_event=None,
                gtol=CONVERGENCE_GTOL):
    """positions: {vertex_id: [x,y,z]} starting point; faces/edge_length:
    as _edge_setup. Runs ONE relaxation pass at a fixed `pressure` -- no
    automatic ramp; call again with the result to keep steering it. Each
    iteration moves
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
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)

    def force_fn(pts):
        return _relax_force(pts, edge_ai, edge_bi, all_face_groups, planarity_groups,
                             length_arr, pressure, planarity_weight)

    pts, steps_taken, max_force, converged = _explicit_relax_loop(
        pts0, edge_ai, edge_bi, length_arr, scale, force_fn, max_nfev, stop_event, gtol)
    new_positions, max_stretch, rms_stretch = _positions_and_stretch(pts, vertex_ids, edges, length_arr)
    return new_positions, steps_taken, max_stretch, rms_stretch, max_force, converged


# "5x5x5" per the user's own suggestion, in edge_length units -- big
# enough that a mesh of a few dozen vertices starts well spread out
# rather than all clumped near the origin.
INITIAL_RANDOM_SPREAD = 5.0


def random_initial_positions(faces, spread=INITIAL_RANDOM_SPREAD, seed=0):
    """Independent uniform-random position in [-spread/2, spread/2]^3 for
    every vertex `faces` references. Deliberately NOT a meaningful
    embedding (this doesn't even look at edge_length) -- just a starting
    point for relax_initial_configuration's spring force to pull into a
    well-separated 3D shape on its own, the same way force-directed graph
    layout starts from noise."""
    vertex_ids = sorted({v for face in faces for v in face})
    rng = np.random.default_rng(seed)
    return {v: rng.uniform(-spread / 2, spread / 2, size=3) for v in vertex_ids}


def _spring_only_force(pts, edge_ai, edge_bi, edge_length):
    """Pure Hooke's-law spring force for relax_initial_configuration --
    the same per-edge term as _relax_force, with no pressure and no
    planarity. Faces aren't expected to be flat or even
    non-self-intersecting at this stage (see relax_initial_configuration's
    docstring); the only goal is a well-separated, edge-length-plausible
    starting point to hand off to the real per-face pressure model
    afterward."""
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


def relax_initial_configuration(positions, faces, edge_length,
                                 max_nfev=None, stop_event=None, gtol=CONVERGENCE_GTOL):
    """positions/faces/edge_length: as relax_once, but `positions` is
    typically random_initial_positions' output here, not a meaningful
    embedding -- this is what turns it into one, WITHOUT ever touching
    pressure: pure Hooke's-law springs only (_spring_only_force). Nothing
    here constrains vertices that don't share an edge, or fixes overall
    position/scale, so the result can end up anywhere in space, at any
    scale, and self-intersecting -- fine, since the only goal is a
    well-separated, edge-length-plausible starting point for relax_once's
    real per-face pressure model afterward. Any view of this result must
    re-derive its own camera
    framing from its actual bounding box (see _draw_wireframe_panel)
    rather than assuming it lands near the origin or at a familiar scale.
    See this module's docstring for why a plain polyhedron wireframe
    (e.g. a cube's own 12 edges, no face diagonals) needs to already be
    subdivided into all-triangle faces (see mesh_levels.subdivide_once)
    before this can find a well-defined 3D shape at all: an unbraced
    quad/pentagon face is a genuine mechanism (like an unbraced
    rectangular frame), not a rigid one, so springs alone can't stop it
    flexing arbitrarily.

    Same stopping rule as relax_once (see _explicit_relax_loop): `gtol`
    on the worst vertex's force, OR max_stretch_pct stalling for
    STALL_WINDOW steps, OR `max_nfev`/`stop_event`. Returns
    (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    max_force, converged) -- exactly relax_once's own return shape."""
    vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, planarity_groups, length_arr, scale = \
        _edge_setup(faces, edge_length)
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)

    def force_fn(pts):
        return _spring_only_force(pts, edge_ai, edge_bi, length_arr)

    pts, steps_taken, max_force, converged = _explicit_relax_loop(
        pts0, edge_ai, edge_bi, length_arr, scale, force_fn, max_nfev, stop_event, gtol)

    # A pure-spring relax has no notion of "outward" at all -- nothing in
    # the force cares which way a face's normal points, so it lands
    # globally inside-out about as often as right-side-out. If every face
    # agrees on being inward, reflecting every vertex through the mesh's
    # own centroid is a free fix: a point reflection is an isometry
    # (every pairwise distance, so every edge length and stretch stat, is
    # unchanged), and it flips every face's sign AT ONCE, since a face's
    # normal itself is unchanged by the reflection (cross(-a,-b) =
    # cross(a,b)) while its "outward from centroid" reference direction
    # flips (see _orientation_signs) -- so what was a consistent wrong
    # answer becomes a consistent right one, for free. A genuinely MIXED
    # result (some faces each way) can't be fixed this cheaply and is
    # returned as-is; per instructions, that residual case is left to the
    # subsequent pressure model rather than retried here.
    idx = {v: i for i, v in enumerate(vertex_ids)}
    if {s for s in _orientation_signs(pts, faces, idx) if s != 0} == {-1.0}:
        pts = 2 * pts.mean(axis=0) - pts

    new_positions, max_stretch, rms_stretch = _positions_and_stretch(pts, vertex_ids, edges, length_arr)
    return new_positions, steps_taken, max_stretch, rms_stretch, max_force, converged


# Empirical starting point for estimate_pressure_for_target_stretch: bisected
# the pressure giving ~10% stretch on each of the 5 Platonic solids (max
# and RMS stretch coincide there -- a regular solid stretches every edge
# equally) and found `pressure * total_rest_area` lands in a much tighter
# band (1.9-3.2) than raw pressure does (0.11-1.44) -- i.e. required
# pressure scales with how much total AREA it's pushing against, not
# vertex/face count. This is the average of pressure*area/target_fraction
# across those 5 solids (range was 19-32) -- a decent first guess, not
# exact, which is why the function refines it against an actual
# relax_once result rather than trusting it alone.
_PRESSURE_AREA_PRODUCT_ESTIMATE = 25.0

# How far a single calibration step is allowed to rescale pressure --
# guards against a wild jump if one trial's stretch reading is degenerate
# (e.g. near zero), while still letting normal cases converge in a couple
# of iterations (stretch responds roughly linearly to pressure in the low-
# stretch regime this targets, verified against the bisection trace above).
_PRESSURE_RATIO_CLAMP = (0.2, 5.0)

DEFAULT_TARGET_RMS_STRETCH_PCT = 8.0


def estimate_pressure_for_target_stretch(positions, faces, edge_length,
                                          target_rms_pct=DEFAULT_TARGET_RMS_STRETCH_PCT,
                                          planarity_weight=PLANARITY_WEIGHT, max_iterations=4,
                                          tol_pct=1.0, max_nfev_per_trial=20000, stop_event=None):
    """positions/faces/edge_length: as relax_once. Finds a pressure whose
    relax_once result lands within `tol_pct` of `target_rms_pct` RMS
    stretch (RMS, not max -- an irregular/subdivided mesh stretches
    unevenly, and RMS is what the "Target RMS stretch" spinner asks for),
    starting from _PRESSURE_AREA_PRODUCT_ESTIMATE's geometric guess and
    refining it by relaxing at that pressure, then rescaling pressure by
    (target / achieved) -- clamped by _PRESSURE_RATIO_CLAMP -- and trying
    again, up to `max_iterations` times. Every trial starts fresh from
    the given `positions` (not chained from the previous trial's
    result), since different pressures can have very different equilibria
    and this is searching for the pressure, not steering a shape.

    Keeps whichever trial got CLOSEST to the target rather than just the
    last one: the rescale step assumes more pressure means more stretch,
    which fails on at least one known net (data/input/stretchy_nets/
    three_squares.json actually stretches LESS as pressure rises -- a
    genuine property of that topology, not a bug here) -- without this,
    a net where that assumption is wrong would escalate pressure every
    iteration chasing a target it's moving away from. Returns (pressure,
    new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    max_force, converged) -- the last five exactly as relax_once's own
    return, from whichever trial this settled on."""
    total_area = _total_rest_area(faces, edge_length)
    pressure = _PRESSURE_AREA_PRODUCT_ESTIMATE * (target_rms_pct / 100.0) / total_area
    best_error, best_pressure, best_result = None, None, None
    for _ in range(max_iterations):
        result = relax_once(positions, faces, edge_length, pressure, planarity_weight,
                             max_nfev=max_nfev_per_trial, stop_event=stop_event)
        _, _, _, rms_stretch, _, _ = result
        error = abs(rms_stretch - target_rms_pct)
        if best_error is None or error < best_error:
            best_error, best_pressure, best_result = error, pressure, result
        stopped = stop_event is not None and stop_event.is_set()
        if stopped or error < tol_pct or rms_stretch <= 0:
            break
        ratio = target_rms_pct / rms_stretch
        ratio = min(max(ratio, _PRESSURE_RATIO_CLAMP[0]), _PRESSURE_RATIO_CLAMP[1])
        pressure *= ratio
    new_positions, steps_taken, max_stretch, rms_stretch, max_force, converged = best_result
    return best_pressure, new_positions, steps_taken, max_stretch, rms_stretch, max_force, converged
