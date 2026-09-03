"""Reusable 2D geometry helpers for regular polygons.

All faces are regular polygons sharing a common edge length, so any two
faces' edges can be glued to each other exactly.
"""
import numpy as np

EDGE_LENGTH = 1.0


def regular_polygon_vertices(k, edge_length=EDGE_LENGTH):
    """CCW vertices of a regular k-gon, centered at the origin, with edge 0
    running from vertex 0 to vertex 1."""
    R = edge_length / (2 * np.sin(np.pi / k))
    start = -np.pi / 2 - np.pi / k
    angles = start + 2 * np.pi * np.arange(k) / k
    return [np.array([R * np.cos(a), R * np.sin(a)]) for a in angles]


def rigid_transform_2d(local_a, local_b, target_a, target_b):
    """Rotation+translation (no reflection, no scale) mapping
    local_a -> target_a and local_b -> target_b. Requires
    |local_b - local_a| == |target_b - target_a|."""
    lv = local_b - local_a
    tv = target_b - target_a
    theta = np.arctan2(tv[1], tv[0]) - np.arctan2(lv[1], lv[0])
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, -s], [s, c]])
    t = target_a - R @ local_a
    return R, t


def apply_rigid(points, R, t):
    return [R @ p + t for p in points]


def attach_polygon(k, local_edge_idx, target_p1, target_p2, edge_length=EDGE_LENGTH):
    """A regular k-gon whose local edge (local_edge_idx -> local_edge_idx+1)
    is placed onto the segment target_p1 -> target_p2."""
    verts = regular_polygon_vertices(k, edge_length)
    j = local_edge_idx
    a, b = verts[j], verts[(j + 1) % k]
    R, t = rigid_transform_2d(a, b, target_p1, target_p2)
    return apply_rigid(verts, R, t)
