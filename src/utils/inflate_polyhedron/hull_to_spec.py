"""Derive a Polyhedron from a convex polyhedron's 3D vertex coordinates.

This is a reusable on-ramp: given nothing but the vertices of a convex
polyhedron with regular-polygon faces, it recovers which faces exist and
builds a Polyhedron from them -- face degrees and face adjacency are then
just `polyhedron.faces`/`polyhedron.compute_face_adjacency()`. scipy's
convex hull always triangulates non-triangular facets, so coplanar
triangles are merged back into their true polygonal face first.
"""
from collections import defaultdict

import numpy as np
from scipy.spatial import ConvexHull

from ..geometry.polyhedron import Polyhedron

PLANE_TOL = 1e-6
_PLANE_DECIMALS = round(-np.log10(PLANE_TOL))


def _merge_coplanar_facets(hull):
    """hull: a scipy.spatial.ConvexHull (always triangulated). Groups its
    simplices by facet plane. Returns a list of vertex-index sets, one per
    true (possibly non-triangular) polygon face."""
    groups = defaultdict(list)
    for simplex, eq in zip(hull.simplices, hull.equations):
        key = tuple(np.round(eq / np.linalg.norm(eq[:3]), _PLANE_DECIMALS))
        groups[key].append(simplex)
    return [set(np.concatenate(simplices)) for simplices in groups.values()]


def _order_face_loop(points, vertex_ids):
    """points: (N,3) all vertex positions; vertex_ids: the ids of one
    planar, convex face. Returns those ids reordered into a CCW
    (outward-facing) polygon loop, by angle around the face's own centroid."""
    pts = points[list(vertex_ids)]
    centroid = pts.mean(axis=0)
    normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
    normal /= np.linalg.norm(normal)
    # outward-facing check: normal should point away from the polyhedron's centroid
    if np.dot(centroid, normal) < 0:
        normal = -normal
    ref = pts[0] - centroid
    ref /= np.linalg.norm(ref)
    u, v = ref, np.cross(normal, ref)
    angles = [(np.arctan2(np.dot(p - centroid, v), np.dot(p - centroid, u)), vid)
              for p, vid in zip(pts, vertex_ids)]
    angles.sort()
    return [vid for _, vid in angles]


def polyhedron_from_vertices(vertices, name=None):
    """vertices: (N, 3) array-like of a convex polyhedron's corner points.
    Returns a Polyhedron built from those vertices and the CCW face loops
    recovered from their convex hull."""
    points = np.asarray(vertices, dtype=float)
    hull = ConvexHull(points)
    vertex_groups = _merge_coplanar_facets(hull)
    face_loops = [_order_face_loop(points, vids) for vids in vertex_groups]
    return Polyhedron(vertices=list(points), faces=face_loops, name=name)
