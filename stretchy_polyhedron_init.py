"""
Stretchy polyhedron viewer: a copy of polyhedral_net_app.py's side-by-side
layout, but for nets whose faces can't stay perfectly rigid and flat --
where closing the shape needs edges to change length a little and/or
faces to bend out of plane.

    python stretchy_polyhedron_init.py

polygon_fold_app.py / polyhedral_net_app.py's whole pipeline (see
polyhedron_spec.py, combinatorics.EdgeMap) assumes every face is a rigid
regular polygon and derives fold angles that bring RIGID faces together
exactly. That's provably impossible for some nets: if two flat faces
share more than one edge, the >=3 shared (non-collinear) points force
both faces into the SAME plane -- there's no dihedral fold left to make
them distinct faces of a solid. combinatorics.EdgeMap can't even
represent such a net (its face-adjacency graph is a plain networkx.Graph,
so a face pair sharing multiple edges collapses to one graph edge and
EdgeMap raises "duplicate edge in the edge list" -- see
tests/test_stretchy_mesh.py for exactly this, worked out for the example
net below).

Nets here (stretchy_nets/*.json, see net_fold_utils/stretchy_mesh.py for
the format) are instead specified directly as vertex loops -- shared
vertex ids ARE the adjacency, so a face pair sharing several edges needs
no special-casing. There's no flat-2D-net/fold-angle concept to derive at
all: stretchy_mesh.solve_wireframe() just finds SOME 3D position for
every vertex that keeps every edge close to unit length (a small
least-squares "spring relaxation", not a hinge-and-rotate fold), with no
constraint on face flatness -- letting edges stretch a little and faces
bend is exactly what makes an otherwise-impossible net like this
realizable. The left panel shows each face's undeformed regular-polygon
target shape for reference; the right panel shows the actual (generally
non-planar, edges not quite unit length) solved result.

Like polygon_fold_app.py / polyhedral_net_app.py, solving is cached
(net_fold_utils/stretchy_cache.py, in stretchy_cache/ next to
stretchy_nets/) so picking an already-solved net is a fast JSON read
instead of re-running the relaxation -- a bigger mesh (e.g. the
dodecahedron's 20 vertices / 30 edges) can take tens of seconds, see
solve_wireframe's docstring. "Compute All Wireframes" warms the cache for
every net at once (also usable standalone via build_stretchy_cache.py);
"Recompute Wireframe" deliberately bypasses the cache to show a
*different* one of the many valid embeddings the underdetermined system
admits, without overwriting the cached canonical one.
"""
import os
import glob
import itertools
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sv_ttk

from net_fold_utils.stretchy_mesh import load_stretchy_mesh, mesh_edges, solve_wireframe
from net_fold_utils.stretchy_cache import load_with_cache, is_cached, build_all
from net_fold_utils.polygon_geom import regular_polygon_vertices
from net_fold_utils.mesh_subdivide import load_fabric_spec
from subdivision_utils import subdivide as subdivide_polygon
from polygon_fold_app import STATUS_COLORS, PLOT_THEME, FACE_COLORS, DISABLED_SUFFIX
from tooltip import Tooltip

STRETCHY_NETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stretchy_nets")
COMPUTE_ALL_TOOLTIP = ("Solves the wireframe for every net that hasn't been computed "
                       "yet.\nThis may take a while -- bigger nets (like the "
                       "dodecahedron)\ncan take up to a minute each.")
# A fabric-subdivided net's fine mesh edges are drawn thin/faint so the
# subdivision reads as texture rather than a bold wireframe competing
# with the per-coarse-face coloring -- see load_fabric_spec.
SUBDIVISION_EDGE_ALPHA = 0.35
SUBDIVISION_EDGE_WIDTH = 0.5


