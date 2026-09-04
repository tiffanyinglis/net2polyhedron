"""
Polyhedron Unfolder -- pick a **rigid** net from data/input/nets/ (5
Platonic solids included) and explore how it folds, via two tabs that
share one net picker / compute-cache control bar:

  - "Animated Fold" -- drag a slider from flat (0%) to fully folded
    (100%).
  - "Flat vs Folded" -- the flat 2D net and the fully folded 3D solid
    side by side at once (drag the 3D panel with the mouse to rotate it;
    matplotlib's own 3D navigation). Also handles **open** nets (some
    faces deliberately omitted -- see polyhedron_spec.py's module
    docstring), which the "Animated Fold" tab can load too.

    python src/apps/polyhedron_unfolder/app.py

Add your own nets by dropping a new .json file (see polyhedron_spec.py
for the format, or any file in data/input/nets/ for reference) into that
folder -- it'll show up in the dropdown automatically. Legacy .txt files
with explicit coordinates and fold angles (see net_io.load_net_txt) are
also supported.

A .json net with no matching cache/*.fold file (in this app's OWN cache/
folder, next to this file -- not shared with any other app) hasn't been
solved yet and shows up greyed out and unselectable; use the "Compute
Folding Pattern" button (or run build_cache.py from the command line) to
solve it.
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
from common.ui_theme import (STATUS_COLORS, PLOT_THEME, FACE_COLORS,
                              DISABLED_SUFFIX, COMPUTE_TOOLTIP)
from ui.tooltip import Tooltip
from ui.cullable_face import _CullableFace
from utils.persistence import load_net, is_cached, build_all
from utils.persistence.fold_cache import cache_path_for
from utils.geometry3d import fold, face_normal, is_closed_solid

# This app's OWN cache -- not shared with inflate_polyhedron_app (a
# different pipeline entirely) or with any other app, so nothing here
# ever depends on another app's cache directory.
CACHE_DIR = Path(__file__).resolve().parent / "cache"


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

        self.compute_button = ttk.Button(picker_row, text="Compute Folding Pattern",
                                          command=self.on_compute_clicked)
        self.compute_button.pack(side=tk.LEFT, padx=(12, 0))
        Tooltip(self.compute_button, COMPUTE_TOOLTIP)

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

        self.net = self.root_face = self.hinges = self.fold_angles = None
        self.colors = []
        self.current_label = None
        self.label_to_path = {}
        self.label_enabled = {}
        self.is_dark = True
        self._apply_plot_theme()
        self.refresh_net_list()
        if self.current_label:
            self.on_select_net()

    # ---- tab construction ----

    def _build_fold_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Animated Fold")

        view_frame = ttk.Frame(tab)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        self.fold_fig = plt.figure(figsize=(6, 6))
        self.fold_ax = self.fold_fig.add_subplot(111, projection="3d")
        self.fold_canvas = FigureCanvasTkAgg(self.fold_fig, master=view_frame)
        self.fold_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

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
        """Rescan data/input/nets/, figure out which are already solved (a
        valid cache/*.fold exists in this app's OWN cache folder), and
        rebuild the dropdown -- unsolved .json nets get a "(not computed)"
        suffix and are rejected on selection instead of being loaded."""
        paths = sorted(glob.glob(os.path.join(NETS_DIR, "*.json")) +
                        glob.glob(os.path.join(NETS_DIR, "*.txt")))

        self.label_to_path = {}
        self.label_enabled = {}
        for path in paths:
            base_label = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            enabled = path.endswith(".txt") or is_cached(path, cache_path_for(path, CACHE_DIR))
            label = base_label if enabled else base_label + DISABLED_SUFFIX
            self.label_to_path[label] = path
            self.label_enabled[label] = enabled

        labels = list(self.label_to_path.keys())
        self.combo["values"] = labels
        self._style_disabled_items()

        previous_path = self.label_to_path.get(self.current_label)
        if keep_selection and previous_path:
            for label, path in self.label_to_path.items():
                if path == previous_path:
                    self.current_label = label
                    break
        elif labels:
            enabled_labels = [l for l in labels if self.label_enabled[l]]
            self.current_label = enabled_labels[0] if enabled_labels else labels[0]
        else:
            self.current_label = None

        if self.current_label:
            self.combo.set(self.current_label)

    def _style_disabled_items(self):
        """Best-effort: grey out disabled entries in the dropdown's popup
        list. Reaches into ttk's Tcl internals, so it's wrapped so a
        failure here (e.g. on an unusual Tk build) never breaks the app --
        the " (not computed)" suffix and selection guard already make
        disabled nets unmistakable and unselectable without it."""
        try:
            popdown = self.combo.tk.eval(f"ttk::combobox::PopdownWindow {self.combo}")
            listbox = f"{popdown}.f.l"
            for i, label in enumerate(self.combo["values"]):
                color = "grey60" if not self.label_enabled.get(label, True) else ""
                self.combo.tk.call(listbox, "itemconfigure", i, "-foreground", color)
        except tk.TclError:
            pass

    def on_select_net(self, event=None):
        chosen = self.combo.get()
        if not self.label_enabled.get(chosen, False):
            self._set_status(f'"{chosen.replace(DISABLED_SUFFIX, "")}" hasn\'t '
                              f'been folded yet -- click Compute Folding Pattern.', "warn")
            self.combo.set(self.current_label)
            return

        self._set_status("")
        self.current_label = chosen
        path = self.label_to_path[chosen]
        self.net, self.root_face, self.hinges, self.fold_angles, _ = load_net(path, cache_dir=CACHE_DIR)
        self.colors = [FACE_COLORS[i % len(FACE_COLORS)] for i in range(len(self.net.faces))]
        self.slider.set(0)
        self.draw_fold(0.0)
        self.draw_compare()

    # ---- compute cache ----

    def on_compute_clicked(self):
        self.compute_button.state(["disabled"])
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        self._set_status("Computing folding patterns, this may take a few minutes...", "info")
        # Tk is not thread-safe: the worker thread only ever pushes to this
        # queue, and the main thread (via _poll_compute_queue, scheduled
        # with `after`) is the only one that touches any Tk widget.
        self._compute_queue = queue.Queue()
        threading.Thread(target=self._compute_worker, daemon=True).start()
        self.root.after(100, self._poll_compute_queue)

    def _compute_worker(self):
        def on_progress(i, n, label, status, elapsed=None):
            if status == "start":
                self._compute_queue.put(
                    ("progress", f"[{i}/{n}] solving {label}... (this can take a while)"))

        results = build_all(NETS_DIR, cache_dir=CACHE_DIR, force=False, on_progress=on_progress)
        self._compute_queue.put(("done", results))

    def _poll_compute_queue(self):
        try:
            while True:
                kind, payload = self._compute_queue.get_nowait()
                if kind == "progress":
                    self._set_status(payload, "info")
                elif kind == "done":
                    self._compute_finished(payload)
                    return  # worker is finished, stop polling
        except queue.Empty:
            pass
        self.root.after(100, self._poll_compute_queue)

    def _compute_finished(self, results):
        self.progress.stop()
        self.progress.pack_forget()
        self.compute_button.state(["!disabled"])
        failures = [(os.path.basename(p), msg) for p, ok, msg in results if not ok]
        if failures:
            self._set_status(f"Done, but {len(failures)} net(s) failed -- see popup.", "error")
            detail = "\n\n".join(f"{name}:\n{msg}" for name, msg in failures)
            messagebox.showerror(
                "Some nets failed to compute",
                f"{len(failures)} net(s) could not be folded:\n\n{detail}",
                parent=self.root)
        else:
            self._set_status("All nets computed." if results else "", "success")
        self.refresh_net_list()

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

    def _draw_solid(self, ax, verts, theme, title):
        """Shared by both tabs: render `verts` (a fold() result) as one
        Poly3DCollection per face onto `ax`, backface-culled (_CullableFace)
        only when it's actually a closed convex solid -- see
        ui.cullable_face's docstring for why that check matters."""
        ax.cla()
        self._style_3d_axis(ax, theme)
        all_pts = np.vstack(list(verts.values()))
        use_culling = is_closed_solid(verts)
        for (fid, pts), color in zip(verts.items(), self.colors):
            if use_culling:
                poly = _CullableFace([pts], face_normal(pts), 0.9,
                                      facecolor=color, edgecolor="k")
            else:
                poly = Poly3DCollection([pts], facecolor=color, edgecolor="k", alpha=0.9)
            ax.add_collection3d(poly)

        # Center the view on the shape's own bounding-box center (not just
        # its raw min/max) so it sits in the middle of the plot regardless
        # of where the net/fold happened to place it, on every axis -- one
        # shared half-width (not one per axis) keeps the box cubic so
        # set_box_aspect([1, 1, 1]) doesn't distort the shape.
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
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
        verts = fold(self.net, self.root_face, self.hinges, self.fold_angles, t)
        # Backface culling (_CullableFace, applied inside _draw_solid) only
        # makes sense once the shape is a closed convex solid -- mid-fold
        # it's an open, generally non-convex shape whose edges don't yet
        # coincide, so is_closed_solid(verts) is already false there in
        # practice (an OPEN net -- some faces omitted -- stays false even
        # at t=1). _draw_solid's own is_closed_solid(verts) check is what
        # actually gates this, not t itself.
        self._draw_solid(self.fold_ax, verts, theme,
                          f"{self.current_label}  (fold {t*100:.0f}%)")
        self.fold_canvas.draw_idle()

    def draw_compare(self):
        """"Flat vs Folded" tab: the flat net (left) and the fully folded
        solid (right) at once."""
        theme = self._apply_plot_theme()
        self._draw_flat_net(theme)
        verts = fold(self.net, self.root_face, self.hinges, self.fold_angles, 1.0)
        self._draw_solid(self.ax3d, verts, theme, "Folded solid")
        self.compare_canvas.draw_idle()

    def _draw_flat_net(self, theme):
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        all_pts = np.vstack([pts for pts in self.net.faces.values()])
        for (fid, pts), color in zip(self.net.faces.items(), self.colors):
            self.ax2d.add_patch(Polygon(pts, closed=True, facecolor=color,
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
