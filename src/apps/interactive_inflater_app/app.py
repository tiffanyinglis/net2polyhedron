"""Interactive Inflater -- combines interactive_builder_app's net-building
canvas (left pane) with a simplified, single-panel version of
inflate_polyhedron_app's solver viewer (right pane) in one window, so a net
built by hand can be inflated immediately with no save/load round trip.

    python src/apps/interactive_inflater_app/app.py

Left pane (BuilderPane): reuses interactive_builder_app.app.InteractiveBuilderApp
directly (imported, not copied -- that file is read-only here, see the
net-fold-project skill's untouchable.md) via a small subclass that only
overrides layout (_build_ui/_build_palette_entry: shape palette moved to a
TOP row, centered; the Move/Join/Polygon-Fold tool strip moved to the LEFT,
matching this app's own required layout) and drops the pieces that only make
sense for a standalone window (its own File menu/window title/WM_DELETE_
WINDOW/font-scaling pass -- CombinedApp builds ONE File menu, with just
Load... (no Save yet, 2026-09-19, explicit), for the whole window instead).
Every canvas interaction (place/drag/select/delete/rotate/pan, Move/Join/
Fold modes, bezier connections, Polygon Fold, undo/redo, flip, debug mode)
is exactly interactive_builder_app's own, unmodified.

Right pane (InflaterPane): a from-scratch, deliberately much simpler sibling
of inflate_polyhedron_app -- one PyVista off-screen-rendered panel (not four
side-by-side Level 0-3 panels), redrawn in place as "Inflate" advances
through the SAME pipeline inflate_polyhedron_app's "Run Simulation" runs
(Level 0 fan-triangulate -> Relax -> calibrate to target RMS -> Subdivide ->
repeat through MAX_LEVEL). No replay-frame animation, no per-level camera
groups, no Convergence History table, no debug mode/normals/mesh validation,
no Stop button -- see the module's own "Simplifications vs.
inflate_polyhedron_app" note below for the full list and why.

Bridging the two panes: clicking Inflate reads the LEFT pane's CURRENT
in-memory shapes/connections through the exact same
_expand_folded_shapes/_faces_from_shapes/_edges_from_shapes/
_face_edge_ids_from_shapes pipeline interactive_builder_app's own Save uses
(BuilderPane.export_mesh_dict, calling the inherited _export_faces_and_layout
directly), producing the same mesh dict Save would write to a .poly file --
without ever writing one. stretchy_mesh.load_stretchy_mesh/
load_stretchy_mesh_edges (this project's one authoritative parser+validator
for that format) only accept a file PATH, and are on this project's
untouchable list (no signature changes allowed) -- rather than reimplement
their validation a second time here (real risk of it drifting from the
original), _load_mesh_from_dict writes the dict to a throwaway
tempfile.NamedTemporaryFile, calls those same two functions on it, and
deletes it immediately after -- the mesh itself is never written to (or
read from) any file under data/, only this one transient temp file that
never outlives a single Inflate click.

Simplifications vs. inflate_polyhedron_app (all explicitly allowed by this
app's own spec):
- One drawing panel, redrawn per level, not four side-by-side ones.
- No replay-frame capture/animation -- estimate_pressure_for_target_stretch
  is called with capture_frames=False; the winning trial's final result is
  applied and drawn directly.
- No per-level independent camera groups/pan/drag/scroll -- the single
  panel auto-frames itself fresh on every redraw (PyVista's own "iso" view
  + reset_camera()), no interactive camera at all.
- No Convergence History table, no session save/load, no Stop button, no
  debug mode (normals/mesh validation), no steps-vs-convergence radio.
- Per-level target RMS %/tolerance entries and DEFAULT_TOLERANCE are
  adapted directly from inflate_polyhedron_app's own setup row.
"""
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import json
import os
import queue
import tkinter as tk
from tkinter import messagebox, ttk
import tkinter.font as tkfont

import numpy as np
from PIL import Image, ImageTk
import pyvista as pv
from scipy.spatial.transform import Rotation
import sv_ttk

import common.paths  # noqa: F401 -- side effect: puts src/ and src/apps/ on sys.path
from common.ui_theme import FACE_COLORS, PLOT_THEME, STATUS_COLORS

from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.inflate_polyhedron.stretchy_mesh import (
    EDGE_LENGTH, estimate_pressure_for_target_stretch, load_stretchy_mesh,
    load_stretchy_mesh_edges, mesh_edges, random_initial_positions,
    relax_initial_configuration,
)

# interactive_builder_app/app.py is NOT on the untouchable list, but per this app's own
# instructions it's still read-only from here -- imported directly (a plain namespace-package
# import, src/apps/ already being on sys.path) rather than copied, so its ~3700 lines of net-
# building logic are reused verbatim, not duplicated.
from interactive_builder_app.app import (
    ICON_SIZE, MENU_ACTIVE_BG, MENU_BG, MENU_DISABLED_FG, MENU_FG, NetValidationError,
    POLYGON_COLORS, POLYGON_NS, InteractiveBuilderApp, _ICON_VERTICES, _rasterize_polygon,
    _enable_windows_dpi_awareness,
)

INFLATER_APP_DIR = Path(__file__).resolve().parent

