"""Color computation, moved out of inflate_polyhedron_app/app.py (2026-09-30 modularization).
Every function here is pure -- `InflaterPane`/`ViewerPane` call these by name.
"""
import matplotlib.colors as mcolors
import numpy as np

from common.ui_theme import FACE_COLORS

__all__ = ["INSIDE_FACE_DARKEN_FACTOR", "midpoint_color", "darken_color", "face_colors_by_group"]

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


def face_colors_by_group(n_faces, source_polygon_id):
    """Returns (colors, color_by_group, group_of_face): `colors[i]` is face `i`'s color (flat
    list, same indexing as `base_faces`); `group_of_face[i]` is `source_polygon_id[i]`
    (interactive_builder_app's Polygon-Fold grouping) when given, else `i` itself (reduces to
    plain per-face coloring for a file without it); `color_by_group` is the same colors keyed by
    group id, for a caller (_draw_level_panel) grouping several base faces into one draw call.
    Every face sharing a group gets the same color; first-seen group order picks which
    FACE_COLORS entry each group gets."""
    group_of_face = [source_polygon_id[i] if source_polygon_id else i for i in range(n_faces)]
    color_by_group = {}
    colors = []
    for g in group_of_face:
        if g not in color_by_group:
            color_by_group[g] = FACE_COLORS[len(color_by_group) % len(FACE_COLORS)]
        colors.append(color_by_group[g])
    return colors, color_by_group, group_of_face
