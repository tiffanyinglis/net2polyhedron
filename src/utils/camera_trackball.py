"""Pure camera trackball math (initial-angle construction, drag-rotate, drag-pan, scroll-zoom)
shared across every PyVista panel in this project (2026-10-01, explicit: "make sure they are
using shared code whenever possible. shared code should be moved to utils"). Previously
duplicated, byte-identical, in THREE places: inflate_polyhedron_app's own InflaterPane level-
panel camera handlers, that same file's ViewerPane quadrant camera handlers, and
interactive_inflater_app's `state/camera_controller.py`.

Not inflate_polyhedron-specific (just quaternion/NDC-offset/clamped-scalar math against a plain
`{"rotation", "zoom", "pan"}` camera dict or its individual fields), so this lives at the top
level rather than under a domain sub-package. A camera's rotation is always a
`scipy.spatial.transform.Rotation`; callers own the dict itself and how it's applied to a real
VTK camera (see each app's own `_render_level_pv`/`_apply_camera`)."""
import numpy as np
from scipy.spatial.transform import Rotation

__all__ = ["initial_rotation", "rotate", "pan", "zoom"]


def initial_rotation(azim_deg, elev_deg):
    """Builds a starting camera quaternion from a classic (azimuth, elevation) pair -- the only
    place spherical angles are converted into a rotation; every update after this (`rotate`)
    works with the quaternion directly and never decomposes it back into angles, which is what
    avoids gimbal lock. Constructs an explicit orthonormal (direction, right, up) frame and
    reads the rotation off it as a 3x3 matrix (a rotation matrix IS exactly
    [x|y|z-axis-image] as columns)."""
    azim, elev = np.radians(azim_deg), np.radians(elev_deg)
    direction = np.array([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim),
                           np.sin(elev)])
    world_up = np.array([0.0, 0.0, 1.0])
    # This cross-product order makes [direction | right | up] a right-handed (det +1) frame --
    # the other order is left-handed and scipy's Rotation.from_matrix rejects it.
    right = np.cross(world_up, direction)
    right /= np.linalg.norm(right)
    up = np.cross(direction, right)
    return Rotation.from_matrix(np.column_stack([direction, right, up]))


def rotate(rotation, dx, dy, sensitivity_deg):
    """Returns the updated rotation for one trackball drag-rotate tick (`dx`/`dy` in pixels
    since the last tick). A free trackball rotation: composes two small rotations -- about the
    CURRENT up axis for a horizontal drag, the CURRENT right axis for a vertical one -- onto the
    existing quaternion, rather than accumulating into a stored azimuth/elevation pair. "up"/
    "right" are read off the rotation as it currently is (not re-pinned to a fixed world axis
    every frame), so there's no pole for elevation to lock up near, and no clamp needed."""
    up = rotation.apply([0.0, 0.0, 1.0])
    right = rotation.apply([0.0, 1.0, 0.0])
    sensitivity = np.radians(sensitivity_deg)
    yaw = Rotation.from_rotvec(-dx * sensitivity * up)
    pitch = Rotation.from_rotvec(-dy * sensitivity * right)
    return pitch * yaw * rotation


def pan(pan_vec, dx, dy, panel_width, panel_height):
    """Returns the updated 2D NDC pan offset for one drag-pan tick (`dx`/`dy` in pixels since
    the last tick) -- applied via a VTK camera's own SetWindowCenter, so NDC rather than a 3D
    world-space offset (which would desync panels of different scale). Needs no per-panel scale
    beyond `panel_width`/`panel_height` since NDC is resolution/scale-independent.

    Sign convention: SetWindowCenter(x, y) moves the image LEFT for x=+1 (half the panel width)
    and DOWN for y=+1 (half the panel height) -- so a rightward drag needs a negative x term, a
    downward drag (screen y already growing downward) a positive y term."""
    return pan_vec + np.array([-dx / (panel_width / 2.0), dy / (panel_height / 2.0)])


def zoom(value, zoom_in, step, lo, hi):
    """Returns the updated zoom scalar for one scroll-wheel notch. `step` > 1 zooms in per
    notch (a camera's own parallel_scale is multiplied by this value's RECIPROCAL elsewhere --
    smaller parallel_scale = smaller visible world height = zoomed in); `zoom_in=False` applies
    the notch in the opposite direction. Clamped to [`lo`, `hi`] so scrolling can't shrink the
    shape to nothing or push it arbitrarily far away."""
    factor = step if zoom_in else 1.0 / step
    return max(lo, min(hi, value * factor))
