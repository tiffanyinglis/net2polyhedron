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
  a real instance there (at the click point) and disarms the tool -- it
  is NOT left selected afterward (a freshly dropped shape used to become
  the selected one; changed at the user's request). Shapes are drawn in
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
- **Edge connections**: every shape already on the canvas (not a still-
  armed/not-yet-dropped ghost) has a small circular handle at the
  midpoint of each of its edges -- selecting the shape first is NOT
  required (an earlier version needed that, so starting a connection
  took two clicks: select the shape, then click its handle; now a single
  click straight onto any handle starts one, whether or not that shape
  happens to be selected). A handle that's already the endpoint of a
  real connection is a solid filled dot ("occupied") and stays visible
  all the time; one that isn't is an UNFILLED (outline-only) ring that
  only shows up once the cursor is close enough to it -- showing every
  free handle on every shape at all times was tried first and just read
  as clutter across a canvas with more than a couple of shapes. The
  reveal distance is the exact same one a click needs to actually hit
  the handle, so "visible" and "clickable" never disagree. Click-click,
  not click-drag:
  clicking a handle DESELECTS the shape (its outline stops being
  highlighted, if it happened to be selected at all) and "arms" a
  pending connection from that edge instead -- the POINT becomes the
  selected thing now, shown as the one handle lit red, rather than the
  whole shape (the same idea as arming a palette shape) -- and a red
  line (the same color a selection gets) then follows the mouse from it.
  Getting close enough to one of an OTHER shape's own handles (not just
  anywhere over its body) lights up that ONE handle -- not the whole
  shape -- red, as a purely visual "this is a valid target, right here"
  cue; the rest of that shape (its outline included) stays its normal,
  unselected look.
  A SECOND click then either completes the connection onto whichever
  handle is CURRENTLY lit that way, or cancels the pending attempt with
  no connection made if nothing is lit right now (own shape, empty
  background, a shape's body without being near any of its handles, or
  anywhere else) -- the same proximity check drives both the highlight
  and what a click can actually complete onto, so a connection is never
  made onto something that wasn't visibly about to happen first. A
  cancel doesn't swallow the click either way -- it still gets to do its
  normal job otherwise (select a shape, deselect, etc.). A made
  connection (drawn as a thin light-grey line between the two edges'
  midpoints from then on, tracking both shapes if either moves/rotates)
  deselects everything. A connection can itself be clicked (selecting it
  turns it red and deselects any shape) and deleted with Delete, exactly
  like a shape. Deleting either shape a connection touches removes the
  connection too, since a connection with a missing endpoint is
  meaningless.
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

import colorsys
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

import sv_ttk
from PIL import Image, ImageColor, ImageDraw, ImageTk

import common.paths  # noqa: F401 -- import side effect: adds src/ to sys.path for utils.*
from common.ui_theme import PLOT_THEME
from utils.geometry.polygon_geom import regular_polygon_vertices

# Palette entries, in display order.
POLYGON_NS = [3, 4, 5, 6, 7, 8]

# One FIXED color per polygon type (never per-instance), each an
# explicit (hue_deg, lightness, saturation) rather than one formula
# swept evenly across all 6 -- started that way (an even hue gradient,
# green -> blue -> purple, flat lightness/saturation throughout except
# a darker/less-saturated override for two green entries -- see git
# history), but per-color tweaks since (dropping the first green and
# shifting the rest up, inserting a new hue between the darker blue and
# the purple, lightening that darker blue, darkening the turquoise) left
# the hues unevenly spaced and several with their own lightness/
# saturation -- an explicit table reads more clearly at this point than
# a formula with growing exceptions bolted onto it. Order matches
# POLYGON_NS (triangle..8-gon); base lightness/saturation is 0.50/0.65
# (medium / medium-high, not maxed-out) except where a color's own tweak
# departs from it.
_POLYGON_HLS = [
    (136, 0.38, 0.50),  # triangle: green (darker/less saturated -- the
                         # untouched one of what used to be two greens)
    (172, 0.40, 0.65),  # square: turquoise, darkened a bit
    (208, 0.50, 0.65),  # pentagon: blue
    (244, 0.58, 0.65),  # hexagon: darker blue, lightened a bit
    (262, 0.50, 0.65),  # 7-gon: violet (new -- between the darker blue and purple)
    (280, 0.50, 0.65),  # 8-gon: purple
]


def _hls_hex(hue_deg, lightness, saturation):
    r, g, b = colorsys.hls_to_rgb(hue_deg / 360.0, lightness, saturation)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


