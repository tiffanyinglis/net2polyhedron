"""Polyhedron: pure 3D solid geometry -- shared, indexed vertices; faces as
CCW (viewed from outside) vertex-index tuples; edges as vertex-index pairs,
derived from faces. Knows nothing about nets, hinges, roots, fold progress,
or color -- those all belong to PolyhedralNet (the pre-fold flat net + hinge
tree) and to whatever renders a Polyhedron, not to this class. In that
spirit, whether a Polyhedron is actually closed is a net_unfolder concern
(net_unfolder.is_closed(polyhedron) -- closure is a fact about fold
progress, not about the geometry alone), and bounding_box() is a rendering
helper (apps/common/bounding_box.py) rather than a method here.

PolyhedralNet.fold(t) is what produces one of these, at any fold progress t
(not just t=1) -- see its docstring for how per-face-corner points get
merged into this class's shared vertex indices."""
import numpy as np

from ..geometry3d.net_fold_core import face_normal as _face_normal


class Polyhedron:
    def __init__(self, vertices, faces, name=None):
        self.vertices = vertices   # list[np.ndarray(3,)]
        self.faces = faces         # list[tuple[int, ...]], CCW from outside
        self.name = name
        self._edges = None

    def face_vertices(self, face_index):
        """np.ndarray(k,3) -- this face's own vertex positions, in order."""
        return np.array([self.vertices[i] for i in self.faces[face_index]])

    def face_normal(self, face_index):
        """Outward unit normal -- reuses net_fold_core.face_normal's cross-
        product formula on this face's own gathered vertex positions."""
        return _face_normal(self.face_vertices(face_index))

    @property
    def edges(self):
        """list[tuple[int,int]] (small index first), derived from faces --
        not separately stored, so it can never disagree with them."""
        if self._edges is None:
            edge_set = set()
            for face in self.faces:
                k = len(face)
                for i in range(k):
                    a, b = face[i], face[(i + 1) % k]
                    edge_set.add((a, b) if a < b else (b, a))
            self._edges = sorted(edge_set)
        return self._edges

    def __repr__(self):
        return f"Polyhedron(name={self.name!r}, vertices={len(self.vertices)}, faces={len(self.faces)})"
