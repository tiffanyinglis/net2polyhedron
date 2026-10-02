"""Base-mesh topology and net-layout reconstruction, moved out of inflate_polyhedron_app/app.py
(2026-09-30 modularization). Every function here is pure.
"""
import numpy as np

from utils.inflate_polyhedron.stretchy_mesh import mesh_edges
from utils.geometry.polygon_geom import regular_polygon_vertices, apply_rigid
# `build_level1_topology`/`open_base_edges` moved to utils.inflate_polyhedron.mesh_topology
# (2026-10-01, explicit: "make sure they are using shared code whenever possible. shared code
# should be moved to utils") -- were duplicated, byte-identical, in interactive_inflater_app's
# own app.py. `fan_level_edges`/`layout_from_net_layout`/`net_layout_is_new_format`/
# `INTERACTIVE_BUILDER_EDGE_LENGTH` below stay here -- no counterpart in that app (it never
# loads a saved net file). Re-exported under the same names so every existing
# `from inflate_polyhedron_app.logic.mesh_topology import ...` call site is unchanged.
from utils.inflate_polyhedron.mesh_topology import build_level1_topology, open_base_edges

__all__ = [
    "INTERACTIVE_BUILDER_EDGE_LENGTH", "build_level1_topology", "open_base_edges",
    "fan_level_edges", "layout_from_net_layout", "net_layout_is_new_format",
]

# interactive_builder_app's own DEFAULT_SHAPE_EDGE_LENGTH -- the edge length its "net_layout"
# section's saved cx/cy/rotation are expressed at (a Tkinter pixel scale, unrelated to this
# app's own EDGE_LENGTH=1.0 convention). Duplicated rather than imported -- a whole separate,
# unrelated Tkinter app (see docs/README.md).
INTERACTIVE_BUILDER_EDGE_LENGTH = 70.0


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
