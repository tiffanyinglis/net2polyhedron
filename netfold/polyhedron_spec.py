"""Parser and writer for the abstract polyhedron-net spec format:

    # optional name comment
    FACES
    4      <- face 0 is a square (regular 4-gon)
    4      <- face 1
    ...

    ROOT 0

    NET
    0 1    <- face 0 and face 1 are joined by a hinge in the flat net
    0 2
    ...    (must form a spanning tree over all faces: len(NET) == n-1)

    EXTRA
    2 5    <- face 2 and face 5 meet along an edge once folded, but are not
    3 5        directly hinged in the net -- these pin down the fold angles
    ...        so the solid is fully and uniquely determined

Faces are numbered 0, 1, 2, ... in the order their FACES lines appear. No
coordinates or angles are given -- both are derived from this combinatorial
description.
"""

SECTIONS = {"FACES", "NET", "EXTRA"}


def load_polyhedron_spec(path):
    degrees, net_edges, extra_edges = [], [], []
    root, name, section = None, None, None

    with open(path) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                if name is None:
                    name = line.lstrip("#").strip()
                continue

            head = line.split()[0].upper()
            if head in SECTIONS:
                section = head
                continue
            if head == "ROOT":
                root = int(line.split()[1])
                section = None
                continue

            if section == "FACES":
                degrees.append(int(line))
            elif section == "NET":
                a, b = map(int, line.split())
                net_edges.append((a, b))
            elif section == "EXTRA":
                a, b = map(int, line.split())
                extra_edges.append((a, b))
            else:
                raise ValueError(f"{path}: line outside any section: {line!r}")

    if not degrees:
        raise ValueError(f"{path}: no FACES declared")
    if root is None:
        root = 0
    if len(net_edges) != len(degrees) - 1:
        raise ValueError(
            f"{path}: NET must contain exactly {len(degrees) - 1} edges "
            f"(a spanning tree over {len(degrees)} faces), found {len(net_edges)}")

    return degrees, net_edges, extra_edges, root, (name or path)


def write_polyhedron_spec(path, degrees, net_edges, extra_edges, root, name=None):
    lines = []
    if name:
        lines.append(f"# {name}")
    lines.append("FACES")
    lines.extend(str(k) for k in degrees)
    lines.append("")
    lines.append(f"ROOT {root}")
    lines.append("")
    lines.append("NET")
    lines.extend(f"{a} {b}" for a, b in net_edges)
    lines.append("")
    lines.append("EXTRA")
    lines.extend(f"{a} {b}" for a, b in extra_edges)
    lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines))
