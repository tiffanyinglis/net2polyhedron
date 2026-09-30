"""Loader + solver for STRETCHY meshes: a polyhedron-like net, closed or
OPEN, whose faces are combinatorially valid (every edge shared by AT MOST
two faces, in opposite directions -- see WINDING CONVENTION below) but
that cannot necessarily be realized with perfectly RIGID, FLAT faces --
e.g. two faces glued together along more than one shared edge, which
forces them into the same plane if both stay flat and rigid.

Rather than a hinge-tree-plus-fold-angles model (which assumes every face
stays flat), a stretchy mesh is specified directly as VERTEX loops -- the
standard "indexed face set" representation (like an .obj file): shared
vertices ARE the adjacency, so faces sharing multiple edges need no
special-casing. JSON shape:

    {
      "faces": [
        [0, 1, 2, 3, 4],
        [3, 2, 1, 0, 5],
        [0, 4, 3, 5]
      ]
    }

No "name" field -- a net's own display name is always its FILENAME (see
load_stretchy_mesh), not anything stored inside the file, so a copy/rename
never leaves a stale name behind. A legacy file that still carries one is
simply ignored.

WINDING CONVENTION: each face is a loop of vertex ids (ints, 0..N-1,
referenced -- not separately declared; N is inferred as 1 + the largest
id used) listed COUNTERCLOCKWISE as seen from OUTSIDE the finished solid
(or, for a net deliberately left OPEN -- a bowl, a patch, a box with no
lid -- outside whichever side was chosen; the winding is what encodes
that choice, not a separate flag). For any edge (v, w) shared by two
faces, one face's loop contains it as v -> w and the other's as w -> v --
never the same direction twice. An edge referenced by only ONE face is a
free BOUNDARY edge -- valid, not an error; this is what lets a net stay
open rather than requiring a closed 2-manifold. load_stretchy_mesh rejects
a directed edge that appears more than once, UNLESS the file carries its
own "face_edge_ids" (see mesh_edges and interactive_builder_app's net
JSON import/export): vertex dedup can legitimately merge enough OTHER
corners together that two unrelated edges end up sharing a directed
vertex pair by coincidence (each still shared by at most its own 2 faces)
-- "face_edge_ids" is what tells that apart from an actual authoring
mistake.

That check alone can't catch every mistake: flipping EVERY face at once
(a full mirror image) is just as valid a loop structure as the original,
and pre_inflation_relaxer.relax_initial_configuration's random-start
relax has no GLOBAL notion of "outward", so it can land inside-out or
genuinely mixed. See _orientation_signs/_is_orientation_consistent for
how a caller can check this.

Pipeline (used by inflate_polyhedron_app): a raw loaded net is first
passed through self_join_triangulator (splits any self-joined face --
see that module's own docstring); random_initial_positions then gives it
a starting point that isn't a meaningful embedding yet;
pre_inflation_relaxer.relax_initial_configuration pulls that into a
well-separated 3D shape using pure spring forces (no pressure); relax_once
(here) then takes over for interactive, pressure-based "inflation" --
letting edges stretch a little and faces bend to round the shape out,
exactly what makes an otherwise-rigid-impossible net realizable at all,
and what puffs an ordinary closed solid into a rounded, convex,
plushie-like shape. multi_trial_inflater.estimate_pressure_for_target_
stretch drives relax_once across several pressure trials to hit a target
stretch %.

This module holds the loader, mesh geometry helpers (volume/area/
orientation), the shared low-level force primitives (_relax_force,
repulsion_force, _edge_setup, _explicit_relax_loop), and relax_once
itself. Four related responsibilities live in their own sibling modules
instead: self_join_triangulator (self-joined-face splitting at load
time), pre_inflation_relaxer (Level 0's relax_initial_configuration),
multi_trial_inflater (pressure calibration, estimate_pressure_for_
target_stretch), convergence_checker (the periodic stopping check
_explicit_relax_loop uses), and mesh_stretch_checker (turning solved
positions into max/RMS stretch %). Each of those depends on THIS module
for its own shared primitives, not the other way around -- so importing
stretchy_mesh alone never pulls the others in.

Full scientific writeup: docs/algorithm.md; current-state/tuning summary:
.claude/skills/net-fold-project/physics.md. Keep all three in sync when
changing the physics.

Design notes:
- **relax_once is a genuine force balance, walked step by step -- no
  volume anywhere** (_relax_force): each edge is a HARDENING spring; each
  face applies a real outward force, `pressure * area * normal`, split
  across its own vertices. Each call moves every vertex a small step
  along its own net force (explicit relaxation), not a least_squares
  solve: a Newton-style solver re-linearizes the whole mesh and can jump
  past the physically-reachable equilibrium to a distant, spurious one
  (see algorithm.md sec 4.2). Direction vectors use _safe_unit_vectors
  (a fixed fallback at an exact zero vector) instead of a naive division.
- **A hardening (linear + cubic) spring, not pure Hooke's-law linear.**
  Pressure's quadratic area growth defeats a plain linear spring past
  some critical value; a pure-cubic replacement settles as a slow power
  law rather than exponentially near rest. See algorithm.md sec 4.1/4.4
  and physics.md's Force model section.
- **pre_inflation_relaxer.relax_initial_configuration (Level 0's "Relax"
  step) uses a PLAIN LINEAR spring, not the hardening one** -- no
  pressure there for the hardening term to guard against, and plain
  linear settles faster near rest.
"""
import collections
import json
import os

