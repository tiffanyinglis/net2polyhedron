"""
Inflate Polyhedron -- interactive fabric relaxation for stretchy meshes.

    python src/apps/inflate_polyhedron_app/app.py

Nets (data/input/stretchy_nets/*.json or *.poly, see refresh_net_list) are vertex loops --
shared vertex ids ARE the adjacency, so a face pair sharing several edges needs no special
casing (see utils/inflate_polyhedron/stretchy_mesh.py's module docstring). Full pipeline
detail (force model, calibration, convergence) lives in physics.md; UI wiring detail lives
in apps.md -- keep both in sync when changing behavior described here. Summary:

1. On selecting a net, its BASE faces are fan-triangulated (Level 0/1's shared topology,
   see mesh_levels.subdivide_once) and given a fresh random start.
2. "Relax" (Level 0 only) runs pure-spring relaxation to convergence, then promotes straight
   into Level 1's starting position -- a tangled result is possible and left for Inflate to
   resolve.
3. "Subdivide" (up to MAX_LEVEL) quarters every triangle; new positions interpolate from the
   current mesh, new rest lengths derive from the original flat geometry so the target shape
   stays fixed across levels.
4. "Inflate" (Level 1+) calibrates a pressure toward the current level's "Target RMS stretch"
   spinner (self.target_rms_vars, defaults LEVEL_DEFAULT_TARGET_RMS_PCT, independently
   user-editable) via estimate_pressure_for_target_stretch. The winning trial's own result IS
   the Inflate outcome (no separate re-run at the found pressure) and is topped up to real
   convergence if the search's own step budget cut it off first. Frames captured during the
   winning trial are replayed at REPLAY_FPS once found; "Steps" advances with the real
   computation, not the replay. See apps.md for the full click/replay/UI sequencing.
5. "Convergence History" records one row per level visited: pressure, steps, stretch stats,
   and a combined "Convergence" cell (`optimality` vs. `gtol`, generic about what optimality
   measures since it just mirrors whatever stretchy_mesh reports).
6. Layout: "Net" panel (flat, matplotlib) plus one 3D panel per level via PyVista/VTK (a real
   GPU depth buffer, needed because meshes here are routinely self-intersecting/non-convex,
   which matplotlib's painter's-algorithm sort can't draw correctly). Level 0 and Levels 1-3
   have independent camera groups (rotation/zoom/pan) since they look very different; the Net
   panel's own zoom/pan are separate again (different rendering stack). See apps.md for pan/
   zoom/camera mechanics.
7. Debug mode ("d" key) adds "Validate Mesh" (purely combinatorial winding check) and normal-
   arrow toggles (face/vertex) for visually checking orientation -- see apps.md.
8. "Auto" runs the whole pipeline unattended (Relax, then Inflate/Subdivide/... to MAX_LEVEL),
   exactly one attempt per level, no retries -- see apps.md/physics.md.
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
if str(_APPS_DIR) not in sys.path:
    sys.path.insert(0, str(_APPS_DIR))

import glob
import json
import math
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont

import numpy as np
from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import pyvista as pv
import sv_ttk

from common.paths import STRETCHY_NETS_DIR, DATA_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS
from utils.inflate_polyhedron.stretchy_mesh import (
    load_stretchy_mesh, load_stretchy_mesh_edges, relax_once, relax_initial_configuration,
    random_initial_positions, estimate_pressure_for_target_stretch, mesh_edges, EDGE_LENGTH,
    CONVERGENCE_GTOL,
)
from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.subdivisions.mesh_subdivide import load_fabric_spec
from utils.inflate_polyhedron.stretchy_net_layout import build_stretchy_net_layout
from utils.geometry.polygon_geom import regular_polygon_vertices, apply_rigid

from session_state import (
    SessionStateModel, LevelStateModel, LevelHistoryRecordModel, LastStatsModel,
)

DEFAULT_NET_BASENAME = "cube"

# Window title (_apply_mode_visibility) backronym; ".hippo" was named first (SESSION_FILE_
# EXTENSION, below), this is what it stands for.
APP_TITLE = "HIPPO — Hierarchical Inflatable Phabric Polyhedron Optimizer"

# File > Save/Load's default directory for a whole SESSION -- deliberately not
# STRETCHY_NETS_DIR, since a saved session is a generated artifact, not an input.
SESSION_OUTPUT_DIR = DATA_DIR / "output"
# Still plain JSON content (SessionStateModel.model_dump_json) -- distinct extension so a
# saved session reads as this app's own file type, not an ordinary net .json.
SESSION_FILE_EXTENSION = ".hippo"

# Fine mesh edges drawn thin so subdivision reads as texture, not a bold wireframe competing
# with per-coarse-face coloring.
SUBDIVISION_EDGE_WIDTH = 0.5


def _midpoint_color(color_a, color_b):
    """RGB midpoint of two matplotlib-recognized colors, as an (r, g, b) tuple in [0, 1] --
    used for each "Level N" panel's wireframe edge color, halfway between white and that
    face's own fill color."""
    a, b = np.array(mcolors.to_rgb(color_a)), np.array(mcolors.to_rgb(color_b))
    return tuple((a + b) / 2)


# A face's INSIDE (its backface, as seen through the mesh) is drawn this fraction darker than
# its own outward-facing color (_draw_level_panel's own add_mesh backface_params) -- lets a
# user tell outside from inside at a glance (2026-09-19, explicit: "i'd like the inside of the
# polygon face to be a shade dark[er] than the outside").
INSIDE_FACE_DARKEN_FACTOR = 0.65


def _darken_color(color, factor=INSIDE_FACE_DARKEN_FACTOR):
    """`color` scaled toward black by `factor` (an (r, g, b) tuple in [0, 1]) -- same
    matplotlib-recognized-color handling as _midpoint_color."""
    return tuple(np.array(mcolors.to_rgb(color)) * factor)


def _vertex_normals(faces, positions):
    """faces: triangle vertex-id loops; positions: {vertex_id: pos}.
    Returns {vertex_id: (unit_normal, mean_incident_edge_length)} for "Show vertex normals"
    (_draw_level_panel) -- every vertex touched by at least one non-degenerate face.
    `unit_normal` is the NORMALIZED SUM of every incident face's unit normal, each face
    weighted equally (not by area) -- shows "which way do my own faces agree this vertex
    points" (surfaces a fold/inconsistency a per-face check alone would miss), rather than
    approximating a smooth surface normal. `mean_incident_edge_length` scales the drawn
    segment the same "about half an edge" way face normals are. A vertex whose incident
    faces cancel exactly, or that has no non-degenerate incident face, is omitted."""
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

# Net panel's own bezier connection curves (interactive_builder_app's gluing between two
# faces' edges), shown read-only for context -- solid white for contrast against every
# per-face color, drawn above every face patch/subdivision overlay so it always reads on top.
CONNECTION_CURVE_COLOR = "white"
CONNECTION_CURVE_WIDTH = 1.0
CONNECTION_CURVE_ZORDER = 5

# Convergence History's "running" row tag -- own dedicated bright color, not
# STATUS_COLORS["warn"] (tuned for warning text elsewhere, too muddy for a row highlight).
RUNNING_ROW_COLOR = "#e0b400"

# Every "Level N" panel renders via PyVista/VTK, not matplotlib (see _build_level_pv_panel)
# -- a real GPU depth buffer, needed because meshes here are routinely self-intersecting/
# non-convex (mid-relax, mid-inflate, or Level 0's own random-start), which neither
# mplot3d's painter's-algorithm depth sort nor a convexity-only culling approach can draw
# correctly. Pixel size matches the Net panel's own matplotlib figsize*dpi so every panel is
# the same size as its neighbors (Level 0 excepted, below).
NET_PANEL_SIZE = (320, 450)
# Level 0's panel is 60% of Levels 1-3's own width -- the freed width is split evenly across
# Levels 1-3 instead. Height unchanged for every panel; `_level_panel_size(level)` returns
# the right (width, height) pair.
LEVEL_PANEL_HEIGHT = 450
LEVEL_PANEL_WIDTH_LEVEL_0 = round(320 * 0.6)
LEVEL_PANEL_WIDTH_LEVELS_1_3 = round(320 + (320 - LEVEL_PANEL_WIDTH_LEVEL_0) / 3)


def _level_panel_size(level):
    """(width, height) for `level`'s own panel -- see LEVEL_PANEL_WIDTH_LEVEL_0/_LEVELS_1_3."""
    width = LEVEL_PANEL_WIDTH_LEVEL_0 if level == 0 else LEVEL_PANEL_WIDTH_LEVELS_1_3
    return (width, LEVEL_PANEL_HEIGHT)


# Fraction of the panel the shape's own bounding box fills at zoom=1.0 (1.0 would touch the
# panel edge exactly). Level 0 and Levels 1-3 both fill the same 90% of their own
# (differently-sized) panels.
LEVEL_ZOOM_FILL_LEVEL_0 = 0.9
LEVEL_ZOOM_FILL_LEVELS_1_3 = 0.90


def _level_zoom_fill(level):
    """LEVEL_ZOOM_FILL_LEVEL_0 for level 0, LEVEL_ZOOM_FILL_LEVELS_1_3 for every other level."""
    return LEVEL_ZOOM_FILL_LEVEL_0 if level == 0 else LEVEL_ZOOM_FILL_LEVELS_1_3
# Initial camera angle -- arbitrary, a reasonable non-axis-aligned starting view (close to
# mplot3d's own default elev=30/azim=-60). Used once to build the initial quaternion
# (_initial_level_rotation) -- nothing decomposes back into separate angles afterward, which
# is what avoids gimbal lock.
LEVEL_DEFAULT_ELEV = 30.0
LEVEL_DEFAULT_AZIM = -60.0
# Degrees of camera rotation per pixel of click-drag -- tuned by feel.
LEVEL_DRAG_SENSITIVITY = 0.5
# Zoom multiplier per mouse-wheel notch -- >1 zooms in, so camera.parallel_scale is
# multiplied by its RECIPROCAL (smaller parallel_scale = smaller visible world height =
# zoomed in). Clamped to 30%..400% so scrolling can't shrink the shape to nothing or push it
# arbitrarily far away.
LEVEL_ZOOM_STEP = 1.1
LEVEL_ZOOM_MIN = 0.3
LEVEL_ZOOM_MAX = 4.0

# Same idea for the Net panel's own mouse-wheel zoom (_on_net_scroll) -- separate state
# (self.net_zoom) since the Net panel is matplotlib, not a PyVista camera: scales the
# half-extent _draw_target_faces derives from the flat layout's bounding box. NET_ZOOM_MAX
# is higher than the level panels' since the Net panel's bounding box includes every
# connection's bezier curve (see _draw_target_faces), which can sweep well past the faces.
NET_ZOOM_STEP = 1.1
NET_ZOOM_MIN = 0.3
NET_ZOOM_MAX = 8.0

# Overall UI text size multiplier, applied once at startup to every named Tk/ttk font
# (_scale_ui_fonts) so the whole app's text grows together.
UI_FONT_SCALE = 1.3

# Every panel's title ("Net", "Level N") is a plain Tkinter Label above its image, not text
# drawn inside the rendered scene (which a PyVista panel would clip against its own edge).
# Font can't be a plain module-level (family, size) tuple naming a Tk *named* font
# ("TkDefaultFont") -- Tk takes the name literally as a nonexistent family and silently
# falls back to Arial. Computed instead as self.LEVEL_TITLE_FONT at startup (_init_ui_fonts)
# from "Choose a net"'s own actual rendered font, so every title/message label genuinely
# matches it in family and size.

# Bottom-of-panel status message ("Computing...", "Replay frame N / M") is LEFT-justified
# (anchor=tk.W) with a per-message computed padx (_set_level_message, via a real tkfont.Font)
# rather than tk.CENTER or one fixed pad -- true centering re-anchors the whole string on
# every update (dot added, frame count digit count changes), and a single fixed pad tuned
# for one message length reads off-center for another. self.LEVEL_MESSAGE_FONT ==
# self.LEVEL_TITLE_FONT (see _init_ui_fonts).

# Shown on the Pressure readout before "Auto"/"Inflate" has ever calibrated one.
DEFAULT_PRESSURE = 3.0

DEFAULT_STEPS = 10

# This app's own default for the "Tolerance" spinner (self.tolerance_var) -- the `gtol`
# every relax_once/relax_initial_configuration/estimate_pressure_for_target_stretch call
# actually uses (self._current_gtol), distinct from stretchy_mesh.CONVERGENCE_GTOL (that
# module's own hardcoded default for a caller that passes no gtol at all). Tightened over
# time alongside stretchy_mesh's periodic (not per-step) convergence checking, which makes a
# tighter per-step-equivalent rate affordable.
DEFAULT_TOLERANCE = 1e-4

# Default value for each level's own "Target RMS stretch" spinner (self.target_rms_vars[level]
# -- one independent tk.DoubleVar per level). Tapered DOWN as level increases: a finer mesh
# approximates the same overall curvature with smaller stretch per edge (more, shorter edges
# bending through the same arc), so keeping these level-dependent holds the actual 3D target
# shape fixed across levels (matches mesh_levels.py's "target shape stays fixed as resolution
# increases" design). No entry for Level 0 -- it has no target RMS stretch at all
# (relax_initial_configuration is pure springs, not calibrated toward a target).
LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 80.0, 2: 40.0, 3: 10.0}

# Debug mode's "Show normals" toggle (_draw_level_panel) draws each triangle's own outward
# normal from its centroid, scaled to that triangle's own mean edge length -- distinct from
# every FACE_COLORS entry and PLOT_THEME's fg/edge color so it reads clearly against either.
NORMAL_COLOR = "yellow"
# "Show vertex normals" toggle's own color -- distinct from NORMAL_COLOR so a face normal and
# a vertex normal on the same panel (both toggles can be on at once) are never confused.
VERTEX_NORMAL_COLOR = "cyan"
# Normal segment length as a fraction of the triangle's (or vertex's own incident) mean edge
# length -- a full edge length reads too long against a dense/fine mesh. Shared by both
# "Show face normals" and "Show vertex normals".
NORMAL_LENGTH_FRACTION = 0.5

# Hard stop for "iterate until convergence" mode in case a mesh/pressure combination never
# reaches the current tolerance -- without this, a plateauing run would loop forever instead
# of settling for "as far as it got". Also the budget Auto gives its single non-converged
# attempt per level (no retry loop -- see physics.md's Auto section): recalibrating Inflate's
# pressure from scratch on retry was wasted work when the mesh just needed more time at the
# SAME pressure. Purely bounds a single uninterrupted relax_once/relax_initial_configuration
# call's own max_nfev in "iterate until convergence" mode (no app-side chunking anymore).
INFLATE_SAFETY_STEP_CAP = 50000


def _build_level1_topology(base_faces):
    """Level 0 and Level 1 share this exact fan-triangulated topology (see
    module docstring/mesh_levels' own docstring for why triangulating
    first matters for a spring-only relax) -- cheap enough (pure index
    math, no numerical solve) to compute synchronously on every net
    selection. Calls subdivide_once with placeholder positions purely to
    get the resulting faces/edge_length/face_of_fine; the interpolated
    positions it also returns are meaningless (every input point is the
    same placeholder) and discarded -- random_initial_positions supplies
    Level 0's real starting positions instead."""
    dummy_positions = {v: np.zeros(3) for face in base_faces for v in face}
    faces, _, edge_length, face_of_fine = subdivide_once(
        base_faces, dummy_positions, EDGE_LENGTH, list(range(len(base_faces))), 0)
    return faces, edge_length, face_of_fine


def _fan_level_edges(faces, base_edges):
    """faces: Level 0/1's own fan-triangulated mesh (_build_level1_topology); base_edges: the
    loaded net's own explicit "edges" field, or None (older file, or nothing to disambiguate --
    the plain mesh_edges vertex-pair fallback is then safe). Returns the explicit mesh-edge
    list for Level 0/1's relax/inflate calls, or None to mean "use the fallback".

    Fan triangulation never touches a base face's own RIM edges (see
    mesh_levels._fan_level_0_to_1) -- those stay exactly `base_edges`' own pairs, already
    correctly disambiguated. The only edges triangulation ADDS are SPOKES (rim vertex to a
    fresh centroid id), always globally unique, so deriving those the plain way is safe. This
    combines the two: `base_edges` as-is, plus every other edge of `faces` from mesh_edges."""
    if base_edges is None:
        return None
    base_vertex_ids = {v for e in base_edges for v in e}
    spokes = [e for e in mesh_edges(faces)
              if not (e[0] in base_vertex_ids and e[1] in base_vertex_ids)]
    return list(base_edges) + spokes


# interactive_builder_app's own DEFAULT_SHAPE_EDGE_LENGTH -- the edge length its "net_layout"
# section's saved cx/cy/rotation are expressed at (a Tkinter pixel scale, unrelated to this
# app's own EDGE_LENGTH=1.0 convention). Duplicated rather than imported -- a whole separate,
# unrelated Tkinter app (see docs/README.md).
_INTERACTIVE_BUILDER_EDGE_LENGTH = 70.0


def _layout_from_net_layout(faces, net_layout):
    """faces: vertex-id loops; net_layout: interactive_builder_app's own saved list of
    per-placed-shape placements. Returns {key: [2D point, ...]} -- the same shape
    build_stretchy_net_layout returns -- by reproducing each shape's saved rigid transform
    directly rather than re-deriving a layout via a fresh BFS spanning tree, since a BFS only
    follows the first shared edge it reaches an already-visited face through and silently
    drops any other edge-sharing (normal for a stretchy mesh) -- a net arranged in the
    interactive builder should show up here exactly as left.

    Two `net_layout` formats, matching interactive_builder_app's own _load_faces:
    - NEW (entry has "shape_id"/"n", written since Polygon Fold): `key` is "shape_id", polygon
      built at its own "n" sides directly -- `faces` isn't consulted (no longer 1:1 with
      placed shapes once a folded polygon's triangles are in it).
    - LEGACY (no "shape_id", one face per shape): `key` is the entry's list position `i`,
      "n" is `len(faces[i])`.

    Rigid transforms are scale-covariant, so reproducing the net at this app's own unit edge
    length is a uniform rescale by _INTERACTIVE_BUILDER_EDGE_LENGTH (build each polygon at
    edge_length=1, divide every saved cx/cy by 70).

    Also flips every point's Y sign (a whole-picture reflection, isometric so adjacency is
    preserved) to correct a real coordinate-convention mismatch: interactive_builder_app's
    Tkinter canvas has Y increasing downward, this panel's matplotlib axes have Y increasing
    upward -- without the flip the net renders as a vertical mirror image of what was built."""
    placed = {}
    for i, layout in enumerate(net_layout):
        key = layout.get("shape_id", i)
        n = layout.get("n", len(faces[i]) if i < len(faces) else 3)
        theta = layout["rotation"]
        c, s = np.cos(theta), np.sin(theta)
        R = np.array([[c, -s], [s, c]])
        t = np.array([layout["cx"], layout["cy"]]) / _INTERACTIVE_BUILDER_EDGE_LENGTH
        points = apply_rigid(regular_polygon_vertices(n), R, t)
        placed[key] = [np.array([p[0], -p[1]]) for p in points]
    return placed


def _net_layout_is_new_format(net_layout):
    """True iff `net_layout` is the post-Polygon-Fold, shape-id-keyed format rather than the
    legacy face-index-aligned one (see _layout_from_net_layout). Every entry is tagged the
    same way, so checking just the first is enough."""
    return bool(net_layout) and "shape_id" in net_layout[0]


