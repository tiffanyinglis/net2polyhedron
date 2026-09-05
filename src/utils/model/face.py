"""Face: per-original-face metadata for the rigid pipeline -- id, side
count, and color. All geometry (the flat, pre-fold 2D position AND the
folded 3D position) lives in model.Polyhedron objects instead (see
PolyhedralNet.flat and PolyhedralNet.fold()) -- Face carries only the
handful of facts about one face that a Polyhedron, by design, doesn't."""


class Face:
    def __init__(self, face_id, sides, color=None):
        self.id = face_id
        self.sides = sides
        self.color = color

    def __repr__(self):
        return f"Face(id={self.id}, sides={self.sides}, color={self.color!r})"
