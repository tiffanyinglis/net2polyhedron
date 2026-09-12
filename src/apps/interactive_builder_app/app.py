"""Interactive Builder -- a 2D shape-placement canvas, unrelated to
solving/folding anything: pick a regular polygon from a left-side
palette (triangle through 8-gon, each a fixed color), click to drop
instances of it into a pan/zoomable drawing area on the right, then
select/drag/rotate/delete them. File > Load/Save round-trips the
whole canvas to/from a stretchy-mesh-format .json (see the "net JSON
import/export" section below, near _layout_faces_with_gap).

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
  a real instance there (at the click point), disarms the tool, and
  LEAVES it selected (so it can be immediately rotated, connected, or
  copied with no extra click). Shapes are drawn in the order they're
  stored, so a later drop renders on top of anything it overlaps.
- **Selection (self.selected_ids, possibly more than one shape)**: with
  no tool armed, clicking a shape selects JUST it, replacing whatever was
  selected before, UNLESS it's already part of the current selection (in
  which case the whole group stays selected, so it can be dragged/
  rotated/deleted together -- see Drag/Rotate below); clicking empty
  space deselects everything. Two ways to build up a multi-shape
  selection:
  - **Ctrl+click** a shape to TOGGLE just it in or out of the selection,
    leaving every other selected shape untouched.
  - **Marquee (rubber-band) drag**: pressing on EMPTY space and dragging
    draws a dashed rectangle (`_finish_marquee_select`, on release) --
    every shape it intersects (a proper convex-polygon/rectangle test,
    `_rect_intersects_polygon`, not just a bounding-box check) becomes
    the new selection; holding Ctrl when the drag STARTS adds them to
    the existing selection instead of replacing it.

  Delete (the key, checked globally via bind_all since this app has no
  text-entry widget for it to collide with) removes every selected
  shape.
- **Copy/paste (Ctrl+C / Ctrl+V)**: copies every SELECTED shape's own
  type, rotation, and position, PLUS every connection between two
  selected shapes (one connecting a selected shape to one that ISN'T
  copied along with it has no other end to reproduce, so it's simply
  dropped) (on_copy_key/on_paste_key) -- a no-op with nothing selected;
  pasting drops a fresh instance of each shape, all offset together by
  PASTE_OFFSET so they never land exactly on top of the originals -- a
  multi-shape copy reproduces the exact same relative arrangement AND
  internal connections it was copied with, just shifted as a group.
  Repeated Ctrl+V cascades further each time (each paste advances the
  clipboard's own remembered positions) rather than stacking every copy
  in the same spot. The new shapes (not the new connections) are left
  selected afterward, same as a fresh drop.
- **Drag**: pressing on an already-selected shape (or a shape that press
  is about to select, per Selection above) arms a drag of the WHOLE
  current selection together -- moving the mouse while the button stays
  down moves every selected shape by the same screen-space delta,
  converted through the current pan/zoom transform. A plain click (no
  motion) is just a zero-distance drag, so no separate click-vs-drag
  code path is needed.
- **Rotate**: with a non-empty selection, holding the RIGHT button down
  and dragging rotates the WHOLE selection as one rigid body about its
  own centroid -- every selected shape both spins by the same angle AND
  revolves around that shared point, tracking the mouse's angle around
  it (a trackball-style drag, not an absolute angle readout). For a
  selection of exactly one shape this is identical to the original
  single-shape behavior (its own centroid IS its own center, so
  "revolving" moves it by nothing -- see _on_right_press's own
  docstring), so there's no special-casing between the two cases. With
  nothing selected, right-drag instead pans the view (see below) -- the
  two never conflict, since one or the other is always the case.
- **Esc** cancels a connection that's been armed from one handle (the
  first click of the click-click gesture below) but not yet completed
  onto a second one -- the line following the cursor just disappears,
  with no connection made (`_on_escape_key`).
- **Undo/redo (Ctrl+Z / Ctrl+Y)**: a plain snapshot stack over
  `self.shapes`/`self.connections` (`_push_undo`/`on_undo_key`/
  `on_redo_key`) -- restores the whole canvas as it was one action ago,
  not a field-by-field diff. One entry per WHOLE action: dropping a
  shape, deleting shape(s)/a connection, making a connection, copy/
  paste, Clear, and Load each push one snapshot right before they
  mutate anything, same as any instantaneous action would. A drag (move)
  or right-drag (rotate) gesture is a SINGLE undo step for the whole
  gesture, not one per intermediate mouse-move update --
  `_begin_undoable_change`/`_commit_undoable_change` snapshot at the
  gesture's START and only actually push that snapshot once it ends, and
  only if something about the shapes/connections actually differs from
  it (so a plain click that never moved, or a right-click-drag that
  immediately released, doesn't leave a no-op entry to undo through for
  no reason). Any fresh action clears the redo stack, same as any
  ordinary undo system -- redoing only ever replays what THIS session's
  most recent undo(s) took back, not some independent alternate history.
  Selection is deliberately NOT part of what's restored (undoing back to
  a state where a selected shape no longer exists would leave a
  dangling reference) -- both directions simply clear it.
- **Edge connections**: every shape already on the canvas (not a still-
  armed/not-yet-dropped ghost) has a small circular handle at the
  midpoint of each of its edges -- selecting the shape first is NOT
  required (an earlier version needed that, so starting a connection
  took two clicks: select the shape, then click its handle; now a single
  click straight onto any handle starts one, whether or not that shape
  happens to be selected). A handle that's already the endpoint of a
  real connection is a solid filled dot ("occupied"), stays visible all
  the time, and is no longer clickable at all -- an edge can only ever
  be joined ONCE; connecting an already-joined edge a second time is
  what silently corrupted a hand-built net (transitively merging
  unrelated vertices together the next time it was saved) before this
  was fixed. One that isn't yet joined is an UNFILLED (outline-only)
  ring that
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
  Getting close enough to one of an OTHER shape's own UNJOINED handles
  (not just anywhere over its body) lights up that ONE handle -- not the
  whole shape -- red, as a purely visual "release here" cue; the rest of
  that shape (its outline included) stays its normal, unselected look.
  A SECOND click then either completes the connection onto whichever
  handle is CURRENTLY lit that way, or cancels the pending attempt with
  no connection made if nothing is lit right now (own shape, an already-
  joined handle, empty background, a shape's body without being near
  any of its handles, or anywhere else) -- the same proximity check
  drives both the highlight and what a click can actually complete onto,
  so a connection is never made onto something that wasn't visibly about
  to happen first. A cancel doesn't swallow the click either way -- it
  still gets to do its normal job otherwise (select a shape, deselect,
  etc.). A made connection (drawn as a thin light-grey line between the
  two edges' midpoints from then on, tracking both shapes if either
  moves/rotates) deselects everything. A connection can itself be
  clicked (selecting it turns it red and deselects any shape) and
  deleted with Delete, exactly like a shape. Deleting either shape a
  connection touches removes the connection too, since a connection
  with a missing endpoint is meaningless.

  **Every corner is its own, separate vertex while editing -- no matter
  what any connection implies about it -- and this is deliberate.**
  `_hit_test_any_edge_handle`'s only two rules for what counts as a
  connectable target are local, unambiguous facts about the ONE edge
  being clicked: it isn't already joined (an edge can only ever be
  joined once), and it isn't on the pending connection's own origin
  shape (no shape can connect to itself). Neither depends on what any
  OTHER connection elsewhere happens to imply. An EARLIER version also
  ran a full trial merge (union-find over every corner, following every
  connection transitively) before allowing a connection to complete, and
  rejected it live if that merge would force two different corners of
  some face to collapse into one vertex (a self-loop) -- this sounded
  right but backfired in practice: two individually-free edges that
  LOOKED like an obviously fine, ordinary connection got silently
  rejected because of what some OTHER, unrelated connection elsewhere
  already implied about a shared corner label -- confusing, since that
  implied sharing is itself just as fluid as any single connection (delete
  the connection causing it, and the "shared" vertex stops being shared).
  Treating two corners as fully, physically identified with each other
  during EDITING, rather than as a purely LOCAL, pairwise link each
  connection independently represents, was the actual bug. Full
  structural validation (self-loop and duplicate-directed-edge checks,
  `_validate_shapes_connections`) now happens in exactly ONE place: Save
  (`_export_faces_and_layout`) -- the one moment the full transitive
  merge is the right thing to compute at all, since only then does
  "which corners end up the same vertex" actually matter. It's checked
  directly on `self.shapes`/`self.connections`, in the same
  "vSHAPE.CORNER" terms debug mode (below) already shows a user live --
  never in terms of the fresh integers `_faces_from_shapes` would only
  assign at export time, which a user watching the live app has no
  reason to recognize. A Save that fails names the exact problem (e.g.
  "edge v9.4->v9.0 appears 2 times") AND the specific chain of existing
  connections (`_connection_chain`) whose transitive merge actually ties
  the two conflicting corners together -- neither conflict is ever
  caused by one connection alone, so naming just the connection that
  happened to trip it, on its own, would leave a user unable to tell
  which of it or some earlier, already-accepted connection is the one
  that's actually wrong. A self-loop specifically ALSO rings every
  implicated corner right on the canvas, in `SELF_LOOP_HIGHLIGHT_COLOR`
  (orange -- `_draw_self_loop_highlight`, from the `NetValidationError`
  raised alongside the message), regardless of debug mode, until the
  next edit clears it -- so the problem is visible at a glance, not just
  named in the messagebox text. This is what actually lets a user go
  find and fix the one connection actually causing it, the same way
  debug mode does, live, without needing to attempt a Save first.
- **Pan/zoom**: with no shape selected, right-click-drag pans -- dragging
  the background moves the whole view WITH the drag, the same direction
  as the cursor, like grabbing and sliding the canvas itself under a
  fixed cursor. The scroll wheel zooms about
  the CURSOR position (the world point under the cursor is solved for at
  the OLD scale and pinned there again at the new one, so zooming doesn't
  drift the shape under the mouse away from it).
- **File > Load/Save**: Save writes every shape/connection currently on
  the canvas out as a stretchy-mesh-format `.json` (see "net JSON
  import/export" below), defaulting to `data/input/stretchy_nets/`,
  plus a "view" section (`{"scale": self.view_scale}`, this app's own
  extension) so re-Loading it restores the same zoom level instead of
  resetting to the default. Load reads one back -- a file this app
  itself saved reproduces the EXACT on-screen layout (positions/
  rotations round-trip via its own "net_layout" section) and zoom
  level; a hand-authored net with no such section
  (e.g. any existing file under `data/input/stretchy_nets/`) instead
  gets laid out fresh via a BFS spanning tree over shared edges, each
  face pushed one edge-length away from its parent so the result reads
  as a connected but visibly DISJOINT net rather than a seamlessly
  glued paper one. A LOADED file's own vertex-id NUMBERS are used only
  TRANSIENTLY, purely to work out which edges were connected
  (`_infer_connections`) -- they never become any kind of ongoing
  identity inside this app. Every corner is immediately addressed as
  `(shape_id, edge_index)` from that point on (fresh shape ids, per-
  shape-local edge indices), the exact same way a freshly-drawn shape
  is -- so the loaded file's own labelling and whatever gets exported on
  the next Save are never required or expected to match; only the LIVE
  `self.connections` at Save time decides that, computed once, from
  scratch (`_faces_from_shapes`). A self-loop edge in the source file
  (two adjacent corners of one face sharing a vertex id -- only
  possible from a file an earlier, buggy version of this app saved) is
  never treated as a connection to itself; it's simply left unconnected,
  with a warning naming which face/vertex, so a malformed file still
  loads instead of failing to open at all.
- **Debug mode ("d" key)**: toggles a window-title suffix and, while on,
  hovering near any shape's own VERTEX (a corner -- distinct from an
  edge's midpoint handle) rings it and labels it "vSHAPE.CORNER" (white
  text on a 50%-alpha black box, for legibility over any shape color
  underneath) using that corner's OWN `(shape_id, corner_index)` --
  ALWAYS that, never the union-find ROOT `_vertex_roots` might give it,
  which can legitimately belong to a different, genuinely-connected
  shape (e.g. shape 42's own corner 2 showing as "v34.0" because it's
  really the same vertex as shape 34's corner 0, via however many
  connections tie the two together). An earlier version showed that
  root instead, so hovering two corners that already share an id showed
  identical text -- in principle useful, but confusing in practice on a
  big, densely-connected net (most corners of most shapes ARE genuinely
  shared with a neighbor, so most hovers showed a foreign-looking
  label); a user asked for every corner to always show its own
  polygon's number instead. A failed Save (`_validate_shapes_
  connections`) still names the exact problem in "vSHAPE.CORNER" terms,
  PLUS the specific chain of existing connections responsible
  (`_connection_chain`) -- that, not hovering here, is now how shared or
  conflicting identity actually gets diagnosed.

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
import colorsys
import copy
import itertools
import json
import math
import os
import sys
from collections import deque
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

import sv_ttk
from PIL import Image, ImageColor, ImageDraw, ImageTk

from common.paths import STRETCHY_NETS_DIR
from common.ui_theme import PLOT_THEME
from utils.geometry.polygon_geom import attach_polygon, regular_polygon_vertices

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

# Ctrl+V's own offset (world units, both x and y) from wherever the
# copied shape currently sits -- so a pasted copy never lands exactly on
# top of the original (invisible, indistinguishable) or, repeated, on
# top of the previous paste (see on_paste_key -- each paste advances the
# clipboard's own stored position by this amount, so repeated Ctrl+V
# cascades diagonally instead of stacking).
PASTE_OFFSET = DEFAULT_SHAPE_EDGE_LENGTH * 0.4

# Ctrl+Z/Ctrl+Y's own undo/redo stack (_push_undo/on_undo_key/
# on_redo_key) -- caps how many whole-canvas snapshots it keeps so an
# extremely long editing session can't grow it unboundedly; a project
# built by hand in this app is never going to need more than this many
# steps back.
UNDO_STACK_LIMIT = 100


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
# Debug mode ("d" key): how close the cursor must be to one of a
# shape's own VERTICES (not an edge handle -- a corner) before its
# exported vertex id is shown.
DEBUG_VERTEX_HOVER_RADIUS = 10.0
DEBUG_VERTEX_COLOR = "yellow"
# A failed Save's self-loop check rings every implicated corner in this
# color -- see NetValidationError/_export_faces_and_layout -- regardless
# of debug mode, since this is error feedback a user needs to see even
# with debug mode off.
SELF_LOOP_HIGHLIGHT_COLOR = "orange"
# A handle's resting color, when its shape is neither selected nor the
# current hover target of a pending connection -- SELECTION_OUTLINE_COLOR
# is used instead in those two cases (see _redraw), so a handle reads as
# "active" in the same color a selection does, and plain white otherwise.
HANDLE_COLOR = "white"
CONNECTION_COLOR = "#b0b0b0"
CONNECTION_WIDTH = 1.5
CONNECTION_SELECTED_WIDTH = 2.5

# Marquee (rubber-band) select's own drag rectangle -- see
# _on_canvas_press/_on_canvas_drag/_finish_marquee_select. Plain white
# dashed outline, no fill (a filled/tinted rectangle would need the same
# Pillow-alpha-compositing trick _draw_debug_vertex_label uses for its
# label background, not worth it just for this) -- distinct enough from
# SELECTION_OUTLINE_COLOR (red, solid) that a marquee in progress can't
# be confused with an actual selected shape's outline.
MARQUEE_OUTLINE_COLOR = "white"
MARQUEE_DASH = (4, 2)

# _infer_shape_flips' own combinatorial search: how large a single
# "suspect set" (the shapes implicated in one self-loop's own traced
# chain) it will brute-force over before giving up on auto-fixing that
# one and falling through to the plain, unflipped validation error --
# 2**MAX_FLIP_SEARCH_SHAPES trial validations in the worst case, so this
# stays small enough to always be fast even though each trial re-walks
# every connection.
MAX_FLIP_SEARCH_SHAPES = 16
MAX_FLIP_SEARCH_OUTER_ITERATIONS = 30

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


def _rect_intersects_polygon(rx0, ry0, rx1, ry1, vertices):
    """True if the axis-aligned rectangle [rx0, rx1] x [ry0, ry1]
    (marquee-select's own drag rectangle, see _on_canvas_drag)
    intersects the CONVEX polygon `vertices` (every shape this app
    places is a regular, hence convex, polygon) -- separating-axis test:
    two convex shapes are disjoint iff SOME axis exists (perpendicular to
    one shape's own edge) along which their projections don't overlap,
    so for an axis-aligned rectangle plus a convex polygon, the
    rectangle's own 2 axes plus each polygon edge's own normal are the
    only candidates that could ever separate them."""
    rect_pts = ((rx0, ry0), (rx1, ry0), (rx1, ry1), (rx0, ry1))
    n = len(vertices)
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        axes.append((y1 - y2, x2 - x1))  # edge normal
    for ax, ay in axes:
        r_proj = [px * ax + py * ay for px, py in rect_pts]
        p_proj = [px * ax + py * ay for px, py in vertices]
        if max(r_proj) < min(p_proj) or max(p_proj) < min(r_proj):
            return False
    return True


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


# ---- net JSON import/export (File > Load/Save) ----
#
# Written in the same "faces" vertex-loop format stretchy_mesh.py reads
# (shared vertex ids ARE the adjacency -- see its own module docstring
# for the full convention), plus an extra top-level "net_layout" this
# app alone understands: a list, parallel to "faces", of each face's own
# {"cx", "cy", "rotation"} -- exactly the fields a shape already carries
# -- as it looked on screen when saved. Any OTHER program reading this
# file (the actual stretchy-mesh solver included) only ever looks at
# "faces"/"name" and has no reason to know "net_layout" exists, so it's
# free to ignore an unrecognized top-level key.
#
# Loading a file with no "net_layout" (any hand-authored net under
# data/input/stretchy_nets/, for instance) instead falls back to
# _layout_faces_with_gap -- the same BFS-spanning-tree-over-shared-edges
# idea build_stretchy_net_layout (utils/inflate_polyhedron/
# stretchy_net_layout.py) already implements, reusing its own
# `attach_polygon`/`regular_polygon_vertices` primitives directly rather
# than re-deriving the geometry -- but that function is on this
# project's untouchable-files list and has no parameter for a gap, so it
# can't just be called and asked to leave space between faces; the BFS
# loop itself had to be written again here, parameterized with GAP,
# rather than duplicated wholesale from a file that can't be edited to
# take one.

GAP = DEFAULT_SHAPE_EDGE_LENGTH  # "separated by unit edge length", per the user's own suggestion


def _faces_shared_edges(faces):
    """faces: vertex-id loops. Returns {(a, b) sorted: [(face_idx,
    local_edge_idx), ...]} for every undirected edge -- the same
    grouping idea stretchy_net_layout.py's own (private, so not reused
    directly) _shared_edge_faces uses."""
    shared = {}
    for fi, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            a, b = face[i], face[(i + 1) % n]
            key = (a, b) if a < b else (b, a)
            shared.setdefault(key, []).append((fi, i))
    return shared


def _layout_faces_with_gap(faces, root, gap):
    """faces: vertex-id loops; root: index of the face to place first.
    Same BFS-over-shared-edges idea as build_stretchy_net_layout, but
    each child is attached `gap` world units further out along the
    shared edge's own outward normal (from the parent's centroid)
    instead of flush against it, so connected faces read as visibly
    DISJOINT rather than a seamless paper net. Returns {face_idx: [(x,
    y), ...]}, one entry per face BFS actually reached from `root` --
    faces in a different connected component (if any) are NOT included,
    see _load_faces for how the caller fills those in."""
    shared = _faces_shared_edges(faces)
    placed = {root: regular_polygon_vertices(len(faces[root]), DEFAULT_SHAPE_EDGE_LENGTH)}
    visited = {root}
    queue = deque([root])
    while queue:
        parent = queue.popleft()
        parent_face = faces[parent]
        n_parent = len(parent_face)
        pverts = placed[parent]
        pcx = sum(p[0] for p in pverts) / n_parent
        pcy = sum(p[1] for p in pverts) / n_parent
        for i in range(n_parent):
            a, b = parent_face[i], parent_face[(i + 1) % n_parent]
            key = (a, b) if a < b else (b, a)
            for fi, local_idx in shared[key]:
                if fi == parent or fi in visited:
                    continue
                visited.add(fi)
                p1, p2 = pverts[i], pverts[(i + 1) % n_parent]
                mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
                dx, dy = mx - pcx, my - pcy
                dist = math.hypot(dx, dy) or 1.0
                ox, oy = dx / dist * gap, dy / dist * gap
                # Reversed (p2 then p1), matching build_stretchy_net_layout's
                # own convention, so a child face unfolds outward the same way.
                target_a = p2 + (ox, oy)
                target_b = p1 + (ox, oy)
                placed[fi] = attach_polygon(len(faces[fi]), local_idx, target_a, target_b,
                                             edge_length=DEFAULT_SHAPE_EDGE_LENGTH)
                queue.append(fi)
    return placed


def _shape_from_placed_points(n, points):
    """points: a regular n-gon's own vertex loop (as placed by
    _layout_faces_with_gap or build_stretchy_net_layout), in the SAME
    local order _LOCAL_VERTICES[n] uses. Solves for the (cx, cy,
    rotation) a shape dict needs to reproduce those exact points via
    _shape_world_vertices -- both are the same regular polygon, just
    translated/rotated, so one vertex's angle relative to each polygon's
    own centroid is enough to recover the rotation."""
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    lvx, lvy = _LOCAL_VERTICES[n][0]
    wvx, wvy = points[0][0] - cx, points[0][1] - cy
    rotation = math.atan2(wvy, wvx) - math.atan2(lvy, lvx)
    return cx, cy, rotation


def _infer_connections(faces):
    """faces: vertex-id loops. Returns [{"a_face", "a_edge", "b_face",
    "b_edge"}, ...] (face indices, not shape ids -- the caller maps
    those) for every edge shared by exactly two faces in OPPOSITE
    directions -- the same winding convention stretchy_mesh.py's
    load_stretchy_mesh validates, but lenient rather than strict: an
    edge with no reverse partner (this app allows a still-unconnected
    edge; a fully-closed solver net never has one) is simply left
    unconnected instead of raising. A SELF-LOOP edge (both endpoints the
    same vertex id -- only possible from a file saved by an earlier,
    buggy version of this app; see _self_loop_faces) is skipped
    entirely rather than treated as its own reverse partner, which is
    what a naive directed-edge lookup would otherwise do: `(v, v)`'s
    reverse is also `(v, v)`, so without this guard a self-loop edge
    would silently infer a connection from that edge to ITSELF (same
    face, same edge index on both ends) -- exactly the kind of
    nonsensical entry _validate_faces exists to catch at Save, but there
    was never any reason to let Load manufacture one in the first
    place."""
    directed = {}
    for fi, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            v, w = face[i], face[(i + 1) % n]
            if v == w:
                continue
            directed[(v, w)] = (fi, i)
    connections = []
    seen = set()
    for (v, w), (fi, i) in directed.items():
        if (v, w) in seen:
            continue
        seen.add((v, w))
        reverse = directed.get((w, v))
        if reverse is not None:
            fj, j = reverse
            seen.add((w, v))
            connections.append({"a_face": fi, "a_edge": i, "b_face": fj, "b_edge": j})
    return connections


def _true_edge_slots(shape, edge_index):
    """The (v_slot, w_slot) corner-slot pair edge `edge_index` of `shape`
    represents in TRUE (CCW-from-outside) direction: (corner i, corner
    i+1) normally, or REVERSED -- (corner i+1, corner i) -- when `shape`
    is flipped (see _infer_shape_flips' module-level Design notes). A
    regular polygon placed in this app can only be rotated, never
    mirrored, so its DRAWN corner order always has the same fixed
    handedness; "flipped" is a per-shape bit saying that shape's face is
    meant to be viewed from the OTHER side of the solid, which reverses
    every one of its edges' TRUE direction relative to how they're drawn
    -- this is the one place that fact gets applied, so every caller
    (_connection_pairs, _faces_from_shapes, _validate_shapes_connections)
    agrees. Set automatically by _infer_shape_flips at Save time -- never
    user-editable."""
    sid, n = shape["id"], shape["n"]
    a, b = (sid, edge_index), (sid, (edge_index + 1) % n)
    return (b, a) if shape.get("flipped", False) else (a, b)


def _shape_face_corner_order(shape):
    """The corner-index order _faces_from_shapes/_validate_shapes_connections
    read a shape's OWN face loop in, matching _true_edge_slots: forward
    (0, 1, ..., n-1) normally, or reversed (n-1, ..., 1, 0) when flipped
    -- a flipped shape's consecutive TRUE edges only chain into a valid
    cyclic loop when its corners are visited in reverse (see
    _infer_shape_flips' module-level Design notes)."""
    n = shape["n"]
    return range(n - 1, -1, -1) if shape.get("flipped", False) else range(n)


def _connection_pairs(shapes_by_id, conn):
    """The two corner-slot pairs one connection unions (_vertex_roots) or
    links (_connection_chain's own adjacency): shape A's edge `a_edge`,
    in its TRUE direction (_true_edge_slots), must run the OPPOSITE way
    from shape B's edge `b_edge` in ITS true direction -- the standard
    CCW-from-outside net convention load_stretchy_mesh validates, applied
    to each shape's true (flip-adjusted) direction rather than its raw
    drawn one."""
    a_shape, b_shape = shapes_by_id[conn["a_shape"]], shapes_by_id[conn["b_shape"]]
    a_v, a_w = _true_edge_slots(a_shape, conn["a_edge"])
    b_v, b_w = _true_edge_slots(b_shape, conn["b_edge"])
    return ((a_v, b_w), (a_w, b_v))


def _vertex_roots(shapes, connections):
    """shapes: [{"id", "n", "flipped", ...}, ...]; connections:
    [{"a_shape", "a_edge", "b_shape", "b_edge"}, ...]. Returns
    {(shape_id, corner_index): root_slot} -- a UNION-FIND over each
    shape's own corner slots (`corner i` is the vertex where edge `i-1`
    meets edge `i`, i.e. edge `i` runs corner `i` -> corner `(i+1) % n`,
    the same indexing _shape_edge_midpoints uses), merged pairwise per
    _connection_pairs for every connection. The root itself is a
    `(shape_id, corner_index)` slot -- deliberately NOT a freshly-assigned
    sequential integer (that numbering is _faces_from_shapes' own job,
    layered on top of this, only for the exported JSON's vertex-id
    integers) -- since a slot's root is STABLE across any edit that
    doesn't touch its own group, unlike a from-scratch sequential
    renumbering, which can shift for every corner processed after
    wherever the edit happened to land (adding one connection anywhere
    merges two groups into one, which shifts every id assigned afterward
    down by one). This is what _draw_debug_vertex_label displays instead,
    precisely so a corner's shown identity doesn't change just because
    some UNRELATED connection was added or removed elsewhere."""
    parent = {(s["id"], corner): (s["id"], corner) for s in shapes for corner in range(s["n"])}

    def find(slot):
        while parent[slot] != slot:
            slot = parent[slot]
        return slot

    def union(slot_a, slot_b):
        root_a, root_b = find(slot_a), find(slot_b)
        if root_a != root_b:
            parent[root_a] = root_b

    shapes_by_id = {s["id"]: s for s in shapes}
    for conn in connections:
        for slot_a, slot_b in _connection_pairs(shapes_by_id, conn):
            union(slot_a, slot_b)

    return {slot: find(slot) for slot in parent}


def _faces_from_shapes(shapes, connections):
    """shapes/connections: as _vertex_roots. Returns the vertex-loop
    "faces" list for exporting: each distinct root from _vertex_roots
    gets one fresh sequential integer id (assigned in shape/corner
    visiting order), and each shape's own face is just its corners' ids
    in _shape_face_corner_order (forward normally, reversed if flipped --
    see _infer_shape_flips' module-level Design notes for why a flipped
    shape's own face loop must be read backward to come out
    CCW-from-outside like every other face's). This sequential numbering
    only ever happens HERE, inside
    _export_faces_and_layout (Save) -- never live while editing (see
    module docstring's Edge connections section for why treating a live
    version of this as a gate on new connections turned out to be the
    wrong layer to check at, and _vertex_roots' own docstring for why a
    fresh renumbering isn't what debug mode displays either)."""
    roots = _vertex_roots(shapes, connections)
    vertex_ids = {}
    faces = []
    for shape in shapes:
        face = []
        for corner in _shape_face_corner_order(shape):
            root = roots[(shape["id"], corner)]
            if root not in vertex_ids:
                vertex_ids[root] = len(vertex_ids)
            face.append(vertex_ids[root])
        faces.append(face)
    return faces


def _self_loop_faces(faces):
    """faces: vertex-id loops, as freshly read from a file (BEFORE
    _infer_connections has had a chance to skip anything). Returns
    [(face_index, vertex_id), ...] for every SELF-LOOP edge found -- two
    ADJACENT corners of one face sharing a vertex id, which can only
    come from a file saved by an earlier, buggy version of this app (a
    correctly-behaving Save can never produce one; see
    _export_faces_and_layout/_validate_faces). Purely diagnostic: Load
    calls this just to warn the user that edge(s) were left unconnected
    on the way in, since _infer_connections silently skips them rather
    than raising (a malformed file should still load, not block the
    user from opening and fixing it)."""
    problems = []
    for fi, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            if face[i] == face[(i + 1) % n]:
                problems.append((fi, face[i]))
    return problems


def _validate_faces(faces):
    """faces: vertex-id loops about to be exported. Raises ValueError if
    any face has a SELF-LOOP edge (two ADJACENT corners sharing one
    vertex id -- geometrically two different points on that polygon,
    never legitimately the same one) or any directed edge appears more
    than once (the same rule load_stretchy_mesh itself enforces on
    load). Both are symptoms of the SAME underlying mistake -- an edge
    unioned with two different partners in _export_faces_and_layout,
    which transitively merges unrelated vertices together -- rather than
    something a valid net, open or closed, could ever produce; this is
    exactly what corrupted data/input/stretchy_nets/hippo.json before
    _hit_test_any_edge_handle started refusing to let an already-joined
    edge be clicked again (see its own docstring). Checking again here,
    right before writing the file, catches it even if that guard is ever
    bypassed some other way (a loaded file with the same problem,
    re-saved unchanged, for instance)."""
    problems = []
    counts = {}
    for face in faces:
        n = len(face)
        for i in range(n):
            v, w = face[i], face[(i + 1) % n]
            if v == w:
                problems.append(f"face {face} has a self-loop edge at vertex {v}")
            counts[(v, w)] = counts.get((v, w), 0) + 1
    problems += [f"edge {v}->{w} appears {c} times (need at most once)"
                 for (v, w), c in counts.items() if c > 1]
    if problems:
        raise ValueError("Not a valid net, refusing to save:\n  " + "\n  ".join(problems))


def _connection_chain(shapes, connections, slot_a, slot_b):
    """Returns the shortest list of connections (as {"a_shape", "a_edge",
    "b_shape", "b_edge"} dicts, in traversal order) whose unions link
    slot_a to slot_b -- i.e. the actual reason _vertex_roots gave them
    the same root, spelled out as the specific chain of edge-to-edge
    connections responsible, rather than just the shared root itself.
    A self-loop or duplicate-edge conflict is never caused by one
    connection in isolation (see _validate_shapes_connections) -- it's
    always this transitive chain, possibly running through many other
    shapes, that the two ends of some offending edge got swept into.
    BFS over the same slot-to-slot links _vertex_roots' own union calls
    make (each connection contributes the same two pairs _connection_pairs
    gives it), so the path found here traces the exact unions that
    produced the shared root. Returns None if slot_a/slot_b
    aren't actually linked (shouldn't happen for two slots already
    confirmed to share a root, but guards against it regardless)."""
    shapes_by_id = {s["id"]: s for s in shapes}
    adjacency = {}
    for conn in connections:
        for u, v in _connection_pairs(shapes_by_id, conn):
            adjacency.setdefault(u, []).append((v, conn))
            adjacency.setdefault(v, []).append((u, conn))

    came_from = {slot_a: None}
    queue = deque([slot_a])
    while queue:
        cur = queue.popleft()
        if cur == slot_b:
            break
        for nxt, conn in adjacency.get(cur, ()):
            if nxt not in came_from:
                came_from[nxt] = (cur, conn)
                queue.append(nxt)
    if slot_b not in came_from:
        return None
    chain = []
    slot = slot_b
    while came_from[slot] is not None:
        slot, conn = came_from[slot]
        chain.append(conn)
    chain.reverse()
    return chain


class NetValidationError(ValueError):
    """Raised by _validate_shapes_connections instead of a plain
    ValueError, carrying `self_loop_slots` -- the {(shape_id,
    corner_index), ...} set of every corner involved in a self-loop
    edge (both endpoints of each one found) -- alongside the usual
    message, so on_save_clicked can ring them in the app (in
    SELF_LOOP_HIGHLIGHT_COLOR) as well as naming them in the
    messagebox. A plain `str(err)` still gives the same message a bare
    ValueError would; only code that specifically wants the slots needs
    to know this subclass exists."""

    def __init__(self, message, self_loop_slots=frozenset()):
        super().__init__(message)
        self.self_loop_slots = self_loop_slots


def _validate_shapes_connections(shapes, connections):
    """shapes/connections: as _vertex_roots. Same two checks as
    _validate_faces (self-loop / duplicate-directed-edge) -- but raises
    a NetValidationError (see its own docstring) phrased in terms of the
    LIVE "vSHAPE.CORNER" vertex identity _draw_debug_vertex_label
    already shows a user while editing (the root slot from
    _vertex_roots), never in terms of the fresh sequential integers
    _faces_from_shapes would assign these same vertices at export time.
    A user who's never opened the exported JSON has no reason to know
    what "vertex 37" in a save-failure message even refers to; "v9.4" is
    the same label they can go hover with debug mode to find and fix.
    Called on self.shapes/self.connections directly, BEFORE
    _faces_from_shapes ever runs, so the error a failed Save shows is
    always phrased in terms of the corners the user actually placed and
    connected.

    Neither conflict is ever caused by a single connection considered on
    its own -- see _connection_chain's own docstring -- so every problem
    message also names the SPECIFIC chain of existing connections whose
    transitive merge (via _vertex_roots) is what actually ties the
    conflicting corners together, e.g. because a face otherwise
    untouched by whatever was just connected can still end up implicated
    if its own two corners were already, separately, drawn into the
    same larger group some other connection elsewhere set up. Read
    literally: "shape 9's corners 2 and 3 already come out to the same
    vertex once you trace shape 9 edge 1 -> shape 4 edge 0 -> shape 4
    edge 2 -> shape 9 edge 3" -- exactly the reasoning a user would have
    to redo by hand with debug mode alone, spelled out for them instead."""
    roots = _vertex_roots(shapes, connections)

    def vlabel(root_slot):
        return f"v{root_slot[0]}.{root_slot[1]}"

    def chain_text(slot_a, slot_b):
        chain = _connection_chain(shapes, connections, slot_a, slot_b)
        if not chain:
            return ""
        steps = " -> ".join(f"shape {c['a_shape']} edge {c['a_edge']} <-> "
                             f"shape {c['b_shape']} edge {c['b_edge']}" for c in chain)
        return f" (traced through: {steps})"

    problems = []
    self_loop_slots = set()
    counts = {}
    for shape in shapes:
        n, sid = shape["n"], shape["id"]
        for i in range(n):
            # _true_edge_slots, not the raw (sid, i)/(sid, (i+1)%n) pair --
            # a flipped shape's edge i has its TRUE v/w corners reversed
            # (see _infer_shape_flips' Design notes), and this check has
            # to agree with _connection_pairs/_faces_from_shapes about
            # what each shape's own edges actually connect to.
            slot_v, slot_w = _true_edge_slots(shape, i)
            v, w = roots[slot_v], roots[slot_w]
            if v == w:
                problems.append(
                    f"shape {sid} edge {i} (corners {slot_v[1]}->{slot_w[1]}) "
                    f"is a self-loop at {vlabel(v)}{chain_text(slot_v, slot_w)}")
                self_loop_slots.add(slot_v)
                self_loop_slots.add(slot_w)
            counts.setdefault((v, w), []).append((sid, i, slot_v))
    for (v, w), edges in counts.items():
        if len(edges) > 1:
            where = ", ".join(f"shape {sid} edge {i}" for sid, i, _ in edges)
            first_slot = edges[0][2]
            second_slot = edges[1][2]
            problems.append(
                f"edge {vlabel(v)}->{vlabel(w)} appears {len(edges)} times "
                f"({where}); need at most once{chain_text(first_slot, second_slot)}")
    if problems:
        raise NetValidationError(
            "Not a valid net, refusing to save:\n  " + "\n  ".join(problems), self_loop_slots)


def _infer_shape_flips(shapes, connections):
    """Automatically finds a set of shape ids to mark "flipped" (see
    _true_edge_slots) so _validate_shapes_connections passes -- WITHOUT
    the user ever choosing anything -- or returns None if no such set
    was found (the caller then just validates unflipped, exactly as if
    this function didn't exist, so the reported error is unaffected).

    Design notes -- why this can't be a simple, always-correct rule:
    every shape's own drawn corner order has a single, fixed handedness
    (only rotation, never mirroring, is available when placing it), and
    _connection_pairs' default (REVERSED, "viewed from outside") pairing
    handles most nets built this way with no help. But some valid nets
    genuinely need a face read the OTHER way relative to its neighbors
    -- e.g. 3 triangles connected pairwise around a shared apex, plus a
    4th "base" face closing all 3 of their remaining edges, needs that
    4th face's connections to use the OPPOSITE pairing, since gluing it
    the default way makes two of its own corners collide into one
    vertex (a self-loop) no matter which of its edges are chosen for
    which connection. A user hit exactly this building a tetrahedron
    this way and reported it as a bug.

    Critically, a single connection's own (a_edge, b_edge) never says by
    itself whether it needs the default or opposite pairing -- either
    is equally valid in isolation (it only fixes WHICH physical edges
    are glued, not their relative orientation) -- so this can only be
    determined by REQUIRING GLOBAL CONSISTENCY across every connection
    at once, exactly like determining whether a surface built by gluing
    polygons along edges (with no pre-existing shared vertex labels) is
    orientable at all. That's solvable, but not by a single linear
    pass with a fixed per-edge rule (verified directly: brute-forcing a
    small worked example found relative orientation constraints that
    only became visible once enough of the mesh existed to create a
    cycle, and satisfying one cycle's constraint could just as well have
    required UNDOING an earlier, individually-harmless choice made
    elsewhere). Instead: start from the default (nothing flipped, i.e.
    today's original behavior, unchanged for every net that never needed
    this at all) and only search when that fails -- a failed check's own
    self-loop already NAMES the specific corners involved and, via
    _connection_chain, the specific chain of connections responsible
    (see _validate_shapes_connections), so the "suspect set" of shapes
    that might need flipping is exactly those named, not the whole net.
    Brute-forcing increasing-size subsets of just that (small, for any
    reasonably localized problem) set, retrying validation after each,
    finds a fix quickly in practice (confirmed on the tetrahedron
    example above and on every net already shipped under
    data/input/stretchy_nets/, which validate instantly with an empty
    flip set -- i.e. this changes nothing for a net that already worked).
    MAX_FLIP_SEARCH_SHAPES/MAX_FLIP_SEARCH_OUTER_ITERATIONS cap the
    search so a genuinely non-orientable net (no flip assignment can
    ever fix it) or an unusually large tangle fails fast rather than
    hanging, falling back to the plain validation error."""
    flip_set = set()
    for _ in range(MAX_FLIP_SEARCH_OUTER_ITERATIONS):
        trial = [dict(s, flipped=(s["id"] in flip_set)) for s in shapes]
        try:
            _validate_shapes_connections(trial, connections)
            return flip_set
        except NetValidationError as e:
            if not e.self_loop_slots:
                return None  # a pure duplicate-edge conflict -- no self-loop to localize from
            suspects = {slot[0] for slot in e.self_loop_slots}
            slots = list(e.self_loop_slots)
            chain = _connection_chain(shapes, connections, slots[0], slots[1]) if len(slots) >= 2 else None
            if chain:
                for c in chain:
                    suspects.add(c["a_shape"])
                    suspects.add(c["b_shape"])
        if len(suspects) > MAX_FLIP_SEARCH_SHAPES:
            return None
        candidates = sorted(suspects)
        found = None
        for size in range(1, len(candidates) + 1):
            for combo in itertools.combinations(candidates, size):
                trial_flips = flip_set.symmetric_difference(combo)
                trial = [dict(s, flipped=(s["id"] in trial_flips)) for s in shapes]
                try:
                    _validate_shapes_connections(trial, connections)
                    found = trial_flips
                    break
                except NetValidationError:
                    continue
            if found is not None:
                break
        if found is None:
            return None
        flip_set = found
    return None


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
        # {shape_id, ...} -- every currently-selected shape (possibly
        # empty, possibly more than one via marquee-drag or Ctrl+click,
        # see _on_canvas_press/_finish_marquee_select). A shape click
        # without Ctrl held replaces this wholesale UNLESS the clicked
        # shape is already a member, in which case the whole group stays
        # selected (so it can be dragged/rotated/deleted together).
        self.selected_ids = set()
        self.armed_n = None
        # Marquee (rubber-band) select: screen-space start/current corner
        # of the drag rectangle while one is in progress, else None/None
        # -- see _on_canvas_press/_on_canvas_drag/_finish_marquee_select.
        # _marquee_additive records whether Ctrl was held when the drag
        # started (add to the existing selection) vs replace it.
        self._marquee_start = None
        self._marquee_current = None
        self._marquee_additive = False
        # {"shapes": [{"n", "rotation", "cx", "cy"}, ...], "connections":
        # [{"a_index", "a_edge", "b_index", "b_edge"}, ...]} for the last
        # Ctrl+C (shapes/connections index into that same "shapes" list,
        # not real shape ids, which won't exist again until paste time),
        # or None -- see on_copy_key/on_paste_key.
        self._clipboard = None
        # Ctrl+Z/Ctrl+Y: lists of whole-canvas snapshots
        # (_snapshot_state's own {"shapes", "connections",
        # "_next_shape_id", "_next_connection_id"} shape), oldest first
        # -- see _push_undo/on_undo_key/on_redo_key. _pending_undo_snapshot
        # is the snapshot taken at the START of a drag/rotate gesture
        # still in progress, not yet committed to _undo_stack (see
        # _begin_undoable_change/_commit_undoable_change) -- None when no
        # such gesture is live.
        self._undo_stack = []
        self._redo_stack = []
        self._pending_undo_snapshot = None
        self._ghost_world_xy = None
        self._drag_state = None
        self._pan_last_xy = None
        self._rotate_state = None
        self._shape_photos = []  # keeps this redraw's PhotoImages alive (Tk drops GC'd ones)
        self._icon_photos = {}
        # {(shape_id, corner_index), ...} -- corners a failed Save's
        # self-loop check just implicated (see _export_faces_and_layout);
        # _redraw rings each one in SELF_LOOP_HIGHLIGHT_COLOR, on top of
        # everything else, until the next edit invalidates it.
        self._self_loop_highlight = set()

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
        # selection but never actually added to self.selected_ids. The
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
        # Toggled by the "d" key (bind_all, like Delete above -- no
        # text-entry widget in this app for a stray "d" to collide
        # with), same idea as inflate_polyhedron_app's own debug mode:
        # while on, hovering near any shape's VERTEX (not an edge
        # handle) shows its exported vertex id -- lets a user directly
        # see whether two nearby corners from different shapes already
        # share an id (connected) or don't, exactly the question that
        # comes up when a connection is rejected for a not-immediately-
        # obvious reason (see _draw_debug_vertex_label).
        self.debug_mode = False

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
        self._build_menu()

        left = ttk.Frame(self.root, padding=12)
        left.pack(side=tk.LEFT, fill=tk.Y)

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
        self.root.bind_all("<KeyPress-d>", self._on_toggle_debug_mode)
        self.root.bind_all("<Control-c>", self.on_copy_key)
        self.root.bind_all("<Control-v>", self.on_paste_key)
        self.root.bind_all("<Control-z>", self.on_undo_key)
        self.root.bind_all("<Control-y>", self.on_redo_key)
        self.root.bind_all("<Escape>", self._on_escape_key)

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Load...", command=self.on_load_clicked)
        file_menu.add_command(label="Save...", command=self.on_save_clicked)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

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

    def _joined_points(self):
        """Set of (shape_id, edge_index) already the endpoint of a real
        connection -- an edge can only ever be joined ONCE, so this is
        what _hit_test_any_edge_handle excludes from being clickable a
        second time (see its own docstring for why: connecting the same
        edge twice is what corrupted data/input/stretchy_nets/hippo.json
        -- a single edge unioned with two different partners transitively
        merged unrelated vertices together, producing self-loop and
        duplicate-directed-edge errors far from where the mistake was
        actually made)."""
        joined = set()
        for conn in self.connections:
            joined.add((conn["a_shape"], conn["a_edge"]))
            joined.add((conn["b_shape"], conn["b_edge"]))
        return joined

    def _hit_test_any_edge_handle(self, screen_x, screen_y, exclude_shape_id=None):
        """Nearest edge handle belonging to any shape OTHER than
        `exclude_shape_id`, within HANDLE_HIT_RADIUS screen pixels of the
        given point, or None. Every placed shape's every UNJOINED edge
        handle is clickable this way -- there's no "must be selected
        first" gate (that WAS the rule at one point; dropped since it
        took two clicks, select-the-shape then click-its-handle, to
        start a connection at all -- see module docstring) -- but an
        edge already the endpoint of a real connection (see
        _joined_points) is EXCLUDED entirely, for both starting a new
        connection from it and completing one onto it: an edge can only
        ever be joined once, and allowing a second join is exactly what
        corrupted hippo.json (see _joined_points' own docstring). Also
        used, with `exclude_shape_id` set to a pending connection's own
        origin shape, for both hover highlighting (_on_canvas_motion) and
        deciding what a completing click actually connects to
        (_complete_or_cancel_pending_connection just reads the hover
        state this leaves behind, rather than re-running this itself) --
        the two MUST agree, so nothing ever connects without having
        first been visibly highlighted."""
        joined = self._joined_points()
        best, best_dist = None, HANDLE_HIT_RADIUS
        for shape in self.shapes:
            if shape["id"] == exclude_shape_id:
                continue
            for edge_index, (mx, my) in enumerate(self._shape_edge_midpoints(shape)):
                if (shape["id"], edge_index) in joined:
                    continue
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
        self._self_loop_highlight = set()

    # ---- palette ----

    def _on_palette_clicked(self, n):
        self.armed_n = None if self.armed_n == n else n
        self._ghost_world_xy = None
        if self.armed_n is not None:
            # Arming a new shape to place is a distinct action from
            # working with whatever's already on the canvas -- picking
            # one up shouldn't leave an unrelated shape looking selected.
            self.selected_ids = set()
            self.selected_connection_id = None
        for other_n, icon in self._palette_canvases.items():
            icon.configure(highlightbackground=(
                "white" if other_n == self.armed_n else PLOT_THEME["bg"]))
        self._redraw()

    def on_clear_clicked(self):
        if self.shapes or self.connections:
            self._push_undo()
        self.shapes.clear()
        self.connections.clear()
        self.selected_ids = set()
        self.selected_connection_id = None
        self._drag_state = None
        self._redraw()

    # ---- File menu: load/save ----

    def on_save_clicked(self):
        """Writes the current shapes/connections out as a stretchy-mesh
        "faces" vertex-loop spec, plus a "net_layout" section (this
        app's own extension, see module docstring) so re-Loading it
        reproduces the exact on-screen layout rather than falling back
        to a fresh BFS one, and a "view" section with the current zoom
        level so re-Loading it doesn't reset back to the default zoom.
        A self-loop failure (NetValidationError) also rings every
        implicated corner in SELF_LOOP_HIGHLIGHT_COLOR (_redraw), so the
        problem is visible on the canvas itself, not just named in the
        messagebox text -- cleared again by the next edit (see
        self._self_loop_highlight's own comment in __init__)."""
        path = filedialog.asksaveasfilename(
            title="Save net", initialdir=str(STRETCHY_NETS_DIR), defaultextension=".json",
            filetypes=[("Net JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            faces, net_layout = self._export_faces_and_layout()
        except NetValidationError as e:
            self._self_loop_highlight = e.self_loop_slots
            self._redraw()
            messagebox.showerror("Save failed", str(e))
            return
        except ValueError as e:
            messagebox.showerror("Save failed", str(e))
            return
        spec = {"name": os.path.splitext(os.path.basename(path))[0], "faces": faces,
                "net_layout": net_layout, "view": {"scale": self.view_scale}}
        try:
            with open(path, "w") as f:
                json.dump(spec, f, indent=2)
        except OSError as e:
            messagebox.showerror("Save failed", str(e))

    def _export_faces_and_layout(self):
        """Returns (faces, net_layout): `faces` is the vertex-loop list
        derived from self.shapes/self.connections via _faces_from_shapes;
        `net_layout` is each shape's own {"cx", "cy", "rotation"}, in the
        same order as `faces`. Raises NetValidationError (a ValueError
        subclass, from _validate_shapes_connections) if the current
        connections would produce an invalid mesh even after
        _infer_shape_flips' own automatic search for a working
        "flipped" assignment (see its own Design notes for why some
        valid nets need one at all) -- the ONLY place either of these
        ever run (see module docstring: every corner is deliberately
        treated as its own, separate vertex while editing, no matter
        what any OTHER connection's own merge already implies about it;
        only Save actually computes the full picture and validates it,
        once, as a whole). Validated on self.shapes/self.connections
        directly (in "vSHAPE.CORNER" terms, the same live identity debug
        mode shows), before _faces_from_shapes ever renumbers anything
        for export, so a failed Save's error names corners the user can
        actually go find on screen -- and reflects the SAME (unflipped)
        assignment shown there if no working flip was found, so the
        error is never phrased in terms of a flip the user never asked
        for and can't see."""
        flip_set = _infer_shape_flips(self.shapes, self.connections)
        shapes = ([dict(s, flipped=(s["id"] in flip_set)) for s in self.shapes]
                   if flip_set is not None else self.shapes)
        _validate_shapes_connections(shapes, self.connections)
        faces = _faces_from_shapes(shapes, self.connections)
        net_layout = [{"cx": s["cx"], "cy": s["cy"], "rotation": s["rotation"]} for s in self.shapes]
        return faces, net_layout

    def on_load_clicked(self):
        path = filedialog.askopenfilename(
            title="Load net", initialdir=str(STRETCHY_NETS_DIR),
            filetypes=[("Net JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path) as f:
                spec = json.load(f)
            faces = spec["faces"]
            if not faces:
                raise ValueError("no faces declared")
            self_loops = _self_loop_faces(faces)
            view_scale = spec.get("view", {}).get("scale")
            self._load_faces(faces, spec.get("net_layout"), view_scale)
            if self_loops:
                # A malformed file (from an earlier, buggy Save -- see
                # _self_loop_faces' own docstring) still loads, but
                # every self-loop edge is left unconnected rather than
                # silently wired up wrong -- tell the user so they know
                # to go reconnect those specific edges, rather than
                # discovering it only when some later Save fails.
                where = ", ".join(f"face {fi} vertex {v}" for fi, v in self_loops)
                messagebox.showwarning(
                    "Loaded with degenerate edges",
                    f"{len(self_loops)} self-loop edge(s) in this file were left "
                    f"unconnected (a corrupted vertex label from an earlier bug, "
                    f"not a real connection): {where}")
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            messagebox.showerror("Load failed", str(e))

    def _load_faces(self, faces, net_layout, view_scale=None):
        """Replaces the whole canvas with `faces` (vertex-id loops).
        `net_layout` (this app's own saved {"cx", "cy", "rotation"} per
        face, see module docstring), when present and the right length,
        positions shapes exactly as they were when saved; otherwise
        falls back to _layout_faces_with_gap, rooted at face 0.
        `view_scale` (this app's own saved "view"."scale", see module
        docstring), when present, restores the zoom level the net was
        saved at instead of resetting to the default 1.0."""
        if self.shapes or self.connections:
            self._push_undo()
        self.shapes = []
        self.connections = []
        self.selected_ids = set()
        self.selected_connection_id = None
        self.armed_n = None
        self._connection_pending = None
        self._hover_shape_id = None
        self._hover_edge_index = None
        self._drag_state = None
        self._marquee_start = None
        self._marquee_current = None
        self._self_loop_highlight = set()

        shape_ids = []
        for face in faces:
            shape_id = self._next_shape_id
            self._next_shape_id += 1
            shape_ids.append(shape_id)
            # "flipped" always starts False for a LOADED shape -- never
            # needed here even for a face that a builder session had
            # flipped originally, since _infer_connections derives
            # connections straight from the file's own already-consistent
            # winding (see its own docstring), not via _connection_pairs.
            self.shapes.append({"id": shape_id, "n": len(face), "cx": 0.0, "cy": 0.0,
                                 "rotation": 0.0, "flipped": False})

        if net_layout is not None and len(net_layout) == len(faces):
            for shape, layout in zip(self.shapes, net_layout):
                shape["cx"], shape["cy"], shape["rotation"] = (
                    layout["cx"], layout["cy"], layout["rotation"])
        else:
            placed = _layout_faces_with_gap(faces, root=0, gap=GAP)
            for i, (shape, face) in enumerate(zip(self.shapes, faces)):
                if i in placed:
                    shape["cx"], shape["cy"], shape["rotation"] = \
                        _shape_from_placed_points(len(face), placed[i])
                else:
                    # A face BFS from face 0 never reached (a separate
                    # connected component) -- just set it off to one
                    # side rather than leaving it stacked on the origin.
                    shape["cx"] = (i + 1) * DEFAULT_SHAPE_EDGE_LENGTH * 3

        for conn in _infer_connections(faces):
            self.connections.append({
                "id": self._next_connection_id,
                "a_shape": shape_ids[conn["a_face"]], "a_edge": conn["a_edge"],
                "b_shape": shape_ids[conn["b_face"]], "b_edge": conn["b_edge"],
            })
            self._next_connection_id += 1

        self._center_view_on_shapes(scale=view_scale if view_scale is not None else 1.0)
        self._redraw()

    def _center_view_on_shapes(self, scale=1.0):
        if not self.shapes:
            return
        avg_x = sum(s["cx"] for s in self.shapes) / len(self.shapes)
        avg_y = sum(s["cy"] for s in self.shapes) / len(self.shapes)
        self.view_scale = scale
        self.offset_x = self.canvas.winfo_width() / 2 - avg_x * scale
        self.offset_y = self.canvas.winfo_height() / 2 - avg_y * scale

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
            # lights up when it's actually a connectable target: any
            # UNJOINED edge of any OTHER shape (see
            # _hit_test_any_edge_handle -- both those exclusions are
            # LOCAL, unambiguous facts about the one edge being clicked,
            # never dependent on what any OTHER connection happens to
            # imply about shared vertex identity -- see module docstring
            # on why that's deliberate).
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
            self._push_undo()
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
            self.selected_ids = set()
            self.selected_connection_id = None
            self._redraw()
            return

        conn_hit = self._hit_test_connection(event.x, event.y)
        if conn_hit is not None:
            self.selected_connection_id = conn_hit
            self.selected_ids = set()
            self._drag_state = None
            self._redraw()
            return

        wx, wy = self._screen_to_world(event.x, event.y)
        hit = self._hit_test(wx, wy)
        self.selected_connection_id = None
        ctrl_held = bool(event.state & 0x0004)
        if hit is None:
            # Empty space: a plain click deselects everything and starts
            # a marquee-select drag from here (see _on_canvas_drag/
            # _finish_marquee_select); Ctrl+click on empty space starts
            # one too, but ADDS whatever it encloses to the CURRENT
            # selection instead of replacing it, so it leaves the
            # existing selection alone until release actually confirms
            # something new.
            if not ctrl_held:
                self.selected_ids = set()
            self._drag_state = None
            self._marquee_start = (event.x, event.y)
            self._marquee_current = (event.x, event.y)
            self._marquee_additive = ctrl_held
        else:
            if ctrl_held:
                # Ctrl+click TOGGLES this one shape's membership, leaving
                # every other selected shape exactly as it was.
                self.selected_ids.symmetric_difference_update({hit["id"]})
            elif hit["id"] not in self.selected_ids:
                # Clicking a shape that ISN'T already part of the current
                # selection replaces the whole selection with just it --
                # clicking one that ALREADY is (below) leaves the whole
                # group selected instead, so it can be dragged together.
                self.selected_ids = {hit["id"]}
            if hit["id"] in self.selected_ids:
                # Drag the WHOLE current selection together, not just
                # the shape that happened to be clicked.
                starts = {}
                for sid in self.selected_ids:
                    s = self._shape_by_id(sid)
                    if s is not None:
                        starts[sid] = (s["cx"], s["cy"])
                self._drag_state = {"start_world": (wx, wy), "starts": starts}
                self._begin_undoable_change()
            else:
                self._drag_state = None
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
            self._push_undo()
            self.connections.append({
                "id": self._next_connection_id,
                "a_shape": self._connection_pending["from_shape"],
                "a_edge": self._connection_pending["from_edge"],
                "b_shape": self._hover_shape_id, "b_edge": self._hover_edge_index,
            })
            self._next_connection_id += 1
            self._self_loop_highlight = set()
            # A freshly-made connection deselects everything -- the
            # origin shape was selected (that's how its handle was
            # showing in the first place), but the connection itself is
            # the thing that just changed, not that shape.
            self.selected_ids = set()
            self.selected_connection_id = None
        self._connection_pending = None
        self._hover_shape_id = None
        self._hover_edge_index = None
        return made

    def _drop_shape(self, n, wx, wy):
        shape = {"id": self._next_shape_id, "n": n, "cx": wx, "cy": wy, "rotation": 0.0,
                 "flipped": False}
        self._next_shape_id += 1
        self.shapes.append(shape)
        # Left selected (per explicit user request) so it can be
        # immediately rotated, connected, or copied without a separate
        # click -- the _on_palette_clicked call right after this (in
        # _on_canvas_press) only clears a selection when ARMING a new
        # type, not when disarming (which is what actually happens
        # here), so this survives that call.
        self.selected_ids = {shape["id"]}
        self.selected_connection_id = None

    def _on_canvas_drag(self, event):
        if self._drag_state is not None:
            wx, wy = self._screen_to_world(event.x, event.y)
            start_wx, start_wy = self._drag_state["start_world"]
            dx, dy = wx - start_wx, wy - start_wy
            for sid, (start_cx, start_cy) in self._drag_state["starts"].items():
                shape = self._shape_by_id(sid)
                if shape is not None:
                    shape["cx"] = start_cx + dx
                    shape["cy"] = start_cy + dy
            self._redraw()
            return
        if self._marquee_start is not None:
            self._marquee_current = (event.x, event.y)
            self._redraw()

    def _finish_marquee_select(self):
        """Computes which shapes the marquee rectangle (screen-space
        self._marquee_start/_current, see _on_canvas_press/_on_canvas_drag)
        intersects -- each shape's own CURRENT polygon, in world
        coordinates, tested via _rect_intersects_polygon -- and either
        REPLACES the selection with them, or (self._marquee_additive,
        Ctrl was held when the drag started) adds them to whatever was
        already selected. A drag that never actually moved (a plain
        click on empty space) already deselected everything -- or, if
        Ctrl was held, left the existing selection untouched -- at press
        time, so there's nothing further to do for it here."""
        sx0, sy0 = self._marquee_start
        sx1, sy1 = self._marquee_current
        if sx0 == sx1 and sy0 == sy1:
            return
        wx0, wy0 = self._screen_to_world(min(sx0, sx1), min(sy0, sy1))
        wx1, wy1 = self._screen_to_world(max(sx0, sx1), max(sy0, sy1))
        hit_ids = {s["id"] for s in self.shapes
                   if _rect_intersects_polygon(wx0, wy0, wx1, wy1, self._shape_world_vertices(s))}
        if self._marquee_additive:
            self.selected_ids |= hit_ids
        else:
            self.selected_ids = hit_ids

    def _on_canvas_release(self, _event):
        self._drag_state = None
        self._commit_undoable_change()
        if self._marquee_start is not None:
            self._finish_marquee_select()
            self._marquee_start = None
            self._marquee_current = None
            self._redraw()

    def _on_delete_key(self, _event):
        if self.selected_ids:
            self._push_undo()
            for shape_id in self.selected_ids:
                self._remove_shape(shape_id)
            self.selected_ids = set()
            self._redraw()
        elif self.selected_connection_id is not None:
            self._push_undo()
            self.connections = [c for c in self.connections if c["id"] != self.selected_connection_id]
            self.selected_connection_id = None
            self._self_loop_highlight = set()
            self._redraw()

    def _on_escape_key(self, _event=None):
        """Esc: cancels a connection that's been armed from one handle
        (the first click of the click-click gesture -- see module
        docstring's Edge connections section) but not yet completed onto
        a second one -- the dragging-behind red line just disappears,
        with no connection made. A no-op at any other time (no
        in-progress gesture to cancel -- a marquee-drag is abandoned by
        releasing the mouse button outside any shape instead, which
        already just re-selects whatever it happens to enclose)."""
        if self._connection_pending is not None:
            self._connection_pending = None
            self._pending_cursor_screen = None
            self._hover_shape_id = None
            self._hover_edge_index = None
            self._redraw()

    def _on_toggle_debug_mode(self, _event=None):
        self.debug_mode = not self.debug_mode
        self.root.title(f"Interactive Builder{' (debug mode)' if self.debug_mode else ''}")
        self._redraw()

    # ---- undo/redo (Ctrl+Z / Ctrl+Y) ----

    def _snapshot_state(self):
        """A deep-copied {"shapes", "connections", "_next_shape_id",
        "_next_connection_id"} -- everything Ctrl+Z/Ctrl+Y need to
        restore the canvas exactly, deep-copied so neither the snapshot
        nor later live edits can ever mutate the other's data (every
        value here is a plain int/float/bool/dict/list, so this is cheap
        and never needs anything smarter than copy.deepcopy)."""
        return {"shapes": copy.deepcopy(self.shapes), "connections": copy.deepcopy(self.connections),
                "_next_shape_id": self._next_shape_id, "_next_connection_id": self._next_connection_id}

    def _restore_snapshot(self, snap):
        """The inverse of _snapshot_state -- also deep-copies OUT of the
        snapshot, so continuing to edit afterward can never reach back
        and corrupt a still-live undo/redo stack entry. Selection is
        deliberately left untouched by the snapshot itself -- both
        on_undo_key/on_redo_key clear it explicitly right after calling
        this, since a restored canvas may no longer even contain
        whatever used to be selected."""
        self.shapes = copy.deepcopy(snap["shapes"])
        self.connections = copy.deepcopy(snap["connections"])
        self._next_shape_id = snap["_next_shape_id"]
        self._next_connection_id = snap["_next_connection_id"]

    def _record_undo_snapshot(self, snap):
        """Pushes an ALREADY-CAPTURED snapshot onto the undo stack
        (capping it at UNDO_STACK_LIMIT, dropping the OLDEST entry once
        full) and clears the redo stack -- a fresh action, like any
        ordinary undo system, discards whatever redo history existed
        before it, since it's no longer the alternate future that
        history led to."""
        self._undo_stack.append(snap)
        if len(self._undo_stack) > UNDO_STACK_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _push_undo(self):
        """Call BEFORE an instantaneous action (drop, delete, make a
        connection, copy/paste, Clear, Load) that's about to change
        shapes/connections -- captures and records the state right
        before it. A drag/rotate GESTURE uses _begin_undoable_change/
        _commit_undoable_change instead (see their own docstrings for
        why an instantaneous push here isn't the right fit for those)."""
        self._record_undo_snapshot(self._snapshot_state())

    def _begin_undoable_change(self):
        """Call at the START of a gesture that MIGHT change shapes/
        connections (a drag or a rotate) -- captures a snapshot, but
        does NOT push it onto the undo stack yet (see
        _commit_undoable_change, called at the gesture's END, for why:
        a plain click that never actually moved anything shouldn't leave
        a no-op entry in the undo history for a user to needlessly step
        through)."""
        self._pending_undo_snapshot = self._snapshot_state()

    def _commit_undoable_change(self):
        """Call at the END of a gesture begun with _begin_undoable_change
        (on mouse release) -- pushes the snapshot taken at its start onto
        the undo stack, but ONLY if self.shapes/self.connections actually
        differ from it now (a plain click that never moved, or a
        right-click-drag that released immediately, leaves them
        identical) -- comparing the actual dicts/lists rather than, say,
        tracking "did any drag event fire" directly, so this stays
        correct even if a future gesture ends up being a no-op for some
        other reason. A no-op (nothing pending) when called with no
        gesture in progress, so every mouse-release handler can call
        this unconditionally."""
        snap = self._pending_undo_snapshot
        self._pending_undo_snapshot = None
        if snap is None:
            return
        if snap["shapes"] != self.shapes or snap["connections"] != self.connections:
            self._record_undo_snapshot(snap)

    def on_undo_key(self, _event=None):
        """Ctrl+Z: restores the canvas to right before the most recent
        action (_undo_stack's own last entry), pushing the CURRENT state
        onto the redo stack first so Ctrl+Y can step back forward through
        it. No-op with nothing to undo. Clears the selection rather than
        trying to preserve it -- the restored canvas may not even
        contain whatever used to be selected."""
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot_state())
        self._restore_snapshot(self._undo_stack.pop())
        self.selected_ids = set()
        self.selected_connection_id = None
        self._drag_state = None
        self._rotate_state = None
        self._connection_pending = None
        self._self_loop_highlight = set()
        self._redraw()

    def on_redo_key(self, _event=None):
        """Ctrl+Y: the inverse of on_undo_key -- restores the state most
        recently undone, pushing the current state back onto the undo
        stack first. No-op with nothing to redo (including right after
        any fresh action, which clears this stack -- see
        _record_undo_snapshot)."""
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot_state())
        self._restore_snapshot(self._redo_stack.pop())
        self.selected_ids = set()
        self.selected_connection_id = None
        self._drag_state = None
        self._rotate_state = None
        self._connection_pending = None
        self._self_loop_highlight = set()
        self._redraw()

    def on_copy_key(self, _event=None):
        """Ctrl+C: remembers every SELECTED shape's own type, rotation,
        and ABSOLUTE position, PLUS every connection with BOTH endpoints
        among the selected shapes -- one connecting a selected shape to
        one that ISN'T copied along with it has nothing on the other end
        to reproduce, so it's simply dropped, same as _remove_shape
        already does for a shape that's actually deleted. No-op if
        nothing's selected. Storing each shape's own absolute position,
        not an offset relative to the others, is what lets a
        multi-shape paste reproduce the exact same relative arrangement,
        just moved as a whole -- see on_paste_key. Connections reference
        their two shapes by INDEX into this same list (not by id, which
        won't exist yet until paste time creates fresh ones)."""
        if not self.selected_ids:
            return
        copied_shapes = [s for s in self.shapes if s["id"] in self.selected_ids]
        index_of = {s["id"]: i for i, s in enumerate(copied_shapes)}
        self._clipboard = {
            "shapes": [{"n": s["n"], "rotation": s["rotation"], "cx": s["cx"], "cy": s["cy"]}
                       for s in copied_shapes],
            "connections": [
                {"a_index": index_of[c["a_shape"]], "a_edge": c["a_edge"],
                 "b_index": index_of[c["b_shape"]], "b_edge": c["b_edge"]}
                for c in self.connections
                if c["a_shape"] in index_of and c["b_shape"] in index_of
            ],
        }

    def on_paste_key(self, _event=None):
        """Ctrl+V: drops a fresh instance of every copied shape, each at
        its own remembered rotation, ALL offset together by PASTE_OFFSET
        from their remembered positions -- so a multi-shape copy pastes
        back in the same relative arrangement it was copied in, just
        shifted as a group -- PLUS a fresh connection for every one
        copied alongside them (see on_copy_key), between the
        corresponding NEW shapes. No-op if nothing's been copied yet.
        Advances the clipboard's OWN stored positions by that same
        offset every paste, so repeated Ctrl+V cascades diagonally
        outward instead of stacking every copy exactly on top of the
        last one. The new shapes (not the new connections) are left
        selected afterward (replacing whatever was selected before),
        same as a fresh drop."""
        if not self._clipboard:
            return
        self._push_undo()
        new_ids = []
        for entry in self._clipboard["shapes"]:
            entry["cx"] += PASTE_OFFSET
            entry["cy"] += PASTE_OFFSET
            shape = {"id": self._next_shape_id, "n": entry["n"],
                     "cx": entry["cx"], "cy": entry["cy"],
                     "rotation": entry["rotation"], "flipped": False}
            self._next_shape_id += 1
            self.shapes.append(shape)
            new_ids.append(shape["id"])
        for conn in self._clipboard["connections"]:
            self.connections.append({
                "id": self._next_connection_id,
                "a_shape": new_ids[conn["a_index"]], "a_edge": conn["a_edge"],
                "b_shape": new_ids[conn["b_index"]], "b_edge": conn["b_edge"],
            })
            self._next_connection_id += 1
        self.selected_ids = set(new_ids)
        self.selected_connection_id = None
        self._redraw()

    # ---- canvas: right button -- rotate selected shape(s), else pan ----

    def _on_right_press(self, event):
        """Right-drag has two mutually exclusive meanings, chosen once
        here at press time: rotate the CURRENT selection (if non-empty),
        else pan the view. `_rotate_state`/`_pan_last_xy` are never both
        set. A multi-shape selection rotates as one rigid body about its
        own centroid (each shape spins by the same angle AND revolves
        around that shared point) -- for a selection of exactly one,
        this reduces to the original single-shape behavior exactly
        (its own centroid IS its own center, so "revolving" it moves it
        by zero), so there's no special-casing needed between the two."""
        shapes = [s for s in (self._shape_by_id(sid) for sid in self.selected_ids) if s is not None]
        if shapes:
            cx = sum(s["cx"] for s in shapes) / len(shapes)
            cy = sum(s["cy"] for s in shapes) / len(shapes)
            scx, scy = self._world_to_screen(cx, cy)
            self._rotate_state = {"ids": [s["id"] for s in shapes], "center_world": (cx, cy),
                                   "last_angle": math.atan2(event.y - scy, event.x - scx)}
            self._pan_last_xy = None
            self._begin_undoable_change()
        else:
            self._pan_last_xy = (event.x, event.y)
            self._rotate_state = None

    def _on_right_drag(self, event):
        if self._rotate_state is not None:
            cx, cy = self._rotate_state["center_world"]
            scx, scy = self._world_to_screen(cx, cy)
            angle = math.atan2(event.y - scy, event.x - scx)
            delta = angle - self._rotate_state["last_angle"]
            self._rotate_state["last_angle"] = angle
            cos_d, sin_d = math.cos(delta), math.sin(delta)
            for sid in self._rotate_state["ids"]:
                shape = self._shape_by_id(sid)
                if shape is None:
                    continue
                dx, dy = shape["cx"] - cx, shape["cy"] - cy
                shape["cx"] = cx + dx * cos_d - dy * sin_d
                shape["cy"] = cy + dx * sin_d + dy * cos_d
                shape["rotation"] += delta
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
        self._commit_undoable_change()

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
        "occupied"); or an UNFILLED (outline-only) white ring if it's
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
            self._draw_shape(screen_vertices, POLYGON_COLORS[shape["n"]], selected=shape["id"] in self.selected_ids)

        for conn in self.connections:
            endpoints = self._connection_endpoints(conn)
            if endpoints is not None:
                # A connection highlights whenever it's explicitly
                # selected OR it touches any currently-selected shape --
                # the shape at its OTHER end stays its normal color (see
                # the shape-drawing loop above, which only lights up
                # self.selected_ids), so only the line itself, not its
                # neighbour, reads as "part of this".
                highlighted = (conn["id"] == self.selected_connection_id
                               or conn["a_shape"] in self.selected_ids
                               or conn["b_shape"] in self.selected_ids)
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
        joined_points = self._joined_points()

        for shape in self.shapes:
            mids = self._shape_edge_midpoints(shape)
            for edge_index, (mx, my) in enumerate(mids):
                point = (shape["id"], edge_index)
                lit = shape["id"] in self.selected_ids or point in (pending_point, hover_point)
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

        if self.debug_mode and self._cursor_screen is not None:
            self._draw_debug_vertex_label()

        self._draw_self_loop_highlight()

        if self._marquee_start is not None:
            x0, y0 = self._marquee_start
            x1, y1 = self._marquee_current
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=MARQUEE_OUTLINE_COLOR,
                                          dash=MARQUEE_DASH, width=1.5)

    def _draw_self_loop_highlight(self):
        """Rings every corner in self._self_loop_highlight (set by a
        failed Save -- see on_save_clicked/NetValidationError) in
        SELF_LOOP_HIGHLIGHT_COLOR, regardless of debug mode -- this is
        error feedback about the CURRENT state of the canvas, not a
        debug-only diagnostic, so it stays visible even with debug mode
        off, until the next edit clears it (self._self_loop_highlight's
        own comment in __init__ lists every place that happens)."""
        if not self._self_loop_highlight:
            return
        shapes_by_id = {s["id"]: s for s in self.shapes}
        for shape_id, corner in self._self_loop_highlight:
            shape = shapes_by_id.get(shape_id)
            if shape is None or corner >= shape["n"]:
                continue
            vx, vy = self._shape_world_vertices(shape)[corner]
            sx, sy = self._world_to_screen(vx, vy)
            self.canvas.create_oval(sx - 7, sy - 7, sx + 7, sy + 7,
                                     outline=SELF_LOOP_HIGHLIGHT_COLOR, width=2.5)

    def _draw_debug_vertex_label(self):
        """Debug mode only ("d" key): finds the shape VERTEX (a corner,
        not an edge handle) nearest the cursor within
        DEBUG_VERTEX_HOVER_RADIUS and, if one's close enough, rings it
        and labels it "vSHAPE.CORNER" using the hovered corner's OWN
        (shape_id, corner_index) -- ALWAYS that, never the union-find
        ROOT slot _vertex_roots might give it (which can legitimately
        belong to some other, genuinely-connected shape, e.g. shape 42's
        own corner 2 showing as "v34.0" because it's really the same
        vertex as shape 34's corner 0). An earlier version showed that
        root instead, so hovering two corners that already share an id
        showed identical text -- useful in principle, but a user found
        it confusing in practice on a big, densely-connected net like
        hippo.json (lots of neighboring corners are genuinely shared,
        so lots of foreign-looking labels), and asked for every corner
        to always show its own polygon's number. Shared/conflicting
        identity is still fully diagnosable -- just via
        _validate_shapes_connections's Save-time error and its
        _connection_chain trace, not via hovering here. The label is
        drawn white on a 50%-alpha black box (a small PIL RGBA image
        blitted with create_image, since a plain tk.Canvas item can't do
        translucency) since plain colored canvas text was hard to read
        against arbitrary shape colors underneath it."""
        cx, cy = self._cursor_screen
        best, best_dist = None, DEBUG_VERTEX_HOVER_RADIUS
        for shape in self.shapes:
            for corner, (vx, vy) in enumerate(self._shape_world_vertices(shape)):
                sx, sy = self._world_to_screen(vx, vy)
                dist = math.hypot(cx - sx, cy - sy)
                if dist <= best_dist:
                    best, best_dist = (shape, corner, sx, sy), dist
        if best is None:
            return
        shape, corner, sx, sy = best
        self.canvas.create_oval(sx - 4, sy - 4, sx + 4, sy + 4, outline=DEBUG_VERTEX_COLOR, width=1.5)
        label = f"v{shape['id']}.{corner}"
        font = ("TkDefaultFont", 9)
        text_w = tkfont.Font(font=font).measure(label)
        text_h = tkfont.Font(font=font).metrics("linespace")
        pad = 3
        box_w, box_h = text_w + 2 * pad, text_h + 2 * pad
        box_left, box_bottom = sx - box_w / 2, sy - 12 + pad
        box_top = box_bottom - box_h
        bg = Image.new("RGBA", (max(1, round(box_w)), max(1, round(box_h))), (0, 0, 0, 128))
        photo = ImageTk.PhotoImage(bg)
        self._shape_photos.append(photo)  # keep alive -- Tk drops a GC'd PhotoImage
        self.canvas.create_image(box_left, box_top, anchor="nw", image=photo)
        self.canvas.create_text(sx, sy - 12, text=label, fill="white", anchor="s", font=font)


def main():
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    InteractiveBuilderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
