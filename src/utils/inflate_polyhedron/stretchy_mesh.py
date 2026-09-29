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
      "faces": [
        [0, 1, 2, 3, 4],
        [3, 2, 1, 0, 5],
        [0, 4, 3, 5]
      ]
    }

No "name" field -- a net's own display name is always its FILENAME (see
load_stretchy_mesh's own docstring), not anything stored inside the file,
so a copy/rename never leaves a stale name behind. A legacy file that
still carries one is simply ignored, harmless to leave in place.

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
2-manifold. load_stretchy_mesh rejects a directed edge that appears MORE
than once -- UNLESS the file carries its own "face_edge_ids" (see
mesh_edges' own docstring and interactive_builder_app's "net JSON
import/export" section): vertex dedup can legitimately merge enough
OTHER corners together that two edges never explicitly connected to
EACH OTHER end up sharing a directed vertex pair by pure coincidence
(each is still shared by at most its own 2 faces -- they just happen to
run between the same two now-merged points as some unrelated edge, like
two independent springs, not one edge claimed twice); "face_edge_ids"
is what lets a legitimate coincidence like that be told apart from an
actual authoring mistake. A file with no "face_edge_ids" has no such
information, so it keeps the strict check as a sanity guard, raising a
clear error naming the offending edge(s) if a directed edge repeats.

That check alone can't catch every possible mistake, though: flipping
EVERY face at once (a full mirror image) is just as valid a loop
structure as the original. A subtler problem can still reach the pipeline
even so: relax_initial_configuration's random-start-plus-spring relax
(see its own docstring) has no GLOBAL notion of "outward" at all, so it
can land globally inside-out, or genuinely mixed -- some faces each way
(its own per-vertex repulsion gating, see _vertex_outward_normals, only
discourages a LOCAL fold at each vertex as it relaxes, not a global
inside-out result). See _orientation_signs/_is_orientation_consistent for
how a caller can check this.

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
.claude/skills/net-fold-project/SKILL.md). Full scientific writeup:
docs/algorithm.md; current-state/tuning summary: .claude/skills/
net-fold-project/physics.md. Keep all three in sync when changing the
physics.

- **relax_once is a genuine force balance, walked step by step -- no
  volume anywhere** (_relax_force): each edge is a HARDENING spring (a
  `stretch + HARDENING_CUBIC_COEFFICIENT * stretch**3` restoring force --
  see the next note for why); each face applies a real outward force,
  `pressure * area * normal`, split across its own vertices. Each call
  moves every vertex a small step along its OWN net force (explicit
  relaxation), not a least_squares solve: a Newton-style solver
  re-linearizes the whole mesh and can jump straight past the
  physically-reachable equilibrium to a distant, spurious one (a
  doubled-size, heavily-stretched "solution", or a near-zero-volume
  implosion -- both real zeros of the same equations, but not ones a
  physical process starting nearby would ever walk to; see algorithm.md
  sec 4.2 for the full argument). Direction vectors use
  _safe_unit_vectors (a fixed fallback at an exact zero vector) instead
  of a naive division: without it, "every vertex exactly coincident" is
  a real zero of the force (every edge and face vanishes together) the
  relaxation could still land exactly on instead of the intended shape.

