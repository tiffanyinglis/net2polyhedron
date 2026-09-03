import pytest

from net_fold_utils.combinatorics import EdgeMap

TETRAHEDRON_EDGES = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
TETRAHEDRON_DEGREES = [3, 3, 3, 3]


def test_edge_map_reciprocity_on_tetrahedron():
    edge_map = EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES)
    for f in range(4):
        for nb in range(4):
            if nb == f:
                continue
            idx = edge_map.edge_index(f, nb)
            assert edge_map.neighbor_at(f, idx) == nb

    for f, degree in enumerate(TETRAHEDRON_DEGREES):
        neighbors = {edge_map.neighbor_at(f, i) for i in range(degree)}
        assert neighbors == {0, 1, 2, 3} - {f}


def test_edge_map_rejects_degree_mismatch():
    with pytest.raises(ValueError, match="4-gon"):
        EdgeMap([4, 3, 3, 3], TETRAHEDRON_EDGES)


def test_edge_map_rejects_duplicate_edge():
    with pytest.raises(ValueError, match="duplicate"):
        EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES + [(0, 1)])


def test_edge_map_rejects_self_loop():
    with pytest.raises(ValueError, match="two distinct faces"):
        EdgeMap([2, 3, 3, 3], TETRAHEDRON_EDGES + [(0, 0)])


def test_edge_map_rejects_nonplanar_graph():
    # K5: 5 faces, every pair adjacent -- not planar
    degrees = [4, 4, 4, 4, 4]
    edges = [(a, b) for a in range(5) for b in range(a + 1, 5)]
    with pytest.raises(ValueError, match="planar"):
        EdgeMap(degrees, edges)
