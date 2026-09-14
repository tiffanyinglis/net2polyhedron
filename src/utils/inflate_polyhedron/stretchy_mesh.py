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
      ],
      "edge_folds": [[0, 1, 4, 3]]
    }

An optional top-level "edge_folds" list (interactive_builder_app's "Edge
Fold" tool) names pairs of edges of ONE face folded onto each other --
`[v1, v2, v3, v4]` means edge `v1-v2` is folded onto edge `v3-v4`,
coupling `v1` with `v3` and `v2` with `v4` as the same physical point
(see interactive_builder_app's own docstring for the mod-`n` reflection
rule that picks `v3, v4`'s order). Unlike an ordinary shared vertex,
this does NOT merge `v1`/`v3` or `v2`/`v4` into one id -- see "Edge
folds are a real spring, not a vertex merge" below for why -- so a
reader that ignores this key sees an ordinary, un-folded net; every id
in "faces" stays exactly as authored. `load_stretchy_mesh` returns the
coupling as `fold_pairs`: `[(v1, v3), (v2, v4), ...]`. [] (or the key
absent) for a net with none.

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

- **Edge folds are a real spring, not a vertex merge.** An EARLIER
  version of this feature merged a fold's two corner pairs into one
  shared id (a plain union-find remap on `faces`, applied once at load
  time) -- appealingly simple, since a folded pair then needed no
  special-casing anywhere else, exactly like any other ordinarily-shared
  vertex. It broke on a SELF-fold (one face's own edge glued to another
  edge of the SAME face, e.g. pinched_hex.json: a hexagon folded onto
  its own opposite edge): merging id-wise doesn't just identify the
  fold's own two declared corner pairs, it can ALSO silently collide an
  UN-declared pair right next to them (pinched_hex.json's corners 2 and
  5, each touched by two DIFFERENT original edges that only coincide
  because their OTHER endpoints got merged) -- and since every boundary/
  interior check in this module is vertex-id based (mesh_edges, rest
  lengths, subdivision's own edge dedup), that incidental collision gets
  silently treated as a second, unwanted SEAL, closing off an edge the
  fold never actually declared shared. The visible result: a self-folded
  net that should open into a hollow, tube-like pocket (only the ONE
  declared edge sealed, everything else free) instead came out as a
  fully sealed, closed pillow with no opening at all.

  So a fold now keeps `v1`/`v2`/`v3`/`v4` fully distinct in `faces` --
  every face fan-subdivides exactly like an ordinary one, no special-
  casing -- and instead pulls `v1` to `v3` and `v2` to `v4` with a real,
  very stiff (`FOLD_COUPLING_STIFFNESS`), zero-rest-length spring during
  relaxation (`fold_pairs`, both in relax_once and
  relax_initial_configuration). This is exactly the design an even
  EARLIER version of this feature tried and reverted, over concern that
  a spring that stiff would break the explicit integrator's own step-
  size assumptions and oscillate -- re-tried at the user's own explicit
  request, and that concern turned out to be exactly right: fed through
  the SAME shared force/step machinery as every other spring (whose own
  step size assumes unit stiffness), the coupling pair's gap oscillated
  indefinitely rather than closing, and even a first attempt at damping
  it (repeatedly yanking the pair a fixed fraction of their own gap
  closed, each step, on top of that unstable force) kept re-injecting
  enough uncontrolled motion into the pair's immediate neighbourhood to
  drive a persistent, low-frequency bending oscillation through an
  inflated tube net -- like flexing a piece of macaroni, never settling.

  The actual fix (_advance_fold_coupling) is to stop treating this as
  part of the shared force/step system at all: a zero-rest-length linear
  spring's overdamped relaxation (this module's own model everywhere
  else -- no velocity/inertia term, a step here IS the position update)
  has an EXACT closed-form solution, `gap(t) = gap(0) * exp(-k*t)`, and
  advancing by that formula -- rather than an Euler-style `gap - k*gap*dt`
  approximation, unstable once `k*dt` is this large -- is unconditionally
  stable for any stiffness or step size: |gap| only ever shrinks,
  smoothly, never overshooting or reversing sign, using the SAME `dt`
  the step already computed for everything else, no separate damping
  constant of its own needed. Converges within a handful of steps
  (k=100, dt~0.2 gives decay~2e-9), so it stops perturbing its
  neighbourhood almost immediately rather than every step for as long as
  the mesh keeps relaxing -- verified directly on pinched_hex.json (see
  test_stretchy_mesh.py).

  mesh_levels.subdivide_once has to track this too: a folded edge's own
  two coupled corners multiply into more coupled pairs every time that
  edge gets a new midpoint under subdivision (see its own
  `fold_chains`/_grow_fold_chains), so the WHOLE folded edge stays
  pulled shut at every level, not just its original two corners.
"""
import collections
import json

import numpy as np

from ..geometry.polyhedron import Polyhedron

EDGE_LENGTH = 1.0

# An edge fold's coupling spring (module docstring's "Edge folds are a
# real spring, not a vertex merge"): zero rest length, pulling a folded
# pair together this many times as fast (per unit of remaining gap, in
# EDGE_LENGTH units) as an ordinary edge spring relaxes a unit stretch --
# see _advance_fold_coupling for how this rate is actually integrated
# (exactly, not through the shared explicit force step -- a term this
# stiff breaks that step's own stability margin outright).
FOLD_COUPLING_STIFFNESS = 100.0


def _face_edges(face):
    """The directed edges (v, w) of one CCW face loop."""
    k = len(face)
    return [(face[i], face[(i + 1) % k]) for i in range(k)]


def _check_winding(faces, path, when):
    """Raises ValueError naming every directed edge that appears more
    than once, or is a self-loop (v == w -- degenerate, only possible
    from a bad edge fold). Shared by load_stretchy_mesh's two winding
    checks, run before folding (malformed file) and after (a fold that
    collapses an edge or creates a duplicate directed pair). `when` names
    which half of the process produced a given failure."""
    directed = [e for face in faces for e in _face_edges(face)]
    counts = {}
    for e in directed:
        counts[e] = counts.get(e, 0) + 1
    problems = [f"edge {v}->{w} is a self-loop (a fold collapsed it to a point)"
                for (v, w), c in counts.items() if v == w]
    problems += [f"edge {v}->{w} appears {c} times (need exactly once)"
                 for (v, w), c in counts.items() if v != w and c > 1]
    if problems:
        raise ValueError(f"{path}: not a consistently-oriented mesh {when}:\n  " +
                          "\n  ".join(problems))


def _fold_coupling_chains(faces, edge_folds, path):
    """faces: vertex-id loops, already confirmed consistently-wound;
    edge_folds: [(v1, v2, v3, v4), ...] from the file's own "edge_folds"
    list. Does NOT merge any ids (see module docstring's "Edge folds are
    a real spring, not a vertex merge" note for why) -- just validates
    every named vertex is real and packages each fold as its own
    level-0 coupling chain, `([v1, v2], [v3, v4])`: chain_a[i] must
    coincide with chain_b[i] (relax_once/relax_initial_configuration's
    `fold_pairs`, via fold_pairs_from_chains), and mesh_levels.
    subdivide_once grows each chain as the folded edge subdivides.
    Raises ValueError if a fold references a vertex id no face uses.
    Returns a list of chain pairs, [] for a net with no folds."""
    vertex_ids = {v for face in faces for v in face}
    chains = []
    for v1, v2, v3, v4 in edge_folds:
        for v in (v1, v2, v3, v4):
            if v not in vertex_ids:
                raise ValueError(f"{path}: edge fold {[v1, v2, v3, v4]} references "
                                  f"a vertex no face uses: {v}")
        chains.append(([v1, v2], [v3, v4]))
    return chains


def fold_pairs_from_chains(fold_chains):
    """fold_chains: [(chain_a, chain_b), ...] as returned by
    _fold_coupling_chains/mesh_levels.subdivide_once -- same-length
    vertex-id lists, chain_a[i] paired with chain_b[i]. Flattens to the
    (a, b) vertex-id pairs relax_once/relax_initial_configuration's
    `fold_pairs` argument expects; [] for a net with no folds."""
    return [(a, b) for chain_a, chain_b in fold_chains for a, b in zip(chain_a, chain_b)]


def load_stretchy_mesh(path):
    """path: a vertex-loop stretchy-mesh .json (see module docstring).
    Returns (faces, name, fold_chains): faces a list of vertex-id lists
    exactly as authored (an "edge_folds" entry never merges ids -- see
    module docstring's "Edge folds are a real spring, not a vertex
    merge" note); fold_chains, _fold_coupling_chains' result ([] for a
    net with none), the level-0 seed for mesh_levels.subdivide_once's
    own fold-chain growth and for fold_pairs_from_chains. Raises
    ValueError if any directed edge appears more than once (a genuinely
    malformed file) -- the mesh need NOT be closed: an edge with no
    reverse partner at all is a valid, free boundary edge, not an
    error."""
    with open(path) as f:
        spec = json.load(f)

    faces = spec.get("faces") or []
    if not faces:
        raise ValueError(f"{path}: no faces declared")
    for face in faces:
        if len(face) < 3:
            raise ValueError(f"{path}: a face needs at least 3 vertices, got {face}")

    _check_winding(faces, path, "before folding")
    fold_chains = _fold_coupling_chains(faces, spec.get("edge_folds") or [], path)

    name = spec.get("name") or path
    return faces, name, fold_chains


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
    direction). An edge fold's own coupled corners are handled entirely
    separately (_advance_fold_coupling, called from _explicit_relax_loop)
    -- NOT part of this force, see that function's own docstring for why.
    Returns the (N,3) net force on every vertex -- relax_once walks a
    small step along it (see module docstring's Design notes for why edge
    directions need _safe_unit_vectors rather than a naive division)."""
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


def _edge_setup(faces, edge_length, fold_pairs=()):
    """faces: vertex-id loops (see module docstring for the winding
    convention); edge_length: scalar rest length, or a {(a,b): length}
    dict for a non-uniform (e.g. subdivided) mesh; fold_pairs: [(a, b),
    ...] vertex-id pairs an edge fold couples together (module
    docstring's "Edge folds are a real spring, not a vertex merge" --
    typically stretchy_mesh.fold_pairs_from_chains' result). Shared setup
    for relax_once/relax_initial_configuration: vertex/edge index arrays
    plus the precomputed structures _relax_force/_spring_only_force need
    (built once here, not per call). Coupling pairs are kept OUT of
    `edges`/`length_arr` -- rest-length-based stretch stats would be
    meaningless at rest length 0 -- and returned as their own index
    arrays instead. Returns (vertex_ids, idx, edges, edge_ai, edge_bi,
    all_face_groups, planarity_groups, length_arr, scale, coupling_ai,
    coupling_bi)."""
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
    coupling_ai, coupling_bi = _pair_index_arrays(list(fold_pairs), idx)
    return (vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, planarity_groups,
            length_arr, scale, coupling_ai, coupling_bi)


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
# from an undamped-oscillator's back-and-forth. Multiplied by `scale`
# (see _explicit_relax_loop) -- a FIXED, unscaled cap here would represent
# a shrinking FRACTION of an edge length as the mesh subdivides finer
# (rest lengths shrink -- see mesh_levels.subdivide_once) but a GROWING
# one as it gets coarser, since `scale` is an ABSOLUTE length and this
# cap is what limits an ABSOLUTE per-step displacement; multiplying by
# `scale` keeps it a constant FRACTION of an edge length at every
# resolution, matching STEP_MAX_FRACTION's own already-scaled term.
#
# This value (as a fraction of edge length, now that it's properly
# scaled) was found via direct verification, not derivation: run the
# same fixed-point relax on cube/tetrahedron/icosahedron at several
# pressures (1, 3, 5) and step multipliers, at Level 3 (194+ vertices,
# the finest/most failure-prone resolution this app reaches), watching
# for an undamped 2-cycle in max_stretch_pct (the same failure mode
# below). Stable through 0.3; a genuine 2-cycle reappears at 0.4+. 0.2
# leaves a healthy margin and matches STEP_MAX_FRACTION's own value.
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
STEP_MAX_MULTIPLIER = 0.2

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
#
# Raised from 200 to 2000 after a user reported a single, locally
# concave vertex sometimes getting stuck failing to "pop out" -- a real
# but SLOW correction (max_stretch_pct barely moving over any given
# couple hundred steps, even though the shape genuinely keeps improving
# over a much longer span) could plateau-trigger this criterion well
# before the vertex actually finishes correcting, mistaking "changing
# very slowly" for "done changing" (STALL_TOL_PCT itself wasn't the
# issue -- 200 steps just wasn't a long enough window to tell the two
# apart). 2000 also comfortably exceeds inflate_polyhedron_app's own
# INFLATE_CHUNK_MAX (200, the largest single relax_once call its
# streamed Inflate/Relax ever makes) -- since this deque resets FRESH on
# every relax_once/relax_initial_configuration call (no state carried
# between chunks), no in-app chunk could ever have filled even the OLD
# 200-length window on its own either; a real stall verdict from the app
# only ever happened at the exact moment a chunk grew to 200 AND that
# whole chunk was flat, so raising this mostly just means the app now
# leans on the real gtol/INFLATE_SAFETY_STEP_CAP criteria instead of a
# same-size coincidence, letting a genuinely slow correction (like the
# reported stuck vertex) keep going rather than being cut off early.
#
# This alone turned out NOT to fix that reported stuck vertex, though --
# investigated further (see KICK_WINDOW below): its own force wasn't
# slowly shrinking at all, it was OSCILLATING indefinitely in a fixed
# band (~0.04-0.07 over 30,000 steps, on data/input/stretchy_nets/
# hippo_head.json), the signature of a genuine local-minimum "dimple"
# rather than a merely-slow correction. Directly verified a bigger step
# size does NOT help this case -- it gets WORSE (more overshoot, still
# no escape) -- and that higher pressure just diverges outright past a
# critical value (see module docstring's own "No runaway guard on
# pressure" note); neither is a matter of degree here, this needed an
# actual different mechanism (KICK_WINDOW below).
STALL_WINDOW = 2000
STALL_TOL_PCT = 1.0

# Escaping a genuine local-minimum "dimple" (see STALL_WINDOW's own
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
# reproducible results) keeps its current fully-deterministic behavior;
# inflate_polyhedron_app opts in for its own Relax/Inflate runs.
#
# UNLIKE STALL_WINDOW, this must stay <= inflate_polyhedron_app's own
# INFLATE_CHUNK_MAX (200): `recent_max_force` resets FRESH on every
# relax_once/relax_initial_configuration call, and the app's own
# streamed Inflate/Relax (_run_chunked_relax_stream) never makes one
# call longer than INFLATE_CHUNK_MAX steps -- a window bigger than that
# could NEVER fill within a single chunk, so it would silently never
# fire through the app's actual UI at all (verified directly: with
# KICK_WINDOW=500 chunked at 200, zero kicks fired over 20,000 steps;
# with 150, ~100 did). 150 leaves comfortable room under 200.
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


def _advance_fold_coupling(pts, coupling_ai, coupling_bi, dt):
    """Advances a fold's coupling pairs (module docstring's "Edge folds
    are a real spring, not a vertex merge") over one step of size `dt`,
    kept entirely SEPARATE from the ordinary force/step machinery (not
    part of `force_fn`'s return, no interaction with `max_force`/dt
    sizing) -- deliberately, not for simplicity's sake: a term this stiff
    (FOLD_COUPLING_STIFFNESS, ~100x an ordinary spring's own) genuinely
    cannot share the rest of the mesh's step size. Fed through the SAME
    explicit force-then-step scheme as everything else, it either
    oscillates outright (verified directly: a folded pair's gap bouncing
    5-30% of an edge length, never closing) or, damped by brute
    workarounds, kept re-injecting a large, physically ungrounded
    correction into the couple's IMMEDIATE mesh neighbourhood every
    single step -- exactly what was found driving a real, unwanted, long-
    lived low-frequency bending oscillation through an inflated tube net
    (pinched_hex.json's own use case), like flexing a piece of macaroni,
    that never settled.

    The actual fix: for a LINEAR spring (force strictly proportional to
    displacement, zero rest length -- exactly what this is), the
    overdamped relaxation this whole module already assumes everywhere
    else (a step here IS the position update, no separate velocity/
    inertia term -- see module docstring's Design notes) has a closed-
    form EXACT solution: `gap(t) = gap(0) * exp(-k*t)`. Advancing by that
    formula, rather than forward-Euler-style `gap - k*gap*dt` (unstable
    for `k*dt` this large), is unconditionally stable for ANY stiffness
    or step size -- |gap| only ever shrinks, smoothly, never overshoots
    or reverses sign -- and needs no extra magic-number damping constant
    of its own: the SAME `dt` the rest of the step already computed
    (from the ordinary, non-coupling force) is all this needs. Since it
    converges within a handful of steps regardless (k=100 means even a
    generous dt=0.2 gives decay=exp(-20)~2e-9), it stops perturbing its
    neighbourhood almost immediately, rather than every step for as long
    as the mesh keeps relaxing. Mutates and returns `pts`; a no-op with
    no coupling pairs."""
    if coupling_ai is None or len(coupling_ai) == 0:
        return pts
    gap = pts[coupling_bi] - pts[coupling_ai]
    correction = 0.5 * (1.0 - np.exp(-FOLD_COUPLING_STIFFNESS * dt)) * gap
    pts[coupling_ai] = pts[coupling_ai] + correction
    pts[coupling_bi] = pts[coupling_bi] - correction
    return pts


def _explicit_relax_loop(pts, edge_ai, edge_bi, length_arr, scale, force_fn,
                          max_nfev, stop_event, gtol, rng=None,
                          coupling_ai=None, coupling_bi=None):
    """Shared explicit-relaxation driver for relax_once and
    relax_initial_configuration -- the only thing that varies between
    them is the force itself (`force_fn(pts) -> (N,3)`); the walking
    logic (step size, stopping criteria) is identical, so it lives here
    once rather than being kept in sync by hand in two places.

    Repeatedly nudges `pts` a small step along `force_fn(pts)` (see
    STEP_MAX_FRACTION/STEP_MAX_MULTIPLIER); if `rng` is given and the
    worst vertex's force has been OSCILLATING rather than genuinely
    dropping (see KICK_WINDOW's own comment), nudges every vertex by a
    small random perturbation weighted toward whichever one is actually
    stuck; an edge fold's own coupling pairs (coupling_ai/coupling_bi)
    then advance over the SAME step's `dt`, but via their own exact,
    unconditionally-stable update (_advance_fold_coupling -- see its own
    docstring for why this is kept OUT of force_fn entirely rather than
    folded into the shared force/step); either way then removes whatever
    rigid rotation/translation the step (plus any kick/coupling advance)
    introduced (_remove_rigid_motion, see its own docstring for why a
    free-floating system needs this) -- until EITHER every vertex's
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
    recent_max_force = collections.deque(maxlen=KICK_WINDOW) if rng is not None else None
    for steps_taken in range(1, step_cap + 1):
        if stop_event is not None and stop_event.is_set():
            steps_taken -= 1
            break
        force = force_fn(pts)
        per_vertex_force = np.linalg.norm(force, axis=1)
        max_force = float(per_vertex_force.max())
        if max_force < gtol:
            converged = True
            break
        dist = np.linalg.norm(pts[edge_bi] - pts[edge_ai], axis=1)
        recent_max_stretch.append(float(np.max(np.abs(100 * (dist - length_arr) / length_arr))))
        if (len(recent_max_stretch) == STALL_WINDOW
                and max(recent_max_stretch) - min(recent_max_stretch) < STALL_TOL_PCT):
            converged = True
            break
        dt = min(STEP_MAX_MULTIPLIER * scale, STEP_MAX_FRACTION * scale / max_force)
        new_pts = pts + dt * force
        if rng is not None:
            recent_max_force.append(max_force)
            if (len(recent_max_force) == KICK_WINDOW
                    and max_force > KICK_STALL_RATIO * recent_max_force[0]):
                weight = (per_vertex_force / max_force)[:, None]
                kick = rng.normal(scale=KICK_MAGNITUDE_FRACTION * scale, size=pts.shape)
                new_pts = new_pts + kick * weight
                recent_max_force.clear()  # give the kick a fresh window to show its effect
        new_pts = _advance_fold_coupling(new_pts, coupling_ai, coupling_bi, dt)
        pts = _remove_rigid_motion(pts, new_pts)
    return pts, steps_taken, max_force, converged


def relax_once(positions, faces, edge_length, pressure=0.0,
                planarity_weight=PLANARITY_WEIGHT, max_nfev=None, stop_event=None,
                gtol=CONVERGENCE_GTOL, rng=None, fold_pairs=()):
    """positions: {vertex_id: [x,y,z]} starting point; faces/edge_length:
    as _edge_setup. Runs ONE relaxation pass at a fixed `pressure` -- no
    automatic ramp; call again with the result to keep steering it. Each
    iteration moves
    every vertex a small step along its own net force from _relax_force
    (see module docstring's Design notes for why this walks explicitly
    rather than handing the force balance to a Newton-style solver) --
    `pressure` is a real per-face outward force, with no volume or
    remembered state anywhere in it. `fold_pairs`: [(a, b), ...] an edge
    fold's own coupled corners (module docstring's "Edge folds are a
    real spring, not a vertex merge" -- typically
    stretchy_mesh.fold_pairs_from_chains' result), pulled together with
    their own much stiffer zero-rest-length spring; () for a net with no
    folds.

    `max_nfev` caps the number of steps; None runs until convergence
    (capped at MAX_UNBOUNDED_STEPS as a runaway guard), via EITHER of two
    criteria: every vertex's force drops below `gtol`, or max_stretch_pct
    stops moving for STALL_WINDOW steps (see STALL_WINDOW's comment for
    why both exist). `stop_event` (a threading.Event), if given, is
    checked before each step and aborts at the next one, returning
    whatever position was last reached. `rng` (a numpy Generator, e.g.
    `np.random.default_rng()`), if given, opts into an occasional random
    perturbation when a vertex is stuck oscillating rather than
    genuinely converging -- see KICK_WINDOW's own comment; `None`
    (the default) is fully deterministic, exactly this function's
    original behavior.

    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    max_force, converged). `max_force` is the worst vertex's net force at
    the returned position (compare against `gtol`), None if stopped
    before a single step ran. `converged` is True only if one of the two
    criteria above (not the step cap or a stop request) is what stopped
    it."""
    (vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, planarity_groups, length_arr,
     scale, coupling_ai, coupling_bi) = _edge_setup(faces, edge_length, fold_pairs)
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)

    def force_fn(pts):
        return _relax_force(pts, edge_ai, edge_bi, all_face_groups, planarity_groups,
                             length_arr, pressure, planarity_weight)

    pts, steps_taken, max_force, converged = _explicit_relax_loop(
        pts0, edge_ai, edge_bi, length_arr, scale, force_fn, max_nfev, stop_event, gtol, rng,
        coupling_ai, coupling_bi)
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
    planarity. An edge fold's own coupled corners are handled entirely
    separately (_advance_fold_coupling), same as _relax_force. Faces
    aren't expected to be flat or even non-self-intersecting at this
    stage (see relax_initial_configuration's docstring); the only goal is
    a well-separated, edge-length-plausible starting point to hand off to
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
                                 fold_pairs=()):
    """positions/faces/edge_length: as relax_once, but `positions` is
    typically random_initial_positions' output here, not a meaningful
    embedding -- this is what turns it into one, WITHOUT ever touching
    pressure: pure Hooke's-law springs only (_spring_only_force), plus an
    edge fold's own coupling springs (`fold_pairs`, as relax_once).
    Nothing here constrains vertices that don't share an edge, or fixes
    overall position/scale, so the result can end up anywhere in space,
    at any scale, and self-intersecting -- fine, since the only goal is a
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
    STALL_WINDOW steps, OR `max_nfev`/`stop_event`. `rng`, as in
    relax_once, opts into an occasional random perturbation when stuck
    oscillating (`None` -- the default -- is fully deterministic).
    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    max_force, converged) -- exactly relax_once's own return shape."""
    (vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, planarity_groups, length_arr,
     scale, coupling_ai, coupling_bi) = _edge_setup(faces, edge_length, fold_pairs)
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)

    def force_fn(pts):
        return _spring_only_force(pts, edge_ai, edge_bi, length_arr)

    pts, steps_taken, max_force, converged = _explicit_relax_loop(
        pts0, edge_ai, edge_bi, length_arr, scale, force_fn, max_nfev, stop_event, gtol, rng,
        coupling_ai, coupling_bi)

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

