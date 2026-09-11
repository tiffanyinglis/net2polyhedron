"""Interactive Builder -- a 2D shape-placement canvas, unrelated to
solving/folding anything: pick a regular polygon from a left-side
palette (triangle through 8-gon, each a fixed color), click to drop
instances of it into a pan/zoomable drawing area on the right, then
select/drag/rotate/delete them.

    python src/apps/interactive_builder_app/app.py

Interaction model:

- **Palette (pick up)**: clicking a palette icon "arms" that polygon
  type (highlighted with a white border) -- a ghost preview of it then
  follows the mouse over the drawing area, drawn exactly like a real,
  currently-selected shape (solid fill, white outline) rather than some
  lesser "not real yet" look, since it's about to be dropped as-is.
  Clicking the SAME icon again disarms it (puts it back). Clicking a
  DIFFERENT icon swaps which type is armed, with no need to drop the
  first one first. Every icon has the same centre-to-vertex radius
  regardless of its side count (unlike a shape actually placed on the
  canvas, which shares its EDGE length with every other placed shape
  instead) -- so the palette itself reads as a clean, evenly-sized row
  of options.
- **Drawing area (drop)**: clicking anywhere while a type is armed drops
  a real instance there (at the click point) and disarms the tool. A
  freshly dropped shape becomes the selected one. Shapes are drawn in
  the order they're stored, so a later drop renders on top of anything
  it overlaps.
- **Selection**: with no tool armed, clicking a shape selects it (thin
  white outline) and deselects whatever was selected before; clicking
  empty space deselects. At most one shape is ever selected. Delete (the
  key, checked globally via bind_all since this app has no text-entry
  widget for it to collide with) removes the selected shape.
- **Drag**: pressing on a shape both selects it and arms a drag -- moving
  the mouse while the button stays down drags the shape by the same
  screen-space delta, converted through the current pan/zoom transform.
  A plain click (no motion) is just a zero-distance drag, so no separate
  click-vs-drag code path is needed.
- **Rotate**: with a shape selected, holding the RIGHT button down and
  dragging rotates that shape about its own centre, tracking the mouse's
  angle around it (a trackball-style drag, not an absolute angle readout).
  With no shape selected, right-drag instead pans the view (see below) --
  the two never conflict, since one or the other is always the case.
- **Pan/zoom**: with no shape selected, right-click-drag pans -- dragging
  the background moves the whole view WITH the drag, the same direction
  as the cursor, like grabbing and sliding the canvas itself under a
  fixed cursor. The scroll wheel zooms about
  the CURSOR position (the world point under the cursor is solved for at
  the OLD scale and pinned there again at the new one, so zooming doesn't
  drift the shape under the mouse away from it).

Shapes are stored in "world" coordinates, independent of the current
pan/zoom -- `_world_to_screen`/`_screen_to_world` are the only two places
that ever convert between the two, so panning/zooming is purely a
transform applied at draw (and hit-test/drag) time, never a rewrite of
stored positions.

Rendering (`_rasterize_polygon`): a plain `tk.Canvas` polygon item has no
anti-aliasing at all in Tk -- every edge comes out visibly jagged,
especially on a diagonal side of a pentagon/hexagon/etc. Each polygon
(every placed shape, the ghost preview, and every palette icon) is
instead rasterized through Pillow at SUPERSAMPLE-times its final pixel
size, then downsampled with a LANCZOS resize -- the standard supersample-
and-downsample trick for anti-aliasing something you can render bigger
than you need. Only each polygon's own (padded) bounding box is
rasterized, not the whole canvas, so cost stays proportional to the
shapes actually on screen rather than to canvas area. The resulting
per-shape RGBA image is blitted onto the canvas with `create_image`; the
canvas is otherwise a plain solid-color background, so hit-testing/
dragging/rotating logic never has to look at what's drawn -- it works
entirely in world coordinates against each shape's own stored geometry,
exactly as it did before this module used Pillow at all.
"""
import math
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

import sv_ttk
from PIL import Image, ImageColor, ImageDraw, ImageTk

import common.paths  # noqa: F401 -- import side effect: adds src/ to sys.path for utils.*
from common.ui_theme import PLOT_THEME, FACE_COLORS
from utils.geometry.polygon_geom import regular_polygon_vertices

# Palette entries, in display order.
POLYGON_NS = [3, 4, 5, 6, 7, 8]

