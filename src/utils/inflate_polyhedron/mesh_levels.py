"""Interactive, in-app nested mesh subdivision for inflate_polyhedron_app's
"Subdivide" button. Level 0 is a stretchy net's own (possibly
non-triangular) base faces; level 1 triangulates every face via the same
centroid-fan pattern utils.subdivisions.polygon_subdivisions.SUBDIVISIONS
uses (a triangular face is left unchanged, matching SUBDIVISIONS[3]);
each level after that quarters every triangle from the level before, by
connecting edge midpoints (the "triforce" split), up to MAX_LEVEL.

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


def base_rest_lengths(faces, edge_length):
    """faces: base vertex-loop faces; edge_length: uniform rest length.
    Returns {(a,b) sorted: edge_length} for every edge of `faces` -- the
    level-0 seed for subdivide_once's per-edge rest lengths."""
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
    identity list at level 0. Triangulates every face via SUBDIVISIONS
    (unchanged for an already-triangular face); a new centroid's position
    is its own face's corner mean, its spoke rest length the exact
    circumradius (_spoke_rest_length) -- rim edges are untouched, so their
    rest lengths carry over unchanged. Returns (new_faces, new_positions,
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
        spoke_len = _spoke_rest_length(n, edge_length) if n > 3 else None
        for tri in SUBDIVISIONS[n]:
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


def _quarter_triangles(faces, positions, rest_lengths, face_of_fine):
    """faces: an ALL-TRIANGLE vertex-loop mesh (level >= 1); positions/
    rest_lengths/face_of_fine: that level's own state. Splits every
    triangle into 4 via edge midpoints, deduplicated so a shared edge's
    two triangles reuse the same new midpoint id. A midpoint's position
    is its edge's endpoint average; a split edge's rest length is half
    its parent's, and a quartering's 3 new internal edges are half the
    OPPOSITE original edge's rest length (midsegment theorem). Returns
    (new_faces, new_positions, new_rest_lengths, new_face_of_fine)."""
    next_id = 1 + max(positions)
    new_positions = dict(positions)
    new_rest_lengths = dict(rest_lengths)
    midpoint_of = {}

    def get_or_make_midpoint(u, v):
        nonlocal next_id
        key = tuple(sorted((u, v)))
        mid = midpoint_of.get(key)
        if mid is not None:
            return mid
        mid = next_id
        next_id += 1
        new_positions[mid] = (positions[u] + positions[v]) / 2
        half = rest_lengths[key] / 2
        new_rest_lengths.pop(key, None)  # the parent edge no longer exists, split in two
        new_rest_lengths[tuple(sorted((u, mid)))] = half
        new_rest_lengths[tuple(sorted((mid, v)))] = half
        midpoint_of[key] = mid
        return mid

    new_faces = []
    new_face_of_fine = []
    for face_idx, (a, b, c) in enumerate(faces):
        mab = get_or_make_midpoint(a, b)
        mbc = get_or_make_midpoint(b, c)
        mca = get_or_make_midpoint(c, a)
        rest_ab = rest_lengths[tuple(sorted((a, b)))]
        rest_bc = rest_lengths[tuple(sorted((b, c)))]
        rest_ca = rest_lengths[tuple(sorted((c, a)))]
        new_rest_lengths[tuple(sorted((mab, mbc)))] = rest_ca / 2
        new_rest_lengths[tuple(sorted((mbc, mca)))] = rest_ab / 2
        new_rest_lengths[tuple(sorted((mca, mab)))] = rest_bc / 2
        new_faces += [(a, mab, mca), (mab, b, mbc), (mca, mbc, c), (mab, mbc, mca)]
        new_face_of_fine += [face_of_fine[face_idx]] * 4
    return new_faces, new_positions, new_rest_lengths, new_face_of_fine


def subdivide_once(faces, positions, edge_length, face_of_fine, level):
    """faces/positions: the CURRENT level's mesh; edge_length: scalar
    (level 0) or {(a,b): length} dict (level >= 1) -- same dual form
    stretchy_mesh.relax_once/solve_wireframe accept; face_of_fine: each
    face's own base-face index (identity list at level 0); level: the
    CURRENT level (0..MAX_LEVEL-1). Returns (new_faces, new_positions,
    new_edge_length, new_face_of_fine) one level up -- new_edge_length is
    always a dict from here on. Raises ValueError if level is already at
    MAX_LEVEL."""
    if level >= MAX_LEVEL:
        raise ValueError(f"already at the maximum level ({MAX_LEVEL})")
    if level == 0:
        rest_lengths = base_rest_lengths(faces, edge_length)
        return _fan_level_0_to_1(faces, positions, rest_lengths, face_of_fine, edge_length)
    return _quarter_triangles(faces, positions, edge_length, face_of_fine)
