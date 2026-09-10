"""
Inflate Polyhedron -- interactive fabric relaxation for stretchy meshes.

    python src/apps/inflate_polyhedron_app/app.py

Nets here (data/input/stretchy_nets/*.json, see utils/inflate_polyhedron/stretchy_mesh.py
for the vertex-loop format) are specified directly as vertex loops --
shared vertex ids ARE the adjacency, so a face pair sharing several edges
(which would force two RIGID flat faces into the same plane -- see
utils/inflate_polyhedron/stretchy_mesh.py's module docstring) needs no special
casing.

A net's starting configuration is no longer solved analytically
(solve_wireframe, the old random-restart-plus-inflation-ramp search) --
"Level 0" instead starts from genuine random noise
(stretchy_mesh.random_initial_positions) and the "Relax" button pulls it
into a well-separated 3D shape using pure spring forces only
(stretchy_mesh.relax_initial_configuration -- no pressure, faces may
cross), the same generic force-directed-layout idea for any net
regardless of its combinatorics. Level 0 is triangulated first (fan
subdivision, see mesh_levels.subdivide_once) since an untriangulated
face (e.g. a plain quad) is a flexible mechanism under springs alone, not
a rigid structure -- this fan-triangulated topology is *exactly* Level
1's own topology (see mesh_levels' docstring), so once Relax converges,
promoting Level 0's result into Level 1's starting position is a pure
relabeling, not a new subdivide_once call. A legacy fabric-subdivided
file (one carrying baked-in "coarse_faces", see
utils/subdivisions/mesh_subdivide.load_fabric_spec and
generate_subdivided_stretchy_nets.py) starts this same way from ITS OWN
coarse_faces rather than its pre-baked fine mesh. This supersedes the old
fixed-resolution fabric-net files/build_cache precompute pipeline for
this app's own workflow -- the fixed-resolution example nets it used to
ship with (cube_res3.json and friends) have been removed accordingly,
though the format and generate_subdivided_stretchy_nets.py itself still
work for anyone who wants one.

1. On selecting a net, its BASE faces are fan-triangulated (Level 0/1's
   shared topology) and given a fresh random start -- both cheap enough
   to happen instantly, so there's no background solve or cache for this
   step anymore (see "Relax" below for what actually shapes it).
2. "Relax" (Level 0 only, stretchy_mesh.relax_initial_configuration) runs
   pure-spring relaxation to convergence; once it converges, Level 0's
   result is promoted straight into Level 1's starting position (see
   above -- no user action needed for this handoff). A tangled (mixed
   face-orientation) result is possible and NOT retried automatically --
   the subsequent Inflate/pressure step is expected to work it out.
3. "Subdivide" (mesh_levels.subdivide_once) refines the CURRENT mesh by
   one level (from Level 1 on): each level quarters every triangle by
   connecting edge midpoints. New points are linearly interpolated from
   the current mesh's own nearby points; new REST lengths (as opposed to
   positions) are derived analytically from the original unit-edge flat
   reference geometry, so the ideal target shape stays fixed as
   resolution increases (see mesh_levels' docstring) -- letting "inflate,
   then increase resolution, then inflate again" converge toward one
   consistent answer instead of each level chasing a different target.
   Greyed out once MAX_LEVEL is reached.
4. At Level 1 and up, the "Inflate" button first CALIBRATES a pressure (see
   stretchy_mesh.estimate_pressure_for_target_stretch) landing near the
   "Target RMS stretch" spinner's value (% of rest edge length, default
   DEFAULT_TARGET_RMS_STRETCH_PCT), then applies ONE relaxation pass
   (stretchy_mesh.relax_once) at that pressure, continuing from wherever
   the mesh currently is -- so repeated clicks let you watch/steer the
   shape settle incrementally, and re-calibrate each time since pressure
   is no longer something the user sets directly (required pressure
   varies a lot between nets -- it scales with total surface area, not
   vertex/face count -- so a single fixed number would be either too
   gentle or wildly excessive depending which net is loaded). relax_once
   walks small explicit steps along a genuine spring-vs-pressure force
   (see stretchy_mesh's Design notes) -- no volume or remembered state
   anywhere in it, so it can't compound across a Subdivide.
   - The radio buttons control how much work the actual inflation part of
     each "Inflate" click does (after calibration): either a capped
     number of relax_once steps (`max_nfev`, literally N iterations now),
     or an uncapped run to relax_once's own convergence tolerance
     (CONVERGENCE_GTOL -- some meshes have a long, slow-shrinking tail
     after the shape has visibly settled, so this is deliberately looser
     than it might seem it needs to be).
5. The "Convergence History" table records one row per subdivision level
   visited this net session: the pressure last calibrated for it (n/a for
   Level 0, which has no pressure at all), how many Inflate/Relax steps
   that level has taken so far (self.iteration_count -- reset to 0 by
   every Subdivide/promotion, so it always counts from when that level's
   mesh was first created, not carried over from a coarser level), the
   stretch stats at whatever point it's currently at (RMS shown against
   the CURRENT "Target RMS stretch" spinner value), and a single combined
   "Convergence" cell -- the relax's own `max_force` (the worst vertex's
   net force) against the fixed CONVERGENCE_GTOL threshold, with a check
   or cross mark for whether it's below it -- updated live while
   Inflate/Relax runs.
6. The view below is "Net" (the flat, undeformed layout, matplotlib)
   plus one 3D panel per level, "Level 0".."Level N" (MAX_LEVEL total,
   plus Level 0). Only the panel for self.subdivision_level is LIVE -- it
   redraws every Inflate/Relax progress update; every level already left
   behind (by Subdivide, or by Relax's own promotion) is frozen at
   whatever state it was left in (self.level_snapshots, captured the
   moment the user moves on from it) and never updates again; a level
   not reached yet is drawn empty. Each panel derives its own view
   bounds from its current points' bounding box every redraw (see
   _draw_level_panel) -- necessary since neither a pure-spring relax nor
   a pressure inflation has any mechanism keeping the result near the
   origin or at a familiar scale.

   Every "Level N" panel renders via PyVista/VTK
   (`_build_level_pv_panel`/`_draw_level_panel`/`_render_level_pv`), not
   matplotlib: a mesh here is routinely self-intersecting or non-convex
   (mid-relax, mid-inflate, or Level 0's own random-start-then-relax
   result), which neither mplot3d's own painter's-algorithm depth sort
   nor this app's old `_CullableFace` (exact normal-based culling, valid
   only for a closed CONVEX solid) could draw correctly -- occluded
   faces would wrongly show through. PyVista gives a real GPU depth
   buffer instead, which handles arbitrary triangle soups correctly
   regardless of convexity, blitted into a plain Tkinter Label as an
   off-screen-rendered image. Every level panel shares ONE click-drag
   rotation state (self.level_azim/level_elev) -- a drag on any panel
   rotates all of them together, matching what the old matplotlib
   panels' rotation sync used to do. (Tried on Level 0 alone first, to
   validate the approach before applying it to every level.) Every level
   panel likewise shares ONE mouse-wheel zoom state (self.level_zoom) --
   scrolling over any panel zooms all of them together, same rationale.
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import glob
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import pyvista as pv
import sv_ttk

from common.paths import STRETCHY_NETS_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS
from utils.inflate_polyhedron.stretchy_mesh import (
    load_stretchy_mesh, relax_once, relax_initial_configuration, random_initial_positions,
    estimate_pressure_for_target_stretch, mesh_edges, EDGE_LENGTH,
    PLANARITY_WEIGHT, CONVERGENCE_GTOL, DEFAULT_TARGET_RMS_STRETCH_PCT,
)
from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.subdivisions.mesh_subdivide import load_fabric_spec
from utils.inflate_polyhedron.stretchy_net_layout import build_stretchy_net_layout
from utils.subdivisions import subdivide as subdivide_polygon

DEFAULT_NET_BASENAME = "cube"

# A fabric-subdivided net's fine mesh edges are drawn thin/faint so the
# subdivision reads as texture rather than a bold wireframe competing
# with the per-coarse-face coloring -- see load_fabric_spec.
SUBDIVISION_EDGE_ALPHA = 0.35
SUBDIVISION_EDGE_WIDTH = 0.5

# How much of each "Level N" panel's frame the shape's own bounding
# box fills: axis half-range = shape's half-extent * this. 1.0 would
# exactly touch the frame edge; below 1.0 crops in past it, making the
# shape look bigger within the same panel ("zooming in" without actually
# resizing the panel/window). 0.8 (was 1.2, a 20% MARGIN, before any
# zooming) makes the shape 1.2/0.8 = 50% larger within the frame than
# that original size.
WIREFRAME_VIEW_FILL = 0.8

# Every "Level N" panel renders via PyVista/VTK instead of matplotlib
# (see _build_level_pv_panel) -- a real GPU depth buffer, needed because
# a mesh here is routinely self-intersecting/non-convex (mid-relax or
# mid-inflate, or Level 0's random-start-then-relax result itself),
# which neither mplot3d's own painter's-algorithm depth sort nor this
# app's old _CullableFace (exact culling, valid only for a closed CONVEX
# solid) could draw correctly -- tried on Level 0 alone first to
# validate the approach before applying it to every level. Pixel size
# matches figsize=(3.2, 4.5) at the ~100dpi the Net panel's matplotlib
# figure renders at, so every level panel is the same size as its
# neighbors.
LEVEL_PANEL_SIZE = (320, 450)
# How much of the panel the shape's own bounding box fills, on top of
# the aspect-ratio correction below -- 1.0 would make the shape's widest
# dimension exactly touch the panel edge; below 1.0 leaves margin around
# it (shrinks the apparent shape without resizing the panel). 0.6, then
# a further "60% of that" per two rounds of user request (the unzoomed
# 1.0 rendered noticeably too large/cropped against the panel, and 0.6
# alone still did too) -- 0.6 * 0.6 = 0.36.
LEVEL_ZOOM_FILL = 0.36
# Initial camera angle -- arbitrary, just a reasonable non-axis-aligned
# starting view (close to mplot3d's own default elev=30/azim=-60).
LEVEL_DEFAULT_ELEV = 30.0
LEVEL_DEFAULT_AZIM = -60.0
# Degrees of camera rotation per pixel of click-drag -- tuned by feel
# against mplot3d's own drag-to-rotate sensitivity this replaced.
LEVEL_DRAG_SENSITIVITY = 0.5
# Zoom multiplier applied per mouse-wheel notch (one scroll "click", i.e.
# one event.delta increment of 120 on Windows) -- >1 zooms in, so the
# factor camera.parallel_scale is multiplied by is its RECIPROCAL (a
# smaller parallel_scale means a smaller visible world height, i.e.
# zoomed in). Clamped by LEVEL_ZOOM_MIN/MAX so scrolling can't shrink the
# shape to nothing or push it arbitrarily far away.
LEVEL_ZOOM_STEP = 1.1
LEVEL_ZOOM_MIN = 0.1
LEVEL_ZOOM_MAX = 10.0

# Every panel's title ("Net", "Level N") is a plain Tkinter Label above
# its image/canvas, not text drawn inside the image itself -- a title
# drawn INSIDE a PyVista panel's own rendered scene clipped against the
# panel's own edge (see _render_level_pv's Design notes), which a real
# widget placed above the image can't do.
LEVEL_TITLE_FONT = ("TkDefaultFont", 11)

# Shown on the Pressure readout before the user has ever clicked "Auto"
# -- pressure isn't user-editable (see the "Auto" button), so this only
# matters if "Inflate" is clicked with no calibration done yet.
DEFAULT_PRESSURE = 3.0

DEFAULT_STEPS = 10

# on_inflate_clicked runs relax_once in a growing sequence of chunks
# (5, 10, 20, ...) instead of one big max_nfev call, so the iteration
# counter/plot update incrementally instead of jumping straight from the
# start count to the end one -- each chunk continues from the previous
# one's own final positions, so nothing is lost by splitting the run up.
INFLATE_CHUNK_START = 5
INFLATE_CHUNK_MAX = 200
# Hard stop for "iterate until convergence" mode in case a mesh/pressure
# combination genuinely never reaches CONVERGENCE_GTOL (e.g. a topology
# that can't hold that much pressure) -- without this, a run that plateaus
# just short of convergence would loop forever instead of settling for
# "as far as it got".
INFLATE_SAFETY_STEP_CAP = 5000


def _build_level1_topology(base_faces):
    """Level 0 and Level 1 share this exact fan-triangulated topology (see
    module docstring/mesh_levels' own docstring for why triangulating
    first matters for a spring-only relax) -- cheap enough (pure index
    math, no numerical solve) to compute synchronously on every net
    selection. Calls subdivide_once with placeholder positions purely to
    get the resulting faces/edge_length/face_of_fine; the interpolated
    positions it also returns are meaningless (every input point is the
    same placeholder) and discarded -- random_initial_positions supplies
    Level 0's real starting positions instead."""
    dummy_positions = {v: np.zeros(3) for face in base_faces for v in face}
    faces, _, edge_length, face_of_fine = subdivide_once(
        base_faces, dummy_positions, EDGE_LENGTH, list(range(len(base_faces))), 0)
    return faces, edge_length, face_of_fine


