import json
import threading

import numpy as np
import pytest

from utils.geometry3d.hull_to_spec import polyhedron_from_vertices
from utils.model.platonic_polyhedra import Tetrahedron
from utils.geometry3d import stretchy_mesh
from utils.subdivisions.mesh_subdivide import solve_fabric_mesh
from utils.geometry3d.stretchy_mesh import (
    load_stretchy_mesh, mesh_edges, solve_wireframe, STRETCH_CAP,
    _overall_3d_extent, _min_pairwise_separation, _mesh_volume, _sphere_bound_volume,
    _volume_indices, _planarity_groups, _face_planarity_residual,
    _orientation_signs, _is_orientation_consistent,
    relax_once, EDGE_LENGTH, mesh_volume, per_face_volumes, is_orientation_consistent,
)

PENTAGONS_AND_SQUARE = "data/input/stretchy_nets/two_pentagons_and_a_square.json"

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


# ---- _mesh_volume / _sphere_bound_volume ----

def _unit_edge_tetrahedron_points():
    verts = np.array(Tetrahedron.raw_vertices())
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
# by src/apps/common/generate_stretchy_platonic_nets.py from the same
# solids (utils/model/platonic_polyhedra.py) the RIGID nets/*.json specs use.
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
    faces, _ = load_stretchy_mesh(f"data/input/stretchy_nets/{name}.json")
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
    faces, _ = load_stretchy_mesh(f"data/input/stretchy_nets/{name}.json")
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
    faces, _ = load_stretchy_mesh("data/input/stretchy_nets/cube.json")
    positions, _ = solve_wireframe(faces, seed=0)
    pts = np.array(list(positions.values()))
    centroid = pts.mean(axis=0)
    radii = np.linalg.norm(pts - centroid, axis=1)
    assert radii.std() / radii.mean() < 0.05  # tightly clustered around one radius


# ---- relax_once: manual, restart-free relaxation for
# inflate_polyhedron_app's interactive "Inflate" workflow, continuing
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
        positions, TETRAHEDRON_FACES, EDGE_LENGTH, pressure=0.0)
    assert max_stretch < 0.1
    assert converged
    assert optimality is not None and optimality < 1e-4


def test_relax_once_max_nfev_caps_reported_steps():
    # nfev is counted by relax_once's own wrapper (every actual call,
    # including numerical-Jacobian perturbations), so it can overshoot
    # max_nfev a little -- scipy only checks the cap between its own
    # internal steps, not mid-Jacobian-estimate -- but a small budget
    # should still cut off well short of an unbounded run.
    positions, _ = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    _, nfev, _, _, _, converged = relax_once(
        positions, TETRAHEDRON_FACES, EDGE_LENGTH, pressure=3.0, max_nfev=5)
    assert nfev < 30
    assert not converged  # stopped by the step cap, not scipy's own tolerance


def test_relax_once_stop_event_aborts_and_reports_not_converged():
    positions, _ = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    stop_event = threading.Event()
    stop_event.set()  # already set: should abort at the very first evaluation
    new_positions, nfev, _, _, optimality, converged = relax_once(
        positions, TETRAHEDRON_FACES, EDGE_LENGTH, pressure=3.0, stop_event=stop_event)
    assert set(new_positions) == set(positions)
    assert nfev >= 1
    assert optimality is None
    assert not converged


def test_relax_once_stop_event_reported_nfev_is_capped_by_max_nfev():
    # A Stop mid-call has no scipy sol.nfev to report, so it falls back to
    # the residual wrapper's raw call count -- which counts every
    # numerical-Jacobian perturbation, not just "steps", and can run well
    # past whatever max_nfev the caller declared (see _relax_residual's
    # docstring). Reported nfev must never exceed that declared budget,
    # so a caller tracking cumulative "steps" (e.g.
    # inflate_polyhedron_app's iteration counter) doesn't see a
    # stopped call's cost look bigger than the caller's own request.
    positions, _ = solve_wireframe(TETRAHEDRON_FACES, seed=0)
    stop_event = threading.Event()

    calls = [0]
    real_wrapped = stretchy_mesh._relax_residual

    def counting_residual(*args, **kwargs):
        calls[0] += 1
        if calls[0] == 2:  # let the raw call count exceed max_nfev before stopping
            stop_event.set()
        return real_wrapped(*args, **kwargs)

    import unittest.mock
    with unittest.mock.patch.object(stretchy_mesh, "_relax_residual", counting_residual):
        _, nfev, _, _, optimality, converged = relax_once(
            positions, TETRAHEDRON_FACES, EDGE_LENGTH,
            pressure=3.0, max_nfev=1, stop_event=stop_event)
    assert nfev <= 1
    assert not converged


