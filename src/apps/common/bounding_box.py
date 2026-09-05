"""Bounding-box helper for the Tkinter/matplotlib apps -- centering and
sizing a 3D plot around a solid's own extent is a rendering concern, not
something model.Polyhedron itself needs an opinion about (see that
class's own docstring)."""
import numpy as np


def bounding_box(vertices):
    """(lo, hi) np.ndarray(3,) over a list/array of 3D points, e.g. a
    model.Polyhedron's own .vertices."""
    pts = np.array(vertices)
    return pts.min(axis=0), pts.max(axis=0)