POLYGON_COLORS = {n: _hls_hex(*hls) for n, hls in zip(POLYGON_NS, _POLYGON_HLS)}

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

# Red -- none of the polygon fill colors above (green/blue/purple hues)
# are anywhere near red, so it reads as clearly "selected/active"
# without being confusable with any shape's own fill.
SELECTION_OUTLINE_COLOR = "red"
SELECTION_OUTLINE_WIDTH = 2.0

# Edge-connection handles/lines. Sizes are constant SCREEN pixels (not
# scaled by view_scale), same as SELECTION_OUTLINE_WIDTH above -- UI
# chrome that stays a fixed size regardless of how zoomed-in the content
# is, rather than handles that would themselves balloon at high zoom.
EDGE_HANDLE_RADIUS = 5.0
EDGE_HANDLE_OUTLINE_WIDTH = 1.5
HANDLE_HIT_RADIUS = 9.0
CONNECTION_HIT_RADIUS = 6.0
# A handle's resting color, when its shape is neither selected nor the
# current hover target of a pending connection -- SELECTION_OUTLINE_COLOR
# is used instead in those two cases (see _redraw), so a handle reads as
# "active" in the same color a selection does, and plain white otherwise.
HANDLE_COLOR = "white"
CONNECTION_COLOR = "#b0b0b0"
CONNECTION_WIDTH = 1.5
CONNECTION_SELECTED_WIDTH = 2.5

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


