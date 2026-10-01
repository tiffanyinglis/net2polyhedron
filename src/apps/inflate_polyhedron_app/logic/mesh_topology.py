"""Base-mesh topology and net-layout reconstruction, moved out of inflate_polyhedron_app/app.py
(2026-09-30 modularization). Every function here is pure.
"""
import numpy as np

from utils.inflate_polyhedron.stretchy_mesh import EDGE_LENGTH, mesh_edges
from utils.inflate_polyhedron.mesh_levels import subdivide_once
from utils.geometry.polygon_geom import regular_polygon_vertices, apply_rigid

__all__ = [
    "INTERACTIVE_BUILDER_EDGE_LENGTH", "build_level1_topology", "open_base_edges",
    "fan_level_edges", "layout_from_net_layout", "net_layout_is_new_format",
]

# interactive_builder_app's own DEFAULT_SHAPE_EDGE_LENGTH -- the edge length its "net_layout"
# section's saved cx/cy/rotation are expressed at (a Tkinter pixel scale, unrelated to this
# app's own EDGE_LENGTH=1.0 convention). Duplicated rather than imported -- a whole separate,
# unrelated Tkinter app (see docs/README.md).
INTERACTIVE_BUILDER_EDGE_LENGTH = 70.0


def build_level1_topology(base_faces):
    """Level 0 and Level 1 share this exact fan-triangulated topology (see mesh_levels' own
    docstring for why triangulating first matters for a spring-only relax) -- cheap enough (pure
    index math, no numerical solve) to compute synchronously on every net selection. Calls
    subdivide_once with placeholder positions purely to get the resulting faces/edge_length/
    face_of_fine; the interpolated positions it also returns are meaningless (every input point
    is the same placeholder) and discarded -- random_initial_positions supplies Level 0's real
    starting positions instead."""
    dummy_positions = {v: np.zeros(3) for face in base_faces for v in face}
    faces, _, edge_length, face_of_fine = subdivide_once(
        base_faces, dummy_positions, EDGE_LENGTH, list(range(len(base_faces))), 0)
    return faces, edge_length, face_of_fine


def open_base_edges(base_faces, face_edge_ids):
    """Returns {base_face_idx: {frozenset(rim-edge vertex pair), ...}} -- for each original
    polygon, which of ITS OWN edges have no partner elsewhere in the net (a genuine
    free/boundary edge) rather than being glued to some other piece. Per-EDGE, not per-whole-
    polygon: an n-gon connected at 2 of its own edges triangulates into 2 "closed" wedges and
    n-2 "open" ones.

    Adjacency is found via `face_edge_ids` when given (an edge id used by exactly ONE
    base_faces entry across the whole net is that entry's own free edge) -- same
    disambiguation rationale as mesh_levels.polygon_centroid_springs' own docstring, since two
    DIFFERENT genuine edges can coincidentally share a plain vertex-id pair. Falls back to a
    plain shared-vertex-pair match when `face_edge_ids` is None (a net with no such field has
    no such collision risk either)."""
    owners = {}
    if face_edge_ids is not None:
        for i, ids in enumerate(face_edge_ids):
            face = base_faces[i]
            n = len(face)
            for k, eid in enumerate(ids):
                pair = frozenset((face[k], face[(k + 1) % n]))
                owners.setdefault(eid, []).append((i, pair))
    else:
        for i, face in enumerate(base_faces):
            n = len(face)
            for k in range(n):
                pair = frozenset((face[k], face[(k + 1) % n]))
                owners.setdefault(pair, []).append((i, pair))
    open_edges = {}
    for group in owners.values():
        if len(group) == 1:
            i, pair = group[0]
            open_edges.setdefault(i, set()).add(pair)
    return open_edges


def fan_level_edges(faces, base_edges):
    """faces: Level 0/1's own fan-triangulated mesh (build_level1_topology); base_edges: the
    loaded net's own explicit "edges" field, or None (older file, or nothing to disambiguate --
    the plain mesh_edges vertex-pair fallback is then safe). Returns the explicit mesh-edge list
    for Level 0/1's relax/inflate calls, or None to mean "use the fallback".

    Fan triangulation never touches a base face's own RIM edges (see
    mesh_levels._fan_level_0_to_1) -- those stay exactly `base_edges`' own pairs, already
    correctly disambiguated. The only edges triangulation ADDS are SPOKES (rim vertex to a
    fresh centroid id), always globally unique, so deriving those the plain way is safe. This
    combines the two: `base_edges` as-is, plus every other edge of `faces` from mesh_edges."""
    if base_edges is None:
        return None
    base_vertex_ids = {v for e in base_edges for v in e}
    spokes = [e for e in mesh_edges(faces)
              if not (e[0] in base_vertex_ids and e[1] in base_vertex_ids)]
    return list(base_edges) + spokes


def layout_from_net_layout(faces, net_layout):
    """faces: vertex-id loops; net_layout: interactive_builder_app's own saved list of
    per-placed-shape placements. Returns {key: [2D point, ...]} -- the same shape
    build_stretchy_net_layout returns -- by reproducing each shape's saved rigid transform
    directly rather than re-deriving a layout via a fresh BFS spanning tree, since a BFS only
    follows the first shared edge it reaches an already-visited face through and silently drops
    any other edge-sharing (normal for a stretchy mesh) -- a net arranged in the interactive
    builder should show up here exactly as left.

    Two `net_layout` formats, matching interactive_builder_app's own _load_faces:
    - NEW (entry has "shape_id"/"n", written since Polygon Fold): `key` is "shape_id", polygon
      built at its own "n" sides directly -- `faces` isn't consulted (no longer 1:1 with placed
      shapes once a folded polygon's triangles are in it).
    - LEGACY (no "shape_id", one face per shape): `key` is the entry's list position `i`, "n" is
      `len(faces[i])`.

    Rigid transforms are scale-covariant, so reproducing the net at this app's own unit edge
    length is a uniform rescale by INTERACTIVE_BUILDER_EDGE_LENGTH (build each polygon at
    edge_length=1, divide every saved cx/cy by 70).

    Also flips every point's Y sign (a whole-picture reflection, isometric so adjacency is
    preserved) to correct a real coordinate-convention mismatch: interactive_builder_app's
    Tkinter canvas has Y increasing downward, this panel's matplotlib axes have Y increasing
    upward -- without the flip the net renders as a vertical mirror image of what was built."""
    placed = {}
    for i, layout in enumerate(net_layout):
        key = layout.get("shape_id", i)
        n = layout.get("n", len(faces[i]) if i < len(faces) else 3)
        theta = layout["rotation"]
        c, s = np.cos(theta), np.sin(theta)
        R = np.array([[c, -s], [s, c]])
        t = np.array([layout["cx"], layout["cy"]]) / INTERACTIVE_BUILDER_EDGE_LENGTH
        points = apply_rigid(regular_polygon_vertices(n), R, t)
        placed[key] = [np.array([p[0], -p[1]]) for p in points]
    return placed


def net_layout_is_new_format(net_layout):
    """True iff `net_layout` is the post-Polygon-Fold, shape-id-keyed format rather than the
    legacy face-index-aligned one (see layout_from_net_layout). Every entry is tagged the same
    way, so checking just the first is enough."""
    return bool(net_layout) and "shape_id" in net_layout[0]
