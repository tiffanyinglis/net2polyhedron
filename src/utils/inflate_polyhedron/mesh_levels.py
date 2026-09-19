"""Interactive, in-app nested mesh subdivision for inflate_polyhedron_app's
"Subdivide" button. Level 0 is a stretchy net's own (possibly
non-triangular) base faces; level 1 triangulates every face via a
centroid fan -- for an n>3 face, the same pattern utils.subdivisions.
polygon_subdivisions.SUBDIVISIONS uses; for an ALREADY-triangular face
too (2026-09-19, explicit user request, see _TRIANGLE_FAN's own comment
for why -- this is a LOCAL override, not a change to SUBDIVISIONS[3]
itself, which stays the identity for utils.subdivisions' own unrelated
2D-preview consumers). Each level after that quarters every triangle
from the level before, by connecting edge midpoints (the "triforce"
split), up to MAX_LEVEL.

Unlike utils.subdivisions (which builds a mesh from scratch at one
absolute resolution, purely as a 2D preview), this operates
INCREMENTALLY on the mesh's CURRENT 3D state -- every new point is a
straight interpolation of whatever the mesh's own nearby points already
are (a face's own centroid, or an edge's own midpoint), so any inflation
already done at one level carries over as the next level's starting
point instead of being discarded and re-solved from scratch. This is
also why subdividing is not itself a solve: it's just interpolation, and
each level's edge REST lengths (as opposed to positions) are derived
analytically from the ORIGINAL unit-edge-length flat reference geometry
(circumradius for a spoke, half-length for a quartered edge, the
midsegment theorem for a quartering's new internal edge) rather than
from the current (possibly already-stretched) 3D positions -- so the
"ideal" target shape a solver relaxes toward stays the same fixed target
as resolution increases, letting successive levels converge toward one
consistent answer rather than each level chasing whatever stretch
happened to exist at the moment it was created.
"""
import math

import numpy as np

from utils.subdivisions.polygon_subdivisions import SUBDIVISIONS, MAX_LEVEL

__all__ = ["MAX_LEVEL", "subdivide_once", "base_rest_lengths"]

# _fan_level_0_to_1's own LOCAL override for a 3-gon, in place of
# SUBDIVISIONS[3] (the identity -- utils.subdivisions.polygon_
# subdivisions' own, used by the unrelated 2D-preview app, deliberately
# left untouched: n=3 needs no centroid there since a triangle is
# already the finest mesh cell). Here, though, a PLAIN triangle face is
# otherwise perfectly rigid at the vertex level -- 3 points can only
# ever span one flat plane, so pressure has literally nothing to act on
# there until a LATER Subdivide's own quartering gives it real degrees
# of freedom (2026-09-19, explicit user request: "triangles should be
# subdivided too ... that way the face will be able to inflate a bit
# even at level 1"). Fanning it around its own centroid into 3
# sub-triangles -- same shape as SUBDIVISIONS[n] for n>3, just with n=3
# -- gives every triangular face the SAME spoke-based freedom to dome
# outward under pressure that a quad/pentagon/etc. face already had from
# Level 0/1 onward, rather than leaving it flat until Level 2.
_TRIANGLE_FAN = [(0, 1, "C"), (1, 2, "C"), (2, 0, "C")]


def base_rest_lengths(faces, edge_length):
    """faces: base vertex-loop faces; edge_length: uniform rest length.
    Returns {(a,b) sorted: edge_length} for every edge of `faces` -- the
    level-0 seed for subdivide_once's per-edge rest lengths. Safe to key
    by the plain vertex-id pair even when two DIFFERENT edges
    coincidentally share one (see _quarter_triangles' own docstring for
    when that happens): every rim edge gets the exact same `edge_length`
    value regardless, so a collision here never loses information --
    only _quarter_triangles' own TOPOLOGICAL merge decision (which
    genuinely different edges are the same edge) needs the extra
    disambiguation, via its own `rim_edge_key` param, not this dict."""
    edges = {tuple(sorted((face[i], face[(i + 1) % len(face)])))
             for face in faces for i in range(len(face))}
    return {e: edge_length for e in edges}


def _spoke_rest_length(n, edge_length):
    """Exact distance from a regular n-gon's own vertex to its centroid
    (circumradius), at the given edge length."""
    return edge_length / (2 * math.sin(math.pi / n))


