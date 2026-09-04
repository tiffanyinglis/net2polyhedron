"""Canonical 3D vertex coordinates for convex, unit-edge, regular-faced
solids, for use with hull_to_spec.py to derive their combinatorial net
specs -- the 5 Platonic solids plus a couple of larger Archimedean solids
useful as bushier nets for testing/benchmarking."""
import numpy as np

PHI = (1 + np.sqrt(5)) / 2


def tetrahedron():
    return [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]


def cube():
    return [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]


def octahedron():
    return [(s, 0, 0) for s in (-1, 1)] + \
           [(0, s, 0) for s in (-1, 1)] + \
           [(0, 0, s) for s in (-1, 1)]


def icosahedron():
    verts = []
    for s1 in (-1, 1):
        for s2 in (-1, 1):
            verts.append((0, s1, s2 * PHI))
            verts.append((s1, s2 * PHI, 0))
            verts.append((s2 * PHI, 0, s1))
    return verts


def dodecahedron():
    verts = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    inv = 1 / PHI
    for s1 in (-1, 1):
        for s2 in (-1, 1):
            verts.append((0, s1 * inv, s2 * PHI))
            verts.append((s1 * inv, s2 * PHI, 0))
            verts.append((s2 * PHI, 0, s1 * inv))
    return verts


def truncated_icosahedron():
    """The soccer-ball solid: 12 pentagons + 20 hexagons, 90 edges, 60
    vertices -- a much bushier hinge tree than any Platonic solid, useful
    for stress-testing the fold solver. Coordinates are all even
    permutations (the 3 cyclic rotations) of:
        (0, 1, 3*phi), (1, 2+phi, 2*phi), (phi, 2, 2*phi+1)
    with every sign flip of the nonzero components."""
    templates = [
        (0.0, 1.0, 3 * PHI),
        (1.0, 2 + PHI, 2 * PHI),
        (PHI, 2.0, 2 * PHI + 1),
    ]
    verts = set()
    for x0, y0, z0 in templates:
        for sx in ([1] if x0 == 0 else [1, -1]):
            for sy in ([1] if y0 == 0 else [1, -1]):
                for sz in ([1] if z0 == 0 else [1, -1]):
                    a, b, c = sx * x0, sy * y0, sz * z0
                    for perm in [(a, b, c), (c, a, b), (b, c, a)]:
                        verts.add(tuple(round(v, 9) for v in perm))
    return list(verts)


SOLIDS = {
    "tetrahedron": tetrahedron,
    "cube": cube,
    "octahedron": octahedron,
    "icosahedron": icosahedron,
    "dodecahedron": dodecahedron,
    "truncated_icosahedron": truncated_icosahedron,
}
