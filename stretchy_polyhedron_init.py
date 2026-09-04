"""
Stretchy polyhedron viewer -- interactive fabric relaxation.

    python stretchy_polyhedron_init.py

Nets here (stretchy_nets/*.json, see net_fold_utils/stretchy_mesh.py for
the vertex-loop format) are specified directly as vertex loops -- shared
vertex ids ARE the adjacency, so a face pair sharing several edges (which
would force two RIGID flat faces into the same plane -- see
net_fold_utils/stretchy_mesh.py's module docstring) needs no special
casing. A fabric-subdivided net (see net_fold_utils/mesh_subdivide.py and
tools/generate_subdivided_stretchy_nets.py, e.g. stretchy_nets/cube_res4.json)
additionally carries its original coarse polygons + a fine-triangle ->
coarse-face mapping, used here to color every fine triangle by its
original face and to show the coarse net (with a faint subdivision
overlay) in the left "Target faces" panel.

This app's job is ONLY step 3 below -- interactive, user-driven
inflation/relaxation -- because step 1 (coarse solve) and step 2
(subdivide) are already reliable and fast on their own, and are
precomputed/cached ahead of time via net_fold_utils/stretchy_cache.py
(same cache build_stretchy_cache.py warms):

1. The COARSE net is solved with stretchy_mesh.solve_wireframe -- its
   random-restart-plus-inflation-ramp search is exactly what makes this
   step reliable (it doesn't hang: a coarse net has few enough faces that
   restarting from a different random start when one doesn't inflate
   cleanly is cheap and effective -- see solve_wireframe's docstring).
2. For a fabric-subdivided net (net_fold_utils/mesh_subdivide.py,
   tools/generate_subdivided_stretchy_nets.py, e.g.
   stretchy_nets/cube_res4.json), the fine mesh is then DRAPED over that
   already-solved coarse shape (mesh_subdivide.solve_fabric_mesh) --
   giving every fine vertex a starting position that's already properly
   oriented and already roughly the right shape, then one light
   edge-length relaxation pass to iron out any small discrepancies.
   (Applying pressure directly to a raw random start, skipping 1 and 2,
   was tried first -- it can hang for a very long time or never converge,
   the same failure _inflate's docstring documents for a "cold" random
   point cloud. Draping over an already-solved coarse shape sidesteps
   that entirely.)
3. THIS app loads that precomputed result (net_fold_utils/stretchy_cache.py's
   load_with_cache -- instant on a cache hit, solved fresh and cached if
   not) as iteration 0, then lets the user push further from there:
   - The "Pressure" spinner + "Inflate" button apply ONE relaxation pass
     (stretchy_mesh.relax_once) at a user-chosen, constant inflation
     pressure, continuing from wherever the mesh currently is (not from
     scratch) -- so repeated clicks let you watch/steer the shape settle
     incrementally, rather than the program silently retrying different
     random starts under the hood.
   - The radio buttons control how much work each "Inflate" click does:
     either a capped number of solver steps (relax_once's `max_nfev`, the
     closest thing scipy's trust-region solver exposes to "N steps" --
     there's no cleaner "run exactly N iterations" knob), or an uncapped
     run to the solver's own convergence tolerance.
   - "Save" writes the current vertex positions (plus iteration count,
     pressure, and stretch stats) and a PNG of the current view to Save/,
     both named from the source net's filename plus a timestamp.
"""
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

from net_fold_utils.stretchy_mesh import (
    load_stretchy_mesh, mesh_edges, relax_once,
    _sphere_bound_volume, EDGE_LENGTH, PLANARITY_WEIGHT, CONVERGENCE_GTOL,
)
from net_fold_utils.stretchy_cache import load_with_cache, is_cached
from net_fold_utils.mesh_subdivide import load_fabric_spec, subdivide_mesh
from net_fold_utils.stretchy_net_layout import build_stretchy_net_layout
from subdivision_utils import subdivide as subdivide_polygon
from polygon_fold_app import STATUS_COLORS, PLOT_THEME, FACE_COLORS, DISABLED_SUFFIX

STRETCHY_NETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stretchy_nets")
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Save")
DEFAULT_NET_BASENAME = "cube_res4"

# A fabric-subdivided net's fine mesh edges are drawn thin/faint so the
# subdivision reads as texture rather than a bold wireframe competing
# with the per-coarse-face coloring -- see load_fabric_spec.
SUBDIVISION_EDGE_ALPHA = 0.35
SUBDIVISION_EDGE_WIDTH = 0.5