def _fan_level_0_to_1(faces, positions, rest_lengths, face_of_fine, edge_length):
    """faces: base vertex-loop faces (level 0); positions: {vertex_id:
    np.ndarray(3,)}; rest_lengths: base_rest_lengths' result; face_of_fine:
    identity list at level 0. Triangulates every face via a centroid fan
    -- SUBDIVISIONS for n>3, or _TRIANGLE_FAN (this module's own local
    override, see its own comment for why) for an ALREADY-triangular
    face; a new centroid's position is its own face's corner mean, its
    spoke rest length the exact circumradius (_spoke_rest_length, valid
    for any n including 3) -- rim edges are untouched, so their rest
    lengths carry over unchanged. Returns (new_faces, new_positions,
    new_rest_lengths, new_face_of_fine)."""
    next_id = 1 + max(positions)
    new_positions = dict(positions)
    new_rest_lengths = dict(rest_lengths)
    new_faces = []
    new_face_of_fine = []
    for face_idx, face in enumerate(faces):
        n = len(face)
        if n not in SUBDIVISIONS:
            raise ValueError(f"no hardcoded subdivision for a {n}-gon")
        centroid_id = None
        spoke_len = _spoke_rest_length(n, edge_length)
        for tri in (_TRIANGLE_FAN if n == 3 else SUBDIVISIONS[n]):
            ids = []
            for ref in tri:
                if ref == "C":
                    if centroid_id is None:
                        centroid_id = next_id
                        next_id += 1
                        new_positions[centroid_id] = np.mean(
                            [positions[v] for v in face], axis=0)
                    ids.append(centroid_id)
                else:
                    ids.append(face[ref])
            new_faces.append(tuple(ids))
            new_face_of_fine.append(face_of_fine[face_idx])
            if centroid_id is not None:
                for v in ids:
                    if v != centroid_id:
                        key = tuple(sorted((v, centroid_id)))
                        new_rest_lengths.setdefault(key, spoke_len)
    return new_faces, new_positions, new_rest_lengths, new_face_of_fine


def _rim_edge_key_lookup(base_faces, face_edge_ids):
    """base_faces/face_edge_ids: the ORIGINAL level-0 faces and their own
    _face_edge_ids_from_shapes-style ids (a small int per face-edge,
    shared between two face-edges iff they're the same genuine mesh
    edge). Returns {base_face_idx: {frozenset({v, w}): ("orig", id)}} --
    for each base face, a lookup from its own edge's (unordered)
    vertex-id pair to the disambiguated key _quarter_triangles should
    use for that SPECIFIC edge, in place of the raw pair. Safe to build
    per-face: within one face's own edge list a vertex pair can't repeat
    (that would be a degenerate self-touching edge), so this lookup is
    unambiguous even though the SAME pair can also appear in an
    unrelated face (exactly the case this whole mechanism exists for --
    see _quarter_triangles' own docstring)."""
    lookup = {}
    for face_idx, face in enumerate(base_faces):
        n = len(face)
        lookup[face_idx] = {
            frozenset((face[i], face[(i + 1) % n])): ("orig", face_edge_ids[face_idx][i])
            for i in range(n)
        }
    return lookup


