"""
Interactive polyhedron-net folding app: a dropdown to pick from .json net
files in the nets/ folder (5 Platonic solids included), plus a slider to
fold from flat (0%) to fully closed (100%).

    python polygon_fold_app.py

Add your own nets by dropping a new .json file (see polyhedron_spec.py for
the format, or any file in nets/ for reference) into the nets/ folder --
it'll show up in the dropdown automatically. Legacy .txt files with explicit
coordinates and fold angles (see net_io.load_net_txt) are also supported.

A .json net with no matching fold_cache/*.fold file hasn't been solved yet
and shows up greyed out and unselectable; use the "Compute Folding Pattern"
button (or run build_fold_cache.py from the command line) to solve it.
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
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sv_ttk

from net_fold_utils import load_net, fold, is_cached, build_all, face_normal
from tooltip import Tooltip

NETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nets")
DISABLED_SUFFIX = "  (not computed)"
COMPUTE_TOOLTIP = ("Solves the fold for every net that hasn't been computed "
                    "yet.\nThis may take a few minutes -- larger nets (like "
                    "the icosahedron)\ncan take up to a minute each.")

STATUS_COLORS = {
    "info": "#3b6ea5",
    "success": "#1a7f37",
    "error": "#cf222e",
    "warn": "#9a6700",
}

# Mirrors sv_ttk's own background colors (theme/{light,dark}.tcl -bg) so the
# 3D plot doesn't look like a mismatched white box dropped onto a dark
# window. fg/grid are the axis lines, ticks, labels and gridlines -- these
# need to flip to a light color in dark mode to stay visible against -bg.
PLOT_THEME = {
    "light": {"bg": "#fafafa", "fg": "#1c1c1c", "grid": (0, 0, 0, 0.1)},
    "dark": {"bg": "#1c1c1c", "fg": "#e0e0e0", "grid": (1, 1, 1, 0.15)},
}


# A high-variety, fixed face-color palette (two named 8-color sets),
# deliberately more visually distinct than a qualitative colormap like
# Set2, which has only 8 base (fairly similar, muted) hues and blends
# washed-out intermediate tones once a net has more faces than that.
# Cycles (via modulo where it's used) for a net with more faces than
# colors (16 here).
_BRIGHT = ["#003a7d", "#008dff", "#ff73b6", "#c701ff",
           "#4ecb8d", "#ff9d3a", "#f9e858", "#d83034"]
_ALTERNATING_LIGHT_DARK = ["#8fd7d7", "#00b0be", "#ff8ca1", "#f45f74",
                           "#bdd373", "#98c127", "#ffcd8e", "#ffb255"]
FACE_COLORS = _BRIGHT + _ALTERNATING_LIGHT_DARK


class _CullableFace(Poly3DCollection):
    """A single-face Poly3DCollection that hides itself when its outward
    normal points away from the camera, instead of relying on mplot3d's
    painter's-algorithm depth sort (which only has one scalar "depth" per
    face to work with -- a face at a grazing angle to the camera can have
    that scalar put it in front of a face it should be occluded by,
    causing exactly the wrong-face-drawn-on-top glitches this class fixes).

    do_3d_projection() -- which mplot3d calls on every redraw, including
    mid-drag during interactive rotation -- recomputes visibility from the
    CURRENT view angle every time, so it stays correct as the user rotates.

    Only valid for a face on a CLOSED CONVEX solid: there, a face's own
    orientation alone determines whether the solid's far side hides it
    from the camera, and no two visible (camera-facing) faces of a convex
    solid ever overlap in the projection, so no depth sorting is needed
    among them either. Do NOT use this for an open/non-convex net (e.g. a
    mid-fold net) -- a face's own orientation there doesn't determine
    whether some other, unrelated face occludes it.

    Visibility is applied by writing directly to `_facecolor3d` /
    `_edgecolor3d` rather than via the public set_alpha()/set_edgecolor()
    -- Poly3DCollection.set_alpha() only refreshes `_facecolor3d`, not
    `_edgecolor3d` (it updates a *different*, unused `_edgecolors`
    attribute instead, seemingly a matplotlib inconsistency), so the
    do_3d_projection() internals that build the actually-rendered
    `_edgecolors2d` from `_edgecolor3d` never see the alpha-0 update: the
    face fill correctly disappears but its black edge outline stays fully
    opaque and visibly bleeds through the (correctly hidden) face in
    front of it. Setting `_edgecolor3d` directly sidesteps that."""
    def __init__(self, verts, normal, base_alpha, facecolor, edgecolor="k", **kwargs):
        super().__init__(verts, facecolor=facecolor, edgecolor=edgecolor,
                          alpha=base_alpha, **kwargs)
        self._outward_normal = normal
        self._base_alpha = base_alpha
        self._base_facecolor3d = mcolors.to_rgba_array(facecolor, base_alpha)
        self._base_edgecolor3d = mcolors.to_rgba_array(edgecolor, base_alpha)

    def do_3d_projection(self):
        elev, azim = np.radians(self.axes.elev), np.radians(self.axes.azim)
        view_dir = np.array([np.cos(elev) * np.cos(azim),
                              np.cos(elev) * np.sin(azim),
                              np.sin(elev)])
        visible = np.dot(self._outward_normal, view_dir) > 0
        alpha = self._base_alpha if visible else 0.0
        self._facecolor3d = mcolors.to_rgba_array(self._base_facecolor3d, alpha)
        self._edgecolor3d = mcolors.to_rgba_array(self._base_edgecolor3d, alpha)
        return super().do_3d_projection()


class PolygonFoldApp:
    def __init__(self, root):
        self.root = root
        root.title("Polygon Net Folder")
        root.geometry("900x820")
        root.minsize(680, 560)

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

        # ---- 3D view ----
        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=6)
        self.fig = plt.figure(figsize=(6, 6))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.fig, master=view_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # ---- Fold control ----
        fold_frame = ttk.LabelFrame(root, text="Fold", padding=12)
        fold_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=(8, 14))
        slider_row = ttk.Frame(fold_frame)
        slider_row.pack(fill=tk.X)
        ttk.Label(slider_row, text="Flat").pack(side=tk.LEFT)
        self.slider = ttk.Scale(slider_row, from_=0, to=100, orient=tk.HORIZONTAL,
                                 command=self.on_slider)
        self.slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Label(slider_row, text="Folded").pack(side=tk.LEFT)
        self.pct_var = tk.StringVar(value="0%")
        ttk.Label(slider_row, textvariable=self.pct_var, width=5, anchor="e").pack(
            side=tk.LEFT, padx=(10, 0))

        self.net = self.root_face = self.hinges = self.fold_angles = None
        self.current_label = None
        self.label_to_path = {}
        self.label_enabled = {}
        self.is_dark = True
        self._apply_plot_theme()
        self.refresh_net_list()
        if self.current_label:
            self.on_select_net()

    def _set_status(self, text, kind="info"):
        self.status_var.set(text)
        self.status_label.configure(foreground=STATUS_COLORS.get(kind, ""))

    def _apply_plot_theme(self):
        """Recolor the figure/axes chrome to match the current sv_ttk theme
        and the "Show Axes" toggle -- ax.cla() (called every draw()) resets
        all of this to matplotlib's defaults, so it has to be re-applied on
        every redraw, not just on toggle. Returns the active theme dict so
        callers (draw()) can reuse its colors, e.g. for the box wireframe."""
        theme = PLOT_THEME["dark" if self.is_dark else "light"]
        self.fig.patch.set_facecolor(theme["bg"])
        self.ax.set_facecolor(theme["bg"])
        self.ax.title.set_color(theme["fg"])
        if self.show_axes_var.get():
            self.ax.set_axis_on()
            for axis in (self.ax.xaxis, self.ax.yaxis, self.ax.zaxis):
                axis.pane.set_facecolor(theme["bg"])
                axis.pane.set_edgecolor(theme["fg"])
                axis.line.set_color(theme["fg"])
                axis.label.set_color(theme["fg"])
                axis._axinfo["grid"]["color"] = theme["grid"]
            self.ax.tick_params(colors=theme["fg"])
        else:
            self.ax.set_axis_off()
        return theme

    def _refresh_plot(self):
        """Redraw with the current fold position, or just recolor the empty
        plot if no net is loaded yet -- shared by the theme and axes-visibility
        toggles, which both need the same "redraw everything" behavior."""
        if self.net is not None:
            self.draw(self.slider.get() / 100.0)
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

    def refresh_net_list(self, keep_selection=True):
        """Rescan nets/, figure out which are already solved (a valid
        fold_cache/*.fold exists), and rebuild the dropdown -- unsolved
        .json nets get a "(not computed)" suffix and are rejected on
        selection instead of being loaded."""
        paths = sorted(glob.glob(os.path.join(NETS_DIR, "*.json")) +
                        glob.glob(os.path.join(NETS_DIR, "*.txt")))

        self.label_to_path = {}
        self.label_enabled = {}
        for path in paths:
            base_label = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            enabled = path.endswith(".txt") or is_cached(path)
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
        self.net, self.root_face, self.hinges, self.fold_angles, _ = load_net(path)
        self.colors = [FACE_COLORS[i % len(FACE_COLORS)] for i in range(len(self.net.faces))]
        self.slider.set(0)
        self.draw(0.0)

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

        results = build_all(NETS_DIR, force=False, on_progress=on_progress)
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
            self.draw(float(value) / 100.0)

    def _draw_box_wireframe(self, xlim, ylim, zlim, color):
        """Explicitly draw all 12 edges of the bounding box. matplotlib's
        default 3D pane borders only cover the 9 edges belonging to the 3
        panes it renders (whichever are "far" from the camera for the
        current, fixed view angle) -- the near vertical edge where the two
        visible walls meet is never drawn, leaving the box looking open on
        one corner."""
        corners = list(itertools.product(xlim, ylim, zlim))
        edges = [(a, b) for i, a in enumerate(corners) for b in corners[i + 1:]
                  if sum(p != q for p, q in zip(a, b)) == 1]
        self.ax.add_collection3d(Line3DCollection(edges, colors=color, linewidths=0.8))

    def draw(self, t):
        self.ax.cla()
        theme = self._apply_plot_theme()
        verts = fold(self.net, self.root_face, self.hinges, self.fold_angles, t)
        all_pts = np.vstack(list(verts.values()))
        # Backface culling (_CullableFace) only makes sense once the net is
        # a closed convex solid, i.e. fully folded -- mid-fold it's an
        # open, generally non-convex shape, so fall back to the ordinary
        # (imperfect) depth-sorted rendering there.
        fully_folded = abs(t - 1.0) < 1e-9
        for (fid, pts), color in zip(verts.items(), self.colors):
            if fully_folded:
                poly = _CullableFace([pts], face_normal(pts), 0.9,
                                      facecolor=color, edgecolor="k")
            else:
                poly = Poly3DCollection([pts], facecolor=color, edgecolor="k", alpha=0.9)
            self.ax.add_collection3d(poly)

        # Center the view on the shape's own bounding-box center (not just
        # its raw min/max) so it sits in the middle of the plot instead of
        # wherever the net layout happened to place it, on every axis --
        # one shared half-width (not one per axis) keeps the box cubic so
        # set_box_aspect([1, 1, 1]) doesn't distort the shape.
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        center = (lo + hi) / 2
        half = (hi - lo).max() / 2 * 1.2 + 1e-6
        xlim = (center[0] - half, center[0] + half)
        ylim = (center[1] - half, center[1] + half)
        zlim = (center[2] - half, center[2] + half)
        self.ax.set_xlim(*xlim)
        self.ax.set_ylim(*ylim)
        self.ax.set_zlim(*zlim)
        self.ax.set_box_aspect([1, 1, 1])
        if self.show_axes_var.get():
            self._draw_box_wireframe(xlim, ylim, zlim, theme["fg"])
        self.ax.set_title(f"{self.current_label}  (fold {t*100:.0f}%)")
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    app = PolygonFoldApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
