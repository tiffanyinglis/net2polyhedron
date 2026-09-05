"""Core engine for folding a polygonal net into a 3D solid.

A flat net is a dict[face_id -> 2D points]; the caller
(unfoldable_polyhedron.py) supplies the hinge tree (list of Hinge) saying
which faces connect and by how much. Folding walks that tree from a root
face, composing each hinge's rotation with its parent's transform into
one cumulative 4x4 matrix per face -- see fold_transforms().
"""

import numpy as np

from scipy.spatial.transform import Rotation


class Hinge:
    """One fold hinge joining a parent face to a child face along an edge
    of each. Identified by `child_id`, since a face's fold angle is keyed
    on which face is rotating."""

    def __init__(self, parent_id, child_id, parent_edge_idx, child_edge_idx, angle=None):
        self.parent_id = parent_id
        self.child_id = child_id
        self.parent_edge_idx = parent_edge_idx
        self.child_edge_idx = child_edge_idx
        self.angle = angle  # radians, rotation-from-flat, i.e. the dihedral-derived fold angle

    def __repr__(self):
        return (f"Hinge(parent={self.parent_id}, child={self.child_id}, "
                f"angle={self.angle!r})")


def hinge_transform(axis_point, axis_dir, angle):
    """4x4 affine matrix rotating by `angle` radians about the 3D line
    through axis_point with direction axis_dir, so it composes with
    other such matrices via plain matrix multiplication."""
    axis_dir = axis_dir / np.linalg.norm(axis_dir)
    R = Rotation.from_rotvec(axis_dir * angle).as_matrix()
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = axis_point - R @ axis_point
    return M


def face_normal(points):
    """Outward unit normal of a planar CCW polygon face, via the cross
    product of its first two edges."""
    p0, p1, p2 = points[0], points[1], points[2]
    n = np.cross(p1 - p0, p2 - p0)
    return n / np.linalg.norm(n)


def fold_transforms(flat, root, hinges, t, fold_signs=None):
    """Returns dict face_index -> 4x4 transform at fold progress t in
    [0, 1], mapping each face's flat (z=0) points to their 3D position at t.

    - flat: object with .vertices/.faces (Polyhedron-shaped)
    - hinges: list[Hinge], each with parent_id/child_id/angle
      (rotation-from-flat in radians, defaulting to pi/2)
    - fold_signs: optional dict child_face_index -> +1/-1 to flip fold direction

    Root gets the identity. Each hinge's axis is the parent's own edge
    mapped through the parent's already-computed transform, so hinges
    must be processed in BFS order."""
    fold_signs = fold_signs or {}
    transforms = {root: np.eye(4)}
    for h in hinges:
        parent, child = h.parent_id, h.child_id
        pi = h.parent_edge_idx
        parent_face = flat.faces[parent]
        p1 = np.array([*flat.vertices[parent_face[pi]], 1.0])
        p2 = np.array([*flat.vertices[parent_face[(pi + 1) % len(parent_face)]], 1.0])

        M_parent = transforms[parent]
        axis_point = (M_parent @ p1)[:3]
        axis_dir = M_parent[:3, :3] @ (p2 - p1)[:3]

        sign = fold_signs.get(child, 1)
        base_angle = h.angle if h.angle is not None else np.pi / 2
        angle = base_angle * t * sign

        transforms[child] = hinge_transform(axis_point, axis_dir, angle) @ M_parent
    return transforms
