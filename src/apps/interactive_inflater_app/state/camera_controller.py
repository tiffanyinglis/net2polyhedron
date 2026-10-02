"""The 3D panel's own camera (rotation/zoom/pan) plus its rotate-drag/pan-drag/scroll-zoom
gesture bookkeeping, isolated into one small stateful object (2026-09-30 modularization).

This is a genuinely stateful class (not a pure function like the `logic/` modules) -- a rotate-
drag literally accumulates rotation across several calls -- but its state is entirely self-
contained (just (x, y) pairs and a quaternion/pan/zoom triple, no Tkinter/VTK objects of its own)
and touched almost nowhere else in the file (one exception: `InflaterPane.
set_open_edge_drag_cancelled_from_builder` calls `cancel_drag()` to interrupt an in-progress
rotate-drag when an unrelated 3D connection-drag needs to take over the same mouse-down). The
OWNER (`InflaterPane`) still does the actual VTK camera positioning (`_apply_camera`) and
re-render (`_refresh_view`/`_render`) -- this class only computes what the camera VALUE should
become in response to an event.
"""
import numpy as np

# `initial_rotation` moved to utils.camera_trackball (2026-10-01, explicit: "make sure they are
# using shared code whenever possible. shared code should be moved to utils") -- was duplicated,
# byte-identical, in inflate_polyhedron_app's own app.py (where the SAME math was further
# duplicated a second time, between its InflaterPane level-panel camera and its ViewerPane
# quadrant camera). Re-exported under the same name so this module's own `initial_rotation(...)`
# call sites are unchanged.
from utils.camera_trackball import (
    initial_rotation, rotate as _camera_rotate, pan as _camera_pan, zoom as _camera_zoom,
)


class CameraController:
    """One 3D panel's own camera plus its rotate-drag/pan-drag/scroll-zoom gesture state.
    `camera` (a {"rotation", "zoom", "pan"} dict) is the persistent value `InflaterPane._apply_
    camera`/`_render`/`_render_replay_frame` read every frame; the rest of this class's state is
    purely transient per-gesture bookkeeping."""

    def __init__(self, default_azim, default_elev, drag_sensitivity, click_move_tolerance_px,
                 zoom_step, zoom_min, zoom_max):
        self.default_azim = default_azim
        self.default_elev = default_elev
        self.drag_sensitivity = drag_sensitivity
        self.click_move_tolerance_px = click_move_tolerance_px
        self.zoom_step = zoom_step
        self.zoom_min = zoom_min
        self.zoom_max = zoom_max
        self.camera = {"rotation": initial_rotation(default_azim, default_elev), "zoom": 1.0,
                        "pan": np.zeros(2)}
        self.dragging = False
        self.last_xy = None
        self.drag_moved = False
        self.panning = False
        self.pan_last_xy = None

    def reset(self):
        """Middle-click/menu reset -- back to the default angle, zoom, and pan, same as a fresh
        panel."""
        self.camera = {"rotation": initial_rotation(self.default_azim, self.default_elev),
                        "zoom": 1.0, "pan": np.zeros(2)}

    def start_drag(self, x, y):
        self.dragging = True
        self.last_xy = (x, y)
        self.drag_moved = False

    def drag_motion(self, x, y):
        """Updates `self.camera["rotation"]` from a rotate-drag tick (utils.camera_trackball.
        rotate -- a free trackball rotation, see its own docstring). Returns True iff a drag was
        actually active (the caller should re-render only then). Also sets `self.drag_moved`
        once movement exceeds `click_move_tolerance_px` -- the caller's own `end_drag()` uses
        this to tell a genuine rotate-drag apart from a plain click."""
        if not self.dragging or self.last_xy is None:
            return False
        last_x, last_y = self.last_xy
        dx, dy = x - last_x, y - last_y
        if abs(dx) > self.click_move_tolerance_px or abs(dy) > self.click_move_tolerance_px:
            self.drag_moved = True
        self.camera["rotation"] = _camera_rotate(self.camera["rotation"], dx, dy,
                                                   self.drag_sensitivity)
        self.last_xy = (x, y)
        return True

    def end_drag(self):
        """Returns (was_dragging, moved) -- the caller uses this to decide whether a press+
        release with no meaningful motion in between should instead select whatever's under the
        cursor (a plain click, not a rotate-drag)."""
        was_dragging, moved = self.dragging, self.drag_moved
        self.dragging = False
        self.last_xy = None
        return was_dragging, moved

    def cancel_drag(self):
        """Resets rotate-drag state without treating it as a click or firing anything -- used
        when an UNRELATED gesture (e.g. a 3D connection-drag) needs to interrupt a rotate-drag
        that was in progress at the same mouse-down, so the next motion tick doesn't read a now-
        stale `last_xy` as an abrupt camera snap."""
        self.dragging = False
        self.last_xy = None

    def start_pan(self, x, y):
        self.panning = True
        self.pan_last_xy = (x, y)

    def pan_motion(self, x, y, panel_width, panel_height):
        """Updates `self.camera["pan"]` (a 2D NDC offset) from a pan-drag tick (utils.
        camera_trackball.pan). Returns True iff a pan was actually active."""
        if not self.panning or self.pan_last_xy is None:
            return False
        last_x, last_y = self.pan_last_xy
        dx, dy = x - last_x, y - last_y
        self.camera["pan"] = _camera_pan(self.camera["pan"], dx, dy, panel_width, panel_height)
        self.pan_last_xy = (x, y)
        return True

    def end_pan(self):
        self.panning = False
        self.pan_last_xy = None

    def scroll(self, zoom_in):
        self.camera["zoom"] = _camera_zoom(self.camera["zoom"], zoom_in, self.zoom_step,
                                            self.zoom_min, self.zoom_max)