def test_relax_once_pressure_has_no_plateau_unlike_a_fixed_target():
    # relax_once uses _relax_residual (pressure * exp(-volume)), not
    # _residual's target-based `pressure * (target - volume)` -- the
    # whole point being that genuinely higher pressure keeps demanding
    # genuinely more stretch, rather than converging toward the same
    # fixed ceiling harder once volume gets close to a precomputed
    # target (verified manually on a subdivided cube: max stretch
    # plateaus around 5.5% from pressure ~100 all the way past 300 with
    # the target-based formula). Confirm that monotonic relationship
    # holds here too, on a small/fast net.
    faces, _ = load_stretchy_mesh("data/input/stretchy_nets/cube.json")
    positions, _ = solve_wireframe(faces, seed=0)
    stretches = []
    for pressure in (1.0, 5.0, 20.0):
        _, _, max_stretch, _, _, _ = relax_once(positions, faces, EDGE_LENGTH, pressure=pressure)
        stretches.append(max_stretch)
    assert stretches[0] < stretches[1] < stretches[2]


# ---- mesh_volume / per_face_volumes / is_orientation_consistent (public wrappers) ----

def test_mesh_volume_public_wrapper_matches_true_tetrahedron_volume():
    pts, faces = _unit_edge_tetrahedron_points()
    positions = {i: pts[i] for i in range(len(pts))}
    assert np.isclose(mesh_volume(positions, faces), TRUE_VOLUME["tetrahedron"], atol=1e-6)


def test_per_face_volumes_sums_to_the_same_total_as_mesh_volume():
    pts, faces = _unit_edge_tetrahedron_points()
    positions = {i: pts[i] for i in range(len(pts))}
    per_face = per_face_volumes(positions, faces)
    assert len(per_face) == len(faces)
    assert np.isclose(per_face.sum(), mesh_volume(positions, faces))


def test_is_orientation_consistent_public_wrapper_matches_private_helper():
    pts, faces = _unit_edge_tetrahedron_points()
    positions = {i: pts[i] for i in range(len(pts))}
    assert is_orientation_consistent(positions, faces)

    flipped_faces = [list(reversed(faces[0]))] + faces[1:]
    flipped_positions = positions  # same points, just one face's winding reversed
    assert not is_orientation_consistent(flipped_positions, flipped_faces)


# ---- per-face pressure (the fix for a fine mesh's "cheap local fold" exploit) ----

def test_relax_once_per_face_pressure_stays_orientation_consistent_on_a_fine_mesh():
    # Before _relax_residual switched to a PER-FACE pressure term, a
    # single GLOBAL `pressure * exp(-total_volume)` residual gave the
    # optimizer a cheap way to satisfy it on a mesh with many
    # vertices/faces without genuinely inflating at all: fold one small
    # local patch through itself, which spikes the naive divergence-
    # theorem volume sum while leaving nearly every edge (and every OTHER
    # face) untouched. A coarse mesh (few faces, tested above on
    # data/input/stretchy_nets/cube.json) has no room for that cheat -- every vertex
    # has too much leverage over too large a fraction of the mesh's
    # edges. A subdivided FINE mesh (many small faces) is exactly where
    # the cheat has room to hide, so that's what this test exercises:
    # a resolution-2 tetrahedron subdivision (16 small triangles),
    # solved and draped via solve_fabric_mesh (giving it the CORRECT,
    # non-uniform per-edge rest lengths a fine mesh actually needs --
    # see mesh_subdivide.py's docstring), then relaxed under real
    # pressure. If the per-face fix works, every face keeps agreeing on
    # which way is outward at every step, even as the mesh visibly
    # inflates (positive, growing stretch) -- no self-intersecting fold.
    fine_faces, _, positions, _ = solve_fabric_mesh(TETRAHEDRON_FACES, resolution=2, seed=0)
    from utils.subdivisions.mesh_subdivide import subdivide_mesh
    _, _, edge_length, _ = subdivide_mesh(TETRAHEDRON_FACES, resolution=2)
    reference_volume = per_face_volumes(positions, fine_faces)

    pos = positions
    prev_stretch = -1.0
    for pressure in (1.0, 5.0, 15.0):
        pos, _, max_stretch, _, _, converged = relax_once(
            pos, fine_faces, edge_length, pressure=pressure, reference_volume=reference_volume)
        assert is_orientation_consistent(pos, fine_faces)
        assert max_stretch > prev_stretch  # genuinely more pressure keeps demanding more stretch
        prev_stretch = max_stretch


def test_relax_once_reference_volume_accepts_a_scalar_or_a_per_face_array():
    # A scalar broadcasts against every face (the original, still-default
    # behavior several other tests rely on); an array with one entry per
    # face (the new, mesh-size-aware normalization -- see
    # _relax_residual's docstring) must work identically well. Same
    # small/fast coarse net as the plateau test above, just checking the
    # two call styles don't raise and both produce a sane, positive
    # stretch increase.
    faces, _ = load_stretchy_mesh("data/input/stretchy_nets/cube.json")
    positions, _ = solve_wireframe(faces, seed=0)

    _, _, scalar_stretch, _, _, _ = relax_once(
        positions, faces, EDGE_LENGTH, pressure=5.0, reference_volume=1.0)
    per_face_ref = mesh_volume(positions, faces) / len(faces)
    _, _, array_stretch, _, _, _ = relax_once(
        positions, faces, EDGE_LENGTH, pressure=5.0,
        reference_volume=np.full(len(faces), per_face_ref))
    assert scalar_stretch > 0
    assert array_stretch > 0
