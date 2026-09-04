import matplotlib.colors as mcolors
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


class _CullableFace(Poly3DCollection):
    """A single-face Poly3DCollection that hides itself when its outward
    normal points away from the camera, instead of relying on mplot3d's
    painter's-algorithm depth sort (which only has one scalar "depth" per
    face to work with -- a face at a grazing angle to the camera can have
    that scalar put it in front of a face it should be occluded by,
    causing exactly the wrong-face-drawn-on-top glitches this class fixes).

    do_3d_projection() -- which mplot3d calls on every redraw, including
    mid-drag during interactive rotation -- recomputes visibility from the
    CURRENT view angle every time, so it stays correct as the user rotates.

    Only valid for a face on a CLOSED CONVEX solid: there, a face's own
    orientation alone determines whether the solid's far side hides it
    from the camera, and no two visible (camera-facing) faces of a convex
    solid ever overlap in the projection, so no depth sorting is needed
    among them either. Do NOT use this for an open/non-convex net (e.g. a
    mid-fold net) -- a face's own orientation there doesn't determine
    whether some other, unrelated face occludes it.

    Visibility is applied by writing directly to `_facecolor3d` /
    `_edgecolor3d` rather than via the public set_alpha()/set_edgecolor()
    -- Poly3DCollection.set_alpha() only refreshes `_facecolor3d`, not
    `_edgecolor3d` (it updates a *different*, unused `_edgecolors`
    attribute instead, seemingly a matplotlib inconsistency), so the
    do_3d_projection() internals that build the actually-rendered
    `_edgecolors2d` from `_edgecolor3d` never see the alpha-0 update: the
    face fill correctly disappears but its black edge outline stays fully
    opaque and visibly bleeds through the (correctly hidden) face in
    front of it. Setting `_edgecolor3d` directly sidesteps that."""
    def __init__(self, verts, normal, base_alpha, facecolor, edgecolor="k", **kwargs):
        super().__init__(verts, facecolor=facecolor, edgecolor=edgecolor,
                          alpha=base_alpha, **kwargs)
        self._outward_normal = normal
        self._base_alpha = base_alpha
        self._base_facecolor3d = mcolors.to_rgba_array(facecolor, base_alpha)
        self._base_edgecolor3d = mcolors.to_rgba_array(edgecolor, base_alpha)

    def do_3d_projection(self):
        elev, azim = np.radians(self.axes.elev), np.radians(self.axes.azim)
        view_dir = np.array([np.cos(elev) * np.cos(azim),
                              np.cos(elev) * np.sin(azim),
                              np.sin(elev)])
        visible = np.dot(self._outward_normal, view_dir) > 0
        alpha = self._base_alpha if visible else 0.0
        self._facecolor3d = mcolors.to_rgba_array(self._base_facecolor3d, alpha)
        self._edgecolor3d = mcolors.to_rgba_array(self._base_edgecolor3d, alpha)
        return super().do_3d_projection()
