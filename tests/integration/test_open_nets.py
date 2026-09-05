"""End-to-end coverage for OPEN nets: a Polyhedron whose faces are a
subset of a solid's (here, a tetrahedron with its 4th face dropped -- an
open triangular tray) that doesn't fold up into a closed solid. Built via
helpers.TetraNetSpec rather than depending on
data/input/nets/half_dodecahedron.json or dodecahedron_minus_one.json, so
this test doesn't need those files to exist or be pre-cached."""
import numpy as np

from helpers import TetraNetSpec
from utils.polyhedron_unfolder import is_closed


def test_open_net_unfolds_and_builds_only_the_kept_faces():
    polyhedron = TetraNetSpec.build_open()
    net = TetraNetSpec.unfold(polyhedron)

    assert len(net.polyhedron.faces) == 3
    assert len(net.hinges) == 2
    assert net.polyhedron.name == "Open Tetra"


def test_open_net_stays_open_at_full_fold():
    polyhedron = TetraNetSpec.build_open()
    net = TetraNetSpec.unfold(polyhedron)

    solid = net.fold(t=1.0)
    assert not is_closed(solid)

    # but the sole non-hinge closure edge (the two hinge children share an
    # edge in the original tetrahedron, even though they're not directly
    # hinge-connected to each other) DOES still meet exactly, same as it
    # would inside a real, closed tetrahedron -- it's specifically the
    # missing face's edges that are left unmatched, not the whole shape
    # falling apart.
    children = [h.child_id for h in net.hinges]
    p1 = solid.face_vertices(children[0])
    p2 = solid.face_vertices(children[1])
    dists = np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=-1)
    assert np.isclose(dists.min(), 0.0, atol=1e-6)


def test_closed_tetrahedron_net_is_closed_solid_for_comparison():
    polyhedron = TetraNetSpec.build_closed()
    net = TetraNetSpec.unfold(polyhedron)
    solid = net.fold(t=1.0)
    assert is_closed(solid)