# One FIXED color per polygon type (never per-instance, unlike
# FACE_COLORS' usual cycling-by-index use elsewhere in this project) --
# reuses ui_theme's existing high-variety palette rather than inventing a
# new one. Triangle uses FACE_COLORS[6] (a bright yellow) rather than
# FACE_COLORS[0] (a dark navy that read as too dim against the dark
# background); 4..8 take FACE_COLORS[1..5], still unique and mutually
# distinct.
POLYGON_COLORS = {3: FACE_COLORS[6], 4: FACE_COLORS[1], 5: FACE_COLORS[2],
                   6: FACE_COLORS[3], 7: FACE_COLORS[4], 8: FACE_COLORS[5]}

# Regular-polygon local vertices (centered on origin), precomputed once
# per n rather than on every redraw -- a placed shape's world vertices
# are just these offset by its own (cx, cy). Placed shapes share a
# common EDGE length (like every other net/mesh in this project), so
# bigger-n shapes end up with a bigger circumradius, unlike the palette
# icons below.
DEFAULT_SHAPE_EDGE_LENGTH = 70.0
_LOCAL_VERTICES = {n: regular_polygon_vertices(n, DEFAULT_SHAPE_EDGE_LENGTH) for n in POLYGON_NS}


def _vertices_with_radius(n, radius):
    """Regular n-gon vertices (centered on origin) with the given
    CIRCUMRADIUS (centre-to-vertex distance) rather than a given edge
    length -- solves edge_length = 2*radius*sin(pi/n) and defers to
    regular_polygon_vertices for the actual vertex positions."""
    return regular_polygon_vertices(n, edge_length=2 * radius * math.sin(math.pi / n))


ICON_SIZE = 84
# Every palette icon shares this circumradius regardless of side count
# (unlike DEFAULT_SHAPE_EDGE_LENGTH's shared EDGE length above) so the
# palette reads as evenly sized; comfortably inside ICON_SIZE/2 = 42 so
# no icon's corners get clipped against its own canvas.
ICON_RADIUS = 30.0
_ICON_VERTICES = {n: _vertices_with_radius(n, ICON_RADIUS) for n in POLYGON_NS}

SELECTION_OUTLINE_COLOR = "white"
SELECTION_OUTLINE_WIDTH = 2.0

# Supersampling factor for _rasterize_polygon's anti-aliasing -- render
# at this many times final size, then LANCZOS-downsample. Higher looks
# marginally smoother but costs roughly its square in raster pixels;
# 4 already reads as smooth at the sizes this app draws at.
SUPERSAMPLE = 4

ZOOM_STEP = 1.1
ZOOM_MIN = 0.2
ZOOM_MAX = 5.0

# Same idea as inflate_polyhedron_app's UI_FONT_SCALE: applied once, at
# startup, to every named Tk/ttk font, so the whole app's text grows
# together rather than each widget needing its own hardcoded size.
UI_FONT_SCALE = 1.3


def _enable_windows_dpi_awareness():
    """Tells Windows this process renders at its own true resolution --
    without this, Tk draws at a virtualized 96 DPI and Windows bitmap-
    stretches the result to the display's real scaling, which is what
    makes every shape (and text) look soft/blurry on a scaled display.
    A no-op everywhere else."""
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _point_in_polygon(point, vertices):
    """point: (x, y); vertices: [(x, y), ...] in order. Standard
    ray-casting test -- True iff point is inside the (possibly
    non-convex) polygon."""
    x, y = point
    inside = False
    n = len(vertices)
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _rgba(hex_color, alpha=255):
    r, g, b = ImageColor.getrgb(hex_color)
    return r, g, b, alpha