import numpy as np

from ..geometry.polyhedron import Polyhedron
from .convergence_checker import (
    CONVERGENCE_GTOL, CONVERGENCE_CHECK_INTERVAL, check_convergence, remove_rigid_motion,
)
from .mesh_stretch_checker import positions_and_stretch

EDGE_LENGTH = 1.0


def _face_edges(face):
    """The directed edges (v, w) of one CCW face loop."""
    k = len(face)
    return [(face[i], face[(i + 1) % k]) for i in range(k)]


def load_stretchy_mesh(path):
    """path: a vertex-loop stretchy-mesh .json/.poly (see module
    docstring). Returns (faces, name), faces a list of vertex-id lists.
    `name` is always `path`'s own basename (extension stripped), never
    read from a "name" field inside the file (so a copy/rename can never
    leave a stale name behind). Raises ValueError if any directed edge
    appears more than once -- the mesh need NOT be closed: an edge with
    no reverse partner is a valid, free boundary edge. See
    load_stretchy_mesh_edges for a file's own optional explicit
    "edges"/"face_edge_ids" fields."""
    faces, _spec = _load_stretchy_mesh_spec(path)
    name = os.path.splitext(os.path.basename(path))[0]
    return faces, name


def load_stretchy_mesh_edges(path):
    """path: as load_stretchy_mesh. Returns (edges, face_edge_ids): the
    file's own explicit "edges" list (see mesh_edges for why this can't
    always be safely re-derived from `faces` alone) as (a, b) tuples if
    present, else None; and its own explicit "face_edge_ids" list (see
    mesh_levels.subdivide_once) if present, else None."""
    _faces, spec = _load_stretchy_mesh_spec(path)
    raw_edges = spec.get("edges")
    edges = [tuple(e) for e in raw_edges] if raw_edges else None
    face_edge_ids = spec.get("face_edge_ids") or None
    return edges, face_edge_ids


