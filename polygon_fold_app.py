"""
Interactive polyhedron-net folding app: a dropdown to pick from .poly net
files in the nets/ folder (5 Platonic solids included), plus a slider to
fold from flat (0%) to fully closed (100%).

    python polygon_fold_app.py

Add your own nets by dropping a new .poly file (see polyhedron_spec.py for
the format, or any file in nets/ for reference) into the nets/ folder --
it'll show up in the dropdown automatically. Legacy .txt files with explicit
coordinates and fold angles (see net_io.load_net_txt) are also supported.

A .poly net with no matching fold_cache/*.fold file hasn't been solved yet
and shows up greyed out and unselectable; use the "Compute Folding Pattern"
button (or run build_fold_cache.py from the command line) to solve it.
"""
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
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from net_fold_utils import load_net, fold, is_cached, build_all
from tooltip import Tooltip

NETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nets")
DISABLED_SUFFIX = "  (not computed)"
COMPUTE_TOOLTIP = ("Solves the fold for every net that hasn't been computed "
                    "yet.\nThis may take a few minutes -- larger nets (like "
                    "the icosahedron)\ncan take up to a minute each.")


class PolygonFoldApp:
    def __init__(self, root):
        self.root = root
        root.title("Net Folder")
        root.geometry("800x800")

        top = ttk.Frame(root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Net:").pack(side=tk.LEFT, padx=(0, 6))
        self.combo = ttk.Combobox(top, state="readonly", width=30)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        self.compute_button = ttk.Button(top, text="Compute Folding Pattern",
                                          command=self.on_compute_clicked)
        self.compute_button.pack(side=tk.LEFT, padx=(10, 0))
        Tooltip(self.compute_button, COMPUTE_TOOLTIP)

        self.status_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.status_var,
                  foreground="#a05a00").pack(side=tk.LEFT, padx=(10, 0))

        self.fig = plt.figure(figsize=(6, 6))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.fig, master=root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        bottom = ttk.Frame(root, padding=8)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bottom, text="Fold:").pack(side=tk.LEFT, padx=(0, 6))
        self.slider = ttk.Scale(bottom, from_=0, to=100, orient=tk.HORIZONTAL,
                                 command=self.on_slider)
        self.slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.net = self.root_face = self.hinges = self.fold_angles = None
        self.current_label = None
        self.label_to_path = {}
        self.label_enabled = {}
        self.refresh_net_list()
        if self.current_label:
            self.on_select_net()

    def refresh_net_list(self, keep_selection=True):
        """Rescan nets/, figure out which are already solved (a valid
        fold_cache/*.fold exists), and rebuild the dropdown -- unsolved
        .poly nets get a "(not computed)" suffix and are rejected on
        selection instead of being loaded."""
        paths = sorted(glob.glob(os.path.join(NETS_DIR, "*.poly")) +
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
                color = "grey60" if not self.label_enabled.get(label, True) else "black"
                self.combo.tk.call(listbox, "itemconfigure", i, "-foreground", color)
        except tk.TclError:
            pass

    def on_select_net(self, event=None):
        chosen = self.combo.get()
        if not self.label_enabled.get(chosen, False):
            self.status_var.set(f'"{chosen.replace(DISABLED_SUFFIX, "")}" hasn\'t '
                                 f'been folded yet -- click Compute Folding Pattern.')
            self.combo.set(self.current_label)
            return

        self.status_var.set("")
        self.current_label = chosen
        path = self.label_to_path[chosen]
        self.net, self.root_face, self.hinges, self.fold_angles, _ = load_net(path)
        self.colors = plt.cm.Set2(np.linspace(0, 1, len(self.net.faces)))
        self.slider.set(0)
        self.draw(0.0)

    def on_compute_clicked(self):
        self.compute_button.state(["disabled"])
        self.status_var.set("Computing folding patterns, this may take a few minutes...")
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
                    self.status_var.set(payload)
                elif kind == "done":
                    self._compute_finished(payload)
                    return  # worker is finished, stop polling
        except queue.Empty:
            pass
        self.root.after(100, self._poll_compute_queue)

    def _compute_finished(self, results):
        self.compute_button.state(["!disabled"])
        failures = [(os.path.basename(p), msg) for p, ok, msg in results if not ok]
        if failures:
            self.status_var.set(f"Done, but {len(failures)} net(s) failed -- see popup.")
            detail = "\n\n".join(f"{name}:\n{msg}" for name, msg in failures)
            messagebox.showerror(
                "Some nets failed to compute",
                f"{len(failures)} net(s) could not be folded:\n\n{detail}",
                parent=self.root)
        else:
            self.status_var.set("All nets computed." if results else "")
        self.refresh_net_list()

    def on_slider(self, value):
        if self.net is not None:
            self.draw(float(value) / 100.0)

    def draw(self, t):
        self.ax.cla()
        verts = fold(self.net, self.root_face, self.hinges, self.fold_angles, t)
        all_pts = np.vstack(list(verts.values()))
        for (fid, pts), color in zip(verts.items(), self.colors):
            poly = Poly3DCollection([pts], facecolor=color, edgecolor="k", alpha=0.9)
            self.ax.add_collection3d(poly)
        lo, hi = all_pts.min(), all_pts.max()
        pad = (hi - lo) * 0.1 + 1e-6
        self.ax.set_xlim(lo - pad, hi + pad)
        self.ax.set_ylim(lo - pad, hi + pad)
        self.ax.set_zlim(lo - pad, hi + pad)
        self.ax.set_box_aspect([1, 1, 1])
        self.ax.set_title(f"{self.current_label}  (fold {t*100:.0f}%)")
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    app = PolygonFoldApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
