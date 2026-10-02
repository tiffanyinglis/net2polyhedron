from utils.inflate_polyhedron.mesh_topology import base_face_neighbors


def test_base_face_neighbors_without_face_edge_ids():
    # Two triangles sharing edge (1, 2) -- they're each other's only neighbor.
    base_faces = [[0, 1, 2], [1, 3, 2]]
    neighbors = base_face_neighbors(base_faces, None)
    assert neighbors[0] == {1}
    assert neighbors[1] == {0}


def test_base_face_neighbors_with_face_edge_ids_disambiguates():
    # Same vertex pair (0, 1) used by two UNRELATED edges with different ids -- without
    # face_edge_ids this would look glued; with it, neither face has any neighbor.
    base_faces = [[0, 1, 2], [0, 1, 3]]
    face_edge_ids = [[10, 11, 12], [20, 21, 22]]
    neighbors = base_face_neighbors(base_faces, face_edge_ids)
    assert neighbors[0] == set()
    assert neighbors[1] == set()


def test_base_face_neighbors_isolated_face_gets_empty_set_not_missing_key():
    base_faces = [[0, 1, 2]]
    neighbors = base_face_neighbors(base_faces, None)
    assert neighbors == {0: set()}


def test_base_face_neighbors_three_faces_sharing_one_edge():
    # A degenerate but legal case: three faces all claiming the same edge id -- every pair
    # should be marked as neighbors of each other.
    base_faces = [[0, 1, 2], [0, 1, 3], [0, 1, 4]]
    face_edge_ids = [[1, 2, 3], [1, 4, 5], [1, 6, 7]]
    neighbors = base_face_neighbors(base_faces, face_edge_ids)
    assert neighbors[0] == {1, 2}
    assert neighbors[1] == {0, 2}
    assert neighbors[2] == {0, 1}
