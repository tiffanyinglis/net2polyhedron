import json
import threading

import numpy as np
import pytest

from utils.inflate_polyhedron import stretchy_mesh
from utils.inflate_polyhedron.stretchy_mesh import (
    load_stretchy_mesh, mesh_edges, mesh_to_polyhedron,
    _mesh_volume, _volume_indices, _planarity_groups,
    _orientation_signs, _is_orientation_consistent,
    relax_once, relax_initial_configuration, random_initial_positions,
    EDGE_LENGTH, mesh_volume, per_face_volumes, is_orientation_consistent,
    fold_pairs_from_chains,
)
from utils.geometry.polyhedron import Polyhedron
from utils.inflate_polyhedron.mesh_levels import subdivide_once

PENTAGONS_AND_SQUARE = "data/input/stretchy_nets/two_pentagons_and_a_square.json"

# Three squares, each pair sharing exactly 2 sides with one "partner" square
# (cyclically: A-B, B-C, C-A), forcing genuine non-planar bend the same way
# PENTAGONS_AND_SQUARE does. Combinatorially: 3 quad faces, 5 vertices
# (2 "pole" vertices each touching all 3 faces, 3 "equatorial" vertices
# each touching only 2), 6 edges -- like a triangular bipyramid's 6
# triangular faces merged pairwise into 3 quads. Inflated, it rounds out
# into a compact, roughly 4-cornered blob (the 2 poles pull apart from the
# 3 equatorial points) -- a deliberately awkward, no-slack-for-planarity
# case for exercising the inflation algorithm, same role PENTAGONS_AND_SQUARE
# plays for pentagons.
THREE_SQUARES = "data/input/stretchy_nets/three_squares.json"

TETRAHEDRON_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]]

# A real, unit-edge-length regular tetrahedron (CCW-from-outside faces) --
# inlined here (rather than loaded from a rigid net .json) since this is the
# only place in the stretchy pipeline that needs real coordinates rather
# than just combinatorics.
_RIGID_TETRAHEDRON_VERTICES = [
    [1.0, 1.0, 1.0],
    [1.0, -1.0, -1.0],
    [-1.0, 1.0, -1.0],
    [-1.0, -1.0, 1.0],
]
_RIGID_TETRAHEDRON_FACES = [[2, 0, 1], [3, 0, 2], [2, 1, 3], [1, 0, 3]]

# Closed-form volumes of the regular Platonic solids at unit edge length.
TRUE_VOLUME = {
    "tetrahedron": 1 / (6 * np.sqrt(2)),
    "cube": 1.0,
    "octahedron": np.sqrt(2) / 3,
    "icosahedron": (5 / 12) * (3 + np.sqrt(5)),
    "dodecahedron": (15 + 7 * np.sqrt(5)) / 4,
}


def _relaxed_positions(faces, edge_length=EDGE_LENGTH, seed=0, max_nfev=None):
    """A real, non-degenerate embedding of `faces`, via the same
    random-start-plus-spring-relax pipeline inflate_polyhedron_app itself
    now uses for its own starting configuration (see
    stretchy_mesh.relax_initial_configuration) -- used throughout this
    file wherever a test just needs SOME concrete positions to work with,
    in place of the old solve_wireframe fixture data. `max_nfev` caps the
    relax short of full convergence, for a test that specifically wants a
    still-somewhat-stretched starting point."""
    pos0 = random_initial_positions(faces, seed=seed)
    positions, *_ = relax_initial_configuration(pos0, faces, edge_length, max_nfev=max_nfev)
    return positions


def test_load_pentagons_and_square_example():
    faces, name, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    assert len(faces) == 3
    assert [len(f) for f in faces] == [5, 5, 4]
    assert name == "Two Pentagons and a Square"


def test_load_three_squares_example():
    faces, name, _ = load_stretchy_mesh(THREE_SQUARES)
    assert len(faces) == 3
    assert all(len(f) == 4 for f in faces)
    assert name == "Three Squares"
    n_verts = len({v for face in faces for v in face})
    edges = mesh_edges(faces)
    assert n_verts == 5
    assert len(edges) == 6
    assert n_verts - len(edges) + len(faces) == 2  # Euler's formula: closed, genus-0


