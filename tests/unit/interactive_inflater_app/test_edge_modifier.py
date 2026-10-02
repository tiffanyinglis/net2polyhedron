from interactive_inflater_app.logic import edge_modifier as em


def test_is_orphan_to_orphan_join_blocks_two_unreachable_nodes():
    central_ids = frozenset({1})
    assert em.is_orphan_to_orphan_join(2, 3, central_ids) is True


def test_is_orphan_to_orphan_join_allows_joining_the_active_group():
    central_ids = frozenset({1})
    assert em.is_orphan_to_orphan_join(1, 2, central_ids) is False


def test_is_orphan_to_orphan_join_ignores_self_fold():
    central_ids = frozenset()
    assert em.is_orphan_to_orphan_join(5, 5, central_ids) is False


def test_current_root_to_vertex_id_empty_without_central_or_mesh():
    assert em.current_root_to_vertex_id(frozenset(), [], [], None, None) == {}
    assert em.current_root_to_vertex_id(frozenset({1}), [], [], None, None) == {}


def test_current_root_to_vertex_id_maps_real_ids():
    shapes = [{"id": 1, "n": 3, "cx": 0, "cy": 0, "rotation": 0}]
    connections = []
    base_faces = [[100, 101, 102]]
    pending_source_polygon_id = [1]
    result = em.current_root_to_vertex_id(
        frozenset({1}), shapes, connections, base_faces, pending_source_polygon_id)
    assert set(result.values()) == {100, 101, 102}


def test_old_atomic_slot_to_id_empty_without_snapshot():
    assert em.old_atomic_slot_to_id(None, None, None, {}) == {}
    assert em.old_atomic_slot_to_id([{"id": 1}], [], 1, None) == {}


def test_old_atomic_slot_to_id_maps_slots_to_real_ids():
    shapes = [{"id": 1, "n": 3, "cx": 0, "cy": 0, "rotation": 0}]
    connections = []
    last_root_to_vertex_id = em.current_root_to_vertex_id(
        frozenset({1}), shapes, connections, [[100, 101, 102]], [1])
    result = em.old_atomic_slot_to_id(shapes, connections, 1, last_root_to_vertex_id)
    assert set(result.values()) == {100, 101, 102}
    assert len(result) == 3  # one entry per corner (1, 0), (1, 1), (1, 2)
