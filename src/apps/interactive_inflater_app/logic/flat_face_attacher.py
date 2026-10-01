"""Pendant/guest flat-attach pipeline, moved verbatim out of interactive_inflater_app/app.py
(2026-09-30 modularization -- see that module's own docstring for the "club"/guest terminology).

"when a face is attached to the central group by only one edge, it is going to flop around
because it's too unconstrained. that face should be excluded from the relaxation/inflation
process completely. it should be attached to the face it's connected to after the relaxation/
inflation is done, and it should be attached parallel to that face." A face hinged to the rest
of the mesh along exactly one of its own edges has one whole rotational degree of freedom
(around that hinge) the spring/pressure network does nothing to pin down. Rather than solve it
(unconstrained by construction, so any solved position is as arbitrary as any other),
`prepare_mesh_for_inflate` drops it from the mesh entirely before relax/inflate ever runs, then
`reattach_pendant_faces` lays it back on, flat/coplanar ("parallel") against whichever face it's
hinged to, once that neighbor's own final position is known -- a closed-form placement, not a
physics step.

Every function here is pure (no Tkinter/VTK/`self`) -- `InflaterPane` (app.py) calls these by
name and only keeps the Tk/threading orchestration around them.
"""
import math

import numpy as np

from utils.inflate_polyhedron.mesh_levels import subdivide_once
from interactive_inflater_app.logic.edge_indexer import (
    group_boundary_edge_set as fine_group_boundary_edges,
    base_edge_vertex_chain as rim_vertex_chain,
)

__all__ = [
    "pendant_face_attachments", "exclude_pendant_faces", "regular_polygon_rest_positions",
    "flat_pendant_fine_mesh", "fine_group_boundary_edges", "rim_vertex_chain",
    "place_pendant_flat", "reattach_pendant_faces", "pendant_own_face_edge_ids",
    "prepare_mesh_for_inflate", "place_all_flat",
]


def pendant_face_attachments(base_faces, face_edge_ids):
    """Returns {pendant_face_idx: (neighbor_face_idx, (a, b))} for every one of `base_faces`
    attached to the rest of the mesh by EXACTLY one glued edge -- `(a, b)` that edge's own
    vertex-id pair, in the SAME order `base_faces[pendant_face_idx]`'s own loop lists it.
    `neighbor_face_idx` is whichever OTHER base face shares that exact edge. A face with ZERO
    glued edges (not attached to anything -- nothing to exclude it against or reattach it to,
    e.g. a lone anchor with nothing placed yet) or TWO OR MORE (braced by more than one point of
    contact, not the "flops around" case this targets) is not included.

    Same owners-dict disambiguation as interactive_builder_app's own `_open_base_edges` (an edge
    id used by exactly one base_faces entry is a free edge; used by exactly two is a genuine
    glued edge between them) -- reimplemented here rather than extending that function, since
    this needs BOTH sides of a glued pair, not just which edges are free."""
    owners = {}
    if face_edge_ids is not None:
        for i, ids in enumerate(face_edge_ids):
            face = base_faces[i]
            n = len(face)
            for k, eid in enumerate(ids):
                owners.setdefault(eid, []).append((i, (face[k], face[(k + 1) % n])))
    else:
        for i, face in enumerate(base_faces):
            n = len(face)
            for k in range(n):
                pair = (face[k], face[(k + 1) % n])
                owners.setdefault(frozenset(pair), []).append((i, pair))
    glued_count = {}
    glued_partner = {}
    for group in owners.values():
        if len(group) != 2:
            continue
        (i0, pair0), (i1, pair1) = group
        glued_count[i0] = glued_count.get(i0, 0) + 1
        glued_count[i1] = glued_count.get(i1, 0) + 1
        glued_partner[i0] = (i1, pair0)
        glued_partner[i1] = (i0, pair1)
    return {i: glued_partner[i] for i, count in glued_count.items() if count == 1}


