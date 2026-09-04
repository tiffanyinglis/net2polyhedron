"""Lay out a stretchy vertex-loop mesh's faces as a flat, connected 2D net
-- the same idea net_layout.py (in ..geometry2d) uses for the rigid
pipeline (attach each child face to its parent along their shared edge,
reversed so it unfolds outward, like a real paper net), but derived
directly from the vertex loops' own edge order instead of a separately
computed combinatorics.edge_map.EdgeMap.

EdgeMap can't represent a stretchy mesh's face pairs sharing more than
one edge in the first place (see stretchy_mesh.py's module docstring),
and isn't needed here anyway: each face's own vertex loop already gives
its edges in a well-defined CCW order, so which local edge index
corresponds to a given neighbor is immediate, with no separate
planar-embedding step required.

A face pair sharing more than one edge just means extra entries in
_shared_edge_faces below that never get used for layout -- BFS only
follows the FIRST edge it reaches a still-unplaced face through, same as
an `edges.extra` edge in the rigid net format would be ignored for
layout purposes.
"""
from collections import defaultdict, deque

from .polygon_geom import regular_polygon_vertices, attach_polygon


def _shared_edge_faces(faces):
    """{(a, b) sorted: [(face_idx, local_edge_idx), ...]} for every
    undirected edge, one entry per face that has it as one of its own
    directed edges (exactly 2 entries for an internal edge of a closed,
    consistently-wound mesh -- see load_stretchy_mesh's validation)."""
    shared = defaultdict(list)
    for fi, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            a, b = face[i], face[(i + 1) % n]
            shared[(a, b) if a < b else (b, a)].append((fi, i))
    return shared


def build_stretchy_net_layout(faces, root=0):
    """Place every face reachable from `root` by breadth-first search over
    shared edges, as one connected flat net -- root is placed as a plain
    regular polygon, then each face BFS reaches next is attached to
    whichever already-placed neighbor discovered it, along their shared
    edge (reversed, so it unfolds outward). Returns {face_idx: [2D point,
    ...]}. Every face is reachable for a closed, connected mesh (which
    load_stretchy_mesh already guarantees)."""
    shared = _shared_edge_faces(faces)
    placed = {root: regular_polygon_vertices(len(faces[root]))}
    visited = {root}
    q = deque([root])
    while q:
        parent = q.popleft()
        parent_face = faces[parent]
        n_parent = len(parent_face)
        pverts = placed[parent]
        for i in range(n_parent):
            a, b = parent_face[i], parent_face[(i + 1) % n_parent]
            key = (a, b) if a < b else (b, a)
            for fi, local_idx in shared[key]:
                if fi == parent or fi in visited:
                    continue
                visited.add(fi)
                p1, p2 = pverts[i], pverts[(i + 1) % n_parent]
                placed[fi] = attach_polygon(len(faces[fi]), local_idx, p2, p1)
                q.append(fi)
    return placed
