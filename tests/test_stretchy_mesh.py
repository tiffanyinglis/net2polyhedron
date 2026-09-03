import json

import numpy as np
import pytest

from net_fold_utils.combinatorics import EdgeMap
from net_fold_utils.stretchy_mesh import (
    load_stretchy_mesh, mesh_edges, solve_wireframe,
    _overall_3d_extent, _min_pairwise_separation,
)

PENTAGONS_AND_SQUARE = "stretchy_nets/two_pentagons_and_a_square.json"

TETRAHEDRON_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]


def test_load_pentagons_and_square_example():
    faces, name = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    assert len(faces) == 3
    assert [len(f) for f in faces] == [5, 5, 4]
    assert name == "Two Pentagons and a Square"


def test_load_stretchy_mesh_rejects_unmatched_directed_edge(tmp_path):
    # a single triangle: every edge has no reverse partner at all
    path = tmp_path / "open.json"
    path.write_text(json.dumps({"faces": [[0, 1, 2]]}))
    with pytest.raises(ValueError, match="no reverse partner"):
        load_stretchy_mesh(str(path))


def test_load_stretchy_mesh_rejects_duplicate_directed_edge(tmp_path):
    # two faces both declaring the SAME directed edge 0->1
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"faces": [[0, 1, 2], [0, 1, 3]]}))
    with pytest.raises(ValueError, match="appears 2 times"):
        load_stretchy_mesh(str(path))


def test_mesh_edges_deduplicates_and_sorts():
    faces, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    edges = mesh_edges(faces)
    assert edges == sorted(set(edges))
    assert all(a < b for a, b in edges)
    assert len(edges) == 7  # 3 shared A-B + 2 A-S + 2 B-S


def test_the_rigid_pipeline_rejects_this_topology_as_a_duplicate_edge():
    """Reproduces exactly why polygon_fold_app.py / polyhedral_net_app.py
    can't fold the pentagons-and-square net: its face-ADJACENCY graph (not
    the vertex-loop mesh above, but the "which face touches which face"
    view combinatorics.EdgeMap needs) has the pentagon pair (faces 0, 1)
    joined by 3 separate edges and each pentagon joined to the square
    (face 2) by 2 -- EdgeMap's graph is a plain networkx.Graph, which
    can't represent a face pair sharing more than one edge at all."""
    degrees = [5, 5, 4]
    edges = [(0, 1), (0, 1), (0, 1), (0, 2), (0, 2), (1, 2), (1, 2)]
    with pytest.raises(ValueError, match="duplicate edge"):
        EdgeMap(degrees, edges)


def test_solve_wireframe_keeps_edges_close_to_unit_length():
    faces, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    _, stats = solve_wireframe(faces, seed=1)
    assert stats["max_stretch_pct"] < 1.0
    assert stats["rms_stretch_pct"] < 1.0


def test_solve_wireframe_result_is_genuinely_three_dimensional():
    faces, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    positions, _ = solve_wireframe(faces, seed=2)
    pts = np.array(list(positions.values()))
    assert _overall_3d_extent(pts) > 0.1


def test_solve_wireframe_vertices_are_not_collapsed_together():
    faces, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    positions, _ = solve_wireframe(faces, seed=3)
    pts = np.array(list(positions.values()))
    assert _min_pairwise_separation(pts) > 0.3


def test_solve_wireframe_covers_every_vertex_used_by_the_faces():
    faces, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    positions, _ = solve_wireframe(faces, seed=4)
    assert set(positions) == {v for face in faces for v in face}


def test_solve_wireframe_on_an_ordinary_closed_mesh_needs_no_stretch():
    # a real tetrahedron (all-triangle faces) CAN close up rigidly, so
    # the solver should find it with edges essentially exactly unit
    # length -- this isn't a case that needs any real stretching.
    positions, stats = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    assert stats["max_stretch_pct"] < 0.01
    pts = np.array(list(positions.values()))
    assert _overall_3d_extent(pts) > 0.1


# name -> (num_faces, num_vertices, num_edges, sides_per_face), generated
# by tools/generate_stretchy_platonic_nets.py from the same coordinates
# (net_fold_utils/solid_coords.py) the RIGID nets/*.json specs use.
PLATONIC_STRETCHY_NETS = {
    "tetrahedron": (4, 4, 6, 3),
    "cube": (6, 8, 12, 4),
    "octahedron": (8, 6, 12, 3),
    "icosahedron": (20, 12, 30, 3),
    "dodecahedron": (12, 20, 30, 5),
}


@pytest.mark.parametrize("name,expected", PLATONIC_STRETCHY_NETS.items())
def test_platonic_solid_stretchy_nets_load_with_correct_combinatorics(name, expected):
    n_faces, n_verts, n_edges, sides = expected
    faces, _ = load_stretchy_mesh(f"stretchy_nets/{name}.json")
    assert len(faces) == n_faces
    assert all(len(f) == sides for f in faces)
    assert len({v for face in faces for v in face}) == n_verts
    edges = mesh_edges(faces)
    assert len(edges) == n_edges
    assert n_verts - n_edges + n_faces == 2  # Euler's formula: closed, genus-0


# Only the small/fast solids run the actual numerical solve here, same
# rationale as this project's rigid-pipeline tests never running the
# icosahedron/truncated-icosahedron solve (see tests/test_fold_solver.py
# and the net-fold-project skill doc): the dodecahedron and icosahedron
# take tens of seconds via solve_wireframe's random-restart search
# (verified manually -- both settle at ~0% edge stretch; the
# dodecahedron reliably finds a fully untangled embedding, the
# icosahedron's is more tangled but still non-degenerate and genuinely
# 3D -- see solve_wireframe's docstring for why that one's harder).
@pytest.mark.parametrize("name", ["tetrahedron", "cube", "octahedron"])
def test_solve_wireframe_on_small_platonic_solids_needs_almost_no_stretch(name):
    faces, _ = load_stretchy_mesh(f"stretchy_nets/{name}.json")
    positions, stats = solve_wireframe(faces, seed=0)
    assert stats["max_stretch_pct"] < 0.5
    pts = np.array(list(positions.values()))
    assert _overall_3d_extent(pts) > 0.1
    assert _min_pairwise_separation(pts) > 0.5
