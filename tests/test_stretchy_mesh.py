import json
import threading

import numpy as np
import pytest

from net_fold_utils.combinatorics import EdgeMap
from net_fold_utils.hull_to_spec import polyhedron_from_vertices
from net_fold_utils.solid_coords import tetrahedron as tetrahedron_coords
from net_fold_utils import stretchy_mesh
from net_fold_utils.stretchy_mesh import (
    load_stretchy_mesh, mesh_edges, solve_wireframe, STRETCH_CAP,
    _overall_3d_extent, _min_pairwise_separation, _mesh_volume, _sphere_bound_volume,
    _volume_indices, _planarity_groups, _face_planarity_residual,
    _orientation_signs, _is_orientation_consistent,
    relax_once, EDGE_LENGTH,
)

PENTAGONS_AND_SQUARE = "stretchy_nets/two_pentagons_and_a_square.json"

TETRAHEDRON_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]

# Closed-form volumes of the regular Platonic solids at unit edge length.
TRUE_VOLUME = {
    "tetrahedron": 1 / (6 * np.sqrt(2)),
    "cube": 1.0,
    "octahedron": np.sqrt(2) / 3,
    "icosahedron": (5 / 12) * (3 + np.sqrt(5)),
    "dodecahedron": (15 + 7 * np.sqrt(5)) / 4,
}


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


# ---- _mesh_volume / _sphere_bound_volume ----

def _unit_edge_tetrahedron_points():
    verts = np.array(tetrahedron_coords())
    degrees, edges, face_loops = polyhedron_from_vertices(verts)
    edge_length = np.linalg.norm(verts[face_loops[0][0]] - verts[face_loops[0][1]])
    return verts / edge_length, face_loops


def test_mesh_volume_matches_the_true_regular_tetrahedron_volume():
    pts, faces = _unit_edge_tetrahedron_points()
    idx = {i: i for i in range(len(pts))}
    volume_indices = _volume_indices(faces, idx)
    assert np.isclose(_mesh_volume(pts, volume_indices), TRUE_VOLUME["tetrahedron"], atol=1e-6)


def test_face_planarity_residual_is_zero_for_all_triangle_faces():
    # every face here has exactly 3 vertices, always exactly planar --
    # _planarity_groups should exclude them entirely (no size-4+ group).
    pts, faces = _unit_edge_tetrahedron_points()
    idx = {i: i for i in range(len(pts))}
    groups = _planarity_groups(faces, idx)
    assert groups == {}
    assert _face_planarity_residual(pts, groups).size == 0


def test_face_planarity_residual_flags_a_non_planar_quad():
    # a square face lifted out of plane at one corner should give a
    # nonzero residual for that face; a perfectly flat square should not.
    flat = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    bent = flat.copy()
    bent[0, 2] = 0.5  # lift one corner out of plane
    idx = {i: i for i in range(4)}
    face = [0, 1, 2, 3]
    groups = _planarity_groups([face], idx)
    assert set(groups) == {4}
    assert np.allclose(_face_planarity_residual(flat, groups), 0.0, atol=1e-9)
    assert np.max(np.abs(_face_planarity_residual(bent, groups))) > 0.05


def test_planarity_groups_batches_multiple_face_sizes_independently():
    # two squares + one pentagon: two groups (size 4 with 2 faces, size 5
    # with 1), each internally batched, and no cross-contamination.
    square_a = [0, 1, 2, 3]
    square_b = [4, 5, 6, 7]
    pentagon = [8, 9, 10, 11, 12]
    idx = {i: i for i in range(13)}
    groups = _planarity_groups([square_a, square_b, pentagon], idx)
    assert set(groups) == {4, 5}
    assert groups[4].shape == (2, 4)
    assert groups[5].shape == (1, 5)


