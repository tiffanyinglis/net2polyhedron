import numpy as np
import pytest

from utils.combinatorics.edge_map import EdgeMap
from utils.geometry2d.net_layout import build_net_layout
from utils.geometry3d.net_fold_core import fold, distinct_vertices
from utils.geometry3d.fold_solver import solve_fold_angles

TETRAHEDRON_DEGREES = [3, 3, 3, 3]
TETRAHEDRON_EDGES = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
TETRAHEDRON_NET_EDGES = [(0, 1), (0, 2), (0, 3)]
TETRAHEDRON_EXTRA_EDGES = [(1, 2), (1, 3), (2, 3)]

CUBE_DEGREES = [4] * 6
# 0=bottom,5=top (never adjacent); 1,2,3,4 = the four sides
CUBE_EDGES = ([(0, s) for s in (1, 2, 3, 4)] + [(5, s) for s in (1, 2, 3, 4)] +
              [(1, 2), (2, 3), (3, 4), (4, 1)])
CUBE_NET_EDGES = [(0, 1), (0, 2), (0, 3), (0, 4), (5, 2)]
_cube_net_edge_set = {frozenset(e) for e in CUBE_NET_EDGES}
CUBE_EXTRA_EDGES = [e for e in CUBE_EDGES if frozenset(e) not in _cube_net_edge_set]


def _solve(degrees, net_edges, extra_edges, root=0):
    edge_map = EdgeMap(degrees, net_edges + extra_edges)
    net, hinges = build_net_layout(degrees, net_edges, edge_map, root)
    fold_angles = solve_fold_angles(net, root, hinges, extra_edges, edge_map)
    return net, root, hinges, fold_angles


def _check_solid(net, root, hinges, fold_angles, expected_angle_deg, expected_vertices):
    angles = {round(np.degrees(a), 3) for a in fold_angles.values()}
    assert angles == {round(expected_angle_deg, 3)}

    verts = fold(net, root, hinges, fold_angles, t=1.0)
    pts = np.array(distinct_vertices(verts))
    assert len(pts) == expected_vertices

    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    assert np.isclose(d.min(), 1.0, atol=1e-6)


def test_solve_tetrahedron():
    net, root, hinges, fold_angles = _solve(
        TETRAHEDRON_DEGREES, TETRAHEDRON_NET_EDGES, TETRAHEDRON_EXTRA_EDGES)
    _check_solid(net, root, hinges, fold_angles, expected_angle_deg=109.4712, expected_vertices=4)


def test_solve_cube():
    net, root, hinges, fold_angles = _solve(CUBE_DEGREES, CUBE_NET_EDGES, CUBE_EXTRA_EDGES)
    _check_solid(net, root, hinges, fold_angles, expected_angle_deg=90.0, expected_vertices=8)


def test_solve_without_extra_edges_is_underdetermined():
    edge_map = EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES)
    net, hinges = build_net_layout(TETRAHEDRON_DEGREES, TETRAHEDRON_NET_EDGES, edge_map, root=0)
    with pytest.raises(ValueError, match="underdetermined"):
        solve_fold_angles(net, 0, hinges, [], edge_map)
