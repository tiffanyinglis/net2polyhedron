import numpy as np

from interactive_inflater_app.logic import edge_selecter as es


def test_point_segment_distance_3d_endpoint_and_perpendicular():
    a, b = np.array([0.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])
    assert es.point_segment_distance_3d(np.array([-1.0, 0.0, 0.0]), a, b) == 1.0
    assert es.point_segment_distance_3d(np.array([1.0, 1.0, 0.0]), a, b) == 1.0


def test_nearest_connection_picks_closest_within_tolerance():
    a, b = np.array([0.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])
    c, d = np.array([10.0, 0.0, 0.0]), np.array([12.0, 0.0, 0.0])
    cache = {"near": np.array([a, b]), "far": np.array([c, d])}
    pos = np.array([1.0, 0.1, 0.0])
    assert es.nearest_connection(pos, cache, tolerance=1.0) == "near"


def test_nearest_connection_none_when_nothing_within_tolerance():
    a, b = np.array([0.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])
    cache = {"near": np.array([a, b])}
    pos = np.array([1.0, 5.0, 0.0])
    assert es.nearest_connection(pos, cache, tolerance=1.0) is None
    assert es.nearest_connection(None, cache, tolerance=1.0) is None
    assert es.nearest_connection(pos, {}, tolerance=1.0) is None


def test_nearest_connection_restricts_to_shape_id():
    a, b = np.array([0.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])
    cache = {"conn1": np.array([a, b])}
    connections_by_id = {"conn1": {"a_shape": 10, "b_shape": 20}}
    pos = np.array([1.0, 0.0, 0.0])
    assert es.nearest_connection(pos, cache, 1.0, connections_by_id, shape_id=10) == "conn1"
    assert es.nearest_connection(pos, cache, 1.0, connections_by_id, shape_id=99) is None


def test_nearest_open_edge_excludes_and_restricts_by_shape_id():
    a, b = np.array([0.0, 0.0, 0.0]), np.array([2.0, 0.0, 0.0])
    open_edges = {
        (10, 0): {"shape_id": 10, "segments": np.array([a, b])},
        (20, 0): {"shape_id": 20, "segments": np.array([a, b])},
    }
    pos = np.array([1.0, 0.0, 0.0])
    assert es.nearest_open_edge(pos, open_edges, 1.0, exclude_shape_id=10) == (20, 0)
    assert es.nearest_open_edge(pos, open_edges, 1.0, shape_id=10) == (10, 0)
    assert es.nearest_open_edge(None, open_edges, 1.0) is None
    assert es.nearest_open_edge(pos, {}, 1.0) is None
