"""Hinge: one fold hinge, joining a parent face to a child face along one
edge of each. Canonically identified by `child_id` (matching how
fold_angles/precompute_subtree_map already key things in the untouched
net_fold_core.py/fold_solver.py internals) -- the scipy optimization
vector's positional indexing inside fold_solver.solve_fold_angles is a
private detail of that module and never leaves it."""


class Hinge:
    def __init__(self, parent_id, child_id, parent_edge_idx, child_edge_idx, angle=None):
        self.parent_id = parent_id
        self.child_id = child_id
        self.parent_edge_idx = parent_edge_idx
        self.child_edge_idx = child_edge_idx
        self.angle = angle  # radians, rotation-from-flat target; None until solved

    def to_legacy_dict(self):
        """The dict shape net_fold_core.fold()/net_fold_core.Net.build_tree()
        expect -- used only at the boundary into that unchanged code."""
        return dict(parent=self.parent_id, child=self.child_id,
                     parent_edge_idx=self.parent_edge_idx,
                     child_edge_idx=self.child_edge_idx)

    def __repr__(self):
        return (f"Hinge(parent={self.parent_id}, child={self.child_id}, "
                f"angle={self.angle!r})")
