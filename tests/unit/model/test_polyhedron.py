import numpy as np

from utils.model.face import Face
from utils.model.polyhedron import Polyhedron

# A regular tetrahedron's 4 vertices, and its 4 triangular faces -- every
# edge appears in exactly 2 faces regardless of each face's own winding, so
# this is a valid closed solid combinatorially without needing a real
# PolyhedralNet.fold() to produce it.
A = np.array([1.0, 1.0, 1.0])
B = np.array([1.0, -1.0, -1.0])
C = np.array([-1.0, 1.0, -1.0])
D = np.array([-1.0, -1.0, 1.0])

TETRA_FACES = {
    0: Face(0, vertices3d=np.array([A, B, C])),
    1: Face(1, vertices3d=np.array([A, B, D])),
    2: Face(2, vertices3d=np.array([A, C, D])),
    3: Face(3, vertices3d=np.array([B, C, D])),
}


def _closed_tetra():
    return Polyhedron(name="tetra", faces=TETRA_FACES)


def test_is_closed_true_for_a_real_closed_solid():
    assert _closed_tetra().is_closed


def test_is_closed_false_when_a_face_is_missing():
    open_faces = {fid: f for fid, f in TETRA_FACES.items() if fid != 3}
    solid = Polyhedron(name="open tetra", faces=open_faces)
    assert not solid.is_closed


def test_vertices_merges_duplicated_corners_into_four_distinct_points():
    solid = _closed_tetra()
    assert len(solid.vertices) == 4


def test_bounding_box_matches_the_tetrahedron_extent():
    lo, hi = _closed_tetra().bounding_box()
    assert np.allclose(lo, [-1.0, -1.0, -1.0])
    assert np.allclose(hi, [1.0, 1.0, 1.0])
