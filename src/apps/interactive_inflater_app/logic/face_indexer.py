"""Group (3D base-face index) <-> shape_id (2D builder shape) mapping, moved out of
InflaterPane (2026-09-30 modularization) -- this is what keeps the 2D canvas and the 3D panel
"matching": every 3D base face belongs to a "group" (an index into `base_faces`/
`pending_source_polygon_id`), and `pending_source_polygon_id[group]` names which 2D builder
shape that group came from (several groups can share one shape_id, for a Polygon-Fold shape's
fan triangles).

Every function here is pure (no Tkinter/VTK/`self`) -- `InflaterPane` calls these by name,
passing its own `self.*` state, and keeps only the "frozen while a run is in progress" snapshot
rule as a thin per-field wrapper (`_display_pending_source_polygon_id`/etc.).
"""

__all__ = [
    "resolve_display_state", "shape_id_of_group", "group_polygon_n", "groups_for_shape_ids",
    "groups_present",
]


def resolve_display_state(current, running, snapshot, key):
    """The shared "use the frozen pre-click snapshot while a run is in progress" rule
    (2026-09-29, explicit bug report: "when i make a change, while inflation is still going,
    sometimes hovering over objects will yield weird results... when inflation is still ongoing,
    selection/hovering should use the model BEFORE the change was made"). While a pipeline is
    running, `self.pending_source_polygon_id`/`face_of_fine`/the live builder connections all
    already describe the NEW (post-edit) mesh, well before the run's own background thread even
    starts, but the panel is still actually SHOWING the OLD one -- so hover/click during that
    window must resolve against `snapshot` (the OLD, still-displayed state captured right before
    the run touched anything), not `current`. Returns `current` whenever `running` is False or
    `snapshot` is None (nothing to freeze against)."""
    if running and snapshot is not None:
        return snapshot[key]
    return current


def shape_id_of_group(group, source_polygon_id):
    """The 2D builder shape_id that 3D base-face index `group` came from, or None if `group` is
    None or out of range (a transient state, not an error -- see callers)."""
    if group is not None and source_polygon_id is not None and group < len(source_polygon_id):
        return source_polygon_id[group]
    return None


def group_polygon_n(group, source_polygon_id, shapes, base_faces):
    """Side count to key POLYGON_COLORS with for base face `group` -- the ORIGINAL 2D shape's
    own `n` (via source_polygon_id), not `len(base_faces[group])`, since a Polygon-Fold shape's
    fan triangles each have their OWN base face with only 3 sides, which would otherwise color
    every fold-triangle as a triangle instead of as its real source polygon (2026-09-29, explicit
    bug report: a self-joined hexagon showed green, not the hexagon's own purple). Falls back to
    `len(base_faces[group])` whenever the shape lookup fails (no source_polygon_id yet, or a
    shape_id the builder no longer has -- both legitimate transient states, not errors)."""
    shape_id = shape_id_of_group(group, source_polygon_id)
    if shape_id is not None:
        shape = next((s for s in shapes if s["id"] == shape_id), None)
        if shape is not None:
            return shape["n"]
    return len(base_faces[group])


def groups_for_shape_ids(shape_ids, source_polygon_id):
    """Every 3D group whose own source_polygon_id is one of `shape_ids` -- usually one group per
    shape_id, but a Polygon-Fold shape's several triangle groups all share one source_polygon_id,
    so this can return more entries than `shape_ids` has."""
    if not shape_ids or source_polygon_id is None:
        return set()
    return {g for g, sid in enumerate(source_polygon_id) if sid in shape_ids}


def groups_present(face_of_fine):
    """Every group index that actually exists in `face_of_fine` right now -- used to filter out
    STALE group numbers before they reach the boundary/highlight machinery (2026-09-19, explicit
    crash report: deleting two faces from a dodecahedron sometimes raised "Empty meshes cannot be
    plotted", then left hover highlighting a different face than the one under the cursor)."""
    return set(face_of_fine or ())