- **A hardening (linear + cubic) spring, not pure Hooke's-law linear.**
  See algorithm.md sec 4.1/4.4 and physics.md's Force model section for
  the full rationale: why pressure's quadratic area growth defeats a
  plain linear spring past some critical value, why a pure-cubic
  replacement was rejected (power-law rather than exponential settling
  near rest), and why the combined term is a real physical addition
  rather than the same kind of hack as the rejected stretch-limit (see
  physics.md's "No hacky terms rule").

- **relax_initial_configuration (Level 0's "Relax" step) uses a PLAIN
  LINEAR spring (_spring_only_force), not the hardening one above** --
  see physics.md's Force model section for why (no pressure there for
  the hardening term to guard against, and plain linear settles faster
  near rest). relax_once's own force (_relax_force) keeps the hardening
  term unchanged for every level's actual pressure-driven inflation.
"""
import collections
import json
import os

import numpy as np

from ..geometry.polyhedron import Polyhedron

EDGE_LENGTH = 1.0


def _face_edges(face):
    """The directed edges (v, w) of one CCW face loop."""
    k = len(face)
    return [(face[i], face[(i + 1) % k]) for i in range(k)]


def load_stretchy_mesh(path):
    """path: a vertex-loop stretchy-mesh .json (see module docstring).
    Returns (faces, name), faces a list of vertex-id lists. `name` is
    always `path`'s own basename (extension stripped) -- 2026-09-28,
    explicit user request: NOT read from any "name" field inside the
    file itself (a file can be copied/renamed without its own internal
    metadata staying in sync, which is exactly what caused a stale name
    to surface elsewhere -- see inflate_polyhedron_app's own
    on_save_session_clicked). A file's own "name" field, if it still has
    one from before this change, is simply never read here. Raises
    ValueError if any directed edge appears more than once -- the mesh
    need NOT be closed: an edge with no reverse partner at all is a
    valid, free boundary edge, not an error. See load_stretchy_mesh_edges
    for a file's own optional explicit "edges"/"face_edge_ids" fields --
    kept as a separate call (re-reading the same small JSON file) rather
    than added to this return, so this function's own return shape stays
    exactly what its existing callers/tests already unpack."""
    faces, _spec = _load_stretchy_mesh_spec(path)
    name = os.path.splitext(os.path.basename(path))[0]
    return faces, name


def load_stretchy_mesh_edges(path):
    """path: as load_stretchy_mesh. Returns (edges, face_edge_ids): the
    file's own explicit "edges" list (see mesh_edges' own docstring for
    why this can't always be safely re-derived from `faces` alone) as
    (a, b) tuples if the file has one, else None; and its own explicit
    "face_edge_ids" list (see mesh_levels.subdivide_once's own
    docstring) if the file has one, else None. A file written before
    these fields existed, or a hand-authored net where every edge's
    vertex-id pair is already unambiguous, has no reason to carry
    either."""
    _faces, spec = _load_stretchy_mesh_spec(path)
    raw_edges = spec.get("edges")
    edges = [tuple(e) for e in raw_edges] if raw_edges else None
    face_edge_ids = spec.get("face_edge_ids") or None
    return edges, face_edge_ids


def _load_stretchy_mesh_spec(path):
    """Shared parse+validate behind load_stretchy_mesh/
    load_stretchy_mesh_edges -- reads and winding-validates `path` once,
    returning (faces, spec) so each public function only picks its own
    fields out of the same parsed JSON, rather than duplicating the
    parse/validation.

    The "no directed edge appears more than once" check below is SKIPPED
    when the file has its own "face_edge_ids" field. That field only
    ever comes from interactive_builder_app._face_edge_ids_from_shapes,
    which is written on every Save -- meaning this exact net already
    passed _validate_shapes_connections there, whose own docstring
    explains why two DIFFERENT edges (each already fully accounted for
    by its own connection, or its own free/boundary edge) can
    legitimately land on the same directed vertex pair by coincidence
    once vertex dedup merges enough OTHER corners together: neither is
    actually claimed twice, they just happen to run between the same
    two (now-merged) points as some unrelated edge. A file with no
    "face_edge_ids" (hand-authored, or predating this field) has no such
    guarantee behind it, so it keeps the strict check as a sanity/typo
    guard -- there's no connection graph to tell a genuine authoring
    mistake apart from a legitimate coincidence for a file like that."""
    with open(path) as f:
        spec = json.load(f)

    faces = spec.get("faces") or []
    if not faces:
        raise ValueError(f"{path}: no faces declared")
    for face in faces:
        if len(face) < 3:
            raise ValueError(f"{path}: a face needs at least 3 vertices, got {face}")

    if not spec.get("face_edge_ids"):
        directed = [e for face in faces for e in _face_edges(face)]
        counts = {}
        for e in directed:
            counts[e] = counts.get(e, 0) + 1
        problems = [f"edge {v}->{w} appears {c} times (need exactly once)"
                    for (v, w), c in counts.items() if c > 1]
        if problems:
            raise ValueError(f"{path}: not a consistently-oriented mesh:\n  " +
                              "\n  ".join(problems))

    return faces, spec


def mesh_edges(faces, edges=None):
    """faces: vertex-id loops. Returns the mesh's undirected edges as a
    list of (a, b) with a < b. If `edges` is given (a file's own
    explicit edge list, e.g. from load_stretchy_mesh or
    interactive_builder_app._edges_from_shapes), it's returned as-is
    (each pair sorted, duplicates PRESERVED) instead of being re-derived
    from `faces`. Re-deriving purely from `faces`' shared vertex ids is
    ambiguous once vertex dedup has merged unrelated corners onto the
    same ids: two faces glued along more than one shared edge merges
    ALL of their connected corners pairwise, and their remaining FREE
    edges can then coincidentally land on the exact same vertex-id pair
    as each other despite never being connected -- a plain `set` (this
    function's fallback, for a file with no explicit `edges`, where that
    ambiguity can't arise) can't tell that apart from a genuinely shared
    edge, silently fusing two independent boundary edges into one."""
    if edges is not None:
        return [tuple(sorted(e)) for e in edges]
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


def _face_index_groups(faces, idx, pressure_exclude_faces=None):
    """faces/idx: as elsewhere. Groups EVERY face's vertex indices by
    side count (3..8) -- {n: array of shape (num_faces_with_n_sides, n)}
    -- for vectorized per-face area/outward-normal computation (see
    _relax_force).

    `pressure_exclude_faces`, if given, is a sequence of booleans the same length as `faces`
    -- any face where it's True is left out of every group entirely, so _relax_force's own
    pressure term never applies to it (2026-09-27, explicit user request: an "open" wedge
    triangle -- one whose own outer edge isn't glued to another polygon -- "should not
    experience inflation forces"). That face still exists completely normally everywhere
    else (edges/stretch/repulsion/convergence) -- this is the ONLY place its exclusion is
    applied."""
    groups = {}
    for i, face in enumerate(faces):
        if pressure_exclude_faces is not None and pressure_exclude_faces[i]:
            continue
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
# (`stretch + HARDENING_CUBIC_COEFFICIENT * stretch**3`). Was 1.0
# (unweighted sum); lowered to keep more of the original linear spring's
# behavior while still preventing the unbounded pressure blow-up a plain
# linear spring allows -- see physics.md's Force model section.
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


# All-pairs repulsion, used by every relax force (2026-09-27, explicit user request: "just for
# level 0, add some repulsion between all the vertices", then "let's add some repulsion to all
# the levels" as a test) -- inverse-square in distance, like electrostatic repulsion in a
# force-directed graph layout, between EVERY pair of vertices, not just edge-connected ones.
# At Level 0 (relax_initial_configuration's own _spring_only_force) this keeps the initial
# random cloud from leaving vertices piled up near each other before the spring network gets a
# chance to spread them into a well-separated shape; at Level 1+ (_relax_force, via
# relax_once's own `repulsion_strength` param) it's an extra separating force alongside real
# per-face pressure -- strong enough to measurably shift the pressure/stretch equilibrium (see
# relax_once's own comment), so a caller passing a non-default strength should expect to
# recalibrate pressure against it, not assume the old pressure-only tuning still applies.
# REPULSION_STRENGTH (the Level 0/1 baseline) is small relative to the spring's own stiffness
# (its restoring force at exactly 1 edge_length of stretch is 1.0), so it only meaningfully
# pushes vertices that are already close together, fading quickly at ordinary inter-vertex
# spacing rather than fighting the spring network's own job of finding the right edge lengths.
# Lowered from 0.05 (2026-09-27, explicit user report: restricting repulsion to just each
# original polygon's own raw corners -- see inflate_polyhedron_app's own
# _repulsion_vertex_ids -- made those specific, now much SPARSER vertices visibly spike
# outward past their own denser, non-repulsive subdivided neighbors at the old strength).
# MIN_REPULSION_DISTANCE floors the distance term so two vertices that land almost exactly on
# top of each other don't blow the force up toward infinity.
REPULSION_STRENGTH = 0.015
MIN_REPULSION_DISTANCE = 0.05


def repulsion_force(pts, strength=REPULSION_STRENGTH, indices=None, vertex_multipliers=None):
    """All-pairs inverse-square repulsion -- see REPULSION_STRENGTH's own comment. O(k^2) in
    vertex count, where k is len(indices) if given, else all of `pts` -- fine at Level 0/1's
    own (small, unsubdivided) scale, but the SAME O(n^2) cost every relax step at Level 2/3
    too, if run against every one of their own much larger vertex counts, was too slow in
    practice (2026-09-27, explicit user report). `indices` (array positions into `pts`, not
    vertex ids -- see relax_once's own `repulsion_vertex_ids` for the vertex-id-keyed version a
    caller actually passes), when given, restricts BOTH which vertices repel each other AND
    which vertices receive any resulting force to just that subset -- every vertex outside it
    gets a zero contribution here, left entirely to springs/pressure, same as if repulsion
    didn't exist for it at all.

    `vertex_multipliers`, if given, is an array the same length as `indices` (or `pts` if
    `indices` is None) -- each vertex's OWN [0, 1] scale on `strength` (2026-09-27, explicit
    user request: weaken repulsion at "closed" vertices specifically, progressively more at
    higher levels, while "open" ones stay at full strength -- see inflate_polyhedron_app's own
    _repulsion_vertex_multipliers). The pairwise force between i and j uses the PRODUCT of
    their own two multipliers (like a product of electrostatic charges), so a vertex weakened
    to e.g. 0.5 pulls down every pair it's part of by that factor, not just a single uniform
    rescale of the whole term. None (the default) means every vertex is at multiplier 1,
    mathematically identical to `strength` alone -- exactly this function's own behavior
    before this parameter existed."""
    n = pts.shape[0]
    sub_idx = np.arange(n) if indices is None else np.asarray(indices)
    sub_pts = pts[sub_idx]
    mult = (np.ones(len(sub_idx)) if vertex_multipliers is None
            else np.asarray(vertex_multipliers, dtype=float))
    diff = sub_pts[:, None, :] - sub_pts[None, :, :]  # diff[i, j] = sub_pts[i] - sub_pts[j]
    dist_safe = np.maximum(np.linalg.norm(diff, axis=2), MIN_REPULSION_DISTANCE)
    pair_mult = mult[:, None] * mult[None, :]
    magnitude = strength * pair_mult / dist_safe ** 2
    np.fill_diagonal(magnitude, 0.0)  # no self-repulsion
    sub_force = np.sum(diff / dist_safe[:, :, None] * magnitude[:, :, None], axis=1)
    force = np.zeros((n, 3))
    force[sub_idx] = sub_force
    return force


def _vertex_outward_normals(pts, all_face_groups):
    """pts: (N,3); all_face_groups: as _face_index_groups' own return (every face's vertex
    indices INTO pts, grouped by side count) -- same structure _relax_force's own pressure term
    uses, reused here so this works for any polygon size, not just triangles. Returns (N,3):
    each vertex's own outward direction as the NORMALIZED SUM of its incident faces' unit
    normals, each face weighted equally (not by area) -- same definition as
    inflate_polyhedron_app's own _vertex_normals (used there for "Show vertex normals"), just
    array-indexed. Each face's own unit normal is its `area * outward_normal` Newell's-method
    vector (see _relax_force's own comment), normalized -- "outward" here means whatever the
    mesh's own face WINDING implies, the same convention _relax_force's pressure term and
    _orientation_signs both already use elsewhere -- not a distance-from-centroid guess -- so
    it's well-defined even for a currently-folded/self-intersecting embedding.

    A vertex touching no non-degenerate face, or whose incident face normals cancel exactly,
    gets the GENUINE zero vector here -- deliberately NOT _safe_unit_vectors' own (1,0,0)
    fallback (meant for a spring direction, where SOME direction is needed to avoid a NaN step):
    a zero row here means "no known outward direction", and a zero dot product against it
    leaves a repulsion force untouched (not `< 0`) rather than risking suppressing a
    perfectly legitimate force because of an arbitrary fallback axis."""
    n = pts.shape[0]
    normal_sums = np.zeros((n, 3))
    for n_sides, group_idx in all_face_groups.items():
        face_pts = pts[group_idx]                                     # (F, n_sides, 3)
        next_pts = np.roll(face_pts, -1, axis=1)
        area_vector = 0.5 * np.cross(face_pts, next_pts).sum(axis=1)   # (F, 3)
        lens = np.linalg.norm(area_vector, axis=1)
        ok = lens > 1e-12
        unit = np.zeros_like(area_vector)
        unit[ok] = area_vector[ok] / lens[ok, None]
        np.add.at(normal_sums, group_idx.ravel(), np.repeat(unit, n_sides, axis=0))
    sum_lens = np.linalg.norm(normal_sums, axis=1)
    ok_vertex = sum_lens > 1e-12
    result = np.zeros((n, 3))
    result[ok_vertex] = normal_sums[ok_vertex] / sum_lens[ok_vertex, None]
    return result


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


def _edge_setup(faces, edge_length, edges=None, pressure_exclude_faces=None):
    """faces: vertex-id loops (see module docstring for the winding
    convention); edge_length: scalar rest length, or a {(a,b): length}
    dict for a non-uniform (e.g. subdivided) mesh; edges: an explicit
    mesh-edge list (see mesh_edges' own docstring), or None to derive one
    from `faces`. `pressure_exclude_faces`: as _face_index_groups.
    Shared setup for relax_once/relax_initial_configuration:
    vertex/edge index arrays plus the precomputed structures _relax_force
    needs (built once here, not per call). Returns (vertex_ids, idx,
    edges, edge_ai, edge_bi, all_face_groups, length_arr, scale)."""
    vertex_ids = sorted({v for face in faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    edges = mesh_edges(faces, edges)
    edge_ai, edge_bi = _pair_index_arrays(edges, idx)
    all_face_groups = _face_index_groups(faces, idx, pressure_exclude_faces)
    if isinstance(edge_length, dict):
        length_arr = np.array([edge_length[e] for e in edges])
        scale = float(np.min(length_arr)) if len(length_arr) else 1.0
    else:
        length_arr = edge_length
        scale = float(edge_length)
    return (vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups,
            length_arr, scale)


def _positions_and_stretch(pts, vertex_ids, edges, length_arr, rms_exclude_edges=None):
    """pts: (N,3) flat solved positions; vertex_ids/edges/length_arr: as
    from _edge_setup. Returns (positions dict, max_stretch_pct,
    rms_stretch_pct).

    `rms_exclude_edges`, if given, is a set of (a, b) SORTED vertex-id-pair tuples to omit
    from the RMS stat -- `max_stretch_pct` always still uses every edge. Membership is
    checked per edge here rather than requiring a mask the same length/order as `edges`, so a
    caller building this set (e.g. inflate_polyhedron_app's own "exclude any OPEN polygon's
    own edges from RMS" -- 2026-09-27, explicit user request) doesn't need to know anything
    about how `edges` got built or ordered. Falls back to including every edge if the
    exclusion would otherwise leave nothing to average (e.g. every polygon in the mesh is
    open) rather than producing a NaN."""
    positions = {v: pts[i] for i, v in enumerate(vertex_ids)}
    lengths = np.array([np.linalg.norm(positions[a] - positions[b]) for a, b in edges])
    stretch_pct = 100 * (lengths - length_arr) / length_arr
    max_stretch_pct = float(np.max(np.abs(stretch_pct)))
    rms_stretch_pct = float(np.sqrt(np.mean(stretch_pct ** 2)))
    if rms_exclude_edges:
        rms_mask = np.array([tuple(sorted(e)) not in rms_exclude_edges for e in edges])
        if rms_mask.any() and not rms_mask.all():
            rms_stretch_pct = float(np.sqrt(np.mean(stretch_pct[rms_mask] ** 2)))
    return positions, max_stretch_pct, rms_stretch_pct


# relax_once's convergence check: a step counts as "at rest" once every
# vertex's own net force drops below this. Compared directly against the
# force computed by _relax_force -- unlike the old scipy `optimality`
# measure, this is just "how far from equilibrium is the worst vertex",
# so it's meaningful on its own rather than needing scipy's internals to
# interpret. Currently compared against displacement, not force, checked
# only every CONVERGENCE_CHECK_INTERVAL steps rather than every step --
# see physics.md's Convergence section (an active experiment, easy to
# revert to an every-step force comparison); this constant's own
# value/meaning as a per-step rate is unaffected either way.
CONVERGENCE_GTOL = 1e-4

# How often _explicit_relax_loop actually checks the stopping condition
# above, in steps, rather than comparing against `gtol` every single step
# (see physics.md's Convergence section). This also used to gate
# inflate_polyhedron_app's own chunked calling pattern, now removed in
# favor of relax_once/relax_initial_configuration calling this check's
# own `on_check` hook directly (see physics.md's Progress callback
# section for the "515 steps" artifact that chunking caused).
CONVERGENCE_CHECK_INTERVAL = 200

# Explicit relaxation step size: the vertex with the largest net force
# moves this fraction of the mesh's own rest edge length in one
# iteration; every other vertex moves proportionally less (force is
# normalized by its own max each step). Keeps steps small and stable
# (a real physical walk, not a linearized jump that can overshoot the
# reachable equilibrium -- see module docstring's Design notes). The
# former adaptive term (shrinking the step further when force is large)
# is gone -- see _explicit_relax_loop's own comment -- so this constant
# is currently the WHOLE step size, not just a cap on it.
#
# Scaled by the mesh's own rest edge length (`scale`), not a fixed
# absolute cap: a fixed cap would be a shrinking fraction of an edge as
# the mesh subdivides finer but a growing one as it gets coarser, since
# `scale` itself is an absolute length and drops at each Subdivide level.
#
# Value found by direct bisection for stability -- an undamped 2-cycle in
# max_stretch_pct (force stuck alternating between two fixed values
# forever, distinct from a genuinely slow but decaying power-law tail
# near equilibrium) is the failure mode being avoided -- re-verified
# after each change to the spring force itself (linear -> pure quartic ->
# the current hardening term) and after HARDENING_CUBIC_COEFFICIENT was
# lowered from 1.0 to 0.5 (boundary barely moved). See physics.md's Force
# model / Defaults sections for the current value and force-law history.
STEP_MAX_MULTIPLIER = 0.05

# Hard cap on iterations when max_nfev=None (run-to-convergence): explicit
# steps have no scipy-style internal budget of their own, so this stands
# in for one.
MAX_UNBOUNDED_STEPS = 200_000

# The plateau/stall-window convergence shortcut (STALL_WINDOW/
# STALL_TOL_PCT: converge once max_stretch_pct's range over many steps
# stops moving, alongside the real gtol check) was REMOVED entirely --
# it's a fixed, gtol-INDEPENDENT threshold, so at a tighter gtol than it
# was ever tuned against it declared "converged" early, well before the
# mesh had actually reached the real target (see physics.md's Convergence
# section). inflate_polyhedron_app's own INFLATE_SAFETY_STEP_CAP is judged
# sufficient on its own as the non-gtol way a run can end. See git history
# (STALL_WINDOW/STALL_TOL_PCT/STALL_DETECTION_ENABLED) if a plateau-style
# shortcut is ever wanted again.

# Escaping a genuine local-minimum "dimple": a pure explicit gradient-
# style walk has no momentum to coast through a shallow energy barrier
# with, so once a vertex settles into one, smaller OR larger steps both
# just oscillate around it forever rather than crossing over. `rng`
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
# Relax/Inflate runs -- found to interact badly with a genuinely slow
# (not stuck) relaxation (see physics.md's Convergence section).
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
    rotation/translation happened to appear between the two, leaving only
    the genuine shape change (every PAIRWISE distance within `pts_after`
    is preserved exactly, since a rigid transform is an isometry -- so
    this can never affect stretch stats, convergence, or anything else
    the physics actually cares about).

    A free-floating spring/pressure system (nothing pins any vertex to a
    fixed point) has no preferred orientation of its own -- rotating the
    WHOLE mesh about its own center of mass costs zero spring/pressure
    energy, so it's an exactly-flat direction the relaxation can drift
    along for free, and nothing in _relax_force/_spring_only_force
    distinguishes "genuine shape change" from "the whole shape turning in
    place". This isn't only small numerical noise: an ASYMMETRIC net
    (e.g. an off-center Polygon Fold pinch) can have a genuine, physically
    -driven rotational component to its own gradient-descent path toward
    lower stretch, which compounds block over block exactly like real
    motion would, since nothing in the force law objects to it (2026-09-26,
    explicit bug report: a ~121-degree net rotation measured between two
    levels of `three_poly_pinch.hippo`, confirmed via this same Kabsch fit
    applied to the two levels' own shared base vertices). _explicit_relax_
    loop now calls this against a FIXED reference (the state at the very
    start of the run), not a rolling one -- see its own docstring for why
    that specific choice, and not just "call this more often", is what
    actually eliminates cumulative drift rather than merely bounding it
    per-block."""
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
    them are the force itself (`force_fn(pts) -> (N,3)`) and each force
    law's own safe step size (`step_max_multiplier`, defaulting to the
    module's own STEP_MAX_MULTIPLIER for relax_once's hardening spring;
    relax_initial_configuration passes LEVEL0_STEP_MAX_MULTIPLIER for its
    own plain linear one) -- the walking/stopping logic is otherwise
    identical, so it lives here once rather than kept in sync by hand.

    Repeatedly nudges `pts` a small step along `force_fn(pts)`; if `rng`
    is given and the worst vertex's force has been OSCILLATING rather
    than genuinely dropping (see KICK_WINDOW's own comment), nudges every
    vertex by a small random perturbation weighted toward whichever one
    is actually stuck -- until EITHER the worst vertex's own displacement
    over the last CONVERGENCE_CHECK_INTERVAL steps drops below
    `CONVERGENCE_CHECK_INTERVAL * gtol` (checked only once every
    CONVERGENCE_CHECK_INTERVAL steps -- see physics.md's Convergence
    section for the current tuning/rationale), or `max_nfev`/`stop_event`
    cuts it off first.

    Whatever rigid rotation/translation the raw per-step updates
    introduce (_remove_rigid_motion, see its own docstring for why a
    free-floating system needs this) is only computed ONCE per
    CONVERGENCE_CHECK_INTERVAL-step block, immediately before that
    block's convergence check, rather than after every individual step --
    still exactly equivalent to correcting every step (not an
    approximation) as far as the mesh's own SHAPE trajectory goes: every
    force here (spring stretch, pressure area-vector) depends only on
    relative vertex geometry, so it's translation-invariant and rotation-
    equivariant, meaning every edge length/face shape the physics actually
    computes never depends on what rigid frame the steps in between
    happened to be sitting in.

    Aligned against `pts_at_run_start` -- this call's own STARTING
    positions, captured once and never updated -- rather than a rolling
    "the previous block's own end state" (2026-09-26, explicit user
    request, after a ~121-degree net rotation was observed and traced to
    exactly this choice: see _remove_rigid_motion's own docstring). A
    rolling reference only cancels drift introduced WITHIN each block,
    chained block to block -- mathematically fine for removing numerical
    noise, but it does nothing to stop a genuine, physically-driven
    per-block rotational component (an asymmetric net has no reason to
    prefer zero rotation over any other) from compounding across many
    blocks, since each new block's "zero rotation" reference is itself
    already however-many-degrees rotated from where the run began. Aligning
    to the fixed start instead makes every reported/returned `pts` exactly
    orientation-locked to the run's own beginning for its ENTIRE duration,
    not just drift-free one block at a time -- still a pure isometric
    correction (same reasoning above: shape trajectory is frame-
    independent), so this changes nothing about convergence or stretch,
    only which orientation gets reported.

    `pts_at_last_check` (a separate, still-rolling reference) remains
    for the CONVERGENCE comparison itself (`block_displacement` below) --
    "has the mesh stopped moving" is inherently a block-to-block question,
    unrelated to which frame the rigid-motion removal itself targets; both
    `pts` and `pts_at_last_check` live in the same fixed run-start frame
    by this point regardless, so their difference is unaffected either way.
    `on_check(pts, steps_taken, optimality, converged)`, if given, is
    called every time this periodic check runs (whether or not it ends
    the run) -- lets a caller sync progress reporting (e.g.
    inflate_polyhedron_app redrawing its 3D panels) to the SAME cadence
    as the actual convergence check.

    Returns (pts, steps_taken, optimality, converged) -- `optimality` is
    that same worst-vertex displacement from the last completed check,
    divided back down by CONVERGENCE_CHECK_INTERVAL so it's directly
    comparable to plain `gtol`, `None` if stopped before a single check
    completed. Callers each compute their own final positions/stretch
    stats from `pts`."""
    if step_max_multiplier is None:
        step_max_multiplier = STEP_MAX_MULTIPLIER
    step_cap = max_nfev if max_nfev is not None else MAX_UNBOUNDED_STEPS
    steps_taken = 0
    converged = False
    optimality = None
    pts_at_run_start = pts.copy()
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
        # when max_force is large) removed and re-offered/declined again
        # since -- don't reintroduce without new explicit permission naming
        # this change (see physics.md's "No hacky terms rule").
        dt = step_max_multiplier * scale
        pts = pts + dt * force
        if rng is not None:
            recent_max_force.append(max_force)
            if (len(recent_max_force) == KICK_WINDOW
                    and max_force > KICK_STALL_RATIO * recent_max_force[0]):
                weight = (per_vertex_force / max_force)[:, None]
                kick = rng.normal(scale=KICK_MAGNITUDE_FRACTION * scale, size=pts.shape)
                pts = pts + kick * weight
                recent_max_force.clear()  # give the kick a fresh window to show its effect
        # Checked only once every CONVERGENCE_CHECK_INTERVAL steps (see
        # physics.md's Convergence section), comparing the worst vertex's
        # own displacement ACCUMULATED over that whole interval (against
        # pts_at_last_check, the position at the START of the interval)
        # to CONVERGENCE_CHECK_INTERVAL * gtol, the same per-step rate
        # scaled up to the longer window -- so a genuine multi-step drift
        # is caught even if no single step's own displacement would trip
        # an every-step check. Rigid rotation/translation is stripped out
        # HERE, once per block, against the FIXED pts_at_run_start (see
        # this function's own docstring for why a fixed reference, not a
        # rolling one, is what actually prevents cumulative drift) --
        # still just once per block, not after every step.
        if steps_taken % CONVERGENCE_CHECK_INTERVAL == 0:
            pts = _remove_rigid_motion(pts_at_run_start, pts)
            block_displacement = float(np.linalg.norm(pts - pts_at_last_check, axis=1).max())
            optimality = block_displacement / CONVERGENCE_CHECK_INTERVAL
            pts_at_last_check = pts.copy()
            if block_displacement < CONVERGENCE_CHECK_INTERVAL * gtol:
                converged = True
            if on_check is not None:
                on_check(pts, steps_taken, optimality, converged)
            if converged:
                break
    # A run that stops mid-block (stop_event, or step_cap not a multiple
    # of CONVERGENCE_CHECK_INTERVAL) never hit the alignment above for
    # its own trailing partial block -- align once more here (same fixed
    # pts_at_run_start reference) so callers never see a `pts` still
    # carrying uncorrected rigid drift, even though no convergence check
    # ran against it.
    if steps_taken % CONVERGENCE_CHECK_INTERVAL != 0:
        pts = _remove_rigid_motion(pts_at_run_start, pts)
    return pts, steps_taken, optimality, converged


def relax_once(positions, faces, edge_length, pressure=0.0,
                max_nfev=None, stop_event=None,
                gtol=CONVERGENCE_GTOL, rng=None, on_progress=None, edges=None,
                repulsion_strength=REPULSION_STRENGTH, repulsion_vertex_ids=None,
                repulsion_vertex_multipliers=None,
                rms_exclude_edges=None, pressure_exclude_faces=None):
    """positions: {vertex_id: [x,y,z]} starting point; faces/edge_length/
    edges: as _edge_setup. `repulsion_vertex_multipliers`: a {vertex_id: multiplier} dict (only
    needs entries for vertices NOT at the default multiplier of 1) forwarded to
    repulsion_force's own `vertex_multipliers` (see its own comment) -- translated here from
    vertex ids to the same array-index space `repulsion_vertex_ids` already gets translated to.
    `pressure_exclude_faces`: as _face_index_groups -- those faces get
    NO pressure force at all (still fully present for springs/repulsion/edges/convergence).
    `rms_exclude_edges`: as _positions_and_stretch (excluded from every
    reported/checked rms_stretch_pct here, both live progress and the final return -- never
    affects max_stretch_pct, the convergence check itself, or the springs/pressure/repulsion
    forces actually driving the relaxation, only which edges' stretch gets AVERAGED into the
    one summary number). Runs ONE relaxation pass at a fixed `pressure`
    -- no automatic ramp; call again with the result to keep steering it.
    Each iteration moves every vertex a small step along its own net
    force from _relax_force PLUS repulsion_force at `repulsion_strength`
    (2026-09-27, explicit user request, as a test: "let's add some
    repulsion to all the levels" -- previously Level 0 only; see
    repulsion_force's own comment for why the default is weak enough
    not to fight the spring/pressure forces at ordinary spacing).

    `repulsion_vertex_ids`, if given, restricts repulsion to just that
    subset of `positions`' own vertex ids (translated to _repulsion_
    force's own array-index space here, via this call's own `idx`) --
    every OTHER vertex gets zero repulsion, left entirely to springs/
    pressure. None (the default) repels every vertex, O(n^2) in the
    mesh's own current vertex count -- fine at Level 0/1's scale, but
    running the SAME O(n^2) cost every relax step against Level 2/3's
    own much larger vertex count was too slow in practice (2026-09-27,
    explicit user report) -- inflate_polyhedron_app instead passes
    Level 0's own small, fixed vertex-id set at every level ("let's use
    the same set of points (from level 0) for all the levels"), keeping
    the repulsion population size constant regardless of how many finer
    vertices later Subdivides add. `repulsion_strength` is a SEPARATE,
    independent knob from this -- inflate_polyhedron_app still halves it
    at each level past 1 ("let's still halve the repulsion from L1->L2
    and L2->L3, but still use the same set of points for all the
    levels"), it just no longer needs to ALSO shrink the population to
    keep the per-step cost down, now that this param does that instead
    (see module docstring's Design notes for why this walks explicitly
    rather than handing the force balance to a Newton-style solver) --
    `pressure` is a real per-face outward force, with no volume or
    remembered state anywhere in it.

    `max_nfev` caps the number of steps; None runs until convergence
    (capped at MAX_UNBOUNDED_STEPS as a runaway guard), via the worst
    vertex's own displacement dropping below `gtol` (see
    _explicit_relax_loop / physics.md's Convergence section for the
    current check cadence). `stop_event` (a threading.Event), if given,
    is checked before each step and aborts at the next one, returning
    whatever position was last reached. `rng` (a numpy Generator, e.g.
    `np.random.default_rng()`), if given, opts into an occasional random
    perturbation when a vertex is stuck oscillating rather than genuinely
    converging -- see KICK_WINDOW's own comment; `None` (the default) is
    fully deterministic.

    `on_progress(new_positions, steps_taken, max_stretch_pct,
    rms_stretch_pct, optimality, converged)`, if given, is called every
    CONVERGENCE_CHECK_INTERVAL steps (the same cadence the stopping
    condition itself is checked at) with exactly this function's own
    return shape, so a caller can sync its own progress reporting to
    real convergence-check points instead of an artificial schedule of
    its own (see physics.md's Progress callback section).

    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    optimality, converged). `optimality` is exactly the quantity compared
    against `gtol` above (the worst vertex's own last-step displacement),
    None if stopped before a single step ran. `converged` is True only if
    one of the two criteria above (not the step cap or a stop request) is
    what stopped it."""
    vertex_ids, idx, edges, edge_ai, edge_bi, all_face_groups, length_arr, scale = \
        _edge_setup(faces, edge_length, edges, pressure_exclude_faces)
    pts0 = np.array([positions[v] for v in vertex_ids], dtype=float)
    if repulsion_vertex_ids is None:
        repulsion_indices = None
        repulsion_mult_arr = None
    else:
        present_repulsion_ids = [v for v in repulsion_vertex_ids if v in idx]
        repulsion_indices = [idx[v] for v in present_repulsion_ids]
        repulsion_mult_arr = (None if repulsion_vertex_multipliers is None
                               else [repulsion_vertex_multipliers.get(v, 1.0)
                                     for v in present_repulsion_ids])

    def force_fn(pts):
        return (_relax_force(pts, edge_ai, edge_bi, all_face_groups, length_arr, pressure)
                + repulsion_force(pts, strength=repulsion_strength, indices=repulsion_indices,
                                   vertex_multipliers=repulsion_mult_arr))

    def on_check(check_pts, check_steps, check_optimality, check_converged):
        check_positions, check_max_stretch, check_rms_stretch = _positions_and_stretch(
            check_pts, vertex_ids, edges, length_arr, rms_exclude_edges)
        on_progress(check_positions, check_steps, check_max_stretch, check_rms_stretch,
                    check_optimality, check_converged)

    pts, steps_taken, optimality, converged = _explicit_relax_loop(
        pts0, scale, force_fn, max_nfev, stop_event, gtol, rng,
        step_max_multiplier=STEP_MAX_MULTIPLIER,
        on_check=on_check if on_progress is not None else None)
    new_positions, max_stretch, rms_stretch = _positions_and_stretch(
        pts, vertex_ids, edges, length_arr, rms_exclude_edges)
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
# relax_once's STEP_MAX_MULTIPLIER -- since _spring_only_force is a
# plain LINEAR spring (see its own docstring), not the hardening one
# STEP_MAX_MULTIPLIER=0.05 was tuned for, sharing that smaller value here
# just needlessly throttles a force law that never needed it. See
# physics.md's Force model section for the current value and the
# history of why it moved: restored to 0.2 (the pre-hardening value for
# a plain linear spring) after a smaller shared step interacted badly
# with the KICK_WINDOW mechanism and caused Level 0 to jiggle instead of
# converging; then lowered again to 0.1 once every triangular face
# started getting fanned too, since a high-valence "joint" vertex (e.g.
# composite_spider_leg.poly's vertex 0/5, each touching 8 base faces)
# gains enough extra local stiffness from the added spoke springs to
# diverge explosively under the old fixed 0.2 step.
LEVEL0_STEP_MAX_MULTIPLIER = 0.1


def _spring_only_force(pts, edge_ai, edge_bi, edge_length):
    """Pure Hooke's-law LINEAR spring force for relax_initial_configuration
    -- deliberately NOT the same hardening term _relax_force uses (see
    module docstring's Design notes and physics.md's Force model
    section): with pressure=0, there's no outward force for a hardening
    term to guard against in the first place, and plain linear settles
    faster near rest. Faces aren't expected to be flat or even
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




# Periodic "jiggle" (2026-09-28, explicit user request: "shake things up a bit every 200 steps
# ... jiggle in the direction of the vertex normals ... basically an inflation burst every 200
# steps") -- unlike an earlier sustained-pressure burst (tried and removed, see git history),
# this is a single bounded DISPLACEMENT kick along each vertex's own outward normal
# (_vertex_outward_normals, same winding-based convention the repulsion gate above already
# uses). Gated by should_jiggle_next (see its own comment in relax_initial_configuration): a
# jiggle only fires while the mesh hasn't yet been reported converged by the MOST RECENT
# CONVERGENCE_CHECK_INTERVAL-cadence check (fixed at 200 steps, not adjustable here) -- doing
# it unconditionally forever meant the check could never actually see a genuinely settled mesh.
# 200 -> 100 (2026-09-28, "a bit more often, say every 100 steps instead") -> 50 (2026-09-28,
# "inflate more frequently, in smaller doses"). Still evenly divides CONVERGENCE_CHECK_INTERVAL
# (200), so a jiggle never lands ON the check step itself (fires at step_count % 50 == 1, the
# check at step_count % 200 == 0 -- residues 1 and 0 of a shared divisor never coincide), which
# is what keeps the "check is never mid-jiggle" property this whole mechanism relies on --
# see should_jiggle_next's own comment for why that matters. An un-converged block now gets up
# to 4 jiggles (steps 1/51/101/151) before its own check at step 200, not just 2.
LEVEL0_JIGGLE_INTERVAL_STEPS = 50

# Fixed DISPLACEMENT (not force) magnitude per jiggle, as a fraction of the mesh's own `scale`
# (_edge_setup's own representative rest-length scalar -- the min edge length for a per-edge
# dict, or the uniform edge length itself, same value _explicit_relax_loop's own step size is
# scaled against) -- deliberately bounded independent of current geometry (unlike a pressure
# force, whose magnitude scales with CURRENT face area and blew up against
# random_initial_positions' own wildly-oversized raw starting spread -- see git history), so no
# separate warmup delay is needed before the first jiggle. Converted to an equivalent one-step
# FORCE (jiggle_distance / dt) inside force_fn, since _explicit_relax_loop only accepts a force
# to apply, not a direct position nudge. 0.2 -> 0.4 ("enable the jiggle and double that") -> 0.8
# ("make the inflation bursts in level 0 stronger") -> 0.4 (2026-09-28, "inflate more
# frequently, in smaller doses" -- halved back down alongside LEVEL0_JIGGLE_INTERVAL_STEPS
# above). Verified stable (no blowup, still converges) across icosahedron/hippo/cube/turtle/
# giraffe at this interval/fraction pair, and at a further halving of both (25/0.2) too, so
# there's real margin either direction from here.
LEVEL0_JIGGLE_DISTANCE_FRACTION = 0.4


def level0_jiggle_distance(faces, edge_length, edges=None):
    """The actual jiggle displacement magnitude relax_initial_configuration applies at Level 0
    (LEVEL0_JIGGLE_DISTANCE_FRACTION * scale -- see that constant's own comment for what
    `scale` is), exposed here purely for DISPLAY (2026-09-28, explicit user request: show the
    Level 0 burst strength used, in the Convergence History table's own "Pressure" column,
    which otherwise reads "--" for Level 0 since Level 0 never calibrates a real pressure the
    way relax_once does). This is a length (same units as `edge_length`), not literally a
    pressure -- shown there anyway since it's the closest analogue "how strong was the burst"
    has for Level 0, and that column has no other use at Level 0."""
    _, _, _, _, _, _, _, scale = _edge_setup(faces, edge_length, edges)
    return LEVEL0_JIGGLE_DISTANCE_FRACTION * scale


def relax_initial_configuration(positions, faces, edge_length,
                                 max_nfev=None, stop_event=None, gtol=CONVERGENCE_GTOL, rng=None,
                                 on_progress=None, edges=None, rms_exclude_edges=None,
                                 pressure_exclude_faces=None):
    """positions/faces/edge_length/edges/rms_exclude_edges: as relax_once, but `positions` is
    typically random_initial_positions' output here, not a meaningful
    embedding -- this is what turns it into one, WITHOUT ever touching
    pressure: pure Hooke's-law springs (_spring_only_force) plus an
    all-pairs repulsion between EVERY vertex (repulsion_force, see its
    own comment) -- the repulsion is the only thing here that has any
    opinion about a pair of vertices with no edge between them at all,
    and only at short range (it fades quickly past ordinary spacing).
    Nothing here fixes overall position/scale, so the result can end up
    anywhere in space, at any scale, and self-intersecting -- fine, since
    the only goal is a well-separated, edge-length-plausible starting
    point for relax_once's real per-face pressure model afterward. Any
    view of this result must re-derive its own camera
    framing from its actual bounding box (see _draw_wireframe_panel)
    rather than assuming it lands near the origin or at a familiar scale.
    See this module's docstring for why a plain polyhedron wireframe
    (e.g. a cube's own 12 edges, no face diagonals) needs to already be
    subdivided into all-triangle faces (see mesh_levels.subdivide_once)
    before this can find a well-defined 3D shape at all: an unbraced
    quad/pentagon face is a genuine mechanism (like an unbraced
    rectangular frame), not a rigid one, so springs alone can't stop it
    flexing arbitrarily.

    Same stopping rule as relax_once (see _explicit_relax_loop /
    physics.md's Convergence section): `gtol` on the worst vertex's own
    last-step displacement, or `max_nfev`/`stop_event`. `rng`, as in
    relax_once, opts into an occasional random perturbation when stuck
    oscillating (`None` -- the default -- is fully deterministic).
    `on_progress`, as in relax_once, is called every CONVERGENCE_CHECK_
    INTERVAL steps with this function's own return shape.
    Each vertex's own repulsion force (see repulsion_force) is discarded entirely whenever it
    points INWARD -- dot(repulsion_force_at_v, outward_normal_at_v) < 0 (2026-09-28, explicit
    user request) -- rather than letting repulsion push a vertex further into a fold. See
    _vertex_outward_normals' own docstring for what "outward" means here (the mesh's own face
    winding, not a centroid guess) and why a vertex with no well-defined outward direction (the
    zero vector) leaves its repulsion force untouched instead of risking suppressing it on an
    arbitrary fallback axis.

    Every LEVEL0_JIGGLE_INTERVAL_STEPS steps, every vertex also gets a one-step kick along its
    own outward normal (see LEVEL0_JIGGLE_INTERVAL_STEPS/LEVEL0_JIGGLE_DISTANCE_FRACTION's own
    comments) -- meant to jog a locally-stuck/folded region loose periodically, not to shape
    the final result. Convergence is always checked BEFORE that block's own jiggle, never after
    (2026-09-28, explicit user request: "the jiggle shouldn't be taken into account or it'll
    never converge") -- a block's own convergence check and a jiggle NEVER land in the same
    block, so a genuinely at-rest mesh is reported converged (and the loop stops) at the very
    next check, without ever depending on a kick having fully re-settled first. See
    should_jiggle_next's own comment below for how.

    `pressure_exclude_faces`: as _face_index_groups -- an OPEN wedge triangle contributes
    NOTHING to the JIGGLE's own per-vertex outward normal (2026-09-28, explicit user request:
    match Level 1+'s own rule that an open wedge "should not experience inflation forces" --
    see relax_once's own `pressure_exclude_faces` and _face_index_groups' comment; the jiggle
    IS a kind of inflation force, per its own comment). Does NOT affect the repulsion-gate's
    own outward normal, which still considers every face -- that gate has no established
    open/closed distinction of its own (unlike pressure, repulsion was never excluded from open
    wedges at Level 1+ either), so this only narrows what the jiggle itself reads. A vertex
    touching ONLY open faces gets the zero vector for the jiggle's own normal (see
    _vertex_outward_normals' own docstring) and so contributes nothing to that step's jiggle;
    a vertex touching at least one CLOSED face still gets a perfectly good normal from that
    face alone.

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
    # block (nothing has been checked yet, so nothing has earned a jiggle); once a check
    # reports converged, this is set False too, but by then the loop is about to break anyway
    # (_explicit_relax_loop breaks the same iteration its own on_check fires) -- so it's really
    # only ever True for the block immediately following a NOT-yet-converged check.
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
            check_positions, check_max_stretch, check_rms_stretch = _positions_and_stretch(
                check_pts, vertex_ids, edges, length_arr, rms_exclude_edges)
            on_progress(check_positions, check_steps, check_max_stretch, check_rms_stretch,
                        check_optimality, check_converged)

    # Always passed now (not conditional on on_progress), since should_jiggle_next needs
    # updating every check regardless of whether the caller wants progress reports too.
    pts, steps_taken, optimality, converged = _explicit_relax_loop(
        pts0, scale, force_fn, max_nfev, stop_event, gtol, rng,
        step_max_multiplier=LEVEL0_STEP_MAX_MULTIPLIER,
        on_check=on_check)

    new_positions, max_stretch, rms_stretch = _positions_and_stretch(
        pts, vertex_ids, edges, length_arr, rms_exclude_edges)
    return new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged


# Empirical starting point for estimate_pressure_for_target_stretch:
# required pressure scales with how much total rest AREA it's pushing
# against, not vertex/face count -- see physics.md's Pressure calibration
# section for the derivation (bisected on the 5 Platonic solids) and why
# it didn't need re-deriving after the spring force became hardening. A
# decent first guess, not exact, which is why the function refines it
# against an actual relax_once result rather than trusting it alone.
_PRESSURE_AREA_PRODUCT_ESTIMATE = 25.0

# How far a single calibration step is allowed to rescale pressure --
# guards against a wild jump if one trial's stretch reading is degenerate
# (e.g. near zero), while still letting normal cases converge in a couple
# of iterations (stretch responds roughly linearly to pressure in the low-
# stretch regime this targets, verified against the bisection trace above).
_PRESSURE_RATIO_CLAMP = (0.2, 5.0)

# Was 8.0, then 10.0; lowered to 5.0 per explicit user request (2026-09-28: "let the default
# target stretch be all 5%") -- matches inflate_polyhedron_app's own LEVEL_DEFAULT_TARGET_RMS_
# PCT, now 5.0 at every level too.
DEFAULT_TARGET_RMS_STRETCH_PCT = 5.0



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
# exactly like any other insane/blown-up trial by the bracket search.
# Never surfaced to a user in practice. A generic safety net, kept even
# though calibration now uses the exact same step size a real Inflate run
# always has -- see physics.md's Pressure calibration section for why the
# old step-size multiplier was removed.
_DIVERGED_SENTINEL_STRETCH_PCT = 1e6

# How many consecutive trials, still in the pure-rescale phase (no
# lo/hi bracket established yet), with essentially NO change in achieved
# stretch despite pressure being rescaled (up to the 5x ceiling each
# time), before giving up on finding a real pressure at this level
# rather than escalating pressure without bound -- see physics.md's
# Pressure calibration section (Unresponsive-mesh stall detection) for
# the full rationale and the concrete ravioli-paired-mesh case this
# guards against.
_STALL_TRIAL_LIMIT = 2
# "Essentially no change" between consecutive rescale-phase trials --
# deliberately tiny and NOT tied to tol_pct (which is about being close
# to the TARGET, a different question): this only needs to catch a
# trial that moved by a genuinely negligible amount, not one that's
# merely still far from target but actually responding to pressure.
_STALL_DELTA_PCT = 1e-6


def estimate_pressure_for_target_stretch(positions, faces, edge_length,
                                          target_rms_pct=DEFAULT_TARGET_RMS_STRETCH_PCT,
                                          max_iterations=8,
                                          tol_pct=1.0, max_nfev_per_trial=5000, stop_event=None,
                                          gtol=CONVERGENCE_GTOL, rng=None,
                                          initial_pressure_guess=None,
                                          capture_frames=False, on_progress=None, edges=None,
                                          repulsion_strength=REPULSION_STRENGTH,
                                          repulsion_vertex_ids=None,
                                          repulsion_vertex_multipliers=None,
                                          rms_exclude_edges=None,
                                          pressure_exclude_faces=None):
    """positions/faces/edge_length/edges: as relax_once. `repulsion_strength`/
    `repulsion_vertex_ids`/`repulsion_vertex_multipliers`/`rms_exclude_edges`/
    `pressure_exclude_faces` are forwarded
    unchanged to every relax_once call this makes (every trial and the final top-up), same
    defaulting as relax_once's own (see that param's own comment there) -- note this means
    `target_rms_pct` below is calibrated against the EXCLUDED-edges-aside RMS too, so an open
    polygon's own stretch never drives the pressure search, only however the well-connected
    rest of the mesh
    responds. Finds a pressure whose relax_once result lands within `tol_pct` of
    `target_rms_pct` RMS
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
    see physics.md's Pressure calibration section) can land the search
    closer on the FIRST trial, needing fewer of the `max_iterations`
    budget. The search is BRACKET-then-BISECT rather than a single
    multiplicative rescale repeated blindly: as long as every trial so
    far has landed on the SAME side of the target (all under it, or all
    "insane" -- see _INSANE_STRETCH_FLOOR_PCT/_INSANE_STRETCH_TARGET_
    MULTIPLE, a mesh that's blown up rather than settled), it keeps
    rescaling by (target / achieved), clamped by _PRESSURE_RATIO_CLAMP.
    The MOMENT a trial lands on the OPPOSITE side from the best one seen
    so far, pressure is bracketed between them and every remaining trial
    bisects the bracket instead -- the only way to actually converge on
    an intermediate pressure once the mesh's own response to pressure
    turns out highly nonlinear near some critical value (a pure-rescale
    search can otherwise overshoot past the mesh's stable range and
    oscillate between the same two pressures forever without ever trying
    anything in between).

    Keeps whichever SANE trial got CLOSEST to the target rather than
    just the last one (an insane/diverged trial is never a candidate):
    the rescale step assumes more pressure means more stretch, which
    fails on at least one known net (three_squares.json actually
    stretches LESS as pressure rises) -- without keeping the best-so-far,
    a net where that assumption is wrong would escalate pressure every
    iteration chasing a target it's moving away from. Returns (pressure,
    new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    optimality, converged, pressure_found) -- the middle five exactly as
    relax_once's own return, from whichever trial this settled on (if
    every single trial was insane, the LAST one anyway, so this never
    raises for an irrecoverably bad target).

    `pressure_found` is True unless this gave up WITHOUT ever finding a
    usable pressure: either every trial was insane, or the mesh turned
    out completely UNRESPONSIVE to pressure at this level (see
    _STALL_TRIAL_LIMIT / physics.md's Pressure calibration section) --
    e.g. a ravioli-paired mesh whose pressure forces cancel EXACTLY at
    every pressure, so `converged` can still come back True (a real
    equilibrium was found) while `pressure_found` is False (no pressure
    could ever reach the target there).

    The WINNING trial, if it hasn't actually converged yet (it only ran
    `max_nfev_per_trial` steps, a search-time budget, not a real
    convergence criterion), is topped up with one further UNCAPPED
    `relax_once` call from wherever it left off, at the same pressure/
    gtol/rng, before returning -- this function always returns a trial
    that's either genuinely converged or hit relax_once's own
    MAX_UNBOUNDED_STEPS runaway cap. `steps_taken` in the return already
    includes this top-up's own steps. Skipped entirely if no sane trial
    was ever found, or `stop_event` was set.

    `capture_frames`, if True, adds an 8th return value: the WINNING
    trial's own positions every CONVERGENCE_CHECK_INTERVAL steps
    (relax_once's own on_progress cadence) as `(positions,
    cumulative_steps_taken)` pairs, from its starting `positions` (step
    0) through however far it got -- INCLUDING the convergence top-up
    above, so a caller replaying these sees one continuous run rather
    than a break at `max_nfev_per_trial`. Every trial captures its own
    frames as it runs (there's no way to know in advance which will end
    up best), but only the winning trial's list is kept. When False (the
    default), no frames are captured and the return shape is unchanged
    from before this param existed.

    `on_progress(cumulative_steps)`, if given, is called every
    CONVERGENCE_CHECK_INTERVAL steps of EVERY trial attempted (and of the
    convergence top-up), with the TOTAL number of relax_once steps
    actually computed so far across every trial -- including insane/
    thrown-away ones, since that's still real computation. Deliberately
    NOT reset to 0 between trials (so a live "Steps" counter never jumps
    backwards) -- monotonically increasing for the whole call, though NOT
    necessarily ending exactly at the final returned `steps_taken` (only
    the WINNING trial's own count), since the search can keep probing
    after a good-enough candidate if nothing satisfies `tol_pct` outright;
    a caller should snap its own displayed count to the real returned
    `steps_taken` once this function returns."""
    if initial_pressure_guess is not None:
        pressure = initial_pressure_guess
    else:
        total_area = _total_rest_area(faces, edge_length)
        pressure = _PRESSURE_AREA_PRODUCT_ESTIMATE * (target_rms_pct / 100.0) / total_area
    insane_ceiling = max(_INSANE_STRETCH_FLOOR_PCT, target_rms_pct * _INSANE_STRETCH_TARGET_MULTIPLE)
    best_error, best_pressure, best_result, best_frames = None, None, None, None
    # Once both are set, every remaining trial bisects between them:
    # lo_pressure is the LARGEST pressure so far confirmed sane and AT OR
    # UNDER target; hi_pressure is the SMALLEST pressure so far confirmed
    # either insane or over target.
    lo_pressure = hi_pressure = None
    result = None
    trial_frames = None
    cumulative_steps = 0
    pressure_found = True
    stalled_trials = 0
    prev_rescale_rms = None
    for _ in range(max_iterations):
        # `(positions, 0)` -- this trial's own starting point at step 0
        # (the same starting `positions` for every trial) -- is the very
        # first frame, so a replay of the winning trial's own frames
        # starts from where it actually did.
        trial_frames = [(positions, 0)] if capture_frames else None
        # `trial_base` (NOT `cumulative_steps` directly) is captured by
        # value via this default-arg trick, not by reference -- a plain
        # closure over the loop's own `cumulative_steps` would see
        # whatever it's grown to by the time the callback actually FIRES
        # (mid-relax_once, on a LATER iteration's value), not the value
        # at the moment THIS trial started.
        def _relax_progress(new_positions, steps_taken, *_rest, trial_base=cumulative_steps):
            if capture_frames:
                trial_frames.append((new_positions, steps_taken))
            if on_progress is not None:
                on_progress(trial_base + steps_taken)
        need_progress = capture_frames or on_progress is not None
        try:
            # A trial pressure far outside the sane range is EXPECTED to
            # blow the integrator up toward NaN/Inf before the
            # LinAlgError below catches it -- silence the resulting
            # float overflow warnings for this deliberately-tried bad
            # trial only; overflow/invalid warnings anywhere else in the
            # codebase (a real bug) still surface normally.
            with np.errstate(over='ignore', invalid='ignore'):
                result = relax_once(positions, faces, edge_length, pressure,
                                     max_nfev=max_nfev_per_trial, stop_event=stop_event, gtol=gtol,
                                     rng=rng, on_progress=_relax_progress if need_progress else None,
                                     edges=edges, repulsion_strength=repulsion_strength,
                                     repulsion_vertex_ids=repulsion_vertex_ids,
                                     repulsion_vertex_multipliers=repulsion_vertex_multipliers,
                                     rms_exclude_edges=rms_exclude_edges,
                                     pressure_exclude_faces=pressure_exclude_faces)
            _, trial_steps, _, rms_stretch, _, _ = result
        except np.linalg.LinAlgError:
            # A pathological trial (e.g. a pressure far outside any sane
            # range) can still blow the explicit integrator up into
            # NaN/Inf positions -- _remove_rigid_motion's Kabsch SVD then
            # can't converge on garbage input. Not worth crashing
            # calibration over: treated exactly
            # like an ordinary insane/blown-up trial instead (see
            # _DIVERGED_SENTINEL_STRETCH_PCT). Its own frames (if any)
            # are meaningless -- discarded rather than kept for replay.
            result = (positions, 0, _DIVERGED_SENTINEL_STRETCH_PCT,
                      _DIVERGED_SENTINEL_STRETCH_PCT, None, False)
            rms_stretch = _DIVERGED_SENTINEL_STRETCH_PCT
            trial_frames = None
            trial_steps = 0
        cumulative_steps += trial_steps
        sane = rms_stretch < insane_ceiling
        if sane:
            error = abs(rms_stretch - target_rms_pct)
            if best_error is None or error < best_error:
                best_error, best_pressure, best_result, best_frames = (
                    error, pressure, result, trial_frames)
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
            # Stall check FIRST, before rescaling further: if this
            # trial's own achieved stretch is essentially identical to
            # the previous rescale-phase trial's (see _STALL_DELTA_PCT's
            # own comment), rescaling pressure again is very unlikely to
            # help -- a genuinely responsive mesh's stretch moves
            # noticeably when pressure is rescaled by up to 5x. Two such
            # trials in a row (_STALL_TRIAL_LIMIT) means the mesh is
            # unresponsive to pressure at this level entirely (not just
            # slow), so give up rather than keep escalating pressure
            # without bound.
            if prev_rescale_rms is not None and abs(rms_stretch - prev_rescale_rms) < _STALL_DELTA_PCT:
                stalled_trials += 1
            else:
                stalled_trials = 0
            prev_rescale_rms = rms_stretch
            if stalled_trials >= _STALL_TRIAL_LIMIT:
                pressure_found = False
                break
            ratio = target_rms_pct / rms_stretch
            ratio = min(max(ratio, _PRESSURE_RATIO_CLAMP[0]), _PRESSURE_RATIO_CLAMP[1])
            pressure *= ratio
        else:
            # Degenerate reading (zero stretch) with nothing to bracket
            # against yet -- a single sane-at-zero trial isn't itself
            # proof of unresponsiveness (the very first guess could just
            # be too low), but there's no ratio to rescale by either;
            # _STALL_TRIAL_LIMIT only ever triggers above once a SECOND
            # such (near-)zero trial actually confirms it.
            break
    stopped = stop_event is not None and stop_event.is_set()
    if best_result is None:
        # Every trial was insane -- no sane candidate exists at all
        # within max_iterations; report the last attempt anyway rather
        # than raising, same as the original algorithm's own contract
        # (always returns SOMETHING derived from an actual relax_once
        # call). Not a real trial worth topping up to convergence.
        best_pressure, best_result, best_frames = pressure, result, trial_frames
        pressure_found = False
    else:
        new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged = best_result
        if not converged and not stopped:
            # Seeded with the SAME duplicate-first-frame convention
            # `trial_frames` uses above: `top_up_frames[0]` here is
            # `(new_positions, steps_taken)`, exactly `best_frames[-1]`,
            # so the `[1:]` slice below drops that genuine duplicate
            # rather than the top-up's own first real checkpoint (without
            # this seed, `[1:]` would silently drop the first real
            # checkpoint instead, leaving a gap in the replayed sequence).
            top_up_frames = [(new_positions, steps_taken)] if capture_frames else None

            def _topup_progress(p, s, *_rest):
                if capture_frames:
                    top_up_frames.append((p, steps_taken + s))
                if on_progress is not None:
                    on_progress(cumulative_steps + s)

            need_progress = capture_frames or on_progress is not None
            try:
                best_result = relax_once(new_positions, faces, edge_length, best_pressure,
                                          max_nfev=None, stop_event=stop_event, gtol=gtol,
                                          rng=rng,
                                          on_progress=_topup_progress if need_progress else None,
                                          edges=edges, repulsion_strength=repulsion_strength,
                                          repulsion_vertex_ids=repulsion_vertex_ids,
                                          repulsion_vertex_multipliers=repulsion_vertex_multipliers,
                                          rms_exclude_edges=rms_exclude_edges,
                                          pressure_exclude_faces=pressure_exclude_faces)
                (new_positions, top_up_steps, max_stretch, rms_stretch,
                 optimality, converged) = best_result
                best_result = (new_positions, steps_taken + top_up_steps, max_stretch,
                                rms_stretch, optimality, converged)
                if capture_frames:
                    # top_up_frames[0] (its own step-0 checkpoint) is the
                    # exact same position as best_frames[-1] -- merged in
                    # as one continuous run, not duplicated.
                    best_frames = best_frames + top_up_frames[1:]
            except np.linalg.LinAlgError:
                # The winning trial was itself sane -- a genuine
                # divergence during its OWN top-up would be surprising,
                # but not worth losing the already-good `best_result`
                # over; keep it exactly as the bracket search left it.
                pass
    new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged = best_result
    if capture_frames:
        return (best_pressure, new_positions, steps_taken, max_stretch, rms_stretch,
                optimality, converged, best_frames or [], pressure_found)
    return (best_pressure, new_positions, steps_taken, max_stretch, rms_stretch, optimality,
            converged, pressure_found)
