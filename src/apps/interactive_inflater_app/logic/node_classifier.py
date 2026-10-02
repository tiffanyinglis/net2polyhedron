"""Active-group/reachable-node/terminal-node/junction-node/unreachable-node classification,
moved out of interactive_inflater_app/app.py (2026-09-30 modularization). See that module's own
docstring for the terminology: the anchor shape's connected component is the ACTIVE GROUP; every
shape in it is a REACHABLE NODE; a reachable node with 0-1 connections is a TERMINAL NODE; a
reachable node with >=2 connections is a JUNCTION NODE; a shape not in the active group at all is
an UNREACHABLE NODE.

Every function here is pure (no Tkinter/`self`) -- `BuilderPane`/`InflaterPane` (app.py) call
these by name and only keep their own state (self.shapes/self.connections/etc.) around them.
"""

__all__ = [
    "shape_connected_components", "central_shape_ids", "connection_key", "classify_change",
    "plan_anchor_deletion", "is_pendant_add",
]


def shape_connected_components(shapes, connections):
    """shapes: list of shape dicts with an "id"; connections: list of connection dicts with
    "a_shape"/"b_shape". Returns a list of sets of shape ids, one per connected component
    (union-find over the connection graph -- a shape with no connection at all is its own
    singleton component)."""
    parent = {shape["id"]: shape["id"] for shape in shapes}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for conn in connections:
        a, b = find(conn["a_shape"]), find(conn["b_shape"])
        if a != b:
            parent[a] = b

    components = {}
    for shape in shapes:
        root = find(shape["id"])
        components.setdefault(root, set()).add(shape["id"])
    return list(components.values())


def central_shape_ids(shapes, connections, anchor_shape_id):
    """The "central object" (the active group): the connected component containing
    `anchor_shape_id`. Empty frozenset if `shapes` is empty or `anchor_shape_id` isn't (or is no
    longer) one of `shapes`' own ids -- callers needing a fallback (e.g. a freshly loaded net
    whose anchor hasn't been assigned yet) handle that themselves."""
    for component in shape_connected_components(shapes, connections):
        if anchor_shape_id in component:
            return frozenset(component)
    return frozenset()


def connection_key(conn):
    """A connection's own two (shape_id, edge_index) endpoints, as a frozenset (so a<->b/b<->a
    order doesn't matter) -- the comparison key for "is this the SAME connection across two
    snapshots", used by both `classify_change` and `InflaterPane._stage_kept_selection` (to
    re-find a connection `classify_change` already identified by endpoints alone back in a
    shapes/connections snapshot)."""
    return frozenset([(conn["a_shape"], conn["a_edge"]), (conn["b_shape"], conn["b_edge"])])


def classify_change(old_shapes, old_connections, old_anchor_shape_id,
                     new_shapes, new_connections, new_anchor_shape_id):
    """`old_*`: a prior snapshot (or `old_shapes is None`, meaning "never inflated yet").
    `new_*`: the live builder state to compare against. Returns (kind, extra) where kind is
    "none" (no topology change), "add_face" (EXACTLY one shape added and nothing else about the
    surviving net's topology changed -- extra is that one shape's id), "remove_face" (ONE OR
    MORE shapes removed at once and nothing else about the surviving net's topology changed --
    2026-09-19, explicit: "if multiple faces are deleted at once, let that qualify for diff
    inflate/auto inflate" -- extra is the SET of removed shape ids; adding is still capped at
    exactly one, since the diff-add pipeline's interpolation only ever seeds ONE new shape's
    fresh vertices from its own connection(s) to the surviving mesh), "add_connection"/
    "remove_connection" (same shape SET, but exactly one connection added/removed and no shape's
    own n/flipped changed -- extra is that connection's own conn_key, unused by the caller but
    handy for debugging), or "complex" (anything else -- a moved/flipped/multi-shape ADD, more
    than one connection edited at once, etc.), extra is None for "none"/"complex".

    A shape's cx/cy/rotation never affect the exported mesh at all (only n/flipped and the
    connection graph do), so those are deliberately ignored here: dragging a shape around never
    disables Diff Inflate. Connections are compared by their (shape, edge) endpoints only
    (frozenset, so a<->b/b<->a order doesn't matter) -- a connection's own bezier handles are a
    pure drawing detail, never read by the exported mesh either.

    Both snapshots are restricted to their OWN central object first (`central_shape_ids`, same
    restriction `export_mesh_dict` applies) before anything else below runs, so placing (or
    removing) a shape that never joins the central object at all classifies as "none": it
    doesn't change what actually gets exported/inflated, so it shouldn't disable Diff Inflate or
    fire an unnecessary Auto Inflate re-run either."""
    if old_shapes is None:
        return "complex", None
    old_central = central_shape_ids(old_shapes, old_connections, old_anchor_shape_id)
    old_shapes = [s for s in old_shapes if s["id"] in old_central]
    old_connections = [c for c in old_connections
                        if c["a_shape"] in old_central and c["b_shape"] in old_central]
    new_central = central_shape_ids(new_shapes, new_connections, new_anchor_shape_id)
    new_shapes = [s for s in new_shapes if s["id"] in new_central]
    new_connections = [c for c in new_connections
                        if c["a_shape"] in new_central and c["b_shape"] in new_central]

    old_by_id = {s["id"]: s for s in old_shapes}
    new_by_id = {s["id"]: s for s in new_shapes}
    old_ids, new_ids = set(old_by_id), set(new_by_id)
    added, removed, common = new_ids - old_ids, old_ids - new_ids, old_ids & new_ids
    for sid in common:
        a, b = old_by_id[sid], new_by_id[sid]
        if a["n"] != b["n"] or a.get("flipped", False) != b.get("flipped", False):
            return "complex", None

    def touches(key, shape_id):
        return any(sid == shape_id for sid, _edge in key)

    def touches_any(key, shape_ids):
        return any(sid in shape_ids for sid, _edge in key)

    old_conns = {connection_key(c) for c in old_connections}
    new_conns = {connection_key(c) for c in new_connections}
    conn_added, conn_removed = new_conns - old_conns, old_conns - new_conns

    if len(added) == 1 and not removed:
        (new_id,) = added
        if conn_removed or any(not touches(k, new_id) for k in conn_added):
            return "complex", None
        return "add_face", new_id
    if removed and not added:
        if conn_added or any(not touches_any(k, removed) for k in conn_removed):
            return "complex", None
        return "remove_face", frozenset(removed)
    if not added and not removed:
        if not conn_added and not conn_removed:
            return "none", None
        if len(conn_added) == 1 and not conn_removed:
            return "add_connection", next(iter(conn_added))
        if len(conn_removed) == 1 and not conn_added:
            return "remove_connection", next(iter(conn_removed))
    return "complex", None