def test_load_stretchy_mesh_allows_unmatched_directed_edge(tmp_path):
    # a single triangle: every edge has no reverse partner at all -- an
    # OPEN net is valid (no closedness requirement), so this loads fine.
    path = tmp_path / "open.json"
    path.write_text(json.dumps({"faces": [[0, 1, 2]]}))
    faces, _, _ = load_stretchy_mesh(str(path))
    assert faces == [[0, 1, 2]]


def test_load_stretchy_mesh_rejects_duplicate_directed_edge(tmp_path):
    # two faces both declaring the SAME directed edge 0->1
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"faces": [[0, 1, 2], [0, 1, 3]]}))
    with pytest.raises(ValueError, match="appears 2 times"):
        load_stretchy_mesh(str(path))


def test_load_stretchy_mesh_applies_an_edge_fold(tmp_path):
    # A hexagon with edge 0 (corners 0-1) folded onto its OPPOSITE edge,
    # edge 3 (corners 3-4) -- interactive_builder_app's own tuple format,
    # [v1, v2, v3, v4] = edge_a's corners in natural order, edge_b's
    # REVERSED (see this module's own docstring): couples 0~4, 1~3.
    # Unlike an ordinary shared vertex, a fold does NOT merge ids (see
    # module docstring's "Edge folds are a real spring, not a vertex
    # merge") -- faces keeps every id exactly as authored, and the
    # coupling comes back separately as fold_pairs/fold_chains.
    path = tmp_path / "pinched_hex.json"
    path.write_text(json.dumps({"faces": [[0, 1, 2, 3, 4, 5]], "edge_folds": [[0, 1, 4, 3]]}))
    faces, _, fold_chains = load_stretchy_mesh(str(path))
    assert faces == [[0, 1, 2, 3, 4, 5]], "a fold never touches faces' own ids"
    assert stretchy_mesh.fold_pairs_from_chains(fold_chains) == [(0, 4), (1, 3)]


def test_load_stretchy_mesh_edge_fold_references_unknown_vertex(tmp_path):
    path = tmp_path / "bad_fold.json"
    path.write_text(json.dumps({"faces": [[0, 1, 2, 3, 4, 5]], "edge_folds": [[0, 1, 4, 9]]}))
    with pytest.raises(ValueError, match="no face uses"):
        load_stretchy_mesh(str(path))


def test_mesh_edges_deduplicates_and_sorts():
    faces, _, _ = load_stretchy_mesh(PENTAGONS_AND_SQUARE)
    edges = mesh_edges(faces)
    assert edges == sorted(set(edges))
    assert all(a < b for a, b in edges)
    assert len(edges) == 7  # 3 shared A-B + 2 A-S + 2 B-S


def test_mesh_to_polyhedron_wraps_a_solved_mesh():
    positions = _relaxed_positions(TETRAHEDRON_FACES)
    solid = mesh_to_polyhedron(positions, TETRAHEDRON_FACES, name="tetra")
    assert isinstance(solid, Polyhedron)
    assert solid.name == "tetra"
    assert len(solid.vertices) == len(positions)
    assert len(solid.faces) == len(TETRAHEDRON_FACES)
    assert solid.is_closed()
    assert len(solid.edges) == len(mesh_edges(TETRAHEDRON_FACES))


def test_mesh_to_polyhedron_handles_non_contiguous_vertex_ids():
    # vertex ids 10/20/30 instead of 0/1/2 -- Polyhedron itself needs a
    # dense 0..N-1 index space, so mesh_to_polyhedron must remap them.
    positions = {10: np.array([0.0, 0.0, 0.0]), 20: np.array([1.0, 0.0, 0.0]),
                 30: np.array([0.0, 1.0, 0.0])}
    faces = [[10, 20, 30]]
    solid = mesh_to_polyhedron(positions, faces)
    assert solid.faces == [(0, 1, 2)]
    assert np.array_equal(solid.vertices[0], positions[10])
    assert np.array_equal(solid.vertices[1], positions[20])
    assert np.array_equal(solid.vertices[2], positions[30])


# ---- _mesh_volume / planarity groups ----

