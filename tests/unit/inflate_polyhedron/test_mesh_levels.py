import math

import numpy as np
import pytest

from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, base_rest_lengths, subdivide_once
from utils.inflate_polyhedron.stretchy_mesh import mesh_edges, EDGE_LENGTH

# Reused verbatim from test_stretchy_mesh.py -- already-verified CCW,
# closed, all-triangle winding.
TETRAHEDRON_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]

# From data/input/stretchy_nets/cube.json -- all-quad winding.
CUBE_FACES = [
    [4, 0, 2, 6], [1, 0, 4, 5], [5, 4, 6, 7],
    [2, 0, 1, 3], [6, 2, 3, 7], [3, 1, 5, 7],
]


def _rng_positions(faces, seed=0):
    vertex_ids = sorted({v for face in faces for v in face})
    rng = np.random.default_rng(seed)
    return {v: rng.normal(size=3) for v in vertex_ids}


def _directed_edges(faces):
    edges = []
    for face in faces:
        n = len(face)
        edges += [(face[i], face[(i + 1) % n]) for i in range(n)]
    return edges


def _assert_closed_consistent_mesh(faces):
    """Every directed edge must be matched by exactly one reverse partner
    in some other face -- the same check load_stretchy_mesh performs."""
    directed = _directed_edges(faces)
    counts = {}
    for e in directed:
        counts[e] = counts.get(e, 0) + 1
    for (a, b), c in counts.items():
        assert c == 1, f"edge {a}->{b} appears {c} times"
        assert (b, a) in counts, f"edge {a}->{b} has no reverse partner"


def test_level_0_triangle_face_is_unchanged():
    positions = _rng_positions(TETRAHEDRON_FACES)
    faces, new_positions, edge_length, face_of_fine = subdivide_once(
        TETRAHEDRON_FACES, positions, EDGE_LENGTH, list(range(len(TETRAHEDRON_FACES))), level=0)
    assert [tuple(f) for f in faces] == [tuple(f) for f in TETRAHEDRON_FACES]
    assert set(new_positions) == set(positions)
    assert face_of_fine == [0, 1, 2, 3]


def test_level_0_to_1_square_face_adds_centroid_with_exact_spoke_length():
    square = [(0, 1, 2, 3)]
    positions = {0: np.array([0.0, 0, 0]), 1: np.array([1.0, 0, 0]),
                 2: np.array([1.0, 1, 0]), 3: np.array([0.0, 1, 0])}
    faces, new_positions, edge_length, face_of_fine = subdivide_once(
        square, positions, EDGE_LENGTH, [0], level=0)

    assert len(faces) == 4  # centroid fan: one triangle per side
    assert face_of_fine == [0, 0, 0, 0]
    new_ids = set(new_positions) - set(positions)
    assert len(new_ids) == 1
    centroid_id = new_ids.pop()
    assert np.allclose(new_positions[centroid_id], [0.5, 0.5, 0.0])

    # rim edges unchanged
    for rim in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        assert edge_length[tuple(sorted(rim))] == EDGE_LENGTH
    # spoke length is the exact circumradius of a unit square
    expected_spoke = 1.0 / (2 * math.sin(math.pi / 4))
    for corner in range(4):
        key = tuple(sorted((corner, centroid_id)))
        assert edge_length[key] == pytest.approx(expected_spoke)


def test_subdivide_once_rejects_level_at_or_past_max():
    positions = _rng_positions(TETRAHEDRON_FACES)
    with pytest.raises(ValueError):
        subdivide_once(TETRAHEDRON_FACES, positions, EDGE_LENGTH,
                        list(range(len(TETRAHEDRON_FACES))), level=MAX_LEVEL)


@pytest.mark.parametrize("faces", [TETRAHEDRON_FACES, CUBE_FACES])
def test_face_count_and_rest_lengths_scale_correctly_through_every_level(faces):
    positions = _rng_positions(faces)
    edge_length = EDGE_LENGTH
    face_of_fine = list(range(len(faces)))
    cur_faces = faces
    prev_face_count = len(faces)

    for level in range(MAX_LEVEL):
        cur_faces, positions, edge_length, face_of_fine = subdivide_once(
            cur_faces, positions, edge_length, face_of_fine, level)

        # every mesh edge has a rest length, and vice versa
        assert set(edge_length) == set(mesh_edges(cur_faces))
        # stays a valid closed, consistently-wound mesh
        _assert_closed_consistent_mesh(cur_faces)
        # every fine face still points at a real base face
        assert all(0 <= b < len(faces) for b in face_of_fine)
        assert len(face_of_fine) == len(cur_faces)

        if level >= 1:
            # quartering always exactly quadruples the triangle count
            assert len(cur_faces) == 4 * prev_face_count
        prev_face_count = len(cur_faces)


def test_positions_are_nested_subsets_across_levels():
    positions = _rng_positions(CUBE_FACES)
    edge_length = EDGE_LENGTH
    face_of_fine = list(range(len(CUBE_FACES)))
    cur_faces = CUBE_FACES

    for level in range(MAX_LEVEL):
        prev_positions = positions
        cur_faces, positions, edge_length, face_of_fine = subdivide_once(
            cur_faces, positions, edge_length, face_of_fine, level)
        # every previous vertex survives, at the EXACT same position
        for v, p in prev_positions.items():
            assert v in positions
            assert np.array_equal(positions[v], p)


def test_quartering_new_internal_edges_match_midsegment_theorem():
    # A single equilateral triangle, edge length 1.
    positions = {0: np.array([0.0, 0, 0]), 1: np.array([1.0, 0, 0]),
                 2: np.array([0.5, math.sqrt(3) / 2, 0])}
    faces = [(0, 1, 2)]
    edge_length = base_rest_lengths(faces, EDGE_LENGTH)
    new_faces, new_positions, new_edge_length, _ = subdivide_once(
        faces, positions, edge_length, [0], level=1)

    assert len(new_faces) == 4
    # every rest length in a subdivided equilateral triangle is 0.5
    assert all(length == pytest.approx(0.5) for length in new_edge_length.values())
