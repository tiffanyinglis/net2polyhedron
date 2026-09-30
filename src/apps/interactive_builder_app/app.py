"""Interactive Builder -- a 2D shape-placement canvas, unrelated to
solving/folding anything: pick a regular polygon from a left-side
palette (triangle through 8-gon, each a fixed color), click to drop
instances of it into a pan/zoomable drawing area in the middle, then
select/drag/rotate/delete them. A right-side tool strip (see "Tool
modes" below) picks which of those canvas interactions is actually
active at any moment, Photoshop/Illustrator-style. File > New/Load/Save/
Save As round-trips the whole canvas to/from a stretchy-mesh-format,
plain-JSON-content ".poly" file (see NET_FILE_EXTENSION and the "net
JSON import/export" section below, near _layout_faces_with_gap) -- the
associated file, once there is one, shows in the window title and is
what Ctrl+S saves straight to.

    python src/apps/interactive_builder_app/app.py

Interaction model:

- **Tool modes (right-side toolbar, `_build_toolbar`)**: a column of
  icon buttons, most of them mode SELECTORS -- clicking one (or its own
  shortcut key) sets `self.tool_mode` (`_set_tool_mode`), which gates
  what clicking on the canvas itself actually does. Switching modes
  clears every piece of transient state that only made sense in the one
  being LEFT (a selection, an armed palette shape, a pending connection,
  an in-progress marquee), so nothing carries over looking selected/
  armed/pending somewhere it can no longer mean anything.
  - **Move [M]** (the default): drag/select shapes (including marquee
    and Ctrl+click multiselect), flip them ([F], `_on_flip_key`, or
    [H]/[V], see below), rotate (right-drag), copy/paste, or delete them
    -- everything this app could do before the toolbar existed.
    Connections are NOT editable in this mode -- every edge's handle
    circle is hidden entirely (`_redraw` only draws them in Join mode),
    since they aren't clickable here; a connection LINE itself still
    draws for context (so the net's current shape stays visible while
    rearranging it), but can't be selected or deleted either.
  - **Join [J]**: the OPPOSITE trade-off -- every edge's handle circle
    shows (same click-click gesture as always, see "Edge connections"
    below, to add a connection) and an existing connection can be
    clicked and deleted, but shapes themselves are NOT selectable at
    all: clicking a shape's body (away from any handle or connection
    line) just deselects, the same as clicking empty space would.
    Nothing can be dropped from the palette (`_on_palette_clicked` is a
    no-op outside Move mode) or pasted (`on_paste_key`, same guard --
    otherwise a clipboard from an EARLIER Move-mode copy would still be
    pasteable here, landing a shape nothing could then select, move, or
    connect to anything).
  - **Polygon Fold**: not a separate mode -- Join's own click-click
    edge-handle gesture also completes onto a SECOND edge of the SAME
    shape (`_hit_test_any_edge_handle`'s `exclude_point`), modeling a
    polygon folded onto itself (e.g. a pinched leg) rather than glued to
    a neighbor. Same handle visibility/occupied-dot rules as an ordinary
    join, and an existing fold connection is selectable/deletable/
    bezier-draggable exactly like any other connection. A flat n-gon
    face can't literally glue two of its own edges together (that's a
    face with a repeated vertex, which `stretchy_mesh.py` disallows) --
    see `_expand_folded_shapes` for how this is resolved at Save time by
    triangulating any shape with >=1 fold connection into `n` triangles
    fanned from its own centroid, so the two folded edges become a
    connection between two genuinely different (triangle) faces. No
    special validation exists for what edges may fold (adjacent edges
    included) -- exactly like an ordinary join, `_validate_shapes_
    connections` is the sole arbiter, now run against that triangulated
    form.
  - **Flip Horizontal [H]** / **Flip Vertical [V]**: plain immediate
    ACTIONS on the current selection (`_flip_selected_shapes`), not
    modes -- clicking either never touches `self.tool_mode`. Mirrors the
    WHOLE selection together, as one rigid arrangement, about the
    shared bounding box of every selected shape's own vertices (not
    each shape independently about its own center) -- the same
    convention Illustrator/Photoshop use for a multi-object flip. See
    its own docstring for why each shape's own reorientation is a pure
    `rotation` change (no new per-shape state, no effect on connections/
    export validity at all) rather than a real reflection transform:
    every shape here is a regular polygon, always congruent to its own
    mirror image.
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
  type, rotation, position, and "flipped" bit (see Flip below), PLUS
  every connection between two selected shapes (one connecting a
  selected shape to one that ISN'T copied along with it has no other
  end to reproduce, so it's simply dropped) (on_copy_key/on_paste_key)
  -- a no-op with nothing selected;
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
- **Flip (F key, `_on_flip_key`)**: toggles "flipped" on every
  currently-selected shape -- a no-op with nothing selected. A
  FRONT-facing (unflipped) shape renders exactly as ever, a solid fill
  in its own POLYGON_COLORS color; a BACK-facing (flipped) one renders
  as diagonal hatching instead, in that SAME color (`_rasterize_polygon`),
  so which side of a shape is meant to face outward is always visible
  at a glance rather than being an invisible internal bit. Flipping
  never touches `self.connections` at all -- a shape's existing
  connections stay exactly where they were made; only which of its
  two sides counts as CCW-from-outside for that shape (_true_edge_slots)
  changes, which is exactly the ambiguity a real connection has (edge
  v1-v2 meeting edge w1-w2 could pair v1~w1/v2~w2 or v1~w2/v2~w1, and
  either is a perfectly legitimate physical gluing -- see _true_edge_
  slots' own docstring) -- flipping one of the two shapes involved is
  what switches between them. There is no automatic flip-solver: for a
  mesh with a real cycle in its connections, more than one flip
  combination often validates, so an automatic search could only find
  "a species of valid," not necessarily the arrangement the user
  actually intends to crochet. An explicit per-shape keypress avoids
  that ambiguity.
- **Esc** cancels a connection that's been armed from one handle (the
  first click of the click-click gesture below) but not yet completed
  onto a second one -- the line following the cursor just disappears,
  with no connection made (`_on_escape_key`).
- **Undo/redo (Ctrl+Z / Ctrl+Y)**: a plain snapshot stack over
  `self.shapes`/`self.connections` (`_push_undo`/`on_undo_key`/
  `on_redo_key`) -- restores the whole canvas as it was one action ago,
  not a field-by-field diff. One entry per WHOLE action: dropping a
  shape, deleting shape(s)/a connection, making a connection, flipping
  shape(s), copy/paste, New, and Load each push one snapshot right
  before they mutate anything, same as any instantaneous action would.
  A drag (move)
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
  dangling reference) -- both directions simply clear it. Each snapshot
  also carries the canvas's own revision NUMBER from the moment it was
  captured (`self._revision`, see its own comment in `__init__`) --
  restoring it, rather than assigning a fresh one, is what makes undoing
  every change made since the last Save read as no-longer-dirty again
  (see "unsaved changes" below), not just "some undo happened".
- **Edge connections**: every shape already on the canvas (not a still-
  armed/not-yet-dropped ghost) has a small circular handle at the
  midpoint of each of its edges -- a single click straight onto any
  handle starts a connection, whether or not that shape is selected. A
  handle that's already the endpoint of a real connection is a solid
  filled dot ("occupied"), stays visible all the time, and is no longer
  clickable at all -- an edge can only ever be joined ONCE; connecting
  an already-joined edge a second time used to silently corrupt a
  hand-built net (transitively merging unrelated vertices on the next
  save). One that isn't yet joined is an UNFILLED (outline-only) ring
  that only shows up once the cursor is close enough to it, to avoid
  clutter on a busy canvas. The reveal distance is the exact same one a
  click needs to actually hit the handle, so "visible" and "clickable"
  never disagree. Click-click, not click-drag:
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
  etc.). A made connection (drawn as a light-grey CUBIC BEZIER curve
  between the two edges' midpoints from then on, tracking both shapes if
  either moves/rotates -- see "Bezier handles" below) deselects
  everything. A connection can itself be clicked (selecting it turns it
  red and deselects any shape) and deleted with Delete, exactly like a
  shape. Deleting either shape a connection touches removes the
  connection too, since a connection with a missing endpoint is
  meaningless.
- **Bezier handles**: every connection is a cubic bezier, not a straight
  line -- freshly made, its two control points sit one third and two
  thirds of the way along the straight line between its edges' own
  midpoints (`_default_connection_handles`), which renders identically
  to a plain line segment until a handle is actually moved. Each control
  point is stored (`{"t", "n"}` on the connection, one pair per end) as a
  world-length offset along its OWN end's edge -- tangent (`t`) and
  outward normal (`n`), `_shape_edge_frame` -- not as an absolute point
  or an offset from the other end, so it tracks that edge's own
  move/rotation exactly like the curve's own endpoint already does, with
  no separate update step anywhere a shape changes. Only ever drawn (as a
  thin red line from the edge midpoint to a filled red dot at the control
  point, `_draw_bezier_handles`) or clickable for the ONE connection
  CURRENTLY selected (`self.selected_connection_id`) -- which, since a
  connection can only be selected in Join mode, also means never in Move
  mode. Dragging one (click-drag straight onto its dot, `_hit_test_
  bezier_handle`) is a single undo step for the whole gesture (`_begin_
  undoable_change`/`_commit_undoable_change`, same pattern a shape drag
  uses) and leaves the connection selected throughout and after.

  **Every corner is its own, separate vertex while editing -- no matter
  what any connection implies about it -- and this is deliberate.**
  `_hit_test_any_edge_handle`'s only two rules for what counts as a
  connectable target are local, unambiguous facts about the ONE edge
  being clicked: it isn't already joined (an edge can only ever be
  joined once), and it isn't on the pending connection's own origin
  shape -- connecting a shape to one of its own other edges isn't
  supported yet (planned for later; needed for a shape like a leg that
  folds back onto itself). Neither depends on what any
  OTHER connection elsewhere happens to imply -- a connection is never
  REJECTED over what it implies about some other, already-accepted
  connection elsewhere. (A full live trial-merge via union-find was
  tried and reverted: it treated corners as fully identified with each
  other during editing rather than as the purely local, pairwise link
  each connection actually is, so an individually-fine connection could
  get silently rejected over what an unrelated connection merely
  implied about a shared corner label.)

  What changed since: full structural validation (vertex-merge-error and
  duplicate-directed-edge checks, `_validate_shapes_connections`) is
  still never a GATE on whether a connection can be made, but it's no
  longer checked only once, at Save -- `_refresh_vme_state` re-runs it
  live after every edit that could change it (making or deleting a
  connection, deleting a shape, flipping one, undo/redo, paste, New,
  Load), so a problem shows up the moment it exists rather than only
  once the user tries to Save. In
  RELEASE mode this is surfaced ONLY as the bottom status bar
  (`_update_status_bar`, "Vertex merge error(s) detected. Fix before
  saving." vs. "Everything is good.") and Save/Save As greying out the
  whole time one exists (`_update_file_menu_state`) -- deliberately no
  per-connection or per-vertex marking on the canvas itself, so a
  release-mode user isn't shown "vSHAPE.CORNER"-flavored internals they
  have no context for; debug mode (below) is where a vertex merge error
  is actually pinpointed, via the always-on dedup vertex display rather
  than anything drawn on a connection. The user can keep working (adding
  shapes, more connections, flips) with one still showing, just can't
  write out an invalid net. Checked directly on
  `self.shapes`/`self.connections`, in the same "vSHAPE.CORNER" terms
  debug mode (below) already shows a user live -- never in terms of the
  fresh integers `_faces_from_shapes` would only assign at export time,
  which a user watching the live app has no reason to recognize.
- **Pan/zoom**: with no shape selected, right-click-drag pans -- dragging
  the background moves the whole view WITH the drag, the same direction
  as the cursor, like grabbing and sliding the canvas itself under a
  fixed cursor. The scroll wheel zooms about
  the CURSOR position (the world point under the cursor is solved for at
  the OLD scale and pinned there again at the new one, so zooming doesn't
  drift the shape under the mouse away from it).
- **File > New/Load/Save/Save As...**: "Save As..." (`on_save_as_clicked`)
  always asks where to write the current shapes/connections out as a
  stretchy-mesh-format, plain-JSON-content `NET_FILE_EXTENSION` (".poly")
  file (see "net JSON import/export" below), defaulting to
  `data/input/stretchy_nets/`, plus a "view" section (`{"scale": self.
  view_scale}`, this app's own extension) so re-Loading it restores the
  same zoom level instead of resetting to the default -- and, on success,
  associates that file with the canvas going forward: its basename
  appears in the window title in brackets (`_update_title`, e.g.
  "Interactive Builder [turtle.poly]"), and it becomes what plain "Save"
  (Ctrl+S, `on_save_clicked`) writes straight
  to with no dialog (falling back to Save As if nothing's associated
  yet -- nowhere to save "directly" to). "New" (`on_new_clicked`)
  clears the canvas back to empty and forgets that association;
  closing the window goes through the exact same check. Both are
  guarded by `_confirm_discard_unsaved`: if anything's changed since the
  last Load/Save/New (`self._dirty`, a read-only property comparing
  `self._revision`/`self._saved_revision` -- see their own comment in
  `__init__`), a dialog asks whether to save first, and a "yes" there
  opens the Save As dialog -- cancelling either that dialog or the
  confirmation itself aborts New/closing rather than silently
  discarding unsaved work. `self._dirty` also drives the title's own "*"
  (right after the bracketed filename, or after "Interactive Builder" if
  none is associated yet) and whether "Save" itself is enabled in the
  File menu at all -- greyed out whenever there's nothing NEW to write
  (not dirty) or the net is currently invalid (see "Edge connections"
  above for `self._vme_active`), both via `_update_file_menu_state`;
  "Save As..." only cares about the latter, since saving a copy under a
  new name is useful even with nothing changed since the last save.
  Ctrl+S and a direct `on_save_as_clicked()` call both re-check
  `self._vme_active` themselves too (a greyed-out menu entry doesn't
  stop a keybinding), refusing with a messagebox instead of silently
  writing an invalid file. Load reads a file back -- a file this app
  itself saved reproduces the EXACT on-screen layout (positions/
  rotations round-trip via its own "net_layout" section, now also
  carrying each shape's "flipped" bit) and zoom level, AND the exact
  shapes/connections themselves (its "builder_connections" section --
  see module docstring's "net JSON import/export" section for why
  "flipped" specifically can only be restored this way, never by
  re-deriving connections from the plain vertex loops alone). A
  hand-authored net with no such sections (e.g. any existing file under
  `data/input/stretchy_nets/`, or one saved before this app tracked
  "flipped" at all) instead gets laid out fresh via a BFS spanning tree
  over shared edges, each face pushed one edge-length away from its
  parent so the result reads as a connected but visibly DISJOINT net
  rather than a seamlessly glued paper one, with every shape starting
  unflipped. In THAT fallback case, a LOADED file's own vertex-id
  NUMBERS are used only TRANSIENTLY, purely to work out which edges were
  connected (`_infer_connections`) -- they never become any kind of
  ongoing identity inside this app. Every corner is immediately
  addressed as `(shape_id, edge_index)` from that point on (fresh shape
  ids, per-shape-local edge indices), the exact same way a freshly-drawn
  shape is -- so the loaded file's own labelling and whatever gets
  exported on the next Save are never required or expected to match;
  only the LIVE `self.connections` at Save time decides that, computed
  once, from scratch (`_faces_from_shapes`). A degenerate edge in the
  source file
  (two adjacent corners of one face already sharing a vertex id -- only
  possible from a file an earlier, buggy version of this app saved) is
  never treated as a connection to itself; it's simply left unconnected,
  with a warning naming which face/vertex, so a malformed file still
  loads instead of failing to open at all.
- **Debug mode ("d" key)**: toggles a window-title suffix and, while on,
  hovering near any shape's own VERTEX (a corner -- distinct from an
  edge's midpoint handle) rings it and labels it "vSHAPE.CORNER" (white
  text on a 50%-alpha black box, for legibility over any shape color
  underneath) using that corner's OWN `(shape_id, corner_index)` --
  ALWAYS that, never the union-find ROOT `_vertex_roots` might give it
  (e.g. shape 42's own corner 2 showing as "v34.0" because it's really
  the same vertex as shape 34's corner 0) -- showing the root instead
  was tried and reverted, since most corners on a densely-connected net
  ARE genuinely shared with a neighbor, making most hovers show a
  foreign-looking label instead of the shape actually under the cursor.
  A failed Save (`_validate_shapes_
  connections`) still names the exact problem in "vSHAPE.CORNER" terms,
  PLUS the specific chain of existing connections responsible
  (`_connection_chain`) -- that, not hovering here, is now how shared or
  conflicting identity actually gets diagnosed.

  Debug mode ALSO always shows a dedup vertex display
  (`_draw_dedup_vertex_labels`, no separate toggle -- on together with
  everything else debug mode turns on), taking the OPPOSITE approach
  from the hover label above, deliberately: EVERY corner of EVERY shape
  is labeled at once, white text on a small filled circle, with its
  dedup GROUP number from `_vertex_roots` -- so two corners already
  merged to the same vertex show the SAME number, at a glance, across
  the whole net. A corner currently part of a genuine vertex merge error
  (in `_validate_shapes_connections`'s own `vertex_merge_error_slots`,
  re-run independently right here rather than reusing whatever
  `_refresh_vme_state` last computed, so this is always exactly current)
  fills RED instead of the usual black -- this, not anything drawn on a
  connection (see "Edge connections" above), is how a vertex merge error
  is actually pinpointed on the canvas. Recomputed fresh on every
  redraw, so a connection made/deleted or a shape flipped is reflected
  immediately with no separate refresh step.

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
from common.ui_theme import PLOT_THEME, STATUS_COLORS
from ui.tooltip import Tooltip
from utils.geometry.polygon_geom import attach_polygon, regular_polygon_vertices

# This app's own File > Save/Save As extension, not ".json" -- still plain JSON content (see module
# docstring's "net JSON import/export" section), just a distinct
# extension marking a file as this pipeline's own net format; also the
# format inflate_polyhedron_app's own "Choose a net" combo scans for
# (STRETCHY_NETS_DIR, see its own refresh_net_list). File > Load still
# ALSO accepts plain ".json" (a second filetypes entry) so every
# existing hand-authored/previously-saved net still opens.
NET_FILE_EXTENSION = ".poly"

# Palette entries, in display order.
POLYGON_NS = [3, 4, 5, 6, 7, 8]

# One FIXED color per polygon type (never per-instance), as an explicit
# (hue_deg, lightness, saturation) table rather than a formula swept
# evenly across all 6 -- per-color tweaks over time left hues unevenly
# spaced, so an explicit table reads more clearly than exceptions
# bolted onto a formula. Order matches POLYGON_NS (triangle..8-gon);
# base lightness/saturation is 0.50/0.65 except where a color's own
# tweak departs from it.
_POLYGON_HLS = [
    (136, 0.38, 0.50),  # triangle: green (darker/less saturated)
    (172, 0.40, 0.65),  # square: turquoise, darkened a bit
    (208, 0.50, 0.65),  # pentagon: blue
    (244, 0.58, 0.65),  # hexagon: darker blue, lightened a bit
    (262, 0.50, 0.65),  # 7-gon: violet
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


def _draw_move_tool_icon(canvas, size, color):
    """An arrow cursor on top of a small pentagon outline -- "Move"."""
    cx, cy = size / 2, size / 2
    verts = [(cx + vx, cy + vy) for vx, vy in _vertices_with_radius(5, size * 0.34)]
    canvas.create_polygon(verts, outline=color, fill="", width=1.5)
    # A plain arrow/cursor silhouette, tip at the pentagon's own upper
    # right, pointing down and to the right -- small enough it reads as
    # "a cursor sitting on a shape" rather than competing with it.
    ax, ay, s = cx + size * 0.08, cy - size * 0.08, size * 0.42
    points = [
        (ax, ay), (ax, ay + s), (ax + s * 0.28, ay + s * 0.74),
        (ax + s * 0.42, ay + s * 1.06), (ax + s * 0.58, ay + s * 0.98),
        (ax + s * 0.44, ay + s * 0.66), (ax + s * 0.72, ay + s * 0.62),
    ]
    canvas.create_polygon(points, outline=color, fill=color)


def _draw_join_tool_icon(canvas, size, color):
    """Two small FILLED circles connected by a line -- "Join"."""
    r = size * 0.12
    y = size / 2
    x1, x2 = size * 0.26, size * 0.74
    canvas.create_line(x1, y, x2, y, fill=color, width=2)
    canvas.create_oval(x1 - r, y - r, x1 + r, y + r, fill=color, outline="")
    canvas.create_oval(x2 - r, y - r, x2 + r, y + r, fill=color, outline="")


def _draw_flip_horizontal_tool_icon(canvas, size, color):
    """A horizontal double-headed arrow -- "Flip Horizontal"."""
    y = size / 2
    canvas.create_line(size * 0.18, y, size * 0.82, y, fill=color, width=2,
                        arrow=tk.BOTH, arrowshape=(8, 10, 4))


def _draw_flip_vertical_tool_icon(canvas, size, color):
    """A vertical double-headed arrow -- "Flip Vertical"."""
    x = size / 2
    canvas.create_line(x, size * 0.18, x, size * 0.82, fill=color, width=2,
                        arrow=tk.BOTH, arrowshape=(8, 10, 4))

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
# Debug mode's always-on dedup vertex display: every corner is labeled
# with its dedup GROUP number (_vertex_roots), white text on a small
# filled circle -- black normally, or DEDUP_VERTEX_CONFLICT_BG for a
# corner currently part of a genuine vertex merge error -- see
# _draw_dedup_vertex_labels.
DEDUP_VERTEX_RADIUS = 9.0
DEDUP_VERTEX_BG = "black"
DEDUP_VERTEX_CONFLICT_BG = "red"
DEDUP_VERTEX_FG = "white"
# A handle's resting color, when its shape is neither selected nor the
# current hover target of a pending connection -- SELECTION_OUTLINE_COLOR
# is used instead in those two cases (see _redraw), so a handle reads as
# "active" in the same color a selection does, and plain white otherwise.
HANDLE_COLOR = "white"
CONNECTION_COLOR = "#b0b0b0"
CONNECTION_WIDTH = 1.5
CONNECTION_SELECTED_WIDTH = 2.5
# How many straight segments a connection's cubic bezier is sampled into
# for drawing/hit-testing -- high enough to read as a smooth curve at
# this app's own line widths, not an actual Tk spline (see
# _cubic_bezier_points).
BEZIER_CURVE_STEPS = 24
# A connection's two adjustable control-point handles (module docstring:
# "Edge connections" -- new bezier section) -- only ever drawn/clickable
# for the ONE connection currently selected (self.selected_connection_id),
# never for one merely highlighted via an endpoint shape's own selection.
# Same red as SELECTION_OUTLINE_COLOR (it IS the selected connection's own
# UI), but its own thin line/small dot rather than reusing
# SELECTION_OUTLINE_WIDTH/EDGE_HANDLE_RADIUS, since a control handle reads
# as a lightweight annotation on top of the curve, not another primary
# selectable thing at the same visual weight as a shape outline or a real
# edge handle.
BEZIER_HANDLE_COLOR = SELECTION_OUTLINE_COLOR
BEZIER_HANDLE_LINE_WIDTH = 1.0
BEZIER_HANDLE_RADIUS = 4.0
BEZIER_HANDLE_HIT_RADIUS = 9.0

# File menu colors (_build_menu) -- a plain tk.Menu on Windows otherwise
# falls back to the OS's own native menu chrome, which draws a DISABLED
# entry (e.g. Save while self._vme_active or not self._dirty -- see
# _update_file_menu_state) with a light, embossed 3D style meant for a
# light-colored menu; against this app's dark theme that reads as a
# stray light box around the disabled entry rather than a dim, greyed-
# out one. Setting explicit colors switches Tk to its own (non-native)
# flat menu rendering instead, which respects `disabledforeground`
# properly. activebackground/activeforeground are the hover highlight.
MENU_BG = PLOT_THEME["bg"]
MENU_FG = PLOT_THEME["fg"]
MENU_ACTIVE_BG = "#3a3a3a"
MENU_DISABLED_FG = "#6e6e6e"

# Right-side tool strip (_build_toolbar) -- see module docstring's "Tool
# modes" section for what each button actually does.
TOOLBAR_ICON_SIZE = 40
TOOLBAR_ICON_COLOR = PLOT_THEME["fg"]
# The current tool's own icon gets this border (mirrors the palette's
# own "armed" white border, _on_palette_clicked) -- plain PLOT_THEME["bg"]
# (i.e. no visible border) otherwise.
TOOLBAR_ACTIVE_BORDER = "white"

# Marquee (rubber-band) select's own drag rectangle -- see
# _on_canvas_press/_on_canvas_drag/_finish_marquee_select. Plain white
# dashed outline, no fill (a filled/tinted rectangle would need the same
# Pillow-alpha-compositing trick _draw_debug_vertex_label uses for its
# label background, not worth it just for this) -- distinct enough from
# SELECTION_OUTLINE_COLOR (red, solid) that a marquee in progress can't
# be confused with an actual selected shape's outline.
MARQUEE_OUTLINE_COLOR = "white"
MARQUEE_DASH = (5, 5)

# A flipped shape (see "flipped" in the module docstring's Flip section)
# renders as diagonal hatching instead of a solid fill, in the same
# per-type color -- constant SCREEN pixels, not scaled by view_scale,
# same rationale as SELECTION_OUTLINE_WIDTH etc.
HATCH_LINE_SPACING = 10.0
HATCH_LINE_WIDTH = 2.0

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


def _cubic_bezier_points(p0, p1, p2, p3, steps=BEZIER_CURVE_STEPS):
    """Samples the cubic bezier curve p0->p1->p2->p3 (p0/p3 the curve's
    own endpoints, p1/p2 its two control points) into `steps` straight
    segments -- Tk has no true two-control-point bezier primitive, so a
    connection's curve is drawn/hit-tested as a plain polyline through
    these sampled points instead (see _draw_connection_curve)."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1.0 - t
        x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        points.append((x, y))
    return points