def _unit_edge_tetrahedron_points():
    verts = np.array(_RIGID_TETRAHEDRON_VERTICES)
    faces = _RIGID_TETRAHEDRON_FACES
    edge_length = np.linalg.norm(verts[faces[0][0]] - verts[faces[0][1]])
    return verts / edge_length, faces


def test_mesh_volume_matches_the_true_regular_tetrahedron_volume():
    pts, faces = _unit_edge_tetrahedron_points()
    idx = {i: i for i in range(len(pts))}
    volume_indices = _volume_indices(faces, idx)
    assert np.isclose(_mesh_volume(pts, volume_indices), TRUE_VOLUME["tetrahedron"], atol=1e-6)


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


def test_relax_once_pressure_still_inflates_a_subdivided_mesh():
    faces, _, _ = load_stretchy_mesh("data/input/stretchy_nets/cube.json")
    positions = _relaxed_positions(faces)
    faces1, positions1, edge_length1, _, _ = subdivide_once(
        faces, positions, EDGE_LENGTH, list(range(len(faces))), level=0)
    _, _, low_stretch, _, _, _ = relax_once(positions1, faces1, edge_length1, pressure=0.1)
    _, _, high_stretch, _, _, _ = relax_once(positions1, faces1, edge_length1, pressure=1.0)
    assert high_stretch > low_stretch + 1.0  # meaningfully more, not stuck near zero


# ---- edge-fold coupling (module docstring's "Edge folds are a real spring, not a vertex merge") ----

def test_edge_fold_coupling_pulls_a_folded_pair_together_without_merging_ids():
    # pinched_hex.json's hexagon, edge 0 folded onto its opposite edge 3.
    # Relaxing with the resulting fold_pairs must pull corners 0~4 and
    # 1~3 close together (the fold "holding"), while every id in faces
    # stays distinct throughout -- no accidental collapse.
    faces, _, fold_chains = load_stretchy_mesh("data/input/stretchy_nets/pinched_hex.json")
    fold_pairs = fold_pairs_from_chains(fold_chains)
    face1, positions1, edge_length1, _, fold_chains1 = subdivide_once(
        faces, random_initial_positions(faces, seed=1), EDGE_LENGTH,
        list(range(len(faces))), level=0, fold_chains=fold_chains)
    fold_pairs1 = fold_pairs_from_chains(fold_chains1)

    positions1, *_ = relax_initial_configuration(
        positions1, face1, edge_length1, max_nfev=8000, gtol=1e-4,
        rng=np.random.default_rng(1), fold_pairs=fold_pairs1)

    assert len({v for face in face1 for v in face}) == len(positions1), \
        "a fold must never merge vertex ids"
    for a, b in fold_pairs1:
        gap = np.linalg.norm(positions1[a] - positions1[b])
        assert gap < 0.1, f"fold pair ({a}, {b}) should have closed, gap={gap}"


def test_edge_fold_coupling_does_not_oscillate():
    # The coupling spring is far stiffer than an ordinary edge spring
    # (FOLD_COUPLING_STIFFNESS); without _damp_coupling_overshoot's own
    # damping, a folded pair's gap oscillates indefinitely rather than
    # closing (verified directly during development). Once damped, the
    # gap in the SECOND half of a long run must be no bigger than in the
    # first half -- a genuinely converging (or already-converged) system,
    # not one still bouncing around a fixed range.
    faces, _, fold_chains = load_stretchy_mesh("data/input/stretchy_nets/pinched_hex.json")
    face1, positions1, edge_length1, _, fold_chains1 = subdivide_once(
        faces, random_initial_positions(faces, seed=2), EDGE_LENGTH,
        list(range(len(faces))), level=0, fold_chains=fold_chains)
    fold_pairs1 = fold_pairs_from_chains(fold_chains1)
    a, b = fold_pairs1[0]

    gaps = []
    for _ in range(20):
        positions1, *_ = relax_initial_configuration(
            positions1, face1, edge_length1, max_nfev=500, gtol=1e-4,
            rng=np.random.default_rng(2), fold_pairs=fold_pairs1)
        gaps.append(np.linalg.norm(positions1[a] - positions1[b]))

    first_half_max = max(gaps[:10])
    second_half_max = max(gaps[10:])
    assert second_half_max <= first_half_max + 1e-6