def exclude_pendant_faces(base_faces, base_edges, face_edge_ids, source_polygon_id=None):
    """Returns (core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id,
    pendants) -- `base_faces`/`face_edge_ids`/`source_polygon_id` with every pendant
    (pendant_face_attachments) face index dropped (all three stay index-parallel to each
    other, same as the caller's own), and `base_edges` filtered down to pairs whose BOTH
    endpoints survive (a stray reference to a now-excluded vertex would otherwise KeyError deep
    in _edge_setup's own index arrays). `pendants` is a list of {"face": <original vertex-id
    loop>, "neighbor_idx": <index into the RETURNED core_base_faces -- already remapped from
    the original list, since face_of_fine values reattach_pendant_faces later compares against
    are themselves built from core_base_faces>, "shared_pair": (a, b)} dicts, everything
    reattach_pendant_faces needs once the core mesh has been solved. Falls back to
    (base_faces, base_edges, face_edge_ids, source_polygon_id, []) UNCHANGED if excluding every
    detected pendant would leave nothing left to solve (e.g. the whole central object is just a
    2-face hinge, so each is the other's only neighbor -- the only way a pendant's own neighbor
    can ALSO be a pendant, since the central object is always one connected component: if that
    pair weren't the WHOLE object, whatever connects them to whatever else contains the anchor
    would itself be a second connection for at least one of them, contradicting "exactly one
    glued edge") -- an empty core mesh has nothing for relax_initial_configuration to do, so
    there's no safe way to exclude here."""
    attachments = pendant_face_attachments(base_faces, face_edge_ids)
    if not attachments or len(attachments) >= len(base_faces):
        return base_faces, base_edges, face_edge_ids, source_polygon_id, []
    keep = [i for i in range(len(base_faces)) if i not in attachments]
    orig_to_core = {orig_i: core_i for core_i, orig_i in enumerate(keep)}
    pendants = [{"face": base_faces[i], "neighbor_idx": orig_to_core[neighbor_idx],
                 "shared_pair": pair,
                 "source_polygon_id": (source_polygon_id[i] if source_polygon_id is not None
                                        else i)}
                for i, (neighbor_idx, pair) in attachments.items()]
    core_base_faces = [base_faces[i] for i in keep]
    core_face_edge_ids = ([face_edge_ids[i] for i in keep] if face_edge_ids is not None else None)
    core_source_polygon_id = ([source_polygon_id[i] for i in keep]
                               if source_polygon_id is not None else None)
    core_vertex_ids = {v for face in core_base_faces for v in face}
    core_base_edges = (None if base_edges is None else
                        [e for e in base_edges if e[0] in core_vertex_ids and e[1] in core_vertex_ids])
    return core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id, pendants


def regular_polygon_rest_positions(face, edge_length):
    """{vertex_id: np.array([x, y, 0.0])} for `face`'s own n corners, laid out as a REGULAR
    n-gon of side length `edge_length` in the z=0 plane -- vertex k (in `face`'s own listed,
    CCW order) at angle 2*pi*k/n, radius edge_length/(2*sin(pi/n)) (the standard circumradius
    that makes every EDGE exactly `edge_length` long, not just every vertex equidistant from
    the center). The canonical REST frame flat_pendant_fine_mesh/place_pendant_flat build on."""
    n = len(face)
    radius = edge_length / (2 * math.sin(math.pi / n))
    return {v: np.array([radius * math.cos(2 * math.pi * k / n),
                          radius * math.sin(2 * math.pi * k / n), 0.0])
            for k, v in enumerate(face)}


def flat_pendant_fine_mesh(pendant_face, edge_length):
    """Returns (faces_lvl3, positions_lvl3) -- `pendant_face` alone, fan-triangulated then
    quartered twice (subdivide_once, level 0->1->2) up to Level 3, EXACTLY as a real Full
    Inflate pipeline would, but starting from regular_polygon_rest_positions instead of a
    random Level-0 start and with NO relax/calibration call in between: every one of
    subdivide_once's own position updates is pure linear interpolation (a new vertex is a
    corner mean or an edge midpoint of whatever's already there -- see mesh_levels.py's own
    _fan_level_0_to_1/_quarter_triangles), which keeps an already-flat (z=0) input exactly flat
    the whole way through. `faces_lvl3`/`positions_lvl3` still use `pendant_face`'s OWN vertex
    ids for its 3 corners plus freshly local-to-this-call ids (from
    `next_id = 1 + max(positions)`, mesh_levels.py's own convention) for every hub/midpoint --
    the caller (exclude_pendant_faces' own pendant reattachment) is responsible for remapping
    those local ids into the real mesh's own global vertex-id space before merging anything in,
    since they're only guaranteed unique within this one call."""
    positions = regular_polygon_rest_positions(pendant_face, edge_length)
    faces, positions, edge_len, face_of_fine = subdivide_once(
        [pendant_face], positions, edge_length, [0], 0)
    for level in (1, 2):
        faces, positions, edge_len, face_of_fine = subdivide_once(
            faces, positions, edge_len, face_of_fine, level)
    return faces, positions


