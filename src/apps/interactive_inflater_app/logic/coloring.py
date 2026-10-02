"""Colour > Multi-colour support for interactive_inflater_app (2026-10-01, explicit: the same
Colour menu built for inflate_polyhedron_app -- see that app's logic/coloring.py -- "once that's
done, add the same thing for interactive_inflater"). Colours here are tracked per 2D BUILDER
SHAPE (shape_id), not per 3D base face/group like the sibling app: a shape exists, and can be
given a colour, well before it's ever inflated (placed flat as a terminal node, or just dropped on the
canvas with no connections at all yet) -- InflaterPane.shape_colors is the one persistent
{shape_id: color} map, broadcast across however many 3D groups that shape_id's own
source_polygon_id entries span (a Polygon-Fold shape's several fan triangles all share one colour,
unlike inflate_polyhedron_app's own per-individual-triangle Multi-colour).
"""
import random

from common.ui_theme import FACE_COLORS
from utils.graph_face_coloring import random_graph_coloring
from utils.inflate_polyhedron.mesh_topology import base_face_neighbors

__all__ = ["shapes_with_open_edges", "pick_color_for_new_shape", "shape_group_neighbors",
           "random_shape_colors"]


def shapes_with_open_edges(shapes, connections):
    """Shape ids with at least one edge not yet used by any connection -- the best available
    proxy for "a piece this NEW piece could plausibly end up connected to" at the moment a piece
    is placed, when no connection (and so no real mesh adjacency) exists for it yet (2026-10-01,
    explicit: "when a user picks up a piece, we don't know where they're going to place it
    yet... give the new piece a colour that's not used or at least not the colour of a piece
    that it could be connected to"). A connection uses edge index `a_edge` on shape `a_shape` and
    `b_edge` on `b_shape` (a Polygon-Fold self-join uses two edges on the same shape, handled
    the same as any other pair)."""
    used = {}
    for conn in connections:
        used.setdefault(conn["a_shape"], set()).add(conn["a_edge"])
        used.setdefault(conn["b_shape"], set()).add(conn["b_edge"])
    return {shape["id"] for shape in shapes if len(used.get(shape["id"], ())) < shape["n"]}


def pick_color_for_new_shape(shape_colors, open_shape_ids, palette=FACE_COLORS, rng=None):
    """A colour for a just-placed shape, before its final connections (and so its real mesh
    adjacency) are known. Avoids every OPEN shape's (see shapes_with_open_edges) own already-
    assigned colour where possible -- those are the only existing pieces this one could actually
    end up glued to; falls back to avoiding every colour in use at all, then to the whole
    palette if even that's exhausted. "Our best effort", not a guarantee, same as
    random_graph_coloring's own fallback -- Colour > Randomize is the explicit escape hatch for a
    less-than-ideal pick."""
    if rng is None:
        rng = random
    open_colors = {shape_colors[sid] for sid in open_shape_ids if sid in shape_colors}
    candidates = [c for c in palette if c not in open_colors]
    if not candidates:
        used_colors = set(shape_colors.values())
        candidates = [c for c in palette if c not in used_colors] or list(palette)
    return rng.choice(candidates)


def shape_group_neighbors(base_faces, face_edge_ids, source_polygon_id):
    """Shape-id adjacency derived from the CURRENT mesh's own group-level adjacency
    (base_face_neighbors) -- two shapes are neighbors iff one of shape A's own groups (3D base
    faces) shares a mesh edge with one of shape B's. A Polygon-Fold shape's several fan-triangle
    groups all map to the same shape_id and so never neighbor themselves this way (a group is
    never its own neighbor to begin with)."""
    group_neighbors = base_face_neighbors(base_faces, face_edge_ids)
    neighbors = {}
    for group, others in group_neighbors.items():
        sid = source_polygon_id[group] if source_polygon_id else group
        for other in others:
            other_sid = source_polygon_id[other] if source_polygon_id else other
            if other_sid != sid:
                neighbors.setdefault(sid, set()).add(other_sid)
    return neighbors


def random_shape_colors(shape_ids, neighbors, palette=FACE_COLORS, rng=None):
    """random_graph_coloring, wrapped to key by shape_id instead of a plain 0..n-1 index."""
    ids = list(shape_ids)
    index_of = {sid: i for i, sid in enumerate(ids)}
    index_neighbors = {index_of[sid]: {index_of[n] for n in neighbors.get(sid, ()) if n in index_of}
                        for sid in ids}
    colors = random_graph_coloring(len(ids), index_neighbors, palette, rng)
    return dict(zip(ids, colors))
