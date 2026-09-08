import numpy as np
import pytest

from utils.inflate_polyhedron.stretchy_mesh import load_stretchy_mesh, mesh_edges
from utils.subdivisions.mesh_subdivide import subdivide_mesh, solve_fabric_mesh

TETRAHEDRON_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]


def _directed_edges(faces):
    return [e for face in faces for e in
            [(face[0], face[1]), (face[1], face[2]), (face[2], face[0])]]


@pytest.mark.parametrize("resolution", [1, 2, 3])
def test_subdivide_mesh_stays_a_closed_consistently_wound_mesh(resolution):
    # every directed fine edge should have exactly one reverse partner and
    # no duplicate, same closure property load_stretchy_mesh checks for
    # the coarse mesh -- subdividing must not break it.
    fine_faces, face_of_fine, edge_lengths, seed = subdivide_mesh(
        TETRAHEDRON_FACES, resolution=resolution)
    assert len(face_of_fine) == len(fine_faces)
    assert seed is None  # no coarse_positions given
    directed = _directed_edges(fine_faces)
    counts = {}
    for e in directed:
        counts[e] = counts.get(e, 0) + 1
    assert all(c == 1 for c in counts.values())
    assert all((b, a) in counts for a, b in counts)


def test_subdivide_mesh_every_fine_edge_has_a_rest_length():
    fine_faces, _, edge_lengths, _ = subdivide_mesh(TETRAHEDRON_FACES, resolution=3)
    for e in mesh_edges(fine_faces):
        assert e in edge_lengths
        assert edge_lengths[e] > 0


def test_subdivide_mesh_shares_boundary_vertices_between_adjacent_faces():
    # a resolution-r subdivision of the tetrahedron's 4 faces should NOT
    # just be 4 disconnected patches: shared coarse edges must merge.
    fine_faces, _, _, _ = subdivide_mesh(TETRAHEDRON_FACES, resolution=3)
    n_verts = len({v for f in fine_faces for v in f})
    # 4 original corners + 3 new points per coarse edge (6 edges, shared)
    # + 3 new interior points per face (4 faces) for a resolution-3 split
    # of a plain triangle (no centroid): (r+1)(r+2)/2 - 3*r - 3*(r-1) per
    # face interior... simplest robust check: strictly fewer vertices
    # than 4 independent copies would need.
    disconnected_upper_bound = 4 * 10  # (r+1)(r+2)/2 = 10 points per triangle at r=3
    assert n_verts < disconnected_upper_bound


def test_subdivide_mesh_pentagon_face_has_two_distinct_rest_lengths():
    # a centroid-fan subdivision of a pentagon has unit-length rim edges
    # but shorter spoke-to-centroid edges -- NOT a uniform edge length.
    faces, _ = load_stretchy_mesh("data/input/stretchy_nets/dodecahedron.json")
    _, _, edge_lengths, _ = subdivide_mesh(faces, resolution=3)
    lengths = sorted(set(round(l, 6) for l in edge_lengths.values()))
    assert len(lengths) == 2
    assert lengths[0] < lengths[1]


def test_solve_fabric_mesh_on_tetrahedron_stays_near_unit_stretch():
    fine_faces, face_of_fine, positions, stats = solve_fabric_mesh(
        TETRAHEDRON_FACES, resolution=2, seed=0)
    assert set(positions) == {v for f in fine_faces for v in f}
    assert len(face_of_fine) == len(fine_faces)
    assert max(face_of_fine) == 3  # 4 coarse faces, ids 0..3
    assert stats["max_stretch_pct"] < 1.0  # tetrahedron faces land ~flat/unit already


def test_solve_fabric_mesh_on_a_genuinely_bendy_net():
    # two_pentagons_and_a_square.json cannot stay rigid/flat at the coarse
    # level either -- the fine fabric mesh should still solve cleanly.
    faces, _ = load_stretchy_mesh("data/input/stretchy_nets/two_pentagons_and_a_square.json")
    fine_faces, face_of_fine, positions, stats = solve_fabric_mesh(faces, resolution=2, seed=0)
    assert set(positions) == {v for f in fine_faces for v in f}
    assert stats["max_stretch_pct"] < 10.0