def place_pendant_flat(pendant, final_positions_by_id, neighbor_face_idx, level3_face_of_fine,
                        level3_faces, edge_length, next_free_id, neighbor_base_face):
    """Computes final 3D positions for one excluded pendant's ENTIRE Level-3 fine mesh, laid
    out flat/coplanar ("parallel") against whichever face it's hinged to, once that neighbor's
    own final positions are known -- see this module's own header comment for why this is a
    closed-form placement, not another relax pass. Returns (faces, positions, next_free_id,
    remapped_face) -- `faces`/`positions` already in the REAL mesh's global vertex-id space
    (remapped from flat_pendant_fine_mesh's own local ids, `next_free_id` the next unused one
    after this call), ready to concatenate straight onto the core's own self.faces/
    self.positions/self.face_of_fine (face_of_fine value: neighbor_face_idx -- see this
    function's own caller). `remapped_face` is `pendant["face"]` (the ORIGINAL, base-export-
    level corner loop) passed through this SAME id_map -- needed because a third+ corner (see
    its own comment below) no longer keeps its raw id, so it's the only correct record of what
    this pendant's own corners are actually CALLED in the mesh just built (the caller uses it
    for its own self.base_faces entry -- self.base_faces[group] must list ids that genuinely
    exist in self.positions, not stale pre-remap ones, or _rebuild_open_edges/
    base_edge_vertex_chain silently walk from a vertex id that was never actually placed,
    2026-09-29, explicit bug report: "highlighted a non-edge that connects a vertex to the
    centre of an opposite face" -- base_edge_vertex_chain's own "never found a path" fallback,
    a straight [u, v] chord, dead code until then).

    The pendant's own SHARED edge's intermediate (subdivision-created) vertices are PINNED to
    the core's own EXISTING ones for that same edge -- same id, same (already-solved) position,
    never independently recomputed -- not just the two endpoints `shared_pair` already reused
    (2026-09-29, explicit bug report: "not able to select any of the edges of the guest
    piece... some non-edges are highlighted when hovered over" -- flat_pendant_fine_mesh builds
    the pendant's own fine mesh as a totally SEPARATE subdivide_once run, with no way to know
    the core's own existing midpoint ids for that same physical edge, so every earlier version
    independently re-synthesized fresh ones instead -- two DIFFERENT vertex ids at the same
    physical location, which group_boundary_edge_set's own by-id matching (everything reading
    a "shared seam" ultimately goes through it) could never recognize as the same edge at all).
    `neighbor_base_face` (`self.base_faces[neighbor_face_idx]`) bounds the walk that finds the
    core's own existing chain (see rim_vertex_chain's own docstring for why that bound is
    needed at all). Also more accurate than the old recompute: a rim edge of an already-solved,
    possibly-curved neighbor isn't necessarily straight, so reusing its own real intermediate
    positions (rather than a pendant-side straight-line guess between the two endpoints) avoids
    a hairline gap/crease at the seam.

    The neighbor's own plane/normal is estimated from the MEAN of only the fine triangles
    actually touching the SHARED EDGE's own two endpoints (a local fan around the attachment
    point), not its whole fine mesh -- a neighbor face can be meaningfully curved once it's a
    real solved part of a multi-face core (unlike a lone flat "place", pressure genuinely bends
    it), and when several pendants hang off DIFFERENT edges of the SAME curved neighbor, a
    single face-wide average plane is a poor stand-in for any one of their own local tangent
    planes -- each pendant would flatten against the same blurred "average" direction instead
    of its own edge's actual local orientation, landing them overlapping/crossing each other
    instead of fanning out with the neighbor's real curvature (2026-09-28, explicit bug report:
    a pentagon core with 3 pendants on 3 different edges came out visibly tangled -- caught by
    restricting this to the local neighborhood and comparing). Falls back to the WHOLE
    neighbor's own fine mesh only if the local fan is somehow empty (shouldn't happen: `a`/`b`
    are always real neighbor vertices). The OUTWARD side (which half-plane, split by the shared
    edge, the pendant extends into) is whichever side is AWAY from this SAME local centroid, so
    the flap extends past the shared edge rather than folding back on top of the piece it's
    hinged to."""
    a, b = pendant["shared_pair"]
    p0, p1 = final_positions_by_id[a], final_positions_by_id[b]
    all_neighbor_tri_idx = [i for i, bf in enumerate(level3_face_of_fine) if bf == neighbor_face_idx]
    local_tri_idx = [i for i in all_neighbor_tri_idx if a in level3_faces[i] or b in level3_faces[i]]
    neighbor_tri_idx = local_tri_idx or all_neighbor_tri_idx
    neighbor_vertex_ids = {v for i in neighbor_tri_idx for v in level3_faces[i]}
    neighbor_normal = np.zeros(3)
    for i in neighbor_tri_idx:
        va, vb, vc = (final_positions_by_id[v] for v in level3_faces[i])
        n = np.cross(vb - va, vc - va)
        norm = np.linalg.norm(n)
        if norm > 1e-9:
            neighbor_normal += n / norm
    plane_normal = neighbor_normal / max(np.linalg.norm(neighbor_normal), 1e-9)
    neighbor_centroid = np.mean([final_positions_by_id[v] for v in neighbor_vertex_ids], axis=0)

    edge_dir = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-9)
    in_plane_perp = np.cross(plane_normal, edge_dir)
    in_plane_perp /= max(np.linalg.norm(in_plane_perp), 1e-9)
    edge_mid = (p0 + p1) / 2
    if np.dot(neighbor_centroid - edge_mid, in_plane_perp) > 0:
        in_plane_perp = -in_plane_perp  # flip so it points AWAY from the neighbor, not into it
    actual_length = np.linalg.norm(p1 - p0)
    scale = actual_length / edge_length

    local_faces, local_positions = flat_pendant_fine_mesh(pendant["face"], edge_length)
    rest_p0, rest_p1 = local_positions[a], local_positions[b]
    rest_edge_dir = (rest_p1 - rest_p0)[:2] / edge_length  # unit, since |rest_p1-rest_p0|==edge_length
    # [-y, x] for (x, y) = cross([0, 0, 1], (rest_edge_dir, 0))[:2] -- [0,0,1] being the REST
    # frame's own fixed normal (`pendant["face"]`'s vertex k sits at angle 2*pi*k/n, INCREASING
    # with k, i.e. CCW as seen from +z, by construction -- see regular_polygon_rest_positions).
    # Deliberately NOT independently sign-flipped by some rest-side "away from centroid" test:
    # using this SAME cross-product FORM on both this side and in_plane_perp's own (rest normal
    # here, plane_normal there) is what makes the rest->target mapping a pure rotation+scale,
    # never a reflection -- a separate flip on EACH side (an earlier version of this function
    # had one here too) can disagree about which way is "outward" and land the pendant
    # MIRRORED, folded back onto the neighbor instead of extending past it (caught by direct
    # numeric testing: a symmetric pendant landed exactly on top of the core's own opposite
    # corner instead of on the far side of the shared edge). The single "which of the two
    # coplanar sides" decision belongs ENTIRELY to in_plane_perp's own flip above, since that's
    # the only side with real information (the neighbor's actual position) to decide it from.
    rest_outward = np.array([-rest_edge_dir[1], rest_edge_dir[0]])

    # The core's own EXISTING chain of vertex ids from a to b along the neighbor's rim, and the
    # pendant's own ANALOGOUS chain along its own (separately-subdivided) rim -- see this
    # function's own docstring for why these get PINNED together below instead of the pendant's
    # own chain getting fresh ids/recomputed positions like everything else. Same subdivision
    # scheme (fan then quarter to the same MAX_LEVEL) on both sides always produces the same
    # NUMBER of intermediate points for one original edge regardless of curvature -- the `len`
    # guard is just defensive (never actually expected to differ).
    core_boundary = fine_group_boundary_edges(level3_faces, level3_face_of_fine, neighbor_face_idx)
    core_chain = rim_vertex_chain(a, b, core_boundary, set(neighbor_base_face))
    pendant_boundary = fine_group_boundary_edges(local_faces, [0] * len(local_faces), 0)
    pendant_chain = rim_vertex_chain(a, b, pendant_boundary, set(pendant["face"]))
    shared_chain_map = (dict(zip(pendant_chain, core_chain))
                         if len(pendant_chain) == len(core_chain) else {})

    # Every corner except the two literally SHARED with the neighbor (a, b, already real
    # global ids) gets a FRESH id here -- including a pendant's own THIRD+ original corner
    # (n > 3, e.g. every pentagon), not just flat_pendant_fine_mesh's own genuinely-new
    # subdivision vertices. An earlier version kept a third+ corner's own original (base-
    # export-level) id as-is, on the theory that it was already a real, reserved global id --
    # but that id space belongs to the WHOLE original net export, while the CORE's own Level-3
    # fine mesh numbers its subdivision-created vertices independently (starting fresh from
    # its own "1 + max" at build time, with no idea some small integer is "reserved" by a
    # pendant not even part of its own solve) -- the two can and do collide on an unrelated
    # vertex (2026-09-29, explicit bug report: "spiky artifacts" persisting through
    # re-inflate/rotation -- traced to exactly this: a core face's own fine-mesh vertex
    # silently got its position overwritten by an unrelated pendant corner that happened to
    # reuse the same numeric id, stretching that core triangle into a giant sliver). Exactly
    # the same bug _diff_attach_pendant_only's own docstring already documents and fixes for
    # its own separate code path ("a just-added pendant's own free corner silently overwrote
    # an existing Level-3 midpoint that happened to share its raw id") -- this path just never
    # got the same fix.
    id_map = {a: a, b: b}
    faces_out = []
    positions_out = {a: p0, b: p1}
    for v in local_positions:
        if v in id_map:
            continue
        if v in shared_chain_map:
            id_map[v] = shared_chain_map[v]
        else:
            id_map[v] = next_free_id
            next_free_id += 1
    for v, local_pos in local_positions.items():
        if v in (a, b) or v in shared_chain_map:
            continue
        rel = local_pos[:2] - rest_p0[:2]
        along = np.dot(rel, rest_edge_dir)
        perp = np.dot(rel, rest_outward)
        positions_out[id_map[v]] = p0 + edge_dir * along * scale + in_plane_perp * perp * scale
    for local_v, core_v in shared_chain_map.items():
        positions_out[core_v] = final_positions_by_id[core_v]
    for face in local_faces:
        faces_out.append([id_map[v] for v in face])
    # The pendant's own ORIGINAL corner loop (pendant["face"]), remapped through id_map --
    # since a THIRD+ corner (above) no longer keeps its own raw id, this is the ONLY correct
    # way to know what its corners are actually CALLED in the output mesh (positions_out/
    # faces_out) -- see this function's own caller for why that distinction matters.
    remapped_face = [id_map[v] for v in pendant["face"]]
    return faces_out, positions_out, next_free_id, remapped_face


