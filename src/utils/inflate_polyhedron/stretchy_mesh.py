"""Loader + solver for STRETCHY meshes: a polyhedron-like net, closed or
OPEN, whose faces are combinatorially valid (every edge shared by AT MOST
two faces, in opposite directions -- see WINDING CONVENTION below) but
that cannot necessarily be realized with perfectly RIGID, FLAT faces
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
solid (or, for a net that's deliberately left OPEN -- a bowl, a patch, a
box with no lid -- OUTSIDE whichever side was chosen as the outside; the
winding is what encodes that choice, not a separate flag). Concretely:
for any edge (v, w) shared by two faces, one face's loop contains it as
v -> w and the other's contains it as w -> v -- never the same direction
twice. An edge referenced by only ONE face (no partner at all) is a free
BOUNDARY edge -- perfectly valid, and simply not shared with anything;
this is what lets a net stay open rather than requiring a full closed
2-manifold. load_stretchy_mesh only rejects a directed edge that appears
MORE than once (the one case that's always a genuine error, since two
faces would then be claiming to own the same directed edge, or a face
would be self-intersecting along it) -- raising a clear error naming the
offending edge(s) if that happens.

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
  volume anywhere** (_relax_force): each edge is a HARDENING spring (a
  `stretch + HARDENING_CUBIC_COEFFICIENT * stretch**3` restoring force --
  see the next note for why); each face applies a real outward force, `pressure * area * normal`, split across
  its own vertices. Each call moves every vertex a small step along its
  OWN net force (explicit relaxation), not a least_squares solve: a
  Newton-style solver re-linearizes the whole mesh and can jump straight
  past the physically-reachable equilibrium to a distant, spurious one
  (verified directly, back when the spring was still linear -- a plain
  cube at pressure=1 landed on a doubled-size, 99%-stretched "solution"
  in 5 solver evaluations; at pressure=3 on a subdivided cube it likewise
  imploded to near-zero volume without any face ever flipping, since a
  uniform implosion never disagrees with itself -- both are real zeros
  of the same equations, just not the one a physical process starting
  nearby would ever walk to). Explicit small steps can't teleport past
  the reachable equilibrium the way a linearized jump can. Step size was
  self-normalizing (a fraction of the mesh's own rest edge length,
  divided by the largest current force) so it adapted to whatever
  pressure/mesh scale was in play without a fixed constant; that adaptive
  term is currently removed, per explicit user request for testing (see
  STEP_MAX_MULTIPLIER's own comment) -- the step is presently just a flat
  fraction of rest edge length, with no force-dependent shrinking.
  Direction vectors use _safe_unit_vectors (a fixed fallback at an exact
  zero vector) instead of a naive division: without it, "every vertex
  exactly coincident" is a real zero of the force (every edge and face
  vanishes together) the relaxation could still land exactly on instead
  of the intended shape.

- **A hardening (linear + cubic) spring, not pure Hooke's-law linear --
  a genuine strain-stiffening term, added at the user's own explicit
  request.** A face's outward pressure force scales with its AREA
  (~ edge_length^2, i.e. quadratic in stretch), so a plain LINEAR
  spring's pull can't keep up past some critical pressure -- past it,
  there's no equilibrium at all, and the mesh inflates without bound
  (this is the same reason a real balloon's own idealized under-
  stiffened material models -- e.g. a bare neo-Hookean membrane -- show
  this exact "no equilibrium past a critical pressure" instability in
  the nonlinear-elasticity literature). A REAL rubber balloon doesn't
  blow up to an unbounded size the same way, because real rubber's
  stress-strain curve stiffens sharply once its polymer chains run out
  of slack at large stretch -- see the two-balloon experiment
  (https://en.wikipedia.org/wiki/Two-balloon_experiment) for the same
  underlying stiffening curve. A first version of this fix replaced the
  linear spring with a PURE quartic one (`stretch**3` alone): this
  worked -- pressure past the old critical value now settles at a large
  but finite stretch instead of diverging -- but a cubic force is much
  WEAKER than the linear one for a SMALL deviation (its own local
  stiffness is `3*stretch**2`, which vanishes at stretch=0), so a mesh
  near its rest length became far slower to settle: `dx/dt = -x**3` has
  a POWER-LAW solution (`x(t) ~ 1/sqrt(t)`) rather than a linear spring's
  EXPONENTIAL one, so each extra decimal of precision costs roughly an
  order of magnitude more steps, not a fixed multiple. The fix, per the
  user's own explicit request for a compromise: `stretch +
  HARDENING_CUBIC_COEFFICIENT * stretch**3` (see that constant's own
  comment for its current value and history) -- both terms are real,
  literal spring-force contributions (`force = -dU/dx` for a smooth
  potential, no clamp or bolted-on limit), so this is deliberately NOT
  the same thing as the per-edge soft stretch limit tried and removed
  earlier in this project's history (see .claude/skills/net-fold-
  project/SKILL.md's "No hacky terms" section) -- that was added
  specifically to paper over this exact instability without the user
  asking for it, where this is a real physical term the user did ask
  for. Near rest (stretch << 1) the linear term dominates (`stretch**3`
  is negligible), recovering the original spring's fast, near-
  exponential settling; past stretch ~= 1 the cubic term takes over and
  grows faster than pressure's own quadratic area growth, so an
  equilibrium still exists at any pressure, same as the pure-quartic
  version. Every pressure/step-size constant tuned against either the
  original linear spring or the intermediate pure-quartic one (see
  CONVERGENCE_GTOL, STEP_MAX_MULTIPLIER, _PRESSURE_AREA_PRODUCT_ESTIMATE,
  and estimate_pressure_for_target_stretch's own docstring) was
  re-verified/re-tuned directly against this combined force -- see each
  constant's own comment for what changed and why.

- **relax_initial_configuration (Level 0's own "Relax" step) uses a
  PLAIN LINEAR spring (_spring_only_force), not the hardening one
  above.** With `pressure=0`, there's no outward force for the hardening
  term to guard against in the first place -- the whole reason it exists
  is to stop a plain linear spring's pull from losing to pressure's own
  quadratic area growth, which simply doesn't apply here. A user
  reported Level 0 visibly failing to settle at a normal tolerance
  (1e-3) under the hardening spring, "jiggling" rather than converging;
  switching this ONE function back to plain linear resolved it directly
  (verified across cube/hippo/octahedron/dodecahedron/three_squares, all
  converging cleanly at gtol=1e-3). relax_once's own force
  (_relax_force), used for every level's actual pressure-driven
  inflation, keeps the hardening term unchanged.
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
    ValueError if any directed edge appears more than once -- the mesh
    need NOT be closed: an edge with no reverse partner at all is a
    valid, free boundary edge, not an error."""
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
    problems = [f"edge {v}->{w} appears {c} times (need exactly once)"
                for (v, w), c in counts.items() if c > 1]
    if problems:
        raise ValueError(f"{path}: not a consistently-oriented mesh:\n  " +
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
    _relax_force)."""
    groups = {}
    for face in faces:
        n = len(face)
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


# The cubic term's own coefficient in _relax_force's hardening spring
# (`stretch + HARDENING_CUBIC_COEFFICIENT * stretch**3`) -- was 1.0 (an
# unweighted sum), lowered per explicit user request for a stronger
# relative quadratic-energy (linear-force) component, i.e. more of the
# original linear spring's behavior and less of the quartic term's, while
# still keeping enough large-stretch stiffening to prevent the unbounded
# pressure blow-up a plain linear spring alone allows (see module
# docstring's Design notes). See STEP_MAX_MULTIPLIER's own comment for
# the re-verification this prompted.
HARDENING_CUBIC_COEFFICIENT = 0.5


def _relax_force(pts, edge_ai, edge_bi, all_face_groups, edge_length, pressure=0.0):
    """relax_once's per-step force: a genuine mechanical force balance.
    Each edge is a HARDENING spring (a `stretch +
    HARDENING_CUBIC_COEFFICIENT * stretch**3` restoring force -- see
    module docstring's Design notes for why, in place of either a plain
    linear or a plain quartic spring alone); each face applies a real
    outward pressure force, `pressure * area * outward_normal` -- area
    and normal computed together straight from its own vertex loop via
    `0.5 * sum_i cross(p_i, p_{i+1})` (Newell's method) -- split evenly
    across its own vertices. Returns the (N,3) net force on every vertex --
    relax_once walks a small step along it (see module docstring's
    Design notes for why edge directions need _safe_unit_vectors rather
    than a naive division)."""
    n = pts.shape[0]
    force = np.zeros((n, 3))

    diff = pts[edge_bi] - pts[edge_ai]
    dist = np.linalg.norm(diff, axis=1)
    direction = _safe_unit_vectors(diff)
    stretch = (dist - edge_length) / edge_length
    spring_on_a = (stretch + HARDENING_CUBIC_COEFFICIENT * stretch ** 3)[:, None] * direction
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


def _edge_setup(faces, edge_length):
    """faces: vertex-id loops (see module docstring for the winding
    convention); edge_length: scalar rest length, or a {(a,b): length}
    dict for a non-uniform (e.g. subdivided) mesh. Shared setup for
    relax_once/relax_initial_configuration: vertex/edge index arrays plus
    the precomputed structures _relax_force needs (built once here, not
    per call). Returns (vertex_ids, idx, edges, edge_ai, edge_bi,
    all_face_groups, length_arr, scale)."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    edges = mesh_edges(faces)
    edge_ai, edge_bi = _pair_index_arrays(edges, idx)
    all_face_groups = _face_index_groups(faces, idx)
    if isinstance(edge_length, dict):
        length_arr = np.array([edge_length[e] for e in edges])
        scale = float(np.min(length_arr)) if len(length_arr) else 1.0
    else:
        length_arr = edge_length
        scale = float(edge_length)
    return (vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups,
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
# interpret. (Currently compared against displacement, not force -- see
# _explicit_relax_loop's own docstring -- a temporary change for testing;
# this constant's own value/meaning as a per-step rate is unaffected.)
CONVERGENCE_GTOL = 1e-4

# How often _explicit_relax_loop actually checks the stopping condition
# above, in steps -- a TEMPORARY change per explicit user request, for
# testing: rather than comparing displacement against `gtol` every single
# step, check once every this-many steps instead, against `gtol` scaled
# up by the same factor (see _explicit_relax_loop's own comment). Raised
# 100 -> 200 per further explicit request. (This USED to also matter for
# inflate_polyhedron_app's own now-removed chunk schedule -- a user
# traced an app-reported "515 steps" convergence directly to this check
# only ever being reachable at a chunk's own boundary; that whole chunking
# scheme is gone now, in favor of relax_once/relax_initial_configuration
# calling this check's own `on_check` hook directly -- see
# inflate_polyhedron_app's own git history for the chunk-schedule details
# if useful context.)
CONVERGENCE_CHECK_INTERVAL = 200

# Explicit relaxation step size: the vertex with the largest net force
# moves this fraction of the mesh's own rest edge length in one
# iteration; every other vertex moves proportionally less (force is
# normalized by its own max each step). Keeps steps small and stable
# (a real physical walk, not a linearized jump that can overshoot the
# reachable equilibrium -- see module docstring's Design notes).
#
# Originally paired with an ADAPTIVE term (`STEP_MAX_FRACTION * scale /
# max_force`, shrinking the step when force is large, capped by this
# constant so it doesn't also grow unbounded as force shrinks near
# equilibrium) -- that adaptive term was temporarily removed per explicit
# user request, for testing (see _explicit_relax_loop's own comment), so
# this constant is currently the WHOLE step size, not just a cap on it.
# STEP_MAX_FRACTION itself (was 0.2, the same value as this constant) was
# removed as dead code once nothing referenced it any more.
#
# This value (as a fraction of edge length, properly scaled by `scale` --
# a FIXED, unscaled cap would represent a shrinking FRACTION of an edge
# length as the mesh subdivides finer but a GROWING one as it gets
# coarser, since `scale` itself is an absolute length) was found via
# direct verification, not derivation: run the same fixed-point relax on
# cube/tetrahedron/icosahedron at several pressures (1, 3, 5) and step
# multipliers, at Level 3 (194+ vertices, the finest/most failure-prone
# resolution this app reaches), watching for an undamped 2-cycle in
# max_stretch_pct (the same failure mode below). Stable through 0.3; a
# genuine 2-cycle reappears at 0.4+. 0.2 leaves a healthy margin.
#
# An EARLIER version of this constant (0.05, UNSCALED) was found the
# same way but without the `scale` factor: a level-3-subdivided cube at
# pressure=1 (194 vertices) was seen to settle into an exact, undamped
# 2-cycle under an unscaled 0.1 (max_stretch_pct alternating ~18.9%/
# ~24.4% forever), while unscaled 0.05 converged cleanly -- BUT that
# 0.05 was only ever actually "5% of an edge length" at Level 0/1, where
# `scale ≈ 1`; at Level 3 (`scale ≈ 0.18` for a cube), it was silently
# behaving as ~28% of an edge length (0.05 / 0.18), landing in the
# stable range purely by chance rather than by being correctly scaled --
# and remained needlessly small (hence needlessly slow to correct a
# small, stuck, locally-concave vertex trying to "pop out") at coarser
# levels where `scale` is closer to 1 and a much bigger relative step
# was actually safe. A user's report of exactly that (a slow-to-correct
# concave vertex, network otherwise looking right) is what prompted
# re-deriving this from scratch with the missing `scale` factor
# included, rather than just nudging the old unscaled constant.
#
# Re-tuned again (0.2 -> 0.05) after the spring force itself changed from
# Hooke's-law LINEAR to QUARTIC (stretch**3, see module docstring's
# Design notes -- added at the user's own request for genuine strain-
# stiffening) -- a user reported a mesh (hippo.json Level 1, calibrated
# for 80% target RMS stretch) that never converged, with the reported
# force hovering around 1.5 indefinitely. Traced directly (not assumed):
# one vertex was in an EXACT, undamped 2-cycle -- force alternating
# 1.97/1.00 forever, position displacement identical every step, never
# decaying -- the same failure mode 0.2 was originally tuned to avoid,
# now reappearing because a cubic force's local stiffness near a
# sharply-stretched edge is much higher than the linear spring's was,
# so the same step size that was safe before can overshoot past the new
# force law's equilibrium and land exactly on the opposite side, forever.
# Bisected directly on that reproducing case: stable from 0.12 down,
# still oscillating at 0.14+. Verified 0.05 stays stable across cube/
# octahedron/dodecahedron/three_squares/hippo at target RMS stretch
# 10/40/80% (a low-target, near-rest reading can still take many steps
# to reach gtol, but that's the expected slow POWER-LAW tail a cubic
# force has near equilibrium -- see estimate_pressure_for_target_
# stretch's own docstring -- not a repeat of this oscillation: its own
# force trace dips and slowly wanders rather than cleanly alternating
# between two fixed values forever).
#
# The spring force itself was changed again shortly after (pure QUARTIC
# -> a HARDENING `stretch + stretch**3`, see module docstring's Design
# notes) specifically to fix that slow power-law tail near rest, per the
# user's own request for a compromise between convergence speed and
# large-stretch stability. This value did NOT need to change again for
# that: re-verified directly on the exact same hippo.json reproducing
# case above -- 0.05 still converges cleanly (no oscillation) while 0.1+
# still shows the same large, non-decaying force (checked via a single
# 200-step chunk, matching inflate_polyhedron_app's own chunk size, to
# rule out the stall detector papering over a real 2-cycle) -- and a
# broader sweep (cube/hippo/octahedron/dodecahedron/three_squares at
# 10/40/80% target RMS stretch) now converges cleanly and lands within
# about a point of target everywhere, including the previously-stuck
# hippo/80% case.
#
# Re-checked again after HARDENING_CUBIC_COEFFICIENT was lowered
# (1.0 -> 0.5, see its own comment): a weaker cubic term could plausibly
# tolerate a bigger step before overshooting, so re-ran the same
# hippo.json boundary search rather than assuming 0.05 still applies
# unexamined. The boundary barely moved (stable through 0.12, oscillating
# at 0.13+ -- versus 0.12/0.14 at coefficient 1.0), so 0.05 was kept
# rather than raised for marginal extra speed at a smaller safety margin;
# re-verified the same 5-net/3-target sweep above still converges
# cleanly at this value.
STEP_MAX_MULTIPLIER = 0.05

# Hard cap on iterations when max_nfev=None (run-to-convergence): explicit
# steps have no scipy-style internal budget of their own, so this stands
# in for one.
MAX_UNBOUNDED_STEPS = 200_000

# The plateau/stall-window convergence shortcut (STALL_WINDOW/
# STALL_TOL_PCT: converge once max_stretch_pct's range over many steps
# stops moving, alongside the real gtol check) was REMOVED entirely per
# explicit user request: it's a fixed, gtol-INDEPENDENT threshold, so at
# a tighter gtol (e.g. 1e-5) than it was ever tuned against it declared
# "converged" early -- reported stopping around 4600 steps at every
# level, well before the mesh had actually reached the real, much
# tighter target. Once disabled (an intermediate step, kept only long
# enough to confirm this was the cause) it was removed outright rather
# than kept as unused dead code -- inflate_polyhedron_app's own
# INFLATE_SAFETY_STEP_CAP (a hard step-count cap per run) is judged
# sufficient on its own as the non-gtol way a run can end. See git
# history (STALL_WINDOW/STALL_TOL_PCT/STALL_DETECTION_ENABLED) for the
# original reasoning if a plateau-style shortcut is ever wanted again --
# it existed to keep a mesh with a tiny persistent wobble or a very long
# slow tail from running to the step cap for no visible benefit, and (a
# separate, later fix) to stop a locally concave vertex's own genuinely
# slow-but-real correction from being mistaken for a plateau.

# Escaping a genuine local-minimum "dimple" (see the removed STALL_WINDOW's own
# comment for how this was diagnosed): a pure explicit gradient-style
# walk has no momentum to coast through a shallow energy barrier with,
# so once a vertex settles into one, smaller OR larger steps both just
# oscillate around it forever rather than crossing over. `rng`
# (optional, `None` by default on every function here -- see their own
# docstrings) opts a caller into an occasional small random perturbation
# instead: if `max_force` hasn't dropped to at most KICK_STALL_RATIO of
# what it was KICK_WINDOW steps ago (still oscillating, not genuinely
# progressing toward `gtol`), every vertex gets nudged by Gaussian noise
# scaled by KICK_MAGNITUDE_FRACTION * `scale`, WEIGHTED by that vertex's
# own current force relative to the worst one -- concentrating the kick
# on whichever vertex/region is actually stuck, leaving an
# already-settled part of the mesh (low force, near-zero weight)
# essentially undisturbed. `rng=None` (the default) skips all of this at
# zero cost -- deliberately opt-in, not automatic, so every existing
# caller (including this module's own tests, which expect exact,
# reproducible results) keeps its current fully-deterministic behavior.
# inflate_polyhedron_app currently passes rng=None (disabled) for its own
# Relax/Inflate runs, per a later explicit user request -- see that
# app's own comment in _run_inflate_stream/_run_relax_stream.
#
# This value's own history predates two things that no longer apply as
# literally as originally written: `recent_max_force` still resets FRESH
# on every relax_once/relax_initial_configuration call, but the app's
# streamed Inflate/Relax no longer chunks that call into short pieces at
# all (see inflate_polyhedron_app's own git history) -- so a window this
# size is no longer at risk of never fitting inside a single call. The
# original verification (KICK_WINDOW=500 chunked at 200: zero kicks fired
# over 20,000 steps; 150: ~100 did) is kept here as the empirical basis
# for the value itself, not as a still-binding chunk-size constraint.
KICK_WINDOW = 150
KICK_STALL_RATIO = 0.5
KICK_MAGNITUDE_FRACTION = 0.3


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


def _remove_rigid_motion(pts_before, pts_after):
    """Re-expresses `pts_after` in the SAME rigid frame (rotation +
    translation) `pts_before` was in, via the standard Kabsch/orthogonal-
    Procrustes best-fit alignment -- removes whatever GLOBAL rigid
    rotation/translation this step's own force-driven update happened to
    introduce, leaving only the genuine shape change (every PAIRWISE
    distance within `pts_after` is preserved exactly, since a rigid
    transform is an isometry -- so this can never affect stretch stats,
    convergence, or anything else the physics actually cares about).

    A free-floating spring/pressure system (nothing pins any vertex to a
    fixed point) has no preferred orientation of its own -- rotating the
    WHOLE mesh about its own center of mass costs zero spring/pressure
    energy, so it's an exactly-flat direction the relaxation can drift
    along for free. Small numerical asymmetries (irregular topology,
    floating-point rounding) can accumulate into a slow but visible net
    spin over many steps with nothing to damp it, since nothing in
    _relax_force/_spring_only_force distinguishes "genuine shape change"
    from "the whole shape turning in place." A user watching
    inflate_polyhedron_app noticed exactly this -- a net visibly rotating
    mid-Inflate with no shape change to show for it -- and, worse, since
    each level's starting position is whatever the previous one was left
    at, a level frozen (Subdivide/promotion) at a DIFFERENT accumulated
    spin than another leaves the "Level N" panels' supposedly-SHARED
    camera (self.level_rotation) looking inconsistent between them even
    though that shared quaternion itself was never touched -- the MESH
    was moving, not the camera. Called every step (see
    _explicit_relax_loop) so each step's own small rotation is what gets
    cancelled, transitively pinning the whole run's trajectory back to
    wherever it started -- an O(N) matrix product plus one 3x3 SVD per
    call, negligible next to the force computation itself."""
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


def _explicit_relax_loop(pts, scale, force_fn,
                          max_nfev, stop_event, gtol, rng=None,
                          step_max_multiplier=None, on_check=None):
    """Shared explicit-relaxation driver for relax_once and
    relax_initial_configuration -- the only things that vary between
    them are the force itself (`force_fn(pts) -> (N,3)`) and, since each
    force law has its own safe step size (see STEP_MAX_MULTIPLIER's own
    comment), `step_max_multiplier` (defaults to the module's own
    STEP_MAX_MULTIPLIER, tuned for relax_once's hardening spring;
    relax_initial_configuration passes LEVEL0_STEP_MAX_MULTIPLIER
    instead, tuned for its own plain linear one) -- the walking logic
    (stopping criteria) itself is otherwise identical, so it lives here
    once rather than being kept in sync by hand in two places.

    Repeatedly nudges `pts` a small step along `force_fn(pts)` (see
    `step_max_multiplier`'s own comment); if `rng` is given and the
    worst vertex's force has been OSCILLATING rather than genuinely
    dropping (see KICK_WINDOW's own comment), nudges every vertex by a
    small random perturbation weighted toward whichever one is actually
    stuck; either way then removes whatever rigid rotation/translation
    the step (plus any kick) introduced (_remove_rigid_motion, see its
    own docstring for why a free-floating system needs this) -- until
    EITHER the worst vertex's own displacement over the last
    CONVERGENCE_CHECK_INTERVAL steps (checked only once every
    CONVERGENCE_CHECK_INTERVAL steps, not every step -- a TEMPORARY
    change, per explicit user request for testing, from comparing the
    worst vertex's net FORCE against `gtol` every step) drops below
    `CONVERGENCE_CHECK_INTERVAL * gtol`, or `max_nfev`/`stop_event` cuts
    it off first (a former THIRD criterion, a max_stretch_pct plateau/
    stall shortcut, was removed entirely per explicit user request -- see
    git history around STALL_WINDOW/STALL_TOL_PCT if it's ever wanted
    again). `on_check(pts, steps_taken, optimality, converged)`, if
    given, is called every time this periodic check runs (whether or not
    it ends the run) -- this is what lets a caller sync progress
    reporting (e.g. inflate_polyhedron_app redrawing its 3D panels) to
    the SAME cadence as the actual convergence check, in place of the
    app's own previous artificial chunk-size schedule (which had no
    relationship to this check's own period at all -- see
    CONVERGENCE_CHECK_INTERVAL's own comment). Returns (pts, steps_taken,
    optimality, converged) -- `optimality` is that same worst-vertex
    displacement from the last completed check, divided back down by
    CONVERGENCE_CHECK_INTERVAL so it's directly comparable to plain
    `gtol` (matching what it used to report every step), `None` if
    stopped before a single check completed. Callers each compute their
    own final positions/stretch stats from `pts`."""
    if step_max_multiplier is None:
        step_max_multiplier = STEP_MAX_MULTIPLIER
    step_cap = max_nfev if max_nfev is not None else MAX_UNBOUNDED_STEPS
    steps_taken = 0
    converged = False
    optimality = None
    pts_at_last_check = pts.copy()
    recent_max_force = collections.deque(maxlen=KICK_WINDOW) if rng is not None else None
    for steps_taken in range(1, step_cap + 1):
        if stop_event is not None and stop_event.is_set():
            steps_taken -= 1
            break
        force = force_fn(pts)
        per_vertex_force = np.linalg.norm(force, axis=1)
        max_force = float(per_vertex_force.max())
        # Adaptive term (STEP_MAX_FRACTION * scale / max_force, shrinking dt
        # when max_force is large) removed per explicit user request -- NOT
        # a temporary testing state: re-offered as a fix for calibration-
        # step divergence (2026-09-16) and explicitly declined again. Don't
        # reintroduce without new explicit permission naming this change
        # (see physics.md's "No hacky terms rule").
        dt = step_max_multiplier * scale
        new_pts = pts + dt * force
        if rng is not None:
            recent_max_force.append(max_force)
            if (len(recent_max_force) == KICK_WINDOW
                    and max_force > KICK_STALL_RATIO * recent_max_force[0]):
                weight = (per_vertex_force / max_force)[:, None]
                kick = rng.normal(scale=KICK_MAGNITUDE_FRACTION * scale, size=pts.shape)
                new_pts = new_pts + kick * weight
                recent_max_force.clear()  # give the kick a fresh window to show its effect
        pts = _remove_rigid_motion(pts, new_pts)
        # Stopping condition temporarily changed, per explicit user
        # request, for testing: rather than comparing displacement (or,
        # before that, force) against `gtol` EVERY step, only check once
        # every CONVERGENCE_CHECK_INTERVAL steps -- comparing the worst
        # vertex's own displacement ACCUMULATED over that whole interval
        # (not per-step) against CONVERGENCE_CHECK_INTERVAL * gtol, the
        # same effective per-step rate scaled up to the longer window.
        # Measured against pts_at_last_check (the position at the START
        # of this interval, itself already rigid-motion-removed each
        # step along the way), so a genuine multi-step drift is caught
        # even if no single step's own displacement would have tripped
        # the old every-step check.
        if steps_taken % CONVERGENCE_CHECK_INTERVAL == 0:
            block_displacement = float(np.linalg.norm(pts - pts_at_last_check, axis=1).max())
            optimality = block_displacement / CONVERGENCE_CHECK_INTERVAL
            pts_at_last_check = pts.copy()
            if block_displacement < CONVERGENCE_CHECK_INTERVAL * gtol:
                converged = True
            if on_check is not None:
                on_check(pts, steps_taken, optimality, converged)
            if converged:
                break
    return pts, steps_taken, optimality, converged


def relax_once(positions, faces, edge_length, pressure=0.0,
                max_nfev=None, stop_event=None,
                gtol=CONVERGENCE_GTOL, rng=None, on_progress=None):
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
    (capped at MAX_UNBOUNDED_STEPS as a runaway guard), via the worst
    vertex's own displacement in its last step dropping below `gtol` (a
    TEMPORARY change from comparing its net FORCE, per explicit user
    request for testing -- see _explicit_relax_loop's own docstring) --
    the former max_stretch_pct/STALL_WINDOW plateau shortcut has been
    removed entirely (see CONVERGENCE_GTOL's neighboring comment for why).
    `stop_event` (a
    threading.Event), if given, is checked before each step and aborts
    at the next one, returning whatever position was last reached. `rng`
    (a numpy Generator, e.g. `np.random.default_rng()`), if given, opts
    into an occasional random perturbation when a vertex is stuck
    oscillating rather than genuinely converging -- see KICK_WINDOW's
    own comment; `None` (the default) is fully deterministic, exactly
    this function's original behavior.

    `on_progress(new_positions, steps_taken, max_stretch_pct,
    rms_stretch_pct, optimality, converged)`, if given, is called every
    CONVERGENCE_CHECK_INTERVAL steps (the same cadence the stopping
    condition itself is checked at -- see _explicit_relax_loop's own
    `on_check`) with exactly this function's own return shape, so a
    caller can sync its own progress reporting (e.g.
    inflate_polyhedron_app redrawing its 3D panels) to real convergence-
    check points instead of an unrelated schedule of its own.

    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    optimality, converged). `optimality` is exactly the quantity compared
    against `gtol` above (the worst vertex's own last-step displacement),
    None if stopped before a single step ran. `converged` is True only if
    one of the two criteria above (not the step cap or a stop request) is
    what stopped it."""
    vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, length_arr, scale = \
        _edge_setup(faces, edge_length)
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)

    def force_fn(pts):
        return _relax_force(pts, edge_ai, edge_bi, all_face_groups, length_arr, pressure)

    def on_check(check_pts, check_steps, check_optimality, check_converged):
        check_positions, check_max_stretch, check_rms_stretch = _positions_and_stretch(
            check_pts, vertex_ids, edges, length_arr)
        on_progress(check_positions, check_steps, check_max_stretch, check_rms_stretch,
                    check_optimality, check_converged)

    pts, steps_taken, optimality, converged = _explicit_relax_loop(
        pts0, scale, force_fn, max_nfev, stop_event, gtol, rng,
        step_max_multiplier=STEP_MAX_MULTIPLIER,
        on_check=on_check if on_progress is not None else None)
    new_positions, max_stretch, rms_stretch = _positions_and_stretch(pts, vertex_ids, edges, length_arr)
    return new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged


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


# relax_initial_configuration's OWN step-size cap, separate from
# relax_once's STEP_MAX_MULTIPLIER -- since _spring_only_force is now a
# plain LINEAR spring (see its own docstring), not the hardening one
# STEP_MAX_MULTIPLIER=0.05 was re-tuned for, sharing that smaller value
# here just needlessly throttles a force law that never needed it in the
# first place. Restored to 0.2, the ORIGINAL value this project used for
# a plain linear spring before the hardening term existed at all (see
# STEP_MAX_MULTIPLIER's own history) -- verified stable in this project's
# own past tuning history for a linear spring specifically.
#
# This mattered more than it looks: a user reported Level 0 ("Relax")
# visibly failing to converge/settle at a normal tolerance (1e-3),
# "jiggling" rather than finishing, on data/input/stretchy_nets/
# hippo.json and dodecahedron.json specifically -- traced directly (not
# assumed) to inflate_polyhedron_app's own chunked calling pattern
# (_run_chunked_relax_stream, capped at INFLATE_CHUNK_MAX=200 steps per
# call): STALL_WINDOW (2000) can never fill within one chunk (a known,
# already-documented limitation), so convergence there can ONLY happen
# via the strict gtol check -- and inflate_polyhedron_app also opts every
# Relax/Inflate run into the KICK_WINDOW mechanism (`rng=np.random.
# default_rng()`), which perturbs the WHOLE mesh whenever the worst
# vertex's force hasn't dropped by half over the last 150 steps. At the
# smaller, hardening-spring-tuned step size, a perfectly healthy but
# slower-moving linear-spring relaxation can fail to clear that 50%-drop
# bar purely because of the smaller step, triggering a kick that
# re-disturbs the mesh right as it's genuinely converging -- a
# self-defeating loop that can run forever without ever satisfying gtol.
# Verified directly: reproducing inflate_polyhedron_app's own chunking on
# hippo.json/dodecahedron.json, the OLD shared 0.05 hit the 20,000-step
# safety cap without converging on both, while 0.1 and 0.2 converged
# cleanly (0.2 fastest, in 3,301 and 2,196 steps respectively) -- and a
# broader 5-net check (cube/hippo/octahedron/dodecahedron/three_squares)
# at gtol=1e-3 with the kick enabled converges cleanly for every one of
# them at this value.
LEVEL0_STEP_MAX_MULTIPLIER = 0.2


def _spring_only_force(pts, edge_ai, edge_bi, edge_length):
    """Pure Hooke's-law LINEAR spring force for relax_initial_configuration
    -- deliberately NOT the same hardening term _relax_force uses (see
    module docstring's Design notes): with pressure=0, there's no outward
    force for a hardening term to guard against in the first place, and a
    user reported Level 0 (relax_initial_configuration's own random-
    start-then-relax step) visibly failing to settle at a normal
    tolerance under the hardening spring -- switching back to plain
    linear here resolved it directly. Faces aren't expected to be flat or
    even non-self-intersecting at this stage (see
    relax_initial_configuration's docstring); the only goal is a
    well-separated, edge-length-plausible starting point to hand off to
    the real per-face pressure model afterward."""
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
                                 max_nfev=None, stop_event=None, gtol=CONVERGENCE_GTOL, rng=None,
                                 on_progress=None):
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
    on the worst vertex's own last-step displacement (a TEMPORARY change
    from its net force, per explicit user request for testing) -- the
    former STALL_WINDOW plateau shortcut has been removed entirely (see
    CONVERGENCE_GTOL's neighboring comment) -- OR `max_nfev`/`stop_event`.
    `rng`, as in relax_once, opts into an
    occasional random perturbation when stuck oscillating (`None` -- the
    default -- is fully deterministic).
    `on_progress`, as in relax_once, is called every CONVERGENCE_CHECK_
    INTERVAL steps with this function's own return shape (note: reflects
    the PRE-reflection embedding described below, since that fix-up only
    happens once, at the very end).
    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    optimality, converged) -- exactly relax_once's own return shape."""
    vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, length_arr, scale = \
        _edge_setup(faces, edge_length)
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)

    def force_fn(pts):
        return _spring_only_force(pts, edge_ai, edge_bi, length_arr)

    def on_check(check_pts, check_steps, check_optimality, check_converged):
        check_positions, check_max_stretch, check_rms_stretch = _positions_and_stretch(
            check_pts, vertex_ids, edges, length_arr)
        on_progress(check_positions, check_steps, check_max_stretch, check_rms_stretch,
                    check_optimality, check_converged)

    pts, steps_taken, optimality, converged = _explicit_relax_loop(
        pts0, scale, force_fn, max_nfev, stop_event, gtol, rng,
        step_max_multiplier=LEVEL0_STEP_MAX_MULTIPLIER,
        on_check=on_check if on_progress is not None else None)

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
    return new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged


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
#
# Re-checked, not re-derived, after the spring force changed to a
# hardening `stretch + HARDENING_CUBIC_COEFFICIENT * stretch**3` (see
# module docstring's Design notes): at this 10%-ish target the cubic
# term is negligible (stretch**3 ~= 0.001 vs stretch ~= 0.1) regardless
# of its own coefficient, so the combined spring behaves almost exactly
# like the plain linear one this constant was originally derived
# against. Re-running the same bisection at HARDENING_CUBIC_COEFFICIENT
# = 0.5 gave a mean of 25.0 (range 18.75-34.5) -- again indistinguishable
# from the original 25.0 within the same per-solid noise the original
# derivation already had -- so this value was kept rather than nudged.
_PRESSURE_AREA_PRODUCT_ESTIMATE = 25.0

# How far a single calibration step is allowed to rescale pressure --
# guards against a wild jump if one trial's stretch reading is degenerate
# (e.g. near zero), while still letting normal cases converge in a couple
# of iterations (stretch responds roughly linearly to pressure in the low-
# stretch regime this targets, verified against the bisection trace above).
_PRESSURE_RATIO_CLAMP = (0.2, 5.0)

# Was 8.0; raised to 10.0 per explicit user request.
DEFAULT_TARGET_RMS_STRETCH_PCT = 10.0



# A trial reading RMS stretch beyond this multiple of the target (and
# beyond this ABSOLUTE floor, so a tiny target -- 1%, say -- doesn't
# make an ordinary 20% stretch look "insane") is treated as the mesh
# having blown up rather than settled, in estimate_pressure_for_target_
# stretch's own bracket search -- not a usable data point for "how
# stretchy is this pressure", since a diverged run's own stretch number
# reflects numerical blow-up, not the mesh's real response to pressure.
_INSANE_STRETCH_FLOOR_PCT = 500.0
_INSANE_STRETCH_TARGET_MULTIPLE = 5.0

# Sentinel RMS/max stretch reading for a calibration trial whose integrator
# diverged into NaN/Inf positions before relax_once could even compute real
# stretch stats -- always >= _INSANE_STRETCH_FLOOR_PCT so it's treated
# exactly like any other insane/blown-up trial by the bracket search. Never
# surfaced to a user in practice (only used if EVERY trial in a calibration
# run diverged, same already-degenerate fallback path as an ordinary
# all-insane run). A generic safety net, kept even though calibration now
# uses the exact same step size a real Inflate run always has (see git
# history around PRESSURE_CALC_STEP_MULTIPLIER for the bigger-step
# experiments this was originally added for, removed 2026-09-16 per
# explicit user request -- "just 1x", no multiplier).
_DIVERGED_SENTINEL_STRETCH_PCT = 1e6


def estimate_pressure_for_target_stretch(positions, faces, edge_length,
                                          target_rms_pct=DEFAULT_TARGET_RMS_STRETCH_PCT,
                                          max_iterations=8,
                                          tol_pct=1.0, max_nfev_per_trial=5000, stop_event=None,
                                          gtol=CONVERGENCE_GTOL, rng=None,
                                          initial_pressure_guess=None):
    """positions/faces/edge_length: as relax_once. Finds a pressure whose
    relax_once result lands within `tol_pct` of `target_rms_pct` RMS
    stretch (RMS, not max -- an irregular/subdivided mesh stretches
    unevenly, and RMS is what the "Target RMS stretch" spinner asks for).
    Every trial runs at the exact same step size and step budget a real
    Inflate run would use (`max_nfev_per_trial`); a trial that still
    diverges numerically is caught and treated as an ordinary
    insane/blown-up trial rather than raising (see
    _DIVERGED_SENTINEL_STRETCH_PCT).
    `gtol` and `rng` are both forwarded to every trial's own relax_once
    call unchanged (defaults CONVERGENCE_GTOL/None, same as relax_once's
    own defaults) -- so a caller with its own convergence tolerance
    and/or stuck-vertex kick (e.g. inflate_polyhedron_app's "Tolerance"
    setting) calibrates pressure against the SAME settings it'll
    actually inflate with, rather than silently recalibrating against
    different ones. Every trial starts fresh from the given `positions`
    (not chained from the previous trial's result), since different
    pressures can have very different equilibria and this is searching
    for the pressure, not steering a shape.

    Starts from _PRESSURE_AREA_PRODUCT_ESTIMATE's geometric guess, unless
    `initial_pressure_guess` is given -- a caller with a BETTER starting
    point (e.g. inflate_polyhedron_app's `_guess_pressure_from_history`,
    extrapolating from a previous level's own already-calibrated pressure
    rather than this function's generic per-solid-derived constant) can
    skip straight past the generic guess's own inaccuracy, landing the
    bracket/rescale search closer on the FIRST trial and needing fewer of
    the `max_iterations` budget to converge. The search itself is now
    BRACKET-then-BISECT rather than a single multiplicative rescale
    repeated blindly: as long as
    every trial so far has landed on the SAME side of the target (all
    under it, or all "insane" -- see _INSANE_STRETCH_FLOOR_PCT/
    _INSANE_STRETCH_TARGET_MULTIPLE, a mesh that's blown up rather than
    settled), it keeps rescaling by (target / achieved), clamped by
    _PRESSURE_RATIO_CLAMP, exactly as the original single-rescale version
    did. The MOMENT a trial lands on the OPPOSITE side from the best one
    seen so far (a sane, under-target trial and an over-target-or-insane
    one now both exist), pressure is bracketed between them and every
    remaining trial simply bisects the bracket -- the only way to
    actually CONVERGE on an intermediate pressure once the mesh's own
    response to pressure turns out highly nonlinear near some critical
    value, rather than the old rescale-only approach's real failure
    mode: a large target whose naive rescale ratio overshoots straight
    past the mesh's own stable range and into catastrophic divergence,
    then rescales right back down from THAT diverged reading to
    approximately the ORIGINAL too-low pressure, forever alternating
    between the same two pressures without ever trying anything in
    between (verified directly: data/input/stretchy_nets/hippo.json at
    Level 1, target 60% RMS stretch, oscillated exactly this way under
    the old algorithm -- 0.165 giving 9.55%, rescaled up to 0.827 giving
    a diverged 70,185%, rescaled back down to 0.165, repeating
    indefinitely, never landing anywhere near 60%).

    Keeps whichever SANE trial got CLOSEST to the target rather than
    just the last one (an insane/diverged trial is never a candidate,
    however numerically close its own stretch number might coincidentally
    land, since that number doesn't reflect a real equilibrium): the
    rescale step (still used before a bracket exists) assumes more
    pressure means more stretch, which fails on at least one known net
    (data/input/stretchy_nets/three_squares.json actually stretches LESS
    as pressure rises -- a genuine property of that topology, not a bug
    here) -- without keeping the best-so-far, a net where that
    assumption is wrong would escalate pressure every iteration chasing
    a target it's moving away from; this is unchanged from the original
    algorithm, and this net's own existing test coverage still passes
    with the bracket/bisect logic added. Returns (pressure, new_positions,
    steps_taken, max_stretch_pct, rms_stretch_pct, optimality, converged)
    -- the last five exactly as relax_once's own return, from whichever
    trial this settled on (if every single trial was insane, the LAST
    one anyway, so this never raises for an irrecoverably bad target)."""
    if initial_pressure_guess is not None:
        pressure = initial_pressure_guess
    else:
        total_area = _total_rest_area(faces, edge_length)
        pressure = _PRESSURE_AREA_PRODUCT_ESTIMATE * (target_rms_pct / 100.0) / total_area
    insane_ceiling = max(_INSANE_STRETCH_FLOOR_PCT, target_rms_pct * _INSANE_STRETCH_TARGET_MULTIPLE)
    best_error, best_pressure, best_result = None, None, None
    # Once both are set, every remaining trial bisects between them:
    # lo_pressure is the LARGEST pressure so far confirmed sane and AT OR
    # UNDER target; hi_pressure is the SMALLEST pressure so far confirmed
    # either insane or over target.
    lo_pressure = hi_pressure = None
    result = None
    for _ in range(max_iterations):
        try:
            result = relax_once(positions, faces, edge_length, pressure,
                                 max_nfev=max_nfev_per_trial, stop_event=stop_event, gtol=gtol,
                                 rng=rng)
            _, _, _, rms_stretch, _, _ = result
        except np.linalg.LinAlgError:
            # A pathological trial (e.g. a pressure far outside any sane
            # range) can still blow the explicit integrator up into
            # NaN/Inf positions -- _remove_rigid_motion's Kabsch SVD then
            # can't converge on garbage input. Not worth crashing
            # calibration over: treated exactly
            # like an ordinary insane/blown-up trial instead (see
            # _DIVERGED_SENTINEL_STRETCH_PCT).
            result = (positions, 0, _DIVERGED_SENTINEL_STRETCH_PCT,
                      _DIVERGED_SENTINEL_STRETCH_PCT, None, False)
            rms_stretch = _DIVERGED_SENTINEL_STRETCH_PCT
        sane = rms_stretch < insane_ceiling
        if sane:
            error = abs(rms_stretch - target_rms_pct)
            if best_error is None or error < best_error:
                best_error, best_pressure, best_result = error, pressure, result
        stopped = stop_event is not None and stop_event.is_set()
        if stopped or (sane and error < tol_pct):
            break
        if sane and rms_stretch <= target_rms_pct:
            lo_pressure = pressure
        else:
            hi_pressure = pressure
        if lo_pressure is not None and hi_pressure is not None:
            pressure = (lo_pressure + hi_pressure) / 2
        elif hi_pressure is not None:
            # No sane/under-target trial yet to bracket against -- the
            # very first guess was already too high; keep halving until
            # one shows up (then the branch above takes over).
            pressure = hi_pressure / 2
        elif rms_stretch > 0:
            ratio = target_rms_pct / rms_stretch
            ratio = min(max(ratio, _PRESSURE_RATIO_CLAMP[0]), _PRESSURE_RATIO_CLAMP[1])
            pressure *= ratio
        else:
            break  # degenerate reading (zero stretch) with nothing to bracket against yet
    if best_result is None:
        # Every trial was insane -- no sane candidate exists at all
        # within max_iterations; report the last attempt anyway rather
        # than raising, same as the original algorithm's own contract
        # (always returns SOMETHING derived from an actual relax_once
        # call).
        best_pressure, best_result = pressure, result
    new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged = best_result
    return best_pressure, new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged
