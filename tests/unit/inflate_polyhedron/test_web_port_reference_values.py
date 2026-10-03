"""Pins exact, DETERMINISTIC (no RNG involved -- fixed input positions, not
random_initial_positions) reference values for the core physics utils, computed from THIS
module's own functions. Exists to give src/webapps/interactive_inflater (a from-scratch
TypeScript port, see its own src/physics/ -- each file there names which function here it
mirrors) a ground truth to assert against with identical inputs, sidestepping the fact that the
two languages use different, uncorrelated RNGs (numpy vs a JS PRNG) -- a random-seeded comparison
across languages can never agree, but every function exercised here is pure given its inputs, so
a FIXED input must produce the same output in both. See that project's own test suite
(src/webapps/interactive_inflater/src/physics/__tests__/) for the matching JS-side assertions
using these exact same inputs and expected values.

Not a substitute for test_stretchy_mesh.py/test_mesh_levels.py's own broader behavioral
coverage -- this file exists purely to be a cross-language reference fixture."""
import numpy as np
import pytest

from utils.inflate_polyhedron.stretchy_mesh import EDGE_LENGTH, relax_once, _total_rest_area
from utils.inflate_polyhedron.pre_inflation_relaxer import relax_initial_configuration
from utils.inflate_polyhedron.mesh_levels import subdivide_once
from utils.inflate_polyhedron.multi_trial_inflater import estimate_pressure_for_target_stretch
from utils.inflate_polyhedron.convergence_checker import remove_rigid_motion

# A real, unit-edge-length regular tetrahedron (CCW-from-outside faces) -- same vertices/faces as
# test_stretchy_mesh.py's own _RIGID_TETRAHEDRON_VERTICES/_RIGID_TETRAHEDRON_FACES, duplicated
# here (rather than imported) so this file has no dependency on that one's own private names.
RIGID_TETRAHEDRON_VERTICES = [
    [1.0, 1.0, 1.0],
    [1.0, -1.0, -1.0],
    [-1.0, 1.0, -1.0],
    [-1.0, -1.0, 1.0],
]
RIGID_TETRAHEDRON_FACES = [[2, 0, 1], [3, 0, 2], [2, 1, 3], [1, 0, 3]]


def _unit_edge_tetrahedron():
    verts = np.array(RIGID_TETRAHEDRON_VERTICES)
    edge_length = np.linalg.norm(verts[RIGID_TETRAHEDRON_FACES[0][0]] - verts[RIGID_TETRAHEDRON_FACES[0][1]])
    pts = verts / edge_length
    return {i: pts[i] for i in range(4)}, RIGID_TETRAHEDRON_FACES


def test_fan_level_0_to_1_single_triangle_reference():
    # mesh_levels.mesh_levels._TRIANGLE_FAN's own n==3 branch -- a lone triangle face [0,1,2],
    # fanned around a fresh centroid id (3). Positions are placeholders (same convention
    # mesh_topology.build_level1_topology itself uses -- only faces/edge_length/face_of_fine are
    # meaningful here, see that function's own docstring).
    base_faces = [[0, 1, 2]]
    dummy_positions = {0: np.zeros(3), 1: np.zeros(3), 2: np.zeros(3)}
    faces, _positions, edge_length, face_of_fine = subdivide_once(
        base_faces, dummy_positions, EDGE_LENGTH, [0], level=0)

    assert faces == [(0, 1, 3), (1, 2, 3), (2, 0, 3)]
    assert face_of_fine == [0, 0, 0]
    assert edge_length[(0, 1)] == pytest.approx(1.0)
    assert edge_length[(0, 2)] == pytest.approx(1.0)
    assert edge_length[(1, 2)] == pytest.approx(1.0)
    # spoke length = circumradius of a unit-edge equilateral triangle = 1/sqrt(3)
    assert edge_length[(0, 3)] == pytest.approx(0.5773502691896258)
    assert edge_length[(1, 3)] == pytest.approx(0.5773502691896258)
    assert edge_length[(2, 3)] == pytest.approx(0.5773502691896258)