def reattach_pendant_faces(pendants, faces, positions, face_of_fine, edge_length, own_groups,
                            core_base_faces):
    """Runs place_pendant_flat for every excluded pendant against the just-solved CORE mesh's
    own final faces/positions/face_of_fine, and returns (faces, positions, face_of_fine) with
    every pendant's own flat Level-3 fine mesh concatenated on -- `face_of_fine` entries for a
    pendant's own fine triangles are `own_groups`' own matching entry (parallel to `pendants`,
    the caller's OWN reserved trailing self.base_faces/self._pending_source_polygon_id index
    for that one pendant -- 2026-09-29, explicit bug report: "not able to select the guest
    piece [in 3D]... only selectable together with the insider it's connected to... not able
    to select any of the edges of the guest piece" -- an EARLIER version tagged a pendant's own
    triangles with its `neighbor_idx` instead, folding it into the SAME pick/hover/rim group as
    the real neighbor it's attached to: clicking anywhere on either one always resolved to the
    neighbor's own shape id (self._pending_source_polygon_id has no entry for the pendant's own
    id at all), and the boundary edge shared between them canceled out INSIDE that one merged
    group instead of surviving as a rim (group_boundary_edge_set counts an edge shared by TWO
    triangles of the SAME group as interior, not a rim -- see its own docstring), so no seam
    ever showed between a guest and its neighbor either. Giving the pendant its own group fixes
    both: it's now its own independently pickable/hoverable actor, with a real rim of its own,
    without changing place_pendant_flat's own geometry at all (`neighbor_face_idx`, read from
    `pendant["neighbor_idx"]` below, is still what its PLACEMENT is computed against -- only the
    OUTPUT tag changes). No-op (returns the inputs unchanged) if `pendants` is empty.

    Every place_pendant_flat call below reads `neighbor_face_idx`'s own plane/normal from
    `core_faces`/`core_face_of_fine` -- a FIXED snapshot taken once, before this loop appends
    anything -- never from the growing `faces`/`face_of_fine` themselves (2026-09-28, explicit
    bug report: "a pentagon anchor with 2+ guests hinged on ADJACENT edges of it came out
    tangled"). Two pendants hinged on the SAME neighbor face share that neighbor's own
    `neighbor_idx` value; once pendant #1 is appended, its own flat triangles are tagged with
    that SAME `neighbor_idx` too (previous paragraph) -- reading the growing lists for pendant
    #2's own neighbor-plane lookup would then also sweep up pendant #1's own already-placed
    (flat, differently-oriented) triangles as if they were more of the neighbor's real curved
    surface, corrupting pendant #2's placement whenever it happens to share a corner vertex with
    pendant #1 (caught by direct testing: place_pendant_flat's own `local_tri_idx` filter,
    which restricts to triangles touching the pendant's shared-edge vertices, isn't enough to
    exclude this -- a shared CORNER vertex between two adjacent pendants means some of pendant
    #1's own triangles pass that filter for pendant #2 too). Every pendant is independently
    flat/coplanar against the neighbor's own TRUE (already fully solved) surface regardless of
    how many other pendants also hang off it, so this snapshot is always correct, never stale.

    `core_base_faces` (the CORE's own self.base_faces, one entry per `core_face_of_fine` value)
    is threaded straight through to place_pendant_flat as each pendant's own
    `neighbor_base_face` -- see its own docstring for why.

    Also returns `remapped_base_faces` (parallel to `pendants`) -- each pendant's own
    `remapped_face` from place_pendant_flat (see its own docstring), for the caller to use
    as that pendant's OWN self.base_faces entry instead of its raw, pre-remap `pendant["face"]`
    (2026-09-29, explicit bug report: "highlighted a non-edge that connects a vertex to the
    centre of an opposite face" -- self.base_faces[group] listing an id that was never actually
    placed sent base_edge_vertex_chain's own rim walk nowhere, falling back to a straight
    chord across the polygon)."""
    if not pendants:
        return faces, positions, face_of_fine, []
    core_faces = list(faces)
    core_face_of_fine = list(face_of_fine)
    faces = list(faces)
    face_of_fine = list(face_of_fine)
    # NOT just `1 + max(positions)` -- `positions` only has the CORE's own vertex ids at this
    # point, but every pendant's own ORIGINAL corners (real, already-reserved ids from the
    # whole original net, just not present in the core-only solve) can be numerically LOWER
    # than that max while still being live ids place_pendant_flat needs to keep as-is -- a
    # "fresh" id counter that only looked at the core would collide with one of those (a real
    # bug, caught by direct numeric testing: a pendant's own un-transformed corner silently got
    # overwritten by a same-numbered subdivision vertex). Every pendant's own face is included
    # in this max too, so the count starts safely above every id that could ever appear here.
    next_free_id = 1 + max([*positions, *(v for p in pendants for v in p["face"])])
    remapped_base_faces = []
    for pendant, own_group in zip(pendants, own_groups):
        pendant_faces, pendant_positions, next_free_id, remapped_face = place_pendant_flat(
            pendant, positions, pendant["neighbor_idx"], core_face_of_fine, core_faces,
            edge_length, next_free_id, core_base_faces[pendant["neighbor_idx"]])
        faces.extend(pendant_faces)
        face_of_fine.extend([own_group] * len(pendant_faces))
        positions.update(pendant_positions)
        remapped_base_faces.append(remapped_face)
    return faces, positions, face_of_fine, remapped_base_faces


