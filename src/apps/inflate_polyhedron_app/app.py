"""
Inflate Polyhedron -- interactive fabric relaxation for stretchy meshes.

    python src/apps/inflate_polyhedron_app/app.py

Nets here (data/input/stretchy_nets/*.json, see utils/inflate_polyhedron/stretchy_mesh.py
for the vertex-loop format) are specified directly as vertex loops --
shared vertex ids ARE the adjacency, so a face pair sharing several edges
(which would force two RIGID flat faces into the same plane -- see
utils/inflate_polyhedron/stretchy_mesh.py's module docstring) needs no special
casing.

Every net is always LOADED at its own base (level 0) resolution -- even a
legacy fabric-subdivided file (one carrying baked-in "coarse_faces", see
utils/subdivisions/mesh_subdivide.load_fabric_spec and
generate_subdivided_stretchy_nets.py) starts from ITS OWN coarse_faces
rather than its pre-baked fine mesh. The "Subdivide" button (see
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
3. At ANY level, the "Pressure" spinner + "Inflate" button apply ONE
   relaxation pass (stretchy_mesh.relax_once) at a user-chosen, constant
   inflation pressure, continuing from wherever the mesh currently is --
   so repeated clicks let you watch/steer the shape settle incrementally.
   This pressure has NO target to converge to -- genuinely more pressure
   asks for genuinely more stretch, with no built-in ceiling (see
   stretchy_mesh._relax_residual's docstring).
   - The radio buttons control how much work each "Inflate" click does:
     either a capped number of solver steps (relax_once's `max_nfev`, the
     closest thing scipy's trust-region solver exposes to "N steps" --
     there's no cleaner "run exactly N iterations" knob), or an uncapped
     run to the solver's own convergence tolerance (CONVERGENCE_GTOL --
     see stretchy_mesh.py's own comment: some meshes visibly settle long
     before scipy's own optimality measure satisfies a strict tolerance,
     so this is deliberately looser than it might seem it needs to be).
   - "Save" writes the current vertex positions (plus iteration count,
     pressure, and stretch stats) and a PNG of the current view to
     data/output/Save/, both named from the source net's filename plus a
     timestamp.
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import glob
import json
import os
import queue
import itertools
import threading
import time
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

from common.paths import STRETCHY_NETS_DIR, SAVE_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS, DISABLED_SUFFIX
from ui.cullable_face import _CullableFace
from utils.inflate_polyhedron.stretchy_mesh import (
    load_stretchy_mesh, solve_wireframe, relax_once, per_face_volumes, is_orientation_consistent,
    mesh_to_polyhedron, mesh_edges, EDGE_LENGTH, PLANARITY_WEIGHT, CONVERGENCE_GTOL,
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

# A fabric-subdivided net's fine mesh edges are drawn thin/faint so the
# subdivision reads as texture rather than a bold wireframe competing
# with the per-coarse-face coloring -- see load_fabric_spec.
SUBDIVISION_EDGE_ALPHA = 0.35
SUBDIVISION_EDGE_WIDTH = 0.5

# Pressure spinner bounds: relax_once's pressure has no fixed target to
# converge to (see stretchy_mesh._relax_residual's docstring -- it uses a
# PER-FACE `pressure * exp(-v_f / reference_volume)`, not _inflate's
# target-based term), so unlike an automatic ramp's weights, there's no
# natural "final" value to anchor the default to -- and the "right" amount
# of pressure now also depends on the current subdivision level (see
# mesh_levels.py), not just which net is loaded, since a finer mesh's
# reference_volume is recomputed fresh on every Subdivide click. Kept
# deliberately gentle (per explicit request) so a first Inflate click
# doesn't overshoot before the user has a chance to watch it settle
# incrementally; MAX_PRESSURE=60 is slider headroom, not a "sane" ceiling.
DEFAULT_PRESSURE = 3.0
MAX_PRESSURE = 60.0
PRESSURE_INCREMENT = 0.5

DEFAULT_STEPS = 10

# on_inflate_clicked runs relax_once in a growing sequence of chunks
# (5, 10, 20, ...) instead of one big max_nfev call, so the iteration
# counter/plot update incrementally instead of jumping straight from the
# start count to the end one. Doubling (rather than a small fixed chunk)
# matters: relax_once's residual wrapper checked, EACH chunk is a fresh
# least_squares call with no memory of the previous one's shrunk
# trust-region radius, so a chunk size that's too small (measured: 1-5 on
# a 330-variable mesh) can get stuck re-exploring the same neighborhood
# forever without ever reaching real convergence, even after hundreds of
# total steps. Starting small keeps early feedback frequent while step
# counts are cheap, then growing the chunk lets later chunks actually be
# large enough to finish the job -- measured on a 330-variable subdivided
# cube mesh: chunks of 5/10/20 (31 total steps) converged in ~2.3s, while
# giving 3 live updates instead of 1.
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

        # ---- Net selection ----
        net_frame = ttk.LabelFrame(root, text="Net", padding=12)
        net_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(14, 8))

        picker_row = ttk.Frame(net_frame)
        picker_row.pack(fill=tk.X)
        ttk.Label(picker_row, text="Choose a net:").pack(side=tk.LEFT, padx=(0, 8))
        self.combo = ttk.Combobox(picker_row, state="readonly", width=30)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        self.save_button = ttk.Button(picker_row, text="Save", command=self.on_save_clicked)
        self.save_button.pack(side=tk.LEFT, padx=(12, 0))

        self.show_axes_var = tk.BooleanVar(value=False)
        self.axes_check = ttk.Checkbutton(picker_row, text="Show Axes",
                                           variable=self.show_axes_var,
                                           command=self.on_toggle_axes)
        self.axes_check.pack(side=tk.RIGHT, padx=(0, 12))

        status_row = ttk.Frame(net_frame)
        status_row.pack(fill=tk.X, pady=(10, 0))
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=160)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(status_row, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # ---- Subdivision: nested-level mesh refinement (level 0 is the
        # net's own base faces; each press adds one level, up to
        # MAX_LEVEL -- see mesh_levels' docstring). ----
        subdivide_frame = ttk.LabelFrame(root, text="Subdivide", padding=12)
        subdivide_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
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
        ttk.Label(pressure_row, text="Pressure:").pack(side=tk.LEFT, padx=(0, 4))
        self.pressure_var = tk.DoubleVar(value=DEFAULT_PRESSURE)
        # A "converged" result is only converged AT this pressure -- if the
        # user changes it, the gate on re-clicking Inflate (see
        # _update_inflate_button_state) needs to lift, since the new
        # pressure hasn't actually been tried yet.
        self.pressure_var.trace_add("write", self._on_pressure_changed)
        self.pressure_spin = ttk.Spinbox(pressure_row, from_=0.0, to=MAX_PRESSURE,
                                          increment=PRESSURE_INCREMENT, width=6,
                                          textvariable=self.pressure_var, format="%.1f")
        self.pressure_spin.pack(side=tk.LEFT)

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

        # ---- Target faces (left) + wireframe result (right) ----
        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))
        self.fig = plt.figure(figsize=(11, 5.5))
        self.ax2d = self.fig.add_subplot(1, 2, 1)
        self.ax3d = self.fig.add_subplot(1, 2, 2, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.fig, master=view_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Vertex markers are only culled/positioned correctly for whatever
        # orientation was current the last time draw() ran (see
        # _draw_wireframe_result's docstring) -- mplot3d's own interactive
        # rotation changes elev/azim continuously without ever calling our
        # draw() again, so hide them for the DURATION of a drag rather than
        # show stale, wrongly-culled markers mid-rotation; they reappear,
        # freshly culled for the new angle, on mouse release.
        self._dragging_3d = False
        self.vertex_scatter = None
        self.canvas.mpl_connect("button_press_event", self._on_3d_drag_start)
        self.canvas.mpl_connect("button_release_event", self._on_3d_drag_end)

        self.faces = None
        self.base_faces = None
        self.face_of_fine = None
        self.subdivision_level = 0
        self.edge_length = None
        self.target_layout = None
        self.positions = None
        self.iteration_count = 0
        self.last_stats = {}
        self.stop_event = None
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

    # ---- theme / axes visibility ----

    def _style_3d_axis(self, ax, theme):
        ax.title.set_color(theme["fg"])
        if self.show_axes_var.get():
            ax.set_axis_on()
            for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
                axis.pane.set_facecolor(theme["bg"])
                axis.pane.set_edgecolor(theme["fg"])
                axis.line.set_color(theme["fg"])
                axis.label.set_color(theme["fg"])
                axis._axinfo["grid"]["color"] = theme["grid"]
            ax.tick_params(colors=theme["fg"])
        else:
            ax.set_axis_off()

    def _style_2d_axis(self, ax, theme):
        ax.title.set_color(theme["fg"])
        if self.show_axes_var.get():
            ax.set_axis_on()
            for spine in ax.spines.values():
                spine.set_color(theme["fg"])
            ax.tick_params(colors=theme["fg"])
            ax.grid(True, color=theme["fg"], alpha=theme["grid"][3])
        else:
            ax.set_axis_off()

    def _apply_plot_theme(self):
        """Recolor the figure/axes chrome to match the (fixed, dark-only)
        plot theme and the "Show Axes" toggle -- ax.cla() (called every
        draw()) resets all of this to matplotlib's defaults, so it has to
        be re-applied on every redraw, not just on toggle. Returns the
        theme dict so draw() can reuse its colors."""
        theme = PLOT_THEME
        self.fig.patch.set_facecolor(theme["bg"])
        self.ax2d.set_facecolor(theme["bg"])
        self.ax3d.set_facecolor(theme["bg"])
        self._style_2d_axis(self.ax2d, theme)
        self._style_3d_axis(self.ax3d, theme)
        return theme

    def _refresh_plot(self):
        if self.positions is not None:
            self.draw()
        else:
            self._apply_plot_theme()
            self.canvas.draw_idle()

    def on_toggle_axes(self):
        self._refresh_plot()

    def _on_3d_drag_start(self, event):
        """mplot3d's own left-click-drag rotation starts here -- hide the
        vertex-marker scatter for the duration (see its own comment in
        __init__ for why), leaving the (live-culled) faces/edges alone."""
        if event.inaxes is not self.ax3d or event.button != 1:
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
        self.positions = None
        self.reference_volume = None
        self.stop_event = None
        self._update_subdivide_button_state()
        self._run_background(
            _solve_level0, (path, self.base_faces, legacy_coarse_faces is not None, CACHE_DIR),
            self._on_loaded, "Loading precomputed starting shape...")

    def _on_loaded(self, payload):
        positions, stats, cached_name = payload
        self.positions = positions
        # Fixed until the next subdivide or net load (see relax_once's and
        # _relax_residual's docstrings on reference_volume): one entry
        # PER FACE, each face's own starting volume contribution, so
        # _relax_residual's per-face pressure term means roughly the same
        # thing on every face of the CURRENT mesh, whether it's a small
        # tetrahedron or a large dodecahedron -- left unnormalized, the
        # SAME pressure value can be ~780x too weak to move a
        # dodecahedron's faces yet already excessive for a cube's, purely
        # because of their very different enclosed volumes at unit edge
        # length, nothing to do with the pressure dial itself.
        self.reference_volume = per_face_volumes(positions, self.faces)
        self.last_stats = {"max_stretch_pct": stats["max_stretch_pct"],
                            "rms_stretch_pct": stats["rms_stretch_pct"],
                            "optimality": None, "converged": None}
        self._update_inflate_button_state()
        self._set_status(
            f"Loaded {cached_name or self.mesh_name}: starting shape ready (edges stretched up "
            f"to {stats['max_stretch_pct']:.2f}%, RMS {stats['rms_stretch_pct']:.2f}%). "
            f"Press Inflate to relax/inflate, or Subdivide to refine the mesh.", "info")
        self.refresh_net_list()  # the net just loaded may have just gained a cache entry
        self.draw()

    # ---- subdivide ----

    def _update_subdivide_button_state(self):
        can_subdivide = self.positions is not None and self.subdivision_level < MAX_LEVEL
        self.subdivide_button.state(["!disabled"] if can_subdivide else ["disabled"])
        self.subdivide_level_var.set(f"Level: {self.subdivision_level}")

    def on_subdivide_clicked(self):
        if self.positions is None or self.subdivision_level >= MAX_LEVEL:
            return
        self.faces, self.positions, self.edge_length, self.face_of_fine = subdivide_once(
            self.faces, self.positions, self.edge_length, self.face_of_fine,
            self.subdivision_level)
        self.subdivision_level += 1
        # The face set just changed entirely (more, smaller faces) -- both
        # of these must be recomputed fresh for the NEW mesh, same as a
        # brand new net load (see _on_loaded).
        self.reference_volume = per_face_volumes(self.positions, self.faces)
        self.last_stats = self._compute_stretch_stats()
        self._update_subdivide_button_state()
        self._update_inflate_button_state()  # a fresh subdivision hasn't converged yet
        self._set_status(
            f"Subdivided to level {self.subdivision_level} ({len(self.faces)} faces, "
            f"{len(self.positions)} vertices, edges stretched up to "
            f"{self.last_stats['max_stretch_pct']:.2f}%). Press Inflate to relax/inflate "
            f"further.", "info")
        self.draw()

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
        burn time without moving anything: a fresh least_squares call
        from an already-converged point has no memory of how far its
        trust region had already shrunk, so it doesn't just no-op, it
        can genuinely wander for a while re-discovering the same spot
        (measured: 10 wasted steps that moved nothing). Re-armed by
        _on_pressure_changed, a new net load, or a Stop (which leaves
        converged=False since it didn't run to completion)."""
        if self.last_stats.get("converged"):
            self.inflate_button.state(["disabled"])
        else:
            self.inflate_button.state(["!disabled"])

    def _on_pressure_changed(self, *_args):
        # A "converged" verdict only applies to the pressure it was
        # reached at -- changing it means the new pressure hasn't
        # actually been tried, so the gate must lift (back to "unknown",
        # not "converged").
        if self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_inflate_button_state()

    def on_inflate_clicked(self):
        if self.positions is None or self.last_stats.get("converged"):
            return
        pressure = self.pressure_var.get()
        target_steps = max(1, self.steps_var.get()) if self.iterate_mode_var.get() == "steps" else None
        status = (f"Inflating at pressure {pressure:.1f} for {target_steps} steps..."
                   if target_steps is not None else
                   f"Inflating at pressure {pressure:.1f} until convergence...")
        self.stop_event = threading.Event()
        self._set_controls_enabled(False)
        self.stop_button.state(["!disabled"])
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        self._set_status(status, "info")
        self._run_inflate_stream(pressure, target_steps, self.stop_event)

    def on_stop_clicked(self):
        if self.stop_event is not None:
            self.stop_event.set()
            self.stop_button.state(["disabled"])  # one request is enough; avoid repeat clicks
            self._set_status("Stopping...", "warn")

    def _run_inflate_stream(self, pressure, target_steps, stop_event):
        """Runs relax_once in a growing sequence of chunks (see
        INFLATE_CHUNK_START's comment for why growing rather than one
        call or a small fixed size) in a background thread, pushing a
        "progress" message to the queue after every chunk so the main
        thread can update the iteration counter/plot incrementally
        instead of jumping straight from the start count to the end one.
        Tk isn't thread-safe, so the worker only ever pushes to the
        queue; the main thread (via the scheduled poll below) is the
        only one that touches Tk widgets.

        Each chunk is checked for orientation consistency (see
        is_orientation_consistent's docstring) before being accepted: a
        big enough single relax_once call CAN fold the mesh through
        itself -- verified empirically even on a plain cube at
        pressure=30 with a single 5-evaluation chunk, which "converges"
        to a deceptively tiny reported edge stretch while actually
        self-intersecting, not genuinely inflated -- and relax_once has
        no restart/retry logic of its own to catch that (by design, see
        its docstring: it's meant for small incremental nudges from an
        already-good point). A chunk that tangles the mesh is REJECTED
        (positions not updated) and retried at half the size instead;
        once a size is found to tangle, `ceiling` permanently caps how
        far this click's chunk is ever allowed to grow back to again, so
        the loop can't oscillate forever between "too small to move
        anything" and "big enough to tangle" -- it converges on some
        safe operating size and keeps making progress at that size
        instead. If even a single-evaluation chunk tangles the mesh (the
        smallest step possible), inflation is stopped there and reported
        as unsafe rather than looping forever or accepting a corrupted
        result."""
        q = queue.Queue()
        faces, edge_length = self.faces, self.edge_length
        start_positions = self.positions
        reference_volume = self.reference_volume

        def worker():
            positions = start_positions
            completed = 0
            chunk = INFLATE_CHUNK_START
            ceiling = None  # once set, chunk is never allowed to grow past this again
            try:
                while True:
                    this_chunk = max(1, chunk if target_steps is None
                                      else min(chunk, target_steps - completed))
                    result = relax_once(positions, faces, edge_length, pressure,
                                         PLANARITY_WEIGHT, max_nfev=this_chunk, stop_event=stop_event,
                                         reference_volume=reference_volume)
                    trial_positions, nfev, max_stretch, rms_stretch, optimality, converged = result
                    stopped = stop_event is not None and stop_event.is_set()

                    if not stopped and not is_orientation_consistent(trial_positions, faces):
                        if this_chunk <= 1:
                            q.put(("tangled", None))
                            return
                        ceiling = max(1, this_chunk - 1)
                        chunk = max(1, this_chunk // 2)
                        continue  # reject this chunk entirely; positions unchanged, no progress counted

                    positions = trial_positions
                    completed += nfev
                    q.put(("progress", result))
                    reached_target = target_steps is not None and completed >= target_steps
                    safety_cap_hit = target_steps is None and completed >= INFLATE_SAFETY_STEP_CAP
                    if converged or stopped or reached_target or safety_cap_hit:
                        break
                    chunk = min(chunk * 2, INFLATE_CHUNK_MAX if ceiling is None else ceiling)
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
                    elif kind == "tangled":
                        self.progress.stop()
                        self.progress.pack_forget()
                        self._set_controls_enabled(True)
                        self._set_status(
                            "Stopped: this pressure folds the mesh through itself even at the "
                            "smallest possible step. Lower the pressure and try again.", "error")
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
        self._set_status(f"Inflating... {self.iteration_count} steps so far "
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
        if was_stopped:
            self._set_status(
                f"Stopped ({self.iteration_count} total steps): edges stretched up to "
                f"{max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%).", "warn")
        elif converged:
            self._set_status(
                f"Converged after {self.iteration_count} total steps: edges stretched up to "
                f"{max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%).", "success")
        else:
            self._set_status(
                f"Inflated ({self.iteration_count} total steps, step cap reached): edges "
                f"stretched up to {max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%).",
                "info")

    # ---- background worker (used by the initial cache load) ----

    def _set_controls_enabled(self, enabled):
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (self.combo, self.pressure_spin,
                       self.steps_radio, self.convergence_radio, self.save_button):
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

    def _run_background(self, fn, args, on_done, status_text):
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
        self._set_status(status_text, "info")
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

    # ---- save ----

    def on_save_clicked(self):
        if self.positions is None:
            return
        os.makedirs(SAVE_DIR, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(self.current_path))[0]
        stem = f"{base_name}_{time.strftime('%Y%m%d_%H%M%S')}"
        json_path = os.path.join(SAVE_DIR, f"{stem}.json")
        png_path = os.path.join(SAVE_DIR, f"{stem}.png")

        data = {
            "name": self.mesh_name,
            "source": os.path.basename(self.current_path),
            "iteration": self.iteration_count,
            "pressure": self.pressure_var.get(),
            "stats": self.last_stats,
            "faces": [list(f) for f in self.faces],
            "positions": {str(v): [float(c) for c in p] for v, p in self.positions.items()},
        }
        if self.subdivision_level > 0:
            data["coarse_faces"] = [list(f) for f in self.base_faces]
            data["resolution"] = self.subdivision_level
            data["face_of_fine"] = list(self.face_of_fine)
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

        self.fig.savefig(png_path, dpi=150)
        self._set_status(f"Saved {os.path.basename(json_path)} and "
                          f"{os.path.basename(png_path)} to Save/.", "success")

    # ---- drawing ----

    def _draw_box_wireframe(self, xlim, ylim, zlim, color):
        """See polyhedron_unfolder's identical helper for why this is
        needed instead of relying on mplot3d's default pane borders."""
        corners = list(itertools.product(xlim, ylim, zlim))
        edges = [(a, b) for i, a in enumerate(corners) for b in corners[i + 1:]
                  if sum(p != q for p, q in zip(a, b)) == 1]
        for edge in edges:
            self.ax3d.add_collection3d(Line3DCollection([edge], colors=color, linewidths=0.8))

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
        self.ax2d.set_title("Target faces (net)")

    def _draw_wireframe_result(self, theme):
        """The actual current state: possibly non-planar faces (drawn
        opaque) plus the raw vertex/edge wireframe on top, since a "face"
        here is just a rendering convenience -- the thing actually being
        relaxed is the vertex positions and edge lengths.

        Once subdivided (self.subdivision_level > 0), colors every fine
        triangle by its ORIGINAL base face (self.face_of_fine, indexing
        the same per-base-face self.colors the left panel uses) so the
        base faces stay visually distinct as color blocks, with the fine
        mesh edges thin and faint (see SUBDIVISION_EDGE_ALPHA/WIDTH) so
        the subdivision reads as texture rather than a bold wireframe, and
        no per-vertex scatter dots (there can be hundreds of fine
        vertices).

        Wraps the current (positions, faces) into a Polyhedron -- its
        .edges gives the wireframe segments for the (rarer) open-mesh
        fallback below (positions re-indexed to Polyhedron's own dense
        0..N-1 space, so `polyhedron.vertices[i]` is the position for
        edge endpoint `i` directly, no dict lookup needed), and
        .is_closed() reports in the title whether the current shape is a
        genuinely closed solid or still an open mesh -- and, more
        importantly here, gates whether _CullableFace's exact backface
        culling applies (see its own docstring: only valid for a closed
        CONVEX solid). When closed, each face is drawn as a _CullableFace
        carrying its OWN boundary edges, so a face's wireframe lines
        disappear together with the face itself once it's facing away
        from the camera -- drawing every edge as one separate, undivided
        Line3DCollection (the open-mesh fallback below) has no per-face
        depth information at all, so back-face lines would otherwise
        render right through the opaque near faces regardless of view
        angle."""
        self.ax3d.cla()
        self._style_3d_axis(self.ax3d, theme)

        fabric = self.subdivision_level > 0
        face_colors = ([self.colors[c % len(self.colors)] for c in self.face_of_fine]
                        if fabric else self.colors)

        polyhedron = mesh_to_polyhedron(self.positions, self.faces)
        closed = polyhedron.is_closed()
        edge_width = SUBDIVISION_EDGE_WIDTH if fabric else 1.6

        all_pts = np.array(list(self.positions.values()))
        # Which vertices belong to at least one face CURRENTLY facing the
        # camera -- a vertex with every adjacent face facing away is
        # purely on the far side and should be hidden from the scatter
        # markers below, the same way _CullableFace already hides a
        # fully-backfacing face's own fill and edges. A silhouette vertex
        # (some faces front, some back) stays visible, correctly, since
        # it's genuinely on the boundary of what's visible. Unlike
        # _CullableFace's own do_3d_projection (called by mplot3d on
        # every frame, including mid-drag), this is computed once here at
        # redraw time -- ax3d.scatter's marker collection has no
        # per-point 3D visibility hook to recompute it live during an
        # interactive rotation, only when this app's own draw() next runs.
        front_facing_vertices = set() if closed else None
        if closed:
            # Same view-direction math as _CullableFace.do_3d_projection
            # (see its docstring) -- duplicated rather than imported since
            # that's a private detail of an untouchable file, not
            # something it exposes for reuse.
            elev, azim = np.radians(self.ax3d.elev), np.radians(self.ax3d.azim)
            view_dir = np.array([np.cos(elev) * np.cos(azim),
                                  np.cos(elev) * np.sin(azim),
                                  np.sin(elev)])
        for face_index, (face, color) in enumerate(zip(self.faces, face_colors)):
            pts = np.array([self.positions[v] for v in face])
            if closed:
                normal = polyhedron.face_normal(face_index)
                self.ax3d.add_collection3d(_CullableFace(
                    [pts], normal, base_alpha=1.0,
                    facecolor=color, edgecolor=theme["fg"], linewidths=edge_width))
                if np.dot(normal, view_dir) > 0:
                    front_facing_vertices.update(face)
            else:
                self.ax3d.add_collection3d(
                    Poly3DCollection([pts], facecolor=color, edgecolor="none", alpha=1.0))

        if not closed:
            # No exact culling is possible without closed convexity (see
            # _CullableFace's docstring) -- fall back to one plain,
            # undivided wireframe overlay, same as before this fix.
            edge_segments = [(polyhedron.vertices[a], polyhedron.vertices[b])
                              for a, b in polyhedron.edges]
            self.ax3d.add_collection3d(Line3DCollection(
                edge_segments, colors=theme["fg"], linewidths=edge_width,
                alpha=SUBDIVISION_EDGE_ALPHA if fabric else 1.0))
        if not fabric:
            vertex_ids = (list(self.positions) if front_facing_vertices is None
                          else [v for v in self.positions if v in front_facing_vertices])
            vis_pts = np.array([self.positions[v] for v in vertex_ids])
            self.vertex_scatter = self.ax3d.scatter(
                vis_pts[:, 0], vis_pts[:, 1], vis_pts[:, 2],
                color=theme["fg"], s=18, depthshade=False)
            self.vertex_scatter.set_visible(not self._dragging_3d)
        else:
            self.vertex_scatter = None

        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        center = (lo + hi) / 2
        half = (hi - lo).max() / 2 * 1.2 + 1e-6
        xlim = (center[0] - half, center[0] + half)
        ylim = (center[1] - half, center[1] + half)
        zlim = (center[2] - half, center[2] + half)
        self.ax3d.set_xlim(*xlim)
        self.ax3d.set_ylim(*ylim)
        self.ax3d.set_zlim(*zlim)
        self.ax3d.set_box_aspect([1, 1, 1])
        if self.show_axes_var.get():
            self._draw_box_wireframe(xlim, ylim, zlim, theme["fg"])
        closed_note = "closed" if closed else "open"
        self.ax3d.set_title(f"Wireframe result (fabric, subdivided, {closed_note})" if fabric else
                             f"Wireframe result ({closed_note})")

    def draw(self):
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_wireframe_result(theme)
        # fig.text accumulates across redraws unless the previous one is
        # removed first -- this is the "Iteration: N" line shown under the
        # image, embedded directly in the figure (rather than a separate
        # Tk label) so it's also captured by on_save_clicked's savefig.
        for txt in list(self.fig.texts):
            txt.remove()
        note = ""
        if self.last_stats:
            optimality = self.last_stats.get("optimality")
            converged = self.last_stats.get("converged")
            if optimality is not None:
                conv_str = "converged" if converged else "not converged"
                opt_note = f"optimality {optimality:.2e} vs. tol {CONVERGENCE_GTOL:.0e} ({conv_str})"
            else:
                opt_note = "optimality n/a"
            note = (f"   |   max stretch {self.last_stats['max_stretch_pct']:.2f}%, "
                    f"RMS {self.last_stats['rms_stretch_pct']:.2f}%   |   {opt_note}")
        self.fig.text(0.5, 0.01, f"Iteration: {self.iteration_count}{note}",
                       ha="center", va="bottom", color=theme["fg"], fontsize=10)
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    InflatePolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
