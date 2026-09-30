"""Detects and resolves SELF-JOINED faces in a raw vertex-loop `faces`
list, at net-LOAD time -- before any other pipeline step (triangulation,
random start, relax) ever runs.

A self-joined face is a single polygon with two of its OWN edges glued
to each other (e.g. a "pinched leg" appendage folded onto itself) -- see
stretchy_mesh.py's module docstring for the winding convention and
paper.tex's "Self joins" section for the physical picture. In this
vertex-loop representation ("shared vertices ARE the adjacency"), that
shows up as a REPEATED vertex id within one face's own loop: e.g. a
hexagon `[0, 1, 2, 3, 4, 5]` folded so corner 3 coincides with corner 1
and corner 4 with corner 0 becomes `[0, 1, 2, 1, 0, 5]`.

interactive_builder_app already resolves this at Save time
(`_expand_folded_shapes`), fan-triangulating a folded shape from a FRESH
centroid vertex BEFORE its corners ever get merged into the repeated-id
form -- so a net produced there never reaches this module with a
self-join at all. This module exists so inflate_polyhedron_app's own
loader doesn't depend on that: a RAW/hand-authored .poly/.json file that
encodes a self-join directly as a repeated-id loop is split the same way
right here, at load time.

Fan-triangulating BY LOOP POSITION (not by distinct vertex id) is exactly
what resolves the fold correctly with no extra bookkeeping: each original
edge (a consecutive pair in the loop) becomes one wedge triangle's own
outer edge, and any two wedges whose outer edge repeats the same id pair
end up correctly GLUED to each other (one wedge's v->w matching the
other's w->v) purely because the repeated ids already encode which
wedges glue to which."""


def has_self_join(face):
    """True iff `face` (a vertex-id loop) references some vertex id more
    than once -- i.e. this single face is folded onto itself (see module
    docstring)."""
    return len(set(face)) < len(face)


def split_self_joined_faces(faces):
    """faces: vertex-id loops (see stretchy_mesh's winding convention).
    Returns a new faces list where every self-joined face (has_self_join)
    is fan-triangulated from a FRESH centroid vertex id (one new id per
    such face, numbered after the current max vertex id) into
    `len(face)` triangles -- `[centroid, face[i], face[i + 1]]` for each
    consecutive pair, wrapping around. A face with no self-join passes
    through unchanged, and `faces` itself is returned as-is (not copied)
    if nothing needed splitting."""
    if not any(has_self_join(face) for face in faces):
        return faces
    next_id = max(v for face in faces for v in face) + 1
    expanded = []
    for face in faces:
        if not has_self_join(face):
            expanded.append(face)
            continue
        centroid = next_id
        next_id += 1
        n = len(face)
        for i in range(n):
            expanded.append([centroid, face[i], face[(i + 1) % n]])
    return expanded
