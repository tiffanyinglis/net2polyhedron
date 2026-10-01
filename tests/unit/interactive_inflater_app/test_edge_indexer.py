import numpy as np

from interactive_inflater_app.logic import edge_indexer as ei


def test_group_boundary_edge_set_excludes_shared_diagonal():
    # Square 0-1-2-3 split into two triangles along the 0-2 diagonal -- the diagonal is interior
    # (shared by both triangles of the same group) and must NOT appear in the boundary.
    faces = [[0, 1, 2], [0, 2, 3]]
    face_of_fine = [0, 0]
    boundary = ei.group_boundary_edge_set(faces, face_of_fine, 0)
    assert boundary == {(0, 1), (1, 2), (2, 3), (0, 3)}


def test_group_boundary_edge_set_ignores_other_groups():
    faces = [[0, 1, 2], [3, 4, 5]]
    face_of_fine = [0, 1]
    assert ei.group_boundary_edge_set(faces, face_of_fine, 0) == {(0, 1), (1, 2), (0, 2)}


def test_base_edge_vertex_chain_unsubdivided_edge():
    boundary = {(0, 1), (1, 2), (2, 3), (0, 3)}
    assert ei.base_edge_vertex_chain(0, 1, boundary, {0, 1, 2, 3}) == [0, 1]


def test_base_edge_vertex_chain_walks_through_a_midpoint():
    # Edge 0-1 has been subdivided once, inserting midpoint vertex 4.
    boundary = {(0, 4), (4, 1), (1, 2), (2, 3), (0, 3)}
    chain = ei.base_edge_vertex_chain(0, 1, boundary, {0, 1, 2, 3})
    assert chain == [0, 4, 1]


def test_base_edge_vertex_chain_falls_back_when_unreachable():
    boundary = {(0, 1)}
    assert ei.base_edge_vertex_chain(2, 3, boundary, {0, 1, 2, 3}) == [2, 3]


def test_open_edge_geometry_odd_length_chain_midpoint_is_real_vertex():
    positions = {0: np.array([0.0, 0.0, 0.0]), 4: np.array([0.5, 0.0, 0.0]),
                 1: np.array([1.0, 0.0, 0.0])}
    midpoint, segments = ei.open_edge_geometry([0, 4, 1], positions, 0, 1)
    assert np.allclose(midpoint, [0.5, 0.0, 0.0])
    assert segments.shape == (4, 3)
    assert np.allclose(segments[0], [0, 0, 0])
    assert np.allclose(segments[-1], [1, 0, 0])


def test_open_edge_geometry_falls_back_to_straight_average_when_chain_unresolved():
    positions = {0: np.array([0.0, 0.0, 0.0]), 1: np.array([2.0, 0.0, 0.0])}
    midpoint, segments = ei.open_edge_geometry([0, 1], positions, 0, 1)
    assert np.allclose(midpoint, [1.0, 0.0, 0.0])
    assert np.array_equal(segments, np.array([positions[0], positions[1]]))


def test_open_edges_for_mesh_builds_one_entry_per_unused_edge():
    base_faces = [[1, 2, 3, 4]]
    pending_source_polygon_id = [100]
    shapes = [{"id": 100, "n": 4, "flipped": False}]
    connections = []
    positions = {1: "p1", 2: "p2", 3: "p3", 4: "p4"}
    calls = []

    def geometry_fn(group, u, v):
        calls.append((group, u, v))
        return f"mid-{u}-{v}", f"seg-{u}-{v}"

    open_edges = ei.open_edges_for_mesh(
        base_faces, pending_source_polygon_id, shapes, connections, positions, geometry_fn)
    assert set(open_edges) == {(100, 0), (100, 1), (100, 2), (100, 3)}
    assert open_edges[(100, 0)] == {
        "shape_id": 100, "raw_edge": 0, "midpoint": "mid-1-2", "segments": "seg-1-2"}
    assert len(calls) == 4


def test_open_edges_for_mesh_skips_edges_already_connected():
    base_faces = [[1, 2, 3, 4]]
    pending_source_polygon_id = [100]
    shapes = [{"id": 100, "n": 4, "flipped": False}]
    connections = [{"a_shape": 100, "a_edge": 0, "b_shape": 200, "b_edge": 0}]
    positions = {1: "p1", 2: "p2", 3: "p3", 4: "p4"}
    open_edges = ei.open_edges_for_mesh(
        base_faces, pending_source_polygon_id, shapes, connections, positions,
        lambda group, u, v: (None, None))
    assert (100, 0) not in open_edges
    assert len(open_edges) == 3


def test_open_edges_for_mesh_skips_deleted_or_mismatched_shapes():
    base_faces = [[1, 2, 3]]  # a fan triangle whose "shape" is really a 5-gon fold
    pending_source_polygon_id = [100]
    shapes = [{"id": 100, "n": 5, "flipped": False}]
    assert ei.open_edges_for_mesh(
        base_faces, pending_source_polygon_id, shapes, [], {1: "p", 2: "p", 3: "p"},
        lambda g, u, v: (None, None)) == {}
    # Deleted shape entirely:
    assert ei.open_edges_for_mesh(
        base_faces, pending_source_polygon_id, [], [], {1: "p", 2: "p", 3: "p"},
        lambda g, u, v: (None, None)) == {}


def test_open_edges_for_mesh_empty_when_no_mesh():
    assert ei.open_edges_for_mesh(None, None, [], [], None, lambda g, u, v: (None, None)) == {}
