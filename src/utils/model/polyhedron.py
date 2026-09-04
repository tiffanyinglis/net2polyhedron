"""Polyhedron: pure 3D solid geometry -- shared, indexed vertices; faces as
CCW (viewed from outside) vertex-index tuples; edges as vertex-index pairs,
derived from faces. Knows nothing about nets, hinges, roots, fold progress,
or color -- those all belong to PolyhedralNet (the pre-fold flat net + hinge
tree) and to whatever renders a Polyhedron, not to this class.

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

    @property
    def is_closed(self):
        """True iff every edge (by vertex-index pair) appears in exactly 2
        faces -- pure integer counting, no float tolerance anywhere (unlike
        net_fold_core.is_closed_solid, which has to match raw 3D points
        since it has no vertex indices to work with)."""
        counts = {}
        for face in self.faces:
            k = len(face)
            for i in range(k):
                a, b = face[i], face[(i + 1) % k]
                key = (a, b) if a < b else (b, a)
                counts[key] = counts.get(key, 0) + 1
        return all(count == 2 for count in counts.values())

    def bounding_box(self):
        """(lo, hi) np.ndarray(3,) over self.vertices."""
        pts = np.array(self.vertices)
        return pts.min(axis=0), pts.max(axis=0)

    def __repr__(self):
        return f"Polyhedron(name={self.name!r}, vertices={len(self.vertices)}, faces={len(self.faces)})"