def plan_anchor_deletion(shapes, connections, old_central, deleted_ids):
    """Called when `deleted_ids` (about to be deleted) contains the CURRENT anchor -- decides
    whether that's allowed and, if so, who the new anchor should be. `shapes`/`connections` are
    the CURRENT, still-intact lists (before anything is actually removed); `old_central` is the
    active group's current reachable-node set (`central_shape_ids(shapes, connections,
    anchor_shape_id)`): every component the OLD central object's own SURVIVING reachable nodes
    fall into, post-deletion, is checked -- more than one means deleting the anchor would split
    the active group into two or more separate pieces, which is never allowed (2026-09-29,
    explicit: "if the user tries to delete the anchor and it splits the club into two, then it's
    not allowed. show a dialog explaining why").

    Returns (allowed, new_anchor_id):
    - (False, None): blocked -- a split. Caller shows the explanatory dialog and leaves the
      anchor out of the deletion.
    - (True, None): allowed, and nothing of the old central object survives at all (the whole
      active group is being deleted along with the anchor) -- no replacement anchor is needed.
    - (True, some_id): allowed, with `some_id` the shape that should become the new anchor --
      "assign another insider piece as the anchor... the insider with the most connections"
      (2026-09-29, explicit), i.e. the surviving reachable node of the (still intact) active
      group with >= 2 remaining connections and the highest connection count among those;
      falling back to the best-connected survivor overall if no junction node survives (e.g. the
      active group shrinks to a single piece, or to two terminal nodes only connected to each
      other)."""
    surviving_central = old_central - deleted_ids
    if not surviving_central:
        return True, None
    surviving_shapes = [s for s in shapes if s["id"] not in deleted_ids]
    surviving_connections = [
        c for c in connections
        if c["a_shape"] not in deleted_ids and c["b_shape"] not in deleted_ids]
    components = shape_connected_components(surviving_shapes, surviving_connections)
    if len([comp for comp in components if comp & surviving_central]) > 1:
        return False, None
    connection_counts = {}
    for c in surviving_connections:
        connection_counts[c["a_shape"]] = connection_counts.get(c["a_shape"], 0) + 1
        connection_counts[c["b_shape"]] = connection_counts.get(c["b_shape"], 0) + 1
    junction_nodes = [sid for sid in surviving_central if connection_counts.get(sid, 0) >= 2]
    pool = junction_nodes or list(surviving_central)
    new_anchor_id = max(pool, key=lambda sid: (connection_counts.get(sid, 0), -sid))
    return True, new_anchor_id


def is_pendant_add(connections, new_shape_id):
    """True iff `new_shape_id` (classify_change's own "add_face" `extra`, always a BRAND NEW
    shape with no prior connections at all) currently has EXACTLY ONE connection in `connections`
    -- i.e. it would be a terminal node (0-or-1-connection reachable node) were this exported and
    inflated right now -- AND that connection's OTHER end (the neighbor it's hinging onto) does
    NOT get PROMOTED from terminal node to junction node by gaining this one extra connection.
    Plain connection counting for new_shape_id's own count is enough (no need for
    pendant_face_attachments' own face_edge_ids disambiguation): being brand new, EVERY
    connection touching it is necessarily its own, so the count IS its own glued-edge count.

    A terminal node is 0 OR 1 connections (2026-09-28, explicit correction: "Guests are members
    with 0 or 1 connections") -- the neighbor's OWN prior connection count (excluding this new
    one) decides what this edit does to IT: 0 -> stays a terminal node (0 -> 1, a mutual
    terminal-node pair, both flatly placed); exactly 1 -> PROMOTED to junction node (1 -> 2), a
    real change to the active group's junction nodes needing a genuine reinflate (diff or full),
    not the fast flat-attach-only path taken when nothing about the junction nodes actually
    changed; 2+ -> already a junction node, unaffected either way."""
    count = sum(1 for c in connections
                if c["a_shape"] == new_shape_id or c["b_shape"] == new_shape_id)
    if count != 1:
        return False
    conn = next(c for c in connections
                if c["a_shape"] == new_shape_id or c["b_shape"] == new_shape_id)
    neighbor_id = conn["b_shape"] if conn["a_shape"] == new_shape_id else conn["a_shape"]
    neighbor_other_connections = sum(
        1 for c in connections
        if c["id"] != conn["id"] and (c["a_shape"] == neighbor_id or c["b_shape"] == neighbor_id))
    return neighbor_other_connections != 1