def _face_colors_by_group(n_faces, source_polygon_id):
    """Returns (colors, color_by_group, group_of_face): `colors[i]` is face `i`'s color (flat
    list, same indexing as `base_faces`); `group_of_face[i]` is `source_polygon_id[i]`
    (interactive_builder_app's Polygon-Fold grouping) when given, else `i` itself (reduces to
    plain per-face coloring for a file without it); `color_by_group` is the same colors keyed
    by group id, for a caller (_draw_level_panel) grouping several base faces into one draw
    call. Every face sharing a group gets the same color; first-seen group order picks which
    FACE_COLORS entry each group gets."""
    group_of_face = [source_polygon_id[i] if source_polygon_id else i for i in range(n_faces)]
    color_by_group = {}
    colors = []
    for g in group_of_face:
        if g not in color_by_group:
            color_by_group[g] = FACE_COLORS[len(color_by_group) % len(FACE_COLORS)]
        colors.append(color_by_group[g])
    return colors, color_by_group, group_of_face


# interactive_builder_app's own bezier connection curves are drawn here too, in the Net panel
# (read-only -- shows the connection, not its handles): only _connection_curve_points/
# _draw_target_faces exist here, never the handle hit-testing/dragging machinery that app owns.

def _placed_edge_frame(points, edge_index):
    """Same construction as interactive_builder_app's own _shape_edge_frame -- (origin,
    tangent, normal) for one edge of an already-placed 2D polygon -- but over plain placed
    points, since this app has no "shape" object. The outward-normal test (perpendicular to
    the edge, flipped if it doesn't point away from the centroid) is chirality-agnostic, so
    it's correct whether `points` is a rotation of the original shape or a mirror image of it
    (as here, after _layout_from_net_layout's Y-flip)."""
    n = len(points)
    v1, v2 = points[edge_index], points[(edge_index + 1) % n]
    ox, oy = (v1[0] + v2[0]) / 2, (v1[1] + v2[1]) / 2
    tx, ty = v2[0] - v1[0], v2[1] - v1[1]
    length = math.hypot(tx, ty) or 1.0
    tx, ty = tx / length, ty / length
    nx, ny = -ty, tx
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    if (ox - cx) * nx + (oy - cy) * ny < 0:
        nx, ny = -nx, -ny
    return np.array([ox, oy]), np.array([tx, ty]), np.array([nx, ny])


