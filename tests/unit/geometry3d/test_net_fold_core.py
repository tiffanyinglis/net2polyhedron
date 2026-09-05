import numpy as np

from utils.geometry3d.net_fold_core import (
    Net, flatten_net, fold, fold_transforms, hinge_transform, cluster_faces_into_mesh,
    distinct_vertices, face_normal, is_closed_solid)
from utils.model.polyhedron import Polyhedron


def _square(x0, y0, s=1.0):
    return [(x0, y0), (x0 + s, y0), (x0 + s, y0 + s), (x0, y0 + s)]


def _cross_cube_net():
    """The classic cross-shaped cube net: a center square with four arms
    plus one more square past the top arm. Returns (net, flat, root,
    hinges, face_ids) -- `net` (the raw net_fold_core.Net) is kept around
    for building fold_angles dicts keyed by face id; `flat` is what
    fold()/fold_transforms() actually take now (see flatten_net). Faces
    are added in order with no explicit fid, so ids are already a dense
    0..5 range -- exactly what flatten_net's positional indexing requires."""
    net = Net()
    bottom = net.add_face(_square(0, 0))
    front = net.add_face(_square(0, 1))
    top = net.add_face(_square(0, 2))
    back = net.add_face(_square(0, 3))
    left = net.add_face(_square(-1, 1))
    right = net.add_face(_square(1, 1))
    root, hinges = net.build_tree(root=front)
    vertices, faces = flatten_net(net)
    flat = Polyhedron(vertices=vertices, faces=faces)
    return net, flat, root, hinges, dict(
        bottom=bottom, top=top, back=back, left=left, right=right)


def test_cube_cross_net_finds_a_spanning_tree_of_five_hinges():
    net, flat, root, hinges, _ = _cross_cube_net()
    assert len(hinges) == 5
    assert {h["child"] for h in hinges} | {root} == set(net.faces)


def test_cube_cross_net_folds_into_a_unit_cube():
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}

    verts = fold(flat, root, hinges, fold_angles, t=1.0)
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
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    verts = fold(flat, root, hinges, fold_angles, t=0.0)
    for pts in verts.values():
        assert np.allclose(pts[:, 2], 0.0)  # nothing has folded out of the z=0 plane


def test_hinge_transform_is_a_pure_rotation_about_an_offset_axis():
    # Rotate 90 degrees about the vertical line through (1, 0, 0) --
    # (1, 0, 5) sits ON that axis so it must map to itself; (2, 0, 0), one
    # unit off-axis along +x, must swing to +y around it.
    M = hinge_transform(axis_point=np.array([1.0, 0.0, 0.0]),
                         axis_dir=np.array([0.0, 0.0, 1.0]),
                         angle=np.pi / 2)
    on_axis = M @ np.array([1.0, 0.0, 5.0, 1.0])
    assert np.allclose(on_axis[:3], [1.0, 0.0, 5.0])
    off_axis = M @ np.array([2.0, 0.0, 0.0, 1.0])
    assert np.allclose(off_axis[:3], [1.0, 1.0, 0.0], atol=1e-10)


def test_fold_transforms_root_is_always_identity():
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    for t in (0.0, 0.5, 1.0):
        transforms = fold_transforms(flat, root, hinges, fold_angles, t=t)
        assert np.allclose(transforms[root], np.eye(4))


def test_fold_transforms_applied_to_flat_points_matches_fold():
    """fold()'s per-face 3D points are just fold_transforms()'s matrices
    applied to that face's own flat (z=0) points -- verify the two agree,
    since fold() is now a thin wrapper over fold_transforms()."""
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    t = 0.6
    verts = fold(flat, root, hinges, fold_angles, t=t)
    transforms = fold_transforms(flat, root, hinges, fold_angles, t=t)

    for i, face in enumerate(flat.faces):
        pts_h = np.array([[*flat.vertices[v], 1.0] for v in face])
        expected = (pts_h @ transforms[i].T)[:, :3]
        assert np.allclose(expected, verts[i])


def test_flatten_net_shares_hinge_vertices_but_not_extra_edge_vertices():
    """The flat net's hinge-glued corners must already coincide (that's
    what a hinge edge IS), while the wrap-around ("extra"-equivalent, not
    physically hinged) edges between non-adjacent arms should NOT be
    merged -- one edge becomes two, one vertex becomes several, until
    folding actually brings them together."""
    net, flat, root, hinges, _ = _cross_cube_net()
    # 6 quads x 4 corners = 24 raw corners; 5 hinges each merge 2 pairs of
    # corners into 1 (4 corners -> 2 shared), so 24 - 5*2 = 14 distinct
    # vertices remain (the wrap-around/non-hinge edges stay unmerged).
    assert len(flat.vertices) == 14
    assert not flat.is_closed  # not a real solid yet -- that's the point


