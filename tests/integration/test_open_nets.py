"""End-to-end coverage for OPEN nets (see polyhedron_spec.py's module
docstring): a .json net with one or more faces marked "omit" that
doesn't fold up into a closed solid. Builds a small one (a tetrahedron
with its 4th face omitted -- an open triangular tray) via
helpers.TetraNetSpec, rather than depending on
data/input/nets/half_dodecahedron.json or dodecahedron_minus_one.json, so
this test doesn't need those files to exist or be pre-solved."""
import numpy as np

from helpers import TetraNetSpec


def test_open_net_solves_and_builds_only_the_kept_faces(tmp_path):
    path = tmp_path / "open_tetra.json"
    TetraNetSpec.write_open(path)

    net = TetraNetSpec.load(path)

    assert set(net.faces) == {0, 1, 2}
    assert len(net.hinges) == 2
    assert net.name == "Open Tetra"


def test_open_net_stays_open_at_full_fold(tmp_path):
    path = tmp_path / "open_tetra.json"
    TetraNetSpec.write_open(path)
    net = TetraNetSpec.load(path)

    solid = net.fold(t=1.0)
    assert not solid.is_closed

    # but the sole "extra" closure constraint (faces 1 and 2 share an
    # edge) DOES still hold, same as it would inside a real, closed
    # tetrahedron -- it's specifically the missing face's edges that are
    # left unmatched, not the whole shape falling apart.
    #
    # solid.faces is ordered by ascending original net face id (see
    # PolyhedralNet.fold's docstring); this open net keeps faces 0,1,2
    # (only face 3 is omitted), so sorted(net.faces).index(fid) gives
    # each original face's position in solid.faces.
    order = sorted(net.faces)
    p1 = solid.face_vertices(order.index(1))
    p2 = solid.face_vertices(order.index(2))
    dists = np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=-1)
    assert np.isclose(dists.min(), 0.0, atol=1e-6)


def test_closed_tetrahedron_net_is_closed_solid_for_comparison(tmp_path):
    path = tmp_path / "closed_tetra.json"
    TetraNetSpec.write_closed(path)
    net = TetraNetSpec.load(path)
    solid = net.fold(t=1.0)
    assert solid.is_closed