def _closest_point_index(point, points):
    """Index into `points` of whichever one is nearest `point` -- used
    by _flip_selected_shapes to work out which NEW edge index a
    reflected shape's edge ended up at, by matching against where the
    OLD edge's own midpoint should land once mirrored (see its own
    docstring)."""
    return min(range(len(points)),
               key=lambda j: math.hypot(points[j][0] - point[0], points[j][1] - point[1]))


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


def _rasterize_polygon(screen_vertices, fill_hex, outline_hex=None, outline_width=0, hatched=False):
    """screen_vertices: [(x, y), ...] in CANVAS pixel space. Renders just
    this polygon's own (padded) bounding box, supersampled by
    SUPERSAMPLE and LANCZOS-downsampled for anti-aliased edges -- see
    module docstring's Rendering section for why this exists instead of
    a plain tk.Canvas polygon item. `hatched` (see module docstring's
    "Flip" section) draws diagonal lines in `fill_hex` instead of a solid
    fill -- how a flipped shape reads as "the other side" at a glance,
    still in its own per-type color. Returns (PhotoImage, (left, top)) --
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
    if hatched:
        # PIL has no direct "hatched fill" primitive: draw the lines
        # across the WHOLE image, then clip them to the polygon via a
        # mask (big itself starts fully transparent, so compositing
        # straight onto it -- rather than drawing the lines first and
        # masking afterward -- needs no separate "erase outside the
        # polygon" step).
        mask = Image.new("L", big.size, 0)
        ImageDraw.Draw(mask).polygon(local, fill=255)
        hatch = Image.new("RGBA", big.size, (0, 0, 0, 0))
        hatch_draw = ImageDraw.Draw(hatch)
        spacing = max(1, round(HATCH_LINE_SPACING * SUPERSAMPLE))
        line_width = max(1, round(HATCH_LINE_WIDTH * SUPERSAMPLE))
        w, h = big.size
        for x0 in range(-h, w, spacing):
            hatch_draw.line([(x0, 0), (x0 + h, h)], fill=_rgba(fill_hex), width=line_width)
        big = Image.composite(hatch, big, mask)
        draw = ImageDraw.Draw(big)
    else:
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
# for the full convention), plus "edges" (_edges_from_shapes), a new
# "source_polygon_id" (see below), and two extra top-level keys this app
# alone understands: "net_layout" and "builder_connections".
#
# Since Polygon Fold (module docstring's "Tool modes" section), a shape
# with >=1 fold connection is exported as `n` TRIANGLES (see
# _expand_folded_shapes), so "faces"/"edges"/"face_edge_ids"/
# "source_polygon_id" are no longer necessarily one entry per PLACED
# shape -- but "net_layout"/"builder_connections" still describe the
# ORIGINAL placed shapes directly (this app never shows/edits individual
# fan triangles), so they're keyed by SHAPE ID now, not by position/index
# into "faces":
#
# - "net_layout": one entry per placed shape, each
#   {"shape_id", "n", "cx", "cy", "rotation", "flipped"} -- exactly the
#   fields a shape already carries, plus its own id, as it looked on
#   screen when saved. "n" lets a reader reconstruct the ORIGINAL
#   polygon's own outline even once it's been triangulated away in
#   "faces" (see inflate_polyhedron_app's own _layout_from_net_layout).
# - "builder_connections": self.connections translated to
#   {"a_shape_id", "a_edge", "b_shape_id", "b_edge", "a_handle",
#   "b_handle"} -- shape ids directly (a fresh shape has no id yet at
#   load time, so these are remapped through a freshly-assigned id table
#   on Load, same idea as before just no longer routed through a `faces`
#   position at all). "a_handle"/"b_handle" (the {"t", "n"} bezier
#   control-point offsets -- module docstring's "Bezier handles" section)
#   are read back as-is, or defaulted via _default_connection_handles for
#   an older file's entry that predates them.
#
# A "net_layout" entry with no "shape_id" (any file saved before Polygon
# Fold existed) is legacy, index-aligned data -- back when every shape
# was necessarily exactly one face, its own list position already WAS
# its shape identity for this purpose, so _load_faces (interactive_
# builder_app) and _layout_from_net_layout (inflate_polyhedron_app) both
# fall back to that position as the shape id, and legacy
# "builder_connections" entries keep their own original "a_face"/
# "b_face" naming (also just an index into that same list) rather than
# "a_shape_id"/"b_shape_id" -- every such file still loads exactly as it
# always has, nothing about this app's own Polygon-Fold-free reading of
# it changes.
#
# "source_polygon_id" is a NEW list parallel to "faces": the ORIGINAL
# placed shape's own id that face came from -- identical for every one
# of a folded polygon's `n` triangles, and for a face that's just an
# ordinary, non-folded shape, it's simply that shape's own id too. This
# is purely a downstream DISPLAY aid (inflate_polyhedron_app colors/
# groups same-source-polygon triangles together) -- stretchy_mesh.py/
# mesh_levels.py don't read it at all.
#
# "edges"/"face_edge_ids" are NOT this app's own private extension the
# way "net_layout"/"builder_connections" are -- stretchy_mesh.py and
# mesh_levels.py themselves read them (when present) as authoritative,
# in place of re-deriving edge identity purely from "faces"' shared
# vertex ids. That re-derivation is ambiguous once two faces glued along
# multiple edges merge unrelated corners onto the same vertex ids: two
# of their remaining FREE edges can then coincidentally land on the
# exact same vertex-id pair as each other despite never being connected,
# and a plain vertex-pair set can't tell that apart from a genuinely
# shared edge (see _edges_from_shapes' own docstring). "edges" fixes
# this for the base mesh's own springs (stretchy_mesh.mesh_edges);
# "face_edge_ids" (_face_edge_ids_from_shapes) fixes the same ambiguity
# for mesh_levels.subdivide_once's own Level 1->2 rim-edge splitting,
# which needs a per-FACE-EDGE answer ("is THIS specific edge of THIS
# specific face the same physical edge as that one?"), not just the
# per-mesh-edge one "edges" gives. This app is the one place either
# ambiguity can still be resolved, since self.connections still records
# exactly which shape-edges are actually glued -- so both are written on
# every Save, alongside "faces", not left for a reader to reconstruct.
# Any OTHER program reading this file only ever looks at "faces"/"name"
# (or now also "edges"/"face_edge_ids") and has no reason to know
# "net_layout"/"builder_connections" exist, so it's free to ignore those
# two.
#
# "flipped" can ONLY be correctly restored together with
# "builder_connections" -- never by re-deriving connections from "faces"
# alone (_infer_connections) and setting "flipped" on top of THAT, which
# corrupts the mesh (see _load_faces' own docstring for exactly why:
# _faces_from_shapes already bakes each shape's true winding into its
# exported loop, so a freshly re-derived connection set already assumes
# every shape is unflipped, and flipping one afterward reverses all of
# its edges relative to what those connections expect). So both keys are
# always written and read together.
#
# Loading a file with no "net_layout" (any hand-authored net under
# data/input/stretchy_nets/, for instance, or one saved before this app
# tracked "flipped"/"builder_connections" at all) instead falls back to
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

GAP = DEFAULT_SHAPE_EDGE_LENGTH  # separated by one edge length


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
    unconnected instead of raising. A DEGENERATE edge (both endpoints the
    same vertex id -- only possible from a file saved by an earlier,
    buggy version of this app; see _degenerate_edge_faces) is skipped
    entirely rather than treated as its own reverse partner, which is
    what a naive directed-edge lookup would otherwise do: `(v, v)`'s
    reverse is also `(v, v)`, so without this guard a degenerate edge
    would silently infer a connection from that edge to ITSELF (same
    face, same edge index on both ends) -- exactly the kind of
    nonsensical entry _validate_shapes_connections exists to catch at
    Save, but there was never any reason to let Load manufacture one in
    the first place."""
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
    is flipped (see "Flip" in the module docstring). A regular polygon
    placed in this app can only be rotated, never mirrored, so its DRAWN
    corner order always has the same fixed handedness; "flipped" is a
    per-shape bit, set directly by the user (select shapes, press F),
    saying that shape's face is meant to be viewed from the OTHER side
    of the solid, which reverses every one of its edges' TRUE direction
    relative to how they're drawn -- this is the one place that fact
    gets applied, so every caller (_connection_pairs, _faces_from_shapes,
    _validate_shapes_connections) agrees."""
    sid, n = shape["id"], shape["n"]
    a, b = (sid, edge_index), (sid, (edge_index + 1) % n)
    return (b, a) if shape.get("flipped", False) else (a, b)


def _shape_face_corner_order(shape):
    """The corner-index order _faces_from_shapes/_validate_shapes_connections
    read a shape's OWN face loop in, matching _true_edge_slots: forward
    (0, 1, ..., n-1) normally, or reversed (n-1, ..., 1, 0) when flipped
    -- a flipped shape's consecutive TRUE edges only chain into a valid
    cyclic loop when its corners are visited in reverse."""
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
    a flipped shape's own face loop must be read backward to come out
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


def _edges_from_shapes(shapes, connections):
    """shapes/connections: as _vertex_roots/_faces_from_shapes. Returns
    the explicit mesh-edge list: one [v, w] vertex-id pair per genuine
    edge, in the SAME vertex-id numbering _faces_from_shapes assigns
    (same roots, same shape/corner visiting order, so ids here line up
    1:1 with that function's own output for the same shapes/
    connections). Each connection's own glued pair of shape-edges
    contributes exactly ONE entry (not one per side); every other
    (free/boundary) shape-edge contributes its own separate entry too,
    even when its vertex-id pair happens to coincide with some other
    free edge's -- two coincidentally-same-pair boundary edges are NOT
    the same edge once vertex dedup has merged unrelated corners onto
    the same ids (e.g. two faces glued along a pair of opposite edges
    merges all 4 corners pairwise, so the two faces' own remaining free
    edges can land on the exact same vertex-id pair as each other by
    coincidence). A plain vertex-pair set rebuilt from `faces` alone
    can't tell that case apart from a genuinely shared edge -- this
    explicit list is what stretchy_mesh.mesh_edges prefers instead, when
    present, so a duplicate pair here is deliberate, not a bug to
    dedupe."""
    roots = _vertex_roots(shapes, connections)
    vertex_ids = {}

    def vid(slot):
        root = roots[slot]
        if root not in vertex_ids:
            vertex_ids[root] = len(vertex_ids)
        return vertex_ids[root]

    # Assign ids in the exact same order _faces_from_shapes does, so a
    # root's id here always matches that function's own numbering.
    for shape in shapes:
        for corner in _shape_face_corner_order(shape):
            vid((shape["id"], corner))

    shapes_by_id = {s["id"]: s for s in shapes}
    glued_slots = {(conn["a_shape"], conn["a_edge"]) for conn in connections} | \
                  {(conn["b_shape"], conn["b_edge"]) for conn in connections}

    edges = []
    seen_conns = set()
    for conn in connections:
        pair_key = frozenset({(conn["a_shape"], conn["a_edge"]),
                               (conn["b_shape"], conn["b_edge"])})
        if pair_key in seen_conns:
            continue
        seen_conns.add(pair_key)
        n = shapes_by_id[conn["a_shape"]]["n"]
        edges.append([vid((conn["a_shape"], conn["a_edge"])),
                      vid((conn["a_shape"], (conn["a_edge"] + 1) % n))])

    for shape in shapes:
        n = shape["n"]
        for e in range(n):
            if (shape["id"], e) in glued_slots:
                continue
            edges.append([vid((shape["id"], e)), vid((shape["id"], (e + 1) % n))])

    return edges


def _face_edge_ids_from_shapes(shapes, connections):
    """shapes/connections: as _vertex_roots/_faces_from_shapes. Returns a
    list parallel to _faces_from_shapes' own `faces`: face_edge_ids[fi]
    is a list of n small ints, one per edge of that face's own exported
    vertex loop (edge k runs from loop position k to loop position
    (k+1) % n -- REVERSED from raw shape-edge order when that shape is
    flipped, same as _faces_from_shapes/_shape_face_corner_order's own
    order, see _true_edge_slots). Two face-edges get the SAME id iff a
    connection glues them (the same genuine mesh edge, seen from its two
    faces); every other face-edge gets an id no other face-edge uses (a
    free/boundary edge).

    This is what lets mesh_levels.subdivide_once (via a saved file's own
    "face_edge_ids" field) correctly disambiguate a rim edge during
    Level 1->2 subdivision -- see _edges_from_shapes' own docstring for
    why a plain vertex-id pair can't tell a genuinely shared edge apart
    from two independent free edges that coincidentally share a
    vertex-id pair after dedup: without this, subdividing a net like
    that would silently weld two unrelated boundary edges' new midpoints
    into one, the exact same bug _edges_from_shapes fixes for the
    UNsubdivided mesh's own springs."""
    glued_partner = {}
    for conn in connections:
        a_slot = (conn["a_shape"], conn["a_edge"])
        b_slot = (conn["b_shape"], conn["b_edge"])
        glued_partner[a_slot] = b_slot
        glued_partner[b_slot] = a_slot

    def raw_edge_for_loop_position(shape, k):
        # Loop position k runs corner_order[k] -> corner_order[k+1]
        # (_shape_face_corner_order); for an unflipped shape that's raw
        # edge k directly, and for a flipped one (corner_order reversed)
        # it works out to raw edge (n - 2 - k) % n.
        n = shape["n"]
        return k if not shape.get("flipped", False) else (n - 2 - k) % n

    next_id = 0
    id_of_slot = {}
    face_edge_ids = []
    for shape in shapes:
        n = shape["n"]
        ids_for_face = []
        for k in range(n):
            slot = (shape["id"], raw_edge_for_loop_position(shape, k))
            cid = id_of_slot.get(slot)
            if cid is None:
                cid = next_id
                next_id += 1
                id_of_slot[slot] = cid
                partner = glued_partner.get(slot)
                if partner is not None:
                    id_of_slot[partner] = cid
            ids_for_face.append(cid)
        face_edge_ids.append(ids_for_face)
    return face_edge_ids


