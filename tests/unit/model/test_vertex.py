import numpy as np

from utils.model.vertex import Vertex


def test_vertex_holds_id_and_position():
    v = Vertex(3, np.array([1.0, 2.0, 3.0]))
    assert v.id == 3
    assert np.array_equal(v.position, [1.0, 2.0, 3.0])
