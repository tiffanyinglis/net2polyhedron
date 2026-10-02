import random

from common.ui_theme import FACE_COLORS
from inflate_polyhedron_app.logic import coloring
from utils.polygon_colors import POLYGON_COLORS


def test_midpoint_color_averages_rgb():
    mid = coloring.midpoint_color("black", "white")
    assert mid == (0.5, 0.5, 0.5)


def test_darken_color_scales_toward_black():
    red = (1.0, 0.0, 0.0)
    darkened = coloring.darken_color(red, factor=0.5)
    assert darkened == (0.5, 0.0, 0.0)


def test_darken_color_default_factor():
    white = (1.0, 1.0, 1.0)
    darkened = coloring.darken_color(white)
    assert darkened == (coloring.INSIDE_FACE_DARKEN_FACTOR,) * 3


def test_face_colors_by_group_plain_per_face_without_source_polygon_id():
    # A triangle, a square, a pentagon -- no source_polygon_id, so each is its own group, colored
    # by POLYGON_COLORS keyed by its own side count (2026-10-01, explicit bug report: "Polygon-
    # specific colouring is wrong... triangles are green, and as n increases, it gradually goes
    # to blue then purple").
    base_faces = [[0, 1, 2], [3, 4, 5, 6], [7, 8, 9, 10, 11]]
    colors, color_by_group, group_of_face = coloring.face_colors_by_group(base_faces, None)
    assert group_of_face == [0, 1, 2]
    assert len(set(colors)) == 3  # a triangle/square/pentagon each get a DIFFERENT color
    assert set(color_by_group) == {0, 1, 2}
    assert colors[0] == POLYGON_COLORS[3]
    assert colors[1] == POLYGON_COLORS[4]
    assert colors[2] == POLYGON_COLORS[5]


def test_face_colors_by_group_shares_color_within_a_group():
    # Group 10 is two triangles (fan-triangulated, as a Polygon-Fold group would be); group 20
    # is two quads. Every face in a group shares that group's own first-seen face's side count.
    base_faces = [[0, 1, 2], [2, 3, 0], [4, 5, 6, 7], [7, 8, 4, 9]]
    colors, color_by_group, group_of_face = coloring.face_colors_by_group(
        base_faces, [10, 10, 20, 20])
    assert group_of_face == [10, 10, 20, 20]
    assert colors[0] == colors[1] == POLYGON_COLORS[3]
    assert colors[2] == colors[3] == POLYGON_COLORS[4]
    assert colors[0] != colors[2]
    assert set(color_by_group) == {10, 20}


def test_face_colors_by_group_uses_n_by_group_for_a_folded_shape():
    # A Polygon-Fold hexagon's own fan triangles (base_faces entries are 3-sided each) must
    # still color as a hexagon (POLYGON_COLORS[6]), not as triangles -- this is exactly what
    # n_by_group (from polygon_n_of_group) exists to fix.
    base_faces = [[0, 1, 2], [0, 2, 3], [0, 3, 4]]  # 3 fan triangles, all group 99
    source_polygon_id = [99, 99, 99]
    n_by_group = {99: 6}
    colors, color_by_group, _ = coloring.face_colors_by_group(
        base_faces, source_polygon_id, n_by_group)
    assert color_by_group[99] == POLYGON_COLORS[6]
    assert all(c == POLYGON_COLORS[6] for c in colors)


def test_polygon_n_of_group_and_face_colors_by_group_integrate_correctly():
    # End-to-end: polygon_n_of_group's own real output fed straight into face_colors_by_group,
    # with group ids (shape_ids 1/2/3) that do NOT match their own position in
    # source_polygon_id/base_faces (2026-10-01: "Polygon-specific colours are not working in
    # Viewer view" -- a hoodie-shaped net: hexagon (shape 1, unfolded), pentagon (shape 2,
    # unfolded), and a folded square (shape 3, fanned into 4 triangles) -- catches exactly the
    # positional-vs-group-id mismatch between these two functions that slipped past each one's
    # own, separately-mocked unit tests).
    base_faces = [list(range(6)), list(range(5)), [0, 1, 2], [0, 2, 3], [0, 3, 4], [0, 4, 1]]
    source_polygon_id = [1, 2, 3, 3, 3, 3]
    net_layout = [{"shape_id": 1, "n": 6}, {"shape_id": 2, "n": 5}, {"shape_id": 3, "n": 4}]
    n_by_group = coloring.polygon_n_of_group(source_polygon_id, net_layout)
    colors, color_by_group, _ = coloring.face_colors_by_group(
        base_faces, source_polygon_id, n_by_group)
    assert colors[0] == POLYGON_COLORS[6]  # hexagon
    assert colors[1] == POLYGON_COLORS[5]  # pentagon
    assert colors[2] == colors[3] == colors[4] == colors[5] == POLYGON_COLORS[4]  # folded square
    assert color_by_group == {1: POLYGON_COLORS[6], 2: POLYGON_COLORS[5], 3: POLYGON_COLORS[4]}


def test_face_colors_by_group_falls_back_to_face_colors_beyond_palette():
    # A 9-gon has no POLYGON_COLORS entry (table only covers 3..8) -- falls back to FACE_COLORS.
    base_faces = [list(range(9))]
    colors, _color_by_group, _ = coloring.face_colors_by_group(base_faces, None)
    assert colors[0] in FACE_COLORS


