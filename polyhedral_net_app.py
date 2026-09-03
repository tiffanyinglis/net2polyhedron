"""
Side-by-side polyhedron-net viewer: a dropdown to pick from .json net files
in the nets/ folder (5 Platonic solids included), with the flat 2D net on
the left and the fully folded 3D solid on the right -- drag the right panel
with the mouse to rotate it (matplotlib's built-in 3D navigation).

    python polyhedral_net_app.py

Unlike polygon_fold_app.py's animated fold slider, this shows the flat and
folded states at once, side by side, so you can compare which 2D edge
becomes which 3D edge. Add your own nets the same way as for
polygon_fold_app.py (see polyhedron_spec.py for the format).

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
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sv_ttk

from net_fold_utils import load_net, fold, is_cached, build_all, face_normal, is_closed_solid
from tooltip import Tooltip
from polygon_fold_app import (STATUS_COLORS, PLOT_THEME, NETS_DIR, DISABLED_SUFFIX,
                               COMPUTE_TOOLTIP, FACE_COLORS, _CullableFace)


class PolyhedralNetApp:
    def __init__(self, root):
        self.root = root
        root.title("Polyhedral Net Viewer")
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

        # ---- Flat net (left) + folded solid (right) ----
        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))
        self.fig = plt.figure(figsize=(11, 5.5))
        self.ax2d = self.fig.add_subplot(1, 2, 1)
        self.ax3d = self.fig.add_subplot(1, 2, 2, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.fig, master=view_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

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
        draw() can reuse its colors, e.g. for the polygon fills' edges and
        the 3D box wireframe."""
        theme = PLOT_THEME["dark" if self.is_dark else "light"]
        self.fig.patch.set_facecolor(theme["bg"])
        self.ax2d.set_facecolor(theme["bg"])
        self.ax3d.set_facecolor(theme["bg"])
        self._style_2d_axis(self.ax2d, theme)
        self._style_3d_axis(self.ax3d, theme)
        return theme

    def _refresh_plot(self):
        """Redraw with the currently loaded net, or just recolor the empty
        plot if none is loaded yet -- shared by the theme and
        axes-visibility toggles, which both need the same "redraw
        everything" behavior."""
        if self.net is not None:
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
        self.draw()

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

    # ---- drawing ----

    def _draw_box_wireframe(self, xlim, ylim, zlim, color):
        """Explicitly draw all 12 edges of the 3D bounding box. matplotlib's
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
            self.ax3d.add_collection3d(Line3DCollection([edge], colors=color, linewidths=0.8))

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

    def _draw_folded_solid(self, theme):
        self.ax3d.cla()
        self._style_3d_axis(self.ax3d, theme)
        verts = fold(self.net, self.root_face, self.hinges, self.fold_angles, 1.0)
        all_pts = np.vstack(list(verts.values()))
        # This panel always shows the fully FOLDED shape, but that's only
        # a closed, convex solid for an ordinary net -- an OPEN net (some
        # faces omitted, see polyhedron_spec.py) never closes even at
        # t=1, and backface culling (_CullableFace) assumes a closed
        # solid (see its docstring in polygon_fold_app.py and
        # is_closed_solid()'s in net_fold_core.py); fall back to the
        # ordinary depth-sorted Poly3DCollection for those.
        use_culling = is_closed_solid(verts)
        for (fid, pts), color in zip(verts.items(), self.colors):
            if use_culling:
                poly = _CullableFace([pts], face_normal(pts), 0.9,
                                      facecolor=color, edgecolor="k")
            else:
                poly = Poly3DCollection([pts], facecolor=color, edgecolor="k", alpha=0.9)
            self.ax3d.add_collection3d(poly)

        # Center the view on the shape's own bounding-box center (not just
        # its raw min/max) so it sits in the middle of the plot instead of
        # wherever the fold happened to place it, on every axis -- one
        # shared half-width (not one per axis) keeps the box cubic so
        # set_box_aspect([1, 1, 1]) doesn't distort the shape.
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
        self.ax3d.set_title("Folded solid")

    def draw(self):
        theme = self._apply_plot_theme()
        self._draw_flat_net(theme)
        self._draw_folded_solid(theme)
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    app = PolyhedralNetApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
