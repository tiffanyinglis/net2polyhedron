"""Pure face hover/selection set arithmetic, moved out of InflaterPane (2026-09-30
modularization) -- the VTK actor-building (`_apply_hover_highlight`/`_apply_selection_highlight`)
stays in app.py; this module only owns the "what should the new selection/hover SET be" decision.
"""

__all__ = ["toggle_selection", "effective_hover_groups"]


def toggle_selection(current_ids, clicked_id, additive):
    """New selection set after clicking `clicked_id` (never None -- callers handle "nothing was
    under the cursor" themselves). Replaces the current selection with `{clicked_id}` unless
    `additive` (ctrl held, 2026-09-19 explicit: "multiselect by holding down ctrl and clicking on
    multiple faces"), in which case toggles `clicked_id` in/out of `current_ids`."""
    if additive:
        new_ids = set(current_ids)
        new_ids.symmetric_difference_update({clicked_id})
        return new_ids
    return {clicked_id}


def effective_hover_groups(requested_groups, groups_present, selected_groups):
    """The actually-highlighted hover set: `requested_groups` filtered down to groups that still
    exist (`groups_present`, guards against a diff pipeline path having renumbered the mesh out
    from under a cached hover request), MINUS whatever's currently selected (2026-09-19,
    explicit: "when you hover then select, the face should go from being highlighted (yellow) to
    being selected (red) [don't draw both]")."""
    return (frozenset(requested_groups) & groups_present) - selected_groups