def _point_segment_distance(point, a, b):
    """Shortest distance from `point` to the line SEGMENT a->b (not the
    infinite line) -- used to hit-test a click against a thin connection
    line, which has no interior to point-in-polygon test against."""
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


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

        # [{"id", "a_shape", "a_edge", "b_shape", "b_edge"}, ...] -- edge
        # indices are stable across a shape's own move/rotation (they
        # just name a position in its local vertex loop), so a
        # connection only ever stores ids/indices, never coordinates.
        self.connections = []
        self._next_connection_id = 1
        self.selected_connection_id = None
        # {"from_shape", "from_edge"} once a handle's been clicked to
        # start a connection, awaiting the SECOND click that either
        # completes or cancels it; None otherwise. _pending_cursor_screen
        # is the live mouse position, for drawing the line following it.
        self._connection_pending = None
        self._pending_cursor_screen = None
        # Shape/edge the pending connection is currently close enough to
        # complete onto, or (None, None) if it isn't near any right now
        # -- both None together always, never just one. Lit up like a
        # selection but never actually assigned to self.selected_id. The
        # SAME two fields drive both the highlight (_redraw) and what a
        # completing click actually connects to (_complete_or_cancel_
        # pending_connection just reads them, rather than re-hit-testing
        # the release point itself) -- so a connection can only ever be
        # made onto something that was visibly highlighted first.
        self._hover_shape_id = None
        self._hover_edge_index = None
        # Live mouse position over the canvas (None once it leaves) --
        # tracked unconditionally, not just while armed/pending, purely
        # so an unjoined handle can reveal itself only once the cursor
        # is genuinely close to it (see _redraw) rather than showing
        # every free handle on every shape all the time.
        self._cursor_screen = None

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
        self.canvas.bind("<Leave>", self._on_canvas_leave)
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

    def _shape_edge_midpoints(self, shape):
        """World-space midpoint of each of the shape's edges, in the
        same order as its vertex loop -- edge i runs from vertex i to
        vertex (i+1) % n, so index i is a stable handle for that edge
        across any later move/rotation."""
        verts = self._shape_world_vertices(shape)
        n = len(verts)
        return [((verts[i][0] + verts[(i + 1) % n][0]) / 2,
                 (verts[i][1] + verts[(i + 1) % n][1]) / 2) for i in range(n)]

    def _hit_test_any_edge_handle(self, screen_x, screen_y, exclude_shape_id=None):
        """Nearest edge handle belonging to any shape OTHER than
        `exclude_shape_id`, within HANDLE_HIT_RADIUS screen pixels of the
        given point, or None. Every placed shape's every edge handle is
        clickable this way -- there's no "must be selected first" gate
        (that WAS the rule at one point; dropped since it took two
        clicks, select-the-shape then click-its-handle, to start a
        connection at all -- see module docstring). Also used, with
        `exclude_shape_id` set to a pending connection's own origin
        shape, for both hover highlighting (_on_canvas_motion) and
        deciding what a completing click actually connects to
        (_complete_or_cancel_pending_connection just reads the hover
        state this leaves behind, rather than re-running this itself) --
        the two MUST agree, so nothing ever connects without having
        first been visibly highlighted."""
        best, best_dist = None, HANDLE_HIT_RADIUS
        for shape in self.shapes:
            if shape["id"] == exclude_shape_id:
                continue
            for edge_index, (mx, my) in enumerate(self._shape_edge_midpoints(shape)):
                sx, sy = self._world_to_screen(mx, my)
                dist = math.hypot(screen_x - sx, screen_y - sy)
                if dist <= best_dist:
                    best, best_dist = {"shape_id": shape["id"], "edge_index": edge_index}, dist
        return best

    def _connection_endpoints(self, conn):
        """Screen-space (a, b) midpoints for a connection, or None if
        either shape it references no longer exists."""
        a_shape, b_shape = self._shape_by_id(conn["a_shape"]), self._shape_by_id(conn["b_shape"])
        if a_shape is None or b_shape is None:
            return None
        a = self._world_to_screen(*self._shape_edge_midpoints(a_shape)[conn["a_edge"]])
        b = self._world_to_screen(*self._shape_edge_midpoints(b_shape)[conn["b_edge"]])
        return a, b

    def _hit_test_connection(self, screen_x, screen_y):
        """Id of the connection whose line passes within
        CONNECTION_HIT_RADIUS screen pixels of the given point, or None."""
        best, best_dist = None, CONNECTION_HIT_RADIUS
        for conn in self.connections:
            endpoints = self._connection_endpoints(conn)
            if endpoints is None:
                continue
            dist = _point_segment_distance((screen_x, screen_y), *endpoints)
            if dist < best_dist:
                best, best_dist = conn["id"], dist
        return best

    def _remove_shape(self, shape_id):
        """Deletes the shape and every connection touching it -- a
        connection with a missing endpoint has nothing left to draw a
        line between, so it can't be left dangling."""
        self.connections = [c for c in self.connections
                             if c["a_shape"] != shape_id and c["b_shape"] != shape_id]
        self.shapes = [s for s in self.shapes if s["id"] != shape_id]

    # ---- palette ----

    def _on_palette_clicked(self, n):
        self.armed_n = None if self.armed_n == n else n
        self._ghost_world_xy = None
        if self.armed_n is not None:
            # Arming a new shape to place is a distinct action from
            # working with whatever's already on the canvas -- picking
            # one up shouldn't leave an unrelated shape looking selected.
            self.selected_id = None
            self.selected_connection_id = None
        for other_n, icon in self._palette_canvases.items():
            icon.configure(highlightbackground=(
                "white" if other_n == self.armed_n else PLOT_THEME["bg"]))
        self._redraw()

    def on_clear_clicked(self):
        self.shapes.clear()
        self.connections.clear()
        self.selected_id = None
        self.selected_connection_id = None
        self._drag_state = None
        self._redraw()

    # ---- canvas: configure / motion ----

    def _on_canvas_configure(self, event):
        if not self._offset_initialized:
            self.offset_x, self.offset_y = event.width / 2, event.height / 2
            self._offset_initialized = True
            self._redraw()

    def _on_canvas_motion(self, event):
        # Tracked unconditionally (not just while armed/pending) so an
        # unjoined handle can reveal itself on proximity alone -- see
        # _redraw -- so this always redraws, not just in the two
        # branches below.
        self._cursor_screen = (event.x, event.y)
        if self._connection_pending is not None:
            self._pending_cursor_screen = (event.x, event.y)
            # PROXIMITY TO A HANDLE, not just being anywhere over the
            # shape's body -- this is the exact same test
            # _complete_or_cancel_pending_connection relies on to decide
            # what a completing click connects to, so a shape only ever
            # lights up when it's actually a valid, connectable target.
            target = self._hit_test_any_edge_handle(
                event.x, event.y, exclude_shape_id=self._connection_pending["from_shape"])
            self._hover_shape_id = None if target is None else target["shape_id"]
            self._hover_edge_index = None if target is None else target["edge_index"]
        elif self.armed_n is not None:
            self._ghost_world_xy = self._screen_to_world(event.x, event.y)
        self._redraw()

    def _on_canvas_leave(self, _event):
        self._cursor_screen = None
        self._redraw()

    # ---- canvas: click-to-drop / select / drag / connect ----

    def _on_canvas_press(self, event):
        if self.armed_n is not None:
            wx, wy = self._screen_to_world(event.x, event.y)
            self._drop_shape(self.armed_n, wx, wy)
            self._on_palette_clicked(self.armed_n)  # disarm (toggles current off)
            return

        if self._connection_pending is not None:
            if self._complete_or_cancel_pending_connection():
                # A completed connection deselects everything and stops
                # here -- letting this SAME click fall through to the
                # ordinary checks below would immediately re-select the
                # handle it just landed on (or the new connection line,
                # which passes through that exact point).
                self._redraw()
                return
            # A cancel, in contrast, doesn't consume the click: fall
            # through so it still does its normal job (select a handle/
            # connection/shape, or deselect) -- it just never creates a
            # SECOND connection.

        handle = self._hit_test_any_edge_handle(event.x, event.y)
        if handle is not None:
            self._connection_pending = {"from_shape": handle["shape_id"],
                                         "from_edge": handle["edge_index"]}
            self._pending_cursor_screen = (event.x, event.y)
            # The POINT becomes the selected thing now, not the shape --
            # deselecting here is what makes _redraw stop outlining the
            # whole shape and light up only this one handle instead.
            self.selected_id = None
            self.selected_connection_id = None
            self._redraw()
            return

        conn_hit = self._hit_test_connection(event.x, event.y)
        if conn_hit is not None:
            self.selected_connection_id = conn_hit
            self.selected_id = None
            self._drag_state = None
            self._redraw()
            return

        wx, wy = self._screen_to_world(event.x, event.y)
        hit = self._hit_test(wx, wy)
        self.selected_connection_id = None
        if hit is None:
            self.selected_id = None
            self._drag_state = None
        else:
            self.selected_id = hit["id"]
            self._drag_state = {"id": hit["id"], "start_world": (wx, wy),
                                 "start_center": (hit["cx"], hit["cy"])}
        self._redraw()

    def _complete_or_cancel_pending_connection(self):
        """The SECOND click of a click-click connection. Returns True
        and makes the connection if self._hover_shape_id/_edge_index are
        currently set (i.e. a valid target is CURRENTLY HIGHLIGHTED --
        deliberately reading this rather than re-hit-testing the click
        point itself, so a connection can only ever be made onto
        something the user actually saw light up first, never onto a
        target that silently stopped being valid a pixel before the
        click landed); returns False (no connection) if nothing is
        highlighted right now. Either way, self._connection_pending/
        _hover_shape_id/_edge_index are cleared before returning -- what
        the caller does with a False (whether to let the click fall
        through to its ordinary job) is its own decision, not this
        method's."""
        made = self._hover_shape_id is not None
        if made:
            self.connections.append({
                "id": self._next_connection_id,
                "a_shape": self._connection_pending["from_shape"],
                "a_edge": self._connection_pending["from_edge"],
                "b_shape": self._hover_shape_id, "b_edge": self._hover_edge_index,
            })
            self._next_connection_id += 1
            # A freshly-made connection deselects everything -- the
            # origin shape was selected (that's how its handle was
            # showing in the first place), but the connection itself is
            # the thing that just changed, not that shape.
            self.selected_id = None
            self.selected_connection_id = None
        self._connection_pending = None
        self._hover_shape_id = None
        self._hover_edge_index = None
        return made

    def _drop_shape(self, n, wx, wy):
        shape = {"id": self._next_shape_id, "n": n, "cx": wx, "cy": wy, "rotation": 0.0}
        self._next_shape_id += 1
        self.shapes.append(shape)

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
            self._remove_shape(self.selected_id)
            self.selected_id = None
            self._redraw()
        elif self.selected_connection_id is not None:
            self.connections = [c for c in self.connections if c["id"] != self.selected_connection_id]
            self.selected_connection_id = None
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

    def _draw_connection_line(self, a, b, selected):
        self.canvas.create_line(
            *a, *b, fill=SELECTION_OUTLINE_COLOR if selected else CONNECTION_COLOR,
            width=CONNECTION_SELECTED_WIDTH if selected else CONNECTION_WIDTH)

    def _draw_handle_circle(self, shape, edge_index, lit, joined):
        """lit (selected/hovered/the pending point itself) always wins,
        drawn filled red. Otherwise: filled white if `joined` (this edge
        already has a real connection on it -- a solid dot reads as
        "occupied"), or an UNFILLED (outline-only) white ring if it's
        free -- so an edge with nothing on it yet doesn't visually
        compete with real connection endpoints, at a glance, across a
        canvas full of shapes that now show every one of their handles
        all the time (see module docstring)."""
        mx, my = self._shape_edge_midpoints(shape)[edge_index]
        sx, sy = self._world_to_screen(mx, my)
        if lit:
            fill, outline = SELECTION_OUTLINE_COLOR, ""
        elif joined:
            fill, outline = HANDLE_COLOR, ""
        else:
            fill, outline = "", HANDLE_COLOR
        self.canvas.create_oval(sx - EDGE_HANDLE_RADIUS, sy - EDGE_HANDLE_RADIUS,
                                 sx + EDGE_HANDLE_RADIUS, sy + EDGE_HANDLE_RADIUS,
                                 fill=fill, outline=outline, width=EDGE_HANDLE_OUTLINE_WIDTH)

    def _redraw(self):
        self.canvas.delete("all")
        self._shape_photos = []
        for shape in self.shapes:
            screen_vertices = [self._world_to_screen(*wv) for wv in self._shape_world_vertices(shape)]
            self._draw_shape(screen_vertices, POLYGON_COLORS[shape["n"]], selected=shape["id"] == self.selected_id)

        for conn in self.connections:
            endpoints = self._connection_endpoints(conn)
            if endpoints is not None:
                # A connection highlights whenever it's explicitly
                # selected OR it touches the currently-selected shape --
                # the shape at its OTHER end stays its normal color (see
                # the shape-drawing loop above, which only lights up
                # self.selected_id), so only the line itself, not its
                # neighbour, reads as "part of this".
                highlighted = (conn["id"] == self.selected_connection_id
                               or self.selected_id in (conn["a_shape"], conn["b_shape"]))
                self._draw_connection_line(*endpoints, selected=highlighted)

        if self._connection_pending is not None:
            from_shape = self._shape_by_id(self._connection_pending["from_shape"])
            if from_shape is not None:
                anchor = self._world_to_screen(
                    *self._shape_edge_midpoints(from_shape)[self._connection_pending["from_edge"]])
                self._draw_connection_line(anchor, self._pending_cursor_screen, selected=True)

        # EVERY placed shape's EVERY edge gets a handle, always -- not
        # just the selected one -- so a connection can be started with a
        # single click straight onto any handle, with no "select the
        # shape first" step (see module docstring). A handle lights up
        # red if its own shape is SELECTED (every one of that shape's
        # edges, so any of them can be picked to start a connection
        # from), or it's the pending connection's own origin point
        # (`pending_point`, which needs to stay lit even though clicking
        # it just DESELECTED that shape -- see _on_canvas_press: the
        # POINT is the selected thing now, not the shape it belongs to)
        # or its CURRENT hover target (`hover_point`) -- deliberately
        # just that one edge, not every edge of the shape it's on: an
        # earlier version lit the whole target shape (mirroring how a
        # real selection looks), and the user asked for it to stop doing
        # that -- only the specific edge a second click would actually
        # complete onto lights up now, leaving the rest of that shape
        # (including its outline, in the shape-drawing loop above) at
        # its normal, unselected look. Otherwise a handle is filled
        # white if some connection already uses it, or an unfilled ring
        # if not (see _draw_handle_circle).
        pending_point = (None if self._connection_pending is None else
                          (self._connection_pending["from_shape"], self._connection_pending["from_edge"]))
        hover_point = (None if self._hover_shape_id is None else
                        (self._hover_shape_id, self._hover_edge_index))
        joined_points = set()
        for conn in self.connections:
            joined_points.add((conn["a_shape"], conn["a_edge"]))
            joined_points.add((conn["b_shape"], conn["b_edge"]))

        for shape in self.shapes:
            mids = self._shape_edge_midpoints(shape)
            for edge_index, (mx, my) in enumerate(mids):
                point = (shape["id"], edge_index)
                lit = shape["id"] == self.selected_id or point in (pending_point, hover_point)
                joined = point in joined_points
                if not lit and not joined:
                    # An unjoined, not-currently-active handle only
                    # reveals itself once the cursor is genuinely close
                    # -- HANDLE_HIT_RADIUS again, same as what actually
                    # clicking it requires, so "visible" and "clickable"
                    # never disagree (same principle as the pending-
                    # connection hover check above). Showing every free
                    # handle on every shape all the time was tried first
                    # and read as visual noise across a canvas with more
                    # than a couple of shapes.
                    if self._cursor_screen is None:
                        continue
                    sx, sy = self._world_to_screen(mx, my)
                    cx, cy = self._cursor_screen
                    if math.hypot(cx - sx, cy - sy) > HANDLE_HIT_RADIUS:
                        continue
                self._draw_handle_circle(shape, edge_index, lit=lit, joined=joined)

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
