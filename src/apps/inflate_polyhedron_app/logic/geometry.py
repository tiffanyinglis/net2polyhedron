"""Mesh/panel geometry math, moved out of inflate_polyhedron_app/app.py (2026-09-30
modularization). Every function here is pure.
"""
import math

import numpy as np

from inflate_polyhedron_app.logic.mesh_topology import INTERACTIVE_BUILDER_EDGE_LENGTH
# `vertex_normals` moved to utils.inflate_polyhedron.mesh_normals (2026-10-01, explicit: "make
# sure they are using shared code whenever possible. shared code should be moved to utils") --
# was duplicated, byte-identical, in interactive_inflater_app's own app.py. Re-exported under
# the same name so every existing `from inflate_polyhedron_app.logic.geometry import
# vertex_normals` call site is unchanged.
from utils.inflate_polyhedron.mesh_normals import vertex_normals

__all__ = [
    "vertex_normals", "bounding_sphere", "placed_edge_frame", "cubic_bezier_points",
    "connection_curve_points",
]


def bounding_sphere(points):
    """(center, radius) for `points` (an (N, 3) array) -- center is the bounding-BOX center
    (not the centroid), radius is the farthest point's own distance from it plus a small
    epsilon (never exactly zero, so a single-point/degenerate mesh still gets a usable camera
    framing distance). Used by each "Level N"/viewer-quadrant panel to auto-fit its own current
    mesh."""
    lo, hi = points.min(axis=0), points.max(axis=0)
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(points - center, axis=1).max()) + 1e-6
    return center, radius


def placed_edge_frame(points, edge_index):
    """Same construction as interactive_builder_app's own _shape_edge_frame -- (origin, tangent,
    normal) for one edge of an already-placed 2D polygon -- but over plain placed points, since
    this app has no "shape" object. The outward-normal test (perpendicular to the edge, flipped
    if it doesn't point away from the centroid) is chirality-agnostic, so it's correct whether
    `points` is a rotation of the original shape or a mirror image of it (as here, after
    layout_from_net_layout's Y-flip)."""
    n = len(points)
    v1, v2 = points[edge_index], points[(edge_index + 1) % n]
    ox, oy = (v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2
    tx, ty = v2[0] - v1[0], v2[1] - v1[1]
    length = math.hypot(tx, ty) or 1.0
    tx, ty = tx / length, ty / length
    nx, ny = -ty, tx
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    if (ox - cx) * nx + (oy - cy) * ny < 0:
        nx, ny = -nx, -ny
    return np.array([ox, oy]), np.array([tx, ty]), np.array([nx, ny])


def cubic_bezier_points(p0, p1, p2, p3, steps=24):
    """Same sampling idea as interactive_builder_app's own _cubic_bezier_points (duplicated
    rather than imported, like INTERACTIVE_BUILDER_EDGE_LENGTH), over numpy points instead of
    plain tuples since that's what this app's own target_layout already uses."""
    return [(1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
            for t in np.linspace(0.0, 1.0, steps + 1)]


def connection_curve_points(target_layout, conn, steps=24):
    """The world-space points of one saved builder_connection's cubic bezier -- None if either
    referenced shape isn't in `target_layout` (a stale connection, not worth a crash over).
    `conn["a_shape_id"]/["b_shape_id"]` (new format) or `conn["a_face"]/["b_face"]` (legacy) key
    into `target_layout`. `conn["a_handle"]/["b_handle"]` are interactive_builder_app's own
    {"t", "n"} pixel-scale offsets -- rescaled by INTERACTIVE_BUILDER_EDGE_LENGTH like every
    cx/cy, then applied against the tangent/normal frame recomputed from this app's own already-
    placed (rescaled + Y-flipped) points (placed_edge_frame), which lands on the same point a
    transformed pre-image control point would since the Y-flip is a linear map."""
    a_key = conn["a_shape_id"] if "a_shape_id" in conn else conn["a_face"]
    b_key = conn["b_shape_id"] if "b_shape_id" in conn else conn["b_face"]
    a_points, b_points = target_layout.get(a_key), target_layout.get(b_key)
    if a_points is None or b_points is None:
        return None
    a_mid, a_tan, a_norm = placed_edge_frame(a_points, conn["a_edge"])
    b_mid, b_tan, b_norm = placed_edge_frame(b_points, conn["b_edge"])
    scale = INTERACTIVE_BUILDER_EDGE_LENGTH
    # An older file's connection entry has no "a_handle"/"b_handle" -- defaults to
    # {"t": 0, "n": 0} (control point at the edge midpoint) rather than a KeyError.
    a_handle = conn.get("a_handle", {"t": 0.0, "n": 0.0})
    b_handle = conn.get("b_handle", {"t": 0.0, "n": 0.0})
    a_ctrl = a_mid + (a_handle["t"] / scale) * a_tan + (a_handle["n"] / scale) * a_norm
    b_ctrl = b_mid + (b_handle["t"] / scale) * b_tan + (b_handle["n"] / scale) * b_norm
    return cubic_bezier_points(a_mid, a_ctrl, b_ctrl, b_mid, steps)