# Same idea as both sibling apps' own UI_FONT_SCALE -- applied once, centrally, to every named
# Tk/ttk font at startup. InteractiveBuilderApp normally does this itself in __init__; BuilderPane
# overrides that step out (see its own docstring) so it only ever happens once for the whole
# combined window, not once per pane. Smaller than the two sibling apps' own 1.3 -- this window
# packs a full builder AND a full inflater side by side, so it needs smaller text to fit
# comfortably (2026-09-19, explicit).
UI_FONT_SCALE = 1.0

# Palette icons (BuilderPane._build_palette_entry, below) are shrunk to this size -- smaller than
# interactive_builder_app's own ICON_SIZE=84, since this app's palette row has roughly half that
# app's own window width to work with (half the window is the inflater pane). _ICON_VERTICES
# (imported from interactive_builder_app, fixed at ICON_RADIUS=30 regardless of ICON_SIZE) is
# scaled down by INFLATER_ICON_SIZE/ICON_SIZE to match, preserving the same padding ratio.
INFLATER_ICON_SIZE = 48

# ---- right pane (InflaterPane) constants, adapted from inflate_polyhedron_app ----

DEFAULT_TOLERANCE = 1e-4
LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 80.0, 2: 40.0, 3: 10.0}
# Hard per-attempt step cap (Relax and each Inflate calibration trial's own convergence top-up)
# -- same constant/value as inflate_polyhedron_app's own INFLATE_SAFETY_STEP_CAP, duplicated
# rather than imported (this app never imports that module -- see its own docstring).
SAFETY_STEP_CAP = 50000

# Smaller than inflate_polyhedron_app's own Level-1..3 panels would suggest (LEVEL_PANEL_WIDTH_
# LEVELS_1_3 x LEVEL_PANEL_HEIGHT there) would be too cramped for a SINGLE panel carrying all the
# detail 4 panels normally split -- this sits between that and this app's earlier, too-large
# 620x560 (2026-09-19, explicit: "make it smaller").
PANEL_SIZE = (420, 450)

# Same trackball-drag/pan/scroll-zoom idea and constants as inflate_polyhedron_app's own
# "Level N" panels (LEVEL_DEFAULT_ELEV/AZIM/LEVEL_DRAG_SENSITIVITY/LEVEL_ZOOM_STEP/_MIN/_MAX/
# _level_zoom_fill), duplicated rather than imported (see module docstring) and renamed without
# the "LEVEL_" prefix since this app has only ever the one panel (2026-09-19, explicit: "not
# rotatable/movable/scaling right now").
PANEL_DEFAULT_ELEV = 30.0
PANEL_DEFAULT_AZIM = -60.0
PANEL_DRAG_SENSITIVITY = 0.5
PANEL_ZOOM_STEP = 1.1
PANEL_ZOOM_MIN = 0.3
PANEL_ZOOM_MAX = 4.0
PANEL_ZOOM_FILL = 0.9


def _is_valid_numeric_partial(proposed, allow_exponent, allow_decimal=True):
    """True if `proposed` is a full number or a prefix a user could still be typing toward one
    -- same validation idea as inflate_polyhedron_app's own _is_valid_numeric_partial
    (duplicated, not imported -- a tiny, self-contained regex check, not worth pulling in that
    whole module for)."""
    digits = r"\d*\.?\d*" if allow_decimal else r"\d*"
    pattern = f"-?{digits}(?:[eE][-+]?\\d*)?" if allow_exponent else f"-?{digits}"
    return re.fullmatch(pattern, proposed) is not None


def _build_level1_topology(base_faces):
    """Level 0 and Level 1 share this exact fan-triangulated topology -- same construction as
    inflate_polyhedron_app's own _build_level1_topology (duplicated, not imported -- see module
    docstring). Calls subdivide_once with placeholder positions purely to get the resulting
    faces/edge_length/face_of_fine; the interpolated positions it also returns are meaningless
    and discarded."""
    dummy_positions = {v: np.zeros(3) for face in base_faces for v in face}
    faces, _, edge_length, face_of_fine = subdivide_once(
        base_faces, dummy_positions, EDGE_LENGTH, list(range(len(base_faces))), 0)
    return faces, edge_length, face_of_fine


def _fan_level_edges(faces, base_edges):
    """Level 0/1's own explicit spring-edge override -- same construction as
    inflate_polyhedron_app's own _fan_level_edges (duplicated, see module docstring).
    `base_edges` (from load_stretchy_mesh_edges) is None for a mesh with no explicit "edges"
    field, in which case this returns None too (mesh_edges' own vertex-pair fallback is safe)."""
    if base_edges is None:
        return None
    base_vertex_ids = {v for e in base_edges for v in e}
    spokes = [e for e in mesh_edges(faces)
              if not (e[0] in base_vertex_ids and e[1] in base_vertex_ids)]
    return list(base_edges) + spokes


