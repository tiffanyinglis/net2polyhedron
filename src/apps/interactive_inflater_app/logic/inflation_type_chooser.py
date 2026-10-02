"""Decides which inflate pipeline a builder edit should trigger -- moved out of
interactive_inflater_app/app.py's `on_diff_inflate_clicked` (2026-09-30 modularization). Pure
decision tree: given a `node_classifier.classify_change` verdict plus whether the just-
added shape (if any) is a pendant/terminal node and whether the active group's junction nodes
are already fully inflated, picks ONE action. `InflaterPane.on_diff_inflate_clicked` calls
`choose_action` then
dispatches to the one matching existing method -- all side effects (status labels, selection
staging, the actual solve) stay in app.py.
"""

DIFF_ELIGIBLE_KINDS = ("add_face", "remove_face", "add_connection", "remove_connection")

PENDANT_ATTACH = "pendant_attach"
FULL_INFLATE_REDIRECT = "full_inflate_redirect"
DIFF_ADD_FACE = "diff_add_face"
DIFF_REMOVE_FACE = "diff_remove_face"
DIFF_CONNECTION_CHANGE = "diff_connection_change"
UNSUPPORTED = "unsupported"

__all__ = [
    "DIFF_ELIGIBLE_KINDS", "PENDANT_ATTACH", "FULL_INFLATE_REDIRECT", "DIFF_ADD_FACE",
    "DIFF_REMOVE_FACE", "DIFF_CONNECTION_CHANGE", "UNSUPPORTED", "choose_action",
]


def choose_action(kind, extra, is_fully_inflated, is_pendant_add):
    """`kind`/`extra`: a `node_classifier.classify_change` result. `is_fully_inflated`:
    whether the active group's junction nodes currently reflect a real relax/inflate result
    (vs. only ever having been flat-attached). `is_pendant_add`: only meaningful when
    `kind == "add_face"`, whether `extra` (the newly added shape) would be a terminal node were
    this inflated right now.

    A terminal-node-only add never changes the junction nodes at all, so it always takes the
    flat-attach fast path regardless of `is_fully_inflated` (PENDANT_ATTACH). Otherwise, if the
    junction nodes were only ever geometrically placed, never really solved, and this edit
    genuinely needs real physics,
    this redirects to a full re-solve from scratch (FULL_INFLATE_REDIRECT) -- every incremental
    path below assumes it's seeding a real relax/calibration pass from an ALREADY relaxed/
    calibrated result, which a flat placement never was. Otherwise dispatches by `kind`; a
    change too complex to diff (more than one added/removed shape or connection, a moved/
    flipped shape, etc.) is UNSUPPORTED."""
    if kind == "add_face" and is_pendant_add:
        return PENDANT_ATTACH
    if not is_fully_inflated and kind in DIFF_ELIGIBLE_KINDS:
        return FULL_INFLATE_REDIRECT
    if kind == "add_face":
        return DIFF_ADD_FACE
    if kind == "remove_face":
        return DIFF_REMOVE_FACE
    if kind in ("add_connection", "remove_connection"):
        return DIFF_CONNECTION_CHANGE
    return UNSUPPORTED
