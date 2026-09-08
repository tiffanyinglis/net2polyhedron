import numpy as np

from utils.geometry.polyhedron import Polyhedron

# A regular tetrahedron: 4 shared vertices, 4 triangular faces as
# vertex-index tuples (CCW from outside) -- every edge appears in exactly
# 2 faces, a proper closed indexed mesh, no per-face point duplication.
A = np.array([1.0, 1.0, 1.0])
B = np.array([1.0, -1.0, -1.0])
C = np.array([-1.0, 1.0, -1.0])
D = np.array([-1.0, -1.0, 1.0])
TETRA_VERTICES = [A, B, C, D]
TETRA_FACES = [(0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)]


def _closed_tetra():
    return Polyhedron(vertices=TETRA_VERTICES, faces=TETRA_FACES, name="tetra")


def test_face_vertices_gathers_positions_in_order():
    solid = _closed_tetra()
    assert np.array_equal(solid.face_vertices(0), np.array([A, B, C]))


def test_face_normal_points_outward():
    solid = _closed_tetra()
    center = np.mean(TETRA_VERTICES, axis=0)
    for i in range(len(solid.faces)):
        normal = solid.face_normal(i)
        assert np.isclose(np.linalg.norm(normal), 1.0)
        centroid = solid.face_vertices(i).mean(axis=0)
        assert np.dot(normal, centroid - center) > 0


def test_edges_derived_from_faces_are_unique_and_unordered_pairs():
    solid = _closed_tetra()
    # 4 vertices, fully connected -> 6 edges (a tetrahedron's edge count)
    assert len(solid.edges) == 6
    for a, b in solid.edges:
        assert a < b


def test_edges_property_is_cached_and_reflects_faces_at_construction():
    solid = _closed_tetra()
    first = solid.edges
    assert solid.edges is first  # same cached list object, not recomputed


def test_is_closed_true_for_a_real_closed_solid():
    assert _closed_tetra().is_closed()


def test_is_closed_false_when_a_face_is_missing():
    tetra = _closed_tetra()
    open_tetra = Polyhedron(vertices=tetra.vertices, faces=tetra.faces[:-1])
    assert not open_tetra.is_closed()


def test_compute_face_adjacency_finds_every_shared_edge():
    solid = _closed_tetra()
    adjacency = solid.compute_face_adjacency()
    # 4 triangular faces, fully closed -> 6 shared edges, one entry each
    assert len(adjacency) == 6
    for face_a, edge_idx_a, face_b, edge_idx_b in adjacency:
        a = solid.faces[face_a][edge_idx_a]
        b = solid.faces[face_a][(edge_idx_a + 1) % len(solid.faces[face_a])]
        c = solid.faces[face_b][edge_idx_b]
        d = solid.faces[face_b][(edge_idx_b + 1) % len(solid.faces[face_b])]
        assert (a, b) == (d, c)  # opposite winding direction on the shared edge
