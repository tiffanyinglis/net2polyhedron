"""Parser/writer for the polyhedron JSON spec: real 3D vertex positions
plus CCW (viewed-from-outside) face vertex-index loops.

    {
      "name": "Cube",
      "vertices": [[1, 1, 1], [1, 1, -1], ...],
      "faces": [[0, 1, 2, 3], [4, 5, 6, 7], ...]
    }

An "open" net just lists a subset of a solid's faces; only include
vertices actually referenced by "faces".
"""
import json


def load_polyhedron_json(path):
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


def write_polyhedron_json(path, vertices, faces, name=None):
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
