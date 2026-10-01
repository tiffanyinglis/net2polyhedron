"""Formalizes InflaterPane's own mesh-state take/restore pair (previously
`_snapshot_mesh_state`/`_restore_mesh_state`, two loose methods) into one small `take()`/
`restore()` object (2026-09-30 modularization). The snapshot/restore MECHANISM is genuinely
isolable (a fixed list of attributes, copied in and out) -- the surrounding DECISION of when to
take one and what else to clean up on restore (the undo stack, replay history, running-flag,
status text) stays in InflaterPane's own `_revert_run`, which is too entangled with the solve
pipeline and threading state to extract alongside this.
"""

__all__ = ["MeshSnapshotManager"]

# (snapshot-dict key, subject attribute name) pairs -- the snapshot dict's own keys drop the
# leading underscore for the two private attributes, matching this dict shape's own pre-existing
# convention (kept so `_pre_click_snapshot["pending_source_polygon_id"]`-style reads elsewhere
# in app.py, e.g. face_indexer.resolve_display_state's callers, are unaffected).
_RESTORED_FIELDS = (
    ("base_faces", "base_faces"),
    ("base_edges", "base_edges"),
    ("base_face_edge_ids", "base_face_edge_ids"),
    ("faces", "faces"),
    ("edge_length", "edge_length"),
    ("face_of_fine", "face_of_fine"),
    ("edges", "edges"),
    ("positions", "positions"),
    ("subdivision_level", "subdivision_level"),
    ("pending_source_polygon_id", "_pending_source_polygon_id"),
    ("pending_pendants", "_pending_pendants"),
    ("is_fully_inflated", "is_fully_inflated"),
)


class MeshSnapshotManager:
    """Captures/restores `subject`'s own mutable mesh-related fields as one opaque snapshot
    dict -- `subject` is an InflaterPane instance (needs every attribute named in
    `_RESTORED_FIELDS` plus a `builder_getter()` method)."""

    def __init__(self, subject):
        self.subject = subject

    def take(self):
        """Every mutable mesh-related field, as of right now -- meant to be taken before a
        pipeline entry point touches any of them, so a Stop click or a non-converged trial can
        revert to exactly the state the user had when they clicked Inflate. A plain shallow copy
        is safe: every pipeline step REASSIGNS these fields wholesale (subdivide_once/relax_once/
        estimate_pressure_for_target_stretch all return fresh list/dict objects) rather than
        mutating one in place, so the objects this snapshot still points at never change out
        from under it.

        Also carries "builder_connections" -- the LIVE builder's own connections list, copied
        here too (never restored by `restore()`, which only touches the mesh fields above)
        purely so a "frozen while running" display read (face_indexer.resolve_display_state) has
        something to serve while the run is in flight: the ONE 2D edit that made a run eligible
        has already been applied to the live builder net by the time this snapshot is taken, so
        `builder.connections` itself is already the NEW list."""
        snapshot = {key: getattr(self.subject, attr) for key, attr in _RESTORED_FIELDS}
        snapshot["builder_connections"] = list(self.subject.builder_getter().connections)
        return snapshot

    def restore(self, snapshot):
        for key, attr in _RESTORED_FIELDS:
            setattr(self.subject, attr, snapshot[key])
