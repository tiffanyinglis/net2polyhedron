from interactive_inflater_app.logic import face_modifier as fm


def test_remove_faces_from_mesh_filters_and_reindexes():
    base_faces = [[0, 1, 2], [2, 3, 4], [4, 5, 0]]
    base_face_edge_ids = [[1, 2, 3], [3, 4, 5], [5, 6, 1]]
    base_edges = [(0, 1), (2, 3), (4, 5)]
    source_polygon_id = [10, 20, 30]
    result = fm.remove_faces_from_mesh(
        base_faces, base_face_edge_ids, base_edges, source_polygon_id, {20})
    assert result["removed_idxs"] == {1}
    assert result["keep_base_idxs"] == [0, 2]
    assert result["surviving_base_faces"] == [[0, 1, 2], [4, 5, 0]]
    assert result["surviving_face_edge_ids"] == [[1, 2, 3], [5, 6, 1]]
    assert result["surviving_source_polygon_id"] == [10, 30]
    # (2, 3) touches the removed face's own vertices -- dropped; (0, 1) and (4, 5) survive.
    assert result["surviving_edges"] == [(0, 1), (4, 5)]


def test_remove_faces_from_mesh_none_when_everything_removed():
    base_faces = [[0, 1, 2]]
    assert fm.remove_faces_from_mesh(base_faces, None, None, [10], {10}) is None


def test_remove_faces_from_mesh_handles_no_face_edge_ids_or_edges():
    base_faces = [[0, 1, 2], [2, 3, 4]]
    result = fm.remove_faces_from_mesh(base_faces, None, None, [10, 20], {20})
    assert result["surviving_face_edge_ids"] is None
    assert result["surviving_edges"] is None


def test_remap_fine_mesh_after_removal():
    # Fine triangles tagged by ORIGINAL base-face index 0, 1, 2 -- base face 1 was removed
    # (removed_idxs={1}), and base faces 0/2 survived removal but face 0 ALSO got excluded as a
    # pendant in a second pass (old_to_core only has an entry for base-face 2's new index).
    faces = [["t0"], ["t1"], ["t2"]]
    face_of_fine = [0, 1, 2]
    removed_idxs = {1}
    old_to_new_base = {0: 0, 2: 1}  # base face 1 dropped, so face 2's new index is 1
    old_to_core = {1: 0}  # only new-index 1 (old base face 2) survives the pendant pass
    new_faces, new_face_of_fine = fm.remap_fine_mesh_after_removal(
        faces, face_of_fine, removed_idxs, old_to_new_base, old_to_core)
    assert new_faces == [["t2"]]
    assert new_face_of_fine == [0]
