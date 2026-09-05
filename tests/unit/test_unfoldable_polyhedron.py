import numpy as np
import pytest

from common.paths import NETS_DIR
from utils.polyhedron import Polyhedron
from utils.polyhedron_json_parser import load_polyhedron_json
from utils.unfoldable_polyhedron import UnfoldablePolyhedron
from utils.spanning_tree import create_spanning_tree_BFS


def _polyhedron(name):
    """Loaded straight from data/input/nets/<name>.json -- these settled,
    checked-in files ARE the canonical sample solids now, so nothing here
    re-derives them from raw coordinates."""
    vertices, faces, net_name = load_polyhedron_json(NETS_DIR / f"{name}.json")
    return Polyhedron(vertices=vertices, faces=faces, name=net_name)


def _unfoldable(polyhedron, root=0):
    """Build an UnfoldablePolyhedron the same two steps
    UnfoldablePolyhedron.load() takes internally, so a test can also
    start from an already-built (or hand-modified -- e.g. open,
    disconnected) Polyhedron instead of a file."""
    adjacency = polyhedron.compute_face_adjacency()
    spanning_tree = create_spanning_tree_BFS(range(len(polyhedron.faces)), adjacency, root)
    return UnfoldablePolyhedron(polyhedron, spanning_tree, root)


def test_spanning_tree_reaches_every_face_of_a_cube():
    net = _unfoldable(_polyhedron("cube"))
    assert len(net.hinges) == 5  # a spanning tree over 6 faces
    reached = {h.child_id for h in net.hinges} | {net.root}
    assert reached == set(range(6))


def test_flat_layout_is_a_genuinely_duplicated_vertex_mesh():
    net = _unfoldable(_polyhedron("cube"))
    # Every face keeps its own private corners -- nothing is merged, not
    # even at hinge edges -- so a cube's flat net has all 6 quads x 4
    # corners = 24 vertices, not 8 or 14.
    assert len(net.flat.vertices) == 24
    assert not net.flat.is_closed()  # no shared indices at all -- never "closed" by this check


def test_flat_layout_hinge_corners_coincide_in_position_despite_separate_indices():
    """A hinge's two corners are separate vertex indices (see module
    docstring: nothing is merged), but they must still land at the exact
    same 2D position -- that's what makes it a hinge rather than just two
    unrelated edges."""
    net = _unfoldable(_polyhedron("cube"))
    hinge = net.hinges[0]
    parent_face = net.flat.faces[hinge.parent_id]
    child_face = net.flat.faces[hinge.child_id]
    k_p, k_c = len(parent_face), len(child_face)
    pi, ci = hinge.parent_edge_idx, hinge.child_edge_idx
    p1 = net.flat.vertices[parent_face[pi]]
    p2 = net.flat.vertices[parent_face[(pi + 1) % k_p]]
    # reversed attach direction (see _build_flat_layout): parent's pi <-> child's ci+1
    assert np.allclose(p1, net.flat.vertices[child_face[(ci + 1) % k_c]])
    assert np.allclose(p2, net.flat.vertices[child_face[ci]])


@pytest.mark.parametrize("name,expected_angle_deg", [
    ("tetrahedron", 109.4712),
    ("cube", 90.0),
    ("octahedron", 70.5288),
    ("dodecahedron", 63.4349),
    ("icosahedron", 41.8103),
])
def test_fold_angle_matches_the_known_dihedral_angle(name, expected_angle_deg):
    """fold_angle = 180 - dihedral, read directly off the given geometry
    -- no numerical solving involved."""
    net = _unfoldable(_polyhedron(name))
    angles = {round(np.degrees(h.angle), 4) for h in net.hinges}
    assert angles == {expected_angle_deg}


def test_get_unfolded_state_zero_returns_the_original_polyhedron_directly():
    polyhedron = _polyhedron("cube")
    net = _unfoldable(polyhedron)
    solid = net.get_unfolded_state(0.0)
    assert solid is polyhedron  # no reconstruction needed -- see module docstring
    assert solid.is_closed()


def test_get_unfolded_state_one_returns_the_flat_layout_directly():
    net = _unfoldable(_polyhedron("cube"))
    solid = net.get_unfolded_state(1.0)
    assert solid is net.flat  # every fold angle scales to 0 -- see module docstring
    for v in solid.vertices:
        assert np.isclose(v[2], 0.0)


def test_get_unfolded_state_halfway_is_a_genuine_partial_fold():
    net = _unfoldable(_polyhedron("cube"))
    solid = net.get_unfolded_state(0.5)
    assert not solid.is_closed()  # closure edges haven't met yet
    assert any(abs(v[2]) > 1e-6 for v in solid.vertices)  # and it's not still flat either


def test_get_unfolded_state_preserves_edge_lengths_when_fully_folded():
    """Every original edge length must be preserved by the fold, since
    fold_transforms applies rigid rotations to a rigid layout -- a real
    reconstruction, not an approximation. (cube.json's raw canonical
    coordinates aren't normalized to edge length 1 -- a cube's corners at
    (+-1,+-1,+-1) have edge length 2 -- so compare against the ORIGINAL
    polyhedron's own edge length, not a hardcoded 1.0.)"""
    polyhedron = _polyhedron("cube")
    net = _unfoldable(polyhedron)
    solid = net.get_unfolded_state(0.0)

    p0 = np.array(polyhedron.vertices[polyhedron.faces[0][0]])
    p1 = np.array(polyhedron.vertices[polyhedron.faces[0][1]])
    edge_length = np.linalg.norm(p1 - p0)
    for face in solid.faces:
        k = len(face)
        for i in range(k):
            a = np.array(solid.vertices[face[i]])
            b = np.array(solid.vertices[face[(i + 1) % k]])
            assert np.isclose(np.linalg.norm(a - b), edge_length, atol=1e-6)


def test_open_polyhedron_stays_open_when_folded():
    polyhedron = _polyhedron("tetrahedron")
    open_polyhedron = Polyhedron(vertices=polyhedron.vertices, faces=polyhedron.faces[:3],
                                  name="open")
    net = _unfoldable(open_polyhedron)
    assert len(net.hinges) == 2
    solid = net.get_unfolded_state(0.0)
    assert not solid.is_closed()


def test_disconnected_polyhedron_is_rejected():
    # Two separate triangles sharing no vertices/edges at all.
    vertices = [np.array(v) for v in [(0, 0, 0), (1, 0, 0), (0, 1, 0),
                                       (5, 5, 5), (6, 5, 5), (5, 6, 5)]]
    faces = [(0, 1, 2), (3, 4, 5)]
    polyhedron = Polyhedron(vertices=vertices, faces=faces, name="disconnected")
    with pytest.raises(ValueError, match="unreachable"):
        _unfoldable(polyhedron)
