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
automatically. utils.polyhedron_unfolder.NetUnfolder derives the spanning tree,
flat layout, and fold angles itself from whatever geometry is given;
there's nothing to hand-author beyond the polyhedron's own shape.

Unfolding a net is cheap (no numerical solving -- see polyhedron_unfolder.py's
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
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sv_ttk

from common.paths import NETS_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS
from common.bounding_box import bounding_box
from ui.cullable_face import _CullableFace
from utils.polyhedron_unfolder import NetUnfolder, is_closed


class PolyhedronUnfolderApp:
    def __init__(self, root):
        self.root = root
        root.title("Polyhedron Unfolder")
        # Taller than it is wide-relative-to-height on purpose: Axes3D
        # always renders as a square (matplotlib hard-codes this in
        # Axes3D.apply_aspect -- it's not something this app's own layout
        # controls), so the 3D view's rendered size is capped by whichever
        # of the tab's available width/height is smaller. This window is
        # wide, so that's height -- the taller the window, the bigger that
        # square gets and the less empty margin sits on either side of it.
        root.geometry("1200x784")
        root.minsize(860, 620)

        sv_ttk.set_theme("dark")

        # ---- Net selection (shared by both tabs) ----
        net_frame = ttk.LabelFrame(root, text="Net", padding=10)
        net_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(10, 6))

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

        # ---- Tabs: each owns its own figure/canvas, both read the SAME
        # loaded net/colors state below -- there's only ever one net
        # loaded at a time, shared across tabs, so switching tabs never
        # re-solves or re-picks anything.
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(4, 10))
        self._build_fold_tab()
        self._build_compare_tab()

        self.net = None
        self.colors = []
        self.current_label = None
        self.label_to_path = {}
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
        slider_frame = ttk.LabelFrame(tab, text="Fold", padding=8)
        slider_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
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
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(4, 0))
        self.fold_fig = plt.figure(figsize=(6, 6))
        self.fold_ax = self.fold_fig.add_subplot(111, projection="3d")
        self.fold_canvas = FigureCanvasTkAgg(self.fold_fig, master=view_frame)
        self.fold_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # matplotlib's default figure margins reserve ~20% of the canvas
        # for axis labels/ticks that this app never shows (axes are always
        # off, see _style_3d_axis) -- trimming them directly is most of
        # what makes the solid render bigger, on top of _draw_solid's own
        # tighter bounding-box padding and box_aspect zoom.
        self.fold_fig.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=0.95)

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
        self.compare_fig.subplots_adjust(left=0.02, right=0.98, bottom=0.02,
                                          top=0.93, wspace=0.05)

    def _set_status(self, text, kind="info"):
        self.status_var.set(text)
        self.status_label.configure(foreground=STATUS_COLORS.get(kind, ""))

    # ---- theme ----

    def _style_3d_axis(self, ax):
        ax.title.set_color(PLOT_THEME["fg"])
        ax.set_axis_off()

    def _style_2d_axis(self, ax):
        ax.title.set_color(PLOT_THEME["fg"])
        ax.set_axis_off()

    def _apply_plot_theme(self):
        """Recolor every axis's chrome (across both tabs) to match the
        (fixed, dark-only) plot theme -- ax.cla() (called on every draw)
        resets all of this to matplotlib's defaults, so it has to be
        re-applied on every redraw, not just once at startup."""
        for fig in (self.fold_fig, self.compare_fig):
            fig.patch.set_facecolor(PLOT_THEME["bg"])
        for ax in (self.fold_ax, self.ax3d):
            ax.set_facecolor(PLOT_THEME["bg"])
            self._style_3d_axis(ax)
        self.ax2d.set_facecolor(PLOT_THEME["bg"])
        self._style_2d_axis(self.ax2d)

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
        # polyhedron_unfolder.py), so this is safe, not fragile.
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

    # Bounding-box padding: a small data-limit margin so a face's outline
    # never touches the plot edge even once _fit_zoom below has zoomed all
    # the way in.
    BOX_PADDING = 1.03
    # The on-screen projected half-extent (in Axes3D.get_proj()'s output
    # units, NOT normalized to [-1, 1] -- see _fit_zoom) that fills the
    # plot without clipping for a fully-folded cube (a shape that already
    # touches every corner of its own bounding box, i.e. has zero slack to
    # spare): 0.108. That's reused as the target for every shape/fold
    # stage, but a cube at t=1 turns out to be the BEST case, not a worst
    # case -- other nets/fold-stages project a bit further than their own
    # bounding box would suggest (e.g. a face's far corner swinging wide
    # mid-fold) and were getting clipped at the full 0.108 target. Scaled
    # down to 75% of that so every shape keeps a visible margin instead.
    TARGET_SCREEN_EXTENT = 0.108 * 0.75

    def _fit_zoom(self, ax, half, points):
        """Solve for the Axes3D.set_box_aspect `zoom` that makes `points`
        (the shape's REAL vertices, not just its bounding-box corners)
        fill the plot as much as possible without clipping.

        A fixed zoom constant can't do this well for every shape: a
        closed, faceted solid (a cube, a dodecahedron) touches nearly
        every corner of its own axis-aligned bounding box, but a bushy
        mid-fold net or a sparse open net can leave much more of that
        box empty -- the same zoom that's already at a closed cube's
        clipping limit leaves a mid-fold net looking small. `zoom`
        doesn't map to on-screen size in a way that's simple to invert in
        closed form (it interacts with mplot3d's fixed internal
        perspective/camera-distance math), so this instead measures the
        ACTUAL projected footprint via ax.get_proj() and corrects zoom
        proportionally -- converges to within 1% of TARGET_SCREEN_EXTENT
        in 2-3 iterations in practice, verified against every net in
        data/input/nets/ at several fold progresses each."""
        pts_h = np.column_stack([points, np.ones(len(points))])
        zoom = 1.0
        for _ in range(4):
            ax.set_box_aspect((half[0], half[1], half[2]), zoom=zoom)
            screen = pts_h @ ax.get_proj().T
            extent = np.abs(screen[:, :2] / screen[:, 3:4]).max()
            if extent <= 0:
                break
            zoom *= self.TARGET_SCREEN_EXTENT / extent
        return zoom

    def _draw_solid(self, ax, solid, title):
        """Shared by both tabs: render `solid` (a NetUnfolder.fold()
        result -- a model.Polyhedron, pure geometry with no color of its
        own) as one Poly3DCollection per face onto `ax`, backface-culled
        (_CullableFace) only when it's actually a closed convex solid --
        see ui.cullable_face's docstring for why that check matters.

        solid.faces[i] always corresponds to self.net.polyhedron.faces[i]
        (see polyhedron_unfolder.py), which is exactly what self.colors is
        indexed by."""
        ax.cla()
        self._style_3d_axis(ax)
        use_culling = is_closed(solid)
        all_pts = []
        for i in range(len(solid.faces)):
            pts3d = solid.face_vertices(i)
            all_pts.append(pts3d)
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
        # of where the net/fold happened to place it. Each axis gets its
        # OWN half-width (not one shared cubic half-width) and box_aspect
        # is set to those same three ratios -- an undistorted, true-to-
        # scale render (every axis still has the same units-per-data-unit
        # scale), but one that doesn't waste render area forcing a cubic
        # box around a shape that's flatter/narrower on some axis than
        # others (e.g. a bushy net mid-unfold, or two faces' worth of
        # thickness). _fit_zoom then pulls the camera in the rest of the
        # way, based on the shape's ACTUAL projected footprint rather than
        # just its bounding box -- see that method's docstring for why a
        # fixed zoom constant isn't enough on its own.
        lo, hi = bounding_box(solid.vertices)
        center = (lo + hi) / 2
        half = (hi - lo) / 2 * self.BOX_PADDING + 1e-6
        ax.set_xlim(center[0] - half[0], center[0] + half[0])
        ax.set_ylim(center[1] - half[1], center[1] + half[1])
        ax.set_zlim(center[2] - half[2], center[2] + half[2])
        zoom = self._fit_zoom(ax, half, np.vstack(all_pts))
        ax.set_box_aspect((half[0], half[1], half[2]), zoom=zoom)
        ax.set_title(title)

    def draw_fold(self, t):
        """"Animated Fold" tab: the single 3D view at fold progress t."""
        self._apply_plot_theme()
        solid = self.net.fold(t)
        # Backface culling (_CullableFace, applied inside _draw_solid) only
        # makes sense once the shape is a closed convex solid -- mid-fold
        # it's an open, generally non-convex shape whose edges don't yet
        # coincide, so is_closed(solid) is already false there in practice
        # (an OPEN net -- some faces omitted -- stays false even at t=1).
        # _draw_solid's own is_closed(solid) check is what actually gates
        # this, not t itself.
        self._draw_solid(self.fold_ax, solid,
                          f"{self.current_label}  (fold {t*100:.0f}%)")
        self.fold_canvas.draw_idle()

    def draw_compare(self):
        """"Flat vs Folded" tab: the flat net (left) and the fully folded
        solid (right) at once."""
        self._apply_plot_theme()
        self._draw_flat_net()
        solid = self.net.fold(1.0)
        self._draw_solid(self.ax3d, solid, "Folded solid")
        self.compare_canvas.draw_idle()

    def _draw_flat_net(self):
        """The flat net's geometry lives in self.net.flat (a Polyhedron at
        z=0) -- see _draw_solid's docstring for why self.colors already
        lines up with it position-for-position."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d)
        flat = self.net.flat
        pts2d_per_face = [flat.face_vertices(i)[:, :2] for i in range(len(flat.faces))]
        all_pts = np.vstack(pts2d_per_face)
        for pts2d, color in zip(pts2d_per_face, self.colors):
            self.ax2d.add_patch(Polygon(pts2d, closed=True, facecolor=color,
                                         edgecolor="k", alpha=0.9))

        # Per-axis half-extents (not one shared half-extent) so the flat
        # net's own aspect ratio -- rarely square -- fills the panel
        # instead of sitting in a padded square crop of it; set_aspect
        # ("equal") still keeps it undistorted.
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        center = (lo + hi) / 2
        half = (hi - lo) / 2 * self.BOX_PADDING + 1e-6
        self.ax2d.set_xlim(center[0] - half[0], center[0] + half[0])
        self.ax2d.set_ylim(center[1] - half[1], center[1] + half[1])
        self.ax2d.set_aspect("equal")
        self.ax2d.set_title("Flat net")


def main():
    root = tk.Tk()
    app = PolyhedronUnfolderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
