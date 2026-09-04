"""Polyhedron: a realized 3D solid at some fold state t (general -- not
always t=1, since e.g. polyhedron_unfolder's "Animated Fold" tab needs
every intermediate slider state as the same shape), produced by
PolyhedralNet.fold(t). Immutable after construction -- don't mutate a
Face's vertices3d on a Polyhedron you're holding onto."""
import numpy as np

from ..geometry3d.net_fold_core import is_closed_solid, distinct_vertices
from .vertex import Vertex


class Polyhedron:
    def __init__(self, name, faces, t=1.0, root_id=None):
        self.name = name
        self.faces = faces          # dict[fid -> Face], vertices3d populated
        self.t = t
        self.root_id = root_id      # provenance only
        self._vertices = None
        self._is_closed = None

    def _verts3d_dict(self):
        """{fid: face.vertices3d} -- the shape net_fold_core.is_closed_solid/
        distinct_vertices expect."""
        return {fid: f.vertices3d for fid, f in self.faces.items()}

    @property
    def is_closed(self):
        """Wraps net_fold_core.is_closed_solid, unchanged -- what
        polyhedron_unfolder checks before applying backface culling."""
        if self._is_closed is None:
            self._is_closed = is_closed_solid(self._verts3d_dict())
        return self._is_closed

    @property
    def vertices(self):
        """list[Vertex] -- lazy, cached; wraps net_fold_core.distinct_vertices."""
        if self._vertices is None:
            merged = distinct_vertices(self._verts3d_dict())
            self._vertices = [Vertex(i, p) for i, p in enumerate(merged)]
        return self._vertices

    def bounding_box(self):
        """(lo, hi) np.ndarray(3,) -- convenience for view-centering."""
        all_pts = np.vstack([f.vertices3d for f in self.faces.values()])
        return all_pts.min(axis=0), all_pts.max(axis=0)

    def __repr__(self):
        return f"Polyhedron(name={self.name!r}, t={self.t}, faces={len(self.faces)})"