def _quarter_triangles(faces, positions, rest_lengths, face_of_fine, rim_edge_key=None):
    """faces: an ALL-TRIANGLE vertex-loop mesh (level >= 1); positions/
    rest_lengths/face_of_fine: that level's own state. Splits every
    triangle into 4 via edge midpoints, deduplicated so a shared edge's
    two triangles reuse the same new midpoint id. A midpoint's position
    is its edge's endpoint average; a split edge's rest length is half
    its parent's, and a quartering's 3 new internal edges are half the
    OPPOSITE original edge's rest length (midsegment theorem).

    rim_edge_key: optional {base_face_idx: {frozenset({v,w}): key}} (see
    _rim_edge_key_lookup) -- when given, used INSTEAD OF the plain
    vertex-id pair to decide whether two of a triangle's edges are the
    SAME genuine edge (so their midpoint should be reused), for whichever
    edges are still UNSPLIT base-mesh rim edges (both endpoints original
    base vertex ids, still present as-is at this triangle's own
    face_of_fine base face). This is a TOPOLOGICAL identity decision
    only -- rest_lengths itself stays keyed by the plain vertex-id pair
    throughout (base_rest_lengths' own value is uniform per rim edge
    regardless of which logical instance is asking, so a plain-pair read
    is always safe/correct here even when this dedup key says two edges
    are actually different). Without this, two DIFFERENT rim edges that
    happen to share a vertex-id pair (two faces glued along multiple
    edges merges unrelated corners pairwise, so their remaining FREE
    edges can coincidentally land on the same pair -- see
    interactive_builder_app._edges_from_shapes' own docstring) would
    wrongly reuse one midpoint, welding two unconnected boundary edges
    together. A triangle edge touching a centroid or an already-made
    midpoint is never looked up this way (rim_edge_key has no entry for
    it, by construction) -- those vertex-id pairs are already globally
    unique, so the plain pair is used directly as its own dedup key too,
    same as when rim_edge_key is None entirely (an older file, or one
    with no such ambiguity to begin with). Returns (new_faces,
    new_positions, new_rest_lengths, new_face_of_fine)."""
    next_id = 1 + max(positions)
    new_positions = dict(positions)
    new_rest_lengths = dict(rest_lengths)
    midpoint_of = {}

    def dedup_key(face_idx, u, v):
        if rim_edge_key is not None:
            key = rim_edge_key.get(face_of_fine[face_idx], {}).get(frozenset((u, v)))
            if key is not None:
                return key
        return tuple(sorted((u, v)))

    def get_or_make_midpoint(u, v, key):
        nonlocal next_id
        mid = midpoint_of.get(key)
        if mid is not None:
            return mid
        mid = next_id
        next_id += 1
        new_positions[mid] = (positions[u] + positions[v]) / 2
        plain_key = tuple(sorted((u, v)))
        half = rest_lengths[plain_key] / 2
        new_rest_lengths.pop(plain_key, None)  # the parent edge no longer exists, split in two
        new_rest_lengths[tuple(sorted((u, mid)))] = half
        new_rest_lengths[tuple(sorted((mid, v)))] = half
        midpoint_of[key] = mid
        return mid

    new_faces = []
    new_face_of_fine = []
    for face_idx, (a, b, c) in enumerate(faces):
        mab = get_or_make_midpoint(a, b, dedup_key(face_idx, a, b))
        mbc = get_or_make_midpoint(b, c, dedup_key(face_idx, b, c))
        mca = get_or_make_midpoint(c, a, dedup_key(face_idx, c, a))
        rest_ab = rest_lengths[tuple(sorted((a, b)))]
        rest_bc = rest_lengths[tuple(sorted((b, c)))]
        rest_ca = rest_lengths[tuple(sorted((c, a)))]
        new_rest_lengths[tuple(sorted((mab, mbc)))] = rest_ca / 2
        new_rest_lengths[tuple(sorted((mbc, mca)))] = rest_ab / 2
        new_rest_lengths[tuple(sorted((mca, mab)))] = rest_bc / 2
        new_faces += [(a, mab, mca), (mab, b, mbc), (mca, mbc, c), (mab, mbc, mca)]
        new_face_of_fine += [face_of_fine[face_idx]] * 4
    return new_faces, new_positions, new_rest_lengths, new_face_of_fine


def subdivide_once(faces, positions, edge_length, face_of_fine, level,
                    base_faces=None, face_edge_ids=None):
    """faces/positions: the CURRENT level's mesh; edge_length: scalar
    (level 0) or {(a,b): length} dict (level >= 1) -- same dual form
    stretchy_mesh.relax_once/solve_wireframe accept; face_of_fine: each
    face's own base-face index (identity list at level 0); level: the
    CURRENT level (0..MAX_LEVEL-1); base_faces/face_edge_ids: the
    ORIGINAL level-0 faces and their own optional per-face-edge
    disambiguation ids (a stretchy-mesh file's own "face_edge_ids" --
    see interactive_builder_app._face_edge_ids_from_shapes' docstring
    and _quarter_triangles' own docstring for why this matters). Pass
    the SAME `base_faces`/`face_edge_ids` on every call for a given net,
    not just the level==0 one: the ambiguity they resolve only ever
    matters for a still-UNSPLIT base rim edge, which can still be
    present as-is in the mesh handed to the level==1 (Level 1->2) call;
    by level==2 every edge already includes a freshly-minted midpoint or
    centroid id (always unambiguous on its own), so passing them to a
    later call is harmless, not just unnecessary. Returns (new_faces,
    new_positions, new_edge_length, new_face_of_fine) one level up --
    new_edge_length is always a dict from here on. Raises ValueError if
    level is already at MAX_LEVEL."""
    if level >= MAX_LEVEL:
        raise ValueError(f"already at the maximum level ({MAX_LEVEL})")
    if level == 0:
        rest_lengths = base_rest_lengths(faces, edge_length)
        return _fan_level_0_to_1(faces, positions, rest_lengths, face_of_fine, edge_length)
    rim_edge_key = (_rim_edge_key_lookup(base_faces, face_edge_ids)
                    if base_faces is not None and face_edge_ids is not None else None)
    return _quarter_triangles(faces, positions, edge_length, face_of_fine, rim_edge_key)
