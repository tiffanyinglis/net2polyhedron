"""Derive a polyhedron-net spec (face degrees + adjacency edges) from a
convex polyhedron's 3D vertex coordinates.

This is a reusable on-ramp: given nothing but the vertices of a convex
polyhedron with regular-polygon faces, it recovers which faces exist, their
degrees, and which faces are adjacent -- everything polyhedron_spec.py needs
to write out a FACES/NET/EXTRA file. scipy's convex hull always triangulates
non-triangular facets, so coplanar triangles are merged back into their true
polygonal face first.
"""
from collections import defaultdict

import numpy as np
from scipy.spatial import ConvexHull

PLANE_TOL = 1e-6


def _merge_coplanar_facets(hull):
    """Group hull.simplices by facet plane, return list of vertex-index
    sets, one per true polygon face."""
    groups = defaultdict(list)
    for simplex, eq in zip(hull.simplices, hull.equations):
        key = tuple(np.round(eq / np.linalg.norm(eq[:3]), 6))
        groups[key].append(simplex)
    return [set(np.concatenate(simplices)) for simplices in groups.values()]


def _order_face_loop(points, vertex_ids):
    """Order a planar, convex set of vertex ids into a CCW polygon loop."""
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


def polyhedron_from_vertices(vertices):
    """vertices: (N, 3) array-like of a convex polyhedron's corner points.
    Returns (degrees, edges, face_loops):
      degrees   -- list, degrees[f] = number of sides of face f
      edges     -- list of (f1, f2) for every pair of faces sharing an edge
      face_loops -- list of each face's vertex-index loop (for inspection)
    """
    points = np.asarray(vertices, dtype=float)
    hull = ConvexHull(points)
    vertex_groups = _merge_coplanar_facets(hull)
    face_loops = [_order_face_loop(points, vids) for vids in vertex_groups]

    degrees = [len(loop) for loop in face_loops]

    edge_owner = {}  # frozenset({vertex_a, vertex_b}) -> face index
    edges = []
    for fid, loop in enumerate(face_loops):
        k = len(loop)
        for i in range(k):
            e = frozenset((loop[i], loop[(i + 1) % k]))
            if e in edge_owner:
                edges.append((edge_owner[e], fid))
            else:
                edge_owner[e] = fid

    return degrees, edges, face_loops
