"""Color computation, moved out of inflate_polyhedron_app/app.py (2026-09-30 modularization).
Every function here is pure -- `InflaterPane`/`ViewerPane` call these by name.
"""
import matplotlib.colors as mcolors
import numpy as np

from common.ui_theme import FACE_COLORS
from utils.graph_face_coloring import random_graph_coloring
from utils.inflate_polyhedron.mesh_topology import base_face_neighbors
from utils.polygon_colors import POLYGON_COLORS

__all__ = ["INSIDE_FACE_DARKEN_FACTOR", "midpoint_color", "darken_color", "polygon_n_of_group",
           "group_of_face", "face_colors_by_group", "random_face_colors",
           "random_face_colors_by_group"]


def group_of_face(base_faces, source_polygon_id):
    """`[source_polygon_id[i] if source_polygon_id else i for i in range(len(base_faces))]` --
    which Polygon-Fold GROUP each base face belongs to (or just its own index, for a file with no
    Polygon-Fold grouping at all). Pulled out as its own function (2026-10-01, bug fix -- see
    `random_face_colors_by_group`'s own docstring) since both `face_colors_by_group` and that
    function need the exact same grouping and must never drift apart from each other."""
    return [source_polygon_id[i] if source_polygon_id else i for i in range(len(base_faces))]

# A face's INSIDE (its backface, as seen through the mesh) is drawn this fraction darker than
# its own outward-facing color (_draw_level_panel's own add_mesh backface_params) -- lets a
# user tell outside from inside at a glance.
INSIDE_FACE_DARKEN_FACTOR = 0.65


def midpoint_color(color_a, color_b):
    """RGB midpoint of two matplotlib-recognized colors, as an (r, g, b) tuple in [0, 1] --
    used for each "Level N" panel's wireframe edge color, halfway between white and that face's
    own fill color."""
    a, b = np.array(mcolors.to_rgb(color_a)), np.array(mcolors.to_rgb(color_b))
    return tuple((a + b) / 2)


def darken_color(color, factor=INSIDE_FACE_DARKEN_FACTOR):
    """`color` scaled toward black by `factor` (an (r, g, b) tuple in [0, 1]) -- same
    matplotlib-recognized-color handling as midpoint_color."""
    return tuple(np.array(mcolors.to_rgb(color)) * factor)


def polygon_n_of_group(source_polygon_id, net_layout):
    """{group: that group's ORIGINAL polygon's own side count}, from `source_polygon_id` (face
    position -> GROUP id, which is a 2D builder shape_id) and `net_layout` (a list of
    {"shape_id", "n", ...} entries, exactly as interactive_builder_app's own Save writes them --
    see apps.md's "net_layout" section) -- needed because a Polygon-Fold shape's own base
    face(s) are fan-TRIANGULATED, so `len(base_faces[group])` would read as 3 (a triangle) for
    every one of its fold-triangles instead of its real source polygon's side count (2026-10-01,
    explicit bug report: "Polygon-specific colouring is wrong. It should use the colour scheme
    in interactive_inflater, where triangles are green, and as n increases, it gradually goes to
    blue then purple" -- same reasoning as interactive_inflater_app's own face_indexer.
    group_polygon_n).

    The returned dict is keyed by GROUP id (a shape_id -- i.e. a `source_polygon_id` VALUE), not
    by face position, matching exactly what `face_colors_by_group` below looks `n_by_group` up
    by (`g`, its own `group_of_face[i]`) (2026-10-01, bug fix: "Polygon-specific colours are not
    working in Viewer view" -- this function used to key its result by `enumerate`'s own
    POSITIONAL index instead, which only coincidentally matched a group's real shape_id for a
    net where every shape_id happened to equal its own 0-based placement order; any other net
    looked up the wrong group's `n`, or missed entirely and fell back to `len(base_faces[i])`).
    Since a shape_id already IS the group id `face_colors_by_group` wants, no position bookkeeping
    is needed at all -- `n_by_shape_id` restricted to whichever shape_ids actually appear in
    `source_polygon_id` is already the exact answer.

    Returns `{}` whenever `source_polygon_id` is `None`, `net_layout` is empty, or no entry in
    it has a "shape_id" at all (a legacy, index-aligned net_layout, or no net_layout at all) --
    callers fall back to `len(base_faces[group])` for a group missing from the result, which is
    already the right side count whenever there's no Polygon-Fold to begin with."""
    if source_polygon_id is None or not net_layout:
        return {}
    n_by_shape_id = {entry["shape_id"]: entry["n"] for entry in net_layout if "shape_id" in entry}
    if not n_by_shape_id:
        return {}
    present_groups = set(source_polygon_id)
    return {g: n_by_shape_id[g] for g in present_groups if g in n_by_shape_id}