class InflatePolyhedronApp:
    def __init__(self, root):
        self.root = root
        # Wide enough for Net + Level 0..MAX_LEVEL (5 panels), each a
        # fixed LEVEL_PANEL_SIZE-wide image -- the panel row no longer
        # stretches its frames to fill extra window width (see
        # panels_row's own comment), so this only needs to fit the
        # panels' own natural width, not leave room to spread them out.
        # Tall enough for Setup + status + Convergence History + each
        # panel's own title-Label-plus-image-plus-button stack at their
        # full natural size (root.winfo_reqheight() once everything is
        # built) -- too short here silently SQUEEZES every image Label
        # below LEVEL_PANEL_SIZE's own height (Tk shrinks a packed widget
        # to whatever's left rather than erroring), which visibly cropped
        # the bottom of every panel and threw off where mouse drags
        # actually land on it (see _on_level_drag_start and friends).
        root.geometry("1700x880")
        root.minsize(820, 600)

        sv_ttk.set_theme("dark")

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
        # collide with).
        self.debug_mode = False
        self.root.bind_all("<KeyPress-d>", self._on_toggle_debug_mode)

        # ---- Setup: net picker + target RMS stretch, shared by both
        # modes, plus (debug mode only) the steps-vs-convergence choice. ----
        setup_frame = ttk.LabelFrame(root, text="Setup", padding=12)
        setup_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(14, 8))

        picker_row = ttk.Frame(setup_frame)
        picker_row.pack(fill=tk.X)
        ttk.Label(picker_row, text="Choose a net:").pack(side=tk.LEFT, padx=(0, 8))
        self.net_var = tk.StringVar()
        self.combo = ttk.Combobox(picker_row, state="readonly", width=30,
                                   textvariable=self.net_var)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        target_row = ttk.Frame(setup_frame)
        target_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(target_row, text="Target RMS stretch:").pack(side=tk.LEFT, padx=(0, 4))
        self.target_rms_var = tk.DoubleVar(value=DEFAULT_TARGET_RMS_STRETCH_PCT)
        # A "converged" verdict only applies to the target it was reached
        # at -- changing this means the current pressure hasn't actually
        # been (re)calibrated for the new target yet, so the gate on
        # re-clicking Inflate (see _update_level_action_buttons) needs to
        # lift, since otherwise a converged mesh would stay stuck
        # refusing to recalibrate even after the user asks for a
        # different target.
        self.target_rms_var.trace_add("write", self._on_target_rms_changed)
        self.target_rms_spin = ttk.Spinbox(target_row, from_=0.1, to=200.0,
                                            increment=1.0, width=6,
                                            textvariable=self.target_rms_var, format="%.1f")
        self.target_rms_spin.pack(side=tk.LEFT)
        ttk.Label(target_row, text="%").pack(side=tk.LEFT, padx=(2, 8))
        # Pressure is no longer user-editable or separately displayed --
        # "Inflate" calibrates it itself (see on_inflate_clicked) and it's
        # already logged per level in the Convergence History table.
        self.pressure_value = DEFAULT_PRESSURE

        # Debug-mode-only: "Iterate for N steps" vs. "until convergence"
        # -- the one thing that actually differs between the two modes.
        # Shown/hidden by _apply_mode_visibility; forced back to
        # "convergence" whenever leaving debug mode, so release mode
        # never runs a stray fixed-step request left over from before.
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

        # ---- Status/progress: shared by both modes, always visible,
        # positioned right after Setup. ----
        status_frame = ttk.Frame(root)
        status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=160)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # ---- Convergence history: one row per subdivision level visited
        # this net session (including Level 0 now -- see module
        # docstring), showing the pressure last calibrated for it
        # (self.pressure_value -- only ever set by on_inflate_clicked's
        # calibration phase; "n/a" for Level 0, which has no pressure at
        # all, see _record_level_history), how many Inflate/Relax steps
        # that level took (self.iteration_count, reset to 0 on every
        # Subdivide/promotion -- see _subdivide_step/_finish_relax), the
        # stretch stats at whatever point it's currently at (updated live
        # while Inflate/Relax runs, finalized once it stops -- see
        # _record_level_history's callers, RMS shown against the CURRENT
        # "Target RMS stretch" spinner value -- see _refresh_history_table),
        # and a single combined "Convergence" cell -- the relax's own
        # `optimality` (the worst vertex's net force) against the fixed
        # CONVERGENCE_GTOL threshold, with a check/cross mark for whether
        # it's below it (see _refresh_history_table). height=MAX_LEVEL+1
        # (0..MAX_LEVEL) since that's the most rows this table will ever
        # hold -- a taller fixed height would just reserve blank space
        # below whatever's actually populated. ----
        self.history_frame = ttk.LabelFrame(root, text="Convergence History", padding=12)
        self.history_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        history_columns = ("level", "pressure", "steps", "max_stretch", "rms_stretch",
                            "convergence")
        self.history_tree = ttk.Treeview(self.history_frame, columns=history_columns,
                                          show="headings", height=MAX_LEVEL + 1)
        for col, heading, width in (
                ("level", "Level", 50), ("pressure", "Pressure", 80), ("steps", "Steps", 70),
                ("max_stretch", "Max Stretch %", 110), ("rms_stretch", "RMS Stretch %", 150),
                ("convergence", "Convergence", 170)):
            self.history_tree.heading(col, text=heading)
            self.history_tree.column(col, width=width, anchor=tk.CENTER)
        # ttk.Treeview can only color a whole ROW, not one cell -- so the
        # Convergence column's check/cross (see _refresh_history_table)
        # comes with its whole row tinted to match, rather than leaving
        # the mark itself in the default text color.
        self.history_tree.tag_configure("converged", foreground=STATUS_COLORS["success"])
        self.history_tree.tag_configure("not_converged", foreground=STATUS_COLORS["error"])
        self.history_tree.pack(fill=tk.X)

        # ---- Net (flat layout, matplotlib) + one 3D panel per level
        # (0..MAX_LEVEL, PyVista -- see LEVEL_PANEL_SIZE's own comment
        # for why), side by side. Each level panel is its OWN off-screen
        # Plotter/Label pair specifically so a native Tkinter
        # Inflate/Subdivide/Relax button can sit directly below it (see
        # _apply_mode_visibility) -- a single shared render target has no
        # way to embed a real button over just one panel. Level N's panel
        # is LIVE (redrawn every Inflate/Relax progress update) only
        # while self.subdivision_level == N; once the user subdivides
        # past it (or, for Level 0, once Relax converges and promotes
        # it), that level's last state is frozen into self.level_snapshots
        # and its panel stops updating -- see draw()/_subdivide_step/
        # _finish_relax. ----
        # No "Sync rotation" choice -- every level panel shares ONE
        # camera angle (self.level_azim/level_elev), updated by a drag on
        # ANY panel (see _on_level_motion) and reapplied to a level just
        # revealed by Subdivide so it inherits the current shared view
        # rather than starting at some default one.
        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))

        # fill/expand=False here (unlike a plain pack default) -- each
        # panel below is a FIXED-size image (LEVEL_PANEL_SIZE) that never
        # grows to fill extra space, so letting this row stretch to the
        # window's full width just spreads the panels apart with dead
        # space between them instead of shrinking; hugging its own
        # natural (sum-of-panels) width keeps them packed together, with
        # any leftover window width left past the last panel instead.
        panels_row = ttk.Frame(view_frame)
        panels_row.pack(side=tk.TOP, anchor=tk.W)

        net_panel_frame = ttk.Frame(panels_row)
        net_panel_frame.pack(side=tk.LEFT)
        # A plain Label, not ax.set_title() -- drawing a title INSIDE a
        # PyVista panel's own rendered image clipped its top edge against
        # the panel boundary (see _render_level_pv's own Design notes);
        # a real Tkinter widget above the image has no such problem, and
        # this same approach is used for every "Level N" panel's title
        # too, so keeping Net's title as a matplotlib ax.set_title()
        # would leave it inconsistently positioned relative to its
        # neighbors' labels.
        ttk.Label(net_panel_frame, text="Net", font=LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        # A disabled, blank button matching every "Level N" panel's own
        # action button below it -- purely to claim the same vertical
        # space, so the Net canvas ends up the same height as every level
        # panel (keeping content aligned in a row rather than Net's
        # canvas rendering visibly larger for having no button competing
        # for space underneath it).
        net_bottom_spacer = ttk.Button(net_panel_frame, text="")
        net_bottom_spacer.state(["disabled"])
        net_bottom_spacer.pack(side=tk.BOTTOM, fill=tk.X)
        self.fig_net = plt.figure(figsize=(3.2, 4.5))
        self.ax2d = self.fig_net.add_subplot(1, 1, 1)
        self.canvas_net = FigureCanvasTkAgg(self.fig_net, master=net_panel_frame)
        self.canvas_net.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.level_frames = {}
        self.level_plotters = {}
        self.level_labels = {}
        self.level_photos = {}
        self._level_center = {}
        self._level_half = {}
        # ONE shared camera angle across every level panel (see this
        # section's own Design notes above) -- updated by a drag on any
        # panel (_on_level_motion), applied to all of them
        # (_render_all_level_panels).
        self.level_azim = LEVEL_DEFAULT_AZIM
        self.level_elev = LEVEL_DEFAULT_ELEV
        # ONE shared zoom factor across every level panel, same rationale
        # as level_azim/level_elev above -- a scroll on any panel updates
        # it and re-renders all of them (see _on_level_scroll).
        self.level_zoom = 1.0
        self._level_dragging = False
        self._level_last_xy = None
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
        for level in range(0, MAX_LEVEL + 1):
            level_frame = ttk.Frame(panels_row)
            # No fill/expand -- see panels_row's own comment on why
            # every panel hugs its own fixed image size instead.
            level_frame.pack(side=tk.LEFT)
            self.level_frames[level] = level_frame
            button = ttk.Button(level_frame, text="Relax" if level == 0 else "Inflate")
            self.level_action_buttons[level] = button
            # Button packed BEFORE the panel widget, at BOTTOM -- packing
            # it AFTER an expand=True widget would starve it of space,
            # since that widget (packed first) would already have
            # claimed the entire remaining cavity by the time it's
            # placed.
            button.pack(side=tk.BOTTOM, fill=tk.X, in_=level_frame)
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
        self.target_layout = None
        self.positions = None
        self.iteration_count = 0
        self.last_stats = {}
        self.level_history = {}
        self.stop_event = None
        self.current_path = None
        self.current_label = None
        self.label_to_path = {}
        self._apply_plot_theme()
        self.refresh_net_list()
        self._apply_mode_visibility()
        if self.current_label:
            self.on_select_net()

    def _on_toggle_debug_mode(self, _event=None):
        self.debug_mode = not self.debug_mode
        self._apply_mode_visibility()

    def _apply_mode_visibility(self):
        """The only actual difference between the two modes: whether the
        steps-vs-convergence radio row is shown. Forces the choice back
        to "convergence" when leaving debug mode, so release mode never
        runs a stray fixed-step request left over from before."""
        self.root.title(f"Inflate Polyhedron{' (debug mode)' if self.debug_mode else ''}")
        if self.debug_mode:
            self.mode_row.pack(fill=tk.X, pady=(8, 0))
        else:
            self.mode_row.pack_forget()
            self.iterate_mode_var.set("convergence")

    def _set_status(self, text, kind="info"):
        # "success" is always dropped, in both modes -- e.g. "Converged
        # after N steps..." -- since the per-level button states and the
        # Convergence History table already show that. Release mode also
        # drops routine "info" narration (e.g. "Relaxing... N steps so
        # far...", "Relaxed... Promoted to Level 1...", "Subdivided to
        # level N...") for the same reason -- the live panel redraw,
        # button state, and history row already say all of it; debug mode
        # keeps "info" since it's meant for someone working on this app,
        # not an end user. "warn"/"error" (Stop requested, a solver
        # crash) always show in both modes -- those aren't otherwise
        # visible anywhere else.
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
        ttk.Label(level_frame, text=f"Level {level}", font=LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        label = tk.Label(level_frame, bg=PLOT_THEME["bg"], bd=0)
        label.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        plotter = pv.Plotter(off_screen=True, window_size=list(LEVEL_PANEL_SIZE))
        plotter.set_background(PLOT_THEME["bg"])
        self.level_labels[level] = label
        self.level_plotters[level] = plotter
        self.level_photos[level] = None  # keeps a reference alive -- Tk drops a GC'd PhotoImage
        self._level_center[level] = np.zeros(3)
        self._level_half[level] = 1.0
        label.bind("<ButtonPress-1>", self._on_level_drag_start)
        label.bind("<B1-Motion>", self._on_level_motion)
        label.bind("<ButtonRelease-1>", self._on_level_drag_end)
        # Windows/macOS deliver <MouseWheel> with event.delta; Linux
        # (X11) delivers wheel motion as Button-4/Button-5 clicks instead
        # -- binding all three covers every platform this app might run
        # on.
        label.bind("<MouseWheel>", self._on_level_scroll)
        label.bind("<Button-4>", self._on_level_scroll)
        label.bind("<Button-5>", self._on_level_scroll)

    def _on_level_drag_start(self, event):
        self._level_dragging = True
        self._level_last_xy = (event.x, event.y)

    def _on_level_motion(self, event):
        """Left-click-drag on ANY level panel rotates the shared camera
        angle (self.level_azim/level_elev) and re-renders EVERY panel
        with it in real time -- this app's own analogue of mplot3d's
        built-in drag rotation, reimplemented here since PyVista/VTK
        panels are plain images, not interactive widgets (see
        _build_level_pv_panel). Re-rendering all four costs ~30ms
        (measured), well within real-time feel -- an earlier version of
        this only re-rendered the dragged panel, misdiagnosing a
        completely different bug (plotter.screenshot() not actually
        re-rendering on a camera-only change without an explicit
        render() first, see _render_level_pv) as a performance problem;
        now that that's fixed, there's no reason to hold the other three
        back until the drag ends."""
        if not self._level_dragging or self._level_last_xy is None:
            return
        last_x, last_y = self._level_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        self.level_azim -= dx * LEVEL_DRAG_SENSITIVITY
        self.level_elev = max(-89.0, min(89.0, self.level_elev + dy * LEVEL_DRAG_SENSITIVITY))
        self._level_last_xy = (event.x, event.y)
        self._render_all_level_panels()

    def _on_level_drag_end(self, event):
        self._level_dragging = False
        self._level_last_xy = None
        # One last explicit render, in case the button release didn't
        # come with its own trailing motion event -- _on_level_motion
        # already keeps every panel live-updated during the drag itself,
        # so this is just a safety net for that edge case, not the
        # primary sync point.
        self._render_all_level_panels()

    def _on_level_scroll(self, event):
        """Mouse-wheel-scroll on ANY level panel zooms the shared camera
        (self.level_zoom) and re-renders EVERY panel with it -- the same
        shared-state-across-all-panels approach _on_level_motion uses for
        rotation (see this class's own Design notes in __init__), just
        for zoom instead of angle. event.num is Button-4/5 on X11 (no
        event.delta there); event.delta is Windows/macOS's own signed
        notch count (positive delta zooms in)."""
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / LEVEL_ZOOM_STEP
        else:
            factor = LEVEL_ZOOM_STEP
        self.level_zoom = max(LEVEL_ZOOM_MIN, min(LEVEL_ZOOM_MAX, self.level_zoom * factor))
        self._render_all_level_panels()

    def _render_all_level_panels(self):
        for level in self.level_plotters:
            self._render_level_pv(level)

    def _draw_level_panel(self, level, faces, positions, face_of_fine):
        """One "Level N" panel, drawn every call from whatever
        faces/positions/face_of_fine draw() passes it (live, frozen
        snapshot, or all-None for "not reached yet this session" -- see
        draw()'s own docstring). Faces are always triangles from Level 1
        on (Level 0's own topology, and everything Subdivide derives
        from it, is all-triangle -- see module docstring), so no
        fan/n-gon handling is needed. Colors every face by its ORIGINAL
        base face (`face_of_fine`, the same per-base-face self.colors
        the Net panel and every level's panel use) as PER-CELL RGB
        scalars -- one `pv.PolyData`/`add_mesh` call for the whole mesh
        (PyVista/VTK's own depth buffer handles occlusion correctly
        regardless of face count or convexity, unlike the old
        matplotlib/`_CullableFace` rendering this replaced -- see module
        docstring)."""
        plotter = self.level_plotters[level]
        plotter.clear()
        if faces is not None:
            vertex_ids = sorted(positions)
            idx = {v: i for i, v in enumerate(vertex_ids)}
            points = np.array([positions[v] for v in vertex_ids])
            face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in faces])
            mesh = pv.PolyData(points, face_conn)
            colors = np.array(
                [np.array(mcolors.to_rgb(self.colors[c % len(self.colors)])) * 255
                 for c in face_of_fine], dtype=np.uint8)
            mesh.cell_data["colors"] = colors
            plotter.add_mesh(mesh, scalars="colors", rgb=True, show_edges=True,
                              edge_color=PLOT_THEME["fg"], line_width=SUBDIVISION_EDGE_WIDTH)

            lo, hi = points.min(axis=0), points.max(axis=0)
            self._level_center[level] = (lo + hi) / 2
            self._level_half[level] = (hi - lo).max() / 2 * WIREFRAME_VIEW_FILL + 1e-6
        self._render_level_pv(level)

    def _render_level_pv(self, level):
        """Positions an orthographic (parallel-projection) camera from
        the SHARED self.level_azim/elev (see the drag handlers) at a
        distance derived from THIS level's own current bounding box
        (self._level_center/_level_half, set by _draw_level_panel --
        necessary since neither a pure-spring relax nor a pressure
        inflation has any mechanism keeping the result near the origin
        or at a familiar scale), renders off-screen, and blits the
        result into self.level_labels[level]. Parallel rather than
        perspective projection to give every panel fixed, comparable
        axis-limit-like framing with no foreshortening. The panel's
        "Level N" title is a separate Tkinter Label (see
        _build_level_pv_panel), not drawn into this image -- a title
        drawn INSIDE the rendered scene (tried first, via
        plotter.add_text) clipped against the panel's own top edge (a
        "0" losing its top arc, reading as a "U") since a VTK text
        actor's positioning/justification doesn't guarantee it stays
        fully inside the viewport the way a real widget placed above the
        image trivially does."""
        azim, elev = np.radians(self.level_azim), np.radians(self.level_elev)
        direction = np.array([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim),
                               np.sin(elev)])
        center, half = self._level_center[level], self._level_half[level]
        distance = half * 4
        plotter = self.level_plotters[level]
        camera = plotter.camera
        camera.parallel_projection = True
        camera.focal_point = tuple(center)
        camera.position = tuple(center + direction * distance)
        camera.up = (0.0, 0.0, 1.0)
        # parallel_scale sets the camera's vertical half-height in world
        # units -- the horizontal half-width it implies is narrower by
        # the window's own aspect ratio (width/height), which would crop
        # the shape's wider dimension on this portrait-shaped panel if
        # left at exactly `half`. Scaling up by height/width (when
        # portrait) guarantees the full half-extent fits in BOTH
        # directions, matching what set_box_aspect([1,1,1]) effectively
        # gave the old matplotlib panels for free; dividing by
        # LEVEL_ZOOM_FILL then shrinks the shape within that
        # guaranteed-fitting frame.
        panel_width, panel_height = LEVEL_PANEL_SIZE
        # self.level_zoom is a divisor here (like LEVEL_ZOOM_FILL) since
        # parallel_scale is a visible-world-HEIGHT, not a magnification --
        # a bigger level_zoom (scrolled in) must shrink parallel_scale.
        camera.parallel_scale = (half * max(1.0, panel_height / panel_width)
                                  / LEVEL_ZOOM_FILL / self.level_zoom)
        plotter.reset_camera_clipping_range()
        # plotter.screenshot() does NOT re-render on a camera-only change
        # by itself -- verified directly: two screenshots taken after
        # only moving the camera, with no explicit render() between them,
        # come back pixel-IDENTICAL. An explicit render() first is what
        # actually asks VTK to redraw the scene from the camera's current
        # position before screenshot() reads the framebuffer back -- this
        # was the actual cause of rotation looking "stuck" (nothing to do
        # with Tk's own redraw/event-queue timing, which earlier fixes in
        # this area wrongly assumed).
        plotter.render()
        image = plotter.screenshot(return_img=True)
        self.level_photos[level] = ImageTk.PhotoImage(Image.fromarray(image))
        self.level_labels[level].configure(image=self.level_photos[level])

    # ---- theme ----

    def _style_2d_axis(self, ax, theme):
        ax.title.set_color(theme["fg"])
        ax.set_axis_off()

    def _apply_plot_theme(self):
        """Recolor the Net figure's chrome to match the (fixed,
        dark-only) plot theme -- ax.cla() (called every draw()) resets
        this to matplotlib's defaults, so it has to be re-applied on
        every redraw. Every "Level N" panel is PyVista, not matplotlib
        (see LEVEL_PANEL_SIZE's own comment) -- its background/text
        color is set once, at panel construction (_build_level_pv_panel/
        _render_level_pv), not re-applied here. Returns the theme dict so
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
        """Rescan data/input/stretchy_nets/ and rebuild the dropdown. No
        more "(not computed)" distinction -- every net now starts from a
        cheap, instant random start (see module docstring), so there's no
        precomputed-vs-not state left to flag."""
        paths = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json")))
        self.label_to_path = {}
        for path in paths:
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
            # Default to DEFAULT_NET_BASENAME (cube.json) if present,
            # else just the first net alphabetically.
            default_path = os.path.join(STRETCHY_NETS_DIR, DEFAULT_NET_BASENAME + ".json")
            default_label = next((l for l, p in self.label_to_path.items() if p == default_path), None)
            self.current_label = default_label or (labels[0] if labels else None)

        if self.current_label:
            self.net_var.set(self.current_label)

    def on_select_net(self, event=None):
        chosen = self.net_var.get()
        self.current_label = chosen
        path = self.label_to_path[chosen]
        try:
            faces, self.mesh_name = load_stretchy_mesh(path)
        except ValueError as e:
            self._set_status(str(e), "error")
            self.faces = None
            return

        # A LEGACY fabric-subdivided net (one carrying baked-in
        # "coarse_faces", see utils/subdivisions/mesh_subdivide.load_fabric_spec
        # and generate_subdivided_stretchy_nets.py) is loaded at ITS OWN
        # coarse_faces -- i.e. always level 0 -- rather than its pre-baked
        # fine mesh; the new "Subdivide" button refines it interactively
        # from there instead (see module docstring). An ordinary net has
        # no coarse_faces and its own "faces" already are level 0.
        legacy_coarse_faces, _, _ = load_fabric_spec(path)
        self.base_faces = legacy_coarse_faces if legacy_coarse_faces is not None else faces
        self.colors = [FACE_COLORS[i % len(FACE_COLORS)] for i in range(len(self.base_faces))]

        # Precomputed once per net selection (see build_stretchy_net_layout's
        # docstring): a breadth-first spanning tree over shared edges,
        # attaching each face to whichever neighbor discovers it first --
        # the same idea utils/inflate_polyhedron/stretchy_net_layout.py uses for the rigid
        # pipeline. _draw_target_faces just reuses this on every redraw
        # rather than recomputing the BFS every time. Always over the
        # BASE faces -- the left panel's flat net layout doesn't change
        # with subdivision level, only its overlay does.
        self.target_layout = build_stretchy_net_layout(self.base_faces)

        # Level 0 and Level 1 share this exact fan-triangulated topology
        # (see module docstring) -- computed once here, up front, rather
        # than re-derived on promotion.
        self.faces, self.edge_length, self.face_of_fine = _build_level1_topology(self.base_faces)
        self.current_path = path
        self.subdivision_level = 0
        self.positions = random_initial_positions(self.faces, seed=0)
        self.iteration_count = 0
        self.last_stats = self._compute_stretch_stats()
        self.level_history = {}
        self.level_snapshots = {}
        self.history_tree.delete(*self.history_tree.get_children())
        self.stop_event = None
        self._record_level_history()
        self._update_level_action_buttons()
        self.draw()

    # ---- subdivide ----

    def _update_level_action_buttons(self):
        """Single source of truth for every level's one action button
        (see __init__'s Design notes): only the current frontier level's
        button is ever enabled -- idle it reads "Relax" (level 0) or
        "Inflate" (levels 1+), once that level converges it becomes
        "Subdivide" (clickable, advances to the next level) or "DONE!"
        (MAX_LEVEL, nothing further to subdivide to and so left
        disabled). A run in progress overrides this via
        _set_level_action_button_running instead -- this method is never
        called while one is active."""
        converged = bool(self.last_stats.get("converged"))
        for level, button in self.level_action_buttons.items():
            if level != self.subdivision_level or self.positions is None:
                # Not the current frontier -- reset its text too, not just
                # its disabled state: without this, a level that reached
                # "DONE!" (MAX_LEVEL, converged) on a PREVIOUS net keeps
                # showing "DONE!", now stuck and disabled, after selecting
                # a different net resets self.subdivision_level back to 0.
                # "Subdivide" (rather than leaving MAX_LEVEL's own idle
                # label, "Inflate") since that's the label this button
                # will actually show once every level up to it converges.
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
        """The actual level-advancing work behind on_subdivide_clicked --
        no status message or redraw of its own, so the caller reports/
        draws once itself. Only ever runs from Level 1 upward (Level 0's
        own advance to Level 1 is a promotion, not a subdivide_once call
        -- see _finish_relax).

        Freezes the level being LEFT into self.level_snapshots (its own
        "Level N" panel stops updating from here on -- see draw()) using
        whatever state that level had reached, before overwriting
        self.faces/positions/etc. with the new level's."""
        self.level_snapshots[self.subdivision_level] = {
            "faces": self.faces, "positions": self.positions,
            "face_of_fine": self.face_of_fine,
        }
        self.faces, self.positions, self.edge_length, self.face_of_fine = subdivide_once(
            self.faces, self.positions, self.edge_length, self.face_of_fine,
            self.subdivision_level)
        self.subdivision_level += 1
        # The face set just changed entirely (more, smaller faces) --
        # recomputed fresh for the NEW mesh, same as a brand new net load.
        self.last_stats = self._compute_stretch_stats()
        # Each level's own step count starts over at 0 -- a level's
        # "how many steps to converge" is only meaningful counted from
        # when that level's mesh was first created, not carried over from
        # however many steps a coarser level happened to need.
        self.iteration_count = 0
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
        """Records/updates the CURRENT level's row: the pressure last
        calibrated for it (None for Level 0, which has no pressure at all
        -- relax_initial_configuration is pure springs, see
        stretchy_mesh's docstring -- shown as "n/a" by
        _refresh_history_table), steps so far this level
        (self.iteration_count, see _subdivide_step/_finish_relax), the
        stretch stats at this point, and the actual stopping-condition
        value -- the relax's own `optimality` (None before any
        Inflate/Relax at this level, or if a Stop request aborted before
        any step ran -- see relax_once's docstring) -- all from
        self.last_stats. Called on every subdivide/promotion, every live
        Inflate/Relax progress update, and when a run finishes, so the row
        always reflects the level's latest state rather than only its
        final converged one."""
        self.level_history[self.subdivision_level] = {
            "pressure": None if self.subdivision_level == 0 else self.pressure_value,
            "steps": self.iteration_count,
            "max_stretch_pct": self.last_stats.get("max_stretch_pct", 0.0),
            "rms_stretch_pct": self.last_stats.get("rms_stretch_pct", 0.0),
            "optimality": self.last_stats.get("optimality"),
            "converged": self.last_stats.get("converged"),
        }
        self._refresh_history_table()

    @staticmethod
    def _format_sci(value, precision=2):
        """1.23e-05 -> "1.23e-5" (no leading zero on the exponent) --
        matches the compact form used in the Convergence column.
        `precision=0` gives "1e-4" style (used for the fixed threshold,
        which doesn't need decimal places since it never varies)."""
        mantissa, exponent = f"{value:.{precision}e}".split("e")
        return f"{mantissa}e{int(exponent)}"

    def _refresh_history_table(self):
        target_rms_pct = self.target_rms_var.get()
        for level in sorted(self.level_history):
            rec = self.level_history[level]
            optimality = rec["optimality"]
            if optimality is None:
                convergence, tags = "n/a", ()
            else:
                # The checkmark tracks the algorithm's own `converged`
                # flag, not a fresh optimality-vs-GTOL comparison redone
                # here -- convergence can also come from the stall-window
                # criterion (see _explicit_relax_loop) with optimality
                # still numerically above CONVERGENCE_GTOL, and the mark
                # would otherwise wrongly call that a failure.
                converged = rec["converged"]
                op = "<" if optimality < CONVERGENCE_GTOL else ">"
                mark = "✔" if converged else "✘"  # colored via row tag, not the glyph itself
                convergence = (f"{self._format_sci(optimality)} {op} "
                                f"{self._format_sci(CONVERGENCE_GTOL, precision=0)} {mark}")
                tags = ("converged",) if converged else ("not_converged",)
            pressure_str = "n/a" if rec["pressure"] is None else f"{rec['pressure']:.4g}"
            # Level 0 has no target stretch to chase (relax_initial_configuration
            # is pure springs, not calibrated against the spinner at all).
            rms_str = f"{rec['rms_stretch_pct']:.2f}"
            if level != 0:
                rms_str += f" (target: {target_rms_pct:.1f})"
            values = (level, pressure_str, rec["steps"], f"{rec['max_stretch_pct']:.2f}",
                      rms_str, convergence)
            iid = str(level)
            if self.history_tree.exists(iid):
                self.history_tree.item(iid, values=values, tags=tags)
            else:
                self.history_tree.insert("", "end", iid=iid, values=values, tags=tags)

    def _compute_stretch_stats(self):
        """max/rms edge stretch of the CURRENT self.faces/self.positions
        against self.edge_length -- the same two stats relax_once/
        relax_initial_configuration report, computed directly rather than
        via a relax, for a mesh that hasn't been relaxed at all yet (a
        fresh random start, or the freshly-interpolated positions right
        after a Subdivide click)."""
        edges = mesh_edges(self.faces)
        rest = (np.array([self.edge_length[e] for e in edges])
                if isinstance(self.edge_length, dict) else self.edge_length)
        lengths = np.array([np.linalg.norm(self.positions[a] - self.positions[b])
                             for a, b in edges])
        stretch_pct = 100 * (lengths - rest) / rest
        return {"max_stretch_pct": float(np.max(np.abs(stretch_pct))),
                "rms_stretch_pct": float(np.sqrt(np.mean(stretch_pct ** 2))),
                "optimality": None, "converged": None}

    # ---- inflate ----

    def _update_mode_state(self):
        self.steps_spin.state(["!disabled"] if self.iterate_mode_var.get() == "steps"
                               else ["disabled"])

    def _on_target_rms_changed(self, *_args):
        if self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_level_action_buttons()

    def on_inflate_clicked(self):
        """Two phases: first calibrate a pressure for the current "Target
        RMS stretch" (stretchy_mesh.estimate_pressure_for_target_stretch,
        via _run_background -- see _on_pressure_calibrated), THEN actually
        inflate at that pressure via the normal streamed _run_inflate_stream
        (respecting the steps-vs-convergence mode and the Stop button, same
        as always). Recalibrates fresh from wherever self.positions
        currently is on every click, since the user can no longer set
        pressure directly."""
        if self.positions is None or self.last_stats.get("converged"):
            return
        faces, edge_length, positions = self.faces, self.edge_length, self.positions
        target_rms_pct = self.target_rms_var.get()
        target_steps = max(1, self.steps_var.get()) if self.iterate_mode_var.get() == "steps" else None
        self._set_status(f"Finding a pressure that settles around {target_rms_pct:.1f}% "
                          "RMS stretch...", "info")
        self._run_background(
            lambda: estimate_pressure_for_target_stretch(positions, faces, edge_length,
                                                           target_rms_pct=target_rms_pct),
            (), lambda result: self._on_pressure_calibrated(result, target_steps))

    def _on_pressure_calibrated(self, result, target_steps):
        pressure = result[0]
        self.pressure_value = pressure
        self.stop_event = threading.Event()
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        status = (f"Inflating at pressure {pressure:.4g} for {target_steps} steps..."
                   if target_steps is not None else
                   f"Inflating at pressure {pressure:.4g} until convergence...")
        self._set_status(status, "info")
        self._run_inflate_stream(pressure, target_steps, self.stop_event)

    def _set_level_action_button_running(self, running):
        """Neither mode has a separate Stop button -- instead, the
        CURRENT frontier level's own action button turns into the Stop
        control for the duration of a run, then back to its normal
        Inflate/Relax/Subdivide/DONE! state once it finishes (delegated
        to _update_level_action_buttons, the single source of truth for
        that -- see _finish_inflate/_finish_relax). Safe to assume the
        frontier level doesn't change mid-run: every other level's button
        is disabled for the whole run too (see _set_controls_enabled),
        and Relax's own promotion only happens in _finish_relax, after
        the run is over."""
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

    def _run_chunked_relax_stream(self, step_fn, target_steps, stop_event, on_progress, on_finished):
        """Shared driver behind _run_inflate_stream and _run_relax_stream:
        calls `step_fn(chunk, stop_event) -> result` (result's own shape:
        (positions, nfev, max_stretch_pct, rms_stretch_pct, optimality,
        converged), same for relax_once and relax_initial_configuration)
        in a growing sequence of chunks (5, 10, 20, ..., capped at
        INFLATE_CHUNK_MAX) in a background thread, pushing a "progress"
        message to the queue after every chunk so the main thread can
        update the iteration counter/plot incrementally instead of
        jumping straight from the start count to the end one. Tk isn't
        thread-safe, so the worker only ever pushes to the queue; the
        main thread (via the scheduled poll below) is the only one that
        touches Tk widgets."""
        q = queue.Queue()

        def worker():
            completed = 0
            chunk = INFLATE_CHUNK_START
            try:
                while True:
                    this_chunk = max(1, chunk if target_steps is None
                                      else min(chunk, target_steps - completed))
                    result = step_fn(this_chunk, stop_event)
                    nfev, converged = result[1], result[5]
                    stopped = stop_event is not None and stop_event.is_set()

                    completed += nfev
                    q.put(("progress", result))
                    reached_target = target_steps is not None and completed >= target_steps
                    safety_cap_hit = target_steps is None and completed >= INFLATE_SAFETY_STEP_CAP
                    if converged or stopped or reached_target or safety_cap_hit:
                        break
                    chunk = min(chunk * 2, INFLATE_CHUNK_MAX)
                q.put(("final", None))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        on_progress(payload)
                    elif kind == "final":
                        on_finished()
                        return
                    elif kind == "error":
                        self.progress.stop()
                        self.progress.pack_forget()
                        self._set_controls_enabled(True)
                        self._set_status(f"Failed: {payload}", "error")
                        return
            except queue.Empty:
                pass
            self.root.after(80, poll)

        self.root.after(80, poll)

    def _run_inflate_stream(self, pressure, target_steps, stop_event):
        faces, edge_length = self.faces, self.edge_length
        state = {"positions": self.positions}

        def step_fn(chunk, stop_event):
            result = relax_once(state["positions"], faces, edge_length, pressure,
                                 PLANARITY_WEIGHT, max_nfev=chunk, stop_event=stop_event)
            state["positions"] = result[0]
            return result

        self._run_chunked_relax_stream(step_fn, target_steps, stop_event,
                                        self._apply_inflate_progress, self._finish_inflate)

    def _apply_inflate_progress(self, result):
        positions, nfev, max_stretch, rms_stretch, optimality, converged = result
        self.positions = positions
        self.iteration_count += nfev
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged}
        self._record_level_history()
        self._set_status(f"Inflating at level {self.subdivision_level}... "
                          f"{self.iteration_count} steps so far "
                          f"(edges stretched up to {max_stretch:.2f}%).", "info")
        self.draw()

    def _finish_inflate(self):
        self.progress.stop()
        self.progress.pack_forget()
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
                f"(RMS {rms_stretch:.2f}%).", "warn")
        elif converged:
            self._set_status(
                f"Converged after {self.iteration_count} steps at level "
                f"{self.subdivision_level}: edges stretched up to {max_stretch:.2f}% from rest "
                f"length (RMS {rms_stretch:.2f}%).", "success")
        else:
            self._set_status(
                f"Inflated ({self.iteration_count} steps at level {self.subdivision_level}, "
                f"step cap reached): edges stretched up to {max_stretch:.2f}% from rest length "
                f"(RMS {rms_stretch:.2f}%).",
                "info")

    # ---- relax (Level 0 only) ----

    def on_relax_clicked(self):
        """Level 0's analogue of on_inflate_clicked -- no pressure to
        calibrate first (relax_initial_configuration is pure springs, no
        pressure term at all, see stretchy_mesh's docstring), so this
        goes straight to the streamed run. Always runs to convergence
        (ignores the debug-mode steps-vs-convergence choice, which only
        applies to Inflate) -- Relax's whole point is to finish the
        initial-configuration algorithm, not to be steppable."""
        if self.positions is None or self.subdivision_level != 0 or self.last_stats.get("converged"):
            return
        self.stop_event = threading.Event()
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        self._set_status("Relaxing random start into a well-separated shape...", "info")
        self._run_relax_stream(self.stop_event)

    def _run_relax_stream(self, stop_event):
        faces, edge_length = self.faces, self.edge_length
        state = {"positions": self.positions}

        def step_fn(chunk, stop_event):
            result = relax_initial_configuration(state["positions"], faces, edge_length,
                                                  max_nfev=chunk, stop_event=stop_event)
            state["positions"] = result[0]
            return result

        self._run_chunked_relax_stream(step_fn, None, stop_event,
                                        self._apply_relax_progress, self._finish_relax)

    def _apply_relax_progress(self, result):
        positions, nfev, max_stretch, rms_stretch, optimality, converged = result
        self.positions = positions
        self.iteration_count += nfev
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged}
        self._record_level_history()
        self._set_status(f"Relaxing... {self.iteration_count} steps so far "
                          f"(edges stretched up to {max_stretch:.2f}%).", "info")
        self.draw()

    def _finish_relax(self):
        self.progress.stop()
        self.progress.pack_forget()
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        converged = self.last_stats.get("converged")
        max_stretch = self.last_stats.get("max_stretch_pct", 0.0)
        rms_stretch = self.last_stats.get("rms_stretch_pct", 0.0)
        self._record_level_history()
        if was_stopped:
            self._set_status(
                f"Stopped ({self.iteration_count} relax steps): edges stretched up to "
                f"{max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%).", "warn")
        elif converged:
            # Level 0 and Level 1 share the exact fan-triangulated
            # topology (see module docstring) -- promoting the
            # just-relaxed result into Level 1's starting position is a
            # pure relabeling, not a new subdivide_once call.
            self.level_snapshots[0] = {"faces": self.faces, "positions": self.positions,
                                        "face_of_fine": self.face_of_fine}
            level0_button = self.level_action_buttons.get(0)
            if level0_button is not None:
                level0_button.config(text="Relax", command=self.on_relax_clicked)
            self.subdivision_level = 1
            self.iteration_count = 0
            self.last_stats = self._compute_stretch_stats()
            self._record_level_history()
            self._set_status(
                f"Relaxed (edges stretched up to {max_stretch:.2f}% from rest length, RMS "
                f"{rms_stretch:.2f}%). Promoted to Level 1 -- press Inflate to continue.", "info")
        else:
            self._set_status(
                f"Relaxed ({self.iteration_count} steps, step cap reached): edges stretched up "
                f"to {max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%). Press Relax "
                "again to continue.", "info")
        self._set_controls_enabled(True)
        self._set_level_action_button_running(False)
        self.draw()

    # ---- background worker (used by pressure calibration) ----

    def _set_controls_enabled(self, enabled):
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (self.combo, self.target_rms_spin,
                       self.steps_radio, self.convergence_radio):
            widget.state(state)
        if enabled:
            self._update_mode_state()  # respect the steps/convergence choice
            self._update_level_action_buttons()  # respect the converged-at-this-pressure gate
        else:
            self.steps_spin.state(["disabled"])
            # The frontier level's action button is deliberately left
            # alone here -- the caller (_on_pressure_calibrated/
            # on_relax_clicked) re-enables it right after this runs,
            # turned into the Stop control (see
            # _set_level_action_button_running); every OTHER level's
            # stays disabled like normal, since it was never eligible
            # anyway (see _update_level_action_buttons). Neither mode has
            # a separate Stop button to arm/disarm here.
            for level, button in self.level_action_buttons.items():
                if level != self.subdivision_level:
                    button.state(["disabled"])

    def _run_background(self, fn, args, on_done):
        """Run fn(*args) in a background thread and call on_done(result)
        on the main thread once it finishes -- used for on_inflate_clicked's
        pressure calibration (estimate_pressure_for_target_stretch), which
        can take a moment. Tk isn't thread-safe, so the worker only ever
        pushes to a queue; the main thread (via the scheduled poll below)
        is the only one that touches Tk widgets. (Inflate/Relax each have
        their own streaming variant, _run_inflate_stream/_run_relax_stream,
        since they report incremental progress rather than one final
        result.)"""
        self._set_controls_enabled(False)
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        q = queue.Queue()

        def worker():
            try:
                q.put(("done", fn(*args)))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            self.progress.stop()
            self.progress.pack_forget()
            self._set_controls_enabled(True)
            if kind == "error":
                self._set_status(f"Failed: {payload}", "error")
                return
            on_done(payload)

        self.root.after(100, poll)

    # ---- drawing ----

    def _draw_target_faces(self, theme):
        """The UNDEFORMED net: every face laid out flat and CONNECTED to
        its neighbors (self.target_layout, precomputed once per net
        selection by a breadth-first search over shared edges -- see
        build_stretchy_net_layout) -- what the mesh would look like cut
        out of paper and unfolded flat, before any stretching/bending
        closes it up into the solved 3D shape on the right.

        Always shows the BASE (level 0) polygons here -- not the current
        level's individual fine triangles -- with a faint subdivision
        overlay at the CURRENT subdivision level (see mesh_levels'
        docstring: level L's overlay is subdivide_polygon's own
        resolution 2**(L-1), the absolute-resolution equivalent of this
        app's own incremental fan-then-quarter scheme), as a 2D preview of
        the mesh actually being solved."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        overlay_level = self.subdivision_level
        faces = self.base_faces
        all_pts = []
        for face_idx in sorted(self.target_layout):
            face = faces[face_idx]
            color = self.colors[face_idx % len(self.colors)]
            placed = self.target_layout[face_idx]
            self.ax2d.add_patch(Polygon(placed, closed=True, facecolor=color,
                                         edgecolor="k", alpha=0.9))
            if overlay_level > 0:
                sub_points, sub_triangles = subdivide_polygon(
                    len(face), placed, 2 ** (overlay_level - 1))
                segments = []
                for i, j, k in sub_triangles:
                    segments += [(sub_points[i], sub_points[j]),
                                 (sub_points[j], sub_points[k]),
                                 (sub_points[k], sub_points[i])]
                self.ax2d.add_collection(LineCollection(
                    segments, colors="k", linewidths=SUBDIVISION_EDGE_WIDTH,
                    alpha=SUBDIVISION_EDGE_ALPHA, zorder=3))
            all_pts.extend(placed)

        all_pts = np.array(all_pts)
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        pad = 0.6
        self.ax2d.set_xlim(lo[0] - pad, hi[0] + pad)
        self.ax2d.set_ylim(lo[1] - pad, hi[1] + pad)
        self.ax2d.set_aspect("equal")
        # No ax.set_title() here -- "Net" is a plain Tkinter Label above
        # this canvas instead, same as every "Level N" panel's title (see
        # __init__'s Design notes on why titles live outside the drawing
        # area now).

    def draw(self):
        """Redraws the Net panel plus every "Level N" panel: level ==
        self.subdivision_level draws LIVE from current state; a level in
        self.level_snapshots (already subdivided past, or -- for Level
        0 -- promoted away from by a converged Relax) draws its frozen
        state; any other level hasn't been reached yet and draws empty
        (see _draw_level_panel). Every level panel shares ONE camera
        angle (self.level_azim/level_elev, see __init__'s Design notes)
        -- nothing further to sync here, since _draw_level_panel already
        renders every panel from that same shared state on every call."""
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        for level in self.level_plotters:
            if level == self.subdivision_level:
                self._draw_level_panel(level, self.faces, self.positions, self.face_of_fine)
            elif level in self.level_snapshots:
                snap = self.level_snapshots[level]
                self._draw_level_panel(level, snap["faces"], snap["positions"],
                                        snap["face_of_fine"])
            else:
                self._draw_level_panel(level, None, None, None)
        self._draw_idle_all()


def main():
    root = tk.Tk()
    InflatePolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
