from inflate_polyhedron_app.logic import net_loading


def test_resolve_base_faces_ordinary_net_no_self_join():
    faces = [[0, 1, 2]]
    base_faces, self_join_split = net_loading.resolve_base_faces(faces, legacy_coarse_faces=None)
    assert base_faces == faces
    assert self_join_split is False


def test_resolve_base_faces_legacy_fabric_net_uses_coarse_faces():
    faces = [[0, 1, 2, 3, 4, 5]]  # fine, pre-baked mesh
    legacy_coarse_faces = [[0, 2, 4]]
    base_faces, self_join_split = net_loading.resolve_base_faces(faces, legacy_coarse_faces)
    assert base_faces == legacy_coarse_faces
    assert self_join_split is False  # never checked for the legacy-fabric case


def test_resolve_base_faces_splits_a_self_joined_face():
    # A hexagon that repeats vertex 0 -- a self-join.
    faces = [[0, 1, 2, 0, 3, 4]]
    base_faces, self_join_split = net_loading.resolve_base_faces(faces, legacy_coarse_faces=None)
    assert self_join_split is True
    assert base_faces != faces  # split_self_joined_faces rewrote it


def test_target_layout_and_connections_falls_back_to_bfs_without_net_layout():
    base_faces = [[0, 1, 2]]
    target_layout, target_connections, target_group_of_face = net_loading.target_layout_and_connections(
        base_faces, net_file_json={})
    assert target_connections is None
    assert set(target_layout) == {0}  # BFS layout keys by face index
    assert target_group_of_face == [0]


def test_target_layout_and_connections_uses_saved_net_layout_when_present():
    base_faces = [[0, 1, 2, 3]]
    net_file_json = {
        "net_layout": [{"shape_id": 7, "n": 4, "rotation": 0.0, "cx": 0.0, "cy": 0.0}],
        "builder_connections": [{"a_shape_id": 7, "a_edge": 0, "b_shape_id": 7, "b_edge": 2}],
        "source_polygon_id": [7],
    }
    target_layout, target_connections, target_group_of_face = net_loading.target_layout_and_connections(
        base_faces, net_file_json)
    assert set(target_layout) == {7}
    assert target_connections == net_file_json["builder_connections"]
    # Matches target_layout's own shape_id key space, not base-face position -- a color-mode
    # lookup keyed by position alone (e.g. Multi-colour) would otherwise KeyError against
    # target_layout's keys (2026-10-01 bug fix).
    assert target_group_of_face == [7]


def test_target_layout_and_connections_ignores_net_layout_when_self_join_split():
    base_faces = [[0, 1, 2, 3]]
    net_file_json = {"net_layout": [{"shape_id": 7, "n": 4, "rotation": 0.0, "cx": 0.0, "cy": 0.0}]}
    target_layout, target_connections, target_group_of_face = net_loading.target_layout_and_connections(
        base_faces, net_file_json, self_join_split=True)
    assert target_connections is None
    assert set(target_layout) == {0}  # fell back to BFS, not the saved net_layout
    assert target_group_of_face == [0]


def test_target_layout_and_connections_legacy_net_layout_requires_length_match():
    base_faces = [[0, 1, 2], [1, 2, 3]]  # sharing an edge, so BFS can place both
    # Legacy net_layout (no "shape_id") with only ONE entry -- length mismatch, falls back.
    net_file_json = {"net_layout": [{"n": 3, "rotation": 0.0, "cx": 0.0, "cy": 0.0}]}
    target_layout, target_connections, target_group_of_face = net_loading.target_layout_and_connections(
        base_faces, net_file_json)
    assert target_connections is None
    assert set(target_layout) == {0, 1}
    assert target_group_of_face == [0, 1]
