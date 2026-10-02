import random

from utils.graph_face_coloring import random_graph_coloring


def test_avoids_neighbor_clash_when_palette_has_enough_colors():
    # A path of 3 items: 0-1-2. Palette has 3 colors, plenty to avoid every clash.
    neighbors = {0: {1}, 1: {0, 2}, 2: {1}}
    colors = random_graph_coloring(3, neighbors, ["red", "green", "blue"], random.Random(0))
    assert colors[0] != colors[1]
    assert colors[1] != colors[2]


def test_isolated_items_get_no_constraint():
    colors = random_graph_coloring(5, {}, ["red", "green"], random.Random(0))
    assert len(colors) == 5
    assert all(c in ("red", "green") for c in colors)


def test_falls_back_to_full_palette_when_every_color_is_excluded():
    # A single item neighboring everything in a 2-color palette's own 2 "other" items -- there's
    # no valid non-clashing choice left, so it must still return SOME color, not crash/None.
    neighbors = {0: {1, 2}, 1: {0}, 2: {0}}
    colors = random_graph_coloring(3, neighbors, ["red", "green"], random.Random(1))
    assert all(c in ("red", "green") for c in colors)
    assert None not in colors


def test_different_rng_seeds_can_give_different_results():
    neighbors = {}
    results = {tuple(random_graph_coloring(6, neighbors, ["r", "g", "b", "y"], random.Random(seed)))
               for seed in range(20)}
    assert len(results) > 1  # not literally the same every time


def test_default_rng_runs_without_error():
    colors = random_graph_coloring(4, {}, ["red", "green", "blue"])
    assert len(colors) == 4
