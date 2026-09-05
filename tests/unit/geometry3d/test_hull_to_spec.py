from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from common.sample_polyhedra import Tetrahedron, Cube, Octahedron


def _assert_euler_consistent(vertices, degrees, edges):
    V, E, F = len(vertices), len(edges), len(degrees)
    assert V - E + F == 2


def test_tetrahedron_from_vertices():
    verts = Tetrahedron.raw_vertices()
    degrees, edges, _ = polyhedron_from_vertices(verts)
    assert degrees == [3, 3, 3, 3]
    assert len(edges) == 6
    _assert_euler_consistent(verts, degrees, edges)


def test_cube_from_vertices():
    verts = Cube.raw_vertices()
    degrees, edges, _ = polyhedron_from_vertices(verts)
    assert degrees == [4] * 6
    assert len(edges) == 12
    _assert_euler_consistent(verts, degrees, edges)


def test_octahedron_from_vertices():
    verts = Octahedron.raw_vertices()
    degrees, edges, _ = polyhedron_from_vertices(verts)
    assert degrees == [3] * 8
    assert len(edges) == 12
    _assert_euler_consistent(verts, degrees, edges)
