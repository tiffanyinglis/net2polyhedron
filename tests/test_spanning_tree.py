import pytest

from net_fold_utils.spanning_tree import split_spanning_tree

TETRAHEDRON_EDGES = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]


def test_split_spanning_tree_partitions_all_edges():
    net_edges, extra_edges = split_spanning_tree(4, TETRAHEDRON_EDGES, root=0)
    assert len(net_edges) == 3  # a tree over 4 nodes has 3 edges
    assert len(extra_edges) == 3
    assert len(net_edges) + len(extra_edges) == len(TETRAHEDRON_EDGES)

    # every original edge appears in exactly one of the two lists
    net_set = {frozenset(e) for e in net_edges}
    extra_set = {frozenset(e) for e in extra_edges}
    all_set = {frozenset(e) for e in TETRAHEDRON_EDGES}
    assert net_set | extra_set == all_set
    assert not (net_set & extra_set)


def test_split_spanning_tree_reaches_every_node_from_root():
    net_edges, _ = split_spanning_tree(4, TETRAHEDRON_EDGES, root=2)
    reached = {2}
    changed = True
    while changed:
        changed = False
        for a, b in net_edges:
            if a in reached and b not in reached:
                reached.add(b)
                changed = True
            elif b in reached and a not in reached:
                reached.add(a)
                changed = True
    assert reached == {0, 1, 2, 3}


def test_split_spanning_tree_rejects_disconnected_graph():
    with pytest.raises(ValueError, match="disconnected"):
        split_spanning_tree(4, [(0, 1)], root=0)
