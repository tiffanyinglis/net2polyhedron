"""Per-vertex normal computation, shared by inflate_polyhedron_app and interactive_inflater_app
(2026-10-01, explicit: "make sure they are using shared code whenever possible. shared code
should be moved to utils" -- previously duplicated, byte-identical, as each app's own
`_vertex_normals`/`vertex_normals`)."""
import numpy as np

__all__ = ["vertex_normals"]


def vertex_normals(faces, positions):
    """faces: triangle vertex-id loops; positions: {vertex_id: pos}. Returns {vertex_id:
    (unit_normal, mean_incident_edge_length)} for "Show vertex normals" -- every vertex touched
    by at least one non-degenerate face. `unit_normal` is the NORMALIZED SUM of every incident
    face's unit normal, each face weighted equally (not by area) -- shows "which way do my own
    faces agree this vertex points" (surfaces a fold/inconsistency a per-face check alone could
    miss), rather than approximating a smooth surface normal. `mean_incident_edge_length` scales
    the drawn segment the same "about half an edge" way face normals are. A vertex whose
    incident faces cancel exactly, or that has no non-degenerate incident face, is omitted."""
    normal_sums = {}
    edge_len_sums = {}
    edge_len_counts = {}
    for a, b, c in faces:
        pa, pb, pc = positions[a], positions[b], positions[c]
        normal = np.cross(pb - pa, pc - pa)
        normal_len = np.linalg.norm(normal)
        if normal_len < 1e-12:
            continue
        unit_normal = normal / normal_len
        for v in (a, b, c):
            normal_sums[v] = normal_sums.get(v, np.zeros(3)) + unit_normal
        for u, w in ((a, b), (b, c), (c, a)):
            length = np.linalg.norm(positions[w] - positions[u])
            for v in (u, w):
                edge_len_sums[v] = edge_len_sums.get(v, 0.0) + length
                edge_len_counts[v] = edge_len_counts.get(v, 0) + 1
    result = {}
    for v, total in normal_sums.items():
        total_len = np.linalg.norm(total)
        if total_len < 1e-12:
            continue
        result[v] = (total / total_len, edge_len_sums[v] / edge_len_counts[v])
    return result
