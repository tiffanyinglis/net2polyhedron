"""Parser and writer for the polyhedron spec format (JSON) -- a direct
encoding of a model.Polyhedron: real 3D vertex positions plus CCW
(viewed-from-outside) face vertex-index loops. No combinatorics to derive
(no root, no net/extra edge split, no per-face degree list) -- NetUnfolder
(src/utils/polyhedron_unfolder/) figures out the spanning tree, flat layout, and
fold angles itself from whatever geometry is given here.

    {
      "name": "Cube",
      "vertices": [[1, 1, 1], [1, 1, -1], ...],
      "faces": [[0, 1, 2, 3], [4, 5, 6, 7], ...]
    }

An "open" net (a solid with some faces deliberately missing) is just a spec
whose "faces" list is a subset -- there's no separate omit/hidden-edge
bookkeeping needed, since NetUnfolder derives face adjacency straight from
whichever faces ARE listed. Only include the vertices actually referenced
by "faces": an unreferenced vertex would still count toward
apps/common/bounding_box.py's bounding_box(), silently enlarging it around
a point nothing actually renders.
"""
import json


def load_polyhedron_spec(path):
    """Returns (vertices, faces, name) -- vertices: list[list[float]] (each
    length 3), faces: list[list[int]] (each a CCW vertex-index loop),
    name: str or None."""
    with open(path) as f:
        spec = json.load(f)

    vertices = spec.get("vertices") or []
    faces = spec.get("faces") or []
    if not vertices:
        raise ValueError(f"{path}: no vertices declared")
    if not faces:
        raise ValueError(f"{path}: no faces declared")

    n = len(vertices)
    for face in faces:
        for i in face:
            if not (0 <= i < n):
                raise ValueError(f"{path}: face references vertex {i}, "
                                  f"but only {n} vertices are declared")

    return vertices, faces, spec.get("name")


def _json_array(items, item_indent, closing_indent):
    """A JSON array with one compact entry per line -- json.dump's own
    indent=2 would instead explode each nested [...] entry across several
    lines, which is unreadable for a list of many vertices/faces."""
    if not items:
        return "[]"
    body = ",\n".join(f"{item_indent}{item}" for item in items)
    return f"[\n{body}\n{closing_indent}]"


def write_polyhedron_spec(path, vertices, faces, name=None):
    lines = ["{"]
    if name:
        lines.append(f"  {json.dumps('name')}: {json.dumps(name)},")
    vertex_strs = [f"[{x:.6f}, {y:.6f}, {z:.6f}]" for x, y, z in vertices]
    face_strs = [f"[{', '.join(str(i) for i in face)}]" for face in faces]
    lines.append(f'  "vertices": {_json_array(vertex_strs, "    ", "  ")},')
    lines.append(f'  "faces": {_json_array(face_strs, "    ", "  ")}')
    lines.append("}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
