import numpy as np
import pytest

from utils.inflate_polyhedron.stretchy_mesh import load_stretchy_mesh, mesh_edges
from utils.inflate_polyhedron.stretchy_net_layout import build_stretchy_net_layout

NETS = ["tetrahedron", "cube", "octahedron", "icosahedron", "dodecahedron"]


@pytest.mark.parametrize("name", NETS)
def test_every_face_gets_placed(name):
    faces, _ = load_stretchy_mesh(f"data/input/stretchy_nets/{name}.poly")
    placed = build_stretchy_net_layout(faces)
    assert set(placed) == set(range(len(faces)))
    for fi, pts in placed.items():
        assert len(pts) == len(faces[fi])


@pytest.mark.parametrize("name", NETS)
def test_every_placed_face_keeps_unit_edge_length(name):
    # attach_polygon must preserve each face's own regular-polygon shape
    # (rotation + translation only, no distortion) regardless of where in
    # the BFS tree it landed.
    faces, _ = load_stretchy_mesh(f"data/input/stretchy_nets/{name}.poly")
    placed = build_stretchy_net_layout(faces)
    for fi, face in enumerate(faces):
        pts = placed[fi]
        n = len(pts)
        for i in range(n):
            length = np.linalg.norm(pts[i] - pts[(i + 1) % n])
            assert abs(length - 1.0) < 1e-9


def test_a_tree_edge_lands_shared_faces_on_the_same_two_points():
    # only edges the BFS tree actually attaches through are guaranteed to
    # coincide in the flat layout (exactly like `edges.net` vs
    # `edges.extra` in the rigid pipeline's format -- a shared edge NOT
    # used for attachment only meets once physically folded, not in the
    # flat net). Reproduce the tree here the same way build_stretchy_net_layout
    # does, and check every edge IT used.
    from collections import deque
    from utils.inflate_polyhedron.stretchy_net_layout import _shared_edge_faces

    faces, _ = load_stretchy_mesh("data/input/stretchy_nets/cube.poly")
    placed = build_stretchy_net_layout(faces)
    shared = _shared_edge_faces(faces)
    visited = {0}
    q = deque([0])
    checked_any = False
    while q:
        parent = q.popleft()
        parent_face = faces[parent]
        n_parent = len(parent_face)
        for i in range(n_parent):
            a, b = parent_face[i], parent_face[(i + 1) % n_parent]
            key = (a, b) if a < b else (b, a)
            for fi, local_idx in shared[key]:
                if fi == parent or fi in visited:
                    continue
                visited.add(fi)
                child_face = faces[fi]
                nc = len(child_face)
                assert np.allclose(placed[parent][i], placed[fi][(local_idx + 1) % nc])
                assert np.allclose(placed[parent][(i + 1) % n_parent], placed[fi][local_idx])
                checked_any = True
                q.append(fi)
    assert checked_any


def test_root_face_is_the_canonical_regular_polygon():
    faces, _ = load_stretchy_mesh("data/input/stretchy_nets/dodecahedron.poly")
    placed = build_stretchy_net_layout(faces, root=0)
    from utils.geometry.polygon_geom import regular_polygon_vertices
    expected = regular_polygon_vertices(len(faces[0]))
    for p, e in zip(placed[0], expected):
        assert np.allclose(p, e)