def _load_mesh_from_dict(mesh_dict):
    """mesh_dict: {"name", "faces", "edges", "face_edge_ids", ...} as built by
    BuilderPane.export_mesh_dict. Returns (faces, base_edges, face_edge_ids) -- `faces` the
    vertex-loop list, `base_edges` the explicit mesh-edge list from `mesh_dict["edges"]` if
    present else None, `face_edge_ids` likewise from `mesh_dict["face_edge_ids"]` (both matching
    load_stretchy_mesh_edges's own return convention -- see its own docstring on why a mesh with
    duplicate/ambiguous edges, e.g. composite_spider_leg.poly, NEEDS face_edge_ids to subdivide
    correctly past Level 1: dropping it, as an earlier version of this function did, is what let
    such a net inflate fine in inflate_polyhedron_app but come out wrong here -- see
    _on_inflate_step_done's own subdivide_once call, which now threads this through).
    Raises ValueError if the mesh fails load_stretchy_mesh's own winding validation.

    load_stretchy_mesh/load_stretchy_mesh_edges (stretchy_mesh.py, untouchable -- see the
    net-fold-project skill) only accept a file PATH, and are this project's one authoritative
    parser+validator for this format -- reimplementing that validation a second time here would
    risk drifting from the original. Instead, this writes `mesh_dict` to a throwaway temp file,
    calls those same two functions on it, and deletes it immediately after -- the mesh is never
    written to (or read from) any file under data/, only this one transient file that never
    outlives a single call."""
    fd, path = tempfile.mkstemp(suffix=".poly", dir=str(INFLATER_APP_DIR))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(mesh_dict, f)
        faces, _name = load_stretchy_mesh(path)
        base_edges, face_edge_ids = load_stretchy_mesh_edges(path)
    finally:
        os.remove(path)
    return faces, base_edges, face_edge_ids


# ---- left pane ----