def pendant_own_face_edge_ids(pendant, base_faces, base_face_edge_ids, next_id):
    """Returns (row, next_id) -- `pendant["face"]`'s own face_edge_ids row (parallel to its
    vertex loop, same convention as interactive_builder_app._face_edge_ids_from_shapes), for
    appending alongside its own trailing self.base_faces entry (2026-09-29, explicit bug
    report: appending a pendant to self.base_faces -- see reattach_pendant_faces' own
    docstring for why -- without a matching self.base_face_edge_ids row left that list one
    entry SHORTER than self.base_faces, raising IndexError the next time _diff_remove_face
    indexed it). `None` if `base_face_edge_ids` itself is None (this mesh has no disambiguation
    data at all -- every OTHER reader already treats that as "fall back to plain vertex-pair
    matching," so there's nothing to extend). The pendant's own SHARED edge reuses whatever id
    the neighbor's own row already has for that exact edge, so the two still correctly count as
    ONE glued connection (see pendant_face_attachments' own owners-dict docstring) rather than
    two independent free edges that merely happen to share a vertex pair; every other edge of
    the pendant gets a fresh id, `next_id` and up (guaranteed not to collide with anything --
    the caller seeds `next_id` past every id already in use)."""
    if base_face_edge_ids is None:
        return None, next_id
    a, b = pendant["shared_pair"]
    neighbor_face = base_faces[pendant["neighbor_idx"]]
    neighbor_ids = base_face_edge_ids[pendant["neighbor_idx"]]
    n = len(neighbor_face)
    shared_id = next(
        (neighbor_ids[k] for k in range(n)
         if {neighbor_face[k], neighbor_face[(k + 1) % n]} == {a, b}),
        None)
    face = pendant["face"]
    m = len(face)
    row = []
    for k in range(m):
        if {face[k], face[(k + 1) % m]} == {a, b}:
            row.append(shared_id)
        else:
            row.append(next_id)
            next_id += 1
    return row, next_id