def _cubic_bezier_points(p0, p1, p2, p3, steps=24):
    """Same sampling idea as interactive_builder_app's own _cubic_bezier_points (duplicated
    rather than imported, like _INTERACTIVE_BUILDER_EDGE_LENGTH), over numpy points instead
    of plain tuples since that's what this app's own target_layout already uses."""
    return [(1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
            for t in np.linspace(0.0, 1.0, steps + 1)]


def _connection_curve_points(target_layout, conn, steps=24):
    """The world-space points of one saved builder_connection's cubic bezier -- None if either
    referenced shape isn't in `target_layout` (a stale connection, not worth a crash over).
    `conn["a_shape_id"]/["b_shape_id"]` (new format) or `conn["a_face"]/["b_face"]` (legacy)
    key into `target_layout`. `conn["a_handle"]/["b_handle"]` are interactive_builder_app's own
    {"t", "n"} pixel-scale offsets -- rescaled by _INTERACTIVE_BUILDER_EDGE_LENGTH like every
    cx/cy, then applied against the tangent/normal frame recomputed from this app's own
    already-placed (rescaled + Y-flipped) points (_placed_edge_frame), which lands on the same
    point a transformed pre-image control point would since the Y-flip is a linear map."""
    a_key = conn["a_shape_id"] if "a_shape_id" in conn else conn["a_face"]
    b_key = conn["b_shape_id"] if "b_shape_id" in conn else conn["b_face"]
    a_points, b_points = target_layout.get(a_key), target_layout.get(b_key)
    if a_points is None or b_points is None:
        return None
    a_mid, a_tan, a_norm = _placed_edge_frame(a_points, conn["a_edge"])
    b_mid, b_tan, b_norm = _placed_edge_frame(b_points, conn["b_edge"])
    scale = _INTERACTIVE_BUILDER_EDGE_LENGTH
    # An older file's connection entry has no "a_handle"/"b_handle" -- defaults to
    # {"t": 0, "n": 0} (control point at the edge midpoint) rather than a KeyError.
    a_handle = conn.get("a_handle", {"t": 0.0, "n": 0.0})
    b_handle = conn.get("b_handle", {"t": 0.0, "n": 0.0})
    a_ctrl = a_mid + (a_handle["t"] / scale) * a_tan + (a_handle["n"] / scale) * a_norm
    b_ctrl = b_mid + (b_handle["t"] / scale) * b_tan + (b_handle["n"] / scale) * b_norm
    return _cubic_bezier_points(a_mid, a_ctrl, b_ctrl, b_mid, steps)


def _validate_mesh(faces):
    """Debug mode's "Validate Mesh" button: checks the CURRENTLY LOADED self.faces
    (post-subdivision, possibly finer than the file's own faces) for structural winding
    consistency. Pure function of `faces` alone (no Tk, no `positions`), independently
    testable. Returns (ok, lines); `lines` always covers the check, even when passing.

    Structural winding consistency (combinatorial, depends only on `faces`' vertex-id loops):
    if face A has an edge as v->w, any other face sharing that undirected edge must have it as
    w->v, never v->w again (this project's winding convention) -- exactly
    load_stretchy_mesh's "no directed edge appears more than once" rule, re-run here against
    the LIVE, possibly-subdivided mesh rather than just the raw file Load already checked.

    Deliberately reports only structure, nothing that varies with `positions` -- "does the
    CURRENT 3D shape look outward-facing" belongs to the separate "Show face normals" toggle
    instead."""
    counts = {}
    owners = {}
    for fi, face in enumerate(faces):
        n = len(face)
        for i in range(n):
            e = (face[i], face[(i + 1) % n])
            counts[e] = counts.get(e, 0) + 1
            owners.setdefault(e, []).append(fi)
    bad_faces = set()
    winding_lines = []
    for (v, w), c in counts.items():
        if c > 1:
            bad_faces.update(owners[(v, w)])
            winding_lines.append(
                f"  edge {v}->{w} runs the SAME direction in {c} faces {owners[(v, w)]} "
                f"(should be reversed in all but one)")
    ok = not winding_lines

    total = len(faces)
    if ok:
        lines = [f"PASS: all {total} faces are consistently oriented."]
    else:
        # bad_faces: every face touching at least one conflicting edge --
        # not just len(winding_lines) (a count of BAD EDGES, which can
        # differ from the number of faces those edges actually touch).
        lines = [f"FAIL: {len(bad_faces)}/{total} faces are inconsistently oriented."]
        lines += winding_lines
    return ok, lines


class InflatePolyhedronApp:
    def __init__(self, root):
        self.root = root
        # Wide enough for the Net panel + Level 0 + Levels 1..MAX_LEVEL (LEVEL_PANEL_WIDTH_
        # LEVELS_1_3 each -- not the same width as Level 0), plus view_frame's own left/right
        # padx=14 -- computed rather than a hardcoded literal, since every row here packs
        # content flush left, so a wider window would leave an uneven blank margin on the
        # right instead of fitting the content's natural width. Stays correct if MAX_LEVEL or
        # either panel width ever changes.
        # Tall enough for Setup + status + Convergence History + each panel's own title-Label-
        # plus-image-plus-button stack at their full natural size -- too short here silently
        # squeezes every image Label below its own panel height (Tk shrinks a packed widget to
        # whatever's left rather than erroring), cropping the bottom of every panel and
        # throwing off where mouse drags land on it.
        window_width = (NET_PANEL_SIZE[0] + LEVEL_PANEL_WIDTH_LEVEL_0
                        + LEVEL_PANEL_WIDTH_LEVELS_1_3 * MAX_LEVEL + 2 * 14)
        root.geometry(f"{window_width}x880")
        root.minsize(820, 600)

        sv_ttk.set_theme("dark")
        self._scale_ui_fonts()
        self._init_ui_fonts()
        self._build_menu()

        # ---- Debug mode vs. release mode: the ONLY difference between
        # them is whether "Iterate for N steps" is offered at all (see
        # the steps row below) -- release mode always drives straight to
        # convergence. Everything else (net/target Setup, one
        # Inflate/Subdivide button pair per level, always-synced
        # rotation, no separate Stop button, the green "Converged"
        # message suppressed) is shared and identical either way.
        # Release mode is what a session starts in (it's the one meant
        # for an actual user, not someone working on this app); "d"
        # toggles between them at any time -- bind_all so it fires
        # regardless of which widget currently has focus (there's no
        # free-text entry in this app for a stray "d" keystroke to
        # collide with).
        self.debug_mode = False
        self.root.bind_all("<KeyPress-d>", self._on_toggle_debug_mode)

        # ---- Setup: net picker + target RMS stretch + tolerance, all
        # tiled HORIZONTALLY in one row to save vertical space (an
        # earlier version stacked net picker and target RMS stretch on
        # their own separate rows), shared by both modes, plus (debug
        # mode only) the steps-vs-convergence choice/Validate Mesh/Show
        # normals row below it. ----
        setup_frame = ttk.LabelFrame(root, text="Setup", padding=12)
        setup_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(14, 8))

        setup_row = ttk.Frame(setup_frame)
        setup_row.pack(fill=tk.X)

        net_group = ttk.Frame(setup_row)
        net_group.pack(side=tk.LEFT)
        ttk.Label(net_group, text="Choose a net:").pack(side=tk.LEFT, padx=(0, 8))
        self.net_var = tk.StringVar()
        self.combo = ttk.Combobox(net_group, state="readonly", width=15,
                                   textvariable=self.net_var)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        target_group = ttk.Frame(setup_row)
        target_group.pack(side=tk.LEFT, padx=(96, 0))
        ttk.Label(target_group, text="Target RMS stretch:").pack(side=tk.LEFT, padx=(0, 4))
        # One independent spinner per level (1-3), not a single spinner reset on frontier
        # change, so every level's own target is visible/settable at once. Both a manual
        # Inflate click and "Auto" read self.target_rms_vars[self.subdivision_level].
        self.target_rms_vars = {}
        self.target_rms_display_vars = {}
        self.target_rms_spins = {}
        for level in (1, 2, 3):
            ttk.Label(target_group, text=f"Level {level}:").pack(side=tk.LEFT, padx=(20, 2))
            var = tk.DoubleVar(value=round(LEVEL_DEFAULT_TARGET_RMS_PCT[level]))
            # A "converged" verdict only applies to the target it was reached at -- editing
            # this level's own target while it's the current frontier means the pressure
            # hasn't been (re)calibrated for the new value, so the Inflate-gate needs to lift
            # (see _update_level_action_buttons). Editing a non-current level touches no gate.
            var.trace_add("write", lambda *_a, lv=level: self._on_target_rms_changed(lv))
            # `var` is the value read everywhere else (on_inflate_clicked, session save/load,
            # history table) -- unchanged by the entry's "%"-suffixed display below, which is
            # a pure presentation layer (self.target_rms_display_vars), never read elsewhere.
            var.trace_add("write", lambda *_a, lv=level: self._sync_target_rms_display(lv))
            self.target_rms_vars[level] = var

            # A plain Entry, not a Spinbox -- restricted to numeric-looking input as typed
            # (_register_numeric_entry, no exponent/decimal needed for a whole-number
            # percentage) and clamped into [0, 100] on commit (_commit_target_rms_entry), since
            # a Spinbox's from_/to_ only gates its up/down arrows, never free typing. Bound to
            # its own display StringVar, not `var` directly -- shows "N%" while unfocused and
            # the bare number while being edited (_begin_edit_target_rms); `_sync_target_rms_
            # display` keeps the StringVar in sync with `var` from any source.
            display_var = tk.StringVar(value=f"{var.get():.0f}%")
            self.target_rms_display_vars[level] = display_var
            spin = ttk.Entry(target_group, width=5, textvariable=display_var)
            self._register_numeric_entry(spin, allow_exponent=False, allow_decimal=False)
            spin.bind("<FocusIn>", lambda event, lv=level: self._begin_edit_target_rms(lv))
            spin.bind("<Return>", lambda event, lv=level: self._commit_target_rms_entry(lv))
            spin.bind("<FocusOut>", lambda event, lv=level: self._commit_target_rms_entry(lv))
            spin.pack(side=tk.LEFT)
            self.target_rms_spins[level] = spin
        # Pressure is not user-editable or separately displayed -- "Inflate" calibrates it
        # itself and it's already logged per level in the Convergence History table.
        self.pressure_value = DEFAULT_PRESSURE

        tolerance_group = ttk.Frame(setup_row)
        tolerance_group.pack(side=tk.LEFT, padx=(96, 0))
        ttk.Label(tolerance_group, text="Tolerance:").pack(side=tk.LEFT, padx=(0, 4))
        # The `gtol` every relax_once/relax_initial_configuration/estimate_pressure_for_
        # target_stretch call actually uses (self._current_gtol, set at the start of every
        # Relax/Inflate click via _get_tolerance) -- distinct from stretchy_mesh's own fixed
        # CONVERGENCE_GTOL. Same converged-gate rationale as target_rms_vars above: a changed
        # tolerance invalidates a past "converged" verdict. A `tk.StringVar` holding
        # scientific-notation text ("1e-03"), not a `tk.DoubleVar` -- a DoubleVar set
        # programmatically renders via Tcl's default float-to-string ("0.001") rather than
        # scientific notation. `_get_tolerance` parses it back to a float when needed.
        self.tolerance_var = tk.StringVar(value=f"{DEFAULT_TOLERANCE:.0e}")
        self.tolerance_var.trace_add("write", self._on_tolerance_changed)
        # A plain Entry, not a Spinbox, restricted to numeric-looking input as typed
        # (_register_numeric_entry, WITH exponent this time for scientific notation like
        # "1e-03"). No commit-time clamp (unlike target RMS) -- `_get_tolerance` falls back to
        # DEFAULT_TOLERANCE for anything unparseable.
        self.tolerance_spin = ttk.Entry(tolerance_group, width=10, textvariable=self.tolerance_var)
        self._register_numeric_entry(self.tolerance_spin, allow_exponent=True)
        self.tolerance_spin.pack(side=tk.LEFT)

        # "Auto": visible/usable in BOTH modes (unlike the debug-only row below) -- a scripted
        # sequence of the same Relax/Inflate/Subdivide actions a user could click by hand
        # (see on_auto_clicked/_auto_step).
        auto_group = ttk.Frame(setup_row)
        auto_group.pack(side=tk.LEFT, padx=(96, 0))
        self.auto_button = ttk.Button(auto_group, text="Run Simulation", command=self.on_auto_clicked)
        self.auto_button.pack(side=tk.LEFT)
        self.auto_button.state(["disabled"])  # no net loaded yet -- _update_auto_button syncs this

        # Debug-mode-only row: "Iterate for N steps" vs. "until convergence" plus
        # "Validate Mesh"/"Show normals" (diagnostics with no effect on the solve). Shown/
        # hidden by _apply_mode_visibility; both are forced back to release-mode defaults
        # whenever leaving debug mode, so release mode never shows a stray fixed-step
        # request or stale normals overlay.
        self.mode_row = ttk.Frame(setup_frame)
        self.iterate_mode_var = tk.StringVar(value="convergence")
        self.steps_radio = ttk.Radiobutton(self.mode_row, text="Iterate for", value="steps",
                                            variable=self.iterate_mode_var,
                                            command=self._update_mode_state)
        self.steps_radio.pack(side=tk.LEFT)
        self.steps_var = tk.IntVar(value=DEFAULT_STEPS)
        self.steps_spin = ttk.Spinbox(self.mode_row, from_=1, to=1000000, width=7,
                                       textvariable=self.steps_var)
        self.steps_spin.pack(side=tk.LEFT, padx=(4, 4))
        ttk.Label(self.mode_row, text="steps").pack(side=tk.LEFT, padx=(0, 18))
        self.convergence_radio = ttk.Radiobutton(self.mode_row, text="Iterate until convergence",
                                                  value="convergence",
                                                  variable=self.iterate_mode_var,
                                                  command=self._update_mode_state)
        self.convergence_radio.pack(side=tk.LEFT)
        ttk.Separator(self.mode_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=18)
        self.validate_button = ttk.Button(self.mode_row, text="Validate Mesh",
                                           command=self.on_validate_mesh_clicked)
        self.validate_button.pack(side=tk.LEFT, padx=(0, 18))
        self.show_normals_var = tk.BooleanVar(value=False)
        self.show_normals_check = ttk.Checkbutton(self.mode_row, text="Show face normals",
                                                    variable=self.show_normals_var,
                                                    command=self.draw)
        self.show_normals_check.pack(side=tk.LEFT)
        # Per-vertex normals -- a vertex between inconsistently-angled faces can have a
        # badly-behaved average direction even when every face normal looks fine. Separate
        # toggle/color from "Show face normals" so the two are never visually conflated.
        self.show_vertex_normals_var = tk.BooleanVar(value=False)
        self.show_vertex_normals_check = ttk.Checkbutton(
            self.mode_row, text="Show vertex normals",
            variable=self.show_vertex_normals_var, command=self.draw)
        self.show_vertex_normals_check.pack(side=tk.LEFT)

        # ---- Status (warning/error/progress message): debug-mode-only. ----
        self.status_frame = ttk.Frame(root)
        self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # ---- Convergence history: one row per subdivision level visited this session
        # (including Level 0), showing pressure ("--" for Level 0, which has none), steps
        # taken (self.iteration_count, reset on Subdivide/promotion), stretch stats (RMS shown
        # against the current Target RMS spinner), and a combined "Convergence" cell
        # (`optimality` vs. gtol, check/cross). height=MAX_LEVEL+1 (0..MAX_LEVEL) is the most
        # rows this table will ever hold. ----
        self.history_frame = ttk.LabelFrame(root, text="Convergence History", padding=12)
        self.history_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        # "max_stretch" is debug-mode-only, "simulation_time"/"cumulative_time" show in both
        # modes -- all three stay DEFINED here regardless of mode (_apply_mode_visibility
        # toggles Treeview's own `displaycolumns`), just shown/hidden.
        history_columns = ("level", "pressure", "steps", "max_stretch", "rms_stretch",
                            "simulation_time", "cumulative_time", "convergence")
        self.history_tree = ttk.Treeview(self.history_frame, columns=history_columns,
                                          show="headings", height=MAX_LEVEL + 1)
        # Per-column "weight" -- proportions (not fixed pixel widths), tuned to roughly what
        # each column's header/content needs relative to the others. _rescale_history_columns
        # (bound below to <Configure>, and called on every mode toggle) turns these into pixel
        # widths that always sum to the widget's current width, every column scaled by the
        # same factor -- ttk.Treeview's own stretch=True instead distributes leftover space
        # evenly per column regardless of configured width, which doesn't give proportional
        # scaling.
        self._history_column_weights = {
            "level": 70, "pressure": 100, "steps": 85, "max_stretch": 115,
            "rms_stretch": 150, "simulation_time": 145, "cumulative_time": 135,
            "convergence": 145,
        }
        for col, heading in (
                ("level", "Level"), ("pressure", "Pressure"), ("steps", "Steps"),
                ("max_stretch", "Max Stretch %"), ("rms_stretch", "RMS Stretch %"),
                ("simulation_time", "Simulation Time"), ("cumulative_time", "Cumulative Time"),
                ("convergence", "Convergence")):
            self.history_tree.heading(col, text=heading)
            # stretch=False -- widths are set explicitly/proportionally by
            # _rescale_history_columns instead; Tk's own stretch would fight that.
            self.history_tree.column(col, width=self._history_column_weights[col],
                                      stretch=False, anchor=tk.CENTER)
        self.history_tree.bind("<Configure>",
                                lambda event: self._rescale_history_columns(event.width))
        self._release_mode_history_columns = tuple(
            col for col in history_columns if col != "max_stretch")
        self.history_tree.config(displaycolumns=self._release_mode_history_columns)
        # ttk.Treeview can only color a whole ROW, not one cell -- the Convergence column's
        # check/cross comes with its whole row tinted to match.
        self.history_tree.tag_configure("converged", foreground=STATUS_COLORS["success"])
        self.history_tree.tag_configure("not_converged", foreground=STATUS_COLORS["error"])
        # A run actively in progress -- distinct from "not_converged": red is reserved for an
        # actual failure (step cap or Stop), not just "still going" (see _refresh_history_table).
        self.history_tree.tag_configure("running", foreground=RUNNING_ROW_COLOR)
        self.history_tree.pack(fill=tk.X)

        # ---- Net (flat layout, matplotlib) + one 3D panel per level (0..MAX_LEVEL, PyVista),
        # side by side. Each level panel is its own off-screen Plotter/Label pair so a native
        # Tkinter Inflate/Subdivide/Relax button can sit directly below it. Level N's panel is
        # LIVE only while self.subdivision_level == N; once the user moves past it, that
        # level's last state freezes into self.level_snapshots. ----
        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))

        # fill/expand=False here (unlike a plain pack default): each panel below is a
        # fixed-size image that never grows, so letting this row stretch to the window's
        # full width would just spread panels apart with dead space instead of keeping them
        # packed together.
        panels_row = ttk.Frame(view_frame)
        panels_row.pack(side=tk.TOP, anchor=tk.W)

        net_panel_frame = ttk.Frame(panels_row)
        # fill=tk.Y stretches this frame to match the row's own height (no button/spacer of
        # its own needed) -- the net canvas grows into whatever extra height that leaves.
        net_panel_frame.pack(side=tk.LEFT, fill=tk.Y)
        # A plain Label, not ax.set_title() -- a title drawn INSIDE a PyVista panel's own
        # rendered image clips against the panel boundary; a real Tkinter widget above the
        # image doesn't, and every "Level N" panel's title uses the same approach.
        ttk.Label(net_panel_frame, text="Net", font=self.LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        self.fig_net = plt.figure(figsize=(3.2, 4.5))
        # add_axes([0, 0, 1, 1]), not add_subplot -- add_subplot's own default margins
        # reserve room for axis labels/ticks that _style_2d_axis's set_axis_off() never draws,
        # shrinking the actual plotting area below the full figure. Filling the whole figure
        # instead matches every "Level N" panel's own PyVista viewport, which already fills
        # its entire window_size.
        self.ax2d = self.fig_net.add_axes([0, 0, 1, 1])
        self.canvas_net = FigureCanvasTkAgg(self.fig_net, master=net_panel_frame)
        net_widget = self.canvas_net.get_tk_widget()
        net_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Mouse-wheel-scroll zoom for the Net panel -- same idea as every "Level N" panel's own
        # self.level_zoom (_on_level_scroll), scaling _draw_target_faces' bounding-box-derived
        # half-extent instead of a PyVista camera's parallel_scale, since this panel is
        # matplotlib, not PyVista.
        self.net_zoom = 1.0
        net_widget.bind("<MouseWheel>", self._on_net_scroll)
        net_widget.bind("<Button-4>", self._on_net_scroll)
        net_widget.bind("<Button-5>", self._on_net_scroll)
        # Right-click-drag pans the Net panel (self.net_pan) -- its own analogue of every
        # "Level N" panel's self.level_pan, entirely separate state; middle-click resets it.
        self.net_pan = np.zeros(2)
        self._net_panning = False
        self._net_pan_last_xy = None
        net_widget.bind("<ButtonPress-3>", self._on_net_pan_start)
        net_widget.bind("<B3-Motion>", self._on_net_pan_motion)
        net_widget.bind("<ButtonRelease-3>", self._on_net_pan_end)
        net_widget.bind("<Button-2>", self._on_net_pan_reset)

        self.level_frames = {}
        self.level_plotters = {}
        self.level_labels = {}
        self.level_message_labels = {}
        # For _set_level_message's own width measurement (tkfont.Font.
        # measure) -- a real Font OBJECT, not the (family, size) tuple
        # LEVEL_MESSAGE_FONT itself is, since only a Font object exposes
        # `.measure()`. Needs a Tk root to already exist, which it does by
        # this point in __init__.
        self._level_message_font = tkfont.Font(root=self.root, family=self.LEVEL_MESSAGE_FONT[0],
                                                 size=self.LEVEL_MESSAGE_FONT[1])
        self.level_photos = {}
        self._level_center = {}
        self._level_half = {}
        # Two independent camera groups: Level 0 (a random-start-then-relax result, often
        # tangled/widely spread) has its own rotation/zoom/pan, while Levels 1-3 (an actual
        # settling/settled solid) share one set among themselves -- they look different
        # enough to need separate framing. `_level_camera(level)` returns the mutable,
        # in-place-updated dict for whichever group `level` belongs to; `_camera_group_levels
        # (level)` returns every panel that needs re-rendering when that group's state changes
        # -- a drag/scroll/pan on one group's panel never re-renders the other group's panels.
        #
        # Each group's own "rotation" is a quaternion (scipy Rotation)
        # rather than a separate azimuth/elevation pair -- two Euler
        # angles hit gimbal lock near the poles (elevation -> +-90
        # degrees, where a horizontal drag stops rotating around a
        # sensible axis); a quaternion represents the whole orientation as
        # one object with no such singularity. _initial_level_rotation()
        # reproduces the old LEVEL_DEFAULT_AZIM/ELEV starting view as a
        # Rotation, used as BOTH groups' own starting rotation (they just
        # don't stay in sync with each other once either is dragged).
        #
        # Each group's own "pan" is a 2D NDC (normalized device
        # coordinate, [-1, 1]) offset applied via vtkCamera's own
        # SetWindowCenter -- a pure post-projection VIEWPORT shift --
        # rather than a 3D world-space vector added to the camera's
        # focal_point/position (an earlier version did that, and had two
        # real bugs): (1) since every level panel renders at the exact
        # same LEVEL_PANEL_SIZE, one NDC value produces the exact same
        # PIXEL shift on every panel in its own group regardless of that
        # panel's own bounding-box scale -- a world-space offset instead
        # produced a DIFFERENT pixel shift per panel (each level's own
        # parallel_scale differs), which is what made translation look
        # unsynced across levels; (2) moving focal_point moves the
        # camera's own orbit center, so rotating (_on_level_motion) after
        # a pan no longer orbited the object's true center -- with
        # SetWindowCenter, the camera's focal_point/position are computed
        # exactly as if no pan existed (_render_level_pv), so a subsequent
        # rotation always still orbits the real center; pan only shifts
        # where that already-correct render lands in the panel.
        self._level0_camera = {"rotation": self._initial_level_rotation(),
                                "zoom": 1.0, "pan": np.zeros(2)}
        self._level13_camera = {"rotation": self._initial_level_rotation(),
                                 "zoom": 1.0, "pan": np.zeros(2)}
        # Populated by _build_level_pv_panel (label -> level), so a drag/
        # pan/scroll event (whose only clue which level it came from is
        # `event.widget`, the image Label that received it) can look up
        # which camera GROUP it should actually update.
        self._level_of_label = {}
        self._level_dragging = False
        self._level_last_xy = None
        # Which level's own camera group a drag/pan currently in progress
        # is updating -- captured once at press time (_on_level_drag_
        # start/_on_level_pan_start) and reused for every motion event
        # during that SAME drag, rather than re-deriving it from
        # event.widget on every motion call -- Tk's implicit button-1
        # grab keeps motion/release events routed to the originally-
        # pressed widget regardless of where the mouse strays, so re-
        # deriving would give the same answer anyway, but capturing once
        # is simpler and doesn't depend on that grab behavior holding.
        self._level_drag_group_level = None
        self._level_panning = False
        self._level_pan_last_xy = None
        self._level_pan_group_level = None
        # ONE button per level, below its panel -- no separate button
        # above (see _update_level_action_buttons for its full state
        # machine): idle it reads "Relax" (level 0 only) or "Inflate",
        # a run in progress turns it into "Stop" (see
        # _set_level_action_button_running), and once that level
        # converges it becomes "Subdivide" (clickable, advances to the
        # next level) or "DONE!" (MAX_LEVEL, nothing further to
        # subdivide to). Only the current frontier level's button is
        # ever enabled.
        self.level_action_buttons = {}
        # Debug-mode-only replay scrubber, one per level with an Inflate/Subdivide button
        # (levels 1..MAX_LEVEL -- Level 0's own Relax doesn't support capture_frames). Lets a
        # user inspect any point in a level's last-captured Inflate trajectory, not just the
        # live end state or the auto-played animation. self._level_frames[level] is that
        # level's own captured (positions, steps_taken) list, kept even after Subdividing past
        # it; self._level_scrub_index[level], when set, OVERRIDES what draw() shows for that
        # panel -- self.positions/level_snapshots are never touched by scrubbing, so the next
        # real action always continues from the true state regardless of the slider.
        self._level_frames = {}
        self._level_scrub_index = {}
        self.level_replay_sliders = {}
        for level in range(0, MAX_LEVEL + 1):
            level_frame = ttk.Frame(panels_row)
            # No fill/expand -- every panel hugs its own fixed image size (see panels_row).
            level_frame.pack(side=tk.LEFT)
            self.level_frames[level] = level_frame
            button = ttk.Button(level_frame, text="Relax" if level == 0 else "Inflate")
            self.level_action_buttons[level] = button
            if level > 0:
                # Packed FIRST among this frame's bottom-side widgets (Tk stacks additional
                # bottom-packed siblings upward from the bottom edge), so it lands below the
                # button once that's packed next.
                slider = ttk.Scale(level_frame, from_=0, to=0, orient=tk.HORIZONTAL,
                                    command=lambda v, lvl=level: self._on_replay_slider_moved(lvl, v))
                slider.state(["disabled"])
                self.level_replay_sliders[level] = slider
                slider.pack(side=tk.BOTTOM, in_=level_frame)
            # Button packed BEFORE the panel widget, at BOTTOM -- packing it after an
            # expand=True widget would starve it of space, since that widget would already
            # have claimed the whole remaining cavity. No fill=tk.X -- left at its own
            # natural, text-sized width, centered under the panel by pack's default anchor.
            button.pack(side=tk.BOTTOM, in_=level_frame)
            self._build_level_pv_panel(level, level_frame)

        # Per-level frozen snapshots of {faces, positions, face_of_fine,
        # edge_length} taken the moment the user subdivides PAST that
        # level (see _subdivide_step), or Level 0's Relax converges and
        # promotes it into Level 1 (see _finish_relax).
        self.level_snapshots = {}

        self.faces = None
        self.base_faces = None
        self.face_of_fine = None
        self.subdivision_level = 0
        self.edge_length = None
        # Level 0/1's own explicit spring-edge override (_fan_level_edges) and its origin, the
        # loaded net's own explicit "edges"/"face_edge_ids" fields -- None past Level 1, or for
        # any net/session with no such fields.
        self.edges = None
        self.base_edges = None
        self.base_face_edge_ids = None
        self.target_layout = None
        # interactive_builder_app's own saved "builder_connections" (bezier control points
        # included), or None -- see on_select_net for when this is populated.
        self.target_connections = None
        self.positions = None
        self.iteration_count = 0
        self.last_stats = {}
        self.level_history = {}
        self.stop_event = None
        # Whether the current frontier level has a Relax/Inflate run actively in progress --
        # set/cleared in lockstep with _set_level_action_button_running, read by
        # _refresh_history_table to color that level's row "running" (yellow) instead of
        # "not_converged" (red, reserved for an actual failure) while still mid-run.
        self._level_running = False
        # Backing state for the Convergence History table's "Simulation Time"/"Cumulative
        # Time" columns -- wall-clock time spent in the current level's own pressure-
        # calibration phase (_on_pressure_calibrated, None for Level 0/Relax, which has no
        # pressure) and, for Level 0 only, its streamed relax phase (_run_relax_stream) --
        # Level 1+ has no separate "sim" phase (calibration's own winning trial IS the Inflate
        # result). The `_start_time` pair marks when each phase began (None between runs); the
        # `_current_*_time_s` pair is what _record_level_history reads -- precomp is set once
        # at calibration finish, sim updates live on every progress callback. Reset to None
        # anywhere iteration_count resets. Never incremented during a frame replay -- that's
        # pure animation of already-finished cached positions, not new simulation work.
        self._precomp_start_time = None
        self._sim_start_time = None
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        # "Computing..." placeholder: which level's panel is currently showing it (None
        # normally) -- _render_level_pv skips that level entirely while set, so nothing can
        # paint a stale image over it mid-calibration. _computing_after_id is the pending
        # `root.after` callback driving the dot-cycle animation.
        self._computing_level = None
        self._computing_after_id = None
        self._computing_dots = 0
        # Frame-replay state: the winning calibration trial's own cached positions
        # (capture_frames), played back for display once calibration lands on a pressure --
        # _replay_after_id is the pending `root.after` callback, None when no replay running.
        self._replay_after_id = None
        self._replay_frames = None
        self._replay_index = 0
        self._replay_final_result = None
        self._replay_base_iteration_count = 0
        # The gtol in effect for the run currently underway (or the last one) -- captured from
        # self.tolerance_var at the moment Relax/Inflate starts, not re-read live, and recorded
        # into self.last_stats/level_history so a finished run's row shows what it actually used.
        self._current_gtol = DEFAULT_TOLERANCE
        # Same rationale as self._current_gtol, for the current level's own Target RMS spinner
        # -- captured when actually used, not re-read live, so a finished level's row keeps
        # showing the target it was calibrated against even after the spinner is edited later.
        self._current_target_rms_pct = self.target_rms_vars[1].get()
        # Whether "Auto"'s scripted sequence is currently driving the app --
        # _auto_attempted_level names the level Auto has already made its one Relax/Inflate
        # attempt at (no retries within a level), reset to None once _auto_step notices the
        # current level has changed since it last ran.
        self._auto_active = False
        self._auto_attempted_level = None
        self.current_path = None
        self.current_label = None
        self.label_to_path = {}
        # The currently-loaded net's own raw file content -- None until a net (or a saved
        # session carrying one) is loaded.
        self._net_file_json = None
        self._apply_plot_theme()
        self.refresh_net_list()
        self._apply_mode_visibility()
        if self.current_label:
            self.on_select_net()
        # Fits the window's starting height to release mode's default layout -- must come
        # after on_select_net's draw() call, not right after _apply_mode_visibility above.
        self._refit_window_height()

    def _init_ui_fonts(self):
        """Computes self.LEVEL_TITLE_FONT/LEVEL_MESSAGE_FONT (and the File menu's own font,
        see _build_menu) from "Choose a net"'s own actual rendered font -- a plain ttk.Label
        with no font= override renders via sv_ttk's default TLabel style, routed to the named
        font "SunValleyBodyFont" (see _scale_ui_fonts). Must run AFTER _scale_ui_fonts (needs
        the final scaled size) and AFTER sv_ttk.set_theme (SunValleyBodyFont doesn't exist
        before that). Using its actual .actual() family/size, rather than a hardcoded string
        that could silently fall back to a generic default, is what makes every title/message
        label genuinely match "Choose a net"."""
        reference = tkfont.nametofont("SunValleyBodyFont", root=self.root).actual()
        self.LEVEL_TITLE_FONT = (reference["family"], reference["size"])
        self.LEVEL_MESSAGE_FONT = self.LEVEL_TITLE_FONT

    def _scale_ui_fonts(self):
        """Scales every named Tk/ttk font by UI_FONT_SCALE, once at startup, right after
        sv_ttk.set_theme -- covers the whole UI's text size in one place. sv_ttk's themes
        route almost every ttk style through its own named Tcl fonts (SunValleyBodyFont, ...)
        rather than the standard TkDefaultFont/etc, so tkfont.names() (every named font known
        to the interpreter) reaches both in one pass. A size of 0 (some internal fonts use
        this) means "use the platform default" and stays that way rather than becoming
        0 * scale = 0."""
        for name in tkfont.names(self.root):
            font = tkfont.nametofont(name, root=self.root)
            size = font.cget("size")
            if size == 0:
                continue
            sign = -1 if size < 0 else 1
            font.configure(size=sign * round(abs(size) * UI_FONT_SCALE))
        # Treeview's rowheight is set by sv_ttk's theme file to SunValleyBodyFont's line
        # spacing plus a fixed padding, computed once when the theme loads -- it doesn't
        # auto-track a later font resize, so rows would stay sized for the old (smaller) font,
        # clipping the new, taller text. Recomputed here the same way (sv_ttk's dark.tcl
        # "Treeview" style) now that SunValleyBodyFont has its final scaled size.
        body_font = tkfont.nametofont("SunValleyBodyFont", root=self.root)
        ttk.Style(self.root).configure("Treeview", rowheight=body_font.metrics("linespace") + 3)

    def _build_menu(self):
        """This app's only menu bar -- File > Load.../Save..., Load above Save as the more
        common entry point (opening a previously-saved session before continuing it). See
        on_save_clicked/on_load_clicked for what the two actually do.

        Explicit `font=` on every Menu/add_command call here: Windows renders the native menu
        bar via its own chrome, which ignores "TkMenuFont"'s configured size regardless of
        _scale_ui_fonts -- a known Tk-on-Windows limitation for the top-level menu bar
        specifically. An explicit per-widget/per-item font IS respected. Reuses
        self.LEVEL_TITLE_FONT ("Choose a net"'s own actual family/size) so the menu genuinely
        matches the rest of the UI."""
        menu_font = self.LEVEL_TITLE_FONT
        menubar = tk.Menu(self.root, font=menu_font)
        file_menu = tk.Menu(menubar, tearoff=False, font=menu_font)
        file_menu.add_command(label="Load...", command=self.on_load_session_clicked, font=menu_font)
        file_menu.add_command(label="Save...", command=self.on_save_session_clicked, font=menu_font)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

    def _on_toggle_debug_mode(self, _event=None):
        self.debug_mode = not self.debug_mode
        self._apply_mode_visibility()
        self._refit_window_height()

    def _apply_mode_visibility(self):
        """Main differences between the two modes: whether the steps-vs-convergence radio row
        (plus Validate Mesh/Show normals) is shown, and whether the Convergence History
        table's "Max Stretch %" column is shown (all columns stay DEFINED in both modes, just
        hidden per mode, so no data is lost switching back and forth). Forces the steps choice
        back to "convergence" and Show normals off when leaving debug mode."""
        self.root.title(f"{APP_TITLE}{' (debug mode)' if self.debug_mode else ''}")
        self.history_tree.config(
            displaycolumns="#all" if self.debug_mode else self._release_mode_history_columns)
        # Changing displaycolumns doesn't resize the widget itself, so no <Configure> fires --
        # re-run the same proportional rescale by hand against the table's current width.
        self._rescale_history_columns(self.history_tree.winfo_width())
        if self.debug_mode:
            self.mode_row.pack(fill=tk.X, pady=(8, 0))
            self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
            # Sliders packed BEFORE their own level's button so they land below it (same
            # bottom-stacking order as __init__) -- both debug-only, same as the buttons.
            for level, slider in self.level_replay_sliders.items():
                slider.pack(side=tk.BOTTOM, in_=self.level_frames[level])
            for button in self.level_action_buttons.values():
                button.pack(side=tk.BOTTOM)
        else:
            self.mode_row.pack_forget()
            self.iterate_mode_var.set("convergence")
            redraw_needed = False
            if self.show_normals_var.get():
                self.show_normals_var.set(False)
                redraw_needed = True
            if self.show_vertex_normals_var.get():
                self.show_vertex_normals_var.set(False)
                redraw_needed = True
            if redraw_needed and self.faces is not None:  # nothing to redraw before a net's ever loaded
                self.draw()
            self.status_frame.pack_forget()  # whole frame, not just its text
            # Per-level Relax/Inflate/Subdivide/Stop buttons are debug-only too (release mode
            # uses Auto): hidden here, NOT destroyed, so every other
            # method that reads/writes their text/state (_update_level_
            # action_buttons, _set_level_action_button_running, _auto_
            # step's own driving calls to on_relax_clicked/on_inflate_
            # clicked/on_subdivide_clicked) keeps working exactly as
            # before regardless of mode -- Auto never invokes a button
            # widget directly, only the same plain methods a manual click
            # would call, so it's unaffected by these being unpacked.
            for button in self.level_action_buttons.values():
                button.pack_forget()
            for slider in self.level_replay_sliders.values():
                slider.pack_forget()

    def _refit_window_height(self):
        """Re-fits the window's height to whatever's actually visible right now -- without
        this, release mode would keep debug mode's own taller height, leaving dead space below
        the now-hidden mode_row/status_frame/per-level buttons. Called from three places,
        every one a genuine mode change (or the equivalent first-time framing) rather than
        routine net switching: once at the end of __init__ (after on_select_net's own draw()
        call), from _on_toggle_debug_mode, and from on_load_session_clicked's own tail (its
        debug_mode can differ from whatever was showing before the load). Deliberately NOT
        called from plain on_select_net -- picking a different net shouldn't fight a manual
        resize the user already made; only an actual mode change re-fits the window.

        NOT called directly from _apply_mode_visibility itself, or from
        inside __init__ before the first draw() -- a "Level N" panel's
        own image Label has essentially ZERO natural height before its
        first PhotoImage is set (self.level_photos[level] starts None),
        so measuring reqheight that early would fit the window to a
        too-short, pre-image layout and squeeze every panel once images
        actually appear (see LEVEL_PANEL_SIZE's own __init__ comment on
        exactly that failure mode) -- by the time _on_toggle_debug_mode
        can even fire, on_select_net's own startup call has already run.
        update_idletasks() forces Tk to actually recompute every widget's
        geometry from whatever pack/pack_forget calls happened since the
        last idle cycle -- winfo_reqheight() would otherwise still
        reflect a stale layout. Width is read back from the window's own
        CURRENT actual size (winfo_width()), not recomputed -- it never
        changes between modes or net selections, only height does."""
        self.root.update_idletasks()
        self.root.geometry(f"{self.root.winfo_width()}x{self.root.winfo_reqheight()}")

    def _set_status(self, text, kind="info"):
        # "success" is always dropped -- the per-level button states and Convergence History
        # table already show it. Release mode also drops routine "info" narration for the
        # same reason -- the live panel redraw, button state, and history row already say all
        # of it; debug mode keeps "info" since it's for someone working on this app, not an
        # end user. "warn"/"error" still get SET here in both modes (meaningful internal
        # state), but release mode never shows them -- the whole status_frame is unpacked
        # there (_apply_mode_visibility).
        if kind == "success" or (kind == "info" and not self.debug_mode):
            text = ""
        self.status_var.set(text)
        self.status_label.configure(foreground=STATUS_COLORS.get(kind, ""))

    # ---- Level panels (PyVista/VTK -- see LEVEL_PANEL_SIZE's comment) ----

    def _build_level_pv_panel(self, level, level_frame):
        """Builds one "Level N" panel: a plain Tkinter title Label (NOT
        text drawn inside the rendered image -- see _render_level_pv's
        own Design notes for why that clipped) above an image Label
        showing an off-screen-rendered PyVista image, rather than a live
        interactive VTK widget -- keeps this app on a single interaction
        toolkit (Tkinter native mouse bindings reimplement just the
        click-drag-to-rotate behavior mplot3d used to give the old
        matplotlib panels for free, see _on_level_drag_start/_motion/_end
        below) instead of also embedding VTK's own widget/event loop."""
        ttk.Label(level_frame, text=f"Level {level}", font=self.LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        # Reserved status-message strip (see _set_level_message's own
        # comment) -- built for EVERY level, including 0 (which never
        # Every "Level N" panel reserves the same fixed message-strip height regardless of
        # whether its own message is in use right now (skipping it for Level 0 would leave its
        # frame one strip shorter than the others -- same cross-panel height-mismatch failure
        # mode as the "Computing..." placeholder). Packed BEFORE the image label, at
        # side=tk.BOTTOM, so it claims its own bottom strip first; the image label's
        # fill=tk.BOTH/expand=True fills the rest. `padx` left at 0 -- _set_level_message
        # computes and applies it per-message.
        message_label = tk.Label(level_frame, text="", anchor=tk.W, bg=PLOT_THEME["bg"],
                                  fg=PLOT_THEME["fg"], font=self.LEVEL_MESSAGE_FONT)
        message_label.pack(side=tk.BOTTOM, fill=tk.X)
        self.level_message_labels[level] = message_label
        label = tk.Label(level_frame, bg=PLOT_THEME["bg"], bd=0)
        label.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        plotter = pv.Plotter(off_screen=True, window_size=list(_level_panel_size(level)))
        plotter.set_background(PLOT_THEME["bg"])
        self.level_labels[level] = label
        self._level_of_label[label] = level
        self.level_plotters[level] = plotter
        self.level_photos[level] = None  # keeps a reference alive -- Tk drops a GC'd PhotoImage
        self._level_center[level] = np.zeros(3)
        self._level_half[level] = 1.0
        label.bind("<ButtonPress-1>", self._on_level_drag_start)
        label.bind("<B1-Motion>", self._on_level_motion)
        label.bind("<ButtonRelease-1>", self._on_level_drag_end)
        # Right-click-drag pans (self.level_pan); middle-click resets to zero. No per-panel
        # state to capture at press time (a pan drag needs no per-panel scale, unlike
        # rotate/zoom), so every level's label shares the same three level-agnostic handlers.
        label.bind("<ButtonPress-3>", self._on_level_pan_start)
        label.bind("<B3-Motion>", self._on_level_pan_motion)
        label.bind("<ButtonRelease-3>", self._on_level_pan_end)
        label.bind("<Button-2>", self._on_level_pan_reset)
        # Windows/macOS deliver <MouseWheel> with event.delta; Linux (X11) delivers wheel
        # motion as Button-4/Button-5 clicks instead -- binding all three covers every platform.
        label.bind("<MouseWheel>", self._on_level_scroll)
        label.bind("<Button-4>", self._on_level_scroll)
        label.bind("<Button-5>", self._on_level_scroll)

    @staticmethod
    def _initial_level_rotation():
        """Builds the starting camera quaternion reproducing LEVEL_DEFAULT_AZIM/ELEV -- the
        only place spherical angles are converted into a rotation; every update after this
        (_on_level_motion) works with the quaternion directly and never decomposes it back
        into angles, which is what avoids gimbal lock. Constructs an explicit orthonormal
        (direction, right, up) frame and reads the rotation off it as a 3x3 matrix (a
        rotation matrix IS exactly [x|y|z-axis-image] as columns)."""
        azim, elev = np.radians(LEVEL_DEFAULT_AZIM), np.radians(LEVEL_DEFAULT_ELEV)
        direction = np.array([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim),
                               np.sin(elev)])
        world_up = np.array([0.0, 0.0, 1.0])
        # This cross-product order makes [direction | right | up] a right-handed (det +1)
        # frame -- the other order is left-handed and scipy's Rotation.from_matrix rejects it.
        right = np.cross(world_up, direction)
        right /= np.linalg.norm(right)
        up = np.cross(direction, right)
        return Rotation.from_matrix(np.column_stack([direction, right, up]))

    def _level_camera(self, level):
        """The mutable camera-state dict (`{"rotation", "zoom", "pan"}`) for `level`'s own
        group -- Level 0 has an independent one from Levels 1-3's shared one. Callers mutate
        the returned dict's keys in place rather than reassigning self._level0_camera/
        _level13_camera themselves."""
        return self._level0_camera if level == 0 else self._level13_camera

    def _camera_group_levels(self, level):
        """Every level panel sharing `level`'s own camera group -- `[0]` for Level 0, every
        other built level otherwise (Levels 1-3)."""
        if level == 0:
            return [0]
        return [lvl for lvl in self.level_plotters if lvl != 0]

    def _render_camera_group(self, level):
        """Re-renders every panel in `level`'s own camera group (not every level panel) --
        what a drag/pan/scroll on one group's panel should refresh."""
        for lvl in self._camera_group_levels(level):
            self._render_level_pv(lvl)

    def _on_level_drag_start(self, event):
        self._level_dragging = True
        self._level_last_xy = (event.x, event.y)
        self._level_drag_group_level = self._level_of_label.get(event.widget, 1)

    def _on_level_motion(self, event):
        """Left-click-drag on a level panel rotates that panel's own camera group's
        orientation (self._level_drag_group_level, set at press time) and re-renders every
        panel in that same group (_render_camera_group). This app's own analogue of mplot3d's
        drag rotation, reimplemented since PyVista/VTK panels are plain images, not
        interactive widgets. Re-rendering the whole group costs ~30ms, well within real-time
        feel.

        Composes two small rotations -- about the current up axis for a horizontal drag, the
        current right axis for a vertical one -- onto the existing quaternion, rather than
        accumulating into a stored azimuth/elevation pair. This is a free trackball rotation:
        "up" is whatever the group's rotation currently says it is (not re-pinned to world +z
        every frame), so there's no pole for elevation to lock up near, and no clamp needed."""
        if not self._level_dragging or self._level_last_xy is None:
            return
        cam = self._level_camera(self._level_drag_group_level)
        last_x, last_y = self._level_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        right = cam["rotation"].apply([0.0, 1.0, 0.0])
        sensitivity = np.radians(LEVEL_DRAG_SENSITIVITY)
        yaw = Rotation.from_rotvec(-dx * sensitivity * up)
        pitch = Rotation.from_rotvec(-dy * sensitivity * right)
        cam["rotation"] = pitch * yaw * cam["rotation"]
        self._level_last_xy = (event.x, event.y)
        self._render_camera_group(self._level_drag_group_level)

    def _on_level_drag_end(self, event):
        self._level_dragging = False
        self._level_last_xy = None
        # One last explicit render as a safety net, in case the button release didn't come
        # with its own trailing motion event (_on_level_motion already keeps the group live
        # during the drag itself).
        if self._level_drag_group_level is not None:
            self._render_camera_group(self._level_drag_group_level)
        self._level_drag_group_level = None

    def _on_level_pan_start(self, event):
        self._level_panning = True
        self._level_pan_last_xy = (event.x, event.y)
        self._level_pan_group_level = self._level_of_label.get(event.widget, 1)

    def _on_level_pan_motion(self, event):
        """Right-click-drag on a level panel translates that panel's own camera group's pan
        (self._level_pan_group_level, set at press time; the pan value is a 2D NDC offset
        applied via vtkCamera's own SetWindowCenter in _render_level_pv -- NDC rather than a
        3D world-space offset, which would desync panels of different scale) and re-renders
        every panel in that group -- pan's analogue of _on_level_motion's rotation drag. Needs
        no per-panel scale since NDC is resolution/scale-independent; converting the drag
        through the one fixed LEVEL_PANEL_SIZE makes the shift identical across the group.

        Sign convention: SetWindowCenter(x, y) moves the image LEFT for x=+1 (half the panel
        width) and DOWN for y=+1 (half the panel height) -- so a rightward drag needs a
        negative x term, a downward drag (screen y already growing downward) a positive y
        term."""
        if not self._level_panning or self._level_pan_last_xy is None:
            return
        cam = self._level_camera(self._level_pan_group_level)
        last_x, last_y = self._level_pan_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        panel_width, panel_height = _level_panel_size(self._level_pan_group_level)
        cam["pan"] = cam["pan"] + np.array(
            [-dx / (panel_width / 2.0), dy / (panel_height / 2.0)])
        self._level_pan_last_xy = (event.x, event.y)
        self._render_camera_group(self._level_pan_group_level)

    def _on_level_pan_end(self, event):
        self._level_panning = False
        self._level_pan_last_xy = None
        # Same safety-net rationale as _on_level_drag_end.
        if self._level_pan_group_level is not None:
            self._render_camera_group(self._level_pan_group_level)
        self._level_pan_group_level = None

    def _on_level_pan_reset(self, event=None):
        """Middle-click on a level panel resets that panel's own camera group's pan/zoom/
        rotation together, back to defaults -- only the ONE group the click landed on, since
        Level 0 and Levels 1-3 are independent groups. Rotation resets through
        _initial_level_rotation() (the same starting quaternion __init__ builds), not plain
        identity, since the default view is deliberately non-axis-aligned. `event=None` (no
        current caller does this) falls back to resetting the Levels-1-3 shared group."""
        level = self._level_of_label.get(event.widget, 1) if event is not None else 1
        cam = self._level_camera(level)
        cam["pan"] = np.zeros(2)
        cam["zoom"] = 1.0
        cam["rotation"] = self._initial_level_rotation()
        self._render_camera_group(level)

    def _on_level_scroll(self, event):
        """Mouse-wheel-scroll on a level panel zooms that panel's own camera group and
        re-renders every panel in that group -- Level 0 and Levels 1-3 zoom independently.
        event.num is Button-4/5 on X11 (no event.delta there); event.delta is Windows/macOS's
        signed notch count (positive delta zooms in)."""
        level = self._level_of_label.get(event.widget)
        if level is None:
            return
        cam = self._level_camera(level)
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / LEVEL_ZOOM_STEP
        else:
            factor = LEVEL_ZOOM_STEP
        cam["zoom"] = max(LEVEL_ZOOM_MIN, min(LEVEL_ZOOM_MAX, cam["zoom"] * factor))
        self._render_camera_group(level)

    def _render_all_level_panels(self):
        for level in self.level_plotters:
            self._render_level_pv(level)

    def _draw_level_panel(self, level, faces, positions, face_of_fine):
        """One "Level N" panel, drawn every call from whatever faces/positions/face_of_fine
        draw() passes it (live, frozen snapshot, or all-None for "not reached yet"). Faces are
        always triangles from Level 1 on, so no fan/n-gon handling is needed. Colors every
        face by its original base face (`face_of_fine`) as per-cell RGB, one add_mesh call
        per group (PyVista/VTK's depth buffer handles occlusion correctly regardless of face
        count or convexity).

        Debug mode's "Show face normals" toggle also draws each triangle's own outward normal
        as a line segment from its centroid, in NORMAL_COLOR, scaled to NORMAL_LENGTH_FRACTION
        of that triangle's mean edge length (current, not rest, geometry) so it always reads
        as "about half an edge long". "Show vertex normals" is the same idea per-vertex
        (averaged from its touching faces) -- catches a vertex where the touching faces
        disagree, which the per-face version alone can miss."""
        plotter = self.level_plotters[level]
        plotter.clear()
        if faces is not None:
            vertex_ids = sorted(positions)
            idx = {v: i for i, v in enumerate(vertex_ids)}
            points = np.array([positions[v] for v in vertex_ids])
            # One add_mesh call per GROUP, not one for the whole mesh with a per-cell "colors"
            # array -- wireframe edges are the color halfway between white and the polygon
            # color, which only makes sense as a per-face edge color, and VTK's edge_color is
            # one uniform color per call. Still one scene/depth buffer (plotter.clear() above,
            # not between these calls), so cross-group occlusion still works.
            # Grouped by self.group_of_base_face, not raw base_face index -- every triangle
            # from one Polygon-Fold-subdivided source polygon (interactive_builder_app's own
            # "source_polygon_id") shares its color and add_mesh call, reading as one
            # uniformly-colored/outlined polygon at every level.
            groups_present = sorted(set(self.group_of_base_face[bf] for bf in set(face_of_fine)))
            for group in groups_present:
                face_color = self.color_by_group[group]
                group_faces = [f for f, bf in zip(faces, face_of_fine)
                               if self.group_of_base_face[bf] == group]
                face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
                mesh = pv.PolyData(points, face_conn)
                plotter.add_mesh(mesh, color=face_color, show_edges=True,
                                  edge_color=_midpoint_color("white", face_color),
                                  line_width=SUBDIVISION_EDGE_WIDTH,
                                  backface_params=dict(color=_darken_color(face_color)))

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

            # Each level fills its own panel to 90% from its own CURRENT bounding box, not a
            # fixed reference framing shared across levels -- the per-level target RMS %
            # tapers down, so the converged mesh's absolute size genuinely shrinks level to
            # level; a fixed camera would just display that shrinkage as "inconsistent
            # sizes". Rotation/pan/zoom stay shared across Levels 1-3 regardless (separate
            # mechanism); only the auto-fit center/half is per-level.
            # `half` is the shape's own bounding-SPHERE radius (largest distance from center
            # to any vertex), not half of the largest single world-axis extent -- a
            # single-axis measure underestimates the true on-screen extent from an oblique
            # angle (the diagonal reaches further than any one axis's half-length), letting
            # renders clip past the edge despite `_level_zoom_fill` claiming "90%". A proper
            # radius bounds the shape from every direction, guaranteed to fit at any
            # rotation. `_render_level_pv`'s aspect handling then makes the panel's narrower
            # dimension exactly `_level_zoom_fill(level)` of the frame, with the taller
            # dimension getting extra slack -- both dimensions end up at most that fraction.
            #
            # `_level_zoom_fill` alone is the single, authoritative fill fraction -- a former
            # second "margin" constant compounded with it and caused >100% clipping.
            lo, hi = points.min(axis=0), points.max(axis=0)
            center = (lo + hi) / 2
            self._level_center[level] = center
            self._level_half[level] = float(np.linalg.norm(points - center, axis=1).max()) + 1e-6
        self._render_level_pv(level)

    def _render_level_pv(self, level):
        """Positions an orthographic (parallel-projection) camera from `level`'s own camera
        group's rotation at a distance derived from this level's own current bounding box
        (self._level_center/_level_half, set by _draw_level_panel -- necessary since neither
        a pure-spring relax nor a pressure inflation keeps the result near the origin or at a
        familiar scale), renders off-screen, and blits the result into self.level_labels[level].
        Parallel rather than perspective projection gives every panel fixed, comparable
        axis-limit-like framing with no foreshortening.

        Skips entirely (leaving the panel's "Computing..." text alone) while `level` is the
        one currently showing it -- the single choke point every caller goes through, so
        nothing can paint a stale image over the placeholder mid-calibration.

        The panel's "Level N" title is a separate Tkinter Label, not drawn into this image --
        a title drawn inside the rendered scene (via plotter.add_text) clips against the
        panel's own top edge, since a VTK text actor's positioning doesn't guarantee it stays
        fully inside the viewport the way a real widget above the image does."""
        if level == self._computing_level:
            return
        cam = self._level_camera(level)
        direction = cam["rotation"].apply([1.0, 0.0, 0.0])
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        center, half = self._level_center[level], self._level_half[level]
        distance = half * 4
        plotter = self.level_plotters[level]
        camera = plotter.camera
        camera.parallel_projection = True
        camera.focal_point = tuple(center)
        camera.position = tuple(center + direction * distance)
        # Read straight off the quaternion, not pinned to world (0,0,1) -- a fixed world-up
        # forces elevation into a separate angle that locks up near the poles; letting up
        # rotate freely with the camera is what a quaternion buys.
        camera.up = tuple(up)
        # parallel_scale sets the camera's vertical half-height in world units -- the
        # horizontal half-width it implies is narrower by the window's aspect ratio, which
        # would crop the wider dimension on this portrait-shaped panel if left at exactly
        # `half`. Scaling up by height/width guarantees the full half-extent fits in both
        # directions; dividing by _level_zoom_fill(level) then shrinks the shape within that
        # guaranteed-fitting frame.
        panel_width, panel_height = _level_panel_size(level)
        # cam["zoom"] is a divisor here (like _level_zoom_fill) since parallel_scale is a
        # visible-world-height, not a magnification -- a bigger zoom must shrink parallel_scale.
        camera.parallel_scale = (half * max(1.0, panel_height / panel_width)
                                  / _level_zoom_fill(level) / cam["zoom"])
        # cam["pan"] is applied here, as a pure post-projection viewport shift, rather than by
        # moving focal_point/position -- that way it can't desync between panels of different
        # scale or move a panel's own orbit center out from under a later rotation.
        camera.SetWindowCenter(*cam["pan"])
        plotter.reset_camera_clipping_range()
        # plotter.screenshot() does NOT re-render on a camera-only change by itself -- an
        # explicit render() first is what actually asks VTK to redraw the scene from the
        # camera's current position before screenshot() reads the framebuffer back.
        plotter.render()
        image = plotter.screenshot(return_img=True)
        self.level_photos[level] = ImageTk.PhotoImage(Image.fromarray(image))
        # text="" clears whatever "Computing..." text was last set -- harmless to leave
        # (Label's default compound="none" shows the image over it regardless), but tidier.
        self.level_labels[level].configure(image=self.level_photos[level], text="")

    # ---- "Computing..." placeholder (pressure calibration) ----

    # How often the "Computing" dot-cycle advances (nothing->1->2->3->
    # repeat) -- purely decorative, so any value that reads as "still
    # working" without being distractingly fast is fine.
    COMPUTING_DOT_INTERVAL_MS = 500

    def _set_level_message(self, level, text):
        """Sets `level`'s bottom status message, left-anchored (anchor=tk.W) but with `padx`
        computed here to make this specific `text` land visually centered under the panel --
        true tk.CENTER re-anchors from scratch on every update, so the message's left edge
        would visibly jump every time its length changes, and a single fixed left inset
        doesn't look centered for every message either ("Computing" is much shorter than
        "Replay frame 27 / 93"). Measuring this string's own rendered width
        (self._level_message_font, a real Font object) and computing the inset that would
        actually center it gives the best of both: visually equivalent to true centering, but
        the position only shifts by however much this message's width actually changed since
        the last call."""
        text_width = self._level_message_font.measure(text)
        pad = max(0, (_level_panel_size(level)[0] - text_width) // 2)
        self.level_message_labels[level].configure(text=text, padx=pad)

    def _start_computing_animation(self, level):
        """Blanks `level`'s panel image (plain background, no mesh) and shows an animated
        "Computing..." in its bottom message area for as long as pressure calibration is
        searching -- most of calibration's several relax_once trials are thrown away, so
        there's no single meaningful shape to show frame-by-frame, unlike Level 0's own Relax
        (which stays live -- only ever one run there). _render_level_pv skips `level` entirely
        while self._computing_level is set to it, so nothing else can paint over the blank
        image.

        The blank image is rendered ONCE here, not regenerated every dot-cycle tick -- a flat
        background never changes frame to frame, so only the separate message Label's text
        needs to keep ticking, far cheaper than a PIL image regenerate + PhotoImage
        conversion every 500ms."""
        self._computing_level = level
        self._computing_dots = 0
        blank = Image.new("RGB", _level_panel_size(level), PLOT_THEME["bg"])
        self.level_photos[level] = ImageTk.PhotoImage(blank)
        self.level_labels[level].configure(image=self.level_photos[level])
        self._tick_computing_animation()

    def _tick_computing_animation(self):
        if self._computing_level is None:
            return
        self._set_level_message(self._computing_level, "Computing" + "." * self._computing_dots)
        self._computing_dots = (self._computing_dots + 1) % 4
        self._computing_after_id = self.root.after(
            self.COMPUTING_DOT_INTERVAL_MS, self._tick_computing_animation)

    def _stop_computing_animation(self):
        """Cancels the dot-cycle, clears the message area, and clears self._computing_level --
        _render_level_pv is free to draw that level normally again, but doesn't do so on its
        own; the caller always follows this with either a real draw() or the start of a frame
        replay. Clearing the message here first covers the stopped-during-calibration case,
        which has nothing else to overwrite "Computing..." otherwise."""
        if self._computing_after_id is not None:
            self.root.after_cancel(self._computing_after_id)
            self._computing_after_id = None
        level = self._computing_level
        self._computing_level = None
        if level is not None:
            self._set_level_message(level, "")

    # ---- theme ----

    def _style_2d_axis(self, ax, theme):
        ax.title.set_color(theme["fg"])
        ax.set_axis_off()

    def _apply_plot_theme(self):
        """Recolor the Net figure's chrome to match the fixed dark-only plot theme -- ax.cla()
        (called every draw()) resets this to matplotlib's defaults, so it's re-applied every
        redraw. Every "Level N" panel is PyVista, not matplotlib -- its background/text color
        is set once at panel construction, not re-applied here. Returns the theme dict so
        draw() can reuse its colors."""
        theme = PLOT_THEME
        self.fig_net.patch.set_facecolor(theme["bg"])
        self.ax2d.set_facecolor(theme["bg"])
        self._style_2d_axis(self.ax2d, theme)
        return theme

    def _draw_idle_all(self):
        """The Net panel is matplotlib and needs an explicit idle-redraw
        request; every "Level N" panel already pushed its own freshly
        rendered image straight to its Label inside _render_level_pv, so
        there's nothing further to do for those here."""
        self.canvas_net.draw_idle()

    # ---- net picker ----

    def refresh_net_list(self, keep_selection=True):
        """Rescan data/input/stretchy_nets/ and rebuild the dropdown. Every net starts from a
        cheap, instant random start, so there's no precomputed-vs-not state to flag. Scans
        both "*.json" (hand-authored nets, and any older net predating interactive_builder_
        app's own save extension) and "*.poly" (that app's own current save extension, same
        plain JSON content) -- load_stretchy_mesh/json.load never care about the extension."""
        paths = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json"))
                        + glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.poly")))
        self.label_to_path = {}
        for path in paths:
            # A ".json" and ".poly" sharing the same basename collide here (second one wins) --
            # not handled specially, since the two extensions replace one another per net.
            label = os.path.splitext(os.path.basename(path))[0].replace("_", " ").title()
            self.label_to_path[label] = path

        labels = list(self.label_to_path.keys())
        self.combo["values"] = labels

        previous_path = self.label_to_path.get(self.current_label)
        if keep_selection and previous_path:
            for label, path in self.label_to_path.items():
                if path == previous_path:
                    self.current_label = label
                    break
        else:
            # Default to DEFAULT_NET_BASENAME (cube.poly or cube.json, matched by basename so a
            # save under the other extension doesn't stop it being found) if present, else the
            # first net alphabetically.
            default_label = next(
                (l for l, p in self.label_to_path.items()
                 if os.path.splitext(os.path.basename(p))[0] == DEFAULT_NET_BASENAME), None)
            self.current_label = default_label or (labels[0] if labels else None)

        if self.current_label:
            self.net_var.set(self.current_label)

    def on_select_net(self, event=None):
        chosen = self.net_var.get()
        self.current_label = chosen
        path = self.label_to_path[chosen]
        try:
            faces, self.mesh_name = load_stretchy_mesh(path)
            base_edges, base_face_edge_ids = load_stretchy_mesh_edges(path)
        except ValueError as e:
            self._set_status(str(e), "error")
            self.faces = None
            return

        # A legacy fabric-subdivided net (carrying baked-in "coarse_faces") is loaded at its
        # own coarse_faces -- always level 0 -- rather than its pre-baked fine mesh; "Subdivide"
        # refines it interactively from there instead. An ordinary net has no coarse_faces and
        # its "faces" already are level 0.
        legacy_coarse_faces, _, _ = load_fabric_spec(path)
        self.base_faces = legacy_coarse_faces if legacy_coarse_faces is not None else faces
        # The raw parsed file is kept as self._net_file_json, read here up front since
        # self.colors below needs its "source_polygon_id" section, so on_save_session_clicked
        # can embed a full copy of it, letting on_load_session_clicked reproduce this exact
        # layout decision later without the original file needing to still exist on disk.
        with open(path) as f:
            self._net_file_json = json.load(f)
        # base_edges/base_face_edge_ids and "source_polygon_id" are all keyed to the file's own
        # "faces" vertex-id/index space -- only meaningful when self.base_faces IS that same
        # "faces" (the ordinary case); a legacy fabric net's re-derived coarse_faces use a
        # different vertex-id space, so these stay None (the always-safe fallbacks every
        # consumer already has).
        if legacy_coarse_faces is not None:
            base_edges = base_face_edge_ids = None
            source_polygon_id = None
        else:
            source_polygon_id = self._net_file_json.get("source_polygon_id")
        self.base_edges = base_edges
        self.base_face_edge_ids = base_face_edge_ids
        self.colors, self.color_by_group, self.group_of_base_face = _face_colors_by_group(
            len(self.base_faces), source_polygon_id)

        # Precomputed once per net selection: this panel's flat net layout doesn't change with
        # subdivision level, only its overlay does. A file saved by interactive_builder_app
        # carries its own "net_layout" section (one entry per original placed shape) -- when
        # present, reproduce that exact arrangement rather than a fresh one. Otherwise (a
        # hand-authored net, or a legacy fabric net with no such section) fall back to
        # build_stretchy_net_layout's own BFS spanning tree over shared edges. A legacy
        # net_layout (no per-entry "shape_id") must still match `faces`' length; a new-format
        # one never will (by design, once a fold exists), so that check doesn't apply to it.
        net_layout = self._net_file_json.get("net_layout")
        if net_layout is not None and (
                _net_layout_is_new_format(net_layout) or len(net_layout) == len(self.base_faces)):
            self.target_layout = _layout_from_net_layout(self.base_faces, net_layout)
            # Only present alongside the exact "net_layout" it was saved with -- the BFS
            # fallback below has no matching connection geometry, so this stays None there.
            self.target_connections = self._net_file_json.get("builder_connections")
        else:
            self.target_layout = build_stretchy_net_layout(self.base_faces)
            self.target_connections = None

        # Level 0 and Level 1 share this exact fan-triangulated topology -- computed once here,
        # up front, rather than re-derived on promotion.
        self.faces, self.edge_length, self.face_of_fine = _build_level1_topology(self.base_faces)
        # Level 0/1's own explicit spring-edge override -- None past Level 1 (Level 2/3's own
        # edges are always unambiguous), reset here on every net load.
        self.edges = _fan_level_edges(self.faces, self.base_edges)
        self.current_path = path
        self.subdivision_level = 0
        self.positions = random_initial_positions(self.faces, seed=0)
        self.iteration_count = 0
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        self.last_stats = self._compute_stretch_stats()
        self.level_history = {}
        self.level_snapshots = {}
        self.history_tree.delete(*self.history_tree.get_children())
        self.stop_event = None
        # A freshly-loaded net has no captured Inflate frames yet -- clears every level's
        # replay slider back to disabled/empty rather than leaving the previous net's own
        # trajectory scrubbable here.
        self._level_frames = {}
        self._level_scrub_index = {}
        for level in self.level_replay_sliders:
            self._update_replay_slider(level)
        # A fresh net starts over cleanly, resetting any Auto sequence defensively.
        self._auto_active = False
        self._auto_attempted_level = None
        # Fresh camera state for both groups on every new net selection -- a totally
        # different-looking shape shouldn't inherit the previous net's camera. Doesn't affect
        # File > Load, which builds its own state directly from the saved SessionStateModel's
        # own camera fields and never calls this method.
        self._level0_camera = {"rotation": self._initial_level_rotation(),
                                "zoom": 1.0, "pan": np.zeros(2)}
        self._level13_camera = {"rotation": self._initial_level_rotation(),
                                 "zoom": 1.0, "pan": np.zeros(2)}
        self._record_level_history()
        self._update_level_action_buttons()
        self._update_auto_button()
        self.draw()

    # ---- session save/load (File menu) ----

    def on_save_session_clicked(self):
        """File > Save -- serializes the whole current session (the net, every Target RMS/
        Tolerance spinner, the Convergence History table, the mesh at every subdivision level
        reached so far, and each panel's own camera view) to one JSON file via
        session_state.SessionStateModel, enough for on_load_session_clicked to reopen it
        exactly as left with no re-solving. self.level_snapshots holds every level already
        left behind; the current frontier level's own live faces/positions/face_of_fine/
        edge_length aren't in there yet, so this adds them under self.subdivision_level before
        writing. Camera rotation (a scipy Rotation) is stored as .as_quat() -- JSON has no
        quaternion type, and a plain tuple round-trips through Rotation.from_quat() losslessly."""
        if self.positions is None:
            messagebox.showwarning("Save", "No net is loaded yet.")
            return
        SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # ".hippo" -- still plain JSON underneath (model_dump_json below), just a distinct
        # extension so a saved session doesn't look like an ordinary net .json in a file picker.
        path = filedialog.asksaveasfilename(
            title="Save session", initialdir=str(SESSION_OUTPUT_DIR),
            defaultextension=SESSION_FILE_EXTENSION,
            filetypes=[("Inflate Polyhedron session", f"*{SESSION_FILE_EXTENSION}")])
        if not path:
            return

        levels = {level: LevelStateModel.from_mesh(snap["faces"], snap["positions"],
                                                     snap["face_of_fine"])
                  for level, snap in self.level_snapshots.items()}
        levels[self.subdivision_level] = LevelStateModel.from_mesh(
            self.faces, self.positions, self.face_of_fine, self.edge_length)
        state = SessionStateModel(
            net_name=self.mesh_name,
            base_faces=[list(face) for face in self.base_faces],
            net_file=self._net_file_json,
            subdivision_level=self.subdivision_level,
            pressure_value=self.pressure_value,
            iteration_count=self.iteration_count,
            debug_mode=self.debug_mode,
            tolerance=self.tolerance_var.get(),
            target_rms_pct={level: var.get() for level, var in self.target_rms_vars.items()},
            last_stats=LastStatsModel(**{k: v for k, v in self.last_stats.items()
                                          if k in LastStatsModel.model_fields}),
            level_history={level: LevelHistoryRecordModel(**rec)
                           for level, rec in self.level_history.items()},
            levels=levels,
            level_zoom=self._level13_camera["zoom"],
            level_pan=(float(self._level13_camera["pan"][0]), float(self._level13_camera["pan"][1])),
            level_rotation=tuple(float(v) for v in self._level13_camera["rotation"].as_quat()),
            level0_zoom=self._level0_camera["zoom"],
            level0_pan=(float(self._level0_camera["pan"][0]), float(self._level0_camera["pan"][1])),
            level0_rotation=tuple(float(v) for v in self._level0_camera["rotation"].as_quat()),
            net_zoom=self.net_zoom,
            net_pan=(float(self.net_pan[0]), float(self.net_pan[1])),
        )
        try:
            with open(path, "w") as f:
                f.write(state.model_dump_json(indent=2))
        except OSError as e:
            messagebox.showerror("Save", f"Could not save session: {e}")
            return
        self._set_status(f"Session saved to {os.path.basename(path)}.", "info")

    def on_load_session_clicked(self):
        """File > Load -- the inverse of on_save_session_clicked. Fully
        replaces the current net/mesh/history (like on_select_net does
        for a fresh net pick) rather than merging into whatever's
        currently loaded, and touches nothing that needs re-solving --
        every level's mesh, the pressure/iteration/history readouts, and
        every spinner come straight from the file."""
        path = filedialog.askopenfilename(
            title="Load session", initialdir=str(SESSION_OUTPUT_DIR),
            filetypes=[("Inflate Polyhedron session", f"*{SESSION_FILE_EXTENSION}"),
                       ("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path) as f:
                state = SessionStateModel.model_validate_json(f.read())
        except (OSError, ValueError) as e:
            messagebox.showerror("Load", f"Could not load session: {e}")
            return

        self.mesh_name = state.net_name
        self.net_var.set(state.net_name)
        self.current_label = state.net_name
        self.current_path = None  # not tied to any file under STRETCHY_NETS_DIR
        self.base_faces = [list(face) for face in state.base_faces]
        self._net_file_json = state.net_file
        # Same "edges"/"face_edge_ids"/"source_polygon_id" disambiguation/
        # grouping on_select_net reads from a fresh net file (see
        # _fan_level_edges/mesh_levels.subdivide_once's own docstrings,
        # and _face_colors_by_group) -- only meaningful when this
        # session's own base_faces actually IS the net_file's "faces"
        # (the ordinary, non-legacy case; see on_select_net's own
        # comment), which a saved session has no direct record of, so
        # this checks the same way on_select_net does: length match. A
        # session with no net_file, or a mismatched one, just falls back
        # to None (the always-safe plain-vertex-pair/per-face-index
        # derivations).
        net_file_faces = (self._net_file_json or {}).get("faces")
        if net_file_faces is not None and len(net_file_faces) == len(self.base_faces):
            self.base_edges = (self._net_file_json or {}).get("edges")
            self.base_face_edge_ids = (self._net_file_json or {}).get("face_edge_ids")
            source_polygon_id = (self._net_file_json or {}).get("source_polygon_id")
        else:
            self.base_edges = None
            self.base_face_edge_ids = None
            source_polygon_id = None
        self.colors, self.color_by_group, self.group_of_base_face = _face_colors_by_group(
            len(self.base_faces), source_polygon_id)
        # Same layout decision as on_select_net (see its own comment): a
        # net_file carrying its own "net_layout" (e.g. one built and
        # connected in interactive_builder_app) reproduces THAT exact
        # arrangement for the "Net" panel next to Level 0, rather than
        # falling back to a fresh BFS layout that ignores how the user
        # actually arranged it.
        net_layout = (self._net_file_json or {}).get("net_layout")
        if net_layout is not None and (
                _net_layout_is_new_format(net_layout) or len(net_layout) == len(self.base_faces)):
            self.target_layout = _layout_from_net_layout(self.base_faces, net_layout)
            self.target_connections = (self._net_file_json or {}).get("builder_connections")
        else:
            self.target_layout = build_stretchy_net_layout(self.base_faces)
            self.target_connections = None

        self.subdivision_level = state.subdivision_level
        # Falls back to DEFAULT_PRESSURE when None -- a session saved mid-Computing genuinely
        # has no real pressure yet, and nothing downstream expects self.pressure_value itself
        # to be None (unlike level_history's own rms_stretch_pct, handled as a "--" sentinel).
        self.pressure_value = (state.pressure_value if state.pressure_value is not None
                                else DEFAULT_PRESSURE)
        self.iteration_count = state.iteration_count
        self.debug_mode = state.debug_mode
        self.tolerance_var.set(state.tolerance)
        for level, value in state.target_rms_pct.items():
            if level in self.target_rms_vars:
                self.target_rms_vars[level].set(value)
        self.last_stats = state.last_stats.model_dump()
        self.level_history = {level: rec.model_dump() for level, rec in state.level_history.items()}

        # Each panel's own camera view -- a rotation field falls back to _initial_level_
        # rotation() (this app's own non-axis-aligned default), not any baked-in quaternion,
        # when None (a session saved before this existed, or with no panel ever rotated).
        # Levels 1-3's own shared group reads the original "level_*" fields (an older,
        # pre-split session file's one shared camera maps onto this group); Level 0's own
        # independent group reads the newer "level0_*" fields, absent in an older file --
        # falling back to a fresh default for Level 0 specifically rather than the old file's
        # one shared camera. draw() below re-renders with all of these live.
        self._level13_camera = {
            "zoom": state.level_zoom,
            "pan": np.array(state.level_pan),
            "rotation": (Rotation.from_quat(state.level_rotation)
                         if state.level_rotation is not None
                         else self._initial_level_rotation()),
        }
        self._level0_camera = {
            "zoom": state.level0_zoom,
            "pan": np.array(state.level0_pan),
            "rotation": (Rotation.from_quat(state.level0_rotation)
                         if state.level0_rotation is not None
                         else self._initial_level_rotation()),
        }
        self.net_zoom = state.net_zoom
        self.net_pan = np.array(state.net_pan)

        self.level_snapshots = {}
        for level, level_state in state.levels.items():
            faces, positions, face_of_fine, edge_length = level_state.to_mesh()
            if level == state.subdivision_level:
                self.faces, self.positions, self.face_of_fine = faces, positions, face_of_fine
                if edge_length is not None:
                    self.edge_length = edge_length
            else:
                self.level_snapshots[level] = {"faces": faces, "positions": positions,
                                                "face_of_fine": face_of_fine}
        # Level 0/1 share their fan-triangulated topology -- only those levels can still have
        # an unsplit base rim edge worth disambiguating; None (the plain, always-safe
        # derivation) past that, same as _subdivide_step.
        self.edges = (_fan_level_edges(self.faces, self.base_edges)
                      if self.subdivision_level <= 1 else None)

        self.history_tree.delete(*self.history_tree.get_children())
        self.stop_event = None
        # A loaded session carries no captured Inflate frames (never part of SessionStateModel)
        # -- clears every level's replay slider rather than leaving some other net's own
        # trajectory scrubbable here.
        self._level_frames = {}
        self._level_scrub_index = {}
        for level in self.level_replay_sliders:
            self._update_replay_slider(level)
        self._auto_active = False
        self._auto_attempted_level = None
        self._apply_mode_visibility()
        self._refresh_history_table()
        self._update_level_action_buttons()
        self._update_auto_button()
        self.draw()
        # A loaded session can carry its own debug_mode, different from what was showing
        # before -- unlike a plain net reselection, this really is a mode change, so it gets
        # the same refit _on_toggle_debug_mode's explicit toggle does.
        self._refit_window_height()
        self._set_status(f"Session loaded from {os.path.basename(path)}.", "info")

    # ---- subdivide ----

    def _update_level_action_buttons(self):
        """Single source of truth for every level's one action button: only the current
        frontier level's button is ever enabled -- idle it reads "Relax" (level 0) or "Inflate"
        (levels 1+), once converged it becomes "Subdivide" or "DONE!" (MAX_LEVEL, disabled). A
        run in progress overrides this via _set_level_action_button_running instead -- this
        method is never called while one is active."""
        converged = bool(self.last_stats.get("converged"))
        for level, button in self.level_action_buttons.items():
            if level != self.subdivision_level or self.positions is None:
                # Not the current frontier -- reset its text too, not just its disabled state:
                # without this, a level that reached "DONE!" on a PREVIOUS net keeps showing it,
                # now stuck and disabled, after selecting a different net resets to level 0.
                button.config(text="Relax" if level == 0 else "Subdivide")
                button.state(["disabled"])
            elif not converged:
                label = "Relax" if level == 0 else "Inflate"
                command = self.on_relax_clicked if level == 0 else self.on_inflate_clicked
                button.config(text=label, command=command)
                button.state(["!disabled"])
            elif level < MAX_LEVEL:
                button.config(text="Subdivide", command=self.on_subdivide_clicked)
                button.state(["!disabled"])
            else:
                button.config(text="DONE!")
                button.state(["disabled"])

    def _subdivide_step(self):
        """The actual level-advancing work behind on_subdivide_clicked -- no status message or
        redraw of its own, caller reports/draws once itself. Only ever runs from Level 1
        upward (Level 0's own advance is a promotion, not a subdivide_once call -- see
        _finish_relax).

        Freezes the level being left into self.level_snapshots (its "Level N" panel stops
        updating from here on) using whatever state it had reached, before overwriting
        self.faces/positions/etc. with the new level's."""
        self.level_snapshots[self.subdivision_level] = {
            "faces": self.faces, "positions": self.positions,
            "face_of_fine": self.face_of_fine,
        }
        self.faces, self.positions, self.edge_length, self.face_of_fine = subdivide_once(
            self.faces, self.positions, self.edge_length, self.face_of_fine,
            self.subdivision_level, base_faces=self.base_faces,
            face_edge_ids=self.base_face_edge_ids)
        self.subdivision_level += 1
        # Level 2+'s own edges are always unambiguous -- self.edges (the Level 0/1-only
        # spring-edge override) has no reason to exist past this point.
        self.edges = None
        # This new level's own Target RMS spinner value, just for the history row recorded
        # below, before Inflate has even run once at this level yet.
        if self.subdivision_level in self.target_rms_vars:
            self._current_target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        # The face set just changed entirely -- recomputed fresh, same as a brand new net load.
        self.last_stats = self._compute_stretch_stats()
        # Each level's own step count starts over at 0 -- only meaningful counted from when
        # that level's mesh was first created, not carried over from a coarser level.
        self.iteration_count = 0
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        self._record_level_history()

    def on_subdivide_clicked(self):
        if self.positions is None or self.subdivision_level >= MAX_LEVEL:
            return
        self._subdivide_step()
        self._update_level_action_buttons()  # a fresh subdivision hasn't converged yet
        self._set_status(
            f"Subdivided to level {self.subdivision_level} ({len(self.faces)} faces, "
            f"{len(self.positions)} vertices, edges stretched up to "
            f"{self.last_stats['max_stretch_pct']:.2f}%). Press Inflate to relax/inflate "
            f"further.", "info")
        self.draw()

    # ---- convergence history table ----

    def _record_level_history(self):
        """Records/updates the current level's row: pressure last calibrated for it (None for
        Level 0, which has no pressure at all), steps so far this level, stretch stats, and
        the stopping-condition `optimality` -- all from self.last_stats, plus the "Simulation
        Time"/"Cumulative Time" columns' own backing state. Called on every subdivide/
        promotion, every live progress update, and when a run finishes, so the row always
        reflects the level's latest state rather than only its final converged one."""
        self.level_history[self.subdivision_level] = {
            "pressure": None if self.subdivision_level == 0 else self.pressure_value,
            "steps": self.iteration_count,
            "max_stretch_pct": self.last_stats.get("max_stretch_pct", 0.0),
            # No 0.0 fallback here -- None is a genuine, distinct "not known yet, still
            # computing" state, shown as "--" by _refresh_history_table.
            "rms_stretch_pct": self.last_stats.get("rms_stretch_pct"),
            "optimality": self.last_stats.get("optimality"),
            "converged": self.last_stats.get("converged"),
            # The gtol actually used to reach this reading -- not necessarily the tolerance
            # spinner's current value, which may have changed since. Falls back to
            # CONVERGENCE_GTOL for a row recorded before this field existed.
            "gtol": self.last_stats.get("gtol") or CONVERGENCE_GTOL,
            # Same idea as "gtol" above, for self._current_target_rms_pct -- None for Level 0.
            "target_rms_pct": (None if self.subdivision_level == 0
                                else self.last_stats.get("target_rms_pct")
                                or self._current_target_rms_pct),
            "precomp_time_s": self._current_precomp_time_s,
            "sim_time_s": self._current_sim_time_s,
            # False only for a level whose pressure calibration gave up without finding a
            # usable pressure (e.g. a mesh whose faces exactly cancel under pressure until a
            # later Subdivide gives it real degrees of freedom). Defaults True for Level 0 and
            # for a row recorded before this field existed.
            "pressure_found": self.last_stats.get("pressure_found", True),
        }
        self._refresh_history_table()

    @staticmethod
    def _format_sci(value, precision=2):
        """1.23e-05 -> "1.23e-5" (no leading zero on the exponent), matching the Convergence
        column's compact form. `precision=0` gives "1e-4" style for a fixed threshold."""
        mantissa, exponent = f"{value:.{precision}e}".split("e")
        return f"{mantissa}e{int(exponent)}"

    @staticmethod
    def _format_mmss(seconds):
        """None (phase hasn't run yet at this level) -> "--"; otherwise mm:ss, floored to the
        second -- minutes not capped at 59, so an hour-plus run reads as one growing number
        ("75:03") instead of wrapping back to "15:03"."""
        if seconds is None:
            return "--"
        total_seconds = int(seconds)
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def _rescale_history_columns(self, available_width):
        """Turns self._history_column_weights (proportions) into pixel widths that sum to
        `available_width` -- only the currently displayed columns share out that width
        (release vs. debug mode have different total weight). Bound to <Configure> and also
        called directly from _apply_mode_visibility, since a displaycolumns change alone
        doesn't fire <Configure>. `available_width` <= 1 (widget not laid out yet) is skipped;
        the real <Configure> once layout finishes calls this again."""
        if available_width <= 1:
            return
        # cget always returns a tuple -- displaycolumns="#all" reads back as ('#all',), not
        # the bare string, so this is checked against a tuple.
        displayed = self.history_tree.cget("displaycolumns")
        if displayed == ("#all",):
            displayed = self.history_tree.cget("columns")
        total_weight = sum(self._history_column_weights[col] for col in displayed)
        if total_weight <= 0:
            return
        for col in displayed:
            weight = self._history_column_weights[col]
            self.history_tree.column(
                col, width=max(1, round(available_width * weight / total_weight)))

    def _refresh_history_table(self):
        # "Cumulative Time" (see below) is a running total across rows in
        # LEVEL order -- levels are always visited 0, 1, 2, ... here (never
        # out of order), so a single running total carried across loop
        # iterations is exactly the right-to-left sum the column wants.
        cumulative_seconds = 0.0
        for level in sorted(self.level_history):
            rec = self.level_history[level]
            optimality = rec["optimality"]
            # A run actively in progress right now for this level colors its row yellow
            # ("running"), overriding the plain optimality-vs-gtol comparison below -- red
            # ("not_converged") is reserved for an actual failure (step cap or Stop), not just
            # "hasn't converged yet, still going". Gated on `optimality is None` too, not just
            # `self._level_running` (which stays True through the whole Inflate click,
            # including the purely-visual replay after a real result is already known) --
            # "running" means "still waiting on a result", which ends once `optimality` is
            # real, not once the animation finishes.
            running_now = (level == self.subdivision_level and self._level_running
                           and optimality is None)
            if optimality is None:
                # "--" covers both "never run at this level yet" and "actively computing".
                convergence, tags = "--", (("running",) if running_now else ())
            else:
                # The checkmark tracks the algorithm's own `converged` flag rather than
                # redoing the optimality-vs-gtol comparison here, kept as the single source of
                # truth in case they ever disagree again. This branch only ever shows two
                # colors: green ("converged", checkmark) or red ("not_converged", X) --
                # "--"/yellow is handled entirely by the `if` branch above.
                gtol = rec["gtol"]
                converged = rec["converged"]
                op = "<" if optimality < gtol else ">"
                mark = "✔" if converged else "✘"  # colored via row tag, not the glyph itself
                convergence = (f"{self._format_sci(optimality)} {op} "
                                f"{self._format_sci(gtol, precision=0)} {mark}")
                tags = ("converged",) if converged else ("not_converged",)
            # "--" for Level 0, the only level whose "pressure" is ever None (pure springs, no
            # pressure to calibrate).
            pressure_str = "--" if rec["pressure"] is None else f"{rec['pressure']:.2f}"
            # This row's own target_rms_pct (recorded at the time it was calibrated, not read
            # live from the spinner), so a level's row keeps showing what it was actually
            # chasing even after the spinner shows a different level's default. "--" while this
            # run's RMS isn't known yet (filled in the instant it's known, before replay
            # starts). Level 0 always shows "--" here regardless of its own last_stats value --
            # its RMS is still computed/stored, just never surfaced for this level's row.
            rms_str = ("--" if level == 0 or rec["rms_stretch_pct"] is None
                       else f"{rec['rms_stretch_pct']:.1f}")
            # "(target: ...)" is debug-mode-only.
            if self.debug_mode and level != 0 and rec.get("target_rms_pct") is not None:
                rms_str += f" (target: {rec['target_rms_pct']:.1f})"
            # "Simulation Time": Precomp + Sim -- except Level 0, which has no precomputation
            # at all, so its row shows just Sim, and Level 1+, which has no separate Sim phase
            # (pressure calibration's own winning trial IS the Inflate result), so its row
            # shows just Precomp. A row loaded from an older session could still show both;
            # that case shows whichever mm:ss values are present, "--" if neither.
            precomp_s = rec.get("precomp_time_s")
            sim_s = rec.get("sim_time_s")
            if precomp_s is not None and sim_s is not None:
                sim_time_str = f"{self._format_mmss(precomp_s)} + {self._format_mmss(sim_s)}"
            elif precomp_s is not None:
                sim_time_str = self._format_mmss(precomp_s)
            elif sim_s is not None:
                sim_time_str = self._format_mmss(sim_s)
            else:
                sim_time_str = self._format_mmss(None)
            # "Cumulative Time": running total of every row's own Simulation Time seconds so
            # far -- a level that hasn't run yet contributes 0, not "n/a", since the running
            # total up to it is still a real, known number.
            cumulative_seconds += (precomp_s or 0.0) + (sim_s or 0.0)
            cumulative_str = self._format_mmss(cumulative_seconds)
            values = (level, pressure_str, rec["steps"], f"{rec['max_stretch_pct']:.2f}",
                      rms_str, sim_time_str, cumulative_str, convergence)
            iid = str(level)
            if self.history_tree.exists(iid):
                self.history_tree.item(iid, values=values, tags=tags)
            else:
                self.history_tree.insert("", "end", iid=iid, values=values, tags=tags)

    def _compute_stretch_stats(self):
        """max/rms edge stretch of the current self.faces/self.positions against
        self.edge_length -- the same stats relax_once/relax_initial_configuration report,
        computed directly for a mesh that hasn't been relaxed yet (a fresh random start, or
        freshly-interpolated positions right after a Subdivide click)."""
        edges = mesh_edges(self.faces, self.edges)
        rest = (np.array([self.edge_length[e] for e in edges])
                if isinstance(self.edge_length, dict) else self.edge_length)
        lengths = np.array([np.linalg.norm(self.positions[a] - self.positions[b])
                             for a, b in edges])
        stretch_pct = 100 * (lengths - rest) / rest
        return {"max_stretch_pct": float(np.max(np.abs(stretch_pct))),
                "rms_stretch_pct": float(np.sqrt(np.mean(stretch_pct ** 2))),
                "optimality": None, "converged": None}

    # ---- inflate ----

    def _update_mode_state(self):
        self.steps_spin.state(["!disabled"] if self.iterate_mode_var.get() == "steps"
                               else ["disabled"])

    def _register_numeric_entry(self, entry, allow_exponent, allow_decimal=True):
        """Restricts `entry` to numeric-looking input as it's typed -- Tk's `validate="key"`
        fires before a keystroke is accepted, with `%P` the field's value as it would read if
        the keystroke goes through; returning False rejects it outright, so this never fights
        the user's cursor position the way a post-hoc correction would. `allow_exponent`
        permits an "e"/"E" exponent, for tolerance's scientific-notation text (e.g. "1e-03").
        `allow_decimal` permits a "." -- target RMS entries pass False (whole numbers only)."""
        vcmd = self.root.register(lambda proposed: self._is_valid_numeric_partial(
            proposed, allow_exponent, allow_decimal))
        entry.configure(validate="key", validatecommand=(vcmd, "%P"))

    @staticmethod
    def _is_valid_numeric_partial(proposed, allow_exponent, allow_decimal=True):
        """True if `proposed` is a full number or a prefix a user could still be typing toward
        one (e.g. "", "-", ".", "1.", "1e", "1e-" when `allow_exponent`) -- accepting these
        in-progress states, not just a complete `float()`-parseable string, lets a user type a
        negative number or decimal point without the first keystroke being rejected."""
        digits = r"\d*\.?\d*" if allow_decimal else r"\d*"
        pattern = f"-?{digits}(?:[eE][-+]?\\d*)?" if allow_exponent else f"-?{digits}"
        return re.fullmatch(pattern, proposed) is not None

    def _begin_edit_target_rms(self, level):
        """<FocusIn> on a target-RMS entry: swaps its displayed "N%" for the bare number alone
        -- the "%" is shown once a number's been entered, not something typed."""
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}")

    def _sync_target_rms_display(self, level):
        """Reformats a target-RMS entry's displayed text as "N%" from its own underlying var --
        fires on every write to that var, from anywhere, so the "%" suffix is never left stale
        after a change that didn't go through this entry."""
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}%")

    def _commit_target_rms_entry(self, level, _event=None):
        """<Return>/<FocusOut> on a target-RMS entry: clamps whatever got typed into [0, 100],
        rounded to the nearest whole number (out-of-range values truncated to the nearest
        extreme, not rejected), or falls back to this level's default if unparseable. Setting
        `self.target_rms_vars[level]` (not the display var directly) is what triggers
        _sync_target_rms_display to put the "%" back."""
        try:
            value = round(float(self.target_rms_display_vars[level].get()))
        except (tk.TclError, ValueError):
            value = LEVEL_DEFAULT_TARGET_RMS_PCT[level]
        self.target_rms_vars[level].set(max(0, min(100, value)))

    def _on_target_rms_changed(self, level):
        # Only the current frontier level's own spinner invalidates a "converged" verdict --
        # editing some other level's target doesn't affect the pressure just calibrated here.
        if level == self.subdivision_level and self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_level_action_buttons()

    def _on_tolerance_changed(self, *_args):
        # Same rationale as _on_target_rms_changed: a "converged" verdict only applies to the
        # tolerance it was reached under.
        if self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_level_action_buttons()

    def _get_tolerance(self):
        """Parses self.tolerance_var's text (e.g. "1e-03") as a float -- a StringVar so it can
        always display in scientific notation -- falling back to DEFAULT_TOLERANCE for anything
        unparseable (e.g. a momentarily-empty field mid-edit)."""
        try:
            return float(self.tolerance_var.get())
        except ValueError:
            return DEFAULT_TOLERANCE

    def _guess_pressure_from_history(self, target_rms_pct):
        """Estimates the pressure to hand estimate_pressure_for_target_stretch as its own
        starting guess, drawing on already-calibrated prior levels' history instead of
        falling back to the generic per-solid-derived constant. Looks at every prior level's
        (pressure, achieved rms_stretch_pct) pair and picks whichever one's achieved stretch
        landed closest to the new target -- scaling that record's pressure by 2 per level of
        resolution difference (each Subdivide roughly doubles resolution, and empirically
        needs ~2x the pressure for the same target RMS stretch %).

        Deliberately not a `target_rms_pct / achieved` rescale -- that ratio explodes when a
        level's achieved stretch is ~0 (pressure genuinely had no effect there, e.g. a mesh
        whose faces cancel out under pressure until a later Subdivide gives it real degrees
        of freedom), producing an absurd guess that overflows the solver. Picking the
        closest-achieved record instead never divides by anything.

        A level whose record has `pressure_found` False is skipped entirely -- its "pressure"
        never came from a real calibration (the search gave up because the mesh was
        unresponsive to pressure there), so it's not a usable extrapolation point.

        Returns None (falling back to the generic guess) if no level below the current
        frontier has a usable recorded pressure/stretch pair yet."""
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

    def on_inflate_clicked(self):
        """Calibrates a pressure for the current "Target RMS stretch" (via _run_background --
        see _on_pressure_calibrated) and, once found, that's the whole run -- no separate
        second relax_once call at the winning pressure. estimate_pressure_for_target_stretch
        itself captures the winning trial's own frames (capture_frames=True) and
        _on_pressure_calibrated replays those (_start_frame_replay) once calibration lands on
        a pressure -- same visual result, zero recomputation.

        While calibration is searching, this level's panel shows an animated "Computing..."
        placeholder instead of a live redraw -- most calibration trials are thrown away, so
        there's no single meaningful shape to show frame-by-frame until it finishes. Level 0's
        Relax has no such phase and keeps redrawing live throughout.

        Recalibrates fresh from wherever self.positions currently is on every click, since the
        user can't set pressure directly. Calibrates against the current Tolerance spinner
        value too. The search's starting pressure comes from _guess_pressure_from_history when
        a usable prior level exists, falling back to the generic guess otherwise.

        self.stop_event is created and the frontier button turned into "Stop" here, before
        calibration even starts -- Stop needs a stop_event in place from the start, or
        clicking it during a slow calibration search (which can run up to max_iterations *
        max_nfev_per_trial steps) has nothing to interrupt."""
        if self.positions is None or self.last_stats.get("converged"):
            return
        faces, edge_length, positions = self.faces, self.edge_length, self.positions
        target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        # Captured here too, not just at the level-default sites, in case the user edited the
        # spinner away from that default before clicking Inflate.
        self._current_target_rms_pct = target_rms_pct
        tolerance = self._get_tolerance()
        initial_pressure_guess = self._guess_pressure_from_history(target_rms_pct)
        self.stop_event = threading.Event()
        # Marks the start of the "Precomp time" column's phase, consumed (as
        # self._current_precomp_time_s) in _on_pressure_calibrated. Level 1+ has no separate
        # "Sim time" phase -- all of a Level 1+ row's Simulation Time is "Precomp" now.
        self._precomp_start_time = time.perf_counter()
        # Read by _on_calibration_progress, which fires from a _run_background poll tick, not
        # a call this method's own local scope survives until -- has to live on self.
        self._precomp_base_iteration_count = self.iteration_count
        # Snapshot to restore if this run gets Stopped, and blank "RMS Stretch %", "Pressure",
        # and "Convergence" to "--" for the duration of this run -- without this the row would
        # keep showing stale data from the previous run's own result, looking current when
        # it isn't. `optimality=None` is what actually blanks "Convergence" --
        # _refresh_history_table already treats None there as "no result yet"; `converged`/
        # `gtol` don't need resetting since the display logic never reads them while
        # optimality is None.
        self._pre_computing_last_stats = dict(self.last_stats)
        self._pre_computing_pressure_value = self.pressure_value
        self.last_stats = {**self.last_stats, "rms_stretch_pct": None, "optimality": None}
        self.pressure_value = None
        self._record_level_history()
        self._set_level_action_button_running(True)
        self._start_computing_animation(self.subdivision_level)
        self._set_status(f"Finding a pressure that settles around {target_rms_pct:.1f}% "
                          "RMS stretch...", "info")
        self._run_background(
            lambda queue_progress: estimate_pressure_for_target_stretch(
                positions, faces, edge_length,
                target_rms_pct=target_rms_pct,
                gtol=tolerance,
                rng=None,
                stop_event=self.stop_event,
                initial_pressure_guess=initial_pressure_guess,
                capture_frames=True,
                on_progress=queue_progress,
                edges=self.edges),
            lambda result: self._on_pressure_calibrated(result, self._precomp_base_iteration_count),
            on_progress=self._on_calibration_progress)

    def _on_calibration_progress(self, cumulative_steps):
        """Live "Steps" column update while pressure calibration is computing.
        `cumulative_steps` is estimate_pressure_for_target_stretch's own running total across
        every trial attempted (not reset per trial -- a counter dropping backwards on each new
        trial would read as broken). Not necessarily the same number the row ends up showing
        once calibration finishes -- _on_pressure_calibrated snaps self.iteration_count to the
        true final steps_taken the instant the real result comes back, before replay starts,
        so any mismatch is a single, one-time correction at the Computing-to-Replay
        transition."""
        self.iteration_count = self._precomp_base_iteration_count + cumulative_steps
        self._record_level_history()

    def _on_pressure_calibrated(self, result, base_iteration_count):
        if self.stop_event is not None and self.stop_event.is_set():
            # Stopped during calibration itself -- its own trial positions are discarded
            # regardless of how it ends, so there's nothing from `result` to apply; just
            # report it the same way a stopped run would. Restores this level's own normal
            # panel (self.positions/faces are unchanged from before this click).
            self._stop_computing_animation()
            self._set_level_action_button_running(False)
            self._set_status(
                f"Stopped (during pressure calibration at level "
                f"{self.subdivision_level}).", "warn")
            # No real result to show -- restore "RMS Stretch %"/"Pressure" (blanked to "--" at
            # the start of this click) back to whatever they genuinely were before this run.
            self.last_stats = self._pre_computing_last_stats
            self.pressure_value = self._pre_computing_pressure_value
            self._record_level_history()
            self.draw()
            self._auto_step()  # no-op unless Auto is what actually drove this run
            return
        (pressure, new_positions, steps_taken, max_stretch, rms_stretch,
         optimality, converged, frames, pressure_found) = result
        self.pressure_value = pressure
        # "Precomp time": calibration has no progress callback of its own to update this live,
        # so it's set once here, the moment it finishes.
        self._current_precomp_time_s = time.perf_counter() - self._precomp_start_time
        # Captured once here, not re-read live during the run, and reused by
        # _finish_frame_replay so the recorded outcome shows the same threshold it actually
        # converged against, even if the spinner's value changes later.
        self._current_gtol = self._get_tolerance()
        self._stop_computing_animation()
        # _run_background's completion just re-synced every control, including the frontier
        # button, back to its normal state -- re-disable them and turn the frontier button
        # back into "Stop" for the replay about to start (Stop during replay just skips to
        # the final frame).
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self._set_status(f"Replaying the winning trial at pressure {pressure:.2f}...", "info")
        # Snaps "Steps" and the Convergence History row's stretch/Convergence columns to their
        # true final values the instant the real result is known, rather than waiting for
        # replay (which can take a while at REPLAY_FPS) to finish. self.positions is
        # deliberately NOT updated yet -- that stays whatever _replay_step shows, frame by
        # frame, until the animation reaches the end.
        self.iteration_count = base_iteration_count + steps_taken
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged,
                            "gtol": self._current_gtol,
                            "target_rms_pct": self._current_target_rms_pct,
                            "pressure_found": pressure_found}
        self._record_level_history()
        final_result = (new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged)
        # Made available for manual scrubbing right away, defaulted to the true final frame --
        # not gated on the auto-played animation finishing, so the slider is usable the instant
        # a result exists, even while that animation is still playing.
        self._level_frames[self.subdivision_level] = frames
        self._level_scrub_index[self.subdivision_level] = len(frames) - 1
        self._update_replay_slider(self.subdivision_level)
        self._start_frame_replay(frames, final_result, base_iteration_count)

    # Target frames per second during a replay -- purely a display rate for an already-
    # finished trial's own positions, fast enough to read as "watching it happen" without
    # dragging out a recap. A ceiling, not a guarantee: each tick still pays the real cost of
    # rendering one "Level N" panel, which can exceed REPLAY_FRAME_INTERVAL_MS on a dense mesh
    # -- _replay_step schedules the next tick only after the current render finishes, so a
    # slow render just means fewer actual fps that tick, never a backlog.
    REPLAY_FPS = 30
    REPLAY_FRAME_INTERVAL_MS = round(1000 / REPLAY_FPS)
    # Advances this many CAPTURED frames (each already CONVERGENCE_CHECK_INTERVAL=200 physics
    # steps apart) per tick, not 1 -- effectively plays the same captured sequence back ~4x
    # faster in wall-clock time than one-frame-per-tick would, while still ticking at a smooth
    # 30fps -- skips frames outright rather than raising REPLAY_FPS further, which would only
    # make each individual render (the real bottleneck) more likely to fall behind.
    REPLAY_FRAME_STRIDE = 4

    def _start_frame_replay(self, frames, final_result, base_iteration_count):
        """Plays back estimate_pressure_for_target_stretch's own captured `frames` (the
        winning trial's `(positions, steps_taken)` pairs every CONVERGENCE_CHECK_INTERVAL
        steps, including its own convergence top-up) at REPLAY_FPS -- a purely visual recap of
        an already-finished run; no physics runs here, and neither a timer nor
        `iteration_count` moves during it ("Steps" already advanced during the actual
        simulation via _on_calibration_progress, snapped to its true final value by
        _on_pressure_calibrated before this is even called). The bottom-of-panel message shows
        "Replaying" + a 0-3-dot cycle through _replay_step, clearing once done.
        `final_result` is only actually applied once the replay reaches its last frame
        (_finish_frame_replay) -- every frame in between is display-only, self.positions
        temporarily set to it just so draw() shows it."""
        self._replay_frames = frames
        self._replay_index = 0
        self._replay_final_result = final_result
        self._replay_base_iteration_count = base_iteration_count
        self._replay_step()

    def _replay_step(self):
        # A Stop click during replay jumps straight to the final frame -- no live physics left
        # to interrupt, just an animation, so skipping ahead is more useful than finishing the
        # recap the user already asked to cut short.
        skip_ahead = self.stop_event is not None and self.stop_event.is_set()
        total = len(self._replay_frames)
        if self._replay_index < total and not skip_ahead:
            positions, _steps_taken = self._replay_frames[self._replay_index]
            self.positions = positions
            # Dot count derived from wall-clock time, not a replay-tick counter --
            # REPLAY_FRAME_INTERVAL_MS (~33ms) is far faster than a readable dot-cycle, so
            # ticking once per replay frame would flicker; time.perf_counter() gives the same
            # ~500ms-per-dot pace _tick_computing_animation uses, no separate timer needed.
            dots = int(time.perf_counter() / (self.COMPUTING_DOT_INTERVAL_MS / 1000)) % 4
            self._set_level_message(self.subdivision_level, "Replaying" + "." * dots)
            # Only this level's own panel changes frame to frame -- a full draw() (Net plus
            # every "Level N" panel) measured ~0.5s on a mid-size net, far slower than
            # REPLAY_FRAME_INTERVAL_MS, since it'd re-render three unrelated, unchanged panels
            # every tick. _draw_level_panel alone keeps replay running near REPLAY_FPS.
            self._draw_level_panel(self.subdivision_level, self.faces,
                                    self.positions, self.face_of_fine)
            # Advances by REPLAY_FRAME_STRIDE captured frames, not 1 -- clamped so the last
            # captured frame always gets its own tick even when the stride would otherwise
            # jump past it, rather than silently skipping straight from an earlier frame.
            if self._replay_index >= total - 1:
                self._replay_index = total  # just showed the last frame -- next tick ends it
            else:
                self._replay_index = min(self._replay_index + self.REPLAY_FRAME_STRIDE, total - 1)
            self._replay_after_id = self.root.after(self.REPLAY_FRAME_INTERVAL_MS,
                                                       self._replay_step)
        else:
            self._replay_after_id = None
            self._finish_frame_replay()

    def _finish_frame_replay(self):
        # A Stop click can only ever reach here meaning "skip the replay animation" -- a Stop
        # that actually interrupted the real computation is caught earlier, in
        # _on_pressure_calibrated's own stop_event branch, which returns before a replay
        # starts. By the time this runs, the winning trial's result is already final
        # regardless of whether the animation played in full -- clearing stop_event here
        # keeps the "Stopped"/"Converged" status message honest.
        self.stop_event = None
        new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged = (
            self._replay_final_result)
        self.positions = new_positions
        # iteration_count/last_stats are already set to these exact values by
        # _on_pressure_calibrated, before replay even started
        # (see _start_frame_replay's own docstring) -- reassigned here
        # anyway for robustness/symmetry with the rest of this method's
        # own final-state bookkeeping, not because replay itself changed
        # them.
        self.iteration_count = self._replay_base_iteration_count + steps_taken
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged,
                            "gtol": self._current_gtol,
                            "target_rms_pct": self._current_target_rms_pct,
                            # Already set by _on_pressure_calibrated, before replay even
                            # started -- carried over rather than dropped by this reassignment.
                            "pressure_found": self.last_stats.get("pressure_found", True)}
        self._record_level_history()
        self._set_level_message(self.subdivision_level, "")  # clears once replay is done
        self.draw()
        self._finish_inflate()

    def _update_replay_slider(self, level):
        """Configures level `level`'s own replay scrubber to match self._level_frames[level] --
        the slider's range spans every captured frame index, enabled iff at least 2 frames
        exist. Also re-syncs the slider's displayed position to self._level_scrub_index[level]
        -- `ttk.Scale.set` DOES fire `command`, so this harmlessly re-triggers
        _on_replay_slider_moved with the same index it was already at -- idempotent (redraws
        the same already-current frame), not a real scrub action."""
        slider = self.level_replay_sliders.get(level)
        if slider is None:
            return
        frames = self._level_frames.get(level)
        if not frames or len(frames) < 2:
            slider.configure(to=0)
            slider.set(0)
            slider.state(["disabled"])
            return
        slider.configure(from_=0, to=len(frames) - 1)
        slider.state(["!disabled"])
        slider.set(self._level_scrub_index.get(level, len(frames) - 1))

    def _on_replay_slider_moved(self, level, value):
        """`command` callback for level `level`'s replay scrubber -- `value` is ttk.Scale's
        string-formatted float, rounded to the nearest captured frame index (clamped, since a
        Scale can report a value fractionally past its `to` during a fast drag). Purely a
        display override: updates self._level_scrub_index[level] and redraws just this panel,
        without touching self.positions/self.level_snapshots -- scrubbing never affects what
        the next real Inflate/Subdivide click continues from."""
        frames = self._level_frames.get(level)
        if not frames:
            return
        idx = max(0, min(int(round(float(value))), len(frames) - 1))
        self._level_scrub_index[level] = idx
        if level == self.subdivision_level:
            faces, face_of_fine = self.faces, self.face_of_fine
        elif level in self.level_snapshots:
            snap = self.level_snapshots[level]
            faces, face_of_fine = snap["faces"], snap["face_of_fine"]
        else:
            return
        self._draw_level_panel(level, faces, frames[idx][0], face_of_fine)

    def _set_level_action_button_running(self, running):
        """Neither mode has a separate Stop button -- the current frontier level's own action
        button turns into the Stop control for the duration of a run, then back to its normal
        Inflate/Relax/Subdivide/DONE! state once it finishes (delegated to
        _update_level_action_buttons). Safe to assume the frontier level doesn't change
        mid-run: every other level's button is disabled for the whole run too, and Relax's own
        promotion only happens in _finish_relax, after the run is over."""
        self._level_running = running
        self._refresh_history_table()
        button = self.level_action_buttons.get(self.subdivision_level)
        if button is None:
            return
        if running:
            button.config(text="Stop", command=self.on_stop_clicked)
            button.state(["!disabled"])
        else:
            self._update_level_action_buttons()

    def on_stop_clicked(self):
        if self.stop_event is not None:
            self.stop_event.set()
            frontier_button = self.level_action_buttons.get(self.subdivision_level)
            if frontier_button is not None:
                frontier_button.state(["disabled"])  # one request is enough; avoid repeat clicks
            self._set_status("Stopping...", "warn")
        # A per-level Stop clicked directly while an Auto sequence is running must ALSO halt
        # the sequence -- otherwise _auto_step would just start the next step right back up.
        self._abort_auto()

    # ---- "Auto": Relax -> Inflate -> Subdivide -> ... -> Level MAX_LEVEL ----

    def on_auto_clicked(self):
        """Runs the whole pipeline unattended: Relax at Level 0, then Inflate/Subdivide/.../
        Level MAX_LEVEL -- see _auto_step, which drives one step at a time and decides what
        "next" means at any given moment. Disabled whenever a net isn't loaded or any run is
        already in progress."""
        if self.positions is None or self._auto_active:
            return
        self._auto_active = True
        self._auto_attempted_level = None
        self._update_auto_button()
        self._auto_step()

    def on_auto_stop_clicked(self):
        """The Auto button's own command while a sequence is running -- ends the sequence and
        interrupts whatever Relax/Inflate step is currently mid-run, via the same stop_event
        on_stop_clicked already uses."""
        self._abort_auto()
        self.on_stop_clicked()

    def _abort_auto(self):
        """Ends an in-progress Auto sequence without touching whatever Relax/Inflate run might
        currently be underway -- also called from every worker-thread failure path that would
        otherwise leave self._auto_active stuck True with the button showing "Stop Simulation"
        for a sequence that's already silently dead. A no-op if Auto isn't running."""
        if self._auto_active:
            self._auto_active = False
            self._update_auto_button()

    def _update_auto_button(self):
        """Single source of truth for the Auto button: idle it reads "Run Simulation", enabled
        only once a net is loaded -- otherwise disabled like every other control while any run
        is in progress. While Auto itself is driving a run, it instead reads "Stop Simulation"
        and is explicitly RE-ENABLED regardless of what _set_controls_enabled(False) just did
        -- the same "frontier button survives the blanket disable" pattern
        _set_level_action_button_running uses, so the one control that can interrupt a
        multi-step Auto sequence stays clickable throughout."""
        if self._auto_active:
            self.auto_button.config(text="Stop Simulation", command=self.on_auto_stop_clicked)
            self.auto_button.state(["!disabled"])
        else:
            self.auto_button.config(text="Run Simulation", command=self.on_auto_clicked)
            self.auto_button.state(["!disabled"] if self.positions is not None else ["disabled"])

    def _auto_step(self):
        """Decides what Auto should do next, called once from on_auto_clicked to kick the
        sequence off and again from the tail of _finish_relax/_finish_inflate every time a
        step it started finishes -- a no-op whenever Auto isn't active.

        - Level 0, not yet converged: Relax -- exactly one attempt per level, no retries (a
          non-converged attempt just runs its own single relax call up to its own large step
          budget -- see INFLATE_SAFETY_STEP_CAP -- rather than Auto stopping short and
          starting a fresh one). If _auto_attempted_level already names this level, declare
          failure and stop Auto rather than trying again.
        - Level 0, converged: _finish_relax has already promoted to Level 1 unconditionally
          by the time this runs, so there's nothing left to do here.
        - Current level converged, below MAX_LEVEL: Subdivide, then immediately re-enter this
          function rather than waiting for a callback Subdivide itself never schedules
          (synchronous, unlike Relax/Inflate).
        - Current level converged, at MAX_LEVEL: done.
        - Current level not converged: same one-attempt-then-stop rule as Level 0, via Inflate."""
        if not self._auto_active:
            return
        if self.last_stats.get("converged"):
            self._auto_attempted_level = None
            if self.subdivision_level == 0:
                return  # _finish_relax already promoted to Level 1
            if self.subdivision_level < MAX_LEVEL:
                self.on_subdivide_clicked()
                self._auto_step()
            else:
                self._auto_active = False
                self._update_auto_button()
                self._set_status(f"Auto: reached Level {MAX_LEVEL} and converged.", "success")
            return
        if self._auto_attempted_level == self.subdivision_level:
            self._auto_active = False
            self._update_auto_button()
            self._set_status(
                f"Auto: Level {self.subdivision_level} still hasn't converged after one "
                f"attempt (up to {INFLATE_SAFETY_STEP_CAP} steps) -- stopping the automatic "
                f"sequence (Inflate/Relax are still available to keep trying by hand).", "warn")
            return
        self._auto_attempted_level = self.subdivision_level
        if self.subdivision_level == 0:
            self.on_relax_clicked()
        else:
            self.on_inflate_clicked()

    def _run_chunked_relax_stream(self, relax_fn, target_steps, stop_event, on_progress, on_finished):
        """Driver behind _run_relax_stream (Level 0's own Relax, its only remaining caller --
        Inflate's own equivalent was removed since pressure calibration's winning trial IS the
        Inflate result now, replayed from cached frames rather than recomputed). Calls
        `relax_fn(max_nfev, stop_event, queue_progress) -> result` once, in a background
        thread -- `max_nfev` is `target_steps` for "iterate for N steps" mode, or
        INFLATE_SAFETY_STEP_CAP otherwise (a single call already runs to real convergence or
        that cap on its own).

        No app-side chunking here -- relax_once/relax_initial_configuration accept
        `on_progress` directly and call it themselves every CONVERGENCE_CHECK_INTERVAL steps,
        exactly the cadence the stopping condition is itself checked at, so the UI redraws in
        sync with real convergence checks rather than an unrelated schedule. `queue_progress`
        bridges that callback (called from the background thread) to this queue/poll
        mechanism; Tk isn't thread-safe, so the worker only pushes to the queue, and the main
        thread (via the scheduled poll below) is the only one that touches Tk widgets."""
        q = queue.Queue()

        def queue_progress(*result):
            q.put(("progress", result))

        def worker():
            try:
                max_nfev = target_steps if target_steps is not None else INFLATE_SAFETY_STEP_CAP
                result = relax_fn(max_nfev, stop_event, queue_progress)
                q.put(("progress", result))
                q.put(("final", None))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            # Drains the whole queue every cycle, but coalesces "progress" messages down to
            # the latest one instead of calling on_progress once per queued message. If
            # physics runs faster than a single redraw, the worker thread can queue several
            # progress messages before poll() next runs -- older ones are immediately
            # superseded and would just be wasted render time. This is what avoids a
            # stall-then-jump: rendering every queued message, oldest first, would let a
            # backlog grow (each render taking longer than the interval it's trying to keep up
            # with) until the display caught up all at once; skipping to whatever's newest
            # each cycle keeps poll() itself fast, so "Simulation Time" and the panel stay
            # genuinely live.
            latest_progress = None
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        latest_progress = payload
                        continue
                    if latest_progress is not None:
                        on_progress(latest_progress)
                        latest_progress = None
                    if kind == "final":
                        on_finished()
                        return
                    elif kind == "error":
                        self._set_controls_enabled(True)
                        self._set_status(f"Failed: {payload}", "error")
                        self._abort_auto()  # nothing left to call _auto_step from otherwise
                        return
            except queue.Empty:
                if latest_progress is not None:
                    on_progress(latest_progress)
                else:
                    # Ticks "Simulation Time"/"Cumulative Time" live between actual progress
                    # events -- Level 0's own on_progress only fires every
                    # CONVERGENCE_CHECK_INTERVAL steps, which can leave the displayed time
                    # frozen for a while otherwise (same wall-clock-not-solver-progress idea
                    # _run_background's own poll loop uses for "Precomp time").
                    self._current_sim_time_s = time.perf_counter() - self._sim_start_time
                    self._record_level_history()
            self.root.after(80, poll)

        self.root.after(80, poll)

    def _finish_inflate(self):
        """Tail end of an Inflate click, called once _finish_frame_replay has already applied
        the winning calibration trial's final result to self.positions/last_stats/
        iteration_count -- this method only reports it (no `_current_sim_time_s` update here:
        Level 1+ has no separate "Sim" phase; all of a Level 1+ row's Simulation Time is
        "Precomp", already finalized in _on_pressure_calibrated)."""
        self._set_controls_enabled(True)
        self._set_level_action_button_running(False)
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        converged = self.last_stats.get("converged")
        max_stretch = self.last_stats.get("max_stretch_pct", 0.0)
        rms_stretch = self.last_stats.get("rms_stretch_pct", 0.0)
        self._record_level_history()
        if was_stopped:
            self._set_status(
                f"Stopped ({self.iteration_count} steps at level {self.subdivision_level}): "
                f"edges stretched up to {max_stretch:.2f}% from rest length "
                f"(RMS {rms_stretch:.1f}%).", "warn")
        elif converged:
            self._set_status(
                f"Converged after {self.iteration_count} steps at level "
                f"{self.subdivision_level}: edges stretched up to {max_stretch:.2f}% from rest "
                f"length (RMS {rms_stretch:.1f}%).", "success")
        else:
            self._set_status(
                f"Inflated ({self.iteration_count} steps at level {self.subdivision_level}, "
                f"step cap reached): edges stretched up to {max_stretch:.2f}% from rest length "
                f"(RMS {rms_stretch:.1f}%).",
                "info")
        self._auto_step()  # no-op unless Auto is what actually drove this run

    # ---- relax (Level 0 only) ----

    def on_relax_clicked(self):
        """Level 0's analogue of on_inflate_clicked -- no pressure to calibrate first (pure
        springs), so this goes straight to the streamed run. Always runs to convergence
        (ignores the debug-mode steps-vs-convergence choice, which only applies to Inflate) --
        Relax's whole point is to finish the initial-configuration algorithm, not to be
        steppable."""
        if self.positions is None or self.subdivision_level != 0 or self.last_stats.get("converged"):
            return
        # Same capture-once rationale as _on_pressure_calibrated -- see self._current_gtol.
        self._current_gtol = self._get_tolerance()
        self.stop_event = threading.Event()
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self._set_status("Relaxing random start into a well-separated shape...", "info")
        # Level 0 has no pressure-calibration phase -- "Precomp time" stays "--"; only "Sim
        # time" applies here, starting now.
        self._sim_start_time = time.perf_counter()
        self._run_relax_stream(self.stop_event)

    def _run_relax_stream(self, stop_event):
        faces, edge_length = self.faces, self.edge_length
        gtol = self._current_gtol
        # KICK_WINDOW's random-perturbation mechanism is disabled here -- found to interact
        # badly with a genuinely slow (not stuck) relaxation, re-disturbing the mesh right as
        # it converges. See LEVEL0_STEP_MAX_MULTIPLIER in stretchy_mesh.py.
        rng = None
        # relax_initial_configuration's own `nfev`/`steps_taken` is the cumulative count for
        # this one call, but self.iteration_count needs to keep accumulating across separate
        # Relax clicks at Level 0 too (reset only on promotion) -- so this call's own
        # contribution is `base_iteration_count + nfev`, not nfev alone.
        base_iteration_count = self.iteration_count

        def relax_fn(max_nfev, stop_event, on_progress):
            return relax_initial_configuration(self.positions, faces, edge_length,
                                                max_nfev=max_nfev, stop_event=stop_event,
                                                gtol=gtol, rng=rng, on_progress=on_progress,
                                                edges=self.edges)

        self._run_chunked_relax_stream(relax_fn, None, stop_event,
                                        lambda result: self._apply_relax_progress(result, base_iteration_count),
                                        self._finish_relax)

    def _apply_relax_progress(self, result, base_iteration_count):
        positions, nfev, max_stretch, rms_stretch, optimality, converged = result
        self.positions = positions
        self.iteration_count = base_iteration_count + nfev
        # optimality/converged are stashed here, NOT written into self.last_stats -- Level 0's
        # own Convergence column shows "--" for the whole time Relax is running, same
        # "--"-while-unknown sentinel Level 1-3's Computing phase uses, via
        # last_stats["optimality"] staying None throughout. _finish_relax reveals it, reading
        # the real final value back from here.
        self._pending_relax_stats = {"optimality": optimality, "converged": converged}
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": None, "converged": None,
                            "gtol": self._current_gtol}
        self._current_sim_time_s = time.perf_counter() - self._sim_start_time
        self._record_level_history()
        self._set_status(f"Relaxing... {self.iteration_count} steps so far "
                          f"(edges stretched up to {max_stretch:.2f}%).", "info")
        # Only Level 0's own panel actually changes here -- a full draw() (Net panel plus
        # every "Level N" panel) is slower than _run_chunked_relax_stream's own 80ms poll
        # interval, which would make "Simulation Time" appear to stall then jump (each
        # already-due `after()` callback gets queued up behind an overlong draw() and
        # processed in one burst once it returns, instead of promptly). Same root cause fixed
        # for Inflate's own replay (_replay_step) -- a targeted _draw_level_panel call keeps
        # each progress tick cheap enough to reach the screen promptly.
        self._draw_level_panel(0, self.faces, self.positions, self.face_of_fine)

    def _finish_relax(self):
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        # Reveals the real optimality/converged now -- see _apply_relax_progress for why these
        # were stashed separately rather than kept live in self.last_stats. Applies regardless
        # of how this run ended (converged, Stopped, or step-cap).
        pending = getattr(self, "_pending_relax_stats", {})
        self.last_stats["optimality"] = pending.get("optimality")
        self.last_stats["converged"] = pending.get("converged")
        converged = self.last_stats.get("converged")
        max_stretch = self.last_stats.get("max_stretch_pct", 0.0)
        rms_stretch = self.last_stats.get("rms_stretch_pct", 0.0)
        self._current_sim_time_s = time.perf_counter() - self._sim_start_time
        self._record_level_history()
        if was_stopped:
            self._set_status(
                f"Stopped ({self.iteration_count} relax steps): edges stretched up to "
                f"{max_stretch:.2f}% from rest length (RMS {rms_stretch:.1f}%).", "warn")
        elif converged:
            # Level 0 and Level 1 share the exact fan-triangulated topology -- promoting the
            # just-relaxed result into Level 1's starting position is a pure relabeling, not a
            # new subdivide_once call.
            self.level_snapshots[0] = {"faces": self.faces, "positions": self.positions,
                                        "face_of_fine": self.face_of_fine}
            level0_button = self.level_action_buttons.get(0)
            if level0_button is not None:
                level0_button.config(text="Relax", command=self.on_relax_clicked)
            self.subdivision_level = 1
            self.iteration_count = 0
            # Same reset as _subdivide_step's own.
            self._current_precomp_time_s = None
            self._current_sim_time_s = None
            self._current_target_rms_pct = self.target_rms_vars[1].get()
            self.last_stats = self._compute_stretch_stats()
            self._record_level_history()
            self._set_status(
                f"Relaxed (edges stretched up to {max_stretch:.2f}% from rest length, RMS "
                f"{rms_stretch:.1f}%). Promoted to Level 1 -- press Inflate to continue.", "info")
        else:
            self._set_status(
                f"Relaxed ({self.iteration_count} steps, step cap reached): edges stretched up "
                f"to {max_stretch:.2f}% from rest length (RMS {rms_stretch:.1f}%). Press Relax "
                "again to continue.", "info")
        self._set_controls_enabled(True)
        self._set_level_action_button_running(False)
        self.draw()
        self._auto_step()  # no-op unless Auto is what actually drove this run

    # ---- debug mode only: mesh validation ----

    def on_validate_mesh_clicked(self):
        """Debug-mode-only "Validate Mesh" button: runs _validate_mesh against the currently
        loaded self.faces and reports the result in a modal messagebox -- a synchronous,
        on-demand check, unlike Inflate/Relax's background-threaded runs, since the check is
        cheap (pure index math, no dependence on self.positions)."""
        if self.faces is None:
            self._set_status("No mesh loaded to validate.", "warn")
            return
        ok, lines = _validate_mesh(self.faces)
        report = "\n".join(lines)
        if ok:
            messagebox.showinfo("Validate Mesh", report)
        else:
            messagebox.showwarning("Validate Mesh", report)

    # ---- background worker (used by pressure calibration) ----

    def _set_controls_enabled(self, enabled):
        state = ["!disabled"] if enabled else ["disabled"]
        for widget in (self.combo, self.tolerance_spin,
                       self.steps_radio, self.convergence_radio,
                       self.validate_button, self.show_normals_check,
                       self.show_vertex_normals_check,
                       self.auto_button, *self.target_rms_spins.values()):
            widget.state(state)
        if enabled:
            self._update_mode_state()  # respect the steps/convergence choice
            self._update_level_action_buttons()  # respect the converged-at-this-pressure gate
        else:
            self.steps_spin.state(["disabled"])
            # The frontier level's action button is deliberately left alone here -- the
            # caller re-enables it right after, turned into the Stop control; every other
            # level's stays disabled, since it was never eligible anyway.
            for level, button in self.level_action_buttons.items():
                if level != self.subdivision_level:
                    button.state(["disabled"])
        # self.auto_button was just blanket-(dis)abled above -- re-sync it regardless of which
        # branch ran: while an Auto sequence is driving the run, this re-enables it (reading
        # "Stop Simulation"), the same "frontier button survives the blanket disable"
        # exception _set_level_action_button_running makes for the per-level buttons.
        self._update_auto_button()

    def _run_background(self, fn, on_done, on_progress=None):
        """Run fn(queue_progress) in a background thread and call on_done(result) on the main
        thread once it finishes -- used for on_inflate_clicked's pressure calibration, which
        can take a moment. `queue_progress` is a callable fn may call from the background
        thread (Tk isn't thread-safe, so it only pushes to a queue) to report live progress;
        the main thread (via the scheduled poll below) calls `on_progress(payload)` with
        whatever fn last reported. (Relax has its own streaming variant, _run_relax_stream,
        since it needs a live panel redraw too.)

        Progress messages are coalesced, same as _run_chunked_relax_stream's own poll: only
        the latest queued progress payload is passed to `on_progress` per poll cycle, older
        ones dropped as superseded. "Precomp time"/"Cumulative Time" tick live on every poll
        cycle unconditionally (not gated behind an "else" alongside on_progress -- with
        progress messages arriving on essentially every poll during calibration, an "else"
        branch would almost never run, leaving "Simulation Time" visibly frozen for Level
        1-3 specifically)."""
        self._set_controls_enabled(False)
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
            latest_progress = None
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        latest_progress = payload
                        continue
                    if latest_progress is not None and on_progress is not None:
                        on_progress(latest_progress)
                    self._set_controls_enabled(True)
                    if kind == "error":
                        self._set_status(f"Failed: {payload}", "error")
                        self._abort_auto()  # nothing left to call _auto_step from otherwise
                        return
                    on_done(payload)
                    return
            except queue.Empty:
                pass
            # Unconditional -- see this method's own docstring.
            self._current_precomp_time_s = time.perf_counter() - self._precomp_start_time
            if latest_progress is not None and on_progress is not None:
                on_progress(latest_progress)  # also refreshes the history table itself
            else:
                self._record_level_history()
            self.root.after(100, poll)

        self.root.after(100, poll)

    # ---- drawing ----

    def _draw_target_faces(self, theme):
        """The undeformed net: every face laid out flat and connected to its neighbors
        (self.target_layout, precomputed once per net selection via a BFS over shared edges)
        -- what the mesh would look like cut out of paper and unfolded flat, before any
        stretching/bending closes it into the solved 3D shape.

        Always shows the base (level 0) polygons -- not the current level's fine triangles,
        and no fine-mesh subdivision overlay either -- just the plain base faces, as a 2D
        preview of the mesh actually being solved. When the loaded net carries
        interactive_builder_app's own saved connections (self.target_connections), each one's
        bezier curve is drawn too -- never its handles, since this panel is read-only."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        all_pts = []
        for face_idx in sorted(self.target_layout):
            # self.target_layout's keys are already GROUP ids, so this looks up color the
            # same way _draw_level_panel's per-group add_mesh calls do, not the flat
            # self.colors list.
            color = self.color_by_group[face_idx]
            placed = self.target_layout[face_idx]
            self.ax2d.add_patch(Polygon(placed, closed=True, facecolor=color,
                                         edgecolor="k", alpha=0.9))
            all_pts.extend(placed)

        if self.target_connections:
            for conn in self.target_connections:
                curve = _connection_curve_points(self.target_layout, conn)
                if curve is not None:
                    xs, ys = zip(*curve)
                    self.ax2d.plot(xs, ys, color=CONNECTION_CURVE_COLOR,
                                    linewidth=CONNECTION_CURVE_WIDTH,
                                    zorder=CONNECTION_CURVE_ZORDER)
                    # A bezier's control points can bow it well past its two faces' combined
                    # extent (the whole point of dragging a handle) -- feeding its sampled
                    # points into the same bounding box the faces use below keeps a bulging
                    # curve from getting clipped at the panel edge.
                    all_pts.extend(curve)

        all_pts = np.array(all_pts)
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        pad = 0.6
        # self.net_zoom shrinks/grows this half-extent around the layout's center (Net
        # panel's own analogue of every "Level N" panel's self.level_zoom).
        # self.net_pan (world-unit offset, right-drag) shifts this same center independently
        # of net_zoom -- analogue of self.level_pan, a plain 2D offset here rather than a 3D
        # one added to a PyVista camera.
        center = (lo + hi) / 2 + self.net_pan
        half_range = (hi - lo) / 2 + pad
        # Stretched to the panel's own aspect ratio before dividing by zoom, rather than
        # handing set_aspect("equal") two independent half_range values and letting it shrink
        # whichever axis has proportionally less content (its default adjustable="box"
        # behavior, which reads as thicker margins than every "Level N" panel's own
        # aspect handling gets -- see camera.parallel_scale's analogous term in
        # _render_level_pv). Whichever axis needs more room wins; the other is grown to
        # match, so set_xlim/set_ylim already fills the panel and set_aspect has nothing left
        # to shrink.
        panel_aspect = NET_PANEL_SIZE[0] / NET_PANEL_SIZE[1]
        half_y = max(half_range[1], half_range[0] / panel_aspect)
        half_range = np.array([half_y * panel_aspect, half_y]) / self.net_zoom
        self.ax2d.set_xlim(center[0] - half_range[0], center[0] + half_range[0])
        self.ax2d.set_ylim(center[1] - half_range[1], center[1] + half_range[1])
        self.ax2d.set_aspect("equal")
        # No ax.set_title() here -- "Net" is a plain Tkinter Label above this canvas, same as
        # every "Level N" panel's title.

    def _on_net_scroll(self, event):
        """Mouse-wheel-scroll on the Net panel zooms it (self.net_zoom) -- the Net panel's own
        analogue of _on_level_scroll, scaling _draw_target_faces' bounding-box half-extent
        instead of a PyVista camera. Only the Net panel redraws -- net_zoom has no effect on
        the "Level N" panels, so re-rendering their off-screen scenes here would be wasted."""
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / NET_ZOOM_STEP
        else:
            factor = NET_ZOOM_STEP
        self.net_zoom = max(NET_ZOOM_MIN, min(NET_ZOOM_MAX, self.net_zoom * factor))
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_idle_all()

    def _on_net_pan_start(self, event):
        self._net_panning = True
        self._net_pan_last_xy = (event.x, event.y)

    def _on_net_pan_motion(self, event):
        """Right-click-drag on the Net panel translates it (self.net_pan, added directly to
        _draw_target_faces' bounding-box center) -- analogue of _on_level_pan_motion, a plain
        2D data-space offset instead of a 3D one through a PyVista camera, since this panel is
        matplotlib. Converts the screen-pixel drag into data units via the axes' current
        x/ylim and the canvas widget's current pixel size (both already reflect zoom, so this
        stays a 1:1 drag at any zoom level). Sign convention: shifting the view's center by
        -dx (x) or +dy (y) in data units is what makes a fixed data point's screen position
        move by the mouse's own (dx, dy) -- the y sign flips relative to x because Tk widget
        pixels grow downward while this axes' data y grows upward."""
        if not self._net_panning or self._net_pan_last_xy is None:
            return
        last_x, last_y = self._net_pan_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        widget = self.canvas_net.get_tk_widget()
        width_px, height_px = widget.winfo_width(), widget.winfo_height()
        if width_px <= 1 or height_px <= 1:
            return
        xlim, ylim = self.ax2d.get_xlim(), self.ax2d.get_ylim()
        data_per_pixel_x = (xlim[1] - xlim[0]) / width_px
        data_per_pixel_y = (ylim[1] - ylim[0]) / height_px
        self.net_pan = self.net_pan + np.array([-dx * data_per_pixel_x, dy * data_per_pixel_y])
        self._net_pan_last_xy = (event.x, event.y)
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_idle_all()

    def _on_net_pan_end(self, event):
        self._net_panning = False
        self._net_pan_last_xy = None

    def _on_net_pan_reset(self, event=None):
        """Middle-click on the Net panel resets pan and zoom back to their defaults -- same
        idea as _on_level_pan_reset, minus rotation, which this 2D panel has none of."""
        self.net_pan = np.zeros(2)
        self.net_zoom = 1.0
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_idle_all()

    def draw(self):
        """Redraws the Net panel plus every "Level N" panel: level == self.subdivision_level
        draws live from current state; a level in self.level_snapshots (already subdivided
        past, or -- for Level 0 -- promoted away from) draws its frozen state; any other level
        hasn't been reached yet and draws empty.

        A level with an active replay-slider scrub (self._level_frames/_level_scrub_index both
        set for it) shows that captured frame's positions instead of its live/frozen ones --
        faces/face_of_fine are unaffected (a captured trajectory never changes topology, only
        positions over time) -- self.positions/level_snapshots themselves are left untouched
        either way, so this is purely a display override."""
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        for level in self.level_plotters:
            if level == self.subdivision_level:
                faces, positions, face_of_fine = self.faces, self.positions, self.face_of_fine
            elif level in self.level_snapshots:
                snap = self.level_snapshots[level]
                faces, positions, face_of_fine = (snap["faces"], snap["positions"],
                                                    snap["face_of_fine"])
            else:
                faces = positions = face_of_fine = None
            frames = self._level_frames.get(level)
            scrub_idx = self._level_scrub_index.get(level)
            if faces is not None and frames and scrub_idx is not None:
                positions = frames[scrub_idx][0]
            self._draw_level_panel(level, faces, positions, face_of_fine)
        self._draw_idle_all()


def main():
    root = tk.Tk()
    InflatePolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
