"""
Polyhedron Unfolder -- pick a **rigid** net from data/input/nets/ and
explore how it folds, via two tabs that share one net picker:

  - "Animated Fold" -- drag a slider from flat (0%) to fully folded
    (100%).
  - "Flat vs Folded" -- the flat 2D net and the fully folded 3D solid
    side by side at once (drag the 3D panel with the mouse to rotate it;
    matplotlib's own 3D navigation). Also handles **open** nets (a
    polyhedron spec whose faces are a subset of a solid's -- see
    polyhedron_spec.py's module docstring), which the "Animated Fold" tab
    can load too.

    python src/apps/polyhedron_unfolder/app.py

Add your own nets by dropping a new .json file (see polyhedron_spec.py
for the format -- a direct encoding of a model.Polyhedron, real vertex
positions plus CCW face loops -- or any file in data/input/nets/ for
reference) into that folder -- it'll show up in the dropdown
automatically. utils.net_unfolder.NetUnfolder derives the spanning tree,
flat layout, and fold angles itself from whatever geometry is given;
there's nothing to hand-author beyond the polyhedron's own shape.

Unfolding a net is cheap (no numerical solving -- see net_unfolder.py's
docstring), so there's no cache and no precompute step: picking a net
just unfolds it on the spot, in a background thread (see on_select_net)
so the UI never blocks even momentarily.
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

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
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sv_ttk

from common.paths import NETS_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS
from ui.cullable_face import _CullableFace
from utils.net_unfolder import NetUnfolder


class PolyhedronUnfolderApp:
    def __init__(self, root):
        self.root = root
        root.title("Polyhedron Unfolder")
        root.geometry("1200x820")
        root.minsize(860, 620)

        sv_ttk.set_theme("dark")

        # ---- Net selection (shared by both tabs) ----
        net_frame = ttk.LabelFrame(root, text="Net", padding=12)
        net_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(14, 8))

        picker_row = ttk.Frame(net_frame)
        picker_row.pack(fill=tk.X)
        ttk.Label(picker_row, text="Choose a net:").pack(side=tk.LEFT, padx=(0, 8))
        self.combo = ttk.Combobox(picker_row, state="readonly", width=30)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

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

        # ---- Tabs: each owns its own figure/canvas, both read the SAME
        # loaded net/colors state below -- there's only ever one net
        # loaded at a time, shared across tabs, so switching tabs never
        # re-solves or re-picks anything.
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))
        self._build_fold_tab()
        self._build_compare_tab()

        self.net = None
        self.colors = []
        self.current_label = None
        self.label_to_path = {}
        self.is_dark = True
        self._apply_plot_theme()
        self.refresh_net_list()
        if self.current_label:
            self.on_select_net()

    # ---- tab construction ----

    def _build_fold_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Animated Fold")

        # The slider bar is packed BEFORE the (expanding) 3D view, so Tk
        # reserves its natural height first -- packed the other way
        # around, the 3D view's `expand=True` greedily claims the whole
        # cavity as soon as it's packed, leaving the slider bar, packed
        # second, squeezed to nothing whenever the window isn't tall
        # enough for both at their natural sizes (which is exactly what
        # happened once this tab had to share the window with a second
        # tab -- the slider was there, just pushed below the visible
        # area). Packing side=BOTTOM chrome first and side=TOP/expanding
        # content last is the general fix for that failure mode.
        slider_frame = ttk.LabelFrame(tab, text="Fold", padding=12)
        slider_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        slider_row = ttk.Frame(slider_frame)
        slider_row.pack(fill=tk.X)
        ttk.Label(slider_row, text="Flat").pack(side=tk.LEFT)
        self.slider = ttk.Scale(slider_row, from_=0, to=100, orient=tk.HORIZONTAL,
                                 command=self.on_slider)
        self.slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Label(slider_row, text="Folded").pack(side=tk.LEFT)
        self.pct_var = tk.StringVar(value="0%")
        ttk.Label(slider_row, textvariable=self.pct_var, width=5, anchor="e").pack(
            side=tk.LEFT, padx=(10, 0))

        view_frame = ttk.Frame(tab)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        self.fold_fig = plt.figure(figsize=(6, 6))
        self.fold_ax = self.fold_fig.add_subplot(111, projection="3d")
        self.fold_canvas = FigureCanvasTkAgg(self.fold_fig, master=view_frame)
        self.fold_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _build_compare_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Flat vs Folded")

        view_frame = ttk.Frame(tab)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        self.compare_fig = plt.figure(figsize=(11, 5.5))
        self.ax2d = self.compare_fig.add_subplot(1, 2, 1)
        self.ax3d = self.compare_fig.add_subplot(1, 2, 2, projection="3d")
        self.compare_canvas = FigureCanvasTkAgg(self.compare_fig, master=view_frame)
        self.compare_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

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
        """Recolor every axis's chrome (across both tabs) to match the
        current sv_ttk theme and the "Show Axes" toggle -- ax.cla()
        (called on every draw) resets all of this to matplotlib's
        defaults, so it has to be re-applied on every redraw, not just on
        toggle. Returns the active theme dict so draw_*() can reuse its
        colors, e.g. for the box wireframe."""
        theme = PLOT_THEME["dark" if self.is_dark else "light"]
        for fig in (self.fold_fig, self.compare_fig):
            fig.patch.set_facecolor(theme["bg"])
        for ax in (self.fold_ax, self.ax3d):
            ax.set_facecolor(theme["bg"])
            self._style_3d_axis(ax, theme)
        self.ax2d.set_facecolor(theme["bg"])
        self._style_2d_axis(self.ax2d, theme)
        return theme

    def _refresh_plot(self):
        """Redraw both tabs with the current fold state, or just recolor
        the empty plots if no net is loaded yet -- shared by the theme
        and axes-visibility toggles, which both need the same
        "redraw everything" behavior."""
        if self.net is not None:
            self.draw_fold(self.slider.get() / 100.0)
            self.draw_compare()
        else:
            self._apply_plot_theme()
            self.fold_canvas.draw_idle()
            self.compare_canvas.draw_idle()

    def on_toggle_theme(self):
        sv_ttk.toggle_theme()
        self.is_dark = sv_ttk.get_theme() == "dark"
        self.theme_button.configure(text="Light Mode" if self.is_dark else "Dark Mode")
        self._refresh_plot()

    def on_toggle_axes(self):
        self._refresh_plot()

    # ---- net picker ----

    def refresh_net_list(self, keep_selection=True):
        """Rescan data/input/nets/ and rebuild the dropdown. Every .json
        there is selectable -- unfolding is cheap enough (see this
        module's docstring) that nothing needs precomputing ahead of
        time."""
        paths = sorted(glob.glob(os.path.join(NETS_DIR, "*.json")))

        self.label_to_path = {
            os.path.splitext(os.path.basename(path))[0].replace("_", " ").title(): path
            for path in paths
        }

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
        """Load the chosen net's NetUnfolder in a background thread so the
        UI stays responsive even for the (rare, bushy) net that takes
        longer than a frame to unfold -- the combo box is disabled for the
        duration so a second selection can't race the first's load. Tk is
        not thread-safe: the worker thread only ever pushes to `_load_queue`,
        and the main thread (via `_poll_load_queue`, scheduled with
        `after`) is the only one that touches any Tk widget."""
        chosen = self.combo.get()
        self.current_label = chosen
        path = self.label_to_path[chosen]

        self.combo.state(["disabled"])
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        self._set_status(f'Loading "{chosen}"...', "info")

        self._load_queue = queue.Queue()
        threading.Thread(target=self._load_worker, args=(path,), daemon=True).start()
        self.root.after(50, self._poll_load_queue)

    def _load_worker(self, path):
        try:
            net = NetUnfolder.load(path)
            self._load_queue.put(("done", net))
        except Exception as exc:
            self._load_queue.put(("error", str(exc)))

    def _poll_load_queue(self):
        try:
            kind, payload = self._load_queue.get_nowait()
        except queue.Empty:
            self.root.after(50, self._poll_load_queue)
            return

        self.progress.stop()
        self.progress.pack_forget()
        self.combo.state(["!disabled"])

        if kind == "error":
            self._set_status(f'Failed to load "{self.current_label}": {payload}', "error")
            messagebox.showerror("Failed to load net", payload, parent=self.root)
            return

        self._set_status("")
        self.net = payload
        # Colors are a plain, position-indexed list -- a Polyhedron's own
        # face list has no id concept of its own, and self.net.flat/
        # solid.faces (from self.net.fold()) always correspond to
        # self.net.polyhedron.faces position-for-position (see
        # net_unfolder.py), so this is safe, not fragile.
        n_faces = len(self.net.polyhedron.faces)
        self.colors = [FACE_COLORS[i % len(FACE_COLORS)] for i in range(n_faces)]
        self.slider.set(0)
        self.draw_fold(0.0)
        self.draw_compare()

    def on_slider(self, value):
        self.pct_var.set(f"{float(value):.0f}%")
        if self.net is not None:
            self.draw_fold(float(value) / 100.0)

    # ---- drawing ----

    def _draw_box_wireframe(self, ax, xlim, ylim, zlim, color):
        """Explicitly draw all 12 edges of the bounding box. matplotlib's
        default 3D pane borders only cover the 9 edges belonging to the 3
        panes it renders (whichever are "far" from the camera for the
        current, fixed view angle) -- the near vertical edge where the two
        visible walls meet is never drawn, leaving the box looking open on
        one corner.

        Each edge is its own Line3DCollection rather than all 12 in one:
        mplot3d sorts collections for draw order by a single depth value
        from do_3d_projection(), and for a line collection that's just the
        nearest point across *every* segment in it -- bundled into one
        collection, the box's far edges would inherit the near edges'
        depth and wrongly draw in front of (or behind) the solid instead
        of being individually depth-tested against it."""
        corners = list(itertools.product(xlim, ylim, zlim))
        edges = [(a, b) for i, a in enumerate(corners) for b in corners[i + 1:]
                  if sum(p != q for p, q in zip(a, b)) == 1]
        for edge in edges:
            ax.add_collection3d(Line3DCollection([edge], colors=color, linewidths=0.8))

    def _draw_solid(self, ax, solid, theme, title):
        """Shared by both tabs: render `solid` (a NetUnfolder.fold()
        result -- a model.Polyhedron, pure geometry with no color of its
        own) as one Poly3DCollection per face onto `ax`, backface-culled
        (_CullableFace) only when it's actually a closed convex solid --
        see ui.cullable_face's docstring for why that check matters.

        solid.faces[i] always corresponds to self.net.polyhedron.faces[i]
        (see net_unfolder.py), which is exactly what self.colors is
        indexed by."""
        ax.cla()
        self._style_3d_axis(ax, theme)
        use_culling = solid.is_closed
        for i in range(len(solid.faces)):
            pts3d = solid.face_vertices(i)
            color = self.colors[i]
            if use_culling:
                poly = _CullableFace([pts3d], solid.face_normal(i), 0.9,
                                      facecolor=color, edgecolor="k")
            else:
                poly = Poly3DCollection([pts3d], facecolor=color,
                                        edgecolor="k", alpha=0.9)
            ax.add_collection3d(poly)

        # Center the view on the shape's own bounding-box center (not just
        # its raw min/max) so it sits in the middle of the plot regardless
        # of where the net/fold happened to place it, on every axis -- one
        # shared half-width (not one per axis) keeps the box cubic so
        # set_box_aspect([1, 1, 1]) doesn't distort the shape.
        lo, hi = solid.bounding_box()
        center = (lo + hi) / 2
        half = (hi - lo).max() / 2 * 1.2 + 1e-6
        xlim = (center[0] - half, center[0] + half)
        ylim = (center[1] - half, center[1] + half)
        zlim = (center[2] - half, center[2] + half)
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        ax.set_zlim(*zlim)
        ax.set_box_aspect([1, 1, 1])
        if self.show_axes_var.get():
            self._draw_box_wireframe(ax, xlim, ylim, zlim, theme["fg"])
        ax.set_title(title)

    def draw_fold(self, t):
        """"Animated Fold" tab: the single 3D view at fold progress t."""
        theme = self._apply_plot_theme()
        solid = self.net.fold(t)
        # Backface culling (_CullableFace, applied inside _draw_solid) only
        # makes sense once the shape is a closed convex solid -- mid-fold
        # it's an open, generally non-convex shape whose edges don't yet
        # coincide, so solid.is_closed is already false there in practice
        # (an OPEN net -- some faces omitted -- stays false even at t=1).
        # _draw_solid's own solid.is_closed check is what actually gates
        # this, not t itself.
        self._draw_solid(self.fold_ax, solid, theme,
                          f"{self.current_label}  (fold {t*100:.0f}%)")
        self.fold_canvas.draw_idle()

    def draw_compare(self):
        """"Flat vs Folded" tab: the flat net (left) and the fully folded
        solid (right) at once."""
        theme = self._apply_plot_theme()
        self._draw_flat_net(theme)
        solid = self.net.fold(1.0)
        self._draw_solid(self.ax3d, solid, theme, "Folded solid")
        self.compare_canvas.draw_idle()

    def _draw_flat_net(self, theme):
        """The flat net's geometry lives in self.net.flat (a Polyhedron at
        z=0) -- see _draw_solid's docstring for why self.colors already
        lines up with it position-for-position."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        flat = self.net.flat
        pts2d_per_face = [flat.face_vertices(i)[:, :2] for i in range(len(flat.faces))]
        all_pts = np.vstack(pts2d_per_face)
        for pts2d, color in zip(pts2d_per_face, self.colors):
            self.ax2d.add_patch(Polygon(pts2d, closed=True, facecolor=color,
                                         edgecolor="k", alpha=0.9))

        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        center = (lo + hi) / 2
        half = (hi - lo).max() / 2 * 1.2 + 1e-6
        self.ax2d.set_xlim(center[0] - half, center[0] + half)
        self.ax2d.set_ylim(center[1] - half, center[1] + half)
        self.ax2d.set_aspect("equal")
        self.ax2d.set_title("Flat net")


def main():
    root = tk.Tk()
    app = PolyhedronUnfolderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