@pytest.mark.parametrize("name,sides_each,n_faces", [
    ("tetrahedron", 3, 4), ("cube", 4, 6), ("octahedron", 3, 8),
    ("icosahedron", 3, 20), ("dodecahedron", 5, 12),
])
def test_sphere_bound_volume_is_an_optimistic_but_well_scaled_target(name, sides_each, n_faces):
    faces = [[0] * sides_each] * n_faces  # only len() per face matters to _sphere_bound_volume
    bound = _sphere_bound_volume(faces, edge_length=1.0)
    true_volume = TRUE_VOLUME[name]
    assert bound > true_volume  # optimistic: never actually reachable
    assert bound < 3 * true_volume  # but well-scaled, not some huge arbitrary constant


# ---- solve_wireframe: edges stretch a bounded amount, never collapse/flatten ----

def test_solve_wireframe_keeps_edge_stretch_within_the_cap():
    faces, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    _, stats = solve_wireframe(faces, seed=1)
    assert stats["max_stretch_pct"] < 100 * STRETCH_CAP + 1.0  # +1 margin for the polish pass


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


# ---- solve_wireframe: inflates a real closed solid into a rounded, ----
# ---- (near-)fully-untangled shape, not just A valid one ----

def test_solve_wireframe_on_a_tetrahedron_inflates_within_the_stretch_cap():
    # a real tetrahedron (all-triangle faces) is ALREADY at its maximum
    # volume for 4 unit triangles -- there's no slack left to inflate --
    # so the inflation pressure just stretches it a little instead, the
    # same as slightly overinflating an already-taut balloon. That's
    # expected, not a bug: capped at STRETCH_CAP, not unbounded.
    positions, stats = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    assert stats["max_stretch_pct"] < 100 * STRETCH_CAP + 1.0
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
# and the net-fold-project skill doc). The dodecahedron and icosahedron
# are much faster than before now that inflation replaced the old
# many-seeds-and-hope repulsion approach (~10s and ~5s respectively,
# down from 30+s) but still slow enough to keep out of the routine
# suite; verified manually instead (see solve_wireframe's docstring) --
# both now reach essentially their true minimum vertex separation, not
# just "some valid embedding".
@pytest.mark.parametrize("name", ["tetrahedron", "cube", "octahedron"])
def test_solve_wireframe_on_small_platonic_solids_nearly_untangles_fully(name):
    faces, _ = load_stretchy_mesh(f"stretchy_nets/{name}.json")
    positions, stats = solve_wireframe(faces, seed=0)
    assert stats["max_stretch_pct"] < 100 * STRETCH_CAP + 1.0
    pts = np.array(list(positions.values()))
    assert _overall_3d_extent(pts) > 0.1
    # inflation should land these very close to their true minimum
    # vertex separation of exactly 1 edge length (a real cube/octahedron
    # /tetrahedron never has two vertices closer than that)
    assert _min_pairwise_separation(pts) > 0.9


# ---- winding convention (_orientation_signs / _is_orientation_consistent) ----

def test_orientation_signs_agree_for_a_genuinely_convex_solid():
    # a real regular tetrahedron: every face's normal should agree in
    # sign with "pointing away from the centroid" -- no ambiguity for
    # something this convex.
    pts, faces = _unit_edge_tetrahedron_points()
    idx = {i: i for i in range(len(pts))}
    signs = _orientation_signs(pts, faces, idx)
    assert signs == [1.0, 1.0, 1.0, 1.0] or signs == [-1.0, -1.0, -1.0, -1.0]
    assert _is_orientation_consistent(pts, faces, idx)


def test_is_orientation_consistent_false_when_one_face_is_flipped():
    pts, faces = _unit_edge_tetrahedron_points()
    idx = {i: i for i in range(len(pts))}
    # same points, but one face's vertex order reversed -- flips just
    # that face's computed normal without moving anything, simulating a
    # solve that folded exactly that face inside-out relative to the rest.
    flipped_faces = [list(reversed(faces[0]))] + faces[1:]
    assert not _is_orientation_consistent(pts, flipped_faces, idx)


