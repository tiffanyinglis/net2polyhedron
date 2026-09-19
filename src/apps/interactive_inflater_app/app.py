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
to "Stop" (InflaterPane._set_running); clicking it, a single trial not converging within
SAFETY_STEP_CAP=50000 steps (relax_once's own PER-TRIAL cap, NOT summed across
estimate_pressure_for_target_stretch's own internal multi-trial search -- see
_run_inflate_step's own max_nfev_per_trial=SAFETY_STEP_CAP), a pressure search that never found
a workable pressure at all, or a background-thread exception, all funnel into the same
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
from PIL import Image, ImageTk
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
    ICON_SIZE, MENU_ACTIVE_BG, MENU_BG, MENU_DISABLED_FG, MENU_FG, NetValidationError,
    POLYGON_COLORS, POLYGON_NS, InteractiveBuilderApp, _ICON_VERTICES, _rasterize_polygon,
    _enable_windows_dpi_awareness, _expand_folded_shapes, _shape_face_corner_order,
    _vertex_roots,
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


def _midpoint_color(color_a, color_b):
    """RGB midpoint of two matplotlib-recognized colors, as an (r, g, b) tuple in [0, 1]."""
    a, b = np.array(mcolors.to_rgb(color_a)), np.array(mcolors.to_rgb(color_b))
    return tuple((a + b) / 2)


def _darken_color(color, factor=INSIDE_FACE_DARKEN_FACTOR):
    """`color` scaled toward black by `factor`, as an (r, g, b) tuple in [0, 1]."""
    return tuple(np.array(mcolors.to_rgb(color)) * factor)


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
    # set_hover_shape/the overridden _redraw below).
    _hover_shape_id = None

    def set_hover_shape(self, shape_id):
        """Called by InflaterPane._set_hover_group whenever the mouse moves over a different
        face of the 3D panel (or leaves it, shape_id=None) -- 2026-09-19, explicit: "that face
        should be outlined in yellow in both the 2d view and the 3d view". A no-op if
        `shape_id` is already the current hover, matching InflaterPane's own such-events-aren't-
        worth-a-redraw guard."""
        if shape_id == self._hover_shape_id:
            return
        self._hover_shape_id = shape_id
        self._redraw()

    def _redraw(self):
        """Runs InteractiveBuilderApp's own full redraw unchanged, then draws the hover
        highlight (if any) on top -- _redraw's own canvas.delete("all") wipes everything first,
        so this can't be done as a one-time canvas item; it has to be re-added after every
        single redraw, from whatever edit triggered it (drag/rotate/connect/etc.), not just
        from set_hover_shape's own calls."""
        super()._redraw()
        if self._hover_shape_id is not None:
            shape = self._shape_by_id(self._hover_shape_id)
            if shape is not None:
                screen_vertices = [self._world_to_screen(*wv)
                                    for wv in self._shape_world_vertices(shape)]
                flat = [coord for point in screen_vertices for coord in point]
                self.canvas.create_polygon(flat, outline="yellow", fill="", width=3)

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
        "add_face"/"remove_face" (EXACTLY one shape added/removed and nothing else about the
        surviving net's topology changed -- extra is that one shape's id), "add_connection"/
        "remove_connection" (same shape SET, but exactly one connection added/removed and no
        shape's own n/flipped changed -- extra is that connection's own conn_key, unused by the
        caller but handy for debugging), or "complex" (anything else -- a moved/flipped/multi-
        shape change, more than one connection edited at once, etc.), extra is None for "none"/
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

        old_conns = {conn_key(c) for c in old_connections}
        new_conns = {conn_key(c) for c in self.connections}
        conn_added, conn_removed = new_conns - old_conns, old_conns - new_conns

        if len(added) == 1 and not removed:
            (new_id,) = added
            if conn_removed or any(not touches(k, new_id) for k in conn_added):
                return "complex", None
            return "add_face", new_id
        if len(removed) == 1 and not added:
            (removed_id,) = removed
            if conn_added or any(not touches(k, removed_id) for k in conn_removed):
                return "complex", None
            return "remove_face", removed_id
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
        # Staged by whichever pipeline path is currently running (on_full_inflate_clicked/
        # _diff_add_face/_diff_remove_face) -- _record_inflate_success adopts it as the new
        # self.last_source_polygon_id once that path reaches a clean Level-3 "Done", but
        # (see _record_inflate_success's own docstring) is never cleared, so it also always
        # tracks "the source_polygon_id for whatever self.base_faces currently is".
        self._pending_source_polygon_id = None

        # Hover-highlight state (2026-09-19, explicit: "when i mouse over a face in the 3d
        # image, that face should be outlined in yellow in both the 2d view and the 3d view")
        # -- self._actor_to_group is rebuilt every _render() ({vtk actor: base-face-group-index}
        # for the group each add_mesh call belongs to); self._picker is one reused vtkCellPicker
        # instance (cheap to reuse, no reason to build a fresh one per mouse-move);
        # self._hover_group/_hover_actor track the CURRENTLY highlighted group and its yellow
        # outline actor so _set_hover_group can cheaply add/remove just that one actor instead
        # of re-running the whole _render().
        self._actor_to_group = {}
        self._picker = vtkCellPicker()
        self._hover_group = None
        self._hover_actor = None

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
        change to Stop so that the user can stop the simulation")."""
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

    def refresh_diff_eligibility(self):
        """Enables Diff Inflate iff an inflate has completed at least once AND the builder's
        current net differs from that completed state by exactly one added/removed shape or
        connection (BuilderPane.classify_change, DIFF_ELIGIBLE_KINDS) -- called after every
        completed Inflate click (via _set_running) and after every builder edit
        (BuilderPane.on_change, wired from CombinedApp) so the button's enabled state always
        reflects the LIVE net, not just whatever it was the last time Inflate ran."""
        if self._running or self.last_shapes_snapshot is None:
            self.diff_inflate_button.state(["disabled"])
            return
        kind, _extra = self.builder_getter().classify_change(
            self.last_shapes_snapshot, self.last_connections_snapshot)
        self.diff_inflate_button.state(
            ["!disabled"] if kind in self.DIFF_ELIGIBLE_KINDS else ["disabled"])

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

    def _on_drag_start(self, event):
        self._dragging = True
        self._last_xy = (event.x, event.y)

    def _on_drag_motion(self, event):
        if not self._dragging or self._last_xy is None:
            return
        cam = self._camera
        last_x, last_y = self._last_xy
        dx, dy = event.x - last_x, event.y - last_y
        up = cam["rotation"].apply([0.0, 0.0, 1.0])
        right = cam["rotation"].apply([0.0, 1.0, 0.0])
        sensitivity = np.radians(PANEL_DRAG_SENSITIVITY)
        yaw = Rotation.from_rotvec(-dx * sensitivity * up)
        pitch = Rotation.from_rotvec(-dy * sensitivity * right)
        cam["rotation"] = pitch * yaw * cam["rotation"]
        self._last_xy = (event.x, event.y)
        self._render()

    def _on_drag_end(self, _event):
        self._dragging = False
        self._last_xy = None

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
        self._render()

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
        self._render()

    # ---- hover highlight ----

    def _on_panel_hover_motion(self, event):
        """Plain mouse motion (no button held) over the panel -- picks whichever face's own
        mesh actor is under the cursor (vtkCellPicker, against the SAME renderer/actors
        _render() just built -- picking is pure ray-vs-geometry math, works identically
        off-screen) and highlights its whole base-face group (_set_hover_group). A drag
        (rotate/pan) fires its OWN motion events (<B1-Motion>/<B3-Motion>), never this plain
        <Motion> one, so hover picking never fights the camera gestures."""
        if not self._actor_to_group:
            return
        width, height = self.panel_size
        # VTK's own pixel origin is bottom-left; Tk's (event.x/event.y) is top-left.
        self._picker.Pick(event.x, height - 1 - event.y, 0, self.plotter.renderer)
        group = self._actor_to_group.get(self._picker.GetActor())
        self._set_hover_group(group)

    def _on_panel_hover_leave(self, _event=None):
        self._set_hover_group(None)

    def _set_hover_group(self, group):
        """Highlights base face `group`'s own polygon outline in yellow in BOTH this 3D panel
        AND the left pane's flat 2D canvas (BuilderPane.set_hover_shape) -- `group is None`
        clears it. A no-op if `group` is already the current hover (the common case -- most
        mouse-move events land on the same face the previous one did), so a still cursor over
        one face doesn't re-render on every motion tick. Cheap: only adds/removes the ONE
        highlight actor (not a full _render()) for the 3D side."""
        if group == self._hover_group:
            return
        self._hover_group = group
        if self._hover_actor is not None:
            self.plotter.remove_actor(self._hover_actor)
            self._hover_actor = None
        if group is not None:
            self._hover_actor = self.plotter.add_lines(
                self._group_boundary_lines(group), color="yellow", width=4)
        self.plotter.render()
        image = self.plotter.screenshot(return_img=True)
        self._photo = ImageTk.PhotoImage(Image.fromarray(image))
        self.panel_label.configure(image=self._photo, text="")

        shape_id = None
        if (group is not None and self._pending_source_polygon_id is not None
                and group < len(self._pending_source_polygon_id)):
            shape_id = self._pending_source_polygon_id[group]
        self.builder_getter().set_hover_shape(shape_id)

    # ---- rendering ----

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
        edge_count = {}
        for face, bf in zip(self.faces, self.face_of_fine):
            if bf != group:
                continue
            a, b, c = face
            for u, v in ((a, b), (b, c), (c, a)):
                key = (u, v) if u < v else (v, u)
                edge_count[key] = edge_count.get(key, 0) + 1
        boundary_edges = [e for e, count in edge_count.items() if count == 1]
        segments = np.empty((2 * len(boundary_edges), 3))
        for i, (u, v) in enumerate(boundary_edges):
            segments[2 * i] = self.positions[u]
            segments[2 * i + 1] = self.positions[v]
        return segments

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
        across Inflate steps. Each face's own fill mesh is drawn with show_edges=False (the fine
        subdivision triangles read as a smooth-ish shaded surface, not a wireframe) plus a
        SEPARATE add_lines call for just that polygon's own outline (_group_boundary_lines).
        Rebuilds self._actor_to_group ({vtk actor: group index}, for hover picking) and
        re-applies the current hover highlight (self._hover_group), since plotter.clear() just
        destroyed the previous highlight actor along with everything else."""
        plotter = self.plotter
        plotter.clear()
        self._actor_to_group = {}
        self._hover_actor = None
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
                face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
                mesh = pv.PolyData(points, face_conn)
                actor = plotter.add_mesh(mesh, color=color, show_edges=False,
                                          backface_params=dict(color=_darken_color(color)))
                self._actor_to_group[actor] = group
                plotter.add_lines(self._group_boundary_lines(group),
                                   color=_midpoint_color("white", color), width=1.5)
            if self._hover_group in groups_present:
                self._hover_actor = plotter.add_lines(
                    self._group_boundary_lines(self._hover_group), color="yellow", width=4)
            lo, hi = points.min(axis=0), points.max(axis=0)
            self._center = (lo + hi) / 2
            self._half = float(np.linalg.norm(points - self._center, axis=1).max()) + 1e-6
            self._apply_camera()
            plotter.render()
            image = plotter.screenshot(return_img=True)
            self._photo = ImageTk.PhotoImage(Image.fromarray(image))
            self.panel_label.configure(image=self._photo, text="")
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

    def _run_inflate_step(self):
        target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        tolerance = self._get_tolerance()
        self._run_background(
            lambda queue_progress: estimate_pressure_for_target_stretch(
                self.positions, self.faces, self.edge_length,
                target_rms_pct=target_rms_pct, gtol=tolerance, rng=None,
                capture_frames=False, on_progress=queue_progress,
                edges=self.edges if self.subdivision_level == 1 else None,
                # SAFETY_STEP_CAP applies PER TRIAL, not summed across estimate_pressure_for_
                # target_stretch's own internal bracket/bisect search (2026-09-19, explicit:
                # "50000 is for one trial, not for all trials combined") -- its default
                # (5000) is smaller, so this must be passed explicitly.
                max_nfev_per_trial=SAFETY_STEP_CAP, stop_event=self._stop_event),
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
            self._revert_run(
                f"Level {self.subdivision_level}: pressure {pressure:.2f} didn't converge "
                f"within {SAFETY_STEP_CAP} steps -- reverted to the state before Inflate.",
                popup_text=(
                    f"The mesh didn't converge at Level {self.subdivision_level} (pressure "
                    f"{pressure:.2f}, max stretch {max_stretch:.1f}%, RMS {rms_stretch:.1f}% "
                    f"after {SAFETY_STEP_CAP} steps) -- it may have a loosely-attached or "
                    "floppy face. Try anchoring/reconnecting it and Inflate again."))
            return
        self.positions = new_positions
        self._render()
        if self.subdivision_level >= MAX_LEVEL:
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
        kind, shape_id = builder.classify_change(
            self.last_shapes_snapshot, self.last_connections_snapshot)
        if kind == "add_face":
            self._diff_add_face(shape_id)
        elif kind == "remove_face":
            self._diff_remove_face(shape_id)
        elif kind == "add_connection":
            self._diff_connection_change("added a connection")
        elif kind == "remove_connection":
            self._diff_connection_change("removed a connection")
        else:
            messagebox.showerror(
                "Cannot Diff Inflate",
                "The net has changed by more than a single added/removed face or connection "
                "since the last Inflate -- use Full Inflate instead.")

    def _diff_remove_face(self, shape_id):
        """Filters the STORED Level-3 mesh (self.faces/self.positions/self.face_of_fine) and
        the stored base mesh down to whatever's left once `shape_id`'s own base face(s) are
        dropped -- pure filtering, no interpolation needed at all, since every SURVIVING vertex
        is already exactly where it was left. positions/edge_length are left as-is (a few now-
        orphaned entries are simply never read again -- relax/estimate_pressure derive their
        own vertex/edge sets purely from `faces`, see stretchy_mesh._edge_setup). Then runs ONE
        pressure-calibration pass at Level 3 (_run_inflate_step, already naturally a single
        pass whenever self.subdivision_level == MAX_LEVEL going in)."""
        removed_idxs = {i for i, spid in enumerate(self.last_source_polygon_id) if spid == shape_id}
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
        self._set_status(
            f"Diff Inflate: removed a face, calibrating pressure at Level {MAX_LEVEL}...", "info")
        self._run_inflate_step()

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
        self._run_inflate_step()

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
