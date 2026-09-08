from utils.inflate_polyhedron.hull_to_spec import polyhedron_from_vertices
from utils.geometry.polyhedron import Polyhedron

TETRAHEDRON_VERTICES = [
    [1.0, 1.0, 1.0],
    [1.0, -1.0, -1.0],
    [-1.0, 1.0, -1.0],
    [-1.0, -1.0, 1.0],
]

CUBE_VERTICES = [
    [-1.0, -1.0, -1.0],
    [-1.0, -1.0, 1.0],
    [-1.0, 1.0, -1.0],
    [-1.0, 1.0, 1.0],
    [1.0, -1.0, -1.0],
    [1.0, -1.0, 1.0],
    [1.0, 1.0, -1.0],
    [1.0, 1.0, 1.0],
]

OCTAHEDRON_VERTICES = [
    [-1.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [0.0, -1.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, -1.0],
    [0.0, 0.0, 1.0],
]


def _assert_euler_consistent(polyhedron):
    V = len(polyhedron.vertices)
    E = len(polyhedron.edges)
    F = len(polyhedron.faces)
    assert V - E + F == 2


def test_tetrahedron_from_vertices():
    solid = polyhedron_from_vertices(TETRAHEDRON_VERTICES)
    assert isinstance(solid, Polyhedron)
    assert [len(f) for f in solid.faces] == [3, 3, 3, 3]
    assert len(solid.edges) == 6
    assert solid.is_closed()
    _assert_euler_consistent(solid)


def test_cube_from_vertices():
    solid = polyhedron_from_vertices(CUBE_VERTICES)
    assert [len(f) for f in solid.faces] == [4] * 6
    assert len(solid.edges) == 12
    assert solid.is_closed()
    _assert_euler_consistent(solid)


def test_octahedron_from_vertices():
    solid = polyhedron_from_vertices(OCTAHEDRON_VERTICES)
    assert [len(f) for f in solid.faces] == [3] * 8
    assert len(solid.edges) == 12
    assert solid.is_closed()
    _assert_euler_consistent(solid)


def test_name_is_passed_through():
    solid = polyhedron_from_vertices(CUBE_VERTICES, name="Cube")
    assert solid.name == "Cube"
