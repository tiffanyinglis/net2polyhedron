import random

from interactive_inflater_app.logic import coloring


def _shape(id_, n):
    return {"id": id_, "n": n}


def _conn(a_shape, a_edge, b_shape, b_edge):
    return {"a_shape": a_shape, "a_edge": a_edge, "b_shape": b_shape, "b_edge": b_edge}


def test_shapes_with_open_edges_none_connected():
    shapes = [_shape(1, 3), _shape(2, 4)]
    assert coloring.shapes_with_open_edges(shapes, []) == {1, 2}


def test_shapes_with_open_edges_fully_connected_triangle_excluded():
    shapes = [_shape(1, 3), _shape(2, 4)]
    connections = [_conn(1, 0, 2, 0), _conn(1, 1, 2, 1), _conn(1, 2, 2, 2)]
    open_ids = coloring.shapes_with_open_edges(shapes, connections)
    assert open_ids == {2}  # shape 1 used all 3 of its edges; shape 2 (n=4) still has edge 3 free


def test_shapes_with_open_edges_self_join_uses_two_edges():
    shapes = [_shape(1, 4)]
    connections = [_conn(1, 0, 1, 2)]
    open_ids = coloring.shapes_with_open_edges(shapes, connections)
    assert open_ids == {1}  # 2 of 4 edges used, still open


def test_pick_color_for_new_shape_avoids_open_neighbor_colors():
    palette = ["red", "green", "blue"]
    shape_colors = {1: "red", 2: "green"}
    color = coloring.pick_color_for_new_shape(shape_colors, open_shape_ids={1, 2},
                                               palette=palette, rng=random.Random(0))
    assert color == "blue"


def test_pick_color_for_new_shape_falls_back_to_any_unused_when_every_open_color_taken():
    palette = ["red", "green"]
    shape_colors = {1: "red", 2: "green"}
    color = coloring.pick_color_for_new_shape(shape_colors, open_shape_ids={1, 2},
                                               palette=palette, rng=random.Random(0))
    assert color in palette  # no color avoids both -- falls back to full palette


def test_pick_color_for_new_shape_ignores_closed_shapes():
    palette = ["red", "green", "blue"]
    shape_colors = {1: "red"}  # shape 1 is closed (not in open_shape_ids) -- its color is fair game
    color = coloring.pick_color_for_new_shape(shape_colors, open_shape_ids=set(),
                                               palette=palette, rng=random.Random(0))
    assert color in palette


def test_shape_group_neighbors_maps_groups_through_source_polygon_id():
    base_faces = [[0, 1, 2], [1, 3, 2]]
    source_polygon_id = [10, 20]
    neighbors = coloring.shape_group_neighbors(base_faces, None, source_polygon_id)
    assert neighbors[10] == {20}
    assert neighbors[20] == {10}


def test_shape_group_neighbors_folded_shape_triangles_dont_neighbor_themselves():
    # Two fan triangles sharing an edge but both from the SAME shape_id -- shouldn't appear.
    base_faces = [[0, 1, 2], [0, 2, 3]]
    source_polygon_id = [10, 10]
    neighbors = coloring.shape_group_neighbors(base_faces, None, source_polygon_id)
    assert neighbors.get(10, set()) == set()


def test_random_shape_colors_avoids_neighbor_clash():
    neighbors = {1: {2}, 2: {1}}
    colors = coloring.random_shape_colors([1, 2], neighbors, palette=["red", "green", "blue"],
                                           rng=random.Random(0))
    assert colors[1] != colors[2]
