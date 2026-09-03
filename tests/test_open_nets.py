"""End-to-end coverage for OPEN nets (see polyhedron_spec.py's module
docstring): a .json net with one or more faces marked "omit" that
doesn't fold up into a closed solid. Builds a small one (a tetrahedron
with its 4th face omitted -- an open triangular tray) directly, rather
than depending on nets/half_dodecahedron.json or
nets/dodecahedron_minus_one.json, so this test doesn't need those files
to exist or be pre-solved."""
import numpy as np

from net_fold_utils.net_io import load_polyhedron_net
from net_fold_utils.net_fold_core import fold, is_closed_solid
from net_fold_utils.polyhedron_spec import write_polyhedron_spec

TETRA_DEGREES = [3, 3, 3, 3]


def _write_open_tetra(path):
    # Face 3 omitted: net/extra span only faces 0-2 (a spanning tree of
    # 2 edges over 3 kept faces), hidden carries every edge touching the
    # omitted face -- same shape of spec tools/generate_open_dodecahedron_nets.py
    # produces for half_dodecahedron.json / dodecahedron_minus_one.json.
    write_polyhedron_spec(str(path), TETRA_DEGREES, [(0, 1), (0, 2)], [(1, 2)],
                           root=0, name="Open Tetra", omitted={3},
                           hidden_edges=[(0, 3), (1, 3), (2, 3)])


def test_open_net_solves_and_builds_only_the_kept_faces(tmp_path):
    path = tmp_path / "open_tetra.json"
    _write_open_tetra(path)

    net, root, hinges, fold_angles, name = load_polyhedron_net(str(path))

    assert set(net.faces) == {0, 1, 2}
    assert len(hinges) == 2
    assert name == "Open Tetra"


def test_open_net_stays_open_at_full_fold(tmp_path):
    path = tmp_path / "open_tetra.json"
    _write_open_tetra(path)
    net, root, hinges, fold_angles, name = load_polyhedron_net(str(path))

    verts = fold(net, root, hinges, fold_angles, t=1.0)
    assert not is_closed_solid(verts)

    # but the sole "extra" closure constraint (faces 1 and 2 share an
    # edge) DOES still hold, same as it would inside a real, closed
    # tetrahedron -- it's specifically the missing face's edges that are
    # left unmatched, not the whole shape falling apart.
    p1, p2 = np.array(verts[1]), np.array(verts[2])
    dists = np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=-1)
    assert np.isclose(dists.min(), 0.0, atol=1e-6)


def test_closed_tetrahedron_net_is_closed_solid_for_comparison(tmp_path):
    path = tmp_path / "closed_tetra.json"
    write_polyhedron_spec(str(path), TETRA_DEGREES, [(0, 1), (0, 2), (0, 3)],
                           [(1, 2), (1, 3), (2, 3)], root=0, name="Closed Tetra")
    net, root, hinges, fold_angles, name = load_polyhedron_net(str(path))
    verts = fold(net, root, hinges, fold_angles, t=1.0)
    assert is_closed_solid(verts)
