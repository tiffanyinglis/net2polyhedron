import numpy as np

from inflate_polyhedron_app.logic import geometry


def test_bounding_sphere_of_a_simple_box():
    points = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 2]], dtype=float)
    center, radius = geometry.bounding_sphere(points)
    assert np.allclose(center, [1.0, 1.0, 1.0])
    assert radius > np.linalg.norm(points - center, axis=1).max()  # epsilon padding
    assert radius == np.linalg.norm(points - center, axis=1).max() + 1e-6


def test_bounding_sphere_never_zero_for_a_single_point():
    points = np.array([[5.0, 5.0, 5.0]])
    center, radius = geometry.bounding_sphere(points)
    assert np.allclose(center, [5.0, 5.0, 5.0])
    assert radius > 0


def test_vertex_normals_of_a_flat_triangle_points_up():
    faces = [(0, 1, 2)]
    positions = {0: np.array([0.0, 0.0, 0.0]), 1: np.array([1.0, 0.0, 0.0]),
                 2: np.array([0.0, 1.0, 0.0])}
    normals = geometry.vertex_normals(faces, positions)
    for v in (0, 1, 2):
        unit_normal, mean_edge_len = normals[v]
        assert np.allclose(unit_normal, [0.0, 0.0, 1.0])
        assert mean_edge_len > 0


def test_vertex_normals_skips_degenerate_faces():
    # A degenerate (zero-area) triangle contributes nothing.
    faces = [(0, 1, 2)]
    positions = {0: np.array([0.0, 0.0, 0.0]), 1: np.array([1.0, 0.0, 0.0]),
                 2: np.array([2.0, 0.0, 0.0])}
    assert geometry.vertex_normals(faces, positions) == {}


def test_placed_edge_frame_outward_normal_points_away_from_centroid():
    # A unit square, CCW.
    points = [np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([1.0, 1.0]), np.array([0.0, 1.0])]
    origin, tangent, normal = geometry.placed_edge_frame(points, 0)  # bottom edge
    assert np.allclose(origin, [0.5, 0.0])
    assert np.allclose(normal, [0.0, -1.0])  # points away from the square's center


def test_cubic_bezier_points_endpoints_match_control_points():
    p0, p1, p2, p3 = (np.array([0.0, 0.0]), np.array([1.0, 1.0]),
                      np.array([2.0, -1.0]), np.array([3.0, 0.0]))
    points = geometry.cubic_bezier_points(p0, p1, p2, p3, steps=10)
    assert np.allclose(points[0], p0)
    assert np.allclose(points[-1], p3)
    assert len(points) == 11


def test_connection_curve_points_none_for_stale_connection():
    target_layout = {1: [np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.5, 1.0])]}
    conn = {"a_shape_id": 1, "a_edge": 0, "b_shape_id": 99, "b_edge": 0}
    assert geometry.connection_curve_points(target_layout, conn) is None


def test_connection_curve_points_builds_a_curve_between_two_triangles():
    tri_a = [np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.5, 1.0])]
    tri_b = [np.array([2.0, 0.0]), np.array([3.0, 0.0]), np.array([2.5, 1.0])]
    target_layout = {1: tri_a, 2: tri_b}
    conn = {"a_shape_id": 1, "a_edge": 0, "b_shape_id": 2, "b_edge": 0}
    curve = geometry.connection_curve_points(target_layout, conn, steps=5)
    assert curve is not None
    assert len(curve) == 6
