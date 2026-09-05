"""UnfoldablePolyhedron: given a Polyhedron and a spanning tree over its
face adjacency, builds the flat net once and returns the shape at any
unfold amount in [0, 1] (0 = fully folded, 1 = fully flat).

The flat net keeps each face's own private, duplicated corners rather
than merging shared vertex indices -- a hinge-glued pair of corners
always lands at the identical 3D position anyway (by construction), so
there's nothing to gain from bookkeeping the shared index.
"""
import numpy as np

from .polyhedron import Polyhedron
from .polygon_geom import rigid_transform_2d, apply_rigid
from .polyhedron_unfolder import Hinge, fold_transforms as _fold_transforms


def _project_face_to_2d(polyhedron, face_idx):
    """Projects this face's real 3D corners into an orthonormal 2D basis
    in its own plane, preserving edge lengths."""
    pts3d = polyhedron.face_vertices(face_idx)
    origin = pts3d[0]
    u = pts3d[1] - origin
    u = u / np.linalg.norm(u)
    w = polyhedron.face_normal(face_idx)
    v = np.cross(w, u)
    return np.array([[np.dot(p - origin, u), np.dot(p - origin, v)] for p in pts3d])


def _hinge_fold_angle(polyhedron, parent_idx, child_idx):
    """The rotation-from-flat angle a real dihedral angle implies --
    arccos(dot(face_normal(parent), face_normal(child)))."""
    n_p = polyhedron.face_normal(parent_idx)
    n_c = polyhedron.face_normal(child_idx)
    return np.arccos(np.clip(np.dot(n_p, n_c), -1.0, 1.0))


def _compute_fold_angles(polyhedron, tree_edges):
    """list[Hinge] -- one per tree edge, each with its fold angle (see
    _hinge_fold_angle) filled in."""
    return [Hinge(parent_id=edge["parent"], child_id=edge["child"],
                   parent_edge_idx=edge["parent_edge_idx"],
                   child_edge_idx=edge["child_edge_idx"],
                   angle=_hinge_fold_angle(polyhedron, edge["parent"], edge["child"]))
            for edge in tree_edges]


def _build_flat_layout(polyhedron, root, tree_edges):
    """Builds the flat 2D layout: each face is projected into its own
    plane, then BFS-attached to its parent's already-placed edge
    (reversed so it unfolds outward). Returns (vertices, faces),
    Polyhedron-shaped, with each face keeping its own private vertex
    block."""
    n_faces = len(polyhedron.faces)
    local2d = {fi: _project_face_to_2d(polyhedron, fi) for fi in range(n_faces)}

    placed = {root: local2d[root]}
    for edge in tree_edges:
        p, c = edge["parent"], edge["child"]
        pi, ci = edge["parent_edge_idx"], edge["child_edge_idx"]
        pverts = placed[p]
        p1, p2 = pverts[pi], pverts[(pi + 1) % len(pverts)]
        local = local2d[c]
        a, b = local[ci], local[(ci + 1) % len(local)]
        R, t = rigid_transform_2d(a, b, p2, p1)  # reversed -- unfolds outward
        placed[c] = apply_rigid(local, R, t)

    vertices2d = []
    faces_idx = []
    for fi in range(n_faces):
        start = len(vertices2d)
        vertices2d.extend(placed[fi])
        faces_idx.append(tuple(range(start, start + len(placed[fi]))))

    vertices3d = [np.array([x, y, 0.0]) for x, y in vertices2d]
    return vertices3d, faces_idx


class UnfoldablePolyhedron:
    """A Polyhedron plus its hinge tree and flat layout.
    get_unfolded_state(amount) gives the shape at any unfold amount in
    [0, 1]: 0 fully folded, 1 fully flat."""

    def __init__(self, polyhedron, spanning_tree, root=0):
        self.polyhedron = polyhedron
        self.spanning_tree = spanning_tree
        self.root = root
        self.hinges = _compute_fold_angles(polyhedron, spanning_tree)
        flat_vertices, flat_faces = _build_flat_layout(polyhedron, root, spanning_tree)
        self.flat = Polyhedron(vertices=flat_vertices, faces=flat_faces, name=polyhedron.name)

    def get_unfolded_state(self, amount_unfolded, fold_signs=None):
        """Returns a Polyhedron at this unfold amount: 0 = fully folded
        (the original polyhedron), 1 = the flat net, else a partial fold
        via each face's cumulative transform."""
        if amount_unfolded <= 0.0:
            return self.polyhedron
        if amount_unfolded >= 1.0:
            return self.flat

        t = 1.0 - amount_unfolded  # polyhedron_unfolder's own fold-progress-from-flat convention
        transforms = _fold_transforms(self.flat, self.root, self.hinges, t, fold_signs=fold_signs)

        new_vertices = list(self.flat.vertices)
        for face_idx, face in enumerate(self.flat.faces):
            M = transforms[face_idx]
            for v in face:
                p = self.flat.vertices[v]
                new_vertices[v] = (M @ np.array([*p, 1.0]))[:3]
        return Polyhedron(vertices=new_vertices, faces=self.flat.faces, name=self.polyhedron.name)

    @classmethod
    def load(cls, path):
        """Parse `path` (polyhedron_json_parser's vertices+faces
        format) into a Polyhedron, compute its face adjacency and a
        spanning tree over it (root always face index 0), and build the
        UnfoldablePolyhedron."""
        from .polyhedron_json_parser import load_polyhedron_json
        from .spanning_tree import create_spanning_tree_BFS

        vertices, faces, name = load_polyhedron_json(path)
        polyhedron = Polyhedron(vertices=vertices, faces=faces, name=name)
        adjacency = polyhedron.compute_face_adjacency()
        spanning_tree = create_spanning_tree_BFS(range(len(polyhedron.faces)), adjacency, root=0)
        return cls(polyhedron, spanning_tree, root=0)

    def __repr__(self):
        return (f"UnfoldablePolyhedron(name={self.polyhedron.name!r}, "
                f"faces={len(self.polyhedron.faces)}, hinges={len(self.hinges)})")