def test_cluster_faces_into_mesh_builds_a_proper_cube():
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    verts = fold(flat, root, hinges, fold_angles, t=1.0)

    vertices, faces = cluster_faces_into_mesh(verts)

    assert len(vertices) == 8         # a cube's distinct vertices
    assert len(faces) == 6            # one per face_id, ascending order
    assert all(len(f) == 4 for f in faces)  # every face still a quad
    # every edge (by vertex index) must appear in exactly 2 faces, i.e.
    # cluster_faces_into_mesh's index tuples describe a real closed cube
    edge_counts = {}
    for face in faces:
        k = len(face)
        for i in range(k):
            a, b = face[i], face[(i + 1) % k]
            key = (a, b) if a < b else (b, a)
            edge_counts[key] = edge_counts.get(key, 0) + 1
    assert len(edge_counts) == 12      # a cube has 12 edges
    assert all(c == 2 for c in edge_counts.values())


def test_face_normal_points_outward_for_every_face_of_a_folded_cube():
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    verts = fold(flat, root, hinges, fold_angles, t=1.0)

    center = np.mean([pts.mean(axis=0) for pts in verts.values()], axis=0)
    for pts in verts.values():
        normal = face_normal(pts)
        assert np.isclose(np.linalg.norm(normal), 1.0)
        assert np.dot(normal, pts.mean(axis=0) - center) > 0


def test_distinct_vertices_merges_close_points_and_keeps_far_ones_separate():
    verts3d = {
        0: np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        1: np.array([[0.0, 0.0, 1e-8], [5.0, 5.0, 5.0]]),  # first point ~coincides with face 0's first
    }
    merged = distinct_vertices(verts3d, tol=1e-4)
    assert len(merged) == 3


def test_add_face_with_explicit_id_preserves_it_and_avoids_future_collisions():
    net = Net()
    fid = net.add_face(_square(0, 0), fid=5)
    assert fid == 5
    assert set(net.faces) == {5}
    # the next auto-assigned id must not collide with the explicit one
    next_fid = net.add_face(_square(1, 0))
    assert next_fid == 6


def test_is_closed_solid_true_for_a_fully_folded_cube():
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    verts = fold(flat, root, hinges, fold_angles, t=1.0)
    assert is_closed_solid(verts)


def test_is_closed_solid_false_for_a_flat_unfolded_net():
    # at t=0 the hinge edges still coincide (that's how the flat net was
    # laid out), but the "wrap-around" edges between non-adjacent arms
    # (e.g. left/right) only meet once actually folded -- so the flat
    # net has unmatched (free) edges and isn't a closed solid.
    net, flat, root, hinges, _ = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    verts = fold(flat, root, hinges, fold_angles, t=0.0)
    assert not is_closed_solid(verts)


def test_is_closed_solid_false_when_a_face_is_missing():
    net, flat, root, hinges, faces = _cross_cube_net()
    fold_angles = {fid: np.pi / 2 for fid in net.faces if fid != root}
    verts = fold(flat, root, hinges, fold_angles, t=1.0)
    del verts[faces["top"]]  # simulate an open net missing one face
    assert not is_closed_solid(verts)


def test_is_closed_solid_true_despite_endpoints_straddling_a_rounding_boundary():
    """Regression test for a real bug found solving
    data/input/nets/icosahedron.json: is_closed_solid used to match edge
    endpoints by independently rounding each point to a tol-sized grid
    (`round(x / tol)`). Two points genuinely coincident (well within tol)
    but landing on OPPOSITE sides of that grid's bucket boundary rounded
    to different keys and were wrongly treated as unmatched -- 4 of the
    icosahedron's 32 edges hit this, so a real closed icosahedron
    incorrectly reported is_closed_solid=False.

    Reproduced here with two copies of the same triangle (a trivially
    "closed" pair -- every edge shared by exactly the two faces) where one
    point is perturbed by ~6e-9 -- far under the default tol=1e-4 -- so
    it sits just past 0.00005, the midpoint of that point's rounding
    bucket, while its otherwise-identical partner sits just before it."""
    boundary = 0.00005
    tri_a = np.array([[boundary - 3e-9, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    tri_b = np.array([[1.0, 0.0, 0.0], [boundary + 3e-9, 0.0, 0.0], [0.0, 1.0, 0.0]])
    assert is_closed_solid({0: tri_a, 1: tri_b})