def face_colors_by_group(base_faces, source_polygon_id, n_by_group=None):
    """Returns (colors, color_by_group, group_of_face): `colors[i]` is face `i`'s color (flat
    list, same indexing as `base_faces`); `group_of_face[i]` is `source_polygon_id[i]`
    (interactive_builder_app's Polygon-Fold grouping) when given, else `i` itself (reduces to
    plain per-face coloring for a file without it); `color_by_group` is the same colors keyed by
    group id, for a caller (_draw_level_panel) grouping several base faces into one draw call.
    Every face sharing a group gets the same color.

    Colored by POLYGON_COLORS, keyed by each group's own ORIGINAL polygon side count (2026-10-01,
    explicit bug report -- see polygon_n_of_group's own docstring) -- triangle green, gradually
    through blue to purple as the side count grows, matching interactive_builder_app/
    interactive_inflater_app's identical "Polygon-specific" scheme exactly. NOT an arbitrary
    FACE_COLORS cycle by first-seen group order, which is what this used to do (the bug) and is
    still the fallback for any `n` with no POLYGON_COLORS entry (> 8 sides -- that table only
    covers 3..8). `n_by_group` ({group: n}, see the polygon_n_of_group function above), when
    given, supplies a Polygon-Fold group's real original side count; falls back to
    `len(base_faces[i])` (that group's own first-seen face) whenever it's `None` or has no entry
    for a given group -- correct whenever there's no Polygon-Fold at all, i.e. every face's own
    vertex count already IS its real polygon's side count."""
    groups_of_face = group_of_face(base_faces, source_polygon_id)
    color_by_group = {}
    colors = []
    for i, g in enumerate(groups_of_face):
        if g not in color_by_group:
            if n_by_group is not None and g in n_by_group:
                n = n_by_group[g]
            else:
                n = len(base_faces[i])
            color_by_group[g] = POLYGON_COLORS.get(n, FACE_COLORS[len(color_by_group) % len(FACE_COLORS)])
        colors.append(color_by_group[g])
    return colors, color_by_group, groups_of_face


def random_face_colors(base_faces, face_edge_ids, rng=None):
    """Colour > Multi-colour mode's ORIGINAL per-face behavior, still used by `ViewerPane` (see
    its own `apps.md` note on why Viewer mode's coloring is deliberately simplified/non-group-
    aware) -- one random color per INDIVIDUAL base face, regardless of any Polygon-Fold group,
    drawn from the same FACE_COLORS palette, chosen to avoid matching an adjacent (edge-sharing)
    face's own color wherever the palette allows it -- random_graph_coloring over
    base_face_neighbors's own adjacency. `rng` (a random.Random-compatible object) controls the
    randomization; pass a fresh one for Colour > Randomize, or omit it to use the `random`
    module's own global state. `InflaterPane`'s own Multi-colour instead uses
    `random_face_colors_by_group` below -- see its docstring."""
    neighbors = base_face_neighbors(base_faces, face_edge_ids)
    return random_graph_coloring(len(base_faces), neighbors, FACE_COLORS, rng)


def random_face_colors_by_group(base_faces, face_edge_ids, source_polygon_id, rng=None):
    """Colour > Multi-colour mode, `InflaterPane`'s own version (2026-10-01, bug fix -- reverses
    this mode's original "one random color per individual base face, not per Polygon-Fold group"
    design, which was explicitly requested when the feature was first built, after the user
    reported it looking wrong in practice: loading `cannoli_open` -- a hexagon saved as ONE
    Polygon-Fold shape, fan-triangulated into 6 base faces for solving -- showed 6 differently-
    colored triangles on the "Level N" panels for what's really one physical crocheted piece,
    while the Net panel (which only ever draws the whole hexagon as a single outline, with no
    per-triangle subdivision) showed one color, an inconsistency the user confirmed should be
    fixed by grouping instead of by keeping the per-triangle Net-panel limitation). Returns
    (colors, color_by_group, group_of_face) -- same shape as `face_colors_by_group` above, and
    using the exact same `group_of_face` helper, so a Polygon-Fold group's own `group_of_face`/
    `color_by_group` key space always agrees with Polygon-specific mode's (and with
    `net_loading.target_layout_and_connections`'s own `target_group_of_face`) regardless of which
    Colour mode is active -- `colors[i]` is face `i`'s color (flat, same indexing as
    `base_faces`); every face sharing a group gets the SAME color, picked once per group.

    Neighbor-avoidance (`random_graph_coloring`) runs at the GROUP level, not the individual-face
    level: `base_face_neighbors`' own face adjacency is collapsed onto groups first (two groups
    are neighbors iff some face of one shares an edge with some face of the other; a group's own
    INTERNAL fold edges, between its own fan triangles, never make it neighbor itself). `rng`:
    same as `random_face_colors` above."""
    groups_of_face = group_of_face(base_faces, source_polygon_id)
    groups = list(dict.fromkeys(groups_of_face))  # first-seen order
    group_index = {g: idx for idx, g in enumerate(groups)}
    face_neighbors = base_face_neighbors(base_faces, face_edge_ids)
    group_neighbors = {idx: set() for idx in range(len(groups))}
    for i, neighbors in face_neighbors.items():
        gi = group_index[groups_of_face[i]]
        for j in neighbors:
            gj = group_index[groups_of_face[j]]
            if gj != gi:
                group_neighbors[gi].add(gj)
    group_colors = random_graph_coloring(len(groups), group_neighbors, FACE_COLORS, rng)
    color_by_group = {g: group_colors[group_index[g]] for g in groups}
    colors = [color_by_group[g] for g in groups_of_face]
    return colors, color_by_group, groups_of_face
