import numpy as np

from interactive_inflater_app.state.camera_controller import CameraController, initial_rotation


def _make_controller(**overrides):
    kwargs = dict(default_azim=-60.0, default_elev=30.0, drag_sensitivity=0.5,
                  click_move_tolerance_px=3, zoom_step=1.1, zoom_min=0.3, zoom_max=4.0)
    kwargs.update(overrides)
    return CameraController(**kwargs)


def test_initial_rotation_is_orthonormal():
    rot = initial_rotation(-60.0, 30.0)
    matrix = rot.as_matrix()
    assert np.allclose(matrix @ matrix.T, np.eye(3), atol=1e-9)


def test_starts_at_default_camera():
    cam = _make_controller()
    assert cam.camera["zoom"] == 1.0
    assert np.array_equal(cam.camera["pan"], np.zeros(2))
    assert not cam.dragging and not cam.panning


def test_drag_motion_noop_when_not_dragging():
    cam = _make_controller()
    before = cam.camera["rotation"].as_quat()
    assert cam.drag_motion(10, 10) is False
    assert np.array_equal(cam.camera["rotation"].as_quat(), before)


def test_start_drag_then_motion_rotates_and_flags_moved_past_tolerance():
    cam = _make_controller()
    before = cam.camera["rotation"].as_quat()
    cam.start_drag(100, 100)
    assert cam.drag_moved is False
    assert cam.drag_motion(120, 95) is True
    assert not np.array_equal(cam.camera["rotation"].as_quat(), before)
    assert cam.drag_moved is True  # moved 20/5 px, past the 3px tolerance


def test_small_motion_stays_under_click_tolerance():
    cam = _make_controller()
    cam.start_drag(100, 100)
    cam.drag_motion(101, 100)  # 1px, under tolerance=3
    assert cam.drag_moved is False


def test_end_drag_reports_state_and_resets():
    cam = _make_controller()
    cam.start_drag(100, 100)
    cam.drag_motion(120, 95)
    was_dragging, moved = cam.end_drag()
    assert (was_dragging, moved) == (True, True)
    assert cam.dragging is False
    assert cam.last_xy is None


def test_end_drag_without_start_reports_not_dragging():
    cam = _make_controller()
    assert cam.end_drag() == (False, False)


def test_cancel_drag_resets_without_affecting_drag_moved():
    cam = _make_controller()
    cam.start_drag(100, 100)
    cam.drag_motion(120, 95)
    cam.cancel_drag()
    assert cam.dragging is False
    assert cam.last_xy is None
    # cancel_drag deliberately doesn't touch drag_moved -- only dragging/last_xy, per its own
    # docstring (interrupted by an unrelated gesture, not treated as a click resolution).
    assert cam.drag_moved is True


def test_pan_motion_updates_pan_in_ndc_units():
    cam = _make_controller()
    cam.start_pan(0, 0)
    assert cam.pan_motion(10, -10, panel_width=100, panel_height=100) is True
    assert np.allclose(cam.camera["pan"], [-0.2, -0.2])


def test_pan_motion_noop_when_not_panning():
    cam = _make_controller()
    assert cam.pan_motion(10, 10, 100, 100) is False


def test_end_pan_resets_state():
    cam = _make_controller()
    cam.start_pan(0, 0)
    cam.end_pan()
    assert cam.panning is False
    assert cam.pan_last_xy is None


def test_scroll_zooms_in_and_out_within_bounds():
    cam = _make_controller(zoom_step=2.0, zoom_min=0.5, zoom_max=4.0)
    cam.scroll(zoom_in=True)
    assert cam.camera["zoom"] == 2.0
    cam.scroll(zoom_in=False)
    assert cam.camera["zoom"] == 1.0


def test_scroll_clamps_to_zoom_bounds():
    cam = _make_controller(zoom_step=10.0, zoom_min=0.5, zoom_max=4.0)
    cam.scroll(zoom_in=True)
    assert cam.camera["zoom"] == 4.0
    cam.scroll(zoom_in=False)
    cam.scroll(zoom_in=False)
    assert cam.camera["zoom"] == 0.5


def test_reset_restores_default_camera_after_changes():
    cam = _make_controller()
    cam.start_pan(0, 0)
    cam.pan_motion(50, 50, 100, 100)
    cam.scroll(zoom_in=True)
    cam.reset()
    assert cam.camera["zoom"] == 1.0
    assert np.array_equal(cam.camera["pan"], np.zeros(2))
    assert np.allclose(cam.camera["rotation"].as_quat(),
                        initial_rotation(-60.0, 30.0).as_quat())
