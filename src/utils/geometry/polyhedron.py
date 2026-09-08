"""Polyhedron: pure 3D solid geometry -- shared, indexed vertices; faces
as CCW (viewed from outside) vertex-index tuples; edges derived from
faces. Knows nothing about nets, hinges, fold progress, or color -- those
belonged to the now-removed rigid-unfolding pipeline (see the sibling
polyhedron-unfolder project). `face_normal` is inlined here rather than
shared with a fold engine, since net2polyhedron has none of its own."""
import numpy as np


def face_normal(points):
    """Outward unit normal of a planar CCW polygon face, via the cross
    product of its first two edges."""
    p0, p1, p2 = points[0], points[1], points[2]
    n = np.cross(p1 - p0, p2 - p0)
    return n / np.linalg.norm(n)


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
        """Outward unit normal of this face."""
        return face_normal(self.face_vertices(face_index))

    def is_closed(self):
        """True iff every edge (by vertex-index pair) appears in exactly
        2 faces -- pure integer counting, no float tolerance anywhere."""
        counts = {}
        for face in self.faces:
            k = len(face)
            for i in range(k):
                a, b = face[i], face[(i + 1) % k]
                key = (a, b) if a < b else (b, a)
                counts[key] = counts.get(key, 0) + 1
        return all(count == 2 for count in counts.values())

    def compute_face_adjacency(self):
        """list of (face_a, edge_idx_a, face_b, edge_idx_b), one entry per
        shared edge -- found via the CCW-from-outside winding convention:
        a shared edge is v->w on one face, w->v on the other. A face edge
        with no match (an open net's boundary edge) is simply omitted."""
        edge_owner = {}
        for fi, face in enumerate(self.faces):
            k = len(face)
            for ei in range(k):
                a, b = face[ei], face[(ei + 1) % k]
                edge_owner[(a, b)] = (fi, ei)

        adjacency = []
        seen_edges = set()
        for fi, face in enumerate(self.faces):
            k = len(face)
            for ei in range(k):
                a, b = face[ei], face[(ei + 1) % k]
                match = edge_owner.get((b, a))
                if match is None:
                    continue
                edge_key = frozenset({(fi, ei), match})
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                adjacency.append((fi, ei, match[0], match[1]))
        return adjacency

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
