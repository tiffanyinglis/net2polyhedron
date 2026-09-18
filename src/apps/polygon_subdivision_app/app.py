"""
Grid demo of n-gon-to-fine-triangle-mesh subdivision: shows a triangle,
square, pentagon, hexagon, 7-gon and 8-gon, each split into a mesh at a
chosen nested "level" via
`utils.subdivisions.subdivide_ngon_at_level` -- level 0 is the bare
polygon, level 1 connects the centroid to every vertex (n triangles),
and each level after that quarters every triangle by connecting its
edge midpoints. Each polygon's vertices are individually draggable
(drawn as small filled circles for easy picking), so the mesh can be
previewed on a non-regular n-gon too -- middle-click anywhere resets
every polygon back to its default regular form.

Laid out as small-paired-with-big columns (3-gon over 8-gon, 4-gon over
7-gon, 5-gon over 6-gon) rather than in n order, so a big and a small
polygon always sit right on top of each other for comparison. All six
subplots share one fixed axis range (sized to the largest, the 8-gon)
instead of each auto-zooming to its own bounding box, so a unit edge
length -- and therefore the mesh triangles -- render at the same pixel
size in every subplot and can be compared directly by eye.

    python src/apps/polygon_subdivision_app/app.py
"""
import math
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import numpy as np
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
from utils.geometry.polygon_geom import regular_polygon_vertices
from utils.subdivisions import MAX_LEVEL, subdivide_ngon_at_level

# Columns pair a small n-gon with a big one (top row / bottom row) so
# their triangle sizes sit side by side for comparison, rather than a
# strict ascending 2x3 grid.
POLYGON_GRID = [[3, 4, 5], [8, 7, 6]]
POLYGON_NAMES = {3: "Triangle", 4: "Square", 5: "Pentagon",
                  6: "Hexagon", 7: "7-gon", 8: "8-gon"}

FACE_COLOR = "#008dff"
SUBDIVISION_COLOR = "#ff9d3a"
VERTEX_COLOR = "#ffffff"
VERTEX_MARKER_SIZE = 7
VERTEX_PICK_RADIUS_PX = 10


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

        ttk.Label(control_frame,
                  text="Drag a vertex to reshape its polygon. Middle-click to reset all.",
                  foreground=PLOT_THEME["fg"]).pack(side=tk.LEFT, padx=(24, 0))

        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))
        self.fig, self.axes = plt.subplots(2, 3, figsize=(9, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=view_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.vertices = {n: regular_polygon_vertices(n)
                          for row in POLYGON_GRID for n in row}
        self._ax_of_n = {}
        self._n_of_ax = {}
        for ax_row, n_row in zip(self.axes, POLYGON_GRID):
            for ax, n in zip(ax_row, n_row):
                self._ax_of_n[n] = ax
                self._n_of_ax[ax] = n
        self._dragging = None  # (n, vertex_index) while a drag is in progress

        self.canvas.mpl_connect("button_press_event", self._on_button_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_button_release)

        self._layout_done = False
        self.draw()

    def _reset_all_vertices(self):
        """Middle-click handler: restore every polygon to its default
        regular-n-gon vertex positions and redraw."""
        for n in self.vertices:
            self.vertices[n] = regular_polygon_vertices(n)
        self.draw()

    def _find_vertex_at(self, ax, n, event):
        """Return the index of the vertex nearest (event.x, event.y) --
        pixel/display coords -- within VERTEX_PICK_RADIUS_PX, or None if
        none is close enough."""
        for idx, v in enumerate(self.vertices[n]):
            vx, vy = ax.transData.transform(v)
            if math.hypot(vx - event.x, vy - event.y) <= VERTEX_PICK_RADIUS_PX:
                return idx
        return None

    def _on_button_press(self, event):
        if event.button == 2:  # middle click, anywhere on the canvas
            self._reset_all_vertices()
            return
        if event.button != 1 or event.inaxes not in self._n_of_ax:
            return
        n = self._n_of_ax[event.inaxes]
        idx = self._find_vertex_at(event.inaxes, n, event)
        if idx is not None:
            self._dragging = (n, idx)

    def _on_motion(self, event):
        if self._dragging is None or event.x is None or event.y is None:
            return
        n, idx = self._dragging
        ax = self._ax_of_n[n]
        # Invert through the dragged vertex's own axes rather than relying
        # on event.xdata/ydata (which go None once the pointer leaves that
        # axes' bounds) -- lets a drag continue smoothly past the edge of
        # the subplot instead of freezing there.
        x, y = ax.transData.inverted().transform((event.x, event.y))
        self.vertices[n][idx] = np.array([x, y])
        self._draw_polygon(ax, n)
        self.canvas.draw_idle()

    def _on_button_release(self, event):
        self._dragging = None

    def _draw_polygon(self, ax, n):
        """Redraw a single subplot -- face fill, mesh at the current
        level, and vertices as small circles -- from self.vertices[n].
        Used for the full draw() and for a single-subplot refresh
        mid-drag, so dragging one vertex doesn't repaint all six."""
        theme = PLOT_THEME
        level = self.level_var.get()
        verts = self.vertices[n]

        ax.cla()
        ax.set_facecolor(theme["bg"])
        xs = [p[0] for p in verts] + [verts[0][0]]
        ys = [p[1] for p in verts] + [verts[0][1]]
        ax.fill(xs, ys, facecolor=FACE_COLOR, edgecolor=theme["fg"],
                 linewidth=1.5, zorder=1)

        if level > 0:
            points, triangles = subdivide_ngon_at_level(verts, level)
            # One LineCollection for all mesh edges rather than an
            # ax.plot() per triangle -- at this resolution each subplot
            # has several hundred triangles, and matplotlib batches a
            # single collection's draw call far faster than that many
            # separate line artists.
            segments = []
            for i, j, k in triangles:
                segments += [(points[i], points[j]),
                             (points[j], points[k]),
                             (points[k], points[i])]
            ax.add_collection(LineCollection(
                segments, colors=SUBDIVISION_COLOR, linewidths=0.6, zorder=2))

        ax.plot([p[0] for p in verts], [p[1] for p in verts], "o",
                 color=VERTEX_COLOR, markersize=VERTEX_MARKER_SIZE,
                 markeredgewidth=0, zorder=3)

        ax.set_title(f"{POLYGON_NAMES[n]} (n={n})", color=theme["fg"], fontsize=11)
        ax.set_aspect("equal")
        # Same range on every subplot (not autoscaled to each polygon's
        # own bounding box) so a unit edge length -- and the mesh
        # triangles -- render at the same size everywhere.
        ax.set_xlim(-AXIS_HALF_EXTENT, AXIS_HALF_EXTENT)
        ax.set_ylim(-AXIS_HALF_EXTENT, AXIS_HALF_EXTENT)
        ax.set_axis_off()

    def draw(self):
        self.fig.patch.set_facecolor(PLOT_THEME["bg"])

        for ax_row, n_row in zip(self.axes, POLYGON_GRID):
            for ax, n in zip(ax_row, n_row):
                self._draw_polygon(ax, n)

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
