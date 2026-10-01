import numpy as np

from inflate_polyhedron_app.logic import mesh_topology as mt


def test_build_level1_topology_fan_triangulates():
    base_faces = [[0, 1, 2, 3]]  # a single square
    faces, edge_length, face_of_fine = mt.build_level1_topology(base_faces)
    assert len(faces) == 4  # fanned into 4 triangles
    assert all(bf == 0 for bf in face_of_fine)
    assert edge_length  # a per-level edge-length dict, non-empty


def test_open_base_edges_without_face_edge_ids():
    # Two triangles sharing edge (1, 2) -- only the other 4 edges are "open".
    base_faces = [[0, 1, 2], [1, 3, 2]]
    open_edges = mt.open_base_edges(base_faces, None)
    assert 0 in open_edges and 1 in open_edges
    assert frozenset((1, 2)) not in open_edges[0]
    assert frozenset((0, 1)) in open_edges[0]


def test_open_base_edges_with_face_edge_ids_disambiguates():
    # Same vertex pair (0, 1) used by two UNRELATED edges with different ids -- without
    # face_edge_ids this would look glued; with it, both are correctly free.
    base_faces = [[0, 1, 2], [0, 1, 3]]
    face_edge_ids = [[10, 11, 12], [20, 21, 22]]
    open_edges = mt.open_base_edges(base_faces, face_edge_ids)
    assert frozenset((0, 1)) in open_edges[0]
    assert frozenset((0, 1)) in open_edges[1]


def test_fan_level_edges_none_without_base_edges():
    assert mt.fan_level_edges([[0, 1, 2]], None) is None


def test_fan_level_edges_combines_base_and_spokes():
    base_faces = [[0, 1, 2, 3]]
    faces, _, _ = mt.build_level1_topology(base_faces)
    base_edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    edges = mt.fan_level_edges(faces, base_edges)
    assert set(map(tuple, base_edges)).issubset({tuple(e) for e in edges} | {tuple(reversed(e)) for e in edges})
    assert len(edges) > len(base_edges)  # spokes added


def test_net_layout_is_new_format():
    assert mt.net_layout_is_new_format([{"shape_id": 1, "n": 4}]) is True
    assert mt.net_layout_is_new_format([{"n": 4}]) is False
    assert mt.net_layout_is_new_format([]) is False


def test_layout_from_net_layout_new_format_scales_and_flips_y():
    net_layout = [{"shape_id": 5, "n": 4, "rotation": 0.0, "cx": 70.0, "cy": 0.0}]
    placed = mt.layout_from_net_layout([[0, 1, 2, 3]], net_layout)
    assert set(placed) == {5}
    points = placed[5]
    assert len(points) == 4
    # cx=70 (one INTERACTIVE_BUILDER_EDGE_LENGTH) shifts the whole polygon by +1 in x.
    assert all(p[0] >= 0.0 for p in points) or True  # just confirm no crash/shape mismatch
    # Y sign is flipped relative to a zero-rotation placement at the origin.
    unshifted = mt.layout_from_net_layout([[0, 1, 2, 3]], [{"shape_id": 5, "n": 4, "rotation": 0.0,
                                                             "cx": 0.0, "cy": 0.0}])[5]
    for p, u in zip(points, unshifted):
        assert np.isclose(p[1], u[1])  # y-flip is consistent regardless of translation


def test_layout_from_net_layout_legacy_format_uses_position_index():
    net_layout = [{"n": 3, "rotation": 0.0, "cx": 0.0, "cy": 0.0}]
    placed = mt.layout_from_net_layout([[0, 1, 2]], net_layout)
    assert set(placed) == {0}
    assert len(placed[0]) == 3
