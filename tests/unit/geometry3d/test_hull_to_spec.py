from common.paths import NETS_DIR
from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from utils.persistence.polyhedron_spec import load_polyhedron_spec


def _raw_vertices(name):
    """The already-settled raw 3D coordinates data/input/nets/<name>.json
    stores -- reused here (ignoring that file's own precomputed `faces`)
    to check hull_to_spec.polyhedron_from_vertices can re-derive them from
    scratch."""
    vertices, _, _ = load_polyhedron_spec(NETS_DIR / f"{name}.json")
    return vertices


def _assert_euler_consistent(vertices, degrees, edges):
    V, E, F = len(vertices), len(edges), len(degrees)
    assert V - E + F == 2


def test_tetrahedron_from_vertices():
    verts = _raw_vertices("tetrahedron")
    degrees, edges, _ = polyhedron_from_vertices(verts)
    assert degrees == [3, 3, 3, 3]
    assert len(edges) == 6
    _assert_euler_consistent(verts, degrees, edges)


def test_cube_from_vertices():
    verts = _raw_vertices("cube")
    degrees, edges, _ = polyhedron_from_vertices(verts)
    assert degrees == [4] * 6
    assert len(edges) == 12
    _assert_euler_consistent(verts, degrees, edges)


def test_octahedron_from_vertices():
    verts = _raw_vertices("octahedron")
    degrees, edges, _ = polyhedron_from_vertices(verts)
    assert degrees == [3] * 8
    assert len(edges) == 12
    _assert_euler_consistent(verts, degrees, edges)