class BuilderPane(InteractiveBuilderApp):
    """interactive_builder_app's own canvas, embedded in a container frame instead of a real
    Toplevel and re-laid-out per this app's own spec: the shape palette in a TOP row, the
    Move/Join/Polygon-Fold tool strip on the LEFT (where the palette used to be), canvas filling
    the rest. Every other method (drag/select/rotate/connections/undo/flip/debug mode/Polygon
    Fold/_export_faces_and_layout) is inherited from InteractiveBuilderApp unchanged.

    `container` must tolerate the whole-WINDOW-only calls InteractiveBuilderApp.__init__ (and
    _build_menu/_update_title/_on_quit_request) make on self.root -- title()/geometry()/
    minsize()/protocol()/config(menu=...) -- none of which make sense for an embedded pane;
    see _PaneRoot below."""

    def _scale_ui_fonts(self):
        """No-op override -- the combined app scales every named font ONCE, centrally
        (see CombinedApp), before either pane is built. InteractiveBuilderApp's own version,
        left to run again here, would double-scale every font (it mutates the same
        interpreter-wide named fonts BuilderPane and InflaterPane both read)."""

    def _build_ui(self):
        self.status_label = ttk.Label(self.root, anchor="w", padding=(8, 3))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        top = ttk.Frame(self.root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)
        # Icons packed into an INNER frame that itself is centered in `top` (pack's default
        # anchor="center" centers a non-filling child within its parcel) -- packing the icons
        # straight into `top` (which fills X) would leave them flush left instead
        # (2026-09-19, explicit: "centre-align the n-gon buttons").
        palette_row = ttk.Frame(top)
        palette_row.pack(side=tk.TOP)
        for n in POLYGON_NS:
            self._build_palette_entry(palette_row, n)

        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(side=tk.LEFT, fill=tk.Y)
        self._build_toolbar(toolbar)

        self.canvas = tk.Canvas(self.root, bg=PLOT_THEME["bg"],
                                 highlightthickness=1, highlightbackground=PLOT_THEME["fg"])
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8), pady=8)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-3>", self._on_right_press)
        self.canvas.bind("<B3-Motion>", self._on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<Button-4>", self._on_zoom)
        self.canvas.bind("<Button-5>", self._on_zoom)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Global (bind_all) keyboard shortcuts, GUARDED to skip while a text-entry widget (the
        # right pane's target-RMS/tolerance Entries) has focus -- interactive_builder_app's own
        # bind_all was safe unguarded (that app has no text-entry widget at all for a shortcut
        # like Delete/Ctrl+C/j to collide with); this combined window does, so typing "1e-04"
        # into Tolerance must not also delete shapes, toggle Join mode, etc.
        self._bind_all_guarded("<Delete>", self._on_delete_key)
        self._bind_all_guarded("<KeyPress-d>", self._on_toggle_debug_mode)
        self._bind_all_guarded("<KeyPress-f>", self._on_flip_key)
        self._bind_all_guarded("<KeyPress-m>", lambda _e: self._set_tool_mode("move"))
        self._bind_all_guarded("<KeyPress-j>", lambda _e: self._set_tool_mode("join"))
        self._bind_all_guarded("<KeyPress-p>", lambda _e: self._set_tool_mode("fold"))
        self._bind_all_guarded("<KeyPress-h>", lambda _e: self._flip_selected_shapes("horizontal"))
        self._bind_all_guarded("<KeyPress-v>", lambda _e: self._flip_selected_shapes("vertical"))
        self._bind_all_guarded("<Control-c>", self.on_copy_key)
        self._bind_all_guarded("<Control-v>", self.on_paste_key)
        self._bind_all_guarded("<Control-z>", self.on_undo_key)
        self._bind_all_guarded("<Control-y>", self.on_redo_key)
        self._bind_all_guarded("<Escape>", self._on_escape_key)

    def _bind_all_guarded(self, sequence, handler):
        def wrapped(event=None):
            focused = self.root.winfo_toplevel().focus_get()
            if isinstance(focused, (tk.Entry, ttk.Entry, tk.Spinbox, ttk.Spinbox)):
                return None
            return handler(event)
        self.root.bind_all(sequence, wrapped)

    def _build_palette_entry(self, parent, n):
        """Same icon construction as InteractiveBuilderApp's own _build_palette_entry, but
        packed LEFT-to-right (a horizontal top row) instead of top-to-bottom (a vertical left
        column), and scaled down to INFLATER_ICON_SIZE (see module docstring) instead of that
        app's own ICON_SIZE -- this app's own required layout."""
        icon = tk.Canvas(parent, width=INFLATER_ICON_SIZE, height=INFLATER_ICON_SIZE,
                          bg=PLOT_THEME["bg"], highlightthickness=2,
                          highlightbackground=PLOT_THEME["bg"])
        icon.pack(side=tk.LEFT, padx=2)
        cx, cy = INFLATER_ICON_SIZE / 2, INFLATER_ICON_SIZE / 2
        scale = INFLATER_ICON_SIZE / ICON_SIZE
        screen_vertices = [(vx * scale + cx, vy * scale + cy) for vx, vy in _ICON_VERTICES[n]]
        photo, (left, top) = _rasterize_polygon(screen_vertices, POLYGON_COLORS[n])
        self._icon_photos[n] = photo
        icon.create_image(left, top, anchor="nw", image=photo)
        icon.bind("<Button-1>", lambda _e, n=n: self._on_palette_clicked(n))
        self._palette_canvases[n] = icon

    def _update_title(self):
        """No-op -- an embedded pane has no window title of its own (this combined app's real
        Toplevel title is set once by CombinedApp)."""

    def _update_file_menu_state(self):
        """No-op -- InteractiveBuilderApp's own version enables/disables Save/Save As on
        self.file_menu, which doesn't exist here (CombinedApp builds the one real File menu,
        with only Load..., outside this pane -- see its own _build_menu)."""

    def export_mesh_dict(self):
        """Returns (mesh_dict, None) built from the CURRENT live shapes/connections, via the
        exact same _expand_folded_shapes/_faces_from_shapes/_edges_from_shapes/
        _face_edge_ids_from_shapes pipeline File > Save uses in interactive_builder_app
        (_export_faces_and_layout, inherited unchanged) -- or (None, message) if the net is
        empty or fails validation (self-loop, duplicate edge, disconnected net, etc.), for the
        caller to show via the existing error-messaging pattern instead of crashing."""
        if not self.shapes:
            return None, "Nothing to inflate yet -- place at least one shape first."
        try:
            faces, edges, face_edge_ids, source_polygon_id, _net_layout, _builder_connections = \
                self._export_faces_and_layout()
        except (NetValidationError, ValueError) as e:
            return None, str(e)
        mesh = {"name": "live_net", "faces": faces, "edges": edges,
                "face_edge_ids": face_edge_ids, "source_polygon_id": source_polygon_id}
        return mesh, None


class _PaneRoot(ttk.Frame):
    """Stands in for InteractiveBuilderApp's own `root` parameter inside this app's left pane --
    a real widget (so ttk.Frame(self.root, ...)/tk.Canvas(self.root, ...) parenting inside the
    inherited methods still works), but swallowing the whole-WINDOW-only calls that class's
    __init__/_build_menu make on it (title/geometry/minsize/protocol/config(menu=...)), none of
    which apply to an embedded pane."""

    def title(self, *_a, **_k):
        pass

    def geometry(self, *_a, **_k):
        pass

    def minsize(self, *_a, **_k):
        pass

    def protocol(self, *_a, **_k):
        pass

    def config(self, *args, **kwargs):
        if "menu" in kwargs:
            return None
        return super().config(*args, **kwargs)

    configure = config


# ---- right pane ----

class InflaterPane:
    """The simplified solver viewer -- see module docstring for the full list of what's
    dropped relative to inflate_polyhedron_app. Owns no state about the LEFT pane at all; it
    only ever reads a fresh mesh dict from `builder.export_mesh_dict()` at the moment Inflate
    is clicked (builder_getter, a zero-arg callable returning the current BuilderPane)."""

    def __init__(self, container, builder_getter):
        self.root = container
        self.builder_getter = builder_getter

        self.base_faces = None
        self.base_edges = None
        self.base_face_edge_ids = None
        self.faces = None
        self.edge_length = None
        self.face_of_fine = None
        self.edges = None
        self.positions = None
        self.subdivision_level = 0
        self._running = False

        # The plotter's own render resolution -- starts at PANEL_SIZE but is kept in sync with
        # the panel_label's actual on-screen pixel size by _on_panel_configure below, so the
        # mesh always renders at full native resolution for whatever space it's actually given
        # (2026-09-19, explicit: "the resolution... seems low compared to the other apps" --
        # inflate_polyhedron_app's own panels render at their own fixed, already-correct pixel
        # size; this app's single panel didn't adapt to ITS pane's real, larger size).
        self.panel_size = PANEL_SIZE
        self._resize_after_id = None

        self._center = np.zeros(3)
        self._half = 1.0
        self._camera = {"rotation": self._initial_rotation(), "zoom": 1.0, "pan": np.zeros(2)}
        self._dragging = False
        self._last_xy = None
        self._panning = False
        self._pan_last_xy = None

        self._build_ui()
        self._render()

    # ---- UI ----

    def _build_ui(self):
        setup = ttk.Frame(self.root, padding=8)
        setup.pack(side=tk.TOP, fill=tk.X)

        # One row -- "Target stretch: L1 __ L2 __ L3 __  Tolerance: ___" -- short enough
        # labels/entry widths to fit on a single line even in this pane's own (roughly half-
        # window) width (2026-09-19, explicit: "i want all to fit on one line if possible").
        row = ttk.Frame(setup)
        row.pack(side=tk.TOP, anchor=tk.W)
        ttk.Label(row, text="Target stretch:").pack(side=tk.LEFT, padx=(0, 4))
        self.target_rms_vars = {}
        self.target_rms_display_vars = {}
        for level in (1, 2, 3):
            ttk.Label(row, text=f"L{level}:").pack(side=tk.LEFT, padx=(8, 2))
            var = tk.DoubleVar(value=round(LEVEL_DEFAULT_TARGET_RMS_PCT[level]))
            self.target_rms_vars[level] = var
            display_var = tk.StringVar(value=f"{var.get():.0f}%")
            self.target_rms_display_vars[level] = display_var
            var.trace_add("write", lambda *_a, lv=level: self._sync_target_rms_display(lv))
            entry = ttk.Entry(row, width=5, textvariable=display_var)
            self._register_numeric_entry(entry, allow_exponent=False, allow_decimal=False)
            entry.bind("<FocusIn>", lambda _e, lv=level: self._begin_edit_target_rms(lv))
            entry.bind("<Return>", lambda _e, lv=level: self._commit_target_rms_entry(lv))
            entry.bind("<FocusOut>", lambda _e, lv=level: self._commit_target_rms_entry(lv))
            entry.pack(side=tk.LEFT)

        ttk.Label(row, text="Tolerance:").pack(side=tk.LEFT, padx=(14, 4))
        self.tolerance_var = tk.StringVar(value=f"{DEFAULT_TOLERANCE:.0e}")
        # width=7 (was 10) -- shorter, still fits "1e-04" plus a couple of extra digits while
        # typing (2026-09-19, explicit: "make the tolerance text box a bit shorter").
        self.tolerance_spin = ttk.Entry(row, width=7, textvariable=self.tolerance_var)
        self._register_numeric_entry(self.tolerance_spin, allow_exponent=True)
        self.tolerance_spin.pack(side=tk.LEFT)

        self.inflate_button = ttk.Button(setup, text="Inflate", command=self.on_inflate_clicked)
        self.inflate_button.pack(side=tk.TOP, anchor=tk.W, pady=(8, 0))

        self.status_label = ttk.Label(self.root, anchor="w", padding=(8, 3))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.panel_label = tk.Label(self.root, bg=PLOT_THEME["bg"], bd=0,
                                     width=PANEL_SIZE[0], height=PANEL_SIZE[1])
        self.panel_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.plotter = pv.Plotter(off_screen=True, window_size=list(self.panel_size))
        self.plotter.set_background(PLOT_THEME["bg"])
        self._photo = None
        self.panel_label.bind("<Configure>", self._on_panel_configure)

        # Left-drag rotates (trackball), right-drag pans, middle-click resets, wheel zooms --
        # same gesture set as inflate_polyhedron_app's own "Level N" panels, reimplemented for
        # this app's one single panel (2026-09-19, explicit: "the 3d object is not rotatable/
        # movable/scaling right now").
        self.panel_label.bind("<ButtonPress-1>", self._on_drag_start)
        self.panel_label.bind("<B1-Motion>", self._on_drag_motion)
        self.panel_label.bind("<ButtonRelease-1>", self._on_drag_end)
        self.panel_label.bind("<ButtonPress-3>", self._on_pan_start)
        self.panel_label.bind("<B3-Motion>", self._on_pan_motion)
        self.panel_label.bind("<ButtonRelease-3>", self._on_pan_end)
        self.panel_label.bind("<Button-2>", self._on_camera_reset)
        self.panel_label.bind("<MouseWheel>", self._on_scroll)
        self.panel_label.bind("<Button-4>", self._on_scroll)
        self.panel_label.bind("<Button-5>", self._on_scroll)

    def _register_numeric_entry(self, entry, allow_exponent, allow_decimal=True):
        vcmd = self.root.register(lambda proposed: _is_valid_numeric_partial(
            proposed, allow_exponent, allow_decimal))
        entry.configure(validate="key", validatecommand=(vcmd, "%P"))

    def _begin_edit_target_rms(self, level):
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}")

    def _sync_target_rms_display(self, level):
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}%")

    def _commit_target_rms_entry(self, level, _event=None):
        try:
            value = round(float(self.target_rms_display_vars[level].get()))
        except (tk.TclError, ValueError):
            value = LEVEL_DEFAULT_TARGET_RMS_PCT[level]
        self.target_rms_vars[level].set(max(0, min(100, value)))

    def _get_tolerance(self):
        try:
            return float(self.tolerance_var.get())
        except ValueError:
            return DEFAULT_TOLERANCE

    def _set_status(self, text, kind="info"):
        self.status_label.config(text=text, foreground=STATUS_COLORS.get(kind, STATUS_COLORS["info"]))

    def _set_running(self, running):
        self._running = running
        self.inflate_button.state(["disabled"] if running else ["!disabled"])

    def _on_panel_configure(self, event):
        """Keeps the off-screen plotter's own render resolution matched to panel_label's real,
        current pixel size -- debounced via a rescheduled `after` call (Configure fires
        continuously while the window/sash is being dragged; rebuilding the plotter on every
        single event would be wasteful and janky) so the actual rebuild+re-render only happens
        once motion settles. Ignores the initial 1x1 Configure Tk sends before real layout."""
        width, height = event.width, event.height
        if width <= 1 or height <= 1:
            return
        if (width, height) == self.panel_size:
            return
        if self._resize_after_id is not None:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(80, lambda: self._apply_panel_resize(width, height))

    def _apply_panel_resize(self, width, height):
        self._resize_after_id = None
        self.panel_size = (width, height)
        self.plotter.close()
        self.plotter = pv.Plotter(off_screen=True, window_size=[width, height])
        self.plotter.set_background(PLOT_THEME["bg"])
        self._render()

    # ---- camera (rotate/pan/zoom) ----

    @staticmethod
    def _initial_rotation():
        """Same construction as inflate_polyhedron_app's own _initial_level_rotation -- an
        explicit orthonormal (direction, right, up) frame read off as a rotation matrix, so the
        starting view matches that app's default (non-axis-aligned) angle instead of a bare
        identity quaternion."""
        azim, elev = np.radians(PANEL_DEFAULT_AZIM), np.radians(PANEL_DEFAULT_ELEV)
        direction = np.array([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim),
                               np.sin(elev)])
        world_up = np.array([0.0, 0.0, 1.0])
        right = np.cross(world_up, direction)
        right /= np.linalg.norm(right)
        up = np.cross(direction, right)
        return Rotation.from_matrix(np.column_stack([direction, right, up]))

    def _apply_camera(self):
        """Positions the plotter's orthographic camera from self._camera (rotation/zoom/pan)
        and self._center/_half (this frame's own bounding-sphere, set by _render just before
        this is called) -- same technique as inflate_polyhedron_app's own _render_level_pv."""
        cam = self._camera
        direction = cam["rotation"].apply([1.0, 0.0, 0.0])
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        distance = self._half * 4
        camera = self.plotter.camera
        camera.parallel_projection = True
        camera.focal_point = tuple(self._center)
        camera.position = tuple(self._center + direction * distance)
        camera.up = tuple(up)
        panel_width, panel_height = self.panel_size
        camera.parallel_scale = (self._half * max(1.0, panel_height / panel_width)
                                  / PANEL_ZOOM_FILL / cam["zoom"])
        camera.SetWindowCenter(*cam["pan"])

    def _on_drag_start(self, event):
        self._dragging = True
        self._last_xy = (event.x, event.y)

    def _on_drag_motion(self, event):
        if not self._dragging or self._last_xy is None:
            return
        cam = self._camera
        last_x, last_y = self._last_xy
        dx, dy = event.x - last_x, event.y - last_y
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        right = cam["rotation"].apply([0.0, 1.0, 0.0])
        sensitivity = np.radians(PANEL_DRAG_SENSITIVITY)
        yaw = Rotation.from_rotvec(-dx * sensitivity * up)
        pitch = Rotation.from_rotvec(-dy * sensitivity * right)
        cam["rotation"] = pitch * yaw * cam["rotation"]
        self._last_xy = (event.x, event.y)
        self._render()

    def _on_drag_end(self, _event):
        self._dragging = False
        self._last_xy = None

    def _on_pan_start(self, event):
        self._panning = True
        self._pan_last_xy = (event.x, event.y)

    def _on_pan_motion(self, event):
        if not self._panning or self._pan_last_xy is None:
            return
        last_x, last_y = self._pan_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        panel_width, panel_height = self.panel_size
        self._camera["pan"] = self._camera["pan"] + np.array(
            [-dx / (panel_width / 2.0), dy / (panel_height / 2.0)])
        self._pan_last_xy = (event.x, event.y)
        self._render()

    def _on_pan_end(self, _event):
        self._panning = False
        self._pan_last_xy = None

    def _on_camera_reset(self, _event=None):
        self._camera = {"rotation": self._initial_rotation(), "zoom": 1.0, "pan": np.zeros(2)}
        self._render()

    def _on_scroll(self, event):
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / PANEL_ZOOM_STEP
        else:
            factor = PANEL_ZOOM_STEP
        self._camera["zoom"] = max(PANEL_ZOOM_MIN, min(PANEL_ZOOM_MAX, self._camera["zoom"] * factor))
        self._render()

    # ---- rendering ----

    def _render(self):
        """Redraws the single panel from whatever self.faces/self.positions/self.face_of_fine
        currently hold -- colored per ORIGINAL base face (face_of_fine) by POLYGON_COLORS[n]
        (n = that base face's own vertex count), the SAME fixed per-shape-type color the left
        pane's canvas draws that shape with (POLYGON_COLORS is keyed by side count, not by
        instance -- see interactive_builder_app's own _draw_shape/_build_palette_entry), so a
        square on the left inflates into a square-colored patch on the right (2026-09-19,
        explicit: "should use the same colours as the left side"). Camera framing/rotation/
        pan/zoom come from self._camera (see _apply_camera/the drag/pan/scroll handlers below)
        instead of a fresh "iso" + reset_camera() every redraw, so a user's view survives
        across Inflate steps."""
        plotter = self.plotter
        plotter.clear()
        if self.faces and self.positions and self.base_faces:
            vertex_ids = sorted(self.positions)
            idx = {v: i for i, v in enumerate(vertex_ids)}
            points = np.array([self.positions[v] for v in vertex_ids])
            face_of_fine = self.face_of_fine or list(range(len(self.faces)))
            for group in sorted(set(face_of_fine)):
                group_faces = [f for f, bf in zip(self.faces, face_of_fine) if bf == group]
                if not group_faces:
                    continue
                n = len(self.base_faces[group])
                color = POLYGON_COLORS.get(n, FACE_COLORS[group % len(FACE_COLORS)])
                face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
                mesh = pv.PolyData(points, face_conn)
                plotter.add_mesh(mesh, color=color, show_edges=True, edge_color="white", line_width=0.75)
            lo, hi = points.min(axis=0), points.max(axis=0)
            self._center = (lo + hi) / 2
            self._half = float(np.linalg.norm(points - self._center, axis=1).max()) + 1e-6
            self._apply_camera()
            plotter.render()
            image = plotter.screenshot(return_img=True)
            self._photo = ImageTk.PhotoImage(Image.fromarray(image))
            self.panel_label.configure(image=self._photo, text="")
        else:
            self.panel_label.configure(image="", text="Build a net on the left, then click Inflate.",
                                        fg=PLOT_THEME["fg"])

    # ---- pipeline ----

    def on_inflate_clicked(self):
        """Reads the LEFT pane's current net, then runs the full Level 0->1->2->3 auto-pipeline
        (fan-triangulate -> Relax -> calibrate/Inflate to target RMS -> Subdivide -> repeat) --
        the same sequence inflate_polyhedron_app's "Run Simulation" runs, redrawing this ONE
        panel in place at each step instead of four side-by-side panels. A no-op while already
        running."""
        if self._running:
            return
        builder = self.builder_getter()
        mesh, err = builder.export_mesh_dict()
        if err:
            messagebox.showerror("Cannot inflate", err)
            return
        try:
            faces, base_edges, face_edge_ids = _load_mesh_from_dict(mesh)
        except ValueError as e:
            messagebox.showerror("Cannot inflate", str(e))
            return
        self.base_faces = faces
        self.base_edges = base_edges
        self.base_face_edge_ids = face_edge_ids
        self.faces, self.edge_length, self.face_of_fine = _build_level1_topology(self.base_faces)
        self.edges = _fan_level_edges(self.faces, self.base_edges)
        self.subdivision_level = 0
        self.positions = random_initial_positions(self.faces, seed=0)
        self._render()
        self._set_running(True)
        self._set_status("Level 0: relaxing...", "info")
        self._run_background(
            lambda queue_progress: relax_initial_configuration(
                self.positions, self.faces, self.edge_length,
                max_nfev=SAFETY_STEP_CAP, gtol=self._get_tolerance(),
                rng=None, on_progress=None, edges=self.edges),
            self._on_relax_done)

    def _on_relax_done(self, result):
        positions, _steps, max_stretch, rms_stretch, _optimality, converged = result
        self.positions = positions
        self._render()
        if not converged:
            self._set_running(False)
            self._set_status(
                f"Level 0 relax hit the step cap ({SAFETY_STEP_CAP}) without converging "
                f"(max stretch {max_stretch:.2f}%, RMS {rms_stretch:.1f}%). Click Inflate to "
                "try again from here.", "warn")
            return
        self.subdivision_level = 1
        self._set_status(
            f"Level 0 relaxed (RMS {rms_stretch:.1f}%). Inflating Level 1...", "info")
        self._run_inflate_step()

    def _run_inflate_step(self):
        target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        tolerance = self._get_tolerance()
        self._run_background(
            lambda queue_progress: estimate_pressure_for_target_stretch(
                self.positions, self.faces, self.edge_length,
                target_rms_pct=target_rms_pct, gtol=tolerance, rng=None,
                capture_frames=False, on_progress=queue_progress,
                edges=self.edges if self.subdivision_level == 1 else None),
            self._on_inflate_step_done,
            on_progress=lambda steps: self._set_status(
                f"Level {self.subdivision_level}: calibrating pressure toward "
                f"{target_rms_pct:.0f}% RMS stretch ({steps} steps so far)...", "info"))

    def _on_inflate_step_done(self, result):
        # capture_frames=False (see on_inflate_clicked's own call) -- 8 values, no frames list.
        (pressure, new_positions, _steps, max_stretch, rms_stretch,
         _optimality, converged, pressure_found) = result
        self.positions = new_positions
        self._render()
        if not pressure_found:
            self._set_running(False)
            self._set_status(
                f"Level {self.subdivision_level}: mesh didn't respond to pressure -- stopping "
                "here.", "warn")
            return
        if not converged:
            self._set_running(False)
            self._set_status(
                f"Level {self.subdivision_level}: pressure {pressure:.2f} reached the step cap "
                f"without fully converging (RMS {rms_stretch:.1f}%, max stretch "
                f"{max_stretch:.2f}%). Click Inflate again to continue.", "warn")
            return
        if self.subdivision_level >= MAX_LEVEL:
            self._set_running(False)
            self._set_status(
                f"Done -- Level {MAX_LEVEL}, pressure {pressure:.2f}, RMS stretch "
                f"{rms_stretch:.1f}% (max {max_stretch:.2f}%).", "success")
            return
        self.level_snapshot_faces = self.faces
        self.faces, self.positions, self.edge_length, self.face_of_fine = subdivide_once(
            self.faces, self.positions, self.edge_length, self.face_of_fine,
            self.subdivision_level, base_faces=self.base_faces,
            face_edge_ids=self.base_face_edge_ids)
        self.subdivision_level += 1
        self.edges = None
        self._render()
        self._set_status(
            f"Subdivided to level {self.subdivision_level}. Inflating...", "info")
        self._run_inflate_step()

    # ---- background thread/progress-poll pattern (same idea as both sibling apps' own
    # _run_background) ----

    def _run_background(self, fn, on_done, on_progress=None):
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
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        if on_progress is not None:
                            on_progress(payload)
                        continue
                    if kind == "error":
                        self._set_running(False)
                        self._set_status(f"Failed: {payload}", "error")
                        return
                    on_done(payload)
                    return
            except queue.Empty:
                pass
            self.root.after(100, poll)

        self.root.after(100, poll)


