import numpy as np
import pytest

from utils.geometry3d.polyhedron import Polyhedron
from common.sample_polyhedra import SAMPLE_SOLIDS
from utils.polyhedron_unfolder import NetUnfolder, is_closed


def _polyhedron(name):
    return SAMPLE_SOLIDS[name]()


def test_is_closed_true_for_a_real_closed_solid():
    assert is_closed(_polyhedron("tetrahedron"))


def test_is_closed_false_when_a_face_is_missing():
    tetra = _polyhedron("tetrahedron")
    open_tetra = Polyhedron(vertices=tetra.vertices, faces=tetra.faces[:-1])
    assert not is_closed(open_tetra)


def test_spanning_tree_reaches_every_face_of_a_cube():
    net = NetUnfolder.for_polyhedron(_polyhedron("cube"))
    assert len(net.hinges) == 5  # a spanning tree over 6 faces
    reached = {h.child_id for h in net.hinges} | {net.root}
    assert reached == set(range(6))


def test_root_is_always_face_zero():
    net = NetUnfolder.for_polyhedron(_polyhedron("tetrahedron"))
    assert net.root == 0


def test_flat_layout_shares_hinge_vertices_but_not_closure_vertices():
    net = NetUnfolder.for_polyhedron(_polyhedron("cube"))
    # 6 quads x 4 corners = 24 raw corners; 5 hinges each merge one pair
    # of corners (2 -> 1), so 24 - 5*2 = 14 distinct vertices remain --
    # same count verified for the old regular-polygon-based net layout.
    assert len(net.flat.vertices) == 14
    assert not is_closed(net.flat)  # not a real solid until folded


@pytest.mark.parametrize("name,expected_angle_deg", [
    ("tetrahedron", 109.4712),
    ("cube", 90.0),
    ("octahedron", 70.5288),
    ("dodecahedron", 63.4349),
    ("icosahedron", 41.8103),
])
def test_fold_angle_matches_the_known_dihedral_angle(name, expected_angle_deg):
    """fold_angle = 180 - dihedral, read directly off the given geometry
    -- no numerical solving involved (see polyhedron_unfolder.py's docstring)."""
    net = NetUnfolder.for_polyhedron(_polyhedron(name))
    angles = {round(np.degrees(h.angle), 4) for h in net.hinges}
    assert angles == {expected_angle_deg}


def test_fold_at_t1_reproduces_the_original_closed_polyhedron():
    polyhedron = _polyhedron("cube")
    net = NetUnfolder.for_polyhedron(polyhedron)
    solid = net.fold(1.0)
    assert is_closed(solid)
    assert len(solid.vertices) == len(polyhedron.vertices)
    assert len(solid.faces) == len(polyhedron.faces)

    # every original edge length is preserved by the fold, since
    # fold_transforms applies rigid rotations to a rigid layout -- a real
    # reconstruction, not an approximation. (sample_polyhedra.py's raw
    # canonical coordinates aren't normalized to edge length 1 -- a cube's
    # corners at (+-1,+-1,+-1) have edge length 2 -- so compare against
    # the ORIGINAL polyhedron's own edge length, not a hardcoded 1.0.)
    p0, p1 = polyhedron.vertices[polyhedron.faces[0][0]], polyhedron.vertices[polyhedron.faces[0][1]]
    edge_length = np.linalg.norm(p1 - p0)
    for face in solid.faces:
        k = len(face)
        for i in range(k):
            a, b = solid.vertices[face[i]], solid.vertices[face[(i + 1) % k]]
            assert np.isclose(np.linalg.norm(a - b), edge_length, atol=1e-6)


def test_fold_at_t0_is_flat():
    net = NetUnfolder.for_polyhedron(_polyhedron("cube"))
    solid = net.fold(0.0)
    for v in solid.vertices:
        assert np.isclose(v[2], 0.0)


def test_open_polyhedron_stays_open_when_folded():
    polyhedron = _polyhedron("tetrahedron")
    open_polyhedron = Polyhedron(vertices=polyhedron.vertices, faces=polyhedron.faces[:3],
                                  name="open")
    net = NetUnfolder.for_polyhedron(open_polyhedron)
    assert len(net.hinges) == 2
    solid = net.fold(1.0)
    assert not is_closed(solid)


def test_disconnected_polyhedron_is_rejected():
    # Two separate triangles sharing no vertices/edges at all.
    vertices = [np.array(v) for v in [(0, 0, 0), (1, 0, 0), (0, 1, 0),
                                       (5, 5, 5), (6, 5, 5), (5, 6, 5)]]
    faces = [(0, 1, 2), (3, 4, 5)]
    polyhedron = Polyhedron(vertices=vertices, faces=faces, name="disconnected")
    with pytest.raises(ValueError, match="unreachable"):
        NetUnfolder.for_polyhedron(polyhedron)


def test_face_transforms_root_is_always_identity():
    net = NetUnfolder.for_polyhedron(_polyhedron("cube"))
    for t in (0.0, 0.5, 1.0):
        transforms = net.face_transforms(t)
        assert np.allclose(transforms[net.root], np.eye(4))


def test_hinge_for_looks_up_by_child_id():
    net = NetUnfolder.for_polyhedron(_polyhedron("cube"))
    hinge = net.hinges[0]
    assert net.hinge_for(hinge.child_id) is hinge


def test_fold_angles_property_matches_hinges():
    net = NetUnfolder.for_polyhedron(_polyhedron("cube"))
    assert set(net.fold_angles) == {h.child_id for h in net.hinges}
    for h in net.hinges:
        assert net.fold_angles[h.child_id] == h.angle