# Pressure spinner bounds: 3.0 was the top (final, most-used) rung of the
# old automatic INFLATION_WEIGHTS ramp in stretchy_mesh._inflate, so it's
# the natural default here; the max gives headroom well beyond that for
# experimentation without being unbounded.
DEFAULT_PRESSURE = 3.0
MAX_PRESSURE = 10.0
PRESSURE_INCREMENT = 0.1

# Each relax_once "step" (solver function evaluation) costs roughly 2s on
# a resolution-4 subdivided cube (98 vertices) -- scipy's numerical
# Jacobian for the pressure/volume residual needs close to one full
# n_vars-sized finite-difference sweep per step, regardless of pressure
# magnitude or how good the starting shape already is (measured: ~2-2.5s
# per reported nfev whether pressure is 0.1 or 3.0). Default kept low so
# a first "Inflate" click is a ~15-25s wait, not ~70-125s; raise it once
# you have a feel for the pace.
DEFAULT_STEPS = 10


class StretchyPolyhedronApp:
    def __init__(self, root):
        self.root = root
        root.title("Stretchy Polyhedron Init")
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

        self.theme_button = ttk.Button(picker_row, text="Light Mode", width=10,
                                        command=self.on_toggle_theme)
        self.theme_button.pack(side=tk.RIGHT)

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

        # ---- Inflation: everything about running relax_once lives here,
        # in the order it's used -- pick a pressure, pick how much work to
        # do, then Inflate (or Stop one that's already running). ----
        inflate_frame = ttk.LabelFrame(root, text="Inflate", padding=12)
        inflate_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))

        pressure_row = ttk.Frame(inflate_frame)
        pressure_row.pack(fill=tk.X)
        ttk.Label(pressure_row, text="Pressure:").pack(side=tk.LEFT, padx=(0, 4))
        self.pressure_var = tk.DoubleVar(value=DEFAULT_PRESSURE)
        self.pressure_spin = ttk.Spinbox(pressure_row, from_=0.0, to=MAX_PRESSURE,
                                          increment=PRESSURE_INCREMENT, width=6,
                                          textvariable=self.pressure_var, format="%.1f")
        self.pressure_spin.pack(side=tk.LEFT)

        mode_row = ttk.Frame(inflate_frame)
        mode_row.pack(fill=tk.X, pady=(8, 0))
        self.iterate_mode_var = tk.StringVar(value="steps")
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

        self.faces = None
        self.coarse_faces = None
        self.face_of_fine = None
        self.fabric_resolution = None
        self.edge_length = None
        self.volume_target = 0.0
        self.target_layout = None
        self.positions = None
        self.iteration_count = 0
        self.last_stats = {}
        self.stop_event = None
        self.current_path = None
        self.current_label = None
        self.label_to_path = {}
        self.is_dark = True
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
        """Recolor the figure/axes chrome to match the current sv_ttk theme
        and the "Show Axes" toggle -- ax.cla() (called every draw()) resets
        all of this to matplotlib's defaults, so it has to be re-applied on
        every redraw, not just on toggle. Returns the active theme dict so
        draw() can reuse its colors."""
        theme = PLOT_THEME["dark" if self.is_dark else "light"]
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

    def on_toggle_theme(self):
        sv_ttk.toggle_theme()
        self.is_dark = sv_ttk.get_theme() == "dark"
        self.theme_button.configure(text="Light Mode" if self.is_dark else "Dark Mode")
        self._refresh_plot()

    def on_toggle_axes(self):
        self._refresh_plot()

    # ---- net picker ----

    def refresh_net_list(self, keep_selection=True):
        """Rescan stretchy_nets/ and rebuild the dropdown -- a net with no
        matching stretchy_cache/*.json gets a "(not computed)" suffix
        (purely informational: selecting it still works, it just means
        the precomputed coarse-solve-then-drape starting point isn't
        ready yet, so on_select_net's background load will solve it
        fresh instead of an instant cache read -- see module docstring)."""
        paths = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json")))
        self.label_to_path = {}
        for path in paths:
            base_label = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            label = base_label if is_cached(path) else base_label + DISABLED_SUFFIX
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
            # Default to DEFAULT_NET_BASENAME (cube_res4.json) if present,
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
            self.faces, self.mesh_name = load_stretchy_mesh(path)
        except ValueError as e:
            self._set_status(str(e), "error")
            self.faces = None
            return

        # A fabric-subdivided net (see net_fold_utils/mesh_subdivide.py and
        # tools/generate_subdivided_stretchy_nets.py) carries its original
        # coarse polygons + a fine-triangle -> coarse-face mapping right in
        # the JSON -- used to color every fine triangle by its ORIGINAL
        # face, to show the coarse net (not hundreds of fine triangles) in
        # the left panel, and to give solving the true per-edge rest
        # lengths instead of a uniform one (see mesh_subdivide.py's
        # docstring for why that distinction matters). An ordinary net has
        # none of this and renders/solves exactly as before.
        self.coarse_faces, self.fabric_resolution, self.face_of_fine = load_fabric_spec(path)
        if self.coarse_faces is not None:
            _, _, self.edge_length, _ = subdivide_mesh(self.coarse_faces, self.fabric_resolution)
            self.volume_target = _sphere_bound_volume(self.coarse_faces, EDGE_LENGTH)
            color_count = len(self.coarse_faces)
        else:
            self.edge_length = EDGE_LENGTH
            self.volume_target = _sphere_bound_volume(self.faces, EDGE_LENGTH)
            color_count = len(self.faces)
        self.colors = [FACE_COLORS[i % len(FACE_COLORS)] for i in range(color_count)]

        # Precomputed once per net selection (see build_stretchy_net_layout's
        # docstring): a breadth-first spanning tree over shared edges,
        # attaching each face to whichever neighbor discovers it first --
        # the same idea net_fold_utils/net_layout.py uses for the rigid
        # pipeline. _draw_target_faces just reuses this on every redraw
        # rather than recomputing the BFS every time.
        self.target_layout = build_stretchy_net_layout(self.coarse_faces
                                                         if self.coarse_faces is not None
                                                         else self.faces)

        self.current_path = path
        self.iteration_count = 0
        self.last_stats = {}
        self.positions = None
        self.stop_event = None
        # load_with_cache is the precomputed "step 1 + step 2" starting
        # point (see module docstring): the coarse net solved with
        # solve_wireframe's reliable random-restart search, then (for a
        # fabric net) draped into the fine mesh -- instant on a cache hit,
        # solved fresh and cached if not (net_fold_utils/stretchy_cache.py).
        # This app's own "Inflate" loop never does any of that solving
        # itself; it only continues from here.
        self._run_background(
            load_with_cache, (path,),
            self._on_loaded, "Loading precomputed starting shape...")

    def _on_loaded(self, payload):
        _, positions, stats, name = payload
        self.positions = positions
        self.last_stats = {"max_stretch_pct": stats["max_stretch_pct"],
                            "rms_stretch_pct": stats["rms_stretch_pct"],
                            "optimality": None, "converged": None}
        self._set_status(
            f"Loaded {name}: precomputed starting shape ready (edges stretched up to "
            f"{stats['max_stretch_pct']:.2f}%, RMS {stats['rms_stretch_pct']:.2f}%). "
            f"Press Inflate to relax/inflate further.", "info")
        self.refresh_net_list()  # the net just loaded may have just gained a cache entry
        self.draw()

    # ---- inflate ----

    def _update_mode_state(self):
        self.steps_spin.state(["!disabled"] if self.iterate_mode_var.get() == "steps"
                               else ["disabled"])

    def on_inflate_clicked(self):
        if self.positions is None:
            return
        pressure = self.pressure_var.get()
        max_nfev = max(1, self.steps_var.get()) if self.iterate_mode_var.get() == "steps" else None
        status = (f"Inflating at pressure {pressure:.1f} for {max_nfev} steps..."
                   if max_nfev is not None else
                   f"Inflating at pressure {pressure:.1f} until convergence...")
        self.stop_event = threading.Event()
        self._run_background(
            relax_once,
            (self.positions, self.faces, self.edge_length, pressure,
             self.volume_target, PLANARITY_WEIGHT, max_nfev, self.stop_event),
            self._on_inflated, status)
        self.stop_button.state(["!disabled"])

    def on_stop_clicked(self):
        if self.stop_event is not None:
            self.stop_event.set()
            self.stop_button.state(["disabled"])  # one request is enough; avoid repeat clicks
            self._set_status("Stopping...", "warn")

    def _on_inflated(self, result):
        positions, nfev, max_stretch, rms_stretch, optimality, converged = result
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        self.positions = positions
        self.iteration_count += nfev
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged}
        if was_stopped:
            self._set_status(
                f"Stopped after +{nfev} steps ({self.iteration_count} total): edges stretched "
                f"up to {max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%).", "warn")
        else:
            reached = "converged" if converged else "step cap reached"
            self._set_status(
                f"Inflated (+{nfev} steps, {self.iteration_count} total, {reached}): edges "
                f"stretched up to {max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%).",
                "info")
        self.draw()

    # ---- background worker (shared by initial load + inflate) ----

    def _set_controls_enabled(self, enabled):
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (self.combo, self.inflate_button, self.pressure_spin,
                       self.steps_radio, self.convergence_radio, self.save_button):
            widget.state(state)
        if enabled:
            self._update_mode_state()  # respect the steps/convergence choice
            self.stop_button.state(["disabled"])
        else:
            self.steps_spin.state(["disabled"])
            # stop_button is armed separately by on_inflate_clicked (right
            # after this runs) -- other background jobs, like the initial
            # cache load, leave it disabled since there's nothing to
            # usefully interrupt there.

    def _run_background(self, fn, args, on_done, status_text):
        """Run fn(*args) in a background thread and call on_done(result)
        on the main thread once it finishes -- shared by the initial
        relaxation and every "Inflate" click, both of which can take a
        moment (see module docstring: no cache, no automatic search, so
        every one of these actually does the solve). Tk isn't
        thread-safe, so the worker only ever pushes to a queue; the main
        thread (via the scheduled poll below) is the only one that
        touches Tk widgets."""
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
        if self.coarse_faces is not None:
            data["coarse_faces"] = [list(f) for f in self.coarse_faces]
            data["resolution"] = self.fabric_resolution
            data["face_of_fine"] = list(self.face_of_fine)
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

        self.fig.savefig(png_path, dpi=150)
        self._set_status(f"Saved {os.path.basename(json_path)} and "
                          f"{os.path.basename(png_path)} to Save/.", "success")

    # ---- drawing ----

    def _draw_box_wireframe(self, xlim, ylim, zlim, color):
        """See polyhedral_net_app.py's identical helper for why this is
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

        For a fabric-subdivided net (self.coarse_faces set, see
        load_fabric_spec), shows the COARSE polygons here -- not the
        hundreds of individual fine triangles -- with a faint subdivision
        overlay at the resolution the net was actually generated at, as a
        2D preview of the mesh being solved."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        fabric = self.coarse_faces is not None
        faces = self.coarse_faces if fabric else self.faces
        all_pts = []
        for face_idx in sorted(self.target_layout):
            face = faces[face_idx]
            color = self.colors[face_idx % len(self.colors)]
            placed = self.target_layout[face_idx]
            self.ax2d.add_patch(Polygon(placed, closed=True, facecolor=color,
                                         edgecolor="k", alpha=0.9))
            if fabric:
                sub_points, sub_triangles = subdivide_polygon(
                    len(face), placed, self.fabric_resolution)
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
        translucent so the bend is visible) plus the raw vertex/edge
        wireframe on top, since a "face" here is just a rendering
        convenience -- the thing actually being relaxed is the vertex
        positions and edge lengths.

        For a fabric-subdivided net, colors every fine triangle by its
        ORIGINAL coarse face (self.face_of_fine, indexing the same
        per-coarse-face self.colors the left panel uses) so the coarse
        faces stay visually distinct as color blocks, with the fine mesh
        edges thin and faint (see SUBDIVISION_EDGE_ALPHA/WIDTH) so the
        subdivision reads as texture rather than a bold wireframe, and no
        per-vertex scatter dots (there can be hundreds of fine
        vertices)."""
        self.ax3d.cla()
        self._style_3d_axis(self.ax3d, theme)

        fabric = self.coarse_faces is not None
        face_colors = ([self.colors[c % len(self.colors)] for c in self.face_of_fine]
                        if fabric else self.colors)

        all_pts = np.array(list(self.positions.values()))
        for face, color in zip(self.faces, face_colors):
            pts = np.array([self.positions[v] for v in face])
            self.ax3d.add_collection3d(
                Poly3DCollection([pts], facecolor=color, edgecolor="none", alpha=0.55))

        edge_segments = [(self.positions[a], self.positions[b]) for a, b in mesh_edges(self.faces)]
        self.ax3d.add_collection3d(Line3DCollection(
            edge_segments, colors=theme["fg"],
            linewidths=SUBDIVISION_EDGE_WIDTH if fabric else 1.6,
            alpha=SUBDIVISION_EDGE_ALPHA if fabric else 1.0))
        if not fabric:
            self.ax3d.scatter(all_pts[:, 0], all_pts[:, 1], all_pts[:, 2],
                               color=theme["fg"], s=18, depthshade=False)

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
        self.ax3d.set_title("Wireframe result (fabric, subdivided)" if fabric else
                             "Wireframe result")

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
    StretchyPolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