def prepare_mesh_for_inflate(base_faces, base_edges, face_edge_ids, source_polygon_id=None):
    """Returns ("solve", core_base_faces, core_base_edges, core_face_edge_ids,
    core_source_polygon_id, pendants) for the ordinary case -- exactly exclude_pendant_faces'
    own return shape, just tagged with which mode applies -- or ("place", reference_face,
    pendants) when there's nothing worth running relax/inflate on AT ALL (2026-09-28, explicit
    user request: "when only one piece is on the canvas, it is also considered unstable... just
    place the piece flat. and if a second piece is joined to it at only one edge, then both are
    unstable... both should just be placed instead of inflated").

    "solve" needs the CORE (every ordinary pendant excluded) to have at least 2 faces -- with
    fewer than that, there's no genuine bracing left for physics to mean anything: a single
    core face has no neighbor to relax against at all. Checking `core_base_faces`' own size
    ALONE isn't enough to decide this, though -- exclude_pendant_faces' own fallback (excluding
    every detected pendant would leave nothing, i.e. the WHOLE object is a mutual single-edge
    pair with nothing else) returns a 2-face "core" that LOOKS large enough, but whose own two
    faces are STILL only single-edge-hinged to EACH OTHER, exactly as unconstrained as a lone
    face -- so this checks pendant_face_attachments directly first, to tell "nothing was
    excluded because nothing needed to be" (attachments empty -- a genuinely braced mesh, e.g.
    a closed net) apart from "nothing was excluded because excluding it all would leave
    nothing" (attachments covers every face -- always degenerate).

    "place" picks a fixed reference face (placed flat/centered with no neighbor to hinge
    against) and folds every OTHER face into ONE combined `pendants` list, all hinged directly
    on that SAME reference -- place_all_flat lays every one of them out with no physics at
    all. A degenerate mesh can only ever have the reference plus pendants hinged DIRECTLY on
    it, never a deeper chain: a connected graph where every node but one has degree <= 1 can
    only be a star centered on that one node (any OTHER shape would need a path of length >= 2
    to reach it, which would force an intermediate node to degree >= 2, making that node's own
    -- and every node's -- "core" at least 2 faces, taking the "solve" path instead)."""
    attachments = pendant_face_attachments(base_faces, face_edge_ids)
    if attachments and len(attachments) < len(base_faces):
        core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id, pendants = \
            exclude_pendant_faces(base_faces, base_edges, face_edge_ids, source_polygon_id)
        if len(core_base_faces) >= 2:
            return ("solve", core_base_faces, core_base_edges, core_face_edge_ids,
                    core_source_polygon_id, pendants)
        # Excluding every ordinary pendant left a LONE core face (e.g. a 3-face straight chain,
        # A-B-C: A and C are each pendant to hub B, and B alone is left with no surviving
        # neighbor of its own) -- still degenerate; B becomes the reference below, A/C its
        # pendants (already correctly attached to core index 0, i.e. B, by
        # exclude_pendant_faces' own neighbor_idx remapping).
        reference_face = core_base_faces[0]
        reference_spid = core_source_polygon_id[0] if core_source_polygon_id is not None else 0
        return "place", reference_face, reference_spid, pendants
    if not attachments and len(base_faces) >= 2:
        # No pendant relationship detected at all -- a genuinely braced mesh (every face has
        # either 0 glued edges, impossible for a connected multi-face object, or >= 2).
        return "solve", base_faces, base_edges, face_edge_ids, source_polygon_id, []
    # Degenerate: a lone face (attachments empty, len(base_faces) == 1), or a mutual single-edge
    # pair (attachments covers both, len(base_faces) == 2).
    reference_face = base_faces[0]
    reference_spid = source_polygon_id[0] if source_polygon_id is not None else 0
    extra_pendants = []
    if len(base_faces) == 2:
        second = base_faces[1]
        second_spid = source_polygon_id[1] if source_polygon_id is not None else 1
        shared = set(reference_face) & set(second)
        n = len(second)
        shared_pair = next((second[k], second[(k + 1) % n]) for k in range(n)
                            if {second[k], second[(k + 1) % n]} == shared)
        extra_pendants.append({"face": second, "neighbor_idx": 0, "shared_pair": shared_pair,
                                "source_polygon_id": second_spid})
    return "place", reference_face, reference_spid, extra_pendants


