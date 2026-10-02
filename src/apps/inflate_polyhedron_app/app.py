"""
Inflate Polyhedron -- interactive fabric relaxation for stretchy meshes.

    python src/apps/inflate_polyhedron_app/app.py

Nets (data/input/stretchy_nets/*.json or *.poly, see refresh_net_list) are vertex loops --
shared vertex ids ARE the adjacency, so a face pair sharing several edges needs no special
casing (see utils/inflate_polyhedron/stretchy_mesh.py's module docstring). Full pipeline
detail (force model, calibration, convergence) lives in physics.md; UI wiring detail lives
in apps.md -- keep both in sync when changing behavior described here. Summary:

1. On selecting a net, its BASE faces are fan-triangulated (Level 0/1's shared topology,
   see mesh_levels.subdivide_once) and given a fresh random start.
2. "Relax" (Level 0 only) runs pure-spring relaxation to convergence, then promotes straight
   into Level 1's starting position -- a tangled result is possible and left for Inflate to
   resolve. EXPERIMENTAL: while BYPASS_LEVEL_1_INFLATE is True, this promotion continues
   straight on through an extra subdivide into Level 2's own starting position instead, so
   Level 1 is never itself inflated -- see that flag's own comment.
3. "Subdivide" (up to MAX_LEVEL) quarters every triangle; new positions interpolate from the
   current mesh, new rest lengths derive from the original flat geometry so the target shape
   stays fixed across levels.
4. "Inflate" (Level 1+) calibrates a pressure toward the current level's "Target RMS stretch"
   spinner (self.target_rms_vars, defaulted per net load -- see _reset_target_rms_defaults --
   from LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED/_OPEN depending on whether the net is closed,
   independently user-editable after that) via estimate_pressure_for_target_stretch. The
   winning trial's own result IS
   the Inflate outcome (no separate re-run at the found pressure) and is topped up to real
   convergence if the search's own step budget cut it off first. Frames captured during the
   winning trial are replayed at REPLAY_FPS once found; "Steps" advances with the real
   computation, not the replay. See apps.md for the full click/replay/UI sequencing.
5. "Convergence History" records one row per level visited: pressure, steps, stretch stats,
   and a combined "Convergence" cell (`optimality` vs. `gtol`, generic about what optimality
   measures since it just mirrors whatever stretchy_mesh reports).
6. Layout: "Net" panel (flat, matplotlib) plus one 3D panel per level via PyVista/VTK (a real
   GPU depth buffer, needed because meshes here are routinely self-intersecting/non-convex,
   which matplotlib's painter's-algorithm sort can't draw correctly). Every level (0-3) shares
   one camera group (rotation/zoom/pan) -- dragging/panning/zooming one panel moves them all
   together; the Net panel's own zoom/pan are separate again (different rendering stack). See
   apps.md for pan/zoom/camera mechanics.
7. Debug mode ("d" key) adds normal-arrow toggles (face/vertex) for visually checking
   orientation, and a repulsive-force-arrow toggle -- see apps.md.
8. "Auto" runs the whole pipeline unattended (Relax, then Inflate/Subdivide/... to MAX_LEVEL),
   exactly one attempt per level, no retries -- see apps.md/physics.md.
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import glob
import json
import math
import os
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont

import numpy as np
from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import pyvista as pv
import sv_ttk

from common.paths import STRETCHY_NETS_DIR, DATA_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS
from utils.inflate_polyhedron.stretchy_mesh import (
    load_stretchy_mesh, load_stretchy_mesh_edges, relax_once,
    random_initial_positions, mesh_edges, EDGE_LENGTH,
    CONVERGENCE_GTOL, REPULSION_STRENGTH, repulsion_force,
)
from utils.inflate_polyhedron.pre_inflation_relaxer import (
    relax_initial_configuration, level0_periodic_burst_distance,
    relax_initial_configuration_with_orientation_retry,
)
from utils.inflate_polyhedron.multi_trial_inflater import estimate_pressure_for_target_stretch
from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.inflate_polyhedron.plotter_lighting import (
    SMOOTH_SHADING, MATERIAL_AMBIENT, MATERIAL_DIFFUSE, MATERIAL_SPECULAR,
    MATERIAL_SPECULAR_POWER, KEY_LIGHT_POSITION, KEY_LIGHT_INTENSITY, FILL_LIGHT_POSITION,
    FILL_LIGHT_INTENSITY, HEADLIGHT_POSITION, HEADLIGHT_INTENSITY,
    setup_plotter_lighting as _setup_plotter_lighting,
)
from utils.subdivisions.mesh_subdivide import load_fabric_spec
from utils.numeric_entry_validation import is_valid_numeric_partial as _is_valid_numeric_partial
from utils.camera_trackball import (
    initial_rotation as _camera_initial_rotation, rotate as _camera_rotate,
    pan as _camera_pan, zoom as _camera_zoom,
)

from inflate_polyhedron_app.state.session_state import (
    SessionStateModel, LevelStateModel, LevelHistoryRecordModel, LastStatsModel,
)

# Pure logic factored out of this module (2026-09-30 modularization, same spirit as the sibling
# interactive_inflater_app's own `logic/` package) -- aliased to their old underscored names so
# every existing call site below is unchanged.
from inflate_polyhedron_app.logic import net_loading
# `reinflater` aliases utils.inflate_polyhedron.pressure_history_guess (2026-10-01, explicit:
# "make sure they are using shared code whenever possible. shared code should be moved to utils")
# -- was this app's own `logic/reinflater.py`, byte-identical to interactive_inflater_app's own
# copy; moved to utils and imported under the SAME alias so every `reinflater.
# guess_pressure_from_history(...)` call site below is unchanged.
from utils.inflate_polyhedron import pressure_history_guess as reinflater
from inflate_polyhedron_app.logic.coloring import (
    midpoint_color as _midpoint_color,
    darken_color as _darken_color,
    polygon_n_of_group as _polygon_n_of_group,
    face_colors_by_group as _face_colors_by_group,
    group_of_face as _group_of_face,
    random_face_colors,
    random_face_colors_by_group as _random_face_colors_by_group,
)
from inflate_polyhedron_app.logic.geometry import (
    vertex_normals as _vertex_normals,
    bounding_sphere,
    connection_curve_points as _connection_curve_points,
)
from inflate_polyhedron_app.logic.mesh_topology import (
    build_level1_topology as _build_level1_topology,
    open_base_edges as _open_base_edges,
    fan_level_edges as _fan_level_edges,
)

DEFAULT_NET_BASENAME = "cube"

# Window title (_apply_mode_visibility) backronym; ".hippo" was named first (SESSION_FILE_
# EXTENSION, below), this is what it stands for.
APP_TITLE = "HIPPO — Hierarchical Inflatable Phabric Polyhedron Optimizer"

# File > Save/Load's default directory for a whole SESSION -- deliberately not
# STRETCHY_NETS_DIR, since a saved session is a generated artifact, not an input.
SESSION_OUTPUT_DIR = DATA_DIR / "output"
# Still plain JSON content (SessionStateModel.model_dump_json) -- distinct extension so a
# saved session reads as this app's own file type, not an ordinary net .json.
SESSION_FILE_EXTENSION = ".hippo"

# Fine mesh edges drawn thin so subdivision reads as texture, not a bold wireframe competing
# with per-coarse-face coloring.
SUBDIVISION_EDGE_WIDTH = 0.5


# Lighting/shading for every "Level N"/viewer-quadrant face actor -- moved to
# utils.inflate_polyhedron.plotter_lighting (2026-10-01, explicit: "make sure they are using
# shared code whenever possible. shared code should be moved to utils") since it was identical,
# including the entire tuning-history comment, to interactive_inflater_app's own copy; see that
# module's own docstring for the full tuning history (light-repositioning fix, flat-shading
# change, every brightness retune). Imported at the top of this file under the same names this
# file's own call sites already use, so nothing below needed to change.

# Net panel's own bezier connection curves (interactive_builder_app's gluing between two
# faces' edges), shown read-only for context -- solid white for contrast against every
# per-face color, drawn above every face patch/subdivision overlay so it always reads on top.
CONNECTION_CURVE_COLOR = "white"
CONNECTION_CURVE_WIDTH = 1.0
CONNECTION_CURVE_ZORDER = 5

# Convergence History's "running" row tag -- own dedicated bright color, not
# STATUS_COLORS["warn"] (tuned for warning text elsewhere, too muddy for a row highlight).
RUNNING_ROW_COLOR = "#e0b400"

# Every "Level N" panel renders via PyVista/VTK, not matplotlib (see _build_level_pv_panel)
# -- a real GPU depth buffer, needed because meshes here are routinely self-intersecting/
# non-convex (mid-relax, mid-inflate, or Level 0's own random-start), which neither
# mplot3d's painter's-algorithm depth sort nor a convexity-only culling approach can draw
# correctly. Pixel size matches the Net panel's own matplotlib figsize*dpi so every panel is
# the same size as its neighbors.
NET_PANEL_SIZE = (320, 450)
# All "Level N" panels are the same width. `_level_panel_size(level)` returns the right
# (width, height) pair -- kept as a per-level lookup (not a bare constant) in case that
# ever needs to differ again.
LEVEL_PANEL_HEIGHT = 450
LEVEL_PANEL_WIDTH_LEVEL_0 = 320
LEVEL_PANEL_WIDTH_LEVELS_1_3 = 320


def _level_panel_size(level):
    """(width, height) for `level`'s own panel -- see LEVEL_PANEL_WIDTH_LEVEL_0/_LEVELS_1_3."""
    width = LEVEL_PANEL_WIDTH_LEVEL_0 if level == 0 else LEVEL_PANEL_WIDTH_LEVELS_1_3
    return (width, LEVEL_PANEL_HEIGHT)


# Fraction of the panel the shape's own bounding box fills at zoom=1.0 (1.0 would touch the
# panel edge exactly). Level 0 and Levels 1-3 both fill the same 90% of their own
# (now equally-sized) panels.
LEVEL_ZOOM_FILL_LEVEL_0 = 0.9
LEVEL_ZOOM_FILL_LEVELS_1_3 = 0.90


def _level_zoom_fill(level):
    """LEVEL_ZOOM_FILL_LEVEL_0 for level 0, LEVEL_ZOOM_FILL_LEVELS_1_3 for every other level."""
    return LEVEL_ZOOM_FILL_LEVEL_0 if level == 0 else LEVEL_ZOOM_FILL_LEVELS_1_3
# Initial camera angle -- arbitrary, a reasonable non-axis-aligned starting view (close to
# mplot3d's own default elev=30/azim=-60). Used once to build the initial quaternion
# (_initial_level_rotation) -- nothing decomposes back into separate angles afterward, which
# is what avoids gimbal lock.
LEVEL_DEFAULT_ELEV = 30.0
LEVEL_DEFAULT_AZIM = -60.0
# Degrees of camera rotation per pixel of click-drag -- tuned by feel.
LEVEL_DRAG_SENSITIVITY = 0.5
# Zoom multiplier per mouse-wheel notch -- >1 zooms in, so camera.parallel_scale is
# multiplied by its RECIPROCAL (smaller parallel_scale = smaller visible world height =
# zoomed in). Clamped to 30%..400% so scrolling can't shrink the shape to nothing or push it
# arbitrarily far away.
LEVEL_ZOOM_STEP = 1.1
LEVEL_ZOOM_MIN = 0.3
LEVEL_ZOOM_MAX = 4.0

# View > Viewer's own drawing area: a 2x2 grid showing all 4 levels AT ONCE (2026-09-30,
# explicit -- "let's split the drawing area into 2x2 and show all 4 views, synced"), not one
# level switched at a time -- all 4 share ONE camera (rotation/zoom/pan), each auto-fit to its
# own current bounding box, exactly like Inflater's own "Level N" panels. Reuses
# LEVEL_DRAG_SENSITIVITY/LEVEL_ZOOM_STEP/_MIN/_MAX/LEVEL_ZOOM_FILL_LEVELS_1_3 for identical
# mouse feel. VIEWER_WINDOW_GEOMETRY is the whole window's size while Viewer mode is active --
# SQUARE ("View mode should be a square window"), unlike Inflater's own wide layout; a little
# taller than wide to leave room for the position-counter margin and status strip below the
# grid.
VIEWER_SUBPANEL_SIZE = (360, 360)
VIEWER_WINDOW_GEOMETRY = "820x900"

# A visible frame around each quadrant's own drawing area (2026-09-30, explicit) -- a plain
# flat border, not a 3D bevel, so highlightthickness/highlightbackground on the image Label
# itself rather than relief/bd.
VIEWER_OUTLINE_COLOR = PLOT_THEME["fg"]
VIEWER_OUTLINE_WIDTH = 2

# Same idea for the Net panel's own mouse-wheel zoom (_on_net_scroll) -- separate state
# (self.net_zoom) since the Net panel is matplotlib, not a PyVista camera: scales the
# half-extent _draw_target_faces derives from the flat layout's bounding box. NET_ZOOM_MAX
# is higher than the level panels' since the Net panel's bounding box includes every
# connection's bezier curve (see _draw_target_faces), which can sweep well past the faces.
NET_ZOOM_STEP = 1.1
NET_ZOOM_MIN = 0.3
NET_ZOOM_MAX = 8.0

# Overall UI text size multiplier, applied once at startup to every named Tk/ttk font
# (_scale_ui_fonts) so the whole app's text grows together.
UI_FONT_SCALE = 1.3

# Every panel's title ("Net", "Level N") is a plain Tkinter Label above its image, not text
# drawn inside the rendered scene (which a PyVista panel would clip against its own edge).
# Font can't be a plain module-level (family, size) tuple naming a Tk *named* font
# ("TkDefaultFont") -- Tk takes the name literally as a nonexistent family and silently
# falls back to Arial. Computed instead as self.LEVEL_TITLE_FONT at startup (_init_ui_fonts)
# from "Choose a net"'s own actual rendered font, so every title/message label genuinely
# matches it in family and size.

# Bottom-of-panel status message ("Computing...", "Replay frame N / M") is LEFT-justified
# (anchor=tk.W) with a per-message computed padx (_set_level_message, via a real tkfont.Font)
# rather than tk.CENTER or one fixed pad -- true centering re-anchors the whole string on
# every update (dot added, frame count digit count changes), and a single fixed pad tuned
# for one message length reads off-center for another. self.LEVEL_MESSAGE_FONT ==
# self.LEVEL_TITLE_FONT (see _init_ui_fonts).

# Shown on the Pressure readout before "Auto"/"Inflate" has ever calibrated one.
DEFAULT_PRESSURE = 3.0

DEFAULT_STEPS = 10

# This app's own default for the "Tolerance" spinner (self.tolerance_var) -- the `gtol`
# every relax_once/relax_initial_configuration/estimate_pressure_for_target_stretch call
# actually uses (self._current_gtol), distinct from stretchy_mesh.CONVERGENCE_GTOL (that
# module's own hardcoded default for a caller that passes no gtol at all). Tightened over
# time alongside stretchy_mesh's periodic (not per-step) convergence checking, which makes a
# tighter per-step-equivalent rate affordable.
DEFAULT_TOLERANCE = 1e-4

# Default value for each level's own "Target RMS stretch" spinner (self.target_rms_vars[level]
# -- one independent tk.DoubleVar per level), applied fresh on every net load
# (on_select_net -> _reset_target_rms_defaults). No entry for Level 0 -- it has no target RMS
# stretch at all (relax_initial_configuration is pure springs, not calibrated toward a target).
#
# Depends on whether the WHOLE net is closed (no free/open edge anywhere -- see
# _open_base_edges): a fully closed net (e.g. any Platonic solid) can take a higher target
# comfortably; an open one (any free rim edge left unglued) defaults lower. Uniform across
# levels 1-3 within each case.
LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED = {1: 10.0, 2: 10.0, 3: 10.0}
LEVEL_DEFAULT_TARGET_RMS_PCT_OPEN = {1: 5.0, 2: 5.0, 3: 5.0}




# Debug mode's "Show normals" toggle (_draw_level_panel) draws each triangle's own outward
# normal from its centroid, scaled to that triangle's own mean edge length -- distinct from
# every FACE_COLORS entry and PLOT_THEME's fg/edge color so it reads clearly against either.
NORMAL_COLOR = "yellow"
# "Show vertex normals" toggle's own color -- distinct from NORMAL_COLOR so a face normal and
# a vertex normal on the same panel (both toggles can be on at once) are never confused.
VERTEX_NORMAL_COLOR = "cyan"
# Normal segment length as a fraction of the triangle's (or vertex's own incident) mean edge
# length -- a full edge length reads too long against a dense/fine mesh. Shared by both
# "Show face normals" and "Show vertex normals".
NORMAL_LENGTH_FRACTION = 0.5

# "Show repulsive forces" toggle's own color -- distinct from both normal colors so all three
# debug overlays stay visually distinct when several are on at once.
REPULSION_FORCE_COLOR = "magenta"

# Hard stop for "iterate until convergence" mode in case a mesh/pressure combination never
# reaches the current tolerance -- without this, a plateauing run would loop forever instead
# of settling for "as far as it got". Also the budget Auto gives its single non-converged
# attempt per level (no retry loop -- see physics.md's Auto section): recalibrating Inflate's
# pressure from scratch on retry was wasted work when the mesh just needed more time at the
# SAME pressure. Purely bounds a single uninterrupted relax_once/relax_initial_configuration
# call's own max_nfev in "iterate until convergence" mode (no app-side chunking anymore).
INFLATE_SAFETY_STEP_CAP = 50000

# EXPERIMENTAL (2026-10-01, explicit: "let's see if level 1 is even necessary... bypass level 1
# entirely, pass the result of level 0 directly to level 2") -- when True, _finish_relax_report's
# own promotion from a converged Level 0 immediately subdivides again (Level 1 -> 2) before the
# user, or Auto, ever gets a chance to Inflate at Level 1: Level 1's own mesh still exists for one
# instant (frozen into self.level_snapshots, same as any other level Subdivide leaves behind) but
# is never itself pressure-relaxed. Level 2 becomes the first level a real (pressure-calibrated)
# Inflate ever runs at, its starting positions interpolated directly from Level 0's own relaxed
# result via TWO interpolation-only subdivide_once calls (fan-triangulate, then quarter) rather
# than one. False restores the normal Level 0 -> 1 -> 2 -> 3 pipeline (2026-10-01, explicit:
# "add back level 1" -- tried, reverted the same day).
BYPASS_LEVEL_1_INFLATE = False


def _initial_level_rotation():
    """Builds the starting camera quaternion reproducing LEVEL_DEFAULT_AZIM/ELEV -- the only
    place spherical angles are converted into a rotation; every update after this
    (_on_level_motion) works with the quaternion directly and never decomposes it back into
    angles, which is what avoids gimbal lock. Shared by both Inflater's own Level-N camera and
    Viewer's own per-file camera (same default angle for both). Delegates to utils.
    camera_trackball.initial_rotation (2026-10-01, explicit: "make sure they are using shared
    code whenever possible. shared code should be moved to utils") -- that same pure math was
    duplicated a THIRD time in interactive_inflater_app's own CameraController."""
    return _camera_initial_rotation(LEVEL_DEFAULT_AZIM, LEVEL_DEFAULT_ELEV)


