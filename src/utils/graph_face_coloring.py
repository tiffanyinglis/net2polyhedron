"""Generic randomized graph coloring: pick one color per item from a fixed palette, biased
toward giving adjacent items different colors (2026-10-01, explicit: "add a Colour menu...
Multi-colour... trying our best to make sure neighbour faces don't share the same colour").
Not inflate_polyhedron-specific -- `neighbors` is caller-supplied, so this is reusable for any
"items" with any adjacency notion (e.g. inflate_polyhedron_app's base-face mesh adjacency, or
interactive_inflater_app's own "pieces that could end up connected" notion)."""
import random

__all__ = ["random_graph_coloring"]


def random_graph_coloring(n, neighbors, palette, rng=None):
    """Returns a list of `n` colors drawn from `palette`. Processes items in a RANDOM order
    (`rng`, a `random.Random`-compatible object exposing `.shuffle(list)`/`.choice(list)` --
    defaults to the `random` module itself), so repeated calls give different results even for
    the same adjacency. For each item, picks uniformly at random from whichever palette entries
    aren't already used by one of its already-colored neighbors (per `neighbors[i]`, an iterable
    of other item indices; a missing key means no neighbors) -- falls back to the full palette if
    every entry is already excluded (more neighbors than palette size, so a clash is unavoidable
    there). Greedy, not globally optimal -- a later item can still end up clashing with an
    earlier one if the palette is tight; "our best effort", not a guarantee, per the request this
    was built for."""
    if rng is None:
        rng = random
    order = list(range(n))
    rng.shuffle(order)
    colors = [None] * n
    for i in order:
        used = {colors[j] for j in neighbors.get(i, ()) if colors[j] is not None}
        candidates = [c for c in palette if c not in used] or list(palette)
        colors[i] = rng.choice(candidates)
    return colors
