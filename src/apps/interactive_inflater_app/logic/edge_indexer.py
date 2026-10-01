"""Base-edge (2D builder shape edge) <-> fine-mesh (3D subdivided vertex chain) identity, moved
out of InflaterPane (2026-09-30 modularization) -- the edge half of keeping the 2D canvas and the
3D panel "matching" (see face_indexer.py's own docstring for the face half). `group_boundary_
edge_set`/`base_edge_vertex_chain` are the canonical versions of logic that used to be
duplicated in the pendant/flat-attach pipeline (`flat_face_attacher.py` now imports them from
here instead of keeping its own copies).

Every function here is pure (no Tkinter/VTK/`self`) -- `InflaterPane` calls these by name,
passing its own `self.faces`/`self.face_of_fine`/`self.positions`/`self.base_faces`.
"""
import numpy as np

__all__ = ["group_boundary_edge_set", "base_edge_vertex_chain", "open_edge_geometry",
           "open_edges_for_mesh"]


def group_boundary_edge_set(faces, face_of_fine, group):
    """{(u, v), ...} (sorted vertex-id pairs, u < v) for every boundary edge of `group` --
    a spoke/internal-to-the-fan edge is shared by two triangles of the SAME group and cancels
    out; only a true rim edge, whose other triangle is in a different group (or doesn't exist at
    all), survives."""
    edge_count = {}
    for face, bf in zip(faces, face_of_fine):
        if bf != group:
            continue
        a, b, c = face
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            edge_count[key] = edge_count.get(key, 0) + 1
    return {e for e, count in edge_count.items() if count == 1}


def base_edge_vertex_chain(u, v, boundary_edges, original_corners):
    """Ordered fine-mesh vertex ids from corner `u` to corner `v` along THIS ONE base edge's own
    rim -- NOT just [u, v] (2026-09-19, explicit bug report: "when i hover over an edge
    midpoint... you're drawing a circle halfway between two vertices rather than actually on the
    edge (which is not straight so you need to look at the subdivisions)"): a rim edge is left
    alone at Level 1 (still literally [u, v]), but gains a real midpoint vertex at every
    subsequent level -- for an inflated/relaxed shape those aren't at the straight average of u
    and v's own positions any more, so the actual chain has to be walked, not assumed.

    `boundary_edges` (group_boundary_edge_set's own result) gives every rim SEGMENT of the group
    as an unordered {(a, b), ...} set -- within it, every vertex has exactly degree 2 (it's one
    closed loop around the whole polygon), so `u` has exactly two neighbors: one starts the short
    chain toward `v` (this one edge, possibly subdivided), the other starts off around the REST
    of the polygon's other edges instead. The two directions can't be told apart by which one
    reaches `v` sooner -- instead, each of `u`'s two neighbors is tried as a walk (always
    stepping to whichever neighbor isn't where it just came from) that stops the instant it
    reaches EITHER `v` (success) OR any OTHER of `original_corners` (failure -- a genuine
    subdivision midpoint is never one of those, only ever a newly-created vertex id, so hitting
    one means this direction wandered onto a DIFFERENT base edge instead). Falls back to the
    plain [u, v] pair if neither direction ever reaches `v` (shouldn't happen for a genuine edge
    of this group, but stays safe if it ever doesn't)."""
    neighbors = {}
    for a, b in boundary_edges:
        neighbors.setdefault(a, []).append(b)
        neighbors.setdefault(b, []).append(a)
    for first_step in neighbors.get(u, []):
        chain = [u, first_step]
        prev, cur = u, first_step
        while cur != v and cur not in original_corners:
            options = [n for n in neighbors.get(cur, []) if n != prev]
            if not options:
                break
            prev, cur = cur, options[0]
            chain.append(cur)
        if cur == v:
            return chain
    return [u, v]


def open_edge_geometry(chain, positions, u, v):
    """(midpoint, segments) for a base edge whose fine-mesh chain is `chain`
    (base_edge_vertex_chain's own result), AT THE CURRENT subdivision level. `midpoint` is the
    middle vertex of that chain (an odd-length chain, Level 2+, has one -- e.g. [u, m, v] at
    Level 2), or the plain average of the two middle ones for an even-length chain (Level 0/1's
    own un-subdivided [u, v], where this is just the ordinary straight-line midpoint).
    `segments` is the whole chain as consecutive (start, end) pairs -- the edge's own ACTUAL
    (possibly curved/subdivided) geometry, what every highlight draws instead of a straight
    chord between the two corners."""
    points = [positions[vid] for vid in chain if vid in positions]
    if len(points) < 2:
        p_u, p_v = positions[u], positions[v]
        return (p_u + p_v) / 2, np.array([p_u, p_v])
    mid = len(points) // 2
    midpoint = points[mid] if len(points) % 2 == 1 else (points[mid - 1] + points[mid]) / 2
    segments = np.empty((2 * (len(points) - 1), 3))
    for i in range(len(points) - 1):
        segments[2 * i] = points[i]
        segments[2 * i + 1] = points[i + 1]
    return midpoint, segments


def open_edges_for_mesh(base_faces, pending_source_polygon_id, shapes, connections, positions,
                         geometry_fn):
    """The pure rebuild computation behind InflaterPane._rebuild_open_edges -- every 2D builder
    edge NOT currently used by a connection, as {(shape_id, raw_edge): {shape_id, raw_edge,
    midpoint, segments}}, deliberately reading the builder's CURRENT shapes/connections (not a
    possibly-stale last-inflated snapshot), since "is this edge already used" is a pure
    2D-data-model question that should update the instant a connection is made, even before the
    3D mesh itself catches up at the next Diff/Full Inflate.

    `geometry_fn(group, u, v) -> (midpoint, segments)` is injected (rather than computed here
    directly) since it needs the caller's own faces/face_of_fine to walk the fine-mesh chain
    (base_edge_vertex_chain) -- typically `InflaterPane._open_edge_geometry`.

    A deleted shape, or one whose group is actually several Polygon-Fold triangles (`len(face)
    == 3` always, regardless of the original shape's own side count), is skipped entirely -- no
    reliable raw-edge<->loop-position mapping to offer a handle through (a Polygon-Fold self-
    connection stays a 2D-only, Fold-mode-only gesture)."""
    open_edges = {}
    if not base_faces or positions is None or pending_source_polygon_id is None:
        return open_edges
    used = set()
    for conn in connections:
        used.add((conn["a_shape"], conn["a_edge"]))
        used.add((conn["b_shape"], conn["b_edge"]))
    shapes_by_id = {s["id"]: s for s in shapes}
    for group, shape_id in enumerate(pending_source_polygon_id):
        if group >= len(base_faces):
            continue
        face = base_faces[group]
        shape = shapes_by_id.get(shape_id)
        if shape is None or len(face) != shape["n"]:
            continue
        n = shape["n"]
        flipped = shape.get("flipped", False)
        for raw_edge in range(n):
            if (shape_id, raw_edge) in used:
                continue
            # raw_edge_for_loop_position (interactive_builder_app._face_edge_ids_from_shapes,
            # untouchable) is its own inverse for this formula, so the same expression maps
            # loop position -> raw edge and back.
            k = raw_edge if not flipped else (n - 2 - raw_edge) % n
            u, v = face[k], face[(k + 1) % n]
            if u not in positions or v not in positions:
                continue
            midpoint, segments = geometry_fn(group, u, v)
            open_edges[(shape_id, raw_edge)] = {
                "shape_id": shape_id, "raw_edge": raw_edge, "midpoint": midpoint,
                "segments": segments,
            }
    return open_edges
