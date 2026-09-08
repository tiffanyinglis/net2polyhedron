"""
Grid demo of regular-polygon-to-fine-triangle-mesh subdivision: shows a
triangle, square, pentagon, hexagon, 7-gon and 8-gon, each split into a
mesh at a chosen nested "level" via
`utils.subdivisions.subdivide_at_level` (see that function's docstring
for the exact level 0..MAX_LEVEL scheme -- level 0 is the bare polygon,
level 1 is the coarse per-n-gon centroid fan, and each level after that
quarters every triangle from the previous level, so a lower level's
points/edges are always an exact subset of a higher level's). A "Level"
selector (0 by default) picks which one all six subplots show at once.

Laid out as small-paired-with-big columns (3-gon over 8-gon, 4-gon over
7-gon, 5-gon over 6-gon) rather than in n order, so a big and a small
polygon always sit right on top of each other for comparison. All six
subplots share one fixed axis range (sized to the largest, the 8-gon)
instead of each auto-zooming to its own bounding box, so a unit edge
length -- and therefore the mesh triangles -- render at the same pixel
size in every subplot and can be compared directly by eye.

    python src/apps/polygon_subdivision_app/app.py
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import sv_ttk

from common.paths import REPO_ROOT  # noqa: F401 -- import side effect puts src/ on sys.path
from common.ui_theme import PLOT_THEME
from utils.geometry2d.polygon_geom import regular_polygon_vertices
from utils.subdivisions import MAX_LEVEL, subdivide_at_level

# Columns pair a small n-gon with a big one (top row / bottom row) so
# their triangle sizes sit side by side for comparison, rather than a
# strict ascending 2x3 grid.
POLYGON_GRID = [[3, 4, 5], [8, 7, 6]]
POLYGON_NAMES = {3: "Triangle", 4: "Square", 5: "Pentagon",
                  6: "Hexagon", 7: "7-gon", 8: "8-gon"}

FACE_COLOR = "#008dff"
SUBDIVISION_COLOR = "#ff9d3a"


def _shared_axis_half_extent(margin=1.15):
    """One axis half-range, sized to the largest n-gon in POLYGON_GRID
    (bigger n -> bigger circumradius at a fixed edge length), so every
    subplot can share the same xlim/ylim -- and therefore the same
    data-units-per-pixel -- instead of each auto-zooming to its own
    bounding box, which would make a unit edge length look a different
    size in every subplot."""
    biggest_n = max(n for row in POLYGON_GRID for n in row)
    verts = regular_polygon_vertices(biggest_n)
    return max(max(abs(p[0]), abs(p[1])) for p in verts) * margin


AXIS_HALF_EXTENT = _shared_axis_half_extent()


class PolygonSubdivisionApp:
    def __init__(self, root):
        self.root = root
        root.title("Polygon Subdivision")
        root.geometry("1000x700")
        root.minsize(700, 500)

        sv_ttk.set_theme("dark")

        control_frame = ttk.LabelFrame(root, text="Options", padding=12)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(14, 8))

        ttk.Label(control_frame, text="Level:").pack(side=tk.LEFT)
        self.level_var = tk.IntVar(value=0)
        self.level_spinbox = ttk.Spinbox(
            control_frame, from_=0, to=MAX_LEVEL, width=3,
            textvariable=self.level_var, state="readonly")
        self.level_spinbox.pack(side=tk.LEFT, padx=(6, 0))
        self.level_var.trace_add("write", lambda *_: self.draw())

        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
        self.fig, self.axes = plt.subplots(2, 3, figsize=(9, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=view_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._layout_done = False
        self.draw()

    def draw(self):
        theme = PLOT_THEME
        self.fig.patch.set_facecolor(theme["bg"])
        level = self.level_var.get()

        for ax_row, n_row in zip(self.axes, POLYGON_GRID):
            for ax, n in zip(ax_row, n_row):
                ax.cla()
                ax.set_facecolor(theme["bg"])
                verts = regular_polygon_vertices(n)
                xs = [p[0] for p in verts] + [verts[0][0]]
                ys = [p[1] for p in verts] + [verts[0][1]]
                ax.fill(xs, ys, facecolor=FACE_COLOR, edgecolor=theme["fg"],
                         linewidth=1.5, zorder=1)

                if level > 0:
                    points, triangles = subdivide_at_level(n, verts, level)
                    # One LineCollection for all mesh edges rather than an
                    # ax.plot() per triangle -- at this resolution each
                    # subplot has several hundred triangles, and matplotlib
                    # batches a single collection's draw call far faster
                    # than that many separate line artists.
                    segments = []
                    for i, j, k in triangles:
                        segments += [(points[i], points[j]),
                                     (points[j], points[k]),
                                     (points[k], points[i])]
                    ax.add_collection(LineCollection(
                        segments, colors=SUBDIVISION_COLOR, linewidths=0.6, zorder=2))

                ax.set_title(f"{POLYGON_NAMES[n]} (n={n})", color=theme["fg"], fontsize=11)
                ax.set_aspect("equal")
                # Same range on every subplot (not autoscaled to each
                # polygon's own bounding box) so a unit edge length -- and
                # the mesh triangles -- render at the same size everywhere.
                ax.set_xlim(-AXIS_HALF_EXTENT, AXIS_HALF_EXTENT)
                ax.set_ylim(-AXIS_HALF_EXTENT, AXIS_HALF_EXTENT)
                ax.set_axis_off()

        # tight_layout() is not idempotent -- each call re-solves subplot
        # spacing from the current renderer's text bounding boxes, and
        # calling it again on every redraw (e.g. each level change)
        # creeps the subplots progressively closer together
        # instead of settling. Nothing that affects layout (titles,
        # axis-off, fixed limits) changes between redraws, so solve it
        # only once.
        if not self._layout_done:
            self.fig.tight_layout()
            self._layout_done = True
        self.canvas.draw_idle()


def main():
    root = tk.Tk()
    PolygonSubdivisionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