def test_solve_wireframe_raises_a_helpful_error_when_no_embedding_is_found(monkeypatch):
    # force every candidate to look inconsistent, regardless of the
    # actual geometry, so solve_wireframe has to exhaust its attempts
    # and raise -- verifies the failure path itself, not the (already
    # well-covered) success path.
    monkeypatch.setattr(stretchy_mesh, "_is_orientation_consistent", lambda *a, **k: False)
    with pytest.raises(ValueError, match="counterclockwise"):
        solve_wireframe(TETRAHEDRON_FACES, seed=0)


def test_solve_wireframe_on_a_cube_rounds_out_the_skew_not_just_the_edges():
    # the specific complaint this was built to fix: a plain edge-length
    # fit can converge to a valid but skewed parallelepiped-looking cube.
    # Inflation should pull all 8 vertices to a near-uniform distance
    # from the centroid, i.e. genuinely rounded out, not just
    # edge-length-correct.
    faces, _ = load_stretchy_mesh("stretchy_nets/cube.json")
    positions, _ = solve_wireframe(faces, seed=0)
    pts = np.array(list(positions.values()))
    centroid = pts.mean(axis=0)
    radii = np.linalg.norm(pts - centroid, axis=1)
    assert radii.std() / radii.mean() < 0.05  # tightly clustered around one radius


# ---- relax_once: manual, restart-free relaxation for
# stretchy_polyhedron_init.py's interactive "Inflate" workflow, continuing
# from an already-solved starting point (that app precomputes/caches the
# starting point via solve_wireframe + mesh_subdivide.solve_fabric_mesh --
# see its module docstring for why applying pressure directly to a raw
# random start doesn't work well: it can hang for a very long time, the
# same failure _inflate's docstring documents for a "cold" random point
# cloud). Using solve_wireframe's own result as that starting point here
# too keeps these tests representative of the real usage.

def test_relax_once_continues_from_the_given_positions_not_from_scratch():
    # solve_wireframe's tetrahedron result is already inflated a little
    # past exact unit edge length (see
    # test_solve_wireframe_on_a_tetrahedron_inflates_within_the_stretch_cap:
    # a regular tetrahedron is already at max volume for 4 unit
    # triangles, so inflation just stretches it slightly). A zero-pressure
    # relax_once from THAT shape should pull the stretch back down close
    # to 0% -- proving it genuinely continued refining the given shape
    # rather than landing on some unrelated fresh embedding (which would
    # have no reason to end up this well edge-length-fitted).
    positions, stats = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    assert stats["max_stretch_pct"] > 0.5  # confirms it started non-trivially stretched
    _, nfev, max_stretch, rms_stretch, optimality, converged = relax_once(
        positions, TETRAHEDRON_FACES, EDGE_LENGTH, pressure=0.0, volume_target=0.0)
    assert max_stretch < 0.1
    assert converged
    assert optimality is not None and optimality < 1e-4


def test_relax_once_max_nfev_caps_reported_steps():
    # nfev is counted by relax_once's own wrapper (every actual call,
    # including numerical-Jacobian perturbations), so it can overshoot
    # max_nfev a little -- scipy only checks the cap between its own
    # internal steps, not mid-Jacobian-estimate -- but a small budget
    # should still cut off well short of an unbounded run.
    vol_target = _sphere_bound_volume(TETRAHEDRON_FACES, EDGE_LENGTH)
    positions, _ = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    _, nfev, _, _, _, converged = relax_once(
        positions, TETRAHEDRON_FACES, EDGE_LENGTH,
        pressure=3.0, volume_target=vol_target, max_nfev=5)
    assert nfev < 30
    assert not converged  # stopped by the step cap, not scipy's own tolerance


def test_relax_once_stop_event_aborts_and_reports_not_converged():
    vol_target = _sphere_bound_volume(TETRAHEDRON_FACES, EDGE_LENGTH)
    positions, _ = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    stop_event = threading.Event()
    stop_event.set()  # already set: should abort at the very first evaluation
    new_positions, nfev, _, _, optimality, converged = relax_once(
        positions, TETRAHEDRON_FACES, EDGE_LENGTH,
        pressure=3.0, volume_target=vol_target, stop_event=stop_event)
    assert set(new_positions) == set(positions)
    assert nfev >= 1
    assert optimality is None
    assert not converged
