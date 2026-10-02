"""Net-loading decision logic, moved out of inflate_polyhedron_app/app.py's `on_select_net`/
`on_load_session_clicked` (2026-09-30 modularization). `target_layout_and_connections` was
previously duplicated verbatim between those two methods; this is a real dedup, not just
reorganization.
"""
from utils.inflate_polyhedron.self_join_triangulator import has_self_join, split_self_joined_faces
from utils.inflate_polyhedron.stretchy_net_layout import build_stretchy_net_layout

from inflate_polyhedron_app.logic.mesh_topology import layout_from_net_layout, net_layout_is_new_format

__all__ = ["resolve_base_faces", "target_layout_and_connections"]


def resolve_base_faces(faces, legacy_coarse_faces):
    """Returns (base_faces, self_join_split). A legacy fabric-subdivided net (carrying baked-in
    `legacy_coarse_faces`) is loaded at its own coarse faces -- always level 0 -- rather than its
    pre-baked fine mesh; an ordinary net has no `legacy_coarse_faces` and `faces` already is
    level 0. `self_join_split` guards a RAW/hand-authored net against a self-joined face (see
    self_join_triangulator's own docstring) -- interactive_builder_app already resolves this at
    Save time, so a net produced there never reaches here with one; this only matters for a file
    that wasn't. Only checked for the ordinary (non-legacy-fabric) case: `legacy_coarse_faces`'
    own re-derived vertex-id space is unrelated to what `faces` (and any self-join within it)
    would mean here."""
    base_faces = legacy_coarse_faces if legacy_coarse_faces is not None else faces
    self_join_split = legacy_coarse_faces is None and any(has_self_join(f) for f in base_faces)
    if self_join_split:
        base_faces = split_self_joined_faces(base_faces)
    return base_faces, self_join_split


def target_layout_and_connections(base_faces, net_file_json, self_join_split=False):
    """Returns (target_layout, target_connections, target_group_of_face) for the Net panel.
    Precomputed once per net selection/load: the Net panel's flat layout doesn't change with
    subdivision level, only its overlay does. A `net_file_json` carrying its own "net_layout"
    section (one entry per original placed shape, written by interactive_builder_app) reproduces
    that exact arrangement rather than a fresh one; otherwise (a hand-authored net, a legacy
    fabric net with no such section, or `self_join_split` -- whose re-derived vertex-id space no
    longer matches a legacy net_layout's own face-index alignment) falls back to
    `build_stretchy_net_layout`'s own BFS spanning tree over shared edges. A legacy net_layout
    (no per-entry "shape_id") must still match `base_faces`' length; a new-format one never will
    (by design, once a fold exists), so that length check doesn't apply to it. `target_connections`
    (the saved bezier connections) is only present alongside the exact "net_layout" it was saved
    with -- the BFS fallback has no matching connection geometry, so it stays None there.

    `target_group_of_face[i]` is base face `i`'s own key into `target_layout` -- NOT necessarily
    the same id space as a color mode's own `color_by_group` (2026-10-01, bug fix: a Multi-colour
    `color_by_group` is keyed by base-face POSITION regardless of this; a new-format net_layout's
    own keys are "shape_id"s from the file, which only coincidentally equal base-face position --
    e.g. a hand-authored `source_polygon_id` of `[1, 2, 3, 4, 5, 6]` KeyErrors a direct
    `color_by_group[face_idx]` lookup in Multi-colour mode, since that dict only has keys
    `0..5`). Callers needing a face_idx's color should instead rebuild a lookup from
    `target_group_of_face`/`self.colors` (a flat, mode-agnostic per-base-face list) -- see
    `_draw_target_faces`. Mirrors the SAME key space `layout_from_net_layout`/
    `build_stretchy_net_layout` actually used: `source_polygon_id` (the new-format net_layout's
    own shape_id groups) when meaningful, else plain base-face position."""
    net_layout = (net_file_json or {}).get("net_layout")
    if (net_layout is not None and not self_join_split
            and (net_layout_is_new_format(net_layout) or len(net_layout) == len(base_faces))):
        target_layout = layout_from_net_layout(base_faces, net_layout)
        target_connections = (net_file_json or {}).get("builder_connections")
        if net_layout_is_new_format(net_layout):
            source_polygon_id = (net_file_json or {}).get("source_polygon_id")
            target_group_of_face = (list(source_polygon_id) if source_polygon_id
                                     else list(range(len(base_faces))))
        else:
            target_group_of_face = list(range(len(base_faces)))
    else:
        target_layout = build_stretchy_net_layout(base_faces)
        target_connections = None
        target_group_of_face = list(range(len(base_faces)))
    return target_layout, target_connections, target_group_of_face