def _rasterize_polygon(screen_vertices, fill_hex, outline_hex=None, outline_width=0):
    """screen_vertices: [(x, y), ...] in CANVAS pixel space. Renders just
    this polygon's own (padded) bounding box, supersampled by
    SUPERSAMPLE and LANCZOS-downsampled for anti-aliased edges -- see
    module docstring's Rendering section for why this exists instead of
    a plain tk.Canvas polygon item. Returns (PhotoImage, (left, top)) --
    the caller places it with `canvas.create_image(left, top, anchor="nw",
    image=photo)` and must keep a reference to the PhotoImage itself
    (Tk drops a garbage-collected one)."""
    xs = [x for x, _ in screen_vertices]
    ys = [y for _, y in screen_vertices]
    pad = outline_width + 2
    left, top = min(xs) - pad, min(ys) - pad
    width = max(1, math.ceil(max(xs) - left + pad))
    height = max(1, math.ceil(max(ys) - top + pad))

    big = Image.new("RGBA", (width * SUPERSAMPLE, height * SUPERSAMPLE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    local = [((x - left) * SUPERSAMPLE, (y - top) * SUPERSAMPLE) for x, y in screen_vertices]
    draw.polygon(local, fill=_rgba(fill_hex))
    if outline_hex and outline_width > 0:
        draw.line(local + [local[0]], fill=_rgba(outline_hex),
                   width=max(1, round(outline_width * SUPERSAMPLE)), joint="curve")
    small = big.resize((width, height), Image.LANCZOS)
    return ImageTk.PhotoImage(small), (left, top)


class InteractiveBuilderApp:
    def __init__(self, root):
        self.root = root
        root.title("Interactive Builder")
        root.geometry("1100x700")
        root.minsize(700, 450)

        sv_ttk.set_theme("dark")
        self._scale_ui_fonts()

        # in z-order, back to front: [{"id", "n", "cx", "cy", "rotation"}, ...]
        self.shapes = []
        self._next_shape_id = 1
        self.selected_id = None
        self.armed_n = None
        self._ghost_world_xy = None
        self._drag_state = None
        self._pan_last_xy = None
        self._rotate_state = None
        self._shape_photos = []  # keeps this redraw's PhotoImages alive (Tk drops GC'd ones)
        self._icon_photos = {}

        # View transform: screen = world * view_scale + (offset_x, offset_y).
        # offset starts at (0, 0) and is recentred once, on the canvas's
        # first real <Configure>, once its actual size is known.
        self.view_scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._offset_initialized = False

        self._palette_canvases = {}
        self._build_ui()

    def _scale_ui_fonts(self):
        """Scales every named Tk/ttk font by UI_FONT_SCALE, once at
        startup, right after sv_ttk.set_theme -- see
        inflate_polyhedron_app's own _scale_ui_fonts for why this (rather
        than a per-widget font= override) is what reaches sv_ttk's own
        Tcl-level fonts too. A size of 0 (some internal fonts use this)
        means "use the platform default" and stays that way."""
        for name in tkfont.names(self.root):
            font = tkfont.nametofont(name, root=self.root)
            size = font.cget("size")
            if size == 0:
                continue
            sign = -1 if size < 0 else 1
            font.configure(size=sign * round(abs(size) * UI_FONT_SCALE))

    def _build_ui(self):
        left = ttk.Frame(self.root, padding=12)
        left.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left, text="Shapes", font=("TkDefaultFont", round(11 * UI_FONT_SCALE), "bold")).pack(
            anchor=tk.W, pady=(0, 8))
        for n in POLYGON_NS:
            self._build_palette_entry(left, n)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)
        ttk.Button(left, text="Clear", command=self.on_clear_clicked).pack(fill=tk.X)

        # highlightthickness/-background give the drawing area a visible
        # border, so it reads as a distinct, clearly-boxed region rather
        # than blending into the rest of the (also dark) window.
        self.canvas = tk.Canvas(self.root, bg=PLOT_THEME["bg"],
                                 highlightthickness=1, highlightbackground=PLOT_THEME["fg"])
        self.canvas.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(0, 12), pady=12)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-3>", self._on_right_press)
        self.canvas.bind("<B3-Motion>", self._on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        # Windows/macOS deliver <MouseWheel> with event.delta; Linux (X11)
        # delivers wheel motion as Button-4/Button-5 clicks instead --
        # binding all three covers every platform this app might run on.
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<Button-4>", self._on_zoom)
        self.canvas.bind("<Button-5>", self._on_zoom)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # bind_all rather than bind -- this app has no text-entry widget
        # for a Delete keystroke to collide with, and the canvas doesn't
        # always hold keyboard focus.
        self.root.bind_all("<Delete>", self._on_delete_key)

    def _build_palette_entry(self, parent, n):
        """One palette icon: a small Canvas showing the regular n-gon in
        its own fixed POLYGON_COLORS color (no text label -- the shape
        itself is the only affordance), bound to arm/disarm that
        polygon type on click. Rasterized once, at build time, via
        _rasterize_polygon -- icons never change, so there's no reason
        to re-rasterize one on every redraw the way a placed shape does."""
        icon = tk.Canvas(parent, width=ICON_SIZE, height=ICON_SIZE,
                          bg=PLOT_THEME["bg"], highlightthickness=2,
                          highlightbackground=PLOT_THEME["bg"])
        icon.pack(fill=tk.X, pady=3)
        cx, cy = ICON_SIZE / 2, ICON_SIZE / 2
        screen_vertices = [(vx + cx, vy + cy) for vx, vy in _ICON_VERTICES[n]]
        photo, (left, top) = _rasterize_polygon(screen_vertices, POLYGON_COLORS[n])
        self._icon_photos[n] = photo  # keep alive -- Tk drops a GC'd PhotoImage
        icon.create_image(left, top, anchor="nw", image=photo)
        icon.bind("<Button-1>", lambda _e, n=n: self._on_palette_clicked(n))
        self._palette_canvases[n] = icon

    # ---- coordinate transform ----

    def _world_to_screen(self, wx, wy):
        return wx * self.view_scale + self.offset_x, wy * self.view_scale + self.offset_y

    def _screen_to_world(self, sx, sy):
        return (sx - self.offset_x) / self.view_scale, (sy - self.offset_y) / self.view_scale

    def _shape_world_vertices(self, shape):
        """The shape's own local vertices, rotated about the origin by
        its stored `rotation` (radians), then translated to its (cx, cy)
        -- the single source of truth both drawing and hit-testing use,
        so a rotated shape's clickable area always matches what's drawn."""
        theta = shape["rotation"]
        c, s = math.cos(theta), math.sin(theta)
        return [(shape["cx"] + vx * c - vy * s, shape["cy"] + vx * s + vy * c)
                for vx, vy in _LOCAL_VERTICES[shape["n"]]]

    def _shape_by_id(self, shape_id):
        return next((s for s in self.shapes if s["id"] == shape_id), None)

    def _hit_test(self, wx, wy):
        """Topmost shape (last in z-order) whose polygon contains the
        given world point, or None."""
        for shape in reversed(self.shapes):
            if _point_in_polygon((wx, wy), self._shape_world_vertices(shape)):
                return shape
        return None

    # ---- palette ----

    def _on_palette_clicked(self, n):
        self.armed_n = None if self.armed_n == n else n
        self._ghost_world_xy = None
        for other_n, icon in self._palette_canvases.items():
            icon.configure(highlightbackground=(
                "white" if other_n == self.armed_n else PLOT_THEME["bg"]))
        self._redraw()

    def on_clear_clicked(self):
        self.shapes.clear()
        self.selected_id = None
        self._drag_state = None
        self._redraw()

    # ---- canvas: configure / motion ----

    def _on_canvas_configure(self, event):
        if not self._offset_initialized:
            self.offset_x, self.offset_y = event.width / 2, event.height / 2
            self._offset_initialized = True
            self._redraw()

    def _on_canvas_motion(self, event):
        if self.armed_n is not None:
            self._ghost_world_xy = self._screen_to_world(event.x, event.y)
            self._redraw()

    # ---- canvas: click-to-drop / select / drag ----

    def _on_canvas_press(self, event):
        wx, wy = self._screen_to_world(event.x, event.y)
        if self.armed_n is not None:
            self._drop_shape(self.armed_n, wx, wy)
            self._on_palette_clicked(self.armed_n)  # disarm (toggles current off)
            return
        hit = self._hit_test(wx, wy)
        if hit is None:
            self.selected_id = None
            self._drag_state = None
        else:
            self.selected_id = hit["id"]
            self._drag_state = {"id": hit["id"], "start_world": (wx, wy),
                                 "start_center": (hit["cx"], hit["cy"])}
        self._redraw()

    def _drop_shape(self, n, wx, wy):
        shape = {"id": self._next_shape_id, "n": n, "cx": wx, "cy": wy, "rotation": 0.0}
        self._next_shape_id += 1
        self.shapes.append(shape)
        self.selected_id = shape["id"]

    def _on_canvas_drag(self, event):
        if self._drag_state is None:
            return
        wx, wy = self._screen_to_world(event.x, event.y)
        start_wx, start_wy = self._drag_state["start_world"]
        start_cx, start_cy = self._drag_state["start_center"]
        shape = self._shape_by_id(self._drag_state["id"])
        if shape is not None:
            shape["cx"] = start_cx + (wx - start_wx)
            shape["cy"] = start_cy + (wy - start_wy)
            self._redraw()

    def _on_canvas_release(self, _event):
        self._drag_state = None

    def _on_delete_key(self, _event):
        if self.selected_id is not None:
            self.shapes = [s for s in self.shapes if s["id"] != self.selected_id]
            self.selected_id = None
            self._redraw()

    # ---- canvas: right button -- rotate selected shape, else pan ----

    def _on_right_press(self, event):
        """Right-drag has two mutually exclusive meanings, chosen once
        here at press time: rotate the selected shape (if any), else pan
        the view. `_rotate_state`/`_pan_last_xy` are never both set."""
        if self.selected_id is not None:
            shape = self._shape_by_id(self.selected_id)
            cx, cy = self._world_to_screen(shape["cx"], shape["cy"])
            self._rotate_state = {"id": shape["id"],
                                   "last_angle": math.atan2(event.y - cy, event.x - cx)}
            self._pan_last_xy = None
        else:
            self._pan_last_xy = (event.x, event.y)
            self._rotate_state = None

    def _on_right_drag(self, event):
        if self._rotate_state is not None:
            shape = self._shape_by_id(self._rotate_state["id"])
            if shape is None:
                return
            cx, cy = self._world_to_screen(shape["cx"], shape["cy"])
            angle = math.atan2(event.y - cy, event.x - cx)
            shape["rotation"] += angle - self._rotate_state["last_angle"]
            self._rotate_state["last_angle"] = angle
            self._redraw()
            return
        if self._pan_last_xy is None:
            return
        last_x, last_y = self._pan_last_xy
        # Same direction as the drag -- dragging the background moves
        # the view as if the canvas itself were being grabbed and slid
        # along with the cursor, not pulled out from under a fixed one.
        self.offset_x += event.x - last_x
        self.offset_y += event.y - last_y
        self._pan_last_xy = (event.x, event.y)
        self._redraw()

    def _on_right_release(self, _event):
        self._rotate_state = None
        self._pan_last_xy = None

    def _on_zoom(self, event):
        """Scroll-to-zoom, centered on the cursor: solves for the world
        point under the cursor at the OLD scale, then re-derives the
        offset so that same world point lands back under the cursor at
        the NEW scale -- without this, zooming would drift whatever's
        under the mouse sideways instead of zooming into/out of it."""
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / ZOOM_STEP
        else:
            factor = ZOOM_STEP
        new_scale = max(ZOOM_MIN, min(ZOOM_MAX, self.view_scale * factor))
        wx, wy = self._screen_to_world(event.x, event.y)
        self.view_scale = new_scale
        self.offset_x = event.x - wx * self.view_scale
        self.offset_y = event.y - wy * self.view_scale
        self._redraw()

    # ---- drawing ----

    def _draw_shape(self, screen_vertices, fill_hex, selected):
        photo, (left, top) = _rasterize_polygon(
            screen_vertices, fill_hex,
            outline_hex=SELECTION_OUTLINE_COLOR if selected else None,
            outline_width=SELECTION_OUTLINE_WIDTH if selected else 0)
        self._shape_photos.append(photo)  # keep alive -- Tk drops a GC'd PhotoImage
        self.canvas.create_image(left, top, anchor="nw", image=photo)

    def _redraw(self):
        self.canvas.delete("all")
        self._shape_photos = []
        for shape in self.shapes:
            screen_vertices = [self._world_to_screen(*wv) for wv in self._shape_world_vertices(shape)]
            self._draw_shape(screen_vertices, POLYGON_COLORS[shape["n"]],
                              selected=shape["id"] == self.selected_id)
        if self.armed_n is not None and self._ghost_world_xy is not None:
            # Drawn exactly like a real, selected shape (solid fill, white
            # outline) -- it's the shape about to be dropped as-is, not a
            # lesser preview.
            gx, gy = self._ghost_world_xy
            screen_vertices = [self._world_to_screen(gx + vx, gy + vy)
                                for vx, vy in _LOCAL_VERTICES[self.armed_n]]
            self._draw_shape(screen_vertices, POLYGON_COLORS[self.armed_n], selected=True)


def main():
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    InteractiveBuilderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
