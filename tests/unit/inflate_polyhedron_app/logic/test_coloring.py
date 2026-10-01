from inflate_polyhedron_app.logic import coloring


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
    colors, color_by_group, group_of_face = coloring.face_colors_by_group(3, None)
    assert group_of_face == [0, 1, 2]
    assert len(set(colors)) == 3  # each face its own color
    assert set(color_by_group) == {0, 1, 2}


def test_face_colors_by_group_shares_color_within_a_group():
    colors, color_by_group, group_of_face = coloring.face_colors_by_group(4, [10, 10, 20, 20])
    assert group_of_face == [10, 10, 20, 20]
    assert colors[0] == colors[1]
    assert colors[2] == colors[3]
    assert colors[0] != colors[2]
    assert set(color_by_group) == {10, 20}