class ViewerPane:
    """View > Viewer -- a second, self-contained top-level pane toggled by the View menu (see
    InflatePolyhedronApp._on_view_mode_changed) -- browses every .hippo file in
    SESSION_OUTPUT_DIR, letting a user step through them and adjust each one's own shared camera
    (level_rotation/level_zoom/level_pan -- the SAME fields Inflater mode itself reads/writes,
    via the same SessionStateModel), without re-solving anything. Entirely separate state from
    InflaterPane's own (every attribute/method here prefixed _viewer_) -- switching modes never
    disturbs whatever Inflater mode currently has loaded, and vice versa.

    Shows all 4 levels AT ONCE in a 2x2 grid, synced to ONE shared camera per file (each
    quadrant auto-fits its own current bounding box, same as InflaterPane's own "Level N"
    panels) -- mouse/camera math mirrors InflaterPane's own level-panel drag/pan/scroll
    handlers, reusing the shared LEVEL_* constants and _initial_level_rotation.

    2026-09-30 modularization: carved out of InflatePolyhedronApp (which used to hold both
    Inflater- and Viewer-mode code in one flat class) into its own class, same attribute/method
    names as before, unchanged -- see apps.md's own inflate_polyhedron_app section.
    """

    def __init__(self, root, view_mode_var, app):
        """Builds self._viewer_frame (constructed but NOT packed -- Inflater is the default
        view; InflatePolyhedronApp._on_view_mode_changed shows/hides it) and all its own
        widgets/state. `view_mode_var` is the SAME tk.StringVar InflatePolyhedronApp's own View
        menu radiobuttons drive -- needed here too since the Left/Right/A/D keyboard bindings
        below are global (root.bind_all), so _on_viewer_prev_clicked/_on_viewer_next_clicked
        must be able to check it's actually Viewer mode that's showing before acting, even
        though Inflater mode itself never binds these keys. `app` is the owning
        InflatePolyhedronApp instance (2026-10-01, explicit: "colour changes should apply in
        Viewer mode as well, and they should factor into the undo/redo stack") -- the Colour
        menu itself (self.color_mode_var/_colour_menu/_update_colour_menu_state) lives on `app`,
        not here, since it's ONE menu shared by both views; ViewerPane needs to read/drive it
        while Viewer mode is active (see _viewer_show_current's own resync, and
        _on_viewer_color_mode_changed/_on_viewer_randomize_colors_clicked, called from `app`'s
        own Colour-menu command handlers whenever view_mode_var is "viewer")."""
        self.root = root
        self.view_mode_var = view_mode_var
        self.app = app
        self._viewer_paths = []
        self._viewer_index = 0
        self._viewer_sessions = {}           # path -> SessionStateModel
        self._viewer_cameras = {}            # path -> {"rotation", "zoom", "pan"}
        self._viewer_saved_cameras = {}      # path -> same shape, the ON-DISK values (dirty-check)
        # path -> {"color_mode", "face_colors"}, the ON-DISK values (dirty-check) -- same
        # lifecycle/purpose as _viewer_saved_cameras, just for Colour-menu state (2026-10-01,
        # explicit, see __init__'s own docstring).
        self._viewer_saved_colors = {}
        self._viewer_dirty_paths = set()
        self._viewer_dragging = False
        self._viewer_panning = False
        self._viewer_last_xy = None
        # Undo/redo for camera adjustments (2026-10-01, explicit: "allow undo/redo in Viewer
        # mode for the current model you're adjusting. if you switch to a new model, then the
        # undo stack resets") -- camera (rotation/pan/zoom) is the only thing Viewer mode lets
        # the user change. A SINGLE stack, not one per file -- switching to a different file
        # (_on_viewer_prev_clicked/_on_viewer_next_clicked, and a file-changing _viewer_rescan)
        # clears both via _viewer_reset_undo_stack, per the user's own framing ("for the current
        # model"). Each entry is a camera-state snapshot from BEFORE one change: one whole
        # drag/pan gesture collapses to a single undo step (see _viewer_commit_gesture_undo),
        # not one per motion tick; a scroll zoom or the middle-click pan-reset each push their
        # own single step, since those are already one discrete action.
        self._viewer_undo_stack = []
        self._viewer_redo_stack = []
        self._viewer_gesture_start_state = None
        # Per-QUADRANT (level) bounding-box auto-fit -- the camera itself (rotation/zoom/pan)
        # is per-FILE, shared across all 4 (see self._viewer_cameras).
        self._viewer_plotters = {}
        self._viewer_image_labels = {}
        self._viewer_photos = {}             # keeps PhotoImage refs alive -- Tk drops a GC'd one
        self._viewer_centers = {}
        self._viewer_halves = {}

        self._viewer_frame = ttk.Frame(self.root)

        # No Save button, no Level buttons/toolbar (2026-09-30, explicit) -- saving now only
        # happens via a prompt covering every dirty file at once, when leaving Viewer mode or
        # quitting (see _on_view_mode_changed/_on_quit_request); Ctrl+S (_on_control_s) still
        # saves the current file on demand. All 4 levels show at once now, so there's nothing
        # left to pick with a Level button either.
        body = ttk.Frame(self._viewer_frame)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(14, 0))

        grid_frame = ttk.Frame(body)
        grid_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        grid_frame.grid_rowconfigure(0, weight=1)
        grid_frame.grid_rowconfigure(1, weight=1)
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        for level in range(MAX_LEVEL + 1):
            quad = ttk.Frame(grid_frame)
            quad.grid(row=level // 2, column=level % 2, sticky="nsew", padx=3, pady=3)
            ttk.Label(quad, text=f"Level {level}", anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
            # A visible flat outline around the drawing area itself (2026-09-30, explicit) --
            # highlightthickness/highlightbackground draws a plain border without the 3D-bevel
            # look relief/bd would give.
            image_label = tk.Label(
                quad, bg=PLOT_THEME["bg"], bd=0, highlightthickness=VIEWER_OUTLINE_WIDTH,
                highlightbackground=VIEWER_OUTLINE_COLOR, highlightcolor=VIEWER_OUTLINE_COLOR)
            image_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            image_label.bind("<ButtonPress-1>", self._on_viewer_drag_start)
            image_label.bind("<B1-Motion>", self._on_viewer_drag_motion)
            image_label.bind("<ButtonRelease-1>", self._on_viewer_drag_end)
            image_label.bind("<ButtonPress-3>", self._on_viewer_pan_start)
            image_label.bind("<B3-Motion>", self._on_viewer_pan_motion)
            image_label.bind("<ButtonRelease-3>", self._on_viewer_pan_end)
            image_label.bind("<Button-2>", self._on_viewer_pan_reset)
            image_label.bind("<MouseWheel>", self._on_viewer_scroll)
            image_label.bind("<Button-4>", self._on_viewer_scroll)
            image_label.bind("<Button-5>", self._on_viewer_scroll)
            self._viewer_image_labels[level] = image_label
            self._viewer_photos[level] = None
            plotter = pv.Plotter(off_screen=True, window_size=list(VIEWER_SUBPANEL_SIZE))
            plotter.set_background(PLOT_THEME["bg"])
            _setup_plotter_lighting(plotter)
            self._viewer_plotters[level] = plotter
            self._viewer_centers[level] = np.zeros(3)
            self._viewer_halves[level] = 1.0

        # A small margin strip directly below the drawing area (2026-09-30, explicit) holding
        # just the "m / n" file-position counter -- no on-screen Prev/Next arrows anymore
        # (2026-09-30, explicit -- removed) and no file-name message either (removed the same
        # day -- the window title already shows the current file's own name); navigation is
        # keyboard-only (Left/Right, A/D -- see _on_key_d and the bind_all calls below).
        margin = ttk.Frame(self._viewer_frame)
        margin.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(6, 14))
        self._viewer_position_label = ttk.Label(margin, text="", anchor=tk.CENTER)
        self._viewer_position_label.pack(side=tk.TOP, fill=tk.X)

        # bind_all (fires regardless of which widget has focus, same rationale as "d"/Ctrl+S
        # above) -- Inflater mode itself has no OTHER use for arrow/A/D keys, so this never
        # collides with anything there except Run > Debug All's own Left/Right-arrow "go back"/
        # "skip ahead or continue" behavior (2026-10-01, explicit -- _on_debug_all_left_key/
        # _on_debug_all_right_key), tried FIRST on every "<Left>"/"<Right>" press: both are a
        # no-op whenever Debug All isn't actually running right now (including the whole time
        # Viewer mode is showing), so falling through to _on_viewer_prev_clicked/_on_viewer_
        # next_clicked afterward is always safe. "d"/"D" dispatch through _on_key_d instead of
        # binding directly here, since lowercase "d" is ALSO Inflater mode's own debug-mode
        # toggle (see __init__).
        def _on_left_key(_event):
            self.app._on_debug_all_left_key()
            self._on_viewer_prev_clicked()

        def _on_right_key(_event):
            self.app._on_debug_all_right_key()
            self._on_viewer_next_clicked()

        self.root.bind_all("<Left>", _on_left_key)
        self.root.bind_all("<Right>", _on_right_key)
        self.root.bind_all("<KeyPress-a>", lambda e: self._on_viewer_prev_clicked())
        self.root.bind_all("<KeyPress-A>", lambda e: self._on_viewer_prev_clicked())
        self.root.bind_all("<KeyPress-D>", lambda e: self._on_viewer_next_clicked())
        # Ctrl+Z/Ctrl+Y themselves are now bound centrally by InflatePolyhedronApp (2026-10-01,
        # explicit: "put Undo/Redo in an Edit menu [for polyhedron_inflater, in both views]")
        # -- dispatching to _on_viewer_undo/_on_viewer_redo here or to this app's OWN Inflater-
        # view undo/redo, by view_mode_var, from ONE place (_on_edit_undo/_on_edit_redo) rather
        # than two separate bind_all calls racing for the same key (Tk's bind_all only keeps the
        # LAST binding registered for a given sequence+tag, so two independent bind_all calls
        # for "<Control-z>" would silently fight over who actually fires).

    def _viewer_rescan(self):
        """Re-globs SESSION_OUTPUT_DIR for *.hippo files -- called every time Viewer mode is
        entered (_on_view_mode_changed), not just once. Keeps every already-cached session/
        camera exactly as it was (only the path LIST is refreshed), so an in-progress, unsaved
        edit made earlier in Viewer mode is never lost by a rescan. Tries to keep showing
        whichever file was on screen before, by path; falls back to index 0 if that file is
        gone (e.g. deleted from disk since)."""
        current_path = self._viewer_current_path()
        self._viewer_paths = sorted(SESSION_OUTPUT_DIR.glob(f"*{SESSION_FILE_EXTENSION}"))
        self._viewer_index = (self._viewer_paths.index(current_path)
                               if current_path in self._viewer_paths else 0)
        if self._viewer_current_path() != current_path:
            self._viewer_reset_undo_stack()
        if not self._viewer_paths:
            self._viewer_position_label.config(text="")
            for level in range(MAX_LEVEL + 1):
                self._viewer_image_labels[level].config(image="")
            self._update_viewer_title()
            return
        self._viewer_show_current()

    def _on_viewer_prev_clicked(self):
        if self.view_mode_var.get() != "viewer" or len(self._viewer_paths) < 2:
            return
        self._viewer_index = (self._viewer_index - 1) % len(self._viewer_paths)
        self._viewer_reset_undo_stack()
        self._viewer_show_current()

    def _on_viewer_next_clicked(self):
        if self.view_mode_var.get() != "viewer" or len(self._viewer_paths) < 2:
            return
        self._viewer_index = (self._viewer_index + 1) % len(self._viewer_paths)
        self._viewer_reset_undo_stack()
        self._viewer_show_current()

    def _viewer_reset_undo_stack(self):
        """Clears camera/Colour undo/redo history -- called whenever the file ON SCREEN
        changes, so undo never reaches back into a DIFFERENT model's adjustments (2026-10-01,
        explicit: "if you switch to a new model, then the undo stack resets")."""
        self._viewer_undo_stack = []
        self._viewer_redo_stack = []
        self._viewer_gesture_start_state = None

    def _viewer_current_path(self):
        return self._viewer_paths[self._viewer_index] if self._viewer_paths else None

    def _viewer_get_session(self, path):
        """Loads and caches `path`'s own SessionStateModel plus its starting camera state --
        the ON-DISK camera (level_rotation/zoom/pan, or the default if the file predates them)
        is kept separately (self._viewer_saved_cameras) so later edits can be compared against
        it to know whether this file is actually dirty."""
        if path not in self._viewer_sessions:
            with open(path) as f:
                session = SessionStateModel.model_validate_json(f.read())
            self._viewer_sessions[path] = session
            rotation = (Rotation.from_quat(session.level_rotation)
                        if session.level_rotation is not None
                        else _initial_level_rotation())
            camera = {"rotation": rotation, "zoom": session.level_zoom,
                      "pan": np.array(session.level_pan, dtype=float)}
            self._viewer_cameras[path] = camera
            self._viewer_saved_cameras[path] = {"rotation": rotation, "zoom": camera["zoom"],
                                                  "pan": camera["pan"].copy()}
            # ON-DISK Colour-menu state (2026-10-01, explicit) -- same dirty-check lifecycle as
            # _viewer_saved_cameras above.
            self._viewer_saved_colors[path] = {
                "color_mode": session.color_mode,
                "face_colors": (list(session.face_colors)
                                 if session.face_colors is not None else None),
            }
        return self._viewer_sessions[path]

    def _viewer_show_current(self):
        """Builds every quadrant's own scene (one per level, 0..MAX_LEVEL -- see
        _viewer_draw_level_panel) and renders them all against the file's own shared camera.
        A level this file never reached draws as a blank quadrant (faces=None), rather than
        picking a fallback level the way the old single-panel viewer did -- showing all 4 at
        once means there's no single "current level" to substitute."""
        path = self._viewer_current_path()
        if path is None:
            return
        session = self._viewer_get_session(path)
        self._update_viewer_title()
        self._viewer_position_label.config(
            text=f"{self._viewer_index + 1} / {len(self._viewer_paths)}")
        # Resyncs the (shared) Colour menu's own display to THIS file's mode (2026-10-01,
        # explicit: "colour changes should apply in Viewer mode as well, and they should factor
        # into the undo/redo stack") -- the menu's radiobuttons are bound to self.app.
        # color_mode_var, Inflater mode's own live state; while Viewer mode is active that same
        # variable instead DISPLAYS/controls whichever file is on screen (see
        # _on_viewer_color_mode_changed), so it needs resyncing on every navigation. self.app.
        # _last_color_mode is reused the same way (undo's own "before" tracking, see
        # _on_viewer_color_mode_changed's own docstring) -- never read by both views at once,
        # since only one is ever showing. _on_view_mode_changed is what saves/restores Inflater
        # mode's own values across a trip into Viewer mode.
        self.app.color_mode_var.set(session.color_mode)
        self.app._last_color_mode = session.color_mode
        self.app._update_colour_menu_state()
        # Polygon-specific mode's own per-base-face color, by ORIGINAL polygon side count
        # (2026-10-01, explicit bug report: "Polygon-specific colouring is wrong. It should use
        # the colour scheme in interactive_inflater..." -- same fix, and the SAME pure
        # _face_colors_by_group Inflater mode's own _apply_color_mode uses, just computed once
        # per file here instead of once per Colour-menu change) -- reused by every level's own
        # _viewer_draw_level_panel call below (only Multi-colour's saved face_colors differ
        # per-level, since that's keyed straight by base_face already).
        net_file = session.net_file or {}
        source_polygon_id = net_file.get("source_polygon_id")
        n_by_group = _polygon_n_of_group(source_polygon_id, net_file.get("net_layout") or [])
        # The flat per-base-face `colors` list (face_colors_by_group's FIRST return value), NOT
        # `color_by_group` (2026-10-01, bug fix: "Polygon-specific colours are not working in
        # Viewer view") -- `color_by_group` is keyed by GROUP id, which is `source_polygon_id[i]`
        # (an arbitrary 2D-builder shape id) whenever that's given, not the plain positional
        # base-face index `_viewer_draw_level_panel`'s own `base_face` (from `face_of_fine`)
        # actually is -- looking it up directly as `color_by_group[base_face]` silently missed
        # for most faces (shape ids essentially never equal their own positional index) and fell
        # through to the arbitrary FACE_COLORS-modulo fallback instead. `colors[i]` is already
        # the right color for base face `i` directly, no group-id translation needed.
        polygon_colors, _color_by_group, _group_of_face = _face_colors_by_group(
            session.base_faces, source_polygon_id, n_by_group)
        for level in range(MAX_LEVEL + 1):
            level_state = session.levels.get(level)
            if level_state is not None:
                faces, positions, face_of_fine, _edge_length = level_state.to_mesh()
            else:
                faces = positions = face_of_fine = None
            self._viewer_draw_level_panel(level, faces, positions, face_of_fine,
                                           session.color_mode, session.face_colors,
                                           polygon_colors)
        self._viewer_render_all()

    # ---- rendering ----

    def _viewer_draw_level_panel(self, level, faces, positions, face_of_fine,
                                  color_mode="polygon", face_colors=None,
                                  polygon_colors=None):
        """Builds ONE quadrant's own PyVista scene -- mesh geometry only, called once per file
        (on navigation), not per camera tick -- and recomputes that quadrant's own center/half
        (bounding sphere), exactly like Inflater's own _draw_level_panel/_level_center/
        _level_half. `faces`/`positions`/`face_of_fine` are None when this file never reached
        `level` -- blanks the quadrant rather than erroring. `polygon_colors` (a flat list,
        `polygon_colors[base_face]`, from _viewer_show_current's own one-per-file
        _face_colors_by_group call) is Polygon-specific mode's own color -- computed once per
        file, not per level, since it only depends on the file's base_faces/source_polygon_id,
        never on which level is being drawn."""
        plotter = self._viewer_plotters[level]
        plotter.clear()
        _setup_plotter_lighting(plotter)
        if faces is None:
            self._viewer_centers[level] = np.zeros(3)
            self._viewer_halves[level] = 1.0
            self._viewer_image_labels[level].config(image="")
            self._viewer_photos[level] = None
            return
        vertex_ids = sorted(positions)
        idx = {v: i for i, v in enumerate(vertex_ids)}
        points = np.array([positions[v] for v in vertex_ids])

        # Multi-colour shows the saved session's own EXACT per-base-face face_colors (2026-10-01,
        # explicit: "these colours persist via Save/Load, even into different app, if the target
        # app supports it") -- those colors are random and only meaningful as whatever was
        # actually saved, so there's nothing to re-derive. Polygon-specific uses `polygon_colors`
        # (a flat list, POLYGON_COLORS by original side count -- same scheme Inflater mode's own
        # _apply_color_mode uses), indexed directly by `base_face` (a plain positional index into
        # base_faces/face_of_fine) -- falling back to a plain base_face-modulo FACE_COLORS cycle
        # only if that list is somehow too short (shouldn't normally happen -- defensive, same as
        # every other fallback here).
        use_saved_colors = (color_mode == "multi" and face_colors is not None)
        for base_face in sorted(set(face_of_fine)):
            if use_saved_colors and base_face < len(face_colors):
                face_color = face_colors[base_face]
            elif polygon_colors is not None and base_face < len(polygon_colors):
                face_color = polygon_colors[base_face]
            else:
                face_color = FACE_COLORS[base_face % len(FACE_COLORS)]
            group_faces = [f for f, bf in zip(faces, face_of_fine) if bf == base_face]
            if not group_faces:
                continue
            face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
            mesh = pv.PolyData(points, face_conn)
            plotter.add_mesh(mesh, color=face_color, show_edges=True,
                              edge_color=_midpoint_color("white", face_color),
                              line_width=SUBDIVISION_EDGE_WIDTH,
                              backface_params=dict(color=_darken_color(face_color)),
                              smooth_shading=SMOOTH_SHADING, ambient=MATERIAL_AMBIENT,
                              diffuse=MATERIAL_DIFFUSE, specular=MATERIAL_SPECULAR,
                              specular_power=MATERIAL_SPECULAR_POWER)

        self._viewer_centers[level], self._viewer_halves[level] = bounding_sphere(points)

    def _viewer_render_all(self):
        for level in range(MAX_LEVEL + 1):
            self._viewer_render_level_camera(level)

    def _viewer_render_level_camera(self, level):
        """Positions quadrant `level`'s own orthographic camera from the file's own SHARED
        camera state (rotation/zoom/pan) but THIS quadrant's own center/half, and blits the
        result into its own image Label -- identical approach to
        InflatePolyhedronApp._capture_level_image, just across 4 small plotters sharing one
        camera instead of 4 independent ones. A quadrant with nothing drawn (blanked by
        _viewer_draw_level_panel) is simply skipped -- its Label already shows no image."""
        path = self._viewer_current_path()
        if path is None:
            return
        session = self._viewer_sessions.get(path)
        if session is not None and level not in session.levels:
            return
        cam = self._viewer_cameras[path]
        direction = cam["rotation"].apply([1.0, 0.0, 0.0])
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        center, half = self._viewer_centers[level], self._viewer_halves[level]
        distance = half * 4
        plotter = self._viewer_plotters[level]
        camera = plotter.camera
        camera.parallel_projection = True
        camera.focal_point = tuple(center)
        camera.position = tuple(center + direction * distance)
        camera.up = tuple(up)
        panel_width, panel_height = VIEWER_SUBPANEL_SIZE
        camera.parallel_scale = (half * max(1.0, panel_height / panel_width)
                                  / LEVEL_ZOOM_FILL_LEVELS_1_3 / cam["zoom"])
        camera.SetWindowCenter(*cam["pan"])
        plotter.reset_camera_clipping_range()
        plotter.render()
        image = Image.fromarray(plotter.screenshot(return_img=True))
        photo = ImageTk.PhotoImage(image)
        self._viewer_photos[level] = photo
        self._viewer_image_labels[level].config(image=photo)

    # ---- mouse: rotate / pan / zoom ----

    def _viewer_mark_dirty(self):
        path = self._viewer_current_path()
        if path is None:
            return
        cam = self._viewer_cameras[path]
        saved_cam = self._viewer_saved_cameras[path]
        camera_changed = (cam["zoom"] != saved_cam["zoom"]
                           or not np.allclose(cam["pan"], saved_cam["pan"])
                           or not np.allclose(cam["rotation"].as_quat(),
                                               saved_cam["rotation"].as_quat()))
        # Colour-menu state dirty-check (2026-10-01, explicit: "colour changes should apply in
        # Viewer mode as well, and they should factor into the undo/redo stack") -- same
        # saved-vs-live comparison idea as the camera check above, just against
        # _viewer_saved_colors instead of _viewer_saved_cameras.
        session = self._viewer_sessions[path]
        saved_colors = self._viewer_saved_colors[path]
        colors_changed = (session.color_mode != saved_colors["color_mode"]
                           or session.face_colors != saved_colors["face_colors"])
        if camera_changed or colors_changed:
            self._viewer_dirty_paths.add(path)
        else:
            self._viewer_dirty_paths.discard(path)
        self._update_viewer_title()

    @staticmethod
    def _viewer_camera_snapshot(cam):
        return {"rotation": cam["rotation"], "zoom": cam["zoom"], "pan": cam["pan"].copy()}

    def _viewer_apply_camera_snapshot(self, snapshot):
        path = self._viewer_current_path()
        if path is None:
            return
        cam = self._viewer_cameras[path]
        cam["rotation"] = snapshot["rotation"]
        cam["zoom"] = snapshot["zoom"]
        cam["pan"] = snapshot["pan"].copy()

    def _viewer_state_snapshot(self, path):
        """One Viewer undo/redo entry for `path`: its camera (_viewer_camera_snapshot) PLUS its
        Colour-menu state (color_mode/face_colors) -- extended from camera-only (2026-10-01,
        explicit: "colour changes should apply in Viewer mode as well, and they should factor
        into the undo/redo stack") the same way InflatePolyhedronApp's own _inflater_snapshot
        bundles Colour state alongside its camera. face_colors is a plain shallow list copy --
        every entry's a hex-string color, nothing nested."""
        session = self._viewer_sessions[path]
        return {
            "camera": self._viewer_camera_snapshot(self._viewer_cameras[path]),
            "color_mode": session.color_mode,
            "face_colors": (list(session.face_colors)
                             if session.face_colors is not None else None),
        }

    def _viewer_apply_state_snapshot(self, snapshot):
        """Inverse of _viewer_state_snapshot -- restores the CURRENT file's camera AND Colour-
        menu state, and keeps self.app's own color_mode_var/_last_color_mode (the Colour menu's
        live display while Viewer mode is active -- see _viewer_show_current's own resync)
        showing the result."""
        path = self._viewer_current_path()
        if path is None:
            return
        self._viewer_apply_camera_snapshot(snapshot["camera"])
        session = self._viewer_sessions[path]
        session.color_mode = snapshot["color_mode"]
        session.face_colors = (list(snapshot["face_colors"])
                                if snapshot["face_colors"] is not None else None)
        self.app.color_mode_var.set(snapshot["color_mode"])
        self.app._last_color_mode = snapshot["color_mode"]
        self.app._update_colour_menu_state()

    def _viewer_push_undo(self, snapshot):
        self._viewer_undo_stack.append(snapshot)
        self._viewer_redo_stack.clear()

    def _viewer_commit_gesture_undo(self):
        """Pushes ONE undo step for the just-finished drag/pan gesture, captured at its START
        (_on_viewer_drag_start/_on_viewer_pan_start) rather than per motion tick -- and only if
        the camera actually ended up different (a drag/pan gesture never touches Colour state),
        so a click-without-moving leaves no undo entry."""
        path = self._viewer_current_path()
        start = self._viewer_gesture_start_state
        self._viewer_gesture_start_state = None
        if start is None or path is None:
            return
        cam = self._viewer_cameras[path]
        start_cam = start["camera"]
        changed = (cam["zoom"] != start_cam["zoom"]
                   or not np.allclose(cam["pan"], start_cam["pan"])
                   or not np.allclose(cam["rotation"].as_quat(), start_cam["rotation"].as_quat()))
        if changed:
            self._viewer_push_undo(start)

    def _on_viewer_undo(self, event=None):
        if self.view_mode_var.get() != "viewer" or not self._viewer_undo_stack:
            return
        path = self._viewer_current_path()
        if path is None:
            return
        current = self._viewer_state_snapshot(path)
        previous = self._viewer_undo_stack.pop()
        self._viewer_redo_stack.append(current)
        self._viewer_apply_state_snapshot(previous)
        self._viewer_mark_dirty()
        self._viewer_show_current()

    def _on_viewer_redo(self, event=None):
        if self.view_mode_var.get() != "viewer" or not self._viewer_redo_stack:
            return
        path = self._viewer_current_path()
        if path is None:
            return
        current = self._viewer_state_snapshot(path)
        following = self._viewer_redo_stack.pop()
        self._viewer_undo_stack.append(current)
        self._viewer_apply_state_snapshot(following)
        self._viewer_mark_dirty()
        self._viewer_show_current()

    def _on_viewer_drag_start(self, event):
        self._viewer_dragging = True
        self._viewer_last_xy = (event.x, event.y)
        path = self._viewer_current_path()
        self._viewer_gesture_start_state = (
            self._viewer_state_snapshot(path) if path is not None else None)

    def _on_viewer_drag_motion(self, event):
        """Free trackball rotation -- identical math to _on_level_motion (see its own
        docstring), via the shared utils.camera_trackball.rotate."""
        if not self._viewer_dragging or self._viewer_last_xy is None:
            return
        path = self._viewer_current_path()
        if path is None:
            return
        cam = self._viewer_cameras[path]
        last_x, last_y = self._viewer_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        cam["rotation"] = _camera_rotate(cam["rotation"], dx, dy, LEVEL_DRAG_SENSITIVITY)
        self._viewer_last_xy = (event.x, event.y)
        self._viewer_mark_dirty()
        self._viewer_render_all()

    def _on_viewer_drag_end(self, event):
        self._viewer_dragging = False
        self._viewer_last_xy = None
        self._viewer_commit_gesture_undo()

    def _on_viewer_pan_start(self, event):
        self._viewer_panning = True
        self._viewer_last_xy = (event.x, event.y)
        path = self._viewer_current_path()
        self._viewer_gesture_start_state = (
            self._viewer_state_snapshot(path) if path is not None else None)

    def _on_viewer_pan_motion(self, event):
        if not self._viewer_panning or self._viewer_last_xy is None:
            return
        path = self._viewer_current_path()
        if path is None:
            return
        cam = self._viewer_cameras[path]
        last_x, last_y = self._viewer_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        panel_width, panel_height = VIEWER_SUBPANEL_SIZE
        cam["pan"] = _camera_pan(cam["pan"], dx, dy, panel_width, panel_height)
        self._viewer_last_xy = (event.x, event.y)
        self._viewer_mark_dirty()
        self._viewer_render_all()

    def _on_viewer_pan_end(self, event):
        self._viewer_panning = False
        self._viewer_last_xy = None
        self._viewer_commit_gesture_undo()

    def _on_viewer_pan_reset(self, event=None):
        path = self._viewer_current_path()
        if path is None:
            return
        cam = self._viewer_cameras[path]
        self._viewer_push_undo(self._viewer_state_snapshot(path))
        cam["pan"] = np.zeros(2)
        cam["zoom"] = 1.0
        cam["rotation"] = _initial_level_rotation()
        self._viewer_mark_dirty()
        self._viewer_render_all()

    def _on_viewer_scroll(self, event):
        path = self._viewer_current_path()
        if path is None:
            return
        cam = self._viewer_cameras[path]
        self._viewer_push_undo(self._viewer_state_snapshot(path))
        zoom_in = not (getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0)
        cam["zoom"] = _camera_zoom(cam["zoom"], zoom_in, LEVEL_ZOOM_STEP, LEVEL_ZOOM_MIN,
                                    LEVEL_ZOOM_MAX)
        self._viewer_mark_dirty()
        self._viewer_render_all()

    # ---- Colour menu (2026-10-01, explicit: "colour changes should apply in Viewer mode as
    # well, and they should factor into the undo/redo stack") ----

    def _viewer_color_face_edge_ids(self, session):
        """Best-effort face_edge_ids for `session.base_faces`, from `session.net_file` -- used
        to avoid a neighbor-color clash when generating fresh Multi-colour colors (same
        disambiguation InflatePolyhedronApp's own on_select_net uses). None (random_face_colors'
        own base_face_neighbors then falls back to a plain shared-vertex-pair match) whenever
        `net_file` is missing or its own "faces" doesn't line up with `base_faces` (a mismatched
        or legacy net)."""
        net_file = session.net_file or {}
        faces = net_file.get("faces")
        if faces is not None and len(faces) == len(session.base_faces):
            return net_file.get("face_edge_ids")
        return None

    def _viewer_ensure_multi_colors(self, session):
        """Lazily (re)generates `session.face_colors` the FIRST time Multi-colour actually needs
        them for this file (none yet, or a stale list left over from a mismatched base_faces
        length) -- NOT every time Multi-colour is re-selected, same "toggling without Randomize
        never changes colors" rule Inflater mode's own _apply_color_mode follows."""
        if session.face_colors is None or len(session.face_colors) != len(session.base_faces):
            session.face_colors = random_face_colors(
                session.base_faces, self._viewer_color_face_edge_ids(session), random.Random())

    def _on_viewer_color_mode_changed(self, new_mode):
        """Colour > Polygon-specific/Multi-colour radiobutton command, while Viewer mode is
        active (InflatePolyhedronApp._on_color_mode_changed dispatches here) -- operates on the
        CURRENTLY VIEWED file's own session.color_mode/face_colors (2026-10-01, explicit:
        "colour changes should apply in Viewer mode as well, and they should factor into the
        undo/redo stack") rather than Inflater mode's own color_mode_var/multi_colors. Same
        undo-snapshot-with-overridden-"before"-mode trick as Inflater's own
        _on_color_mode_changed/interactive_inflater_app's identical feature, for the same
        Tk-Radiobutton-variable-already-flipped reason -- self.app._last_color_mode holds the
        PREVIOUS mode (kept in sync by _viewer_show_current's own resync on every navigation).
        Snapshotted BEFORE _viewer_ensure_multi_colors runs, not after (same bug/fix as
        InflatePolyhedronApp's own _on_color_mode_changed -- that method's own lazily-GENERATED
        colors would otherwise get captured as if they were already "the before state")."""
        path = self._viewer_current_path()
        if path is None:
            return
        session = self._viewer_sessions[path]
        old_mode = self.app._last_color_mode
        if new_mode != old_mode:
            snap = self._viewer_state_snapshot(path)
            snap["color_mode"] = old_mode
        else:
            snap = None
        if new_mode == "multi":
            self._viewer_ensure_multi_colors(session)
        if snap is not None:
            self._viewer_push_undo(snap)
        session.color_mode = new_mode
        self.app._last_color_mode = new_mode
        self.app._update_colour_menu_state()
        self._viewer_mark_dirty()
        self._viewer_show_current()

    def _on_viewer_randomize_colors_clicked(self):
        """Colour > Randomize, while Viewer mode is active -- re-rolls the CURRENTLY VIEWED
        file's own Multi-colour colors from scratch. A no-op outside Multi-colour mode or with
        nothing on screen, same guards Inflater mode's own _on_randomize_colors_clicked uses."""
        path = self._viewer_current_path()
        if path is None:
            return
        session = self._viewer_sessions[path]
        if session.color_mode != "multi":
            return
        self._viewer_push_undo(self._viewer_state_snapshot(path))
        session.face_colors = random_face_colors(
            session.base_faces, self._viewer_color_face_edge_ids(session), random.Random())
        self._viewer_mark_dirty()
        self._viewer_show_current()

    # ---- save ----

    def _on_viewer_save_clicked(self):
        path = self._viewer_current_path()
        if path is None:
            return
        self._viewer_save_path(path)

    def _viewer_save_path(self, path):
        """Writes `path`'s own session back to disk with its camera fields (level_rotation/
        level_zoom/level_pan) updated from the in-memory camera state -- everything else in
        the file (the mesh, the Convergence History, every spinner) passes through unchanged.
        `session.color_mode`/`face_colors` need no such copy-over step before saving -- unlike
        the camera (kept in a separate `self._viewer_cameras[path]` dict, mutated live), Colour-
        menu edits (_on_viewer_color_mode_changed/_on_viewer_randomize_colors_clicked) already
        mutate `session` itself directly, so whatever's currently on it is already what gets
        written."""
        session = self._viewer_sessions[path]
        cam = self._viewer_cameras[path]
        session.level_rotation = tuple(float(x) for x in cam["rotation"].as_quat())
        session.level_zoom = float(cam["zoom"])
        session.level_pan = (float(cam["pan"][0]), float(cam["pan"][1]))
        try:
            path.write_text(session.model_dump_json(indent=2))
        except OSError as e:
            messagebox.showerror("Save", f"Could not save {path.name}: {e}")
            return False
        self._viewer_saved_cameras[path] = {"rotation": cam["rotation"], "zoom": cam["zoom"],
                                              "pan": cam["pan"].copy()}
        self._viewer_saved_colors[path] = {
            "color_mode": session.color_mode,
            "face_colors": (list(session.face_colors)
                             if session.face_colors is not None else None),
        }
        self._viewer_dirty_paths.discard(path)
        # No separate "Saved" message (removed alongside the status label, 2026-09-30) -- the
        # window title's own "*" disappearing is the confirmation.
        self._update_viewer_title()
        return True

    def _update_viewer_title(self):
        path = self._viewer_current_path()
        if path is None:
            self.root.title("HIPPO Viewer")
            return
        star = "*" if path in self._viewer_dirty_paths else ""
        self.root.title(f"{path.name}{star} -- HIPPO Viewer")


    def _viewer_confirm_discard_unsaved(self):
        """Returns True if it's safe to close: no Viewer file is dirty, the user said to
        discard them anyway, or every dirty file actually saved successfully. Covers every
        file touched this session, not just whichever is currently on screen."""
        if not self._viewer_dirty_paths:
            return True
        names = ", ".join(sorted(p.name for p in self._viewer_dirty_paths))
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save changes to {len(self._viewer_dirty_paths)} Viewer file(s) before exiting?\n"
            f"({names})")
        if answer is None:
            return False
        if not answer:
            return True
        return all(self._viewer_save_path(p) for p in list(self._viewer_dirty_paths))