def _load_stretchy_mesh_spec(path):
    """Shared parse+validate behind load_stretchy_mesh/
    load_stretchy_mesh_edges -- reads and winding-validates `path` once,
    returning (faces, spec) so each public function only picks its own
    fields out of the same parsed JSON.

    The "no directed edge appears more than once" check is SKIPPED when
    the file has its own "face_edge_ids" field -- that field only comes
    from interactive_builder_app._face_edge_ids_from_shapes (written on
    every Save), meaning this net already passed
    _validate_shapes_connections there, so a directed-edge collision is
    known to be a legitimate coincidence (vertex dedup merging unrelated
    corners), not an authoring mistake. A file with no "face_edge_ids"
    has no such guarantee, so it keeps the strict check as a sanity/typo
    guard."""
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
    list of (a, b) with a < b. If `edges` is given (a file's own explicit
    edge list, e.g. from load_stretchy_mesh or
    interactive_builder_app._edges_from_shapes), it's returned as-is
    (each pair sorted, duplicates PRESERVED) instead of being re-derived
    from `faces`. Re-deriving purely from `faces`' shared vertex ids is
    ambiguous once vertex dedup has merged unrelated corners onto the
    same ids: two independent boundary edges can coincidentally land on
    the same vertex-id pair, which a plain `set` (the fallback, for a
    file with no explicit `edges`, where this ambiguity can't arise)
    can't tell apart from a genuinely shared edge."""
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

    `pressure_exclude_faces`, if given, is a sequence of booleans the same
    length as `faces` -- any face where it's True is left out of every
    group entirely, so _relax_force's own pressure term never applies to
    it (an "open" wedge triangle, one whose own outer edge isn't glued to
    another polygon, doesn't experience inflation forces). That face
    still exists normally everywhere else (edges/stretch/repulsion/
    convergence) -- this is the only place its exclusion applies."""
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
    fallback at an exact zero vector -- avoids a naive `v/norm(v)`
    division silently shrinking toward the zero vector as `norm(v)`
    shrinks toward it, which would give a genuinely-zero *force* a
    magnitude that was never actually zero."""
    norms = np.linalg.norm(vecs, axis=1)
    ok = norms > 1e-9
    unit = np.zeros_like(vecs)
    unit[ok] = vecs[ok] / norms[ok, None]
    unit[~ok] = (1.0, 0.0, 0.0)
    return unit


# The cubic term's own coefficient in _relax_force's hardening spring
# (`stretch + HARDENING_CUBIC_COEFFICIENT * stretch**3`) -- see
# physics.md's Force model section for the current value/rationale.
HARDENING_CUBIC_COEFFICIENT = 0.5


def _relax_force(pts, edge_ai, edge_bi, all_face_groups, edge_length, pressure=0.0):
    """relax_once's per-step force: a genuine mechanical force balance.
    Each edge is a HARDENING spring (`stretch +
    HARDENING_CUBIC_COEFFICIENT * stretch**3` -- see module docstring's
    Design notes); each face applies a real outward pressure force,
    `pressure * area * outward_normal` -- area and normal computed
    together straight from its own vertex loop via
    `0.5 * sum_i cross(p_i, p_{i+1})` (Newell's method) -- split evenly
    across its own vertices. Returns the (N,3) net force on every vertex;
    relax_once walks a small step along it."""
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


# All-pairs repulsion, used by every relax force -- inverse-square in distance, like
# electrostatic repulsion in a force-directed graph layout, between EVERY pair of vertices, not
# just edge-connected ones. At Level 0 (relax_initial_configuration's own _spring_only_force)
# this keeps the initial random cloud from leaving vertices piled up near each other before the
# spring network gets a chance to spread them into a well-separated shape; at Level 1+
# (_relax_force, via relax_once's own `repulsion_strength` param) it's an extra separating force
# alongside real per-face pressure -- strong enough to measurably shift the pressure/stretch
# equilibrium, so a caller passing a non-default strength should expect to recalibrate pressure
# against it. REPULSION_STRENGTH is small relative to the spring's own stiffness (its restoring
# force at exactly 1 edge_length of stretch is 1.0), so it only meaningfully pushes vertices that
# are already close together. MIN_REPULSION_DISTANCE floors the distance term so two vertices
# that land almost exactly on top of each other don't blow the force up toward infinity.
REPULSION_STRENGTH = 0.015
MIN_REPULSION_DISTANCE = 0.05


def repulsion_force(pts, strength=REPULSION_STRENGTH, indices=None, vertex_multipliers=None):
    """All-pairs inverse-square repulsion -- see REPULSION_STRENGTH's own
    comment. O(k^2) in vertex count, where k is len(indices) if given,
    else all of `pts` -- fine at Level 0/1's own (small, unsubdivided)
    scale, too slow run every relax step against Level 2/3's own much
    larger vertex count. `indices` (array positions into `pts`, not
    vertex ids -- see relax_once's own `repulsion_vertex_ids` for the
    vertex-id-keyed version a caller actually passes), when given,
    restricts BOTH which vertices repel each other AND which vertices
    receive any resulting force to just that subset -- every vertex
    outside it gets a zero contribution here, left entirely to
    springs/pressure.

    `vertex_multipliers`, if given, is an array the same length as
    `indices` (or `pts` if `indices` is None) -- each vertex's OWN [0, 1]
    scale on `strength` (used to weaken repulsion at "closed" vertices
    while "open" ones stay at full strength). The pairwise force between
    i and j uses the PRODUCT of their own two multipliers (like a product
    of electrostatic charges). None (the default) means every vertex is
    at multiplier 1, identical to `strength` alone."""
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
    """pts: (N,3); all_face_groups: as _face_index_groups' own return
    (every face's vertex indices INTO pts, grouped by side count) -- same
    structure _relax_force's own pressure term uses. Returns (N,3): each
    vertex's own outward direction as the NORMALIZED SUM of its incident
    faces' unit normals, each face weighted equally (not by area) --
    same definition as inflate_polyhedron_app's own _vertex_normals ("Show
    vertex normals"). Each face's own unit normal is its `area *
    outward_normal` Newell's-method vector, normalized -- "outward" here
    means whatever the mesh's own face WINDING implies, the same
    convention _relax_force's pressure term and _orientation_signs both
    use -- so it's well-defined even for a currently-folded embedding.

    A vertex touching no non-degenerate face, or whose incident face
    normals cancel exactly, gets the GENUINE zero vector here --
    deliberately NOT _safe_unit_vectors' own (1,0,0) fallback: a zero row
    here means "no known outward direction", and a zero dot product
    against it leaves a repulsion force untouched rather than risking
    suppressing a legitimate force via an arbitrary fallback axis."""
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


# Explicit relaxation step size: the vertex with the largest net force
# moves this fraction of the mesh's own rest edge length in one
# iteration; every other vertex moves proportionally less (force is
# normalized by its own max each step) -- keeps steps small and stable (a
# real physical walk, not a linearized jump that can overshoot the
# reachable equilibrium -- see module docstring's Design notes). Scaled
# by the mesh's own rest edge length (`scale`), not a fixed absolute cap,
# since `scale` drops at each Subdivide level. See physics.md's Force
# model / Defaults sections for the current value.
STEP_MAX_MULTIPLIER = 0.05

# Hard cap on iterations when max_nfev=None (run-to-convergence): explicit
# steps have no scipy-style internal budget of their own, so this stands
# in for one.
MAX_UNBOUNDED_STEPS = 200_000

# Escaping a genuine local-minimum "dimple": a pure explicit gradient-
# style walk has no momentum to coast through a shallow energy barrier
# with, so once a vertex settles into one it just oscillates around it
# forever. `rng` (optional, `None` by default -- fully deterministic)
# opts a caller into an occasional random perturbation instead: if
# `max_force` hasn't dropped to at most KICK_STALL_RATIO of what it was
# KICK_WINDOW steps ago, every vertex gets nudged by Gaussian noise
# scaled by KICK_MAGNITUDE_FRACTION * `scale`, weighted by that vertex's
# own current force relative to the worst one. inflate_polyhedron_app
# currently passes rng=None for Relax/Inflate -- see physics.md's
# Convergence section.
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


def _explicit_relax_loop(pts, scale, force_fn,
                          max_nfev, stop_event, gtol, rng=None,
                          step_max_multiplier=None, on_check=None):
    """Shared explicit-relaxation driver for relax_once and
    relax_initial_configuration -- the only things that vary between them
    are the force itself (`force_fn(pts) -> (N,3)`) and each force law's
    own safe step size (`step_max_multiplier`, defaulting to the module's
    own STEP_MAX_MULTIPLIER; relax_initial_configuration passes its own
    LEVEL0_STEP_MAX_MULTIPLIER).

    Repeatedly nudges `pts` a small step along `force_fn(pts)`; if `rng`
    is given and the worst vertex's force has been OSCILLATING rather
    than genuinely dropping (see KICK_WINDOW's own comment), nudges every
    vertex by a small random perturbation weighted toward whichever one
    is actually stuck -- until EITHER the worst vertex's own displacement
    over the last CONVERGENCE_CHECK_INTERVAL steps drops below
    `CONVERGENCE_CHECK_INTERVAL * gtol` (checked only once every
    CONVERGENCE_CHECK_INTERVAL steps -- see physics.md's Convergence
    section), or `max_nfev`/`stop_event` cuts it off first.

    Whatever rigid rotation/translation the raw per-step updates
    introduce (convergence_checker.remove_rigid_motion) is only computed
    ONCE per CONVERGENCE_CHECK_INTERVAL-step block, immediately before
    that block's convergence check -- still exactly equivalent to
    correcting every step, since every force here depends only on
    relative vertex geometry (translation-invariant, rotation-
    equivariant), so no edge length or face shape the physics computes
    ever depends on what rigid frame the steps in between happened to sit
    in.

    Aligned against `pts_at_run_start` -- this call's own STARTING
    positions, captured once and never updated -- rather than a rolling
    reference (see remove_rigid_motion's own docstring for why: a
    rolling reference only cancels drift WITHIN each block, doing nothing
    to stop a genuine per-block rotational component from compounding
    across many blocks). `pts_at_last_check` (a separate, still-rolling
    reference) remains for the CONVERGENCE comparison itself
    (`block_displacement`) -- that's inherently a block-to-block question,
    unrelated to which frame the rigid-motion removal targets.

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
        # Checked only once every CONVERGENCE_CHECK_INTERVAL steps, comparing the worst vertex's
        # own displacement ACCUMULATED over that whole interval (against pts_at_last_check, the
        # position at the START of the interval) to CONVERGENCE_CHECK_INTERVAL * gtol -- so a
        # genuine multi-step drift is caught even if no single step's own displacement would
        # trip an every-step check. Rigid rotation/translation is stripped out HERE, once per
        # block, against the FIXED pts_at_run_start (see this function's own docstring).
        if steps_taken % CONVERGENCE_CHECK_INTERVAL == 0:
            pts, optimality, converged = check_convergence(
                pts, pts_at_run_start, pts_at_last_check, CONVERGENCE_CHECK_INTERVAL, gtol)
            pts_at_last_check = pts.copy()
            if on_check is not None:
                on_check(pts, steps_taken, optimality, converged)
            if converged:
                break
    # A run that stops mid-block (stop_event, or step_cap not a multiple of
    # CONVERGENCE_CHECK_INTERVAL) never hit the alignment above for its own trailing partial
    # block -- align once more here so callers never see a `pts` still carrying uncorrected
    # rigid drift.
    if steps_taken % CONVERGENCE_CHECK_INTERVAL != 0:
        pts = remove_rigid_motion(pts_at_run_start, pts)
    return pts, steps_taken, optimality, converged


def relax_once(positions, faces, edge_length, pressure=0.0,
                max_nfev=None, stop_event=None,
                gtol=CONVERGENCE_GTOL, rng=None, on_progress=None, edges=None,
                repulsion_strength=REPULSION_STRENGTH, repulsion_vertex_ids=None,
                repulsion_vertex_multipliers=None,
                rms_exclude_edges=None, pressure_exclude_faces=None):
    """positions: {vertex_id: [x,y,z]} starting point; faces/edge_length/
    edges: as _edge_setup. Runs ONE relaxation pass at a fixed `pressure`
    -- no automatic ramp; call again with the result to keep steering it.
    Each iteration moves every vertex a small step along its own net
    force from _relax_force PLUS repulsion_force at `repulsion_strength`
    (see repulsion_force's own comment for why the default is weak
    enough not to fight the spring/pressure forces at ordinary spacing).

    `repulsion_vertex_ids`, if given, restricts repulsion to just that
    subset of `positions`' own vertex ids (translated to repulsion_
    force's own array-index space here) -- every OTHER vertex gets zero
    repulsion, left entirely to springs/pressure. None (the default)
    repels every vertex, O(n^2) in the mesh's own current vertex count --
    fine at Level 0/1's scale, too slow to run every relax step at
    Level 2/3's own larger vertex count in practice; a caller can instead
    pass a fixed, small vertex-id subset (e.g. Level 0's own vertices) at
    every level to keep the repulsion population size constant.
    `repulsion_vertex_multipliers`: a {vertex_id: multiplier} dict (only
    needs entries for vertices NOT at the default of 1), forwarded to
    repulsion_force's own `vertex_multipliers`.

    `pressure_exclude_faces`: as _face_index_groups -- those faces get NO
    pressure force at all (still fully present for springs/repulsion/
    edges/convergence). `rms_exclude_edges`: as mesh_stretch_checker.
    positions_and_stretch (excluded from every reported/checked
    rms_stretch_pct, never affects
    max_stretch_pct, the convergence check, or the forces actually
    driving the relaxation).

    `max_nfev` caps the number of steps; None runs until convergence
    (capped at MAX_UNBOUNDED_STEPS as a runaway guard), via the worst
    vertex's own displacement dropping below `gtol` (see
    _explicit_relax_loop / physics.md's Convergence section for the
    current check cadence). `stop_event` (a threading.Event), if given,
    is checked before each step and aborts at the next one, returning
    whatever position was last reached. `rng` (a numpy Generator, e.g.
    `np.random.default_rng()`), if given, opts into an occasional random
    perturbation when a vertex is stuck oscillating -- see KICK_WINDOW's
    own comment; `None` (the default) is fully deterministic.

    `on_progress(new_positions, steps_taken, max_stretch_pct,
    rms_stretch_pct, optimality, converged)`, if given, is called every
    CONVERGENCE_CHECK_INTERVAL steps (the same cadence the stopping
    condition itself is checked at) with exactly this function's own
    return shape.

    Returns (new_positions, steps_taken, max_stretch_pct, rms_stretch_pct,
    optimality, converged). `optimality` is exactly the quantity compared
    against `gtol` above, None if stopped before a single step ran.
    `converged` is True only if one of the two criteria above (not the
    step cap or a stop request) is what stopped it."""
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
        check_positions, check_max_stretch, check_rms_stretch = positions_and_stretch(
            check_pts, vertex_ids, edges, length_arr, rms_exclude_edges)
        on_progress(check_positions, check_steps, check_max_stretch, check_rms_stretch,
                    check_optimality, check_converged)

    pts, steps_taken, optimality, converged = _explicit_relax_loop(
        pts0, scale, force_fn, max_nfev, stop_event, gtol, rng,
        step_max_multiplier=STEP_MAX_MULTIPLIER,
        on_check=on_check if on_progress is not None else None)
    new_positions, max_stretch, rms_stretch = positions_and_stretch(
        pts, vertex_ids, edges, length_arr, rms_exclude_edges)
    return new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged


# In edge_length units -- big enough that a mesh of a few dozen vertices starts well spread out
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

