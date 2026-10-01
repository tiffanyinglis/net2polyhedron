"""Face/shape-removal-from-mesh arithmetic, moved out of InflaterPane._diff_remove_face
(2026-09-30 modularization) -- the pure base-mesh/fine-mesh filtering and reindexing that happens
when one or more shapes are dropped from an already-solved mesh. The surrounding orchestration
(pendant re-exclusion, staging a background relax pass, status/Tk) stays in app.py.
"""

__all__ = ["remove_faces_from_mesh", "remap_fine_mesh_after_removal"]


def remove_faces_from_mesh(base_faces, base_face_edge_ids, base_edges, source_polygon_id,
                            shape_ids_to_remove):
    """Filters the base mesh down to whatever's left once every shape in `shape_ids_to_remove`'s
    own base face(s) are dropped -- pure filtering, no interpolation needed at all, since every
    SURVIVING vertex is already exactly where it was left. Returns None if nothing survives
    (caller should show its own "nothing left to inflate" error), else a dict:
    - "removed_idxs": the set of ORIGINAL base-face indices dropped
    - "keep_base_idxs": the ORIGINAL indices that survive, in their new order
    - "surviving_base_faces"/"surviving_face_edge_ids"/"surviving_source_polygon_id": `base_faces`
      /`base_face_edge_ids`/`source_polygon_id`, filtered and reindexed to the survivors
    - "surviving_edges": `base_edges` filtered down to pairs whose both endpoints survive
    """
    removed_idxs = {i for i, spid in enumerate(source_polygon_id) if spid in shape_ids_to_remove}
    keep_base_idxs = [i for i in range(len(base_faces)) if i not in removed_idxs]
    if not keep_base_idxs:
        return None
    surviving_base_faces = [base_faces[i] for i in keep_base_idxs]
    surviving_face_edge_ids = (None if base_face_edge_ids is None else
                                [base_face_edge_ids[i] for i in keep_base_idxs])
    surviving_source_polygon_id = [source_polygon_id[i] for i in keep_base_idxs]
    surviving_edges = base_edges
    if surviving_edges is not None:
        remaining_base_vertex_ids = {v for f in surviving_base_faces for v in f}
        surviving_edges = [e for e in surviving_edges if e[0] in remaining_base_vertex_ids
                            and e[1] in remaining_base_vertex_ids]
    return {
        "removed_idxs": removed_idxs,
        "keep_base_idxs": keep_base_idxs,
        "surviving_base_faces": surviving_base_faces,
        "surviving_face_edge_ids": surviving_face_edge_ids,
        "surviving_source_polygon_id": surviving_source_polygon_id,
        "surviving_edges": surviving_edges,
    }


def remap_fine_mesh_after_removal(faces, face_of_fine, removed_idxs, old_to_new_base, old_to_core):
    """The stored Level-3 `faces`/`face_of_fine` filtered down to whatever survives a face
    removal AND a subsequent pendant re-exclusion -- `old_to_new_base` maps an original base-face
    index to its index among `remove_faces_from_mesh`'s own survivors, `old_to_core` then maps
    THAT to its final index in the pendant-excluded core (both keyed by whichever indices are
    still present at that stage; a fine triangle whose base face dropped out of either mapping is
    dropped too)."""
    keep_fine = [i for i, bf in enumerate(face_of_fine)
                 if bf not in removed_idxs and old_to_new_base[bf] in old_to_core]
    new_faces = [faces[i] for i in keep_fine]
    new_face_of_fine = [old_to_core[old_to_new_base[face_of_fine[i]]] for i in keep_fine]
    return new_faces, new_face_of_fine
