"""Base-mesh topology shared by inflate_polyhedron_app and interactive_inflater_app (2026-10-01,
explicit: "make sure they are using shared code whenever possible. shared code should be moved
to utils" -- previously duplicated, byte-identical, in each app's own `logic`/app.py). Only the
two functions actually duplicated between the two apps live here -- inflate_polyhedron_app's own
`logic/mesh_topology.py` keeps `fan_level_edges`/`layout_from_net_layout`/
`net_layout_is_new_format`/`INTERACTIVE_BUILDER_EDGE_LENGTH`, which have no counterpart in
interactive_inflater_app (that app never loads a saved net file)."""
import numpy as np

from utils.inflate_polyhedron.stretchy_mesh import EDGE_LENGTH
from utils.inflate_polyhedron.mesh_levels import subdivide_once

__all__ = ["build_level1_topology", "open_base_edges", "base_face_neighbors"]


def _edge_owners(base_faces, face_edge_ids):
    """Shared by open_base_edges/base_face_neighbors: {edge key: [(face_idx, vertex pair), ...]}
    -- an edge used by exactly one base_faces entry is that entry's own free/open edge; one used
    by two or more is an internal edge joining those entries (base_face_neighbors). See
    open_base_edges's own docstring for the face_edge_ids-vs-fallback disambiguation."""
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
    return owners


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
    owners = _edge_owners(base_faces, face_edge_ids)
    open_edges = {}
    for group in owners.values():
        if len(group) == 1:
            i, pair = group[0]
            open_edges.setdefault(i, set()).add(pair)
    return open_edges


def base_face_neighbors(base_faces, face_edge_ids):
    """Returns {base_face_idx: {other base_face_idx sharing an edge with it, ...}} -- the base-
    face adjacency graph (2026-10-01, explicit: "add a Colour menu... Multi-colour... trying our
    best to make sure neighbour faces don't share the same colour") -- used to pick colors that
    avoid matching an adjacent face's own. Every base_faces index with at least one glued
    (non-open) edge gets an entry; a face with every edge open (e.g. a lone unconnected piece)
    gets an empty set, not a missing key. Same `face_edge_ids`-vs-fallback disambiguation as
    open_base_edges -- this is its complement (edges shared by 2+ entries, not exactly 1)."""
    owners = _edge_owners(base_faces, face_edge_ids)
    neighbors = {i: set() for i in range(len(base_faces))}
    for group in owners.values():
        if len(group) < 2:
            continue
        face_indices = [i for i, _pair in group]
        for a in face_indices:
            for b in face_indices:
                if a != b:
                    neighbors[a].add(b)
    return neighbors
