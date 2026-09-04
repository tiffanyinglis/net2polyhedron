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


def test_color_is_a_plain_attribute():
    face = Face(0, vertices2d=[np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0])])
    assert face.color is None
    face.color = "red"
    assert face.color == "red"
