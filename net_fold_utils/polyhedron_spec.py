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
it must form a spanning tree over all faces (len(net) == len(faces) - 1).

"edges.extra" lists edges [f1, f2] that only meet once folded -- faces not
directly hinged in the net but adjacent in the finished solid. These pin
down the fold angles so the solid is fully and uniquely determined.

No coordinates or angles are ever hand-written -- both are derived from
this combinatorial description.
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
    for i, face in enumerate(faces):
        if face.get("id") != i:
            raise ValueError(f"{path}: faces must be declared in order "
                              f"(expected id {i}, got {face.get('id')})")
        degrees.append(face["sides"])
        if face.get("isRoot"):
            if root is not None:
                raise ValueError(f"{path}: more than one face marked isRoot "
                                  f"({root} and {i})")
            root = i
    if root is None:
        root = 0

    edges = spec.get("edges") or {}
    net_edges = [tuple(e) for e in edges.get("net", [])]
    extra_edges = [tuple(e) for e in edges.get("extra", [])]
    name = spec.get("name")

    if len(net_edges) != len(degrees) - 1:
        raise ValueError(
            f"{path}: net must contain exactly {len(degrees) - 1} edges "
            f"(a spanning tree over {len(degrees)} faces), found {len(net_edges)}")

    return degrees, net_edges, extra_edges, root, (name or path)


def _json_array(items, item_indent, closing_indent):
    """A JSON array with one compact entry per line -- json.dump's own
    indent=2 would instead explode each nested {..}/[..] entry across
    several lines, which is unreadable for a list of hundreds of edges."""
    if not items:
        return "[]"
    body = ",\n".join(f"{item_indent}{item}" for item in items)
    return f"[\n{body}\n{closing_indent}]"


def write_polyhedron_spec(path, degrees, net_edges, extra_edges, root, name=None):
    lines = ["{"]
    if name:
        lines.append(f"  {json.dumps('name')}: {json.dumps(name)},")
    faces = []
    for i, k in enumerate(degrees):
        face = f'{{"id": {i}, "sides": {k}}}' if i != root \
            else f'{{"id": {i}, "sides": {k}, "isRoot": true}}'
        faces.append(face)
    lines.append(f'  "faces": {_json_array(faces, "    ", "  ")},')
    net = [f"[{a}, {b}]" for a, b in net_edges]
    extra = [f"[{a}, {b}]" for a, b in extra_edges]
    lines.append('  "edges": {')
    lines.append(f'    "net": {_json_array(net, "      ", "    ")},')
    lines.append(f'    "extra": {_json_array(extra, "      ", "    ")}')
    lines.append("  }")
    lines.append("}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
