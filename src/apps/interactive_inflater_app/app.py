"""Interactive Inflater -- combines interactive_builder_app's net-building
canvas (left pane) with a simplified, single-panel version of
inflate_polyhedron_app's solver viewer (right pane) in one window, so a net
built by hand can be inflated immediately with no save/load round trip.

    python src/apps/interactive_inflater_app/app.py

Left pane (BuilderPane): reuses interactive_builder_app.app.InteractiveBuilderApp
directly (imported, not copied -- that file is read-only here, see the
net-fold-project skill's untouchable.md) via a small subclass that only
overrides layout (_build_ui/_build_palette_entry: shape palette moved to a
TOP row, centered; the Move/Join/Polygon-Fold tool strip moved to the LEFT,
matching this app's own required layout) and drops the pieces that only make
sense for a standalone window (its own File menu/window title/WM_DELETE_
WINDOW/font-scaling pass -- CombinedApp builds ONE File menu, with just
Load... (no Save yet, 2026-09-19, explicit), for the whole window instead).
Every canvas interaction (place/drag/select/delete/rotate/pan, Move/Join/
Fold modes, bezier connections, Polygon Fold, undo/redo, flip, debug mode)
is exactly interactive_builder_app's own, unmodified.

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

Simplifications vs. inflate_polyhedron_app (all explicitly allowed by this
app's own spec):
- One drawing panel, redrawn per level, not four side-by-side ones.
- No replay-frame capture/animation -- estimate_pressure_for_target_stretch
  is called with capture_frames=False; the winning trial's final result is
  applied and drawn directly.
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
from tkinter import messagebox, ttk
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
from common.ui_theme import FACE_COLORS, PLOT_THEME, STATUS_COLORS

from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.inflate_polyhedron.stretchy_mesh import (
    EDGE_LENGTH, estimate_pressure_for_target_stretch, load_stretchy_mesh,
    load_stretchy_mesh_edges, mesh_edges, random_initial_positions,
    relax_initial_configuration,
)

# interactive_builder_app/app.py is NOT on the untouchable list, but per this app's own
# instructions it's still read-only from here -- imported directly (a plain namespace-package
# import, src/apps/ already being on sys.path) rather than copied, so its ~3700 lines of net-
# building logic are reused verbatim, not duplicated.
from interactive_builder_app.app import (
    CONNECTION_SELECTED_WIDTH, ICON_SIZE, MENU_ACTIVE_BG, MENU_BG, MENU_DISABLED_FG, MENU_FG,
    NetValidationError, POLYGON_COLORS, POLYGON_NS, InteractiveBuilderApp, _ICON_VERTICES,
    _rasterize_polygon, _enable_windows_dpi_awareness, _expand_folded_shapes,
    _shape_face_corner_order, _vertex_roots,
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
INFLATER_ICON_SIZE = 48

# ---- right pane (InflaterPane) constants, adapted from inflate_polyhedron_app ----

DEFAULT_TOLERANCE = 1e-4
LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 80.0, 2: 40.0, 3: 10.0}
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
# edge 3 for both sides and highlight width 4"). The yellow hover highlight stays visually
# thicker still (HOVER_HIGHLIGHT_LINE_WIDTH) so it always reads as distinct from the ordinary
# edges.
POLYGON_EDGE_LINE_WIDTH = 3.0
HOVER_HIGHLIGHT_LINE_WIDTH = 4.0
SELECTED_HIGHLIGHT_LINE_WIDTH = 4.0

# How many pixels of ButtonPress-1-to-release movement still counts as a plain click (selects a
# face) rather than a rotate-drag -- a real click's press/release coordinates are rarely bit-
# for-bit identical (trackpad/mouse jitter), so 0 would misclassify most genuine clicks as tiny
# drags.
CLICK_MOVE_TOLERANCE_PX = 3

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


def _is_valid_numeric_partial(proposed, allow_exponent, allow_decimal=True):
    """True if `proposed` is a full number or a prefix a user could still be typing toward one
    -- same validation idea as inflate_polyhedron_app's own _is_valid_numeric_partial
    (duplicated, not imported -- a tiny, self-contained regex check, not worth pulling in that
    whole module for)."""
    digits = r"\d*\.?\d*" if allow_decimal else r"\d*"
    pattern = f"-?{digits}(?:[eE][-+]?\\d*)?" if allow_exponent else f"-?{digits}"
    return re.fullmatch(pattern, proposed) is not None


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
        connections in 3d... drag to connect to another edge midpoint"). A no-op while locked
        (mirrors _on_canvas_press_join's own lock check for the 2D gesture) or if either shape
        has since been deleted."""
        if self._locked:
            return
        a_shape, b_shape = self._shape_by_id(a_shape_id), self._shape_by_id(b_shape_id)
        if a_shape is None or b_shape is None:
            return
        self._push_undo()
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
        self._redraw()

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
        Move mode picks a whole shape (face selection is Move-only, 2026-09-19 explicit); Join
        mode (idle, i.e. not currently dragging out a NEW pending connection) picks a connection
        OR an open edge's own handle (mutually exclusive by construction -- an edge is always
        exactly one or the other) -- in either OTHER case (Fold, or Join mid-drag) none of these
        hovers apply, so all three are cleared. The open-edge pick reuses
        InteractiveBuilderApp's own _hit_test_any_edge_handle with no exclude/require args --
        EXACTLY the nearest-unjoined-handle-within-HANDLE_HIT_RADIUS lookup its own _redraw
        already uses to decide what to reveal, so "visible in 2D" and "forwarded to 3D" can
        never disagree (2026-09-19, explicit: "in 2d, i need to hover near the edge midpoint
        for the midpoint to show" -- unchanged, this just ALSO mirrors that same rule's result)."""
        super()._on_canvas_motion(event)
        shape_id = None
        conn_id = None
        open_edge_key = None
        if self.tool_mode == "move" and self.armed_n is None:
            wx, wy = self._screen_to_world(event.x, event.y)
            hit = self._hit_test(wx, wy)
            shape_id = None if hit is None else hit["id"]
        elif self.tool_mode == "join" and self._connection_pending is None:
            conn_id = self._hit_test_connection(event.x, event.y)
            handle = self._hit_test_any_edge_handle(event.x, event.y)
            if handle is not None:
                open_edge_key = (handle["shape_id"], handle["edge_index"])
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

    def _redraw(self):
        """Runs InteractiveBuilderApp's own full redraw unchanged (which already draws its own
        RED selection outline for self.selected_ids), then draws the yellow HOVER highlight (if
        any) on top -- _redraw's own canvas.delete("all") wipes everything first, so this can't
        be done as a one-time canvas item; it has to be re-added after every single redraw, from
        whatever edit triggered it (drag/rotate/connect/etc.), not just from set_hover_shape's
        own calls. Outlines whichever shape(s) are hovered from EITHER direction (3D->2D's
        _face_hover_shape_id, this canvas's own _mouse_hover_shape_id) -- a set, deduplicated,
        since both are usually the same shape or one of them is None -- EXCLUDING anything
        already selected (2026-09-19, explicit: "when you hover then select, the face should go
        from being highlighted (yellow) to being selected (red) [don't draw both]"): the base
        class's own red selection outline already covers that case, so a second yellow one on
        top would just be visual noise.

        Also forwards self.selected_ids to InflaterPane whenever it's changed since the last
        forward (see _last_forwarded_selected_ids' own docstring for why this diff-on-redraw
        approach, rather than hooking every mutation site, is used)."""
        super()._redraw()
        hover_ids = {sid for sid in (self._face_hover_shape_id, self._mouse_hover_shape_id)
                     if sid is not None and sid not in self.selected_ids}
        for shape_id in hover_ids:
            shape = self._shape_by_id(shape_id)
            if shape is not None:
                screen_vertices = [self._world_to_screen(*wv)
                                    for wv in self._shape_world_vertices(shape)]
                flat = [coord for point in screen_vertices for coord in point]
                self.canvas.create_polygon(flat, outline="yellow", fill="", width=3)

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
        # Join mode (where this whole concept doesn't apply, and the shape it names may not even
        # still exist as placed).
        if (self._forced_hover_open_edge is not None and self.tool_mode == "join"
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
    # actively working from. Move/rotate/pan/zoom stay allowed throughout -- none of them are
    # guarded below, and none of them affect the exported mesh at all (classify_change ignores
    # cx/cy/rotation entirely) -- only actions that ADD/REMOVE a shape or connection, or an
    # UNDO/REDO/LOAD that could do either, are blocked.
    _locked = False

    def set_locked(self, locked):
        """Called by InflaterPane._set_running. Does NOT force the tool mode back to "move"
        (2026-09-19, explicit: "after deleting a connection, it went back to Move mode. It
        should remain in the same mode" -- deleting a connection while in Join mode is exactly
        what triggers the auto-Diff-Inflate that locks the pane) -- staying in Join/Fold while
        locked is safe on its own, since their own click-click connection gesture is blocked
        directly, at the gesture level (_on_canvas_press_join below), not by kicking the user
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
            self._refresh_vme_state()
        self._redraw()

    def _on_palette_clicked(self, n):
        if self._locked:
            return
        super()._on_palette_clicked(n)

    def _on_canvas_press_join(self, event):
        # Blocks Join/Polygon Fold's own click-click gesture while locked -- it's the one
        # remaining way those modes could still create/edit a connection (hover/selection
        # there stay read-only and are left alone). Since set_locked no longer forces the tool
        # mode back to "move", this is now the ONLY thing standing between a mid-computation
        # click and a corrupted mesh the background thread is actively working from.
        if self._locked:
            return
        # InteractiveBuilderApp's own press handling still ARMS a pending connection from
        # whichever handle was clicked (unchanged) -- the actual behavior change (2026-09-19,
        # explicit: "let's use drag-and-drop to connect midpoints... right now it's
        # click-and-click in 2d") lives entirely in _on_canvas_drag/_on_canvas_release below,
        # which resolve that pending connection at RELEASE instead of waiting for a SEPARATE
        # second click. Its "complete a pending connection" branch (a genuine second click,
        # with the mouse button not held since the first) is dead in practice now -- release
        # always already cleared self._connection_pending by the time any later press could
        # reach it -- but left alone rather than touching this untouchable base method's own
        # call.
        super()._on_canvas_press_join(event)

    def _on_canvas_drag(self, event):
        """Runs InteractiveBuilderApp's own drag handling (shape-move/bezier-handle-drag/
        marquee) UNCHANGED for everything except an active Join/Fold pending connection
        (2026-09-19, explicit: drag-and-drop, see _on_canvas_press_join above) -- for that one
        case, calls its own _on_canvas_motion instead, which is what recomputes
        _hover_shape_id/_hover_edge_index/_pending_cursor_screen for a pending connection
        (bound to plain <Motion>, which never fires while a button is held -- this is what
        turns "arm, release the mouse, move normally, click again" into "arm, keep the button
        held, drag, release")."""
        if self._connection_pending is not None:
            self._on_canvas_motion(event)
            return
        super()._on_canvas_drag(event)

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
        # Blocks switching INTO Join/Polygon Fold while locked -- their own click-click
        # gesture is blocked directly (_on_canvas_press_join above), but a user who wasn't
        # already in one of those modes when the lock kicked in still shouldn't be able to
        # enter one now (there'd be nothing useful to do there anyway). A user who WAS already
        # there stays there -- this only blocks the transition INTO Join/Fold, not staying put.
        if self._locked and mode != "move" and mode != self.tool_mode:
            return
        # 2026-09-19, explicit: "when switching between modes, everything is deselected" --
        # super()._set_tool_mode already clears self.selected_ids/selected_connection_id (its
        # own _redraw, called at the end, diff-forwards those to InflaterPane -- see
        # _last_forwarded_selected_ids/_last_forwarded_selected_connection_id), but the HOVER
        # attributes below aren't covered by that diff (hover isn't "state", just a transient
        # highlight) and aren't reset by the base class at all, so they're cleared here
        # explicitly, both this pane's own copies and InflaterPane's.
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

    def _on_delete_key(self, _event):
        if self._locked:
            return
        super()._on_delete_key(_event)

    def _flip_selected_shapes(self, axis):
        # Flip changes a shape's own "flipped" field, which classify_change DOES compare (see
        # its own docstring) -- unlike a plain move/rotate, this is a real topology-relevant
        # edit, so it's blocked while locked too.
        if self._locked:
            return
        super()._flip_selected_shapes(axis)

    def on_copy_key(self, _event=None):
        if self._locked:
            return
        super().on_copy_key(_event)

    def on_paste_key(self, _event=None):
        if self._locked:
            return
        super().on_paste_key(_event)

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
        if self.shapes is not shapes_before and self.on_load_success is not None:
            self.on_load_success()

    def _refresh_vme_state(self):
        """Runs InteractiveBuilderApp's own vertex-merge-error check unchanged, then notifies
        the right pane (self.on_change, if wired) that the net may have changed -- this is the
        one call site EVERY state-changing edit (place/delete/connect/flip/undo/redo/load/drag-
        release) already funnels through (see that class's own docstring), so it's the natural
        hook for keeping Diff Inflate's enabled state live without a change-tracking mechanism
        of this app's own."""
        super()._refresh_vme_state()
        if self.on_change is not None:
            self.on_change()

    def snapshot_state(self):
        """Returns (shapes, connections) -- per-dict SHALLOW copies (shape/connection dicts are
        flat; edits like flip/drag mutate them IN PLACE, so a plain list-of-references snapshot
        would silently "change" along with the live state) of self.shapes/self.connections at
        this exact moment, for a later classify_change call to diff against."""
        return [dict(s) for s in self.shapes], [dict(c) for c in self.connections]

    def classify_change(self, old_shapes, old_connections):
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
        drawing detail, never read by the exported mesh either."""
        if old_shapes is None:
            return "complex", None
        old_by_id = {s["id"]: s for s in old_shapes}
        new_by_id = {s["id"]: s for s in self.shapes}
        old_ids, new_ids = set(old_by_id), set(new_by_id)
        added, removed, common = new_ids - old_ids, old_ids - new_ids, old_ids & new_ids
        for sid in common:
            a, b = old_by_id[sid], new_by_id[sid]
            if a["n"] != b["n"] or a.get("flipped", False) != b.get("flipped", False):
                return "complex", None

        def conn_key(c):
            return frozenset([(c["a_shape"], c["a_edge"]), (c["b_shape"], c["b_edge"])])

        def touches(key, shape_id):
            return any(sid == shape_id for sid, _edge in key)

        def touches_any(key, shape_ids):
            return any(sid in shape_ids for sid, _edge in key)

        old_conns = {conn_key(c) for c in old_connections}
        new_conns = {conn_key(c) for c in self.connections}
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

        top = ttk.Frame(self.root, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)
        # Icons packed into an INNER frame that itself is centered in `top` (pack's default
        # anchor="center" centers a non-filling child within its parcel) -- packing the icons
        # straight into `top` (which fills X) would leave them flush left instead
        # (2026-09-19, explicit: "centre-align the n-gon buttons").
        palette_row = ttk.Frame(top)
        palette_row.pack(side=tk.TOP)
        for n in POLYGON_NS:
            self._build_palette_entry(palette_row, n)

        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(side=tk.LEFT, fill=tk.Y)
        self._build_toolbar(toolbar)

        self.canvas = tk.Canvas(self.root, bg=PLOT_THEME["bg"],
                                 highlightthickness=1, highlightbackground=PLOT_THEME["fg"])
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8), pady=8)
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
        self._bind_all_guarded("<KeyPress-m>", lambda _e: self._set_tool_mode("move"))
        self._bind_all_guarded("<KeyPress-j>", lambda _e: self._set_tool_mode("join"))
        self._bind_all_guarded("<KeyPress-p>", lambda _e: self._set_tool_mode("fold"))
        self._bind_all_guarded("<KeyPress-h>", lambda _e: self._flip_selected_shapes("horizontal"))
        self._bind_all_guarded("<KeyPress-v>", lambda _e: self._flip_selected_shapes("vertical"))
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
        app's own ICON_SIZE -- this app's own required layout."""
        icon = tk.Canvas(parent, width=INFLATER_ICON_SIZE, height=INFLATER_ICON_SIZE,
                          bg=PLOT_THEME["bg"], highlightthickness=2,
                          highlightbackground=PLOT_THEME["bg"])
        icon.pack(side=tk.LEFT, padx=2)
        cx, cy = INFLATER_ICON_SIZE / 2, INFLATER_ICON_SIZE / 2
        scale = INFLATER_ICON_SIZE / ICON_SIZE
        screen_vertices = [(vx * scale + cx, vy * scale + cy) for vx, vy in _ICON_VERTICES[n]]
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

    def export_mesh_dict(self):
        """Returns (mesh_dict, None) built from the CURRENT live shapes/connections, via the
        exact same _expand_folded_shapes/_faces_from_shapes/_edges_from_shapes/
        _face_edge_ids_from_shapes pipeline File > Save uses in interactive_builder_app
        (_export_faces_and_layout, inherited unchanged) -- or (None, message) if the net is
        empty or fails validation (self-loop, duplicate edge, disconnected net, etc.), for the
        caller to show via the existing error-messaging pattern instead of crashing."""
        if not self.shapes:
            return None, "Nothing to inflate yet -- place at least one shape first."
        try:
            faces, edges, face_edge_ids, source_polygon_id, _net_layout, _builder_connections = \
                self._export_faces_and_layout()
        except (NetValidationError, ValueError) as e:
            return None, str(e)
        mesh = {"name": "live_net", "faces": faces, "edges": edges,
                "face_edge_ids": face_edge_ids, "source_polygon_id": source_polygon_id}
        return mesh, None

    def root_to_vertex_id(self):
        """Returns {root_slot: vertex_id} in the SAME numbering export_mesh_dict's own
        _faces_from_shapes (run inside the inherited _export_faces_and_layout) assigns --
        root_slot a (shape_id, corner_index) tuple from interactive_builder_app._vertex_roots,
        run over the EXPANDED (post-_expand_folded_shapes) shapes/connections to match what's
        actually exported. A root slot is STABLE across an edit that doesn't touch its own
        group (see _vertex_roots' own docstring) -- unlike the raw integer id, which shifts
        under an edit that merges/splits vertex groups (a connection add/remove), NOT just a
        plain shape append/removal. Lets InflaterPane match a vertex across two different
        exports by this stable identity instead of by raw id (see
        InflaterPane._diff_reexport_and_relax). This duplicates _faces_from_shapes' own
        numbering loop (that function doesn't return the root map itself) rather than editing
        it -- interactive_builder_app/app.py is read-only from here."""
        if not self.shapes:
            return {}
        expanded_shapes, expanded_connections, _source_polygon_id = \
            _expand_folded_shapes(self.shapes, self.connections)
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

        # The BUILDER's own shapes/connections at the moment of the last successfully-COMPLETED
        # inflate (Full or Diff) -- None until the first one finishes -- plus source_polygon_id
        # (parallel to self.base_faces) from that same mesh, so a later add/remove diff can find
        # which base face(s) a given shape id owns. Set together, only on a clean "Done" (see
        # _record_inflate_success), never on a mid-pipeline stop/failure.
        self.last_shapes_snapshot = None
        self.last_connections_snapshot = None
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
        self._render()

    # ---- UI ----

    def _build_ui(self):
        setup = ttk.Frame(self.root, padding=8)
        setup.pack(side=tk.TOP, fill=tk.X)

        # One row -- "Target stretch: L1 __ L2 __ L3 __  Tolerance: ___" -- short enough
        # labels/entry widths to fit on a single line even in this pane's own (roughly half-
        # window) width (2026-09-19, explicit: "i want all to fit on one line if possible").
        row = ttk.Frame(setup)
        row.pack(side=tk.TOP, anchor=tk.W)
        ttk.Label(row, text="Target stretch:").pack(side=tk.LEFT, padx=(0, 4))
        self.target_rms_vars = {}
        self.target_rms_display_vars = {}
        for level in (1, 2, 3):
            ttk.Label(row, text=f"L{level}:").pack(side=tk.LEFT, padx=(8, 2))
            var = tk.DoubleVar(value=round(LEVEL_DEFAULT_TARGET_RMS_PCT[level]))
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
        button_row = ttk.Frame(setup)
        button_row.pack(side=tk.TOP, anchor=tk.W, pady=(8, 0))
        self.full_inflate_button = ttk.Button(
            button_row, text="Full Inflate", command=self.on_full_inflate_clicked)
        self.full_inflate_button.pack(side=tk.LEFT)
        self.diff_inflate_button = ttk.Button(
            button_row, text="Diff Inflate", command=self.on_diff_inflate_clicked)
        self.diff_inflate_button.pack(side=tk.LEFT, padx=(8, 0))
        self.diff_inflate_button.state(["disabled"])
        # Default checked (2026-09-19, explicit) -- whenever refresh_diff_eligibility finds a
        # single-face/connection add/remove since the last completed inflate (the SAME
        # DIFF_ELIGIBLE_KINDS check the button's own enabled state uses), it fires Diff Inflate
        # automatically instead of just enabling the button.
        self.auto_inflate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(button_row, text="Auto Inflate", variable=self.auto_inflate_var).pack(
            side=tk.LEFT, padx=(8, 0))

        self.status_label = ttk.Label(self.root, anchor="w", padding=(8, 3))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.panel_label = tk.Label(self.root, bg=PLOT_THEME["bg"], bd=0,
                                     width=PANEL_SIZE[0], height=PANEL_SIZE[1])
        self.panel_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.plotter = pv.Plotter(off_screen=True, window_size=list(self.panel_size))
        self.plotter.set_background(PLOT_THEME["bg"])
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

    def _register_numeric_entry(self, entry, allow_exponent, allow_decimal=True):
        vcmd = self.root.register(lambda proposed: _is_valid_numeric_partial(
            proposed, allow_exponent, allow_decimal))
        entry.configure(validate="key", validatecommand=(vcmd, "%P"))

    def _begin_edit_target_rms(self, level):
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}")

    def _sync_target_rms_display(self, level):
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}%")

    def _commit_target_rms_entry(self, level, _event=None):
        try:
            value = round(float(self.target_rms_display_vars[level].get()))
        except (tk.TclError, ValueError):
            value = LEVEL_DEFAULT_TARGET_RMS_PCT[level]
        self.target_rms_vars[level].set(max(0, min(100, value)))

    def _get_tolerance(self):
        try:
            return float(self.tolerance_var.get())
        except ValueError:
            return DEFAULT_TOLERANCE

    def _set_status(self, text, kind="info"):
        self.status_label.config(text=text, foreground=STATUS_COLORS.get(kind, STATUS_COLORS["info"]))

    def _set_running(self, running, active=None):
        """running=True: `active` ("full" or "diff") is whichever button was clicked -- that
        button switches to "Stop" (still enabled, now wired to _on_stop_clicked), the OTHER one
        disables. running=False: both buttons return to their normal text/command
        (2026-09-19, explicit: "After Diff Inflate or Full Inflate are clicked, they should
        change to Stop so that the user can stop the simulation"). Either way, also locks/
        unlocks the LEFT pane (BuilderPane.set_locked) -- while an inflate of any kind is
        running, the net stays read-only (move/rotate/pan/the 3D camera still work; add/
        delete/connect don't) so a mid-computation edit can never invalidate the mesh the
        background thread is actively working on (2026-09-19, explicit)."""
        self._running = running
        if running:
            self._active_button = active
            active_btn = self.full_inflate_button if active == "full" else self.diff_inflate_button
            other_btn = self.diff_inflate_button if active == "full" else self.full_inflate_button
            active_btn.config(text="Stop", command=self._on_stop_clicked)
            active_btn.state(["!disabled"])
            other_btn.state(["disabled"])
        else:
            self._active_button = None
            self.full_inflate_button.config(text="Full Inflate", command=self.on_full_inflate_clicked)
            self.full_inflate_button.state(["!disabled"])
            self.diff_inflate_button.config(text="Diff Inflate", command=self.on_diff_inflate_clicked)
        self.builder_getter().set_locked(running)
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
        still points at never change out from under it."""
        return {
            "base_faces": self.base_faces, "base_edges": self.base_edges,
            "base_face_edge_ids": self.base_face_edge_ids, "faces": self.faces,
            "edge_length": self.edge_length, "face_of_fine": self.face_of_fine,
            "edges": self.edges, "positions": self.positions,
            "subdivision_level": self.subdivision_level,
            "pending_source_polygon_id": self._pending_source_polygon_id,
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
        popup telling the user what they themselves just did)."""
        if self._pre_click_snapshot is not None:
            self._restore_mesh_state(self._pre_click_snapshot)
        self._pre_click_snapshot = None
        self._stop_event = None
        self._stop_requested = False
        self._render()
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
        if self.auto_inflate_var.get() and not self._running:
            self.on_full_inflate_clicked()

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
        # Keeps self._open_edges in sync with the LIVE net on every edit, not just after the
        # next full _render() (which only happens once an Inflate actually runs) -- otherwise a
        # just-made-or-broken connection could keep offering/hiding its own edges' 3D
        # drag-to-connect handles a beat too long (2026-09-19 feature, "creating connections in
        # 3d").
        self._rebuild_open_edges()
        if self._running or self.last_shapes_snapshot is None:
            self.diff_inflate_button.state(["disabled"])
            return
        kind, _extra = self.builder_getter().classify_change(
            self.last_shapes_snapshot, self.last_connections_snapshot)
        eligible = kind in self.DIFF_ELIGIBLE_KINDS
        self.diff_inflate_button.state(["!disabled"] if eligible else ["disabled"])
        if eligible and self.auto_inflate_var.get():
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
        # A ButtonPress-1 landing while an open edge is currently revealed (Join mode's own
        # hover-reveal, see _set_hover_open_edge) starts a drag-to-connect instead of a camera
        # rotate-drag (2026-09-19, explicit: "hover over an open edge... drag to connect to
        # another edge midpoint... clicking is distinct from press-drag-release, which is used
        # for rotation" -- the same distinction, extended to a second drag-triggering gesture).
        if self.builder_getter().tool_mode == "join" and self._hover_open_edge_key is not None:
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
        Join[J] mode, hovering over the 3d edge highlights the corresponding 2d connection") --
        Move picks a whole face (_set_hover_group); Join picks the nearest connection seam
        (_hover_edge_at); any other mode (Fold) clears both, since neither gesture applies
        there."""
        if not self._actor_to_group:
            return
        mode = self.builder_getter().tool_mode
        if mode == "move":
            width, height = self.panel_size
            # VTK's own pixel origin is bottom-left; Tk's (event.x/event.y) is top-left.
            self._picker.Pick(event.x, height - 1 - event.y, 0, self.plotter.renderer)
            group = self._actor_to_group.get(self._picker.GetActor())
            self._set_hover_group(group)
        elif mode == "join":
            self._hover_edge_at(event)
        else:
            self._set_hover_group(None)
            self._set_hover_connection(None)

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

    def _nearest_connection_at_position(self, pos):
        """The builder connection id whose cached 3D seam segments
        (self._connection_edge_cache) come closest to world point `pos`, within
        CONNECTION_PICK_TOLERANCE_FRACTION * self._half -- or None if nothing's close enough
        (including simply because `pos` is None, no surface under the cursor at all). There's
        no dedicated pickable actor per connection (unlike a base face's own mesh actor,
        _actor_to_group) -- a connection's seam is a thin line lying exactly on the already-
        picked surface, not a separate 3D object of its own, so proximity-to-the-pick-point
        is used instead of a second vtkCellPicker pass."""
        if pos is None or not self._connection_edge_cache:
            return None
        tolerance = CONNECTION_PICK_TOLERANCE_FRACTION * self._half
        best_id, best_dist = None, tolerance
        for conn_id, segments in self._connection_edge_cache.items():
            for i in range(0, len(segments), 2):
                dist = _point_segment_distance_3d(pos, segments[i], segments[i + 1])
                if dist < best_dist:
                    best_id, best_dist = conn_id, dist
        return best_id

    def _nearest_open_edge_at_position(self, pos, exclude_shape_id=None):
        """The (shape_id, raw_edge) key in self._open_edges whose own segments come closest to
        world point `pos`, within OPEN_EDGE_PICK_TOLERANCE_FRACTION * self._half -- or None if
        nothing's close enough (including `pos is None`). Point-to-SEGMENT distance against the
        edge's own actual (possibly subdivided) geometry, not just its midpoint -- matches
        "hovering over open edges" being the trigger (2026-09-19, explicit), not just their
        midpoint specifically; same convention _nearest_connection_at_position already uses for
        an EXISTING connection's own seam. `exclude_shape_id` drops one shape's own edges from
        consideration -- used while dragging OUT of a shape's edge, since Join mode never
        connects a shape to itself (that's Fold's job)."""
        if pos is None or not self._open_edges:
            return None
        tolerance = OPEN_EDGE_PICK_TOLERANCE_FRACTION * self._half
        best_key, best_dist = None, tolerance
        for key, info in self._open_edges.items():
            if exclude_shape_id is not None and info["shape_id"] == exclude_shape_id:
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

    def _hover_edge_at(self, event):
        """Join-mode 3D hover: an in-progress drag reads its own live target instead
        (_update_connection_drag); otherwise picks whichever's closer between an EXISTING
        connection's seam (for selecting it, _nearest_connection_at_position) and an OPEN
        edge (for starting a NEW one, _nearest_open_edge_at_position) -- an edge is always
        exactly one or the other, never both, so there's no real ambiguity, just two
        independent lookups against the same pick position. Locked (an inflate is running)
        suppresses the open-edge side entirely, matching _on_canvas_press_join's own lock check
        on the 2D side -- both are how this app blocks starting a NEW connection mid-computation
        (an EXISTING connection's hover/select stays read-only and harmless throughout)."""
        if self._connection_drag is not None:
            self._update_connection_drag(event)
            return
        pos = self._pick_world_position(event)
        self._set_hover_connection(self._nearest_connection_at_position(pos))
        if self.builder_getter()._locked:
            self._set_hover_open_edge(None)
        else:
            self._set_hover_open_edge(self._nearest_open_edge_at_position(pos))

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
        same as InteractiveBuilderApp letting a click-click connection lapse."""
        drag, self._connection_drag = self._connection_drag, None
        self._line_end_screen_override = None
        self.builder_getter().set_pending_connection(None, None, None, None)
        origin = None if drag is None else self._open_edges.get(drag["origin_key"])
        target = (None if drag is None or drag["target_key"] is None
                  else self._open_edges.get(drag["target_key"]))
        if origin is not None and target is not None:
            self.builder_getter().create_connection(
                origin["shape_id"], origin["raw_edge"], target["shape_id"], target["raw_edge"])
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
        else:
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

    def _shape_id_of_group(self, group):
        if (group is not None and self._pending_source_polygon_id is not None
                and group < len(self._pending_source_polygon_id)):
            return self._pending_source_polygon_id[group]
        return None

    def _groups_for_shape_ids(self, shape_ids):
        """Every 3D group whose own source_polygon_id is one of `shape_ids` -- usually one
        group per shape_id, but a Polygon-Fold shape's several triangle groups all share one
        source_polygon_id, so this can return more entries than `shape_ids` has."""
        if not shape_ids or self._pending_source_polygon_id is None:
            return set()
        return {g for g, sid in enumerate(self._pending_source_polygon_id) if sid in shape_ids}

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
        one, so the highlight shows up whichever side of that face is currently being viewed."""
        self._hover_target_groups = frozenset(groups)
        effective = self._hover_target_groups - self._groups_for_shape_ids(self._selected_shape_ids)
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
        selects it in both 2d and 3d"): Move selects a whole face (_click_select_face); Join
        selects the nearest connection seam (_click_select_edge); any other mode (Fold) does
        nothing here, since neither gesture applies there."""
        if not self._actor_to_group:
            return
        mode = self.builder_getter().tool_mode
        if mode == "move":
            self._click_select_face(event)
        elif mode == "join":
            self._click_select_edge(event)

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
        """Selects whichever connection's seam is nearest the cursor (2026-09-19, explicit:
        "multiselect is not available in this mode" -- always REPLACES the selection, no Ctrl-
        toggle at all, unlike face selection in Move mode). Clicking somewhere with no seam
        within CONNECTION_PICK_TOLERANCE_FRACTION clears the selection, same as clicking empty
        space in Move mode."""
        self._select_connection(self._nearest_connection_at_position(self._pick_world_position(event)))

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
        one that just got deselected while still under the cursor needs them back."""
        for actor in self._selected_actors:
            self.plotter.remove_actor(actor)
        self._selected_actors = []
        for group in self._groups_for_shape_ids(self._selected_shape_ids):
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
        keeps VTK's default flat line ends."""
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

    def _connection_edge_segments(self, a_shape_id, b_shape_id):
        """Best-effort 3D geometry for a Join-mode connection between shapes `a_shape_id` and
        `b_shape_id`: every fine-mesh segment that's a boundary edge of BOTH shapes' own 3D
        group(s) at once, i.e. wherever the two shapes' currently-displayed patches are glued
        together. Empty (no 3D highlight, 2D still works fine on its own) when: `a_shape_id ==
        b_shape_id` (a Polygon-Fold self-connection glues two edges of the SAME shape, so a
        boundary-intersection can't tell its seam apart from that shape's own ordinary outer
        rim -- out of scope here); either shape isn't currently in the displayed mesh at all
        (net edited since the last Inflate); or -- a known limitation -- there's more than one
        connection between this exact pair of shapes, in which case every one of their shared
        seams comes back together, undistinguished, since this only looks at the SHAPE pair,
        not which specific edge a particular connection glues."""
        if a_shape_id is None or b_shape_id is None or a_shape_id == b_shape_id:
            return np.empty((0, 3))
        a_edges, b_edges = set(), set()
        for group in self._groups_for_shape_ids({a_shape_id}):
            a_edges |= self._group_boundary_edge_set(group)
        for group in self._groups_for_shape_ids({b_shape_id}):
            b_edges |= self._group_boundary_edge_set(group)
        shared = a_edges & b_edges
        segments = np.empty((2 * len(shared), 3))
        for i, (u, v) in enumerate(shared):
            segments[2 * i] = self.positions[u]
            segments[2 * i + 1] = self.positions[v]
        return segments

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
        """(front_segs, back_segs) -- every boundary edge of `group`, nudged a hair along its
        own owning triangle's outward normal (front) or the opposite way (back), so the two
        copies don't Z-fight when drawn co-located on the real surface. Used for BOTH the
        ordinary polygon-rim overlay and the yellow hover highlight (_render/_set_hover_group)
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
        front_pairs, back_pairs = [], []
        for (u, v), (ta, tb, tc) in boundary:
            pa, pb, pc = self.positions[ta], self.positions[tb], self.positions[tc]
            normal = np.cross(pb - pa, pc - pa)
            length = np.linalg.norm(normal)
            offset = (normal / length * nudge) if length > 1e-12 else np.zeros(3)
            # NOT named `pv` -- that would shadow the module-level `pyvista as pv` import (bit
            # us once already in the sibling ribbon method this replaced).
            p_u, p_v = self.positions[u], self.positions[v]
            front_pairs.append((p_u + offset, p_v + offset))
            back_pairs.append((p_u - offset, p_v - offset))

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
        (n = that base face's own vertex count), the SAME fixed per-shape-type color the left
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
            conn["id"]: self._connection_edge_segments(conn["a_shape"], conn["b_shape"])
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
                n = len(self.base_faces[group])
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
                    line_width=SUBDIVISION_EDGE_LINE_WIDTH, culling="back")
                inside_actor = plotter.add_mesh(
                    mesh, color=inside_color, show_edges=True,
                    # Blended from inside_color (the actor's OWN fill color) toward WHITE --
                    # same idea as the outside edges, just off the darker inside fill color
                    # instead of the bright outward one (2026-09-19, explicit: "backside lines
                    # should be 85% backside face color and 15% white").
                    edge_color=_weighted_color(inside_color, BACK_EDGE_WEIGHT),
                    line_width=SUBDIVISION_EDGE_LINE_WIDTH, culling="front")
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

    def on_full_inflate_clicked(self):
        """Reads the LEFT pane's current net, then runs the full Level 0->1->2->3 auto-pipeline
        (fan-triangulate -> Relax -> calibrate/Inflate to target RMS -> Subdivide -> repeat) --
        the same sequence inflate_polyhedron_app's "Run Simulation" runs, redrawing this ONE
        panel in place at each step instead of four side-by-side panels. Always enabled, always
        starts completely from scratch (2026-09-19, explicit) -- contrast Diff Inflate
        (on_diff_inflate_clicked), which reuses the last completed inflate's own Level-3
        result. A no-op while already running."""
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
        self.base_faces = faces
        self.base_edges = base_edges
        self.base_face_edge_ids = face_edge_ids
        self._pending_source_polygon_id = mesh.get("source_polygon_id")
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
        self._set_status("Level 0: relaxing...", "info")
        self._run_background(
            lambda queue_progress: relax_initial_configuration(
                self.positions, self.faces, self.edge_length,
                max_nfev=SAFETY_STEP_CAP, gtol=self._get_tolerance(), rng=None,
                on_progress=None, edges=self.edges, stop_event=self._stop_event),
            self._on_relax_done)

    def _on_relax_done(self, result):
        if self._stop_requested:
            self._revert_run("Stopped -- reverted to the state before Inflate.")
            return
        positions, _steps, max_stretch, rms_stretch, _optimality, converged = result
        if not converged:
            self._revert_run(
                f"Level 0 relax didn't converge within {SAFETY_STEP_CAP} steps -- reverted to "
                "the state before Inflate.",
                popup_text=(
                    f"The mesh didn't converge (max stretch {max_stretch:.1f}%, RMS "
                    f"{rms_stretch:.1f}% after {SAFETY_STEP_CAP} steps) -- it may have a "
                    "loosely-attached or floppy face. Try anchoring/reconnecting it and "
                    "Inflate again."))
            return
        self.positions = positions
        self._render()
        self.subdivision_level = 1
        self._set_status(
            f"Level 0 relaxed (RMS {rms_stretch:.1f}%). Inflating Level 1...", "info")
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
                capture_frames=False, on_progress=queue_progress,
                edges=self.edges if self.subdivision_level == 1 else None,
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
                stop_event=self._stop_event, **extra),
            self._on_inflate_step_done,
            on_progress=lambda steps: self._set_status(
                f"Level {self.subdivision_level}: calibrating pressure toward "
                f"{target_rms_pct:.0f}% RMS stretch ({steps} steps so far)...", "info"))

    def _on_inflate_step_done(self, result):
        if self._stop_requested:
            self._revert_run("Stopped -- reverted to the state before Inflate.")
            return
        # capture_frames=False (see on_full_inflate_clicked's own call) -- 8 values, no frames list.
        (pressure, new_positions, _steps, max_stretch, rms_stretch,
         _optimality, converged, pressure_found) = result
        if not pressure_found:
            self._revert_run(
                f"Level {self.subdivision_level}: mesh didn't respond to pressure -- reverted "
                "to the state before Inflate.",
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
                f"Level {self.subdivision_level}: pressure {pressure:.2f} didn't converge -- "
                "reverted to the state before Inflate.",
                popup_text=(
                    f"The mesh didn't converge at Level {self.subdivision_level} (pressure "
                    f"{pressure:.2f}, max stretch {max_stretch:.1f}%, RMS {rms_stretch:.1f}%) "
                    "-- it may have a loosely-attached or floppy face. Try anchoring/"
                    "reconnecting it and Inflate again."))
            return
        self.positions = new_positions
        self._render()
        # Feeds _guess_pressure_from_history for whichever level runs next this SAME Full
        # Inflate pass (harmless to also record during a Diff Inflate run -- nothing reads
        # self.level_history there, since those callers pass their own explicit guess).
        self.level_history[self.subdivision_level] = {
            "pressure": pressure, "rms_stretch_pct": rms_stretch, "pressure_found": pressure_found}
        if self.subdivision_level >= MAX_LEVEL:
            self.last_pressure = pressure
            self._record_inflate_success()
            self._pre_click_snapshot = None
            self._stop_event = None
            self._set_running(False)
            self._set_status(
                f"Done -- Level {MAX_LEVEL}, pressure {pressure:.2f}, RMS stretch "
                f"{rms_stretch:.1f}% (max {max_stretch:.2f}%).", "success")
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
            f"Subdivided to level {self.subdivision_level}. Inflating...", "info")
        self._run_inflate_step()

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
        pipeline the way source_polygon_id is). Deliberately does NOT clear
        self._pending_source_polygon_id afterward -- it doubles as "the source_polygon_id
        parallel to self.base_faces RIGHT NOW" (every pipeline path sets both together, see
        each one's own assignment), which hover picking (_set_hover_group) needs available
        even for a mesh that's currently displayed but not yet (or never) successfully
        recorded."""
        builder = self.builder_getter()
        self.last_shapes_snapshot, self.last_connections_snapshot = builder.snapshot_state()
        self.last_source_polygon_id = self._pending_source_polygon_id
        self.last_root_to_vertex_id = builder.root_to_vertex_id()

    # ---- diff inflate ----

    def on_diff_inflate_clicked(self):
        """Only meaningful once refresh_diff_eligibility has already enabled this button (an
        "add_face"/"remove_face"/"add_connection"/"remove_connection" change since the last
        completed inflate -- see BuilderPane.classify_change) -- re-classifies once more here
        regardless, as a safety net against a stale enabled state (e.g. a builder edit landing
        between the button's last refresh and this click), and tells the user to use Full
        Inflate instead if that's no longer true. A no-op while already running."""
        if self._running:
            return
        builder = self.builder_getter()
        kind, extra = builder.classify_change(
            self.last_shapes_snapshot, self.last_connections_snapshot)
        if kind == "add_face":
            self._diff_add_face(extra)
        elif kind == "remove_face":
            self._diff_remove_face(extra)
        elif kind == "add_connection":
            self._diff_connection_change("added a connection")
        elif kind == "remove_connection":
            self._diff_connection_change("removed a connection")
        else:
            messagebox.showerror(
                "Cannot Diff Inflate",
                "The net has changed by more than a single added face/connection, or more than "
                "one removed face/connection, since the last Inflate -- use Full Inflate "
                "instead.")

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
        their own vertex/edge sets purely from `faces`, see stretchy_mesh._edge_setup). Then
        runs ONE pressure-calibration pass at Level 3 (_run_inflate_step, already naturally a
        single pass whenever self.subdivision_level == MAX_LEVEL going in)."""
        removed_idxs = {i for i, spid in enumerate(self.last_source_polygon_id) if spid in shape_ids}
        keep_base_idxs = [i for i in range(len(self.base_faces)) if i not in removed_idxs]
        if not keep_base_idxs:
            messagebox.showerror("Cannot Diff Inflate", "That was the last face -- nothing left to inflate.")
            return
        old_to_new_base = {old_i: new_i for new_i, old_i in enumerate(keep_base_idxs)}

        self._pre_click_snapshot = self._snapshot_mesh_state()
        self._stop_event = threading.Event()
        self._stop_requested = False

        self.base_faces = [self.base_faces[i] for i in keep_base_idxs]
        if self.base_face_edge_ids is not None:
            self.base_face_edge_ids = [self.base_face_edge_ids[i] for i in keep_base_idxs]
        pending_source_polygon_id = [self.last_source_polygon_id[i] for i in keep_base_idxs]
        remaining_base_vertex_ids = {v for f in self.base_faces for v in f}
        if self.base_edges is not None:
            self.base_edges = [e for e in self.base_edges if e[0] in remaining_base_vertex_ids
                                and e[1] in remaining_base_vertex_ids]

        keep_fine = [i for i, bf in enumerate(self.face_of_fine) if bf not in removed_idxs]
        self.faces = [self.faces[i] for i in keep_fine]
        self.face_of_fine = [old_to_new_base[self.face_of_fine[i]] for i in keep_fine]
        self.edges = None
        self.subdivision_level = MAX_LEVEL
        self._pending_source_polygon_id = pending_source_polygon_id
        # Deliberately no self._render() here -- the mesh with the face just cut out hasn't
        # been recalibrated yet, so it's not a state worth showing (2026-09-19, explicit:
        # "never redraw anything" before real convergence) -- if it never converges,
        # _revert_run puts the panel straight back to self._pre_click_snapshot instead.
        self._set_running(True, active="diff")
        face_word = "a face" if len(shape_ids) == 1 else f"{len(shape_ids)} faces"
        self._set_status(
            f"Diff Inflate: removed {face_word}, calibrating pressure at Level {MAX_LEVEL}...", "info")
        self._run_inflate_step(initial_pressure_guess=self.last_pressure,
                                tol_pct=DIFF_PRESSURE_GUESS_TOL_PCT)

    def _diff_add_face(self, _shape_id):
        """A new shape's own added-and-connected face(s) -- handled by the same general
        re-export-and-root-match-seed path as a connection add/remove (see
        _diff_reexport_and_relax); the shape id itself isn't needed there (root-matching finds
        automatically that this shape's own corners have no prior root, and BFS-seeds them near
        whatever they got connected to)."""
        self._diff_reexport_and_relax("Diff Inflate: added a face")

    def _diff_connection_change(self, verb_phrase):
        self._diff_reexport_and_relax(f"Diff Inflate: {verb_phrase}")

    def _diff_reexport_and_relax(self, status_verb_phrase):
        """Shared by _diff_add_face/_diff_connection_change (see module docstring's "Full
        Inflate vs. Diff Inflate" section) -- re-exports the FULL current net, seeds the fresh
        base mesh's own Level-0 positions by matching each vertex's STABLE root identity
        (BuilderPane.root_to_vertex_id, comparable across exports even when a connection
        add/remove has MERGED or SPLIT vertex groups and shifted raw integer ids -- unlike
        appending one new shape, which never renumbers anything else, a connection edit can
        renumber vertices anywhere after the affected group in traversal order, so a plain
        `self.positions[v]` id lookup isn't safe here the way it was for _diff_remove_face's
        pure filtering) against self.last_root_to_vertex_id (the SAME map from the last
        completed inflate), falling back to a neighbor-BFS fill (_seed_unknown_by_bfs) for any
        vertex with no matching old root (a genuinely new shape's own corners, or one half of a
        just-split connection), subdivides straight to Level 3 as pure interpolation
        (_subdivide_combined_to_level3 -- no solving), then runs ONE pressure-calibration pass
        at Level 3."""
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

        self._pre_click_snapshot = self._snapshot_mesh_state()
        self._stop_event = threading.Event()
        self._stop_requested = False

        seed = {}
        old_roots = self.last_root_to_vertex_id or {}
        for root, new_id in new_root_to_id.items():
            old_id = old_roots.get(root)
            if old_id is not None and old_id in self.positions:
                seed[new_id] = self.positions[old_id]
        rng = np.random.default_rng(0)
        _seed_unknown_by_bfs(new_base_faces, seed, rng)

        self.base_faces = new_base_faces
        self.base_edges = new_base_edges
        self.base_face_edge_ids = new_face_edge_ids
        self._pending_source_polygon_id = source_polygon_id
        self.faces, self.positions, self.edge_length, self.face_of_fine = \
            _subdivide_combined_to_level3(new_base_faces, new_face_edge_ids, seed)
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
        self._set_status(f"{status_verb_phrase}, calibrating pressure at Level {MAX_LEVEL}...", "info")
        self._run_inflate_step(initial_pressure_guess=self.last_pressure,
                                tol_pct=DIFF_PRESSURE_GUESS_TOL_PCT)

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
        root.title("Interactive Inflater")
        # Smaller than this app's earlier 1500x900 (2026-09-19, explicit: "the window is too
        # big... make it smaller like the size of the polyhedron_inflater") -- close to that
        # sibling app's own ~1629x880, but this window also needs to fit a full builder pane
        # alongside the inflater, so slightly narrower/shorter than a literal match would be.
        root.geometry("1280x760")
        root.minsize(900, 560)

        sv_ttk.set_theme("dark")
        _scale_ui_fonts_once(root)
        self._build_menu(root)

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
        # Inflate is clicked.
        self.builder.on_change = self.inflater.refresh_diff_eligibility
        # Reverse hover direction (2026-09-19, explicit) -- BuilderPane's own mouse hover
        # forwards to InflaterPane.set_hover_shape_from_builder via this, mirroring
        # InflaterPane's builder_getter above.
        self.builder.inflater_getter = lambda: self.inflater
        # 2026-09-19, explicit: "if auto inflate is enabled, as soon as i load a file, it
        # should also inflate" -- a fresh Load has no relation to whatever was inflated before
        # (if anything), so this always means a FULL Inflate, never a diff.
        self.builder.on_load_success = self.inflater.on_load_success

    def _build_menu(self, root):
        """A File menu with just Load... (no New/Save/Save As -- this app has no window-level
        concept of "the current file" to Save back to, and Save isn't offered yet at all,
        2026-09-19, explicit) -- replaces the earlier plain toolbar button so Load lives where
        a user expects file operations to be. Same explicit-color kwargs as
        interactive_builder_app's own _build_menu (MENU_BG/MENU_FG/etc, imported, not
        duplicated) so this matches that app's look."""
        menu_kwargs = dict(bg=MENU_BG, fg=MENU_FG, activebackground=MENU_ACTIVE_BG,
                            activeforeground=MENU_FG, disabledforeground=MENU_DISABLED_FG)
        menubar = tk.Menu(root, **menu_kwargs)
        file_menu = tk.Menu(menubar, tearoff=False, **menu_kwargs)
        file_menu.add_command(label="Load...", command=lambda: self.builder.on_load_clicked())
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
