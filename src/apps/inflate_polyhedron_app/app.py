"""
Inflate Polyhedron -- interactive fabric relaxation for stretchy meshes.

    python src/apps/inflate_polyhedron_app/app.py

Nets here (data/input/stretchy_nets/*.json, see utils/inflate_polyhedron/stretchy_mesh.py
for the vertex-loop format) are specified directly as vertex loops --
shared vertex ids ARE the adjacency, so a face pair sharing several edges
(which would force two RIGID flat faces into the same plane -- see
utils/inflate_polyhedron/stretchy_mesh.py's module docstring) needs no special
casing.

Every net is always SOLVED at its own base (level 0) resolution first --
even a legacy fabric-subdivided file (one carrying baked-in
"coarse_faces", see utils/subdivisions/mesh_subdivide.load_fabric_spec
and generate_subdivided_stretchy_nets.py) starts from ITS OWN
coarse_faces rather than its pre-baked fine mesh -- but is only ever
SHOWN already subdivided to STARTING_LEVEL (1): level 0 exists purely as
what STARTING_LEVEL's fan subdivision interpolates from, never as
something the user interacts with directly. The "Subdivide" button (see
utils.inflate_polyhedron.mesh_levels) then refines the CURRENT mesh
interactively, one nested level at a time (0..MAX_LEVEL), interpolating
every new point from wherever the mesh's own nearby points currently sit
-- so any inflation already done at one level carries forward as the
next level's starting point, rather than being discarded and re-solved
from scratch the way loading a fixed precomputed fine mesh used to. This
supersedes the old fixed-resolution fabric-net files/build_cache
precompute pipeline for this app's own workflow -- the fixed-resolution
example nets it used to ship with (cube_res3.json and friends) have been
removed accordingly, though the format and generate_subdivided_stretchy_nets.py
itself still work for anyone who wants one.

1. On selecting a net, its BASE (level 0) faces are solved with
   stretchy_mesh.solve_wireframe -- its random-restart-plus-inflation-ramp
   search is exactly what makes this reliable (it doesn't hang: a coarse
   net has few enough faces that restarting from a different random start
   when one doesn't inflate cleanly is cheap and effective -- see
   solve_wireframe's docstring). An ordinary (non-fabric) net's solve is
   still cached via utils/inflate_polyhedron/stretchy_cache.py
   (load_with_cache -- instant on a cache hit); a legacy fabric file's
   extracted coarse_faces are solved fresh instead, uncached, since a
   coarse solve is already cheap.
2. "Subdivide" (mesh_levels.subdivide_once) refines the CURRENT mesh by
   one level: level 0 -> 1 triangulates every face via a centroid fan
   (unchanged for an already-triangular face); each level after that
   quarters every triangle by connecting edge midpoints. New points are
   linearly interpolated from the current mesh's own nearby points; new
   REST lengths (as opposed to positions) are derived analytically from
   the original unit-edge flat reference geometry, so the ideal target
   shape stays fixed as resolution increases (see mesh_levels' docstring)
   -- letting "inflate, then increase resolution, then inflate again"
   converge toward one consistent answer instead of each level chasing a
   different target. Greyed out once MAX_LEVEL is reached.
3. At ANY level, the "Inflate" button first CALIBRATES a pressure (see
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
4. The "Convergence History" table records one row per subdivision level
   visited this net session: the pressure last calibrated for it, how
   many Inflate steps that level has taken so far (self.iteration_count
   -- reset to 0 by every Subdivide click, so it always counts from when
   that level's mesh was first created, not carried over from a coarser
   level), the stretch stats at whatever point it's currently at (RMS
   shown against the CURRENT "Target RMS stretch" spinner value), and a
   single combined "Convergence" cell -- relax_once's own `max_force`
   (the worst vertex's net force) against the fixed CONVERGENCE_GTOL
   threshold, with a check or cross mark for whether it's below it --
   updated live while Inflate runs.
5. The view below is "Net" (the flat, undeformed layout) plus one 3D
   panel per level, "Level 1".."Level N" (MAX_LEVEL total). Only the
   panel for self.subdivision_level is LIVE -- it redraws every Inflate
   progress update; every level already subdivided past is frozen at
   whatever state it was left in (self.level_snapshots, captured by
   _subdivide_step the moment the user moves on from it) and never
   updates again; a level not reached yet is drawn empty. Level 0 never
   gets its own panel -- this app always auto-advances past it, see
   STARTING_LEVEL above.
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
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sv_ttk

from common.paths import STRETCHY_NETS_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS, DISABLED_SUFFIX
from ui.cullable_face import _CullableFace
from utils.inflate_polyhedron.stretchy_mesh import (
    load_stretchy_mesh, solve_wireframe, relax_once, estimate_pressure_for_target_stretch,
    mesh_to_polyhedron, mesh_edges, EDGE_LENGTH, PLANARITY_WEIGHT, CONVERGENCE_GTOL,
    DEFAULT_TARGET_RMS_STRETCH_PCT,
)
from utils.inflate_polyhedron.stretchy_cache import load_with_cache, is_cached, cache_path_for
from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.subdivisions.mesh_subdivide import load_fabric_spec
from utils.inflate_polyhedron.stretchy_net_layout import build_stretchy_net_layout
from utils.subdivisions import subdivide as subdivide_polygon

# This app's OWN cache -- not shared with polyhedron_unfolder (a different
# pipeline entirely) or with any other app.
CACHE_DIR = Path(__file__).resolve().parent / "cache"

DEFAULT_NET_BASENAME = "cube"

# Every net now starts already subdivided to this level rather than at the
# raw level-0 base faces -- level 0 is still solved first internally (it's
# what the fan subdivision to level 1 interpolates from), just never shown
# on its own.
STARTING_LEVEL = 1

# A fabric-subdivided net's fine mesh edges are drawn thin/faint so the
# subdivision reads as texture rather than a bold wireframe competing
# with the per-coarse-face coloring -- see load_fabric_spec.
SUBDIVISION_EDGE_ALPHA = 0.35
SUBDIVISION_EDGE_WIDTH = 0.5

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


def _solve_level0(path, base_faces, is_legacy_fabric, cache_dir):
    """The level-0 (coarse) starting shape for a just-selected net -- run
    in a background thread by on_select_net via _run_background.
    `is_legacy_fabric` (a file with baked-in "coarse_faces", see
    load_fabric_spec): its own precomputed fine-mesh cache targeted a
    fixed resolution from the old, now-superseded precompute pipeline, so
    `base_faces` is solved fresh instead (cheap -- see solve_wireframe's
    docstring) rather than via that stale cache. An ordinary net still
    uses stretchy_cache normally. Returns (positions, stats, name) --
    name is None for the fresh-solve path (the caller already has the
    net's own name from load_stretchy_mesh)."""
    if is_legacy_fabric:
        positions, stats = solve_wireframe(base_faces, edge_length=EDGE_LENGTH, seed=0)
        return positions, stats, None
    _, positions, stats, name = load_with_cache(path, cache_path_for(path, cache_dir))
    return positions, stats, name


class InflatePolyhedronApp:
    def __init__(self, root):
        self.root = root
        root.title("Inflate Polyhedron")
        root.geometry("1200x820")
        root.minsize(820, 600)

        sv_ttk.set_theme("dark")

        # ---- Net selection + Subdivision, side by side to save vertical
        # space -- unrelated topics, but both are small/short controls. ----
        top_row = ttk.Frame(root)
        top_row.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(14, 8))

        net_frame = ttk.LabelFrame(top_row, text="Net", padding=12)
        net_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        picker_row = ttk.Frame(net_frame)
        picker_row.pack(fill=tk.X)
        ttk.Label(picker_row, text="Choose a net:").pack(side=tk.LEFT, padx=(0, 8))
        self.combo = ttk.Combobox(picker_row, state="readonly", width=30)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        status_row = ttk.Frame(net_frame)
        status_row.pack(fill=tk.X, pady=(10, 0))
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=160)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(status_row, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # ---- Subdivision: nested-level mesh refinement (level 0 is the
        # net's own base faces; each press adds one level, up to
        # MAX_LEVEL -- see mesh_levels' docstring). ----
        subdivide_frame = ttk.LabelFrame(top_row, text="Subdivide", padding=12)
        subdivide_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        self.subdivide_button = ttk.Button(subdivide_frame, text="Subdivide",
                                            command=self.on_subdivide_clicked)
        self.subdivide_button.pack(side=tk.LEFT)
        self.subdivide_level_var = tk.StringVar(value="Level: 0")
        ttk.Label(subdivide_frame, textvariable=self.subdivide_level_var).pack(
            side=tk.LEFT, padx=(10, 0))

        # ---- Inflation: everything about running relax_once lives here,
        # in the order it's used -- pick a pressure, pick how much work to
        # do, then Inflate (or Stop one that's already running). ----
        inflate_frame = ttk.LabelFrame(root, text="Inflate", padding=12)
        inflate_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))

        pressure_row = ttk.Frame(inflate_frame)
        pressure_row.pack(fill=tk.X)
        ttk.Label(pressure_row, text="Target RMS stretch:").pack(side=tk.LEFT, padx=(0, 4))
        self.target_rms_var = tk.DoubleVar(value=DEFAULT_TARGET_RMS_STRETCH_PCT)
        # A "converged" verdict only applies to the target it was reached
        # at -- changing this means the current pressure hasn't actually
        # been (re)calibrated for the new target yet, so the gate on
        # re-clicking Inflate (see _update_inflate_button_state) needs to
        # lift, since otherwise a converged mesh would stay stuck
        # refusing to recalibrate even after the user asks for a
        # different target.
        self.target_rms_var.trace_add("write", self._on_target_rms_changed)
        self.target_rms_spin = ttk.Spinbox(pressure_row, from_=0.1, to=200.0,
                                            increment=1.0, width=6,
                                            textvariable=self.target_rms_var, format="%.1f")
        self.target_rms_spin.pack(side=tk.LEFT)
        ttk.Label(pressure_row, text="%").pack(side=tk.LEFT, padx=(2, 8))
        # Pressure is no longer user-editable or separately displayed --
        # "Inflate" calibrates it itself (see on_inflate_clicked) and it's
        # already logged per level in the Convergence History table.
        self.pressure_value = DEFAULT_PRESSURE

        mode_row = ttk.Frame(inflate_frame)
        mode_row.pack(fill=tk.X, pady=(8, 0))
        self.iterate_mode_var = tk.StringVar(value="convergence")
        self.steps_radio = ttk.Radiobutton(mode_row, text="Iterate for", value="steps",
                                            variable=self.iterate_mode_var,
                                            command=self._update_mode_state)
        self.steps_radio.pack(side=tk.LEFT)
        self.steps_var = tk.IntVar(value=DEFAULT_STEPS)
        self.steps_spin = ttk.Spinbox(mode_row, from_=1, to=1000000, width=7,
                                       textvariable=self.steps_var)
        self.steps_spin.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(mode_row, text="steps").pack(side=tk.LEFT, padx=(0, 18))
        self.convergence_radio = ttk.Radiobutton(mode_row, text="Iterate until convergence",
                                                  value="convergence",
                                                  variable=self.iterate_mode_var,
                                                  command=self._update_mode_state)
        self.convergence_radio.pack(side=tk.LEFT)

        button_row = ttk.Frame(inflate_frame)
        button_row.pack(fill=tk.X, pady=(8, 0))
        self.inflate_button = ttk.Button(button_row, text="Inflate",
                                          command=self.on_inflate_clicked)
        self.inflate_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(button_row, text="Stop", command=self.on_stop_clicked)
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_button.state(["disabled"])

        # ---- Convergence history: one row per subdivision level visited
        # this net session, showing the pressure last calibrated for it
        # (self.pressure_value -- only ever set by on_inflate_clicked's
        # calibration phase), how many Inflate steps that level took
        # (self.iteration_count, reset to 0 on every Subdivide -- see
        # _subdivide_step), the stretch stats at whatever point it's
        # currently at (updated live while Inflate runs, finalized once it
        # stops -- see _record_level_history's callers, RMS shown against
        # the CURRENT "Target RMS stretch" spinner value -- see
        # _refresh_history_table), and a single combined "Convergence"
        # cell -- relax_once's own `optimality` (the worst vertex's net
        # force) against the fixed CONVERGENCE_GTOL threshold, with a
        # check/cross mark for whether it's below it (see
        # _refresh_history_table). height=MAX_LEVEL since that's the most
        # rows this table will ever hold -- a taller fixed height would
        # just reserve blank space below whatever's actually populated. ----
        history_frame = ttk.LabelFrame(root, text="Convergence History", padding=12)
        history_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        history_columns = ("level", "pressure", "steps", "max_stretch", "rms_stretch",
                            "convergence")
        self.history_tree = ttk.Treeview(history_frame, columns=history_columns,
                                          show="headings", height=MAX_LEVEL)
        for col, heading, width in (
                ("level", "Level", 50), ("pressure", "Pressure", 80), ("steps", "Steps", 70),
                ("max_stretch", "Max Stretch %", 110), ("rms_stretch", "RMS Stretch %", 150),
                ("convergence", "Convergence", 170)):
            self.history_tree.heading(col, text=heading)
            self.history_tree.column(col, width=width, anchor=tk.CENTER)
        self.history_tree.pack(fill=tk.X)

        # ---- Net (flat layout) + one 3D panel per level (1..MAX_LEVEL),
        # side by side. Level N's panel is LIVE (redrawn every Inflate
        # progress update) only while self.subdivision_level == N; once
        # the user subdivides past it, that level's last state is frozen
        # into self.level_snapshots and its panel stops updating -- see
        # draw()/_subdivide_step. ----
        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))
        self.fig = plt.figure(figsize=(18, 5))
        n_panels = 1 + MAX_LEVEL
        self.ax2d = self.fig.add_subplot(1, n_panels, 1)
        self.ax3d_by_level = {
            level: self.fig.add_subplot(1, n_panels, 1 + level, projection="3d")
            for level in range(1, MAX_LEVEL + 1)
        }
        self.canvas = FigureCanvasTkAgg(self.fig, master=view_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Vertex markers are only culled/positioned correctly for whatever
        # orientation was current the last time draw() ran (see
        # _draw_wireframe_panel's docstring) -- mplot3d's own interactive
        # rotation changes elev/azim continuously without ever calling our
        # draw() again, so hide them for the DURATION of a drag rather than
        # show stale, wrongly-culled markers mid-rotation; they reappear,
        # freshly culled for the new angle, on mouse release.
        self._dragging_3d = False
        self.vertex_scatter = None
        self.canvas.mpl_connect("button_press_event", self._on_3d_drag_start)
        self.canvas.mpl_connect("button_release_event", self._on_3d_drag_end)

        # Per-level frozen snapshots of {faces, positions, face_of_fine,
        # edge_length} taken the moment the user subdivides PAST that
        # level (see _subdivide_step) -- level 0 is never snapshotted or
        # shown (this app always auto-advances past it, see STARTING_LEVEL).
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
        # Bumped on every on_select_net call and captured by that call's
        # own _on_loaded closure -- if a second net selection starts
        # before the first one's background solve finishes, the first's
        # eventually-arriving result is now for a STALE generation (this
        # matters more now than it used to: _on_loaded auto-subdivides to
        # STARTING_LEVEL, mutating self.faces, so a late, stale result's
        # positions could otherwise be paired with a self.faces that has
        # already moved on to a newer selection's subdivided mesh).
        self._load_generation = 0
        self.current_path = None
        self.current_label = None
        self.label_to_path = {}
        self._apply_plot_theme()
        self.refresh_net_list()
        if self.current_label:
            self.on_select_net()

    def _set_status(self, text, kind="info"):
        self.status_var.set(text)
        self.status_label.configure(foreground=STATUS_COLORS.get(kind, ""))

    # ---- theme ----

    def _style_3d_axis(self, ax, theme):
        ax.title.set_color(theme["fg"])
        ax.set_axis_off()

    def _style_2d_axis(self, ax, theme):
        ax.title.set_color(theme["fg"])
        ax.set_axis_off()

    def _apply_plot_theme(self):
        """Recolor the figure/axes chrome to match the (fixed, dark-only)
        plot theme -- ax.cla() (called every draw()) resets all of this to
        matplotlib's defaults, so it has to be re-applied on every redraw.
        Returns the theme dict so draw() can reuse its colors."""
        theme = PLOT_THEME
        self.fig.patch.set_facecolor(theme["bg"])
        self.ax2d.set_facecolor(theme["bg"])
        self._style_2d_axis(self.ax2d, theme)
        for ax in self.ax3d_by_level.values():
            ax.set_facecolor(theme["bg"])
            self._style_3d_axis(ax, theme)
        return theme

    def _refresh_plot(self):
        if self.positions is not None:
            self.draw()
        else:
            self._apply_plot_theme()
            self.canvas.draw_idle()

    def _on_3d_drag_start(self, event):
        """mplot3d's own left-click-drag rotation starts here -- hide the
        vertex-marker scatter for the duration (see its own comment in
        __init__ for why), leaving the (live-culled) faces/edges alone."""
        if event.inaxes not in self.ax3d_by_level.values() or event.button != 1:
            return
        self._dragging_3d = True
        if self.vertex_scatter is not None:
            self.vertex_scatter.set_visible(False)
            self.canvas.draw_idle()

    def _on_3d_drag_end(self, event):
        if not self._dragging_3d:
            return
        self._dragging_3d = False
        # A full redraw (not just set_visible(True)) so the vertex culling
        # itself is recomputed for wherever the drag left the view angle.
        self._refresh_plot()

    # ---- net picker ----

    def refresh_net_list(self, keep_selection=True):
        """Rescan data/input/stretchy_nets/ and rebuild the dropdown -- a net with no
        matching stretchy_cache/*.json gets a "(not computed)" suffix
        (purely informational: selecting it still works, it just means
        the precomputed coarse-solve-then-drape starting point isn't
        ready yet, so on_select_net's background load will solve it
        fresh instead of an instant cache read -- see module docstring)."""
        paths = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json")))
        self.label_to_path = {}
        for path in paths:
            base_label = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            label = base_label if is_cached(path, cache_path_for(path, CACHE_DIR)) else base_label + DISABLED_SUFFIX
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
            self.combo.set(self.current_label)

    def on_select_net(self, event=None):
        chosen = self.combo.get()
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

        self.current_path = path
        self.subdivision_level = 0
        self.faces = self.base_faces
        self.face_of_fine = list(range(len(self.base_faces)))
        self.edge_length = EDGE_LENGTH
        self.iteration_count = 0
        self.last_stats = {}
        self.level_history = {}
        self.level_snapshots = {}
        self.history_tree.delete(*self.history_tree.get_children())
        self.positions = None
        self.stop_event = None
        self._update_subdivide_button_state()
        self._load_generation += 1
        generation = self._load_generation
        self._run_background(
            _solve_level0, (path, self.base_faces, legacy_coarse_faces is not None, CACHE_DIR),
            lambda payload: self._on_loaded(payload, generation))

    def _on_loaded(self, payload, generation):
        if generation != self._load_generation:
            return  # a newer net selection has since started; this result is stale
        positions, stats, _cached_name = payload
        self.positions = positions
        self.last_stats = {"max_stretch_pct": stats["max_stretch_pct"],
                            "rms_stretch_pct": stats["rms_stretch_pct"],
                            "optimality": None, "converged": None}
        # Every net starts already advanced to STARTING_LEVEL rather than
        # shown at the raw level-0 base faces (see its own comment) --
        # level 0 itself never gets a history row, since the user never
        # interacts with it directly.
        while self.subdivision_level < STARTING_LEVEL:
            self._subdivide_step()
        self._update_inflate_button_state()
        self._update_subdivide_button_state()  # reflect STARTING_LEVEL, not level 0
        self.refresh_net_list()  # the net just loaded may have just gained a cache entry
        self.draw()

    # ---- subdivide ----

    def _update_subdivide_button_state(self):
        can_subdivide = self.positions is not None and self.subdivision_level < MAX_LEVEL
        self.subdivide_button.state(["!disabled"] if can_subdivide else ["disabled"])
        self.subdivide_level_var.set(f"Level: {self.subdivision_level}")

    def _subdivide_step(self):
        """The actual level-advancing work, shared by on_subdivide_clicked
        and _on_loaded's auto-advance to STARTING_LEVEL -- no status
        message or redraw of its own, so the caller can run this several
        times in a row (e.g. level 0 -> STARTING_LEVEL) and only report/
        draw once at the end.

        Freezes the level being LEFT into self.level_snapshots (its own
        "Level N" panel stops updating from here on -- see draw()) using
        whatever state that level had reached, before overwriting
        self.faces/positions/etc. with the new level's. Level 0 is never
        snapshotted (or shown at all -- see STARTING_LEVEL)."""
        if self.subdivision_level >= 1:
            self.level_snapshots[self.subdivision_level] = {
                "faces": self.faces, "positions": self.positions,
                "face_of_fine": self.face_of_fine,
            }
        self.faces, self.positions, self.edge_length, self.face_of_fine = subdivide_once(
            self.faces, self.positions, self.edge_length, self.face_of_fine,
            self.subdivision_level)
        self.subdivision_level += 1
        # The face set just changed entirely (more, smaller faces) --
        # recomputed fresh for the NEW mesh, same as a brand new net load
        # (see _on_loaded).
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
        self._update_subdivide_button_state()
        self._update_inflate_button_state()  # a fresh subdivision hasn't converged yet
        self._set_status(
            f"Subdivided to level {self.subdivision_level} ({len(self.faces)} faces, "
            f"{len(self.positions)} vertices, edges stretched up to "
            f"{self.last_stats['max_stretch_pct']:.2f}%). Press Inflate to relax/inflate "
            f"further.", "info")
        self.draw()

    # ---- convergence history table ----

    def _record_level_history(self):
        """Records/updates the CURRENT level's row: the pressure last
        calibrated for it, steps so far this level (self.iteration_count,
        see _subdivide_step), the stretch stats at this point, and the
        actual stopping-condition value -- relax_once's own `optimality`
        (None before any Inflate at this level, or if a Stop request
        aborted before any step ran -- see relax_once's docstring) -- all
        from self.last_stats. Called on every subdivide, every live
        Inflate progress update, and when an Inflate run finishes, so the
        row always reflects the level's latest state rather than only its
        final converged one."""
        self.level_history[self.subdivision_level] = {
            "pressure": self.pressure_value,
            "steps": self.iteration_count,
            "max_stretch_pct": self.last_stats.get("max_stretch_pct", 0.0),
            "rms_stretch_pct": self.last_stats.get("rms_stretch_pct", 0.0),
            "optimality": self.last_stats.get("optimality"),
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
                convergence = "n/a"
            else:
                op = "<" if optimality < CONVERGENCE_GTOL else ">"
                mark = "✅" if optimality < CONVERGENCE_GTOL else "❌"
                convergence = (f"{self._format_sci(optimality)} {op} "
                                f"{self._format_sci(CONVERGENCE_GTOL, precision=0)} {mark}")
            values = (level, f"{rec['pressure']:.4g}", rec["steps"], f"{rec['max_stretch_pct']:.2f}",
                      f"{rec['rms_stretch_pct']:.2f} (target: {target_rms_pct:g})",
                      convergence)
            iid = str(level)
            if self.history_tree.exists(iid):
                self.history_tree.item(iid, values=values)
            else:
                self.history_tree.insert("", "end", iid=iid, values=values)

    def _compute_stretch_stats(self):
        """max/rms edge stretch of the CURRENT self.faces/self.positions
        against self.edge_length -- the same two stats relax_once/
        solve_wireframe report, computed directly rather than via a solve,
        for the freshly-interpolated (not yet relaxed) mesh right after a
        Subdivide click."""
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

    def _update_inflate_button_state(self):
        """Greys out Inflate once self.last_stats reports the mesh already
        converged at the current pressure -- clicking again would just
        burn steps without moving anything, since relax_once from an
        already-converged point starts with near-zero force already.
        Re-armed by _on_target_rms_changed, a new net load, or a Stop
        (which leaves converged=False since it didn't run to
        completion)."""
        if self.last_stats.get("converged"):
            self.inflate_button.state(["disabled"])
        else:
            self.inflate_button.state(["!disabled"])

    def _on_target_rms_changed(self, *_args):
        if self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_inflate_button_state()

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
        self.stop_button.state(["!disabled"])
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        status = (f"Inflating at pressure {pressure:.4g} for {target_steps} steps..."
                   if target_steps is not None else
                   f"Inflating at pressure {pressure:.4g} until convergence...")
        self._set_status(status, "info")
        self._run_inflate_stream(pressure, target_steps, self.stop_event)

    def on_stop_clicked(self):
        if self.stop_event is not None:
            self.stop_event.set()
            self.stop_button.state(["disabled"])  # one request is enough; avoid repeat clicks
            self._set_status("Stopping...", "warn")
        self._set_status(
            f"Auto pressure {pressure:.3f}: edges stretched up to {max_stretch:.2f}% from rest "
            f"length (RMS {rms_stretch:.2f}%).", "success")
        self.draw()

    def _run_inflate_stream(self, pressure, target_steps, stop_event):
        """Runs relax_once in a growing sequence of chunks (5, 10, 20, ...,
        capped at INFLATE_CHUNK_MAX) in a background thread, pushing a
        "progress" message to the queue after every chunk so the main
        thread can update the iteration counter/plot incrementally
        instead of jumping straight from the start count to the end one.
        Tk isn't thread-safe, so the worker only ever pushes to the
        queue; the main thread (via the scheduled poll below) is the
        only one that touches Tk widgets."""
        q = queue.Queue()
        faces, edge_length = self.faces, self.edge_length
        start_positions = self.positions

        def worker():
            positions = start_positions
            completed = 0
            chunk = INFLATE_CHUNK_START
            try:
                while True:
                    this_chunk = max(1, chunk if target_steps is None
                                      else min(chunk, target_steps - completed))
                    result = relax_once(positions, faces, edge_length, pressure,
                                         PLANARITY_WEIGHT, max_nfev=this_chunk, stop_event=stop_event)
                    trial_positions, nfev, max_stretch, rms_stretch, optimality, converged = result
                    stopped = stop_event is not None and stop_event.is_set()

                    positions = trial_positions
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
                        self._apply_inflate_progress(payload)
                    elif kind == "final":
                        self._finish_inflate()
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

    # ---- background worker (used by the initial cache load) ----

    def _set_controls_enabled(self, enabled):
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (self.combo, self.target_rms_spin,
                       self.steps_radio, self.convergence_radio):
            widget.state(state)
        if enabled:
            self._update_mode_state()  # respect the steps/convergence choice
            self._update_inflate_button_state()  # respect the converged-at-this-pressure gate
            self._update_subdivide_button_state()  # respect the at-MAX_LEVEL gate
            self.stop_button.state(["disabled"])
        else:
            self.steps_spin.state(["disabled"])
            self.inflate_button.state(["disabled"])
            self.subdivide_button.state(["disabled"])
            # stop_button is armed separately by on_inflate_clicked (right
            # after this runs) -- other background jobs, like the initial
            # cache load, leave it disabled since there's nothing to
            # usefully interrupt there.

    def _run_background(self, fn, args, on_done):
        """Run fn(*args) in a background thread and call on_done(result)
        on the main thread once it finishes -- used for the initial
        precomputed-shape load (see module docstring), which can take a
        moment on a cache miss. Tk isn't thread-safe, so the worker only
        ever pushes to a queue; the main thread (via the scheduled poll
        below) is the only one that touches Tk widgets. ("Inflate" has
        its own streaming variant, _run_inflate_stream, since it reports
        incremental progress rather than one final result.)"""
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
        self.ax2d.set_title("Net")

    def _draw_wireframe_panel(self, ax, theme, level, faces, positions, face_of_fine):
        """One "Level N" panel: possibly non-planar faces (drawn opaque)
        plus the raw vertex/edge wireframe on top, since a "face" here is
        just a rendering convenience -- the thing actually being relaxed
        is the vertex positions and edge lengths. `faces` is None for a
        level not yet reached this net session (see draw()) -- drawn as
        an empty panel with just its title.

        Colors every fine triangle by its ORIGINAL base face
        (`face_of_fine`, indexing the same per-base-face self.colors the
        Net panel uses) so the base faces stay visually distinct as color
        blocks, with the fine mesh edges thin and faint (see
        SUBDIVISION_EDGE_ALPHA/WIDTH) so the subdivision reads as texture
        rather than a bold wireframe.

        Wraps (positions, faces) into a Polyhedron -- its .edges gives the
        wireframe segments for the (rarer) open-mesh fallback below
        (positions re-indexed to Polyhedron's own dense 0..N-1 space, so
        `polyhedron.vertices[i]` is the position for edge endpoint `i`
        directly, no dict lookup needed), and .is_closed() gates whether
        _CullableFace's exact backface culling applies (see its own
        docstring: only valid for a closed CONVEX solid). When closed,
        each face is drawn as a _CullableFace carrying its OWN boundary
        edges, so a face's wireframe lines disappear together with the
        face itself once it's facing away from the camera -- drawing
        every edge as one separate, undivided Line3DCollection (the
        open-mesh fallback below) has no per-face depth information at
        all, so back-face lines would otherwise render right through the
        opaque near faces regardless of view angle."""
        ax.cla()
        self._style_3d_axis(ax, theme)
        if faces is None:
            ax.set_title(f"Level {level}")
            return

        face_colors = [self.colors[c % len(self.colors)] for c in face_of_fine]
        polyhedron = mesh_to_polyhedron(positions, faces)
        closed = polyhedron.is_closed()

        all_pts = np.array(list(positions.values()))
        for face_index, (face, color) in enumerate(zip(faces, face_colors)):
            pts = np.array([positions[v] for v in face])
            if closed:
                normal = polyhedron.face_normal(face_index)
                ax.add_collection3d(_CullableFace(
                    [pts], normal, base_alpha=1.0,
                    facecolor=color, edgecolor=theme["fg"], linewidths=SUBDIVISION_EDGE_WIDTH))
            else:
                ax.add_collection3d(
                    Poly3DCollection([pts], facecolor=color, edgecolor="none", alpha=1.0))

        if not closed:
            # No exact culling is possible without closed convexity (see
            # _CullableFace's docstring) -- fall back to one plain,
            # undivided wireframe overlay.
            edge_segments = [(polyhedron.vertices[a], polyhedron.vertices[b])
                              for a, b in polyhedron.edges]
            ax.add_collection3d(Line3DCollection(
                edge_segments, colors=theme["fg"], linewidths=SUBDIVISION_EDGE_WIDTH,
                alpha=SUBDIVISION_EDGE_ALPHA))

        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        center = (lo + hi) / 2
        half = (hi - lo).max() / 2 * 1.2 + 1e-6
        ax.set_xlim(center[0] - half, center[0] + half)
        ax.set_ylim(center[1] - half, center[1] + half)
        ax.set_zlim(center[2] - half, center[2] + half)
        ax.set_box_aspect([1, 1, 1])
        ax.set_title(f"Level {level}")

    def draw(self):
        """Redraws the Net panel plus every "Level N" panel: level ==
        self.subdivision_level draws LIVE from current state; a level in
        self.level_snapshots (already subdivided past) draws its frozen
        state; any other level hasn't been reached yet and draws empty
        (see _draw_wireframe_panel)."""
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        for level, ax in self.ax3d_by_level.items():
            if level == self.subdivision_level:
                self._draw_wireframe_panel(ax, theme, level, self.faces, self.positions,
                                            self.face_of_fine)
            elif level in self.level_snapshots:
                snap = self.level_snapshots[level]
                self._draw_wireframe_panel(ax, theme, level, snap["faces"], snap["positions"],
                                            snap["face_of_fine"])
            else:
                self._draw_wireframe_panel(ax, theme, level, None, None, None)
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    InflatePolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