class InflatePolyhedronApp:
    def __init__(self, root):
        self.root = root
        # Wide enough for the Net panel + Level 0 + Levels 1..MAX_LEVEL (LEVEL_PANEL_WIDTH_
        # LEVELS_1_3 each -- not the same width as Level 0), plus view_frame's own left/right
        # padx=14 -- computed rather than a hardcoded literal, since every row here packs
        # content flush left, so a wider window would leave an uneven blank margin on the
        # right instead of fitting the content's natural width. Stays correct if MAX_LEVEL or
        # either panel width ever changes.
        # Tall enough for Setup + status + Convergence History + each panel's own title-Label-
        # plus-image-plus-button stack at their full natural size -- too short here silently
        # squeezes every image Label below its own panel height (Tk shrinks a packed widget to
        # whatever's left rather than erroring), cropping the bottom of every panel and
        # throwing off where mouse drags land on it.
        window_width = (NET_PANEL_SIZE[0] + LEVEL_PANEL_WIDTH_LEVEL_0
                        + LEVEL_PANEL_WIDTH_LEVELS_1_3 * MAX_LEVEL + 2 * 14)
        # Captured (not just computed fresh each time) so _on_view_mode_changed's return trip
        # from Viewer mode's own square window restores whatever geometry Inflater mode
        # actually had -- including a manual resize the user made before ever switching -- not
        # this hardcoded default every time.
        self._inflater_geometry = f"{window_width}x880"
        root.geometry(self._inflater_geometry)
        root.minsize(820, 600)

        sv_ttk.set_theme("dark")
        self._scale_ui_fonts()
        self._init_ui_fonts()
        # View > Inflater/Viewer -- created before _build_menu (which reads it to build the
        # radiobuttons) so both frames it later toggles between exist under one shared switch.
        self.view_mode_var = tk.StringVar(value="inflater")
        # Colour > Polygon-specific/Multi-colour -- same "created before _build_menu" reasoning
        # (2026-10-01, explicit: "add a Colour menu"). self.multi_colors (the actual persisted
        # per-base-face color list for Multi-colour mode, None until first needed) and
        # self._source_polygon_id (Polygon-specific mode's own grouping, set by on_select_net/
        # on_load_session_clicked) are read by _apply_color_mode, not referenced by any widget,
        # so they don't need to exist this early -- only the StringVar does. Default is
        # "multi" (2026-10-01, explicit: "use multi-colour as default") -- only this live
        # starting value changed; a LOADED session still restores whatever mode it was actually
        # saved with (on_load_session_clicked sets color_mode_var from the file), and
        # SessionStateModel.color_mode's own default stays "polygon" for backward compatibility
        # with a session saved before this field existed (such a file never saved any
        # face_colors either, so defaulting ITS read-back to "multi" would show freshly
        # randomized colors instead of reproducing what was actually on screen when it was
        # saved).
        self.color_mode_var = tk.StringVar(value="multi")
        self.multi_colors = None
        self._source_polygon_id = None
        # Undo/redo for the Inflater view (2026-10-01, explicit: "put Undo/Redo in an Edit
        # menu... it should apply to polyhedron_inflater too (in both views). There, the
        # undo/redo stack applies to colours, rotations/scale/zoom") -- same single-stack-of-
        # snapshots idea as ViewerPane's own pre-existing camera undo (_viewer_undo_stack), just
        # covering this view's own Colour-menu state (color_mode/multi_colors) ALONGSIDE its
        # shared Level camera (rotation/zoom/pan), since both are "the only things Inflater mode
        # lets the user change" that aren't already Ctrl+Z-able net edits (there are none of
        # those here -- this view has no 2D canvas). See _inflater_snapshot's own docstring for
        # exactly what one entry holds. _last_color_mode tracks color_mode_var's own PREVIOUS
        # value -- needed because a Tk Radiobutton's variable is already set to the NEW value by
        # the time its own `command` fires, so _on_color_mode_changed can't just read
        # color_mode_var itself to find the "before" state.
        self._last_color_mode = "multi"
        self._inflater_undo_stack = []
        self._inflater_redo_stack = []
        self._inflater_gesture_start_snapshot = None
        self._build_menu()

        # ---- Debug mode vs. release mode: the ONLY difference between
        # them is whether "Iterate for N steps" is offered at all (see
        # the steps row below) -- release mode always drives straight to
        # convergence. Everything else (net/target Setup, one
        # Inflate/Subdivide button pair per level, always-synced
        # rotation, no separate Stop button, the green "Converged"
        # message suppressed) is shared and identical either way.
        # Release mode is what a session starts in (it's the one meant
        # for an actual user, not someone working on this app); "d"
        # toggles between them at any time -- bind_all so it fires
        # regardless of which widget currently has focus (there's no
        # free-text entry in this app for a stray "d" keystroke to
        # collide with). Dispatched through _on_key_d (not bound directly)
        # since "d" ALSO means "next file" in Viewer mode (2026-09-30,
        # explicit -- "let A and D work as arrow keys too") -- debug-mode
        # toggling only fires in Inflater mode.
        self.debug_mode = False
        self.root.bind_all("<KeyPress-d>", self._on_key_d)

        # The seed random_initial_positions uses on every net (re)load (see on_select_net/
        # _get_or_generate_seed) -- blank (the default) means "pick a fresh random one each
        # time", a typed integer pins that exact seed for the next net load. Only ever edited
        # via debug mode's own "Seed" entry, but the VALUE itself isn't debug-only -- release
        # mode gets the same randomize-by-default behavior, just without a way to see/set it:
        # a fixed seed would mean a net's own random starting embedding -- and thus which of
        # several very different-looking local equilibria it settles into -- was always
        # exactly the same, run after run.
        self.seed_var = tk.StringVar(value="")

        # Every existing (Inflater-mode) widget below is parented to this ONE frame, not root
        # directly, so _on_view_mode_changed can hide the whole thing with one pack_forget()
        # when Viewer mode is selected, and restore it with one pack() -- nothing else about
        # this section changes.
        self._inflater_frame = ttk.Frame(root)
        self._inflater_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ---- Setup: net picker + target RMS stretch + tolerance, all
        # tiled HORIZONTALLY in one row to save vertical space (an
        # earlier version stacked net picker and target RMS stretch on
        # their own separate rows), shared by both modes, plus (debug
        # mode only) the steps-vs-convergence choice/Show normals row
        # below it. ----
        setup_frame = ttk.LabelFrame(self._inflater_frame, text="Setup", padding=12)
        setup_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(14, 8))

        setup_row = ttk.Frame(setup_frame)
        setup_row.pack(fill=tk.X)

        net_group = ttk.Frame(setup_row)
        net_group.pack(side=tk.LEFT)
        ttk.Label(net_group, text="Choose a net:").pack(side=tk.LEFT, padx=(0, 8))
        self.net_var = tk.StringVar()
        self.combo = ttk.Combobox(net_group, state="readonly", width=15,
                                   textvariable=self.net_var)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        target_group = ttk.Frame(setup_row)
        target_group.pack(side=tk.LEFT, padx=(96, 0))
        ttk.Label(target_group, text="Target RMS stretch:").pack(side=tk.LEFT, padx=(0, 4))
        # One independent spinner per level (1-3), not a single spinner reset on frontier
        # change, so every level's own target is visible/settable at once. Both a manual
        # Inflate click and "Auto" read self.target_rms_vars[self.subdivision_level].
        self.target_rms_vars = {}
        self.target_rms_display_vars = {}
        self.target_rms_spins = {}
        # Which of LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED/_OPEN currently applies -- set for real
        # by on_select_net (_reset_target_rms_defaults) once a net's own closed/open status is
        # known; OPEN here is just a placeholder for widget construction, before any net has
        # been loaded at all.
        self._target_rms_defaults = LEVEL_DEFAULT_TARGET_RMS_PCT_OPEN
        for level in (1, 2, 3):
            ttk.Label(target_group, text=f"Level {level}:").pack(side=tk.LEFT, padx=(20, 2))
            var = tk.DoubleVar(value=round(self._target_rms_defaults[level]))
            # A "converged" verdict only applies to the target it was reached at -- editing
            # this level's own target while it's the current frontier means the pressure
            # hasn't been (re)calibrated for the new value, so the Inflate-gate needs to lift
            # (see _update_level_action_buttons). Editing a non-current level touches no gate.
            var.trace_add("write", lambda *_a, lv=level: self._on_target_rms_changed(lv))
            # `var` is the value read everywhere else (on_inflate_clicked, session save/load,
            # history table) -- unchanged by the entry's "%"-suffixed display below, which is
            # a pure presentation layer (self.target_rms_display_vars), never read elsewhere.
            var.trace_add("write", lambda *_a, lv=level: self._sync_target_rms_display(lv))
            self.target_rms_vars[level] = var

            # A plain Entry, not a Spinbox -- restricted to numeric-looking input as typed
            # (_register_numeric_entry, no exponent/decimal needed for a whole-number
            # percentage) and clamped into [0, 100] on commit (_commit_target_rms_entry), since
            # a Spinbox's from_/to_ only gates its up/down arrows, never free typing. Bound to
            # its own display StringVar, not `var` directly -- shows "N%" while unfocused and
            # the bare number while being edited (_begin_edit_target_rms); `_sync_target_rms_
            # display` keeps the StringVar in sync with `var` from any source.
            display_var = tk.StringVar(value=f"{var.get():.0f}%")
            self.target_rms_display_vars[level] = display_var
            spin = ttk.Entry(target_group, width=5, textvariable=display_var)
            self._register_numeric_entry(spin, allow_exponent=False, allow_decimal=False)
            spin.bind("<FocusIn>", lambda event, lv=level: self._begin_edit_target_rms(lv))
            spin.bind("<Return>", lambda event, lv=level: self._commit_target_rms_entry(lv))
            spin.bind("<FocusOut>", lambda event, lv=level: self._commit_target_rms_entry(lv))
            spin.pack(side=tk.LEFT)
            self.target_rms_spins[level] = spin
        # Pressure is not user-editable or separately displayed -- "Inflate" calibrates it
        # itself and it's already logged per level in the Convergence History table.
        self.pressure_value = DEFAULT_PRESSURE

        tolerance_group = ttk.Frame(setup_row)
        tolerance_group.pack(side=tk.LEFT, padx=(96, 0))
        ttk.Label(tolerance_group, text="Tolerance:").pack(side=tk.LEFT, padx=(0, 4))
        # The `gtol` every relax_once/relax_initial_configuration/estimate_pressure_for_
        # target_stretch call actually uses (self._current_gtol, set at the start of every
        # Relax/Inflate click via _get_tolerance) -- distinct from stretchy_mesh's own fixed
        # CONVERGENCE_GTOL. Same converged-gate rationale as target_rms_vars above: a changed
        # tolerance invalidates a past "converged" verdict. A `tk.StringVar` holding
        # scientific-notation text ("1e-03"), not a `tk.DoubleVar` -- a DoubleVar set
        # programmatically renders via Tcl's default float-to-string ("0.001") rather than
        # scientific notation. `_get_tolerance` parses it back to a float when needed.
        self.tolerance_var = tk.StringVar(value=f"{DEFAULT_TOLERANCE:.0e}")
        self.tolerance_var.trace_add("write", self._on_tolerance_changed)
        # A plain Entry, not a Spinbox, restricted to numeric-looking input as typed
        # (_register_numeric_entry, WITH exponent this time for scientific notation like
        # "1e-03"). No commit-time clamp (unlike target RMS) -- `_get_tolerance` falls back to
        # DEFAULT_TOLERANCE for anything unparseable.
        self.tolerance_spin = ttk.Entry(tolerance_group, width=10, textvariable=self.tolerance_var)
        self._register_numeric_entry(self.tolerance_spin, allow_exponent=True)
        self.tolerance_spin.pack(side=tk.LEFT)

        # "Auto": visible/usable in BOTH modes (unlike the debug-only row below) -- a scripted
        # sequence of the same Relax/Inflate/Subdivide actions a user could click by hand
        # (see on_auto_clicked/_auto_step).
        auto_group = ttk.Frame(setup_row)
        auto_group.pack(side=tk.LEFT, padx=(96, 0))
        self.auto_button = ttk.Button(auto_group, text="Run Simulation", command=self.on_auto_clicked)
        self.auto_button.pack(side=tk.LEFT)
        self.auto_button.state(["disabled"])  # no net loaded yet -- _update_auto_button syncs this

        # Debug-mode-only row: "Iterate for N steps" vs. "until convergence" plus
        # "Show normals"/"Show repulsive forces" (diagnostics with no effect on the solve).
        # Shown/hidden by _apply_mode_visibility; both are forced back to release-mode defaults
        # whenever leaving debug mode, so release mode never shows a stray fixed-step
        # request or stale normals overlay.
        self.mode_row = ttk.Frame(setup_frame)
        self.iterate_mode_var = tk.StringVar(value="convergence")
        self.steps_radio = ttk.Radiobutton(self.mode_row, text="Iterate for", value="steps",
                                            variable=self.iterate_mode_var,
                                            command=self._update_mode_state)
        self.steps_radio.pack(side=tk.LEFT)
        self.steps_var = tk.IntVar(value=DEFAULT_STEPS)
        self.steps_spin = ttk.Spinbox(self.mode_row, from_=1, to=1000000, width=7,
                                       textvariable=self.steps_var)
        self.steps_spin.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(self.mode_row, text="steps").pack(side=tk.LEFT, padx=(0, 18))
        self.convergence_radio = ttk.Radiobutton(self.mode_row, text="Iterate until convergence",
                                                  value="convergence",
                                                  variable=self.iterate_mode_var,
                                                  command=self._update_mode_state)
        self.convergence_radio.pack(side=tk.LEFT)
        ttk.Separator(self.mode_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=18)
        self.show_normals_var = tk.BooleanVar(value=False)
        self.show_normals_check = ttk.Checkbutton(self.mode_row, text="Show face normals",
                                                    variable=self.show_normals_var,
                                                    command=self.draw)
        self.show_normals_check.pack(side=tk.LEFT)
        # Per-vertex normals -- a vertex between inconsistently-angled faces can have a
        # badly-behaved average direction even when every face normal looks fine. Separate
        # toggle/color from "Show face normals" so the two are never visually conflated.
        self.show_vertex_normals_var = tk.BooleanVar(value=False)
        self.show_vertex_normals_check = ttk.Checkbutton(
            self.mode_row, text="Show vertex normals",
            variable=self.show_vertex_normals_var, command=self.draw)
        self.show_vertex_normals_check.pack(side=tk.LEFT)
        # Draws each repulsive vertex's own CURRENT force from _repulsion_force -- see
        # _draw_level_panel's own repulsion block for the color/scale convention, matching
        # "Show normals"' own pattern.
        self.show_repulsive_forces_var = tk.BooleanVar(value=False)
        self.show_repulsive_forces_check = ttk.Checkbutton(
            self.mode_row, text="Show repulsive forces",
            variable=self.show_repulsive_forces_var, command=self.draw)
        self.show_repulsive_forces_check.pack(side=tk.LEFT)

        ttk.Separator(self.mode_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=18)
        ttk.Label(self.mode_row, text="Seed:").pack(side=tk.LEFT, padx=(0, 4))
        # Blank (the default) means "randomize" -- _get_or_generate_seed fills this in with
        # whatever it actually picked right after using it, so the value that produced the
        # current shape is always visible/copyable here, even in the common case where the
        # user never typed one in themselves. Typing a specific integer here pins that exact
        # seed for the NEXT net (re)load (on_select_net); clearing it back to blank returns to
        # randomizing. A plain Entry, not a Spinbox, same restricted-input pattern as the
        # target RMS entries (_register_numeric_entry, no exponent/decimal -- but blank must
        # stay valid, unlike a required numeric field, so no commit-time fallback is wired up
        # the way target RMS's is).
        self.seed_spin = ttk.Entry(self.mode_row, width=10, textvariable=self.seed_var)
        self._register_numeric_entry(self.seed_spin, allow_exponent=False, allow_decimal=False)
        self.seed_spin.pack(side=tk.LEFT)

        # ---- Status (warning/error/progress message): debug-mode-only. ----
        self.status_frame = ttk.Frame(self._inflater_frame)
        self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # ---- Convergence history: one row per subdivision level visited this session
        # (including Level 0), showing pressure ("--" for Level 0, which has none), steps
        # taken (self.iteration_count, reset on Subdivide/promotion), stretch stats (RMS shown
        # against the current Target RMS spinner), and a combined "Convergence" cell
        # (`optimality` vs. gtol, check/cross). height=MAX_LEVEL+1 (0..MAX_LEVEL) is the most
        # rows this table will ever hold. ----
        self.history_frame = ttk.LabelFrame(self._inflater_frame, text="Convergence History",
                                             padding=12)
        self.history_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        # "max_stretch" is debug-mode-only, "simulation_time"/"cumulative_time" show in both
        # modes -- all three stay DEFINED here regardless of mode (_apply_mode_visibility
        # toggles Treeview's own `displaycolumns`), just shown/hidden.
        history_columns = ("level", "pressure", "steps", "max_stretch", "rms_stretch",
                            "simulation_time", "cumulative_time", "convergence")
        self.history_tree = ttk.Treeview(self.history_frame, columns=history_columns,
                                          show="headings", height=MAX_LEVEL + 1)
        # Per-column "weight" -- proportions (not fixed pixel widths), tuned to roughly what
        # each column's header/content needs relative to the others. _rescale_history_columns
        # (bound below to <Configure>, and called on every mode toggle) turns these into pixel
        # widths that always sum to the widget's current width, every column scaled by the
        # same factor -- ttk.Treeview's own stretch=True instead distributes leftover space
        # evenly per column regardless of configured width, which doesn't give proportional
        # scaling.
        self._history_column_weights = {
            "level": 70, "pressure": 100, "steps": 85, "max_stretch": 115,
            "rms_stretch": 150, "simulation_time": 145, "cumulative_time": 135,
            "convergence": 145,
        }
        for col, heading in (
                ("level", "Level"), ("pressure", "Pressure"), ("steps", "Steps"),
                ("max_stretch", "Max Stretch %"), ("rms_stretch", "RMS Stretch %"),
                ("simulation_time", "Simulation Time"), ("cumulative_time", "Cumulative Time"),
                ("convergence", "Convergence")):
            self.history_tree.heading(col, text=heading)
            # stretch=False -- widths are set explicitly/proportionally by
            # _rescale_history_columns instead; Tk's own stretch would fight that.
            self.history_tree.column(col, width=self._history_column_weights[col],
                                      stretch=False, anchor=tk.CENTER)
        self.history_tree.bind("<Configure>",
                                lambda event: self._rescale_history_columns(event.width))
        self._release_mode_history_columns = tuple(
            col for col in history_columns if col != "max_stretch")
        self.history_tree.config(displaycolumns=self._release_mode_history_columns)
        # ttk.Treeview can only color a whole ROW, not one cell -- the Convergence column's
        # check/cross comes with its whole row tinted to match.
        self.history_tree.tag_configure("converged", foreground=STATUS_COLORS["success"])
        self.history_tree.tag_configure("not_converged", foreground=STATUS_COLORS["error"])
        # A run actively in progress -- distinct from "not_converged": red is reserved for an
        # actual failure (step cap or Stop), not just "still going" (see _refresh_history_table).
        self.history_tree.tag_configure("running", foreground=RUNNING_ROW_COLOR)
        self.history_tree.pack(fill=tk.X)

        # ---- Net (flat layout, matplotlib) + one 3D panel per level (0..MAX_LEVEL, PyVista),
        # side by side. Each level panel is its own off-screen Plotter/Label pair so a native
        # Tkinter Inflate/Subdivide/Relax button can sit directly below it. Level N's panel is
        # LIVE only while self.subdivision_level == N; once the user moves past it, that
        # level's last state freezes into self.level_snapshots. ----
        view_frame = ttk.Frame(self._inflater_frame)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))

        # fill/expand=False here (unlike a plain pack default): each panel below is a
        # fixed-size image that never grows, so letting this row stretch to the window's
        # full width would just spread panels apart with dead space instead of keeping them
        # packed together.
        panels_row = ttk.Frame(view_frame)
        panels_row.pack(side=tk.TOP, anchor=tk.W)

        net_panel_frame = ttk.Frame(panels_row)
        # fill=tk.Y stretches this frame to match the row's own height (no button/spacer of
        # its own needed) -- the net canvas grows into whatever extra height that leaves.
        net_panel_frame.pack(side=tk.LEFT, fill=tk.Y)
        # A plain Label, not ax.set_title() -- a title drawn INSIDE a PyVista panel's own
        # rendered image clips against the panel boundary; a real Tkinter widget above the
        # image doesn't, and every "Level N" panel's title uses the same approach.
        ttk.Label(net_panel_frame, text="Net", font=self.LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        self.fig_net = plt.figure(figsize=(3.2, 4.5))
        # add_axes([0, 0, 1, 1]), not add_subplot -- add_subplot's own default margins
        # reserve room for axis labels/ticks that _style_2d_axis's set_axis_off() never draws,
        # shrinking the actual plotting area below the full figure. Filling the whole figure
        # instead matches every "Level N" panel's own PyVista viewport, which already fills
        # its entire window_size.
        self.ax2d = self.fig_net.add_axes([0, 0, 1, 1])
        self.canvas_net = FigureCanvasTkAgg(self.fig_net, master=net_panel_frame)
        net_widget = self.canvas_net.get_tk_widget()
        net_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Mouse-wheel-scroll zoom for the Net panel -- same idea as every "Level N" panel's own
        # self.level_zoom (_on_level_scroll), scaling _draw_target_faces' bounding-box-derived
        # half-extent instead of a PyVista camera's parallel_scale, since this panel is
        # matplotlib, not PyVista.
        self.net_zoom = 1.0
        net_widget.bind("<MouseWheel>", self._on_net_scroll)
        net_widget.bind("<Button-4>", self._on_net_scroll)
        net_widget.bind("<Button-5>", self._on_net_scroll)
        # Right-click-drag pans the Net panel (self.net_pan) -- its own analogue of every
        # "Level N" panel's self.level_pan, entirely separate state; middle-click resets it.
        self.net_pan = np.zeros(2)
        self._net_panning = False
        self._net_pan_last_xy = None
        net_widget.bind("<ButtonPress-3>", self._on_net_pan_start)
        net_widget.bind("<B3-Motion>", self._on_net_pan_motion)
        net_widget.bind("<ButtonRelease-3>", self._on_net_pan_end)
        net_widget.bind("<Button-2>", self._on_net_pan_reset)

        self.level_frames = {}
        self.level_plotters = {}
        self.level_labels = {}
        self.level_message_labels = {}
        # For _set_level_message's own width measurement (tkfont.Font.
        # measure) -- a real Font OBJECT, not the (family, size) tuple
        # LEVEL_MESSAGE_FONT itself is, since only a Font object exposes
        # `.measure()`. Needs a Tk root to already exist, which it does by
        # this point in __init__.
        self._level_message_font = tkfont.Font(root=self.root, family=self.LEVEL_MESSAGE_FONT[0],
                                                 size=self.LEVEL_MESSAGE_FONT[1])
        self.level_photos = {}
        self._level_center = {}
        self._level_half = {}
        # ONE shared camera group across every level (0-3) -- every level's panel rotates/
        # pans/zooms together. `_level_camera(level)` returns the mutable, in-place-updated
        # dict (`level` is accepted for a uniform call signature across every caller, even
        # though every level now maps to the same dict);
        # `_camera_group_levels(level)` returns every panel that needs re-rendering when the
        # shared state changes -- currently always every built level, but keeps the same
        # call shape a future re-split would need.
        #
        # The camera's own "rotation" is a quaternion (scipy Rotation)
        # rather than a separate azimuth/elevation pair -- two Euler
        # angles hit gimbal lock near the poles (elevation -> +-90
        # degrees, where a horizontal drag stops rotating around a
        # sensible axis); a quaternion represents the whole orientation as
        # one object with no such singularity. _initial_level_rotation()
        # reproduces the old LEVEL_DEFAULT_AZIM/ELEV starting view as a
        # Rotation, used as the group's own starting rotation.
        #
        # The camera's own "pan" is a 2D NDC (normalized device
        # coordinate, [-1, 1]) offset applied via vtkCamera's own
        # SetWindowCenter -- a pure post-projection VIEWPORT shift --
        # rather than a 3D world-space vector added to the camera's
        # focal_point/position (an earlier version did that, and had two
        # real bugs): (1) an NDC value produces the same FRACTIONAL shift
        # regardless of a given panel's own pixel size or bounding-box
        # scale -- a world-space offset instead produced a DIFFERENT pixel
        # shift per panel (each level's own parallel_scale differs, and
        # Level 0's own panel is a different pixel size besides, see
        # LEVEL_PANEL_SIZE), which is what made translation look unsynced
        # across levels; (2) moving focal_point moves the
        # camera's own orbit center, so rotating (_on_level_motion) after
        # a pan no longer orbited the object's true center -- with
        # SetWindowCenter, the camera's focal_point/position are computed
        # exactly as if no pan existed (_render_level_pv), so a subsequent
        # rotation always still orbits the real center; pan only shifts
        # where that already-correct render lands in the panel.
        self._level_camera_state = {"rotation": _initial_level_rotation(),
                                     "zoom": 1.0, "pan": np.zeros(2)}
        # Populated by _build_level_pv_panel (label -> level), so a drag/
        # pan/scroll event (whose only clue which level it came from is
        # `event.widget`, the image Label that received it) can look up
        # which level it happened on (still needed for _level_pan_group_level
        # etc., even though every level shares one camera now).
        self._level_of_label = {}
        self._level_dragging = False
        self._level_last_xy = None
        # Which level's own camera group a drag/pan currently in progress
        # is updating -- captured once at press time (_on_level_drag_
        # start/_on_level_pan_start) and reused for every motion event
        # during that SAME drag, rather than re-deriving it from
        # event.widget on every motion call -- Tk's implicit button-1
        # grab keeps motion/release events routed to the originally-
        # pressed widget regardless of where the mouse strays, so re-
        # deriving would give the same answer anyway, but capturing once
        # is simpler and doesn't depend on that grab behavior holding.
        self._level_drag_group_level = None
        self._level_panning = False
        self._level_pan_last_xy = None
        self._level_pan_group_level = None
        # ONE button per level, below its panel -- no separate button
        # above (see _update_level_action_buttons for its full state
        # machine): idle it reads "Relax" (level 0 only) or "Inflate",
        # a run in progress turns it into "Stop" (see
        # _set_level_action_button_running), and once that level
        # converges it becomes "Subdivide" (clickable, advances to the
        # next level) or "DONE!" (MAX_LEVEL, nothing further to
        # subdivide to). Only the current frontier level's button is
        # ever enabled.
        self.level_action_buttons = {}
        # Debug-mode-only replay scrubber, one per level (including Level 0 -- its own Relax
        # replays/captures frames the same way Levels 1-3's Inflate does, see _finish_relax;
        # 2026-10-01, explicit: "debug mode should have the replay slider"). Lets a user inspect
        # any point in a level's last-captured trajectory, not just the live end state or the
        # auto-played animation. self._level_frames[level] is that level's own captured
        # (positions, steps_taken) list, kept even after Subdividing/promoting past it;
        # self._level_scrub_index[level], when set, OVERRIDES what draw() shows for that panel
        # -- self.positions/level_snapshots are never touched by scrubbing, so the next real
        # action always continues from the true state regardless of the slider.
        self._level_frames = {}
        self._level_scrub_index = {}
        self.level_replay_sliders = {}
        for level in range(0, MAX_LEVEL + 1):
            level_frame = ttk.Frame(panels_row)
            # No fill/expand -- every panel hugs its own fixed image size (see panels_row).
            level_frame.pack(side=tk.LEFT)
            self.level_frames[level] = level_frame
            button = ttk.Button(level_frame, text="Relax" if level == 0 else "Inflate")
            self.level_action_buttons[level] = button
            # Packed FIRST among this frame's bottom-side widgets (Tk stacks additional
            # bottom-packed siblings upward from the bottom edge), so it lands below the
            # button once that's packed next.
            slider = ttk.Scale(level_frame, from_=0, to=0, orient=tk.HORIZONTAL,
                                command=lambda v, lvl=level: self._on_replay_slider_moved(lvl, v))
            slider.state(["disabled"])
            self.level_replay_sliders[level] = slider
            slider.pack(side=tk.BOTTOM, in_=level_frame)
            # Button packed BEFORE the panel widget, at BOTTOM -- packing it after an
            # expand=True widget would starve it of space, since that widget would already
            # have claimed the whole remaining cavity. No fill=tk.X -- left at its own
            # natural, text-sized width, centered under the panel by pack's default anchor.
            button.pack(side=tk.BOTTOM, in_=level_frame)
            self._build_level_pv_panel(level, level_frame)

        # Per-level frozen snapshots of {faces, positions, face_of_fine,
        # edge_length} taken the moment the user subdivides PAST that
        # level (see _subdivide_step), or Level 0's Relax converges and
        # promotes it into Level 1 (see _finish_relax).
        self.level_snapshots = {}

        self.faces = None
        self.base_faces = None
        self.face_of_fine = None
        self.subdivision_level = 0
        self.edge_length = None
        # Level 0/1's own explicit spring-edge override (_fan_level_edges) and its origin, the
        # loaded net's own explicit "edges"/"face_edge_ids" fields -- None past Level 1, or for
        # any net/session with no such fields.
        self.edges = None
        self.base_edges = None
        self.base_face_edge_ids = None
        self.target_layout = None
        # interactive_builder_app's own saved "builder_connections" (bezier control points
        # included), or None -- see on_select_net for when this is populated.
        self.target_connections = None
        # target_layout's own key space (see net_loading.target_layout_and_connections) --
        # parallel to self.base_faces, populated alongside target_layout.
        self.target_group_of_face = None
        self.positions = None
        self.iteration_count = 0
        self.last_stats = {}
        self.level_history = {}
        self.stop_event = None
        # Whether the current frontier level has a Relax/Inflate run actively in progress --
        # set/cleared in lockstep with _set_level_action_button_running, read by
        # _refresh_history_table to color that level's row "running" (yellow) instead of
        # "not_converged" (red, reserved for an actual failure) while still mid-run.
        self._level_running = False
        # Backing state for the Convergence History table's "Simulation Time"/"Cumulative
        # Time" columns -- wall-clock time spent in the current level's own pressure-
        # calibration phase (_on_pressure_calibrated, None for Level 0/Relax, which has no
        # pressure) and, for Level 0 only, its streamed relax phase (_run_relax_stream) --
        # Level 1+ has no separate "sim" phase (calibration's own winning trial IS the Inflate
        # result). The `_start_time` pair marks when each phase began (None between runs); the
        # `_current_*_time_s` pair is what _record_level_history reads -- precomp is set once
        # at calibration finish, sim updates live on every progress callback. Reset to None
        # anywhere iteration_count resets. Never incremented during a frame replay -- that's
        # pure animation of already-finished cached positions, not new simulation work.
        self._precomp_start_time = None
        self._sim_start_time = None
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        # "Computing..." placeholder: which level's panel is currently showing it (None
        # normally) -- _render_level_pv skips that level entirely while set, so nothing can
        # paint a stale image over it mid-calibration. _computing_after_id is the pending
        # `root.after` callback driving the dot-cycle animation.
        self._computing_level = None
        self._computing_after_id = None
        self._computing_dots = 0
        # Frame-replay state: the winning calibration trial's own cached positions
        # (capture_frames), played back for display once calibration lands on a pressure --
        # _replay_after_id is the pending `root.after` callback, None when no replay running.
        self._replay_after_id = None
        self._replay_frames = None
        self._replay_index = 0
        self._replay_final_result = None
        self._replay_base_iteration_count = 0
        # The gtol in effect for the run currently underway (or the last one) -- captured from
        # self.tolerance_var at the moment Relax/Inflate starts, not re-read live, and recorded
        # into self.last_stats/level_history so a finished run's row shows what it actually used.
        self._current_gtol = DEFAULT_TOLERANCE
        # Same rationale as self._current_gtol, for the current level's own Target RMS spinner
        # -- captured when actually used, not re-read live, so a finished level's row keeps
        # showing the target it was calibrated against even after the spinner is edited later.
        self._current_target_rms_pct = self.target_rms_vars[1].get()
        # Whether "Auto"'s scripted sequence is currently driving the app --
        # _auto_attempted_level names the level Auto has already made its one Relax/Inflate
        # attempt at (no retries within a level), reset to None once _auto_step notices the
        # current level has changed since it last ran.
        self._auto_active = False
        self._auto_attempted_level = None
        # How the LAST Auto sequence ended, once it's no longer active -- None (never run, or
        # a fresh net/session just loaded), "completed" (reached MAX_LEVEL and converged, OR
        # gave up on a level that wouldn't converge after one attempt -- either way, ran to a
        # natural end on its own), or "stopped" (aborted by an explicit Stop click, or a
        # worker-thread failure -- see _abort_auto). Read by _update_auto_button to choose the
        # Auto button's own label/action: "completed"/None both read "Run Simulation" and
        # restart fresh from Level 0 (on_auto_clicked);
        # "stopped" reads "Continue Simulation" and resumes from the START of whatever level
        # was interrupted (on_auto_continue_clicked), not from its own mid-run progress.
        self._auto_end_state = None
        # Run > Run All/Debug All's own state (see on_run_all_clicked/on_debug_all_clicked):
        # whether a run is currently working through self._run_all_paths (a
        # fixed [(label, path), ...] snapshot of self.label_to_path taken at kickoff, so a net
        # added/removed mid-run doesn't change the list underway) and which index it's on --
        # read by _update_window_title for the "(m/n)" suffix. _run_all_wait_for_advance/
        # _run_all_awaiting_key are Debug All's own pause-between-nets state (see
        # _poll_run_all_net/_on_debug_all_right_key) -- always False for a plain Run All run.
        # _run_all_poll_token guards against TWO _poll_run_all_net chains ever running at once
        # (see _debug_all_jump's own comment) -- bumped every time a net is (re)started, and
        # checked by every _poll_run_all_net call against the CURRENT value, so a poll chain
        # left over from a net the user jumped away from early (Left/Right arrow mid-run)
        # recognizes itself as stale and quietly stops, instead of racing the new chain.
        self._run_all_active = False
        self._run_all_paths = []
        self._run_all_index = 0
        self._run_all_save_results = True
        self._run_all_wait_for_advance = False
        self._run_all_awaiting_key = False
        self._run_all_poll_token = 0
        # The CURRENT level's own starting faces/positions/face_of_fine/edge_length/edges,
        # captured fresh every time a level is first entered (on_select_net for Level 0,
        # _finish_relax's own promotion to Level 1, _subdivide_step for Level 2+) -- exactly
        # what on_auto_continue_clicked restores before resuming a stopped level, discarding
        # whatever partial Relax/Inflate progress it had made. Safe to keep as plain
        # references (no deep copy): self.positions/faces etc. are always REASSIGNED to a new
        # dict/list on every update, never mutated in place, so an old reference here keeps
        # pointing at that exact past state.
        self._level_start_state = None
        self.current_path = None
        self.current_label = None
        self.label_to_path = {}
        # The currently-loaded net's own raw file content -- None until a net (or a saved
        # session carrying one) is loaded.
        self._net_file_json = None
        self._apply_plot_theme()
        self.refresh_net_list()
        self._apply_mode_visibility()
        if self.current_label:
            self.on_select_net()
        # Fits the window's starting height to release mode's default layout -- must come
        # after on_select_net's draw() call, not right after _apply_mode_visibility above.
        self._refit_window_height()

        self.viewer = ViewerPane(self.root, self.view_mode_var, self)
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit_request)

    def _on_view_mode_changed(self):
        """View > Inflater/Viewer radiobutton command -- toggles which top-level frame is
        packed, and the window's own size (VIEWER_WINDOW_GEOMETRY -- square -- for Viewer,
        whatever Inflater's own geometry was right before the switch otherwise, including a
        manual resize the user made). Viewer mode always rescans SESSION_OUTPUT_DIR fresh on
        the way in (_viewer_rescan), so a .hippo file saved earlier in this same Inflater
        session (File > Save, or Run All) is visible immediately, not just ones that existed
        at app startup.

        Leaving Viewer mode for Inflater prompts to save first if anything is dirty there
        (2026-09-30, explicit -- "when the user tries to... go back to Inflater view, that's
        when you prompt"), same as actually quitting (_on_quit_request) -- if the user cancels
        that prompt, the radiobutton selection is reverted (view_mode_var set back to
        "viewer") and nothing else about this call happens, leaving Viewer mode exactly as it
        was."""
        if self.view_mode_var.get() == "viewer":
            # wm geometry() can report stale (pre-maximize) dimensions while the window is
            # zoomed, so a maximized Inflater window must be restored by re-zooming, not by
            # replaying that stale geometry string (2026-10-01, fix for reported bug: "when
            # switching back to Inflater mode, the window size should change" -- it was staying
            # at Viewer's square size because the captured geometry was stale).
            self._inflater_was_zoomed = self.root.state() == "zoomed"
            self._inflater_geometry = self.root.geometry()
            # Same capture-before-overwrite idea as the geometry above, for the Colour menu's
            # own state (2026-10-01, explicit: "colour changes should apply in Viewer mode as
            # well...") -- self.viewer._viewer_rescan() below (via _viewer_show_current) is
            # about to repoint color_mode_var/_last_color_mode at whatever file Viewer mode
            # shows, so Inflater's own current values need saving first to be restored on the
            # way back out.
            self._inflater_color_mode_snapshot = self.color_mode_var.get()
            self._inflater_last_color_mode_snapshot = self._last_color_mode
            self._inflater_frame.pack_forget()
            self.viewer._viewer_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.root.state("normal")
            self.root.geometry(VIEWER_WINDOW_GEOMETRY)
            self.viewer._viewer_rescan()
            self._update_run_menu_state()
        else:
            if not self.viewer._viewer_confirm_discard_unsaved():
                self.view_mode_var.set("viewer")
                return
            self.viewer._viewer_frame.pack_forget()
            self._inflater_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            if getattr(self, "_inflater_was_zoomed", False):
                self.root.state("zoomed")
            else:
                self.root.geometry(self._inflater_geometry)
            # Restores Inflater mode's own Colour-menu state, captured above on the way in --
            # color_mode_var currently holds whatever Viewer file was last on screen.
            self.color_mode_var.set(
                getattr(self, "_inflater_color_mode_snapshot", self.color_mode_var.get()))
            self._last_color_mode = getattr(
                self, "_inflater_last_color_mode_snapshot", self._last_color_mode)
            self._update_colour_menu_state()
            self._update_run_menu_state()
        self._update_window_title()

    def _on_control_s(self):
        """Ctrl+S dispatches by view_mode_var -- "save the current .hippo file" in Viewer
        mode, "save an Inflater session" (on_save_session_clicked, unchanged) otherwise."""
        if self.view_mode_var.get() == "viewer":
            self.viewer._on_viewer_save_clicked()
        else:
            self.on_save_session_clicked()

    # ---- Edit menu (2026-10-01, explicit: "Put Undo/Redo in an Edit menu... it should apply
    # to polyhedron_inflater too (in both views)") ----

    def _on_edit_undo(self):
        """Edit > Undo / Ctrl+Z -- dispatches by view_mode_var, same pattern as _on_control_s.
        Viewer mode's own undo (_viewer_undo_stack, pre-existing) already covers that view's
        camera; _on_inflater_undo is this view's own new equivalent, covering Colour-menu state
        plus the shared Level camera (see _inflater_snapshot's own docstring)."""
        if self.view_mode_var.get() == "viewer":
            self.viewer._on_viewer_undo()
        else:
            self._on_inflater_undo()

    def _on_edit_redo(self):
        """Edit > Redo / Ctrl+Y -- see _on_edit_undo's own docstring."""
        if self.view_mode_var.get() == "viewer":
            self.viewer._on_viewer_redo()
        else:
            self._on_inflater_redo()

    # ---- close (Viewer's own unsaved-changes check; Inflater mode has none of its own to
    # preserve here, so this is the app's first WM_DELETE_WINDOW handler) ----

    def _on_quit_request(self):
        if self.viewer._viewer_confirm_discard_unsaved():
            self.root.destroy()

    def _init_ui_fonts(self):
        """Computes self.LEVEL_TITLE_FONT/LEVEL_MESSAGE_FONT (and the File menu's own font,
        see _build_menu) from "Choose a net"'s own actual rendered font -- a plain ttk.Label
        with no font= override renders via sv_ttk's default TLabel style, routed to the named
        font "SunValleyBodyFont" (see _scale_ui_fonts). Must run AFTER _scale_ui_fonts (needs
        the final scaled size) and AFTER sv_ttk.set_theme (SunValleyBodyFont doesn't exist
        before that). Using its actual .actual() family/size, rather than a hardcoded string
        that could silently fall back to a generic default, is what makes every title/message
        label genuinely match "Choose a net"."""
        reference = tkfont.nametofont("SunValleyBodyFont", root=self.root).actual()
        self.LEVEL_TITLE_FONT = (reference["family"], reference["size"])
        self.LEVEL_MESSAGE_FONT = self.LEVEL_TITLE_FONT

    def _scale_ui_fonts(self):
        """Scales every named Tk/ttk font by UI_FONT_SCALE, once at startup, right after
        sv_ttk.set_theme -- covers the whole UI's text size in one place. sv_ttk's themes
        route almost every ttk style through its own named Tcl fonts (SunValleyBodyFont, ...)
        rather than the standard TkDefaultFont/etc, so tkfont.names() (every named font known
        to the interpreter) reaches both in one pass. A size of 0 (some internal fonts use
        this) means "use the platform default" and stays that way rather than becoming
        0 * scale = 0."""
        for name in tkfont.names(self.root):
            font = tkfont.nametofont(name, root=self.root)
            size = font.cget("size")
            if size == 0:
                continue
            sign = -1 if size < 0 else 1
            font.configure(size=sign * round(abs(size) * UI_FONT_SCALE))
        # Treeview's rowheight is set by sv_ttk's theme file to SunValleyBodyFont's line
        # spacing plus a fixed padding, computed once when the theme loads -- it doesn't
        # auto-track a later font resize, so rows would stay sized for the old (smaller) font,
        # clipping the new, taller text. Recomputed here the same way (sv_ttk's dark.tcl
        # "Treeview" style) now that SunValleyBodyFont has its final scaled size.
        body_font = tkfont.nametofont("SunValleyBodyFont", root=self.root)
        ttk.Style(self.root).configure("Treeview", rowheight=body_font.metrics("linespace") + 3)

    def _build_menu(self):
        """This app's only menu bar -- File > Load.../Save..., Load above Save as the more
        common entry point (opening a previously-saved session before continuing it); Run >
        Run All/Debug All (see on_run_all_clicked/on_debug_all_clicked). See on_save_clicked/
        on_load_clicked for what the File items actually do.

        Explicit `font=` on every Menu/add_command call here: Windows renders the native menu
        bar via its own chrome, which ignores "TkMenuFont"'s configured size regardless of
        _scale_ui_fonts -- a known Tk-on-Windows limitation for the top-level menu bar
        specifically. An explicit per-widget/per-item font IS respected. Reuses
        self.LEVEL_TITLE_FONT ("Choose a net"'s own actual family/size) so the menu genuinely
        matches the rest of the UI."""
        menu_font = self.LEVEL_TITLE_FONT
        menubar = tk.Menu(self.root, font=menu_font)
        file_menu = tk.Menu(menubar, tearoff=False, font=menu_font)
        file_menu.add_command(label="Load...", command=self.on_load_session_clicked, font=menu_font)
        # "accelerator" is display-only (the menu label's own right-aligned hint text) -- Tk
        # never wires it up as an actual key binding, so bind_all below is what makes Ctrl+S
        # really work. command=self._on_control_s, not self.on_save_session_clicked directly
        # (2026-10-01, explicit bug report: "in Viewer view, choose File > Save As should try
        # to save the currently loaded file, not the one in Inflater mode") -- _on_control_s
        # already dispatches by view_mode_var exactly this way (Viewer's own
        # _on_viewer_save_clicked vs. Inflater's on_save_session_clicked), the menu item had
        # just never been routed through it.
        file_menu.add_command(label="Save...", command=self._on_control_s,
                               accelerator="Ctrl+S", font=menu_font)
        menubar.add_cascade(label="File", menu=file_menu)
        run_menu = tk.Menu(menubar, tearoff=False, font=menu_font)
        run_menu.add_command(label="Run All", command=self.on_run_all_clicked, font=menu_font)
        # Debug All (2026-10-01, explicit): same unattended run through every net as Run All,
        # except it never saves results and pauses after each net for the Right arrow key
        # (see on_debug_all_clicked) -- only meaningful, and only enabled, in debug mode.
        run_menu.add_command(label="Debug All", command=self.on_debug_all_clicked, font=menu_font)
        menubar.add_cascade(label="Run", menu=run_menu)
        # Run All is disabled while Viewer mode is active (2026-10-01, explicit: "Run All
        # should be disabled in this view") -- it iterates every shipped net through the
        # Inflater pipeline, which has nothing to do with whatever Viewer mode is showing.
        # Debug All is additionally disabled outside debug mode (see _update_run_menu_state).
        self._run_menu = run_menu
        self._run_all_menu_index = run_menu.index("Run All")
        self._debug_all_menu_index = run_menu.index("Debug All")
        self._update_run_menu_state()
        # Edit > Undo/Redo (2026-10-01, explicit: "Put Undo/Redo in an Edit menu... it should
        # apply to polyhedron_inflater too (in both views)") -- _on_edit_undo/_on_edit_redo
        # dispatch to whichever view is actually showing (self.view_mode_var), same pattern
        # _on_control_s already uses for Ctrl+S. self.viewer doesn't exist yet at this point in
        # __init__ (built further down) -- fine, since these are only ever CALLED later, same
        # "lazy self.viewer reference" already used by _on_key_d below.
        edit_menu = tk.Menu(menubar, tearoff=False, font=menu_font)
        edit_menu.add_command(label="Undo", command=self._on_edit_undo,
                               accelerator="Ctrl+Z", font=menu_font)
        edit_menu.add_command(label="Redo", command=self._on_edit_redo,
                               accelerator="Ctrl+Y", font=menu_font)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        # Colour > Polygon-specific/Multi-colour (radio, mutually exclusive)/Randomize
        # (2026-10-01, explicit: "add a Colour menu"). Polygon-specific is this app's existing
        # per-Polygon-Fold-group coloring (_face_colors_by_group); Multi-colour is a NEW mode --
        # one random color per individual base face, from the same FACE_COLORS palette, chosen
        # to avoid matching an adjacent face's color where possible (_apply_color_mode/
        # logic.coloring.random_face_colors). Randomize re-rolls Multi-colour's own colors; kept
        # enabled only while Multi-colour is selected (_update_colour_menu_state) -- it has
        # nothing to do in Polygon-specific mode, which has no random element to reroll.
        # P/M/R keyboard shortcuts (2026-10-01, explicit: "let P, M, R be the keyboard
        # shortcuts for Polygon-specific, Multi-colour, and Randomize") -- accelerator= is
        # display-only, same convention as every other accelerator label here; the bind_all
        # calls near the end of this method are what actually make the keys work.
        colour_menu = tk.Menu(menubar, tearoff=False, font=menu_font)
        colour_menu.add_radiobutton(label="Polygon-specific", variable=self.color_mode_var,
                                     value="polygon", command=self._on_color_mode_changed,
                                     accelerator="P", font=menu_font)
        colour_menu.add_radiobutton(label="Multi-colour", variable=self.color_mode_var,
                                     value="multi", command=self._on_color_mode_changed,
                                     accelerator="M", font=menu_font)
        colour_menu.add_separator()
        colour_menu.add_command(label="Randomize", command=self._on_randomize_colors_clicked,
                                 accelerator="R", font=menu_font)
        menubar.add_cascade(label="Colour", menu=colour_menu)
        self._colour_menu = colour_menu
        self._randomize_menu_index = colour_menu.index("Randomize")
        self._update_colour_menu_state()
        # Inflater (default) is this app's own existing UI; Viewer is the read-only .hippo
        # browser (see _build_hippo_viewer_pane) -- a plain radiobutton pair, not separate
        # windows, so switching is instant and keeps both panes' own state alive underneath.
        view_menu = tk.Menu(menubar, tearoff=False, font=menu_font)
        view_menu.add_radiobutton(label="Inflater", variable=self.view_mode_var,
                                   value="inflater", command=self._on_view_mode_changed,
                                   font=menu_font)
        view_menu.add_radiobutton(label="Viewer", variable=self.view_mode_var,
                                   value="viewer", command=self._on_view_mode_changed,
                                   font=menu_font)
        menubar.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menubar)
        # Both cases bound since a held Shift/Caps Lock reports the keysym as uppercase "S" --
        # Control itself doesn't shift letter case the way it does on some platforms/layouts.
        # bind_all (not bound to one widget) so it works regardless of which widget has focus,
        # same as the "d" debug-mode toggle below. Dispatches by view_mode_var since Ctrl+S
        # means "save the current .hippo file" in Viewer mode, not "save an Inflater session".
        self.root.bind_all("<Control-s>", lambda event: self._on_control_s())
        self.root.bind_all("<Control-S>", lambda event: self._on_control_s())
        # Edit > Undo/Redo (2026-10-01, explicit) -- same dispatch-by-view_mode_var/bind_all
        # pattern as Ctrl+S above. Bound here (ONE place) rather than separately inside
        # ViewerPane's own __init__ too -- Tk's bind_all only keeps the LAST binding registered
        # for a given sequence+tag, so two independent bind_all calls for "<Control-z>" would
        # silently fight over which one actually fires; see ViewerPane.__init__'s own comment
        # where its half of this used to live.
        self.root.bind_all("<Control-z>", lambda event: self._on_edit_undo())
        self.root.bind_all("<Control-Z>", lambda event: self._on_edit_undo())
        self.root.bind_all("<Control-y>", lambda event: self._on_edit_redo())
        self.root.bind_all("<Control-Y>", lambda event: self._on_edit_redo())
        # Colour > Polygon-specific/Multi-colour/Randomize (2026-10-01, explicit: "let P, M, R
        # be the keyboard shortcuts..."). Both cases bound (no Ctrl involved here, so Shift
        # alone produces the uppercase keysym) -- same reasoning as every other plain-letter
        # shortcut in this app/interactive_builder_app (d/f/h/v/j/m there). _on_color_mode_key
        # dispatches through _on_color_mode_changed exactly as the menu's own radiobutton click
        # would (including its own Viewer-vs-Inflater dispatch).
        self.root.bind_all("<KeyPress-p>", lambda event: self._on_color_mode_key("polygon"))
        self.root.bind_all("<KeyPress-P>", lambda event: self._on_color_mode_key("polygon"))
        self.root.bind_all("<KeyPress-m>", lambda event: self._on_color_mode_key("multi"))
        self.root.bind_all("<KeyPress-M>", lambda event: self._on_color_mode_key("multi"))
        self.root.bind_all("<KeyPress-r>", lambda event: self._on_randomize_colors_clicked())
        self.root.bind_all("<KeyPress-R>", lambda event: self._on_randomize_colors_clicked())

    def _on_color_mode_key(self, mode):
        """P/M keyboard shortcuts -- sets color_mode_var then reuses _on_color_mode_changed
        exactly as the Colour menu's own radiobutton click would (same undo-push/Viewer-vs-
        Inflater dispatch, no separate logic needed here)."""
        self.color_mode_var.set(mode)
        self._on_color_mode_changed()

    def _on_key_d(self, event=None):
        """"d" dispatches by view_mode_var -- "next file" in Viewer mode (2026-09-30,
        explicit), debug-mode toggle (unchanged) otherwise."""
        if self.view_mode_var.get() == "viewer":
            self.viewer._on_viewer_next_clicked()
        else:
            self._on_toggle_debug_mode(event)

    def _on_toggle_debug_mode(self, _event=None):
        self.debug_mode = not self.debug_mode
        self._apply_mode_visibility()
        self._refit_window_height()
        self._update_run_menu_state()

    # ---- Colour menu (2026-10-01, explicit: "add a Colour menu") ----

    def _on_color_mode_changed(self):
        """Colour > Polygon-specific/Multi-colour radiobutton command -- dispatches by
        view_mode_var (2026-10-01, explicit: "colour changes should apply in Viewer mode as
        well, and they should factor into the undo/redo stack"), same pattern _on_control_s/
        _on_edit_undo already use: Viewer mode's own _on_viewer_color_mode_changed operates on
        the CURRENTLY VIEWED file instead of this view's live net. _apply_color_mode (Inflater's
        own path, below) lazily generates Multi-colour's own colors the FIRST time they're
        needed for this net (none yet, or a stale list left over from a net with a different
        face count) -- NOT every time Multi-colour is RE-selected, so toggling back and forth
        without ever hitting Randomize keeps showing the SAME colors each time (explicit: "if
        the user is toggling... but they haven't selected Randomize, then the colours used in
        Multi-colour shouldn't change every time we toggle back").

        Undoable (2026-10-01, explicit: "the undo/redo stack applies to colours...") -- pushes
        an undo snapshot whose own "color_mode" field is OVERRIDDEN to self._last_color_mode
        (the value from right before this click), since by the time a Tk Radiobutton's own
        `command` fires, its `variable` has ALREADY been set to the new value --
        self._inflater_snapshot() alone would otherwise capture the new mode as if it were the
        "before" state. Snapshotted BEFORE _apply_color_mode runs, not after (2026-10-01, fix
        for a bug caught while building Viewer mode's own identical feature): _apply_color_mode
        lazily GENERATES self.multi_colors the first time Multi-colour is ever selected for this
        net, so snapshotting afterward would capture those freshly-generated colors as if they
        were already "the before state" -- undoing back out of Multi-colour would then leave
        multi_colors non-None (and the net spuriously flagged dirty on a subsequent save) even
        though it was genuinely None before this click. Only pushes when the mode actually
        changed."""
        new_mode = self.color_mode_var.get()
        if self.view_mode_var.get() == "viewer":
            self.viewer._on_viewer_color_mode_changed(new_mode)
            return
        old_mode = self._last_color_mode
        if new_mode != old_mode:
            snap = self._inflater_snapshot()
            snap["color_mode"] = old_mode
        else:
            snap = None
        self._apply_color_mode()
        self._update_colour_menu_state()
        if snap is not None:
            self._inflater_push_undo(snap)
        self._last_color_mode = new_mode
        if self.base_faces is not None:
            self.draw()

    def _on_randomize_colors_clicked(self):
        """Colour > Randomize -- dispatches by view_mode_var, same pattern as
        _on_color_mode_changed above. Inflater mode's own path (below) re-rolls Multi-colour's
        own per-base-face colors from scratch; a no-op outside Multi-colour mode (the menu item
        is disabled then -- see _update_colour_menu_state) or before any net is loaded. Undoable
        (2026-10-01, explicit) -- an ordinary push right before the actual color change
        (nothing's mutated self.multi_colors yet at this point, unlike _on_color_mode_changed's
        trickier case, so the plain automatic "before" snapshot is already correct)."""
        if self.view_mode_var.get() == "viewer":
            self.viewer._on_viewer_randomize_colors_clicked()
            return
        if self.color_mode_var.get() != "multi" or self.base_faces is None:
            return
        self._inflater_push_undo(self._inflater_snapshot())
        self._regenerate_multi_colors()
        self._apply_color_mode()
        self.draw()

    def _regenerate_multi_colors(self):
        self.multi_colors, _, _ = _random_face_colors_by_group(
            self.base_faces, self.base_face_edge_ids, self._source_polygon_id, random.Random())

    def _apply_color_mode(self):
        """Recomputes self.colors/self.color_by_group/self.group_of_base_face for
        self.color_mode_var's current value -- the one place on_select_net/
        on_load_session_clicked and the Colour menu's own handlers all go through, so every
        caller sees the same mode-dependent coloring applied consistently. "multi" lazily
        (re)generates self.multi_colors first if it's missing or stale (wrong length for the
        current net -- e.g. right after a fresh on_select_net, or a session loaded with no
        saved face_colors), then assigns it directly -- one color per Polygon-Fold GROUP
        (2026-10-01, bug fix: was one color per individual base face, see
        random_face_colors_by_group's own docstring for why that changed), same group_of_base_face
        _draw_level_panel's existing per-group add_mesh grouping already uses for Polygon-specific
        mode. A no-op if no net is loaded yet."""
        if self.base_faces is None:
            return
        if self.color_mode_var.get() == "multi":
            if self.multi_colors is None or len(self.multi_colors) != len(self.base_faces):
                self._regenerate_multi_colors()
            self.colors = list(self.multi_colors)
            self.group_of_base_face = _group_of_face(self.base_faces, self._source_polygon_id)
            self.color_by_group = {}
            for i, g in enumerate(self.group_of_base_face):
                self.color_by_group.setdefault(g, self.colors[i])
        else:
            net_layout = (self._net_file_json or {}).get("net_layout") or []
            n_by_group = _polygon_n_of_group(self._source_polygon_id, net_layout)
            self.colors, self.color_by_group, self.group_of_base_face = _face_colors_by_group(
                self.base_faces, self._source_polygon_id, n_by_group)

    def _update_colour_menu_state(self):
        """Randomize only does something in Multi-colour mode (Polygon-specific has no random
        element to reroll) -- disabled otherwise."""
        state = "normal" if self.color_mode_var.get() == "multi" else "disabled"
        self._colour_menu.entryconfig(self._randomize_menu_index, state=state)

    def _update_run_menu_state(self):
        """Run > Run All only makes sense in Inflater mode -- disabled in Viewer mode
        (2026-10-01, explicit: "Run All should be disabled in this view"), same as Randomize's
        own mode-gated enabled state above. Run > Debug All is additionally gated on debug mode
        itself -- it's a debugging aid (pauses after each net for the Right arrow key), not
        something a release-mode user should see enabled at all. Called from both
        _on_view_mode_changed and _on_toggle_debug_mode, so either toggle alone keeps both
        items' state correct."""
        viewer_active = self.view_mode_var.get() == "viewer"
        self._run_menu.entryconfig(
            self._run_all_menu_index, state="disabled" if viewer_active else "normal")
        # getattr: _build_menu's own initial call runs before self.debug_mode is set (defaults
        # to False there, same as the real default moments later).
        debug_mode = getattr(self, "debug_mode", False)
        self._run_menu.entryconfig(
            self._debug_all_menu_index,
            state="normal" if (debug_mode and not viewer_active) else "disabled")

    # ---- Inflater-view undo/redo (2026-10-01, explicit -- see _on_edit_undo's own docstring) --

    def _inflater_snapshot(self):
        """One Inflater-view undo/redo entry: color_mode/multi_colors (Colour menu) plus the
        shared Level camera's own rotation/zoom/pan -- mirrors ViewerPane's own per-file camera
        snapshot (_viewer_camera_snapshot), just for this view's single live net instead of
        per-file, and with Colour state folded in alongside (this view has no 2D canvas/net
        edits of its own to cover, unlike interactive_inflater_app's equivalent feature -- Colour
        + camera really is everything Inflater mode lets the user change). multi_colors is a
        plain shallow list copy -- every entry's a hex-string color, nothing nested."""
        cam = self._level_camera_state
        return {
            "color_mode": self.color_mode_var.get(),
            "multi_colors": list(self.multi_colors) if self.multi_colors is not None else None,
            "camera": {"rotation": cam["rotation"], "zoom": cam["zoom"], "pan": cam["pan"].copy()},
        }

    def _inflater_apply_snapshot(self, snap):
        """Inverse of _inflater_snapshot -- restores color_mode/multi_colors/camera, then
        recomputes self.colors/color_by_group/group_of_base_face (_apply_color_mode) and
        redraws (draw()) so the restored state is actually visible, same as every other Colour-
        menu/camera-changing call site here already does."""
        self.color_mode_var.set(snap["color_mode"])
        self.multi_colors = list(snap["multi_colors"]) if snap["multi_colors"] is not None else None
        self._last_color_mode = snap["color_mode"]
        cam = self._level_camera_state
        cam["rotation"] = snap["camera"]["rotation"]
        cam["zoom"] = snap["camera"]["zoom"]
        cam["pan"] = snap["camera"]["pan"].copy()
        self._update_colour_menu_state()
        self._apply_color_mode()
        if self.base_faces is not None:
            self.draw()

    def _inflater_push_undo(self, snapshot):
        self._inflater_undo_stack.append(snapshot)
        self._inflater_redo_stack.clear()

    def _inflater_commit_gesture_undo(self):
        """Pushes ONE undo step for a just-finished camera drag/pan gesture, captured at its
        START (_on_level_drag_start/_on_level_pan_start) rather than per motion tick -- and only
        if the camera actually ended up different, so a click-without-moving leaves no undo
        entry. Mirrors ViewerPane._viewer_commit_gesture_undo exactly."""
        start = self._inflater_gesture_start_snapshot
        self._inflater_gesture_start_snapshot = None
        if start is None:
            return
        cam = self._level_camera_state
        start_cam = start["camera"]
        changed = (cam["zoom"] != start_cam["zoom"]
                   or not np.allclose(cam["pan"], start_cam["pan"])
                   or not np.allclose(cam["rotation"].as_quat(), start_cam["rotation"].as_quat()))
        if changed:
            self._inflater_push_undo(start)

    def _on_inflater_undo(self):
        if not self._inflater_undo_stack:
            return
        current = self._inflater_snapshot()
        previous = self._inflater_undo_stack.pop()
        self._inflater_redo_stack.append(current)
        self._inflater_apply_snapshot(previous)

    def _on_inflater_redo(self):
        if not self._inflater_redo_stack:
            return
        current = self._inflater_snapshot()
        following = self._inflater_redo_stack.pop()
        self._inflater_undo_stack.append(current)
        self._inflater_apply_snapshot(following)

    def _update_window_title(self):
        """The window's own title: APP_TITLE, plus " (debug mode)" while debug mode is on, plus
        " (m/n)" while Run All is working through the net list (see on_run_all_clicked) --
        e.g. "...  (debug mode) (2/11)" if both apply at once. The single place either suffix
        gets composed, so toggling debug mode mid-Run-All (or vice versa) never drops the
        other one. Dispatches to _update_viewer_title instead while View > Viewer is active --
        a completely different title scheme (the CURRENT .hippo file's own name, not this
        app's), see that method's own docstring."""
        if self.view_mode_var.get() == "viewer":
            self.viewer._update_viewer_title()
            return
        suffix = " (debug mode)" if self.debug_mode else ""
        if self._run_all_active:
            suffix += f" ({self._run_all_index + 1}/{len(self._run_all_paths)})"
        self.root.title(f"{APP_TITLE}{suffix}")

    def _apply_mode_visibility(self):
        """Main differences between the two modes: whether the steps-vs-convergence radio row
        (plus Show normals/Show repulsive forces) is shown, and whether the Convergence
        History table's "Max Stretch %" column is shown (all columns stay DEFINED in both
        modes, just hidden per mode, so no data is lost switching back and forth). Forces the
        steps choice back to "convergence" and Show normals/Show repulsive forces off when
        leaving debug mode."""
        self._update_window_title()
        self.history_tree.config(
            displaycolumns="#all" if self.debug_mode else self._release_mode_history_columns)
        # Changing displaycolumns doesn't resize the widget itself, so no <Configure> fires --
        # re-run the same proportional rescale by hand against the table's current width.
        self._rescale_history_columns(self.history_tree.winfo_width())
        if self.debug_mode:
            self.mode_row.pack(fill=tk.X, pady=(8, 0))
            self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
            # Sliders packed BEFORE their own level's button so they land below it (same
            # bottom-stacking order as __init__) -- both debug-only, same as the buttons.
            for level, slider in self.level_replay_sliders.items():
                slider.pack(side=tk.BOTTOM, in_=self.level_frames[level])
            for button in self.level_action_buttons.values():
                button.pack(side=tk.BOTTOM)
        else:
            self.mode_row.pack_forget()
            self.iterate_mode_var.set("convergence")
            redraw_needed = False
            if self.show_normals_var.get():
                self.show_normals_var.set(False)
                redraw_needed = True
            if self.show_vertex_normals_var.get():
                self.show_vertex_normals_var.set(False)
                redraw_needed = True
            if self.show_repulsive_forces_var.get():
                self.show_repulsive_forces_var.set(False)
                redraw_needed = True
            if redraw_needed and self.faces is not None:  # nothing to redraw before a net's ever loaded
                self.draw()
            self.status_frame.pack_forget()  # whole frame, not just its text
            # Per-level Relax/Inflate/Subdivide/Stop buttons are debug-only too (release mode
            # uses Auto): hidden here, NOT destroyed, so every other
            # method that reads/writes their text/state (_update_level_
            # action_buttons, _set_level_action_button_running, _auto_
            # step's own driving calls to on_relax_clicked/on_inflate_
            # clicked/on_subdivide_clicked) keeps working exactly as
            # before regardless of mode -- Auto never invokes a button
            # widget directly, only the same plain methods a manual click
            # would call, so it's unaffected by these being unpacked.
            for button in self.level_action_buttons.values():
                button.pack_forget()
            for slider in self.level_replay_sliders.values():
                slider.pack_forget()

    def _refit_window_height(self):
        """Re-fits the window's height to whatever's actually visible right now -- without
        this, release mode would keep debug mode's own taller height, leaving dead space below
        the now-hidden mode_row/status_frame/per-level buttons. Called from three places,
        every one a genuine mode change (or the equivalent first-time framing) rather than
        routine net switching: once at the end of __init__ (after on_select_net's own draw()
        call), from _on_toggle_debug_mode, and from on_load_session_clicked's own tail (its
        debug_mode can differ from whatever was showing before the load). Deliberately NOT
        called from plain on_select_net -- picking a different net shouldn't fight a manual
        resize the user already made; only an actual mode change re-fits the window.

        NOT called directly from _apply_mode_visibility itself, or from
        inside __init__ before the first draw() -- a "Level N" panel's
        own image Label has essentially ZERO natural height before its
        first PhotoImage is set (self.level_photos[level] starts None),
        so measuring reqheight that early would fit the window to a
        too-short, pre-image layout and squeeze every panel once images
        actually appear (see LEVEL_PANEL_SIZE's own __init__ comment on
        exactly that failure mode) -- by the time _on_toggle_debug_mode
        can even fire, on_select_net's own startup call has already run.
        update_idletasks() forces Tk to actually recompute every widget's
        geometry from whatever pack/pack_forget calls happened since the
        last idle cycle -- winfo_reqheight() would otherwise still
        reflect a stale layout. Width is read back from the window's own
        CURRENT actual size (winfo_width()), not recomputed -- it never
        changes between modes or net selections, only height does."""
        self.root.update_idletasks()
        self.root.geometry(f"{self.root.winfo_width()}x{self.root.winfo_reqheight()}")

    def _set_status(self, text, kind="info"):
        # "success" is always dropped -- the per-level button states and Convergence History
        # table already show it. Release mode also drops routine "info" narration for the
        # same reason -- the live panel redraw, button state, and history row already say all
        # of it; debug mode keeps "info" since it's for someone working on this app, not an
        # end user. "warn"/"error" still get SET here in both modes (meaningful internal
        # state), but release mode never shows them -- the whole status_frame is unpacked
        # there (_apply_mode_visibility).
        if kind == "success" or (kind == "info" and not self.debug_mode):
            text = ""
        self.status_var.set(text)
        self.status_label.configure(foreground=STATUS_COLORS.get(kind, ""))

    # ---- Level panels (PyVista/VTK -- see LEVEL_PANEL_SIZE's comment) ----

    def _build_level_pv_panel(self, level, level_frame):
        """Builds one "Level N" panel: a plain Tkinter title Label (NOT
        text drawn inside the rendered image -- see _render_level_pv's
        own Design notes for why that clipped) above an image Label
        showing an off-screen-rendered PyVista image, rather than a live
        interactive VTK widget -- keeps this app on a single interaction
        toolkit (Tkinter native mouse bindings reimplement just the
        click-drag-to-rotate behavior mplot3d used to give the old
        matplotlib panels for free, see _on_level_drag_start/_motion/_end
        below) instead of also embedding VTK's own widget/event loop."""
        ttk.Label(level_frame, text=f"Level {level}", font=self.LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        # Reserved status-message strip (see _set_level_message's own
        # comment) -- built for EVERY level, including 0 (which never
        # Every "Level N" panel reserves the same fixed message-strip height regardless of
        # whether its own message is in use right now (skipping it for Level 0 would leave its
        # frame one strip shorter than the others -- same cross-panel height-mismatch failure
        # mode as the "Computing..." placeholder). Packed BEFORE the image label, at
        # side=tk.BOTTOM, so it claims its own bottom strip first; the image label's
        # fill=tk.BOTH/expand=True fills the rest. `padx` left at 0 -- _set_level_message
        # computes and applies it per-message.
        message_label = tk.Label(level_frame, text="", anchor=tk.W, bg=PLOT_THEME["bg"],
                                  fg=PLOT_THEME["fg"], font=self.LEVEL_MESSAGE_FONT)
        message_label.pack(side=tk.BOTTOM, fill=tk.X)
        self.level_message_labels[level] = message_label
        label = tk.Label(level_frame, bg=PLOT_THEME["bg"], bd=0)
        label.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        plotter = pv.Plotter(off_screen=True, window_size=list(_level_panel_size(level)))
        plotter.set_background(PLOT_THEME["bg"])
        _setup_plotter_lighting(plotter)
        self.level_labels[level] = label
        self._level_of_label[label] = level
        self.level_plotters[level] = plotter
        self.level_photos[level] = None  # keeps a reference alive -- Tk drops a GC'd PhotoImage
        self._level_center[level] = np.zeros(3)
        self._level_half[level] = 1.0
        label.bind("<ButtonPress-1>", self._on_level_drag_start)
        label.bind("<B1-Motion>", self._on_level_motion)
        label.bind("<ButtonRelease-1>", self._on_level_drag_end)
        # Right-click-drag pans (self.level_pan); middle-click resets to zero. No per-panel
        # state to capture at press time (a pan drag needs no per-panel scale, unlike
        # rotate/zoom), so every level's label shares the same three level-agnostic handlers.
        label.bind("<ButtonPress-3>", self._on_level_pan_start)
        label.bind("<B3-Motion>", self._on_level_pan_motion)
        label.bind("<ButtonRelease-3>", self._on_level_pan_end)
        label.bind("<Button-2>", self._on_level_pan_reset)
        # Windows/macOS deliver <MouseWheel> with event.delta; Linux (X11) delivers wheel
        # motion as Button-4/Button-5 clicks instead -- binding all three covers every platform.
        label.bind("<MouseWheel>", self._on_level_scroll)
        label.bind("<Button-4>", self._on_level_scroll)
        label.bind("<Button-5>", self._on_level_scroll)

    def _level_camera(self, level):
        """The mutable camera-state dict (`{"rotation", "zoom", "pan"}`) -- ONE shared dict for
        every level (0-3, see this state's own init comment). `level` is accepted, and unused,
        purely so every caller keeps a uniform "which level's camera do I need" call shape.
        Callers mutate the returned dict's keys in place rather than reassigning
        self._level_camera_state themselves."""
        return self._level_camera_state

    def _camera_group_levels(self, level):
        """Every level panel sharing the camera state -- every built level (`level` is
        accepted, and unused, for the same uniform-call-shape reason as _level_camera)."""
        return list(self.level_plotters)

    def _render_camera_group(self, level):
        """Re-renders every panel in `level`'s own camera group (not every level panel) --
        what a drag/pan/scroll on one group's panel should refresh."""
        for lvl in self._camera_group_levels(level):
            self._render_level_pv(lvl)

    def _on_level_drag_start(self, event):
        self._level_dragging = True
        self._level_last_xy = (event.x, event.y)
        self._level_drag_group_level = self._level_of_label.get(event.widget, 1)
        # Undo/redo (2026-10-01, explicit) -- captured at gesture START, pushed at gesture END
        # (_on_level_drag_end) only if the camera actually ended up different; see
        # _inflater_commit_gesture_undo's own docstring.
        self._inflater_gesture_start_snapshot = self._inflater_snapshot()

    def _on_level_motion(self, event):
        """Left-click-drag on a level panel rotates that panel's own camera group's
        orientation (self._level_drag_group_level, set at press time) and re-renders every
        panel in that same group (_render_camera_group). This app's own analogue of mplot3d's
        drag rotation, reimplemented since PyVista/VTK panels are plain images, not
        interactive widgets. Re-rendering the whole group costs ~30ms, well within real-time
        feel.

        This is a free trackball rotation (utils.camera_trackball.rotate -- "up"/"right" read
        off the group's rotation as it currently is, not re-pinned to world +z every frame, so
        there's no pole for elevation to lock up near, and no clamp needed)."""
        if not self._level_dragging or self._level_last_xy is None:
            return
        cam = self._level_camera(self._level_drag_group_level)
        last_x, last_y = self._level_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        cam["rotation"] = _camera_rotate(cam["rotation"], dx, dy, LEVEL_DRAG_SENSITIVITY)
        self._level_last_xy = (event.x, event.y)
        self._render_camera_group(self._level_drag_group_level)

    def _on_level_drag_end(self, event):
        self._level_dragging = False
        self._level_last_xy = None
        # One last explicit render as a safety net, in case the button release didn't come
        # with its own trailing motion event (_on_level_motion already keeps the group live
        # during the drag itself).
        if self._level_drag_group_level is not None:
            self._render_camera_group(self._level_drag_group_level)
        self._level_drag_group_level = None
        self._inflater_commit_gesture_undo()

    def _on_level_pan_start(self, event):
        self._level_panning = True
        self._level_pan_last_xy = (event.x, event.y)
        self._level_pan_group_level = self._level_of_label.get(event.widget, 1)
        # Undo/redo (2026-10-01, explicit) -- same gesture-start/commit pattern as
        # _on_level_drag_start/_on_level_drag_end above.
        self._inflater_gesture_start_snapshot = self._inflater_snapshot()

    def _on_level_pan_motion(self, event):
        """Right-click-drag on a level panel translates that panel's own camera group's pan
        (self._level_pan_group_level, set at press time; the pan value is a 2D NDC offset
        applied via vtkCamera's own SetWindowCenter in _render_level_pv -- NDC rather than a
        3D world-space offset, which would desync panels of different scale) and re-renders
        every panel in that group -- pan's analogue of _on_level_motion's rotation drag. Needs
        no per-panel scale since NDC is resolution/scale-independent; converting the drag
        through the one fixed LEVEL_PANEL_SIZE makes the shift identical across the group.

        Sign convention: SetWindowCenter(x, y) moves the image LEFT for x=+1 (half the panel
        width) and DOWN for y=+1 (half the panel height) -- so a rightward drag needs a
        negative x term, a downward drag (screen y already growing downward) a positive y
        term."""
        if not self._level_panning or self._level_pan_last_xy is None:
            return
        cam = self._level_camera(self._level_pan_group_level)
        last_x, last_y = self._level_pan_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        panel_width, panel_height = _level_panel_size(self._level_pan_group_level)
        cam["pan"] = _camera_pan(cam["pan"], dx, dy, panel_width, panel_height)
        self._level_pan_last_xy = (event.x, event.y)
        self._render_camera_group(self._level_pan_group_level)

    def _on_level_pan_end(self, event):
        self._level_panning = False
        self._level_pan_last_xy = None
        # Same safety-net rationale as _on_level_drag_end.
        if self._level_pan_group_level is not None:
            self._render_camera_group(self._level_pan_group_level)
        self._level_pan_group_level = None
        self._inflater_commit_gesture_undo()

    def _on_level_pan_reset(self, event=None):
        """Middle-click on a level panel resets the shared camera's pan/zoom/rotation
        together, back to defaults -- every level panel, since they all now share one camera.
        Rotation resets through _initial_level_rotation() (the same starting quaternion
        __init__ builds), not plain identity, since the default view is deliberately
        non-axis-aligned. Undoable (2026-10-01, explicit) -- pushed directly, same "already one
        discrete action" reasoning _on_level_scroll's own push uses."""
        level = self._level_of_label.get(event.widget, 1) if event is not None else 1
        cam = self._level_camera(level)
        self._inflater_push_undo(self._inflater_snapshot())
        cam["pan"] = np.zeros(2)
        cam["zoom"] = 1.0
        cam["rotation"] = _initial_level_rotation()
        self._render_camera_group(level)

    def _on_level_scroll(self, event):
        """Mouse-wheel-scroll on a level panel zooms the shared camera and re-renders every
        level panel (they all zoom together now). event.num is Button-4/5 on X11 (no
        event.delta there); event.delta is Windows/macOS's signed notch count (positive delta
        zooms in). Undoable (2026-10-01, explicit) -- pushed directly, one undo step per wheel
        tick (already a single discrete action, unlike a drag gesture's many motion ticks)."""
        level = self._level_of_label.get(event.widget)
        if level is None:
            return
        cam = self._level_camera(level)
        self._inflater_push_undo(self._inflater_snapshot())
        zoom_in = not (getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0)
        cam["zoom"] = _camera_zoom(cam["zoom"], zoom_in, LEVEL_ZOOM_STEP, LEVEL_ZOOM_MIN,
                                    LEVEL_ZOOM_MAX)
        self._render_camera_group(level)

    def _render_all_level_panels(self):
        for level in self.level_plotters:
            self._render_level_pv(level)

    def _draw_level_panel(self, level, faces, positions, face_of_fine):
        """One "Level N" panel, drawn every call from whatever faces/positions/face_of_fine
        draw() passes it (live, frozen snapshot, or all-None for "not reached yet"). Faces are
        always triangles from Level 1 on, so no fan/n-gon handling is needed. Colors every
        face by its original base face (`face_of_fine`) as per-cell RGB, one add_mesh call
        per group (PyVista/VTK's depth buffer handles occlusion correctly regardless of face
        count or convexity).

        Debug mode's "Show face normals" toggle also draws each triangle's own outward normal
        as a line segment from its centroid, in NORMAL_COLOR, scaled to NORMAL_LENGTH_FRACTION
        of that triangle's mean edge length (current, not rest, geometry) so it always reads
        as "about half an edge long". "Show vertex normals" is the same idea per-vertex
        (averaged from its touching faces) -- catches a vertex where the touching faces
        disagree, which the per-face version alone can miss. "Show repulsive forces" draws
        each repulsive vertex's (see _repulsion_vertex_ids) own CURRENT repulsion_force
        direction the same way (REPULSION_FORCE_COLOR, same length convention -- direction
        only, not the force's own actual magnitude)."""
        plotter = self.level_plotters[level]
        plotter.clear()
        _setup_plotter_lighting(plotter)
        if faces is not None:
            vertex_ids = sorted(positions)
            idx = {v: i for i, v in enumerate(vertex_ids)}
            points = np.array([positions[v] for v in vertex_ids])
            # One add_mesh call per GROUP, not one for the whole mesh with a per-cell "colors"
            # array -- wireframe edges are the color halfway between white and the polygon
            # color, which only makes sense as a per-face edge color, and VTK's edge_color is
            # one uniform color per call. Still one scene/depth buffer (plotter.clear() above,
            # not between these calls), so cross-group occlusion still works.
            # Grouped by self.group_of_base_face, not raw base_face index -- every triangle
            # from one Polygon-Fold-subdivided source polygon (interactive_builder_app's own
            # "source_polygon_id") shares its color and add_mesh call, reading as one
            # uniformly-colored/outlined polygon at every level.
            groups_present = sorted(set(self.group_of_base_face[bf] for bf in set(face_of_fine)))
            for group in groups_present:
                face_color = self.color_by_group[group]
                group_faces = [f for f, bf in zip(faces, face_of_fine)
                               if self.group_of_base_face[bf] == group]
                face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
                mesh = pv.PolyData(points, face_conn)
                plotter.add_mesh(mesh, color=face_color, show_edges=True,
                                  edge_color=_midpoint_color("white", face_color),
                                  line_width=SUBDIVISION_EDGE_WIDTH,
                                  backface_params=dict(color=_darken_color(face_color)),
                                  smooth_shading=SMOOTH_SHADING, ambient=MATERIAL_AMBIENT,
                                  diffuse=MATERIAL_DIFFUSE, specular=MATERIAL_SPECULAR,
                                  specular_power=MATERIAL_SPECULAR_POWER)

            if self.show_normals_var.get():
                # Skips every OPEN triangle (see _is_open_of_fine/_pressure_exclude_faces) --
                # those genuinely feel NO pressure force at all, so showing a face normal on
                # one would misleadingly read as "this face is being pushed outward" when it
                # isn't. Reuses the exact same is_open
                # flag stretchy_mesh._face_index_groups itself excludes that triangle with, not
                # an independent display-only check that could drift out of sync with it.
                is_open = self._is_open_of_fine(level)
                starts, ends = [], []
                for (a, b, c), face_is_open in zip(faces, is_open):
                    if face_is_open:
                        continue
                    pa, pb, pc = positions[a], positions[b], positions[c]
                    normal = np.cross(pb - pa, pc - pa)
                    normal_len = np.linalg.norm(normal)
                    if normal_len < 1e-12:
                        continue
                    centroid = (pa + pb + pc) / 3.0
                    edge_len = (np.linalg.norm(pb - pa) + np.linalg.norm(pc - pb)
                                + np.linalg.norm(pa - pc)) / 3.0
                    starts.append(centroid)
                    ends.append(centroid + normal / normal_len * edge_len * NORMAL_LENGTH_FRACTION)
                if starts:
                    segment_points = np.empty((2 * len(starts), 3))
                    segment_points[0::2] = starts
                    segment_points[1::2] = ends
                    plotter.add_lines(segment_points, color=NORMAL_COLOR, width=2.0)

            if self.show_vertex_normals_var.get():
                starts, ends = [], []
                for v, (unit_normal, mean_edge_len) in _vertex_normals(faces, positions).items():
                    starts.append(positions[v])
                    ends.append(positions[v] + unit_normal * mean_edge_len * NORMAL_LENGTH_FRACTION)
                if starts:
                    segment_points = np.empty((2 * len(starts), 3))
                    segment_points[0::2] = starts
                    segment_points[1::2] = ends
                    plotter.add_lines(segment_points, color=VERTEX_NORMAL_COLOR, width=2.0)

            if self.show_repulsive_forces_var.get():
                # Scaled by ACTUAL relative magnitude, NOT direction-only at a fixed length
                # (unlike "Show normals" above) -- a unit-length arrow would look identical for
                # a full-strength vertex and one weakened by _repulsion_vertex_multipliers,
                # defeating the entire point of this toggle. The STRONGEST vertex drawn here
                # gets the usual EDGE_LENGTH*NORMAL_LENGTH_FRACTION reference length, every
                # other one scaled down proportionally against it -- absolute force magnitude
                # depends heavily on inter-vertex distance, which varies a lot net to net, so
                # normalizing against "the strongest one currently on screen" is what actually
                # keeps a weakened vertex's own arrow visibly shorter regardless of that scale.
                # Computed via the SAME repulsion_force/_repulsion_vertex_ids/
                # _repulsion_vertex_multipliers this level's own Inflate call actually uses.
                repulsion_ids = [v for v in self._repulsion_vertex_ids() if v in idx]
                if repulsion_ids:
                    rep_indices = [idx[v] for v in repulsion_ids]
                    mult_by_id = self._repulsion_vertex_multipliers() or {}
                    rep_mults = [mult_by_id.get(v, 1.0) for v in repulsion_ids]
                    forces = repulsion_force(points, strength=REPULSION_STRENGTH,
                                              indices=rep_indices, vertex_multipliers=rep_mults)
                    force_lens = {v: np.linalg.norm(forces[idx[v]]) for v in repulsion_ids}
                    max_len = max(force_lens.values(), default=0.0)
                    starts, ends = [], []
                    if max_len >= 1e-12:
                        for v in repulsion_ids:
                            force_len = force_lens[v]
                            if force_len < 1e-12:
                                continue
                            force_vec = forces[idx[v]]
                            starts.append(positions[v])
                            ends.append(positions[v] + force_vec / max_len
                                        * EDGE_LENGTH * NORMAL_LENGTH_FRACTION)
                    if starts:
                        segment_points = np.empty((2 * len(starts), 3))
                        segment_points[0::2] = starts
                        segment_points[1::2] = ends
                        plotter.add_lines(segment_points, color=REPULSION_FORCE_COLOR, width=2.0)

            # Each level fills its own panel to 90% from its own CURRENT bounding box, not a
            # fixed reference framing shared across levels -- the per-level target RMS %
            # tapers down, so the converged mesh's absolute size genuinely shrinks level to
            # level; a fixed camera would just display that shrinkage as "inconsistent
            # sizes". Rotation/pan/zoom stay shared across Levels 1-3 regardless (separate
            # mechanism); only the auto-fit center/half is per-level.
            # `half` is the shape's own bounding-SPHERE radius (largest distance from center
            # to any vertex), not half of the largest single world-axis extent -- a
            # single-axis measure underestimates the true on-screen extent from an oblique
            # angle (the diagonal reaches further than any one axis's half-length), letting
            # renders clip past the edge despite `_level_zoom_fill` claiming "90%". A proper
            # radius bounds the shape from every direction, guaranteed to fit at any
            # rotation. `_render_level_pv`'s aspect handling then makes the panel's narrower
            # dimension exactly `_level_zoom_fill(level)` of the frame, with the taller
            # dimension getting extra slack -- both dimensions end up at most that fraction.
            #
            # `_level_zoom_fill` alone is the single, authoritative fill fraction -- a former
            # second "margin" constant compounded with it and caused >100% clipping.
            self._level_center[level], self._level_half[level] = bounding_sphere(points)
        self._render_level_pv(level)

    def _capture_level_image(self, level):
        """The actual pixels _render_level_pv blits into self.level_labels[level]. Positions an
        orthographic (parallel-projection) camera from `level`'s own
        camera group's rotation at a distance derived from this level's own current bounding
        box (self._level_center/_level_half, set by _draw_level_panel -- necessary since
        neither a pure-spring relax nor a pressure inflation keeps the result near the origin
        or at a familiar scale), and renders off-screen. Parallel rather than perspective
        projection gives every panel fixed, comparable axis-limit-like framing with no
        foreshortening. Returns None while `level` is the one currently showing "Computing..."
        (nothing real to capture yet) or if `level` was never actually drawn at all (no entry
        in self._level_center)."""
        if level == self._computing_level or level not in self._level_center:
            return None
        cam = self._level_camera(level)
        direction = cam["rotation"].apply([1.0, 0.0, 0.0])
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        center, half = self._level_center[level], self._level_half[level]
        distance = half * 4
        plotter = self.level_plotters[level]
        camera = plotter.camera
        camera.parallel_projection = True
        camera.focal_point = tuple(center)
        camera.position = tuple(center + direction * distance)
        # Read straight off the quaternion, not pinned to world (0,0,1) -- a fixed world-up
        # forces elevation into a separate angle that locks up near the poles; letting up
        # rotate freely with the camera is what a quaternion buys.
        camera.up = tuple(up)
        # parallel_scale sets the camera's vertical half-height in world units -- the
        # horizontal half-width it implies is narrower by the window's aspect ratio, which
        # would crop the wider dimension on this portrait-shaped panel if left at exactly
        # `half`. Scaling up by height/width guarantees the full half-extent fits in both
        # directions; dividing by _level_zoom_fill(level) then shrinks the shape within that
        # guaranteed-fitting frame.
        panel_width, panel_height = _level_panel_size(level)
        # cam["zoom"] is a divisor here (like _level_zoom_fill) since parallel_scale is a
        # visible-world-height, not a magnification -- a bigger zoom must shrink parallel_scale.
        camera.parallel_scale = (half * max(1.0, panel_height / panel_width)
                                  / _level_zoom_fill(level) / cam["zoom"])
        # cam["pan"] is applied here, as a pure post-projection viewport shift, rather than by
        # moving focal_point/position -- that way it can't desync between panels of different
        # scale or move a panel's own orbit center out from under a later rotation.
        camera.SetWindowCenter(*cam["pan"])
        plotter.reset_camera_clipping_range()
        # plotter.screenshot() does NOT re-render on a camera-only change by itself -- an
        # explicit render() first is what actually asks VTK to redraw the scene from the
        # camera's current position before screenshot() reads the framebuffer back.
        plotter.render()
        return Image.fromarray(plotter.screenshot(return_img=True))

    def _render_level_pv(self, level):
        """Renders `level`'s own panel (_capture_level_image) and blits the result into
        self.level_labels[level]. Skips entirely (leaving the panel's "Computing..." text
        alone) while `level` is the one currently showing it -- the single choke point every
        caller goes through, so nothing can paint a stale image over the placeholder mid-
        calibration.

        The panel's "Level N" title is a separate Tkinter Label, not drawn into this image --
        a title drawn inside the rendered scene (via plotter.add_text) clips against the
        panel's own top edge, since a VTK text actor's positioning doesn't guarantee it stays
        fully inside the viewport the way a real widget above the image does."""
        image = self._capture_level_image(level)
        if image is None:
            return
        self.level_photos[level] = ImageTk.PhotoImage(image)
        # text="" clears whatever "Computing..." text was last set -- harmless to leave
        # (Label's default compound="none" shows the image over it regardless), but tidier.
        self.level_labels[level].configure(image=self.level_photos[level], text="")

    # ---- "Computing..." placeholder (pressure calibration) ----

    # How often the "Computing" dot-cycle advances (nothing->1->2->3->
    # repeat) -- purely decorative, so any value that reads as "still
    # working" without being distractingly fast is fine.
    COMPUTING_DOT_INTERVAL_MS = 500

    def _set_level_message(self, level, text):
        """Sets `level`'s bottom status message, left-anchored (anchor=tk.W) but with `padx`
        computed here to make this specific `text` land visually centered under the panel --
        true tk.CENTER re-anchors from scratch on every update, so the message's left edge
        would visibly jump every time its length changes, and a single fixed left inset
        doesn't look centered for every message either ("Computing" is much shorter than
        "Replay frame 27 / 93"). Measuring this string's own rendered width
        (self._level_message_font, a real Font object) and computing the inset that would
        actually center it gives the best of both: visually equivalent to true centering, but
        the position only shifts by however much this message's width actually changed since
        the last call."""
        text_width = self._level_message_font.measure(text)
        pad = max(0, (_level_panel_size(level)[0] - text_width) // 2)
        self.level_message_labels[level].configure(text=text, padx=pad)

    def _start_computing_animation(self, level):
        """Blanks `level`'s panel image (plain background, no mesh) and shows an animated
        "Computing..." in its bottom message area while a run is in progress -- Levels 1-3
        (pressure calibration) since most of calibration's several relax_once trials are thrown
        away, so there's no single meaningful shape to show frame-by-frame; Level 0's own Relax
        the same way since 2026-10-01 (explicit: "when it's computing, it should say
        Computing... like the other levels" -- previously stayed live instead, only ever one
        run there, see on_relax_clicked). _render_level_pv skips `level` entirely while
        self._computing_level is set to it, so nothing else can paint over the blank image.

        The blank image is rendered ONCE here, not regenerated every dot-cycle tick -- a flat
        background never changes frame to frame, so only the separate message Label's text
        needs to keep ticking, far cheaper than a PIL image regenerate + PhotoImage
        conversion every 500ms."""
        self._computing_level = level
        self._computing_dots = 0
        blank = Image.new("RGB", _level_panel_size(level), PLOT_THEME["bg"])
        self.level_photos[level] = ImageTk.PhotoImage(blank)
        self.level_labels[level].configure(image=self.level_photos[level])
        self._tick_computing_animation()

    def _tick_computing_animation(self):
        if self._computing_level is None:
            return
        self._set_level_message(self._computing_level, "Computing" + "." * self._computing_dots)
        self._computing_dots = (self._computing_dots + 1) % 4
        self._computing_after_id = self.root.after(
            self.COMPUTING_DOT_INTERVAL_MS, self._tick_computing_animation)

    def _stop_computing_animation(self):
        """Cancels the dot-cycle, clears the message area, and clears self._computing_level --
        _render_level_pv is free to draw that level normally again, but doesn't do so on its
        own; the caller always follows this with either a real draw() or the start of a frame
        replay. Clearing the message here first covers the stopped-during-calibration case,
        which has nothing else to overwrite "Computing..." otherwise."""
        if self._computing_after_id is not None:
            self.root.after_cancel(self._computing_after_id)
            self._computing_after_id = None
        level = self._computing_level
        self._computing_level = None
        if level is not None:
            self._set_level_message(level, "")

    # ---- theme ----

    def _style_2d_axis(self, ax, theme):
        ax.title.set_color(theme["fg"])
        ax.set_axis_off()

    def _apply_plot_theme(self):
        """Recolor the Net figure's chrome to match the fixed dark-only plot theme -- ax.cla()
        (called every draw()) resets this to matplotlib's defaults, so it's re-applied every
        redraw. Every "Level N" panel is PyVista, not matplotlib -- its background/text color
        is set once at panel construction, not re-applied here. Returns the theme dict so
        draw() can reuse its colors."""
        theme = PLOT_THEME
        self.fig_net.patch.set_facecolor(theme["bg"])
        self.ax2d.set_facecolor(theme["bg"])
        self._style_2d_axis(self.ax2d, theme)
        return theme

    def _draw_idle_all(self):
        """The Net panel is matplotlib and needs an explicit idle-redraw
        request; every "Level N" panel already pushed its own freshly
        rendered image straight to its Label inside _render_level_pv, so
        there's nothing further to do for those here."""
        self.canvas_net.draw_idle()

    # ---- net picker ----

    def refresh_net_list(self, keep_selection=True):
        """Rescan data/input/stretchy_nets/ and rebuild the dropdown. Every net starts from a
        cheap, instant random start, so there's no precomputed-vs-not state to flag. Scans
        both "*.json" (hand-authored nets, and any older net predating interactive_builder_
        app's own save extension) and "*.poly" (that app's own current save extension, same
        plain JSON content) -- load_stretchy_mesh/json.load never care about the extension."""
        paths = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json"))
                        + glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.poly")))
        self.label_to_path = {}
        for path in paths:
            # A ".json" and ".poly" sharing the same basename collide here (second one wins) --
            # not handled specially, since the two extensions replace one another per net.
            label = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            self.label_to_path[label] = path

        labels = list(self.label_to_path.keys())
        self.combo["values"] = labels

        previous_path = self.label_to_path.get(self.current_label)
        if keep_selection and previous_path:
            for label, path in self.label_to_path.items():
                if path == previous_path:
                    self.current_label = label
                    break
        else:
            # Default to DEFAULT_NET_BASENAME (cube.poly or cube.json, matched by basename so a
            # save under the other extension doesn't stop it being found) if present, else the
            # first net alphabetically.
            default_label = next(
                (l for l, p in self.label_to_path.items()
                 if os.path.splitext(os.path.basename(p))[0] == DEFAULT_NET_BASENAME), None)
            self.current_label = default_label or (labels[0] if labels else None)

        if self.current_label:
            self.net_var.set(self.current_label)

    def on_select_net(self, event=None):
        chosen = self.net_var.get()
        self.current_label = chosen
        path = self.label_to_path[chosen]
        try:
            faces, self.mesh_name = load_stretchy_mesh(path)
            base_edges, base_face_edge_ids = load_stretchy_mesh_edges(path)
        except ValueError as e:
            self._set_status(str(e), "error")
            self.faces = None
            return

        # A legacy fabric-subdivided net (carrying baked-in "coarse_faces") is loaded at its
        # own coarse_faces -- always level 0 -- rather than its pre-baked fine mesh; "Subdivide"
        # refines it interactively from there instead. An ordinary net has no coarse_faces and
        # its "faces" already are level 0. self_join_split guards a RAW/hand-authored net
        # against a self-joined face -- see net_loading.resolve_base_faces's own docstring.
        legacy_coarse_faces, _, _ = load_fabric_spec(path)
        self.base_faces, self_join_split = net_loading.resolve_base_faces(
            faces, legacy_coarse_faces)
        # The raw parsed file is kept as self._net_file_json, read here up front since
        # self.colors below needs its "source_polygon_id" section, so on_save_session_clicked
        # can embed a full copy of it, letting on_load_session_clicked reproduce this exact
        # layout decision later without the original file needing to still exist on disk.
        with open(path) as f:
            self._net_file_json = json.load(f)
        # base_edges/base_face_edge_ids and "source_polygon_id" are all keyed to the file's own
        # "faces" vertex-id/index space -- only meaningful when self.base_faces IS that same
        # "faces" (the ordinary case); a legacy fabric net's re-derived coarse_faces use a
        # different vertex-id space, and a self-join split changes both the face COUNT and the
        # vertex-id space (a fresh centroid id per split face), so both stay None (the
        # always-safe fallbacks every consumer already has).
        if legacy_coarse_faces is not None or self_join_split:
            base_edges = base_face_edge_ids = None
            source_polygon_id = None
        else:
            source_polygon_id = self._net_file_json.get("source_polygon_id")
        self.base_edges = base_edges
        self.base_face_edge_ids = base_face_edge_ids
        # Only reapply the net's own closed/open target-RMS defaults when the net actually
        # CHANGES, not on every on_select_net call -- on_select_net also re-runs for the SAME
        # net (e.g. on_auto_clicked's own "Run Simulation again after a completed run restarts
        # fresh from Level 0" case), and unconditionally resetting here was wiping out a user's
        # own already-typed Target RMS value on every one of those re-runs. self.current_path
        # (from the PREVIOUS call, not yet overwritten at this point) is None on the very first load, so
        # that first call still gets its defaults applied.
        if getattr(self, "current_path", None) != path:
            self._reset_target_rms_defaults()
        # A freshly-loaded net has no Multi-colour colors of its own yet -- _apply_color_mode
        # (below, after self.base_faces is final) regenerates them on demand if Multi-colour is
        # the active mode; a net with the SAME face count as whatever was loaded before is still
        # treated as fresh here (not worth trying to detect "genuinely the same net" to preserve
        # colors across a reselect -- on_select_net already re-runs for the same net in a few
        # places, e.g. on_auto_clicked's restart, and those should look freshly-colored too).
        self.multi_colors = None
        self._source_polygon_id = source_polygon_id
        self._apply_color_mode()

        # Precomputed once per net selection: this panel's flat net layout doesn't change with
        # subdivision level, only its overlay does -- see net_loading.target_layout_and_
        # connections's own docstring for the net_layout/BFS-fallback decision.
        (self.target_layout, self.target_connections,
         self.target_group_of_face) = net_loading.target_layout_and_connections(
            self.base_faces, self._net_file_json, self_join_split)

        # Level 0 and Level 1 share this exact fan-triangulated topology -- computed once here,
        # up front, rather than re-derived on promotion.
        self.faces, self.edge_length, self.face_of_fine = _build_level1_topology(self.base_faces)
        # Level 0/1's own explicit spring-edge override -- None past Level 1 (Level 2/3's own
        # edges are always unambiguous), reset here on every net load.
        self.edges = _fan_level_edges(self.faces, self.base_edges)
        self.current_path = path
        self.subdivision_level = 0
        self.positions = random_initial_positions(self.faces, seed=self._get_or_generate_seed())
        self._capture_level_start_state()
        self.iteration_count = 0
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        self.last_stats = self._compute_stretch_stats()
        self.level_history = {}
        self.level_snapshots = {}
        self.history_tree.delete(*self.history_tree.get_children())
        self.stop_event = None
        # A freshly-loaded net has no captured Inflate frames yet -- clears every level's
        # replay slider back to disabled/empty rather than leaving the previous net's own
        # trajectory scrubbable here.
        self._level_frames = {}
        self._level_scrub_index = {}
        for level in self.level_replay_sliders:
            self._update_replay_slider(level)
        # A fresh net starts over cleanly, resetting any Auto sequence defensively.
        self._auto_active = False
        self._auto_attempted_level = None
        self._auto_end_state = None
        # Fresh camera state on every new net selection -- a totally different-looking shape
        # shouldn't inherit the previous net's camera. Doesn't affect File > Load, which builds
        # its own state directly from the saved SessionStateModel's own camera fields and never
        # calls this method.
        self._level_camera_state = {"rotation": _initial_level_rotation(),
                                     "zoom": 1.0, "pan": np.zeros(2)}
        self._record_level_history()
        self._update_level_action_buttons()
        self._update_auto_button()
        self.draw()

    # ---- session save/load (File menu) ----

    def on_save_session_clicked(self):
        """File > Save -- prompts for a path (defaulting to self.mesh_name under
        SESSION_OUTPUT_DIR) and writes the current session there via _write_session. See
        _write_session's own docstring for what actually gets saved."""
        if self.positions is None:
            messagebox.showwarning("Save", "No net is loaded yet.")
            return
        SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # ".hippo" -- still plain JSON underneath (model_dump_json below), just a distinct
        # extension so a saved session doesn't look like an ordinary net .json in a file picker.
        # self.mesh_name is always the loaded net FILE's own basename now (load_stretchy_mesh
        # never reads a "name" field from inside the file), so it's safe to use directly --
        # works the same whether this session came from picking a net or from loading a
        # PREVIOUS session (self.mesh_name is restored either way).
        path = filedialog.asksaveasfilename(
            title="Save session", initialdir=str(SESSION_OUTPUT_DIR),
            initialfile=self.mesh_name,
            defaultextension=SESSION_FILE_EXTENSION,
            filetypes=[("Inflate Polyhedron session", f"*{SESSION_FILE_EXTENSION}")])
        if not path:
            return
        self._write_session(path)

    def _write_session(self, path):
        """Serializes the whole current session (the net, every Target RMS/Tolerance spinner,
        the Convergence History table, the mesh at every subdivision level reached so far, and
        each panel's own camera view) to `path` via session_state.SessionStateModel, enough for
        on_load_session_clicked to reopen it exactly as left with no re-solving -- shared by
        on_save_session_clicked (path from the Save dialog) and on_run_all_clicked (path
        computed automatically per net, no dialog).
        self.level_snapshots holds every level already left behind; the current frontier
        level's own live faces/positions/face_of_fine/edge_length aren't in there yet, so this
        adds them under self.subdivision_level before writing. Camera rotation (a scipy
        Rotation) is stored as .as_quat() -- JSON has no quaternion type, and a plain tuple
        round-trips through Rotation.from_quat() losslessly."""
        levels = {level: LevelStateModel.from_mesh(snap["faces"], snap["positions"],
                                                     snap["face_of_fine"])
                  for level, snap in self.level_snapshots.items()}
        levels[self.subdivision_level] = LevelStateModel.from_mesh(
            self.faces, self.positions, self.face_of_fine, self.edge_length)
        state = SessionStateModel(
            net_name=self.mesh_name,
            base_faces=[list(face) for face in self.base_faces],
            net_file=self._net_file_json,
            subdivision_level=self.subdivision_level,
            pressure_value=self.pressure_value,
            iteration_count=self.iteration_count,
            debug_mode=self.debug_mode,
            tolerance=self.tolerance_var.get(),
            seed=self.seed_var.get(),
            target_rms_pct={level: var.get() for level, var in self.target_rms_vars.items()},
            last_stats=LastStatsModel(**{k: v for k, v in self.last_stats.items()
                                          if k in LastStatsModel.model_fields}),
            level_history={level: LevelHistoryRecordModel(**rec)
                           for level, rec in self.level_history.items()},
            levels=levels,
            # Every level shares one camera now -- written into BOTH the
            # "level_*" and "level0_*" fields (same values) rather than dropping the latter,
            # so the SessionStateModel schema/file format doesn't need to change and an older
            # saved file's own level0_* fields stay meaningful to read back (on_load_session_
            # clicked below no longer reads them, but nothing stops another tool from).
            level_zoom=self._level_camera_state["zoom"],
            level_pan=(float(self._level_camera_state["pan"][0]),
                       float(self._level_camera_state["pan"][1])),
            level_rotation=tuple(float(v) for v in self._level_camera_state["rotation"].as_quat()),
            level0_zoom=self._level_camera_state["zoom"],
            level0_pan=(float(self._level_camera_state["pan"][0]),
                        float(self._level_camera_state["pan"][1])),
            level0_rotation=tuple(float(v) for v in self._level_camera_state["rotation"].as_quat()),
            net_zoom=self.net_zoom,
            net_pan=(float(self.net_pan[0]), float(self.net_pan[1])),
            color_mode=self.color_mode_var.get(),
            face_colors=(list(self.multi_colors)
                         if self.color_mode_var.get() == "multi" and self.multi_colors is not None
                         else None),
        )
        try:
            with open(path, "w") as f:
                f.write(state.model_dump_json(indent=2))
        except OSError as e:
            messagebox.showerror("Save", f"Could not save session: {e}")
            return False
        self._set_status(f"Session saved to {os.path.basename(path)}.", "info")
        return True

    def on_load_session_clicked(self):
        """File > Load -- the inverse of on_save_session_clicked. Fully
        replaces the current net/mesh/history (like on_select_net does
        for a fresh net pick) rather than merging into whatever's
        currently loaded, and touches nothing that needs re-solving --
        every level's mesh, the pressure/iteration/history readouts, and
        every spinner come straight from the file."""
        path = filedialog.askopenfilename(
            title="Load session", initialdir=str(SESSION_OUTPUT_DIR),
            filetypes=[("Inflate Polyhedron session", f"*{SESSION_FILE_EXTENSION}"),
                       ("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path) as f:
                state = SessionStateModel.model_validate_json(f.read())
        except (OSError, ValueError) as e:
            messagebox.showerror("Load", f"Could not load session: {e}")
            return

        self.mesh_name = state.net_name
        self.net_var.set(state.net_name)
        self.current_label = state.net_name
        self.current_path = None  # not tied to any file under STRETCHY_NETS_DIR
        self.base_faces = [list(face) for face in state.base_faces]
        self._net_file_json = state.net_file
        # Same "edges"/"face_edge_ids"/"source_polygon_id" disambiguation/
        # grouping on_select_net reads from a fresh net file (see
        # _fan_level_edges/mesh_levels.subdivide_once's own docstrings,
        # and _face_colors_by_group) -- only meaningful when this
        # session's own base_faces actually IS the net_file's "faces"
        # (the ordinary, non-legacy case; see on_select_net's own
        # comment), which a saved session has no direct record of, so
        # this checks the same way on_select_net does: length match. A
        # session with no net_file, or a mismatched one, just falls back
        # to None (the always-safe plain-vertex-pair/per-face-index
        # derivations).
        net_file_faces = (self._net_file_json or {}).get("faces")
        if net_file_faces is not None and len(net_file_faces) == len(self.base_faces):
            self.base_edges = (self._net_file_json or {}).get("edges")
            self.base_face_edge_ids = (self._net_file_json or {}).get("face_edge_ids")
            source_polygon_id = (self._net_file_json or {}).get("source_polygon_id")
        else:
            self.base_edges = None
            self.base_face_edge_ids = None
            source_polygon_id = None
        self._source_polygon_id = source_polygon_id
        # Colour mode + Multi-colour's own persisted colors (2026-10-01, explicit: "these
        # colours persist via Save/Load, even into different app, if the target app supports
        # it") -- state.face_colors is None for a session saved before this existed, or one
        # saved in Polygon-specific mode (nothing to persist there, it's re-derived fresh every
        # time from source_polygon_id); _apply_color_mode's own lazy-regenerate path covers a
        # length mismatch (e.g. face_colors from a DIFFERENT net than base_faces, shouldn't
        # normally happen but isn't trusted blindly either) the same way a fresh net's own None
        # is covered.
        self.color_mode_var.set(state.color_mode)
        # Keeps _last_color_mode in sync with the just-loaded mode (2026-10-01, explicit:
        # "make sure the specific colours and the colour mode are saved/loaded appropriately")
        # -- _on_color_mode_changed's own undo-snapshot logic reads this to find the mode from
        # "before" a later Colour-menu click; left stale (at whatever it was pre-load), the
        # FIRST mode toggle after a load would record the wrong "before" state in its own undo
        # entry.
        self._last_color_mode = state.color_mode
        self.multi_colors = list(state.face_colors) if state.face_colors is not None else None
        self._apply_color_mode()
        self._update_colour_menu_state()
        # Same layout decision as on_select_net -- see net_loading.target_layout_and_
        # connections's own docstring.
        (self.target_layout, self.target_connections,
         self.target_group_of_face) = net_loading.target_layout_and_connections(
            self.base_faces, self._net_file_json)

        self.subdivision_level = state.subdivision_level
        # Falls back to DEFAULT_PRESSURE when None -- a session saved mid-Computing genuinely
        # has no real pressure yet, and nothing downstream expects self.pressure_value itself
        # to be None (unlike level_history's own rms_stretch_pct, handled as a "--" sentinel).
        self.pressure_value = (state.pressure_value if state.pressure_value is not None
                                else DEFAULT_PRESSURE)
        self.iteration_count = state.iteration_count
        self.debug_mode = state.debug_mode
        self.tolerance_var.set(state.tolerance)
        self.seed_var.set(state.seed)
        for level, value in state.target_rms_pct.items():
            if level in self.target_rms_vars:
                self.target_rms_vars[level].set(value)
        self.last_stats = state.last_stats.model_dump()
        self.level_history = {level: rec.model_dump() for level, rec in state.level_history.items()}

        # Every level's own camera view (one shared state, see this state's own init comment)
        # -- read from the "level_*" fields (an older, pre-split session file's one shared
        # camera maps onto these too; the newer "level0_*" fields written alongside them by
        # on_save_session_clicked are ignored here, since Level 0 no longer has anything
        # separate to restore). A rotation field falls back to _initial_level_rotation() (this
        # app's own non-axis-aligned default), not any baked-in quaternion, when None (a
        # session saved before rotation existed, or with no panel ever rotated). draw() below
        # re-renders with this live.
        self._level_camera_state = {
            "zoom": state.level_zoom,
            "pan": np.array(state.level_pan),
            "rotation": (Rotation.from_quat(state.level_rotation)
                         if state.level_rotation is not None
                         else _initial_level_rotation()),
        }
        self.net_zoom = state.net_zoom
        self.net_pan = np.array(state.net_pan)

        self.level_snapshots = {}
        for level, level_state in state.levels.items():
            faces, positions, face_of_fine, edge_length = level_state.to_mesh()
            if level == state.subdivision_level:
                self.faces, self.positions, self.face_of_fine = faces, positions, face_of_fine
                if edge_length is not None:
                    self.edge_length = edge_length
            else:
                self.level_snapshots[level] = {"faces": faces, "positions": positions,
                                                "face_of_fine": face_of_fine}
        # Level 0/1 share their fan-triangulated topology -- only those levels can still have
        # an unsplit base rim edge worth disambiguating; None (the plain, always-safe
        # derivation) past that, same as _subdivide_step.
        self.edges = (_fan_level_edges(self.faces, self.base_edges)
                      if self.subdivision_level <= 1 else None)

        self.history_tree.delete(*self.history_tree.get_children())
        self.stop_event = None
        # A loaded session carries no captured Inflate frames (never part of SessionStateModel)
        # -- clears every level's replay slider rather than leaving some other net's own
        # trajectory scrubbable here.
        self._level_frames = {}
        self._level_scrub_index = {}
        for level in self.level_replay_sliders:
            self._update_replay_slider(level)
        self._auto_active = False
        self._auto_attempted_level = None
        self._auto_end_state = None
        # A loaded session's own current level has no "start of level" state to resume from
        # (a Continue right after loading would have nothing meaningful to restore) -- treated
        # the same as a level whose Inflate/Relax hasn't been (re)started since loading.
        self._capture_level_start_state()
        self._apply_mode_visibility()
        self._refresh_history_table()
        self._update_level_action_buttons()
        self._update_auto_button()
        self.draw()
        # A loaded session can carry its own debug_mode, different from what was showing
        # before -- unlike a plain net reselection, this really is a mode change, so it gets
        # the same refit _on_toggle_debug_mode's explicit toggle does.
        self._refit_window_height()
        self._set_status(f"Session loaded from {os.path.basename(path)}.", "info")

    # ---- subdivide ----

    def _update_level_action_buttons(self):
        """Single source of truth for every level's one action button: only the current
        frontier level's button is ever enabled -- idle it reads "Relax" (level 0) or "Inflate"
        (levels 1+), once converged it becomes "Subdivide" or "DONE!" (MAX_LEVEL, disabled). A
        run in progress overrides this via _set_level_action_button_running instead -- this
        method is never called while one is active."""
        converged = bool(self.last_stats.get("converged"))
        for level, button in self.level_action_buttons.items():
            if level != self.subdivision_level or self.positions is None:
                # Not the current frontier -- reset its text too, not just its disabled state:
                # without this, a level that reached "DONE!" on a PREVIOUS net keeps showing it,
                # now stuck and disabled, after selecting a different net resets to level 0.
                button.config(text="Relax" if level == 0 else "Subdivide")
                button.state(["disabled"])
            elif not converged:
                label = "Relax" if level == 0 else "Inflate"
                command = self.on_relax_clicked if level == 0 else self.on_inflate_clicked
                button.config(text=label, command=command)
                button.state(["!disabled"])
            elif level < MAX_LEVEL:
                button.config(text="Subdivide", command=self.on_subdivide_clicked)
                button.state(["!disabled"])
            else:
                button.config(text="DONE!")
                button.state(["disabled"])

    def _subdivide_step(self):
        """The actual level-advancing work behind on_subdivide_clicked -- no status message or
        redraw of its own, caller reports/draws once itself. Only ever runs from Level 1
        upward (Level 0's own advance is a promotion, not a subdivide_once call -- see
        _finish_relax).

        Freezes the level being left into self.level_snapshots (its "Level N" panel stops
        updating from here on) using whatever state it had reached, before overwriting
        self.faces/positions/etc. with the new level's."""
        self.level_snapshots[self.subdivision_level] = {
            "faces": self.faces, "positions": self.positions,
            "face_of_fine": self.face_of_fine,
        }
        self.faces, self.positions, self.edge_length, self.face_of_fine = subdivide_once(
            self.faces, self.positions, self.edge_length, self.face_of_fine,
            self.subdivision_level, base_faces=self.base_faces,
            face_edge_ids=self.base_face_edge_ids)
        self.subdivision_level += 1
        # Level 2+'s own edges are always unambiguous -- self.edges (the Level 0/1-only
        # spring-edge override) has no reason to exist past this point.
        self.edges = None
        self._capture_level_start_state()
        # This new level's own Target RMS spinner value, just for the history row recorded
        # below, before Inflate has even run once at this level yet.
        if self.subdivision_level in self.target_rms_vars:
            self._current_target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        # The face set just changed entirely -- recomputed fresh, same as a brand new net load.
        self.last_stats = self._compute_stretch_stats()
        # Each level's own step count starts over at 0 -- only meaningful counted from when
        # that level's mesh was first created, not carried over from a coarser level.
        self.iteration_count = 0
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        self._record_level_history()

    def on_subdivide_clicked(self):
        if self.positions is None or self.subdivision_level >= MAX_LEVEL:
            return
        self._subdivide_step()
        self._update_level_action_buttons()  # a fresh subdivision hasn't converged yet
        self._set_status(
            f"Subdivided to level {self.subdivision_level} ({len(self.faces)} faces, "
            f"{len(self.positions)} vertices, edges stretched up to "
            f"{self.last_stats['max_stretch_pct']:.2f}%). Press Inflate to relax/inflate "
            f"further.", "info")
        self.draw()

    # ---- convergence history table ----

    def _record_level_history(self):
        """Records/updates the current level's row: pressure last calibrated for it at Level
        1+, or the periodic-burst strength actually used at Level 0 (level0_periodic_burst_
        distance -- see that function's own docstring for why a displacement, not a literal
        pressure, ends up in that column), steps so far this
        level, stretch stats, and the stopping-condition `optimality` -- all from
        self.last_stats, plus the "Simulation Time"/"Cumulative Time" columns' own backing
        state. Called on every subdivide/promotion, every live progress update, and when a run
        finishes, so the row always reflects the level's latest state rather than only its
        final converged one."""
        level0_burst = (level0_periodic_burst_distance(self.faces, self.edge_length, self.edges)
                         if self.subdivision_level == 0 and self.faces is not None else None)
        self.level_history[self.subdivision_level] = {
            "pressure": level0_burst if self.subdivision_level == 0 else self.pressure_value,
            "steps": self.iteration_count,
            "max_stretch_pct": self.last_stats.get("max_stretch_pct", 0.0),
            # No 0.0 fallback here -- None is a genuine, distinct "not known yet, still
            # computing" state, shown as "--" by _refresh_history_table.
            "rms_stretch_pct": self.last_stats.get("rms_stretch_pct"),
            "optimality": self.last_stats.get("optimality"),
            "converged": self.last_stats.get("converged"),
            # The gtol actually used to reach this reading -- not necessarily the tolerance
            # spinner's current value, which may have changed since. Falls back to
            # CONVERGENCE_GTOL for a row recorded before this field existed.
            "gtol": self.last_stats.get("gtol") or CONVERGENCE_GTOL,
            # Same idea as "gtol" above, for self._current_target_rms_pct -- None for Level 0.
            "target_rms_pct": (None if self.subdivision_level == 0
                                else self.last_stats.get("target_rms_pct")
                                or self._current_target_rms_pct),
            "precomp_time_s": self._current_precomp_time_s,
            "sim_time_s": self._current_sim_time_s,
            # False only for a level whose pressure calibration gave up without finding a
            # usable pressure (e.g. a mesh whose faces exactly cancel under pressure until a
            # later Subdivide gives it real degrees of freedom). Defaults True for Level 0 and
            # for a row recorded before this field existed.
            "pressure_found": self.last_stats.get("pressure_found", True),
        }
        self._refresh_history_table()

    @staticmethod
    def _format_sci(value, precision=2):
        """1.23e-05 -> "1.23e-5" (no leading zero on the exponent), matching the Convergence
        column's compact form. `precision=0` gives "1e-4" style for a fixed threshold."""
        mantissa, exponent = f"{value:.{precision}e}".split("e")
        return f"{mantissa}e{int(exponent)}"

    @staticmethod
    def _format_mmss(seconds):
        """None (phase hasn't run yet at this level) -> "--"; otherwise mm:ss, floored to the
        second -- minutes not capped at 59, so an hour-plus run reads as one growing number
        ("75:03") instead of wrapping back to "15:03"."""
        if seconds is None:
            return "--"
        total_seconds = int(seconds)
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def _rescale_history_columns(self, available_width):
        """Turns self._history_column_weights (proportions) into pixel widths that sum to
        `available_width` -- only the currently displayed columns share out that width
        (release vs. debug mode have different total weight). Bound to <Configure> and also
        called directly from _apply_mode_visibility, since a displaycolumns change alone
        doesn't fire <Configure>. `available_width` <= 1 (widget not laid out yet) is skipped;
        the real <Configure> once layout finishes calls this again."""
        if available_width <= 1:
            return
        # cget always returns a tuple -- displaycolumns="#all" reads back as ('#all',), not
        # the bare string, so this is checked against a tuple.
        displayed = self.history_tree.cget("displaycolumns")
        if displayed == ("#all",):
            displayed = self.history_tree.cget("columns")
        total_weight = sum(self._history_column_weights[col] for col in displayed)
        if total_weight <= 0:
            return
        for col in displayed:
            weight = self._history_column_weights[col]
            self.history_tree.column(
                col, width=max(1, round(available_width * weight / total_weight)))

    def _refresh_history_table(self):
        # "Cumulative Time" (see below) is a running total across rows in
        # LEVEL order -- levels are always visited 0, 1, 2, ... here (never
        # out of order), so a single running total carried across loop
        # iterations is exactly the right-to-left sum the column wants.
        cumulative_seconds = 0.0
        for level in sorted(self.level_history):
            rec = self.level_history[level]
            optimality = rec["optimality"]
            # A run actively in progress right now for this level colors its row yellow
            # ("running"), overriding the plain optimality-vs-gtol comparison below -- red
            # ("not_converged") is reserved for an actual failure (step cap or Stop), not just
            # "hasn't converged yet, still going". Gated on `optimality is None` too, not just
            # `self._level_running` (which stays True through the whole Inflate click,
            # including the purely-visual replay after a real result is already known) --
            # "running" means "still waiting on a result", which ends once `optimality` is
            # real, not once the animation finishes.
            running_now = (level == self.subdivision_level and self._level_running
                           and optimality is None)
            if optimality is None:
                # "--" covers both "never run at this level yet" and "actively computing".
                convergence, tags = "--", (("running",) if running_now else ())
            else:
                # The checkmark tracks the algorithm's own `converged` flag rather than
                # redoing the optimality-vs-gtol comparison here, kept as the single source of
                # truth in case they ever disagree again. This branch only ever shows two
                # colors: green ("converged", checkmark) or red ("not_converged", X) --
                # "--"/yellow is handled entirely by the `if` branch above.
                gtol = rec["gtol"]
                converged = rec["converged"]
                op = "<" if optimality < gtol else ">"
                mark = "✔" if converged else "✘"  # colored via row tag, not the glyph itself
                convergence = (f"{self._format_sci(optimality)} {op} "
                                f"{self._format_sci(gtol, precision=0)} {mark}")
                tags = ("converged",) if converged else ("not_converged",)
            # "--" only when this level's own row hasn't recorded anything yet -- Level 0's own
            # "pressure" is level0_periodic_burst_distance (the burst strength actually used
            # there, see _record_level_history's own comment), not a literal calibrated
            # pressure, but still a real number once Level 0 has run at all.
            pressure_str = "--" if rec["pressure"] is None else f"{rec['pressure']:.2f}"
            # This row's own target_rms_pct (recorded at the time it was calibrated, not read
            # live from the spinner), so a level's row keeps showing what it was actually
            # chasing even after the spinner shows a different level's default. "--" while this
            # run's RMS isn't known yet (filled in the instant it's known, before replay
            # starts). Level 0 has no TARGET (it's pure springs, not calibrated toward
            # anything), but its actual achieved RMS stretch % is shown same as every other
            # level.
            rms_str = "--" if rec["rms_stretch_pct"] is None else f"{rec['rms_stretch_pct']:.1f}"
            # "(target: ...)" is debug-mode-only.
            if self.debug_mode and level != 0 and rec.get("target_rms_pct") is not None:
                rms_str += f" (target: {rec['target_rms_pct']:.1f})"
            # "Simulation Time": Precomp + Sim -- except Level 0, which has no precomputation
            # at all, so its row shows just Sim, and Level 1+, which has no separate Sim phase
            # (pressure calibration's own winning trial IS the Inflate result), so its row
            # shows just Precomp. A row loaded from an older session could still show both;
            # that case shows whichever mm:ss values are present, "--" if neither.
            precomp_s = rec.get("precomp_time_s")
            sim_s = rec.get("sim_time_s")
            if precomp_s is not None and sim_s is not None:
                sim_time_str = f"{self._format_mmss(precomp_s)} + {self._format_mmss(sim_s)}"
            elif precomp_s is not None:
                sim_time_str = self._format_mmss(precomp_s)
            elif sim_s is not None:
                sim_time_str = self._format_mmss(sim_s)
            else:
                sim_time_str = self._format_mmss(None)
            # "Cumulative Time": running total of every row's own Simulation Time seconds so
            # far -- a level that hasn't run yet contributes 0, not "n/a", since the running
            # total up to it is still a real, known number.
            cumulative_seconds += (precomp_s or 0.0) + (sim_s or 0.0)
            cumulative_str = self._format_mmss(cumulative_seconds)
            values = (level, pressure_str, rec["steps"], f"{rec['max_stretch_pct']:.2f}",
                      rms_str, sim_time_str, cumulative_str, convergence)
            iid = str(level)
            if self.history_tree.exists(iid):
                self.history_tree.item(iid, values=values, tags=tags)
            else:
                self.history_tree.insert("", "end", iid=iid, values=values, tags=tags)

    def _compute_stretch_stats(self):
        """max/rms edge stretch of the current self.faces/self.positions against
        self.edge_length -- the same stats relax_once/relax_initial_configuration report,
        computed directly for a mesh that hasn't been relaxed yet (a fresh random start, or
        freshly-interpolated positions right after a Subdivide click). Excludes any OPEN
        polygon's own edges from the RMS average the same way those functions do (see
        _rms_exclude_edges) -- max_stretch_pct is unaffected."""
        edges = mesh_edges(self.faces, self.edges)
        rest = (np.array([self.edge_length[e] for e in edges])
                if isinstance(self.edge_length, dict) else self.edge_length)
        lengths = np.array([np.linalg.norm(self.positions[a] - self.positions[b])
                             for a, b in edges])
        stretch_pct = 100 * (lengths - rest) / rest
        rms_exclude_edges = self._rms_exclude_edges()
        rms_stretch_pct = float(np.sqrt(np.mean(stretch_pct ** 2)))
        if rms_exclude_edges:
            rms_mask = np.array([tuple(sorted(e)) not in rms_exclude_edges for e in edges])
            if rms_mask.any() and not rms_mask.all():
                rms_stretch_pct = float(np.sqrt(np.mean(stretch_pct[rms_mask] ** 2)))
        return {"max_stretch_pct": float(np.max(np.abs(stretch_pct))),
                "rms_stretch_pct": rms_stretch_pct,
                "optimality": None, "converged": None}

    # ---- inflate ----

    def _update_mode_state(self):
        self.steps_spin.state(["!disabled"] if self.iterate_mode_var.get() == "steps"
                               else ["disabled"])

    def _register_numeric_entry(self, entry, allow_exponent, allow_decimal=True):
        """Restricts `entry` to numeric-looking input as it's typed -- Tk's `validate="key"`
        fires before a keystroke is accepted, with `%P` the field's value as it would read if
        the keystroke goes through; returning False rejects it outright, so this never fights
        the user's cursor position the way a post-hoc correction would. `allow_exponent`
        permits an "e"/"E" exponent, for tolerance's scientific-notation text (e.g. "1e-03").
        `allow_decimal` permits a "." -- target RMS entries pass False (whole numbers only)."""
        vcmd = self.root.register(lambda proposed: _is_valid_numeric_partial(
            proposed, allow_exponent, allow_decimal))
        entry.configure(validate="key", validatecommand=(vcmd, "%P"))

    def _begin_edit_target_rms(self, level):
        """<FocusIn> on a target-RMS entry: swaps its displayed "N%" for the bare number alone
        -- the "%" is shown once a number's been entered, not something typed."""
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}")

    def _sync_target_rms_display(self, level):
        """Reformats a target-RMS entry's displayed text as "N%" from its own underlying var --
        fires on every write to that var, from anywhere, so the "%" suffix is never left stale
        after a change that didn't go through this entry."""
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}%")

    def _reset_target_rms_defaults(self):
        """Called by on_select_net for every freshly-loaded net: picks LEVEL_DEFAULT_TARGET_
        RMS_PCT_CLOSED or _OPEN based on whether THIS net is closed (no free/open edge
        anywhere -- _open_base_edges returns nothing) or open (at least one), stashes it as
        self._target_rms_defaults (read by _commit_target_rms_entry's own fallback), and
        writes it straight into every level's spinner -- a previous net's own edited values
        never carry over to a different net."""
        is_closed = not _open_base_edges(self.base_faces, self.base_face_edge_ids)
        self._target_rms_defaults = (LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED if is_closed
                                      else LEVEL_DEFAULT_TARGET_RMS_PCT_OPEN)
        for level, var in self.target_rms_vars.items():
            var.set(round(self._target_rms_defaults[level]))

    def _commit_target_rms_entry(self, level, _event=None):
        """<Return>/<FocusOut> on a target-RMS entry: clamps whatever got typed into [0, 100],
        rounded to the nearest whole number (out-of-range values truncated to the nearest
        extreme, not rejected), or falls back to this level's default if unparseable. Setting
        `self.target_rms_vars[level]` (not the display var directly) is what triggers
        _sync_target_rms_display to put the "%" back."""
        try:
            value = round(float(self.target_rms_display_vars[level].get()))
        except (tk.TclError, ValueError):
            value = self._target_rms_defaults[level]
        self.target_rms_vars[level].set(max(0, min(100, value)))

    def _on_target_rms_changed(self, level):
        # Only the current frontier level's own spinner invalidates a "converged" verdict --
        # editing some other level's target doesn't affect the pressure just calibrated here.
        if level == self.subdivision_level and self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_level_action_buttons()

    def _on_tolerance_changed(self, *_args):
        # Same rationale as _on_target_rms_changed: a "converged" verdict only applies to the
        # tolerance it was reached under.
        if self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_level_action_buttons()

    def _get_tolerance(self):
        """Parses self.tolerance_var's text (e.g. "1e-03") as a float -- a StringVar so it can
        always display in scientific notation -- falling back to DEFAULT_TOLERANCE for anything
        unparseable (e.g. a momentarily-empty field mid-edit)."""
        try:
            return float(self.tolerance_var.get())
        except ValueError:
            return DEFAULT_TOLERANCE

    def _get_or_generate_seed(self):
        """Parses self.seed_var's text as an int and returns it unchanged if present -- a
        specific seed typed into debug mode's own "Seed" entry, pinned for this net load.
        Blank (the default) instead draws a fresh random one and writes it back into
        self.seed_var, so whatever seed actually produced this net's starting embedding stays
        visible/copyable afterward even though nothing was typed in beforehand."""
        text = self.seed_var.get().strip()
        if text:
            try:
                return int(text)
            except ValueError:
                pass
        seed = int(np.random.default_rng().integers(0, 2**31 - 1))
        self.seed_var.set(str(seed))
        return seed

    def _capture_level_start_state(self):
        """Snapshots self.faces/positions/face_of_fine/edge_length/edges as "the current
        level's own starting point" (self._level_start_state) -- called every time a level is
        first entered: on_select_net (Level 0), _finish_relax's own promotion to Level 1, and
        _subdivide_step (Level 2+). on_auto_continue_clicked restores exactly this to resume a
        STOPPED level from its own beginning rather than wherever its partial Relax/Inflate
        progress left off."""
        self._level_start_state = {
            "faces": self.faces, "positions": self.positions,
            "face_of_fine": self.face_of_fine, "edge_length": self.edge_length,
            "edges": self.edges,
        }

    def _repulsion_vertex_ids(self):
        """The vertex ids repulsion acts on: each ORIGINAL polygon's own raw corners, straight
        from self.base_faces -- e.g. a hexagon's own 6 vertices, not the extra fan-hub centroid
        _build_level1_topology's own triangulation would add on top. A SELF-JOINED polygon
        (already exported as several base_faces triangle pieces, e.g. a folded hexagon's own 6
        wedges -- see mesh_levels.py's own docstring) has no single well-defined "original
        polygon" left to speak of, so its own already-triangular pieces' own raw corners are
        used instead -- exactly what reading self.base_faces directly gives regardless, with no
        special-casing needed either way (an ordinary, non-folded polygon is always exactly one
        base_faces entry already).

        A small, FIXED set -- computed from self.base_faces, unaffected by whatever the
        CURRENT subdivision_level actually is, so it stays correct even after later Subdivides
        add their own finer vertices on top. Passed as every level's own `repulsion_vertex_ids`
        in on_inflate_clicked, keeping the population (and thus repulsion's own O(n^2) cost)
        constant regardless of level, rather than growing with Level 2/3's own much larger
        full vertex count."""
        return sorted({v for face in self.base_faces for v in face})

    def _closed_repulsion_vertex_ids(self):
        """The subset of _repulsion_vertex_ids that are "closed": NOT an endpoint of any free
        (unglued) base-polygon edge -- for an ordinary manifold vertex this is exactly
        equivalent to "borders as many edges as faces", since a complete fan has one face per
        edge while an incomplete one has one fewer.

        Deliberately reuses _open_base_edges (the SAME face_edge_ids-disambiguated free-edge
        detection _level1_is_open already relies on) rather than counting edges/faces directly
        on the fine mesh: a plain vertex-id-pair count gets the WRONG answer at a
        highly-overlapping "pinch point" like a self-folded polygon's own fan hub, where
        several flap-duplicate layers (see mesh_levels.py's own docstring on flap pairs) can
        each independently have a genuinely FREE edge that happens to share its plain
        vertex-id pair with another layer's own edge -- e.g. cannoli.poly's hub vertex sees
        every one of its incident plain vertex-pairs "used twice" this way even though real,
        disambiguated free edges DO touch it, so a naive count reads it as fully closed when
        it's actually open. face_edge_ids' own per-edge-slot ids don't have that ambiguity."""
        repulsion_ids = self._repulsion_vertex_ids()
        open_edges_by_base = _open_base_edges(self.base_faces, self.base_face_edge_ids)
        open_vertices = set()
        for pairs in open_edges_by_base.values():
            for pair in pairs:
                open_vertices.update(pair)
        return {v for v in repulsion_ids if v not in open_vertices}

    def _repulsion_vertex_multipliers(self):
        """{vertex_id: multiplier} for every CLOSED repulsion vertex (see
        _closed_repulsion_vertex_ids) -- 1.0 at Level 0/1, halved at every level after that:
        full strength at Level 1, half at Level 2, a quarter at Level 3. An OPEN vertex is
        simply absent from this dict, defaulting to its own full multiplier of 1 wherever it's
        looked up, unaffected by level. None (rather than an all-1.0 dict) when every repulsion
        vertex is open, so callers can skip the machinery entirely."""
        closed = self._closed_repulsion_vertex_ids()
        if not closed:
            return None
        factor = 1.0 / (2 ** max(0, self.subdivision_level - 1))
        return {v: factor for v in closed}

    def _level1_is_open(self):
        """True/False per LEVEL-1 fine triangle (same order _build_level1_topology's own
        `faces` would be), independent of self.subdivision_level -- whether THAT SPECIFIC
        wedge's own outer rim edge (the one opposite the fan hub, corresponding to exactly one
        edge of its own original polygon) is free ("open") rather than glued to a neighbor
        ("closed"). Classified per WEDGE, not per whole polygon: an n-gon connected at 2 of
        its own edges triangulates into 2 closed wedges and n-2 open ones.

        The fan hub is found the same way fan_hub_vertices used to (before the C2C springs
        work that introduced it was reverted): the one vertex every one of a base polygon's
        own wedges has in common. A wedge's own rim edge is then just its other two vertices."""
        level1_faces, _edge_length, level1_face_of_fine = _build_level1_topology(self.base_faces)
        open_edges = _open_base_edges(self.base_faces, self.base_face_edge_ids)
        verts_by_base = {}
        for face, base_idx in zip(level1_faces, level1_face_of_fine):
            verts = set(face)
            verts_by_base[base_idx] = (verts if base_idx not in verts_by_base
                                        else verts_by_base[base_idx] & verts)
        hub_by_base = {i: next(iter(s)) for i, s in verts_by_base.items() if len(s) == 1}
        flags = []
        for face, base_idx in zip(level1_faces, level1_face_of_fine):
            hub = hub_by_base.get(base_idx)
            if hub is None:
                flags.append(False)  # no well-defined single hub -- default to "closed"/participating
                continue
            rim_pair = frozenset(v for v in face if v != hub)
            flags.append(rim_pair in open_edges.get(base_idx, ()))
        return flags

    def _is_open_of_fine(self, level=None):
        """is_open flags parallel to self.faces at `level` (self.subdivision_level if not
        given) -- _level1_is_open's own result, repeated 4x per Subdivide since Level 1
        (mirroring exactly how mesh_levels._quarter_triangles itself propagates face_of_fine:
        every old triangle's 4 children are appended contiguously, in old-index order -- see
        that function's own docstring -- so a parallel array only needs the same
        repeat-4x-in-order treatment to stay aligned, without mesh_levels.py needing to know
        this array exists at all). Level 0 shares Level 1's own topology, so `level <= 1` both
        mean zero repeats. Takes an explicit `level` (rather than always reading
        self.subdivision_level) so _draw_level_panel can compute this for whichever panel
        it's drawing, not just the live frontier one."""
        if level is None:
            level = self.subdivision_level
        flags = self._level1_is_open()
        for _ in range(max(0, level - 1)):
            flags = [f for f in flags for _ in range(4)]
        return flags

    def _rms_exclude_edges(self):
        """(a, b) sorted vertex-id-pair tuples, at the CURRENT subdivision level, to exclude
        from the RMS Stretch % calculation -- every edge of every OPEN fine triangle (see
        _is_open_of_fine), not just its own free edge: an open wedge triangle doesn't
        participate in the RMS stretch % calculation at all. None (rather than an empty set)
        when nothing in the net is open, so callers can skip the exclusion machinery
        entirely."""
        is_open = self._is_open_of_fine()
        if not any(is_open):
            return None
        exclude = set()
        for face, open_flag in zip(self.faces, is_open):
            if open_flag:
                n = len(face)
                for k in range(n):
                    exclude.add(tuple(sorted((face[k], face[(k + 1) % n]))))
        return exclude

    def _pressure_exclude_faces(self):
        """Boolean list parallel to self.faces AT THE CURRENT subdivision_level -- True for
        every OPEN fine triangle (see _is_open_of_fine), which should feel NO pressure/
        inflation force at all, while still fully existing for springs/repulsion/edges/
        convergence. None when nothing in the net is open, so callers can skip the exclusion
        machinery (and stretchy_mesh._face_index_groups' own per-face check) entirely."""
        is_open = self._is_open_of_fine()
        return is_open if any(is_open) else None

    def _guess_pressure_from_history(self, target_rms_pct):
        """Estimates the pressure to hand estimate_pressure_for_target_stretch as its own
        starting guess, drawing on already-calibrated prior levels' history instead of
        falling back to the generic per-solid-derived constant. Looks at every prior level's
        (pressure, achieved rms_stretch_pct) pair and picks whichever one's achieved stretch
        landed closest to the new target -- scaling that record's pressure by 2 per level of
        resolution difference (each Subdivide roughly doubles resolution, and empirically
        needs ~2x the pressure for the same target RMS stretch %).

        Deliberately not a `target_rms_pct / achieved` rescale -- that ratio explodes when a
        level's achieved stretch is ~0 (pressure genuinely had no effect there, e.g. a mesh
        whose faces cancel out under pressure until a later Subdivide gives it real degrees
        of freedom), producing an absurd guess that overflows the solver. Picking the
        closest-achieved record instead never divides by anything.

        A level whose record has `pressure_found` False is skipped entirely -- its "pressure"
        never came from a real calibration (the search gave up because the mesh was
        unresponsive to pressure there), so it's not a usable extrapolation point.

        Returns None (falling back to the generic guess) if no level below the current
        frontier has a usable recorded pressure/stretch pair yet."""
        return reinflater.guess_pressure_from_history(
            self.level_history, self.subdivision_level, target_rms_pct)

    def on_inflate_clicked(self):
        """Calibrates a pressure for the current "Target RMS stretch" (via _run_background --
        see _on_pressure_calibrated) and, once found, that's the whole run -- no separate
        second relax_once call at the winning pressure. estimate_pressure_for_target_stretch
        itself captures the winning trial's own frames (capture_frames=True) and
        _on_pressure_calibrated replays those (_start_frame_replay) once calibration lands on
        a pressure -- same visual result, zero recomputation.

        While calibration is searching, this level's panel shows an animated "Computing..."
        placeholder instead of a live redraw -- most calibration trials are thrown away, so
        there's no single meaningful shape to show frame-by-frame until it finishes. Level 0's
        own Relax has no calibration phase to discard trials from, but shows the same
        "Computing..." placeholder throughout its one real run (see on_relax_clicked).

        Recalibrates fresh from wherever self.positions currently is on every click, since the
        user can't set pressure directly. Calibrates against the current Tolerance spinner
        value too. The search's starting pressure comes from _guess_pressure_from_history when
        a usable prior level exists, falling back to the generic guess otherwise.

        self.stop_event is created and the frontier button turned into "Stop" here, before
        calibration even starts -- Stop needs a stop_event in place from the start, or
        clicking it during a slow calibration search (which can run up to max_iterations *
        max_nfev_per_trial steps) has nothing to interrupt."""
        if self.positions is None or self.last_stats.get("converged"):
            return
        faces, edge_length, positions = self.faces, self.edge_length, self.positions
        repulsion_vertex_ids = self._repulsion_vertex_ids()
        repulsion_vertex_multipliers = self._repulsion_vertex_multipliers()
        rms_exclude_edges = self._rms_exclude_edges()
        pressure_exclude_faces = self._pressure_exclude_faces()
        target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        # Captured here too, not just at the level-default sites, in case the user edited the
        # spinner away from that default before clicking Inflate.
        self._current_target_rms_pct = target_rms_pct
        tolerance = self._get_tolerance()
        initial_pressure_guess = self._guess_pressure_from_history(target_rms_pct)
        self.stop_event = threading.Event()
        # Marks the start of the "Precomp time" column's phase, consumed (as
        # self._current_precomp_time_s) in _on_pressure_calibrated. Level 1+ has no separate
        # "Sim time" phase -- all of a Level 1+ row's Simulation Time is "Precomp" now.
        self._precomp_start_time = time.perf_counter()
        # Read by _on_calibration_progress, which fires from a _run_background poll tick, not
        # a call this method's own local scope survives until -- has to live on self.
        self._precomp_base_iteration_count = self.iteration_count
        # Snapshot to restore if this run gets Stopped, and blank "RMS Stretch %", "Pressure",
        # and "Convergence" to "--" for the duration of this run -- without this the row would
        # keep showing stale data from the previous run's own result, looking current when
        # it isn't. `optimality=None` is what actually blanks "Convergence" --
        # _refresh_history_table already treats None there as "no result yet"; `converged`/
        # `gtol` don't need resetting since the display logic never reads them while
        # optimality is None.
        self._pre_computing_last_stats = dict(self.last_stats)
        self._pre_computing_pressure_value = self.pressure_value
        self.last_stats = {**self.last_stats, "rms_stretch_pct": None, "optimality": None}
        self.pressure_value = None
        self._record_level_history()
        self._set_level_action_button_running(True)
        self._start_computing_animation(self.subdivision_level)
        self._set_status(f"Finding a pressure that settles around {target_rms_pct:.1f}% "
                          "RMS stretch...", "info")
        self._run_background(
            lambda queue_progress: estimate_pressure_for_target_stretch(
                positions, faces, edge_length,
                target_rms_pct=target_rms_pct,
                gtol=tolerance,
                rng=None,
                stop_event=self.stop_event,
                initial_pressure_guess=initial_pressure_guess,
                capture_frames=True,
                on_progress=queue_progress,
                edges=self.edges,
                repulsion_vertex_ids=repulsion_vertex_ids,
                repulsion_vertex_multipliers=repulsion_vertex_multipliers,
                rms_exclude_edges=rms_exclude_edges,
                pressure_exclude_faces=pressure_exclude_faces),
            lambda result: self._on_pressure_calibrated(result, self._precomp_base_iteration_count),
            on_progress=self._on_calibration_progress)

    def _on_calibration_progress(self, cumulative_steps):
        """Live "Steps" column update while pressure calibration is computing.
        `cumulative_steps` is estimate_pressure_for_target_stretch's own running total across
        every trial attempted (not reset per trial -- a counter dropping backwards on each new
        trial would read as broken). Not necessarily the same number the row ends up showing
        once calibration finishes -- _on_pressure_calibrated snaps self.iteration_count to the
        true final steps_taken the instant the real result comes back, before replay starts,
        so any mismatch is a single, one-time correction at the Computing-to-Replay
        transition."""
        self.iteration_count = self._precomp_base_iteration_count + cumulative_steps
        self._record_level_history()

    def _on_pressure_calibrated(self, result, base_iteration_count):
        if self.stop_event is not None and self.stop_event.is_set():
            # Stopped during calibration itself -- its own trial positions are discarded
            # regardless of how it ends, so there's nothing from `result` to apply; just
            # report it the same way a stopped run would. Restores this level's own normal
            # panel (self.positions/faces are unchanged from before this click).
            self._stop_computing_animation()
            self._set_level_action_button_running(False)
            self._set_status(
                f"Stopped (during pressure calibration at level "
                f"{self.subdivision_level}).", "warn")
            # No real result to show -- restore "RMS Stretch %"/"Pressure" (blanked to "--" at
            # the start of this click) back to whatever they genuinely were before this run.
            self.last_stats = self._pre_computing_last_stats
            self.pressure_value = self._pre_computing_pressure_value
            self._record_level_history()
            self.draw()
            self._auto_step()  # no-op unless Auto is what actually drove this run
            return
        (pressure, new_positions, steps_taken, max_stretch, rms_stretch,
         optimality, converged, frames, pressure_found) = result
        self.pressure_value = pressure
        # "Precomp time": calibration has no progress callback of its own to update this live,
        # so it's set once here, the moment it finishes.
        self._current_precomp_time_s = time.perf_counter() - self._precomp_start_time
        # Captured once here, not re-read live during the run, and reused by
        # _finish_frame_replay so the recorded outcome shows the same threshold it actually
        # converged against, even if the spinner's value changes later.
        self._current_gtol = self._get_tolerance()
        self._stop_computing_animation()
        # _run_background's completion just re-synced every control, including the frontier
        # button, back to its normal state -- re-disable them and turn the frontier button
        # back into "Stop" for the replay about to start (Stop during replay just skips to
        # the final frame).
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self._set_status(f"Replaying the winning trial at pressure {pressure:.2f}...", "info")
        # Snaps "Steps" and the Convergence History row's stretch/Convergence columns to their
        # true final values the instant the real result is known, rather than waiting for
        # replay (which can take a while at REPLAY_FPS) to finish. self.positions is
        # deliberately NOT updated yet -- that stays whatever _replay_step shows, frame by
        # frame, until the animation reaches the end.
        self.iteration_count = base_iteration_count + steps_taken
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged,
                            "gtol": self._current_gtol,
                            "target_rms_pct": self._current_target_rms_pct,
                            "pressure_found": pressure_found}
        self._record_level_history()
        # Made available for manual scrubbing right away, defaulted to the true final frame --
        # not gated on the auto-played animation finishing, so the slider is usable the instant
        # a result exists, even while that animation is still playing.
        self._level_frames[self.subdivision_level] = frames
        self._level_scrub_index[self.subdivision_level] = len(frames) - 1
        self._update_replay_slider(self.subdivision_level)
        # iteration_count/last_stats are already set to their true final values above, before
        # replay even starts -- only self.positions needs applying once replay finishes (every
        # frame in between is display-only, see _start_frame_replay's own docstring).
        self._start_frame_replay(
            frames, lambda: setattr(self, "positions", new_positions), self._finish_inflate)

    # Target frames per second during a replay -- purely a display rate for an already-
    # finished trial's own positions, fast enough to read as "watching it happen" without
    # dragging out a recap. A ceiling, not a guarantee: each tick still pays the real cost of
    # rendering one "Level N" panel, which can exceed REPLAY_FRAME_INTERVAL_MS on a dense mesh
    # -- _replay_step schedules the next tick only after the current render finishes, so a
    # slow render just means fewer actual fps that tick, never a backlog.
    REPLAY_FPS = 30
    REPLAY_FRAME_INTERVAL_MS = round(1000 / REPLAY_FPS)
    # Advances this many CAPTURED frames (each already CONVERGENCE_CHECK_INTERVAL=200 physics
    # steps apart) per tick, not 1 -- effectively plays the same captured sequence back ~4x
    # faster in wall-clock time than one-frame-per-tick would, while still ticking at a smooth
    # 30fps -- skips frames outright rather than raising REPLAY_FPS further, which would only
    # make each individual render (the real bottleneck) more likely to fall behind.
    REPLAY_FRAME_STRIDE = 4

    def _start_frame_replay(self, frames, apply_final, on_finished):
        """Plays back `frames` (`(positions, steps_taken)` pairs, captured every
        CONVERGENCE_CHECK_INTERVAL steps) at REPLAY_FPS -- a purely visual recap of an
        already-finished run; no physics runs here. Shared by Inflate's own winning-
        calibration-trial replay (_on_pressure_calibrated) and Level 0's own Relax replay
        (_finish_relax, 2026-10-01, explicit: "when it's done, it should replay like the other
        levels" -- previously Inflate-only, Level 0 kept redrawing live throughout instead).
        The bottom-of-panel message shows "Replaying" + a 0-3-dot cycle through _replay_step,
        clearing once done.

        `apply_final` (no args) is called once the replay reaches its last frame
        (_finish_frame_replay), to apply whatever the caller's own true final state actually is
        (self.positions/iteration_count/last_stats -- every frame in between is DISPLAY-ONLY,
        self.positions temporarily pointed at it just so draw() shows it); `on_finished` (no
        args), called right after, does whatever level-specific reporting/promotion/Auto
        follow-up comes next (_finish_inflate for Levels 1-3, _finish_relax_report for Level
        0)."""
        self._replay_frames = frames
        self._replay_index = 0
        self._replay_apply_final = apply_final
        self._replay_on_finished = on_finished
        self._replay_step()

    def _replay_step(self):
        # A Stop click during replay jumps straight to the final frame -- no live physics left
        # to interrupt, just an animation, so skipping ahead is more useful than finishing the
        # recap the user already asked to cut short.
        skip_ahead = self.stop_event is not None and self.stop_event.is_set()
        total = len(self._replay_frames)
        if self._replay_index < total and not skip_ahead:
            positions, _steps_taken = self._replay_frames[self._replay_index]
            self.positions = positions
            # Dot count derived from wall-clock time, not a replay-tick counter --
            # REPLAY_FRAME_INTERVAL_MS (~33ms) is far faster than a readable dot-cycle, so
            # ticking once per replay frame would flicker; time.perf_counter() gives the same
            # ~500ms-per-dot pace _tick_computing_animation uses, no separate timer needed.
            dots = int(time.perf_counter() / (self.COMPUTING_DOT_INTERVAL_MS / 1000)) % 4
            self._set_level_message(self.subdivision_level, "Replaying" + "." * dots)
            # Only this level's own panel changes frame to frame -- a full draw() (Net plus
            # every "Level N" panel) measured ~0.5s on a mid-size net, far slower than
            # REPLAY_FRAME_INTERVAL_MS, since it'd re-render three unrelated, unchanged panels
            # every tick. _draw_level_panel alone keeps replay running near REPLAY_FPS.
            self._draw_level_panel(self.subdivision_level, self.faces,
                                    self.positions, self.face_of_fine)
            # Advances by REPLAY_FRAME_STRIDE captured frames, not 1 -- clamped so the last
            # captured frame always gets its own tick even when the stride would otherwise
            # jump past it, rather than silently skipping straight from an earlier frame.
            if self._replay_index >= total - 1:
                self._replay_index = total  # just showed the last frame -- next tick ends it
            else:
                self._replay_index = min(self._replay_index + self.REPLAY_FRAME_STRIDE, total - 1)
            self._replay_after_id = self.root.after(self.REPLAY_FRAME_INTERVAL_MS,
                                                       self._replay_step)
        else:
            self._replay_after_id = None
            self._finish_frame_replay()

    def _finish_frame_replay(self):
        # A Stop click can only ever reach here meaning "skip the replay animation" -- a Stop
        # that actually interrupted the real computation is caught earlier, in
        # _on_pressure_calibrated's own stop_event branch (or _finish_relax's own was_stopped
        # branch), which returns before a replay starts. By the time this runs, the run's
        # result is already final regardless of whether the animation played in full --
        # clearing stop_event here keeps the "Stopped"/"Converged" status message honest.
        self.stop_event = None
        self._replay_apply_final()
        self._record_level_history()
        self._set_level_message(self.subdivision_level, "")  # clears once replay is done
        self.draw()
        self._replay_on_finished()

    def _update_replay_slider(self, level):
        """Configures level `level`'s own replay scrubber to match self._level_frames[level] --
        the slider's range spans every captured frame index, enabled iff at least 2 frames
        exist. Also re-syncs the slider's displayed position to self._level_scrub_index[level]
        -- `ttk.Scale.set` DOES fire `command`, so this harmlessly re-triggers
        _on_replay_slider_moved with the same index it was already at -- idempotent (redraws
        the same already-current frame), not a real scrub action."""
        slider = self.level_replay_sliders.get(level)
        if slider is None:
            return
        frames = self._level_frames.get(level)
        if not frames or len(frames) < 2:
            slider.configure(to=0)
            slider.set(0)
            slider.state(["disabled"])
            return
        slider.configure(from_=0, to=len(frames) - 1)
        slider.state(["!disabled"])
        slider.set(self._level_scrub_index.get(level, len(frames) - 1))

    def _on_replay_slider_moved(self, level, value):
        """`command` callback for level `level`'s replay scrubber -- `value` is ttk.Scale's
        string-formatted float, rounded to the nearest captured frame index (clamped, since a
        Scale can report a value fractionally past its `to` during a fast drag). Purely a
        display override: updates self._level_scrub_index[level] and redraws just this panel,
        without touching self.positions/self.level_snapshots -- scrubbing never affects what
        the next real Inflate/Subdivide click continues from."""
        frames = self._level_frames.get(level)
        if not frames:
            return
        idx = max(0, min(int(round(float(value))), len(frames) - 1))
        self._level_scrub_index[level] = idx
        if level == self.subdivision_level:
            faces, face_of_fine = self.faces, self.face_of_fine
        elif level in self.level_snapshots:
            snap = self.level_snapshots[level]
            faces, face_of_fine = snap["faces"], snap["face_of_fine"]
        else:
            return
        self._draw_level_panel(level, faces, frames[idx][0], face_of_fine)

    def _set_level_action_button_running(self, running):
        """Neither mode has a separate Stop button -- the current frontier level's own action
        button turns into the Stop control for the duration of a run, then back to its normal
        Inflate/Relax/Subdivide/DONE! state once it finishes (delegated to
        _update_level_action_buttons). Safe to assume the frontier level doesn't change
        mid-run: every other level's button is disabled for the whole run too, and Relax's own
        promotion only happens in _finish_relax, after the run is over."""
        self._level_running = running
        self._refresh_history_table()
        button = self.level_action_buttons.get(self.subdivision_level)
        if button is None:
            return
        if running:
            button.config(text="Stop", command=self.on_stop_clicked)
            button.state(["!disabled"])
        else:
            self._update_level_action_buttons()

    def on_stop_clicked(self):
        if self.stop_event is not None:
            self.stop_event.set()
            frontier_button = self.level_action_buttons.get(self.subdivision_level)
            if frontier_button is not None:
                frontier_button.state(["disabled"])  # one request is enough; avoid repeat clicks
            self._set_status("Stopping...", "warn")
        # A per-level Stop clicked directly while an Auto sequence is running must ALSO halt
        # the sequence -- otherwise _auto_step would just start the next step right back up.
        self._abort_auto()

    # ---- "Auto": Relax -> Inflate -> Subdivide -> ... -> Level MAX_LEVEL ----

    def on_auto_clicked(self):
        """Runs the whole pipeline unattended: Relax at Level 0, then Inflate/Subdivide/.../
        Level MAX_LEVEL -- see _auto_step, which drives one step at a time and decides what
        "next" means at any given moment. Disabled whenever a net isn't loaded or any run is
        already in progress.

        If the LAST Auto sequence ran all the way to a natural end (self._auto_end_state ==
        "completed" -- reached MAX_LEVEL and converged, OR gave up on a level that wouldn't
        converge), this is "Run Simulation" clicked again after that: restarts fresh from
        Level 0 (on_select_net, which also draws a new random seed unless one's pinned) rather
        than doing nothing/erroring on an already-finished run. `_auto_end_state is None`
        (never run at all yet) skips that reset -- the
        current state already IS Level 0's own fresh start, nothing to redo."""
        if self.positions is None or self._auto_active:
            return
        if self._auto_end_state == "completed":
            self.on_select_net()
        self._auto_end_state = None
        self._auto_active = True
        self._auto_attempted_level = None
        self._update_auto_button()
        self._auto_step()

    def on_auto_continue_clicked(self):
        """The Auto button's own command when self._auto_end_state == "stopped" (reads
        "Continue Simulation" -- see _update_auto_button): resumes from the START of whatever
        level was interrupted, restoring self._level_start_state (that level's own faces/
        positions/face_of_fine/edge_length/edges, captured the moment it was first entered --
        see _capture_level_start_state) rather than wherever its partial Relax/Inflate progress
        left off. Every EARLIER level's own already-recorded history/snapshot is untouched --
        this only discards the CURRENT (interrupted) level's own in-progress attempt."""
        if self.positions is None or self._auto_active or self._auto_end_state != "stopped":
            return
        if self._level_start_state is not None:
            self.faces = self._level_start_state["faces"]
            self.positions = self._level_start_state["positions"]
            self.face_of_fine = self._level_start_state["face_of_fine"]
            self.edge_length = self._level_start_state["edge_length"]
            self.edges = self._level_start_state["edges"]
        self.iteration_count = 0
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        if self.subdivision_level in self.target_rms_vars:
            self._current_target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        self.last_stats = self._compute_stretch_stats()
        self._record_level_history()
        self._auto_end_state = None
        self._auto_active = True
        self._auto_attempted_level = None
        self._update_level_action_buttons()
        self._update_auto_button()
        self.draw()
        self._auto_step()

    def on_auto_stop_clicked(self):
        """The Auto button's own command while a sequence is running -- ends the sequence and
        interrupts whatever Relax/Inflate step is currently mid-run, via the same stop_event
        on_stop_clicked already uses."""
        self._abort_auto()
        self.on_stop_clicked()

    def _abort_auto(self):
        """Ends an in-progress Auto sequence without touching whatever Relax/Inflate run might
        currently be underway -- also called from every worker-thread failure path that would
        otherwise leave self._auto_active stuck True with the button showing "Stop Simulation"
        for a sequence that's already silently dead. Marks self._auto_end_state "stopped" (see
        its own comment) so the button becomes "Continue Simulation" next -- a no-op, including
        that marking, if Auto isn't actually running."""
        if self._auto_active:
            self._auto_active = False
            self._auto_end_state = "stopped"
            self._update_auto_button()

    def _update_auto_button(self):
        """Single source of truth for the Auto button: idle it reads "Run Simulation" (never
        run yet, or the last run reached a natural end -- self._auto_end_state None/
        "completed"), enabled only once a net is loaded -- otherwise disabled like every other
        control while any run is in progress. While Auto itself is driving a run, it instead
        reads "Stop Simulation" and is explicitly RE-ENABLED regardless of what
        _set_controls_enabled(False) just did -- the same "frontier button survives the
        blanket disable" pattern _set_level_action_button_running uses, so the one control
        that can interrupt a multi-step Auto sequence stays clickable throughout. After an
        explicit Stop (self._auto_end_state == "stopped"), it reads "Continue Simulation"
        instead (on_auto_continue_clicked) -- see that method's own comment."""
        if self._auto_active:
            self.auto_button.config(text="Stop Simulation", command=self.on_auto_stop_clicked)
            self.auto_button.state(["!disabled"])
        elif self._auto_end_state == "stopped":
            self.auto_button.config(text="Continue Simulation", command=self.on_auto_continue_clicked)
            self.auto_button.state(["!disabled"] if self.positions is not None else ["disabled"])
        else:
            self.auto_button.config(text="Run Simulation", command=self.on_auto_clicked)
            self.auto_button.state(["!disabled"] if self.positions is not None else ["disabled"])

    def _auto_step(self):
        """Decides what Auto should do next, called once from on_auto_clicked to kick the
        sequence off and again from the tail of _finish_relax/_finish_inflate every time a
        step it started finishes -- a no-op whenever Auto isn't active.

        - Level 0, not yet converged: Relax -- exactly one attempt per level, no retries (a
          non-converged attempt just runs its own single relax call up to its own large step
          budget -- see INFLATE_SAFETY_STEP_CAP -- rather than Auto stopping short and
          starting a fresh one). If _auto_attempted_level already names this level, declare
          failure and stop Auto rather than trying again.
        - Level 0, converged: _finish_relax has already promoted to Level 1 unconditionally
          by the time this runs, so there's nothing left to do here.
        - Current level converged, below MAX_LEVEL: Subdivide, then immediately re-enter this
          function rather than waiting for a callback Subdivide itself never schedules
          (synchronous, unlike Relax/Inflate).
        - Current level converged, at MAX_LEVEL: done.
        - Current level not converged: same one-attempt-then-stop rule as Level 0, via Inflate."""
        if not self._auto_active:
            return
        if self.last_stats.get("converged"):
            self._auto_attempted_level = None
            if self.subdivision_level == 0:
                return  # _finish_relax already promoted to Level 1
            if self.subdivision_level < MAX_LEVEL:
                self.on_subdivide_clicked()
                self._auto_step()
            else:
                self._auto_active = False
                self._auto_end_state = "completed"
                self._update_auto_button()
                self._set_status(f"Auto: reached Level {MAX_LEVEL} and converged.", "success")
            return
        if self._auto_attempted_level == self.subdivision_level:
            self._auto_active = False
            self._auto_end_state = "completed"
            self._update_auto_button()
            self._set_status(
                f"Auto: Level {self.subdivision_level} still hasn't converged after one "
                f"attempt (up to {INFLATE_SAFETY_STEP_CAP} steps) -- stopping the automatic "
                f"sequence (Inflate/Relax are still available to keep trying by hand).", "warn")
            return
        self._auto_attempted_level = self.subdivision_level
        if self.subdivision_level == 0:
            self.on_relax_clicked()
        else:
            self.on_inflate_clicked()

    # ---- Run > Run All / Debug All ----

    def on_run_all_clicked(self):
        """Run > Run All: runs the exact same unattended
        pipeline "Run Simulation" (on_auto_clicked) drives for ONE net, for EVERY net currently
        listed in "Choose a net", one after another, through the real UI (each one actually
        selected, relaxed/inflated/subdivided on screen, not some separate headless
        computation) -- saving each net's own .hippo (_write_session) the instant its own
        sequence reaches a natural end, before moving straight on to the next (no save-results
        prompt, no pause between nets -- see on_debug_all_clicked for the debug-only variant
        that skips saving and pauses on the Right arrow key instead). The window title shows
        "(m/n)" progress throughout (_update_window_title). No-op if Run All/Debug All or an
        Auto sequence is already active, there's nothing to run, or Viewer mode is showing
        (2026-10-01, explicit: "Run All should be disabled in this view" -- the menu item itself
        is disabled there too, via _update_run_menu_state; this guard is defense in depth)."""
        self._start_run_all(save_results=True, wait_for_advance=False)

    def on_debug_all_clicked(self):
        """Run > Debug All (2026-10-01, explicit -- debug-mode only, see _update_run_menu_state):
        the same unattended run through every net as Run All, except it never saves any net's
        own .hippo (a dry/test run), and PAUSES after each net finishes until the user presses
        the Right arrow key, rather than moving straight on to the next -- see
        _on_debug_all_right_key. Lets a developer actually look at each net's own Level 3
        result before the next one overwrites the panels. The Right/Left arrow keys ALSO work
        while a net is still mid-run (not just once paused): Right abandons it and skips straight
        to the next net, Left abandons it and goes back to re-run the previous one (see
        _on_debug_all_right_key/_on_debug_all_left_key, and _debug_all_jump for the shared
        abandon-and-jump logic both use). Same no-op guards as on_run_all_clicked (Debug All or
        an Auto sequence already active, nothing to run, Viewer mode)."""
        self._start_run_all(save_results=False, wait_for_advance=True)

    def _start_run_all(self, save_results, wait_for_advance):
        """Shared kickoff for on_run_all_clicked/on_debug_all_clicked -- see their own
        docstrings for what `save_results`/`wait_for_advance` mean."""
        if (self._run_all_active or self._auto_active or not self.label_to_path
                or self.view_mode_var.get() == "viewer"):
            return
        self._run_all_save_results = save_results
        self._run_all_wait_for_advance = wait_for_advance
        self._run_all_awaiting_key = False
        # A fixed snapshot taken now, not read live from self.label_to_path later -- so a net
        # file added/removed/renamed while Run All is already working through the list doesn't
        # change what's left to do partway through.
        self._run_all_paths = list(self.label_to_path.items())
        self._run_all_index = 0
        self._run_all_active = True
        self._start_next_run_all_net()

    def _start_next_run_all_net(self):
        """Loads self._run_all_paths[self._run_all_index] (on_select_net, exactly as if picked
        from the dropdown by hand) and kicks off its own Auto sequence (on_auto_clicked) --
        on_select_net's own defensive reset already clears self._auto_end_state back to None,
        so on_auto_clicked doesn't redundantly reload the net it was just given. Bumps
        self._run_all_poll_token and starts _poll_run_all_net watching for that sequence's own
        natural end, tagged with the NEW token -- see _run_all_poll_token's own comment (in
        __init__) for why every call here gets a fresh one."""
        label, _path = self._run_all_paths[self._run_all_index]
        self.net_var.set(label)
        self.on_select_net()
        self._update_window_title()
        run_label = "Debug All" if self._run_all_wait_for_advance else "Run All"
        self._set_status(
            f"{run_label} ({self._run_all_index + 1}/{len(self._run_all_paths)}): "
            f"running {label}...", "info")
        self.on_auto_clicked()
        self._run_all_poll_token += 1
        self._poll_run_all_net(self._run_all_poll_token)

    def _poll_run_all_net(self, token):
        """Watches the CURRENT net's own Auto sequence (self._auto_active) until it reaches a
        natural end, polling every 200ms rather than threading a callback through on_auto_
        clicked/_auto_step's own machinery (which has plenty of its own exit points already,
        e.g. Stop, a worker error, or genuinely finishing -- self._auto_active going False is
        the one signal all of them already funnel through, via _update_auto_button). `token`:
        this call's own poll chain's identity (self._run_all_poll_token at the moment
        _start_next_run_all_net started it) -- if it no longer matches the CURRENT value, a
        Left/Right-arrow jump (_debug_all_jump) abandoned this net for a different one while
        this chain was still watching it, so this call quietly does nothing instead of
        double-processing a net the jump already moved on from.

        Once the watched net genuinely finishes: saves this net's own .hippo (_write_session,
        no dialog -- straight to SESSION_OUTPUT_DIR under self.mesh_name), unless this run
        started via on_debug_all_clicked (self._run_all_save_results False). If
        self._run_all_wait_for_advance and there's a next net still to run, stops HERE and waits
        for the Right arrow key (_on_debug_all_right_key) rather than continuing immediately.
        Otherwise either starts the next net right away or, if this was the last one, ends the
        run via _finish_run_all."""
        if token != self._run_all_poll_token:
            return
        if self._auto_active:
            self.root.after(200, self._poll_run_all_net, token)
            return
        if self._run_all_save_results:
            SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = str(SESSION_OUTPUT_DIR / f"{self.mesh_name}{SESSION_FILE_EXTENSION}")
            self._write_session(output_path)
        self._run_all_index += 1
        if self._run_all_index < len(self._run_all_paths):
            if self._run_all_wait_for_advance:
                self._run_all_awaiting_key = True
                self._set_status(
                    f"Debug All ({self._run_all_index}/{len(self._run_all_paths)} done): "
                    f"press -> to continue to the next net, <- to go back.", "info")
                return
            self._start_next_run_all_net()
            return
        self._finish_run_all()

    def _finish_run_all(self):
        """Ends a Run All/Debug All run (reached the natural end of self._run_all_paths, or
        Left/Right jumped past either end of it -- see _debug_all_jump) and restores the plain
        window title. `self._run_all_save_results` is read BEFORE being reset, so the final
        status message still correctly says whether this was a real save or a dry run."""
        run_label = "Debug All" if not self._run_all_save_results else "Run All"
        saved_note = "" if self._run_all_save_results else " (results not saved)"
        total = len(self._run_all_paths)
        self._run_all_active = False
        self._run_all_wait_for_advance = False
        self._run_all_awaiting_key = False
        self._update_window_title()
        self._set_status(f"{run_label}: finished all {total} nets.{saved_note}", "success")

    def _on_debug_all_right_key(self):
        """The Right arrow key's own Debug-All-specific behavior (see the "<Right>" bind_all in
        ViewerPane.__init__) -- a no-op whenever Debug All isn't actually the thing running
        right now (self._run_all_active and self._run_all_wait_for_advance both True; a plain
        Run All run never sets the latter), so this key does nothing unexpected the rest of the
        time. Two cases: if a net just finished and Debug All is PAUSED waiting for this key
        (self._run_all_awaiting_key), resumes by starting the already-advanced next net --
        normal "continue" case. Otherwise a net is still mid-run: abandons it and jumps straight
        to the next one (_debug_all_jump), skipping whatever it hadn't gotten to yet."""
        if not (self._run_all_active and self._run_all_wait_for_advance):
            return
        if self._run_all_awaiting_key:
            self._run_all_awaiting_key = False
            self._start_next_run_all_net()
            return
        self._debug_all_jump(self._run_all_index + 1)

    def _on_debug_all_left_key(self):
        """The Left arrow key's own Debug-All-specific behavior -- same gating as
        _on_debug_all_right_key. Always means "go back and re-run the PREVIOUS net", whether
        the current one is still mid-run (abandoned) or already finished and Debug All is just
        paused on it (self._run_all_awaiting_key -- self._run_all_index already points PAST the
        just-finished net in that case, see _poll_run_all_net, so the net actually on screen
        right now is self._run_all_index - 1, and "previous" means one before THAT)."""
        if not (self._run_all_active and self._run_all_wait_for_advance):
            return
        shown_index = self._run_all_index - 1 if self._run_all_awaiting_key else self._run_all_index
        self._debug_all_jump(shown_index - 1)

    def _debug_all_jump(self, target_index):
        """Shared Left/Right-arrow-while-Debug-All-is-running logic: below 0 is a no-op --
        already at the first net, Left has nothing earlier to go back to, so this returns
        WITHOUT disturbing anything (whatever net is currently running, if any, keeps running
        exactly as if the key had never been pressed; a paused Debug All stays paused). Otherwise
        abandons whatever net is CURRENTLY mid-run, if any (same stop_event-based interrupt
        on_auto_stop_clicked uses -- _abort_auto marks the sequence stopped, on_stop_clicked
        actually signals the worker thread to unwind), then jumps straight to `target_index` --
        at or past the end of self._run_all_paths ends the run via _finish_run_all, same as
        reaching it normally would.

        Calling _start_next_run_all_net directly here (rather than letting the abandoned net's
        own _poll_run_all_net chain notice and continue on its own) is exactly why
        self._run_all_poll_token exists: that OLD chain is still scheduled to fire again in up
        to 200ms, and once self._auto_active does go False (moments after the abort below) it
        would otherwise run its OWN completion logic for the abandoned net too -- a second,
        stale _start_next_run_all_net/_finish_run_all racing the one this method just triggered.
        Bumping the token (inside _start_next_run_all_net, or directly here on the past-the-end
        path) makes that old chain recognize itself as stale and quietly stop instead."""
        if target_index < 0:
            return
        if self._auto_active:
            self.on_stop_clicked()  # signals stop_event (if any) AND calls _abort_auto
        self._run_all_awaiting_key = False
        if target_index >= len(self._run_all_paths):
            self._run_all_poll_token += 1
            self._finish_run_all()
            return
        self._run_all_index = target_index
        self._start_next_run_all_net()

    def _run_chunked_relax_stream(self, relax_fn, target_steps, stop_event, on_progress, on_finished):
        """Driver behind _run_relax_stream (Level 0's own Relax, its only remaining caller --
        Inflate's own equivalent was removed since pressure calibration's winning trial IS the
        Inflate result now, replayed from cached frames rather than recomputed). Calls
        `relax_fn(max_nfev, stop_event, queue_progress) -> result` once, in a background
        thread -- `max_nfev` is `target_steps` for "iterate for N steps" mode, or
        INFLATE_SAFETY_STEP_CAP otherwise (a single call already runs to real convergence or
        that cap on its own).

        No app-side chunking here -- relax_once/relax_initial_configuration accept
        `on_progress` directly and call it themselves every CONVERGENCE_CHECK_INTERVAL steps,
        exactly the cadence the stopping condition is itself checked at, so the UI redraws in
        sync with real convergence checks rather than an unrelated schedule. `queue_progress`
        bridges that callback (called from the background thread) to this queue/poll
        mechanism; Tk isn't thread-safe, so the worker only pushes to the queue, and the main
        thread (via the scheduled poll below) is the only one that touches Tk widgets."""
        q = queue.Queue()

        def queue_progress(*result):
            q.put(("progress", result))

        def worker():
            try:
                max_nfev = target_steps if target_steps is not None else INFLATE_SAFETY_STEP_CAP
                result = relax_fn(max_nfev, stop_event, queue_progress)
                q.put(("progress", result))
                q.put(("final", None))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            # Drains the whole queue every cycle, but coalesces "progress" messages down to
            # the latest one instead of calling on_progress once per queued message. If
            # physics runs faster than a single redraw, the worker thread can queue several
            # progress messages before poll() next runs -- older ones are immediately
            # superseded and would just be wasted render time. This is what avoids a
            # stall-then-jump: rendering every queued message, oldest first, would let a
            # backlog grow (each render taking longer than the interval it's trying to keep up
            # with) until the display caught up all at once; skipping to whatever's newest
            # each cycle keeps poll() itself fast, so "Simulation Time" and the panel stay
            # genuinely live.
            latest_progress = None
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        latest_progress = payload
                        continue
                    if latest_progress is not None:
                        on_progress(latest_progress)
                        latest_progress = None
                    if kind == "final":
                        on_finished()
                        return
                    elif kind == "error":
                        self._set_controls_enabled(True)
                        self._set_status(f"Failed: {payload}", "error")
                        self._abort_auto()  # nothing left to call _auto_step from otherwise
                        return
            except queue.Empty:
                if latest_progress is not None:
                    on_progress(latest_progress)
                else:
                    # Ticks "Simulation Time"/"Cumulative Time" live between actual progress
                    # events -- Level 0's own on_progress only fires every
                    # CONVERGENCE_CHECK_INTERVAL steps, which can leave the displayed time
                    # frozen for a while otherwise (same wall-clock-not-solver-progress idea
                    # _run_background's own poll loop uses for "Precomp time").
                    self._current_sim_time_s = time.perf_counter() - self._sim_start_time
                    self._record_level_history()
            self.root.after(80, poll)

        self.root.after(80, poll)

    def _finish_inflate(self):
        """Tail end of an Inflate click, called once _finish_frame_replay has already applied
        the winning calibration trial's final result to self.positions/last_stats/
        iteration_count -- this method only reports it (no `_current_sim_time_s` update here:
        Level 1+ has no separate "Sim" phase; all of a Level 1+ row's Simulation Time is
        "Precomp", already finalized in _on_pressure_calibrated)."""
        self._set_controls_enabled(True)
        self._set_level_action_button_running(False)
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        converged = self.last_stats.get("converged")
        max_stretch = self.last_stats.get("max_stretch_pct", 0.0)
        rms_stretch = self.last_stats.get("rms_stretch_pct", 0.0)
        self._record_level_history()
        if was_stopped:
            self._set_status(
                f"Stopped ({self.iteration_count} steps at level {self.subdivision_level}): "
                f"edges stretched up to {max_stretch:.2f}% from rest length "
                f"(RMS {rms_stretch:.1f}%).", "warn")
        elif converged:
            self._set_status(
                f"Converged after {self.iteration_count} steps at level "
                f"{self.subdivision_level}: edges stretched up to {max_stretch:.2f}% from rest "
                f"length (RMS {rms_stretch:.1f}%).", "success")
        else:
            self._set_status(
                f"Inflated ({self.iteration_count} steps at level {self.subdivision_level}, "
                f"step cap reached): edges stretched up to {max_stretch:.2f}% from rest length "
                f"(RMS {rms_stretch:.1f}%).",
                "info")
        self._auto_step()  # no-op unless Auto is what actually drove this run

    # ---- relax (Level 0 only) ----

    def on_relax_clicked(self):
        """Level 0's analogue of on_inflate_clicked -- no pressure to calibrate first (pure
        springs), so this goes straight to the streamed run. Always runs to convergence
        (ignores the debug-mode steps-vs-convergence choice, which only applies to Inflate) --
        Relax's whole point is to finish the initial-configuration algorithm, not to be
        steppable.

        Shows the same "Computing..." placeholder Levels 1-3 show during pressure calibration,
        and replays its own captured frames once done, exactly like Levels 1-3's own Inflate
        (2026-10-01, explicit: "when it's computing, it should say Computing... like the other
        levels. then when it's done, it should replay like the other levels" -- previously kept
        redrawing live throughout instead of either)."""
        if self.positions is None or self.subdivision_level != 0 or self.last_stats.get("converged"):
            return
        # Same capture-once rationale as _on_pressure_calibrated -- see self._current_gtol.
        self._current_gtol = self._get_tolerance()
        self.stop_event = threading.Event()
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        # Starting frame for this click's own replay (see _apply_relax_progress for the rest) --
        # fresh every click, same as Levels 1-3's own self._level_frames[level]: only the MOST
        # RECENT Relax click's run is ever replayed/scrubbable, not a history across clicks.
        self._level0_relax_frames = [(self.positions, self.iteration_count)]
        self._start_computing_animation(0)
        self._set_status("Relaxing random start into a well-separated shape...", "info")
        # Level 0 has no pressure-calibration phase -- "Precomp time" stays "--"; only "Sim
        # time" applies here, starting now.
        self._sim_start_time = time.perf_counter()
        self._run_relax_stream(self.stop_event)

    def _run_relax_stream(self, stop_event):
        faces, edge_length = self.faces, self.edge_length
        gtol = self._current_gtol
        # KICK_WINDOW's random-perturbation mechanism is disabled here -- found to interact
        # badly with a genuinely slow (not stuck) relaxation, re-disturbing the mesh right as
        # it converges. See LEVEL0_STEP_MAX_MULTIPLIER in stretchy_mesh.py.
        rng = None
        # relax_initial_configuration's own `nfev`/`steps_taken` is the cumulative count for
        # this one call, but self.iteration_count needs to keep accumulating across separate
        # Relax clicks at Level 0 too (reset only on promotion) -- so this call's own
        # contribution is `base_iteration_count + nfev`, not nfev alone.
        base_iteration_count = self.iteration_count
        # Read on the MAIN thread (this method itself, never relax_fn -- that runs inside
        # _run_chunked_relax_stream's own worker thread, where touching self.seed_var, a Tk
        # StringVar, would be unsafe) -- relax_initial_configuration_with_orientation_retry
        # below regenerates its own fresh starting cloud per attempt from this seed rather than
        # consuming self.positions (the single-seed raw cloud on_select_net already set, kept
        # only as the level's own pre-Relax preview/restart snapshot -- see
        # _capture_level_start_state).
        seed = self._get_or_generate_seed()

        def relax_fn(max_nfev, stop_event, on_progress):
            result = relax_initial_configuration_with_orientation_retry(
                faces, edge_length, seed=seed, base_faces=self.base_faces,
                max_nfev=max_nfev, stop_event=stop_event,
                gtol=gtol, rng=rng, on_progress=on_progress, edges=self.edges,
                rms_exclude_edges=self._rms_exclude_edges(),
                pressure_exclude_faces=self._pressure_exclude_faces())
            *relax_result, seed_used = result
            # A plain attribute write (not a Tk widget touch) -- safe from the worker thread;
            # _finish_relax (back on the main thread) applies it to self.seed_var itself. Only
            # differs from `seed` above when a retry (or the free mirror fix) was needed -- see
            # relax_initial_configuration_with_orientation_retry's own docstring.
            self._pending_level0_seed_used = seed_used
            return tuple(relax_result)

        self._run_chunked_relax_stream(relax_fn, None, stop_event,
                                        lambda result: self._apply_relax_progress(result, base_iteration_count),
                                        self._finish_relax)

    def _apply_relax_progress(self, result, base_iteration_count):
        positions, nfev, max_stretch, rms_stretch, optimality, converged = result
        self.positions = positions
        self.iteration_count = base_iteration_count + nfev
        # Captured for _finish_relax's own replay once the run is done (2026-10-01, explicit:
        # "when it's done, it should replay like the other levels") -- the panel itself shows
        # the "Computing..." placeholder meanwhile (_start_computing_animation, called from
        # on_relax_clicked), not a live redraw of this tick's positions.
        self._level0_relax_frames.append((positions, self.iteration_count))
        # optimality/converged are stashed here, NOT written into self.last_stats -- Level 0's
        # own Convergence column shows "--" for the whole time Relax is running, same
        # "--"-while-unknown sentinel Level 1-3's Computing phase uses, via
        # last_stats["optimality"] staying None throughout. _finish_relax reveals it, reading
        # the real final value back from here.
        self._pending_relax_stats = {"optimality": optimality, "converged": converged}
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": None, "converged": None,
                            "gtol": self._current_gtol}
        self._current_sim_time_s = time.perf_counter() - self._sim_start_time
        self._record_level_history()
        self._set_status(f"Relaxing... {self.iteration_count} steps so far "
                          f"(edges stretched up to {max_stretch:.2f}%).", "info")

    def _finish_relax(self):
        # Reveals whatever seed relax_initial_configuration_with_orientation_retry actually
        # used (see _run_relax_stream) -- almost always the one already shown, but a retry (or
        # the free mirror fix) can mean the RETURNED shape came from a different seed than what
        # was requested; the displayed/stored seed should reflect the shape that's now actually
        # on screen, not the one merely asked for.
        seed_used = getattr(self, "_pending_level0_seed_used", None)
        if seed_used is not None:
            self.seed_var.set(str(seed_used))
            self._pending_level0_seed_used = None
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        # Reveals the real optimality/converged now -- see _apply_relax_progress for why these
        # were stashed separately rather than kept live in self.last_stats. Applies regardless
        # of how this run ended (converged, Stopped, or step-cap).
        pending = getattr(self, "_pending_relax_stats", {})
        self.last_stats["optimality"] = pending.get("optimality")
        self.last_stats["converged"] = pending.get("converged")
        self._current_sim_time_s = time.perf_counter() - self._sim_start_time
        self._record_level_history()
        self._stop_computing_animation()
        if was_stopped:
            # Nothing finished to replay -- same as _on_pressure_calibrated's own stopped
            # branch, which also skips straight to reporting rather than starting a replay.
            max_stretch = self.last_stats.get("max_stretch_pct", 0.0)
            rms_stretch = self.last_stats.get("rms_stretch_pct", 0.0)
            self._set_status(
                f"Stopped ({self.iteration_count} relax steps): edges stretched up to "
                f"{max_stretch:.2f}% from rest length (RMS {rms_stretch:.1f}%).", "warn")
            self._set_controls_enabled(True)
            self._set_level_action_button_running(False)
            self.draw()
            self._auto_step()  # no-op unless Auto is what actually drove this run
            return
        # Replays this click's own run (2026-10-01, explicit: "when it's done, it should
        # replay like the other levels"). self.positions is ALREADY the true final value here
        # (set live, tick by tick, by _apply_relax_progress) -- unlike Inflate's own calibration
        # replay, there's no separate "apply the real result" step needed, just carrying it
        # through apply_final so replay's own intermediate frames don't leave it pointed at an
        # earlier one.
        final_positions = self.positions
        frames = self._level0_relax_frames
        if frames[-1][0] is not final_positions:
            frames.append((final_positions, self.iteration_count))
        self._level_frames[0] = frames
        self._level_scrub_index[0] = len(frames) - 1
        self._update_replay_slider(0)
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self._set_status("Replaying the relax...", "info")
        self._start_frame_replay(
            frames, lambda: setattr(self, "positions", final_positions),
            self._finish_relax_report)

    def _finish_relax_report(self):
        """Tail end of a Relax click, called once _finish_frame_replay has already replayed
        this run's captured frames and restored self.positions to its true final value --
        reports status and, on convergence, promotes to Level 1 (or, if BYPASS_LEVEL_1_INFLATE,
        straight on through to Level 2 -- see that flag's own comment). Split out of
        _finish_relax so replay can sit between "the run itself just finished" and "report it",
        same shape as Inflate's own on_inflate_clicked/_on_pressure_calibrated/_finish_inflate."""
        converged = self.last_stats.get("converged")
        max_stretch = self.last_stats.get("max_stretch_pct", 0.0)
        rms_stretch = self.last_stats.get("rms_stretch_pct", 0.0)
        if converged:
            # Level 0 and Level 1 share the exact fan-triangulated topology -- promoting the
            # just-relaxed result into Level 1's starting position is a pure relabeling, not a
            # new subdivide_once call.
            self.level_snapshots[0] = {"faces": self.faces, "positions": self.positions,
                                        "face_of_fine": self.face_of_fine}
            level0_button = self.level_action_buttons.get(0)
            if level0_button is not None:
                level0_button.config(text="Relax", command=self.on_relax_clicked)
            self.subdivision_level = 1
            self._capture_level_start_state()
            self.iteration_count = 0
            # Same reset as _subdivide_step's own.
            self._current_precomp_time_s = None
            self._current_sim_time_s = None
            self._current_target_rms_pct = self.target_rms_vars[1].get()
            self.last_stats = self._compute_stretch_stats()
            self._record_level_history()
            if BYPASS_LEVEL_1_INFLATE:
                # _subdivide_step snapshots Level 1's own (never-inflated) mesh exactly as left
                # above, then quarters it straight into Level 2 -- its own bookkeeping (another
                # _capture_level_start_state/_compute_stretch_stats/_record_level_history, this
                # time for Level 2) supersedes the Level-1-specific calls just above, same as an
                # ordinary Subdivide click immediately following a Relax would.
                self._subdivide_step()
                self._set_status(
                    f"Relaxed (edges stretched up to {max_stretch:.2f}% from rest length, RMS "
                    f"{rms_stretch:.1f}%). Bypassed Level 1 -- subdivided straight to Level 2 "
                    f"({len(self.faces)} faces, {len(self.positions)} vertices). Press Inflate "
                    "to continue.", "info")
            else:
                self._set_status(
                    f"Relaxed (edges stretched up to {max_stretch:.2f}% from rest length, RMS "
                    f"{rms_stretch:.1f}%). Promoted to Level 1 -- press Inflate to continue.",
                    "info")
        else:
            self._set_status(
                f"Relaxed ({self.iteration_count} steps, step cap reached): edges stretched up "
                f"to {max_stretch:.2f}% from rest length (RMS {rms_stretch:.1f}%). Press Relax "
                "again to continue.", "info")
        self._set_controls_enabled(True)
        self._set_level_action_button_running(False)
        # draw() again here (on top of _finish_frame_replay's own) only actually redraws
        # anything new in the converged branch above -- subdivision_level/level_snapshots just
        # changed, so the Net panel's current-level highlight and the now-current frontier
        # panel (Level 1, or Level 2 if BYPASS_LEVEL_1_INFLATE) need a fresh draw() that
        # _finish_frame_replay's own (taken while still at Level 0) couldn't have shown.
        self.draw()
        self._auto_step()  # no-op unless Auto is what actually drove this run

    # ---- background worker (used by pressure calibration) ----

    def _set_controls_enabled(self, enabled):
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (self.combo, self.tolerance_spin, self.seed_spin,
                       self.steps_radio, self.convergence_radio,
                       self.show_normals_check,
                       self.show_vertex_normals_check, self.show_repulsive_forces_check,
                       self.auto_button, *self.target_rms_spins.values()):
            widget.state(state)
        if enabled:
            self._update_mode_state()  # respect the steps/convergence choice
            self._update_level_action_buttons()  # respect the converged-at-this-pressure gate
        else:
            self.steps_spin.state(["disabled"])
            # The frontier level's action button is deliberately left alone here -- the
            # caller re-enables it right after, turned into the Stop control; every other
            # level's stays disabled, since it was never eligible anyway.
            for level, button in self.level_action_buttons.items():
                if level != self.subdivision_level:
                    button.state(["disabled"])
        # self.auto_button was just blanket-(dis)abled above -- re-sync it regardless of which
        # branch ran: while an Auto sequence is driving the run, this re-enables it (reading
        # "Stop Simulation"), the same "frontier button survives the blanket disable"
        # exception _set_level_action_button_running makes for the per-level buttons.
        self._update_auto_button()

    def _run_background(self, fn, on_done, on_progress=None):
        """Run fn(queue_progress) in a background thread and call on_done(result) on the main
        thread once it finishes -- used for on_inflate_clicked's pressure calibration, which
        can take a moment. `queue_progress` is a callable fn may call from the background
        thread (Tk isn't thread-safe, so it only pushes to a queue) to report live progress;
        the main thread (via the scheduled poll below) calls `on_progress(payload)` with
        whatever fn last reported. (Relax has its own streaming variant, _run_relax_stream,
        since it needs a live panel redraw too.)

        Progress messages are coalesced, same as _run_chunked_relax_stream's own poll: only
        the latest queued progress payload is passed to `on_progress` per poll cycle, older
        ones dropped as superseded. "Precomp time"/"Cumulative Time" tick live on every poll
        cycle unconditionally (not gated behind an "else" alongside on_progress -- with
        progress messages arriving on essentially every poll during calibration, an "else"
        branch would almost never run, leaving "Simulation Time" visibly frozen for Level
        1-3 specifically)."""
        self._set_controls_enabled(False)
        q = queue.Queue()

        def queue_progress(payload):
            q.put(("progress", payload))

        def worker():
            try:
                q.put(("done", fn(queue_progress)))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            latest_progress = None
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        latest_progress = payload
                        continue
                    if latest_progress is not None and on_progress is not None:
                        on_progress(latest_progress)
                    self._set_controls_enabled(True)
                    if kind == "error":
                        self._set_status(f"Failed: {payload}", "error")
                        self._abort_auto()  # nothing left to call _auto_step from otherwise
                        return
                    on_done(payload)
                    return
            except queue.Empty:
                pass
            # Unconditional -- see this method's own docstring.
            self._current_precomp_time_s = time.perf_counter() - self._precomp_start_time
            if latest_progress is not None and on_progress is not None:
                on_progress(latest_progress)  # also refreshes the history table itself
            else:
                self._record_level_history()
            self.root.after(100, poll)

        self.root.after(100, poll)

    # ---- drawing ----

    def _draw_target_faces(self, theme):
        """The undeformed net: every face laid out flat and connected to its neighbors
        (self.target_layout, precomputed once per net selection via a BFS over shared edges)
        -- what the mesh would look like cut out of paper and unfolded flat, before any
        stretching/bending closes it into the solved 3D shape.

        Always shows the base (level 0) polygons -- not the current level's fine triangles,
        and no fine-mesh subdivision overlay either -- just the plain base faces, as a 2D
        preview of the mesh actually being solved. When the loaded net carries
        interactive_builder_app's own saved connections (self.target_connections), each one's
        bezier curve is drawn too -- never its handles, since this panel is read-only."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        # self.target_layout's keys live in self.target_group_of_face's id space (see
        # net_loading.target_layout_and_connections's own docstring) -- NOT necessarily
        # self.color_by_group's key space (Multi-colour mode keys that by base-face position,
        # which only coincidentally matches). Rebuilt fresh each draw from the flat,
        # mode-agnostic self.colors list instead of indexing self.color_by_group directly.
        target_color_by_group = {}
        for i, g in enumerate(self.target_group_of_face):
            target_color_by_group.setdefault(g, self.colors[i])
        all_pts = []
        for face_idx in sorted(self.target_layout):
            color = target_color_by_group[face_idx]
            placed = self.target_layout[face_idx]
            self.ax2d.add_patch(Polygon(placed, closed=True, facecolor=color,
                                         edgecolor="k", alpha=0.9))
            all_pts.extend(placed)

        if self.target_connections:
            for conn in self.target_connections:
                curve = _connection_curve_points(self.target_layout, conn)
                if curve is not None:
                    xs, ys = zip(*curve)
                    self.ax2d.plot(xs, ys, color=CONNECTION_CURVE_COLOR,
                                    linewidth=CONNECTION_CURVE_WIDTH,
                                    zorder=CONNECTION_CURVE_ZORDER)
                    # A bezier's control points can bow it well past its two faces' combined
                    # extent (the whole point of dragging a handle) -- feeding its sampled
                    # points into the same bounding box the faces use below keeps a bulging
                    # curve from getting clipped at the panel edge.
                    all_pts.extend(curve)

        all_pts = np.array(all_pts)
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        pad = 0.6
        # self.net_zoom shrinks/grows this half-extent around the layout's center (Net
        # panel's own analogue of every "Level N" panel's self.level_zoom).
        # self.net_pan (world-unit offset, right-drag) shifts this same center independently
        # of net_zoom -- analogue of self.level_pan, a plain 2D offset here rather than a 3D
        # one added to a PyVista camera.
        center = (lo + hi) / 2 + self.net_pan
        half_range = (hi - lo) / 2 + pad
        # Stretched to the panel's own aspect ratio before dividing by zoom, rather than
        # handing set_aspect("equal") two independent half_range values and letting it shrink
        # whichever axis has proportionally less content (its default adjustable="box"
        # behavior, which reads as thicker margins than every "Level N" panel's own
        # aspect handling gets -- see camera.parallel_scale's analogous term in
        # _render_level_pv). Whichever axis needs more room wins; the other is grown to
        # match, so set_xlim/set_ylim already fills the panel and set_aspect has nothing left
        # to shrink.
        panel_aspect = NET_PANEL_SIZE[0] / NET_PANEL_SIZE[1]
        half_y = max(half_range[1], half_range[0] / panel_aspect)
        half_range = np.array([half_y * panel_aspect, half_y]) / self.net_zoom
        self.ax2d.set_xlim(center[0] - half_range[0], center[0] + half_range[0])
        self.ax2d.set_ylim(center[1] - half_range[1], center[1] + half_range[1])
        self.ax2d.set_aspect("equal")
        # No ax.set_title() here -- "Net" is a plain Tkinter Label above this canvas, same as
        # every "Level N" panel's title.

    def _on_net_scroll(self, event):
        """Mouse-wheel-scroll on the Net panel zooms it (self.net_zoom) -- the Net panel's own
        analogue of _on_level_scroll, scaling _draw_target_faces' bounding-box half-extent
        instead of a PyVista camera. Only the Net panel redraws -- net_zoom has no effect on
        the "Level N" panels, so re-rendering their off-screen scenes here would be wasted."""
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / NET_ZOOM_STEP
        else:
            factor = NET_ZOOM_STEP
        self.net_zoom = max(NET_ZOOM_MIN, min(NET_ZOOM_MAX, self.net_zoom * factor))
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_idle_all()

    def _on_net_pan_start(self, event):
        self._net_panning = True
        self._net_pan_last_xy = (event.x, event.y)

    def _on_net_pan_motion(self, event):
        """Right-click-drag on the Net panel translates it (self.net_pan, added directly to
        _draw_target_faces' bounding-box center) -- analogue of _on_level_pan_motion, a plain
        2D data-space offset instead of a 3D one through a PyVista camera, since this panel is
        matplotlib. Converts the screen-pixel drag into data units via the axes' current
        x/ylim and the canvas widget's current pixel size (both already reflect zoom, so this
        stays a 1:1 drag at any zoom level). Sign convention: shifting the view's center by
        -dx (x) or +dy (y) in data units is what makes a fixed data point's screen position
        move by the mouse's own (dx, dy) -- the y sign flips relative to x because Tk widget
        pixels grow downward while this axes' data y grows upward."""
        if not self._net_panning or self._net_pan_last_xy is None:
            return
        last_x, last_y = self._net_pan_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        widget = self.canvas_net.get_tk_widget()
        width_px, height_px = widget.winfo_width(), widget.winfo_height()
        if width_px <= 1 or height_px <= 1:
            return
        xlim, ylim = self.ax2d.get_xlim(), self.ax2d.get_ylim()
        data_per_pixel_x = (xlim[1] - xlim[0]) / width_px
        data_per_pixel_y = (ylim[1] - ylim[0]) / height_px
        self.net_pan = self.net_pan + np.array([-dx * data_per_pixel_x, dy * data_per_pixel_y])
        self._net_pan_last_xy = (event.x, event.y)
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_idle_all()

    def _on_net_pan_end(self, event):
        self._net_panning = False
        self._net_pan_last_xy = None

    def _on_net_pan_reset(self, event=None):
        """Middle-click on the Net panel resets pan and zoom back to their defaults -- same
        idea as _on_level_pan_reset, minus rotation, which this 2D panel has none of."""
        self.net_pan = np.zeros(2)
        self.net_zoom = 1.0
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_idle_all()

    def draw(self):
        """Redraws the Net panel plus every "Level N" panel: level == self.subdivision_level
        draws live from current state; a level in self.level_snapshots (already subdivided
        past, or -- for Level 0 -- promoted away from) draws its frozen state; any other level
        hasn't been reached yet and draws empty.

        Level 0 specifically draws empty too, even though it's self.subdivision_level and
        self.positions already holds a real (random-initial, or in-progress-relaxed) cloud,
        UNLESS self._level_frames[0] is already populated -- i.e. at least one Relax run has
        actually finished and been replayed (2026-10-01, explicit: "for level 0, don't show the
        initial random state at the start... stuff is only shown after simulation done and it's
        showing the replay"). Doesn't affect replay ITSELF (_replay_step draws Level 0's panel
        directly, bypassing this method entirely) or the "Computing..." placeholder (already
        blanks the panel on its own, via _start_computing_animation) -- only this general redraw
        path, which otherwise ran right after on_select_net and would show raw noise.

        A level with an active replay-slider scrub (self._level_frames/_level_scrub_index both
        set for it) shows that captured frame's positions instead of its live/frozen ones --
        faces/face_of_fine are unaffected (a captured trajectory never changes topology, only
        positions over time) -- self.positions/level_snapshots themselves are left untouched
        either way, so this is purely a display override."""
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        for level in self.level_plotters:
            if level == self.subdivision_level:
                if level == 0 and not self._level_frames.get(0):
                    faces = positions = face_of_fine = None
                else:
                    faces, positions, face_of_fine = self.faces, self.positions, self.face_of_fine
            elif level in self.level_snapshots:
                snap = self.level_snapshots[level]
                faces, positions, face_of_fine = (snap["faces"], snap["positions"],
                                                    snap["face_of_fine"])
            else:
                faces = positions = face_of_fine = None
            frames = self._level_frames.get(level)
            scrub_idx = self._level_scrub_index.get(level)
            if faces is not None and frames and scrub_idx is not None:
                positions = frames[scrub_idx][0]
            self._draw_level_panel(level, faces, positions, face_of_fine)
        self._draw_idle_all()


def main():
    root = tk.Tk()
    InflatePolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