def test_total_rest_area_dict_branch_matches_the_original_unfanned_triangle_area():
    # The fanned mesh's own total area (sum of its 3 wedges, Heron's-formula branch) must equal
    # the ORIGINAL single triangle's closed-form area -- fanning only subdivides, never changes
    # total area. This is exactly the computation src/webapps/interactive_inflater's own
    # pressure-calibration initial guess depends on; a web-port bug here (assuming every face is
    # a REGULAR polygon with one uniform edge length, instead of Heron's formula per actual
    # triangle) was caught by comparing against this exact value.
    base_faces = [[0, 1, 2]]
    dummy_positions = {0: np.zeros(3), 1: np.zeros(3), 2: np.zeros(3)}
    faces, _positions, edge_length, _face_of_fine = subdivide_once(
        base_faces, dummy_positions, EDGE_LENGTH, [0], level=0)

    fanned_area = _total_rest_area(faces, edge_length)
    original_triangle_area = (3 / 4) / np.tan(np.pi / 3) * EDGE_LENGTH ** 2
    assert fanned_area == pytest.approx(original_triangle_area)
    assert fanned_area == pytest.approx(0.43301270189221913)


def test_remove_rigid_motion_recovers_a_known_rotation_and_translation():
    pts_before = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 1.0, 1.0]])
    theta = 0.4
    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    translation = np.array([2.0, -1.0, 0.5])
    pts_after = (pts_before @ rot.T) + translation

    realigned = remove_rigid_motion(pts_before, pts_after)
    np.testing.assert_allclose(realigned, pts_before, atol=1e-9)


def test_relax_once_fixed_unit_tetrahedron_reference():
    # Fully deterministic: an explicit, already-unit-edge-length (zero initial stretch) starting
    # embedding, not random_initial_positions -- no RNG anywhere in this call.
    positions, faces = _unit_edge_tetrahedron()
    new_positions, steps, max_stretch, rms_stretch, optimality, converged = relax_once(
        positions, faces, EDGE_LENGTH, pressure=0.5, max_nfev=200, gtol=1e-4)

    assert steps == 200
    assert not converged  # step cap reached first, at this pressure/step budget
    assert rms_stretch == pytest.approx(4.594339496868712, rel=1e-9)
    assert max_stretch == pytest.approx(rms_stretch)  # a regular tetrahedron stretches uniformly
    assert optimality == pytest.approx(0.0001406723434055446, rel=1e-6)
    # the inflated shape stays a regular tetrahedron, uniformly scaled up from the unit-edge start
    expected_scale = 0.3697968336598191
    for v in range(4):
        np.testing.assert_allclose(
            np.abs(new_positions[v]), [expected_scale] * 3, atol=1e-9)


def test_relax_initial_configuration_fixed_perturbed_start_reference():
    # A fixed (not random) small perturbation away from a unit-edge tetrahedron's own fan-
    # triangulated rest state -- deterministic, so this pins relax_initial_configuration's own
    # spring+repulsion+burst behavior independent of random_initial_positions' RNG.
    base_positions = {i: np.array(v) for i, v in enumerate(RIGID_TETRAHEDRON_VERTICES)}
    fan_faces, fan_positions, fan_edge_length, _face_of_fine = subdivide_once(
        RIGID_TETRAHEDRON_FACES, base_positions, EDGE_LENGTH, list(range(4)), level=0)
    perturbed = {v: p + np.array([0.05 * (v % 3), -0.03 * (v % 2), 0.02])
                 for v, p in fan_positions.items()}

    _new_positions, steps, max_stretch, rms_stretch, optimality, converged = \
        relax_initial_configuration(perturbed, fan_faces, fan_edge_length, max_nfev=400, gtol=1e-4)

    assert steps == 400
    assert converged
    assert rms_stretch == pytest.approx(7.791307986563624, rel=1e-6)
    assert max_stretch == pytest.approx(9.354775223621571, rel=1e-6)
    assert optimality == pytest.approx(2.3154775023524188e-05, rel=1e-3)


def test_estimate_pressure_for_target_stretch_fixed_unit_tetrahedron_reference():
    # Same fixed, zero-initial-stretch unit tetrahedron as the relax_once reference above, run
    # through the full bracket-then-bisect pressure search -- the strongest possible cross-
    # language check, since every trial inside this search is itself deterministic too.
    positions, faces = _unit_edge_tetrahedron()
    pressure, _new_positions, steps, max_stretch, rms_stretch, _optimality, converged, \
        pressure_found = estimate_pressure_for_target_stretch(
            positions, faces, EDGE_LENGTH, target_rms_pct=5.0, max_nfev_per_trial=2000)

    assert pressure_found
    assert converged
    assert steps == 400
    assert pressure == pytest.approx(0.541265877365274, rel=1e-9)
    assert rms_stretch == pytest.approx(4.871642155742525, rel=1e-9)
    assert max_stretch == pytest.approx(rms_stretch)