def place_all_flat(reference_face, pendants, edge_length):
    """Builds a full Level-3 mesh (faces, positions, face_of_fine, base_faces,
    source_polygon_id) with NO physics at all -- 2026-09-28, explicit user request, see
    prepare_mesh_for_inflate's own docstring for when this applies. `reference_face` is placed
    flat/centered as a fixed reference (base index 0, via flat_pendant_fine_mesh -- the exact
    same flat construction a pendant's own fine mesh uses); every one of `pendants` (all hinged
    directly on `reference_face` -- see prepare_mesh_for_inflate's own proof) is then flat-
    attached against it via reattach_pendant_faces, the SAME closed-form geometry a real
    pendant uses post-solve."""
    local_faces, local_positions = flat_pendant_fine_mesh(reference_face, edge_length)
    # Local hub/midpoint ids from flat_pendant_fine_mesh are only guaranteed unique WITHIN
    # that one call (see its own docstring) -- remapped here to ids guaranteed safe against
    # every pendant's own real corners too, same "keep real corners, remap the rest" pattern
    # place_pendant_flat's own id_map uses.
    all_real_ids = set(reference_face) | {v for p in pendants for v in p["face"]}
    next_id = 1 + max([*all_real_ids, *local_positions])
    id_map = {}
    for v in local_positions:
        if v in reference_face:
            id_map[v] = v
        else:
            id_map[v] = next_id
            next_id += 1
    faces = [[id_map[v] for v in face] for face in local_faces]
    positions = {id_map[v]: pos for v, pos in local_positions.items()}
    face_of_fine = [0] * len(faces)
    # own_groups: reference_face is base_faces[0], each pendant its own trailing index (1..N)
    # -- see this function's own base_faces line below, and reattach_pendant_faces' own
    # docstring for why each pendant needs a DISTINCT tag rather than sharing its neighbor's.
    faces, positions, face_of_fine, remapped_base_faces = reattach_pendant_faces(
        pendants, faces, positions, face_of_fine, edge_length,
        list(range(1, 1 + len(pendants))), [reference_face])
    # remapped_base_faces, NOT raw p["face"] -- see reattach_pendant_faces' own docstring for
    # why a pendant's own THIRD+ corner no longer keeps its raw id.
    base_faces = [reference_face, *remapped_base_faces]
    return faces, positions, face_of_fine, base_faces
