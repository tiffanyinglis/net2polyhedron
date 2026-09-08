"""
Grid demo of regular-polygon-to-fine-triangle-mesh subdivision: shows a
triangle, square, pentagon, hexagon, 7-gon and 8-gon, each split into a
fine triangular mesh via utils.subdivisions (see that package's
docstring for how the mesh is built and merged with no duplicate points
across all six shapes). Each n-gon is subdivided at
`resolution_for(n, FABRIC_APP_RESOLUTION)`, not the same literal
resolution for every n -- a bigger-sided polygon has more area per fixed
edge length, so using the same resolution across all six would give it
visibly larger (lower-density) fine triangles than a triangle's or
square's; `resolution_for` scales resolution per n-gon so every subplot's
triangles come out roughly the same size. `FABRIC_APP_RESOLUTION` is the
SAME base resolution (3) utils/subdivisions/mesh_subdivide.py's
DEFAULT_RESOLUTION uses for the real stretchy fabric nets
(generate_subdivided_stretchy_nets.py, e.g.
data/input/stretchy_nets/cube_res3.json) -- this demo is meant as a
preview of exactly that mesh, so it shows exactly that subdivision rather
than some other, denser one (utils.subdivisions.DEFAULT_RESOLUTION=10 is
a much finer default meant for a purely visual preview, not this one). A
"Show subdivision" checkbox (on by default) toggles the internal mesh
edges on/off.

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
from utils.subdivisions.mesh_subdivide import DEFAULT_RESOLUTION as FABRIC_APP_RESOLUTION
from utils.subdivisions import subdivide, resolution_for

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

        self.show_subdivision_var = tk.BooleanVar(value=True)
        self.subdivision_check = ttk.Checkbutton(
            control_frame, text="Show subdivision",
            variable=self.show_subdivision_var, command=self.draw)
        self.subdivision_check.pack(side=tk.LEFT)

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
        show_subdivision = self.show_subdivision_var.get()

        for ax_row, n_row in zip(self.axes, POLYGON_GRID):
            for ax, n in zip(ax_row, n_row):
                ax.cla()
                ax.set_facecolor(theme["bg"])
                verts = regular_polygon_vertices(n)
                xs = [p[0] for p in verts] + [verts[0][0]]
                ys = [p[1] for p in verts] + [verts[0][1]]
                ax.fill(xs, ys, facecolor=FACE_COLOR, edgecolor=theme["fg"],
                         linewidth=1.5, zorder=1)

                if show_subdivision:
                    points, triangles = subdivide(n, verts, resolution_for(n, FABRIC_APP_RESOLUTION))
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
        # calling it again on every redraw (e.g. each "Show subdivision"
        # toggle) creeps the subplots progressively closer together
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
