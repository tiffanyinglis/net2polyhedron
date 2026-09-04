"""Face: one polygon face -- its combinatorial identity (id, sides), its
color, and whichever geometry it currently has: 2D net-layout coordinates
(pre-fold), 3D folded coordinates (post-fold), or both."""
import copy

from ..geometry3d.net_fold_core import face_normal


class Face:
    def __init__(self, face_id, sides=None, vertices2d=None, vertices3d=None, color=None):
        self.id = face_id
        self.sides = sides if sides is not None else (
            len(vertices2d) if vertices2d is not None else None)
        self.vertices2d = vertices2d   # list[np.ndarray(2,)] or None
        self.vertices3d = vertices3d   # np.ndarray(sides,3) or None
        self.color = color

    def edge2d(self, edge_idx):
        """(p1, p2) -- this face's 2D polygon edge `edge_idx` (vertex
        edge_idx -> edge_idx+1)."""
        pts = self.vertices2d
        return pts[edge_idx], pts[(edge_idx + 1) % len(pts)]

    def edge3d(self, edge_idx):
        """(p1, p2) -- this face's 3D (folded) polygon edge `edge_idx`."""
        pts = self.vertices3d
        return pts[edge_idx], pts[(edge_idx + 1) % len(pts)]

    def normal(self):
        """Outward unit normal of the folded face -- thin wrapper over
        net_fold_core.face_normal, unchanged."""
        return face_normal(self.vertices3d)

    def with_vertices3d(self, vertices3d):
        """A shallow copy of this face with vertices3d set. Used by
        PolyhedralNet.fold() to produce a Polyhedron's faces without
        mutating this (net-layout) face, so the same PolyhedralNet can be
        folded at many different t's (e.g. a slider drag) without one
        fold's result stepping on another's -- and `color` (and any other
        attribute) travels forward for free via the copy."""
        new = copy.copy(self)
        new.vertices3d = vertices3d
        return new

    def __repr__(self):
        return f"Face(id={self.id}, sides={self.sides}, color={self.color!r})"
