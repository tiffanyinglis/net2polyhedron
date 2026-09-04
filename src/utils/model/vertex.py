"""Vertex: one of a Polyhedron's actual distinct 3D corners -- merges the
several per-face-corner points net_fold_core.fold() produces for what is
geometrically one point (see net_fold_core.distinct_vertices). A derived
value object, not a graph node Face holds shared references to: the fold
engine computes each face's corners independently via its own hinge-
rotation chain, so two faces' corners landing on the "same" 3D point is a
fold-time geometric coincidence, not a static combinatorial fact -- there
is no vertex identity to assign before folding. `id` is just this list's
position and has no meaning outside the one Polyhedron it came from."""


class Vertex:
    def __init__(self, vertex_id, position):
        self.id = vertex_id
        self.position = position  # np.ndarray(3,)

    def __repr__(self):
        return f"Vertex({self.id}, {self.position!r})"