def test_polygon_n_of_group_keyed_by_group_id_not_position():
    # Group ids (1, 2) deliberately don't match their own 0-based position in
    # source_polygon_id, to catch the positional-vs-group-id bug (2026-10-01: "Polygon-specific
    # colours are not working in Viewer view" -- this used to key its result by enumerate's own
    # position instead of the real group/shape id).
    net_layout = [{"shape_id": 1, "n": 6}, {"shape_id": 2, "n": 4}]
    source_polygon_id = [1, 1, 1, 2]
    n_by_group = coloring.polygon_n_of_group(source_polygon_id, net_layout)
    assert n_by_group == {1: 6, 2: 4}


def test_polygon_n_of_group_only_includes_groups_actually_present():
    # net_layout can list a shape not actually referenced by source_polygon_id (e.g. a guest/
    # outsider piece never folded into any inflated group) -- excluded from the result.
    net_layout = [{"shape_id": 1, "n": 6}, {"shape_id": 2, "n": 4}, {"shape_id": 3, "n": 5}]
    source_polygon_id = [1, 1, 1]
    n_by_group = coloring.polygon_n_of_group(source_polygon_id, net_layout)
    assert n_by_group == {1: 6}


def test_polygon_n_of_group_empty_without_net_layout_or_source_polygon_id():
    assert coloring.polygon_n_of_group(None, [{"shape_id": 1, "n": 6}]) == {}
    assert coloring.polygon_n_of_group([1, 2], []) == {}
    assert coloring.polygon_n_of_group([1, 2], None) == {}


def test_polygon_n_of_group_empty_for_legacy_net_layout_with_no_shape_id():
    # A legacy, index-aligned net_layout (pre-Polygon-Fold format) has no "shape_id" entries at
    # all -- callers fall back to len(base_faces[i]) instead, which is already correct there.
    net_layout = [{"n": 6, "cx": 0.0}, {"n": 4, "cx": 1.0}]
    assert coloring.polygon_n_of_group([0, 1], net_layout) == {}


def test_random_face_colors_one_per_base_face_avoiding_neighbor_clash():
    # Two triangles sharing an edge -- their colors should differ (3-color palette, plenty of
    # room to avoid the one clash).
    base_faces = [[0, 1, 2], [1, 3, 2]]
    colors = coloring.random_face_colors(base_faces, None, random.Random(0))
    assert len(colors) == 2
    assert colors[0] != colors[1]


def test_random_face_colors_different_calls_can_differ():
    base_faces = [[0, 1, 2], [1, 3, 2], [3, 4, 2]]
    results = {tuple(coloring.random_face_colors(base_faces, None, random.Random(seed)))
               for seed in range(20)}
    assert len(results) > 1


def test_group_of_face_identity_without_source_polygon_id():
    base_faces = [[0, 1, 2], [3, 4, 5]]
    assert coloring.group_of_face(base_faces, None) == [0, 1]


def test_group_of_face_uses_source_polygon_id_when_given():
    base_faces = [[0, 1, 2], [0, 2, 3], [4, 5, 6]]
    assert coloring.group_of_face(base_faces, [10, 10, 20]) == [10, 10, 20]


def test_random_face_colors_by_group_shares_one_color_within_a_fold_group():
    # A Polygon-Fold hexagon's own 3 fan triangles (group 99, 2026-10-01 bug fix: cannoli_open's
    # own 6-triangle hexagon showed 6 different colors on the "Level N" panels while the Net
    # panel -- which can only ever draw the whole hexagon as one outline -- showed one; user
    # confirmed Multi-colour should group like this instead).
    base_faces = [[0, 1, 2], [0, 2, 3], [0, 3, 4]]
    source_polygon_id = [99, 99, 99]
    colors, color_by_group, group_of_face = coloring.random_face_colors_by_group(
        base_faces, None, source_polygon_id, random.Random(0))
    assert group_of_face == [99, 99, 99]
    assert colors[0] == colors[1] == colors[2]
    assert set(color_by_group) == {99}
    assert color_by_group[99] == colors[0]


def test_random_face_colors_by_group_plain_per_face_without_source_polygon_id():
    base_faces = [[0, 1, 2], [1, 3, 2]]
    colors, color_by_group, group_of_face = coloring.random_face_colors_by_group(
        base_faces, None, None, random.Random(0))
    assert group_of_face == [0, 1]
    assert set(color_by_group) == {0, 1}


def test_random_face_colors_by_group_avoids_neighbor_group_clash():
    # Two separate 2-triangle Polygon-Fold groups, chained edge-to-edge (face1-face2 share an
    # edge) -- the GROUPS should differ, with plenty of palette room to do so. No face_edge_ids
    # -- falls back to the plain shared-vertex-pair match.
    base_faces = [[0, 1, 2], [2, 1, 3], [1, 3, 4], [1, 4, 5]]
    source_polygon_id = [10, 10, 20, 20]
    colors, color_by_group, _ = coloring.random_face_colors_by_group(
        base_faces, None, source_polygon_id, random.Random(0))
    assert color_by_group[10] != color_by_group[20]
    assert colors[0] == colors[1] == color_by_group[10]
    assert colors[2] == colors[3] == color_by_group[20]
