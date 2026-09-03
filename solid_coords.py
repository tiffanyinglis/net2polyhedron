"""Canonical 3D vertex coordinates for the 5 Platonic solids, for use with
hull_to_spec.py to derive their combinatorial net specs."""
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


SOLIDS = {
    "tetrahedron": tetrahedron,
    "cube": cube,
    "octahedron": octahedron,
    "icosahedron": icosahedron,
    "dodecahedron": dodecahedron,
}
