import numpy as np

from utils.camera_trackball import initial_rotation, rotate, pan, zoom


def test_initial_rotation_is_orthonormal():
    r = initial_rotation(azim_deg=-60.0, elev_deg=30.0)
    m = r.as_matrix()
    assert np.allclose(m.T @ m, np.eye(3), atol=1e-9)
    assert np.isclose(np.linalg.det(m), 1.0)


def test_rotate_changes_rotation_for_nonzero_drag():
    r0 = initial_rotation(-60.0, 30.0)
    r1 = rotate(r0, dx=10, dy=5, sensitivity_deg=0.5)
    assert not np.allclose(r0.as_quat(), r1.as_quat())


def test_rotate_is_noop_for_zero_drag():
    r0 = initial_rotation(-60.0, 30.0)
    r1 = rotate(r0, dx=0, dy=0, sensitivity_deg=0.5)
    assert np.allclose(r0.as_quat(), r1.as_quat())


def test_pan_accumulates_ndc_offset():
    p0 = np.zeros(2)
    p1 = pan(p0, dx=100, dy=50, panel_width=400, panel_height=300)
    # rightward drag -> negative x (image moves left relative to content); downward -> positive y
    assert p1[0] < 0
    assert p1[1] > 0
    p2 = pan(p1, dx=-100, dy=-50, panel_width=400, panel_height=300)
    assert np.allclose(p2, p0)


def test_zoom_in_increases_and_clamps_to_hi():
    value = zoom(3.9, zoom_in=True, step=1.1, lo=0.3, hi=4.0)
    assert value == 4.0  # 3.9 * 1.1 would exceed the clamp


def test_zoom_out_decreases_and_clamps_to_lo():
    value = zoom(0.4, zoom_in=False, step=1.1, lo=0.3, hi=4.0)
    assert np.isclose(value, 0.4 / 1.1)
    value_floor = zoom(0.3, zoom_in=False, step=1.1, lo=0.3, hi=4.0)
    assert value_floor == 0.3


def test_zoom_in_then_out_round_trips():
    value = zoom(1.0, zoom_in=True, step=1.1, lo=0.3, hi=4.0)
    value = zoom(value, zoom_in=False, step=1.1, lo=0.3, hi=4.0)
    assert np.isclose(value, 1.0)