# name -> (num_faces, num_vertices, num_edges, sides_per_face) -- these
# stretchy nets share the same combinatorial structure as the RIGID
# data/input/nets/*.json specs for the same solids.
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
    faces, _, _ = load_stretchy_mesh(f"data/input/stretchy_nets/{name}.json")
    assert len(faces) == n_faces
    assert all(len(f) == sides for f in faces)
    assert len({v for face in faces for v in face}) == n_verts
    edges = mesh_edges(faces)
    assert len(edges) == n_edges
    assert n_verts - n_edges + n_faces == 2  # Euler's formula: closed, genus-0


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


# ---- relax_once: manual, restart-free relaxation for
# inflate_polyhedron_app's interactive "Inflate" workflow, continuing
# from an already-relaxed starting point (that app now builds its own
# starting point via relax_initial_configuration -- see that function's
# and inflate_polyhedron_app's own module docstrings). Using
# _relaxed_positions here too keeps these tests representative of the
# real usage.

def test_relax_once_continues_from_the_given_positions_not_from_scratch():
    # A partial (not fully converged) relax_initial_configuration run
    # leaves the tetrahedron meaningfully stretched. A zero-pressure
    # relax_once from THAT shape should pull the stretch back down close
    # to 0% -- proving it genuinely continued refining the given shape
    # rather than landing on some unrelated fresh embedding (which would
    # have no reason to end up this well edge-length-fitted).
    positions = _relaxed_positions(TETRAHEDRON_FACES, max_nfev=5)
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
    positions = _relaxed_positions(TETRAHEDRON_FACES)
    _, nfev, _, _, _, converged = relax_once(
        positions, TETRAHEDRON_FACES, EDGE_LENGTH, pressure=3.0, max_nfev=5)
    assert nfev < 30
    assert not converged  # stopped by the step cap, not scipy's own tolerance


def test_relax_once_stop_event_aborts_and_reports_not_converged():
    positions = _relaxed_positions(TETRAHEDRON_FACES)
    stop_event = threading.Event()
    stop_event.set()  # already set: should abort before even the first step
    new_positions, nfev, _, _, max_force, converged = relax_once(
        positions, TETRAHEDRON_FACES, EDGE_LENGTH, pressure=3.0, stop_event=stop_event)
    assert set(new_positions) == set(positions)
    assert nfev == 0  # no step actually ran
    assert max_force is None
    assert not converged


def test_relax_once_stop_event_reported_nfev_is_capped_by_max_nfev():
    # Each relax_once iteration checks stop_event BEFORE computing that
    # step's force, so a Stop raised from inside one step's own force
    # calculation still lets that step complete, but the NEXT iteration's
    # check aborts before another one starts -- reported steps should be
    # exactly the number that actually completed, never more than max_nfev.
    positions = _relaxed_positions(TETRAHEDRON_FACES)
    stop_event = threading.Event()

    calls = [0]
    real_force = stretchy_mesh._relax_force

    def counting_force(*args, **kwargs):
        calls[0] += 1
        stop_event.set()  # stop after this step's force is computed
        return real_force(*args, **kwargs)

    import unittest.mock
    with unittest.mock.patch.object(stretchy_mesh, "_relax_force", counting_force):
        _, nfev, _, _, max_force, converged = relax_once(
            positions, TETRAHEDRON_FACES, EDGE_LENGTH,
            pressure=3.0, max_nfev=1, stop_event=stop_event)
    assert nfev == 1
    assert not converged


def test_relax_once_pressure_increases_stretch_over_a_normal_working_range():
    # relax_once's spring+pressure force balance (see module docstring's
    # Design notes) genuinely stretches more as pressure grows, over a
    # range comfortably below the pressure where a plain cube stops
    # having any equilibrium at all (see the Design notes on why there's
    # no runaway guard) -- past that, more pressure isn't meaningful.
    faces, _, _ = load_stretchy_mesh("data/input/stretchy_nets/cube.json")
    positions = _relaxed_positions(faces)
    stretches = []
    for pressure in (0.1, 0.3, 0.8):
        _, _, max_stretch, _, _, _ = relax_once(positions, faces, EDGE_LENGTH, pressure=pressure)
        stretches.append(max_stretch)
    assert stretches[0] < stretches[1] < stretches[2]


