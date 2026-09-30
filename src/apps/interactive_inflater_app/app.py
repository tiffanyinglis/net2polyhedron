"""Interactive Inflater -- combines interactive_builder_app's net-building
canvas (left pane) with a simplified, single-panel version of
inflate_polyhedron_app's solver viewer (right pane) in one window, so a net
built by hand can be inflated immediately with no save/load round trip.

    python src/apps/interactive_inflater_app/app.py

Left pane (BuilderPane): reuses interactive_builder_app.app.InteractiveBuilderApp
directly (imported, not copied -- that file is read-only here, see the
net-fold-project skill's untouchable.md) via a small subclass that only
overrides layout (_build_ui/_build_palette_entry: shape palette moved to a
TOP row, centered; no left tool strip at all -- Edit is this app's only tool
mode, so a mode-switch button/strip for it would be pure vestigial UI,
2026-09-29 explicit user request -- the canvas fills that space instead) and
drops the pieces that only make sense for a standalone window (its own File
menu/window title/WM_DELETE_WINDOW/font-scaling pass -- CombinedApp builds
ONE File menu, with just Load... (no Save yet, 2026-09-19, explicit), for the
whole window instead).
Every canvas interaction (place/drag/select/delete/rotate/pan, Edit mode,
bezier connections, Polygon Fold, undo/redo, flip, debug mode) is exactly
interactive_builder_app's own, unmodified.

Right pane (InflaterPane): a from-scratch, deliberately much simpler sibling
of inflate_polyhedron_app -- one PyVista off-screen-rendered panel (not four
side-by-side Level 0-3 panels), redrawn in place as "Inflate" advances
through the SAME pipeline inflate_polyhedron_app's "Run Simulation" runs
(Level 0 fan-triangulate -> Relax -> calibrate to target RMS -> Subdivide ->
repeat through MAX_LEVEL). No replay-frame animation, no per-level camera
groups, no Convergence History table, no debug mode/normals/mesh validation,
no Stop button -- see the module's own "Simplifications vs.
inflate_polyhedron_app" note below for the full list and why.

Bridging the two panes: clicking Inflate reads the LEFT pane's CURRENT
in-memory shapes/connections through the exact same
_expand_folded_shapes/_faces_from_shapes/_edges_from_shapes/
_face_edge_ids_from_shapes pipeline interactive_builder_app's own Save uses
(BuilderPane.export_mesh_dict, calling the inherited _export_faces_and_layout
directly), producing the same mesh dict Save would write to a .poly file --
without ever writing one. stretchy_mesh.load_stretchy_mesh/
load_stretchy_mesh_edges (this project's one authoritative parser+validator
for that format) only accept a file PATH, and are on this project's
untouchable list (no signature changes allowed) -- rather than reimplement
their validation a second time here (real risk of it drifting from the
original), _load_mesh_from_dict writes the dict to a throwaway
tempfile.NamedTemporaryFile, calls those same two functions on it, and
deletes it immediately after -- the mesh itself is never written to (or
read from) any file under data/, only this one transient temp file that
never outlives a single Inflate click.

Club terminology (2026-09-28, explicit user request -- "let's make it clear by using the same
language (both in docs and in code)"): the anchor's own connected component (BuilderPane.
central_shape_ids) is the CLUB. Every shape in it is a MEMBER. A member with 0 or 1 connections
is a GUEST (2026-09-28, explicit correction: "Guests are members with 0 or 1 connections" -- 0
covers the very first piece ever placed, with nothing to connect to yet) -- placed flatly
against its one neighbor if it has one, or just placed with no relax/inflate involved at all if
it has none, never touching relax/inflate either way (this is what the surrounding code still
mostly calls a "pendant" -- same concept, not yet renamed everywhere). A member with two or more
connections is an INSIDER -- inflation only ever involves insiders (Rule 1). A shape not in the
club at all (not connected to the anchor) is an OUTSIDER/non-member. self.is_fully_inflated tracks whether the club's own insiders currently
reflect a real relax/inflate result (Rule 2: reset to False whenever the club empties out
entirely; set True whenever a real pressure-calibration pass completes) -- on_diff_inflate_
clicked reads it to decide Diff Inflate (True) vs. a Full Inflate redirect (False) whenever a
builder edit actually changes the insiders -- their own membership (a guest promoted to insider,
or vice versa) or a connection between two of them (Rule 3). A guest-only add/remove never
reaches that decision at all (_is_pendant_add/_diff_attach_pendant_only's own fast path) since
it never changes what the insiders are. Undo/redo funnel through the SAME BuilderPane.on_change
hook (refresh_diff_eligibility) every other edit does, so Rule 4 falls out of the existing
architecture for free -- no separate undo/redo-specific handling needed.

Simplifications vs. inflate_polyhedron_app (all explicitly allowed by this
app's own spec):
- One drawing panel, redrawn per level, not four side-by-side ones.
- No AUTO-PLAY replay animation -- unlike inflate_polyhedron_app's own winning-trial replay
  (_start_frame_replay), a completed run's own captured frames (self._replay_frames, debug-
  mode-only -- 2026-09-29, explicit user request) are only ever scrubbed by hand via the
  replay slider (_on_replay_slider_moved), never auto-played.
- No per-level independent camera groups/pan/drag/scroll -- the single
  panel auto-frames itself fresh on every redraw (PyVista's own "iso" view
  + reset_camera()), no interactive camera at all.
- No Convergence History table, no session save/load, no Stop button, no
  debug mode (normals/mesh validation), no steps-vs-convergence radio.
- Per-level target RMS %/tolerance entries and DEFAULT_TOLERANCE are
  adapted directly from inflate_polyhedron_app's own setup row.

Full Inflate vs. Diff Inflate (2026-09-19, explicit): "Full Inflate" is the pipeline above,
unchanged, always enabled. "Diff Inflate" instead reuses the LAST successfully-completed
inflate's own Level-3 result as its starting point, when the net has changed by only ONE
added or removed shape since then (BuilderPane.classify_change) -- it skips Levels 0-2's own
(expensive) relax/calibrate passes entirely:
- Remove: filters the stored Level-3 faces/positions down to whatever's left (no interpolation
  needed at all -- see InflaterPane._diff_remove_face), then runs ONE pressure-calibration pass
  at Level 3.
- Add: seeds a FRESH combined (old+new) base mesh's own Level-0 positions with the OLD
  faces' CURRENT (already-relaxed) 3D positions -- a base vertex id persists unchanged through
  every subdivision level (see mesh_levels.py's own docstring), so interpolating from these
  through the ordinary fan+quarter+quarter pipeline (_subdivide_combined_to_level3, pure
  interpolation, no solving) reproduces the OLD portion's Level-3 geometry exactly; only the
  NEW face's own region is actually unknown, seeded near its attachment point. A single relax
  pass settles that region, then ONE pressure-calibration pass at Level 3 (see
  InflaterPane._diff_add_face) -- deliberately NOT a vertex-id-preserving splice (subdivide_once's
  own id numbering shifts under an appended face -- see mesh_levels.py -- so this reconstructs
  fresh ids throughout instead of trying to reuse the old mesh's ones, which correctness doesn't
  need: only the SEED POSITIONS need to be old-consistent, not the ids labeling them).
Both paths share the ordinary _run_inflate_step/_on_inflate_step_done calibration call (already
naturally a single pass whenever self.subdivision_level == MAX_LEVEL going in). Anything else
(a moved/flipped/multi-shape change, an edited connection) is "complex" -- Diff Inflate stays
disabled and only Full Inflate can run. Eligibility re-checks after every builder edit
(BuilderPane.on_change, wired from CombinedApp) and after every completed Inflate click.

Stop/revert (2026-09-19, explicit): whichever button (Full/Diff Inflate) starts a run switches
to "Stop" (InflaterPane._set_running); clicking it, Level 0's own relax not converging within
SAFETY_STEP_CAP=50000 steps, a calibration trial that never converges (bounded by relax_once's
own MAX_UNBOUNDED_STEPS runaway guard, not by this app -- see _run_inflate_step's own docstring
for why SAFETY_STEP_CAP is deliberately NOT passed as estimate_pressure_for_target_stretch's own
max_nfev_per_trial), a pressure search that never found a workable pressure at all, or a
background-thread exception, all funnel into the same
_revert_run: discards whatever was computed and restores the mesh EXACTLY as it was right
before the click (self._pre_click_snapshot, taken by every pipeline entry point before it
touches self.faces/positions/etc.). Nothing is ever rendered mid-computation before a real
convergence checkpoint (on_full_inflate_clicked/_diff_remove_face/_diff_reexport_and_relax all
skip their own pre-computation self._render() calls) -- a non-converging run (e.g. a face left
floppy/loosely-attached by a net edit) used to redraw a visibly wrong intermediate state and
sometimes crash the renderer on it; now it simply reverts, with a popup for a genuine non-
convergence/divergence outcome (not for a plain user-requested Stop, which doesn't need one).
"""
import math
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import json
import os
import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinter.font as tkfont

import matplotlib.colors as mcolors
import numpy as np
from PIL import Image, ImageDraw, ImageTk
import pyvista as pv
# vtkmodules.* (the same sub-package pyvista itself imports from), not the monolithic `vtk`
# package -- `import vtk` eagerly loads every VTK module and is dramatically slower (order of
# a minute here) than pulling just the one class needed for picking.
from vtkmodules.vtkRenderingCore import vtkCellPicker
from scipy.spatial.transform import Rotation
import sv_ttk

import common.paths  # noqa: F401 -- side effect: puts src/ and src/apps/ on sys.path
from common.paths import DATA_DIR
from common.ui_theme import FACE_COLORS, PLOT_THEME, STATUS_COLORS

# inflate_polyhedron_app/session_state.py is a plain pydantic module with no Tkinter/app-object
# dependency (see its own module docstring) -- safe to import cross-app to read the SAME .hippo
# session format that app's own File > Save writes, rather than re-declaring an equivalent schema
# here (2026-09-26, explicit: "you need to implement loading of .hippo files").
from inflate_polyhedron_app.session_state import LevelStateModel, SessionStateModel
from interactive_inflater_app.session_state import InflaterSessionStateModel

from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.inflate_polyhedron.stretchy_mesh import (
    EDGE_LENGTH, estimate_pressure_for_target_stretch, load_stretchy_mesh,
    load_stretchy_mesh_edges, mesh_edges, random_initial_positions,
    relax_initial_configuration, repulsion_force,
)

# interactive_builder_app/app.py is NOT on the untouchable list, but per this app's own
# instructions it's still read-only from here -- imported directly (a plain namespace-package
# import, src/apps/ already being on sys.path) rather than copied, so its ~3700 lines of net-
# building logic are reused verbatim, not duplicated.
from interactive_builder_app.app import (
    CONNECTION_SELECTED_WIDTH, ICON_SIZE, MENU_ACTIVE_BG, MENU_BG, MENU_DISABLED_FG, MENU_FG,
    NetValidationError, POLYGON_COLORS, POLYGON_NS, SELECTION_OUTLINE_COLOR, InteractiveBuilderApp,
    _ICON_VERTICES, _rasterize_polygon, _enable_windows_dpi_awareness, _expand_folded_shapes,
    _shape_face_corner_order, _vertex_roots, _edges_from_shapes, _face_edge_ids_from_shapes,
    _faces_from_shapes, _validate_shapes_connections,
)

INFLATER_APP_DIR = Path(__file__).resolve().parent

# Same idea as both sibling apps' own UI_FONT_SCALE -- applied once, centrally, to every named
# Tk/ttk font at startup. InteractiveBuilderApp normally does this itself in __init__; BuilderPane
# overrides that step out (see its own docstring) so it only ever happens once for the whole
# combined window, not once per pane. Smaller than the two sibling apps' own 1.3 -- this window
# packs a full builder AND a full inflater side by side, so it needs smaller text to fit
# comfortably (2026-09-19, explicit).
UI_FONT_SCALE = 1.0

# Palette icons (BuilderPane._build_palette_entry, below) are shrunk to this size -- smaller than
# interactive_builder_app's own ICON_SIZE=84, since this app's palette row has roughly half that
# app's own window width to work with (half the window is the inflater pane). _ICON_VERTICES
# (imported from interactive_builder_app, fixed at ICON_RADIUS=30 regardless of ICON_SIZE) is
# scaled down by INFLATER_ICON_SIZE/ICON_SIZE to match, preserving the same padding ratio.
# 56, not the original 48 (2026-09-29, explicit user request: "make the polygon shapes at the
# top bigger, without increasing the overall toolbar size") -- paired with _build_ui's own
# palette-row padding drop from 8 to 4 top/bottom, so the row's total height (padding + icon
# widget, including its own highlightthickness border) comes out EXACTLY the same as before:
# old 8 + (48 + 2*2) + 8 = 68, new 4 + (56 + 2*2) + 4 = 68.
INFLATER_ICON_SIZE = 56

# ---- right pane (InflaterPane) constants, adapted from inflate_polyhedron_app ----

# Release mode's button row (2026-09-29, explicit user request: "replace the reinflate button
# with an icon button like the refresh button in browsers. also have an undo and redo button
# to the left of it", then "the buttons should look like [a flat browser nav bar]") -- plain
# Unicode glyphs on flat, borderless plain tk.Button widgets (own docstring on their
# construction has why plain tk over ttk) rather than hand-drawn canvas icons (the convention
# the now-removed left tool strip used, see interactive_builder_app's own _new_toolbar_icon) --
# simpler, and these buttons live in InflaterPane's own root, not BuilderPane's, so that helper
# isn't available here anyway.
REFRESH_ICON_TEXT = "↻"  # clockwise open circle arrow -- Reinflate's new icon.
# Plain straight arrows, not curved undo/redo hooks (2026-09-29, explicit user request, second
# reference image: a browser-style back/forward/refresh trio) -- back == undo, forward == redo.
UNDO_ICON_TEXT = "←"
REDO_ICON_TEXT = "→"
# Text color for a disabled icon button (undo/redo when their own stack is empty) -- a plain
# tk.Button (see _build_icon_button) takes this directly as `disabledforeground`, no per-theme
# ttk style/state map needed.
ICON_BUTTON_DISABLED_FG = "#555555"

DEFAULT_TOLERANCE = 1e-4
# Per-level Target RMS stretch % defaults -- auto-picked from whether the CENTRAL object is
# currently closed (no free/unglued edge anywhere) or open (at least one), re-checked after
# every builder edit (2026-09-28, explicit user request: "the algorithm should auto detect
# whether the current central model is open or closed, and inflate it to 5% or 10% based on
# that information. that should be checked after every change") -- see InflaterPane's own
# _is_central_object_closed/_apply_target_rms_defaults, and refresh_diff_eligibility for where
# it's re-applied on every change. Adapted directly from inflate_polyhedron_app's own
# LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED/_OPEN (duplicated, not imported -- see module docstring).
LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED = {1: 10.0, 2: 10.0, 3: 10.0}
LEVEL_DEFAULT_TARGET_RMS_PCT_OPEN = {1: 5.0, 2: 5.0, 3: 5.0}

# Where inflate_polyhedron_app's own .hippo session saves (and this app's own .hippie saves) live
# -- same directory that app's SESSION_OUTPUT_DIR points at (DATA_DIR / "output"), duplicated
# rather than imported (this app never imports that app's own app.py -- see module docstring;
# session_state.py, imported above, is a plain schema module with no such constant).
SESSION_OUTPUT_DIR = DATA_DIR / "output"

# This app's own session-file extension (2026-09-26, explicit) -- ".hippie" rather than
# inflate_polyhedron_app's own ".hippo", since the two formats aren't interchangeable: a .hippie
# may describe more than one connected piece (net_fold_project's own untouchable.md now forbids
# that everywhere else -- see BuilderPane.export_full_net_dict's own docstring) and carries an
# anchor_shape_id a .hippo file has no concept of at all.
SESSION_FILE_EXTENSION = ".hippie"
# Hard per-attempt step cap (Relax and each Inflate calibration trial's own convergence top-up)
# -- same constant/value as inflate_polyhedron_app's own INFLATE_SAFETY_STEP_CAP, duplicated
# rather than imported (this app never imports that module -- see its own docstring).
SAFETY_STEP_CAP = 50000

# Diff Inflate's own looser acceptance tolerance (vs. estimate_pressure_for_target_stretch's own
# default tol_pct=1.0) when seeding its pressure search from the last successful inflate's own
# converged pressure (2026-09-19, explicit: "If it results in more than 5% different from the
# target stretch, then you can do another guess" -- i.e. within 5% needs no second guess at
# all). Only the Diff Inflate paths pass this; Full Inflate keeps the function's own default.
DIFF_PRESSURE_GUESS_TOL_PCT = 5.0

# Polygon-edge line width in the 3D panel (2026-09-19, explicit, most recently "make the rim
# edge 3 for both sides and highlight width 4"; thinned to 2.5 on 2026-09-29, explicit: "make
# them a tad thinner"). The yellow hover highlight stays visually thicker still
# (HOVER_HIGHLIGHT_LINE_WIDTH) so it always reads as distinct from the ordinary edges.
POLYGON_EDGE_LINE_WIDTH = 2.5
HOVER_HIGHLIGHT_LINE_WIDTH = 4.0
SELECTED_HIGHLIGHT_LINE_WIDTH = 4.0

# How many pixels of ButtonPress-1-to-release movement still counts as a plain click (selects a
# face) rather than a rotate-drag -- a real click's press/release coordinates are rarely bit-
# for-bit identical (trackpad/mouse jitter), so 0 would misclassify most genuine clicks as tiny
# drags.
CLICK_MOVE_TOLERANCE_PX = 3

# The "central object" anchor's own on-canvas marker color -- white (2026-09-26, explicit: "make
# the anchor white instead of red"). Only shown in debug mode (2026-09-29, explicit: "show the
# anchor only in debug mode" -- the anchor is now purely automatic, see _plan_anchor_deletion/
# _on_delete_key, so there's no longer a user-facing reason to always keep it on screen).
ANCHOR_MARKER_COLOR = "white"
# The actual glyph drawn (2026-09-26, explicit: "use this ⚓︎") -- U+2693 ANCHOR, plus
# the U+FE0E "text presentation" variation selector so a font/platform that would otherwise
# prefer a colorful emoji-style glyph renders the plain monochrome symbol instead (matching every
# other single-color toolbar icon here).
ANCHOR_SYMBOL_CHAR = "⚓︎"
# The on-canvas anchor marker's own size, in fixed SCREEN pixels (not world units) -- so it reads
# as a consistent-size marker regardless of the anchor shape's polygon type or the canvas's
# current zoom level, unlike everything else BuilderPane draws in world space.
ANCHOR_MARKER_RADIUS_PX = 13

# A shape not part of the live central object is dimmed to this fraction of its own color (the
# rest blended toward the canvas background -- see _draw_shape) and gets a dashed outline instead
# of a solid one (2026-09-26, explicit: "add back the transparency... make the orphaned pieces
# 50% opacity").
DISCONNECTED_OPACITY = 0.5
# PLOT_THEME["fg"] rather than a hardcoded color so the outline reads as a neutral "not part of
# the model yet" marker, distinct from SELECTION_OUTLINE_COLOR (red) and the yellow hover
# highlight (both plain solid lines).
DISCONNECTED_OUTLINE_COLOR = PLOT_THEME["fg"]
# "Thick" is NOT a wider `width=` on a single line -- Tk-on-Windows only honors a custom dash
# PATTERN precisely at hairline width=1; anything wider silently snaps the pattern to the
# nearest of a small set of built-in pen styles (2026-09-26, explicit bug reports: "your changes
# aren't working" at width=2, then "the red/thick version reverted back to dots" at width=3).
# Instead, thickness is simulated by drawing DISCONNECTED_OUTLINE_LINE_COUNT (unselected, 2026-
# 09-26 explicit: "make the white outline on orphaned pieces slightly thicker. like thickness 2")
# or DISCONNECTED_SELECTED_OUTLINE_LINE_COUNT (selected) separate width=1 dashed lines side by
# side, offset a pixel apart PERPENDICULAR to each edge (_draw_dashed_edge) -- each individual
# line keeps its dash pattern crisp, and together they read as one thicker dashed line.
DISCONNECTED_OUTLINE_DASH = (5, 5)
DISCONNECTED_OUTLINE_LINE_COUNT = 2
# A SELECTED orphan's own outline (2026-09-26, explicit: "when an orphaned piece is selected,
# the white dashed outline should be replaced with a thick red dashed outline") -- SELECTION_
# OUTLINE_COLOR (imported below) for the color, same dash pattern as the unselected outline.
DISCONNECTED_SELECTED_OUTLINE_DASH = (5, 5)
DISCONNECTED_SELECTED_OUTLINE_LINE_COUNT = 3


def _draw_anchor_symbol(canvas, cx, cy, radius, color):
    """The anchor glyph ANCHOR_SYMBOL_CHAR ("⚓︎"), rendered as text centered at
    (cx, cy) -- the on-canvas anchor marker's own glyph (BuilderPane._redraw; formerly also
    shared with an "Anchor [A]" toolbar icon, removed 2026-09-29, explicit: "remove the
    Anchor[A] mode") (2026-09-26, explicit: "use this ⚓︎" -- replaces an earlier
    hand-drawn ring/shaft/crossbar glyph, which itself replaced a plain 5-point star). Font size
    scaled off `radius` the same way the earlier hand-drawn version's proportions were.

    No explicit font FAMILY (2026-09-26, explicit bug report: "the tool button is not displaying
    properly" -- a literal "Segoe UI Symbol" isn't guaranteed present under that exact name on
    every Windows version, and Tk doesn't substitute a different family on its own when the named
    one is missing or lacks the glyph, unlike relying on the empty-family/default font, which
    goes through the platform's own font-linking/fallback for a missing glyph). `anchor="center"`
    centers create_text's FONT-METRICS bounding box, not the glyph's own visible ink -- a symbol
    glyph is rarely vertically centered within its own font metrics, so the caller (2026-09-26,
    explicit bug report: "anchor symbol is not centred in the polygon") re-centers the item on
    its ACTUAL rendered ink bbox afterward via canvas.move, which works regardless of whatever
    font ends up actually being used."""
    item = canvas.create_text(cx, cy, text=ANCHOR_SYMBOL_CHAR, fill=color,
                               font=("", max(1, round(radius * 1.6))), anchor="center")
    bbox = canvas.bbox(item)
    if bbox is not None:
        left, top, right, bottom = bbox
        canvas.move(item, cx - (left + right) / 2, cy - (top + bottom) / 2)


def _draw_dashed_edge(canvas, x1, y1, x2, y2, color, dash, line_count):
    """Draws a dashed segment from (x1, y1) to (x2, y2) as `line_count` separate width=1
    create_line calls, each offset one pixel further PERPENDICULAR to the edge than the last,
    centered on the true edge -- a "thick" dashed line built from several thin ones instead of
    one wide one (see DISCONNECTED_SELECTED_OUTLINE_LINE_COUNT's own comment for why: Tk-on-
    Windows only renders a custom `dash` pattern precisely at width=1). `line_count=1` draws a
    single ordinary width=1 dashed line, no offset."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    perp_x, perp_y = (0.0, 0.0) if length < 1e-9 else (-dy / length, dx / length)
    for i in range(line_count):
        offset = i - (line_count - 1) / 2
        ox, oy = perp_x * offset, perp_y * offset
        canvas.create_line(x1 + ox, y1 + oy, x2 + ox, y2 + oy, fill=color, width=1, dash=dash)


# Join-mode 3D edge hover/click (2026-09-19, explicit: "hovering over the 3d edge highlights
# the corresponding 2d connection") picks the nearest connection's glued seam to wherever the
# cursor's pick ray actually HITS the mesh surface (there's no separate pickable line geometry
# for each seam -- see _nearest_connection_at_position's own docstring) -- a fraction of the
# model's own bounding-sphere radius (self._half), not a fixed world distance, so it scales with
# the model regardless of zoom/subdivision level.
CONNECTION_PICK_TOLERANCE_FRACTION = 0.06

# Join-mode 3D drag-to-connect (2026-09-19, explicit: "hover over an open edge... drag to
# connect to another edge midpoint") -- fraction-of-self._half distance for how close the
# cursor's pick position must be to an open edge itself (proximity to the whole edge LINE, not
# just its midpoint -- 2026-09-19, explicit: "hovering over open edges highlight them") to
# reveal/target it.
OPEN_EDGE_PICK_TOLERANCE_FRACTION = 0.10

# Every part of the open-edge connect gesture is now REAL 3D geometry -- an edge highlighted
# yellow on hover, red once pressed/confirmed, and a red line between two connected edges'
# midpoints (2026-09-19, explicit: "let hovering over open edges highlight them in yellow...
# the mouse press causes the edge to be selected and drawn in red... mouse release causes both
# to be drawn in red with their midpoint connected in a thick red line (all drawn in 3d)") --
# unlike a flat screen-space overlay, real geometry follows the edge's own actual (possibly
# curved/subdivided) shape and persists correctly through camera rotate/pan/zoom for as long as
# Diff/Full Inflate takes to converge in the background. The ONE remaining screen-space overlay
# is the live drag's own rubber-band line to the cursor (2026-09-19, explicit: "the mouse drags
# out a connection in screen space (thick line)") -- CONNECTION_OVERLAY_LINE_WIDTH_PX/_COLOR are
# just for that. As thick as a SELECTED face/connection's own 3D highlight line (2026-09-19,
# explicit: "the line joining two midpoints should be as thick as selected edges") --
# SELECTED_HIGHLIGHT_LINE_WIDTH is a VTK actor line width (also effectively screen pixels),
# reused here directly rather than picking an unrelated pixel value, so the two stay in sync if
# that one ever changes.
CONNECTION_OVERLAY_LINE_WIDTH_PX = int(SELECTED_HIGHLIGHT_LINE_WIDTH)
CONNECTION_OVERLAY_LINE_COLOR = (220, 30, 30)

# The polygon-rim overlay's own color -- a single PLAIN light grey, not blended off the face's
# own color at all, and the SAME for both offset copies now, not a front/back split (2026-09-19,
# explicit: "the front/backside rims are super messy now [a ribbon-mesh attempt, see git
# history] go back to how things are and just draw both front/back rims in light gray (80%
# white)" -- since both copies read identically now, which one happens to be more visible at a
# given angle no longer matters, sidestepping the whole front/back distinction rather than
# solving it more precisely).
RIM_COLOR = (0.8, 0.8, 0.8)

# Smaller than inflate_polyhedron_app's own Level-1..3 panels would suggest (LEVEL_PANEL_WIDTH_
# LEVELS_1_3 x LEVEL_PANEL_HEIGHT there) would be too cramped for a SINGLE panel carrying all the
# detail 4 panels normally split -- this sits between that and this app's earlier, too-large
# 620x560 (2026-09-19, explicit: "make it smaller").
PANEL_SIZE = (420, 450)

# Same trackball-drag/pan/scroll-zoom idea and constants as inflate_polyhedron_app's own
# "Level N" panels (LEVEL_DEFAULT_ELEV/AZIM/LEVEL_DRAG_SENSITIVITY/LEVEL_ZOOM_STEP/_MIN/_MAX/
# _level_zoom_fill), duplicated rather than imported (see module docstring) and renamed without
# the "LEVEL_" prefix since this app has only ever the one panel (2026-09-19, explicit: "not
# rotatable/movable/scaling right now").
PANEL_DEFAULT_ELEV = 30.0
PANEL_DEFAULT_AZIM = -60.0
PANEL_DRAG_SENSITIVITY = 0.5
PANEL_ZOOM_STEP = 1.1
PANEL_ZOOM_MIN = 0.3
PANEL_ZOOM_MAX = 4.0
PANEL_ZOOM_FILL = 0.9

# A face's INSIDE (its backface) is drawn this fraction darker than its own outward-facing
# color, and its wireframe edges halfway between white and that color -- same idea and same
# INSIDE_FACE_DARKEN_FACTOR value as inflate_polyhedron_app's own _draw_level_panel (duplicated,
# not imported -- see module docstring), so both apps' 3D panels read consistently
# (2026-09-19, explicit: "the subdivision lines should be half way between white and the face
# colour, like in polyhedron_inflater"; "the inside of the polygon face [should be] a shade
# dark[er] than the outside... for both interactive_inflater and polyhedron_inflater").
INSIDE_FACE_DARKEN_FACTOR = 0.65


def _darken_color(color, factor=INSIDE_FACE_DARKEN_FACTOR):
    """`color` scaled toward black by `factor`, as an (r, g, b) tuple in [0, 1]."""
    return tuple(np.array(mcolors.to_rgb(color)) * factor)


def _weighted_color(color, weight, other="white"):
    """`weight` fraction `color` blended with `(1 - weight)` fraction `other`, as an (r, g, b)
    tuple in [0, 1] -- e.g. _weighted_color(face_color, 0.75) is 75% face_color/25% white."""
    a, b = np.array(mcolors.to_rgb(color)), np.array(mcolors.to_rgb(other))
    return tuple(weight * a + (1 - weight) * b)


def _point_segment_distance_3d(point, a, b):
    """Shortest distance from `point` to the 3D line SEGMENT a->b (not the infinite line) --
    the 3D counterpart of interactive_builder_app's own 2D _point_segment_distance, used to
    hit-test the 3D panel's own Join-mode cursor ray against a connection's glued seam (a thin
    line with no interior to pick a mesh face against)."""
    ab = b - a
    denom = np.dot(ab, ab)
    if denom < 1e-18:
        return float(np.linalg.norm(point - a))
    t = max(0.0, min(1.0, np.dot(point - a, ab) / denom))
    return float(np.linalg.norm(point - (a + t * ab)))


def _boundary_vertex_offsets(boundary, positions, nudge):
    """{vertex_id: offset_vector} -- the Z-fighting nudge _group_boundary_offset_lines/
    _frame_group_boundary_offset_lines give a group's own boundary rim, computed PER VERTEX
    (one shared owning-triangle-normal AVERAGE across every boundary edge that touches it) --
    NOT per edge, each along its own single owning triangle's normal, the way an earlier
    version of both callers did (2026-09-29, explicit bug report: "when zoomed in close, the
    thick polygon outlines are drawn twice and a bit broken" -- two boundary edges meeting at
    a shared vertex can easily have DIFFERENT owning triangles with genuinely different
    normals, especially where the subdivided surface curves -- nudging each edge independently
    along its own triangle's normal pushed the two edges' endpoints AT THAT SAME VERTEX in
    slightly different directions, so they no longer landed on the same point -- a visible gap
    right at the joint, worse the more the surface curves there, plus the two nudged copies
    (front/back) reading as genuinely doubled instead of a single crisp line wherever that gap
    was wide enough to resolve at all when zoomed in). Every edge sharing a vertex now nudges
    that vertex by the exact same amount, in the exact same direction, so they still meet
    exactly -- `boundary`: [((u, v), (ta, tb, tc)), ...] (_group_boundary_owners' own return
    shape); `positions`: {vertex_id: np.ndarray(3,)}."""
    vertex_normals = {}
    for (u, v), (ta, tb, tc) in boundary:
        pa, pb, pc = positions[ta], positions[tb], positions[tc]
        normal = np.cross(pb - pa, pc - pa)
        length = np.linalg.norm(normal)
        if length <= 1e-12:
            continue
        unit = normal / length
        vertex_normals.setdefault(u, []).append(unit)
        vertex_normals.setdefault(v, []).append(unit)
    offsets = {}
    for vertex_id, normals in vertex_normals.items():
        avg = np.mean(normals, axis=0)
        avg_length = np.linalg.norm(avg)
        offsets[vertex_id] = (avg / avg_length * nudge) if avg_length > 1e-12 else np.zeros(3)
    return offsets


# The FINE subdivision mesh's own wireframe -- much fainter than the bold polygon-outline
# overlay (RIM_COLOR, see _group_boundary_offset_lines) it sits underneath, and thinner too.
# Separate front/back
# weights (2026-09-19, explicit: first "for the front faces, use 85/15... for the back faces,
# use 95/5", then "make backside lines 85/15 as well", then "backside lines should be 85%
# backside face color and 15% white", then "try back_edge_weight=0.9") -- FRONT_EDGE_WEIGHT
# blends the outward-facing `color` against white; BACK_EDGE_WEIGHT blends the actor's OWN
# (already-darkened) inside fill color against white too (not black -- an earlier attempt
# blended toward black, reverted the same day). Two SEPARATE weights/actors (not one shared),
# because VTK ties edge color to the ACTOR, not to front/back orientation, so a single actor
# can't give front and back independent edge colors -- see _render's own two-actor culling
# setup.
FRONT_EDGE_WEIGHT = 0.85
BACK_EDGE_WEIGHT = 0.9
SUBDIVISION_EDGE_LINE_WIDTH = 0.75

# Lighting/shading for the two per-group face actors (2026-09-29, explicit user request: "add
# some lighting and shading... performant") -- SMOOTH_SHADING is the actual visual win: VTK
# interpolates PER-VERTEX normals (averaged from each vertex's own incident fine triangles)
# across every triangle instead of using one flat per-triangle normal, so a subdivided face
# reads as a smoothly curved/inflated surface instead of a faceted polyhedron made of visible
# flat triangles -- exactly what an "inflated" mesh should look like, and cheap: VTK computes
# these normals once per add_mesh call (a `vtkPolyDataNormals` pass over however many triangles
# that one group's own PolyData has, not the whole scene, not per-frame), not a rendering-time
# cost repeated every redraw. No new library needed -- this is PyVista/VTK's own existing Phong
# lighting pipeline (already active with a default 3-light kit; add_mesh's default
# smooth_shading=False was simply never overridden), not a swap to some heavier PBR/raytracing
# path. The material constants below tone the default lighting down slightly from add_mesh's
# own defaults (ambient=0.0, diffuse=1.0, specular=0.0) -- a touch of ambient keeps the shadowed
# side of a face from ever going fully black/flat, and a modest specular highlight is what
# actually SELLS the "smooth, slightly glossy inflated surface" look once combined with smooth
# shading; SPECULAR_POWER keeps that highlight small/tight rather than a big soft blob.
SMOOTH_SHADING = True
MATERIAL_AMBIENT = 0.25
MATERIAL_DIFFUSE = 0.85
MATERIAL_SPECULAR = 0.35
MATERIAL_SPECULAR_POWER = 20

# Explicit 2-light camera-relative rig, REPLACING the plotter's own default light kit
# (2026-09-29, explicit bug report: "I don't see any shading" on a mesh that converges fine --
# smooth_shading/material tuning alone weren't enough). A plain default VTK Plotter lights the
# scene with a HEADLIGHT -- a light collocated with the camera, pointed straight down the view
# axis -- which is exactly the lighting setup that looks flattest: every point on a convex
# surface facing the camera receives close to the SAME light angle relative to its own normal,
# so there's minimal brightness falloff across the visible surface regardless of how good
# smooth_shading's own normal interpolation is (a shading MODEL can't manufacture contrast a
# light rig never provides). `light_type='camera light'` positions a light in a coordinate
# space where the camera itself sits at (0, 0, 1) looking at (0, 0, 0) with up=(0, 1, 0) --
# OFFSETTING position away from (0, 0, 1) (unlike a headlight) puts the light off the view axis,
# so there's always real angular falloff across a curved surface, and VTK automatically keeps
# the light following the camera as the user rotates/pans -- no per-render recomputation needed,
# unlike a world-space light that could leave one whole side permanently unlit. KEY (bright,
# upper-right) does the actual shape-defining work; FILL (dim, opposite side) keeps the unlit
# side from going flat black without washing out the key's own contrast -- classic 2-point
# rig, cheaper than the default kit's 5 lights and deliberately more off-axis than any of them.
KEY_LIGHT_POSITION = (0.55, 0.7, 0.85)
KEY_LIGHT_INTENSITY = 1.0
FILL_LIGHT_POSITION = (-0.6, -0.35, 0.5)
FILL_LIGHT_INTENSITY = 0.35

# Debug mode's "Show face normals"/"Show vertex normals"/"Show repulsive forces" toggles
# (2026-09-29, explicit user request -- diagnosing a crumpled guest boundary after a Diff
# Inflate join) -- same colors/length convention as inflate_polyhedron_app's own identically-
# named toggles (_draw_level_panel), so a user familiar with that app reads these the same way.
NORMAL_COLOR = "yellow"
VERTEX_NORMAL_COLOR = "cyan"
REPULSION_FORCE_COLOR = "magenta"
NORMAL_LENGTH_FRACTION = 0.5


def _vertex_normals(faces, positions):
    """Same as inflate_polyhedron_app's own _vertex_normals (duplicated, not imported -- that
    app's own app.py only resolves its `from session_state import ...` when run as __main__
    with its own directory on sys.path, so it isn't safely importable as a library module from
    here). faces: triangle vertex-id loops; positions: {vertex_id: pos}. Returns
    {vertex_id: (unit_normal, mean_incident_edge_length)} for "Show vertex normals" below --
    every vertex touched by at least one non-degenerate face, `unit_normal` the normalized SUM
    of every incident face's own unit normal (equally weighted, not by area)."""
    normal_sums = {}
    edge_len_sums = {}
    edge_len_counts = {}
    for a, b, c in faces:
        pa, pb, pc = positions[a], positions[b], positions[c]
        normal = np.cross(pb - pa, pc - pa)
        normal_len = np.linalg.norm(normal)
        if normal_len < 1e-12:
            continue
        unit_normal = normal / normal_len
        for v in (a, b, c):
            normal_sums[v] = normal_sums.get(v, np.zeros(3)) + unit_normal
        for u, w in ((a, b), (b, c), (c, a)):
            length = np.linalg.norm(positions[w] - positions[u])
            for v in (u, w):
                edge_len_sums[v] = edge_len_sums.get(v, 0.0) + length
                edge_len_counts[v] = edge_len_counts.get(v, 0) + 1
    result = {}
    for v, total in normal_sums.items():
        total_len = np.linalg.norm(total)
        if total_len < 1e-12:
            continue
        result[v] = (total / total_len, edge_len_sums[v] / edge_len_counts[v])
    return result


def _is_valid_numeric_partial(proposed, allow_exponent, allow_decimal=True):
    """True if `proposed` is a full number or a prefix a user could still be typing toward one
    -- same validation idea as inflate_polyhedron_app's own _is_valid_numeric_partial
    (duplicated, not imported -- a tiny, self-contained regex check, not worth pulling in that
    whole module for)."""
    digits = r"\d*\.?\d*" if allow_decimal else r"\d*"
    pattern = f"-?{digits}(?:[eE][-+]?\\d*)?" if allow_exponent else f"-?{digits}"
    return re.fullmatch(pattern, proposed) is not None


def _open_base_edges(base_faces, face_edge_ids):
    """Returns {base_face_idx: {frozenset(rim-edge vertex pair), ...}} -- for each of
    `base_faces`' own polygons, which of ITS OWN edges have no partner elsewhere in the mesh (a
    genuine free/boundary edge) rather than being glued to some other piece. Same logic as
    inflate_polyhedron_app's own _open_base_edges (duplicated, not imported -- see module
    docstring), used here only to answer "is the central object closed" (InflaterPane's own
    _is_central_object_closed) -- an empty return means every edge is glued, i.e. closed.

    Adjacency is found via `face_edge_ids` when given (an edge id used by exactly ONE
    base_faces entry across the whole mesh is that entry's own free edge) -- same
    disambiguation rationale as mesh_levels.polygon_centroid_springs' own docstring, since two
    DIFFERENT genuine edges can coincidentally share a plain vertex-id pair. Falls back to a
    plain shared-vertex-pair match when `face_edge_ids` is None."""
    owners = {}
    if face_edge_ids is not None:
        for i, ids in enumerate(face_edge_ids):
            face = base_faces[i]
            n = len(face)
            for k, eid in enumerate(ids):
                pair = frozenset((face[k], face[(k + 1) % n]))
                owners.setdefault(eid, []).append((i, pair))
    else:
        for i, face in enumerate(base_faces):
            n = len(face)
            for k in range(n):
                pair = frozenset((face[k], face[(k + 1) % n]))
                owners.setdefault(pair, []).append((i, pair))
    open_edges = {}
    for group in owners.values():
        if len(group) == 1:
            i, pair = group[0]
            open_edges.setdefault(i, set()).add(pair)
    return open_edges


def _build_level1_topology(base_faces):
    """Level 0 and Level 1 share this exact fan-triangulated topology -- same construction as
    inflate_polyhedron_app's own _build_level1_topology (duplicated, not imported -- see module
    docstring). Calls subdivide_once with placeholder positions purely to get the resulting
    faces/edge_length/face_of_fine; the interpolated positions it also returns are meaningless
    and discarded."""
    dummy_positions = {v: np.zeros(3) for face in base_faces for v in face}
    faces, _, edge_length, face_of_fine = subdivide_once(
        base_faces, dummy_positions, EDGE_LENGTH, list(range(len(base_faces))), 0)
    return faces, edge_length, face_of_fine


def _subdivide_combined_to_level3(base_faces, face_edge_ids, seed_positions):
    """Runs the SAME fan (Level 0->1) + quarter (1->2->3) pipeline on_full_inflate_clicked/
    _on_inflate_step_done normally drive through 3 EXPENSIVE relax/calibrate passes, but as
    PURE INTERPOLATION only (no solving) -- used by InflaterPane._diff_add_face to bring a
    freshly combined (old+new) base mesh straight to Level-3 TOPOLOGY. `seed_positions` must
    already place every OLD corner (any vertex id also present in the PREVIOUS base mesh) at
    its CURRENT (already-relaxed) 3D position; interpolating from those recreates the OLD
    portion's Level-3 geometry exactly (a base vertex id persists unchanged through every
    subdivision level -- see mesh_levels.py's own docstring), so only the NEW face's own
    (freshly seeded) region actually needs the relax/calibrate pass that follows -- this is
    what lets Diff Inflate skip Levels 0-2's own solving (2026-09-19, explicit: "add that face
    directly at level 3 subdivision"). Deliberately doesn't try to preserve the OLD mesh's own
    vertex ids (subdivide_once's own numbering shifts once a face is appended -- see
    mesh_levels.py's `next_id = 1 + max(positions)` -- so this reconstructs fresh ids
    throughout instead); correctness only needs the SEED POSITIONS to be old-consistent, not
    the integer ids labeling them. Returns (faces, positions, edge_length, face_of_fine) at
    Level 3."""
    faces, positions, edge_length = base_faces, dict(seed_positions), EDGE_LENGTH
    face_of_fine = list(range(len(base_faces)))
    for level in range(MAX_LEVEL):
        faces, positions, edge_length, face_of_fine = subdivide_once(
            faces, positions, edge_length, face_of_fine, level,
            base_faces=base_faces, face_edge_ids=face_edge_ids)
    return faces, positions, edge_length, face_of_fine


def _seed_unknown_by_bfs(faces, seed, rng):
    """faces: base vertex-loop faces; seed: {vertex_id: np.ndarray(3,)}, MUTATED IN PLACE to
    add an entry for every vertex `faces` references that isn't already a key. Fills each
    missing one by BFS along mesh_edges(faces) from whatever's already known -- takes the first
    found KNOWN neighbor's position plus a small random jitter (so two vertices that used to be
    the exact same point, e.g. a just-removed connection's two newly-separated corners, don't
    start EXACTLY coincident -- a zero-length edge risks a divide-by-zero direction vector). A
    vertex with no known neighbor reachable at all (every neighbor is ALSO unknown, e.g. a
    freshly added, entirely unconnected new shape) falls back to the overall known centroid (or
    the origin if nothing is known yet), so it's at least somewhere plausible for the very
    first relax step to pull from -- used by InflaterPane._diff_reexport_and_relax for any
    single add/remove-connection or add-face diff (see BuilderPane.classify_change), not just
    the "one clearly new shape" case _diff_add_face used to special-case."""
    adjacency = {}
    for a, b in mesh_edges(faces):
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    unknown = {v for f in faces for v in f} - set(seed)
    fallback_center = np.mean(list(seed.values()), axis=0) if seed else np.zeros(3)
    while unknown:
        progressed = []
        for v in unknown:
            for neighbor in adjacency.get(v, ()):
                if neighbor in seed:
                    seed[v] = seed[neighbor] + rng.uniform(-0.05, 0.05, size=3)
                    progressed.append(v)
                    break
        if not progressed:
            # Nothing left in `unknown` is adjacent to anything known yet -- seed the rest near
            # the overall fallback center instead of looping forever.
            for v in unknown:
                seed[v] = fallback_center + rng.uniform(-0.5, 0.5, size=3)
            break
        unknown -= set(progressed)
    return seed


def _fine_vertex_local_order(faces, face_of_fine, group):
    """The raw fine vertex ids belonging to base group `group`, in FIRST-SEEN order while
    scanning `faces` (filtered to that group) in emitted order -- a purely LOCAL identity
    (2026-09-29, explicit bug report: "when I ... delete one connection, then did the replay
    of the diff inflate, I saw that the inflation started with all the faces flat, which is
    wrong because it should start from the inflated model we already have" -- traced to
    _diff_reexport_and_relax seeding only the coarse BASE (Level-0) vertices from the last
    completed inflate, then re-deriving every FINE vertex fresh via _subdivide_combined_to_
    level3's pure geometric interpolation -- which discards the old, already pressure-
    calibrated curvature for the WHOLE mesh, not just near the edit, producing flat-faceted
    polygons at the seed even for faces nowhere near the changed connection).

    subdivide_once's own fan (Level 0->1) + quarter (1->2->3) recursion is a deterministic
    function of a base face's own (n, corner-id traversal order) alone -- unaffected by which
    OTHER faces exist, their processing order, or the raw integer ids assigned (only WHICH
    vertices get created/reused, never the sequence subdividing THIS face's own triangles
    visits them in). So for a base face group whose shape/corner order is unchanged (see
    _diff_reexport_and_relax's own "matched_base_ids" check), the SAME local index here always
    names the SAME logical corner/edge-fraction/interior point in both the OLD and NEW mesh,
    even though the raw ids differ -- letting the caller copy that point's OLD, already-curved
    3D position across exactly, instead of re-interpolating it flat."""
    seen = set()
    order = []
    for tri, g in zip(faces, face_of_fine):
        if g != group:
            continue
        for v in tri:
            if v not in seen:
                seen.add(v)
                order.append(v)
    return order


def _fan_level_edges(faces, base_edges):
    """Level 0/1's own explicit spring-edge override -- same construction as
    inflate_polyhedron_app's own _fan_level_edges (duplicated, see module docstring).
    `base_edges` (from load_stretchy_mesh_edges) is None for a mesh with no explicit "edges"
    field, in which case this returns None too (mesh_edges' own vertex-pair fallback is safe)."""
    if base_edges is None:
        return None
    base_vertex_ids = {v for e in base_edges for v in e}
    spokes = [e for e in mesh_edges(faces)
              if not (e[0] in base_vertex_ids and e[1] in base_vertex_ids)]
    return list(base_edges) + spokes


def _load_mesh_from_dict(mesh_dict):
    """mesh_dict: {"name", "faces", "edges", "face_edge_ids", ...} as built by
    BuilderPane.export_mesh_dict. Returns (faces, base_edges, face_edge_ids) -- `faces` the
    vertex-loop list, `base_edges` the explicit mesh-edge list from `mesh_dict["edges"]` if
    present else None, `face_edge_ids` likewise from `mesh_dict["face_edge_ids"]` (both matching
    load_stretchy_mesh_edges's own return convention -- see its own docstring on why a mesh with
    duplicate/ambiguous edges, e.g. composite_spider_leg.poly, NEEDS face_edge_ids to subdivide
    correctly past Level 1: dropping it, as an earlier version of this function did, is what let
    such a net inflate fine in inflate_polyhedron_app but come out wrong here -- see
    _on_inflate_step_done's own subdivide_once call, which now threads this through).
    Raises ValueError if the mesh fails load_stretchy_mesh's own winding validation.

    load_stretchy_mesh/load_stretchy_mesh_edges (stretchy_mesh.py, untouchable -- see the
    net-fold-project skill) only accept a file PATH, and are this project's one authoritative
    parser+validator for this format -- reimplementing that validation a second time here would
    risk drifting from the original. Instead, this writes `mesh_dict` to a throwaway temp file,
    calls those same two functions on it, and deletes it immediately after -- the mesh is never
    written to (or read from) any file under data/, only this one transient file that never
    outlives a single call."""
    fd, path = tempfile.mkstemp(suffix=".poly", dir=str(INFLATER_APP_DIR))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(mesh_dict, f)
        faces, _name = load_stretchy_mesh(path)
        base_edges, face_edge_ids = load_stretchy_mesh_edges(path)
    finally:
        os.remove(path)
    return faces, base_edges, face_edge_ids


# ---- pendant (single-edge-attached) face exclusion (2026-09-28, explicit user request) ----
#
# "when a face is attached to the central group by only one edge, it is going to flop around
# because it's too unconstrained. that face should be excluded from the relaxation/inflation
# process completely. it should be attached to the face it's connected to after the relaxation/
# inflation is done, and it should be attached parallel to that face." A face hinged to the rest
# of the mesh along exactly one of its own edges has one whole rotational degree of freedom
# (around that hinge) the spring/pressure network does nothing to pin down -- exactly the
# "loosely-attached or floppy face" _on_relax_done/_on_inflate_step_done already warn about by
# name. Rather than solve it (unconstrained by construction, so any solved position is as
# arbitrary as any other), on_full_inflate_clicked drops it from the mesh entirely before
# relax/inflate ever runs, then _reattach_pendant_faces lays it back on, flat/coplanar
# ("parallel") against whichever face it's hinged to, once that neighbor's own final position is
# known -- a closed-form placement, not a physics step.

def _pendant_face_attachments(base_faces, face_edge_ids):
    """Returns {pendant_face_idx: (neighbor_face_idx, (a, b))} for every one of `base_faces`
    attached to the rest of the mesh by EXACTLY one glued edge -- `(a, b)` that edge's own
    vertex-id pair, in the SAME order `base_faces[pendant_face_idx]`'s own loop lists it.
    `neighbor_face_idx` is whichever OTHER base face shares that exact edge. A face with ZERO
    glued edges (not attached to anything -- nothing to exclude it against or reattach it to,
    e.g. a lone anchor with nothing placed yet) or TWO OR MORE (braced by more than one point of
    contact, not the "flops around" case this targets) is not included.

    Same owners-dict disambiguation as _open_base_edges (an edge id used by exactly one
    base_faces entry is a free edge; used by exactly two is a genuine glued edge between
    them) -- reimplemented here rather than extending that function, since this needs BOTH
    sides of a glued pair, not just which edges are free."""
    owners = {}
    if face_edge_ids is not None:
        for i, ids in enumerate(face_edge_ids):
            face = base_faces[i]
            n = len(face)
            for k, eid in enumerate(ids):
                owners.setdefault(eid, []).append((i, (face[k], face[(k + 1) % n])))
    else:
        for i, face in enumerate(base_faces):
            n = len(face)
            for k in range(n):
                pair = (face[k], face[(k + 1) % n])
                owners.setdefault(frozenset(pair), []).append((i, pair))
    glued_count = {}
    glued_partner = {}
    for group in owners.values():
        if len(group) != 2:
            continue
        (i0, pair0), (i1, pair1) = group
        glued_count[i0] = glued_count.get(i0, 0) + 1
        glued_count[i1] = glued_count.get(i1, 0) + 1
        glued_partner[i0] = (i1, pair0)
        glued_partner[i1] = (i0, pair1)
    return {i: glued_partner[i] for i, count in glued_count.items() if count == 1}


def _exclude_pendant_faces(base_faces, base_edges, face_edge_ids, source_polygon_id=None):
    """Returns (core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id,
    pendants) -- `base_faces`/`face_edge_ids`/`source_polygon_id` with every pendant
    (_pendant_face_attachments) face index dropped (all three stay index-parallel to each
    other, same as the caller's own), and `base_edges` filtered down to pairs whose BOTH
    endpoints survive (a stray reference to a now-excluded vertex would otherwise KeyError deep
    in _edge_setup's own index arrays). `pendants` is a list of {"face": <original vertex-id
    loop>, "neighbor_idx": <index into the RETURNED core_base_faces -- already remapped from
    the original list, since face_of_fine values _reattach_pendant_faces later compares against
    are themselves built from core_base_faces>, "shared_pair": (a, b)} dicts, everything
    _reattach_pendant_faces needs once the core mesh has been solved. Falls back to
    (base_faces, base_edges, face_edge_ids, source_polygon_id, []) UNCHANGED if excluding every
    detected pendant would leave nothing left to solve (e.g. the whole central object is just a
    2-face hinge, so each is the other's only neighbor -- the only way a pendant's own neighbor
    can ALSO be a pendant, since the central object is always one connected component: if that
    pair weren't the WHOLE object, whatever connects them to whatever else contains the anchor
    would itself be a second connection for at least one of them, contradicting "exactly one
    glued edge") -- an empty core mesh has nothing for relax_initial_configuration to do, so
    there's no safe way to exclude here."""
    attachments = _pendant_face_attachments(base_faces, face_edge_ids)
    if not attachments or len(attachments) >= len(base_faces):
        return base_faces, base_edges, face_edge_ids, source_polygon_id, []
    keep = [i for i in range(len(base_faces)) if i not in attachments]
    orig_to_core = {orig_i: core_i for core_i, orig_i in enumerate(keep)}
    pendants = [{"face": base_faces[i], "neighbor_idx": orig_to_core[neighbor_idx],
                 "shared_pair": pair,
                 "source_polygon_id": (source_polygon_id[i] if source_polygon_id is not None
                                        else i)}
                for i, (neighbor_idx, pair) in attachments.items()]
    core_base_faces = [base_faces[i] for i in keep]
    core_face_edge_ids = ([face_edge_ids[i] for i in keep] if face_edge_ids is not None else None)
    core_source_polygon_id = ([source_polygon_id[i] for i in keep]
                               if source_polygon_id is not None else None)
    core_vertex_ids = {v for face in core_base_faces for v in face}
    core_base_edges = (None if base_edges is None else
                        [e for e in base_edges if e[0] in core_vertex_ids and e[1] in core_vertex_ids])
    return core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id, pendants


def _regular_polygon_rest_positions(face, edge_length):
    """{vertex_id: np.array([x, y, 0.0])} for `face`'s own n corners, laid out as a REGULAR
    n-gon of side length `edge_length` in the z=0 plane -- vertex k (in `face`'s own listed,
    CCW order) at angle 2*pi*k/n, radius edge_length/(2*sin(pi/n)) (the standard circumradius
    that makes every EDGE exactly `edge_length` long, not just every vertex equidistant from
    the center). The canonical REST frame _flat_pendant_fine_mesh/_place_pendant_flat build on."""
    n = len(face)
    radius = edge_length / (2 * math.sin(math.pi / n))
    return {v: np.array([radius * math.cos(2 * math.pi * k / n),
                          radius * math.sin(2 * math.pi * k / n), 0.0])
            for k, v in enumerate(face)}


def _flat_pendant_fine_mesh(pendant_face, edge_length):
    """Returns (faces_lvl3, positions_lvl3) -- `pendant_face` alone, fan-triangulated then
    quartered twice (subdivide_once, level 0->1->2) up to Level 3, EXACTLY as a real Full
    Inflate pipeline would, but starting from _regular_polygon_rest_positions instead of a
    random Level-0 start and with NO relax/calibration call in between: every one of
    subdivide_once's own position updates is pure linear interpolation (a new vertex is a
    corner mean or an edge midpoint of whatever's already there -- see mesh_levels.py's own
    _fan_level_0_to_1/_quarter_triangles), which keeps an already-flat (z=0) input exactly flat
    the whole way through. `faces_lvl3`/`positions_lvl3` still use `pendant_face`'s OWN vertex
    ids for its 3 corners plus freshly local-to-this-call ids (from
    `next_id = 1 + max(positions)`, mesh_levels.py's own convention) for every hub/midpoint --
    the caller (_exclude_pendant_faces' own pendant reattachment) is responsible for remapping
    those local ids into the real mesh's own global vertex-id space before merging anything in,
    since they're only guaranteed unique within this one call."""
    positions = _regular_polygon_rest_positions(pendant_face, edge_length)
    faces, positions, edge_len, face_of_fine = subdivide_once(
        [pendant_face], positions, edge_length, [0], 0)
    for level in (1, 2):
        faces, positions, edge_len, face_of_fine = subdivide_once(
            faces, positions, edge_len, face_of_fine, level)
    return faces, positions


def _fine_group_boundary_edges(faces, face_of_fine, group):
    """{(u, v) sorted, ...} for every boundary edge of `group` within `faces`/`face_of_fine` --
    a free function twin of InflaterPane._group_boundary_edge_set (same counting rule: a
    spoke/internal-to-the-fan edge is shared by two triangles of the SAME group and cancels
    out; only a true rim edge, whose other triangle is in a different group (or doesn't exist
    at all), survives) -- needed here because _place_pendant_flat runs before any InflaterPane
    group state exists for a pendant's own new group."""
    edge_count = {}
    for face, bf in zip(faces, face_of_fine):
        if bf != group:
            continue
        a, b, c = face
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            edge_count[key] = edge_count.get(key, 0) + 1
    return {e for e, count in edge_count.items() if count == 1}


def _rim_vertex_chain(u, v, boundary_edges, original_corners):
    """Ordered fine-mesh vertex ids from `u` to `v` along one rim (walking `boundary_edges`,
    stopping at `v` or any other of `original_corners`) -- a free function twin of
    InflaterPane._base_edge_vertex_chain (see its own docstring for the full walk rationale:
    `u` has exactly two neighbors within a closed rim loop, one toward `v` via this one edge,
    the other around the rest of the polygon, and the two can't be told apart by which reaches
    `v` sooner). Falls back to the plain `[u, v]` pair if neither direction ever reaches `v`."""
    neighbors = {}
    for a, b in boundary_edges:
        neighbors.setdefault(a, []).append(b)
        neighbors.setdefault(b, []).append(a)
    for first_step in neighbors.get(u, []):
        chain = [u, first_step]
        prev, cur = u, first_step
        while cur != v and cur not in original_corners:
            options = [n for n in neighbors.get(cur, []) if n != prev]
            if not options:
                break
            prev, cur = cur, options[0]
            chain.append(cur)
        if cur == v:
            return chain
    return [u, v]


def _place_pendant_flat(pendant, final_positions_by_id, neighbor_face_idx, level3_face_of_fine,
                         level3_faces, edge_length, next_free_id, neighbor_base_face):
    """Computes final 3D positions for one excluded pendant's ENTIRE Level-3 fine mesh, laid
    out flat/coplanar ("parallel") against whichever face it's hinged to, once that neighbor's
    own final positions are known -- see this section's own header comment for why this is a
    closed-form placement, not another relax pass. Returns (faces, positions, next_free_id,
    remapped_face) -- `faces`/`positions` already in the REAL mesh's global vertex-id space
    (remapped from _flat_pendant_fine_mesh's own local ids, `next_free_id` the next unused one
    after this call), ready to concatenate straight onto the core's own self.faces/
    self.positions/self.face_of_fine (face_of_fine value: neighbor_face_idx -- see this
    function's own caller). `remapped_face` is `pendant["face"]` (the ORIGINAL, base-export-
    level corner loop) passed through this SAME id_map -- needed because a third+ corner (see
    its own comment below) no longer keeps its raw id, so it's the only correct record of what
    this pendant's own corners are actually CALLED in the mesh just built (the caller uses it
    for its own self.base_faces entry -- self.base_faces[group] must list ids that genuinely
    exist in self.positions, not stale pre-remap ones, or _rebuild_open_edges/
    _base_edge_vertex_chain silently walk from a vertex id that was never actually placed,
    2026-09-29, explicit bug report: "highlighted a non-edge that connects a vertex to the
    centre of an opposite face" -- _base_edge_vertex_chain's own "never found a path" fallback,
    a straight [u, v] chord, dead code until then).

    The pendant's own SHARED edge's intermediate (subdivision-created) vertices are PINNED to
    the core's own EXISTING ones for that same edge -- same id, same (already-solved) position,
    never independently recomputed -- not just the two endpoints `shared_pair` already reused
    (2026-09-29, explicit bug report: "not able to select any of the edges of the guest
    piece... some non-edges are highlighted when hovered over" -- _flat_pendant_fine_mesh builds
    the pendant's own fine mesh as a totally SEPARATE subdivide_once run, with no way to know
    the core's own existing midpoint ids for that same physical edge, so every earlier version
    independently re-synthesized fresh ones instead -- two DIFFERENT vertex ids at the same
    physical location, which `_group_boundary_edge_set`'s own by-id matching (everything reading
    a "shared seam" ultimately goes through it) could never recognize as the same edge at all).
    `neighbor_base_face` (`self.base_faces[neighbor_face_idx]`) bounds the walk that finds the
    core's own existing chain (see _rim_vertex_chain's own docstring for why that bound is
    needed at all). Also more accurate than the old recompute: a rim edge of an already-solved,
    possibly-curved neighbor isn't necessarily straight, so reusing its own real intermediate
    positions (rather than a pendant-side straight-line guess between the two endpoints) avoids
    a hairline gap/crease at the seam.

    The neighbor's own plane/normal is estimated from the MEAN of only the fine triangles
    actually touching the SHARED EDGE's own two endpoints (a local fan around the attachment
    point), not its whole fine mesh -- a neighbor face can be meaningfully curved once it's a
    real solved part of a multi-face core (unlike a lone flat "place", pressure genuinely bends
    it), and when several pendants hang off DIFFERENT edges of the SAME curved neighbor, a
    single face-wide average plane is a poor stand-in for any one of their own local tangent
    planes -- each pendant would flatten against the same blurred "average" direction instead
    of its own edge's actual local orientation, landing them overlapping/crossing each other
    instead of fanning out with the neighbor's real curvature (2026-09-28, explicit bug report:
    a pentagon core with 3 pendants on 3 different edges came out visibly tangled -- caught by
    restricting this to the local neighborhood and comparing). Falls back to the WHOLE
    neighbor's own fine mesh only if the local fan is somehow empty (shouldn't happen: `a`/`b`
    are always real neighbor vertices). The OUTWARD side (which half-plane, split by the shared
    edge, the pendant extends into) is whichever side is AWAY from this SAME local centroid, so
    the flap extends past the shared edge rather than folding back on top of the piece it's
    hinged to."""
    a, b = pendant["shared_pair"]
    p0, p1 = final_positions_by_id[a], final_positions_by_id[b]
    all_neighbor_tri_idx = [i for i, bf in enumerate(level3_face_of_fine) if bf == neighbor_face_idx]
    local_tri_idx = [i for i in all_neighbor_tri_idx if a in level3_faces[i] or b in level3_faces[i]]
    neighbor_tri_idx = local_tri_idx or all_neighbor_tri_idx
    neighbor_vertex_ids = {v for i in neighbor_tri_idx for v in level3_faces[i]}
    neighbor_normal = np.zeros(3)
    for i in neighbor_tri_idx:
        va, vb, vc = (final_positions_by_id[v] for v in level3_faces[i])
        n = np.cross(vb - va, vc - va)
        norm = np.linalg.norm(n)
        if norm > 1e-9:
            neighbor_normal += n / norm
    plane_normal = neighbor_normal / max(np.linalg.norm(neighbor_normal), 1e-9)
    neighbor_centroid = np.mean([final_positions_by_id[v] for v in neighbor_vertex_ids], axis=0)

    edge_dir = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-9)
    in_plane_perp = np.cross(plane_normal, edge_dir)
    in_plane_perp /= max(np.linalg.norm(in_plane_perp), 1e-9)
    edge_mid = (p0 + p1) / 2
    if np.dot(neighbor_centroid - edge_mid, in_plane_perp) > 0:
        in_plane_perp = -in_plane_perp  # flip so it points AWAY from the neighbor, not into it
    actual_length = np.linalg.norm(p1 - p0)
    scale = actual_length / edge_length

    local_faces, local_positions = _flat_pendant_fine_mesh(pendant["face"], edge_length)
    rest_p0, rest_p1 = local_positions[a], local_positions[b]
    rest_edge_dir = (rest_p1 - rest_p0)[:2] / edge_length  # unit, since |rest_p1-rest_p0|==edge_length
    # [-y, x] for (x, y) = cross([0, 0, 1], (rest_edge_dir, 0))[:2] -- [0,0,1] being the REST
    # frame's own fixed normal (`pendant["face"]`'s vertex k sits at angle 2*pi*k/n, INCREASING
    # with k, i.e. CCW as seen from +z, by construction -- see _regular_polygon_rest_positions).
    # Deliberately NOT independently sign-flipped by some rest-side "away from centroid" test:
    # using this SAME cross-product FORM on both this side and in_plane_perp's own (rest normal
    # here, plane_normal there) is what makes the rest->target mapping a pure rotation+scale,
    # never a reflection -- a separate flip on EACH side (an earlier version of this function
    # had one here too) can disagree about which way is "outward" and land the pendant
    # MIRRORED, folded back onto the neighbor instead of extending past it (caught by direct
    # numeric testing: a symmetric pendant landed exactly on top of the core's own opposite
    # corner instead of on the far side of the shared edge). The single "which of the two
    # coplanar sides" decision belongs ENTIRELY to in_plane_perp's own flip above, since that's
    # the only side with real information (the neighbor's actual position) to decide it from.
    rest_outward = np.array([-rest_edge_dir[1], rest_edge_dir[0]])

    # The core's own EXISTING chain of vertex ids from a to b along the neighbor's rim, and the
    # pendant's own ANALOGOUS chain along its own (separately-subdivided) rim -- see this
    # function's own docstring for why these get PINNED together below instead of the pendant's
    # own chain getting fresh ids/recomputed positions like everything else. Same subdivision
    # scheme (fan then quarter to the same MAX_LEVEL) on both sides always produces the same
    # NUMBER of intermediate points for one original edge regardless of curvature -- the `len`
    # guard is just defensive (never actually expected to differ).
    core_boundary = _fine_group_boundary_edges(level3_faces, level3_face_of_fine, neighbor_face_idx)
    core_chain = _rim_vertex_chain(a, b, core_boundary, set(neighbor_base_face))
    pendant_boundary = _fine_group_boundary_edges(local_faces, [0] * len(local_faces), 0)
    pendant_chain = _rim_vertex_chain(a, b, pendant_boundary, set(pendant["face"]))
    shared_chain_map = (dict(zip(pendant_chain, core_chain))
                         if len(pendant_chain) == len(core_chain) else {})

    # Every corner except the two literally SHARED with the neighbor (a, b, already real
    # global ids) gets a FRESH id here -- including a pendant's own THIRD+ original corner
    # (n > 3, e.g. every pentagon), not just _flat_pendant_fine_mesh's own genuinely-new
    # subdivision vertices. An earlier version kept a third+ corner's own original (base-
    # export-level) id as-is, on the theory that it was already a real, reserved global id --
    # but that id space belongs to the WHOLE original net export, while the CORE's own Level-3
    # fine mesh numbers its subdivision-created vertices independently (starting fresh from
    # its own "1 + max" at build time, with no idea some small integer is "reserved" by a
    # pendant not even part of its own solve) -- the two can and do collide on an unrelated
    # vertex (2026-09-29, explicit bug report: "spiky artifacts" persisting through
    # re-inflate/rotation -- traced to exactly this: a core face's own fine-mesh vertex
    # silently got its position overwritten by an unrelated pendant corner that happened to
    # reuse the same numeric id, stretching that core triangle into a giant sliver). Exactly
    # the same bug _diff_attach_pendant_only's own docstring already documents and fixes for
    # its own separate code path ("a just-added pendant's own free corner silently overwrote
    # an existing Level-3 midpoint that happened to share its raw id") -- this path just never
    # got the same fix.
    id_map = {a: a, b: b}
    faces_out = []
    positions_out = {a: p0, b: p1}
    for v in local_positions:
        if v in id_map:
            continue
        if v in shared_chain_map:
            id_map[v] = shared_chain_map[v]
        else:
            id_map[v] = next_free_id
            next_free_id += 1
    for v, local_pos in local_positions.items():
        if v in (a, b) or v in shared_chain_map:
            continue
        rel = local_pos[:2] - rest_p0[:2]
        along = np.dot(rel, rest_edge_dir)
        perp = np.dot(rel, rest_outward)
        positions_out[id_map[v]] = p0 + edge_dir * along * scale + in_plane_perp * perp * scale
    for local_v, core_v in shared_chain_map.items():
        positions_out[core_v] = final_positions_by_id[core_v]
    for face in local_faces:
        faces_out.append([id_map[v] for v in face])
    # The pendant's own ORIGINAL corner loop (pendant["face"]), remapped through id_map --
    # since a THIRD+ corner (above) no longer keeps its own raw id, this is the ONLY correct
    # way to know what its corners are actually CALLED in the output mesh (positions_out/
    # faces_out) -- see this function's own caller for why that distinction matters.
    remapped_face = [id_map[v] for v in pendant["face"]]
    return faces_out, positions_out, next_free_id, remapped_face


def _reattach_pendant_faces(pendants, faces, positions, face_of_fine, edge_length, own_groups,
                             core_base_faces):
    """Runs _place_pendant_flat for every excluded pendant against the just-solved CORE mesh's
    own final faces/positions/face_of_fine, and returns (faces, positions, face_of_fine) with
    every pendant's own flat Level-3 fine mesh concatenated on -- `face_of_fine` entries for a
    pendant's own fine triangles are `own_groups`' own matching entry (parallel to `pendants`,
    the caller's OWN reserved trailing self.base_faces/self._pending_source_polygon_id index
    for that one pendant -- 2026-09-29, explicit bug report: "not able to select the guest
    piece [in 3D]... only selectable together with the insider it's connected to... not able
    to select any of the edges of the guest piece" -- an EARLIER version tagged a pendant's own
    triangles with its `neighbor_idx` instead, folding it into the SAME pick/hover/rim group as
    the real neighbor it's attached to: clicking anywhere on either one always resolved to the
    neighbor's own shape id (self._pending_source_polygon_id has no entry for the pendant's own
    id at all), and the boundary edge shared between them canceled out INSIDE that one merged
    group instead of surviving as a rim (_group_boundary_edge_set counts an edge shared by TWO
    triangles of the SAME group as interior, not a rim -- see its own docstring), so no seam
    ever showed between a guest and its neighbor either. Giving the pendant its own group fixes
    both: it's now its own independently pickable/hoverable actor, with a real rim of its own,
    without changing `_place_pendant_flat`'s own geometry at all (`neighbor_face_idx`, read from
    `pendant["neighbor_idx"]` below, is still what its PLACEMENT is computed against -- only the
    OUTPUT tag changes). No-op (returns the inputs unchanged) if `pendants` is empty.

    Every `_place_pendant_flat` call below reads `neighbor_face_idx`'s own plane/normal from
    `core_faces`/`core_face_of_fine` -- a FIXED snapshot taken once, before this loop appends
    anything -- never from the growing `faces`/`face_of_fine` themselves (2026-09-28, explicit
    bug report: "a pentagon anchor with 2+ guests hinged on ADJACENT edges of it came out
    tangled"). Two pendants hinged on the SAME neighbor face share that neighbor's own
    `neighbor_idx` value; once pendant #1 is appended, its own flat triangles are tagged with
    that SAME `neighbor_idx` too (previous paragraph) -- reading the growing lists for pendant
    #2's own neighbor-plane lookup would then also sweep up pendant #1's own already-placed
    (flat, differently-oriented) triangles as if they were more of the neighbor's real curved
    surface, corrupting pendant #2's placement whenever it happens to share a corner vertex with
    pendant #1 (caught by direct testing: `_place_pendant_flat`'s own `local_tri_idx` filter,
    which restricts to triangles touching the pendant's shared-edge vertices, isn't enough to
    exclude this -- a shared CORNER vertex between two adjacent pendants means some of pendant
    #1's own triangles pass that filter for pendant #2 too). Every pendant is independently
    flat/coplanar against the neighbor's own TRUE (already fully solved) surface regardless of
    how many other pendants also hang off it, so this snapshot is always correct, never stale.

    `core_base_faces` (the CORE's own self.base_faces, one entry per `core_face_of_fine` value)
    is threaded straight through to `_place_pendant_flat` as each pendant's own
    `neighbor_base_face` -- see its own docstring for why.

    Also returns `remapped_base_faces` (parallel to `pendants`) -- each pendant's own
    `remapped_face` from `_place_pendant_flat` (see its own docstring), for the caller to use
    as that pendant's OWN self.base_faces entry instead of its raw, pre-remap `pendant["face"]`
    (2026-09-29, explicit bug report: "highlighted a non-edge that connects a vertex to the
    centre of an opposite face" -- self.base_faces[group] listing an id that was never actually
    placed sent _base_edge_vertex_chain's own rim walk nowhere, falling back to a straight
    chord across the polygon)."""
    if not pendants:
        return faces, positions, face_of_fine, []
    core_faces = list(faces)
    core_face_of_fine = list(face_of_fine)
    faces = list(faces)
    face_of_fine = list(face_of_fine)
    # NOT just `1 + max(positions)` -- `positions` only has the CORE's own vertex ids at this
    # point, but every pendant's own ORIGINAL corners (real, already-reserved ids from the
    # whole original net, just not present in the core-only solve) can be numerically LOWER
    # than that max while still being live ids _place_pendant_flat needs to keep as-is -- a
    # "fresh" id counter that only looked at the core would collide with one of those (a real
    # bug, caught by direct numeric testing: a pendant's own un-transformed corner silently got
    # overwritten by a same-numbered subdivision vertex). Every pendant's own face is included
    # in this max too, so the count starts safely above every id that could ever appear here.
    next_free_id = 1 + max([*positions, *(v for p in pendants for v in p["face"])])
    remapped_base_faces = []
    for pendant, own_group in zip(pendants, own_groups):
        pendant_faces, pendant_positions, next_free_id, remapped_face = _place_pendant_flat(
            pendant, positions, pendant["neighbor_idx"], core_face_of_fine, core_faces,
            edge_length, next_free_id, core_base_faces[pendant["neighbor_idx"]])
        faces.extend(pendant_faces)
        face_of_fine.extend([own_group] * len(pendant_faces))
        positions.update(pendant_positions)
        remapped_base_faces.append(remapped_face)
    return faces, positions, face_of_fine, remapped_base_faces


def _pendant_own_face_edge_ids(pendant, base_faces, base_face_edge_ids, next_id):
    """Returns (row, next_id) -- `pendant["face"]`'s own face_edge_ids row (parallel to its
    vertex loop, same convention as interactive_builder_app._face_edge_ids_from_shapes), for
    appending alongside its own trailing self.base_faces entry (2026-09-29, explicit bug
    report: appending a pendant to self.base_faces -- see _reattach_pendant_faces' own
    docstring for why -- without a matching self.base_face_edge_ids row left that list one
    entry SHORTER than self.base_faces, raising IndexError the next time _diff_remove_face
    indexed it). `None` if `base_face_edge_ids` itself is None (this mesh has no disambiguation
    data at all -- every OTHER reader already treats that as "fall back to plain vertex-pair
    matching," so there's nothing to extend). The pendant's own SHARED edge reuses whatever id
    the neighbor's own row already has for that exact edge, so the two still correctly count as
    ONE glued connection (see _pendant_face_attachments' own owners-dict docstring) rather than
    two independent free edges that merely happen to share a vertex pair; every other edge of
    the pendant gets a fresh id, `next_id` and up (guaranteed not to collide with anything --
    the caller seeds `next_id` past every id already in use)."""
    if base_face_edge_ids is None:
        return None, next_id
    a, b = pendant["shared_pair"]
    neighbor_face = base_faces[pendant["neighbor_idx"]]
    neighbor_ids = base_face_edge_ids[pendant["neighbor_idx"]]
    n = len(neighbor_face)
    shared_id = next(
        (neighbor_ids[k] for k in range(n)
         if {neighbor_face[k], neighbor_face[(k + 1) % n]} == {a, b}),
        None)
    face = pendant["face"]
    m = len(face)
    row = []
    for k in range(m):
        if {face[k], face[(k + 1) % m]} == {a, b}:
            row.append(shared_id)
        else:
            row.append(next_id)
            next_id += 1
    return row, next_id


def _prepare_mesh_for_inflate(base_faces, base_edges, face_edge_ids, source_polygon_id=None):
    """Returns ("solve", core_base_faces, core_base_edges, core_face_edge_ids,
    core_source_polygon_id, pendants) for the ordinary case -- exactly _exclude_pendant_faces'
    own return shape, just tagged with which mode applies -- or ("place", reference_face,
    pendants) when there's nothing worth running relax/inflate on AT ALL (2026-09-28, explicit
    user request: "when only one piece is on the canvas, it is also considered unstable... just
    place the piece flat. and if a second piece is joined to it at only one edge, then both are
    unstable... both should just be placed instead of inflated").

    "solve" needs the CORE (every ordinary pendant excluded) to have at least 2 faces -- with
    fewer than that, there's no genuine bracing left for physics to mean anything: a single
    core face has no neighbor to relax against at all. Checking `core_base_faces`' own size
    ALONE isn't enough to decide this, though -- _exclude_pendant_faces' own fallback (excluding
    every detected pendant would leave nothing, i.e. the WHOLE object is a mutual single-edge
    pair with nothing else) returns a 2-face "core" that LOOKS large enough, but whose own two
    faces are STILL only single-edge-hinged to EACH OTHER, exactly as unconstrained as a lone
    face -- so this checks _pendant_face_attachments directly first, to tell "nothing was
    excluded because nothing needed to be" (attachments empty -- a genuinely braced mesh, e.g.
    a closed net) apart from "nothing was excluded because excluding it all would leave
    nothing" (attachments covers every face -- always degenerate).

    "place" picks a fixed reference face (placed flat/centered with no neighbor to hinge
    against) and folds every OTHER face into ONE combined `pendants` list, all hinged directly
    on that SAME reference -- `_place_all_flat` lays every one of them out with no physics at
    all. A degenerate mesh can only ever have the reference plus pendants hinged DIRECTLY on
    it, never a deeper chain: a connected graph where every node but one has degree <= 1 can
    only be a star centered on that one node (any OTHER shape would need a path of length >= 2
    to reach it, which would force an intermediate node to degree >= 2, making that node's own
    -- and every node's -- "core" at least 2 faces, taking the "solve" path instead)."""
    attachments = _pendant_face_attachments(base_faces, face_edge_ids)
    if attachments and len(attachments) < len(base_faces):
        core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id, pendants = \
            _exclude_pendant_faces(base_faces, base_edges, face_edge_ids, source_polygon_id)
        if len(core_base_faces) >= 2:
            return ("solve", core_base_faces, core_base_edges, core_face_edge_ids,
                    core_source_polygon_id, pendants)
        # Excluding every ordinary pendant left a LONE core face (e.g. a 3-face straight chain,
        # A-B-C: A and C are each pendant to hub B, and B alone is left with no surviving
        # neighbor of its own) -- still degenerate; B becomes the reference below, A/C its
        # pendants (already correctly attached to core index 0, i.e. B, by
        # _exclude_pendant_faces' own neighbor_idx remapping).
        reference_face = core_base_faces[0]
        reference_spid = core_source_polygon_id[0] if core_source_polygon_id is not None else 0
        return "place", reference_face, reference_spid, pendants
    if not attachments and len(base_faces) >= 2:
        # No pendant relationship detected at all -- a genuinely braced mesh (every face has
        # either 0 glued edges, impossible for a connected multi-face object, or >= 2).
        return "solve", base_faces, base_edges, face_edge_ids, source_polygon_id, []
    # Degenerate: a lone face (attachments empty, len(base_faces) == 1), or a mutual single-edge
    # pair (attachments covers both, len(base_faces) == 2).
    reference_face = base_faces[0]
    reference_spid = source_polygon_id[0] if source_polygon_id is not None else 0
    extra_pendants = []
    if len(base_faces) == 2:
        second = base_faces[1]
        second_spid = source_polygon_id[1] if source_polygon_id is not None else 1
        shared = set(reference_face) & set(second)
        n = len(second)
        shared_pair = next((second[k], second[(k + 1) % n]) for k in range(n)
                            if {second[k], second[(k + 1) % n]} == shared)
        extra_pendants.append({"face": second, "neighbor_idx": 0, "shared_pair": shared_pair,
                                "source_polygon_id": second_spid})
    return "place", reference_face, reference_spid, extra_pendants


def _place_all_flat(reference_face, pendants, edge_length):
    """Builds a full Level-3 mesh (faces, positions, face_of_fine, base_faces,
    source_polygon_id) with NO physics at all -- 2026-09-28, explicit user request, see
    _prepare_mesh_for_inflate's own docstring for when this applies. `reference_face` is placed
    flat/centered as a fixed reference (base index 0, via _flat_pendant_fine_mesh -- the exact
    same flat construction a pendant's own fine mesh uses); every one of `pendants` (all hinged
    directly on `reference_face` -- see _prepare_mesh_for_inflate's own proof) is then flat-
    attached against it via _reattach_pendant_faces, the SAME closed-form geometry a real
    pendant uses post-solve."""
    local_faces, local_positions = _flat_pendant_fine_mesh(reference_face, edge_length)
    # Local hub/midpoint ids from _flat_pendant_fine_mesh are only guaranteed unique WITHIN
    # that one call (see its own docstring) -- remapped here to ids guaranteed safe against
    # every pendant's own real corners too, same "keep real corners, remap the rest" pattern
    # _place_pendant_flat's own id_map uses.
    all_real_ids = set(reference_face) | {v for p in pendants for v in p["face"]}
    next_id = 1 + max([*all_real_ids, *local_positions])
    id_map = {}
    for v in local_positions:
        if v in reference_face:
            id_map[v] = v
        else:
            id_map[v] = next_id
            next_id += 1
    faces = [[id_map[v] for v in face] for face in local_faces]
    positions = {id_map[v]: pos for v, pos in local_positions.items()}
    face_of_fine = [0] * len(faces)
    # own_groups: reference_face is base_faces[0], each pendant its own trailing index (1..N)
    # -- see this function's own base_faces line below, and _reattach_pendant_faces' own
    # docstring for why each pendant needs a DISTINCT tag rather than sharing its neighbor's.
    faces, positions, face_of_fine, remapped_base_faces = _reattach_pendant_faces(
        pendants, faces, positions, face_of_fine, edge_length,
        list(range(1, 1 + len(pendants))), [reference_face])
    # remapped_base_faces, NOT raw p["face"] -- see _reattach_pendant_faces' own docstring for
    # why a pendant's own THIRD+ corner no longer keeps its raw id.
    base_faces = [reference_face, *remapped_base_faces]
    return faces, positions, face_of_fine, base_faces


# "Central object" concept (2026-09-26, explicit: "if i add polygon and its not attached to
# anything, things go haywire" -- a shape/component with no connection at all into the rest of
# the net still passed export_mesh_dict's own validation (that function's docstring already
# names "disconnected net" as something a caller should handle, but nothing actually rejected
# it), so it got exported and solved as one MULTI-COMPONENT mesh -- stretchy_mesh's relax/
# pressure-calibration pipeline has no notion of "more than one rigid piece" and produces
# garbage (the reported "haywire") once positions/forces from unrelated components mix into the
# same convergence check. Fix: exactly one shape is the ANCHOR at any time
# (BuilderPane._anchor_shape_id -- 2026-09-26, explicit correction: "central" is NOT the largest
# connected component, it's whichever piece the user started from, permanently, no matter how
# large a disconnected side-blob grows) -- the "central object" is whichever connected component
# CURRENTLY CONTAINS the anchor, recomputed fresh from the live shapes/connections on every call.
# It alone is exported/inflated/shown in the 3D pane (BuilderPane.export_mesh_dict/
# root_to_vertex_id); every other shape is drawn at reduced opacity in the 2D pane instead
# (BuilderPane._draw_shape) so it's still visible to attach later. See BuilderPane's own anchor-
# lifecycle methods (_refresh_vme_state's anchor-assignment branch, _on_delete_key's/
# _plan_anchor_deletion's own anchor delete-guard/reassignment) for how the anchor itself
# moves/persists -- purely automatically now, 2026-09-29 explicit ("remove the Anchor[A]
# mode"), never user-picked.
def _shape_connected_components(shapes, connections):
    """shapes: list of shape dicts with an "id"; connections: list of connection dicts with
    "a_shape"/"b_shape". Returns a list of sets of shape ids, one per connected component
    (union-find over the connection graph -- a shape with no connection at all is its own
    singleton component)."""
    parent = {shape["id"]: shape["id"] for shape in shapes}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for conn in connections:
        a, b = find(conn["a_shape"]), find(conn["b_shape"])
        if a != b:
            parent[a] = b

    components = {}
    for shape in shapes:
        root = find(shape["id"])
        components.setdefault(root, set()).add(shape["id"])
    return list(components.values())


def _central_shape_ids(shapes, connections, anchor_shape_id):
    """The "central object" (see above) among `shapes`/`connections`: the connected component
    containing `anchor_shape_id`. Empty frozenset if `shapes` is empty or `anchor_shape_id` isn't
    (or is no longer) one of `shapes`' own ids -- callers needing a fallback (e.g. a freshly
    loaded net whose anchor hasn't been assigned yet) handle that themselves, see
    BuilderPane._refresh_vme_state."""
    for component in _shape_connected_components(shapes, connections):
        if anchor_shape_id in component:
            return frozenset(component)
    return frozenset()


def _connection_key(conn):
    """A connection's own two (shape_id, edge_index) endpoints, as a frozenset (so a<->b/b<->a
    order doesn't matter) -- BuilderPane.classify_change's own comparison key for "is this the
    SAME connection across two snapshots", hoisted out of that method (used to be a local
    nested function there) so InflaterPane._stage_kept_selection can also use it, to re-find a
    connection classify_change already identified by endpoints alone (its own `extra`) back in
    a shapes/connections snapshot (2026-09-29, explicit user request: "if there's a connection
    being deleted, then keep that connection/edge selected... if two edges are being joined,
    the two edges remain selected")."""
    return frozenset([(conn["a_shape"], conn["a_edge"]), (conn["b_shape"], conn["b_edge"])])


# ---- left pane ----

class BuilderPane(InteractiveBuilderApp):
    """interactive_builder_app's own canvas, embedded in a container frame instead of a real
    Toplevel and re-laid-out per this app's own spec: the shape palette in a TOP row, the
    Move/Join/Polygon-Fold tool strip on the LEFT (where the palette used to be), canvas filling
    the rest. Every other method (drag/select/rotate/connections/undo/flip/debug mode/Polygon
    Fold/_export_faces_and_layout) is inherited from InteractiveBuilderApp unchanged.

    `container` must tolerate the whole-WINDOW-only calls InteractiveBuilderApp.__init__ (and
    _build_menu/_update_title/_on_quit_request) make on self.root -- title()/geometry()/
    minsize()/protocol()/config(menu=...) -- none of which make sense for an embedded pane;
    see _PaneRoot below."""

    # A class attribute (not set in an __init__ override) so it's already present the moment
    # InteractiveBuilderApp.__init__ makes its own first _refresh_vme_state call, before
    # CombinedApp has had a chance to assign the real callback -- wired to
    # InflaterPane.refresh_diff_eligibility once both panes exist (see CombinedApp.__init__).
    on_change = None

    # The "central object" concept's own anchor (2026-09-26, explicit) -- which shape id the red
    # star marks; central_shape_ids() is the connected component currently containing this id.
    # None only when self.shapes is empty; _refresh_vme_state (the one call site every state-
    # changing edit funnels through, see its own docstring) keeps this assigned to SOME surviving
    # shape whenever shapes exist -- the very first shape placed on an empty canvas, or (a freshly
    # loaded net with no anchor of its own, e.g. any pre-existing .poly/.hippo file) the first
    # shape of the loaded net -- rather than hooking every individual creation site. A class
    # attribute for the same before-__init__-finishes reason as on_change above.
    _anchor_shape_id = None

    # Same idea as on_change -- a class attribute so it exists before the inherited
    # InteractiveBuilderApp.__init__ makes its own first _redraw() call. Which shape (if any)
    # InflaterPane's own hover-picking currently wants outlined in yellow on this canvas (see
    # set_hover_shape/the overridden _redraw below). Named _face_hover_shape_id, NOT
    # _hover_shape_id -- InteractiveBuilderApp already has its OWN self._hover_shape_id/
    # _hover_edge_index (the Join-mode edge-handle-proximity hover its _redraw draws a lit red
    # circle for), a completely different meaning; reusing that exact name here would silently
    # collide -- this class's own instance would still have only ONE such attribute, and OUR
    # _redraw's face-outline code would then also fire whenever the BASE class's Join-mode
    # gesture (or, deliberately, set_pending_connection below) sets ITS meaning of that name.
    _face_hover_shape_id = None

    # Reverse direction (2026-09-19, explicit: "now make the opposite true") -- which shape (if
    # any) THIS canvas's own mouse is currently over, forwarded to InflaterPane so it can
    # highlight the matching 3D group(s) too. A separate attribute from _face_hover_shape_id
    # above: that one is driven BY InflaterPane (3D->2D), this one drives IT (2D->3D) -- keeping them
    # apart means a plain mouse-move over the 3D panel can never fight one over the 2D canvas.
    _mouse_hover_shape_id = None

    # `inflater_getter` mirrors InflaterPane's own `builder_getter` -- a zero-arg callable
    # returning the current InflaterPane, wired by CombinedApp AFTER both panes exist (see
    # CombinedApp.__init__). A class attribute (not an __init__ param) for the same
    # before-both-panes-exist reason as on_change/_hover_shape_id above -- left None until then,
    # in which case the 2D->3D hover direction below is simply not forwarded.
    inflater_getter = None

    # Notified whenever this pane's own inherited debug_mode ('d' key) flips (2026-09-28,
    # explicit user request: InflaterPane's own release-vs-debug UI split reuses THIS SAME
    # toggle, rather than inventing a separate one) -- wired to InflaterPane._apply_mode_
    # visibility once both panes exist, same before-both-panes-exist reasoning as on_change.
    on_debug_mode_change = None

    def _on_toggle_debug_mode(self, _event=None):
        super()._on_toggle_debug_mode()
        if self.on_debug_mode_change is not None:
            self.on_debug_mode_change()

    # Join-mode connection hover state (2026-09-19, explicit: "in Join[J] mode, hovering over a
    # connection highlights it in yellow and the corresponding edge in 3d is also highlighted...
    # hovering over the 3d edge highlights the corresponding 2d connection") -- same 3D->2D
    # (_hover_connection_id) / 2D->3D (_mouse_hover_connection_id) split as the face-hover pair
    # above, and for the same reason (keeping the two directions from fighting each other).
    _hover_connection_id = None
    _mouse_hover_connection_id = None

    # Open-edge handle hover-reveal, mirrored with InflaterPane (2026-09-19, explicit: "if i
    # hover over an edge and it shows the midpoint circle, the corresponding edge should also
    # show its midpoint circle in 3d... conversely, when i hover over an open edge in 3d, its
    # midpoint as a unfilled white circle should show up... same thing should happen in 2d").
    # _mouse_hover_open_edge_key is THIS canvas's own reveal (2D->3D, forwarded in
    # _set_mouse_hover_open_edge -- see its own docstring for why it doesn't also call
    # self._redraw(), unlike the shape/connection pair above). _forced_hover_open_edge is
    # InflaterPane's own reveal, mirrored the OTHER way (3D->2D, set_open_edge_hover below) --
    # InteractiveBuilderApp's own _redraw has no field it reads for "reveal this ONE handle
    # regardless of cursor proximity", so the overridden _redraw draws it separately, on top,
    # the same way it already does for the yellow face/connection hover overlays.
    _mouse_hover_open_edge_key = None
    _forced_hover_open_edge = None

    def set_open_edge_hover(self, shape_id, edge_index):
        """Called by InflaterPane._set_hover_open_edge whenever ITS OWN mouse hover changes
        (3D->2D direction, or leaves it, shape_id=None). A no-op if already showing this exact
        edge (or already showing nothing, for a clear)."""
        key = None if shape_id is None else (shape_id, edge_index)
        if key == self._forced_hover_open_edge:
            return
        self._forced_hover_open_edge = key
        self._redraw()

    # Tracks the LAST self.selected_connection_id forwarded to InflaterPane -- same diff-on-
    # redraw approach as _last_forwarded_selected_ids above, and for the same reason (a dozen+
    # inherited methods mutate self.selected_connection_id directly, each already ending in its
    # own self._redraw()). Set by InflaterPane.set_selected_connection (3D->2D direction) BEFORE
    # it mutates self.selected_connection_id, so that direction's own _redraw doesn't bounce the
    # same selection right back.
    _last_forwarded_selected_connection_id = None

    def set_selected_connection(self, conn_id):
        """Called by InflaterPane._select_connection whenever a 3D click changes its own
        connection selection (2026-09-19, explicit: "clicking on the connection selects it in
        both 2d and 3d"). A no-op if `conn_id` already matches the current selection."""
        if conn_id == self.selected_connection_id:
            return
        self.selected_connection_id = conn_id
        self._last_forwarded_selected_connection_id = conn_id
        self._redraw()

    def set_hover_connection(self, conn_id):
        """Called by InflaterPane._set_hover_connection whenever the mouse moves over a
        different connection's seam in the 3D panel (Join mode only, or leaves it, conn_id=
        None). A no-op if `conn_id` is already the current hover."""
        if conn_id == self._hover_connection_id:
            return
        self._hover_connection_id = conn_id
        self._redraw()

    # Tracks the LAST (pending, hover_shape, hover_edge) tuple this pane forwarded to
    # InflaterPane FROM a genuine 2D click-click Join gesture -- same diff-on-redraw approach as
    # _last_forwarded_selected_ids, and for the same reason (self._connection_pending/
    # _hover_shape_id/_hover_edge_index are all mutated directly by several inherited methods,
    # each already ending in its own self._redraw()). Set by set_pending_connection (3D->2D
    # direction) BEFORE it mutates those same three fields, so that direction's own _redraw
    # doesn't bounce the same state right back out to InflaterPane.
    _last_forwarded_pending = (None, None, None)

    def set_pending_connection(self, from_shape, from_edge, to_shape, to_edge):
        """Called by InflaterPane while its own 3D drag-to-connect gesture is active (2026-09-19,
        explicit: "as i'm dragging out that connection [in 3d], the corresponding circle should
        also show in 2d... when that connection reaches another circle, the corresponding circle
        should also show in 2d"). Drives the SAME self._connection_pending/_hover_shape_id/
        _hover_edge_index fields InteractiveBuilderApp's own 2D click-click Join gesture uses
        (untouched, in the untouchable base class) -- its EXISTING _redraw already draws a lit
        red handle circle for `_connection_pending`'s own origin and for
        (_hover_shape_id, _hover_edge_index)'s target, plus the dashed preview line to
        self._pending_cursor_screen, so nothing new needs drawing here at all. `from_shape=None`
        clears everything (the drag ended, with or without a connection actually made).
        `to_shape=None` (with `from_shape` set) means the drag has an origin but no target
        under the cursor yet."""
        pending = None if from_shape is None else (from_shape, from_edge)
        current_pending = (None if self._connection_pending is None else
                            (self._connection_pending["from_shape"], self._connection_pending["from_edge"]))
        if (pending, to_shape, to_edge) == (current_pending, self._hover_shape_id, self._hover_edge_index):
            return
        self._connection_pending = None if pending is None else {"from_shape": pending[0], "from_edge": pending[1]}
        self._hover_shape_id = to_shape
        self._hover_edge_index = to_edge
        self._last_forwarded_pending = (pending, to_shape, to_edge)
        anchor_shape_id, anchor_edge = (to_shape, to_edge) if to_shape is not None else (from_shape, from_edge)
        if anchor_shape_id is not None:
            anchor_shape = self._shape_by_id(anchor_shape_id)
            if anchor_shape is not None:
                self._pending_cursor_screen = self._world_to_screen(
                    *self._shape_edge_midpoints(anchor_shape)[anchor_edge])
        self._redraw()

    def create_connection(self, a_shape_id, a_edge, b_shape_id, b_edge):
        """Creates a real connection exactly the way completing a 2D click-click Join gesture
        does (InteractiveBuilderApp._complete_or_cancel_pending_connection's own made-connection
        branch, untouchable -- replicated here rather than factored out into that file) -- used
        by InflaterPane's own 3D drag-to-connect gesture (2026-09-19, explicit: "creating
        connections in 3d... drag to connect to another edge midpoint"). A no-op (False) while
        locked (mirrors _on_canvas_press_join's own lock check for the 2D gesture) or if either
        shape has since been deleted.

        Returns True on success, False if the connection would be ILLEGAL (a vertex-merge
        conflict) -- automatically UNDONE via _undo_illegal_connection rather than leaving the
        invalid net in place with just a warning (2026-09-19, explicit bug report: "when i try
        to make an illegal join, the app does warn me... but it should then undo the illegal
        move in both 2d and 3d") -- the caller (InflaterPane._finish_connection_drag) reads
        this to decide whether to show its own "connection made" indicator at all."""
        if self._locked:
            return False
        a_shape, b_shape = self._shape_by_id(a_shape_id), self._shape_by_id(b_shape_id)
        if a_shape is None or b_shape is None:
            return False
        if self._is_orphan_to_orphan_join(a_shape_id, b_shape_id):
            self._show_orphan_join_error()
            return False
        self._push_undo()
        was_vme_active = self._vme_active  # _push_undo's own _refresh_vme_state just set this
        a_handle, b_handle = self._default_connection_handles(a_shape, a_edge, b_shape, b_edge)
        self.connections.append({
            "id": self._next_connection_id,
            "a_shape": a_shape_id, "a_edge": a_edge,
            "b_shape": b_shape_id, "b_edge": b_edge,
            "a_handle": a_handle, "b_handle": b_handle,
        })
        self._next_connection_id += 1
        self.selected_ids = set()
        self.selected_connection_id = None
        self._refresh_vme_state()
        if self._vme_active and not was_vme_active:
            self._undo_illegal_connection()
            return False
        self._redraw()
        return True

    def _is_orphan_to_orphan_join(self, a_shape_id, b_shape_id):
        """True iff `a_shape_id`/`b_shape_id` are two DIFFERENT shapes, NEITHER of which is
        currently part of the live central object (2026-09-26, explicit: "it's permitted for
        there to be more than one unconnected piece, BUT they cannot be connected to one
        another. they can only be connected to the main group"). A Polygon Fold connection
        (`a_shape_id == b_shape_id`, folding one shape onto itself) is never affected -- it can't
        change which PIECES are connected to which at all, so it's excluded outright rather than
        risk a same-shape false positive (a non-central shape folding onto itself would otherwise
        look like "both endpoints are the same non-central piece")."""
        if a_shape_id == b_shape_id:
            return False
        central_ids = self.central_shape_ids()
        return a_shape_id not in central_ids and b_shape_id not in central_ids

    def _show_orphan_join_error(self):
        messagebox.showerror(
            "Cannot connect two disconnected pieces",
            "Neither of these pieces is connected to the central object yet -- a piece that "
            "isn't connected to the central object can only be joined TO the central object, "
            "not to another disconnected piece.")

    def _undo_illegal_connection(self):
        """Rolls back a just-made connection that turned the net invalid -- pops the SAME
        undo-stack entry the caller's own _push_undo just recorded (the pre-connection state)
        and restores it directly, rather than going through on_undo_key (which would also push
        a REDO entry for something the user never asked to undo). Also tells InflaterPane to
        tear down whatever it may have already shown for this now-undone connection (2026-09-19,
        explicit bug report: "it should then undo the illegal move in both 2d and 3d. redraw if
        needed") -- covers the 2D-driven path (set_pending_connection_from_builder's own red
        highlights, still showing at the moment of rollback); the 3D-native drag path instead
        reads create_connection's own False return to skip ever creating its "made" indicator
        in the first place (see InflaterPane._finish_connection_drag)."""
        if self._undo_stack:
            self._restore_snapshot(self._undo_stack.pop())
        self.selected_ids = set()
        self.selected_connection_id = None
        self._connection_pending = None
        self._hover_shape_id = None
        self._hover_edge_index = None
        self._update_title()
        self._refresh_vme_state()
        self._redraw()
        if self.inflater_getter is not None:
            self.inflater_getter().undo_illegal_connection_from_builder()

    # Tracks the LAST selection (self.selected_ids, inherited from InteractiveBuilderApp) this
    # pane forwarded to InflaterPane -- self.selected_ids itself is mutated directly by a dozen+
    # inherited methods (click/ctrl-click/marquee/Delete/undo/redo/load/copy-paste), each already
    # ending in its own self._redraw() call (see module docstring's "one call site EVERY state-
    # changing edit... calls" note on _refresh_vme_state for the same pattern with on_change) --
    # rather than hook every one of them, the overridden _redraw below just diffs against this
    # every time and forwards only on an actual change. Set by InflaterPane.set_selected_shape_ids
    # (3D->2D direction) BEFORE it mutates self.selected_ids, so that direction's own _redraw
    # doesn't immediately bounce the same selection right back.
    _last_forwarded_selected_ids = frozenset()

    def set_selected_shape_ids(self, shape_ids):
        """Called by InflaterPane._select_shape_ids whenever a 3D click changes its own
        selection (2026-09-19, explicit: "clicking on a face in 3d should select it in both
        views"). A no-op if `shape_ids` already matches the current selection."""
        shape_ids = frozenset(shape_ids)
        if shape_ids == frozenset(self.selected_ids):
            return
        self.selected_ids = set(shape_ids)
        self._last_forwarded_selected_ids = shape_ids
        self._redraw()

    def set_hover_shape(self, shape_id):
        """Called by InflaterPane._set_hover_group whenever the mouse moves over a different
        face of the 3D panel (or leaves it, shape_id=None) -- 2026-09-19, explicit: "that face
        should be outlined in yellow in both the 2d view and the 3d view". A no-op if
        `shape_id` is already the current hover, matching InflaterPane's own such-events-aren't-
        worth-a-redraw guard."""
        if shape_id == self._face_hover_shape_id:
            return
        self._face_hover_shape_id = shape_id
        self._redraw()

    def _on_canvas_motion(self, event):
        """Runs InteractiveBuilderApp's own motion handling unchanged, then (2026-09-19,
        explicit: "now make the opposite true", mirroring InflaterPane's own 3D->2D
        _on_panel_hover_motion) picks whichever shape/connection/open-edge-handle is under the
        cursor and forwards it to InflaterPane so it highlights the matching 3D geometry too.
        Edit mode (idle, i.e. no palette shape armed and no NEW pending connection being dragged
        out) picks WHICHEVER of an open edge's own handle, an existing connection line, or a
        whole shape body is under the cursor -- same priority order _on_canvas_press_edit uses
        to decide what a CLICK there would hit (handle first, since a handle's hit area can sit
        right on top of a shape's own edge; then a connection line; only a shape body falling
        through to the last -- these three are mutually exclusive per pixel by construction, so
        exactly one (or none) ever lights up) -- since Edit mode merged what used to be separate
        Move-only (shape hover) and Join-only (connection/open-edge hover) behavior into one mode
        (2026-09-29, explicit: "combine Move mode with Join mode to make Edit[E] mode"). While a
        palette shape is armed, or a new connection is actively being dragged out, none of these
        hovers apply, so all three are cleared -- same as the old Move-mid-arm/Join-mid-drag
        exclusions. The open-edge pick reuses InteractiveBuilderApp's own
        _hit_test_any_edge_handle with no exclude/require args -- EXACTLY the nearest-unjoined-
        handle-within-HANDLE_HIT_RADIUS lookup its own _redraw already uses to decide what to
        reveal, so "visible in 2D" and "forwarded to 3D" can never disagree (2026-09-19, explicit:
        "in 2d, i need to hover near the edge midpoint for the midpoint to show" -- unchanged,
        this just ALSO mirrors that same rule's result).

        All three hovers are also forced clear while locked (2026-09-29, explicit user request:
        "disable hovering highlight and selecting while inflating is ongoing"), same as an
        armed palette shape/in-progress pending connection above -- an inflate in progress is
        exactly when self.base_faces/self._pending_source_polygon_id (what a forwarded hover
        would be resolved against on the 3D side) can be mid-flight ahead of what's still on
        screen (see InflaterPane._display_pending_source_polygon_id's own docstring), so
        blocking the hover at its SOURCE here is simpler and more robust than trying to keep
        every downstream consumer correct."""
        super()._on_canvas_motion(event)
        shape_id = None
        conn_id = None
        open_edge_key = None
        if (not self._locked and self.tool_mode == "edit" and self.armed_n is None
                and self._connection_pending is None):
            handle = self._hit_test_any_edge_handle(event.x, event.y)
            if handle is not None:
                open_edge_key = (handle["shape_id"], handle["edge_index"])
            else:
                conn_id = self._hit_test_connection(event.x, event.y)
                if conn_id is None:
                    wx, wy = self._screen_to_world(event.x, event.y)
                    hit = self._hit_test(wx, wy)
                    shape_id = None if hit is None else hit["id"]
        self._set_mouse_hover_shape(shape_id)
        self._set_mouse_hover_connection(conn_id)
        self._set_mouse_hover_open_edge(open_edge_key)

    def _on_canvas_leave(self, event):
        super()._on_canvas_leave(event)
        self._set_mouse_hover_shape(None)
        self._set_mouse_hover_connection(None)
        self._set_mouse_hover_open_edge(None)

    def _set_mouse_hover_connection(self, conn_id):
        """A no-op if `conn_id` is already the current mouse hover (the common case -- most
        mouse-move events land on the same connection the previous one did, or on the same
        empty space)."""
        if conn_id == self._mouse_hover_connection_id:
            return
        self._mouse_hover_connection_id = conn_id
        self._redraw()
        if self.inflater_getter is not None:
            self.inflater_getter().set_hover_connection_from_builder(conn_id)

    def _set_mouse_hover_open_edge(self, key):
        """A no-op if `key` already matches the current mouse hover. Unlike
        _set_mouse_hover_shape/_set_mouse_hover_connection, this does NOT call self._redraw()
        -- the reveal it's forwarding is already drawn by InteractiveBuilderApp's own base-class
        _redraw (super()._on_canvas_motion, called just before this in _on_canvas_motion,
        already redrew this exact frame), so a second redraw here would just be redundant."""
        if key == self._mouse_hover_open_edge_key:
            return
        self._mouse_hover_open_edge_key = key
        if self.inflater_getter is not None:
            shape_id, edge_index = key if key is not None else (None, None)
            self.inflater_getter().set_open_edge_hover_from_builder(shape_id, edge_index)

    def _set_mouse_hover_shape(self, shape_id):
        """A no-op if `shape_id` is already the current mouse hover (the common case -- most
        mouse-move events land on the same shape the previous one did, or on the same empty
        space)."""
        if shape_id == self._mouse_hover_shape_id:
            return
        self._mouse_hover_shape_id = shape_id
        self._redraw()
        if self.inflater_getter is not None:
            self.inflater_getter().set_hover_shape_from_builder(shape_id)

    # Which shape (by index into self.shapes) the NEXT _draw_shape override call corresponds to
    # -- see that method's own docstring for why this index-counting trick is needed at all. A
    # class attribute for the same before-__init__-finishes reason as on_change/
    # _face_hover_shape_id above.
    _draw_shape_index = 0

    def _draw_shape(self, screen_vertices, fill_hex, selected, hatched=False):
        """For a shape NOT part of the live central object: dims its fill to
        DISCONNECTED_OPACITY (2026-09-26, explicit: "add back the transparency... make the
        orphaned pieces 50% opacity" -- blended toward the canvas's own background color,
        _weighted_color(fill_hex, DISCONNECTED_OPACITY, other=PLOT_THEME["bg"]), same "weight =
        fraction of the shape's own color" convention this module's other _weighted_color calls
        use), AND suppresses InteractiveBuilderApp's own solid-red selection outline (2026-09-26,
        explicit: "when an orphaned piece is selected, the white dashed outline should be
        replaced with a thick red dashed outline") -- _redraw's own dashed-outline overlay (drawn
        after this returns) is the ONLY outline an orphan shape ever gets, white when unselected
        or thick red when selected; the solid baked-in red rectangle `selected=True` would
        otherwise draw here is turned off (forced to False) so it doesn't show through that
        dashed overlay's own gaps.

        InteractiveBuilderApp's own _redraw (untouchable, called via super()._redraw() below)
        calls this once per self.shapes entry, IN ORDER, with no shape id in the call itself --
        self._draw_shape_index (reset to 0 by the overridden _redraw just before calling super())
        exploits that fixed calling order: the Nth call this pass is self.shapes[N]. The one
        OTHER call site (the armed palette shape about to be dropped, drawn AFTER that loop, not
        yet a real placed shape at all) falls past the range and is left alone."""
        if self._draw_shape_index < len(self.shapes):
            shape = self.shapes[self._draw_shape_index]
            if shape["id"] not in self.central_shape_ids():
                selected = False
                fill_hex = mcolors.to_hex(
                    _weighted_color(fill_hex, DISCONNECTED_OPACITY, other=PLOT_THEME["bg"]))
        self._draw_shape_index += 1
        super()._draw_shape(screen_vertices, fill_hex, selected, hatched=hatched)

    def _redraw(self):
        """Runs InteractiveBuilderApp's own full redraw unchanged (which already draws its own
        RED selection outline for self.selected_ids -- suppressed for an orphan shape, see
        _draw_shape above), then draws the yellow HOVER highlight (if any) on top -- _redraw's
        own canvas.delete("all") wipes everything first, so this can't be done as a one-time
        canvas item; it has to be re-added after every single redraw, from whatever edit
        triggered it (drag/rotate/connect/etc.), not just from set_hover_shape's own calls.
        Outlines whichever shape(s) are hovered from EITHER direction (3D->2D's
        _face_hover_shape_id, this canvas's own _mouse_hover_shape_id) -- a set, deduplicated,
        since both are usually the same shape or one of them is None -- EXCLUDING anything
        already selected (2026-09-19, explicit: "when you hover then select, the face should go
        from being highlighted (yellow) to being selected (red) [don't draw both]"): the base
        class's own red selection outline already covers that case, so a second yellow one on
        top would just be visual noise.

        Also forwards self.selected_ids to InflaterPane whenever it's changed since the last
        forward (see _last_forwarded_selected_ids' own docstring for why this diff-on-redraw
        approach, rather than hooking every mutation site, is used).

        InteractiveBuilderApp's own _redraw (called via super() below) only draws edge handles/
        the selected connection's own bezier handles while `self.tool_mode == "join"` -- Edit
        mode merges Move+Join (2026-09-29, explicit), so it needs both showing too, but this app
        never actually sets self.tool_mode to "join" (see _build_ui/_set_tool_mode -- "join"
        no longer exists as a real mode here at all). Rather than duplicating that base method's
        ~90 lines just to change two `== "join"` checks (interactive_builder_app.app is kept
        read-only from this file, see its own import comment up top), this temporarily SWAPS
        self.tool_mode to "join" for just the duration of the super() call, restoring it right
        after -- safe because the whole call is synchronous with no event/callback that could
        observe the swapped value in between."""
        self._draw_shape_index = 0
        if self.tool_mode == "edit":
            self.tool_mode = "join"
            try:
                super()._redraw()
            finally:
                self.tool_mode = "edit"
        else:
            super()._redraw()

        # Ghost outline for whatever face/connection deletion just triggered the run currently
        # locking this pane (2026-09-29, explicit user request -- see stage_locked_ghost's own
        # docstring for how these two fields get populated, set_locked's own unlock branch for
        # how they get cleared). Gated on self._locked alone, not on whether a run is a diff or
        # a redirected full inflate -- either way it's still the same triggering edit. Drawn the
        # same SELECTION_OUTLINE_COLOR/CONNECTION_SELECTED_WIDTH the base class's own (still-
        # live) selection outline uses, so a ghost reads as "still selected", not as some new,
        # different kind of highlight -- _shape_world_vertices/_connection_screen_curve only
        # need the dict itself, never a live self.shapes/self.connections lookup, so a shape/
        # connection already removed from those still outlines correctly from its own snapshot
        # copy (a connection's own two endpoint SHAPES are never removed by a plain connection
        # deletion, so _connection_screen_curve's own shape lookups inside it still succeed).
        if self._locked:
            for ghost_shape in self._locked_ghost_shapes:
                screen_vertices = [self._world_to_screen(*wv)
                                   for wv in self._shape_world_vertices(ghost_shape)]
                flat = [coord for point in screen_vertices for coord in point]
                self.canvas.create_polygon(flat, outline=SELECTION_OUTLINE_COLOR, fill="", width=3)
            if self._locked_ghost_connection is not None:
                curve = self._connection_screen_curve(self._locked_ghost_connection)
                if curve is not None:
                    flat = [coord for point in curve for coord in point]
                    self.canvas.create_line(*flat, fill=SELECTION_OUTLINE_COLOR,
                                             width=CONNECTION_SELECTED_WIDTH)

        # The anchor's own on-canvas marker (2026-09-26, explicit) -- centered on the anchor
        # shape's own world position, drawn in SCREEN-FIXED size (not scaled by the shape's own
        # size/zoom) so it stays a clear, legible marker regardless of polygon type or zoom
        # level. Debug-mode only (2026-09-29, explicit: "show the anchor only in debug mode" --
        # the anchor is now purely automatic, see _plan_anchor_deletion/_on_delete_key, so it's
        # an implementation detail most users have no reason to see).
        if self.debug_mode and self._anchor_shape_id is not None:
            anchor_shape = self._shape_by_id(self._anchor_shape_id)
            if anchor_shape is not None:
                sx, sy = self._world_to_screen(anchor_shape["cx"], anchor_shape["cy"])
                _draw_anchor_symbol(self.canvas, sx, sy, ANCHOR_MARKER_RADIUS_PX, ANCHOR_MARKER_COLOR)

        # Dashed outline for every shape NOT part of the live central object (2026-09-26,
        # explicit: "instead of having it a bit transparent, give it a dotted outline"; then "the
        # dashes don't look right. they should look like the selection box" -- a single
        # create_polygon(..., dash=...) resets tk's dash phase at every vertex, which reads as a
        # ring of small dots rather than clean dashes running along each edge, and doesn't match
        # the crisp look of the hover/selection outlines drawn the same way elsewhere in this
        # method. One create_line PER EDGE instead -- each edge gets its own clean, independent
        # dash run, closing the loop back to the first vertex. A SELECTED orphan gets the thick
        # red variant instead of the plain white one (2026-09-26, explicit) -- _draw_shape above
        # already suppressed the base class's own solid red selection outline for these shapes,
        # so this dashed one is the only selection indicator an orphan ever shows.
        central_ids = self.central_shape_ids()
        for shape in self.shapes:
            if shape["id"] not in central_ids:
                screen_vertices = [self._world_to_screen(*wv)
                                    for wv in self._shape_world_vertices(shape)]
                selected = shape["id"] in self.selected_ids
                color = SELECTION_OUTLINE_COLOR if selected else DISCONNECTED_OUTLINE_COLOR
                dash = DISCONNECTED_SELECTED_OUTLINE_DASH if selected else DISCONNECTED_OUTLINE_DASH
                line_count = (DISCONNECTED_SELECTED_OUTLINE_LINE_COUNT if selected
                              else DISCONNECTED_OUTLINE_LINE_COUNT)
                n = len(screen_vertices)
                for i in range(n):
                    x1, y1 = screen_vertices[i]
                    x2, y2 = screen_vertices[(i + 1) % n]
                    _draw_dashed_edge(self.canvas, x1, y1, x2, y2, color, dash, line_count)

        hover_ids = {sid for sid in (self._face_hover_shape_id, self._mouse_hover_shape_id)
                     if sid is not None and sid not in self.selected_ids}
        for shape_id in hover_ids:
            shape = self._shape_by_id(shape_id)
            if shape is not None:
                screen_vertices = [self._world_to_screen(*wv)
                                    for wv in self._shape_world_vertices(shape)]
                if shape_id in central_ids:
                    flat = [coord for point in screen_vertices for coord in point]
                    self.canvas.create_polygon(flat, outline="yellow", fill="", width=3)
                else:
                    # An orphan's own hover outline is DASHED too (2026-09-26, explicit) --
                    # matching its dashed selection/idle outlines above rather than the plain
                    # solid yellow ring a central shape gets. Same "several width=1 lines instead
                    # of one wide one" technique as _draw_dashed_edge's other callers (a literal
                    # width=3 solid-style polygon can't ALSO carry a crisp custom dash on
                    # Windows -- see DISCONNECTED_OUTLINE_LINE_COUNT's own comment).
                    n = len(screen_vertices)
                    for i in range(n):
                        x1, y1 = screen_vertices[i]
                        x2, y2 = screen_vertices[(i + 1) % n]
                        _draw_dashed_edge(self.canvas, x1, y1, x2, y2, "yellow",
                                          DISCONNECTED_SELECTED_OUTLINE_DASH,
                                          DISCONNECTED_SELECTED_OUTLINE_LINE_COUNT)

        current_selection = frozenset(self.selected_ids)
        if current_selection != self._last_forwarded_selected_ids:
            self._last_forwarded_selected_ids = current_selection
            if self.inflater_getter is not None:
                self.inflater_getter().set_selected_shape_ids_from_builder(current_selection)

        # Connection hover (Join mode only) -- same either-direction/exclude-selected pattern as
        # the shape outline above, drawn as an extra curve on top of the base class's own
        # (grey/red) one rather than replacing it, same as _draw_connection_curve's own
        # highlighted-vs-not convention.
        hover_conn_ids = {cid for cid in (self._hover_connection_id, self._mouse_hover_connection_id)
                           if cid is not None and cid != self.selected_connection_id}
        for conn_id in hover_conn_ids:
            conn = next((c for c in self.connections if c["id"] == conn_id), None)
            if conn is not None:
                curve = self._connection_screen_curve(conn)
                if curve is not None:
                    flat = [coord for point in curve for coord in point]
                    self.canvas.create_line(*flat, fill="yellow", width=CONNECTION_SELECTED_WIDTH)

        if self.selected_connection_id != self._last_forwarded_selected_connection_id:
            self._last_forwarded_selected_connection_id = self.selected_connection_id
            if self.inflater_getter is not None:
                self.inflater_getter().set_selected_connection_from_builder(self.selected_connection_id)

        # InflaterPane's own open-edge hover-reveal (3D->2D, see set_open_edge_hover) -- forces
        # the SAME unfilled ring InteractiveBuilderApp's own _redraw already knows how to draw
        # (_draw_handle_circle(lit=False, joined=False)) for this one edge, even if the 2D
        # cursor itself isn't anywhere near it. Suppressed while a REAL pending connection is
        # active (its own origin/target already draw a LIT circle for whichever edges matter;
        # forcing an unfilled one on top would be redundant at best, wrong at worst) or outside
        # Edit mode (formerly Join -- where this whole concept doesn't apply, and the shape it
        # names may not even still exist as placed).
        if (self._forced_hover_open_edge is not None and self.tool_mode == "edit"
                and self._connection_pending is None):
            forced_shape_id, forced_edge_index = self._forced_hover_open_edge
            forced_shape = self._shape_by_id(forced_shape_id)
            if forced_shape is not None and forced_edge_index < forced_shape["n"]:
                self._draw_handle_circle(forced_shape, forced_edge_index, lit=False, joined=False)

        # A genuine 2D click-click Join gesture's own pending connection/hover target, forwarded
        # to InflaterPane so it shows the matching lit marker(s) in 3D too (2026-09-19, explicit:
        # "vice versa from 2d to 3d") -- self._connection_pending/_hover_shape_id/
        # _hover_edge_index are InteractiveBuilderApp's OWN fields (untouchable base class); this
        # doesn't touch them, just reads and diffs them the same way selected_ids/
        # selected_connection_id are above. set_pending_connection (3D->2D direction) pre-sets
        # _last_forwarded_pending before mutating these same three fields, so that direction's
        # own call into _redraw doesn't bounce right back out here.
        current_pending = (None if self._connection_pending is None else
                           (self._connection_pending["from_shape"], self._connection_pending["from_edge"]))
        current_forward = (current_pending, self._hover_shape_id, self._hover_edge_index)
        if current_forward != self._last_forwarded_pending:
            self._last_forwarded_pending = current_forward
            if self.inflater_getter is not None:
                from_shape, from_edge = current_pending if current_pending is not None else (None, None)
                self.inflater_getter().set_pending_connection_from_builder(
                    from_shape, from_edge, self._hover_shape_id, self._hover_edge_index)

    # Read-only lock (2026-09-19, explicit) -- another class attribute for the same
    # before-__init__-finishes reason as on_change/_hover_shape_id above. True for the whole
    # duration of ANY running inflate (InflaterPane._set_running wires this via set_locked),
    # so a mid-computation edit can never invalidate the mesh the background thread is
    # actively working from. Only camera-equivalent view changes -- 2D pan/zoom (_on_zoom/
    # _on_right_press/_on_right_drag/_on_right_release, always tool_mode/lock-agnostic) and the
    # 3D panel's own rotate/pan/zoom (InflaterPane, never gated on this flag at all) -- stay
    # allowed throughout (2026-09-29, explicit user request: "disable all types of editing.
    # only allow view changes like rotating/panning/zooming"). Everything else that reads as
    # "interacting with the model" is blocked while locked: shape/connection ADD/REMOVE/DRAG,
    # UNDO/REDO/LOAD, and now also plain SELECTION and HOVER highlighting in both panes
    # (_on_canvas_press_edit/_on_canvas_motion here, _on_panel_click/_on_panel_hover_motion on
    # InflaterPane's own side) -- an earlier version of this left selection/hover live on the
    # theory that they're read-only and harmless, but they were still "editing" in the sense
    # that mattered to this request, and 3D hover/select in particular could resolve against a
    # mid-flight NEW mesh while the panel still showed the OLD one (see InflaterPane.
    # _display_pending_source_polygon_id's own docstring for that particular failure mode).
    # EXCEPTION (2026-09-29, explicit user request): whatever single edit actually TRIGGERED the
    # run stays visibly outlined the whole time it's in progress -- a deleted face or connection
    # (self._locked_ghost_shapes/_locked_ghost_connection, own docstrings on stage_locked_ghost/
    # _redraw's own ghost-outline block) or a just-made connection (plain self.selected_
    # connection_id, already handled by the ordinary unlocked-or-not selection draw) -- so the
    # user can still see exactly what they just changed while it recomputes, without that
    # reading as "selection is back on".
    _locked = False
    _locked_ghost_shapes = []
    _locked_ghost_connection = None

    def set_locked(self, locked):
        """Called by InflaterPane._set_running. Does NOT force the tool mode back to "edit"
        (2026-09-19, explicit: "after deleting a connection, it went back to Move mode. It
        should remain in the same mode" -- deleting a connection while in what's now Edit mode
        is exactly what triggers the auto-Diff-Inflate that locks the pane) -- staying in Edit
        while locked is safe on its own, since its own click-click connection gesture is blocked
        directly, at the gesture level (_on_canvas_press_edit above), not by kicking the user
        out of the mode that gesture lives in. Swaps the bottom status line to a fixed
        explanatory message -- unlocking hands the status line back to the ordinary
        vertex-merge-error display (_refresh_vme_state, which every edit already keeps
        current)."""
        if locked == self._locked:
            return
        self._locked = locked
        if locked:
            self.status_label.config(text="Model is not editable until inflation is complete.",
                                      foreground=PLOT_THEME["fg"])
        else:
            # The run is over (success, stop, or revert) -- whatever ghost was kept outlined for
            # it is no longer meaningful (a success's own fresh _redraw draws the REAL, current
            # net instead; a stop/revert's own _refresh_vme_state call below does too) -- see
            # stage_locked_ghost's own docstring.
            self._locked_ghost_shapes = []
            self._locked_ghost_connection = None
            self._refresh_vme_state()
        self._redraw()

    def stage_locked_ghost(self, shapes=(), connection=None):
        """Called by InflaterPane._stage_kept_selection, right as a Diff (or redirected Full)
        Inflate run is about to start, for the two kinds of triggering edit that remove
        something from self.shapes/self.connections outright (2026-09-29, explicit user
        request: "if the change is a face deletion, then keep that face selected... if there's
        a connection being deleted, then keep that connection/edge selected") -- `shapes`/
        `connection` are full dict copies (from InflaterPane.last_shapes_snapshot/last_
        connections_snapshot, the net as of the last completed inflate, i.e. right before
        THIS edit), stashed here since _redraw's own selection-outline pass only ever knows how
        to outline something still IN self.shapes/self.connections -- a deleted shape/connection
        needs its geometry carried along separately instead. See _redraw's own ghost-outline
        block for how these get drawn (gated on self._locked, so they never show once the run
        that asked for them ends)."""
        self._locked_ghost_shapes = list(shapes)
        self._locked_ghost_connection = connection
        self._redraw()

    def _drop_shape(self, n, wx, wy):
        """Runs InteractiveBuilderApp's own shape creation unchanged, then refreshes VME/anchor
        state immediately (2026-09-26, explicit bug report: "when i start with an empty canvas
        and add a first piece, that piece shouldn't have a dotted outline because it's
        automatically the anchor of the central group") -- the inherited caller
        (_on_canvas_press_move) never calls _refresh_vme_state itself after a plain drop, only
        _redraw (via the immediately-following disarm click) -- without this override, that
        _redraw ran BEFORE _refresh_vme_state's own anchor-assignment fallback (see its
        docstring) ever got a chance to see the brand-new shape, so a first-ever shape briefly
        (and, since nothing else happens to re-trigger a refresh, indefinitely) rendered as if it
        had no anchor at all."""
        super()._drop_shape(n, wx, wy)
        self._refresh_vme_state()

    def _on_palette_clicked(self, n):
        """Same as the inherited palette click, except it first switches to Edit mode if some
        OTHER tool mode is currently active (2026-09-28, explicit user request: "when one of
        the shapes at the top are clicked, we should automatically switch to Move mode" -- Move
        no longer exists as its own mode here, see _build_ui's own docstring; Edit is what
        it was folded into) -- the inherited implementation silently no-ops on a palette click
        made from any mode but Move ("dropping a new shape only makes sense in Move mode" --
        its own comment). Reimplements the inherited body directly, checking `self.tool_mode !=
        "edit"` instead of calling super() (whose own `!= "move"` gate would always fail here,
        since this app never sets self.tool_mode to "move" at all) -- small enough (unlike
        _redraw's ~90-line base method) that duplicating it beats the temporary-tool_mode-swap
        trick _redraw uses. _set_tool_mode("edit") is always allowed even while locked (see its
        own docstring), so this doesn't need its own separate locked-check for that part."""
        if self._locked:
            return
        if self.tool_mode != "edit":
            self._set_tool_mode("edit")
        self.armed_n = None if self.armed_n == n else n
        self._ghost_world_xy = None
        if self.armed_n is not None:
            self.selected_ids = set()
            self.selected_connection_id = None
        for other_n, icon in self._palette_canvases.items():
            icon.configure(highlightbackground=(
                "white" if other_n == self.armed_n else PLOT_THEME["bg"]))
        self._redraw()

    def _on_canvas_press(self, event):
        """Dispatches to _on_canvas_press_edit for Edit mode (base InteractiveBuilderApp's own
        dispatch only knows "move"/"join", neither of which this app ever sets self.tool_mode
        to any more -- see _build_ui's own docstring; super()._on_canvas_press(event) is
        still called as a harmless no-op fallback for any OTHER mode string, same defensive
        shape the base class's own dispatch has -- though Edit is in fact the only mode this
        app has left at all). There used to be an "Anchor [A]" mode's own gesture here too (a
        plain click on a shape moved the central-object anchor there) -- removed 2026-09-29,
        explicit ("remove the Anchor[A] mode"): the anchor is now assigned purely automatically
        (see _plan_anchor_deletion), never picked by the user."""
        if self.tool_mode == "edit":
            self._on_canvas_press_edit(event)
        else:
            super()._on_canvas_press(event)

    def _on_canvas_press_edit(self, event):
        """Edit mode's own press handler (2026-09-29, explicit: "combine Move mode with Join
        mode to make Edit[E] mode") -- merges InteractiveBuilderApp's separate Move
        (_on_canvas_press_move: drop/select/drag/marquee shapes) and Join
        (_on_canvas_press_join: click-click/drag-and-drop connect, select a connection line) own
        press handlers into ONE gesture, reusing Join's own internal priority among ITSELF (a
        bezier-handle drag beats completing/arming a pending connection, which beats an edge
        handle, which beats a connection line) -- but where Join's own last resort was just
        "deselect", this one falls all the way through to Move's OWN shape hit-test/drag/marquee
        logic instead, via super()._on_canvas_press_move(event) (inherited, unchanged, and
        itself tool_mode-agnostic -- it only reads self.armed_n and runs hit tests, never checks
        self.tool_mode), rather than duplicating that whole method here.

        Nothing here fires at all while locked (2026-09-29, explicit user request: "disable
        hovering highlight and selecting while inflating is ongoing... disable all types of
        editing. only allow view changes like rotating/panning/zooming" -- an earlier version
        blocked only connection editing/selection here, deliberately leaving the shape hit-test/
        drag/marquee fallback below live, matching Move's own historical never-lock-guarded
        behavior; that fallback is now blocked too, since a shape SELECT -- not just a drag --
        counts as "editing" for this purpose. A palette shape can't even get armed while locked
        in the first place, since _on_palette_clicked's own lock-check already blocks that
        upstream, so the self.armed_n branch below is unreachable while locked anyway -- this
        guard is what actually stops the trailing super()._on_canvas_press_move(event) fallback.
        The drag-and-drop connection convention (arm on press, resolve on release) is similarly
        blocked at the source -- it lives entirely in _on_canvas_drag/_on_canvas_release below,
        which are already tool_mode-agnostic (they only look at self._connection_pending/
        self._bezier_handle_drag/self._drag_state/self._marquee_start, never self.tool_mode
        itself) and only ever get INTO one of those states via a press that this guard now
        blocks from ever starting one while locked."""
        if self._locked:
            return
        if self.armed_n is not None:
            super()._on_canvas_press_move(event)
            return
        if self._connection_pending is None:
            end = self._hit_test_bezier_handle(event.x, event.y)
            if end is not None:
                self._begin_undoable_change()
                self._bezier_handle_drag = {"conn_id": self.selected_connection_id, "end": end}
                return
        if self._connection_pending is not None:
            if self._complete_or_cancel_pending_connection():
                self._redraw()
                return
        handle = self._hit_test_any_edge_handle(event.x, event.y)
        if handle is not None:
            self._connection_pending = {"from_shape": handle["shape_id"],
                                         "from_edge": handle["edge_index"]}
            self._pending_cursor_screen = (event.x, event.y)
            self.selected_connection_id = None
            # Unlike old Join mode (where shapes were never selectable at all, so this
            # never mattered), Edit mode can have a shape selected when a handle gets
            # clicked -- clear it so a stale red shape outline doesn't sit next to the new
            # in-progress connection line.
            self.selected_ids = set()
            self._redraw()
            return
        conn_hit = self._hit_test_connection(event.x, event.y)
        if conn_hit is not None:
            self.selected_connection_id = conn_hit
            self.selected_ids = set()
            self._redraw()
            return
        super()._on_canvas_press_move(event)

    def _on_canvas_drag(self, event):
        """Runs InteractiveBuilderApp's own drag handling (shape-move/bezier-handle-drag/
        marquee) UNCHANGED for everything except an active pending connection (2026-09-19,
        explicit: drag-and-drop, see _on_canvas_press_edit above) -- for that one
        case, calls its own _on_canvas_motion instead, which is what recomputes
        _hover_shape_id/_hover_edge_index/_pending_cursor_screen for a pending connection
        (bound to plain <Motion>, which never fires while a button is held -- this is what
        turns "arm, release the mouse, move normally, click again" into "arm, keep the button
        held, drag, release")."""
        if self._connection_pending is not None:
            self._on_canvas_motion(event)
            return
        super()._on_canvas_drag(event)

    def _complete_or_cancel_pending_connection(self):
        """Runs InteractiveBuilderApp's own click-click/drag-and-drop completion unchanged,
        then UNDOES it if the connection it just made turns the net invalid (2026-09-19,
        explicit bug report: "when i try to make an illegal join, the app does warn me... but
        it should then undo the illegal move in both 2d and 3d") -- the base method's own
        _push_undo (called right before appending) already recorded the pre-connection state;
        _undo_illegal_connection pops that SAME entry back off rather than pushing a second,
        user-never-asked-for undo step. self._on_canvas_release's own `len(self.connections) >
        connections_before` check already reads the length AFTER this returns, so a rollback
        here is invisible to it -- it correctly sees no NET change and skips showing the "made"
        3D indicator.

        Also blocks an orphan-to-orphan join (2026-09-26, explicit -- see
        _is_orphan_to_orphan_join's own docstring) BEFORE calling super() at all, rather than
        letting it complete and then undoing it the way the vertex-merge-error branch does above
        -- self._connection_pending["from_shape"]/self._hover_shape_id are exactly the two
        endpoints the base method itself is about to join, checkable without having to make (and
        unmake) the connection first."""
        if self._connection_pending is not None and self._hover_shape_id is not None:
            from_shape = self._connection_pending["from_shape"]
            to_shape = self._hover_shape_id
            if self._is_orphan_to_orphan_join(from_shape, to_shape):
                self._show_orphan_join_error()
                self._connection_pending = None
                self._hover_shape_id = None
                self._hover_edge_index = None
                self._pending_cursor_screen = None
                self._redraw()
                return False
        was_vme_active = self._vme_active
        made = super()._complete_or_cancel_pending_connection()
        if made and self._vme_active and not was_vme_active:
            self._undo_illegal_connection()
        return made

    def _on_canvas_release(self, event):
        """Completes (or cancels, if the drag never reached a valid target) a Join/Fold pending
        connection the instant the mouse is released (2026-09-19, explicit: drag-and-drop, see
        _on_canvas_press_join above) -- InteractiveBuilderApp's own
        _complete_or_cancel_pending_connection already does exactly this job for the old
        click-click gesture's second click; reused verbatim here, just triggered by
        ButtonRelease-1 instead of a second Button-1. A successful completion also tells
        InflaterPane to show its own persistent 3D red-edges-plus-connecting-line indicator for
        the new connection (2026-09-19, explicit: "mouse release causes both to be drawn in
        red..." -- applies whichever side actually made it, not just a 3D-native drag).

        Both endpoints' CURRENT self._open_edges info (segments/midpoint) is snapshotted from
        InflaterPane BEFORE completing -- _complete_or_cancel_pending_connection's own
        _refresh_vme_state call fires BuilderPane.on_change (InflaterPane.
        refresh_diff_eligibility), which immediately rebuilds THAT cache to exclude the two
        edges a successful connection just used, so looking them up AFTER completing would
        always find nothing."""
        if self._connection_pending is not None:
            origin_info, target_info = None, None
            if self.inflater_getter is not None:
                inflater = self.inflater_getter()
                origin_info = inflater._open_edges.get(
                    (self._connection_pending["from_shape"], self._connection_pending["from_edge"]))
                if self._hover_shape_id is not None:
                    target_info = inflater._open_edges.get((self._hover_shape_id, self._hover_edge_index))
            connections_before = len(self.connections)
            self._complete_or_cancel_pending_connection()
            self._redraw()
            if (len(self.connections) > connections_before and self.inflater_getter is not None
                    and origin_info is not None and target_info is not None):
                self.inflater_getter().add_pending_made_connection_from_builder(origin_info, target_info)
            return
        super()._on_canvas_release(event)

    def _on_escape_key(self, _event=None):
        """Runs InteractiveBuilderApp's own Esc handling (cancels a 2D-originated pending
        connection) unchanged, then ALSO tells InflaterPane to abort any 3D-originated
        drag-to-connect of its own (2026-09-19, explicit: "pressing esc should remove any
        in-progress connection in both 2d and 3d") -- set_open_edge_drag_cancelled_from_builder
        is the same cleanup a tool-mode switch already uses, and is a no-op if no 3D drag is
        actually in progress, so this covers both directions unconditionally regardless of
        which one (if either) is actually active."""
        super()._on_escape_key(_event)
        if self.inflater_getter is not None:
            self.inflater_getter().set_open_edge_drag_cancelled_from_builder()

    def _set_tool_mode(self, mode):
        # 2026-09-19, explicit: "when switching between modes, everything is deselected" --
        # super()._set_tool_mode already clears self.selected_ids/selected_connection_id (its
        # own _redraw, called at the end, diff-forwards those to InflaterPane -- see
        # _last_forwarded_selected_ids/_last_forwarded_selected_connection_id), but the HOVER
        # attributes below aren't covered by that diff (hover isn't "state", just a transient
        # highlight) and aren't reset by the base class at all, so they're cleared here
        # explicitly, both this pane's own copies and InflaterPane's. (There used to be an
        # "Anchor [A]" mode with its own enter/leave bookkeeping here too -- removed 2026-09-29,
        # explicit ("remove the Anchor[A] mode"); Edit is this app's only tool mode now, so
        # `mode != self.tool_mode` below is effectively unreachable in practice, but left as
        # ordinary defensive code rather than assuming that can never change.)
        if mode != self.tool_mode:
            self._mouse_hover_shape_id = None
            self._face_hover_shape_id = None
            self._mouse_hover_connection_id = None
            self._hover_connection_id = None
            self._mouse_hover_open_edge_key = None
            self._forced_hover_open_edge = None
            if self.inflater_getter is not None:
                inflater = self.inflater_getter()
                inflater.set_hover_shape_from_builder(None)
                inflater.set_hover_connection_from_builder(None)
                inflater.set_open_edge_hover_from_builder(None, None)
                inflater.set_open_edge_drag_cancelled_from_builder()
        super()._set_tool_mode(mode)

    def _plan_anchor_deletion(self, deleted_ids):
        """Called from _on_delete_key when `deleted_ids` (about to be deleted) contains the
        CURRENT anchor -- decides whether that's allowed and, if so, who the new anchor should
        be. Simulates the deletion against the CURRENT self.shapes/self.connections (both still
        intact at call time, since this runs BEFORE anything is actually removed): every
        component the OLD central object's own SURVIVING members fall into, post-deletion, gets
        checked -- more than one means deleting the anchor would split the club into two or more
        separate pieces, which is never allowed (2026-09-29, explicit: "if the user tries to
        delete the anchor and it splits the club into two, then it's not allowed. show a dialog
        explaining why").

        Returns (allowed, new_anchor_id):
        - (False, None): blocked -- a split. Caller shows the explanatory dialog and leaves the
          anchor out of the deletion.
        - (True, None): allowed, and nothing of the old central object survives at all (the
          whole club is being deleted along with the anchor) -- no replacement anchor is needed;
          _refresh_vme_state's own fallback (or the next shape placed, if the canvas ends up
          fully empty) takes it from here.
        - (True, some_id): allowed, with `some_id` the shape that should become the new anchor
          -- "assign another insider piece as the anchor... the insider with the most
          connections" (2026-09-29, explicit), i.e. the surviving member of the (still intact)
          club with >= 2 remaining connections and the highest connection count among those;
          falling back to the best-connected survivor overall if no insider survives (e.g. the
          club shrinks to a single piece, or to two guests only connected to each other)."""
        old_central = self.central_shape_ids()
        surviving_central = old_central - deleted_ids
        if not surviving_central:
            return True, None
        surviving_shapes = [s for s in self.shapes if s["id"] not in deleted_ids]
        surviving_connections = [
            c for c in self.connections
            if c["a_shape"] not in deleted_ids and c["b_shape"] not in deleted_ids]
        components = _shape_connected_components(surviving_shapes, surviving_connections)
        if len([comp for comp in components if comp & surviving_central]) > 1:
            return False, None
        connection_counts = {}
        for c in surviving_connections:
            connection_counts[c["a_shape"]] = connection_counts.get(c["a_shape"], 0) + 1
            connection_counts[c["b_shape"]] = connection_counts.get(c["b_shape"], 0) + 1
        insiders = [sid for sid in surviving_central if connection_counts.get(sid, 0) >= 2]
        pool = insiders or list(surviving_central)
        new_anchor_id = max(pool, key=lambda sid: (connection_counts.get(sid, 0), -sid))
        return True, new_anchor_id

    def _on_delete_key(self, _event):
        """Runs InteractiveBuilderApp's own multi-shape/connection delete unchanged, except when
        the current anchor is among the shapes about to be deleted: _plan_anchor_deletion decides
        whether that's allowed (deleting it mustn't split the club into two or more pieces,
        2026-09-29 explicit) and, if so, who the new anchor should be. When blocked, the anchor
        is dropped from this deletion (an explanatory popup says why, 2026-09-26 explicit) but
        whatever ELSE was selected is still deleted normally. When allowed, self._anchor_shape_id
        is updated to the chosen replacement BEFORE the actual deletion runs (so
        _refresh_vme_state's own "current anchor id no longer names a real shape" fallback --
        which would otherwise pick an arbitrary self.shapes[0], not necessarily even a survivor
        of the OLD central object -- never has anything to correct)."""
        if self._locked:
            return
        if self.selected_ids and self._anchor_shape_id in self.selected_ids:
            allowed, new_anchor_id = self._plan_anchor_deletion(self.selected_ids)
            if not allowed:
                self.selected_ids = self.selected_ids - {self._anchor_shape_id}
                messagebox.showerror(
                    "Cannot delete the anchor piece",
                    "Deleting the anchor here would split the central object into two or more "
                    "separate pieces, which isn't allowed -- select every piece on the other "
                    "side of the split for deletion too, or leave the anchor out of this "
                    "selection.")
            elif new_anchor_id is not None:
                self._anchor_shape_id = new_anchor_id
        super()._on_delete_key(_event)

    def _flip_selected_shapes(self, axis):
        # Flip changes a shape's own "flipped" field, which classify_change DOES compare (see
        # its own docstring) -- unlike a plain move/rotate, this is a real topology-relevant
        # edit, so it's blocked while locked too.
        if self._locked:
            return
        super()._flip_selected_shapes(axis)

    def _call_super_in_move_mode(self, bound_super_method, _event):
        """Temporarily treats Edit mode as "move" for the duration of one base-class method
        call, then restores it -- InteractiveBuilderApp's own on_copy_key/on_paste_key each
        gate on `if self.tool_mode != "move": return`, which would otherwise always fail here,
        since this app never sets self.tool_mode to "move" at all (see _build_ui's own
        docstring: Move+Join merged into Edit, 2026-09-29 explicit). Same swap-and-restore trick
        _redraw uses above, for the same reason -- avoiding a duplicate of either base method's
        own body just to change one string comparison (interactive_builder_app.app is kept
        read-only from this file). `bound_super_method` is a bound super() method (e.g.
        `super().on_copy_key`), so this works for both callers below without needing its own
        copy of the swap logic."""
        if self.tool_mode == "edit":
            self.tool_mode = "move"
            try:
                bound_super_method(_event)
            finally:
                self.tool_mode = "edit"
        else:
            bound_super_method(_event)

    def on_copy_key(self, _event=None):
        """Blocks a MULTI-shape copy (2026-09-29, explicit: "multiselect copy paste should be
        disallowed... outsiders must be isolated and are only allowed to connect to the club")
        -- InteractiveBuilderApp.on_copy_key's own docstring says it captures every connection
        with BOTH endpoints among the selected shapes, so copying 2+ CONNECTED shapes and
        pasting would drop in two brand-new shapes already connected to EACH OTHER, neither one
        yet connected to the club -- exactly the outsider-to-outsider connection this app
        never otherwise allows (an outsider can only ever gain its first connection by joining
        the club directly). Blocked here, at Ctrl+C itself, rather than at Ctrl+V -- this is
        the only place self._clipboard ever gets populated, so refusing it here means the
        clipboard can never hold more than one shape to begin with, no separate paste-time
        guard needed. A single-shape copy is unaffected (its own clipboard entry can never
        carry a connection either way -- classify_change's underlying set is what would still
        show as an outsider, isolated, after paste). See _call_super_in_move_mode's own
        docstring for why the actual super() call goes through that helper rather than a plain
        super().on_copy_key(_event)."""
        if self._locked:
            return
        if len(self.selected_ids) > 1:
            messagebox.showerror(
                "Cannot copy multiple pieces",
                "Copy/paste only works one piece at a time here -- pieces not yet connected to "
                "the club (outsiders) must stay isolated from each other, and pasting more than "
                "one at once would paste them still connected to each other.")
            return
        self._call_super_in_move_mode(super().on_copy_key, _event)

    def on_paste_key(self, _event=None):
        if self._locked:
            return
        self._call_super_in_move_mode(super().on_paste_key, _event)

    def on_undo_key(self, _event=None):
        if self._locked:
            return
        super().on_undo_key(_event)

    def on_redo_key(self, _event=None):
        if self._locked:
            return
        super().on_redo_key(_event)

    # Same before-__init__-finishes reasoning as on_change/_hover_shape_id/_locked above --
    # wired to InflaterPane.on_load_success once both panes exist (CombinedApp.__init__).
    on_load_success = None

    def on_load_clicked(self):
        if self._locked:
            return
        shapes_before = self.shapes
        super().on_load_clicked()
        # _load_faces (the inherited method a successful Load funnels through) always
        # REASSIGNS self.shapes to a fresh list (`self.shapes = []`, then appended into) --
        # never mutates the old one in place -- so an identity change here means the load
        # actually went through, as opposed to a failed one (a bad file shows its own error
        # box and returns with self.shapes untouched). 2026-09-19, explicit: "as soon as i
        # load a file, it should also inflate" (when Auto Inflate is checked).
        if self.shapes is not shapes_before:
            # _load_faces' own _redraw() call (its very last line) fires BEFORE
            # InteractiveBuilderApp.on_load_clicked's subsequent self._refresh_vme_state()
            # call corrects self._anchor_shape_id (the overridden _refresh_vme_state's own
            # "shapes exist but the current anchor id doesn't name any of them" fallback,
            # above) -- so that first redraw always draws every shape dimmed as an outsider
            # (self.central_shape_ids() sees the OLD, no-longer-valid anchor id, or None),
            # regardless of the newly-loaded net's real connectivity. Nothing else redraws
            # the canvas again afterward, so that wrong frame was what stayed on screen
            # until some unrelated interaction (hover, drag, ...) happened to trigger a real
            # one (2026-09-29, explicit bug report: "the polygons are rendered as outsiders
            # initially and later became members"). One extra _redraw() here, now that the
            # anchor is correct, fixes it for good.
            self._redraw()
            if self.on_load_success is not None:
                self.on_load_success()

    def _refresh_vme_state(self):
        """Runs InteractiveBuilderApp's own vertex-merge-error check unchanged, then notifies
        the right pane (self.on_change, if wired) that the net may have changed -- this is the
        one call site EVERY state-changing edit (place/delete/connect/flip/undo/redo/load/drag-
        release) already funnels through (see that class's own docstring), so it's the natural
        hook for keeping Diff Inflate's enabled state live without a change-tracking mechanism
        of this app's own.

        Also the one place the anchor (see _anchor_shape_id's own docstring) gets a default
        assigned: whenever shapes exist but the current anchor id doesn't name any of them
        (empty canvas -> first shape ever placed; a Load that replaced self.shapes wholesale with
        no anchor of its own restored yet -- Phase 2/3's own session loaders set the REAL anchor
        explicitly right after calling _load_faces, which runs before this fallback would ever
        fire from that same call), it falls back to self.shapes[0] -- unambiguous in the classic
        "canvas was empty, exactly one shape now exists" case this is mainly for. Clears to None
        when self.shapes empties out entirely (_on_delete_key's own guard is what makes that only
        reachable by deleting the very last remaining shape)."""
        if self.shapes:
            if self._anchor_shape_id not in {s["id"] for s in self.shapes}:
                self._anchor_shape_id = self.shapes[0]["id"]
        else:
            self._anchor_shape_id = None
        super()._refresh_vme_state()
        if self.on_change is not None:
            self.on_change()

    def snapshot_state(self):
        """Returns (shapes, connections, anchor_shape_id) -- per-dict SHALLOW copies (shape/
        connection dicts are flat; edits like flip/drag mutate them IN PLACE, so a plain
        list-of-references snapshot would silently "change" along with the live state) of
        self.shapes/self.connections, plus self._anchor_shape_id, all at this exact moment, for a
        later classify_change call to diff against (the anchor id is needed there too, to find
        which component was central AT THAT SNAPSHOT -- see its own docstring)."""
        return [dict(s) for s in self.shapes], [dict(c) for c in self.connections], self._anchor_shape_id

    def classify_change(self, old_shapes, old_connections, old_anchor_shape_id):
        """old_shapes/old_connections: a prior snapshot_state() result (or None, meaning
        "never inflated yet"). Returns (kind, extra) where kind is "none" (no topology change),
        "add_face" (EXACTLY one shape added and nothing else about the surviving net's topology
        changed -- extra is that one shape's id), "remove_face" (ONE OR MORE shapes removed at
        once and nothing else about the surviving net's topology changed -- 2026-09-19, explicit:
        "if multiple faces are deleted at once, let that qualify for diff inflate/auto inflate"
        -- extra is the SET of removed shape ids; adding is still capped at exactly one, since
        InflaterPane._diff_add_face's interpolation only ever seeds ONE new shape's fresh
        vertices from its own connection(s) to the surviving mesh), "add_connection"/
        "remove_connection" (same shape SET, but exactly one connection added/removed and no
        shape's own n/flipped changed -- extra is that connection's own conn_key, unused by the
        caller but handy for debugging), or "complex" (anything else -- a moved/flipped/multi-
        shape ADD, more than one connection edited at once, etc.), extra is None for "none"/
        "complex".

        A shape's cx/cy/rotation never affect the exported mesh at all (only n/flipped and the
        connection graph do -- _faces_from_shapes/_edges_from_shapes never read position), so
        those are deliberately ignored here: dragging a shape around never disables Diff
        Inflate. Connections are compared by their (shape, edge) endpoints only (frozenset, so
        a<->b/b<->a order doesn't matter) -- a connection's own bezier handles are a pure
        drawing detail, never read by the exported mesh either.

        Both snapshots are restricted to their OWN central object first (_central_shape_ids,
        same restriction export_mesh_dict applies -- see its own docstring) before anything
        else below runs, so placing (or removing) a shape that never joins the central object at
        all classifies as "none": it doesn't change what actually gets exported/inflated, so it
        shouldn't disable Diff Inflate or fire an unnecessary Auto Inflate re-run either."""
        if old_shapes is None:
            return "complex", None
        old_central = _central_shape_ids(old_shapes, old_connections, old_anchor_shape_id)
        old_shapes = [s for s in old_shapes if s["id"] in old_central]
        old_connections = [c for c in old_connections
                            if c["a_shape"] in old_central and c["b_shape"] in old_central]
        new_central = self.central_shape_ids()
        new_shapes = [s for s in self.shapes if s["id"] in new_central]
        new_connections = [c for c in self.connections
                            if c["a_shape"] in new_central and c["b_shape"] in new_central]

        old_by_id = {s["id"]: s for s in old_shapes}
        new_by_id = {s["id"]: s for s in new_shapes}
        old_ids, new_ids = set(old_by_id), set(new_by_id)
        added, removed, common = new_ids - old_ids, old_ids - new_ids, old_ids & new_ids
        for sid in common:
            a, b = old_by_id[sid], new_by_id[sid]
            if a["n"] != b["n"] or a.get("flipped", False) != b.get("flipped", False):
                return "complex", None

        def touches(key, shape_id):
            return any(sid == shape_id for sid, _edge in key)

        def touches_any(key, shape_ids):
            return any(sid in shape_ids for sid, _edge in key)

        old_conns = {_connection_key(c) for c in old_connections}
        new_conns = {_connection_key(c) for c in new_connections}
        conn_added, conn_removed = new_conns - old_conns, old_conns - new_conns

        if len(added) == 1 and not removed:
            (new_id,) = added
            if conn_removed or any(not touches(k, new_id) for k in conn_added):
                return "complex", None
            return "add_face", new_id
        if removed and not added:
            if conn_added or any(not touches_any(k, removed) for k in conn_removed):
                return "complex", None
            return "remove_face", frozenset(removed)
        if not added and not removed:
            if not conn_added and not conn_removed:
                return "none", None
            if len(conn_added) == 1 and not conn_removed:
                return "add_connection", next(iter(conn_added))
            if len(conn_removed) == 1 and not conn_added:
                return "remove_connection", next(iter(conn_removed))
        return "complex", None

    def _scale_ui_fonts(self):
        """No-op override -- the combined app scales every named font ONCE, centrally
        (see CombinedApp), before either pane is built. InteractiveBuilderApp's own version,
        left to run again here, would double-scale every font (it mutates the same
        interpreter-wide named fonts BuilderPane and InflaterPane both read)."""

    def _build_ui(self):
        self.status_label = ttk.Label(self.root, anchor="w", padding=(8, 3))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # padding=(8, 2, 8, 2) -- horizontal unchanged, top/bottom both dropped 8 -> 4 -> 2
        # (2026-09-29, explicit user request: "the shape buttons need to be shifted a bit lower
        # to have even top/bottom margins", then "there's too much space between the button bar
        # and the drawing area. close that up", then "still too much" -- both sides shrunk
        # together each time, so top/bottom stay equal to each other, just narrower than before).
        # The WHOLE visual gap below the icons
        # (down to self.canvas's own border) lives inside this frame's own bottom padding; self.
        # canvas's own pady is (0, 8) (top 0), not (8, 8), specifically so there's no SEPARATE
        # gap stacked on top of this one -- see its own comment for why that second gap would
        # also break header-height matching below, not just the margins look.
        # self._header_frame (not just a local `top`) + pack_propagate(False): InflaterPane's
        # own _apply_mode_visibility keeps this frame's HEIGHT in lockstep with its own header
        # (self._setup_frame) right after every (re)pack, in BOTH directions, so self.canvas's
        # own top border always lands exactly where InflaterPane.panel_label's does regardless
        # of which mode InflaterPane happens to be showing (2026-09-29, explicit user request:
        # "the 2d and 3d canvas boxes are not aligned at the top" -- hand-tuning padding/pady on
        # each side to match by ARITHMETIC, tried first, broke again the moment either side's
        # own content needed to change -- pack_propagate(False) here (this frame stops sizing
        # itself to its own content, so setting its height from outside actually sticks) is what
        # makes an explicit, ALWAYS-current height assignment possible at all). This only works
        # cleanly because self.canvas's own pady has NO top component either (see its own
        # comment) -- otherwise this frame's reqheight and InflaterPane._setup_frame's own
        # wouldn't correspond to the same "header top to box top" distance any more, and this
        # method's own height assignment would need to compensate for that mismatch instead of
        # just copying the number across.
        self._header_frame = top = ttk.Frame(self.root, padding=(8, 2, 8, 2))
        top.pack_propagate(False)
        top.pack(side=tk.TOP, fill=tk.X)
        # Icons packed into an INNER frame that itself is centered in `top` (pack's default
        # anchor="center" centers a non-filling child within its parcel) -- packing the icons
        # straight into `top` (which fills X) would leave them flush left instead
        # (2026-09-19, explicit: "centre-align the n-gon buttons").
        palette_row = ttk.Frame(top)
        # pady=(4, 0) -- nudges the icons down a bit within `top`'s own (fixed-height, see
        # pack_propagate(False) above) box (2026-09-29, explicit user request: "just move the
        # polygon buttons down a bit") -- purely a shift within the row's own existing space,
        # not a change to that space itself, so it doesn't reopen the header-height-matching
        # this frame's own height assignment (_apply_mode_visibility's tail) relies on.
        palette_row.pack(side=tk.TOP, pady=(4, 0))
        for n in POLYGON_NS:
            self._build_palette_entry(palette_row, n)

        # No left tool strip (2026-09-29, explicit user request: "get rid of the Edit mode
        # button and the left toolbar since we're always in Edit mode") -- Edit has been this
        # app's only tool mode for a while now (see _build_toolbar's own former docstring, kept
        # below on self.tool_mode's own assignment), so a mode-switch button/strip for a mode
        # that can never be switched away from was pure vestigial UI; the canvas now simply
        # starts flush against the left edge instead.
        self.tool_mode = "edit"

        self.canvas = tk.Canvas(self.root, bg=PLOT_THEME["bg"],
                                 highlightthickness=1, highlightbackground=PLOT_THEME["fg"])
        # padx=8 (was (0, 8), no left margin -- a leftover from when the now-removed left tool
        # strip used to occupy that space) -- both views get a left/right margin now (2026-09-29,
        # explicit user request: "both views should have some margins on the left/right sides").
        # pady=(0, 8), not a plain 8 -- top's own bottom padding already provides the gap above
        # this border (see top's own comment); a second one stacked here would both look uneven
        # and throw off the header-height match _apply_mode_visibility relies on.
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", self._on_canvas_leave)
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-3>", self._on_right_press)
        self.canvas.bind("<B3-Motion>", self._on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.canvas.bind("<MouseWheel>", self._on_zoom)
        self.canvas.bind("<Button-4>", self._on_zoom)
        self.canvas.bind("<Button-5>", self._on_zoom)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Global (bind_all) keyboard shortcuts, GUARDED to skip while a text-entry widget (the
        # right pane's target-RMS/tolerance Entries) has focus -- interactive_builder_app's own
        # bind_all was safe unguarded (that app has no text-entry widget at all for a shortcut
        # like Delete/Ctrl+C/j to collide with); this combined window does, so typing "1e-04"
        # into Tolerance must not also delete shapes, toggle Join mode, etc.
        self._bind_all_guarded("<Delete>", self._on_delete_key)
        self._bind_all_guarded("<KeyPress-d>", self._on_toggle_debug_mode)
        self._bind_all_guarded("<KeyPress-f>", self._on_flip_key)
        self._bind_all_guarded("<KeyPress-e>", lambda _e: self._set_tool_mode("edit"))
        self._bind_all_guarded("<Control-c>", self.on_copy_key)
        self._bind_all_guarded("<Control-v>", self.on_paste_key)
        self._bind_all_guarded("<Control-z>", self.on_undo_key)
        self._bind_all_guarded("<Control-y>", self.on_redo_key)
        self._bind_all_guarded("<Escape>", self._on_escape_key)

    def _bind_all_guarded(self, sequence, handler):
        def wrapped(event=None):
            focused = self.root.winfo_toplevel().focus_get()
            if isinstance(focused, (tk.Entry, ttk.Entry, tk.Spinbox, ttk.Spinbox)):
                return None
            return handler(event)
        self.root.bind_all(sequence, wrapped)

    def _build_palette_entry(self, parent, n):
        """Same icon construction as InteractiveBuilderApp's own _build_palette_entry, but
        packed LEFT-to-right (a horizontal top row) instead of top-to-bottom (a vertical left
        column), and scaled down to INFLATER_ICON_SIZE (see module docstring) instead of that
        app's own ICON_SIZE -- this app's own required layout.

        Centered by its own BOUNDING BOX, not by _ICON_VERTICES' shared circumradius/circumcenter
        (2026-09-29, explicit user request: "make the triangle aligned with the rest of the
        shapes") -- every n-gon in POLYGON_NS shares one circumradius (interactive_builder_app's
        own ICON_RADIUS) so they read as "evenly sized", but a triangle's own bounding box is far
        from centered on that shared circumcenter the way an even-sided (or higher-n) polygon's
        is: one vertex reaches the full radius on one side, while the OPPOSITE flat edge only
        reaches half that -- drawn at the circumcenter, it visibly sat higher than the rest of
        the row. Recentering every shape by its own bbox instead fixes the triangle and is a
        no-op (or near enough) for the others, which were already close to bbox-centered."""
        icon = tk.Canvas(parent, width=INFLATER_ICON_SIZE, height=INFLATER_ICON_SIZE,
                          bg=PLOT_THEME["bg"], highlightthickness=2,
                          highlightbackground=PLOT_THEME["bg"])
        icon.pack(side=tk.LEFT, padx=2)
        cx, cy = INFLATER_ICON_SIZE / 2, INFLATER_ICON_SIZE / 2
        scale = INFLATER_ICON_SIZE / ICON_SIZE
        verts = _ICON_VERTICES[n]
        xs, ys = [v[0] for v in verts], [v[1] for v in verts]
        bbox_cx, bbox_cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        screen_vertices = [((vx - bbox_cx) * scale + cx, (vy - bbox_cy) * scale + cy)
                            for vx, vy in verts]
        photo, (left, top) = _rasterize_polygon(screen_vertices, POLYGON_COLORS[n])
        self._icon_photos[n] = photo
        icon.create_image(left, top, anchor="nw", image=photo)
        icon.bind("<Button-1>", lambda _e, n=n: self._on_palette_clicked(n))
        self._palette_canvases[n] = icon

    def _update_title(self):
        """No-op -- an embedded pane has no window title of its own (this combined app's real
        Toplevel title is set once by CombinedApp)."""

    def _update_file_menu_state(self):
        """No-op -- InteractiveBuilderApp's own version enables/disables Save/Save As on
        self.file_menu, which doesn't exist here (CombinedApp builds the one real File menu,
        with only Load..., outside this pane -- see its own _build_menu)."""

    def central_shape_ids(self):
        """The live "central object"'s own shape ids (see _central_shape_ids' own docstring) --
        the connected component currently containing self._anchor_shape_id, which
        export_mesh_dict/root_to_vertex_id/_draw_shape all restrict themselves to. Recomputed
        fresh from self.shapes/self.connections every call (cheap at this scale, and keeps this
        correct through every add/remove/join/split with no separate state to invalidate)."""
        return _central_shape_ids(self.shapes, self.connections, self._anchor_shape_id)

    def export_mesh_dict(self):
        """Returns (mesh_dict, None) built from the CENTRAL OBJECT's current live shapes/
        connections only (central_shape_ids -- any OTHER shape, not connected into it at all, is
        excluded here so it never reaches the solver/3D view; see _central_shape_ids' own
        docstring for why), via the same _expand_folded_shapes/_faces_from_shapes/
        _edges_from_shapes/_face_edge_ids_from_shapes pipeline File > Save uses in
        interactive_builder_app (_export_faces_and_layout's own body, reimplemented here over
        the filtered shape/connection lists rather than calling that method directly -- it always
        reads self.shapes/self.connections itself, with no override point for a filtered subset,
        and is read-only from here) -- or (None, message) if there's no central object yet or it
        fails validation (self-loop, duplicate edge, etc.), for the caller to show via the
        existing error-messaging pattern instead of crashing."""
        central_ids = self.central_shape_ids()
        if not central_ids:
            return None, "Nothing to inflate yet -- place at least one shape first."
        central_shapes = [s for s in self.shapes if s["id"] in central_ids]
        central_connections = [c for c in self.connections
                                if c["a_shape"] in central_ids and c["b_shape"] in central_ids]
        try:
            expanded_shapes, expanded_connections, source_polygon_id = \
                _expand_folded_shapes(central_shapes, central_connections)
            _validate_shapes_connections(expanded_shapes, expanded_connections)
            faces = _faces_from_shapes(expanded_shapes, expanded_connections)
            edges = _edges_from_shapes(expanded_shapes, expanded_connections)
            face_edge_ids = _face_edge_ids_from_shapes(expanded_shapes, expanded_connections)
        except (NetValidationError, ValueError) as e:
            return None, str(e)
        mesh = {"name": "live_net", "faces": faces, "edges": edges,
                "face_edge_ids": face_edge_ids, "source_polygon_id": source_polygon_id}
        return mesh, None

    def export_full_net_dict(self):
        """Returns (mesh_dict, None) built from EVERY shape/connection currently placed --
        central object or not -- unlike export_mesh_dict (central-object only, for actual
        inflation), this is used ONLY by .hippie Save (2026-09-26, explicit: "Only .hippie files
        allow more than one connected component"). Safe to call the inherited
        _export_faces_and_layout() DIRECTLY here (unlike export_mesh_dict, which needs its own
        filtered reimplementation): that method only checks vertex-merge/duplicate-edge validity
        (_validate_shapes_connections), never connectivity -- the NEW connectivity restriction
        (net-fold-project's untouchable.md, "forbid saving nets... with more than one connected
        component") lives ONLY in interactive_builder_app's own plain-.poly Save path
        (_save_to_path), which this method never goes through. Adds "net_layout"/
        "builder_connections" into the returned dict (export_mesh_dict's own callers never
        needed these -- they only ever feed a LIVE inflate, which reconstructs positions itself --
        but a real file Save does, for an exact round trip through Load Session).
        Returns (None, message) if the net is empty or fails that vertex-merge/duplicate-edge
        check."""
        if not self.shapes:
            return None, "Nothing to save -- place at least one shape first."
        try:
            faces, edges, face_edge_ids, source_polygon_id, net_layout, builder_connections = \
                self._export_faces_and_layout()
        except (NetValidationError, ValueError) as e:
            return None, str(e)
        mesh = {"name": "live_net", "faces": faces, "edges": edges,
                "face_edge_ids": face_edge_ids, "source_polygon_id": source_polygon_id,
                "net_layout": net_layout, "builder_connections": builder_connections}
        return mesh, None

    def root_to_vertex_id(self):
        """Returns {root_slot: vertex_id} in the SAME numbering export_mesh_dict's own
        _faces_from_shapes assigns -- root_slot a (shape_id, corner_index) tuple from
        interactive_builder_app._vertex_roots, run over the EXPANDED (post-
        _expand_folded_shapes) CENTRAL-OBJECT-ONLY shapes/connections (central_shape_ids, same
        restriction export_mesh_dict applies -- see its own docstring) to match what's actually
        exported. A root slot is STABLE across an edit that doesn't touch its own group (see
        _vertex_roots' own docstring) -- unlike the raw integer id, which shifts under an edit
        that merges/splits vertex groups (a connection add/remove), NOT just a plain shape
        append/removal. Lets InflaterPane match a vertex across two different exports by this
        stable identity instead of by raw id (see InflaterPane._diff_reexport_and_relax). This
        duplicates _faces_from_shapes' own numbering loop (that function doesn't return the root
        map itself) rather than editing it -- interactive_builder_app/app.py is read-only from
        here."""
        central_ids = self.central_shape_ids()
        if not central_ids:
            return {}
        central_shapes = [s for s in self.shapes if s["id"] in central_ids]
        central_connections = [c for c in self.connections
                                if c["a_shape"] in central_ids and c["b_shape"] in central_ids]
        expanded_shapes, expanded_connections, _source_polygon_id = \
            _expand_folded_shapes(central_shapes, central_connections)
        roots = _vertex_roots(expanded_shapes, expanded_connections)
        vertex_ids = {}
        for shape in expanded_shapes:
            for corner in _shape_face_corner_order(shape):
                root = roots[(shape["id"], corner)]
                if root not in vertex_ids:
                    vertex_ids[root] = len(vertex_ids)
        return vertex_ids


class _PaneRoot(ttk.Frame):
    """Stands in for InteractiveBuilderApp's own `root` parameter inside this app's left pane --
    a real widget (so ttk.Frame(self.root, ...)/tk.Canvas(self.root, ...) parenting inside the
    inherited methods still works), but swallowing the whole-WINDOW-only calls that class's
    __init__/_build_menu make on it (title/geometry/minsize/protocol/config(menu=...)), none of
    which apply to an embedded pane."""

    def title(self, *_a, **_k):
        pass

    def geometry(self, *_a, **_k):
        pass

    def minsize(self, *_a, **_k):
        pass

    def protocol(self, *_a, **_k):
        pass

    def config(self, *args, **kwargs):
        if "menu" in kwargs:
            return None
        return super().config(*args, **kwargs)

    configure = config


# ---- right pane ----

class InflaterPane:
    """The simplified solver viewer -- see module docstring for the full list of what's
    dropped relative to inflate_polyhedron_app. Owns no state about the LEFT pane at all; it
    only ever reads a fresh mesh dict from `builder.export_mesh_dict()` at the moment Inflate
    is clicked (builder_getter, a zero-arg callable returning the current BuilderPane)."""

    def __init__(self, container, builder_getter):
        self.root = container
        self.builder_getter = builder_getter

        # Which of LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED/_OPEN currently applies -- set for real
        # by _apply_target_rms_defaults (called once _build_ui below has built target_rms_vars,
        # and again after every builder edit via refresh_diff_eligibility); OPEN here is just a
        # placeholder read by _commit_target_rms_entry's own fallback before that first call.
        self._target_rms_defaults = LEVEL_DEFAULT_TARGET_RMS_PCT_OPEN

        self.base_faces = None
        self.base_edges = None
        self.base_face_edge_ids = None
        self.faces = None
        self.edge_length = None
        self.face_of_fine = None
        self.edges = None
        self.positions = None
        self.subdivision_level = 0
        self._running = False
        # True for the duration of _load_hippie_session/_load_hippo_session's own restoration
        # work (from right before builder._load_faces through right before _apply_loaded_
        # session) -- suppresses refresh_diff_eligibility entirely during that window (2026-09-
        # 28, explicit bug report: loading a session crashed/froze on its own, no user action,
        # because builder._load_faces/its own _refresh_vme_state call BuilderPane.on_change
        # (== refresh_diff_eligibility) mid-restoration, while self.last_shapes_snapshot still
        # holds whatever it was BEFORE this load -- often None on a fresh app, which fired
        # refresh_diff_eligibility's own "first piece ever" auto-Full-Inflate branch against a
        # net that's only PARTLY restored: self.base_faces/positions/etc. still describe the
        # OLD (or no) mesh while builder.shapes/connections already describe the NEW one, and a
        # relax_initial_configuration this triggers ends up rendering the just-solved CORE
        # against the NEW net's own full connection list, including ones to a pendant shape
        # whose vertices were never part of that core -- crashing with a KeyError deep in
        # _render, which aborts _on_relax_done partway through, leaving self._running stuck
        # True forever with no live background thread left for Stop to interrupt). Cleared
        # right before _apply_loaded_session runs its OWN correct, fully-populated
        # refresh_diff_eligibility call.
        self._loading_session = False

        # Stop/revert state (2026-09-19, explicit: "never redraw anything" mid-computation
        # before real convergence; Inflate becomes a Stop button while running; a stop or a
        # trial that doesn't converge within its own step cap reverts to the mesh state from
        # right before the click, discarding whatever was computed). self._pre_click_snapshot
        # is a _snapshot_mesh_state() result taken at the top of on_full_inflate_clicked/
        # _diff_remove_face/_diff_reexport_and_relax, None whenever nothing is running.
        # self._stop_event is a fresh threading.Event() per run, forwarded as every relax/
        # calibration call's own stop_event= so a Stop click can actually interrupt mid-trial
        # (see stretchy_mesh.relax_once's own docstring). self._stop_requested short-circuits
        # every on_done callback straight into a revert once set, instead of processing
        # whatever partial result the interrupted call returned. self._active_button records
        # which button ("full"/"diff") is currently showing "Stop", so _set_running(False) can
        # restore both buttons' normal text/command.
        self._pre_click_snapshot = None
        self._stop_event = None
        self._stop_requested = False
        self._active_button = None
        # Debug-mode replay scrubber (2026-09-29, explicit user request -- "replay the last
        # full/diff inflate"): self._replay_frames is every (faces, face_of_fine, positions)
        # snapshot captured (see _capture_replay_frame) at every progress checkpoint of the
        # LAST run, across every level/pass it actually ran, in chronological order -- reset
        # to [] at the start of every new run (_set_running(True)) and on a revert
        # (_revert_run), so a stale replay from an earlier/failed run can never linger.
        # self._replay_scrub_index, when not None, is which frame _render draws INSTEAD of the
        # live self.faces/positions/face_of_fine (None means "show live", including whenever
        # nothing's been captured yet) -- see _on_replay_slider_moved's own docstring.
        self._replay_frames = []
        self._replay_scrub_index = None
        # Window-title/unsaved-changes hooks (2026-09-29, explicit user request) -- all three
        # None until CombinedApp.__init__ wires them, same optional-callback pattern as
        # BuilderPane.on_load_success/on_debug_mode_change. on_inflate_success fires at the very
        # end of _record_inflate_success (a completed Full/Diff Inflate/flat-place run changes
        # what a Save Session would write even when the 2D net itself didn't change, e.g. a
        # manual Reinflate after only a target-RMS/tolerance tweak -- CombinedApp's own
        # BuilderPane-revision-based dirty tracking can't see that on its own).
        # on_session_saved/on_session_loaded fire once a Save Session/Load Session actually
        # completes (see on_save_session_clicked/_apply_loaded_session's own call sites) --
        # CombinedApp wires both to its own _mark_clean.
        self.on_inflate_success = None
        self.on_session_saved = None
        self.on_session_loaded = None
        # True for the duration of a Full Inflate run that on_diff_inflate_clicked itself
        # redirected into (self.is_fully_inflated False -- see that method's own docstring) --
        # lets _revert_run's own "undo the triggering edit
        # on a failed run" safety net still fire even though self._active_button reads "full",
        # not "diff", for a redirected run (2026-09-28, explicit bug report: without this, a
        # redirected run that fails to converge leaves the doomed edit in place, and Auto
        # Inflate deterministically re-triggers -- SAME seed=0 starting point -- the exact same
        # failing run forever, since refresh_diff_eligibility's post-run re-check still sees the
        # same "eligible" change with nothing ever undone). Set only by the redirect call site
        # itself, never by a genuine manual Full Inflate/Reinflate/on_load_success click (those
        # correctly leave this False, so a real manual-run failure still doesn't auto-undo an
        # unrelated edit) -- cleared in both _revert_run and _record_inflate_success so it never
        # leaks into a later, unrelated run.
        self._diff_redirect_pending = False
        # A short label ("Anchor piece"/"Insider added"/"Insiders deleted"/"Insider modified")
        # prefixed onto every status message for the run this change triggered (2026-09-28,
        # explicit user request: status messages should say what kind of club change is
        # driving the run, not just which pipeline/level -- see _describe_change's own
        # docstring for how this is derived and _pipeline_label for where it's applied). None
        # for a run started by a plain manual Full Inflate/Reinflate/on_load_success click,
        # which has no single "triggering change" to describe. Deliberately NOT cleared in
        # _set_running -- the Level-3 "Done" status is set AFTER _set_running(False) runs (see
        # _on_inflate_step_done), so clearing it there would wipe the label before that final
        # message ever reads it. Instead, every genuine entry point sets this FRESH at its own
        # start (on_diff_inflate_clicked always recomputes it; on_full_inflate_clicked takes it
        # as an explicit `change_label` param, defaulting to None for a bare manual click) --
        # each new run's own start always overwrites whatever a PRIOR run left behind, so
        # staleness is never possible without a separate clearing step.
        self._change_label = None
        # {shape_id, ...} of every OUTSIDER (a placed shape not connected to the club at all --
        # see the module's own "Club terminology" section) as of the last refresh_diff_
        # eligibility call -- BuilderPane.classify_change deliberately reports "none" for an
        # outsider-only add/remove (see its own docstring: it never changes what's actually
        # exported/inflated), so this is the ONLY way outsider changes get their own status
        # message ("Outsider added"/"Outsider deleted") at all (2026-09-28, explicit user
        # request).
        self._last_outsider_ids = frozenset()

        # The BUILDER's own shapes/connections at the moment of the last successfully-COMPLETED
        # inflate (Full or Diff) -- None until the first one finishes -- plus source_polygon_id
        # (parallel to self.base_faces) from that same mesh, so a later add/remove diff can find
        # which base face(s) a given shape id owns. Set together, only on a clean "Done" (see
        # _record_inflate_success), never on a mid-pipeline stop/failure.
        self.last_shapes_snapshot = None
        self.last_connections_snapshot = None
        self.last_anchor_snapshot = None
        self.last_source_polygon_id = None
        # {root_slot: vertex_id} from BuilderPane.root_to_vertex_id() at that same moment --
        # lets a later add_connection/remove_connection/add_face diff seed its fresh mesh's
        # positions by STABLE root identity instead of raw (edit-shiftable) vertex id -- see
        # InflaterPane._diff_reexport_and_relax.
        self.last_root_to_vertex_id = None
        # The Level-3 pressure the last successful inflate converged at -- seeds Diff Inflate's
        # own next pressure search (see _run_inflate_step's own initial_pressure_guess/tol_pct
        # params and DIFF_PRESSURE_GUESS_TOL_PCT) instead of that search's generic area-based
        # guess, since a Diff Inflate's mesh is usually only a small perturbation of the one
        # that converged at this pressure (2026-09-19, explicit).
        self.last_pressure = None
        # {level: {"pressure", "rms_stretch_pct", "pressure_found"}} for every level ALREADY
        # completed within the CURRENT Full Inflate run -- reset fresh at the top of
        # on_full_inflate_clicked, populated in _on_inflate_step_done right after each level's
        # own calibration succeeds. Feeds _guess_pressure_from_history, which _run_inflate_step
        # falls back to whenever a caller doesn't supply its own initial_pressure_guess (i.e.
        # every Full Inflate level after the first -- Diff Inflate's own callers always supply
        # self.last_pressure explicitly instead, bypassing this).
        self.level_history = {}
        # Staged by whichever pipeline path is currently running (on_full_inflate_clicked/
        # _diff_add_face/_diff_remove_face) -- _record_inflate_success adopts it as the new
        # self.last_source_polygon_id once that path reaches a clean Level-3 "Done", but
        # (see _record_inflate_success's own docstring) is never cleared, so it also always
        # tracks "the source_polygon_id for whatever self.base_faces currently is".
        self._pending_source_polygon_id = None
        # Same staging idea as _pending_source_polygon_id above, for pendant (single-edge-
        # attached) face reattachment (2026-09-28, explicit user request -- see
        # _exclude_pendant_faces' own section header comment) -- only ever set by
        # on_full_inflate_clicked (Diff Inflate's own paths explicitly clear it to [], since
        # they don't run pendant exclusion themselves); _on_inflate_step_done's own Level-3
        # "Done" branch consumes it via _reattach_pendant_faces.
        self._pending_pendants = []
        # Whether the CLUB's own insiders (every member except guests, i.e. single-connection
        # members -- see the module docstring's "Club terminology" section) currently reflect a
        # real relax/inflate result, or were only ever geometrically placed
        # (on_full_inflate_clicked's own "place" mode -- see _prepare_mesh_for_inflate's own
        # docstring) -- 2026-09-28, explicit user request, now this app's Rule 2/3: "every time
        # the canvas empties, the is_fully_inflated flag is set to false. every time a full
        # inflate is performed, the flag is set to true... when there is a change to insiders...
        # if is_fully_inflated = true, then do diff inflate. else do full inflate." Diff
        # Inflate's own incremental paths all assume they're seeding from an ALREADY relaxed/
        # calibrated result -- reusing a flat placement's own positions that way would feed
        # real physics a starting point it was never designed for. Checked by
        # on_diff_inflate_clicked, set True whenever _on_inflate_step_done's own Level-3 "Done"
        # branch is reached (a real pressure-calibration pass just ran, whichever pipeline path
        # got it there), set False by on_full_inflate_clicked's own "place" branch AND by
        # refresh_diff_eligibility whenever the club empties out entirely (Rule 2). Left
        # UNCHANGED by _diff_attach_pendant_only -- attaching a guest never touches the
        # insiders either way, so it doesn't change whether they were ever really solved.
        self.is_fully_inflated = False

        # Hover-highlight state (2026-09-19, explicit: "when i mouse over a face in the 3d
        # image, that face should be outlined in yellow in both the 2d view and the 3d view",
        # then "now make the opposite true" -- 2D mouse hover on the left pane also highlights
        # here) -- self._actor_to_group is rebuilt every _render() ({vtk actor: base-face-
        # group-index} for the group each add_mesh call belongs to); self._picker is one reused
        # vtkCellPicker instance (cheap to reuse, no reason to build a fresh one per mouse-move);
        # self._hover_groups/_hover_actors track the CURRENTLY highlighted group(s) and their
        # yellow outline actors (a line actor plus a rounded-joint point-sprite actor per group,
        # see _add_rounded_lines) so _apply_hover_highlight can cheaply add/remove just those
        # instead of re-running the whole _render(). A frozenset, not a single group, because a
        # 2D shape hover (set_hover_shape_from_builder) can map onto SEVERAL 3D groups at once --
        # a Polygon-Fold shape's triangles all share one source_polygon_id but are separate
        # groups.
        self._actor_to_group = {}
        self._picker = vtkCellPicker()
        # self._hover_target_groups is the RAW request from whichever direction last drove
        # hover (a 3D pick or a 2D shape) -- self._hover_groups is that minus whatever's
        # currently SELECTED (below), i.e. what's actually got yellow actors right now. Kept
        # separate so a selection change can recompute the effective set without needing to
        # know which direction last asked for hover.
        self._hover_target_groups = frozenset()
        self._hover_groups = frozenset()
        self._hover_actors = []

        # Click-to-select state (2026-09-19, explicit: "clicking on a face in 3d should select
        # it in both views... multiselect by holding down ctrl", "when you hover then select,
        # the face should go from being highlighted (yellow) to being selected (red)"). Selected
        # shapes are tracked by BUILDER shape_id (self._selected_shape_ids), same identity
        # BuilderPane.selected_ids already uses -- a group index alone can't be the shared
        # identity since a Polygon-Fold shape's several triangle groups all need to select/
        # deselect together as one shape. self._selected_actors are this panel's own red outline
        # actors, same add/remove-just-these-on-change convention as _hover_actors.
        self._selected_shape_ids = set()
        self._selected_actors = []
        # Set by _on_drag_start/_on_drag_motion/_on_drag_end below to tell a genuine
        # rotate-drag apart from a plain click (a press+release with no meaningful motion
        # between them) -- a rotate-drag must never ALSO select whatever's under the cursor.
        self._drag_moved = False

        # Join-mode connection hover/select (2026-09-19, explicit: "in Join[J] mode, hovering
        # over a connection highlights it in yellow and the corresponding edge in 3d is also
        # highlighted... clicking on the connection selects it in both 2d and 3d... similarly,
        # hovering over the 3d edge highlights the corresponding 2d connection and clicking
        # selects both. multiselect is not available in this mode") -- tracked by BUILDER
        # connection id (self.builder_getter().connections' own "id"), the shared identity both
        # panes already key off of. self._connection_edge_cache ({conn_id: segments}, rebuilt
        # every _render() from _connection_edge_segments) is what both the 3D nearest-edge pick
        # (_nearest_connection_at_position) and the highlight actors read from, so it's computed
        # once per render rather than per mouse-move tick.
        self._connection_edge_cache = {}
        self._hover_connection_id = None
        self._hover_connection_actors = []
        self._selected_connection_id = None
        self._selected_connection_actors = []

        # Join-mode 3D connect-by-dragging-edges (2026-09-19, explicit: "let hovering over open
        # edges highlight them in yellow. then you can click down on them... the mouse drags out
        # a connection in screen space (thick line), then it can hover over another edge (which
        # will highlight in yellow), and mouse release causes both to be drawn in red with their
        # midpoint connected in a thick red line (all drawn in 3d). all this persists until
        # simulation converges and redraws"). self._open_edges ({(shape_id, raw_edge): {
        # "shape_id", "raw_edge", "midpoint", "segments"}}) is rebuilt by _rebuild_open_edges --
        # from _render() (a fresh mesh) AND right after a successful create_connection (the mesh
        # itself doesn't change until a later Diff/Full Inflate, but the just-used edge must
        # stop offering itself immediately) -- from the CURRENTLY DISPLAYED mesh's own shape
        # groups crossed with the builder's CURRENT connections (an edge already used by ANY
        # connection is never "open", even one the mesh hasn't visually caught up to yet).
        # "segments" (from _base_edge_vertex_chain, see _open_edge_geometry) is the edge's own
        # ACTUAL (possibly subdivided/curved) boundary, the same geometry every highlight below
        # draws -- not a straight chord between its two corners.
        #
        # EVERY highlight this gesture draws -- the hovered/target edge (yellow), the pressed/
        # confirmed edge(s) (red), and the final midpoint-to-midpoint connecting line -- is now
        # REAL 3D geometry (_edge_highlight_actors, a role-keyed {"hover"/"origin"/"target"/
        # "connecting_line": [actor, ...]} dict, same incremental swap convention as
        # _hover_actors/_selected_actors elsewhere in this file), not a 2D overlay: it follows
        # the edge's own true shape and persists correctly through camera rotate/pan/zoom for as
        # long as Diff/Full Inflate takes to converge in the background -- something a
        # per-frame-repainted 2D overlay isn't designed for. The ONE remaining 2D overlay is the
        # live 3D-native drag's own rubber-band line to the raw cursor position
        # (self._line_end_screen_override, a PANEL-PIXEL point, drawn by _draw_connection_
        # overlays -- 2026-09-19, explicit: "the mouse drags out a connection in screen space").
        self._open_edges = {}
        self._hover_open_edge_key = None
        self._connection_drag = None
        self._edge_highlight_actors = {}
        self._line_end_screen_override = None

        # Every edge highlight + connecting line PROMOTED here once a connection is actually
        # made (2026-09-19, explicit: "all this persists until simulation converges and
        # redraws") -- a plain growing list of actors, since several connections could be made
        # in a row before any Inflate runs; plotter.clear() (the top of every _render()) destroys
        # them wholesale the instant the mesh itself catches up, so this list is just reset to
        # [] alongside that, never pruned actor-by-actor.
        self._pending_made_connection_actors = []

        # The plotter's own render resolution -- starts at PANEL_SIZE but is kept in sync with
        # the panel_label's actual on-screen pixel size by _on_panel_configure below, so the
        # mesh always renders at full native resolution for whatever space it's actually given
        # (2026-09-19, explicit: "the resolution... seems low compared to the other apps" --
        # inflate_polyhedron_app's own panels render at their own fixed, already-correct pixel
        # size; this app's single panel didn't adapt to ITS pane's real, larger size).
        self.panel_size = PANEL_SIZE
        self._resize_after_id = None

        self._center = np.zeros(3)
        self._half = 1.0
        self._camera = {"rotation": self._initial_rotation(), "zoom": 1.0, "pan": np.zeros(2)}
        self._dragging = False
        self._last_xy = None
        self._panning = False
        self._pan_last_xy = None

        self._build_ui()
        self._apply_target_rms_defaults()
        self._render()

    # ---- UI ----

    def _build_icon_button(self, parent, text, command):
        """A flat, borderless icon button -- plain tk.Button, not ttk (2026-09-29, explicit user
        request, reference image: a browser-style back/forward/refresh trio, just the glyphs
        themselves with no visible button box/border around them) -- sv_ttk's own dark theme
        draws every ttk.Button with its own bordered/boxed look that isn't reachable through
        plain style options (would need a custom ttk element/layout), while tk's own Button
        takes flat/no-border/matching-background directly. `self._icon_font` (set once, right
        before the first of these three gets built) is a scaled-up copy of the ordinary default
        font -- big enough that the glyph itself reads as an icon, not a tiny character.
        Disabled state uses `disabledforeground` (plain tk.Button's own built-in dimming, not a
        ttk state map) -- see ICON_BUTTON_DISABLED_FG's own comment."""
        return tk.Button(
            parent, text=text, font=self._icon_font, command=command,
            bg=PLOT_THEME["bg"], fg=PLOT_THEME["fg"],
            activebackground=PLOT_THEME["bg"], activeforeground=PLOT_THEME["fg"],
            disabledforeground=ICON_BUTTON_DISABLED_FG,
            bd=0, relief=tk.FLAT, highlightthickness=0, padx=6, pady=0, cursor="hand2")

    def _build_ui(self):
        # padding=(8, 2, 8, 2), not a plain 8 -- top/bottom dropped 8 -> 4 -> 2 (2026-09-29,
        # explicit user request: "there's too much space between the button bar and the drawing
        # area. close that up (for both left and right panels)", then "still too much"),
        # matching BuilderPane's own header frame so the two stay in lockstep (see
        # _apply_mode_visibility's own tail, which copies this frame's reqheight onto that one).
        self._setup_frame = setup = ttk.Frame(self.root, padding=(8, 2, 8, 2))
        setup.pack(side=tk.TOP, fill=tk.X)

        # One row -- "Target stretch: L1 __ L2 __ L3 __  Tolerance: ___" -- short enough
        # labels/entry widths to fit on a single line even in this pane's own (roughly half-
        # window) width (2026-09-19, explicit: "i want all to fit on one line if possible").
        # Debug-mode-only (2026-09-28, explicit user request -- see _apply_mode_visibility):
        # `self._setup_row` is kept unpacked at the end of _build_ui rather than packed here,
        # then (re-)packed only while debug mode is on.
        self._setup_row = row = ttk.Frame(setup)
        ttk.Label(row, text="Target stretch:").pack(side=tk.LEFT, padx=(0, 4))
        self.target_rms_vars = {}
        self.target_rms_display_vars = {}
        for level in (1, 2, 3):
            ttk.Label(row, text=f"L{level}:").pack(side=tk.LEFT, padx=(8, 2))
            var = tk.DoubleVar(value=round(self._target_rms_defaults[level]))
            self.target_rms_vars[level] = var
            display_var = tk.StringVar(value=f"{var.get():.0f}%")
            self.target_rms_display_vars[level] = display_var
            var.trace_add("write", lambda *_a, lv=level: self._sync_target_rms_display(lv))
            entry = ttk.Entry(row, width=5, textvariable=display_var)
            self._register_numeric_entry(entry, allow_exponent=False, allow_decimal=False)
            entry.bind("<FocusIn>", lambda _e, lv=level: self._begin_edit_target_rms(lv))
            entry.bind("<Return>", lambda _e, lv=level: self._commit_target_rms_entry(lv))
            entry.bind("<FocusOut>", lambda _e, lv=level: self._commit_target_rms_entry(lv))
            entry.pack(side=tk.LEFT)

        ttk.Label(row, text="Tolerance:").pack(side=tk.LEFT, padx=(14, 4))
        self.tolerance_var = tk.StringVar(value=f"{DEFAULT_TOLERANCE:.0e}")
        # width=7 (was 10) -- shorter, still fits "1e-04" plus a couple of extra digits while
        # typing (2026-09-19, explicit: "make the tolerance text box a bit shorter").
        self.tolerance_spin = ttk.Entry(row, width=7, textvariable=self.tolerance_var)
        self._register_numeric_entry(self.tolerance_spin, allow_exponent=True)
        self.tolerance_spin.pack(side=tk.LEFT)

        # Two buttons instead of one "Inflate" (2026-09-19, explicit): "Full Inflate" always
        # runs the complete Level 0-3 pipeline from scratch; "Diff Inflate" reuses the last
        # completed inflate's own Level-3 result and is only enabled when the net has changed
        # by exactly one added/removed shape since then (see refresh_diff_eligibility, module
        # docstring's own "Full Inflate vs. Diff Inflate" section).
        # `self._button_row` itself is always packed (it also holds the release-mode-only
        # Reinflate button below); the three debug-only widgets inside it are individually
        # packed/unpacked by _apply_mode_visibility instead of the whole row.
        self._button_row = button_row = ttk.Frame(setup)
        button_row.pack(side=tk.TOP, anchor=tk.W, pady=(8, 0))
        self.full_inflate_button = ttk.Button(
            button_row, text="Full Inflate", command=self.on_full_inflate_clicked)
        self.diff_inflate_button = ttk.Button(
            button_row, text="Diff Inflate", command=self.on_diff_inflate_clicked)
        self.diff_inflate_button.state(["disabled"])
        # Default checked (2026-09-19, explicit) -- whenever refresh_diff_eligibility finds a
        # single-face/connection add/remove since the last completed inflate (the SAME
        # DIFF_ELIGIBLE_KINDS check the button's own enabled state uses), it fires Diff Inflate
        # automatically instead of just enabling the button. Debug-mode-only UI (see
        # _apply_mode_visibility) -- release mode instead always behaves as if this were
        # checked (2026-09-28, explicit user request: "remove... auto inflate in its release
        # mode" means the CONTROL, not the behavior -- see _effective_auto_inflate), with
        # "Reinflate" below as its manual force-a-clean-Full-Inflate escape hatch.
        self.auto_inflate_var = tk.BooleanVar(value=True)
        self._auto_inflate_check = ttk.Checkbutton(
            button_row, text="Auto Inflate", variable=self.auto_inflate_var)

        # Debug-mode-only replay scrubber (2026-09-29, explicit user request -- "add a replay
        # slider... to replay the last full/diff inflate", "put it after Auto Inflate"): ranges
        # over self._replay_frames (populated across the whole last completed run -- see
        # _capture_replay_frame/_update_replay_slider), disabled/empty until one exists.
        # length=140 -- short enough to leave room for the other button_row widgets alongside
        # it, long enough to scrub usefully.
        self._replay_slider = ttk.Scale(
            button_row, from_=0, to=0, orient=tk.HORIZONTAL, length=140,
            command=self._on_replay_slider_moved)
        self._replay_slider.state(["disabled"])

        # Debug-mode-only diagnostics (2026-09-29, explicit user request -- diagnosing a
        # crumpled guest boundary after a Diff Inflate join): same idea as
        # inflate_polyhedron_app's own identically-named toggles, see _render's own overlay
        # block for what each actually draws. command=self._render (not a separate redraw path)
        # since this pane has exactly one panel/one _render, unlike that app's per-level draw().
        # Own ROW (self._debug_overlay_row), not packed into button_row -- three extra labeled
        # checkbuttons alongside Full/Diff Inflate/Auto Inflate didn't fit on one line (2026-09-29,
        # explicit user request: "those three checkboxes need to be on another line").
        self._debug_overlay_row = overlay_row = ttk.Frame(setup)
        self.show_normals_var = tk.BooleanVar(value=False)
        self._show_normals_check = ttk.Checkbutton(
            overlay_row, text="Show face normals", variable=self.show_normals_var,
            command=self._render)
        self.show_vertex_normals_var = tk.BooleanVar(value=False)
        self._show_vertex_normals_check = ttk.Checkbutton(
            overlay_row, text="Show vertex normals", variable=self.show_vertex_normals_var,
            command=self._render)
        self.show_repulsive_forces_var = tk.BooleanVar(value=False)
        self._show_repulsive_forces_check = ttk.Checkbutton(
            overlay_row, text="Show repulsive forces", variable=self.show_repulsive_forces_var,
            command=self._render)
        # Release-mode-only (see _apply_mode_visibility): "basically Full Inflate" (2026-09-28,
        # explicit user request) -- same command, just the one button a release-mode user needs,
        # since auto-inflate already keeps the mesh current without any button in that mode.
        # A plain Unicode glyph (REFRESH_ICON_TEXT), not the word "Reinflate" (2026-09-29,
        # explicit user request: "replace the reinflate button with an icon button like the
        # refresh button in browsers") -- _set_running's own text swap to "Stop"/back is
        # unaffected (still plain text, just a different idle-state string, see its own
        # docstring). self._icon_font (own docstring on _build_icon_button) is what actually
        # makes the glyph read as a real icon instead of a tiny default-size character -- sized
        # (2026-09-29, explicit user request: "make the undo/redo/refresh button icons bigger,
        # about the size of the polygon buttons") so the resulting button widget lands close to
        # INFLATER_ICON_SIZE (56px) square, same as one of the palette icons above, not just a
        # fixed multiple of the ordinary UI text size -- a plain scale factor undershot badly
        # once actually measured (1.6x the default 9pt only produced a ~20px-tall button).
        self._icon_font = tkfont.nametofont("TkDefaultFont").copy()
        self._icon_font.configure(size=20)
        # Undo/redo (2026-09-29, explicit user request: "also have an undo and redo button to
        # the left of it. the undo/redo buttons are greyed out when there's nothing to undo/
        # redo") -- BuilderPane.on_undo_key/on_redo_key are the exact same actions Ctrl+Z/Ctrl+Y
        # already call (see _build_ui's own _bind_all_guarded calls); already lock-guarded on
        # their own (BuilderPane.on_undo_key/on_redo_key each start with `if self._locked:
        # return`), so a stray click while an inflate is running is harmless even before
        # _refresh_undo_redo_buttons' own disabling below takes effect. Enabled state itself is
        # kept current by _refresh_undo_redo_buttons, called after every builder edit
        # (refresh_diff_eligibility) and on every _set_running transition -- starts disabled
        # here (both stacks are empty on a fresh pane) until that first real call.
        self.undo_button = self._build_icon_button(
            button_row, UNDO_ICON_TEXT, lambda: self.builder_getter().on_undo_key())
        self.redo_button = self._build_icon_button(
            button_row, REDO_ICON_TEXT, lambda: self.builder_getter().on_redo_key())
        self.undo_button.config(state=tk.DISABLED)
        self.redo_button.config(state=tk.DISABLED)
        self.reinflate_button = self._build_icon_button(
            button_row, REFRESH_ICON_TEXT, self.on_full_inflate_clicked)

        self.status_label = ttk.Label(self.root, anchor="w", padding=(8, 3))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # highlightthickness=1/highlightbackground (2026-09-29, explicit user request: "the 3d
        # view should also have a box around it") -- same border convention BuilderPane's own
        # 2D canvas already uses, so both panes read as matching framed panels.
        self.panel_label = tk.Label(self.root, bg=PLOT_THEME["bg"], bd=0,
                                     width=PANEL_SIZE[0], height=PANEL_SIZE[1],
                                     highlightthickness=1, highlightbackground=PLOT_THEME["fg"])
        self.panel_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.plotter = pv.Plotter(off_screen=True, window_size=list(self.panel_size))
        self.plotter.set_background(PLOT_THEME["bg"])
        self._setup_plotter_lighting()
        self._photo = None
        self.panel_label.bind("<Configure>", self._on_panel_configure)

        # Left-drag rotates (trackball), right-drag pans, middle-click resets, wheel zooms --
        # same gesture set as inflate_polyhedron_app's own "Level N" panels, reimplemented for
        # this app's one single panel (2026-09-19, explicit: "the 3d object is not rotatable/
        # movable/scaling right now").
        self.panel_label.bind("<ButtonPress-1>", self._on_drag_start)
        self.panel_label.bind("<B1-Motion>", self._on_drag_motion)
        self.panel_label.bind("<ButtonRelease-1>", self._on_drag_end)
        self.panel_label.bind("<ButtonPress-3>", self._on_pan_start)
        self.panel_label.bind("<B3-Motion>", self._on_pan_motion)
        self.panel_label.bind("<ButtonRelease-3>", self._on_pan_end)
        self.panel_label.bind("<Button-2>", self._on_camera_reset)
        self.panel_label.bind("<MouseWheel>", self._on_scroll)
        self.panel_label.bind("<Button-4>", self._on_scroll)
        self.panel_label.bind("<Button-5>", self._on_scroll)
        self.panel_label.bind("<Motion>", self._on_panel_hover_motion)
        self.panel_label.bind("<Leave>", self._on_panel_hover_leave)

        self._apply_mode_visibility()

    def _effective_auto_inflate(self):
        """Whether an eligible builder edit should auto-fire an inflate right now (2026-09-28,
        explicit user request). Debug mode: exactly self.auto_inflate_var (the visible
        checkbox, user-controlled, default True). Release mode: always True -- that mode has no
        checkbox at all (see _apply_mode_visibility), "removing auto inflate" there means
        removing the CONTROL, not the behavior itself -- a release-mode user just builds/edits
        and watches it inflate, with Reinflate as a manual force-a-clean-Full-Inflate escape
        hatch, never needing to babysit a toggle."""
        if not self.builder_getter().debug_mode:
            return True
        return self.auto_inflate_var.get()

    def _apply_mode_visibility(self):
        """Debug mode ('d' key, shared with BuilderPane's own toggle -- see BuilderPane.
        on_debug_mode_change) shows the target-stretch/tolerance row plus Full Inflate/Diff
        Inflate/Auto Inflate; release mode (the default) hides all of those and shows just
        Reinflate instead (2026-09-28, explicit user request: "remove all the target stretch,
        tolerance, full/diff inflate buttons and auto inflate in its release mode... just have
        a 'reinflate' which basically is 'full inflate'"). Called once at the end of _build_ui
        (release mode is the startup default) and again every time debug mode flips."""
        debug = self.builder_getter().debug_mode
        if debug:
            # button_row's own pady back to its ORIGINAL (8, 0) -- debug mode has _setup_row
            # (the target-stretch/tolerance row) packed above it, so it still needs its own gap
            # underneath that row; see the `else` branch's own comment for why release mode
            # needs something different here.
            self._button_row.pack_configure(pady=(8, 0))
            self._setup_row.pack(side=tk.TOP, anchor=tk.W)
            self.full_inflate_button.pack(side=tk.LEFT)
            self.diff_inflate_button.pack(side=tk.LEFT, padx=(8, 0))
            self._auto_inflate_check.pack(side=tk.LEFT, padx=(8, 0))
            self._replay_slider.pack(side=tk.LEFT, padx=(8, 0))
            self._debug_overlay_row.pack(side=tk.TOP, anchor=tk.W, pady=(4, 0))
            self._show_normals_check.pack(side=tk.LEFT)
            self._show_vertex_normals_check.pack(side=tk.LEFT, padx=(8, 0))
            self._show_repulsive_forces_check.pack(side=tk.LEFT, padx=(8, 0))
            self.undo_button.pack_forget()
            self.redo_button.pack_forget()
            self.reinflate_button.pack_forget()
        else:
            self._setup_row.pack_forget()
            self.full_inflate_button.pack_forget()
            self.diff_inflate_button.pack_forget()
            self._auto_inflate_check.pack_forget()
            self._replay_slider.pack_forget()
            self._debug_overlay_row.pack_forget()
            # button_row's own pady dropped to (0, 0) here (2026-09-29, explicit user request:
            # "the 3 buttons on the right need to be shifted a bit higher", then "decrease the
            # margin below the buttons so the space above and below the buttons are equal") --
            # release mode has no _setup_row above it to leave a gap under, so this pane's own
            # header only needs self._setup_frame's own outer padding (top/bottom both 4, see
            # its own comment) above/below button_row -- with no extra pady of its own on either
            # side, that margin is already equal top vs bottom by construction. The two panes'
            # header HEIGHTS still get kept equal regardless (see this method's own tail), so
            # BuilderPane's palette row shrinks its own gap to match automatically.
            self._button_row.pack_configure(pady=(0, 0))
            # Undo/redo to the LEFT of the refresh-icon Reinflate button (2026-09-29, explicit
            # user request) -- release mode's own button row, in this order.
            self.undo_button.pack(side=tk.LEFT)
            self.redo_button.pack(side=tk.LEFT, padx=(4, 8))
            self.reinflate_button.pack(side=tk.LEFT)
            # Off, not just hidden, when leaving debug mode -- same as inflate_polyhedron_app's
            # own _apply_mode_visibility -- so a stale overlay never lingers into release mode.
            redraw_needed = False
            for var in (self.show_normals_var, self.show_vertex_normals_var,
                        self.show_repulsive_forces_var):
                if var.get():
                    var.set(False)
                    redraw_needed = True
            if self._replay_scrub_index is not None:
                self._replay_scrub_index = None
                redraw_needed = True
            if redraw_needed and self.faces is not None:
                self._render()
        # Keeps BuilderPane's own header frame (self._header_frame, the palette row's own
        # container) exactly as tall as THIS pane's own header (self._setup_frame) -- whichever
        # is taller right now (2026-09-29, explicit user request: "the 2d and 3d canvas boxes
        # are not aligned at the top") -- so self.canvas's own top border and self.panel_label's
        # own always land on the same row, regardless of which mode is showing here (debug's own
        # extra rows make this header taller than release's). winfo_reqheight() needs a fresh
        # geometry pass first (update_idletasks, not a full update -- no event processing, just
        # geometry) to reflect the packing changes just made above, not whatever it measured
        # last time. BuilderPane._build_ui's own pack_propagate(False) on that frame is what
        # makes an externally-assigned height actually stick instead of being overridden back to
        # fit its own content on the next redraw.
        self.root.update_idletasks()
        self.builder_getter()._header_frame.configure(height=self._setup_frame.winfo_reqheight())

    def _register_numeric_entry(self, entry, allow_exponent, allow_decimal=True):
        vcmd = self.root.register(lambda proposed: _is_valid_numeric_partial(
            proposed, allow_exponent, allow_decimal))
        entry.configure(validate="key", validatecommand=(vcmd, "%P"))

    def _is_central_object_closed(self):
        """True iff the BUILDER's current central object (builder_getter().export_mesh_dict())
        has no free/unglued edge anywhere -- read straight off the LIVE 2D builder state, not
        off whatever was last actually inflated, so this stays correct even before the very
        first Inflate click. False (treated as "open") whenever there's nothing to inflate yet
        (export_mesh_dict returns (None, message) -- see its own docstring) or the net fails
        validation, since neither case has a real closed shape to claim."""
        mesh, error = self.builder_getter().export_mesh_dict()
        if mesh is None:
            return False
        return not _open_base_edges(mesh["faces"], mesh["face_edge_ids"])

    def _repulsion_vertex_ids(self):
        """Same as inflate_polyhedron_app's own _repulsion_vertex_ids (duplicated, not imported
        -- see module docstring): each ORIGINAL polygon's own raw corners, straight from
        self.base_faces -- a small, FIXED set, unaffected by self.subdivision_level, passed as
        every level's own `repulsion_vertex_ids` in _run_inflate_step (2026-09-28, bug fix --
        this call used to omit repulsion_vertex_ids entirely, so repulsion_force ran against
        EVERY Level 2/3 vertex instead of this small fixed set, an O(n^2) blowup that was the
        actual cause of a reported "Level 3 got much slower" regression)."""
        return sorted({v for face in self.base_faces for v in face})

    def _closed_repulsion_vertex_ids(self):
        """Same as inflate_polyhedron_app's own _closed_repulsion_vertex_ids (duplicated, not
        imported -- see module docstring): the subset of _repulsion_vertex_ids that are NOT an
        endpoint of any free (unglued) base-polygon edge."""
        repulsion_ids = self._repulsion_vertex_ids()
        open_edges_by_base = _open_base_edges(self.base_faces, self.base_face_edge_ids)
        open_vertices = set()
        for pairs in open_edges_by_base.values():
            for pair in pairs:
                open_vertices.update(pair)
        return {v for v in repulsion_ids if v not in open_vertices}

    def _repulsion_vertex_multipliers(self):
        """Same as inflate_polyhedron_app's own _repulsion_vertex_multipliers (duplicated, not
        imported -- see module docstring): {vertex_id: multiplier} for every CLOSED repulsion
        vertex, 1.0 at Level 1, halved at every level after that. None when every repulsion
        vertex is open."""
        closed = self._closed_repulsion_vertex_ids()
        if not closed:
            return None
        factor = 1.0 / (2 ** max(0, self.subdivision_level - 1))
        return {v: factor for v in closed}

    def _level1_is_open(self):
        """Same as inflate_polyhedron_app's own _level1_is_open (duplicated, not imported --
        see module docstring): True/False per LEVEL-1 fine triangle (same order
        _build_level1_topology's own `faces` would be) -- whether THAT SPECIFIC wedge's own
        outer rim edge (the one opposite the fan hub, corresponding to exactly one edge of its
        own original polygon) is free ("open") rather than glued to a neighbor ("closed") -- an
        n-gon connected at 2 of its own edges triangulates into 2 closed wedges and n-2 open
        ones, classified per WEDGE, not per whole polygon. The fan hub is the one vertex every
        one of a base polygon's own wedges has in common; a wedge's own rim edge is then just
        its other two vertices."""
        level1_faces, _edge_length, level1_face_of_fine = _build_level1_topology(self.base_faces)
        open_edges = _open_base_edges(self.base_faces, self.base_face_edge_ids)
        verts_by_base = {}
        for face, base_idx in zip(level1_faces, level1_face_of_fine):
            verts = set(face)
            verts_by_base[base_idx] = (verts if base_idx not in verts_by_base
                                        else verts_by_base[base_idx] & verts)
        hub_by_base = {i: next(iter(s)) for i, s in verts_by_base.items() if len(s) == 1}
        flags = []
        for face, base_idx in zip(level1_faces, level1_face_of_fine):
            hub = hub_by_base.get(base_idx)
            if hub is None:
                flags.append(False)  # no well-defined single hub -- default to "closed"/participating
                continue
            rim_pair = frozenset(v for v in face if v != hub)
            flags.append(rim_pair in open_edges.get(base_idx, ()))
        return flags

    def _is_open_of_fine(self, level=None):
        """Same as inflate_polyhedron_app's own _is_open_of_fine (duplicated, not imported --
        see module docstring): is_open flags parallel to self.faces at `level`
        (self.subdivision_level if not given) -- _level1_is_open's own result, repeated 4x per
        Subdivide since Level 1 (mirroring exactly how mesh_levels._quarter_triangles itself
        propagates face_of_fine -- every old triangle's 4 children are appended contiguously,
        in old-index order -- so a parallel array only needs the same repeat-4x-in-order
        treatment to stay aligned). Level 0 shares Level 1's own topology, so `level <= 1` both
        mean zero repeats."""
        if level is None:
            level = self.subdivision_level
        flags = self._level1_is_open()
        for _ in range(max(0, level - 1)):
            flags = [f for f in flags for _ in range(4)]
        return flags

    def _rms_exclude_edges(self):
        """Same as inflate_polyhedron_app's own _rms_exclude_edges (duplicated, not imported --
        see module docstring): (a, b) sorted vertex-id-pair tuples, at the CURRENT subdivision
        level, to exclude from the RMS Stretch % calculation -- every edge of every OPEN fine
        triangle (see _is_open_of_fine), not just its own free edge: an open wedge triangle
        doesn't participate in the RMS stretch % calculation at all (2026-09-29, explicit bug
        report -- goose.poly, an open/semi-closed net, converged in inflate_polyhedron_app but
        not here; this exclusion -- entirely missing from this app until now -- was the actual
        cause: without it, an open wedge's own unconstrained, naturally-higher stretch never
        lets the RMS convergence check settle below gtol, so relax_initial_configuration/
        estimate_pressure_for_target_stretch just grind to their own step caps and report
        "failed to converge" on a net that genuinely has nothing wrong with it). None (rather
        than an empty set) when nothing in the net is open, so callers can skip the exclusion
        machinery entirely."""
        is_open = self._is_open_of_fine()
        if not any(is_open):
            return None
        exclude = set()
        for face, open_flag in zip(self.faces, is_open):
            if open_flag:
                n = len(face)
                for k in range(n):
                    exclude.add(tuple(sorted((face[k], face[(k + 1) % n]))))
        return exclude

    def _pressure_exclude_faces(self):
        """Same as inflate_polyhedron_app's own _pressure_exclude_faces (duplicated, not
        imported -- see module docstring): Boolean list parallel to self.faces AT THE CURRENT
        subdivision_level -- True for every OPEN fine triangle (see _is_open_of_fine), which
        should feel NO pressure/inflation force at all (2026-09-29, explicit bug report -- see
        _rms_exclude_edges' own docstring for the goose.poly non-convergence this and that
        together fix), while still fully existing for springs/repulsion/edges/convergence.
        None when nothing in the net is open, so callers can skip the exclusion machinery
        entirely."""
        is_open = self._is_open_of_fine()
        return is_open if any(is_open) else None

    def _apply_target_rms_defaults(self):
        """Re-picks LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED/_OPEN from _is_central_object_closed and
        writes it straight into every level's Target RMS spinner (2026-09-28, explicit user
        request: "checked after every change") -- called from refresh_diff_eligibility, so this
        runs on every builder edit, not just once at startup. Unlike inflate_polyhedron_app's
        own _reset_target_rms_defaults (which only re-applies when the NET FILE changes, to
        avoid clobbering a hand-typed value -- see its own comment), this app's own spec asks
        for it every time, since a live-edited shape's open/closed status can flip on any edit
        and there's no separate "net just loaded" moment to gate on here."""
        self._target_rms_defaults = (LEVEL_DEFAULT_TARGET_RMS_PCT_CLOSED
                                      if self._is_central_object_closed()
                                      else LEVEL_DEFAULT_TARGET_RMS_PCT_OPEN)
        for level, var in self.target_rms_vars.items():
            var.set(round(self._target_rms_defaults[level]))

    def _begin_edit_target_rms(self, level):
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}")

    def _sync_target_rms_display(self, level):
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}%")

    def _commit_target_rms_entry(self, level, _event=None):
        try:
            value = round(float(self.target_rms_display_vars[level].get()))
        except (tk.TclError, ValueError):
            value = self._target_rms_defaults[level]
        self.target_rms_vars[level].set(max(0, min(100, value)))

    def _get_tolerance(self):
        try:
            return float(self.tolerance_var.get())
        except ValueError:
            return DEFAULT_TOLERANCE

    def _set_status(self, text, kind="info"):
        self.status_label.config(text=text, foreground=STATUS_COLORS.get(kind, STATUS_COLORS["info"]))

    def _pipeline_label(self):
        """'Full Inflate' or 'Diff Inflate', matching self._active_button -- every in-run status
        message is prefixed with this (2026-09-28, explicit user request: "it should say
        whether it's doing Full Inflate (and which level) or Diff Inflate") so it's never
        ambiguous which pipeline is actually running, including when on_diff_inflate_clicked
        redirected an ordinary edit into a real Full Inflate (self._active_button reads "full"
        for one of those too, same as a manual Full Inflate/Reinflate click -- see
        self._diff_redirect_pending's own comment) -- the user should see "Full Inflate" and
        know why it's starting from Level 0, not be left guessing whether it's a bug. Read
        only while self._active_button is actually set (i.e. mid-run); harmless default of
        "Diff Inflate" otherwise, since nothing calls this outside a run.

        Prefixed with self._change_label when set (2026-09-28, explicit user request: "Insider
        added/deleted/modified: diff inflate" / "Insiders added/deleted/modified: full inflate
        -- Level x: Step xx" -- see _describe_change's own docstring for how that label is
        derived), e.g. "Insider modified: Diff Inflate -- Level 3: calibrating...". Bare
        "Full Inflate"/"Diff Inflate" (no prefix) for a run with no single triggering change to
        describe (a manual Full Inflate/Reinflate/Stop click, or on_load_success)."""
        base = "Full Inflate" if self._active_button == "full" else "Diff Inflate"
        return f"{self._change_label}: {base}" if self._change_label else base

    def _describe_change(self, kind, extra):
        """Returns a short label ("Anchor piece"/"Insider(s) added"/"Insider(s) deleted"/
        "Insider modified"/"Guest(s) added"/"Guest(s) deleted") for `kind`/`extra` (as returned
        by BuilderPane.classify_change) -- see the module's own "Club terminology" section for
        what these mean, and _pipeline_label for where this gets used. None for a kind this
        doesn't describe (only ever called with a DIFF_ELIGIBLE_KINDS value or "add_face" for a
        guest attach, never "none"/"complex").

        "add_face": a brand new shape, so ITS OWN connection count IS its own glued-edge count
        (see _is_pendant_add's own reasoning). 0 connections means this is the very first piece
        ever placed (nothing else exists yet to connect to) -- "Anchor piece". Exactly 1
        connection is ordinarily a guest add, UNLESS that one neighbor itself only had exactly
        1 OTHER connection before this -- then the neighbor is PROMOTED from guest to insider
        by this same edit (see _is_pendant_add's own docstring), so it's really an insider
        change, not a guest one. 2+ connections (rare, but possible) is a genuine insider add.

        "remove_face": `extra` is the SET of removed shape ids -- gone now, so their own former
        connection counts are read from self.last_connections_snapshot (the net as of the last
        successful inflate, the correct "before" reference point for a single diff-eligible
        edit). Counts as an insider change if any removed member itself had >= 2 connections
        THEN, or if removing it drops some SURVIVING neighbor that had exactly 2 down to 1
        (demoting that neighbor from insider to guest) -- otherwise every removed member (and
        anything it touched) was already guest-level, so it's a guest removal.

        "add_connection"/"remove_connection": always an insider change -- these only ever run
        between two members ALREADY in the club (see classify_change's own docstring), and
        changing a connection between them is exactly Rule 3's "their internal connections"."""
        builder = self.builder_getter()
        if kind == "add_face":
            new_shape_id = extra
            connections = builder.connections
            my_conns = [c for c in connections
                        if c["a_shape"] == new_shape_id or c["b_shape"] == new_shape_id]
            if not my_conns:
                return "Anchor piece"
            if len(my_conns) == 1:
                conn = my_conns[0]
                neighbor_id = (conn["b_shape"] if conn["a_shape"] == new_shape_id
                                else conn["a_shape"])
                neighbor_other = sum(
                    1 for c in connections if c["id"] != conn["id"]
                    and (c["a_shape"] == neighbor_id or c["b_shape"] == neighbor_id))
                # A guest is 0 OR 1 connections -- the neighbor stays a guest itself (0 -> 1,
                # a mutual guest pair) iff it had ZERO other connections before this one; it's
                # promoted to insider (1 -> 2) iff it had EXACTLY one. 2+ already meant it was
                # already an insider, unaffected either way.
                if neighbor_other != 1:
                    return "Guest added"
            return "Insider added"
        if kind == "remove_face":
            removed_ids = set(extra)
            word = "Insider" if len(removed_ids) == 1 else "Insiders"
            old_conns = self.last_connections_snapshot or []

            def count_of(shape_id):
                return sum(1 for c in old_conns
                           if c["a_shape"] == shape_id or c["b_shape"] == shape_id)

            if any(count_of(sid) >= 2 for sid in removed_ids):
                return f"{word} deleted"
            for c in old_conns:
                other = None
                if c["a_shape"] in removed_ids and c["b_shape"] not in removed_ids:
                    other = c["b_shape"]
                elif c["b_shape"] in removed_ids and c["a_shape"] not in removed_ids:
                    other = c["a_shape"]
                if other is not None and count_of(other) == 2:
                    return f"{word} deleted"
            guest_word = "Guest" if len(removed_ids) == 1 else "Guests"
            return f"{guest_word} deleted"
        if kind in ("add_connection", "remove_connection"):
            return "Insider modified"
        return None

    def _set_running(self, running, active=None):
        """running=True: `active` ("full" or "diff") is whichever button was clicked -- that
        button switches to "Stop" (still enabled, now wired to _on_stop_clicked), the OTHER one
        disables. running=False: both buttons return to their normal text/command
        (2026-09-19, explicit: "After Diff Inflate or Full Inflate are clicked, they should
        change to Stop so that the user can stop the simulation"). Either way, also locks/
        unlocks the LEFT pane (BuilderPane.set_locked) -- while an inflate of any kind is
        running, the net stays read-only (move/rotate/pan/the 3D camera still work; add/
        delete/connect don't) so a mid-computation edit can never invalidate the mesh the
        background thread is actively working on (2026-09-19, explicit).

        `self.reinflate_button` (release mode's own stand-in for Full Inflate, see
        _apply_mode_visibility) is kept in lockstep with `self.full_inflate_button` here too,
        always, regardless of which mode is CURRENTLY visible -- cheap (only one of the two is
        ever packed at a time) and means a Reinflate click in release mode still gets a real,
        visible Stop while it runs, instead of the invisible debug-mode button silently
        becoming unclickable "Stop" text no one can see (2026-09-28, explicit user request's
        own Reinflate button needs to behave exactly like Full Inflate, Stop included)."""
        self._running = running
        if running:
            # A brand new run's own frames haven't been captured yet -- discard whatever the
            # PREVIOUS run left in the scrubber right away (not just on success/revert) so it
            # can never be scrubbed mid-run, when self.faces/positions are actively changing
            # underneath it.
            self._replay_frames = []
            self._update_replay_slider()
            self._active_button = active
            active_btn = self.full_inflate_button if active == "full" else self.diff_inflate_button
            other_btn = self.diff_inflate_button if active == "full" else self.full_inflate_button
            active_btn.config(text="Stop", command=self._on_stop_clicked)
            active_btn.state(["!disabled"])
            other_btn.state(["disabled"])
            # "Stop" regardless of whether THIS run is "full" or "diff" -- release mode has no
            # separate Diff Inflate button of its own to show a Stop on, so an auto-fired Diff
            # Inflate (see _effective_auto_inflate) needs Reinflate itself to double as the only
            # visible way to interrupt it, not just runs it itself started. The ordinary default
            # font (not self._icon_font) while it reads "Stop" -- that word in the icon's own
            # oversized font would look wrong; back to the icon font once idle, below.
            self.reinflate_button.config(text="Stop", command=self._on_stop_clicked,
                                          font=tkfont.nametofont("TkDefaultFont"))
            self.reinflate_button.config(state=tk.NORMAL)
        else:
            self._active_button = None
            # Cleared here, not in _revert_run alone, so it can't leak into a LATER, unrelated
            # run -- every run's end (success via _on_inflate_step_done's Done branch, or
            # failure via _revert_run) passes through here exactly once, and _revert_run itself
            # already reads this flag's value (into its own local `was_diff`) before calling
            # this method, so clearing it here is always safe (see _diff_redirect_pending's own
            # init comment).
            self._diff_redirect_pending = False
            self.full_inflate_button.config(text="Full Inflate", command=self.on_full_inflate_clicked)
            self.full_inflate_button.state(["!disabled"])
            self.diff_inflate_button.config(text="Diff Inflate", command=self.on_diff_inflate_clicked)
            self.reinflate_button.config(text=REFRESH_ICON_TEXT, command=self.on_full_inflate_clicked,
                                          font=self._icon_font)
            self.reinflate_button.config(state=tk.NORMAL)
        if not running:
            # Drops whatever _stage_kept_selection staged directly into these two fields for
            # the run that just ended (2026-09-29, explicit user request -- see that method's
            # own docstring) -- BuilderPane.set_locked's own unlock branch (called right below)
            # clears its OWN parallel ghost fields the same way, for the same reason: the run is
            # over, so there's nothing left to keep specially outlined. Harmless no-op if
            # nothing was ever staged (the common case, every OTHER kind of run).
            self._selected_shape_ids = set()
            self._selected_connection_id = None
            self._apply_selection_highlight()
            self._apply_connection_selection_highlight()
        self.builder_getter().set_locked(running)
        # Undo/redo need refreshing on BOTH transitions (2026-09-29, explicit user request: "the
        # undo/redo buttons are greyed out when there's nothing to undo/redo") -- set_locked's
        # own call to _refresh_vme_state (which cascades into refresh_diff_eligibility, see its
        # own _refresh_undo_redo_buttons call) only fires on UNLOCK, never on lock, so this would
        # otherwise leave both buttons wrongly enabled for the whole duration of a run.
        self._refresh_undo_redo_buttons()
        if not running:
            self.refresh_diff_eligibility()

    def _on_stop_clicked(self):
        """Signals the running background computation to stop at its next checked point
        (self._stop_event, forwarded as every relax/calibration call's own stop_event=) --
        the actual revert happens once that call's on_done callback runs and sees
        self._stop_requested (see _on_relax_done/_on_inflate_step_done), not here, since the
        worker thread needs to actually unwind first."""
        if not self._running or self._stop_requested:
            return
        self._stop_requested = True
        if self._stop_event is not None:
            self._stop_event.set()
        self._set_status("Stopping...", "info")

    def _snapshot_mesh_state(self):
        """Every mutable mesh-related field, as of right now -- taken at the top of
        on_full_inflate_clicked/_diff_remove_face/_diff_reexport_and_relax, before any of them
        touch self.faces/positions/etc., so a Stop click or a non-converged trial can revert
        to exactly the state the user had when they clicked Inflate (2026-09-19, explicit).
        A plain shallow copy is safe: every pipeline step REASSIGNS these fields wholesale
        (subdivide_once/relax_once/estimate_pressure_for_target_stretch all return fresh
        list/dict objects) rather than mutating one in place, so the objects this snapshot
        still points at never change out from under it.

        Also carries "builder_connections" -- the LIVE builder's own connections list, copied
        here too (never restored by _restore_mesh_state, which only touches this pane's own
        mesh fields) purely so _display_connections has something to serve while the run is in
        flight: the ONE 2D edit that made a Diff Inflate run eligible has already been applied
        to the live builder net by the time this snapshot is taken, so `builder.connections`
        itself is already the NEW list -- same "computed but not yet shown" mismatch as
        self._pending_source_polygon_id (see _display_pending_source_polygon_id's own
        docstring), just on the BuilderPane side instead of this one's."""
        return {
            "base_faces": self.base_faces, "base_edges": self.base_edges,
            "base_face_edge_ids": self.base_face_edge_ids, "faces": self.faces,
            "edge_length": self.edge_length, "face_of_fine": self.face_of_fine,
            "edges": self.edges, "positions": self.positions,
            "subdivision_level": self.subdivision_level,
            "pending_source_polygon_id": self._pending_source_polygon_id,
            "pending_pendants": self._pending_pendants,
            "is_fully_inflated": self.is_fully_inflated,
            "builder_connections": list(self.builder_getter().connections),
        }

    def _restore_mesh_state(self, snapshot):
        self.base_faces = snapshot["base_faces"]
        self.base_edges = snapshot["base_edges"]
        self.base_face_edge_ids = snapshot["base_face_edge_ids"]
        self.faces = snapshot["faces"]
        self.edge_length = snapshot["edge_length"]
        self.face_of_fine = snapshot["face_of_fine"]
        self.edges = snapshot["edges"]
        self.positions = snapshot["positions"]
        self.subdivision_level = snapshot["subdivision_level"]
        self._pending_source_polygon_id = snapshot["pending_source_polygon_id"]
        self.is_fully_inflated = snapshot["is_fully_inflated"]
        self._pending_pendants = snapshot["pending_pendants"]

    def _revert_run(self, status_text, popup_text=None):
        """Discards whatever the current run computed and restores self._pre_click_snapshot --
        shared by a user Stop click, a trial that didn't converge within its own step cap, a
        pressure search that never found a workable pressure at all, and a background-thread
        exception (2026-09-19, explicit: "just go back to the state you started with when you
        pressed the button. discard anything that was computed" / "show a popup letting the
        user know the configuration did not converge and prompt them to anchor any faces that
        might be loosely attached and try again"). `popup_text`, if given, shows a
        messagebox.showwarning in addition to the status line -- used for a genuine non-
        convergence/divergence outcome, not a plain user-requested Stop (which doesn't need a
        popup telling the user what they themselves just did).

        A reverted DIFF run (self._active_button == "diff") ALSO undoes the single 2D edit
        that made it eligible in the first place (2026-09-19, explicit: "if a simulation ends
        up diverging or if the user stops it, it should also revert to the state before the
        simulation (which means undoing one action when in auto mode)") -- Diff Inflate is, BY
        DEFINITION (BuilderPane.classify_change/DIFF_ELIGIBLE_KINDS), only ever eligible when
        the net differs from the last successful inflate by EXACTLY one added/removed face or
        connection, so "the edit" is unambiguous: whatever's on top of the undo stack. Calls
        InteractiveBuilderApp.on_undo_key DIRECTLY (the unbound base method, bypassing
        BuilderPane's own `if self._locked: return` guard) rather than through
        BuilderPane.on_undo_key -- this needs to run WHILE STILL LOCKED (self._set_running(False)
        hasn't run yet), specifically so refresh_diff_eligibility's own early-out
        (`if self._running: return`, still True here) suppresses its Auto-Inflate retrigger
        until AFTER the net is back to the last known-good state -- undoing AFTER unlocking
        would instead let that retrigger fire ONE MORE TIME against the still-broken edit,
        immediately re-running (and re-failing) the exact same doomed calibration."""
        if self._pre_click_snapshot is not None:
            self._restore_mesh_state(self._pre_click_snapshot)
        self._pre_click_snapshot = None
        self._stop_event = None
        self._stop_requested = False
        # A reverted run's own frames describe a mesh state that no longer exists (the restore
        # above just discarded it) -- discard the replay history right along with it rather
        # than leaving the scrubber pointing at a run that never actually completed.
        self._replay_frames = []
        self._update_replay_slider()
        # self._diff_redirect_pending covers on_diff_inflate_clicked's own redirect into a real
        # Full Inflate (self._active_button reads "full" for one of those, not "diff", even
        # though the SAME "undo the triggering edit" logic applies -- see that flag's own init
        # comment for the infinite-retry loop this prevents).
        was_diff = self._active_button == "diff" or self._diff_redirect_pending
        self._render()
        if was_diff:
            InteractiveBuilderApp.on_undo_key(self.builder_getter())
            status_text = f"{status_text} The change that caused it has been undone."
        self._set_running(False)
        self._set_status(status_text, "warn")
        if popup_text is not None:
            messagebox.showwarning("Inflate did not converge", popup_text)

    DIFF_ELIGIBLE_KINDS = ("add_face", "remove_face", "add_connection", "remove_connection")

    def on_load_success(self):
        """Wired from BuilderPane.on_load_success (CombinedApp.__init__) -- fires right after a
        Load actually replaces the net. Always a Full Inflate, never Diff (a freshly-loaded net
        has no relation to whatever self.last_shapes_snapshot/last_pressure/etc. were from
        before, if anything). A no-op if Auto Inflate is unchecked or something's already
        running (2026-09-19, explicit: "as soon as i load a file, it should also inflate")."""
        if self._effective_auto_inflate() and not self._running:
            self.on_full_inflate_clicked()

    def on_load_session_clicked(self):
        """File > Load Session... (2026-09-26, explicit: "you need to implement loading of
        .hippo files... it will also fill in the parameters used... it should also know the
        pressure used for level 3 so we can immediately do auto inflate as the user starts
        interacting with the model") -- picks a session file and dispatches to whichever format
        it actually is: an inflate_polyhedron_app `.hippo` (_load_hippo_session, ALWAYS exactly
        one connected piece, no anchor of its own) or this app's own `.hippie`
        (_load_hippie_session, MAY have more than one piece, carries its own anchor_shape_id) --
        told apart by a raw JSON peek for the "anchor_shape_id" key (only an InflaterSessionStateModel has one) rather than the file extension, so a renamed/misnamed file still loads
        correctly. A no-op while an inflate is already running."""
        if self._running:
            return
        SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            title="Load session", initialdir=str(SESSION_OUTPUT_DIR),
            filetypes=[("Session", f"*{SESSION_FILE_EXTENSION} *.hippo"),
                       ("Session JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path) as f:
                raw_text = f.read()
            raw = json.loads(raw_text)
        except (OSError, ValueError) as e:
            messagebox.showerror("Load session failed", str(e))
            return
        if "anchor_shape_id" in raw:
            self._load_hippie_session(raw_text, path=path)
        else:
            self._load_hippo_session(raw_text)

    def _load_hippo_session(self, raw_text):
        """Restores an inflate_polyhedron_app `.hippo` session (SessionStateModel, imported at
        module level) -- see on_load_session_clicked's own docstring for the format-dispatch.
        `net_file` (the ORIGINAL raw net JSON, self-contained -- no separate net file needs to
        exist on disk) restores the LEFT pane via BuilderPane._load_faces, the exact same
        inherited method every other Load path in this app already funnels through.
        `self.base_faces`/base_edges/base_face_edge_ids are RE-DERIVED from `net_file` via
        _load_mesh_from_dict (this app's own existing authoritative net-dict parser) rather than
        trusting `state.base_faces` blindly, keeping this path consistent with every other
        net-loading path here. Pressure prefers `level_history[3].pressure` (populated
        specifically for Level 3 once reached, independent of whatever `pressure_value`/
        `subdivision_level` happen to be at save time) over the top-level `pressure_value`
        fallback.

        A `.hippo` file predates the anchor concept entirely -- BuilderPane._refresh_vme_state's
        own anchor-assignment fallback (see its docstring) picks the net's first shape as anchor
        automatically once _load_faces replaces self.shapes wholesale, matching "when you load an
        old save file with one connected component and no anchor specified, just let the first
        piece be the anchor." """
        try:
            state = SessionStateModel.model_validate_json(raw_text)
        except ValueError as e:
            messagebox.showerror("Load session failed", str(e))
            return

        builder = self.builder_getter()
        net_file = state.net_file
        if net_file is not None:
            try:
                new_base_faces, new_base_edges, new_face_edge_ids = _load_mesh_from_dict(net_file)
            except ValueError as e:
                messagebox.showerror("Load session failed", str(e))
                return
            self._loading_session = True
            builder._load_faces(net_file.get("faces", state.base_faces), net_file.get("net_layout"),
                                 net_file.get("view", {}).get("scale"), net_file.get("builder_connections"))
            builder._refresh_vme_state()
            self._loading_session = False
            # _load_faces' own _redraw() call (its very last line, above) draws with whatever
            # self._anchor_shape_id was BEFORE this load -- _refresh_vme_state's own fallback
            # (self.shapes[0]["id"], see its docstring) only corrects it just now, one line
            # above, so that first redraw always shows every shape dimmed as an outsider
            # regardless of the newly-loaded net's real connectivity (2026-09-29, explicit bug
            # report: "the polygons are rendered as outsiders initially and later became
            # members"). Nothing else redraws the canvas again afterward.
            builder._redraw()
        else:
            new_base_faces = [list(f) for f in state.base_faces]
            new_base_edges, new_face_edge_ids = None, None
            messagebox.showwarning(
                "Partial session load",
                "This session has no embedded net layout -- the 3D mesh was restored, but the "
                "2D net on the left could not be.")

        level = state.subdivision_level
        level_state = state.levels.get(level)
        if level_state is None:
            messagebox.showerror(
                "Load session failed",
                f"Session's own subdivision_level ({level}) has no matching saved mesh.")
            return
        faces, positions, face_of_fine, edge_length = level_state.to_mesh()

        level_history = {
            lvl: {"pressure": record.pressure, "rms_stretch_pct": record.rms_stretch_pct,
                  "pressure_found": record.pressure_found}
            for lvl, record in state.level_history.items()
        }
        level3_record = state.level_history.get(3)
        if level3_record is not None and level3_record.pressure is not None:
            last_pressure = level3_record.pressure
        else:
            last_pressure = state.pressure_value

        self._apply_loaded_session(
            builder=builder, net_file=net_file, base_faces=new_base_faces,
            base_edges=new_base_edges, base_face_edge_ids=new_face_edge_ids,
            subdivision_level=level, faces=faces, positions=positions,
            face_of_fine=face_of_fine, edge_length=edge_length,
            target_rms_pct=state.target_rms_pct, tolerance=state.tolerance,
            last_pressure=last_pressure, level_history=level_history, session_label=state.net_name,
            # A .hippo comes from inflate_polyhedron_app, which has no guest/insider concept at
            # all -- every mesh it ever saves is a real relax/inflate result, never a flat
            # "place" (see this app's own is_fully_inflated docstring), so this is always True.
            is_fully_inflated=True)

    def _load_hippie_session(self, raw_text, path=None):
        """Restores this app's OWN `.hippie` session (InflaterSessionStateModel) -- see
        on_load_session_clicked's own docstring for the format-dispatch. `net_file` here
        describes EVERY placed shape/connection (central or not, see
        BuilderPane.export_full_net_dict's own docstring) -- restored via _load_faces exactly
        like a `.hippo`'s own net_file, giving back the FULL 2D net including any non-central
        piece(s). The central object's own base mesh/edges are then re-derived by calling the
        just-restored builder's OWN export_mesh_dict() (after the anchor below is set) rather
        than re-parsing `net_file` directly (which describes the WHOLE net, not just the central
        piece `state.base_faces`/`state.mesh` actually describe). This gives back `base_edges`/
        `base_face_edge_ids` (NOT saved in the file at all -- InflaterSessionStateModel has no
        field for either), but NOT `base_faces` itself: `state.base_faces` is used for that
        directly instead of `central_mesh["faces"]` (2026-09-29 fix, explicit bug report --
        "i'm not able to select the guest piece"/"highlighted a non-edge that connects a vertex
        to the centre of an opposite face"). A guest/pendant shape's own corners get FRESH
        runtime-counter vertex ids when first placed flat (_place_pendant_flat, so they never
        collide with the core's independently-numbered fine mesh -- see its own docstring), ids
        that are only reproducible by saving them, never by re-deriving them: a fresh
        export_mesh_dict() call assigns a guest's corners whatever ids _faces_from_shapes'
        deterministic numbering happens to land on, which is generally DIFFERENT from the
        arbitrary-but-consistent ids `state.mesh`'s own saved positions/faces actually use for
        that same guest. self.base_faces is read by every pick/hover/rim-walk path that matters
        here (_rebuild_open_edges, _base_edge_vertex_chain, _group_boundary_edge_set -- none of
        them ever touch self.base_edges/self.base_face_edge_ids), so using the SAVED value there
        is both correct and sufficient; base_edges/base_face_edge_ids are only consulted by the
        Diff Inflate incremental-attach path, which always re-derives its own fresh state off the
        LIVE builder net before touching them anyway, so a freshly-exported value for those two
        is fine.

        `anchor_shape_id` is the ANCHOR's saved `net_layout` "shape_id" -- `_load_faces` always
        reassigns fresh LIVE ids in net_layout order (see its own docstring: "a fresh saved-id ->
        live-id table"), so the saved integer itself is not a valid live id after this Load; the
        anchor is instead re-found by INDEX into `net_file["net_layout"]` (the entry whose own
        saved "shape_id" matches), then read back off `builder.shapes` at that same index --
        `_load_faces` builds `self.shapes` in exactly `net_layout`'s own order (confirmed by
        reading its shape-creation loop), so this index correspondence is exact."""
        try:
            state = InflaterSessionStateModel.model_validate_json(raw_text)
        except ValueError as e:
            messagebox.showerror("Load session failed", str(e))
            return

        builder = self.builder_getter()
        net_file = state.net_file
        self._loading_session = True
        builder._load_faces(net_file.get("faces"), net_file.get("net_layout"),
                             net_file.get("view", {}).get("scale"), net_file.get("builder_connections"))

        net_layout = net_file.get("net_layout") or []
        anchor_index = next((i for i, entry in enumerate(net_layout)
                             if entry.get("shape_id") == state.anchor_shape_id), None)
        if anchor_index is not None and anchor_index < len(builder.shapes):
            builder._anchor_shape_id = builder.shapes[anchor_index]["id"]
        builder._refresh_vme_state()
        # _load_faces' own _redraw() call (its very last line, above) draws with whatever
        # self._anchor_shape_id was BEFORE this load -- the real one is only assigned just
        # now, a few lines above -- so that first redraw always shows every shape dimmed as
        # an outsider regardless of the newly-loaded net's real connectivity (2026-09-29,
        # explicit bug report: "the polygons are rendered as outsiders initially and later
        # became members"). Nothing else redraws the canvas again afterward.
        builder._redraw()

        central_mesh, err = builder.export_mesh_dict()
        if err:
            self._loading_session = False
            messagebox.showerror("Load session failed",
                                  f"Restored net's central object no longer matches the saved "
                                  f"mesh: {err}")
            return

        faces, positions, face_of_fine, edge_length = state.mesh.to_mesh()
        self._loading_session = False
        self._apply_loaded_session(
            builder=builder, net_file=net_file, base_faces=[list(f) for f in state.base_faces],
            base_edges=central_mesh["edges"], base_face_edge_ids=central_mesh["face_edge_ids"],
            subdivision_level=state.subdivision_level, faces=faces, positions=positions,
            face_of_fine=face_of_fine, edge_length=edge_length,
            target_rms_pct=state.target_rms_pct, tolerance=state.tolerance,
            last_pressure=state.last_pressure, level_history=state.level_history,
            session_label=state.net_name, is_fully_inflated=state.is_fully_inflated,
            session_path=path)

    def _apply_loaded_session(self, builder, net_file, base_faces, base_edges, base_face_edge_ids,
                               subdivision_level, faces, positions, face_of_fine, edge_length,
                               target_rms_pct, tolerance, last_pressure, level_history,
                               session_label, is_fully_inflated, session_path=None):
        """Shared tail of _load_hippo_session/_load_hippie_session -- everything past "the
        builder's own 2D net is already restored, and we have the central object's own base
        mesh/current mesh": populates every remaining InflaterPane field (see
        on_load_session_clicked's own docstring for the full list and WHY each one matters), then
        renders and refreshes Diff Inflate's own enabled state (harmless right after a load --
        classify_change sees an identical snapshot and reports "none", so nothing auto-fires).

        `session_path`, only ever given by _load_hippie_session (None from _load_hippo_session
        -- 2026-09-29, explicit user request: "if loaded from a non-hippie file... say
        '[Untitled]'"), is passed straight to self.on_session_loaded (CombinedApp's own
        _mark_clean) at the very end, once every field above is genuinely consistent -- a
        `.hippo` load's own None correctly resets the title to "[Untitled]" (still marked
        CLEAN, not "started from scratch" dirty: nothing's unsaved immediately after a load,
        only once the user actually changes something)."""
        self.base_faces = base_faces
        self.base_edges = base_edges
        self.base_face_edge_ids = base_face_edge_ids
        self.faces = faces
        self.positions = positions
        self.face_of_fine = face_of_fine
        if edge_length is not None:
            self.edge_length = edge_length
        self.edges = None
        self.subdivision_level = subdivision_level

        for lvl in (1, 2, 3):
            if lvl in target_rms_pct and lvl in self.target_rms_vars:
                self.target_rms_vars[lvl].set(target_rms_pct[lvl])
        self.tolerance_var.set(tolerance)
        self.level_history = dict(level_history)
        if last_pressure is not None:
            self.last_pressure = last_pressure

        source_polygon_id = (net_file or {}).get("source_polygon_id")
        if source_polygon_id is None:
            # No "source_polygon_id" in the file at all -- e.g. a `.hippo` (predates the
            # Polygon-Fold/source_polygon_id concept entirely, which only ever exists in THIS
            # app's own export pipeline) -- NOT list(range(len(base_faces))) (2026-09-29,
            # explicit bug report: "i loaded turtle.hippo, and when i hovered over the
            # triangular piece in the 2d view, a hexagonal piece lit up in the 3d view" -- that
            # bare-index fallback silently assumed base_faces group i's own real 2D shape is
            # whatever LIVE builder shape id happens to equal i, which is essentially never
            # true: _load_faces assigns fresh live ids from its own running counter, not
            # 0/1/2/... in net_layout order). base_faces IS always 1:1 with builder.shapes in
            # net_layout order here (a `.hippo`'s own net can never contain a Polygon-Fold
            # shape -- that's an interactive_builder_app-only feature the hippo format has no
            # way to express -- so _load_mesh_from_dict never needed _expand_folded_shapes to
            # build it), and `_load_faces` builds `builder.shapes` in exactly that same
            # net_layout order (confirmed by _load_hippie_session's own docstring, which relies
            # on the identical invariant for its own anchor-by-index lookup) -- so group i's
            # real shape id is builder.shapes[i]["id"], not i itself.
            source_polygon_id = [s["id"] for s in builder.shapes[:len(base_faces)]]
        else:
            # A `.hippie`'s own "source_polygon_id" entries are SAVE-TIME shape ids (2026-09-29,
            # explicit bug report: "the two .hippie files, when i load them, i can't select the
            # edges" -- traced to exactly this: `_load_faces` always reassigns FRESH live ids in
            # net_layout order on every load (see _load_hippie_session's own docstring, "the
            # saved integer itself is not a valid live id after this Load"), so a save-time id
            # here is only STILL a valid live id by coincidence -- whenever a session's shapes
            # weren't all placed fresh starting from id 1 with none ever deleted (e.g. bird_
            # feeder.hippie's own ids run 13-30, hippo_tumour.hippie's skip one), reloading
            # leaves self._pending_source_polygon_id pointing at shape ids that no longer exist,
            # so _groups_for_shape_ids/_shape_id_of_group can never find those groups again --
            # every hover/select/3D-edge-highlight path silently finds nothing for them.
            # Remapped here exactly the same way anchor_shape_id already is, just for every
            # entry instead of one: by INDEX into net_layout (whose own "shape_id" is the SAME
            # save-time id, in the SAME order _load_faces built builder.shapes in), reading the
            # fresh live id back off builder.shapes at that index.
            net_layout = (net_file or {}).get("net_layout") or []
            old_to_live_id = {entry.get("shape_id"): builder.shapes[i]["id"]
                               for i, entry in enumerate(net_layout) if i < len(builder.shapes)}
            source_polygon_id = [old_to_live_id.get(spid, spid) for spid in source_polygon_id]
        self._pending_source_polygon_id = source_polygon_id
        self.last_source_polygon_id = source_polygon_id
        # 2026-09-28, explicit user request: a save now records is_fully_inflated (True if the
        # saved mesh is a real relax/inflate result, False if it was only ever geometrically
        # placed -- see InflaterSessionStateModel's own docstring) -- restored here rather than
        # assumed True, so a loaded "place"-only session still correctly redirects its own next
        # edit to a real Full Inflate (Rule 3) instead of trying to Diff Inflate from geometry
        # that was never actually solved.
        self.is_fully_inflated = is_fully_inflated
        # Nothing pendant/guest-excluded staged here regardless -- a future Full/Diff Inflate
        # re-derives its own guest exclusion fresh from the builder's current net either way.
        self._pending_pendants = []
        (self.last_shapes_snapshot, self.last_connections_snapshot,
         self.last_anchor_snapshot) = builder.snapshot_state()
        # _current_root_to_vertex_id (NOT builder.root_to_vertex_id() directly -- see that
        # method's own docstring) -- self.base_faces/self._pending_source_polygon_id are
        # already set above, correctly (state.base_faces, per _load_hippie_session's own fix),
        # so this correctly reads a loaded guest's own arbitrary remapped id straight off them
        # instead of re-deriving a fresh id that wouldn't match self.positions.
        self.last_root_to_vertex_id = self._current_root_to_vertex_id()

        self._render()
        self.refresh_diff_eligibility()
        self._set_status(f"Loaded session '{session_label}' at Level {subdivision_level}.", "info")
        if self.on_session_loaded is not None:
            self.on_session_loaded(session_path)

    def on_save_session_clicked(self):
        """File > Save Session... (2026-09-26, explicit) -- writes the CURRENT full session (the
        whole live net, central or not, plus the central object's own current mesh/params/
        pressure/anchor) to a `.hippie` file, the ONLY format allowed to describe more than one
        connected piece (see BuilderPane.export_full_net_dict's own docstring). Refuses (with an
        error dialog, no file written) if nothing has been placed yet or the net currently fails
        vertex-merge/duplicate-edge validation (export_full_net_dict's own check), or if nothing
        has been inflated yet (self.faces/base_faces are None before any Inflate ever runs -- a
        `.hippie` always carries a real central-object mesh, never a placeholder one). A no-op
        while an inflate is running (the net could still be changing underneath the save).

        Returns True iff a file was actually written, False otherwise (refused, or the user
        cancelled the save dialog) -- CombinedApp._confirm_discard_unsaved (2026-09-29, explicit
        user request: File > New/window-close should offer to save first) reads this to know
        whether "Yes" genuinely went through before it's safe to proceed with discarding the
        current session."""
        if self._running:
            return False
        builder = self.builder_getter()
        net_file, err = builder.export_full_net_dict()
        if err:
            messagebox.showerror("Save session failed", err)
            return False
        if self.faces is None or self.base_faces is None or builder._anchor_shape_id is None:
            messagebox.showerror("Save session failed",
                                  "Nothing has been inflated yet -- run Full Inflate first.")
            return False
        SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Save session", initialdir=str(SESSION_OUTPUT_DIR),
            defaultextension=SESSION_FILE_EXTENSION,
            filetypes=[("Inflater session", f"*{SESSION_FILE_EXTENSION}"), ("All files", "*.*")])
        if not path:
            return False
        mesh_state = LevelStateModel.from_mesh(self.faces, self.positions, self.face_of_fine,
                                                self.edge_length)
        state = InflaterSessionStateModel(
            net_name=net_file.get("name", "live_net"), net_file=net_file,
            anchor_shape_id=builder._anchor_shape_id,
            base_faces=[list(f) for f in self.base_faces], subdivision_level=self.subdivision_level,
            mesh=mesh_state, tolerance=self.tolerance_var.get(),
            target_rms_pct={lvl: var.get() for lvl, var in self.target_rms_vars.items()},
            last_pressure=self.last_pressure, level_history=self.level_history,
            is_fully_inflated=self.is_fully_inflated,
        )
        try:
            with open(path, "w") as f:
                f.write(state.model_dump_json())
        except OSError as e:
            messagebox.showerror("Save session failed", str(e))
            return False
        self._set_status(f"Session saved to {path}.", "info")
        # 2026-09-29, explicit user request: the window title/dirty-tracking needs to know a
        # `.hippie` was just successfully written to `path` -- CombinedApp.__init__ wires this
        # to its own _mark_clean(path).
        if self.on_session_saved is not None:
            self.on_session_saved(Path(path))
        return True

    def _refresh_undo_redo_buttons(self):
        """Greys the undo/redo icon buttons out whenever there's nothing to undo/redo, or while
        an inflate is running (2026-09-29, explicit user request: "the undo/redo buttons are
        greyed out when there's nothing to undo/redo" -- extended to the running case too, same
        "only view changes while inflating" reasoning as every other editing action, see
        BuilderPane._locked's own docstring). Reads the builder's raw _undo_stack/_redo_stack
        lists directly (BuilderPane.on_undo_key/on_redo_key already read the exact same lists to
        decide their own no-op case) -- cheap, and always current since this is called after
        every builder edit (refresh_diff_eligibility) and every _set_running transition."""
        builder = self.builder_getter()
        can_undo = bool(builder._undo_stack) and not builder._locked
        can_redo = bool(builder._redo_stack) and not builder._locked
        self.undo_button.config(state=tk.NORMAL if can_undo else tk.DISABLED)
        self.redo_button.config(state=tk.NORMAL if can_redo else tk.DISABLED)

    def refresh_diff_eligibility(self):
        """Enables Diff Inflate iff an inflate has completed at least once AND the builder's
        current net differs from that completed state by exactly one added/removed shape or
        connection (BuilderPane.classify_change, DIFF_ELIGIBLE_KINDS) -- called after every
        completed Inflate click (via _set_running) and after every builder edit
        (BuilderPane.on_change, wired from CombinedApp) so the button's enabled state always
        reflects the LIVE net, not just whatever it was the last time Inflate ran. When Auto
        Inflate is checked (default on, 2026-09-19, explicit), an eligible change fires
        Diff Inflate immediately instead of just enabling the button -- "every time there is a
        [topological] change to the model... it automatically does a Diff Inflate" (a plain
        move/rotate never reaches here as anything but "none", since classify_change already
        ignores cx/cy/rotation entirely -- see its own docstring)."""
        self._refresh_undo_redo_buttons()
        if self._loading_session:
            # A session load is still MID-restoration (see self._loading_session's own init
            # comment for the crash this prevents) -- builder.shapes/connections already
            # describe the NEW net, but self.base_faces/faces/positions/last_shapes_snapshot
            # etc. don't yet, so nothing here (eligibility, target-RMS re-pick, any auto-fire)
            # would be evaluating a consistent state. _apply_loaded_session calls this again,
            # correctly, once everything is actually in sync.
            return
        # A builder edit always snaps the replay scrubber back to live (2026-09-29, explicit
        # user request) -- self._replay_frames itself is left alone (still valid history of
        # the last completed run until the NEXT run overwrites it), but a stale mid-history
        # frame drawn via _render_replay_frame would otherwise keep showing while the user
        # edits a now-DIFFERENT live net, which reads as this pane being stuck/broken.
        if self._replay_scrub_index is not None:
            self._replay_scrub_index = None
            self._update_replay_slider()
        # Keeps self._open_edges in sync with the LIVE net on every edit, not just after the
        # next full _render() (which only happens once an Inflate actually runs) -- otherwise a
        # just-made-or-broken connection could keep offering/hiding its own edges' 3D
        # drag-to-connect handles a beat too long (2026-09-19 feature, "creating connections in
        # 3d").
        self._rebuild_open_edges()
        # Re-picks the Target RMS % defaults from the LIVE central object's own closed/open
        # status on every edit (2026-09-28, explicit user request) -- same chokepoint, same
        # reasoning: this needs to stay current even before the first Inflate click, not just
        # once a completed run exists to diff against.
        self._apply_target_rms_defaults()
        # Clears a stale last-inflated mesh once nothing is central anymore -- e.g. the anchor
        # (and everything else) just got deleted (2026-09-28, explicit user request: "after
        # anchor deleted, the view should refresh") -- without this, self.faces/self.positions
        # still hold whatever was inflated before the delete, and _render() keeps drawing that
        # now-nonexistent shape since nothing else here ever clears them.
        if not self.builder_getter().central_shape_ids() and self.faces is not None:
            self.base_faces = self.base_edges = self.base_face_edge_ids = None
            self.faces = self.edge_length = self.face_of_fine = self.edges = None
            self.positions = None
            self.subdivision_level = 0
            # Rule 2 (2026-09-28, explicit): "every time the canvas empties, the
            # is_fully_inflated flag is set to false" -- the club itself is gone (no member is
            # central anymore), so there's nothing left that could be "fully inflated".
            self.is_fully_inflated = False
            self._render()
        if self._running:
            self.diff_inflate_button.state(["disabled"])
            return
        # Outsider add/delete gets its OWN status message (2026-09-28, explicit user request:
        # "if outsiders changed, it can say 'Outsider added/deleted/modified'") -- BuilderPane.
        # classify_change deliberately reports "none" for an outsider-only change (see its own
        # docstring: it never affects what's actually exported/inflated), so it's the only way
        # this ever gets noticed at all. Tracked here (every edit), not just around a
        # successful inflate, since an outsider change never touches self.last_shapes_snapshot
        # either.
        builder = self.builder_getter()
        current_central_ids = builder.central_shape_ids()
        current_outsider_ids = frozenset(
            s["id"] for s in builder.shapes if s["id"] not in current_central_ids)
        if current_outsider_ids != self._last_outsider_ids:
            added = current_outsider_ids - self._last_outsider_ids
            removed = self._last_outsider_ids - current_outsider_ids
            if added and not removed:
                self._set_status(
                    f"{'Outsider' if len(added) == 1 else 'Outsiders'} added.", "info")
            elif removed and not added:
                self._set_status(
                    f"{'Outsider' if len(removed) == 1 else 'Outsiders'} deleted.", "info")
            else:
                self._set_status("Outsiders modified.", "info")
            self._last_outsider_ids = current_outsider_ids
        if not current_central_ids:
            # Nothing central at all (e.g. the anchor -- and everything else -- was just
            # deleted, see the empty-club clearing block above) -- there's no net left to Full
            # or Diff Inflate against, so stop here rather than falling into classify_change's
            # own "remove_face" verdict below, which would otherwise redirect straight into
            # on_full_inflate_clicked -- export_mesh_dict's own "Nothing to inflate yet" error
            # for an empty club, surfaced as a "Cannot inflate" popup for what's really just an
            # ordinary delete (2026-09-28, explicit bug report: "when i place the anchor and
            # delete it, it shouldn't have a 'Cannot Inflate' popup").
            self.diff_inflate_button.state(["disabled"])
            return
        if self.last_shapes_snapshot is None:
            self.diff_inflate_button.state(["disabled"])
            # No inflate has EVER completed yet -- nothing to diff against, so the only
            # meaningful action is a Full Inflate (2026-09-28, explicit user request: "let auto
            # inflate apply as soon as i put down the first piece" -- _prepare_mesh_for_inflate
            # itself reduces this to a plain flat "place", never real physics, for a lone face,
            # see its own docstring, so this is cheap even on the very first piece).
            if self._effective_auto_inflate() and self.builder_getter().central_shape_ids():
                # Same infinite-retry hazard as on_diff_inflate_clicked's own redirect (see its
                # own docstring/_diff_redirect_pending's init comment) if this auto-triggered
                # run fails to converge -- e.g. several pieces placed and braced together before
                # any prior inflate ever succeeded.
                self._diff_redirect_pending = True
                self.on_full_inflate_clicked(change_label="Anchor piece")
            return
        kind, _extra = self.builder_getter().classify_change(
            self.last_shapes_snapshot, self.last_connections_snapshot, self.last_anchor_snapshot)
        eligible = kind in self.DIFF_ELIGIBLE_KINDS
        self.diff_inflate_button.state(["!disabled"] if eligible else ["disabled"])
        if eligible and self._effective_auto_inflate():
            self.on_diff_inflate_clicked()

    def _on_panel_configure(self, event):
        """Keeps the off-screen plotter's own render resolution matched to panel_label's real,
        current pixel size -- debounced via a rescheduled `after` call (Configure fires
        continuously while the window/sash is being dragged; rebuilding the plotter on every
        single event would be wasteful and janky) so the actual rebuild+re-render only happens
        once motion settles. Ignores the initial 1x1 Configure Tk sends before real layout."""
        width, height = event.width, event.height
        if width <= 1 or height <= 1:
            return
        if (width, height) == self.panel_size:
            return
        if self._resize_after_id is not None:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(80, lambda: self._apply_panel_resize(width, height))

    def _apply_panel_resize(self, width, height):
        self._resize_after_id = None
        self.panel_size = (width, height)
        self.plotter.close()
        self.plotter = pv.Plotter(off_screen=True, window_size=[width, height])
        self.plotter.set_background(PLOT_THEME["bg"])
        self._setup_plotter_lighting()
        self._render()

    # ---- camera (rotate/pan/zoom) ----

    @staticmethod
    def _initial_rotation():
        """Same construction as inflate_polyhedron_app's own _initial_level_rotation -- an
        explicit orthonormal (direction, right, up) frame read off as a rotation matrix, so the
        starting view matches that app's default (non-axis-aligned) angle instead of a bare
        identity quaternion."""
        azim, elev = np.radians(PANEL_DEFAULT_AZIM), np.radians(PANEL_DEFAULT_ELEV)
        direction = np.array([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim),
                               np.sin(elev)])
        world_up = np.array([0.0, 0.0, 1.0])
        right = np.cross(world_up, direction)
        right /= np.linalg.norm(right)
        up = np.cross(direction, right)
        return Rotation.from_matrix(np.column_stack([direction, right, up]))

    def _setup_plotter_lighting(self):
        """Replaces self.plotter's own default light kit with the explicit KEY/FILL
        camera-relative rig (see KEY_LIGHT_POSITION's own comment for why). Called right after
        every `self.plotter = pv.Plotter(...)` (both _build_ui's initial one and
        _apply_panel_resize's rebuild-on-resize one) AND at the top of every _render/
        _render_replay_frame, right after plotter.clear() -- that call wipes every light, not
        just actors (pyvista's own Renderer.clear() calls remove_all_lights() internally), so a
        one-time setup right after construction was silently undone the moment the very first
        real frame drew (2026-09-29, explicit bug report: "I don't see any shading" -- this was
        the actual cause, not the lighting model itself). Cheap either way: two lightweight VTK
        Light objects, no mesh work -- `light_type='camera light'` lights track the camera
        automatically from here on, no re-positioning needed as the user rotates/pans/zooms."""
        self.plotter.remove_all_lights()
        key_light = pv.Light(light_type="camera light", intensity=KEY_LIGHT_INTENSITY)
        key_light.position = KEY_LIGHT_POSITION
        self.plotter.add_light(key_light)
        fill_light = pv.Light(light_type="camera light", intensity=FILL_LIGHT_INTENSITY)
        fill_light.position = FILL_LIGHT_POSITION
        self.plotter.add_light(fill_light)

    def _apply_camera(self):
        """Positions the plotter's orthographic camera from self._camera (rotation/zoom/pan)
        and self._center/_half (this frame's own bounding-sphere, set by _render just before
        this is called) -- same technique as inflate_polyhedron_app's own _render_level_pv."""
        cam = self._camera
        direction = cam["rotation"].apply([1.0, 0.0, 0.0])
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        distance = self._half * 4
        camera = self.plotter.camera
        camera.parallel_projection = True
        camera.focal_point = tuple(self._center)
        camera.position = tuple(self._center + direction * distance)
        camera.up = tuple(up)
        panel_width, panel_height = self.panel_size
        camera.parallel_scale = (self._half * max(1.0, panel_height / panel_width)
                                  / PANEL_ZOOM_FILL / cam["zoom"])
        camera.SetWindowCenter(*cam["pan"])

    def _grab_frame(self):
        """Renders the plotter's CURRENT scene (whatever actors/camera it already has -- this
        does no scene or camera work of its own) and blits it into panel_label -- the one
        choke point every redraw path (_render's full rebuild, _refresh_view's camera-only
        update, _set_hover_group's incremental highlight toggle) ends with. Also where the
        open-edge hover/drag gesture's own flat 2D overlay gets drawn (see
        _draw_connection_overlays's own docstring for why it's a 2D image overlay, not 3D
        geometry at all)."""
        self.plotter.render()
        image = self.plotter.screenshot(return_img=True)
        pil_image = Image.fromarray(image)
        self._draw_connection_overlays(pil_image)
        self._photo = ImageTk.PhotoImage(pil_image)
        self.panel_label.configure(image=self._photo, text="")

    def _world_to_display(self, point):
        """World-space 3D point -> (x, y) panel PIXEL coordinates, Tk's own top-left-origin
        convention (matching event.x/event.y and the PIL image _grab_frame draws onto) -- the
        OPPOSITE conversion from _pick_world_position's own pixel-to-world pick, using the
        renderer's WorldToDisplay transform against whatever camera is CURRENTLY applied."""
        renderer = self.plotter.renderer
        renderer.SetWorldPoint(float(point[0]), float(point[1]), float(point[2]), 1.0)
        renderer.WorldToDisplay()
        x, y, _z = renderer.GetDisplayPoint()
        height = self.panel_size[1]
        return x, height - 1 - y

    def _draw_connection_overlays(self, pil_image):
        """Draws ONLY the live 3D-native drag's own screen-space rubber-band line -- from the
        drag's own PINNED starting point (wherever the press actually landed, see
        _start_connection_drag -- 2026-09-19, explicit: "that connection should start at where
        you clicked, not the midpoint of that edge") to the ACTUAL cursor position (2026-09-19,
        explicit: "the mouse drags out a connection in screen space (thick line)"). Every OTHER
        part of this gesture -- the hovered/target edge's yellow highlight, the pressed/
        confirmed edge(s)' red highlight, and the final connecting line -- is real 3D geometry
        now (self._edge_highlight_actors/_pending_made_connection_actors), not a 2D overlay, so
        it isn't drawn here at all."""
        if self._connection_drag is None or self._line_end_screen_override is None:
            return
        origin_point = self._connection_drag.get("origin_point")
        if origin_point is None:
            return
        origin_screen = self._world_to_display(origin_point)
        ImageDraw.Draw(pil_image).line(
            [origin_screen, self._line_end_screen_override], fill=CONNECTION_OVERLAY_LINE_COLOR,
            width=CONNECTION_OVERLAY_LINE_WIDTH_PX)

    def _refresh_view(self):
        """Camera-only redraw -- repositions the camera (_apply_camera) and grabs a fresh
        frame, WITHOUT rebuilding any mesh/wireframe/rim actor (contrast full _render(), a
        complete plotter.clear() + rebuild of every actor: two culled mesh actors with
        wireframe edge extraction, plus rounded/tube rim-line actors, PER base face). Used for
        EVERY frame of a rotate/pan/zoom drag -- none of those change any actual geometry, only
        where the SAME already-built scene is viewed from, so rebuilding it every frame was
        pure waste (2026-09-19: "it's also much more laggy to rotate... is it because of the
        face highlighting from mouse over?" -- no; hover's own update was already this cheap.
        Every camera interaction, rotate/pan/zoom alike, was instead going through the full
        rebuild on every single drag frame, which is what actually caused the lag).

        This is fully correct for rotation too, not just pan/zoom, with no follow-up full
        rebuild ever needed: the polygon-rim overlay's own two offset copies
        (_group_boundary_offset_lines) are a fixed, purely geometric nudge along each edge's
        own owning triangle's normal, resolved by ordinary Z-buffer depth testing at render
        time, not by anything computed here against the camera. Rotating the camera never
        invalidates it."""
        if not (self.faces and self.positions and self.base_faces):
            return
        self._apply_camera()
        self._grab_frame()

    def _on_drag_start(self, event):
        self._dragging = True
        self._last_xy = (event.x, event.y)
        self._drag_moved = False
        # A ButtonPress-1 landing while an open edge is currently revealed (Edit mode's own
        # hover-reveal, see _set_hover_open_edge) starts a drag-to-connect instead of a camera
        # rotate-drag (2026-09-19, explicit: "hover over an open edge... drag to connect to
        # another edge midpoint... clicking is distinct from press-drag-release, which is used
        # for rotation" -- the same distinction, extended to a second drag-triggering gesture).
        # `not self._running` is belt-and-suspenders here (2026-09-29, explicit user request:
        # "disable all types of editing [while inflating]... only allow view changes") --
        # self._hover_open_edge_key is already forced None for the whole duration of a run by
        # _on_panel_hover_motion's own running-guard, so this branch is unreachable while
        # running regardless, but the explicit check keeps that invariant from being silent.
        if (not self._running and self.builder_getter().tool_mode == "edit"
                and self._hover_open_edge_key is not None):
            self._start_connection_drag(event)

    def _on_drag_motion(self, event):
        if self._connection_drag is not None:
            self._update_connection_drag(event)
            return
        if not self._dragging or self._last_xy is None:
            return
        cam = self._camera
        last_x, last_y = self._last_xy
        dx, dy = event.x - last_x, event.y - last_y
        # Anything past a couple pixels of actual movement means this is a rotate-drag, not a
        # click -- _on_drag_end reads this to decide whether to select instead.
        if abs(dx) > CLICK_MOVE_TOLERANCE_PX or abs(dy) > CLICK_MOVE_TOLERANCE_PX:
            self._drag_moved = True
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        right = cam["rotation"].apply([0.0, 1.0, 0.0])
        sensitivity = np.radians(PANEL_DRAG_SENSITIVITY)
        yaw = Rotation.from_rotvec(-dx * sensitivity * up)
        pitch = Rotation.from_rotvec(-dy * sensitivity * right)
        cam["rotation"] = pitch * yaw * cam["rotation"]
        self._last_xy = (event.x, event.y)
        self._refresh_view()

    def _on_drag_end(self, event):
        """A press+release with no meaningful motion in between (self._drag_moved never set --
        see CLICK_MOVE_TOLERANCE_PX above) is a plain CLICK, not a rotate-drag -- selects
        whatever face/connection is under the cursor (2026-09-19, explicit: "clicking on a face
        in 3d should select it in both views... clicking is distinct from press-drag-release,
        which is used for rotation"). A connection-drag started at press time (above) is a
        THIRD gesture, checked first -- it ends here regardless of how far the mouse moved
        (dragging a bare few pixels onto an adjacent edge's own handle is a completely
        reasonable connection, not a "click")."""
        was_dragging, moved, was_connecting = self._dragging, self._drag_moved, self._connection_drag is not None
        self._dragging = False
        self._last_xy = None
        if was_connecting:
            self._finish_connection_drag(event)
        elif was_dragging and not moved:
            self._on_panel_click(event)

    def _on_pan_start(self, event):
        self._panning = True
        self._pan_last_xy = (event.x, event.y)

    def _on_pan_motion(self, event):
        if not self._panning or self._pan_last_xy is None:
            return
        last_x, last_y = self._pan_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        panel_width, panel_height = self.panel_size
        self._camera["pan"] = self._camera["pan"] + np.array(
            [-dx / (panel_width / 2.0), dy / (panel_height / 2.0)])
        self._pan_last_xy = (event.x, event.y)
        self._refresh_view()

    def _on_pan_end(self, _event):
        self._panning = False
        self._pan_last_xy = None

    def _on_camera_reset(self, _event=None):
        self._camera = {"rotation": self._initial_rotation(), "zoom": 1.0, "pan": np.zeros(2)}
        self._render()

    def _on_scroll(self, event):
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / PANEL_ZOOM_STEP
        else:
            factor = PANEL_ZOOM_STEP
        self._camera["zoom"] = max(PANEL_ZOOM_MIN, min(PANEL_ZOOM_MAX, self._camera["zoom"] * factor))
        self._refresh_view()

    # ---- hover highlight ----

    def _on_panel_hover_motion(self, event):
        """Plain mouse motion (no button held) over the panel -- a drag (rotate/pan) fires its
        OWN motion events (<B1-Motion>/<B3-Motion>), never this plain <Motion> one, so hover
        picking never fights the camera gestures. Dispatches by the LEFT pane's own tool mode
        (2026-09-19, explicit: "select faces... should only be possible in Move[M] mode... in
        Join[J] mode, hovering over the 3d edge highlights the corresponding 2d connection";
        Move+Join merged into Edit mode 2026-09-29, explicit -- so Edit mode now does BOTH: the
        nearest connection seam/open edge AND a whole face, same as the 2D canvas's own merged
        Edit-mode hover) -- Edit is this app's only tool mode now (2026-09-29, explicit: "remove
        the Anchor[A] mode"), so the `else` branch below (clearing both) is purely defensive at
        this point, not reachable in practice.

        Edge wins over face (2026-09-29, explicit bug report: "first check if i'm near any
        edges... if not, then check faces -- right now it's checking faces first so edges never
        get highlighted"): an edge (existing connection seam or open edge) is looked up FIRST,
        within its own pick tolerance around the cursor's world position; only when neither is
        found does the face under the cursor get the yellow hover outline instead. The two are
        mutually exclusive so there's no double highlight.

        No hover picking at all while an inflate is running (2026-09-29, explicit user request:
        "disable hovering highlight and selecting while inflating is ongoing... only allow view
        changes like rotating/panning/zooming") -- self._running is exactly the window where
        self.base_faces/self._pending_source_polygon_id can already describe the NEW mesh while
        the panel is still showing the OLD one (see _display_pending_source_polygon_id's own
        docstring), so a picked group can resolve to the wrong shape; more fundamentally, hover/
        select are themselves a form of interacting with the model, which this request narrows
        down to view-only (camera rotate/pan/zoom, still handled by the drag/pan/scroll bindings
        below, none of which route through here) for the whole duration of a run."""
        if self._running:
            self._set_hover_group(None)
            self._set_hover_connection(None)
            self._set_hover_open_edge(None)
            return
        if not self._actor_to_group:
            return
        mode = self.builder_getter().tool_mode
        if mode != "edit":
            self._set_hover_group(None)
            self._set_hover_connection(None)
            return
        if self._connection_drag is not None:
            self._update_connection_drag(event)
            return
        width, height = self.panel_size
        # VTK's own pixel origin is bottom-left; Tk's (event.x/event.y) is top-left.
        hit = self._picker.Pick(event.x, height - 1 - event.y, 0, self.plotter.renderer)
        group = self._actor_to_group.get(self._picker.GetActor())
        pos = np.array(self._picker.GetPickPosition()) if hit else None
        picked_shape_id = self._shape_id_of_group(group)
        conn_id = self._nearest_connection_at_position(pos, shape_id=picked_shape_id)
        open_edge_key = None
        if not self.builder_getter()._locked:
            open_edge_key = self._nearest_open_edge_at_position(pos, shape_id=picked_shape_id)
        self._set_hover_group(None if (conn_id is not None or open_edge_key is not None) else group)
        self._set_hover_connection(conn_id)
        self._set_hover_open_edge(open_edge_key)

    def _on_panel_hover_leave(self, _event=None):
        self._set_hover_group(None)
        self._set_hover_connection(None)
        self._set_hover_open_edge(None)

    def _pick_world_position(self, event):
        """The world-space point where the cursor's pick ray hits the CURRENTLY displayed mesh
        surface, or None if it misses everything -- shared by Join mode's edge hover/click
        (there's no separate pickable line geometry per connection, see
        _nearest_connection_at_position's own docstring) with Move mode's own face pick, just
        reading GetPickPosition() instead of GetActor()."""
        if not self._actor_to_group:
            return None
        width, height = self.panel_size
        if not self._picker.Pick(event.x, height - 1 - event.y, 0, self.plotter.renderer):
            return None
        return np.array(self._picker.GetPickPosition())

    def _nearest_connection_at_position(self, pos, shape_id=None):
        """The builder connection id whose cached 3D seam segments
        (self._connection_edge_cache) come closest to world point `pos`, within
        CONNECTION_PICK_TOLERANCE_FRACTION * self._half -- or None if nothing's close enough
        (including simply because `pos` is None, no surface under the cursor at all). There's
        no dedicated pickable actor per connection (unlike a base face's own mesh actor,
        _actor_to_group) -- a connection's seam is a thin line lying exactly on the already-
        picked surface, not a separate 3D object of its own, so proximity-to-the-pick-point
        is used instead of a second vtkCellPicker pass.

        `shape_id`, when given, restricts candidates to connections touching that ONE shape
        (2026-09-29, explicit bug report: "the edges of the guest piece [are] still not
        selectable. instead there are some non-edges that are highlighted when hovered over"
        -- traced to plain nearest-in-3D-space search across the WHOLE mesh: a compact,
        nearly-closed net folds enough that a totally unrelated shape's own seam can sit
        CLOSER in 3D to a given surface point than that surface's own nearby seam, even
        directly on top of it, topologically distant faces having folded close together in
        space -- caught by direct testing: a pick position confirmed to be on the guest's own
        rendered surface still matched a DIFFERENT shape's connection more often than its own).
        The caller passes the shape actually under the cursor (`_actor_to_group`'s own hit),
        so a hover only ever finds an edge genuinely belonging to what's actually being
        pointed at."""
        if pos is None or not self._connection_edge_cache:
            return None
        tolerance = CONNECTION_PICK_TOLERANCE_FRACTION * self._half
        best_id, best_dist = None, tolerance
        connections_by_id = None
        if shape_id is not None:
            connections_by_id = {c["id"]: c for c in self._display_connections()}
        for conn_id, segments in self._connection_edge_cache.items():
            if shape_id is not None:
                conn = connections_by_id.get(conn_id)
                if conn is None or shape_id not in (conn["a_shape"], conn["b_shape"]):
                    continue
            for i in range(0, len(segments), 2):
                dist = _point_segment_distance_3d(pos, segments[i], segments[i + 1])
                if dist < best_dist:
                    best_id, best_dist = conn_id, dist
        return best_id

    def _nearest_open_edge_at_position(self, pos, exclude_shape_id=None, shape_id=None):
        """The (shape_id, raw_edge) key in self._open_edges whose own segments come closest to
        world point `pos`, within OPEN_EDGE_PICK_TOLERANCE_FRACTION * self._half -- or None if
        nothing's close enough (including `pos is None`). Point-to-SEGMENT distance against the
        edge's own actual (possibly subdivided) geometry, not just its midpoint -- matches
        "hovering over open edges" being the trigger (2026-09-19, explicit), not just their
        midpoint specifically; same convention _nearest_connection_at_position already uses for
        an EXISTING connection's own seam. `exclude_shape_id` drops one shape's own edges from
        consideration -- used while dragging OUT of a shape's edge, since Join mode never
        connects a shape to itself (that's Fold's job). `shape_id`, when given, restricts
        candidates to that ONE shape's own edges -- see _nearest_connection_at_position's own
        docstring for why (same fold-brings-unrelated-shapes-close issue, same fix)."""
        if pos is None or not self._open_edges:
            return None
        tolerance = OPEN_EDGE_PICK_TOLERANCE_FRACTION * self._half
        best_key, best_dist = None, tolerance
        for key, info in self._open_edges.items():
            if exclude_shape_id is not None and info["shape_id"] == exclude_shape_id:
                continue
            if shape_id is not None and info["shape_id"] != shape_id:
                continue
            segments = info["segments"]
            for i in range(0, len(segments), 2):
                dist = _point_segment_distance_3d(pos, segments[i], segments[i + 1])
                if dist < best_dist:
                    best_key, best_dist = key, dist
        return best_key

    def _rebuild_open_edges(self):
        """Rebuilds self._open_edges -- see its own docstring in __init__. Deliberately reads
        the builder's CURRENT shapes/connections (not the possibly-stale last-inflated
        snapshot), since "is this edge already used" is a pure 2D-data-model question that
        should update the instant a connection is made, even before the 3D mesh itself catches
        up at the next Diff/Full Inflate."""
        self._open_edges = {}
        if not self.base_faces or self.positions is None or self._pending_source_polygon_id is None:
            return
        builder = self.builder_getter()
        used = set()
        for conn in builder.connections:
            used.add((conn["a_shape"], conn["a_edge"]))
            used.add((conn["b_shape"], conn["b_edge"]))
        shapes_by_id = {s["id"]: s for s in builder.shapes}
        for group, shape_id in enumerate(self._pending_source_polygon_id):
            if group >= len(self.base_faces):
                continue
            face = self.base_faces[group]
            shape = shapes_by_id.get(shape_id)
            # A deleted shape, or one whose group is actually several Polygon-Fold triangles
            # (len(face) == 3 always, regardless of the original shape's own side count) --
            # either way there's no reliable raw-edge<->loop-position mapping to offer a handle
            # through, so this shape's edges are simply never made available here (a Polygon-
            # Fold self-connection stays a 2D-only, Fold-mode-only gesture, same limitation as
            # _connection_edge_segments' own).
            if shape is None or len(face) != shape["n"]:
                continue
            n = shape["n"]
            flipped = shape.get("flipped", False)
            for raw_edge in range(n):
                if (shape_id, raw_edge) in used:
                    continue
                # raw_edge_for_loop_position (interactive_builder_app._face_edge_ids_from_shapes,
                # untouchable) is its own inverse for this formula, so the same expression maps
                # loop position -> raw edge and back.
                k = raw_edge if not flipped else (n - 2 - raw_edge) % n
                u, v = face[k], face[(k + 1) % n]
                if u not in self.positions or v not in self.positions:
                    continue
                midpoint, segments = self._open_edge_geometry(group, u, v)
                self._open_edges[(shape_id, raw_edge)] = {
                    "shape_id": shape_id, "raw_edge": raw_edge, "midpoint": midpoint,
                    "segments": segments,
                }

    def _base_edge_vertex_chain(self, group, u, v):
        """Ordered fine-mesh vertex ids from corner `u` to corner `v` along THIS ONE base edge
        of `group`'s own rim -- NOT just [u, v] (2026-09-19, explicit bug report: "when i hover
        over an edge midpoint... you're drawing a circle halfway between two vertices rather
        than actually on the edge (which is not straight so you need to look at the
        subdivisions)"): mesh_levels._fan_level_0_to_1 leaves a rim edge alone at Level 1 (still
        literally [u, v]), but _quarter_triangles inserts a real midpoint vertex on it at every
        subsequent level (2 segments at Level 2, 4 at Level 3) -- for an inflated/relaxed shape
        those aren't at the straight average of u and v's own positions any more, so the actual
        chain has to be walked, not assumed.

        self._group_boundary_edge_set(group) gives every rim SEGMENT of the group as an
        unordered {(a, b), ...} set (see its own docstring) -- within it, every vertex has
        exactly degree 2 (it's one closed loop around the whole polygon), so `u` has exactly
        two neighbors: one starts the short chain toward `v` (this one edge, possibly
        subdivided), the other starts off around the REST of the polygon's other edges instead.
        The two directions can't be told apart by which one reaches `v` sooner (a heavily-
        subdivided target edge can easily have MORE segments than the rest of a small polygon's
        other edges combined, and vice versa) -- instead, each of `u`'s two neighbors is tried
        as a walk (always stepping to whichever neighbor isn't where it just came from) that
        stops the instant it reaches EITHER `v` (success) OR any OTHER of this group's ORIGINAL
        corners (self.base_faces[group], failure -- a genuine subdivision midpoint is never one
        of those, only ever a newly-created vertex id, so hitting one means this direction
        wandered onto a DIFFERENT base edge instead). Falls back to the plain [u, v] pair if
        neither direction ever reaches `v` (shouldn't happen for a genuine edge of this group,
        but stays safe if it ever doesn't)."""
        original_corners = set(self.base_faces[group])
        neighbors = {}
        for a, b in self._group_boundary_edge_set(group):
            neighbors.setdefault(a, []).append(b)
            neighbors.setdefault(b, []).append(a)
        for first_step in neighbors.get(u, []):
            chain = [u, first_step]
            prev, cur = u, first_step
            while cur != v and cur not in original_corners:
                options = [n for n in neighbors.get(cur, []) if n != prev]
                if not options:
                    break
                prev, cur = cur, options[0]
                chain.append(cur)
            if cur == v:
                return chain
        return [u, v]

    def _open_edge_geometry(self, group, u, v):
        """(midpoint, segments) for base edge (u, v) of `group`'s own rim, AT THE CURRENT
        subdivision level, both derived from ONE _base_edge_vertex_chain walk. `midpoint` is
        the middle vertex of that chain (an odd-length chain, Level 2+, has one -- e.g.
        [u, m, v] at Level 2), or the plain average of the two middle ones for an even-length
        chain (Level 0/1's own un-subdivided [u, v], where this is just the ordinary
        straight-line midpoint). `segments` is the whole chain as consecutive (start, end)
        pairs -- the edge's own ACTUAL (possibly curved/subdivided) geometry, what every
        highlight in this file draws instead of a straight chord between the two corners
        (2026-09-19, explicit bug report: "the edge... is not straight so you need to look at
        the subdivisions")."""
        chain = self._base_edge_vertex_chain(group, u, v)
        points = [self.positions[vid] for vid in chain if vid in self.positions]
        if len(points) < 2:
            p_u, p_v = self.positions[u], self.positions[v]
            return (p_u + p_v) / 2, np.array([p_u, p_v])
        mid = len(points) // 2
        midpoint = points[mid] if len(points) % 2 == 1 else (points[mid - 1] + points[mid]) / 2
        segments = np.empty((2 * (len(points) - 1), 3))
        for i in range(len(points) - 1):
            segments[2 * i] = points[i]
            segments[2 * i + 1] = points[i + 1]
        return midpoint, segments

    def _set_edge_highlight_actors(self, role, key, color):
        """Swaps out `role`'s own actors ("hover"/"origin"/"target"/"connecting_line" in
        self._edge_highlight_actors) for a fresh highlight of `key`'s own edge segments, or
        removes them entirely if `key` is None -- same incremental swap convention as
        _apply_hover_highlight/_apply_selection_highlight elsewhere in this file. `color`
        picks the line width too (yellow = hover, HOVER_HIGHLIGHT_LINE_WIDTH; anything else =
        confirmed/pressed, SELECTED_HIGHLIGHT_LINE_WIDTH, 2026-09-19 explicit: "the line joining
        two midpoints should be as thick as selected edges" -- applied to every RED highlight
        here, not just the connecting line)."""
        for actor in self._edge_highlight_actors.pop(role, []):
            self.plotter.remove_actor(actor)
        info = None if key is None else self._open_edges.get(key)
        if info is not None:
            width = HOVER_HIGHLIGHT_LINE_WIDTH if color == "yellow" else SELECTED_HIGHLIGHT_LINE_WIDTH
            self._edge_highlight_actors[role] = self._add_rounded_lines(info["segments"], color, width)

    def _apply_hover_open_edge_highlight(self, key):
        """Highlight-only half of the open-edge hover-reveal -- a real 3D yellow line along
        `key`'s own edge segments (2026-09-19, explicit: "let hovering over open edges
        highlight them in yellow"), or none at all for `key=None`. Shared by both directions
        (_set_hover_open_edge, 3D-native, which also forwards to BuilderPane; and
        set_open_edge_hover_from_builder, 2D-driven, which must NOT forward back), and by
        _update_connection_drag's own live target search (which does NOT forward either -- see
        its own docstring). A no-op if `key` already matches the current hover."""
        if key == self._hover_open_edge_key:
            return
        self._hover_open_edge_key = key
        self._set_edge_highlight_actors("hover", key, "yellow")
        self._grab_frame()

    def _set_hover_open_edge(self, key):
        """3D-mouse-over-an-open-edge direction: the plain reveal-on-proximity state (not yet
        dragging) -- forwards to BuilderPane.set_open_edge_hover so the SAME yellow highlight
        shows in 2D too (2026-09-19, explicit: "if i hover over an edge [in 2d]... the
        corresponding edge should also show... in 3d" -- applied symmetrically to this, the
        reverse direction)."""
        changed = key != self._hover_open_edge_key
        self._apply_hover_open_edge_highlight(key)
        if changed:
            info = None if key is None else self._open_edges.get(key)
            self.builder_getter().set_open_edge_hover(
                None if info is None else info["shape_id"], None if info is None else info["raw_edge"])

    def set_open_edge_hover_from_builder(self, shape_id, raw_edge):
        """2D-mouse-over-an-open-edge direction -- called by BuilderPane whenever ITS OWN plain
        proximity-reveal (InteractiveBuilderApp's _hit_test_any_edge_handle, read fresh every
        <Motion>, see BuilderPane._on_canvas_motion) changes, or clears (shape_id=None). Does
        NOT call back into BuilderPane.set_open_edge_hover, since the 2D side already shows its
        own reveal via its base class's own _redraw; this only drives the 3D side. Ignored
        entirely while a 3D-originated drag is active (self._connection_drag) -- its own
        origin/target highlights own the hover-reveal's own visual slot instead while
        dragging."""
        if self._connection_drag is not None:
            return
        key = None if shape_id is None else (shape_id, raw_edge)
        self._apply_hover_open_edge_highlight(key)

    def _start_connection_drag(self, event):
        """Called from _on_drag_start when a ButtonPress-1 lands while an open edge is
        currently revealed (self._hover_open_edge_key) in Join mode -- switches that yellow
        hover highlight into the drag's own RED "origin" highlight (2026-09-19, explicit: "the
        mouse press causes the edge to be selected and drawn in red"), and mirrors the origin
        into 2D via BuilderPane.set_pending_connection (already-existing behavior, unchanged).
        Also pins down the connection's own ACTUAL starting point (self._connection_drag's own
        "origin_point") to wherever the press itself landed on the mesh surface, not the edge's
        midpoint (2026-09-19, explicit: "that connection should start at where you clicked, not
        the midpoint of that edge") -- falls back to the midpoint only if the press somehow
        didn't land on any surface at all (shouldn't happen, since _on_drag_start only reaches
        here while an edge is already revealed, meaning the picker just found something)."""
        origin_key = self._hover_open_edge_key
        origin = self._open_edges.get(origin_key)
        if origin is None:
            self._connection_drag = None
            return
        click_point = self._pick_world_position(event)
        if click_point is None:
            click_point = origin["midpoint"]
        self._connection_drag = {
            "origin_key": origin_key, "target_key": None,
            "origin_point": click_point, "last_pick_point": click_point,
        }
        self._apply_hover_open_edge_highlight(None)
        self._set_edge_highlight_actors("origin", origin_key, "red")
        self._line_end_screen_override = None
        self.builder_getter().set_pending_connection(origin["shape_id"], origin["raw_edge"], None, None)
        self._grab_frame()

    def _update_connection_drag(self, event):
        """Re-picks the nearest OPEN edge (excluding the origin's own shape -- Join mode never
        connects a shape to itself) to wherever the drag ray currently hits the mesh surface --
        highlights it yellow the same way plain hovering does (2026-09-19, explicit: "then it
        can hover over another edge (which will highlight in yellow)"), WITHOUT forwarding to
        BuilderPane's own hover-reveal (that would show a confusing second, passive highlight
        alongside the 2D side's own ACTIVE red pending-connection visual, which
        set_pending_connection below already drives) -- and mirrors a CHANGED target into 2D
        via that same call. The connecting line's own screen-space endpoint
        (self._line_end_screen_override) is updated on EVERY call regardless of whether the
        target changed -- it always follows the raw cursor position (2026-09-19, explicit: "the
        mouse drags out a connection in screen space"), which moves every tick even when the
        nearest-target result doesn't. self._connection_drag's own "last_pick_point" is kept in
        sync the same way, so _finish_connection_drag has a last-known 3D point to fall back on
        if the release itself doesn't land on any surface."""
        drag = self._connection_drag
        origin = self._open_edges.get(drag["origin_key"])
        if origin is None:
            return
        self._line_end_screen_override = (event.x, event.y)
        pos = self._pick_world_position(event)
        if pos is not None:
            drag["last_pick_point"] = pos
        target_key = self._nearest_open_edge_at_position(pos, exclude_shape_id=origin["shape_id"])
        self._apply_hover_open_edge_highlight(target_key)
        if target_key != drag["target_key"]:
            drag["target_key"] = target_key
            target = None if target_key is None else self._open_edges.get(target_key)
            self.builder_getter().set_pending_connection(
                origin["shape_id"], origin["raw_edge"],
                None if target is None else target["shape_id"],
                None if target is None else target["raw_edge"])
        self._grab_frame()

    def _finish_connection_drag(self, event):
        """Ends the drag (ButtonRelease-1) -- on a valid target, creates the real connection and
        PROMOTES both edges' highlights (origin already red; target's current yellow hover
        swapped to red) plus a red connecting line into self._pending_made_connection_actors, a
        PERSISTENT list that survives until the mesh itself catches up (2026-09-19, explicit:
        "mouse release causes both to be drawn in red with their midpoint connected in a thick
        red line (all drawn in 3d)... this persists until simulation converges and redraws").
        The connecting line runs from the drag's own PINNED starting point (wherever the press
        actually landed, see _start_connection_drag) to wherever THIS release itself lands --
        not either edge's midpoint (2026-09-19, explicit: "where that connection ends should be
        where your mouse released, not the midpoint of the second edge"); falls back to the
        last live pick point from _update_connection_drag (or, failing that, the target's own
        midpoint) if the release itself doesn't land on any surface. An incomplete drag (no
        target) is a plain cancel -- both edges' highlights are torn down, nothing persists,
        same as InteractiveBuilderApp letting a click-click connection lapse. An ILLEGAL
        connection (a vertex-merge conflict) is ALSO effectively a cancel -- create_connection
        returns False for one after already rolling it back and clearing this pane's own
        transient highlights itself (via BuilderPane._undo_illegal_connection ->
        undo_illegal_connection_from_builder, 2026-09-19 explicit bug report: "it should then
        undo the illegal move in both 2d and 3d") -- so the "made" branch below is simply
        skipped, nothing further to undo here."""
        drag, self._connection_drag = self._connection_drag, None
        self._line_end_screen_override = None
        self.builder_getter().set_pending_connection(None, None, None, None)
        origin = None if drag is None else self._open_edges.get(drag["origin_key"])
        target = (None if drag is None or drag["target_key"] is None
                  else self._open_edges.get(drag["target_key"]))
        made = False
        if origin is not None and target is not None:
            made = self.builder_getter().create_connection(
                origin["shape_id"], origin["raw_edge"], target["shape_id"], target["raw_edge"])
        if made:
            self._apply_hover_open_edge_highlight(None)  # clear the yellow hover on the target edge
            self._pending_made_connection_actors += self._edge_highlight_actors.pop("origin", [])
            self._pending_made_connection_actors += self._add_rounded_lines(
                target["segments"], "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
            release_point = self._pick_world_position(event)
            if release_point is None:
                release_point = drag.get("last_pick_point", target["midpoint"])
            origin_point = drag.get("origin_point", origin["midpoint"])
            self._pending_made_connection_actors += self._add_rounded_lines(
                np.array([origin_point, release_point]), "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
            self._rebuild_open_edges()
        elif origin is None or target is None:
            # A plain cancel (no target found) -- an illegal connection already tore its own
            # highlights down via undo_illegal_connection_from_builder, so only clean up here
            # for the "never had a target" case.
            self._set_edge_highlight_actors("origin", None, "red")
            self._apply_hover_open_edge_highlight(None)
        self._grab_frame()

    def add_pending_made_connection_from_builder(self, origin_info, target_info):
        """Called by BuilderPane._on_canvas_release whenever its own 2D Join gesture (click-
        click or drag-and-drop) successfully creates a NEW connection -- the same persistent 3D
        indicator applies regardless of which side the connection was actually made on
        (2026-09-19, explicit: "mouse release causes both to be drawn in red with their
        midpoint connected in a thick red line... this persists until simulation converges and
        redraws"). `origin_info`/`target_info` are the two endpoints' OWN self._open_edges
        dicts (with "segments"/"midpoint"), ALREADY resolved by the caller -- BuilderPane's own
        lookup has to happen BEFORE the connection completes, since completing immediately
        rebuilds that cache to exclude the two now-used edges (see _on_canvas_release's own
        docstring)."""
        self._pending_made_connection_actors += self._add_rounded_lines(
            origin_info["segments"], "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
        self._pending_made_connection_actors += self._add_rounded_lines(
            target_info["segments"], "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
        self._pending_made_connection_actors += self._add_rounded_lines(
            np.array([origin_info["midpoint"], target_info["midpoint"]]), "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
        self._grab_frame()

    def set_open_edge_drag_cancelled_from_builder(self):
        """Called by BuilderPane._set_tool_mode (a tool-mode switch, "when switching between
        modes, everything is deselected") and BuilderPane._on_escape_key (2026-09-19, explicit:
        "pressing esc should remove any in-progress connection in both 2d and 3d") whenever
        either could be interrupting an in-progress 3D drag -- clears the drag and its own
        TRANSIENT highlight state (hover/origin/target/connecting_line) without creating a
        connection, and without calling back into BuilderPane (whose own
        _set_tool_mode/_on_escape_key is what triggered this in the first place -- it already
        knows/shows its own cleared pending state). Never touches
        self._pending_made_connection_actors -- an already-successful connection's own
        persistent highlight is not what's being cancelled here.

        Also resets self._dragging/_last_xy IFF a connection-drag was actually active -- left
        alone otherwise, so this never disturbs an UNRELATED plain camera rotate-drag that
        happens to be in progress when a tool-mode switch or Esc fires. Without this, Esc
        pressed while the mouse button is still physically held down would cancel the
        connection but leave _dragging True with a now-STALE _last_xy, so the very next
        <B1-Motion> tick would jump the camera by whatever distance the cursor moved since the
        drag started, read as an abrupt, unexplained camera snap."""
        was_dragging_connection = self._connection_drag is not None
        if not was_dragging_connection and not self._edge_highlight_actors and self._hover_open_edge_key is None:
            return
        self._connection_drag = None
        self._hover_open_edge_key = None
        for role in list(self._edge_highlight_actors):
            self._set_edge_highlight_actors(role, None, "red")
        self._line_end_screen_override = None
        if was_dragging_connection:
            self._dragging = False
            self._last_xy = None
        self._grab_frame()

    def undo_illegal_connection_from_builder(self):
        """Called by BuilderPane._undo_illegal_connection whenever it just auto-reverted a
        just-made connection that turned the net invalid (2026-09-19, explicit bug report:
        "when i try to make an illegal join, the app does warn me... but it should then undo
        the illegal move in both 2d and 3d. redraw if needed") -- reuses
        set_open_edge_drag_cancelled_from_builder's own cleanup (the transient hover/origin/
        target/connecting-line highlights and any in-progress 3D drag it clears are exactly
        what a just-reverted connection could have left showing) and then re-syncs
        self._open_edges, since the two edges the now-undone connection used are open again."""
        self.set_open_edge_drag_cancelled_from_builder()
        self._rebuild_open_edges()
        self._grab_frame()

    def set_pending_connection_from_builder(self, from_shape, from_edge, to_shape, to_edge):
        """2D-drag-a-connection direction (2026-09-19, explicit: "vice versa from 2d to 3d") --
        called by BuilderPane whenever its own click-click/drag-and-drop Join gesture's pending
        connection or hover target changes. Mirrors the origin/target as this panel's own RED
        edge highlights, plus a red connecting line between their midpoints once both resolve
        (there's no 3D-panel cursor position for a 2D-originated drag, so unlike the 3D-native
        rubber band this is real 3D geometry, not a screen overlay -- it just runs straight
        between the two known points). Silently shows nothing for an edge whose shape isn't
        currently a plain, non-folded group in the displayed mesh (the same documented
        limitation _open_edges itself has). Ignored entirely while a 3D-originated drag of its
        own is active (self._connection_drag) -- the two directions can't really overlap (one
        mouse), but this keeps one from clobbering the other's highlights if they somehow did."""
        if self._connection_drag is not None:
            return
        origin_key = None if from_shape is None else (from_shape, from_edge)
        target_key = None if to_shape is None else (to_shape, to_edge)
        self._set_edge_highlight_actors("origin", origin_key, "red")
        self._set_edge_highlight_actors("target", target_key, "red")
        origin = None if origin_key is None else self._open_edges.get(origin_key)
        target = None if target_key is None else self._open_edges.get(target_key)
        for actor in self._edge_highlight_actors.pop("connecting_line", []):
            self.plotter.remove_actor(actor)
        if origin is not None and target is not None:
            self._edge_highlight_actors["connecting_line"] = self._add_rounded_lines(
                np.array([origin["midpoint"], target["midpoint"]]), "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
        self._grab_frame()

    def _set_hover_group(self, group):
        """3D-mouse-over-a-face direction: highlights base face `group`'s own polygon outline
        in yellow in BOTH this 3D panel AND the left pane's flat 2D canvas
        (BuilderPane.set_hover_shape) -- `group is None` clears it. Looks up `group`'s own
        source_polygon_id (the whole 2D shape it came from) and forwards THAT, not the raw
        group index, since a Polygon-Fold shape's several triangle groups all belong to one 2D
        shape."""
        shape_id = self._shape_id_of_group(group)
        self._apply_hover_highlight(set() if group is None else {group})
        self.builder_getter().set_hover_shape(shape_id)

    def set_hover_shape_from_builder(self, shape_id):
        """2D-mouse-over-a-shape direction (2026-09-19, explicit: "now make the opposite
        true") -- called by BuilderPane whenever the mouse moves over a different shape on its
        flat canvas (or leaves it, shape_id=None). Highlights EVERY 3D group whose own
        source_polygon_id matches `shape_id` (usually one, but a Polygon-Fold shape's triangles
        are several groups sharing one source_polygon_id) -- does NOT call back into
        BuilderPane.set_hover_shape, since the 2D side already knows what it's hovering and
        highlights itself; this only drives the 3D side."""
        self._apply_hover_highlight(self._groups_for_shape_ids({shape_id} if shape_id is not None else set()))

    def _display_pending_source_polygon_id(self):
        """self._pending_source_polygon_id, or -- while an inflate is actively RUNNING -- the
        FROZEN value from self._pre_click_snapshot instead (2026-09-29, explicit bug report:
        "when i make a change, while inflation is still going, sometimes hovering over objects
        will yield weird results... when inflation is still ongoing, selection/hovering should
        use the model BEFORE the change was made"). on_full_inflate_clicked/_diff_remove_face/
        _diff_reexport_and_relax all reassign self._pending_source_polygon_id (and self.
        base_faces/face_of_fine) SYNCHRONOUSLY, well before the run's own background thread
        even starts -- deliberately, so the mesh is fully staged for the NEXT _render() once the
        run finishes (see _diff_reexport_and_relax's own "Deliberately no self._render() here"
        comment) -- but that means for the WHOLE remaining duration of the run, these fields
        describe the NEW (post-edit) mesh while the panel is still actually SHOWING the OLD one
        (self._actor_to_group/_connection_edge_cache/_open_edges were all last rebuilt by the
        PREVIOUS real _render() call, and stay exactly as they were until the next one). Hover/
        click during that window must resolve a picked group index against whichever mesh is
        ACTUALLY on screen, not the one being computed underneath it -- self._pre_click_snapshot
        (captured by every pipeline entry point right before it touches anything, see
        _snapshot_mesh_state) is exactly that OLD, still-displayed state."""
        if self._running and self._pre_click_snapshot is not None:
            return self._pre_click_snapshot["pending_source_polygon_id"]
        return self._pending_source_polygon_id

    def _display_face_of_fine(self):
        """Same "frozen while running" rule as _display_pending_source_polygon_id (own
        docstring has the full reasoning), for self.face_of_fine -- used by _groups_present to
        validate a picked group index against whichever mesh is actually on screen."""
        if self._running and self._pre_click_snapshot is not None:
            return self._pre_click_snapshot["face_of_fine"]
        return self.face_of_fine

    def _display_connections(self):
        """Same "frozen while running" rule as _display_pending_source_polygon_id (own
        docstring has the full reasoning), for self.builder_getter().connections -- the live
        builder net already reflects the ONE edit that made this run eligible, so during the
        run it's the NEW list, not the one _connection_edge_cache's own (still-displayed, OLD)
        seams actually belong to. Used by _nearest_connection_at_position's own shape_id
        restriction, so a mid-run hover doesn't get excluded by looking up an old connection id
        against the wrong (already-edited) live list."""
        if self._running and self._pre_click_snapshot is not None:
            return self._pre_click_snapshot["builder_connections"]
        return self.builder_getter().connections

    def _shape_id_of_group(self, group):
        spid_list = self._display_pending_source_polygon_id()
        if group is not None and spid_list is not None and group < len(spid_list):
            return spid_list[group]
        return None

    def _group_polygon_n(self, group):
        """Side count to key POLYGON_COLORS with for base face `group` -- the ORIGINAL 2D
        shape's own `n` (via source_polygon_id), not `len(self.base_faces[group])`, since a
        Polygon-Fold shape's fan triangles each have their OWN base face with only 3 sides,
        which would otherwise color every fold-triangle as a triangle instead of as its real
        source polygon (2026-09-29, explicit bug report: a self-joined hexagon showed green,
        not the hexagon's own purple). Falls back to `len(self.base_faces[group])` whenever
        the shape lookup fails (no source_polygon_id yet, or a shape_id the builder no longer
        has -- both legitimate transient states, not errors)."""
        shape_id = self._shape_id_of_group(group)
        if shape_id is not None:
            shape = next((s for s in self.builder_getter().shapes if s["id"] == shape_id), None)
            if shape is not None:
                return shape["n"]
        return len(self.base_faces[group])

    def _groups_for_shape_ids(self, shape_ids):
        """Every 3D group whose own source_polygon_id is one of `shape_ids` -- usually one
        group per shape_id, but a Polygon-Fold shape's several triangle groups all share one
        source_polygon_id, so this can return more entries than `shape_ids` has. Reads via
        _display_pending_source_polygon_id (own docstring), not the live field directly, so
        this still resolves against whichever mesh is actually on screen while an inflate is
        running."""
        spid_list = self._display_pending_source_polygon_id()
        if not shape_ids or spid_list is None:
            return set()
        return {g for g, sid in enumerate(spid_list) if sid in shape_ids}

    def _groups_present(self):
        """Every group index that actually exists in self.face_of_fine RIGHT NOW (or, while an
        inflate is running, in the FROZEN pre-click self.face_of_fine still actually on screen
        -- see _display_face_of_fine) -- used to
        filter out STALE group numbers before they reach _group_boundary_offset_lines/
        _group_boundary_lines (2026-09-19, explicit crash report: deleting two faces from a
        dodecahedron sometimes raised "Empty meshes cannot be plotted", then left hover
        highlighting a different face than the one under the cursor). A diff pipeline path
        (_diff_remove_face, _diff_reexport_and_relax) reassigns/renumbers self.face_of_fine
        and self.base_faces BEFORE the next _render() -- deliberately, so "never redraw
        anything before real convergence" holds -- but self._hover_target_groups is a plain
        cache of raw group indices from whenever it was last set, with no way to know its own
        numbers went stale the instant that reassignment happened. _render()'s own tail already
        guards its group loops with `if group in groups_present`; _apply_hover_highlight/
        _apply_selection_highlight (which run OUTSIDE _render(), e.g. via the selection-
        forwarding cascade set_locked's own _redraw triggers) need the identical guard, since a
        stale index otherwise either builds an actor from an EMPTY boundary (a group that no
        longer exists at all -- the actual crash, in _add_rounded_lines' own add_mesh call) or,
        worse, silently highlights whatever DIFFERENT face now happens to occupy that same
        index in the renumbered mesh."""
        return set(self._display_face_of_fine() or ())

    def _apply_hover_highlight(self, groups):
        """Shared by both hover directions above -- swaps the current set of highlighted
        groups' yellow outline actors for `groups`'s own, MINUS whatever's currently selected
        (2026-09-19, explicit: "when you hover then select, the face should go from being
        highlighted (yellow) to being selected (red) [don't draw both]") -- `groups` itself is
        stashed unfiltered in self._hover_target_groups so _apply_selection_highlight can
        recompute the effective set from scratch whenever the selection (not the hover target)
        is what changed. A no-op if the EFFECTIVE set already matches the current hover (the
        common case -- most mouse-move events land on the same face/shape the previous one
        did), so a still cursor doesn't re-render on every motion tick. Cheap: only adds/
        removes the couple of highlight actors _add_rounded_lines makes per group (not a full
        _render()). Draws BOTH offset copies (_group_boundary_offset_lines) per group, not just
        one, so the highlight shows up whichever side of that face is currently being viewed.
        Intersected with _groups_present() -- see its own docstring for why a stale group index
        can otherwise reach here (a diff pipeline path renumbering self.face_of_fine out from
        under a cached self._hover_target_groups)."""
        self._hover_target_groups = frozenset(groups)
        effective = ((self._hover_target_groups & self._groups_present())
                     - self._groups_for_shape_ids(self._selected_shape_ids))
        if effective == self._hover_groups:
            return
        self._hover_groups = effective
        for actor in self._hover_actors:
            self.plotter.remove_actor(actor)
        self._hover_actors = []
        for group in effective:
            front_hl, back_hl = self._group_boundary_offset_lines(group)
            self._hover_actors += (
                self._add_rounded_lines(front_hl, "yellow", HOVER_HIGHLIGHT_LINE_WIDTH)
                + self._add_rounded_lines(back_hl, "yellow", HOVER_HIGHLIGHT_LINE_WIDTH))
        self._grab_frame()

    def _rebuild_hover_connection_actors(self):
        """Swaps self._hover_connection_actors for whatever self._hover_connection_id now
        needs -- shared by both hover directions AND _apply_connection_selection_highlight
        (whenever the SELECTED connection changes, the hovered one's own actors may need to
        appear/disappear too, even though the hover target itself didn't change). Excludes the
        currently selected connection so hovering it never redraws a redundant yellow line on
        top of its own red one (2026-09-19, explicit: "when you hover then select, the face
        should go from being highlighted (yellow) to being selected (red) [don't draw both]" --
        the same rule applies to connections)."""
        for actor in self._hover_connection_actors:
            self.plotter.remove_actor(actor)
        self._hover_connection_actors = []
        segments = self._connection_edge_cache.get(self._hover_connection_id)
        if (segments is not None and len(segments)
                and self._hover_connection_id != self._selected_connection_id):
            self._hover_connection_actors = self._add_rounded_lines(
                segments, "yellow", HOVER_HIGHLIGHT_LINE_WIDTH)

    def _set_hover_connection(self, conn_id):
        """3D-mouse-over-an-edge direction (Join mode only, see _on_panel_hover_motion):
        highlights connection `conn_id`'s own glued seam in yellow in BOTH this 3D panel AND
        the left pane's flat 2D canvas (BuilderPane.set_hover_connection) -- `conn_id is None`
        clears it. A no-op if `conn_id` already matches the current hover."""
        if conn_id == self._hover_connection_id:
            return
        self._hover_connection_id = conn_id
        self._rebuild_hover_connection_actors()
        self._grab_frame()
        self.builder_getter().set_hover_connection(conn_id)

    def set_hover_connection_from_builder(self, conn_id):
        """2D-mouse-over-a-connection direction -- called by BuilderPane whenever the mouse
        moves over a different connection on its flat canvas in Join mode (or leaves one,
        conn_id=None). Does NOT call back into BuilderPane.set_hover_connection, since the 2D
        side already knows/shows its own hover; this only drives the 3D side."""
        if conn_id == self._hover_connection_id:
            return
        self._hover_connection_id = conn_id
        self._rebuild_hover_connection_actors()
        self._grab_frame()

    def _select_connection(self, conn_id):
        if conn_id == self._selected_connection_id:
            return
        self._selected_connection_id = conn_id
        self._apply_connection_selection_highlight()
        self.builder_getter().set_selected_connection(conn_id)

    def set_selected_connection_from_builder(self, conn_id):
        """2D-select-a-connection direction -- called by BuilderPane whenever its own
        self.selected_connection_id changes (click/Delete/undo/redo/mode-switch on the 2D
        canvas). Does NOT call back into BuilderPane.set_selected_connection, since the 2D side
        already knows/shows its own selection; this only drives the 3D side."""
        if conn_id == self._selected_connection_id:
            return
        self._selected_connection_id = conn_id
        self._apply_connection_selection_highlight()

    def _apply_connection_selection_highlight(self):
        """Rebuilds this panel's own red connection-selection outline actor from
        self._selected_connection_id, then re-derives the hover highlight
        (_rebuild_hover_connection_actors) -- a connection that just became selected needs its
        own yellow hover actor (if any) torn down, and one that just got deselected while still
        hovered needs it back. Never forwards anything to BuilderPane -- both callers
        (_select_connection/set_selected_connection_from_builder) already handle their own
        forwarding (or deliberately don't), so doing it here too would risk a redundant round
        trip."""
        for actor in self._selected_connection_actors:
            self.plotter.remove_actor(actor)
        self._selected_connection_actors = []
        segments = self._connection_edge_cache.get(self._selected_connection_id)
        if segments is not None and len(segments):
            self._selected_connection_actors = self._add_rounded_lines(
                segments, "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
        self._rebuild_hover_connection_actors()
        self._grab_frame()

    # ---- click-to-select ----

    def _on_panel_click(self, event):
        """A plain click (press+release with no meaningful motion -- see _on_drag_end) on the
        3D panel. Dispatches by the LEFT pane's own tool mode (2026-09-19, explicit: "select
        faces... should only be possible in Move[M] mode... clicking on the [3d] connection
        selects it in both 2d and 3d"; Move+Join merged into Edit mode 2026-09-29, explicit):
        Edit mode selects a connection seam if the click landed within
        CONNECTION_PICK_TOLERANCE_FRACTION of one (_click_select_edge's own tolerance, same
        priority the 2D canvas's own merged Edit-mode click gives a handle/connection line over
        a shape body), else falls through to selecting a whole face (_click_select_face); Edit is
        this app's only tool mode now (2026-09-29, explicit: "remove the Anchor[A] mode"), so the
        `if mode == "edit":` guard below is purely defensive at this point, not reachable in
        practice.

        No selection at all while an inflate is running (2026-09-29, explicit user request:
        "disable hovering highlight and selecting while inflating is ongoing... only allow view
        changes like rotating/panning/zooming") -- same reasoning as _on_panel_hover_motion's
        own running-guard."""
        if self._running:
            return
        if not self._actor_to_group:
            return
        mode = self.builder_getter().tool_mode
        if mode == "edit":
            if not self._click_select_edge(event):
                # No seam close enough -- falls through to face selection, same as the 2D
                # canvas's own merged press handler does (super()._on_canvas_press_move always
                # clears any prior connection selection at its own top, regardless of what it
                # then hits) -- a stale red connection highlight shouldn't survive a click that
                # was clearly aimed at something else.
                self._select_connection(None)
                self._click_select_face(event)

    def _click_select_face(self, event):
        """Selects whichever face is under the cursor, deselecting any other previously
        selected face unless Ctrl is held (2026-09-19, explicit: "selecting in 3d should
        deselect any other previously selected faces" / "multiselect by holding down ctrl and
        clicking on multiple faces"). Clicking empty space (no actor under the cursor) clears
        the selection, same as BuilderPane's own empty-space click; Ctrl+click on empty space is
        a no-op (mirrors BuilderPane's own "leaves the existing selection alone" rule for that
        case, minus the marquee this panel has no equivalent of)."""
        width, height = self.panel_size
        # VTK's own pixel origin is bottom-left; Tk's (event.x/event.y) is top-left.
        self._picker.Pick(event.x, height - 1 - event.y, 0, self.plotter.renderer)
        group = self._actor_to_group.get(self._picker.GetActor())
        shape_id = self._shape_id_of_group(group)
        ctrl_held = bool(event.state & 0x0004)
        if shape_id is None:
            if ctrl_held:
                return
            new_ids = set()
        elif ctrl_held:
            new_ids = set(self._selected_shape_ids)
            new_ids.symmetric_difference_update({shape_id})
        else:
            new_ids = {shape_id}
        self._select_shape_ids(new_ids)

    def _click_select_edge(self, event):
        """Selects whichever connection's seam is nearest the cursor, if one is within
        CONNECTION_PICK_TOLERANCE_FRACTION (2026-09-19, explicit: "multiselect is not available
        in this mode" -- always REPLACES the selection, no Ctrl-toggle at all, unlike face
        selection). Restricted to the shape actually under the cursor, same as
        _on_panel_hover_motion's own edge lookups --
        see _nearest_connection_at_position's own docstring for why. Returns True (a connection
        WAS selected) or False (nothing within tolerance, selection untouched) -- _on_panel_click
        (Edit mode, 2026-09-29, explicit: Move+Join merged) uses this to decide whether to fall
        through to a face-select click instead, the same "handle/connection line beats a shape
        body" priority the 2D canvas's own merged press handler uses."""
        pos = self._pick_world_position(event)
        picked_shape_id = self._shape_id_of_group(self._actor_to_group.get(self._picker.GetActor()))
        conn_id = self._nearest_connection_at_position(pos, shape_id=picked_shape_id)
        if conn_id is None:
            return False
        self._select_connection(conn_id)
        return True

    def _select_shape_ids(self, shape_ids):
        shape_ids = set(shape_ids)
        if shape_ids == self._selected_shape_ids:
            return
        self._selected_shape_ids = shape_ids
        self._apply_selection_highlight()
        self.builder_getter().set_selected_shape_ids(shape_ids)

    def set_selected_shape_ids_from_builder(self, shape_ids):
        """2D-select-a-shape direction -- called by BuilderPane whenever its own
        self.selected_ids changes (click/ctrl-click/marquee/Delete/undo/redo/load on the 2D
        canvas). Does NOT call back into BuilderPane.set_selected_shape_ids, since the 2D side
        already knows/shows its own selection; this only drives the 3D side."""
        shape_ids = set(shape_ids)
        if shape_ids == self._selected_shape_ids:
            return
        self._selected_shape_ids = shape_ids
        self._apply_selection_highlight()

    def _apply_selection_highlight(self):
        """Rebuilds this panel's own red selection outline actors from self._selected_shape_ids
        (same incremental add/remove convention as _apply_hover_highlight), then re-derives the
        hover highlight's EFFECTIVE set from its last raw target (self._hover_target_groups) --
        a shape that just became selected needs its yellow hover actors (if any) torn down, and
        one that just got deselected while still under the cursor needs them back. Intersected
        with _groups_present() too, for the same "a diff pipeline path may have already
        renumbered self.face_of_fine" reason _apply_hover_highlight guards against -- normally
        redundant here (self._pending_source_polygon_id, which _groups_for_shape_ids reads, IS
        kept in sync with every such renumbering), but cheap insurance against the two ever
        being updated out of step."""
        for actor in self._selected_actors:
            self.plotter.remove_actor(actor)
        self._selected_actors = []
        for group in self._groups_for_shape_ids(self._selected_shape_ids) & self._groups_present():
            front_sel, back_sel = self._group_boundary_offset_lines(group)
            self._selected_actors += (
                self._add_rounded_lines(front_sel, "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
                + self._add_rounded_lines(back_sel, "red", SELECTED_HIGHLIGHT_LINE_WIDTH))
        self._apply_hover_highlight(self._hover_target_groups)
        self._grab_frame()

    # ---- rendering ----

    def _add_rounded_lines(self, segments, color, width):
        """add_lines, but with genuinely rounded caps/joins at every segment end -- returns a
        LIST of the actors this creates (a caller doing its own incremental add/remove, like
        _set_hover_group, needs to track/remove all of them, not just one).

        render_lines_as_tubes alone (set on the line actor's own Property afterward -- add_lines
        has no such parameter of its own, unlike add_mesh) only rounds each segment's CYLINDER
        BODY -- VTK's tube filter still caps every segment with a flat disk, not a hemisphere,
        so wherever two of these (disconnected, independently-capped) segments meet at a shared
        vertex, two flat-capped cylinder ends meeting at an angle reads as a visible bevel/facet,
        not a smooth round join (2026-09-19, explicit: "i don't think the line ends are
        rounded... they still look beveled"). A small sphere point-sprite at every DISTINCT
        vertex the segments use (render_points_as_spheres + point_size, no custom glyph geometry
        needed) fills in exactly that gap, rounding off both the joints and the otherwise-flat
        end caps. Used for every line-primitive actor this pane draws (the polygon-rim overlay,
        front and back, and the yellow hover highlight). NOT used for the FINE subdivision
        wireframe (add_mesh's own show_edges, in _render) -- PyVista silently drops show_edges
        entirely whenever render_lines_as_tubes is also requested on the same add_mesh call,
        which would delete that wireframe outright rather than just rounding its caps, so it
        keeps VTK's default flat line ends. Returns [] for an empty `segments` (no group/edge
        boundary to draw at all) instead of calling add_mesh on a zero-point PolyData, which
        PyVista raises ValueError on (2026-09-19, explicit crash report: a stale group index --
        see _apply_hover_highlight's own docstring on why that could happen -- reached here via
        an empty _group_boundary_offset_lines result)."""
        if len(segments) == 0:
            return []
        line_actor = self.plotter.add_lines(segments, color=color, width=width)
        line_actor.prop.render_lines_as_tubes = True
        unique_points = np.unique(segments.reshape(-1, 3), axis=0)
        points_actor = self.plotter.add_mesh(
            pv.PolyData(unique_points), color=color, style="points",
            render_points_as_spheres=True, point_size=width)
        return [line_actor, points_actor]

    def _group_boundary_lines(self, group):
        """The ORIGINAL polygon's own rim, at its CURRENT (possibly already-inflated) 3D
        positions, traced through every FINE subdivision vertex that lies along it -- NOT a
        straight chord between the two original corners, which would cut straight through the
        inflated volume instead of following the actual (curved/faceted) surface (2026-09-19,
        explicit: "you have to draw the subdivisions that make up those edges... they wouldn't
        be on the surface" -- applies equally to the always-drawn polygon outline (_render) and
        the yellow hover highlight (_set_hover_group), both of which call this).

        Found by counting how many of `group`'s own fine triangles each of their edges belongs
        to: a spoke/internal-to-the-fan edge is shared by exactly TWO triangles in this same
        group (so it cancels out), while a rim edge (whether or not it's been quartered into
        shorter segments by later subdivision levels) belongs to only ONE -- its other triangle
        is in a DIFFERENT group, on the far side of that edge. The result is already every
        SHORT segment making up the rim, in whatever order the count dict yields them --
        add_lines doesn't need them connected into one ordered polyline, just paired up as
        (start, end)."""
        boundary_edges = self._group_boundary_edge_set(group)
        segments = np.empty((2 * len(boundary_edges), 3))
        for i, (u, v) in enumerate(boundary_edges):
            segments[2 * i] = self.positions[u]
            segments[2 * i + 1] = self.positions[v]
        return segments

    def _group_boundary_edge_set(self, group):
        """{(u, v), ...} (sorted vertex-id pairs, u < v) for every boundary edge of `group` --
        the identity half of _group_boundary_lines (see its own docstring for the counting
        rule), split out so _connection_edge_segments can intersect two groups' own boundary
        sets to find their SHARED seam without caring about actual positions."""
        edge_count = {}
        for face, bf in zip(self.faces, self.face_of_fine):
            if bf != group:
                continue
            a, b, c = face
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_count[key] = edge_count.get(key, 0) + 1
        return {e for e, count in edge_count.items() if count == 1}

    def _connection_edge_segments(self, conn):
        """Best-effort 3D geometry for Join-mode connection `conn`: the fine-mesh boundary
        segments where `conn["a_shape"]`/`conn["b_shape"]`'s own currently-displayed 3D patches
        are glued together. Empty (no 3D highlight, 2D still works fine on its own) when:
        `a_shape == b_shape` (a Polygon-Fold self-connection glues two edges of the SAME shape,
        so a boundary-intersection can't tell its seam apart from that shape's own ordinary
        outer rim -- out of scope here), or either shape isn't currently in the displayed mesh
        at all (net edited since the last Inflate).

        The raw intersection of the two shapes' own boundary edge sets can trace out MORE than
        just this one connection's own seam -- two shapes glued by several distinct connections
        at once, ones whose base edges happen to share a corner, leave the WHOLE glued boundary
        between that shape pair as one continuous chain, not one separate piece per connection
        (2026-09-29, explicit bug report: "when i select one connection... the 3d view shows 3
        edges selected" -- neighboring connections along that same chain were being highlighted
        right along with the one actually clicked, since nothing here previously distinguished
        one connection's own fine-mesh sub-segments from a NEIGHBORING connection's, once their
        two base edges turned out to share an endpoint). Narrowed down to just the segments
        actually BETWEEN `conn`'s own two base-mesh endpoints -- found via
        _connection_base_vertex_endpoints (this connection's own two BASE/coarse vertex ids,
        read straight off self.base_faces the same way _current_root_to_vertex_id does) and
        _boundary_edge_path (the shortest path between them through the raw intersection,
        stopping at the far endpoint rather than continuing into whatever ELSE happens to be
        reachable from it) -- unless either endpoint can't be found at all, or no path between
        them exists (both: a stale connection whose shape/edge no longer matches the currently-
        displayed mesh), in which case every shared seam is returned exactly as before, rather
        than showing nothing."""
        a_shape_id, b_shape_id = conn["a_shape"], conn["b_shape"]
        if a_shape_id is None or b_shape_id is None or a_shape_id == b_shape_id:
            return np.empty((0, 3))
        a_edges, b_edges = set(), set()
        for group in self._groups_for_shape_ids({a_shape_id}):
            a_edges |= self._group_boundary_edge_set(group)
        for group in self._groups_for_shape_ids({b_shape_id}):
            b_edges |= self._group_boundary_edge_set(group)
        shared = a_edges & b_edges
        if shared:
            endpoints = self._connection_base_vertex_endpoints(conn)
            if endpoints is not None:
                isolated = self._boundary_edge_path(shared, *endpoints)
                if isolated:
                    shared = isolated
        segments = np.empty((2 * len(shared), 3))
        for i, (u, v) in enumerate(shared):
            segments[2 * i] = self.positions[u]
            segments[2 * i + 1] = self.positions[v]
        return segments

    def _connection_base_vertex_endpoints(self, conn):
        """The two BASE (coarse) vertex ids `conn`'s own glued edge (its `a_shape`'s `a_edge`,
        running corner `a_edge` -> corner `(a_edge + 1) % n`, same convention _vertex_roots'
        own docstring uses) runs between right now -- via the SAME shape/corner -> base-id
        lookup _current_root_to_vertex_id already establishes for the whole mesh, restricted to
        just this one shape/edge -- or None if `a_shape` isn't currently in the displayed mesh,
        or its corner count no longer matches self.base_faces (both: net edited since the last
        Inflate)."""
        shape_id, edge_index = conn["a_shape"], conn["a_edge"]
        groups = self._groups_for_shape_ids({shape_id})
        if not groups:
            return None
        group = next(iter(groups))
        shape = next((s for s in self.builder_getter().shapes if s["id"] == shape_id), None)
        if shape is None or group >= len(self.base_faces):
            return None
        corners = _shape_face_corner_order(shape)
        face = self.base_faces[group]
        if len(corners) != len(face) or edge_index >= len(corners):
            return None
        corner_to_base_id = dict(zip(corners, face))
        n = len(corners)
        u = corner_to_base_id.get(edge_index)
        v = corner_to_base_id.get((edge_index + 1) % n)
        return None if u is None or v is None else (u, v)

    def _boundary_edge_path(self, edges, start, end):
        """The sequence of `edges` ({(u, v), ...}) along the SHORTEST path from vertex `start`
        to vertex `end`, walking edge to edge -- isolates ONE specific glued seam out of
        _connection_edge_segments' own raw `shared` set when it traces out more than just that
        one connection's own edge (own docstring has the full reasoning). A plain BFS with
        predecessor tracking, stopping the instant `end` is reached rather than exploring
        the rest of the graph -- deliberately NOT "every edge reachable from `start`": a
        neighboring connection's own edge, sharing a corner with this one, is reachable from
        `start` too, but lies off to the side of the direct start->end path, not on it, so a
        plain reachability walk wouldn't have excluded it. Empty if `start`/`end` aren't both
        endpoints of a connected path through `edges` at all (the caller falls back to the
        unfiltered set in that case, rather than showing nothing)."""
        if start == end:
            return set()
        adjacency = {}
        for u, v in edges:
            adjacency.setdefault(u, []).append(v)
            adjacency.setdefault(v, []).append(u)
        if start not in adjacency or end not in adjacency:
            return set()
        predecessor = {start: None}
        frontier = [start]
        while frontier and end not in predecessor:
            next_frontier = []
            for node in frontier:
                for neighbor in adjacency[node]:
                    if neighbor not in predecessor:
                        predecessor[neighbor] = node
                        next_frontier.append(neighbor)
            frontier = next_frontier
        if end not in predecessor:
            return set()
        path_edges = set()
        node = end
        while predecessor[node] is not None:
            prev = predecessor[node]
            path_edges.add((prev, node) if prev < node else (node, prev))
            node = prev
        return path_edges

    def _group_boundary_owners(self, group):
        """{(u, v) sorted: owning_face} for every boundary edge of `group` -- used by
        _group_boundary_offset_lines, which needs each boundary edge's own OWNING triangle (see
        _group_boundary_lines' own docstring for why an edge belongs to only one triangle
        within its group: a spoke/internal-to-the-fan edge is shared by two triangles in the
        SAME group and cancels out of this dict; only a true rim edge, whose other triangle is
        in a DIFFERENT group, survives)."""
        edge_owner = {}
        for face, bf in zip(self.faces, self.face_of_fine):
            if bf != group:
                continue
            a, b, c = face
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_owner.setdefault(key, []).append(face)
        return [(edge, tris[0]) for edge, tris in edge_owner.items() if len(tris) == 1]

    def _group_boundary_offset_lines(self, group):
        """(front_segs, back_segs) -- every boundary edge of `group`, nudged a hair along a
        PER-VERTEX averaged owning-triangle normal (front) or the opposite way (back) --
        _boundary_vertex_offsets' own docstring has the full reasoning for why per-vertex,
        not per-edge -- so the two copies don't Z-fight when drawn co-located on the real
        surface. Used for BOTH the ordinary polygon-rim overlay and the yellow hover highlight
        (_render/_set_hover_group)
        -- a ribbon-mesh, exactly-culled version of the rim was tried in between (giving the
        front/back copies genuinely distinct colors with no grazing-angle bleed at all), but
        came out visibly messier overall (2026-09-19, explicit: "the front/backside rims are
        super messy now... go back to how things are and just draw both front/back rims in
        light gray (80% white)") -- reverted. Drawing BOTH copies in the SAME color (RIM_COLOR)
        sidesteps the front/back distinction issue entirely: it no longer matters which copy is
        more visible from a given angle, since they're indistinguishable either way."""
        boundary = self._group_boundary_owners(group)
        # A hair's width relative to the model's own overall size -- enough to resolve Z-
        # fighting reliably, small enough that the rim still reads as sitting right on the
        # surface rather than visibly floating off it.
        nudge = self._half * 0.002
        vertex_offsets = _boundary_vertex_offsets(boundary, self.positions, nudge)
        front_pairs, back_pairs = [], []
        for (u, v), _owner in boundary:
            off_u, off_v = vertex_offsets[u], vertex_offsets[v]
            # NOT named `pv` -- that would shadow the module-level `pyvista as pv` import (bit
            # us once already in the sibling ribbon method this replaced).
            p_u, p_v = self.positions[u], self.positions[v]
            front_pairs.append((p_u + off_u, p_v + off_v))
            back_pairs.append((p_u - off_u, p_v - off_v))

        def to_segments(pairs):
            segments = np.empty((2 * len(pairs), 3))
            for i, (p, q) in enumerate(pairs):
                segments[2 * i] = p
                segments[2 * i + 1] = q
            return segments

        return to_segments(front_pairs), to_segments(back_pairs)

    def _capture_replay_frame(self, faces, face_of_fine, positions):
        """Appends one snapshot to self._replay_frames (2026-09-29, explicit user request --
        see _on_replay_slider_moved's own docstring). `positions`' own dict VALUES are deep-
        copied -- relax_once/estimate_pressure_for_target_stretch's own on_progress callbacks
        hand back array views into a `pts` array that keeps changing step to step (see
        stretchy_mesh._positions_and_stretch), so a captured frame would otherwise silently
        change out from under an earlier one. `faces`/`face_of_fine` are never mutated in
        place by anything in this pipeline (every step reassigns a fresh list instead -- same
        reasoning _snapshot_mesh_state's own docstring gives), so those are kept by reference."""
        self._replay_frames.append({
            "faces": faces, "face_of_fine": face_of_fine,
            "positions": {v: np.array(p, dtype=float) for v, p in positions.items()},
        })

    def _update_replay_slider(self):
        """Configures the replay scrubber to match self._replay_frames -- enabled, ranged over
        every captured frame index, iff at least 2 exist; positioned at the LAST one (the
        live-equivalent end, see _on_replay_slider_moved). Called once a run finishes
        successfully (_on_inflate_step_done's Level-3 Done branch) and whenever a builder edit
        resets the scrub back to live (refresh_diff_eligibility) -- ttk.Scale.set DOES fire
        `command`, so the latter harmlessly re-triggers _on_replay_slider_moved at the same
        (live) index, not a real scrub."""
        frames = self._replay_frames
        if not frames or len(frames) < 2:
            self._replay_slider.configure(to=0)
            self._replay_slider.set(0)
            self._replay_slider.state(["disabled"])
            self._replay_scrub_index = None
            return
        self._replay_slider.configure(from_=0, to=len(frames) - 1)
        self._replay_slider.state(["!disabled"])
        self._replay_slider.set(len(frames) - 1)

    def _on_replay_slider_moved(self, value):
        """`command` callback for the debug-mode replay scrubber (2026-09-29, explicit user
        request -- "add a replay slider... to replay the last full/diff inflate"): scrubs
        through self._replay_frames, every (faces, face_of_fine, positions) snapshot captured
        across the WHOLE last completed run (Level 0's relax_initial_configuration plus every
        Level 1-3/single-Diff-pass estimate_pressure_for_target_stretch call it actually ran,
        in chronological order -- see _capture_replay_frame's own call sites). `value` is
        ttk.Scale's string-formatted float, rounded to the nearest captured frame index
        (clamped, since a Scale can report a value fractionally past its `to` during a fast
        drag). Purely a display override -- never touches self.faces/self.positions/etc., so
        scrubbing can't affect what the next real Inflate continues from.

        The RIGHTMOST position (the final, already-live frame) draws through the ordinary
        _render() -- full hover/selection/open-edge picking, exactly like right after the run
        finished. Every other position draws through _render_replay_frame instead, a reduced
        STATIC view (colored face mesh only, no rim outline/hover/selection/open-edge picking)
        -- a mid-history frame has no live-net hover/selection state that would make sense to
        overlay on it anyway, and _group_boundary_offset_lines/_rebuild_open_edges/etc. all
        read self.positions directly, not whatever frame is being scrubbed to."""
        frames = self._replay_frames
        if not frames:
            return
        idx = max(0, min(int(round(float(value))), len(frames) - 1))
        if idx == len(frames) - 1:
            self._replay_scrub_index = None
            self._render()
        else:
            self._replay_scrub_index = idx
            self._render_replay_frame(frames[idx])

    def _render_replay_frame(self, frame):
        """Static, reduced-feature redraw of one self._replay_frames entry -- the colored face
        mesh (same per-group POLYGON_COLORS/inside-darkening convention _render's own first
        loop uses) PLUS its own bold rim outline and, when their debug-mode checkboxes are
        checked, the SAME face-normal/vertex-normal/repulsive-force overlays _render draws for
        the live mesh -- but no hover/selection/open-edge picking (see _on_replay_slider_moved's
        own docstring for why). self._actor_to_group is cleared, not repopulated -- a scrubbed
        frame isn't pickable, so hover/click during a scrub simply find nothing, same as an
        empty panel.

        2026-09-29, explicit user request ("in 3d view, debug mode should show the polygon
        edges, face normals/vertex normals/repulsive forces... as the user uses the replay
        slider"): every overlay here is genuinely computed fresh per scrub tick, not just at
        release -- repulsion_force is only ever run over self._repulsion_vertex_ids()' own
        small, FIXED base-corner set (see its own comment: intentionally excluded from the
        full fine-mesh vertex count specifically to stay cheap), so recomputing it live during
        a drag is no more expensive than the ordinary rebuild <ttk.Scale> already does on every
        `command` firing; there's no separate throttle-to-release path to fall back to."""
        plotter = self.plotter
        plotter.clear()
        # plotter.clear() wipes EVERY light too (Renderer.clear() calls its own
        # remove_all_lights() internally, not just actors) -- re-applied every call, not just
        # once at plotter construction (2026-09-29, explicit bug report: "I don't see any
        # shading" -- the custom KEY/FILL rig was being silently wiped on the very first real
        # render, long before the user ever saw a frame; see _setup_plotter_lighting's own
        # docstring). Cheap: two lightweight VTK Light objects, no mesh work.
        self._setup_plotter_lighting()
        self._actor_to_group = {}
        faces = frame["faces"]
        positions = frame["positions"]
        face_of_fine = frame["face_of_fine"]
        vertex_ids = sorted(positions)
        idx = {v: i for i, v in enumerate(vertex_ids)}
        points = np.array([positions[v] for v in vertex_ids])
        lo, hi = points.min(axis=0), points.max(axis=0)
        self._center = (lo + hi) / 2
        self._half = float(np.linalg.norm(points - self._center, axis=1).max()) + 1e-6
        groups_present = sorted(set(face_of_fine))
        for group in groups_present:
            group_faces = [f for f, bf in zip(faces, face_of_fine) if bf == group]
            if not group_faces:
                continue
            n = self._group_polygon_n(group) if group < len(self.base_faces) else 3
            color = POLYGON_COLORS.get(n, FACE_COLORS[group % len(FACE_COLORS)])
            inside_color = _darken_color(color)
            face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
            mesh = pv.PolyData(points, face_conn)
            plotter.add_mesh(mesh, color=color, show_edges=True,
                              edge_color=_weighted_color(color, FRONT_EDGE_WEIGHT),
                              line_width=SUBDIVISION_EDGE_LINE_WIDTH, culling="back",
                              smooth_shading=SMOOTH_SHADING, ambient=MATERIAL_AMBIENT,
                              diffuse=MATERIAL_DIFFUSE, specular=MATERIAL_SPECULAR,
                              specular_power=MATERIAL_SPECULAR_POWER)
            plotter.add_mesh(mesh, color=inside_color, show_edges=True,
                              edge_color=_weighted_color(inside_color, BACK_EDGE_WEIGHT),
                              line_width=SUBDIVISION_EDGE_LINE_WIDTH, culling="front",
                              smooth_shading=SMOOTH_SHADING, ambient=MATERIAL_AMBIENT,
                              diffuse=MATERIAL_DIFFUSE, specular=MATERIAL_SPECULAR,
                              specular_power=MATERIAL_SPECULAR_POWER)
            front_rim, back_rim = self._frame_group_boundary_offset_lines(
                faces, face_of_fine, positions, group)
            if len(front_rim):
                self._add_rounded_lines(front_rim, RIM_COLOR, POLYGON_EDGE_LINE_WIDTH)
            if len(back_rim):
                self._add_rounded_lines(back_rim, RIM_COLOR, POLYGON_EDGE_LINE_WIDTH)

        if self.show_normals_var.get():
            starts, ends = [], []
            for a, b, c in faces:
                pa, pb, pc = positions[a], positions[b], positions[c]
                normal = np.cross(pb - pa, pc - pa)
                normal_len = np.linalg.norm(normal)
                if normal_len < 1e-12:
                    continue
                centroid = (pa + pb + pc) / 3.0
                edge_len = (np.linalg.norm(pb - pa) + np.linalg.norm(pc - pb)
                            + np.linalg.norm(pa - pc)) / 3.0
                starts.append(centroid)
                ends.append(centroid + normal / normal_len * edge_len * NORMAL_LENGTH_FRACTION)
            if starts:
                segment_points = np.empty((2 * len(starts), 3))
                segment_points[0::2] = starts
                segment_points[1::2] = ends
                plotter.add_lines(segment_points, color=NORMAL_COLOR, width=2.0)

        if self.show_vertex_normals_var.get():
            starts, ends = [], []
            for v, (unit_normal, mean_edge_len) in _vertex_normals(faces, positions).items():
                starts.append(positions[v])
                ends.append(positions[v] + unit_normal * mean_edge_len * NORMAL_LENGTH_FRACTION)
            if starts:
                segment_points = np.empty((2 * len(starts), 3))
                segment_points[0::2] = starts
                segment_points[1::2] = ends
                plotter.add_lines(segment_points, color=VERTEX_NORMAL_COLOR, width=2.0)

        if self.show_repulsive_forces_var.get():
            repulsion_ids = [v for v in self._repulsion_vertex_ids() if v in idx]
            if repulsion_ids:
                rep_indices = [idx[v] for v in repulsion_ids]
                mult_by_id = self._repulsion_vertex_multipliers() or {}
                rep_mults = [mult_by_id.get(v, 1.0) for v in repulsion_ids]
                forces = repulsion_force(points, indices=rep_indices, vertex_multipliers=rep_mults)
                force_lens = {v: np.linalg.norm(forces[idx[v]]) for v in repulsion_ids}
                max_len = max(force_lens.values(), default=0.0)
                starts, ends = [], []
                if max_len >= 1e-12:
                    for v in repulsion_ids:
                        force_len = force_lens[v]
                        if force_len < 1e-12:
                            continue
                        force_vec = forces[idx[v]]
                        starts.append(positions[v])
                        ends.append(positions[v] + force_vec / max_len
                                    * EDGE_LENGTH * NORMAL_LENGTH_FRACTION)
                if starts:
                    segment_points = np.empty((2 * len(starts), 3))
                    segment_points[0::2] = starts
                    segment_points[1::2] = ends
                    plotter.add_lines(segment_points, color=REPULSION_FORCE_COLOR, width=2.0)

        self._apply_camera()
        self._grab_frame()

    def _frame_group_boundary_offset_lines(self, faces, face_of_fine, positions, group):
        """Same (front_segs, back_segs) shape/nudge convention as _group_boundary_offset_lines
        (see its own docstring) -- reimplemented over explicit faces/face_of_fine/positions (a
        self._replay_frames entry's own, not self.faces/self.face_of_fine/self.positions)
        rather than parametrizing that method itself, since every OTHER caller of it (_render's
        own live rim, _set_hover_group's yellow highlight) always means the live mesh and would
        otherwise need to pass the same three arguments right back through for no reason.
        `self._half` (the Z-fighting nudge distance) is read as-is -- already set from THIS
        frame's own bounding box by the caller (_render_replay_frame), same order _render's own
        live path already establishes it in."""
        edge_owner = {}
        for face, bf in zip(faces, face_of_fine):
            if bf != group:
                continue
            a, b, c = face
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_owner.setdefault(key, []).append(face)
        boundary = [(edge, tris[0]) for edge, tris in edge_owner.items() if len(tris) == 1]
        nudge = self._half * 0.002
        vertex_offsets = _boundary_vertex_offsets(boundary, positions, nudge)
        front_pairs, back_pairs = [], []
        for (u, v), _owner in boundary:
            off_u, off_v = vertex_offsets[u], vertex_offsets[v]
            p_u, p_v = positions[u], positions[v]
            front_pairs.append((p_u + off_u, p_v + off_v))
            back_pairs.append((p_u - off_u, p_v - off_v))

        def to_segments(pairs):
            segments = np.empty((2 * len(pairs), 3))
            for i, (p, q) in enumerate(pairs):
                segments[2 * i] = p
                segments[2 * i + 1] = q
            return segments

        return to_segments(front_pairs), to_segments(back_pairs)

    def _render(self):
        """Redraws the single panel from whatever self.faces/self.positions/self.face_of_fine
        currently hold -- colored per ORIGINAL base face (face_of_fine) by POLYGON_COLORS[n]
        (n = that base face's own SOURCE POLYGON's vertex count, via _group_polygon_n --
        NOT len(self.base_faces[group]), since a Polygon-Fold shape's fan triangles each have
        their own 3-sided base face and would otherwise color as a triangle instead of the
        real source polygon), the SAME fixed per-shape-type color the left
        pane's canvas draws that shape with (POLYGON_COLORS is keyed by side count, not by
        instance -- see interactive_builder_app's own _draw_shape/_build_palette_entry), so a
        square on the left inflates into a square-colored patch on the right (2026-09-19,
        explicit: "should use the same colours as the left side"). Camera framing/rotation/
        pan/zoom come from self._camera (see _apply_camera/the drag/pan/scroll handlers below)
        instead of a fresh "iso" + reset_camera() every redraw, so a user's view survives
        across Inflate steps. Each face's own fill mesh is drawn as TWO separate, culled actors
        sharing the same PolyData -- an OUTSIDE one (culling="back", so only outward-facing
        triangles render) with its FINE subdivision wireframe faintly visible (show_edges=True,
        FRONT_EDGE_WEIGHT/SUBDIVISION_EDGE_LINE_WIDTH -- 85% face color/15% white, much
        fainter/thinner than the bold polygon-outline overlay drawn on top of it), and an
        INSIDE one (culling="front", only inward-facing triangles) with its own edge_color
        blended 85% ITS OWN (darkened inside) fill color/15% BLACK (BACK_EDGE_WEIGHT) instead of
        against white. TWO actors, not one with backface_params, because VTK's edge
        color/visibility belongs to the ACTOR (its
        mapper), not to front vs. back faces -- backface_params's own edge_color is silently
        ignored, so a single actor always drew every edge (inside or outside) in the OUTSIDE
        color regardless (2026-09-19, explicit bug report, confirmed via a screenshot: "the
        inside lines still look lighter than the face colours"). Plus a SEPARATE add_lines call
        for just that polygon's own outline (_group_boundary_lines). Rebuilds
        self._actor_to_group ({vtk actor: group index}, for hover/click picking -- both the
        outside and inside actor map to the same group) and re-applies the current hover
        highlight (self._hover_groups) and selection highlight (self._selected_shape_ids), since
        plotter.clear() just destroyed the previous highlight actors along with everything else.
        Also rebuilds self._connection_edge_cache (see its own docstring) fresh from the
        builder's CURRENT connections and this new mesh -- a stale cache would misreport a
        connection's own 3D seam as gone (or reuse a coincidentally-matching but now-wrong one)
        after any edit."""
        plotter = self.plotter
        plotter.clear()
        # plotter.clear() wipes EVERY light too (Renderer.clear() calls its own
        # remove_all_lights() internally, not just actors) -- see _setup_plotter_lighting's own
        # docstring for why this has to be reapplied on every render, not just once at plotter
        # construction.
        self._setup_plotter_lighting()
        self._actor_to_group = {}
        self._hover_actors = []
        self._selected_actors = []
        self._hover_connection_actors = []
        self._selected_connection_actors = []
        # A freshly-rebuilt mesh means any open-edge hover/drag highlight AND any just-made
        # connection's own persistent red highlight are either now REAL mesh geometry (a
        # converged inflate) or the attempt reverted -- either way, plotter.clear() just
        # destroyed all of these actors along with everything else, so the tracking dicts/lists
        # are reset too.
        self._edge_highlight_actors = {}
        self._pending_made_connection_actors = []
        self._connection_edge_cache = {
            conn["id"]: self._connection_edge_segments(conn)
            for conn in self.builder_getter().connections
        }
        self._rebuild_open_edges()
        if self.faces and self.positions and self.base_faces:
            vertex_ids = sorted(self.positions)
            idx = {v: i for i, v in enumerate(vertex_ids)}
            points = np.array([self.positions[v] for v in vertex_ids])
            face_of_fine = self.face_of_fine or list(range(len(self.faces)))
            groups_present = sorted(set(face_of_fine))
            for group in groups_present:
                group_faces = [f for f, bf in zip(self.faces, face_of_fine) if bf == group]
                if not group_faces:
                    continue
                n = self._group_polygon_n(group)
                color = POLYGON_COLORS.get(n, FACE_COLORS[group % len(FACE_COLORS)])
                inside_color = _darken_color(color)
                face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
                mesh = pv.PolyData(points, face_conn)
                # TWO actors sharing the same mesh, not one with backface_params -- VTK's edge
                # color/visibility is a property of the ACTOR (its mapper), not of front vs.
                # back faces, so backface_params's own edge_color is silently ignored and every
                # edge -- inside or outside -- used to come out looking like the OUTSIDE one
                # regardless (2026-09-19, explicit bug report: "the inside lines still look
                # lighter than the face colours" -- confirmed via a screenshot). culling='back'
                # keeps only front-facing (outward) triangles+edges in one actor;
                # culling='front' keeps only back-facing (inward, seen through a gap) ones in
                # the other, each getting its own genuinely independent edge_color this way.
                # NOT render_lines_as_tubes here -- PyVista silently drops show_edges entirely
                # whenever render_lines_as_tubes is also set ("`show_edges=True` not supported
                # when `render_lines_as_tubes=True`. Ignoring `show_edges`", caught testing this
                # change), which would delete the fine subdivision wireframe outright rather
                # than just squaring its line caps. The rim overlay/hover highlight below
                # (plain add_lines actors, not a show_edges mesh) don't have this conflict, so
                # those get rounded ends (2026-09-19, explicit: "make all the line ends
                # rounded") via _add_rounded_lines; the subdivision wireframe's own line ends
                # stay as VTK's default flat caps.
                outside_actor = plotter.add_mesh(
                    mesh, color=color, show_edges=True,
                    edge_color=_weighted_color(color, FRONT_EDGE_WEIGHT),
                    line_width=SUBDIVISION_EDGE_LINE_WIDTH, culling="back",
                    smooth_shading=SMOOTH_SHADING, ambient=MATERIAL_AMBIENT,
                    diffuse=MATERIAL_DIFFUSE, specular=MATERIAL_SPECULAR,
                    specular_power=MATERIAL_SPECULAR_POWER)
                inside_actor = plotter.add_mesh(
                    mesh, color=inside_color, show_edges=True,
                    # Blended from inside_color (the actor's OWN fill color) toward WHITE --
                    # same idea as the outside edges, just off the darker inside fill color
                    # instead of the bright outward one (2026-09-19, explicit: "backside lines
                    # should be 85% backside face color and 15% white").
                    edge_color=_weighted_color(inside_color, BACK_EDGE_WEIGHT),
                    line_width=SUBDIVISION_EDGE_LINE_WIDTH, culling="front",
                    smooth_shading=SMOOTH_SHADING, ambient=MATERIAL_AMBIENT,
                    diffuse=MATERIAL_DIFFUSE, specular=MATERIAL_SPECULAR,
                    specular_power=MATERIAL_SPECULAR_POWER)
                self._actor_to_group[outside_actor] = group
                self._actor_to_group[inside_actor] = group
                # The bold rim overlay -- both offset copies (_group_boundary_offset_lines, see
                # its own docstring for the front/back history) drawn in the SAME plain light
                # grey (2026-09-19, explicit: "just draw both front/back rims in light gray (80%
                # white)"). _add_rounded_lines (not a plain add_lines) rounds every segment's
                # caps/joins (2026-09-19, explicit: "make all the line ends rounded").
                front_rim, back_rim = self._group_boundary_offset_lines(group)
                if len(front_rim):
                    self._add_rounded_lines(front_rim, RIM_COLOR, POLYGON_EDGE_LINE_WIDTH)
                if len(back_rim):
                    self._add_rounded_lines(back_rim, RIM_COLOR, POLYGON_EDGE_LINE_WIDTH)

            # Debug mode's "Show face/vertex normals"/"Show repulsive forces" toggles
            # (2026-09-29, explicit user request -- diagnosing a crumpled guest boundary after a
            # Diff Inflate join) -- same drawing convention as inflate_polyhedron_app's own
            # identically-named toggles (_draw_level_panel): a line segment per vertex/face,
            # NORMAL_LENGTH_FRACTION of the local mean edge length long, direction only (not
            # scaled by any physical magnitude) for the two normal toggles, but ACTUAL relative
            # magnitude for repulsive forces (a unit-length arrow would look identical for a
            # full-strength vertex and one weakened by _repulsion_vertex_multipliers, defeating
            # the whole point of the toggle) -- the strongest vertex drawn gets the usual
            # EDGE_LENGTH*NORMAL_LENGTH_FRACTION reference length, every other one scaled down
            # proportionally against it.
            if self.show_normals_var.get():
                starts, ends = [], []
                for a, b, c in self.faces:
                    pa, pb, pc = self.positions[a], self.positions[b], self.positions[c]
                    normal = np.cross(pb - pa, pc - pa)
                    normal_len = np.linalg.norm(normal)
                    if normal_len < 1e-12:
                        continue
                    centroid = (pa + pb + pc) / 3.0
                    edge_len = (np.linalg.norm(pb - pa) + np.linalg.norm(pc - pb)
                                + np.linalg.norm(pa - pc)) / 3.0
                    starts.append(centroid)
                    ends.append(centroid + normal / normal_len * edge_len * NORMAL_LENGTH_FRACTION)
                if starts:
                    segment_points = np.empty((2 * len(starts), 3))
                    segment_points[0::2] = starts
                    segment_points[1::2] = ends
                    plotter.add_lines(segment_points, color=NORMAL_COLOR, width=2.0)

            if self.show_vertex_normals_var.get():
                starts, ends = [], []
                for v, (unit_normal, mean_edge_len) in _vertex_normals(
                        self.faces, self.positions).items():
                    starts.append(self.positions[v])
                    ends.append(self.positions[v]
                                 + unit_normal * mean_edge_len * NORMAL_LENGTH_FRACTION)
                if starts:
                    segment_points = np.empty((2 * len(starts), 3))
                    segment_points[0::2] = starts
                    segment_points[1::2] = ends
                    plotter.add_lines(segment_points, color=VERTEX_NORMAL_COLOR, width=2.0)

            if self.show_repulsive_forces_var.get():
                repulsion_ids = [v for v in self._repulsion_vertex_ids() if v in idx]
                if repulsion_ids:
                    rep_indices = [idx[v] for v in repulsion_ids]
                    mult_by_id = self._repulsion_vertex_multipliers() or {}
                    rep_mults = [mult_by_id.get(v, 1.0) for v in repulsion_ids]
                    forces = repulsion_force(points, indices=rep_indices,
                                              vertex_multipliers=rep_mults)
                    force_lens = {v: np.linalg.norm(forces[idx[v]]) for v in repulsion_ids}
                    max_len = max(force_lens.values(), default=0.0)
                    starts, ends = [], []
                    if max_len >= 1e-12:
                        for v in repulsion_ids:
                            force_len = force_lens[v]
                            if force_len < 1e-12:
                                continue
                            force_vec = forces[idx[v]]
                            starts.append(self.positions[v])
                            ends.append(self.positions[v] + force_vec / max_len
                                        * EDGE_LENGTH * NORMAL_LENGTH_FRACTION)
                    if starts:
                        segment_points = np.empty((2 * len(starts), 3))
                        segment_points[0::2] = starts
                        segment_points[1::2] = ends
                        plotter.add_lines(segment_points, color=REPULSION_FORCE_COLOR, width=2.0)

            for group in self._hover_groups:
                if group in groups_present:
                    self._hover_actors += self._add_rounded_lines(
                        self._group_boundary_lines(group), "yellow", HOVER_HIGHLIGHT_LINE_WIDTH)
            for group in self._groups_for_shape_ids(self._selected_shape_ids):
                if group in groups_present:
                    self._selected_actors += self._add_rounded_lines(
                        self._group_boundary_lines(group), "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
            hover_conn_segments = self._connection_edge_cache.get(self._hover_connection_id)
            if hover_conn_segments is not None and len(hover_conn_segments):
                self._hover_connection_actors = self._add_rounded_lines(
                    hover_conn_segments, "yellow", HOVER_HIGHLIGHT_LINE_WIDTH)
            selected_conn_segments = self._connection_edge_cache.get(self._selected_connection_id)
            if selected_conn_segments is not None and len(selected_conn_segments):
                self._selected_connection_actors = self._add_rounded_lines(
                    selected_conn_segments, "red", SELECTED_HIGHLIGHT_LINE_WIDTH)
            lo, hi = points.min(axis=0), points.max(axis=0)
            self._center = (lo + hi) / 2
            self._half = float(np.linalg.norm(points - self._center, axis=1).max()) + 1e-6
            self._apply_camera()
            self._grab_frame()
        else:
            self.panel_label.configure(image="", text="Build a net on the left, then click Inflate.",
                                        fg=PLOT_THEME["fg"])

    # ---- pipeline ----

    def on_full_inflate_clicked(self, change_label=None):
        """Reads the LEFT pane's current net, then runs the full Level 0->1->2->3 auto-pipeline
        (fan-triangulate -> Relax -> calibrate/Inflate to target RMS -> Subdivide -> repeat) --
        the same sequence inflate_polyhedron_app's "Run Simulation" runs, redrawing this ONE
        panel in place at each step instead of four side-by-side panels. Always enabled, always
        starts completely from scratch (2026-09-19, explicit) -- contrast Diff Inflate
        (on_diff_inflate_clicked), which reuses the last completed inflate's own Level-3
        result. A no-op while already running.

        `change_label`, if given, is set as self._change_label for the WHOLE run (2026-09-28,
        explicit user request -- see _describe_change/_pipeline_label) -- passed only by the
        two callers that actually have a single classified change driving this run
        (refresh_diff_eligibility's own "Anchor piece" first-placement branch, and
        on_diff_inflate_clicked's own redirect); every other caller (a manual Full Inflate/
        Reinflate click, on_load_success, or BuilderPane's own "moving the anchor" confirmation)
        leaves it None, correctly, since none of those has one single change to describe."""
        self._change_label = change_label
        if self._running:
            return
        builder = self.builder_getter()
        mesh, err = builder.export_mesh_dict()
        if err:
            messagebox.showerror("Cannot inflate", err)
            return
        try:
            faces, base_edges, face_edge_ids = _load_mesh_from_dict(mesh)
        except ValueError as e:
            messagebox.showerror("Cannot inflate", str(e))
            return
        self._pre_click_snapshot = self._snapshot_mesh_state()
        self._stop_event = threading.Event()
        self._stop_requested = False
        self.level_history = {}
        # A face hinged to the rest by exactly one glued edge is excluded from the actual
        # relax/inflate pipeline entirely and reattached flat once it's done (2026-09-28,
        # explicit user request -- see this module's own "pendant (single-edge-attached) face
        # exclusion" section header comment). self._pending_pendants is consumed once, in
        # _on_inflate_step_done's own Level-3 "Done" branch. When there's nothing left worth
        # running physics on AT ALL (a lone face, or a mutual single-edge pair -- 2026-09-28,
        # explicit user request: "just place the piece flat" -- see _prepare_mesh_for_inflate's
        # own docstring), this skips the whole Relax/Inflate pipeline below entirely and places
        # everything directly instead.
        prepared = _prepare_mesh_for_inflate(
            faces, base_edges, face_edge_ids, mesh.get("source_polygon_id"))
        if prepared[0] == "place":
            _mode, reference_face, reference_spid, pendants = prepared
            self.faces, self.positions, self.face_of_fine, self.base_faces = _place_all_flat(
                reference_face, pendants, EDGE_LENGTH)
            self.base_edges = None
            self.base_face_edge_ids = None
            self.edge_length = EDGE_LENGTH
            self.edges = None
            self.subdivision_level = MAX_LEVEL
            self._pending_source_polygon_id = [
                reference_spid, *(p["source_polygon_id"] for p in pendants)]
            self._pending_pendants = []
            # No physics ran here at all -- any earlier run's own replay history describes a
            # mesh this flat placement just replaced, so it's discarded rather than left
            # scrubbable against a topology that no longer exists.
            self._replay_frames = []
            self._update_replay_slider()
            self._render()
            self.last_pressure = None  # nothing was calibrated this run
            # No real physics ran -- flags a future Diff Inflate to force a real Full Inflate
            # instead of incrementally "solving" from a flat placement (2026-09-28, explicit
            # user request -- see this flag's own init comment).
            self.is_fully_inflated = False
            self._record_inflate_success()
            self._pre_click_snapshot = None
            self._stop_event = None
            # self._change_label ("Anchor piece" for the very first placement, or whatever
            # club change triggered a LATER degenerate collapse -- e.g. deleting enough
            # insiders to leave only guests) prefixes this exactly like _pipeline_label does
            # for a real relax/inflate run (2026-09-28, explicit user request: "Anchor piece:
            # placed flat"). None only for a genuine manual Full Inflate/Reinflate click on an
            # already-degenerate net, with no single change to describe.
            self._set_status(
                f"{self._change_label}: placed flat."
                if self._change_label else
                "Placed directly: no insiders yet (every member is a guest -- Rule 1), so "
                "there's nothing to inflate here, only to place.", "success")
            return
        (_mode, self.base_faces, self.base_edges, self.base_face_edge_ids, source_polygon_id,
         self._pending_pendants) = prepared
        self._pending_source_polygon_id = source_polygon_id
        self.faces, self.edge_length, self.face_of_fine = _build_level1_topology(self.base_faces)
        self.edges = _fan_level_edges(self.faces, self.base_edges)
        self.subdivision_level = 0
        self.positions = random_initial_positions(self.faces, seed=0)
        # Deliberately no self._render() here -- these are raw, unrelaxed random positions, not
        # a converged state (2026-09-19, explicit: "never redraw anything" before real
        # convergence). The first real redraw is _on_relax_done's, once Level 0 has actually
        # settled -- or, if it never does, _revert_run puts the panel straight back to
        # self._pre_click_snapshot without ever showing this or any other unconverged frame.
        self._set_running(True, active="full")
        self._set_status(f"{self._pipeline_label()} -- Level 0: Step 0.", "info")
        self._run_background(
            lambda queue_progress: relax_initial_configuration(
                self.positions, self.faces, self.edge_length,
                max_nfev=SAFETY_STEP_CAP, gtol=self._get_tolerance(), rng=None,
                # Adapts relax_once's own 6-arg on_progress (new_positions, steps_taken,
                # max_stretch_pct, rms_stretch_pct, optimality, converged -- see its own
                # docstring) down to (positions, steps_taken) -- queue_progress/on_progress
                # below need positions too now, to capture a replay frame per checkpoint
                # (2026-09-29, explicit user request -- see _capture_replay_frame), not just
                # the step count status messages show.
                on_progress=lambda new_positions, steps_taken, *_rest:
                    queue_progress((new_positions, steps_taken)),
                edges=self.edges, stop_event=self._stop_event,
                # 2026-09-29, explicit bug report: goose.poly (an open/semi-closed net)
                # converged in inflate_polyhedron_app but not here -- these two were simply
                # never passed at all, so an open wedge's own unconstrained, naturally-higher
                # stretch kept the RMS convergence check from ever settling below gtol, and its
                # own jiggle kick kept nudging vertices that should feel no inflation force at
                # all. See _rms_exclude_edges/_pressure_exclude_faces' own docstrings.
                rms_exclude_edges=self._rms_exclude_edges(),
                pressure_exclude_faces=self._pressure_exclude_faces()),
            self._on_relax_done,
            on_progress=self._on_level0_relax_progress)

    def _on_level0_relax_progress(self, payload):
        """`on_progress` for on_full_inflate_clicked's own relax_initial_configuration call --
        runs on the MAIN thread (via _run_background's own queue/poll), so it's safe to touch
        self._replay_frames/self.faces/self.face_of_fine directly here. self.faces/
        self.face_of_fine are fixed for this whole Level 0 call (only reassigned afterward, in
        _on_relax_done once it's converged), so every captured frame this level gets tagged
        with the SAME pair, correctly."""
        positions, steps = payload
        self._capture_replay_frame(self.faces, self.face_of_fine, positions)
        self._set_status(f"{self._pipeline_label()} -- Level 0: Step {steps}.", "info")

    def _on_relax_done(self, result):
        if self._stop_requested:
            self._revert_run(f"{self._pipeline_label()} -- Stopped.")
            return
        positions, _steps, max_stretch, rms_stretch, _optimality, converged = result
        if not converged:
            self._revert_run(
                f"{self._pipeline_label()} -- Failed to converge.",
                popup_text=(
                    f"The mesh didn't converge (max stretch {max_stretch:.1f}%, RMS "
                    f"{rms_stretch:.1f}% after {SAFETY_STEP_CAP} steps) -- it may have a "
                    "loosely-attached or floppy face. Try anchoring/reconnecting it and "
                    "Inflate again."))
            return
        self.positions = positions
        self._render()
        self.subdivision_level = 1
        self._set_status(f"{self._pipeline_label()} -- Level 1: Step 0.", "info")
        self._run_inflate_step()

    def _guess_pressure_from_history(self, target_rms_pct):
        """Same algorithm as inflate_polyhedron_app's own _guess_pressure_from_history
        (duplicated, not imported -- see module docstring): looks at every level ALREADY
        completed this Full Inflate run (self.level_history) and picks whichever one's own
        ACHIEVED RMS stretch landed closest to `target_rms_pct`, scaling that record's pressure
        by 2 per level of resolution difference (each Subdivide roughly doubles resolution,
        empirically needing ~2x the pressure for the same target RMS stretch %). Deliberately
        not a `target_rms_pct / achieved` rescale -- that ratio explodes when a level's achieved
        stretch is ~0. A level whose search never found a working pressure at all
        (pressure_found False) is skipped -- not a usable extrapolation point. Returns None
        (the caller then falls back to estimate_pressure_for_target_stretch's own generic
        guess) if nothing usable is recorded yet -- e.g. Level 1, the very first calibration of
        a run, which is exactly why Full Inflate used to skip straight to the generic guess at
        EVERY level instead of just the first, needing far more total steps by Level 3
        (2026-09-19, explicit: "when inflating hippo, in level 3, interactive_inflater took
        34000 steps... but polyhedron_inflater only took ~7k")."""
        best = None
        for level, record in self.level_history.items():
            if level >= self.subdivision_level or not record:
                continue
            if not record.get("pressure_found", True):
                continue
            prior_pressure = record.get("pressure")
            prior_rms = record.get("rms_stretch_pct")
            if not prior_pressure or prior_rms is None:
                continue
            error = abs(prior_rms - target_rms_pct)
            if best is None or error < best[0]:
                best = (error, level, prior_pressure)
        if best is None:
            return None
        _, level, prior_pressure = best
        return prior_pressure * (2 ** (self.subdivision_level - level))

    def _run_inflate_step(self, initial_pressure_guess=None, tol_pct=None):
        """`initial_pressure_guess`/`tol_pct`, if given (only ever by the Diff Inflate paths --
        see _diff_remove_face/_diff_reexport_and_relax), let estimate_pressure_for_target_
        stretch start its search from a pressure ALREADY KNOWN to converge near this same
        target (the last successful inflate's own pressure -- a Diff Inflate's mesh is mostly
        unchanged from that point, so it's usually still a good guess) instead of its own
        generic area-based one, and accept a looser match before trying another guess
        (2026-09-19, explicit: "use the previous pressure as a starting point... If it results
        in more than 5% different from the target stretch, then you can do another guess...
        speed up Diff Inflate" -- fewer/no extra bracket-search trials needed when the first
        guess already lands close). Full Inflate never passes either explicitly -- instead,
        when `initial_pressure_guess` comes in None, this falls back to
        self._guess_pressure_from_history (same idea, using THIS run's own earlier levels
        instead of the last completed inflate), matching inflate_polyhedron_app's own behavior
        at every level past the first."""
        target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        tolerance = self._get_tolerance()
        if initial_pressure_guess is None:
            initial_pressure_guess = self._guess_pressure_from_history(target_rms_pct)
        extra = {}
        if initial_pressure_guess is not None:
            extra["initial_pressure_guess"] = initial_pressure_guess
        if tol_pct is not None:
            extra["tol_pct"] = tol_pct
        self._run_background(
            lambda queue_progress: estimate_pressure_for_target_stretch(
                self.positions, self.faces, self.edge_length,
                target_rms_pct=target_rms_pct, gtol=tolerance, rng=None,
                # capture_frames=True (2026-09-29, explicit user request -- "replay the last
                # full/diff inflate"): returns the WINNING trial's own frames as an extra
                # return value (see _on_inflate_step_done's own unpacking) -- only ITS frames,
                # never a discarded search trial's, so a replay scrub never shows a pressure
                # guess that didn't pan out.
                capture_frames=True, on_progress=queue_progress,
                edges=self.edges if self.subdivision_level == 1 else None,
                # Restricted to self.base_faces' own small fixed vertex set, same as
                # inflate_polyhedron_app's own on_inflate_clicked -- see _repulsion_vertex_ids'
                # own comment for why omitting this let repulsion run against every Level 2/3
                # vertex instead (an O(n^2) regression).
                repulsion_vertex_ids=self._repulsion_vertex_ids(),
                repulsion_vertex_multipliers=self._repulsion_vertex_multipliers(),
                # Deliberately NOT max_nfev_per_trial=SAFETY_STEP_CAP here (an earlier version
                # of this call passed it explicitly) -- inflate_polyhedron_app's own equivalent
                # calibration call never overrides it either, leaving it at the function's own
                # default (5000, one tenth of SAFETY_STEP_CAP), and that mismatch is exactly
                # why the SAME net took far more total steps here than there (2026-09-19,
                # explicit bug report: "in polyhedron_inflater, step 1 took ~45000 steps...
                # while in interactive_inflater, it went over 100k"). A smaller per-trial cap
                # doesn't risk worse final accuracy -- the WINNING trial always gets an
                # UNCAPPED top-up to real convergence regardless of max_nfev_per_trial (capped
                # only by relax_once's own MAX_UNBOUNDED_STEPS=200_000 runaway guard, see its
                # docstring) -- it only makes the SEARCH abandon an unpromising pressure sooner
                # instead of grinding on it for up to 10x longer before moving on.
                # SAFETY_STEP_CAP stays the Level 0 relax's own cap (a single, non-search call,
                # where inflate_polyhedron_app's own relax path uses the SAME 50000 value --
                # see its own INFLATE_SAFETY_STEP_CAP) and the "stop/revert if a trial doesn't
                # converge" ceiling _on_relax_done/_on_inflate_step_done quote in their own
                # messages -- unaffected by this change.
                stop_event=self._stop_event,
                # 2026-09-29, explicit bug report -- see on_full_inflate_clicked's own Level 0
                # relax_initial_configuration call for the full "goose.poly doesn't converge
                # here but does in inflate_polyhedron_app" explanation; same fix applies here,
                # at every level past 0 too.
                rms_exclude_edges=self._rms_exclude_edges(),
                pressure_exclude_faces=self._pressure_exclude_faces(),
                **extra),
            self._on_inflate_step_done,
            on_progress=lambda steps: self._set_status(
                f"{self._pipeline_label()} -- Level {self.subdivision_level}: Step {steps}.",
                "info"))

    def _on_inflate_step_done(self, result):
        if self._stop_requested:
            self._revert_run(f"{self._pipeline_label()} -- Stopped.")
            return
        # capture_frames=True (see _run_inflate_step's own call) -- 9 values, `frames` (the
        # winning trial's own captured positions) 8th, before pressure_found.
        (pressure, new_positions, _steps, max_stretch, rms_stretch,
         _optimality, converged, frames, pressure_found) = result
        if not pressure_found:
            self._revert_run(
                f"{self._pipeline_label()} -- Failed to converge.",
                popup_text=(
                    "The mesh didn't respond to any pressure tried at Level "
                    f"{self.subdivision_level} -- it may have a loosely-attached or floppy "
                    "face. Try anchoring/reconnecting it and Inflate again."))
            return
        if not converged:
            # No step-count figure quoted here -- unlike Level 0's plain relax_initial_
            # configuration call, this is a multi-trial SEARCH (estimate_pressure_for_target_
            # stretch): the winning trial's own reported step count isn't capped by any single
            # constant this app controls (its search-phase trials each cap at that function's
            # own default of 5000, but the winner then gets an UNCAPPED top-up bounded only by
            # relax_once's internal MAX_UNBOUNDED_STEPS=200_000 runaway guard) -- so a specific
            # "didn't converge within N steps" number would just be wrong.
            self._revert_run(
                f"{self._pipeline_label()} -- Failed to converge.",
                popup_text=(
                    f"The mesh didn't converge at Level {self.subdivision_level} (pressure "
                    f"{pressure:.2f}, max stretch {max_stretch:.1f}%, RMS {rms_stretch:.1f}%) "
                    "-- it may have a loosely-attached or floppy face. Try anchoring/"
                    "reconnecting it and Inflate again."))
            return
        # self.faces/self.face_of_fine are still THIS level's own (fixed since before this
        # call, only reassigned below by subdivide_once once this level is fully done) -- every
        # frame from `frames` (this level's own winning-trial capture) gets tagged with them,
        # correctly, same as _on_level0_relax_progress's own Level 0 capture.
        for frame_positions, _frame_steps in frames:
            self._capture_replay_frame(self.faces, self.face_of_fine, frame_positions)
        self.positions = new_positions
        if self.subdivision_level >= MAX_LEVEL and self._pending_pendants:
            # Only now, once the CORE mesh (every pendant excluded from it -- see
            # _exclude_pendant_faces) has actually reached its own final Level-3 result, is
            # each excluded pendant's own neighbor position known -- reattach flat against it
            # (2026-09-28, explicit user request) before this level's own render/status, so the
            # very first thing shown at Level 3 already includes them, not a later redraw.
            # Each pendant gets its OWN trailing self.base_faces/self._pending_source_polygon_id
            # index (2026-09-29, explicit bug report -- see _reattach_pendant_faces' own
            # docstring) -- same convention _diff_attach_pendant_only already used for its own
            # single-pendant fast path, applied here too so a guest is independently pickable
            # regardless of which pipeline path reattached it.
            core_base_faces = self.base_faces
            own_groups = list(range(len(core_base_faces),
                                     len(core_base_faces) + len(self._pending_pendants)))
            if self.base_face_edge_ids is not None:
                next_edge_id = 1 + max(eid for ids in self.base_face_edge_ids for eid in ids)
                new_edge_id_rows = []
                for pendant in self._pending_pendants:
                    row, next_edge_id = _pendant_own_face_edge_ids(
                        pendant, core_base_faces, self.base_face_edge_ids, next_edge_id)
                    new_edge_id_rows.append(row)
                self.base_face_edge_ids = [*self.base_face_edge_ids, *new_edge_id_rows]
            self.faces, self.positions, self.face_of_fine, remapped_base_faces = \
                _reattach_pendant_faces(
                    self._pending_pendants, self.faces, self.positions, self.face_of_fine,
                    EDGE_LENGTH, own_groups, core_base_faces)
            # remapped_base_faces, NOT raw p["face"] -- see _reattach_pendant_faces' own
            # docstring for why a pendant's own THIRD+ corner no longer keeps its raw id.
            self.base_faces = [*core_base_faces, *remapped_base_faces]
            self._pending_source_polygon_id = [
                *self._pending_source_polygon_id,
                *(p["source_polygon_id"] for p in self._pending_pendants)]
        self._render()
        # Feeds _guess_pressure_from_history for whichever level runs next this SAME Full
        # Inflate pass (harmless to also record during a Diff Inflate run -- nothing reads
        # self.level_history there, since those callers pass their own explicit guess).
        self.level_history[self.subdivision_level] = {
            "pressure": pressure, "rms_stretch_pct": rms_stretch, "pressure_found": pressure_found}
        if self.subdivision_level >= MAX_LEVEL:
            self.last_pressure = pressure
            # A real pressure calibration pass just completed, whichever pipeline path got
            # here (Full Inflate's own "solve" mode, _diff_remove_face, or
            # _diff_reexport_and_relax) -- see this flag's own init comment.
            self.is_fully_inflated = True
            self._record_inflate_success()
            self._pre_click_snapshot = None
            self._stop_event = None
            # Captured BEFORE _set_running(False) -- that call clears self._active_button (see
            # its own docstring), which _pipeline_label() reads to decide "Full Inflate" vs.
            # "Diff Inflate"; calling _pipeline_label() only AFTER _set_running(False) (as this
            # used to) always read the just-cleared value and mislabeled every run's own final
            # "Done" message as "Diff Inflate", even a genuine Full Inflate run throughout
            # (2026-09-29, explicit bug report: "add a connection... you'll trigger a full
            # inflate and then a diff inflate (at least according to the UI message), rather
            # than just a full inflate" -- confirmed by direct testing: every OTHER status
            # message during the same run correctly read "Full Inflate", only this final one
            # didn't).
            done_label = self._pipeline_label()
            self._set_running(False)
            # This run's own replay history is only ever complete/meaningful once the WHOLE
            # run has actually converged -- populated here, not per-level, so a Diff Inflate's
            # single Level-3 pass and a Full Inflate's Level 0-3 run both end up with their
            # own frames spanning start to finish (2026-09-29, explicit user request).
            self._update_replay_slider()
            self._set_status(f"{done_label} -- Converged.", "success")
            return
        self.level_snapshot_faces = self.faces
        self.faces, self.positions, self.edge_length, self.face_of_fine = subdivide_once(
            self.faces, self.positions, self.edge_length, self.face_of_fine,
            self.subdivision_level, base_faces=self.base_faces,
            face_edge_ids=self.base_face_edge_ids)
        self.subdivision_level += 1
        self.edges = None
        self._render()
        self._set_status(
            f"{self._pipeline_label()} -- Level {self.subdivision_level}: Step 0.", "info")
        self._run_inflate_step()

    def _current_root_to_vertex_id(self):
        """Same {root_slot: vertex_id} shape as builder.root_to_vertex_id() (see its own
        docstring for what a root_slot is/why it's stable) -- but every value is the REAL
        vertex id self.base_faces/self.positions actually use RIGHT NOW, not a fresh export's
        own deterministic sequential numbering. builder.root_to_vertex_id() reimplements
        _faces_from_shapes' own numbering loop from scratch, with NO knowledge of a pendant's
        own arbitrary _place_pendant_flat id_map remapping -- using its raw output directly as
        a self.positions lookup key (as self.last_root_to_vertex_id used to, before this fix)
        silently matched some UNRELATED vertex that happened to share the same small integer id
        whenever a pendant/guest was involved (2026-09-29, explicit bug report, confirmed via
        the debug replay slider: a guest promoted from pendant to insider mid-Diff-Inflate got
        seeded from a random vertex on the opposite side of the mesh, "connected to the centre
        of an opposite pentagon" -- the exact same class of stale-id mismatch as the earlier
        _load_hippie_session fix, here in _diff_reexport_and_relax's own root-matched seeding
        instead of the file-load path).

        Walks self._pending_source_polygon_id/self.base_faces (this pane's own CURRENT, already
        correct ids -- pendant-remapped or not, doesn't matter) group by group, matching each
        group's shape id back to its own expanded_shapes/roots entry (same
        central_shape_ids/_expand_folded_shapes/_vertex_roots pipeline root_to_vertex_id's own
        traversal uses) -- then reads the REAL id straight off self.base_faces[group][corner]
        instead of assigning a fresh sequential one. Ambiguous (silently skipped) for a Polygon-
        Fold shape split into several expanded_shapes sharing one source_polygon_id -- same
        known limitation _rebuild_open_edges/_connection_edge_segments already carry for a
        Polygon-Fold group (see their own comments); out of scope for this fix."""
        builder = self.builder_getter()
        central_ids = builder.central_shape_ids()
        if not central_ids or not self.base_faces or self._pending_source_polygon_id is None:
            return {}
        central_shapes = [s for s in builder.shapes if s["id"] in central_ids]
        central_connections = [c for c in builder.connections
                                if c["a_shape"] in central_ids and c["b_shape"] in central_ids]
        expanded_shapes, expanded_connections, _spid = _expand_folded_shapes(
            central_shapes, central_connections)
        roots = _vertex_roots(expanded_shapes, expanded_connections)
        shape_by_id = {s["id"]: s for s in expanded_shapes}
        vertex_ids = {}
        for group, spid in enumerate(self._pending_source_polygon_id):
            if group >= len(self.base_faces):
                continue
            shape = shape_by_id.get(spid)
            if shape is None:
                continue
            corners = _shape_face_corner_order(shape)
            face = self.base_faces[group]
            if len(corners) != len(face):
                continue
            for corner, real_id in zip(corners, face):
                root = roots.get((shape["id"], corner))
                if root is not None:
                    vertex_ids[root] = real_id
        return vertex_ids

    def _old_atomic_slot_to_id(self):
        """{(shape_id, corner): real_vertex_id} for every ATOMIC corner slot in the net as of
        the last completed inflate (self.last_shapes_snapshot/last_connections_snapshot/
        last_anchor_snapshot, the SAME triple _current_root_to_vertex_id's own caller snapshots
        alongside it -- see _record_inflate_success) -- unlike self.last_root_to_vertex_id
        itself (keyed by ROOT slot only, one entry per glued GROUP), this has one entry per
        individual corner, letting _diff_reexport_and_relax's own seeding recover a vertex's old
        position even when that corner's group didn't keep the same root slot across the edit
        (2026-09-29, explicit bug report -- see _diff_reexport_and_relax's own docstring for the
        full "why root-to-root matching under-seeds" explanation).

        Re-expands self.last_shapes_snapshot/last_connections_snapshot (restricted to their OWN
        central object, exactly like _current_root_to_vertex_id's live equivalent) rather than
        reusing any of THIS pane's current-state fields -- the whole point is a snapshot of the
        net as it stood at the LAST successful inflate, independent of whatever's been edited
        since. Every slot's root is looked up in self.last_root_to_vertex_id (unaffected by this
        method's own re-expansion -- that map's REAL ids were already recorded at the time, see
        _current_root_to_vertex_id) to get its real id; a root with no entry there (shouldn't
        normally happen -- every root _vertex_roots produces here comes from the exact same
        expansion _current_root_to_vertex_id used to build that map in the first place) is
        silently skipped rather than raising."""
        if not self.last_shapes_snapshot or self.last_root_to_vertex_id is None:
            return {}
        old_central = _central_shape_ids(
            self.last_shapes_snapshot, self.last_connections_snapshot, self.last_anchor_snapshot)
        if not old_central:
            return {}
        old_shapes = [s for s in self.last_shapes_snapshot if s["id"] in old_central]
        old_connections = [c for c in self.last_connections_snapshot
                            if c["a_shape"] in old_central and c["b_shape"] in old_central]
        expanded_shapes, expanded_connections, _spid = _expand_folded_shapes(
            old_shapes, old_connections)
        roots = _vertex_roots(expanded_shapes, expanded_connections)
        old_root_to_id = self.last_root_to_vertex_id
        return {slot: old_root_to_id[root] for slot, root in roots.items()
                if root in old_root_to_id}

    def _record_inflate_success(self):
        """Called only from _on_inflate_step_done's "Done" branch above (a clean Level-3
        finish -- never a mid-pipeline stop/failure, so a warn/error outcome leaves Diff
        Inflate pointed at whatever the PREVIOUS successful result was) -- snapshots the
        builder's CURRENT shapes/connections as the new baseline a future Diff Inflate's
        classify_change compares against, adopts whichever pipeline path (Full Inflate/
        _diff_add_face/_diff_remove_face/_diff_reexport_and_relax) staged into
        self._pending_source_polygon_id as the new self.last_source_polygon_id, and
        re-derives self.last_root_to_vertex_id FRESH from the builder's current state (cheap,
        and always correct at this exact moment -- no need to thread it through the async
        pipeline the way source_polygon_id is) via _current_root_to_vertex_id (NOT
        builder.root_to_vertex_id() directly -- see that method's own docstring for why).
        Deliberately does NOT clear self._pending_source_polygon_id afterward -- it doubles as
        "the source_polygon_id parallel to self.base_faces RIGHT NOW" (every pipeline path sets
        both together, see each one's own assignment), which hover picking (_set_hover_group)
        needs available even for a mesh that's currently displayed but not yet (or never)
        successfully recorded."""
        builder = self.builder_getter()
        (self.last_shapes_snapshot, self.last_connections_snapshot,
         self.last_anchor_snapshot) = builder.snapshot_state()
        self.last_source_polygon_id = self._pending_source_polygon_id
        self.last_root_to_vertex_id = self._current_root_to_vertex_id()
        if self.on_inflate_success is not None:
            self.on_inflate_success()

    # ---- diff inflate ----

    def _stage_kept_selection(self, kind, extra):
        """Keeps exactly the ONE thing that triggered this run visibly outlined/selected (2D
        and 3D) for its WHOLE duration, even though hover/selection are otherwise fully disabled
        while locked (2026-09-29, explicit user request: "if the change is a face deletion, then
        keep that face selected... if there's a connection being deleted, then keep that
        connection/edge selected... if two edges are being joined, the two edges remain selected
        ... with 3d showing the line between the two edges as well"). A no-op for every other
        `kind` (add_face, complex, none) -- nothing else asked for this treatment. Called from
        on_diff_inflate_clicked right before it locks the pane (directly, or via its own Full
        Inflate redirect -- either way still the SAME triggering edit).

        "remove_face"/"remove_connection": the shape(s)/connection are already gone from the
        LIVE builder.shapes/connections by this point, so self.last_shapes_snapshot/last_
        connections_snapshot (the net as of the last completed inflate, i.e. right before this
        edit) is where their own geometry has to come from instead -- handed to BuilderPane.
        stage_locked_ghost (own docstring has the rest), which is what actually keeps them
        outlined in 2D. The 3D side sets self._selected_shape_ids/_selected_connection_id (and
        re-derives their own highlight actors) directly, bypassing _select_shape_ids/
        _select_connection's own forward-to-BuilderPane step -- forwarding would set the
        BUILDER's live self.selected_ids/selected_connection_id to an id it no longer has any
        record of, which BuilderPane.stage_locked_ghost's own separate, dedicated ghost fields
        make unnecessary anyway.

        "add_connection": the new connection, unlike the two cases above, is very much still
        live in builder.connections -- its own 3D "two edges in red plus a connecting line"
        indicator already exists independently of this method (BuilderPane._on_canvas_release/
        InflaterPane._finish_connection_drag's own persistent self._pending_made_connection_
        actors, made the instant the join itself completes, well before this ever runs), so only
        the 2D side needs anything here: a plain BuilderPane.set_selected_connection, the same
        ordinary (non-ghost) selection path _click_select_edge already uses, since the
        connection is real and still there to select."""
        builder = self.builder_getter()
        if kind == "remove_face":
            removed_shapes = [s for s in self.last_shapes_snapshot if s["id"] in extra]
            builder.stage_locked_ghost(shapes=removed_shapes)
            self._selected_shape_ids = set(extra)
            self._apply_selection_highlight()
        elif kind == "remove_connection":
            removed_conn = next(
                (c for c in self.last_connections_snapshot if _connection_key(c) == extra), None)
            builder.stage_locked_ghost(connection=removed_conn)
            if removed_conn is not None:
                self._selected_connection_id = removed_conn["id"]
                self._apply_connection_selection_highlight()
        elif kind == "add_connection":
            made_conn = next(
                (c for c in builder.connections if _connection_key(c) == extra), None)
            if made_conn is not None:
                builder.set_selected_connection(made_conn["id"])

    def on_diff_inflate_clicked(self):
        """Only meaningful once refresh_diff_eligibility has already enabled this button (an
        "add_face"/"remove_face"/"add_connection"/"remove_connection" change since the last
        completed inflate -- see BuilderPane.classify_change) -- re-classifies once more here
        regardless, as a safety net against a stale enabled state (e.g. a builder edit landing
        between the button's last refresh and this click), and tells the user to use Full
        Inflate instead if that's no longer true. A no-op while already running.

        If the CLUB's own insiders were only ever geometrically placed, never really solved
        (self.is_fully_inflated False -- e.g. a chain of pieces joined one single edge at a
        time, each one just flat-attached, no real physics run yet), and this particular change
        genuinely needs real physics (anything except another pendant-only add, which stays
        flat-attached same as before), this redirects to a full on_full_inflate_clicked instead
        of any of the incremental Diff Inflate paths below (2026-09-28, explicit user request:
        "if a bunch of pieces have been flatly connected... and then i finally connect them in
        a way that requires inflation, that initial inflation needs to be a Full Inflate") --
        every incremental path assumes it's seeding a real relax/calibration pass from an
        ALREADY relaxed/calibrated result, which a flat placement never was.

        _diff_add_face/_diff_remove_face/_diff_connection_change below each run their OWN
        pendant exclusion now (2026-09-28, explicit user request: "teach Diff Inflate to
        exclude pendants too" -- an earlier version instead redirected to Full Inflate whenever
        the post-edit mesh had ANY pendant at all, which correctly avoided handing an
        unconstrained single-edge-hinged face to the real solver, but at the cost of discarding
        the existing warm-started Level-3 result/pressure guess for a random Level-0 restart on
        EVERY such edit -- slower, and for some topologies never converges at all: "it tried to
        reinflate by starting at level 0... the inflate did not converge" when the saved session
        already had a working Level-3 pressure to diff from). Each of those methods stages
        whatever it excludes into self._pending_pendants itself, exactly like
        on_full_inflate_clicked's own "solve" branch, so _on_inflate_step_done's existing
        Level-3 "Done" branch reattaches them the same generic way regardless of which pipeline
        path got there."""
        if self._running:
            return
        builder = self.builder_getter()
        kind, extra = builder.classify_change(
            self.last_shapes_snapshot, self.last_connections_snapshot, self.last_anchor_snapshot)
        label = self._describe_change(kind, extra)
        if kind == "add_face" and self._is_pendant_add(extra):
            self._diff_attach_pendant_only(extra, label)
            return
        self._stage_kept_selection(kind, extra)
        if (not self.is_fully_inflated
                and kind in ("add_face", "add_connection", "remove_connection", "remove_face")):
            # Marks this run as a REDIRECTED one so _revert_run's own "undo the triggering edit
            # on failure" safety net still fires even though self._active_button will read
            # "full", not "diff" (see this flag's own init comment for the infinite-retry
            # hazard this closes) -- set here, not inside on_full_inflate_clicked itself, so a
            # genuine manual Full Inflate/Reinflate click (which never runs through this
            # redirect) correctly leaves it False.
            self._diff_redirect_pending = True
            self.on_full_inflate_clicked(change_label=label)
            return
        self._change_label = label
        if kind == "add_face":
            self._diff_add_face(extra)
        elif kind == "remove_face":
            self._diff_remove_face(extra)
        elif kind == "add_connection":
            self._diff_connection_change()
        elif kind == "remove_connection":
            self._diff_connection_change()
        else:
            messagebox.showerror(
                "Cannot Diff Inflate",
                "The net has changed by more than a single added face/connection, or more than "
                "one removed face/connection, since the last Inflate -- use Full Inflate "
                "instead.")

    def _is_pendant_add(self, new_shape_id):
        """True iff `new_shape_id` (classify_change's own "add_face" `extra`, always a BRAND
        NEW shape with no prior connections at all) currently has EXACTLY ONE connection in the
        live builder net -- i.e. it would be a guest (0-or-1-connection member) were this
        exported and inflated right now (see this module's own "Club terminology" section) --
        AND that connection's OTHER end (the neighbor it's hinging onto) does NOT get PROMOTED
        from guest to insider by gaining this one extra connection. Plain connection counting
        for new_shape_id's own count is enough (no need for _pendant_face_attachments' own
        face_edge_ids disambiguation): being brand new, EVERY connection touching it is
        necessarily its own, so the count IS its own glued-edge count.

        A guest is 0 OR 1 connections (2026-09-28, explicit correction: "Guests are members
        with 0 or 1 connections") -- the neighbor's OWN prior connection count (excluding this
        new one) decides what this edit does to IT: 0 -> stays a guest (0 -> 1, a mutual guest
        pair, both flatly placed -- see _place_pendant_flat's own "chained onto another guest"
        handling); exactly 1 -> PROMOTED to insider (1 -> 2), a real change to the club's
        insiders needing a genuine reinflate (diff or full, per Rule 3), not the fast flat-
        attach-only path _diff_attach_pendant_only takes when nothing about the insiders
        actually changed; 2+ -> already an insider, unaffected either way."""
        connections = self.builder_getter().connections
        count = sum(1 for c in connections
                    if c["a_shape"] == new_shape_id or c["b_shape"] == new_shape_id)
        if count != 1:
            return False
        conn = next(c for c in connections
                    if c["a_shape"] == new_shape_id or c["b_shape"] == new_shape_id)
        neighbor_id = conn["b_shape"] if conn["a_shape"] == new_shape_id else conn["a_shape"]
        neighbor_other_connections = sum(
            1 for c in connections
            if c["id"] != conn["id"] and (c["a_shape"] == neighbor_id or c["b_shape"] == neighbor_id))
        return neighbor_other_connections != 1

    def _diff_attach_pendant_only(self, new_shape_id, label="Guest added"):
        """Skips the whole Diff Inflate relax/calibrate pipeline entirely when the just-added
        shape is a pendant (2026-09-28, explicit user request: "since the new piece is not used
        in the inflation algorithm... there hasn't actually been any change to the inflatable
        model. so you don't need to re-inflate. just attach the new piece.") -- a pendant face
        never participates in relax/inflate at all (see this module's own "pendant (single-
        edge-attached) face exclusion" section), so adding one changes NOTHING about the
        already-solved core mesh; _place_pendant_flat can attach it directly against the
        EXISTING self.faces/self.positions, no re-export-and-reseed or recalibration pass
        needed. No snapshot/revert/background thread either -- this is a plain, synchronous,
        closed-form placement (same as _reattach_pendant_faces' own use after a real solve),
        nothing here can fail to converge the way a relax/calibration pass could.

        Re-exports the mesh once anyway (builder.export_mesh_dict) purely to read the new
        shape's own vertex-id loop and its exact shared edge -- matched back to the EXISTING,
        already-solved self.base_faces by SHAPE id (self._pending_source_polygon_id), not by
        raw vertex/face index, since a fresh export can number things differently than
        self.base_faces currently does."""
        builder = self.builder_getter()
        mesh, err = builder.export_mesh_dict()
        if err:
            messagebox.showerror("Cannot attach", err)
            return
        try:
            fresh_base_faces, _fresh_base_edges, fresh_face_edge_ids = _load_mesh_from_dict(mesh)
        except ValueError as e:
            messagebox.showerror("Cannot attach", str(e))
            return
        fresh_source_polygon_id = mesh.get("source_polygon_id") or list(range(len(fresh_base_faces)))
        attachments = _pendant_face_attachments(fresh_base_faces, fresh_face_edge_ids)
        new_fresh_idx = next(
            (i for i, sid in enumerate(fresh_source_polygon_id) if sid == new_shape_id), None)
        existing_source_polygon_id = self._pending_source_polygon_id or []
        neighbor_idx = None
        shared_pair = None
        if new_fresh_idx is not None and new_fresh_idx in attachments:
            neighbor_fresh_idx, shared_pair = attachments[new_fresh_idx]
            neighbor_shape_id = fresh_source_polygon_id[neighbor_fresh_idx]
            neighbor_idx = next(
                (i for i, sid in enumerate(existing_source_polygon_id) if sid == neighbor_shape_id),
                None)
        if neighbor_idx is None:
            # Shouldn't happen (the caller already checked _is_pendant_add) -- fall back to the
            # full, safe path rather than silently doing nothing. Sets self._change_label
            # itself since on_diff_inflate_clicked's own caller never reaches its usual
            # "self._change_label = label" line for this branch (it returned straight into
            # here instead) -- _diff_add_face/_diff_reexport_and_relax read it via
            # _pipeline_label without setting it themselves.
            self._change_label = label
            self._diff_add_face(new_shape_id)
            return
        # The fresh re-export's own ids for shared_pair are NOT guaranteed to already match
        # self.base_faces' own stored ids for those same two corners -- true when the neighbor
        # is an ORIGINAL core face (whose stored ids came from the very export numbering that
        # hasn't since diverged), but false once the neighbor is ITSELF a pendant attached by an
        # EARLIER call to this method: that call gave the neighbor's own "other" corners
        # freshly-synthesized ids (see the next comment down) with no relation to what a brand
        # new export numbers those same physical corners (2026-09-28, explicit bug report:
        # chaining a new piece onto an already-pendant-attached piece produced a garbled
        # attachment -- "the square got joined to v1v3 which is not even an edge" -- because the
        # fresh export's raw id for the shared edge was used directly, silently colliding with
        # whatever UNRELATED existing vertex happened to already own that number). Translated
        # through a per-corner fresh-id -> real-id map built from the neighbor's own two
        # parallel face loops instead -- safe because a shape's own corner-index order
        # (_shape_face_corner_order) is a pure function of its n/flipped fields, identical in
        # every export regardless of numbering, so corner k of fresh_base_faces[neighbor_fresh_idx]
        # and corner k of self.base_faces[neighbor_idx] are always the SAME physical vertex.
        neighbor_fresh_to_real = dict(zip(fresh_base_faces[neighbor_fresh_idx],
                                           self.base_faces[neighbor_idx]))
        real_shared_pair = tuple(neighbor_fresh_to_real[v] for v in shared_pair)
        # The new shape's own OTHER corners are a different story, though: `fresh_base_faces`/`fresh_source_polygon_id`
        # are numbered fresh at the BASE-MESH level (this net's handful of shapes), while
        # self.positions is the EXISTING mesh's own Level-3 FINE mesh, with FAR more vertices --
        # a brand-new base-level id (e.g. "4" for this net's 5th-ever corner) can easily collide
        # with some UNRELATED subdivision-created vertex already using that same number in the
        # existing fine mesh (caught by direct testing: a just-added pendant's own free corner
        # silently overwrote an existing Level-3 midpoint that happened to share its raw id).
        # Remapped to a guaranteed-fresh id here, relative to the EXISTING fine mesh's own full
        # id space, before this pendant ever reaches _place_pendant_flat.
        existing_ids = set(self.positions) | {v for p in self._pending_pendants for v in p["face"]}
        next_id = 1 + max([*existing_ids, *fresh_base_faces[new_fresh_idx]], default=0)
        # `remap` keys are the PENDANT's own fresh ids (matching fresh_base_faces[new_fresh_idx]
        # directly) -- the shared pair's two fresh keys map to their translated REAL ids above,
        # every other corner gets a brand-new synthetic one.
        fresh_a, fresh_b = shared_pair
        real_a, real_b = real_shared_pair
        remap = {fresh_a: real_a, fresh_b: real_b}
        for v in fresh_base_faces[new_fresh_idx]:
            if v not in remap:
                remap[v] = next_id
                next_id += 1
        pendant_face = [remap[v] for v in fresh_base_faces[new_fresh_idx]]
        pendant = {"face": pendant_face, "neighbor_idx": neighbor_idx,
                   "shared_pair": (real_a, real_b), "source_polygon_id": new_shape_id}
        core_base_faces = self.base_faces
        if self.base_face_edge_ids is not None:
            next_edge_id = 1 + max(eid for ids in self.base_face_edge_ids for eid in ids)
            new_row, _next_edge_id = _pendant_own_face_edge_ids(
                pendant, core_base_faces, self.base_face_edge_ids, next_edge_id)
            self.base_face_edge_ids = [*self.base_face_edge_ids, new_row]
        self._pending_source_polygon_id = [*existing_source_polygon_id, new_shape_id]
        self._pending_pendants = [*self._pending_pendants, pendant]
        # A defensive copy, not self.positions itself -- _reattach_pendant_faces mutates its own
        # `positions` argument in place (.update()), and self.positions may still be referenced
        # by an EARLIER _snapshot_mesh_state() (e.g. self._pre_click_snapshot from a just-
        # stopped run) that must not silently change out from under it. own_group is this
        # pendant's own future trailing self.base_faces index (core_base_faces's own length,
        # before the append below).
        self.faces, self.positions, self.face_of_fine, remapped_base_faces = \
            _reattach_pendant_faces(
                [pendant], self.faces, dict(self.positions), self.face_of_fine, EDGE_LENGTH,
                [len(core_base_faces)], core_base_faces)
        # remapped_base_faces, NOT raw pendant["face"] -- see _reattach_pendant_faces' own
        # docstring for why a pendant's own THIRD+ corner no longer keeps its raw id.
        self.base_faces = [*core_base_faces, *remapped_base_faces]
        self._render()
        self._record_inflate_success()
        self._set_status(f"{label}: no inflation needed.", "success")

    def _diff_remove_face(self, shape_ids):
        """Filters the STORED Level-3 mesh (self.faces/self.positions/self.face_of_fine) and
        the stored base mesh down to whatever's left once EVERY shape in `shape_ids`' own base
        face(s) are dropped -- pure filtering, no interpolation needed at all, since every
        SURVIVING vertex is already exactly where it was left. `shape_ids` can be more than one
        shape (2026-09-19, explicit: "if multiple faces are deleted at once, let that qualify
        for diff inflate/auto inflate") -- classify_change already guarantees no OTHER topology
        change (an added shape/connection, or a connection removed that didn't touch one of
        these shapes) rides along, so dropping them all in one filtering pass is exactly as safe
        as dropping the single-shape case always was. positions/edge_length are left as-is (a
        few now-orphaned entries are simply never read again -- relax/estimate_pressure derive
        their own vertex/edge sets purely from `faces`, see stretchy_mesh._edge_setup).

        Also runs pendant exclusion on whatever survives the removal (2026-09-28, explicit user
        request: "teach Diff Inflate to exclude pendants too" -- removing a face's own only
        bracing neighbor can leave some OTHER face newly pendant, which used to force a cold
        Full Inflate redirect purely because this method had no pendant-exclusion logic of its
        own; that redirect discarded the perfectly good existing Level-3 result/pressure guess
        for a random Level-0 restart, which is slower AND, for some topologies, doesn't even
        converge). Filters `self.faces`/`self.face_of_fine`/`self.base_faces` a SECOND time
        (past the shape-removal filtering above) down to just the surviving pendant-free core,
        stages the excluded pieces in self._pending_pendants exactly like on_full_inflate_
        clicked's own "solve" branch does -- _on_inflate_step_done's existing Level-3 "Done"
        branch already reattaches them generically, no changes needed there. Then runs ONE
        pressure-calibration pass at Level 3 (_run_inflate_step, already naturally a single pass
        whenever self.subdivision_level == MAX_LEVEL going in) -- on the CORE only, still warm-
        started from the existing Level-3 positions/pressure, same as before this pendant-
        exclusion step was added."""
        removed_idxs = {i for i, spid in enumerate(self.last_source_polygon_id) if spid in shape_ids}
        keep_base_idxs = [i for i in range(len(self.base_faces)) if i not in removed_idxs]
        if not keep_base_idxs:
            messagebox.showerror("Cannot Diff Inflate", "That was the last face -- nothing left to inflate.")
            return
        old_to_new_base = {old_i: new_i for new_i, old_i in enumerate(keep_base_idxs)}

        surviving_base_faces = [self.base_faces[i] for i in keep_base_idxs]
        surviving_face_edge_ids = (None if self.base_face_edge_ids is None else
                                    [self.base_face_edge_ids[i] for i in keep_base_idxs])
        surviving_source_polygon_id = [self.last_source_polygon_id[i] for i in keep_base_idxs]
        surviving_edges = self.base_edges
        if surviving_edges is not None:
            remaining_base_vertex_ids = {v for f in surviving_base_faces for v in f}
            surviving_edges = [e for e in surviving_edges if e[0] in remaining_base_vertex_ids
                                and e[1] in remaining_base_vertex_ids]

        prepared = _prepare_mesh_for_inflate(
            surviving_base_faces, surviving_edges, surviving_face_edge_ids,
            surviving_source_polygon_id)
        if prepared[0] == "place":
            # Degenerate even before considering pendants (e.g. removing a face left only a
            # mutual single-edge pair) -- no incremental core left for this method's own warm-
            # start machinery to mean anything; on_full_inflate_clicked's own "place" branch
            # already handles this cheaply (pure geometry, no relax/calibration at all).
            self._diff_redirect_pending = True
            self.on_full_inflate_clicked(change_label=self._change_label)
            return
        (_mode, core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id,
         pendants) = prepared
        attachments = _pendant_face_attachments(surviving_base_faces, surviving_face_edge_ids)
        old_to_core = {old_i: core_i for core_i, old_i in
                       enumerate(i for i in range(len(surviving_base_faces)) if i not in attachments)}

        self._pre_click_snapshot = self._snapshot_mesh_state()
        self._stop_event = threading.Event()
        self._stop_requested = False

        self.base_faces = core_base_faces
        self.base_face_edge_ids = core_face_edge_ids
        self.base_edges = core_base_edges
        pending_source_polygon_id = core_source_polygon_id

        keep_fine = [i for i, bf in enumerate(self.face_of_fine)
                     if bf not in removed_idxs and old_to_new_base[bf] in old_to_core]
        self.faces = [self.faces[i] for i in keep_fine]
        self.face_of_fine = [old_to_core[old_to_new_base[self.face_of_fine[i]]] for i in keep_fine]
        self.edges = None
        self.subdivision_level = MAX_LEVEL
        self._pending_source_polygon_id = pending_source_polygon_id
        self._pending_pendants = pendants
        # Deliberately no self._render() here -- the mesh with the face just cut out hasn't
        # been recalibrated yet, so it's not a state worth showing (2026-09-19, explicit:
        # "never redraw anything" before real convergence) -- if it never converges,
        # _revert_run puts the panel straight back to self._pre_click_snapshot instead.
        self._set_running(True, active="diff")
        self._set_status(f"{self._pipeline_label()} -- Level {MAX_LEVEL}: Step 0.", "info")
        self._run_inflate_step(initial_pressure_guess=self.last_pressure,
                                tol_pct=DIFF_PRESSURE_GUESS_TOL_PCT)

    def _diff_add_face(self, _shape_id):
        """A new shape's own added-and-connected face(s) -- handled by the same general
        re-export-and-root-match-seed path as a connection add/remove (see
        _diff_reexport_and_relax); the shape id itself isn't needed there (root-matching finds
        automatically that this shape's own corners have no prior root, and BFS-seeds them near
        whatever they got connected to)."""
        self._diff_reexport_and_relax()

    def _diff_connection_change(self):
        self._diff_reexport_and_relax()

    def _diff_reexport_and_relax(self):
        """Shared by _diff_add_face/_diff_connection_change (see module docstring's "Full
        Inflate vs. Diff Inflate" section) -- re-exports the FULL current net, seeds the fresh
        base mesh's own Level-0 positions by matching each vertex's ATOMIC (shape_id, corner)
        slot (2026-09-29, explicit bug report -- see this method's own second docstring
        paragraph below for why this replaced a plain NEW-root-to-OLD-root match) against
        self._old_atomic_slot_to_id() (the same slot's own real vertex id as of the last
        completed inflate), falling back to a neighbor-BFS fill (_seed_unknown_by_bfs) for any
        slot that didn't exist in the old net at all (a genuinely new shape's own corners),
        subdivides straight to Level 3 as pure interpolation (_subdivide_combined_to_level3 --
        no solving), then runs ONE pressure-calibration pass at Level 3.

        Also runs pendant exclusion on the fresh export (2026-09-28, explicit user request --
        see _diff_remove_face's own comment for the full rationale: without this, a connection
        add/remove/face-add that leaves some face newly pendant used to force a cold Full
        Inflate redirect, discarding the existing warm-start seed for a random Level-0 restart).
        Root-matched seeding still runs against the FULL fresh export first (a pendant's own
        corners may still be real, already-positioned vertices worth reusing, e.g. an unrelated
        existing pendant that rode along unchanged) -- only the actual subdivide/calibrate step
        below is restricted to the CORE, with the excluded pieces staged in self._pending_
        pendants for _on_inflate_step_done's existing generic reattachment.

        Matching by NEW-root-to-OLD-root alone (an earlier version of this method) under-seeds:
        union-find's own root choice for a group that DIDN'T lose or gain any of its own glued
        vertices can still shift just because a DIFFERENT, unrelated connection nearby was
        edited (_vertex_roots picks whichever slot a union() call happens to leave as the
        survivor, not a fixed canonical one) -- so a group's new root can come out as a slot
        that was never the OLD group's own chosen root, silently missing an old-position match
        for a vertex that never actually moved. Worse, for the ONE group a connection edit
        genuinely does split (its own two now-unglued corners), root-to-root matching can never
        succeed at all -- each newly-solo corner's own root is brand new, never the OLD merged
        group's root either -- even though each of those corners individually DOES still have a
        perfectly good old position (they were exactly coincident, at the old merged vertex,
        right up until this edit). Matching per ATOMIC SLOT instead (self._old_atomic_slot_to_
        id, keyed by the raw (shape_id, corner) pair alone, before any union) sidesteps both: a
        slot's OWN old root -- whatever the OLD net's union-find gave it -- is looked up
        directly, independent of what the NEW net's root happens to be, so every slot that
        existed in the old net recovers its old position, split or not (2026-09-29, explicit bug
        report: "you did fix the problem of all the faces being flat, but now most of the faces
        are inflated while the affected faces look weird at the start of that inflation... The
        inflation's initial configuration should just be what the model is like before the
        change" -- with root-to-root matching, the two corners right at a just-deleted
        connection, and any other slot whose group's root happened to shift, fell through to
        _seed_unknown_by_bfs's crude neighbor-jitter guess instead of their own perfectly good
        old position).

        Base-level slot-matching alone only seeds the COARSE (Level-0) corners from history --
        every FINE vertex below that gets re-derived fresh by _subdivide_combined_to_level3's
        pure interpolation, discarding the old, already pressure-calibrated curvature for the
        WHOLE mesh, not just near the edit (2026-09-29, explicit bug report: "the inflation
        started with all the faces flat, which is wrong because it should start from the
        inflated model we already have"). old_faces/old_face_of_fine/old_positions/
        old_source_polygon_id (captured here, before any of self.faces/positions/
        _pending_source_polygon_id below get overwritten) let the snap-back after subdividing
        (see this method's own tail, _fine_vertex_local_order) copy the OLD fine positions
        across exactly for every base face group whose own shape/corner order didn't change --
        now including the group(s) touching the edit too, since slot-matching (above) gives
        them a real old position for every one of their own corners as well."""
        old_faces = self.faces
        old_face_of_fine = self.face_of_fine
        old_positions = self.positions
        old_source_polygon_id = self._pending_source_polygon_id
        builder = self.builder_getter()
        mesh, err = builder.export_mesh_dict()
        if err:
            messagebox.showerror("Cannot Diff Inflate", err)
            return
        try:
            new_base_faces, new_base_edges, new_face_edge_ids = _load_mesh_from_dict(mesh)
        except ValueError as e:
            messagebox.showerror("Cannot Diff Inflate", str(e))
            return
        source_polygon_id = mesh.get("source_polygon_id") or []
        new_root_to_id = builder.root_to_vertex_id()

        prepared = _prepare_mesh_for_inflate(new_base_faces, new_base_edges, new_face_edge_ids,
                                              source_polygon_id)
        if prepared[0] == "place":
            # Degenerate even before considering pendants -- see _diff_remove_face's own
            # matching branch for why this redirects instead of trying to warm-start anything.
            self._diff_redirect_pending = True
            self.on_full_inflate_clicked(change_label=self._change_label)
            return
        (_mode, core_base_faces, core_base_edges, core_face_edge_ids, core_source_polygon_id,
         pendants) = prepared

        self._pre_click_snapshot = self._snapshot_mesh_state()
        self._stop_event = threading.Event()
        self._stop_requested = False

        central_ids = builder.central_shape_ids()
        central_shapes = [s for s in builder.shapes if s["id"] in central_ids]
        central_connections = [c for c in builder.connections
                                if c["a_shape"] in central_ids and c["b_shape"] in central_ids]
        new_expanded_shapes, new_expanded_connections, _spid = _expand_folded_shapes(
            central_shapes, central_connections)
        new_slot_roots = _vertex_roots(new_expanded_shapes, new_expanded_connections)
        old_slot_to_id = self._old_atomic_slot_to_id()

        seed = {}
        for shape in new_expanded_shapes:
            for corner in _shape_face_corner_order(shape):
                slot = (shape["id"], corner)
                root = new_slot_roots.get(slot)
                new_id = new_root_to_id.get(root) if root is not None else None
                if new_id is None or new_id in seed:
                    continue
                old_id = old_slot_to_id.get(slot)
                if old_id is not None and old_id in self.positions:
                    seed[new_id] = self.positions[old_id]
        matched_base_ids = set(seed)
        rng = np.random.default_rng(0)
        _seed_unknown_by_bfs(core_base_faces, seed, rng)

        self.base_faces = core_base_faces
        self.base_edges = core_base_edges
        self.base_face_edge_ids = core_face_edge_ids
        self._pending_source_polygon_id = core_source_polygon_id
        self._pending_pendants = pendants
        self.faces, self.positions, self.edge_length, self.face_of_fine = \
            _subdivide_combined_to_level3(core_base_faces, core_face_edge_ids, seed)
        self._snap_unchanged_groups_to_old_fine_positions(
            core_base_faces, core_source_polygon_id, matched_base_ids,
            old_faces, old_face_of_fine, old_positions, old_source_polygon_id)
        self.edges = None
        self.subdivision_level = MAX_LEVEL
        # Deliberately no self._render() here -- any freshly-seeded (as opposed to root-
        # matched) vertex is still at its crude BFS/jitter guess, not yet pulled into shape by
        # calibration -- drawing it now showed a visibly wrong/"stiff" pose (2026-09-19,
        # explicit: "don't draw un-finalized/unconverged simulations"). The panel keeps showing
        # whatever it last had until the calibration pass below actually finishes.
        self._set_running(True, active="diff")
        # Straight to pressure calibration (_run_inflate_step), deliberately WITHOUT a
        # zero-pressure relax_initial_configuration pass first: that force law is pure Hooke's-
        # law springs with NO pressure term, so run on the OLD (root-matched) portion (already
        # stretched well past rest length by whatever pressure it converged at) it would just
        # yank the already-correct old shape back toward rest length before the calibration
        # below ever got to re-inflate it -- wasted work at best, a bad/slow-to-recover starting
        # point at worst. estimate_pressure_for_target_stretch's own trials use relax_once (the
        # REAL, pressure-inclusive force law) starting fresh from these seeded positions each
        # time, so the old portion's already-correct geometry is respected from the very first
        # trial.
        self._set_status(f"{self._pipeline_label()} -- Level {MAX_LEVEL}: Step 0.", "info")
        self._run_inflate_step(initial_pressure_guess=self.last_pressure,
                                tol_pct=DIFF_PRESSURE_GUESS_TOL_PCT)

    def _snap_unchanged_groups_to_old_fine_positions(
            self, core_base_faces, core_source_polygon_id, matched_base_ids,
            old_faces, old_face_of_fine, old_positions, old_source_polygon_id):
        """Mutates self.positions in place, right after _diff_reexport_and_relax's own
        _subdivide_combined_to_level3 call -- for every NEW base face group whose own corners
        ALL root-matched (every id in matched_base_ids, i.e. this shape's own gluing pattern is
        completely unaffected by the edit), replaces its freshly-interpolated FINE vertices with
        the OLD mesh's own already-curved ones, via _fine_vertex_local_order's local-index
        identity (own docstring has the full "why this is safe" reasoning) -- a no-op fallback
        (leaves the flatter interpolated guess in place) for any group that's new, unmatched, or
        whose fine vertex COUNT doesn't line up with its old counterpart (should never happen
        for a genuinely unchanged shape, but cheap to guard rather than assume).

        `old_source_polygon_id`, only ever None for a session with no prior successful inflate
        at all, short-circuits immediately -- _diff_reexport_and_relax is never reached without
        one (Diff Inflate stays disabled until self.last_shapes_snapshot exists), so this is
        purely defensive."""
        if not old_source_polygon_id:
            return
        old_group_by_spid = {spid: g for g, spid in enumerate(old_source_polygon_id)}
        for group, base_face in enumerate(core_base_faces):
            if any(v not in matched_base_ids for v in base_face):
                continue
            spid = core_source_polygon_id[group] if core_source_polygon_id else None
            old_group = old_group_by_spid.get(spid)
            if old_group is None:
                continue
            new_order = _fine_vertex_local_order(self.faces, self.face_of_fine, group)
            old_order = _fine_vertex_local_order(old_faces, old_face_of_fine, old_group)
            if len(new_order) != len(old_order):
                continue
            for new_id, old_id in zip(new_order, old_order):
                pos = old_positions.get(old_id)
                if pos is not None:
                    self.positions[new_id] = pos

    # ---- background thread/progress-poll pattern (same idea as both sibling apps' own
    # _run_background) ----

    def _run_background(self, fn, on_done, on_progress=None):
        q = queue.Queue()

        def queue_progress(payload):
            q.put(("progress", payload))

        def worker():
            try:
                q.put(("done", fn(queue_progress)))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        if on_progress is not None:
                            on_progress(payload)
                        continue
                    if kind == "error":
                        # A crash mid-computation (2026-09-19, explicit: "sometimes it
                        # crashes") -- reverts the same way a non-convergence does, rather than
                        # leaving whatever partial/possibly-invalid state was on screen when it
                        # blew up.
                        self._revert_run(
                            f"Reverted to the state before Inflate (error: {payload}).",
                            popup_text=(
                                f"Inflate hit an error and was reverted: {payload}\n\nIf this "
                                "keeps happening, the mesh may have a loosely-attached or "
                                "floppy face -- try anchoring/reconnecting it and Inflate "
                                "again."))
                        return
                    on_done(payload)
                    return
            except queue.Empty:
                pass
            self.root.after(100, poll)

        self.root.after(100, poll)


# ---- combined window ----

def _scale_ui_fonts_once(root):
    """Scales every named Tk/ttk font by UI_FONT_SCALE, exactly once for the whole combined
    window -- same technique both sibling apps use (tkfont.nametofont mutates the interpreter-
    wide named font, so this only ever needs doing once regardless of how many panes read it)."""
    for name in tkfont.names(root):
        font = tkfont.nametofont(name, root=root)
        size = font.cget("size")
        if size == 0:
            continue
        sign = -1 if size < 0 else 1
        font.configure(size=sign * round(abs(size) * UI_FONT_SCALE))


class CombinedApp:
    def __init__(self, root):
        self.root = root
        # Smaller than this app's earlier 1500x900 (2026-09-19, explicit: "the window is too
        # big... make it smaller like the size of the polyhedron_inflater") -- close to that
        # sibling app's own ~1629x880, but this window also needs to fit a full builder pane
        # alongside the inflater, so slightly narrower/shorter than a literal match would be.
        root.geometry("1280x760")
        root.minsize(900, 560)

        # Window-title/unsaved-changes tracking (2026-09-29, explicit user request) --
        # self.current_session_path is only ever a `.hippie` (Save Session/Load Session of a
        # `.hippie`, specifically -- a plain "Load..." net or a loaded `.hippo` both leave this
        # None, i.e. "[Untitled]", even though a load just happened: neither has a `.hippie`
        # round-trip to associate the window with). Dirty state is TWO sources ORed together,
        # not one flag: self.builder._dirty (inherited from InteractiveBuilderApp, already
        # correctly revision-based -- undo/redo restore a snapshot's own ORIGINAL revision
        # number, so undoing every change since the last save/load lands back on that exact
        # number and correctly reads as clean again, not just "any edit happened" -- see its
        # own docstring) covers every 2D net edit; self._mesh_dirty (this app's own, since the
        # base class has no revision counter for it) covers a completed Full/Diff Inflate
        # changing the MESH a Save Session would write even when the 2D net itself didn't
        # change (e.g. a manual Reinflate after only a target-RMS/tolerance tweak). See
        # _update_title/_mark_dirty/_mark_clean.
        self.current_session_path = None
        self._mesh_dirty = False

        sv_ttk.set_theme("dark")
        _scale_ui_fonts_once(root)
        self._build_menu(root)
        # WM_DELETE_WINDOW (2026-09-29, explicit user request: "if the user tries to quit the
        # program, also prompt them to save if there are any unsaved changes") -- same
        # unsaved-work check File > New uses, see _confirm_discard_unsaved/_on_quit_request.
        root.protocol("WM_DELETE_WINDOW", self._on_quit_request)

        # A plain 2-column grid with equal, UNIFORM weight (not tk.PanedWindow, which only
        # obeys its stretch="always" flags for LEFTOVER space beyond each pane's own requested
        # size -- with panes this differently sized it never actually split 50/50) -- guarantees
        # the left/right panes stay exactly equal width, including as the window is resized
        # (2026-09-19, explicit: "the left and right pane should be equal width").
        container = ttk.Frame(root)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1, uniform="panes")
        container.columnconfigure(1, weight=1, uniform="panes")
        container.rowconfigure(0, weight=1)

        left_root = _PaneRoot(container)
        right_frame = ttk.Frame(container)
        left_root.grid(row=0, column=0, sticky="nsew")
        right_frame.grid(row=0, column=1, sticky="nsew")
        separator = ttk.Separator(container, orient=tk.VERTICAL)
        separator.place(relx=0.5, rely=0, relheight=1, anchor="n")

        self.builder = BuilderPane(left_root)
        self.inflater = InflaterPane(right_frame, lambda: self.builder)
        # Wired AFTER both panes exist -- keeps Diff Inflate's enabled state live across every
        # builder edit (BuilderPane._refresh_vme_state's own hook), not just re-checked when
        # Inflate is clicked. Also keeps the window title's own "*" current (2026-09-29,
        # explicit user request) -- self.builder._dirty already reflects this same edit the
        # instant _refresh_vme_state bumps self.builder._revision, so no separate dirty bit is
        # needed for this half of it (see __init__'s own comment).
        self.builder.on_change = self._on_builder_change
        # Reverse hover direction (2026-09-19, explicit) -- BuilderPane's own mouse hover
        # forwards to InflaterPane.set_hover_shape_from_builder via this, mirroring
        # InflaterPane's builder_getter above.
        self.builder.inflater_getter = lambda: self.inflater
        # 2026-09-19, explicit: "if auto inflate is enabled, as soon as i load a file, it
        # should also inflate" -- a fresh Load has no relation to whatever was inflated before
        # (if anything), so this always means a FULL Inflate, never a diff. Wrapped (rather
        # than wired straight to self.inflater.on_load_success) so a plain "Load..." ALSO
        # resets the window title to "[Untitled]", clean (2026-09-29, explicit user request) --
        # before InteractiveBuilderApp.on_load_clicked's own _saved_revision reset even runs,
        # so self.builder._dirty already reads False by the time this fires; if Auto Inflate
        # then re-solves the mesh, on_inflate_success (below) correctly marks it dirty again
        # once that finishes.
        self.builder.on_load_success = self._on_builder_load_success
        # 2026-09-28, explicit -- InflaterPane's own release-vs-debug UI split (target-stretch/
        # tolerance/Full/Diff/Auto Inflate vs. just Reinflate) reuses the SAME 'd'-key toggle
        # BuilderPane already has, rather than a separate one; see BuilderPane.
        # on_debug_mode_change/InflaterPane._apply_mode_visibility.
        self.builder.on_debug_mode_change = self.inflater._apply_mode_visibility
        # 2026-09-29, explicit user request -- see __init__'s own comment on self._mesh_dirty/
        # self.current_session_path for why these three exist.
        self.inflater.on_inflate_success = self._mark_dirty
        self.inflater.on_session_saved = self._mark_clean
        self.inflater.on_session_loaded = self._mark_clean

        self._update_title()

    def _on_builder_change(self):
        self.inflater.refresh_diff_eligibility()
        self._update_title()

    def _on_builder_load_success(self):
        self._mark_clean(path=None)
        self.inflater.on_load_success()

    def _update_title(self):
        """Single source of truth for the window title (2026-09-29, explicit user request):
        "[Untitled]" if self.current_session_path is None (started from scratch, or loaded from
        anything other than a `.hippie` -- see __init__'s own comment), else that file's own
        basename, plus a trailing "*" iff self.builder._dirty or self._mesh_dirty (unsaved
        changes)."""
        name = self.current_session_path.name if self.current_session_path else "[Untitled]"
        star = "*" if (self.builder._dirty or self._mesh_dirty) else ""
        self.root.title(f"{name}{star} - Interactive Inflater")

    def _mark_dirty(self):
        """Called from InflaterPane.on_inflate_success -- a completed Full/Diff Inflate (or the
        flat-place pipeline) changed the mesh a Save Session would write, independent of
        whatever self.builder._dirty already reflects (see __init__'s own comment)."""
        self._mesh_dirty = True
        self._update_title()

    def _mark_clean(self, path=None):
        """Called from InflaterPane.on_session_saved (a `.hippie` was just written to `path`)
        or on_session_loaded (a session was just loaded -- `path` is that `.hippie`'s own path,
        or None for a `.hippo`/plain "Load..." -- see _apply_loaded_session/
        _on_builder_load_success's own comments), and from File > New. Resets BOTH dirty
        sources to clean: self.builder._saved_revision = self.builder._revision (the SAME
        mark-clean InteractiveBuilderApp's own on_new_clicked/on_save_as_clicked/on_load_clicked
        do for their own `.poly` scheme -- reused here for the `.hippie` one instead, since it's
        the exact same revision-comparison self.builder._dirty already reads) and
        self._mesh_dirty = False."""
        self.current_session_path = Path(path) if path else None
        self.builder._saved_revision = self.builder._revision
        self._mesh_dirty = False
        self._update_title()

    def _confirm_discard_unsaved(self):
        """Returns True if it's safe to proceed with something that would discard the current
        session (File > New, or closing the window) -- either nothing's unsaved, the user said
        to discard it anyway ("No"), or they said to save first ("Yes") and
        InflaterPane.on_save_session_clicked actually went through (it returns False on a
        cancelled save dialog or a refused save, e.g. nothing's been inflated yet -- see its own
        docstring). Returns False if the caller should abort instead: "Cancel", or "Yes"
        followed by a save that didn't actually happen, since proceeding would still lose the
        unsaved work (2026-09-29, explicit user request, same three-way prompt
        InteractiveBuilderApp's own _confirm_discard_unsaved uses for its `.poly` scheme,
        reimplemented here for `.hippie` Save Session instead of that class's own `.poly` Save
        As -- interactive_builder_app/app.py is read-only from here)."""
        if not (self.builder._dirty or self._mesh_dirty):
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", "Save your changes before continuing?")
        if answer is None:  # Cancel
            return False
        if not answer:  # No -- discard
            return True
        return self.inflater.on_save_session_clicked()  # Yes -- must actually succeed

    def _on_new_clicked(self):
        """File > New (2026-09-29, explicit user request) -- prompts to save first if anything's
        unsaved (_confirm_discard_unsaved), then clears the LEFT pane's canvas back to empty
        (same fields InteractiveBuilderApp's own on_new_clicked clears, plus this app's own
        anchor concept) and resets the window title to "[Untitled]", clean. A no-op while an
        inflate is running -- same "the net could still be changing underneath" reasoning
        on_save_session_clicked's own guard has.

        Deliberately does NOT touch self.inflater's own mesh fields directly -- clearing
        self.builder.shapes/connections then calling _refresh_vme_state() (which fires
        self.on_change -> refresh_diff_eligibility) already cascades into InflaterPane's own
        "nothing's central anymore" branch, which clears self.faces/positions/base_faces/etc.
        AND sets self.is_fully_inflated = False (Rule 2 -- explicit user request: "set
        is_fully_inflated to false"), exactly the same way deleting every shape by hand already
        does -- reusing that existing path instead of duplicating its field list here."""
        if self.inflater._running:
            return
        if not self._confirm_discard_unsaved():
            return
        b = self.builder
        if b.shapes or b.connections:
            b._push_undo()
        b.shapes.clear()
        b.connections.clear()
        b.selected_ids = set()
        b.selected_connection_id = None
        b._drag_state = None
        b._anchor_shape_id = None
        b._refresh_vme_state()
        b._redraw()
        self._mark_clean(path=None)

    def _on_quit_request(self):
        """WM_DELETE_WINDOW (the window's own close button, Alt+F4, etc. -- 2026-09-29, explicit
        user request) -- same unsaved-work check File > New uses before actually closing."""
        if self._confirm_discard_unsaved():
            self.root.destroy()

    def _build_menu(self, root):
        """A File menu with New/Load.../Load Session.../Save Session... -- see New (below), and
        InflaterPane.on_load_session_clicked/on_save_session_clicked's own docstrings for the
        other two. Same explicit-color kwargs as interactive_builder_app's own _build_menu
        (MENU_BG/MENU_FG/etc, imported, not duplicated) so this matches that app's look."""
        menu_kwargs = dict(bg=MENU_BG, fg=MENU_FG, activebackground=MENU_ACTIVE_BG,
                            activeforeground=MENU_FG, disabledforeground=MENU_DISABLED_FG)
        menubar = tk.Menu(root, **menu_kwargs)
        file_menu = tk.Menu(menubar, tearoff=False, **menu_kwargs)
        # 2026-09-29, explicit user request -- see _on_new_clicked's own docstring.
        file_menu.add_command(label="New", command=lambda: self._on_new_clicked())
        file_menu.add_command(label="Load...", command=lambda: self.builder.on_load_clicked())
        # 2026-09-26, explicit -- restores a full inflate_polyhedron_app .hippo session (net +
        # mesh + params + pressure) into this combined window; see InflaterPane.
        # on_load_session_clicked's own docstring.
        file_menu.add_command(label="Load Session...",
                               command=lambda: self.inflater.on_load_session_clicked())
        # 2026-09-26, explicit -- writes a .hippie (this app's own session format, the only one
        # allowed >1 connected piece); see InflaterPane.on_save_session_clicked's own docstring.
        file_menu.add_command(label="Save Session...",
                               command=lambda: self.inflater.on_save_session_clicked())
        menubar.add_cascade(label="File", menu=file_menu)
        root.config(menu=menubar)


def main():
    # Must run BEFORE tk.Tk() -- once the window exists it's too late to change how Windows
    # scales it. Reused from interactive_builder_app (imported, not duplicated) rather than a
    # second copy in this file; without it, Tk renders at a virtualized 96 DPI and Windows
    # bitmap-stretches the whole window (UI text included, not just the 3D panel) to the
    # display's real scaling -- the actual cause of "the entire app... down to the UI. the
    # text looks fuzzy too" (2026-09-19, explicit).
    _enable_windows_dpi_awareness()
    root = tk.Tk()
    CombinedApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
