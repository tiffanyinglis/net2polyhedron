from interactive_inflater_app.logic import face_indexer as fi


def test_resolve_display_state_uses_live_value_when_not_running():
    assert fi.resolve_display_state("live", False, {"k": "frozen"}, "k") == "live"
    assert fi.resolve_display_state("live", True, None, "k") == "live"


def test_resolve_display_state_uses_frozen_snapshot_while_running():
    assert fi.resolve_display_state("live", True, {"k": "frozen"}, "k") == "frozen"


def test_shape_id_of_group_basic_lookup_and_out_of_range():
    assert fi.shape_id_of_group(0, [11, 22]) == 11
    assert fi.shape_id_of_group(5, [11, 22]) is None
    assert fi.shape_id_of_group(None, [11, 22]) is None
    assert fi.shape_id_of_group(0, None) is None


def test_group_polygon_n_prefers_source_shape_n():
    shapes = [{"id": 11, "n": 6}]
    base_faces = [[1, 2, 3]]  # fan triangle, only 3 sides
    assert fi.group_polygon_n(0, [11], shapes, base_faces) == 6


def test_group_polygon_n_falls_back_to_base_face_length():
    base_faces = [[1, 2, 3, 4]]
    assert fi.group_polygon_n(0, None, [], base_faces) == 4
    assert fi.group_polygon_n(0, [99], [], base_faces) == 4  # shape_id not found


def test_groups_for_shape_ids():
    source_polygon_id = [11, 11, 22]
    assert fi.groups_for_shape_ids({11}, source_polygon_id) == {0, 1}
    assert fi.groups_for_shape_ids(set(), source_polygon_id) == set()
    assert fi.groups_for_shape_ids({11}, None) == set()


def test_groups_present():
    assert fi.groups_present([0, 0, 1, 2]) == {0, 1, 2}
    assert fi.groups_present(None) == set()
    assert fi.groups_present([]) == set()