def _expand_folded_shapes(shapes, connections):
    """Returns (expanded_shapes, expanded_connections, source_polygon_id)
    -- the actual structure to validate/export (see
    _validate_shapes_connections/_faces_from_shapes/_edges_from_shapes/
    _face_edge_ids_from_shapes, all fed THIS rather than the raw
    `shapes`/`connections`). A flat n-gon face can't have two of its own
    edges glued directly (that's a face with a repeated vertex in its own
    loop -- a structural impossibility the same way any other vertex
    merge error is); a Polygon Fold connection (module docstring's "Tool
    modes" section -- a connection with `a_shape == b_shape`) resolves
    this by triangulating that WHOLE shape into `n` triangles fanned from
    a new centroid vertex, exactly like mesh_levels._fan_level_0_to_1's
    own Level 0->1 subdivision: triangle i is (corner i, corner i+1,
    centroid), with true (`_true_edge_slots`, flip already baked in)
    corner order [0, 1, 2] and RAW edge indices 0 (the one true OUTER
    edge -- corner i -> corner i+1, i.e. the original polygon's own edge
    i), 1 (corner i+1 -> centroid), 2 (centroid -> corner i). Every
    triangle is given `flipped=False` -- there's nothing left to flip,
    since flip was already resolved into which raw edge IS the true
    outer edge before this ever runs.

    Every connection (an ordinary inter-shape one, or a same-shape fold
    one) that touches a folded shape's raw edge i is rewritten onto that
    shape's triangle i's edge 0 -- both cases are just "a connection
    touching this polygon's edge i", so no special-casing is needed
    between them; a fold connection's two ends simply land on two
    DIFFERENT triangles' edge 0, which is exactly what turns it into a
    genuine two-different-faces connection the existing union-find
    machinery already knows how to validate. Each folded shape's own `n`
    spokes are added as new connections gluing consecutive triangles at
    the shared centroid (triangle i's edge 1 <-> triangle (i+1)%n's edge
    2), which unions triangle i's own corner 1 with triangle (i+1)%n's
    corner 0 (the shared original corner i+1) AND both triangles' own
    corner 2 (the shared centroid) -- exactly the sharing a real fan of
    triangles has.

    `source_polygon_id` is parallel to `expanded_shapes` (and, after
    _faces_from_shapes, to the exported "faces"): the ORIGINAL shape's
    own id, for every triangle from one fan and for every untouched shape
    alike -- a pure downstream grouping/coloring aid (see
    inflate_polyhedron_app), never read by stretchy_mesh.py/
    mesh_levels.py. Non-folded shapes/connections pass through completely
    unchanged, both in identity (same shape dict, same id) and position
    in the returned lists."""
    fold_shape_ids = {c["a_shape"] for c in connections if c["a_shape"] == c["b_shape"]}

    expanded_shapes = []
    source_polygon_id = []
    for shape in shapes:
        if shape["id"] in fold_shape_ids:
            for i in range(shape["n"]):
                expanded_shapes.append({"id": (shape["id"], i), "n": 3, "flipped": False})
                source_polygon_id.append(shape["id"])
        else:
            expanded_shapes.append(shape)
            source_polygon_id.append(shape["id"])

    def _retarget(shape_id, edge):
        if shape_id in fold_shape_ids:
            return (shape_id, edge), 0
        return shape_id, edge

    expanded_connections = []
    for conn in connections:
        a_shape, a_edge = _retarget(conn["a_shape"], conn["a_edge"])
        b_shape, b_edge = _retarget(conn["b_shape"], conn["b_edge"])
        expanded_connections.append(
            {"a_shape": a_shape, "a_edge": a_edge, "b_shape": b_shape, "b_edge": b_edge})

    for shape in shapes:
        if shape["id"] not in fold_shape_ids:
            continue
        n, pid = shape["n"], shape["id"]
        for i in range(n):
            expanded_connections.append({
                "a_shape": (pid, i), "a_edge": 1,
                "b_shape": (pid, (i + 1) % n), "b_edge": 2,
            })

    return expanded_shapes, expanded_connections, source_polygon_id


def _degenerate_edge_faces(faces):
    """faces: vertex-id loops, as freshly read from a file (BEFORE
    _infer_connections has had a chance to skip anything). Returns
    [(face_index, vertex_id), ...] for every DEGENERATE edge found -- two
    ADJACENT corners of one face already sharing a vertex id, which can
    only come from a file saved by an earlier, buggy version of this app
    (a correctly-behaving Save can never produce one; see
    _export_faces_and_layout/_validate_shapes_connections). Purely
    diagnostic: Load calls this just to warn the user that edge(s) were
    left unconnected on the way in, since _infer_connections silently
    skips them rather than raising (a malformed file should still load,
    not block the user from opening and fixing it)."""
    problems = []
    for fi, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            if face[i] == face[(i + 1) % n]:
                problems.append((fi, face[i]))
    return problems


