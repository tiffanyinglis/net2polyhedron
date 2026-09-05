"""Sample solids (and a couple of OPEN nets carved from one of them) as
ready-to-use model.Polyhedron objects, for the generate_*.py scripts and
tests to instantiate directly rather than hand-building coordinates --
replaces the old geometry3d/solid_coords.py, which only handed back raw
coordinate tuples and left every caller to separately run those through
hull_to_spec.polyhedron_from_vertices to get CCW face loops. Lives in
apps/common/ (not utils/model/) since this is sample/demo content the
apps and their generator scripts consume, not reusable fold-pipeline
domain logic itself.

Named "sample", not "platonic": most of the closed solids below ARE
Platonic (Tetrahedron, Cube, Octahedron, Icosahedron, Dodecahedron), but
TruncatedIcosahedron is Archimedean (semi-regular faces, not all
identical) -- included anyway as a much bushier net for stress-testing,
so the module/collection name can't honestly claim "Platonic" for all of
them.
"""
import sys
from pathlib import Path

# Same bootstrap as paths.py in this directory, duplicated rather than
# imported: this module needs to resolve `utils...` regardless of HOW it
# itself was reached -- a bare sibling `import sample_polyhedra` (from a
# script run directly, e.g. generate_platonic_nets.py), `from
# common.sample_polyhedra import ...` (pytest, with src/apps on
# sys.path but not src/apps/common itself, so a bare `import paths`
# would fail here), or that same package path from an app. Only src/
# actually needs adding for THIS module's own `utils` imports, but both
# are inserted for consistency with paths.py's own bootstrap.
_APPS_DIR = Path(__file__).resolve().parent.parent
_SRC_DIR = _APPS_DIR.parent
for _p in (_SRC_DIR, _APPS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np

from utils.model.polyhedron import Polyhedron
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices

PHI = (1 + np.sqrt(5)) / 2


class SamplePolyhedron(Polyhedron):
    """Base class for a CLOSED sample solid: subclasses provide
    `raw_vertices()`; this derives CCW face loops via hull_to_spec and
    builds a full Polyhedron from them."""

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


class Tetrahedron(SamplePolyhedron):
    name = "Tetrahedron"

    @staticmethod
    def raw_vertices():
        return [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]


class Cube(SamplePolyhedron):
    name = "Cube"

    @staticmethod
    def raw_vertices():
        return [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]


class Octahedron(SamplePolyhedron):
    name = "Octahedron"

    @staticmethod
    def raw_vertices():
        return [(s, 0, 0) for s in (-1, 1)] + \
               [(0, s, 0) for s in (-1, 1)] + \
               [(0, 0, s) for s in (-1, 1)]


class Icosahedron(SamplePolyhedron):
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


class Dodecahedron(SamplePolyhedron):
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


class TruncatedIcosahedron(SamplePolyhedron):
    """The soccer-ball solid: 12 pentagons + 20 hexagons, 90 edges, 60
    vertices -- a much bushier hinge tree than any Platonic solid, useful
    for stress-testing the fold pipeline. Archimedean, not Platonic (two
    different face shapes) -- the reason this whole module is named
    "sample", not "platonic". Coordinates are all even permutations (the
    3 cyclic rotations) of:
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


SAMPLE_SOLIDS = {
    "tetrahedron": Tetrahedron,
    "cube": Cube,
    "octahedron": Octahedron,
    "icosahedron": Icosahedron,
    "dodecahedron": Dodecahedron,
    "truncated_icosahedron": TruncatedIcosahedron,
}


class OpenSamplePolyhedron(Polyhedron):
    """Base class for an OPEN sample net: a face SUBSET of another sample
    solid's faces (`base_cls`), remapped to reference only the vertices
    those kept faces actually use -- an unreferenced vertex would still
    count toward apps/common/bounding_box.py's bounding_box(), silently
    enlarging it around an invisible point (see polyhedron_spec.py's
    module docstring for what an "open" net is more generally).

    These exist to exercise/validate the apps against nets that don't
    fold up into a closed solid -- which polyhedron_unfolder's backface
    culling (ui.cullable_face._CullableFace) must NOT be applied to
    (checked via utils.net_unfolder.is_closed)."""

    name = None
    base_cls = None  # a SamplePolyhedron subclass this is carved from

    @staticmethod
    def keep_faces(base):
        """Return the set of face indices (into base.faces) to keep."""
        raise NotImplementedError

    def __init__(self):
        base = self.base_cls()
        kept_faces = [base.faces[f] for f in sorted(self.keep_faces(base))]
        used = sorted({v for face in kept_faces for v in face})
        remap = {old: new for new, old in enumerate(used)}
        vertices = [base.vertices[v] for v in used]
        faces = [tuple(remap[v] for v in face) for face in kept_faces]
        super().__init__(vertices=vertices, faces=faces, name=self.name)


def _dodecahedron_face_adjacency(base):
    """dict face_index -> set of adjacent face indices, recomputed from
    `base`'s own vertices via hull_to_spec (deterministic, so this lines
    up exactly with `base.faces`' own indexing)."""
    _, edges, _ = polyhedron_from_vertices(base.vertices)
    adjacency = {f: set() for f in range(len(base.faces))}
    for a, b in edges:
        adjacency[a].add(b)
        adjacency[b].add(a)
    return adjacency


class HalfDodecahedron(OpenSamplePolyhedron):
    """One dodecahedron face plus its 5 neighbors -- a symmetric 6-face
    "cap" (a pentagon surrounded by its ring of neighbors), open all the
    way around where the other 6 faces would be, like a shallow bowl."""

    name = "Half Dodecahedron"
    base_cls = Dodecahedron

    @staticmethod
    def keep_faces(base):
        center = 0
        return {center} | _dodecahedron_face_adjacency(base)[center]


class DodecahedronMinusOne(OpenSamplePolyhedron):
    """Every dodecahedron face but one -- an almost-closed solid with a
    single pentagon-shaped hole where that face was."""

    name = "Dodecahedron Minus One"
    base_cls = Dodecahedron

    @staticmethod
    def keep_faces(base):
        removed = 0
        return set(range(len(base.faces))) - {removed}


OPEN_SAMPLE_POLYHEDRA = {
    "half_dodecahedron": HalfDodecahedron,
    "dodecahedron_minus_one": DodecahedronMinusOne,
}
