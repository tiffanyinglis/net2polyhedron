import numpy as np

from utils.model.face import Face


def test_sides_inferred_from_vertices2d_when_not_given():
    face = Face(0, vertices2d=[np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0])])
    assert face.sides == 3


def test_edge2d_wraps_around():
    pts = [np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    face = Face(0, vertices2d=pts)
    assert np.allclose(face.edge2d(0), (pts[0], pts[1]))
    assert np.allclose(face.edge2d(2), (pts[2], pts[0]))


def test_with_vertices3d_copies_color_and_leaves_original_untouched():
    face = Face(0, vertices2d=[np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0])],
                color="red")
    verts3d = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

    folded = face.with_vertices3d(verts3d)

    assert folded.color == "red"
    assert folded.id == face.id
    assert np.array_equal(folded.vertices3d, verts3d)
    assert face.vertices3d is None  # original face untouched


def test_normal_wraps_face_normal():
    verts3d = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    face = Face(0, vertices3d=verts3d)
    assert np.allclose(face.normal(), [0.0, 0.0, 1.0])