def estimate_pressure_for_target_stretch(positions, faces, edge_length,
                                          target_rms_pct=DEFAULT_TARGET_RMS_STRETCH_PCT,
                                          planarity_weight=PLANARITY_WEIGHT, max_iterations=8,
                                          tol_pct=1.0, max_nfev_per_trial=20000, stop_event=None,
                                          gtol=CONVERGENCE_GTOL, rng=None, fold_pairs=()):
    """positions/faces/edge_length/fold_pairs: as relax_once. Finds a pressure whose
    relax_once result lands within `tol_pct` of `target_rms_pct` RMS
    stretch (RMS, not max -- an irregular/subdivided mesh stretches
    unevenly, and RMS is what the "Target RMS stretch" spinner asks for).
    `gtol` and `rng` are both forwarded to every trial's own relax_once
    call unchanged (defaults CONVERGENCE_GTOL/None, same as relax_once's
    own defaults) -- so a caller with its own convergence tolerance
    and/or stuck-vertex kick (e.g. inflate_polyhedron_app's "Tolerance"
    setting) calibrates pressure against the SAME settings it'll
    actually inflate with, rather than silently recalibrating against
    different ones. Every trial starts fresh from the given `positions`
    (not chained from the previous trial's result -- a chained version,
    and a version with a much smaller `max_nfev_per_trial` to keep that
    fast, were both tried and reverted, see git history: chaining sped up
    the common case, but its own chained trials could read a pressure as
    "insane" purely because the SPECIFIC shape they happened to be
    chained from couldn't relax to that pressure's equilibrium in one
    trial's own budget, not because the pressure itself was unsustainable
    -- a hysteresis artifact, verified directly on data/input/
    stretchy_nets/hippo.json, that corrupted the whole search; a smaller
    per-trial step budget on its own then overinflated on the SAME net,
    a user reported directly, rather than settling near the requested
    target). Different pressures can have very different equilibria and
    this is searching for the pressure, not steering a shape -- back to
    this function's very first design, restarting fresh and giving every
    trial the full `max_nfev_per_trial=20000` budget to reach a genuine
    equilibrium reading, at the cost of being slow on a mesh that's slow
    to converge (verified directly: 44 seconds on hippo.json at Level 1)
    until a faster approach is found that doesn't reintroduce either of
    those two regressions.

    Starts from _PRESSURE_AREA_PRODUCT_ESTIMATE's geometric guess, then
    BRACKET-then-BISECTS: as long as every trial so far has landed on the
    SAME side of the target (all under it, or all "insane" -- see
    _INSANE_STRETCH_FLOOR_PCT/_INSANE_STRETCH_TARGET_MULTIPLE, a mesh
    that's blown up rather than settled), it keeps rescaling by (target /
    achieved), clamped by _PRESSURE_RATIO_CLAMP. The MOMENT a trial lands
    on the OPPOSITE side from the best one seen so far (a sane, under-
    target trial and an over-target-or-insane one now both exist),
    pressure is bracketed between them and every remaining trial simply
    bisects the bracket -- the only way to actually CONVERGE on an
    intermediate pressure once the mesh's own response to pressure turns
    out highly nonlinear near some critical value, rather than a naive
    rescale-only approach's real failure mode: a large target whose ratio
    overshoots straight past the mesh's own stable range and into
    catastrophic divergence, then rescales right back down from THAT
    diverged reading to approximately the ORIGINAL too-low pressure,
    forever alternating between the same two pressures without ever
    trying anything in between (verified directly: hippo.json at Level 1,
    target 60% RMS stretch, oscillated exactly this way under a
    rescale-only search -- 0.165 giving 9.55%, rescaled up to 0.827
    giving a diverged 70,185%, rescaled back down to 0.165, repeating
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
    a target it's moving away from. Returns (pressure, new_positions,
    steps_taken, max_stretch_pct, rms_stretch_pct, max_force, converged)
    -- the last five exactly as relax_once's own return, from whichever
    trial this settled on (if every single trial was insane, the LAST
    one anyway, so this never raises for an irrecoverably bad target).
    If `stop_event` fires mid-search, that's always the CURRENT trial --
    the one actually interrupted -- never an earlier, better-scoring but
    otherwise unrelated one, so a caller stopping this can rely on the
    result reflecting wherever it actually left off."""
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
    stopped = False
    for _ in range(max_iterations):
        result = relax_once(positions, faces, edge_length, pressure, planarity_weight,
                             max_nfev=max_nfev_per_trial, stop_event=stop_event, gtol=gtol,
                             rng=rng, fold_pairs=fold_pairs)
        _, _, _, rms_stretch, _, _ = result
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
    if stopped:
        # Interrupted mid-calibration (a caller's stop_event, e.g. a
        # user's Stop click) -- report exactly where THIS trial, the one
        # actually running when it was stopped, left off, not
        # best_result: an earlier, different-pressure trial might score
        # closer to the target on paper, but jumping to it would
        # silently discard the positions the caller was just watching
        # update, rather than the "return/render the last configuration"
        # a stop is supposed to give.
        best_pressure, best_result = pressure, result
    elif best_result is None:
        # Every trial was insane -- no sane candidate exists at all
        # within max_iterations; report the last attempt anyway rather
        # than raising, same as the original algorithm's own contract
        # (always returns SOMETHING derived from an actual relax_once
        # call).
        best_pressure, best_result = pressure, result
    new_positions, steps_taken, max_stretch, rms_stretch, max_force, converged = best_result
    return best_pressure, new_positions, steps_taken, max_stretch, rms_stretch, max_force, converged
