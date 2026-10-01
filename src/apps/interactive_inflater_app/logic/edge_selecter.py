"""Pure connection/open-edge hover+selection, moved out of InflaterPane (2026-09-30
modularization) -- "which connection/open-edge is closest to this 3D point" nearest-point search.
The VTK actor-building stays in app.py.
"""
import numpy as np

__all__ = ["point_segment_distance_3d", "nearest_connection", "nearest_open_edge"]


def point_segment_distance_3d(point, a, b):
    """Shortest distance from `point` to the 3D line SEGMENT a->b (not the infinite line)."""
    ab = b - a
    denom = np.dot(ab, ab)
    if denom < 1e-18:
        return float(np.linalg.norm(point - a))
    t = max(0.0, min(1.0, np.dot(point - a, ab) / denom))
    return float(np.linalg.norm(point - (a + t * ab)))


def nearest_connection(pos, connection_edge_cache, tolerance, connections_by_id=None,
                        shape_id=None):
    """The builder connection id whose cached 3D seam segments (`connection_edge_cache`) come
    closest to world point `pos`, within `tolerance` -- or None if nothing's close enough
    (including simply because `pos` is None, no surface under the cursor at all). There's no
    dedicated pickable actor per connection (unlike a base face's own mesh actor) -- a
    connection's seam is a thin line lying exactly on the already-picked surface, not a separate
    3D object of its own, so proximity-to-the-pick-point is used instead of a second picker pass.

    `shape_id`, when given (with `connections_by_id`, a {conn_id: conn} lookup), restricts
    candidates to connections touching that ONE shape (2026-09-29, explicit bug report: "the
    edges of the guest piece [are] still not selectable. instead there are some non-edges that
    are highlighted when hovered over" -- a compact, nearly-closed net folds enough that a
    totally unrelated shape's own seam can sit CLOSER in 3D to a given surface point than that
    surface's own nearby seam). The caller passes the shape actually under the cursor, so a
    hover only ever finds an edge genuinely belonging to what's actually being pointed at."""
    if pos is None or not connection_edge_cache:
        return None
    best_id, best_dist = None, tolerance
    for conn_id, segments in connection_edge_cache.items():
        if shape_id is not None:
            conn = connections_by_id.get(conn_id) if connections_by_id else None
            if conn is None or shape_id not in (conn["a_shape"], conn["b_shape"]):
                continue
        for i in range(0, len(segments), 2):
            dist = point_segment_distance_3d(pos, segments[i], segments[i + 1])
            if dist < best_dist:
                best_id, best_dist = conn_id, dist
    return best_id


def nearest_open_edge(pos, open_edges, tolerance, exclude_shape_id=None, shape_id=None):
    """The (shape_id, raw_edge) key in `open_edges` whose own segments come closest to world
    point `pos`, within `tolerance` -- or None if nothing's close enough. Point-to-SEGMENT
    distance against the edge's own actual (possibly subdivided) geometry, not just its
    midpoint -- same convention `nearest_connection` uses for an EXISTING connection's own seam.
    `exclude_shape_id` drops one shape's own edges from consideration -- used while dragging OUT
    of a shape's edge, since Join mode never connects a shape to itself. `shape_id`, when given,
    restricts candidates to that ONE shape's own edges -- see `nearest_connection`'s own
    docstring for why (same fold-brings-unrelated-shapes-close issue, same fix)."""
    if pos is None or not open_edges:
        return None
    best_key, best_dist = None, tolerance
    for key, info in open_edges.items():
        if exclude_shape_id is not None and info["shape_id"] == exclude_shape_id:
            continue
        if shape_id is not None and info["shape_id"] != shape_id:
            continue
        segments = info["segments"]
        for i in range(0, len(segments), 2):
            dist = point_segment_distance_3d(pos, segments[i], segments[i + 1])
            if dist < best_dist:
                best_key, best_dist = key, dist
    return best_key
