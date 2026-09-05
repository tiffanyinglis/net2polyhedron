"""Hinge: one fold hinge, joining a parent face to a child face along one
edge of each. `parent_id`/`child_id` are positions in a Polyhedron's own
`faces` list (there's no separate "id" concept above that -- see
net_unfolder.py/model.Polyhedron). Canonically identified by `child_id`
(matching how fold_angles keys things in net_fold_core.py's fold engine) --
the scipy optimization vector's positional indexing that used to live in
the now-deleted fold_solver.py is gone entirely, since fold angles are read
directly off the given geometry now (see net_unfolder.py)."""


class Hinge:
    def __init__(self, parent_id, child_id, parent_edge_idx, child_edge_idx, angle=None):
        self.parent_id = parent_id
        self.child_id = child_id
        self.parent_edge_idx = parent_edge_idx
        self.child_edge_idx = child_edge_idx
        self.angle = angle  # radians, rotation-from-flat, i.e. the dihedral-derived fold angle

    def to_legacy_dict(self):
        """The dict shape net_fold_core.fold()/fold_transforms() expect --
        used only at the boundary into that unchanged code."""
        return dict(parent=self.parent_id, child=self.child_id,
                     parent_edge_idx=self.parent_edge_idx,
                     child_edge_idx=self.child_edge_idx)

    def __repr__(self):
        return (f"Hinge(parent={self.parent_id}, child={self.child_id}, "
                f"angle={self.angle!r})")
