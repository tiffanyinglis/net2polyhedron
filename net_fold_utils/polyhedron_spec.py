"""Parser and writer for the abstract polyhedron-net spec format (JSON):

    {
      "name": "Cube",
      "faces": [
        {"id": 0, "sides": 4, "isRoot": true},
        {"id": 1, "sides": 4},
        ...
      ],
      "edges": {
        "net": [[0, 1], [0, 2], ...],
        "extra": [[1, 2], [1, 3], ...]
      }
    }

"faces" gives each face's number of sides (a regular k-gon), with an
explicit "id" per face (0, 1, 2, ... in order) so faces stay easy to look
up and cross-reference by number even in a long list. The face the flat
net is built outward from is marked "isRoot": true; if no face is marked,
face 0 is the root.

"edges.net" lists the hinge edges [f1, f2] joining faces in the flat net;
it must form a spanning tree over every non-omitted face (see "omit"
below): len(net) == len(faces) - len(omitted) - 1.

"edges.extra" lists edges [f1, f2] that only meet once folded -- faces not
directly hinged in the net but adjacent in the finished solid. These pin
down the fold angles so the solid is fully and uniquely determined.

No coordinates or angles are ever hand-written -- both are derived from
this combinatorial description.

OPEN nets (a net that doesn't fold up into a fully closed solid, e.g. a
polyhedron with one or more faces missing) can mark the missing faces
"omit": true. An omitted face still needs a "sides" entry and still
needs every one of its real edges listed (in "edges.hidden", see below)
-- it's never built into 2D/3D geometry or physically hinged/folded, but
the *combinatorics* of a missing face still matter: they're what let the
faces bordering the hole recover their correct polygon-edge index for
the neighbors they DO have (net_fold_utils.combinatorics.EdgeMap derives
every face's edge order from the whole adjacency graph via a planar
embedding, per Whitney's uniqueness theorem for 3-connected planar
graphs -- which requires the *complete* graph, omitted faces included,
to come out right). Concretely: generate an open net the same way as a
normal one (e.g. via hull_to_spec.py against a real solid's
coordinates), then simply mark the faces you don't want physically
present as omitted, without dropping any of their edges from the spec.

"edges.hidden" lists every edge [f1, f2] touching at least one omitted
face -- present only so EdgeMap sees the complete graph; never used as a
physical hinge (edges.net) or a fold-closure constraint (edges.extra),
since an omitted face has no 3D position to hinge from or close against.
Omit or leave empty for an ordinary (fully closed) net.
"""
import json


def load_polyhedron_spec(path):
    with open(path) as f:
        spec = json.load(f)

    faces = spec.get("faces") or []
    if not faces:
        raise ValueError(f"{path}: no faces declared")

    degrees = []
    root = None
    omitted = set()
    for i, face in enumerate(faces):
        if face.get("id") != i:
            raise ValueError(f"{path}: faces must be declared in order "
                              f"(expected id {i}, got {face.get('id')})")
        degrees.append(face["sides"])
        if face.get("omit"):
            omitted.add(i)
        if face.get("isRoot"):
            if root is not None:
                raise ValueError(f"{path}: more than one face marked isRoot "
                                  f"({root} and {i})")
            root = i
    if root is None:
        root = 0
    if root in omitted:
        raise ValueError(f"{path}: root face {root} cannot be omitted")

    edges = spec.get("edges") or {}
    net_edges = [tuple(e) for e in edges.get("net", [])]
    extra_edges = [tuple(e) for e in edges.get("extra", [])]
    hidden_edges = [tuple(e) for e in edges.get("hidden", [])]
    name = spec.get("name")

    expected_net_len = len(degrees) - len(omitted) - 1
    if len(net_edges) != expected_net_len:
        raise ValueError(
            f"{path}: net must contain exactly {expected_net_len} edges "
            f"(a spanning tree over {len(degrees) - len(omitted)} non-omitted "
            f"faces), found {len(net_edges)}")

    return degrees, net_edges, extra_edges, hidden_edges, omitted, root, (name or path)


def _json_array(items, item_indent, closing_indent):
    """A JSON array with one compact entry per line -- json.dump's own
    indent=2 would instead explode each nested {..}/[..] entry across
    several lines, which is unreadable for a list of hundreds of edges."""
    if not items:
        return "[]"
    body = ",\n".join(f"{item_indent}{item}" for item in items)
    return f"[\n{body}\n{closing_indent}]"


def write_polyhedron_spec(path, degrees, net_edges, extra_edges, root, name=None,
                           omitted=None, hidden_edges=None):
    """omitted (a set/iterable of face ids) and hidden_edges are for OPEN
    nets only (see the module docstring); left as None/empty, the output
    is exactly the ordinary closed-net format."""
    omitted = set(omitted or ())
    hidden_edges = hidden_edges or []
    lines = ["{"]
    if name:
        lines.append(f"  {json.dumps('name')}: {json.dumps(name)},")
    faces = []
    for i, k in enumerate(degrees):
        attrs = f'"id": {i}, "sides": {k}'
        if i == root:
            attrs += ', "isRoot": true'
        if i in omitted:
            attrs += ', "omit": true'
        faces.append(f"{{{attrs}}}")
    lines.append(f'  "faces": {_json_array(faces, "    ", "  ")},')
    net = [f"[{a}, {b}]" for a, b in net_edges]
    extra = [f"[{a}, {b}]" for a, b in extra_edges]
    hidden = [f"[{a}, {b}]" for a, b in hidden_edges]
    lines.append('  "edges": {')
    if hidden:
        lines.append(f'    "net": {_json_array(net, "      ", "    ")},')
        lines.append(f'    "extra": {_json_array(extra, "      ", "    ")},')
        lines.append(f'    "hidden": {_json_array(hidden, "      ", "    ")}')
    else:
        lines.append(f'    "net": {_json_array(net, "      ", "    ")},')
        lines.append(f'    "extra": {_json_array(extra, "      ", "    ")}')
    lines.append("  }")
    lines.append("}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
