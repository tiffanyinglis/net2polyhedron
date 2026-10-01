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
from scipy.spatial.transform import Rotation


def initial_rotation(azim_deg, elev_deg):
    """An explicit orthonormal (direction, right, up) frame read off as a rotation matrix, so
    the starting view matches a deliberately non-axis-aligned angle instead of a bare identity
    quaternion."""
    azim, elev = np.radians(azim_deg), np.radians(elev_deg)
    direction = np.array([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim),
                           np.sin(elev)])
    world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(world_up, direction)
    right /= np.linalg.norm(right)
    up = np.cross(direction, right)
    return Rotation.from_matrix(np.column_stack([direction, right, up]))


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
        """Updates `self.camera["rotation"]` from a rotate-drag tick. Returns True iff a drag
        was actually active (the caller should re-render only then) -- composes two small
        rotations (about the current up axis for a horizontal drag, the current right axis for
        a vertical one) onto the existing quaternion, rather than accumulating into a stored
        azimuth/elevation pair: "up" is whatever the rotation currently says it is (not re-pinned
        to world +z every frame), so there's no pole for elevation to lock up near, and no clamp
        needed. Also sets `self.drag_moved` once movement exceeds `click_move_tolerance_px` --
        the caller's own `end_drag()` uses this to tell a genuine rotate-drag apart from a plain
        click."""
        if not self.dragging or self.last_xy is None:
            return False
        last_x, last_y = self.last_xy
        dx, dy = x - last_x, y - last_y
        if abs(dx) > self.click_move_tolerance_px or abs(dy) > self.click_move_tolerance_px:
            self.drag_moved = True
        cam = self.camera
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        right = cam["rotation"].apply([0.0, 1.0, 0.0])
        sensitivity = np.radians(self.drag_sensitivity)
        yaw = Rotation.from_rotvec(-dx * sensitivity * up)
        pitch = Rotation.from_rotvec(-dy * sensitivity * right)
        cam["rotation"] = pitch * yaw * cam["rotation"]
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
        """Updates `self.camera["pan"]` (a 2D NDC offset) from a pan-drag tick. Returns True iff
        a pan was actually active. Needs no per-panel scale beyond `panel_width`/`panel_height`
        since NDC is resolution/scale-independent."""
        if not self.panning or self.pan_last_xy is None:
            return False
        last_x, last_y = self.pan_last_xy
        dx, dy = x - last_x, y - last_y
        self.camera["pan"] = self.camera["pan"] + np.array(
            [-dx / (panel_width / 2.0), dy / (panel_height / 2.0)])
        self.pan_last_xy = (x, y)
        return True

    def end_pan(self):
        self.panning = False
        self.pan_last_xy = None

    def scroll(self, zoom_in):
        factor = self.zoom_step if zoom_in else 1.0 / self.zoom_step
        self.camera["zoom"] = max(self.zoom_min, min(self.zoom_max, self.camera["zoom"] * factor))
