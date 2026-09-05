"""Platonic (and Platonic-like) solids as ready-to-use model.Polyhedron
objects -- replaces the old geometry3d/solid_coords.py, which only handed
back raw coordinate tuples and left every caller to separately run those
through hull_to_spec.polyhedron_from_vertices to get CCW face loops.

Each subclass below supplies canonical, unit-edge-ish 3D vertex
coordinates (`raw_vertices`); the shared PlatonicPolyhedron.__init__ runs
them through hull_to_spec once and initializes self as a full Polyhedron
-- so `Cube()` is immediately usable anywhere a Polyhedron is expected
(NetUnfolder.for_polyhedron, write_polyhedron_spec, etc.), no separate
hull step needed at call sites."""
import numpy as np

from .polyhedron import Polyhedron
from ..geometry3d.hull_to_spec import polyhedron_from_vertices

PHI = (1 + np.sqrt(5)) / 2


class PlatonicPolyhedron(Polyhedron):
    """Base class: subclasses provide `raw_vertices()`; this derives CCW
    face loops via hull_to_spec and builds a full Polyhedron from them."""

    name = None

    def __init__(self):
        raw_vertices = self.raw_vertices()
        _, _, face_loops = polyhedron_from_vertices(raw_vertices)
        vertices = [np.array(v, dtype=float) for v in raw_vertices]
        faces = [tuple(loop) for loop in face_loops]
        super().__init__(vertices=vertices, faces=faces, name=self.name)

    @staticmethod
    def raw_vertices():
        raise NotImplementedError


class Tetrahedron(PlatonicPolyhedron):
    name = "Tetrahedron"

    @staticmethod
    def raw_vertices():
        return [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]


class Cube(PlatonicPolyhedron):
    name = "Cube"

    @staticmethod
    def raw_vertices():
        return [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]


class Octahedron(PlatonicPolyhedron):
    name = "Octahedron"

    @staticmethod
    def raw_vertices():
        return [(s, 0, 0) for s in (-1, 1)] + \
               [(0, s, 0) for s in (-1, 1)] + \
               [(0, 0, s) for s in (-1, 1)]


class Icosahedron(PlatonicPolyhedron):
    name = "Icosahedron"

    @staticmethod
    def raw_vertices():
        verts = []
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                verts.append((0, s1, s2 * PHI))
                verts.append((s1, s2 * PHI, 0))
                verts.append((s2 * PHI, 0, s1))
        return verts


class Dodecahedron(PlatonicPolyhedron):
    name = "Dodecahedron"

    @staticmethod
    def raw_vertices():
        verts = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
        inv = 1 / PHI
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                verts.append((0, s1 * inv, s2 * PHI))
                verts.append((s1 * inv, s2 * PHI, 0))
                verts.append((s2 * PHI, 0, s1 * inv))
        return verts


class TruncatedIcosahedron(PlatonicPolyhedron):
    """The soccer-ball solid: 12 pentagons + 20 hexagons, 90 edges, 60
    vertices -- a much bushier hinge tree than any Platonic solid, useful
    for stress-testing the fold pipeline. Coordinates are all even
    permutations (the 3 cyclic rotations) of:
        (0, 1, 3*phi), (1, 2+phi, 2*phi), (phi, 2, 2*phi+1)
    with every sign flip of the nonzero components."""

    name = "Truncated Icosahedron"

    @staticmethod
    def raw_vertices():
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


PLATONIC_SOLIDS = {
    "tetrahedron": Tetrahedron,
    "cube": Cube,
    "octahedron": Octahedron,
    "icosahedron": Icosahedron,
    "dodecahedron": Dodecahedron,
    "truncated_icosahedron": TruncatedIcosahedron,
}
