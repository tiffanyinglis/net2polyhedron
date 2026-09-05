import numpy as np

from common.bounding_box import bounding_box

TETRA_VERTICES = [np.array(v) for v in
                   [(1.0, 1.0, 1.0), (1.0, -1.0, -1.0), (-1.0, 1.0, -1.0), (-1.0, -1.0, 1.0)]]


def test_bounding_box_matches_the_tetrahedron_extent():
    lo, hi = bounding_box(TETRA_VERTICES)
    assert np.allclose(lo, [-1.0, -1.0, -1.0])
    assert np.allclose(hi, [1.0, 1.0, 1.0])
