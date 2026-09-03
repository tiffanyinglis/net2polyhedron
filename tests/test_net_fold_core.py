import numpy as np

from net_fold_utils.net_fold_core import Net, fold, distinct_vertices, precompute_subtree_map


def _square(x0, y0, s=1.0):
    return [(x0, y0), (x0 + s, y0), (x0 + s, y0 + s), (x0, y0 + s)]


def _cross_cube_net():
    """The classic cross-shaped cube net: a center square with four arms
    plus one more square past the top arm."""
    net = Net()
    bottom = net.add_face(_square(0, 0))
    front = net.add_face(_square(0, 1))
    top = net.add_face(_square(0, 2))
    back = net.add_face(_square(0, 3))
    left = net.add_face(_square(-1, 1))
    right = net.add_face(_square(1, 1))
    root, hinges = net.build_tree(root=front)
    return net, root, hinges, dict(bottom=bottom, top=top, back=back, left=left, right=right)


def test_cube_cross_net_finds_a_spanning_tree_of_five_hinges():
    net, root, hinges, _ = _cross_cube_net()
    assert len(hinges) == 5
    assert {h["child"] for h in hinges} | {root} == set(net.faces)


def test_cube_cross_net_folds_into_a_unit_cube():
    net, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}

    verts = fold(net, root, hinges, fold_angles, t=1.0)
    pts = np.array(distinct_vertices(verts))

    # a unit cube has exactly 8 vertices, all edges (and thus all
    # nearest-neighbor distances) length 1, and a well-defined center
    assert len(pts) == 8
    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
    np.fill_diagonal(d, np.inf)
    assert np.isclose(d.min(), 1.0)

    center = pts.mean(axis=0)
    radii = np.linalg.norm(pts - center, axis=1)
    assert np.allclose(radii, radii[0])  # cube vertices are equidistant from its center


def test_fold_at_t_zero_is_flat():
    net, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    verts = fold(net, root, hinges, fold_angles, t=0.0)
    for pts in verts.values():
        assert np.allclose(pts[:, 2], 0.0)  # nothing has folded out of the z=0 plane


def test_fold_with_precomputed_subtree_map_matches_default():
    net, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    subtree_map = precompute_subtree_map(hinges)

    verts_default = fold(net, root, hinges, fold_angles, t=0.6)
    verts_precomputed = fold(net, root, hinges, fold_angles, t=0.6, subtree_map=subtree_map)

    for fid in net.faces:
        assert np.allclose(verts_default[fid], verts_precomputed[fid])


def test_distinct_vertices_merges_close_points_and_keeps_far_ones_separate():
    verts3d = {
        0: np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        1: np.array([[0.0, 0.0, 1e-8], [5.0, 5.0, 5.0]]),  # first point ~coincides with face 0's first
    }
    merged = distinct_vertices(verts3d, tol=1e-4)
    assert len(merged) == 3
