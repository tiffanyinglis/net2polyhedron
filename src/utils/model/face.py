"""Face: one polygon face of the flat, pre-fold 2D net layout -- its
combinatorial identity (id, sides), its color, and its net-space 2D
coordinates. Purely 2D: PolyhedralNet.fold() is what turns a whole net's
worth of these (plus the hinge tree) into a 3D model.Polyhedron -- this
class itself carries no 3D information."""


class Face:
    def __init__(self, face_id, sides=None, vertices2d=None, color=None):
        self.id = face_id
        self.sides = sides if sides is not None else (
            len(vertices2d) if vertices2d is not None else None)
        self.vertices2d = vertices2d   # list[np.ndarray(2,)] or None
        self.color = color

    def edge2d(self, edge_idx):
        """(p1, p2) -- this face's 2D polygon edge `edge_idx` (vertex
        edge_idx -> edge_idx+1)."""
        pts = self.vertices2d
        return pts[edge_idx], pts[(edge_idx + 1) % len(pts)]

    def __repr__(self):
        return f"Face(id={self.id}, sides={self.sides}, color={self.color!r})"
