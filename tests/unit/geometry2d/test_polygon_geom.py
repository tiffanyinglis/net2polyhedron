import numpy as np

from utils.geometry2d.polygon_geom import (
    EDGE_LENGTH, regular_polygon_vertices, rigid_transform_2d, attach_polygon,
)


def edge_lengths(verts):
    k = len(verts)
    return [np.linalg.norm(verts[(i + 1) % k] - verts[i]) for i in range(k)]


def test_regular_polygon_has_unit_edges_and_right_vertex_count():
    for k in (3, 4, 5, 6, 8):
        verts = regular_polygon_vertices(k)
        assert len(verts) == k
        assert np.allclose(edge_lengths(verts), EDGE_LENGTH)


def test_regular_polygon_is_ccw():
    # signed area via the shoelace formula is positive for CCW polygons
    for k in (3, 4, 5, 6):
        verts = regular_polygon_vertices(k)
        area = 0.0
        for i in range(k):
            x1, y1 = verts[i]
            x2, y2 = verts[(i + 1) % k]
            area += x1 * y2 - x2 * y1
        assert area > 0


def test_rigid_transform_maps_points_exactly():
    a, b = np.array([0.0, 0.0]), np.array([1.0, 0.0])
    target_a, target_b = np.array([3.0, 4.0]), np.array([3.0, 5.0])
    R, t = rigid_transform_2d(a, b, target_a, target_b)
    assert np.allclose(R @ a + t, target_a)
    assert np.allclose(R @ b + t, target_b)
    # a proper rotation matrix: orthonormal, determinant +1 (no reflection)
    assert np.allclose(R @ R.T, np.eye(2))
    assert np.isclose(np.linalg.det(R), 1.0)


def test_attach_polygon_edge_lands_exactly_on_target():
    target_p1 = np.array([2.0, 0.0])
    target_p2 = np.array([1.5, 0.8660254])  # 60 degrees away, unit distance
    verts = attach_polygon(5, local_edge_idx=2, target_p1=target_p1, target_p2=target_p2)
    assert len(verts) == 5
    assert np.allclose(verts[2], target_p1, atol=1e-9)
    assert np.allclose(verts[3], target_p2, atol=1e-9)
    assert np.allclose(edge_lengths(verts), EDGE_LENGTH)