# ---- estimate_pressure_for_target_stretch: stop mid-calibration ----

def test_estimate_pressure_stopped_mid_calibration_reports_current_trial(monkeypatch):
    # Stopping mid-calibration must report wherever the CURRENTLY
    # running trial left off, not an earlier trial that happened to
    # score closer to the target: an app watching this update the
    # screen live would otherwise see it silently jump backwards to a
    # different, stale shape the instant the user clicks Stop.
    calls = []

    def fake_relax_once(positions, faces, edge_length, pressure, planarity_weight,
                         max_nfev=None, stop_event=None, gtol=stretchy_mesh.CONVERGENCE_GTOL,
                         rng=None, fold_pairs=()):
        calls.append(pressure)
        if len(calls) == 1:
            # Closer to the 10% target (error 2) -- would be "best" by
            # score alone, but isn't the trial that gets interrupted.
            return ({0: np.zeros(3)}, 5, 1.0, 8.0, 0.5, False)
        # Second trial: further from target (error 15) AND the one
        # that's actually stopped mid-run.
        stop_event.set()
        return ({0: np.ones(3)}, 3, 5.0, 25.0, 0.5, False)

    monkeypatch.setattr(stretchy_mesh, "relax_once", fake_relax_once)
    stop_event = threading.Event()
    result = stretchy_mesh.estimate_pressure_for_target_stretch(
        {0: np.zeros(3)}, [[0, 1, 2]], EDGE_LENGTH, target_rms_pct=10.0,
        max_iterations=2, stop_event=stop_event)
    _, new_positions, _, _, rms_stretch, _, _ = result
    assert len(calls) == 2, "the test must actually reach a second, interrupted trial"
    assert rms_stretch == 25.0
    assert np.array_equal(new_positions[0], np.ones(3))


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
    # A single GLOBAL pressure term gives the optimizer a cheap way to
    # satisfy it on a mesh with many vertices/faces without genuinely
    # inflating at all: fold one small local patch through itself, which
    # spikes the naive divergence-theorem volume sum while leaving nearly
    # every edge (and every OTHER face) untouched. A coarse mesh (few
    # faces, tested above on data/input/stretchy_nets/cube.json) has no
    # room for that cheat -- every vertex has too much leverage over too
    # large a fraction of the mesh's edges. A subdivided FINE mesh (many
    # small faces) is exactly where the cheat has room to hide, so that's
    # what this test exercises: the tetrahedron fan-triangulated (level 0,
    # a no-op on already-triangular faces) then quartered once more
    # (level 1, mesh_levels.subdivide_once) -- 16 small triangles, given a
    # real starting embedding via relax_initial_configuration (seed=0
    # happens to land orientation-consistent; see that function's
    # docstring for why this isn't guaranteed for every seed) -- then
    # relaxed under real pressure. If the per-face fix works, every face
    # keeps agreeing on which way is outward at every step, even as the
    # mesh visibly inflates (positive, growing stretch) -- no
    # self-intersecting fold.
    dummy0 = {v: np.zeros(3) for face in TETRAHEDRON_FACES for v in face}
    faces1, _, edge_length1, face_of_fine1, _ = subdivide_once(
        TETRAHEDRON_FACES, dummy0, EDGE_LENGTH, list(range(len(TETRAHEDRON_FACES))), 0)
    dummy1 = {v: np.zeros(3) for face in faces1 for v in face}
    fine_faces, _, edge_length, _, _ = subdivide_once(faces1, dummy1, edge_length1, face_of_fine1, 1)

    pos = _relaxed_positions(fine_faces, edge_length=edge_length, seed=0)
    assert is_orientation_consistent(pos, fine_faces)

    prev_stretch = -1.0
    for pressure in (0.2, 0.5, 0.8):
        pos, _, max_stretch, _, _, converged = relax_once(
            pos, fine_faces, edge_length, pressure=pressure)
        assert is_orientation_consistent(pos, fine_faces)
        assert max_stretch > prev_stretch  # genuinely more pressure keeps demanding more stretch
        prev_stretch = max_stretch