# ---- combined window ----

def _scale_ui_fonts_once(root):
    """Scales every named Tk/ttk font by UI_FONT_SCALE, exactly once for the whole combined
    window -- same technique both sibling apps use (tkfont.nametofont mutates the interpreter-
    wide named font, so this only ever needs doing once regardless of how many panes read it)."""
    for name in tkfont.names(root):
        font = tkfont.nametofont(name, root=root)
        size = font.cget("size")
        if size == 0:
            continue
        sign = -1 if size < 0 else 1
        font.configure(size=sign * round(abs(size) * UI_FONT_SCALE))


class CombinedApp:
    def __init__(self, root):
        self.root = root
        root.title("Interactive Inflater")
        # Smaller than this app's earlier 1500x900 (2026-09-19, explicit: "the window is too
        # big... make it smaller like the size of the polyhedron_inflater") -- close to that
        # sibling app's own ~1629x880, but this window also needs to fit a full builder pane
        # alongside the inflater, so slightly narrower/shorter than a literal match would be.
        root.geometry("1280x760")
        root.minsize(900, 560)

        sv_ttk.set_theme("dark")
        _scale_ui_fonts_once(root)
        self._build_menu(root)

        # A plain 2-column grid with equal, UNIFORM weight (not tk.PanedWindow, which only
        # obeys its stretch="always" flags for LEFTOVER space beyond each pane's own requested
        # size -- with panes this differently sized it never actually split 50/50) -- guarantees
        # the left/right panes stay exactly equal width, including as the window is resized
        # (2026-09-19, explicit: "the left and right pane should be equal width").
        container = ttk.Frame(root)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1, uniform="panes")
        container.columnconfigure(1, weight=1, uniform="panes")
        container.rowconfigure(0, weight=1)

        left_root = _PaneRoot(container)
        right_frame = ttk.Frame(container)
        left_root.grid(row=0, column=0, sticky="nsew")
        right_frame.grid(row=0, column=1, sticky="nsew")
        separator = ttk.Separator(container, orient=tk.VERTICAL)
        separator.place(relx=0.5, rely=0, relheight=1, anchor="n")

        self.builder = BuilderPane(left_root)
        self.inflater = InflaterPane(right_frame, lambda: self.builder)

    def _build_menu(self, root):
        """A File menu with just Load... (no New/Save/Save As -- this app has no window-level
        concept of "the current file" to Save back to, and Save isn't offered yet at all,
        2026-09-19, explicit) -- replaces the earlier plain toolbar button so Load lives where
        a user expects file operations to be. Same explicit-color kwargs as
        interactive_builder_app's own _build_menu (MENU_BG/MENU_FG/etc, imported, not
        duplicated) so this matches that app's look."""
        menu_kwargs = dict(bg=MENU_BG, fg=MENU_FG, activebackground=MENU_ACTIVE_BG,
                            activeforeground=MENU_FG, disabledforeground=MENU_DISABLED_FG)
        menubar = tk.Menu(root, **menu_kwargs)
        file_menu = tk.Menu(menubar, tearoff=False, **menu_kwargs)
        file_menu.add_command(label="Load...", command=lambda: self.builder.on_load_clicked())
        menubar.add_cascade(label="File", menu=file_menu)
        root.config(menu=menubar)


def main():
    # Must run BEFORE tk.Tk() -- once the window exists it's too late to change how Windows
    # scales it. Reused from interactive_builder_app (imported, not duplicated) rather than a
    # second copy in this file; without it, Tk renders at a virtualized 96 DPI and Windows
    # bitmap-stretches the whole window (UI text included, not just the 3D panel) to the
    # display's real scaling -- the actual cause of "the entire app... down to the UI. the
    # text looks fuzzy too" (2026-09-19, explicit).
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    CombinedApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
