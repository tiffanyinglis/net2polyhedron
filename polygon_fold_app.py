"""
Interactive polyhedron-net folding app: a dropdown to pick from .poly net
files in the nets/ folder (5 Platonic solids included), plus a slider to
fold from flat (0%) to fully closed (100%).

    python polygon_fold_app.py

Add your own nets by dropping a new .poly file (see polyhedron_spec.py for
the format, or any file in nets/ for reference) into the nets/ folder --
it'll show up in the dropdown automatically. Legacy .txt files with explicit
coordinates and fold angles (see net_io.load_net_txt) are also supported.
Run build_fold_cache.py after adding/editing a .poly file to avoid solving
it on first load.
"""
import os
import glob
import tkinter as tk
from tkinter import ttk

import numpy as np
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from net_fold_utils import load_net, fold

NETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nets")


class PolygonFoldApp:
    def __init__(self, root):
        self.root = root
        root.title("Net Folder")
        root.geometry("800x800")

        top = ttk.Frame(root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Net:").pack(side=tk.LEFT, padx=(0, 6))
        self.net_files = self._scan_nets()
        self.combo = ttk.Combobox(top, values=list(self.net_files.keys()),
                                   state="readonly", width=30)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

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
        if self.net_files:
            self.combo.current(0)
            self.on_select_net()

    def _scan_nets(self):
        files = sorted(glob.glob(os.path.join(NETS_DIR, "*.poly")) +
                        glob.glob(os.path.join(NETS_DIR, "*.txt")))
        result = {}
        for path in files:
            label = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            result[label] = path
        return result

    def on_select_net(self, event=None):
        path = self.net_files[self.combo.get()]
        self.net, self.root_face, self.hinges, self.fold_angles, _ = load_net(path)
        self.colors = plt.cm.Set2(np.linspace(0, 1, len(self.net.faces)))
        self.slider.set(0)
        self.draw(0.0)

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
        self.ax.set_title(f"{self.combo.get()}  (fold {t*100:.0f}%)")
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    app = PolygonFoldApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
