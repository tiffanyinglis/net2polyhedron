from interactive_inflater_app.logic import flat_face_attacher as ffa


def test_prepare_mesh_for_inflate_place_mode_for_lone_face():
    mode, reference_face, reference_spid, pendants = ffa.prepare_mesh_for_inflate(
        [[0, 1, 2]], None, None)
    assert mode == "place"
    assert reference_face == [0, 1, 2]
    assert pendants == []


def test_prepare_mesh_for_inflate_place_mode_for_mutual_pair():
    # Two triangles glued along one shared edge (0, 1) -- each is the other's only neighbor.
    base_faces = [[0, 1, 2], [1, 0, 3]]
    mode, reference_face, reference_spid, pendants = ffa.prepare_mesh_for_inflate(
        base_faces, None, None)
    assert mode == "place"
    assert reference_face == [0, 1, 2]
    assert len(pendants) == 1
    assert pendants[0]["face"] == [1, 0, 3]


def test_prepare_mesh_for_inflate_solve_mode_for_a_braced_mesh():
    # A closed loop of 3 faces, each glued to the other two -- never degenerates to pendants.
    base_faces = [[0, 1, 2], [0, 2, 3], [0, 3, 1]]
    result = ffa.prepare_mesh_for_inflate(base_faces, None, None)
    assert result[0] == "solve"
    core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id, pendants = result[1:]
    assert core_base_faces == base_faces
    assert pendants == []


def test_prepare_mesh_for_inflate_excludes_single_edge_hinged_pendant():
    # A fully-braced 3-triangle loop (t0/t1/t2, each glued to the other two -- see the "solve
    # mode" test above) plus t3, hinged onto t0 by exactly ONE edge -- t3 should be excluded as
    # a pendant, leaving the braced 3-face loop as the solvable core.
    t0, t1, t2, t3 = [0, 1, 2], [0, 2, 3], [0, 3, 1], [2, 1, 4]
    base_faces = [t0, t1, t2, t3]
    result = ffa.prepare_mesh_for_inflate(base_faces, None, None)
    assert result[0] == "solve"
    core_base_faces, _, _, _, pendants = result[1:]
    assert core_base_faces == [t0, t1, t2]
    assert len(pendants) == 1
    assert pendants[0]["face"] == t3
    assert pendants[0]["neighbor_idx"] == 0
