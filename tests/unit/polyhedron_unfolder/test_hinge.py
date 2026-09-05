from utils.polyhedron_unfolder import Hinge


def test_to_legacy_dict_matches_net_fold_core_shape():
    hinge = Hinge(parent_id=0, child_id=1, parent_edge_idx=2, child_edge_idx=0, angle=1.23)
    assert hinge.to_legacy_dict() == dict(parent=0, child=1, parent_edge_idx=2, child_edge_idx=0)