class StretchyPolyhedronApp:
    def __init__(self, root):
        self.root = root
        root.title("Stretchy Polyhedron Init")
        root.geometry("1200x760")
        root.minsize(820, 560)

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

        self.recompute_button = ttk.Button(picker_row, text="Recompute Wireframe",
                                            command=self.on_recompute_clicked)
        self.recompute_button.pack(side=tk.LEFT, padx=(12, 0))

        self.compute_all_button = ttk.Button(picker_row, text="Compute All Wireframes",
                                              command=self.on_compute_all_clicked)
        self.compute_all_button.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(self.compute_all_button, COMPUTE_ALL_TOOLTIP)

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
        self.current_path = None
        self.seed = 0
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
        if self.faces is not None:
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
        matching stretchy_cache/*.json gets a "(not computed)" suffix, same
        wording as polyhedral_net_app.py, but (unlike that app) it's purely
        informational here, not a selection guard: solving already runs in
        a background thread with its own progress indicator (see
        _solve_and_draw), so there's no need to force a separate "Compute"
        step first just to pick a single fast net."""
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
        elif labels:
            self.current_label = labels[0]
        else:
            self.current_label = None

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
        # face and to show the coarse net (not hundreds of fine triangles)
        # in the left "Target faces" panel. An ordinary net has none of
        # this, and renders exactly as before.
        self.coarse_faces, self.fabric_resolution, self.face_of_fine = load_fabric_spec(path)
        color_count = len(self.coarse_faces) if self.coarse_faces is not None else len(self.faces)
        self.colors = [FACE_COLORS[i % len(FACE_COLORS)] for i in range(color_count)]
        self.current_path = path
        self.seed = 0
        self._solve_and_draw(use_cache=True)

    def on_recompute_clicked(self):
        if self.faces is None:
            return
        self.seed += 1  # try a different random restart sequence
        self._solve_and_draw(use_cache=False)

    def _solve_and_draw(self, use_cache):
        """solve_wireframe's random-restart search can take a while on a
        bigger mesh (the dodecahedron's 20 vertices / 30 edges sometimes
        needs several full retries -- see solve_wireframe's docstring --
        each one its own least_squares search), so it runs in a
        background thread exactly like polygon_fold_app.py /
        polyhedral_net_app.py's "Compute Folding Pattern" button: Tk
        isn't thread-safe, so the worker only ever pushes to a queue, and
        the main thread (via _poll_solve_queue, scheduled with `after`)
        is the only one that ever touches a Tk widget.

        use_cache=True (net selection) reads/writes stretchy_cache/ via
        load_with_cache -- a cache hit makes this thread finish almost
        immediately, but it's still backgrounded uniformly rather than
        special-cased, since a miss can be slow. use_cache=False
        ("Recompute Wireframe") calls solve_wireframe directly, bypassing
        the cache entirely: it deliberately wants a *different* one of the
        many valid embeddings, not the cached canonical one, and mustn't
        overwrite it either."""
        self.combo.state(["disabled"])
        self.recompute_button.state(["disabled"])
        self.compute_all_button.state(["disabled"])
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        self._set_status("Solving..." if not use_cache else "Loading...", "info")
        faces, seed, path = self.faces, self.seed, self.current_path
        self._solve_queue = queue.Queue()
        threading.Thread(target=self._solve_worker, args=(faces, seed, path, use_cache),
                          daemon=True).start()
        self.root.after(100, self._poll_solve_queue)

    def _solve_worker(self, faces, seed, path, use_cache):
        try:
            if use_cache:
                _, positions, stats, _ = load_with_cache(path)
            else:
                positions, stats = solve_wireframe(faces, seed=seed)
            self._solve_queue.put(("done", (positions, stats)))
        except Exception as e:  # surface a solver crash instead of hanging forever
            self._solve_queue.put(("error", str(e)))

    def _poll_solve_queue(self):
        try:
            kind, payload = self._solve_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_solve_queue)
            return

        self.progress.stop()
        self.progress.pack_forget()
        self.combo.state(["!disabled"])
        self.recompute_button.state(["!disabled"])
        self.compute_all_button.state(["!disabled"])
        if kind == "error":
            self._set_status(f"Solve failed: {payload}", "error")
            return

        self.positions, self.stats = payload
        self._set_status(
            f"Solved: edges stretched up to {self.stats['max_stretch_pct']:.2f}% "
            f"from unit length (RMS {self.stats['rms_stretch_pct']:.2f}%).", "info")
        self.refresh_net_list()  # the net just solved may have just gained a cache entry
        self.draw()

    # ---- compute-all cache warming ----

    def on_compute_all_clicked(self):
        self.compute_all_button.state(["disabled"])
        self.recompute_button.state(["disabled"])
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        self._set_status("Computing wireframes for every net, this may take a while...", "info")
        self._compute_queue = queue.Queue()
        threading.Thread(target=self._compute_all_worker, daemon=True).start()
        self.root.after(100, self._poll_compute_all_queue)

    def _compute_all_worker(self):
        def on_progress(i, n, label, status, elapsed=None):
            if status == "start":
                self._compute_queue.put(
                    ("progress", f"[{i}/{n}] solving {label}... (this can take a while)"))

        results = build_all(STRETCHY_NETS_DIR, force=False, on_progress=on_progress)
        self._compute_queue.put(("done", results))

    def _poll_compute_all_queue(self):
        try:
            while True:
                kind, payload = self._compute_queue.get_nowait()
                if kind == "progress":
                    self._set_status(payload, "info")
                elif kind == "done":
                    self._compute_all_finished(payload)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll_compute_all_queue)

    def _compute_all_finished(self, results):
        self.progress.stop()
        self.progress.pack_forget()
        self.compute_all_button.state(["!disabled"])
        self.recompute_button.state(["!disabled"])
        failures = [(os.path.basename(p), msg) for p, ok, msg in results if not ok]
        if failures:
            self._set_status(f"Done, but {len(failures)} net(s) failed -- see popup.", "error")
            detail = "\n\n".join(f"{name}:\n{msg}" for name, msg in failures)
            messagebox.showerror(
                "Some nets failed to compute",
                f"{len(failures)} net(s) could not be solved:\n\n{detail}",
                parent=self.root)
        else:
            self._set_status("All wireframes computed." if results else "", "success")
        self.refresh_net_list()

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
        """Each face's UNDEFORMED regular polygon, drawn standalone (not
        connected to its neighbors) side by side purely for reference --
        there's no flat "net" for a mesh whose faces are allowed to bend,
        so this just shows what each face would look like if it weren't
        being stretched/bent to make the whole thing close up.

        For a fabric-subdivided net (self.coarse_faces set, see
        load_fabric_spec), shows the COARSE polygons here -- not the
        hundreds of individual fine triangles -- with a faint subdivision
        overlay at the resolution the net was actually generated at, as a
        2D preview of the mesh being solved."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        fabric = self.coarse_faces is not None
        faces = self.coarse_faces if fabric else self.faces
        gap = 0.6
        x_cursor = 0.0
        all_pts = []
        for face, color in zip(faces, self.colors):
            verts = regular_polygon_vertices(len(face))
            width = max(p[0] for p in verts) - min(p[0] for p in verts)
            offset = np.array([x_cursor - min(p[0] for p in verts), 0.0])
            placed = [p + offset for p in verts]
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
            cx = np.mean([p[0] for p in placed])
            top_y = max(p[1] for p in placed)
            self.ax2d.text(cx, top_y + 0.15, str(face), ha="center", va="bottom",
                            color=theme["fg"], fontsize=8)
            all_pts.extend(placed)
            x_cursor += width + gap

        all_pts = np.array(all_pts)
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        pad = 0.6
        self.ax2d.set_xlim(lo[0] - pad, hi[0] + pad)
        self.ax2d.set_ylim(lo[1] - pad, hi[1] + pad * 1.8)
        self.ax2d.set_aspect("equal")
        self.ax2d.set_title("Target faces (undeformed, unconnected)")

    def _draw_wireframe_result(self, theme):
        """The actual solved result: possibly non-planar faces (drawn
        translucent so the bend is visible) plus the raw vertex/edge
        wireframe on top, since a "face" here is just a rendering
        convenience -- the thing that's actually being solved for is the
        vertex positions and edge lengths.

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
                             "Wireframe result (bent, edges stretched to fit)")

    def draw(self):
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_wireframe_result(theme)
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    StretchyPolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
