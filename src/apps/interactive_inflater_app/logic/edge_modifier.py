"""Connection-level validity + vertex-identity continuity across edits, moved out of
BuilderPane/InflaterPane (2026-09-30 modularization).

Every function here is pure (no Tkinter/`self`) -- callers pass their own shapes/connections/
snapshots directly.
"""
from interactive_builder_app.app import _expand_folded_shapes, _shape_face_corner_order, _vertex_roots
from interactive_inflater_app.logic.node_classifier import central_shape_ids

__all__ = ["is_orphan_to_orphan_join", "current_root_to_vertex_id", "old_atomic_slot_to_id"]


def is_orphan_to_orphan_join(a_shape_id, b_shape_id, central_ids):
    """True iff `a_shape_id`/`b_shape_id` are two DIFFERENT shapes, NEITHER of which is
    currently part of the live central object (2026-09-26, explicit: "it's permitted for there
    to be more than one unconnected piece, BUT they cannot be connected to one another. they can
    only be connected to the main group"). A Polygon Fold connection (`a_shape_id == b_shape_id`,
    folding one shape onto itself) is never affected -- it can't change which PIECES are
    connected to which at all, so it's excluded outright."""
    if a_shape_id == b_shape_id:
        return False
    return a_shape_id not in central_ids and b_shape_id not in central_ids


def current_root_to_vertex_id(central_ids, shapes, connections, base_faces,
                               pending_source_polygon_id):
    """Same {root_slot: vertex_id} shape as BuilderPane.root_to_vertex_id() (see its own
    docstring for what a root_slot is/why it's stable) -- but every value is the REAL vertex id
    `base_faces` actually uses RIGHT NOW, not a fresh export's own deterministic sequential
    numbering. A fresh export's numbering has NO knowledge of a pendant's own arbitrary
    flat-attach id remapping -- using it directly as a positions lookup key silently matched some
    UNRELATED vertex that happened to share the same small integer id whenever a pendant/
    terminal node was involved (2026-09-29, explicit bug report, confirmed via the debug replay
    slider: a terminal node promoted from pendant to junction node mid-Diff-Inflate got seeded
    from a random vertex on the opposite side of the mesh).

    Walks `pending_source_polygon_id`/`base_faces` (the CURRENT, already correct ids -- pendant-
    remapped or not, doesn't matter) group by group, matching each group's shape id back to its
    own expanded_shapes/roots entry (same central_shape_ids/_expand_folded_shapes/_vertex_roots
    pipeline `root_to_vertex_id`'s own traversal uses) -- then reads the REAL id straight off
    `base_faces[group][corner]` instead of assigning a fresh sequential one. Ambiguous (silently
    skipped) for a Polygon-Fold shape split into several expanded_shapes sharing one
    source_polygon_id."""
    if not central_ids or not base_faces or pending_source_polygon_id is None:
        return {}
    central_shapes = [s for s in shapes if s["id"] in central_ids]
    central_connections = [c for c in connections
                            if c["a_shape"] in central_ids and c["b_shape"] in central_ids]
    expanded_shapes, expanded_connections, _spid = _expand_folded_shapes(
        central_shapes, central_connections)
    roots = _vertex_roots(expanded_shapes, expanded_connections)
    shape_by_id = {s["id"]: s for s in expanded_shapes}
    vertex_ids = {}
    for group, spid in enumerate(pending_source_polygon_id):
        if group >= len(base_faces):
            continue
        shape = shape_by_id.get(spid)
        if shape is None:
            continue
        corners = _shape_face_corner_order(shape)
        face = base_faces[group]
        if len(corners) != len(face):
            continue
        for corner, real_id in zip(corners, face):
            root = roots.get((shape["id"], corner))
            if root is not None:
                vertex_ids[root] = real_id
    return vertex_ids


def old_atomic_slot_to_id(last_shapes_snapshot, last_connections_snapshot, last_anchor_snapshot,
                           last_root_to_vertex_id):
    """{(shape_id, corner): real_vertex_id} for every ATOMIC corner slot in the net as of the
    last completed inflate -- unlike `last_root_to_vertex_id` itself (keyed by ROOT slot only,
    one entry per glued GROUP), this has one entry per individual corner, letting a diff re-solve
    recover a vertex's old position even when that corner's group didn't keep the same root slot
    across the edit (2026-09-29, explicit bug report).

    Re-expands `last_shapes_snapshot`/`last_connections_snapshot` (restricted to their OWN
    central object, exactly like `current_root_to_vertex_id`'s live equivalent) rather than
    reusing any of the caller's current-state fields -- the whole point is a snapshot of the net
    as it stood at the LAST successful inflate, independent of whatever's been edited since.
    Every slot's root is looked up in `last_root_to_vertex_id` to get its real id; a root with no
    entry there (shouldn't normally happen) is silently skipped rather than raising."""
    if not last_shapes_snapshot or last_root_to_vertex_id is None:
        return {}
    old_central = central_shape_ids(
        last_shapes_snapshot, last_connections_snapshot, last_anchor_snapshot)
    if not old_central:
        return {}
    old_shapes = [s for s in last_shapes_snapshot if s["id"] in old_central]
    old_connections = [c for c in last_connections_snapshot
                        if c["a_shape"] in old_central and c["b_shape"] in old_central]
    expanded_shapes, expanded_connections, _spid = _expand_folded_shapes(
        old_shapes, old_connections)
    roots = _vertex_roots(expanded_shapes, expanded_connections)
    return {slot: last_root_to_vertex_id[root] for slot, root in roots.items()
            if root in last_root_to_vertex_id}
