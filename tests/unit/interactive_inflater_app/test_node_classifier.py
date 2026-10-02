from interactive_inflater_app.logic import node_classifier as nc


def _shape(sid, n=4, flipped=False):
    return {"id": sid, "n": n, "flipped": flipped}


def _conn(a_shape, a_edge, b_shape, b_edge, cid=None):
    return {"id": cid if cid is not None else (a_shape, a_edge, b_shape, b_edge),
            "a_shape": a_shape, "a_edge": a_edge, "b_shape": b_shape, "b_edge": b_edge}


def test_shape_connected_components_groups_by_connection():
    shapes = [_shape(1), _shape(2), _shape(3)]
    connections = [_conn(1, 0, 2, 0)]
    components = nc.shape_connected_components(shapes, connections)
    assert {1, 2} in components
    assert {3} in components


def test_central_shape_ids_is_anchors_own_component():
    shapes = [_shape(1), _shape(2), _shape(3)]
    connections = [_conn(1, 0, 2, 0)]
    assert nc.central_shape_ids(shapes, connections, 1) == frozenset({1, 2})
    assert nc.central_shape_ids(shapes, connections, 3) == frozenset({3})


def test_central_shape_ids_empty_when_anchor_missing():
    assert nc.central_shape_ids([], [], 1) == frozenset()


def test_connection_key_ignores_endpoint_order():
    a = _conn(1, 0, 2, 1)
    b = _conn(2, 1, 1, 0)
    assert nc.connection_key(a) == nc.connection_key(b)


def test_classify_change_none_when_nothing_changed():
    shapes = [_shape(1), _shape(2)]
    connections = [_conn(1, 0, 2, 0)]
    kind, extra = nc.classify_change(shapes, connections, 1, shapes, connections, 1)
    assert (kind, extra) == ("none", None)


def test_classify_change_add_face():
    old_shapes = [_shape(1)]
    new_shapes = [_shape(1), _shape(2)]
    new_connections = [_conn(1, 0, 2, 0)]
    kind, extra = nc.classify_change(old_shapes, [], 1, new_shapes, new_connections, 1)
    assert (kind, extra) == ("add_face", 2)


def test_classify_change_remove_face():
    old_shapes = [_shape(1), _shape(2)]
    old_connections = [_conn(1, 0, 2, 0)]
    new_shapes = [_shape(1)]
    kind, extra = nc.classify_change(old_shapes, old_connections, 1, new_shapes, [], 1)
    assert kind == "remove_face"
    assert extra == frozenset({2})


def test_classify_change_add_and_remove_connection():
    # 2 and 3 are each already reachable via their own connection to anchor 1 -- adding/removing
    # the EXTRA 2-3 connection changes neither's reachability, isolating a pure connection edit.
    shapes = [_shape(1), _shape(2), _shape(3)]
    base_connections = [_conn(1, 0, 2, 0), _conn(1, 1, 3, 0)]
    extra_connection = _conn(2, 1, 3, 1)
    old_connections = base_connections
    new_connections = base_connections + [extra_connection]
    kind, extra = nc.classify_change(shapes, old_connections, 1, shapes, new_connections, 1)
    assert kind == "add_connection"
    kind, extra = nc.classify_change(shapes, new_connections, 1, shapes, old_connections, 1)
    assert kind == "remove_connection"


def test_classify_change_complex_on_shape_edit_or_never_inflated():
    old_shapes = [_shape(1, n=4)]
    new_shapes = [_shape(1, n=5)]
    assert nc.classify_change(old_shapes, [], 1, new_shapes, [], 1) == ("complex", None)
    assert nc.classify_change(None, None, None, new_shapes, [], 1) == ("complex", None)


def test_classify_change_ignores_unreachable_nodes_outside_the_active_group():
    # A shape not connected to the anchor at all never affects the verdict.
    shapes = [_shape(1), _shape(99)]
    kind, extra = nc.classify_change(shapes, [], 1, shapes + [_shape(100)], [], 1)
    assert (kind, extra) == ("none", None)


def test_plan_anchor_deletion_blocks_a_split():
    # 1-2-3 chain; deleting the middle (anchor) would split the active group in two.
    shapes = [_shape(1), _shape(2), _shape(3)]
    connections = [_conn(1, 0, 2, 0), _conn(2, 1, 3, 0)]
    old_central = nc.central_shape_ids(shapes, connections, 2)
    allowed, new_anchor = nc.plan_anchor_deletion(shapes, connections, old_central, {2})
    assert allowed is False
    assert new_anchor is None


def test_plan_anchor_deletion_picks_best_connected_junction_node():
    # Star: 1 is anchor/hub connected to 2 and 3; 2 is also connected to 3 (junction node).
    shapes = [_shape(1), _shape(2), _shape(3)]
    connections = [_conn(1, 0, 2, 0), _conn(1, 1, 3, 0), _conn(2, 1, 3, 1)]
    old_central = nc.central_shape_ids(shapes, connections, 1)
    allowed, new_anchor = nc.plan_anchor_deletion(shapes, connections, old_central, {1})
    assert allowed is True
    assert new_anchor in (2, 3)  # both junction nodes with 2 connections among survivors


def test_plan_anchor_deletion_allows_emptying_the_whole_active_group():
    shapes = [_shape(1)]
    old_central = nc.central_shape_ids(shapes, [], 1)
    allowed, new_anchor = nc.plan_anchor_deletion(shapes, [], old_central, {1})
    assert (allowed, new_anchor) == (True, None)


def test_is_pendant_add_true_for_lone_new_terminal_node():
    connections = [_conn(10, 0, 20, 0)]
    assert nc.is_pendant_add(connections, 10) is True


def test_is_pendant_add_false_when_neighbor_promoted_to_junction_node():
    # Neighbor (20) already had one other connection before this new one -- gaining this
    # second connection promotes it from terminal node to junction node, so this is NOT a
    # pendant-only add.
    connections = [_conn(20, 1, 99, 0, cid="old"), _conn(10, 0, 20, 0, cid="new")]
    assert nc.is_pendant_add(connections, 10) is False


def test_is_pendant_add_false_when_more_than_one_connection():
    connections = [_conn(10, 0, 20, 0), _conn(10, 1, 30, 0)]
    assert nc.is_pendant_add(connections, 10) is False