def _connection_chain(shapes, connections, slot_a, slot_b):
    """Returns the shortest list of connections (as {"a_shape", "a_edge",
    "b_shape", "b_edge"} dicts, in traversal order) whose unions link
    slot_a to slot_b -- i.e. the actual reason _vertex_roots gave them
    the same root, spelled out as the specific chain of edge-to-edge
    connections responsible, rather than just the shared root itself.
    A vertex merge error (a corner collapsing onto itself, or a duplicate
    directed edge) is never caused by one
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


def _count_shape_components(shapes, connections):
    """Number of connected components among `shapes` via `connections` ("a_shape"/"b_shape"
    endpoints) -- a small union-find, used ONLY by _save_to_path's own multi-component Save
    restriction below (this app forbids saving a net with more than one connected component,
    so there's never an "anchor piece" ambiguity; only interactive_inflater_app's own session
    files allow more than one component) -- not shared with interactive_inflater_app's own
    equivalent (which needs this for a different reason, finding which piece is the "central
    object" anchor), since that file already imports FROM this one; importing back would be
    circular, and this is a self-contained handful of lines either way. Returns 0 for an empty
    net (never counts as "more than one piece")."""
    if not shapes:
        return 0
    parent = {s["id"]: s["id"] for s in shapes}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for c in connections:
        a, b = find(c["a_shape"]), find(c["b_shape"])
        if a != b:
            parent[a] = b
    return len({find(s["id"]) for s in shapes})


class NetValidationError(ValueError):
    """Raised by _validate_shapes_connections instead of a plain
    ValueError, carrying `vertex_merge_error_slots` -- the {(shape_id,
    corner_index), ...} set of every corner involved in a vertex merge
    error (a corner colliding with another corner of its own face, both
    endpoints of each one found) -- alongside the usual message.
    Debug mode's dedup vertex display (_draw_dedup_vertex_labels) is the
    app's own live consumer of this: it fills a corner's circle red iff
    that corner's slot is in `vertex_merge_error_slots`. A plain
    `str(err)` still gives the same message a bare ValueError would."""

    def __init__(self, message, vertex_merge_error_slots=frozenset()):
        super().__init__(message)
        self.vertex_merge_error_slots = vertex_merge_error_slots


def _validate_shapes_connections(shapes, connections):
    """shapes/connections: as _vertex_roots. Two checks can fail: a
    face's own two (different) corners ending up merged into the same
    vertex (a VERTEX MERGE ERROR -- a face's own edge would have to run
    from a point to itself, a genuine structural impossibility), or a
    single edge slot being claimed by more than one connection (already
    prevented live by _hit_test_any_edge_handle excluding an
    already-joined handle from being clickable -- checked again here
    too, since this function is meant to be the authoritative,
    from-scratch check right before a file is written, not something
    that trusts the live UI alone).

    Two DIFFERENT, otherwise-unrelated edges resolving to the same
    directed (or reversed) vertex pair is deliberately NOT checked here
    -- see stretchy_mesh.py's module docstring's WINDING CONVENTION
    section and interactive_builder_app's own "net JSON import/export"
    section for why: vertex dedup can legitimately merge enough corners
    that two edges that were never explicitly connected to EACH OTHER
    (each already fully accounted for by its own connection, or each its
    own free/boundary edge) end up sharing a vertex-id pair by pure
    coincidence -- e.g. two faces glued along a pair of opposite edges
    merges all their OTHER corners pairwise too, so their remaining free
    edges land on the same pair; or a fan of shapes glued opposite each
    other around a shared hub does the same to two of their already-glued
    spokes. Neither case is an actual conflict: each edge is still shared
    by (at most) its own 2 faces, they just happen to run between the
    same two (now-merged) points as some unrelated edge -- exactly like
    two independent springs between the same two points, not one edge
    being claimed twice. Rejecting that coincidence outright (an earlier
    version of this check did) blocks perfectly buildable nets for no
    real structural reason. A genuine problem -- the SAME edge slot
    actually being asked to serve two different connections -- is caught
    by the slot-reuse check above instead, which doesn't depend on
    vertex-id coincidence at all.

    Raises a NetValidationError (see its own docstring) phrased in terms
    of the LIVE "vSHAPE.CORNER" vertex identity _draw_debug_vertex_label
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

    A vertex merge error is never caused by a single connection
    considered on its own -- see _connection_chain's own docstring -- so
    its problem message also names the SPECIFIC chain of existing
    connections whose transitive merge (via _vertex_roots) is what
    actually ties the conflicting corners together, e.g. because a face
    otherwise untouched by whatever was just connected can still end up
    implicated if its own two corners were already, separately, drawn
    into the same larger group some other connection elsewhere set up.
    Read literally: "shape 9's corners 2 and 3 already come out to the
    same vertex once you trace shape 9 edge 1 -> shape 4 edge 0 -> shape
    4 edge 2 -> shape 9 edge 3" -- exactly the reasoning a user would
    have to redo by hand with debug mode alone, spelled out for them
    instead."""
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
    vertex_merge_error_slots = set()
    for shape in shapes:
        n, sid = shape["n"], shape["id"]
        for i in range(n):
            # _true_edge_slots, not the raw (sid, i)/(sid, (i+1)%n) pair --
            # a flipped shape's edge i has its TRUE v/w corners reversed,
            # and this check has to agree with _connection_pairs/
            # _faces_from_shapes about what each shape's own edges
            # actually connect to.
            slot_v, slot_w = _true_edge_slots(shape, i)
            v, w = roots[slot_v], roots[slot_w]
            if v == w:
                problems.append(
                    f"shape {sid} edge {i} (corners {slot_v[1]}->{slot_w[1]}) "
                    f"already merges to the same vertex {vlabel(v)}{chain_text(slot_v, slot_w)}")
                vertex_merge_error_slots.add(slot_v)
                vertex_merge_error_slots.add(slot_w)

    slot_owner = {}
    for conn in connections:
        for slot in ((conn["a_shape"], conn["a_edge"]), (conn["b_shape"], conn["b_edge"])):
            if slot in slot_owner:
                problems.append(
                    f"shape {slot[0]} edge {slot[1]} is joined by more than one connection")
            else:
                slot_owner[slot] = conn

    if problems:
        raise NetValidationError(
            "Not a valid net, refusing to save:\n  " + "\n  ".join(problems), vertex_merge_error_slots)


class InteractiveBuilderApp:
    def __init__(self, root):
        self.root = root
        root.title("Interactive Builder")
        root.geometry("1100x700")
        root.minsize(700, 450)

        sv_ttk.set_theme("dark")
        self._scale_ui_fonts()

        # Which canvas interaction is currently active -- "move" (drag/
        # select/flip/copy/paste shapes; connections stay visible but
        # unselectable) or "join" (add/delete connections; shapes become
        # unselectable, nothing can be dropped or pasted) -- see
        # _set_tool_mode, bound to the right-side toolbar's own buttons
        # and to the M/J keys. "move" is the default -- everything this
        # app could do before the toolbar existed.
        self.tool_mode = "move"
        # {mode_name: icon_canvas} for the toolbar's own MODE buttons
        # (Move/Join, not the plain-action Flip buttons) -- filled in by
        # _build_toolbar, read by _update_toolbar_highlight to ring
        # whichever one is current.
        self.toolbar_buttons = {}

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
        # {"conn_id", "end"} ("a" or "b") while a bezier control-point
        # handle is being dragged (_on_canvas_press_join/_on_canvas_drag),
        # None otherwise -- same "begin/commit" undo gesture pattern as
        # _drag_state, sharing _begin_undoable_change/_commit_undoable_change
        # with it (both mutate self.connections/self.shapes, which is all
        # that snapshot compares).
        self._bezier_handle_drag = None
        self._pan_last_xy = None
        self._rotate_state = None
        self._shape_photos = []  # keeps this redraw's PhotoImages alive (Tk drops GC'd ones)
        self._icon_photos = {}
        # Whether the CURRENT self.shapes/self.connections has a vertex
        # merge error right now -- see _refresh_vme_state, called after
        # every edit that could change validity (not just at Save any
        # more). Drives the bottom status message and disables Save/Save
        # As (_update_file_menu_state) while True. Debug mode's own
        # dedup vertex display (_draw_dedup_vertex_labels) independently
        # re-validates to know which specific corners to ring red --
        # this flag is only ever the plain yes/no answer.
        self._vme_active = False

        # [{"id", "a_shape", "a_edge", "b_shape", "b_edge", "a_handle",
        # "b_handle"}, ...] -- edge indices are stable across a shape's
        # own move/rotation (they just name a position in its local
        # vertex loop), so a connection never stores an absolute
        # coordinate for its two ENDPOINTS. Its two bezier control points
        # (module docstring's "Bezier handles" section) are the one
        # exception -- {"t", "n"} world-length offsets, but along their
        # OWN end's edge frame (_shape_edge_frame), not an absolute point
        # either, for the exact same reason: staying meaningful across
        # that edge's own move/rotation with no separate update step.
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

        # File currently associated with the canvas (a successful Load
        # or Save/Save As sets this; File > New clears it back to None)
        # -- shown in the window title (_update_title) and what Ctrl+S
        # saves straight to without asking, see on_save_clicked.
        self.current_save_path = None
        # "Unsaved changes" tracking, Ctrl+Z/Ctrl+Y-aware: self._revision
        # is the LIVE canvas's own revision number, self._next_revision
        # is the next brand-new number a genuine edit will be given
        # (_record_undo_snapshot), and self._saved_revision is whatever
        # self._revision was at the last Load/Save/New. `_dirty` (a
        # read-only property, below) is simply self._revision !=
        # self._saved_revision. Undo/redo restore a snapshot's own
        # ORIGINAL revision number rather than assigning a fresh one
        # (_snapshot_state/_restore_snapshot), so undoing every change
        # made since the last save lands back on that exact number and
        # correctly reads as clean again -- a plain "any edit happened"
        # boolean can't tell that apart from a genuinely new, different
        # state that just happens to come after the same number of
        # undo/redo steps.
        self._revision = 0
        self._next_revision = 1
        self._saved_revision = 0

        # View transform: screen = world * view_scale + (offset_x, offset_y).
        # offset starts at (0, 0) and is recentred once, on the canvas's
        # first real <Configure>, once its actual size is known.
        self.view_scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._offset_initialized = False

        self._palette_canvases = {}
        self._build_ui()
        self._update_title()
        self._refresh_vme_state()

    @property
    def _dirty(self):
        """True iff the live canvas differs from whatever was live at
        the last Load/Save/New -- see self._revision's own comment in
        __init__. Read-only: every place that used to just set a
        `self._dirty` flag now updates self._revision/_saved_revision
        instead, so this always reflects the real comparison rather
        than a separately-maintained bit that could drift out of sync
        with it."""
        return self._revision != self._saved_revision

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

        # Bottom status bar -- packed BEFORE the left/canvas frames below
        # so it claims a full-width strip at the bottom of the window
        # first, with the palette/drawing area filling whatever's left
        # above it. Says whether the current net has a vertex merge
        # error right now (_update_status_bar, called by
        # _refresh_vme_state after every edit that could change it).
        self.status_label = ttk.Label(self.root, anchor="w", padding=(10, 4))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        left = ttk.Frame(self.root, padding=12)
        left.pack(side=tk.LEFT, fill=tk.Y)

        for n in POLYGON_NS:
            self._build_palette_entry(left, n)

        # Right-side tool strip -- packed BEFORE the canvas below (same
        # reason as the status bar above: whoever packs first claims
        # their own strip of the window, leaving the canvas to fill
        # whatever's left).
        toolbar = ttk.Frame(self.root, padding=12)
        toolbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._build_toolbar(toolbar)

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
        self.root.bind_all("<KeyPress-f>", self._on_flip_key)
        self.root.bind_all("<KeyPress-m>", lambda _e: self._set_tool_mode("move"))
        self.root.bind_all("<KeyPress-j>", lambda _e: self._set_tool_mode("join"))
        self.root.bind_all("<KeyPress-h>", lambda _e: self._flip_selected_shapes("horizontal"))
        self.root.bind_all("<KeyPress-v>", lambda _e: self._flip_selected_shapes("vertical"))
        self.root.bind_all("<Control-c>", self.on_copy_key)
        self.root.bind_all("<Control-v>", self.on_paste_key)
        self.root.bind_all("<Control-z>", self.on_undo_key)
        self.root.bind_all("<Control-y>", self.on_redo_key)
        self.root.bind_all("<Control-s>", lambda _e: self.on_save_clicked())
        self.root.bind_all("<Escape>", self._on_escape_key)

        # Closing the window goes through the same unsaved-work check as
        # File > New (see _confirm_discard_unsaved) rather than just
        # discarding silently.
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit_request)

    def _build_menu(self):
        # Explicit colors (see MENU_BG's own comment) on BOTH the menu
        # bar and the dropdown -- otherwise only one of the two ends up
        # with Tk's own flat rendering and the other keeps the native
        # (here, light-embossed-disabled) look.
        menu_kwargs = dict(bg=MENU_BG, fg=MENU_FG, activebackground=MENU_ACTIVE_BG,
                            activeforeground=MENU_FG, disabledforeground=MENU_DISABLED_FG)
        menubar = tk.Menu(self.root, **menu_kwargs)
        self.file_menu = tk.Menu(menubar, tearoff=False, **menu_kwargs)
        self.file_menu.add_command(label="New", command=self.on_new_clicked)
        self.file_menu.add_command(label="Load...", command=self.on_load_clicked)
        # Indices into self.file_menu, for _update_file_menu_state to
        # enable/disable Save/Save As without hunting for them by label.
        self._save_menu_index = self.file_menu.index(tk.END) + 1
        self.file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self.on_save_clicked)
        self._save_as_menu_index = self.file_menu.index(tk.END) + 1
        self.file_menu.add_command(label="Save As...", command=self.on_save_as_clicked)
        menubar.add_cascade(label="File", menu=self.file_menu)
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

    def _build_toolbar(self, parent):
        """The right-side tool strip: one column of icon buttons,
        Photoshop/Illustrator-style. "Move"/"Join" SELECT a tool MODE
        (self.tool_mode, see _set_tool_mode) that gates what clicking on the canvas does --
        Join handles both an ordinary cross-shape connection and a polygon fold (a shape
        connected to its own other edge) in one mode -- see
        _hit_test_any_edge_handle's own `exclude_point`. "Flip Horizontal"/"Flip Vertical" are
        plain immediate ACTIONS on the current selection
        (_flip_selected_shapes) -- clicking either never changes
        self.tool_mode."""
        self._add_toolbar_mode_button(parent, "move", "Move [M]", _draw_move_tool_icon)
        self._add_toolbar_mode_button(parent, "join", "Join [J]", _draw_join_tool_icon)
        self._add_toolbar_action_button(parent, "Flip Horizontal [H]", _draw_flip_horizontal_tool_icon,
                                         lambda: self._flip_selected_shapes("horizontal"))
        self._add_toolbar_action_button(parent, "Flip Vertical [V]", _draw_flip_vertical_tool_icon,
                                         lambda: self._flip_selected_shapes("vertical"))
        self._update_toolbar_highlight()

    def _new_toolbar_icon(self, parent, draw_icon, color):
        icon = tk.Canvas(parent, width=TOOLBAR_ICON_SIZE, height=TOOLBAR_ICON_SIZE,
                          bg=PLOT_THEME["bg"], highlightthickness=2,
                          highlightbackground=PLOT_THEME["bg"])
        icon.pack(pady=3)
        draw_icon(icon, TOOLBAR_ICON_SIZE, color)
        return icon

    def _add_toolbar_mode_button(self, parent, mode, tooltip_text, draw_icon):
        icon = self._new_toolbar_icon(parent, draw_icon, TOOLBAR_ICON_COLOR)
        icon.bind("<Button-1>", lambda _e, m=mode: self._set_tool_mode(m))
        Tooltip(icon, tooltip_text)
        self.toolbar_buttons[mode] = icon

    def _add_toolbar_action_button(self, parent, tooltip_text, draw_icon, action):
        icon = self._new_toolbar_icon(parent, draw_icon, TOOLBAR_ICON_COLOR)
        icon.bind("<Button-1>", lambda _e: action())
        Tooltip(icon, tooltip_text)

    def _update_toolbar_highlight(self):
        """Rings whichever MODE button matches self.tool_mode in
        TOOLBAR_ACTIVE_BORDER, same idea as the palette's own "armed"
        white border (_on_palette_clicked) -- every other mode button
        (and the plain-action Flip buttons, never in self.toolbar_buttons
        at all) goes back to no visible border."""
        for mode, icon in self.toolbar_buttons.items():
            icon.configure(highlightbackground=(
                TOOLBAR_ACTIVE_BORDER if mode == self.tool_mode else PLOT_THEME["bg"]))

    def _set_tool_mode(self, mode):
        """Switches which canvas interaction is active (see module
        docstring's "Tool modes" section) -- a no-op if `mode` is
        already current. Clears every piece of transient state that
        only makes sense in the mode being LEFT (a selection, an armed
        palette shape, a pending connection, an in-progress marquee),
        so nothing carries over looking selected/armed/pending in a mode
        where it can no longer mean anything."""
        if mode == self.tool_mode:
            return
        self.tool_mode = mode
        self.selected_ids = set()
        self.selected_connection_id = None
        self.armed_n = None
        self._ghost_world_xy = None
        self._drag_state = None
        self._bezier_handle_drag = None
        self._connection_pending = None
        self._pending_cursor_screen = None
        self._hover_shape_id = None
        self._hover_edge_index = None
        self._marquee_start = None
        self._marquee_current = None
        for icon in self._palette_canvases.values():
            icon.configure(highlightbackground=PLOT_THEME["bg"])
        self._update_toolbar_highlight()
        self._redraw()

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

    def _shape_edge_frame(self, shape, edge_index):
        """(origin, tangent, normal) for one of `shape`'s own edges, all
        in world space: `origin` is the edge's midpoint (same point
        _shape_edge_midpoints returns), `tangent` the unit vector along
        it (from corner `edge_index` to corner `edge_index + 1`), and
        `normal` the unit vector perpendicular to it, pointing AWAY from
        the shape's own centroid. A connection's bezier control points
        are stored relative to THIS frame (see _bezier_handle_world) --
        recomputed fresh from the shape's CURRENT rotation/position every
        call, the same "never stored, always derived live" convention
        _shape_edge_midpoints itself already uses, so a handle tracks its
        own shape's move/rotate exactly like the curve's own endpoint
        does, with no separate update step needed anywhere a shape
        changes."""
        verts = self._shape_world_vertices(shape)
        n = len(verts)
        v1, v2 = verts[edge_index], verts[(edge_index + 1) % n]
        ox, oy = (v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2
        tx, ty = v2[0] - v1[0], v2[1] - v1[1]
        length = math.hypot(tx, ty) or 1.0
        tx, ty = tx / length, ty / length
        nx, ny = -ty, tx
        cx = sum(p[0] for p in verts) / n
        cy = sum(p[1] for p in verts) / n
        if (ox - cx) * nx + (oy - cy) * ny < 0:
            nx, ny = -nx, -ny
        return (ox, oy), (tx, ty), (nx, ny)

    def _bezier_handle_world(self, shape, edge_index, handle):
        """World-space position of one connection endpoint's control
        point: `handle` is {"t", "n"}, world-length offsets along that
        edge's own tangent/normal (_shape_edge_frame) from its midpoint
        -- NOT a fraction and NOT a point relative to the OTHER end, so
        it stays meaningful regardless of where the connection's far end
        currently is."""
        origin, (tx, ty), (nx, ny) = self._shape_edge_frame(shape, edge_index)
        t, n = handle["t"], handle["n"]
        return origin[0] + t * tx + n * nx, origin[1] + t * ty + n * ny

    def _handle_from_world_point(self, shape, edge_index, world_point):
        """Inverse of _bezier_handle_world -- the {"t", "n"} a control
        point currently AT `world_point` would need, in `shape`'s edge
        `edge_index` own frame. Used both to set a freshly-made
        connection's default handles (a colinear third-of-the-way point,
        see _complete_or_cancel_pending_connection) and to update a
        handle live while it's being dragged (_on_canvas_drag)."""
        (ox, oy), (tx, ty), (nx, ny) = self._shape_edge_frame(shape, edge_index)
        dx, dy = world_point[0] - ox, world_point[1] - oy
        return {"t": dx * tx + dy * ty, "n": dx * nx + dy * ny}

    def _default_connection_handles(self, a_shape, a_edge, b_shape, b_edge):
        """The {"a_handle", "b_handle"} a brand-new connection between
        these two edges starts with -- two points, one third and two
        thirds of the way along the straight line between the edges' own
        midpoints, which makes the initial cubic bezier render as exactly
        that straight line (the standard construction: a cubic through
        colinear, evenly-spaced control points is itself a straight
        line) -- so a fresh connection looks identical to the plain line
        segment this feature replaces, until a handle is actually
        dragged."""
        a_mid = self._shape_edge_midpoints(a_shape)[a_edge]
        b_mid = self._shape_edge_midpoints(b_shape)[b_edge]
        third = (a_mid[0] + (b_mid[0] - a_mid[0]) / 3, a_mid[1] + (b_mid[1] - a_mid[1]) / 3)
        two_thirds = (a_mid[0] + (b_mid[0] - a_mid[0]) * 2 / 3, a_mid[1] + (b_mid[1] - a_mid[1]) * 2 / 3)
        return (self._handle_from_world_point(a_shape, a_edge, third),
                self._handle_from_world_point(b_shape, b_edge, two_thirds))

    def _joined_points(self):
        """Set of (shape_id, edge_index) already the endpoint of a real
        connection -- an edge can only ever be joined ONCE, so this is
        what _hit_test_any_edge_handle excludes from being clickable a
        second time (see its own docstring for why: connecting the same
        edge twice is what corrupted data/input/stretchy_nets/hippo.json
        -- a single edge unioned with two different partners transitively
        merged unrelated vertices together, producing vertex-merge and
        duplicate-directed-edge errors far from where the mistake was
        actually made)."""
        joined = set()
        for conn in self.connections:
            joined.add((conn["a_shape"], conn["a_edge"]))
            joined.add((conn["b_shape"], conn["b_edge"]))
        return joined

    def _hit_test_any_edge_handle(self, screen_x, screen_y, exclude_point=None):
        """Nearest edge handle within HANDLE_HIT_RADIUS screen pixels of the given point, or
        None. Every placed shape's every UNJOINED edge handle is clickable this way -- there's
        no "must be selected first" gate (that WAS the rule at one point; dropped since it took
        two clicks, select-the-shape then click-its-handle, to start a connection at all -- see
        module docstring) -- but an edge already the endpoint of a real connection (see
        _joined_points) is EXCLUDED entirely, for both starting a new connection from it and
        completing one onto it: an edge can only ever be joined once, and allowing a second
        join is exactly what corrupted hippo.json (see _joined_points' own docstring).

        `exclude_point`, a `(shape_id, edge_index)` pair, additionally excludes exactly that
        ONE edge -- used with a pending connection's own origin. Join mode doesn't restrict a
        completing click to a DIFFERENT shape; the only edge that can never be the target is
        the origin's own, since an edge can't join itself. This single exclusion is what lets
        one mode complete onto either a different shape's edge (an ordinary join) or the SAME
        shape's own different edge (a polygon fold, self._expand_folded_shapes' own concern at
        Save time -- see module docstring's "Polygon folding" section), with no mode-level
        distinction needed here at all). Also used this way for both hover highlighting
        (_on_canvas_motion) and deciding what a completing click actually connects to
        (_complete_or_cancel_pending_connection just reads the hover state this leaves behind,
        rather than re-running this itself) -- the two MUST agree, so nothing ever connects
        without having first been visibly highlighted."""
        joined = self._joined_points()
        best, best_dist = None, HANDLE_HIT_RADIUS
        for shape in self.shapes:
            for edge_index, (mx, my) in enumerate(self._shape_edge_midpoints(shape)):
                if (shape["id"], edge_index) == exclude_point:
                    continue
                if (shape["id"], edge_index) in joined:
                    continue
                sx, sy = self._world_to_screen(mx, my)
                dist = math.hypot(screen_x - sx, screen_y - sy)
                if dist <= best_dist:
                    best, best_dist = {"shape_id": shape["id"], "edge_index": edge_index}, dist
        return best

    def _connection_geometry(self, conn):
        """World-space (a_mid, a_ctrl, b_ctrl, b_mid) -- the four points
        defining this connection's cubic bezier (endpoint, its own
        control point, the other end's control point, other endpoint) --
        or None if either shape it references no longer exists."""
        a_shape, b_shape = self._shape_by_id(conn["a_shape"]), self._shape_by_id(conn["b_shape"])
        if a_shape is None or b_shape is None:
            return None
        a_mid = self._shape_edge_midpoints(a_shape)[conn["a_edge"]]
        b_mid = self._shape_edge_midpoints(b_shape)[conn["b_edge"]]
        a_ctrl = self._bezier_handle_world(a_shape, conn["a_edge"], conn["a_handle"])
        b_ctrl = self._bezier_handle_world(b_shape, conn["b_edge"], conn["b_handle"])
        return a_mid, a_ctrl, b_ctrl, b_mid

    def _connection_screen_curve(self, conn):
        """This connection's bezier sampled into screen-space points
        (_cubic_bezier_points), or None if either shape no longer exists.
        World-to-screen (_world_to_screen) is a uniform scale + translate,
        so converting the 4 control points first and sampling the curve
        AFTER gives exactly the same polyline as sampling in world space
        and converting every point -- cheaper, since it's only 4
        conversions instead of BEZIER_CURVE_STEPS + 1."""
        geometry = self._connection_geometry(conn)
        if geometry is None:
            return None
        screen_points = [self._world_to_screen(*p) for p in geometry]
        return _cubic_bezier_points(*screen_points)

    def _hit_test_connection(self, screen_x, screen_y):
        """Id of the connection whose curve passes within
        CONNECTION_HIT_RADIUS screen pixels of the given point, or None."""
        best, best_dist = None, CONNECTION_HIT_RADIUS
        for conn in self.connections:
            curve = self._connection_screen_curve(conn)
            if curve is None:
                continue
            dist = min(_point_segment_distance((screen_x, screen_y), curve[i], curve[i + 1])
                       for i in range(len(curve) - 1))
            if dist < best_dist:
                best, best_dist = conn["id"], dist
        return best

    def _hit_test_bezier_handle(self, screen_x, screen_y):
        """"a" or "b" if the given point is within BEZIER_HANDLE_HIT_RADIUS
        of that end's control-point handle for the CURRENTLY selected
        connection, else None -- there's nothing to hit-test at all with
        no connection selected (self.selected_connection_id), since a
        handle is only ever drawn/clickable for that one connection (see
        module docstring's bezier section -- "only adjustable when
        visible")."""
        if self.selected_connection_id is None:
            return None
        conn = next((c for c in self.connections if c["id"] == self.selected_connection_id), None)
        if conn is None:
            return None
        geometry = self._connection_geometry(conn)
        if geometry is None:
            return None
        _, a_ctrl, b_ctrl, _ = geometry
        for end, ctrl in (("a", a_ctrl), ("b", b_ctrl)):
            sx, sy = self._world_to_screen(*ctrl)
            if math.hypot(screen_x - sx, screen_y - sy) <= BEZIER_HANDLE_HIT_RADIUS:
                return end
        return None

    def _remove_shape(self, shape_id):
        """Deletes the shape and every connection touching it -- a
        connection with a missing endpoint has nothing left to draw a
        line between, so it can't be left dangling. Doesn't itself
        refresh the vertex-merge-error state -- callers that delete
        several shapes in a loop (_on_delete_key) do that once,
        afterward, rather than re-validating after every single one."""
        self.connections = [c for c in self.connections
                             if c["a_shape"] != shape_id and c["b_shape"] != shape_id]
        self.shapes = [s for s in self.shapes if s["id"] != shape_id]

    # ---- palette ----

    def _on_palette_clicked(self, n):
        # Dropping a new shape only makes sense in Move mode -- Join
        # mode has nothing to select it or connect it FROM the moment
        # it lands (see module docstring's "Tool modes" section).
        if self.tool_mode != "move":
            return
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

    def on_new_clicked(self):
        """File > New -- clears the canvas back to empty (what the old
        "Clear" button used to do) and forgets whatever file was
        associated with it (window title, Ctrl+S's own direct-save
        target -- see current_save_path), after first checking there's
        nothing unsaved that this would silently throw away (see
        _confirm_discard_unsaved). The fresh empty canvas is itself the
        new "nothing unsaved" baseline (self._saved_revision), same as a
        successful Load/Save -- so a blank canvas never itself warrants
        an unsaved-changes prompt."""
        if not self._confirm_discard_unsaved():
            return
        if self.shapes or self.connections:
            self._push_undo()
        self.shapes.clear()
        self.connections.clear()
        self.selected_ids = set()
        self.selected_connection_id = None
        self._drag_state = None
        self.current_save_path = None
        self._saved_revision = self._revision
        self._update_title()
        self._refresh_vme_state()
        self._redraw()

    def _on_quit_request(self):
        """WM_DELETE_WINDOW (the window's own close button, Alt+F4,
        etc.) -- same unsaved-work check as File > New before actually
        closing (see _confirm_discard_unsaved)."""
        if self._confirm_discard_unsaved():
            self.root.destroy()

    def _confirm_discard_unsaved(self):
        """Returns True if it's safe to proceed with something that
        would discard the current canvas (File > New, or closing the
        window) -- either nothing's unsaved (self._dirty is False), the
        user said to discard it anyway, or they asked to save first and
        the save dialog that opened for it actually went through.
        Returns False if the caller should abort instead (the user
        cancelled outright, or cancelled/failed the save dialog after
        saying "yes" -- either way, nothing has actually been saved, so
        proceeding would still lose it)."""
        if not self._dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", "Save your changes before continuing?")
        if answer is None:  # Cancel
            return False
        if not answer:  # No -- discard
            return True
        return self.on_save_as_clicked()  # Yes -- must actually succeed

    def _update_title(self):
        """Single source of truth for the window title: the base name,
        plus the associated file's own basename in brackets if there is
        one (current_save_path, set by a successful Load/Save/Save As
        and cleared by New), plus a "*" if self._dirty (unsaved changes
        -- see its own comment in __init__), plus the debug-mode suffix
        if that's on. Called wherever any of those change."""
        title = "Interactive Builder"
        if self.current_save_path is not None:
            title += f" [{os.path.basename(self.current_save_path)}]"
        if self._dirty:
            title += " *"
        if self.debug_mode:
            title += " (debug mode)"
        self.root.title(title)

    def _update_status_bar(self):
        """Single source of truth for the bottom status message --
        "everything is good" while self._vme_active is False, an
        explicit warning naming a vertex merge error otherwise. Called
        by _refresh_vme_state whenever that flag might have changed."""
        if self._vme_active:
            self.status_label.config(
                text="Vertex merge error(s) detected. Fix before saving.",
                foreground=STATUS_COLORS["error"])
        else:
            self.status_label.config(
                text="Everything is good.", foreground=STATUS_COLORS["success"])

    def _update_file_menu_state(self):
        """Save is enabled only while there's something new to write
        (self._dirty) AND the net is currently valid (not
        self._vme_active) -- greyed out otherwise, since there's either
        nothing to save or nothing SAFE to save. Save As has no reason
        to care about self._dirty (saving a copy under a new name is
        useful even with nothing changed since the last save), but still
        refuses a currently-invalid net, same as Save. Called by
        _refresh_vme_state (after every edit that could change either
        flag) and directly by _save_to_path (right after a successful
        save flips self._dirty to False, without going through
        _refresh_vme_state itself)."""
        self.file_menu.entryconfig(
            self._save_menu_index, state=tk.NORMAL if (self._dirty and not self._vme_active) else tk.DISABLED)
        self.file_menu.entryconfig(
            self._save_as_menu_index, state=tk.DISABLED if self._vme_active else tk.NORMAL)

    def _refresh_vme_state(self):
        """Re-validates the CURRENT self.shapes/self.connections and
        updates self._vme_active, the status bar, and Save/Save As's
        enabled state accordingly -- call this after any edit that could
        change whether the net has a vertex merge error (VME): making or
        deleting a connection, deleting a shape, flipping a shape,
        undo/redo, paste, New, Load. Only ever the plain yes/no answer --
        WHICH corners are actually conflicting is debug mode's own
        concern (_draw_dedup_vertex_labels re-validates independently,
        live, on every redraw, to ring the specific ones red), not
        something this needs to compute or store for release mode,
        which shows nothing more specific than the status bar text.
        Validates the EXPANDED (post-_expand_folded_shapes) form, not
        self.shapes/self.connections directly -- a Polygon Fold
        connection only actually resolves into a real (in)validity
        question once its shape is triangulated, see that function's own
        docstring."""
        try:
            expanded_shapes, expanded_connections, _ = _expand_folded_shapes(
                self.shapes, self.connections)
            _validate_shapes_connections(expanded_shapes, expanded_connections)
        except NetValidationError:
            self._vme_active = True
        else:
            self._vme_active = False
        self._update_status_bar()
        self._update_file_menu_state()

    # ---- File menu: new/load/save ----

    def _save_to_path(self, path):
        """The actual save logic shared by "Save" (direct, straight to
        whatever file's already associated with the canvas) and
        "Save As..." (always asks first) -- writes shapes/connections
        out as a stretchy-mesh "faces" vertex-loop spec, plus a
        "net_layout" section (each shape's "cx"/"cy"/"rotation"/
        "flipped") and a "builder_connections" section (this app's own
        extensions, see module docstring) so re-Loading it reproduces
        the exact on-screen layout AND the exact shapes/connections/flip
        state, rather than falling back to a fresh BFS layout plus
        re-derived (always-unflipped) connections, and a "view" section
        with the current zoom level so re-Loading it doesn't reset back
        to the default zoom. The NetValidationError branch below should
        be unreachable in normal use -- on_save_clicked/on_save_as_clicked
        already refuse to call this at all while self._vme_active (see
        their own docstrings) -- kept only as a defensive fallback.
        Returns True on success, False on a validation or I/O failure
        (already reported via messagebox) -- callers that need to know
        whether the save actually happened (_confirm_discard_unsaved,
        before letting New/quitting throw away unsaved work) check
        this.

        Refuses (no file written) if the net has more than one connected
        piece (see _count_shape_components' own docstring): a plain net
        file has no way to record which piece is
        "central", so this app only ever saves a single connected net;
        interactive_inflater_app's own .hippie format is the one place a
        multi-piece net can be saved. Checked here, not inside
        _export_faces_and_layout/_validate_shapes_connections (which
        interactive_inflater_app's own live inflate/central-object
        export also call) -- those need to keep working unchanged on a
        DISCONNECTED net (a shape not yet attached to the central object
        is a completely normal, temporary state while building one)."""
        component_count = _count_shape_components(self.shapes, self.connections)
        if component_count > 1:
            messagebox.showerror(
                "Save failed",
                f"This net has {component_count} disconnected pieces -- only a single "
                f"connected net can be saved here.")
            return False
        try:
            faces, edges, face_edge_ids, source_polygon_id, net_layout, builder_connections = \
                self._export_faces_and_layout()
        except (NetValidationError, ValueError) as e:
            messagebox.showerror("Save failed", str(e))
            return False
        spec = {"name": os.path.splitext(os.path.basename(path))[0], "faces": faces,
                "edges": edges, "face_edge_ids": face_edge_ids,
                "source_polygon_id": source_polygon_id, "net_layout": net_layout,
                "builder_connections": builder_connections,
                "view": {"scale": self.view_scale}}
        try:
            with open(path, "w") as f:
                json.dump(spec, f, indent=2)
        except OSError as e:
            messagebox.showerror("Save failed", str(e))
            return False
        self.current_save_path = path
        self._saved_revision = self._revision
        self._update_title()
        self._update_file_menu_state()
        return True

    def on_save_as_clicked(self):
        """File > Save As... -- always asks where to save (unlike
        File > Save/Ctrl+S, which reuses current_save_path if there is
        one), then associates that file with the canvas going forward.
        Refuses outright, with a messagebox and no file dialog, while
        self._vme_active -- Save As is greyed out in the File menu for
        the same reason (_update_file_menu_state), but Ctrl+S/a direct
        call here would otherwise bypass that. Returns True on a
        successful save, False if the dialog was cancelled, a VME
        blocked it, or the save itself failed (see _save_to_path) --
        _confirm_discard_unsaved relies on this to know whether it's
        actually safe to then discard/replace the canvas."""
        if self._vme_active:
            messagebox.showerror(
                "Can't save", "Vertex merge error(s) detected. Fix before saving.")
            return False
        path = filedialog.asksaveasfilename(
            title="Save net as", initialdir=str(STRETCHY_NETS_DIR),
            defaultextension=NET_FILE_EXTENSION,
            filetypes=[("Net", f"*{NET_FILE_EXTENSION}"), ("Net JSON", "*.json"),
                       ("All files", "*.*")])
        if not path:
            return False
        return self._save_to_path(path)

    def on_save_clicked(self):
        """File > Save (Ctrl+S) -- saves straight to whatever file is
        already associated with the canvas (current_save_path, set by a
        prior Load or Save As), with no dialog; falls back to Save As if
        nothing's associated with it yet (nowhere to save "directly" to,
        same as any other app's Save the first time) -- which itself
        refuses while self._vme_active, so this doesn't need its own
        separate check for that case. Also refuses directly when there's
        nothing new to save (self._dirty is False) -- Save is greyed out
        in the File menu then too (_update_file_menu_state), but Ctrl+S
        would otherwise still fire. Returns True/False like
        on_save_as_clicked, for the same reason."""
        if self.current_save_path is None:
            return self.on_save_as_clicked()
        if self._vme_active:
            messagebox.showerror(
                "Can't save", "Vertex merge error(s) detected. Fix before saving.")
            return False
        if not self._dirty:
            return True
        return self._save_to_path(self.current_save_path)

    def _export_faces_and_layout(self):
        """Returns (faces, edges, face_edge_ids, source_polygon_id,
        net_layout, builder_connections). `faces`/`edges`/`face_edge_ids`/
        `source_polygon_id` are all derived from the EXPANDED (post-
        _expand_folded_shapes) shapes/connections, not self.shapes/
        self.connections directly -- see that function's own docstring
        for why a Polygon Fold connection needs its whole shape
        triangulated before the plain _faces_from_shapes/_edges_from_shapes/
        _face_edge_ids_from_shapes machinery (which itself needs no
        changes at all) can make sense of it. `faces` is the vertex-loop
        list; `edges` is the explicit mesh-edge list from
        _edges_from_shapes (see its own docstring for why this can't just
        be re-derived from `faces` alone downstream -- two
        coincidentally-same-vertex-pair free edges are NOT the same
        edge); `face_edge_ids` is _face_edge_ids_from_shapes' own
        per-face-edge disambiguation ids (same reason, but for
        mesh_levels.subdivide_once's own Level 1->2 rim-edge splitting,
        which can't rely on `edges` alone since it needs a per-FACE-EDGE,
        not per-mesh-edge, answer); `source_polygon_id` is parallel to
        `faces` -- the ORIGINAL placed shape's own id each face came from
        (see _expand_folded_shapes), a pure downstream display/grouping
        aid.

        `net_layout`/`builder_connections`, in contrast, are built
        straight from the ORIGINAL (un-expanded) self.shapes/
        self.connections -- they describe the placed polygons themselves,
        which this app never shows as individual fan triangles even once
        Saved (module docstring's "Tool modes"/"net JSON import/export"
        sections), so they're keyed by each shape's own stable id rather
        than by any position into `faces` (which, once a fold exists, no
        longer has one entry per placed shape at all): `net_layout` is
        each shape's own {"shape_id", "n", "cx", "cy", "rotation",
        "flipped"}; `builder_connections` is self.connections with shape
        ids renamed to "a_shape_id"/"b_shape_id" (already exactly the ids
        needed -- no translation table required any more). See module
        docstring's "net JSON import/export" section for why Load
        reconstructs shapes/connections directly from these two (when
        present) rather than re-deriving them from the plain vertex-loop
        `faces` alone: re-deriving can only ever recover SOME valid
        flip/connection assignment for the exported mesh, not necessarily
        the exact one the user built (see _load_faces' own docstring for
        why "flipped" specifically can't just be read back onto a
        re-derived connection).

        Raises NetValidationError (a ValueError subclass, from
        _validate_shapes_connections) if self.shapes' CURRENT "flipped"
        bits (see module docstring's "Flip" section -- set directly by
        the user, never inferred) don't produce a valid mesh once
        expanded -- should be unreachable in normal use, since Save/Save
        As already refuse to call this while self._vme_active
        (_refresh_vme_state re-runs the same check live after every edit
        -- see module docstring's "Edge connections" section), but kept
        here as the defensive, authoritative check right before a file
        is actually written."""
        expanded_shapes, expanded_connections, source_polygon_id = \
            _expand_folded_shapes(self.shapes, self.connections)
        _validate_shapes_connections(expanded_shapes, expanded_connections)
        faces = _faces_from_shapes(expanded_shapes, expanded_connections)
        edges = _edges_from_shapes(expanded_shapes, expanded_connections)
        face_edge_ids = _face_edge_ids_from_shapes(expanded_shapes, expanded_connections)
        net_layout = [{"shape_id": s["id"], "n": s["n"], "cx": s["cx"], "cy": s["cy"],
                       "rotation": s["rotation"], "flipped": s["flipped"]} for s in self.shapes]
        builder_connections = [
            {"a_shape_id": c["a_shape"], "a_edge": c["a_edge"],
             "b_shape_id": c["b_shape"], "b_edge": c["b_edge"],
             "a_handle": dict(c["a_handle"]), "b_handle": dict(c["b_handle"])}
            for c in self.connections
        ]
        return faces, edges, face_edge_ids, source_polygon_id, net_layout, builder_connections

    def on_load_clicked(self):
        path = filedialog.askopenfilename(
            title="Load net", initialdir=str(STRETCHY_NETS_DIR),
            filetypes=[("Net", f"*{NET_FILE_EXTENSION}"), ("Net JSON", "*.json"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path) as f:
                spec = json.load(f)
            faces = spec["faces"]
            if not faces:
                raise ValueError("no faces declared")
            degenerate_edges = _degenerate_edge_faces(faces)
            view_scale = spec.get("view", {}).get("scale")
            self._load_faces(faces, spec.get("net_layout"), view_scale,
                              spec.get("builder_connections"))
            self.current_save_path = path
            self._saved_revision = self._revision
            self._update_title()
            self._refresh_vme_state()
            if degenerate_edges:
                # A malformed file (from an earlier, buggy Save -- see
                # _degenerate_edge_faces' own docstring) still loads, but
                # every degenerate edge is left unconnected rather than
                # silently wired up wrong -- tell the user so they know
                # to go reconnect those specific edges, rather than
                # discovering it only when some later Save fails.
                where = ", ".join(f"face {fi} vertex {v}" for fi, v in degenerate_edges)
                messagebox.showwarning(
                    "Loaded with degenerate edges",
                    f"{len(degenerate_edges)} degenerate edge(s) in this file were left "
                    f"unconnected (a corrupted vertex label from an earlier bug, "
                    f"not a real connection): {where}")
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            messagebox.showerror("Load failed", str(e))

    def _connections_from_builder_list(self, builder_connections, resolve_shape_id):
        """Shared by every builder_connections reconstruction path below
        (new shape-id-keyed format, legacy face-index-keyed format, and
        the _infer_connections(faces) fallback, which returns the same
        legacy "a_face"/"b_face" shape) -- only HOW a raw saved endpoint
        id maps to a freshly-assigned live shape id differs between them,
        which `resolve_shape_id(raw_id)` supplies. "a_handle"/"b_handle"
        (this app's own bezier control points) are only present in an
        entry saved by a version of this app that tracked them -- one
        that has neither (an older file, or a hand-authored/inferred
        one) gets the same straight-line default a freshly-made
        connection would (_default_connection_handles), rather than
        failing to load."""
        connections = []
        for c in builder_connections:
            a_shape_id = resolve_shape_id(c["a_shape_id"] if "a_shape_id" in c else c["a_face"])
            b_shape_id = resolve_shape_id(c["b_shape_id"] if "b_shape_id" in c else c["b_face"])
            if "a_handle" in c and "b_handle" in c:
                a_handle, b_handle = c["a_handle"], c["b_handle"]
            else:
                a_handle, b_handle = self._default_connection_handles(
                    self._shape_by_id(a_shape_id), c["a_edge"],
                    self._shape_by_id(b_shape_id), c["b_edge"])
            connections.append({
                "id": self._next_connection_id,
                "a_shape": a_shape_id, "a_edge": c["a_edge"],
                "b_shape": b_shape_id, "b_edge": c["b_edge"],
                "a_handle": a_handle, "b_handle": b_handle,
            })
            self._next_connection_id += 1
        return connections

    def _load_faces(self, faces, net_layout, view_scale=None, builder_connections=None):
        """Replaces the whole canvas with either `net_layout` (preferred,
        see below) or `faces` (vertex-id loops, the plain fallback).
        `view_scale` (this app's own saved "view"."scale", see module
        docstring), when present, restores the zoom level the net was
        saved at instead of resetting to the default 1.0.

        Two `net_layout` shapes are understood (module docstring's "net
        JSON import/export" section):

        - NEW format (`net_layout[i]` has its own "shape_id"/"n", written
          by this app since Polygon Fold): one shape is reconstructed per
          `net_layout` ENTRY directly (its own "n"/"cx"/"cy"/"rotation"/
          "flipped"), completely independent of `faces`' own length/order
          -- necessary since a folded shape's `n` triangles in `faces` no
          longer correspond 1:1 with the ORIGINAL placed shapes at all.
          `builder_connections` entries (keyed by "a_shape_id"/
          "b_shape_id") are remapped through a fresh saved-id -> live-id
          table built while placing those shapes.
        - LEGACY format (no "shape_id" -- any file saved before Polygon
          Fold existed, when 1 shape was always exactly 1 face): one
          shape per FACE, positioned from `net_layout[i]` when its length
          matches `faces`, else via _layout_faces_with_gap rooted at face
          0. `builder_connections` entries (keyed by legacy "a_face"/
          "b_face") are remapped through that same per-face shape-id
          list.

        Either way, `builder_connections`, when present alongside a
        usable layout, reconstructs self.connections (and each shape's
        "flipped", from the SAME per-shape layout entry) DIRECTLY from
        it, instead of falling back to _infer_connections(faces) -- this
        is the ONLY way to correctly restore a shape's "flipped" bit at
        all: _faces_from_shapes already bakes each shape's TRUE (flip-
        adjusted) winding directly into its exported loop, so
        _infer_connections always derives a fully self-consistent set of
        connections treating EVERY shape as unflipped (this is exactly
        why a hand-authored net, or an app-saved one from before
        "flipped" was tracked, always loads with every shape unflipped
        and still validates instantly). Naively marking a shape
        "flipped" again afterward, on top of those re-derived
        connections, corrupts the mesh -- flipping any single already-
        fully-integrated shape reverses EVERY one of its edges' true
        direction at once, which the freshly re-derived connections
        don't expect, producing exactly the vertex-merge-error/
        duplicate-edge errors _validate_shapes_connections exists to
        catch. Restoring
        "flipped" is only safe together with the EXACT connections it
        was originally paired with, which is what `builder_connections`
        supplies -- there is no way to derive a correct substitute from
        `faces` alone. The legacy fallback (no usable `net_layout` at
        all, e.g. any hand-authored net) never has fold-shaped `faces`
        either, so it's never affected by any of the above -- one shape
        per face, `_infer_connections`, every shape unflipped, exactly as
        always."""
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
        self._bezier_handle_drag = None
        self._marquee_start = None
        self._marquee_current = None

        new_format = bool(net_layout) and "shape_id" in net_layout[0]

        if new_format:
            shape_id_map = {}
            for entry in net_layout:
                new_id = self._next_shape_id
                self._next_shape_id += 1
                shape_id_map[entry["shape_id"]] = new_id
                self.shapes.append({"id": new_id, "n": entry["n"], "cx": entry["cx"],
                                     "cy": entry["cy"], "rotation": entry["rotation"],
                                     "flipped": entry.get("flipped", False)})
            if builder_connections is not None:
                self.connections = self._connections_from_builder_list(
                    builder_connections, lambda raw: shape_id_map[raw])
            # A NEW-format net_layout with no builder_connections at all
            # can't happen from anything this app itself ever Saves (the
            # two are always written together) -- left with no
            # connections rather than guessing, sooner than crashing.
        else:
            layout_ok = net_layout is not None and len(net_layout) == len(faces)
            exact_connections_ok = layout_ok and builder_connections is not None

            shape_ids = []
            for i, face in enumerate(faces):
                shape_id = self._next_shape_id
                self._next_shape_id += 1
                shape_ids.append(shape_id)
                flipped = net_layout[i].get("flipped", False) if exact_connections_ok else False
                self.shapes.append({"id": shape_id, "n": len(face), "cx": 0.0, "cy": 0.0,
                                     "rotation": 0.0, "flipped": flipped})

            if layout_ok:
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

            if exact_connections_ok:
                self.connections = self._connections_from_builder_list(
                    builder_connections, lambda raw: shape_ids[raw])
            else:
                self.connections = self._connections_from_builder_list(
                    _infer_connections(faces), lambda raw: shape_ids[raw])

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
            # UNJOINED edge other than the origin's own (see
            # _hit_test_any_edge_handle -- both those exclusions are
            # LOCAL, unambiguous facts about the one edge being clicked,
            # never dependent on what any OTHER connection happens to
            # imply about shared vertex identity -- see module docstring
            # on why that's deliberate). A different shape's edge and the
            # SAME shape's own other edge (a polygon fold) are equally
            # valid targets -- Join no longer distinguishes them.
            target = self._hit_test_any_edge_handle(
                event.x, event.y,
                exclude_point=(self._connection_pending["from_shape"],
                                self._connection_pending["from_edge"]))
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
        """Dispatches to whichever tool mode is current (see module
        docstring's "Tool modes" section) -- Move (drag/select/marquee
        shapes; connections aren't editable at all) or Join (add/delete
        connections, both cross-shape and same-shape/polygon-fold; shapes
        aren't selectable, so a click can never start a drag)."""
        if self.tool_mode == "move":
            self._on_canvas_press_move(event)
        elif self.tool_mode == "join":
            self._on_canvas_press_join(event)

    def _on_canvas_press_move(self, event):
        if self.armed_n is not None:
            wx, wy = self._screen_to_world(event.x, event.y)
            self._push_undo()
            self._drop_shape(self.armed_n, wx, wy)
            self._on_palette_clicked(self.armed_n)  # disarm (toggles current off)
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

    def _on_canvas_press_join(self, event):
        """Shapes aren't selectable/draggable at all in Join mode -- a
        click here only ever starts/completes a connection (via an edge
        handle) or selects/deselects an existing connection line (for
        Delete). Clicking a shape's body away from any handle or
        connection line simply deselects, same as clicking empty
        space."""
        if self._connection_pending is None:
            # A bezier handle is only ever checked while nothing's
            # pending (arming a pending connection already clears
            # selected_connection_id -- see below -- so there's nothing
            # to drag a handle OF at that point anyway). Starts a drag
            # rather than falling through to the ordinary handle/
            # connection hit-tests below -- the SAME click-click gesture
            # target and a handle's own hit area can overlap right at a
            # curve's own endpoint, and a handle drag should win there.
            end = self._hit_test_bezier_handle(event.x, event.y)
            if end is not None:
                self._begin_undoable_change()
                self._bezier_handle_drag = {"conn_id": self.selected_connection_id, "end": end}
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
            # connection, or deselect) -- it just never creates a SECOND
            # connection.

        handle = self._hit_test_any_edge_handle(event.x, event.y)
        if handle is not None:
            self._connection_pending = {"from_shape": handle["shape_id"],
                                         "from_edge": handle["edge_index"]}
            self._pending_cursor_screen = (event.x, event.y)
            self.selected_connection_id = None
            self._redraw()
            return

        conn_hit = self._hit_test_connection(event.x, event.y)
        self.selected_connection_id = conn_hit  # None if the click missed everything
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
            a_shape_id, a_edge = self._connection_pending["from_shape"], self._connection_pending["from_edge"]
            b_shape_id, b_edge = self._hover_shape_id, self._hover_edge_index
            a_handle, b_handle = self._default_connection_handles(
                self._shape_by_id(a_shape_id), a_edge, self._shape_by_id(b_shape_id), b_edge)
            self.connections.append({
                "id": self._next_connection_id,
                "a_shape": a_shape_id, "a_edge": a_edge,
                "b_shape": b_shape_id, "b_edge": b_edge,
                "a_handle": a_handle, "b_handle": b_handle,
            })
            self._next_connection_id += 1
            self._refresh_vme_state()
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
        # Left selected so it can be immediately rotated, connected, or
        # copied without a separate click -- the _on_palette_clicked call
        # right after this (in _on_canvas_press) only clears a selection
        # when ARMING a new type, not when disarming (which is what
        # actually happens here), so this survives that call.
        self.selected_ids = {shape["id"]}
        self.selected_connection_id = None

    def _on_canvas_drag(self, event):
        if self._bezier_handle_drag is not None:
            conn = next((c for c in self.connections
                         if c["id"] == self._bezier_handle_drag["conn_id"]), None)
            if conn is not None:
                end = self._bezier_handle_drag["end"]
                shape = self._shape_by_id(conn[f"{end}_shape"])
                if shape is not None:
                    wx, wy = self._screen_to_world(event.x, event.y)
                    conn[f"{end}_handle"] = self._handle_from_world_point(
                        shape, conn[f"{end}_edge"], (wx, wy))
                    self._redraw()
            return
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
        self._bezier_handle_drag = None
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
            self._refresh_vme_state()
            self._redraw()
        elif self.selected_connection_id is not None:
            self._push_undo()
            self.connections = [c for c in self.connections if c["id"] != self.selected_connection_id]
            self.selected_connection_id = None
            self._refresh_vme_state()
            self._redraw()

    def _on_flip_key(self, _event=None):
        """F: toggles "flipped" (see module docstring's "Flip" section)
        on every currently-selected shape -- a no-op with nothing
        selected. Purely a per-shape bit: none of self.connections
        change at all, so an already-made connection stays exactly where
        it was clicked; only which side of the flipped shape(s) reads as
        "outside" (solid fill vs. hatching -- see _draw_shape/
        _rasterize_polygon) and how their edges' TRUE direction is
        interpreted at Save/live validation (_true_edge_slots) changes.
        Re-checks for a vertex merge error afterward (_refresh_vme_state)
        -- flipping is exactly as likely to introduce or fix one as
        making/deleting a connection is."""
        if not self.selected_ids:
            return
        self._push_undo()
        for shape in self.shapes:
            if shape["id"] in self.selected_ids:
                shape["flipped"] = not shape["flipped"]
        self._refresh_vme_state()
        self._redraw()

    def _flip_selected_shapes(self, axis):
        """"Flip Horizontal"/"Flip Vertical" ([H]/[V], or the matching
        toolbar button, `axis` = "horizontal"/"vertical") -- mirrors the
        WHOLE current selection, as one rigid arrangement, about the
        shared bounding box of every selected shape's own world
        vertices -- a no-op with nothing selected. For a single selected
        shape this is the same as flipping it about its own bounding
        box; for several, they flip TOGETHER about one shared axis (so
        their positions relative to each other mirror too), not each
        independently in place -- the same convention Illustrator/
        Photoshop use for a multi-object flip.

        Unrelated to _on_flip_key's "flipped" bit (which side of the
        fabric faces out) -- this is a purely geometric reorientation.
        Every shape here is a REGULAR polygon, always congruent to its
        own mirror image, so a genuine reflection of ITS OWN vertices
        produces the exact same vertex SET as some plain rotation of it
        does -- no real reflection transform is ever needed for the
        shape itself. Which rotation, though, is NOT simply "pi minus
        the current angle" for one axis and "minus the current angle"
        for the other, the way a single isolated point would reflect --
        mirroring a whole polygon also REVERSES which direction its
        vertices are traversed in (a genuine reflection has no fixed
        handedness the way a rotation does), so the correct replacement
        rotation also depends on _LOCAL_VERTICES' own starting angle. For
        this app's own _LOCAL_VERTICES convention, `rotation = -rotation`
        reproduces a HORIZONTAL mirror (flip left-right) and `rotation =
        pi - rotation` reproduces a VERTICAL one (flip up-down) -- the
        reverse of what the single-point intuition suggests.

        Reflecting a shape's OWN vertex set about an axis OTHER than its
        own center (the group's shared one, generally) is then just that
        same rotation change PLUS moving its center to the mirror image
        of where it was: reflecting about a line at x=A is, for every
        point, exactly reflecting about x=cx shifted by 2*(A-cx) in x
        (a plain algebraic identity, independent of the shape's own
        geometry) -- so `new_cx = 2*A - cx` (or `new_cy = 2*A - cy` for a
        vertical flip) is what actually carries a shape from mirroring
        "in place" to mirroring about the group's own shared axis.

        BUT that same index-reversal is exactly why an existing
        connection can't just be left alone: since edge index k's
        physical direction shifts to wherever some OTHER index now
        points, a connection anchored to "shape S edge k" would silently
        end up glued to the WRONG physical edge once the rotation
        changes, even though the shape's own silhouette flipped
        correctly. So for every flipped shape, this also captures its
        edge midpoints BEFORE changing anything, works out (by matching
        each one's mirrored position against the shape's NEW edge
        midpoints, `_closest_point_index`) which NEW edge index each OLD
        one now corresponds to, and rewrites every connection touching
        that shape to use the new index -- keeping it attached to the
        exact same PHYSICAL edge (and neighbor) it was before, not just
        the same-numbered one. Net validity (`_refresh_vme_state`) is
        therefore unaffected by a flip either way: no physical gluing
        actually changed, only which local index each shape happens to
        call it by.

        A touched connection's own bezier handle also gets its "t" component NEGATED
        (the "n" component is left
        alone): mirroring reverses which physical direction "corner k ->
        corner k+1" actually points along a given edge (the same
        handedness reversal the edge-index remap above exists for), so a
        "t" (tangent-axis)
        offset must flip sign to keep the control point at its own
        correctly-mirrored world position, while "n" (the normal-axis
        offset, "how far outward from centroid") is a handedness-
        independent distance that a mirror doesn't touch at all. Without
        this, a curve's own shape would silently distort (not just
        relocate) every time either endpoint's shape got flipped, even
        though the edges themselves stayed correctly glued."""
        if not self.selected_ids:
            return
        self._push_undo()
        selected = [s for s in self.shapes if s["id"] in self.selected_ids]
        all_vertices = [v for s in selected for v in self._shape_world_vertices(s)]
        old_mids = {shape["id"]: self._shape_edge_midpoints(shape) for shape in selected}

        if axis == "horizontal":
            xs = [v[0] for v in all_vertices]
            axis_value = (min(xs) + max(xs)) / 2

            def mirror_point(p):
                return (2 * axis_value - p[0], p[1])

            for shape in selected:
                shape["cx"] = 2 * axis_value - shape["cx"]
                shape["rotation"] = -shape["rotation"]
        else:
            ys = [v[1] for v in all_vertices]
            axis_value = (min(ys) + max(ys)) / 2

            def mirror_point(p):
                return (p[0], 2 * axis_value - p[1])

            for shape in selected:
                shape["cy"] = 2 * axis_value - shape["cy"]
                shape["rotation"] = math.pi - shape["rotation"]

        edge_maps = {}
        for shape in selected:
            new_mids = self._shape_edge_midpoints(shape)
            edge_maps[shape["id"]] = {
                old_edge: _closest_point_index(mirror_point(mid), new_mids)
                for old_edge, mid in enumerate(old_mids[shape["id"]])
            }
        for conn in self.connections:
            if conn["a_shape"] in edge_maps:
                conn["a_edge"] = edge_maps[conn["a_shape"]][conn["a_edge"]]
                conn["a_handle"]["t"] = -conn["a_handle"]["t"]
            if conn["b_shape"] in edge_maps:
                conn["b_edge"] = edge_maps[conn["b_shape"]][conn["b_edge"]]
                conn["b_handle"]["t"] = -conn["b_handle"]["t"]

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
        self._update_title()
        self._redraw()

    # ---- undo/redo (Ctrl+Z / Ctrl+Y) ----

    def _snapshot_state(self):
        """A deep-copied {"shapes", "connections", "_next_shape_id",
        "_next_connection_id", "_rev"} -- everything Ctrl+Z/Ctrl+Y need
        to restore the canvas exactly, deep-copied so neither the
        snapshot nor later live edits can ever mutate the other's data
        (every value here is a plain int/float/bool/dict/list, so this
        is cheap and never needs anything smarter than copy.deepcopy).
        "_rev" is the live canvas's OWN revision number at the moment of
        capture (self._revision -- see its own comment in __init__) --
        restoring it, rather than assigning a fresh one, is what lets
        undoing back to a previously-saved state read as no-longer-dirty
        again."""
        return {"shapes": copy.deepcopy(self.shapes), "connections": copy.deepcopy(self.connections),
                "_next_shape_id": self._next_shape_id, "_next_connection_id": self._next_connection_id,
                "_rev": self._revision}

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
        self._revision = snap["_rev"]

    def _record_undo_snapshot(self, snap):
        """Pushes an ALREADY-CAPTURED snapshot onto the undo stack
        (capping it at UNDO_STACK_LIMIT, dropping the OLDEST entry once
        full) and clears the redo stack -- a fresh action, like any
        ordinary undo system, discards whatever redo history existed
        before it, since it's no longer the alternate future that
        history led to. This is also the single place that gives the
        LIVE canvas a fresh revision number (see self._revision's own
        comment in __init__, which is what self._dirty actually reads)
        -- both _push_undo and _commit_undoable_change funnel through
        here, so every REAL change (as opposed to a plain click that
        moved nothing) is covered without needing to do it separately at
        each call site. Also refreshes the title (for the "*") and the
        vertex-merge-error state (_refresh_vme_state) -- harmless to
        recompute even for an edit (like a drag) that can't actually
        change validity, and it means most call sites don't need to
        remember to do either themselves."""
        self._undo_stack.append(snap)
        if len(self._undo_stack) > UNDO_STACK_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._revision = self._next_revision
        self._next_revision += 1
        self._update_title()
        self._refresh_vme_state()

    def _push_undo(self):
        """Call BEFORE an instantaneous action (drop, delete, make a
        connection, copy/paste, New, Load) that's about to change
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
        contain whatever used to be selected. _restore_snapshot puts
        self._revision back to whatever it was at the restored point
        (see its own comment), so self._dirty (and the title's "*")
        automatically read correctly -- undoing all the way back to the
        last save reads as no-longer-dirty, not just "some undo
        happened"."""
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot_state())
        self._restore_snapshot(self._undo_stack.pop())
        self.selected_ids = set()
        self.selected_connection_id = None
        self._drag_state = None
        self._bezier_handle_drag = None
        self._rotate_state = None
        self._connection_pending = None
        self._update_title()
        self._refresh_vme_state()
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
        self._bezier_handle_drag = None
        self._rotate_state = None
        self._connection_pending = None
        self._update_title()
        self._refresh_vme_state()
        self._redraw()

    def on_copy_key(self, _event=None):
        """Ctrl+C: remembers every SELECTED shape's own type, rotation,
        ABSOLUTE position, and "flipped" bit, PLUS every connection with
        BOTH endpoints among the selected shapes -- one connecting a
        selected shape to one that ISN'T copied along with it has
        nothing on the other end to reproduce, so it's simply dropped,
        same as _remove_shape already does for a shape that's actually
        deleted. No-op if nothing's selected. Storing each shape's own
        absolute position, not an offset relative to the others, is what
        lets a multi-shape paste reproduce the exact same relative
        arrangement, just moved as a whole -- see on_paste_key.
        Connections reference their two shapes by INDEX into this same
        list (not by id, which won't exist yet until paste time creates
        fresh ones). Also a no-op outside Move mode -- shapes aren't
        selectable in Join mode at all (see module docstring's "Tool
        modes" section), so self.selected_ids is already always empty
        there, but this makes the restriction explicit rather than
        incidental."""
        if self.tool_mode != "move" or not self.selected_ids:
            return
        copied_shapes = [s for s in self.shapes if s["id"] in self.selected_ids]
        index_of = {s["id"]: i for i, s in enumerate(copied_shapes)}
        self._clipboard = {
            "shapes": [{"n": s["n"], "rotation": s["rotation"], "cx": s["cx"], "cy": s["cy"],
                        "flipped": s["flipped"]}
                       for s in copied_shapes],
            "connections": [
                {"a_index": index_of[c["a_shape"]], "a_edge": c["a_edge"],
                 "b_index": index_of[c["b_shape"]], "b_edge": c["b_edge"],
                 "a_handle": dict(c["a_handle"]), "b_handle": dict(c["b_handle"])}
                for c in self.connections
                if c["a_shape"] in index_of and c["b_shape"] in index_of
            ],
        }

    def on_paste_key(self, _event=None):
        """Ctrl+V: drops a fresh instance of every copied shape, each at
        its own remembered rotation and "flipped" bit, ALL offset
        together by PASTE_OFFSET from their remembered positions -- so a
        multi-shape copy pastes back in the same relative arrangement
        (hatching included) it was copied in, just shifted as a group --
        PLUS a fresh connection for every one copied alongside them (see
        on_copy_key), between the corresponding NEW shapes. No-op if
        nothing's been copied yet. Advances the clipboard's OWN stored
        positions by that same offset every paste, so repeated Ctrl+V
        cascades diagonally outward instead of stacking every copy
        exactly on top of the last one. The new shapes (not the new
        connections) are left selected afterward (replacing whatever was
        selected before), same as a fresh drop. Also a no-op outside
        Move mode (see on_copy_key) -- otherwise the clipboard from an
        EARLIER Move-mode copy would still be pasteable after switching
        to Join mode, where a pasted shape couldn't be selected, moved,
        or connected to anything anyway."""
        if self.tool_mode != "move" or not self._clipboard:
            return
        self._push_undo()
        new_ids = []
        for entry in self._clipboard["shapes"]:
            entry["cx"] += PASTE_OFFSET
            entry["cy"] += PASTE_OFFSET
            shape = {"id": self._next_shape_id, "n": entry["n"],
                     "cx": entry["cx"], "cy": entry["cy"],
                     "rotation": entry["rotation"], "flipped": entry["flipped"]}
            self._next_shape_id += 1
            self.shapes.append(shape)
            new_ids.append(shape["id"])
        for conn in self._clipboard["connections"]:
            self.connections.append({
                "id": self._next_connection_id,
                "a_shape": new_ids[conn["a_index"]], "a_edge": conn["a_edge"],
                "b_shape": new_ids[conn["b_index"]], "b_edge": conn["b_edge"],
                "a_handle": dict(conn["a_handle"]), "b_handle": dict(conn["b_handle"]),
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

    def _draw_shape(self, screen_vertices, fill_hex, selected, hatched=False):
        photo, (left, top) = _rasterize_polygon(
            screen_vertices, fill_hex,
            outline_hex=SELECTION_OUTLINE_COLOR if selected else None,
            outline_width=SELECTION_OUTLINE_WIDTH if selected else 0,
            hatched=hatched)
        self._shape_photos.append(photo)  # keep alive -- Tk drops a GC'd PhotoImage
        self.canvas.create_image(left, top, anchor="nw", image=photo)

    def _draw_connection_line(self, a, b, selected):
        """Plain straight segment -- used only for the pending connection's
        own drag-preview line (_redraw), which has no second shape/edge
        yet to define a real curve from. A MADE connection always draws
        as a bezier instead (_draw_connection_curve)."""
        self.canvas.create_line(
            *a, *b, fill=SELECTION_OUTLINE_COLOR if selected else CONNECTION_COLOR,
            width=CONNECTION_SELECTED_WIDTH if selected else CONNECTION_WIDTH)

    def _draw_connection_curve(self, conn, selected):
        """A real connection's cubic bezier (module docstring's bezier
        section), sampled into a many-segment polyline (_cubic_bezier_
        points has no Tk equivalent with two independent control
        points) -- same color/width convention _draw_connection_line
        used for the plain-line version this replaced."""
        curve = self._connection_screen_curve(conn)
        if curve is None:
            return
        flat = [coord for point in curve for coord in point]
        self.canvas.create_line(
            *flat, fill=SELECTION_OUTLINE_COLOR if selected else CONNECTION_COLOR,
            width=CONNECTION_SELECTED_WIDTH if selected else CONNECTION_WIDTH)

    def _draw_bezier_handles(self, conn):
        """The two adjustable control-point handles for `conn` -- a thin
        red line from each endpoint (edge midpoint) to its own control
        point, with a filled red dot at the point itself (BEZIER_HANDLE_
        COLOR/_RADIUS/_LINE_WIDTH) -- ONLY ever called for the single
        currently-selected connection (see _redraw and module docstring:
        "only adjustable when visible")."""
        geometry = self._connection_geometry(conn)
        if geometry is None:
            return
        a_mid, a_ctrl, b_ctrl, b_mid = geometry
        for mid, ctrl in ((a_mid, a_ctrl), (b_mid, b_ctrl)):
            p0 = self._world_to_screen(*mid)
            p1 = self._world_to_screen(*ctrl)
            self.canvas.create_line(*p0, *p1, fill=BEZIER_HANDLE_COLOR,
                                     width=BEZIER_HANDLE_LINE_WIDTH)
            self.canvas.create_oval(
                p1[0] - BEZIER_HANDLE_RADIUS, p1[1] - BEZIER_HANDLE_RADIUS,
                p1[0] + BEZIER_HANDLE_RADIUS, p1[1] + BEZIER_HANDLE_RADIUS,
                fill=BEZIER_HANDLE_COLOR, outline="")

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
            self._draw_shape(screen_vertices, POLYGON_COLORS[shape["n"]],
                              selected=shape["id"] in self.selected_ids, hatched=shape["flipped"])

        for conn in self.connections:
            # A connection highlights whenever it's explicitly selected
            # OR it touches any currently-selected shape -- the shape at
            # its OTHER end stays its normal color (see the shape-drawing
            # loop above, which only lights up self.selected_ids), so
            # only the curve itself, not its neighbour, reads as "part of
            # this".
            highlighted = (conn["id"] == self.selected_connection_id
                           or conn["a_shape"] in self.selected_ids
                           or conn["b_shape"] in self.selected_ids)
            self._draw_connection_curve(conn, selected=highlighted)

        if self._connection_pending is not None:
            from_shape = self._shape_by_id(self._connection_pending["from_shape"])
            if from_shape is not None:
                anchor = self._world_to_screen(
                    *self._shape_edge_midpoints(from_shape)[self._connection_pending["from_edge"]])
                self._draw_connection_line(anchor, self._pending_cursor_screen, selected=True)

        # EVERY placed shape's EVERY edge gets a handle -- but ONLY in
        # Join mode, the only mode a handle is actually selectable in at
        # all (see module docstring's "Tool
        # modes" section) -- not just the selected one, so a connection can be
        # started with a single click straight onto any handle, with no
        # "select the shape first" step. A handle lights up red if its
        # own shape is SELECTED (every one of that shape's edges, so any
        # of them can be picked to start a connection from), or it's the
        # pending connection's own origin point (`pending_point`, which
        # needs to stay lit even though clicking it just DESELECTED that
        # shape -- see _on_canvas_press: the POINT is the selected thing
        # now, not the shape it belongs to) or its CURRENT hover target
        # (`hover_point`) -- deliberately just that one edge, not every
        # edge of the shape it's on (an earlier version lit the whole
        # target shape, which read as a stray selection): only the
        # specific edge a second click would actually complete onto
        # lights up now, leaving the rest of that shape (including its
        # outline, in the shape-drawing loop above) at its normal,
        # unselected look.
        # Otherwise a handle is filled white if some connection already
        # uses it, or an unfilled ring if not (see _draw_handle_circle).
        if self.tool_mode == "join":
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
                        # connection hover check above); showing every free
                        # handle all the time read as visual noise on a busy
                        # canvas.
                        if self._cursor_screen is None:
                            continue
                        sx, sy = self._world_to_screen(mx, my)
                        cx, cy = self._cursor_screen
                        if math.hypot(cx - sx, cy - sy) > HANDLE_HIT_RADIUS:
                            continue
                    self._draw_handle_circle(shape, edge_index, lit=lit, joined=joined)

        # The selected connection's own two bezier control handles --
        # ONLY that one connection (never one merely highlighted via an
        # endpoint shape's selection, see module docstring's bezier
        # section) and only in Join mode, the only mode a
        # connection can even BE selected in (self.selected_connection_id
        # is already always None otherwise -- see _set_tool_mode). Drawn
        # last (on top of everything else drawn so far) so a handle is
        # never occluded by a shape or another connection's own curve.
        if self.tool_mode == "join" and self.selected_connection_id is not None:
            selected_conn = next(
                (c for c in self.connections if c["id"] == self.selected_connection_id), None)
            if selected_conn is not None:
                self._draw_bezier_handles(selected_conn)

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

        if self.debug_mode:
            self._draw_dedup_vertex_labels()

        if self._marquee_start is not None:
            x0, y0 = self._marquee_start
            x1, y1 = self._marquee_current
            # width=1 (not 2) -- Tk-on-Windows only honors a custom dash PATTERN precisely at
            # hairline width; a wider line silently falls back to a generic short dotted GDI pen
            # regardless of the requested dash tuple.
            #
            # Four separate create_line calls (one per edge), not one create_rectangle -- a
            # single closed-shape item (rectangle or polygon) resets Tk's own dash PHASE at each
            # corner based on where the previous edge's pattern happened to end, so the same
            # dash tuple can land completely differently at each corner depending on the
            # rectangle's exact pixel dimensions -- a tiny dash-length change can then shift that
            # phase landing enough to look like a much bigger visual change than the numbers
            # suggest. Each edge getting its OWN independent dash
            # run starting fresh (same fix already applied to the orphan-piece outline in
            # interactive_inflater_app.app) makes a dash-length change behave predictably.
            for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                                        ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                self.canvas.create_line(ax, ay, bx, by, fill=MARQUEE_OUTLINE_COLOR,
                                         dash=MARQUEE_DASH, width=1)

    def _draw_debug_vertex_label(self):
        """Debug mode only ("d" key): finds the shape VERTEX (a corner,
        not an edge handle) nearest the cursor within
        DEBUG_VERTEX_HOVER_RADIUS and, if one's close enough, rings it
        and labels it "vSHAPE.CORNER" using the hovered corner's OWN
        (shape_id, corner_index) -- ALWAYS that, never the union-find
        ROOT slot _vertex_roots might give it (which can legitimately
        belong to some other, genuinely-connected shape, e.g. shape 42's
        own corner 2 showing as "v34.0" because it's really the same
        vertex as shape 34's corner 0) -- showing the root instead was
        tried and reverted, since most corners on a big, densely-
        connected net ARE genuinely shared with a neighbor, so most
        hovers showed a foreign-looking label instead of the shape
        actually under the cursor. Shared/conflicting
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

    def _draw_dedup_vertex_labels(self):
        """Debug mode's always-on dedup vertex display (no separate
        toggle): labels EVERY shape's EVERY corner with its dedup GROUP
        number, white text on a small filled circle -- unlike
        _draw_debug_vertex_label (one corner, on hover, by its OWN
        address), two corners already merged to the same vertex via
        _vertex_roots show the SAME number here, so a whole net's dedup
        structure is visible at a glance rather than one corner at a
        time. A corner currently part of a genuine vertex merge error
        (re-validated independently, live, right here -- see
        _validate_shapes_connections' own `vertex_merge_error_slots`,
        NOT whatever self._vme_active last cached, so this is always
        exactly current) fills red instead of the usual black. Numbers
        are assigned fresh on every redraw, in shape/corner visiting
        order (same convention _faces_from_shapes uses for its own,
        separate export-time numbering) -- a display convenience
        recomputed from the CURRENT self.shapes/self.connections each
        time, not a stored id, so a connection made/deleted or a shape
        flipped is reflected the next redraw with no separate
        invalidation step needed."""
        roots = _vertex_roots(self.shapes, self.connections)
        try:
            _validate_shapes_connections(self.shapes, self.connections)
            conflicting_slots = frozenset()
        except NetValidationError as e:
            conflicting_slots = e.vertex_merge_error_slots
        group_numbers = {}
        font = ("TkDefaultFont", 8, "bold")
        r = DEDUP_VERTEX_RADIUS
        for shape in self.shapes:
            for corner, (vx, vy) in enumerate(self._shape_world_vertices(shape)):
                slot = (shape["id"], corner)
                root = roots[slot]
                if root not in group_numbers:
                    group_numbers[root] = len(group_numbers)
                sx, sy = self._world_to_screen(vx, vy)
                bg = DEDUP_VERTEX_CONFLICT_BG if slot in conflicting_slots else DEDUP_VERTEX_BG
                self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill=bg, outline="")
                self.canvas.create_text(sx, sy, text=str(group_numbers[root]),
                                         fill=DEDUP_VERTEX_FG, font=font)


def main():
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    InteractiveBuilderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
