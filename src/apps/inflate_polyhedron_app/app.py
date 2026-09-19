"""
Inflate Polyhedron -- interactive fabric relaxation for stretchy meshes.

    python src/apps/inflate_polyhedron_app/app.py

Nets here (data/input/stretchy_nets/*.json or *.poly -- interactive_builder_app's own current
save extension, plain JSON content either way, see refresh_net_list -- see utils/
inflate_polyhedron/stretchy_mesh.py for the vertex-loop format) are specified directly as
vertex loops --
shared vertex ids ARE the adjacency, so a face pair sharing several edges
(which would force two RIGID flat faces into the same plane -- see
utils/inflate_polyhedron/stretchy_mesh.py's module docstring) needs no special
casing.

A net's starting configuration is no longer solved analytically
(solve_wireframe, the old random-restart-plus-inflation-ramp search) --
"Level 0" instead starts from genuine random noise
(stretchy_mesh.random_initial_positions) and the "Relax" button pulls it
into a well-separated 3D shape using pure spring forces only
(stretchy_mesh.relax_initial_configuration -- no pressure, faces may
cross), the same generic force-directed-layout idea for any net
regardless of its combinatorics. Level 0 is triangulated first (fan
subdivision, see mesh_levels.subdivide_once) since an untriangulated
face (e.g. a plain quad) is a flexible mechanism under springs alone, not
a rigid structure -- this fan-triangulated topology is *exactly* Level
1's own topology (see mesh_levels' docstring), so once Relax converges,
promoting Level 0's result into Level 1's starting position is a pure
relabeling, not a new subdivide_once call. A legacy fabric-subdivided
file (one carrying baked-in "coarse_faces", see
utils/subdivisions/mesh_subdivide.load_fabric_spec and
generate_subdivided_stretchy_nets.py) starts this same way from ITS OWN
coarse_faces rather than its pre-baked fine mesh. This supersedes the old
fixed-resolution fabric-net files/build_cache precompute pipeline for
this app's own workflow -- the fixed-resolution example nets it used to
ship with (cube_res3.json and friends) have been removed accordingly,
though the format and generate_subdivided_stretchy_nets.py itself still
work for anyone who wants one.

1. On selecting a net, its BASE faces are fan-triangulated (Level 0/1's
   shared topology) and given a fresh random start -- both cheap enough
   to happen instantly, so there's no background solve or cache for this
   step anymore (see "Relax" below for what actually shapes it).
2. "Relax" (Level 0 only, stretchy_mesh.relax_initial_configuration) runs
   pure-spring relaxation to convergence; once it converges, Level 0's
   result is promoted straight into Level 1's starting position (see
   above -- no user action needed for this handoff). A tangled (mixed
   face-orientation) result is possible and NOT retried automatically --
   the subsequent Inflate/pressure step is expected to work it out.
3. "Subdivide" (mesh_levels.subdivide_once) refines the CURRENT mesh by
   one level (from Level 1 on): each level quarters every triangle by
   connecting edge midpoints. New points are linearly interpolated from
   the current mesh's own nearby points; new REST lengths (as opposed to
   positions) are derived analytically from the original unit-edge flat
   reference geometry, so the ideal target shape stays fixed as
   resolution increases (see mesh_levels' docstring) -- letting "inflate,
   then increase resolution, then inflate again" converge toward one
   consistent answer instead of each level chasing a different target.
   Greyed out once MAX_LEVEL is reached.
4. At Level 1 and up, the "Inflate" button first CALIBRATES a pressure (see
   stretchy_mesh.estimate_pressure_for_target_stretch -- a bracket-then-
   bisect search now, not just a repeated rescale, specifically so a
   LARGE target like 60% can actually be reached rather than the
   calibration oscillating forever between one pressure too low and
   another that diverges outright -- see its own docstring) landing near
   the CURRENT level's OWN "Target RMS stretch" spinner value (% of rest
   edge length) -- there are three separate spinners, one each for Level
   1/2/3 (self.target_rms_vars), defaulting to LEVEL_DEFAULT_TARGET_RMS_PCT
   (200/100/10% respectively, tapered down as resolution increases since a
   finer mesh needs LESS relative stretch per edge to trace the SAME
   overall curvature) but independently user-editable at any time, and
   used identically by a manual Inflate click and by "Auto" (both just
   call on_inflate_clicked, which always reads whichever level is
   current). The WINNING calibration trial's own already-computed result
   is the entire Inflate outcome (2026-09-17, explicit user request) --
   there's no separate second relax_once pass at that pressure any more.
   There used to be one, but it was pure duplicated work: every
   calibration trial already starts from the same positions, and the
   winning trial runs at the exact pressure/gtol/rng a follow-up call
   would use, so it retraced an already-computed trajectory step for
   step just to have something to show frame-by-frame. The winning trial
   is also topped up to REAL convergence if `max_nfev_per_trial` (its own
   search-time step budget, not a real stopping criterion) cut it off
   first (2026-09-17, explicit user request) -- estimate_pressure_for_
   target_stretch no longer hands back a merely part-finished trial for
   someone else to somehow finish; the extra wall-clock time this can
   take is included in "Precomp time" for free, since it all happens
   inside that one call. estimate_pressure_for_target_stretch itself
   captures the winning trial's own `(positions, cumulative_steps_taken)`
   every CONVERGENCE_CHECK_INTERVAL steps (`capture_frames=True`,
   including the top-up), and _on_pressure_calibrated replays THOSE
   (_start_frame_replay) once calibration lands on a pressure -- this
   level's own panel shows an animated "Computing..." placeholder
   (_start_computing_animation) while the search (and any top-up) runs
   (most of its several trials are thrown away, so there's nothing
   meaningful to show frame-by-frame until it's done), then the replay
   plays the winning trial's own shape evolving at REPLAY_FPS once it's
   known -- `iteration_count` (the "Steps" column) advances in step with
   each replayed frame's own recorded step count too (explicit user
   request, same date), even though it's a purely visual recap and no new
   simulation runs during it.
   Repeated Inflate clicks still let you watch/steer the shape further,
   each one re-calibrating fresh from wherever the PREVIOUS click's
   winning trial left off -- pressure is still not something the user
   sets directly (required pressure varies a lot between nets -- it
   scales with total surface area, not vertex/face count -- so a single
   fixed number would be either too gentle or wildly excessive depending
   which net is loaded). relax_once itself (used by every calibration
   trial) walks small explicit steps along a genuine spring-vs-pressure
   force (see stretchy_mesh's Design notes) -- no volume or remembered
   state anywhere in it, so it can't compound across a Subdivide.
   - The steps-vs-convergence radio buttons (self.iterate_mode_var/
     steps_var) no longer affect Inflate at all now that there's no
     separate post-calibration pass for them to bound -- each calibration
     trial always runs up to its own fixed `max_nfev_per_trial` (see
     estimate_pressure_for_target_stretch). They're left in place,
     inert, rather than removed outright, pending a decision on whether
     to repurpose or drop them. Relax (Level 0) never read them either
     (see on_relax_clicked's own docstring) -- "Tolerance" (self.
     tolerance_var, default DEFAULT_TOLERANCE, NOT the fixed
     stretchy_mesh.CONVERGENCE_GTOL a bare relax_once/relax_initial_
     configuration call would otherwise default to -- some meshes have a
     long, slow-shrinking tail after the shape has visibly settled, so a
     looser tolerance than it might seem it needs to be is often the
     right call) is still very much live: captured once per Relax/
     Inflate click (self._current_gtol), not re-read live mid-run (the
     spinner is disabled for the run's duration anyway), and forwarded to
     pressure calibration (estimate_pressure_for_target_stretch's own
     `gtol`) so every one of its trials settles against the SAME
     threshold Relax itself uses.
   - relax_once/relax_initial_configuration also remove any RIGID
     rotation/translation each step introduces (stretchy_mesh.
     _remove_rigid_motion) -- a free-floating spring/pressure system has
     no fixed orientation of its own, and an OPEN net in particular
     (unlike a closed one, where pressure forces are torque-free by
     construction) can pick up genuine net torque and slowly spin in
     place with no shape change to show for it. A user watching this
     happen mid-Inflate is what prompted the fix -- worse, since each
     level starts from wherever the previous one was left, two levels
     frozen at DIFFERENT accumulated spins made the "Level N" panels'
     supposedly-shared camera (point 6 below) look inconsistent between
     them, even though that shared rotation state was never touched --
     see _remove_rigid_motion's own docstring in stretchy_mesh.py for
     the full reasoning and verification.
   - Every Relax/Inflate call also passes its own `np.random.default_
     rng()` as `rng` to relax_once/relax_initial_configuration/
     estimate_pressure_for_target_stretch, opting into their occasional
     random-perturbation "kick" when a vertex is genuinely stuck
     OSCILLATING rather than slowly converging (stretchy_mesh.
     KICK_WINDOW/_explicit_relax_loop -- see their own comments) -- a
     user asked for this after a small, weakly-braced part of a net (a
     boundary vertex touching only 2 triangles, from testing a cut-out
     piece of a larger net standalone) got stuck this way and wouldn't
     "pop out" no matter the step size. Directly verified this can't be
     fixed by step size alone (tried larger AND smaller -- oscillation
     either way, never an escape) nor by raising pressure (diverges past
     a critical value instead); the kick helps in general but ISN'T
     guaranteed to rescue every case -- a sufficiently under-constrained
     vertex (as in the case above) can still fail to fully converge even
     with it, since there's no strong nearby equilibrium for a kick to
     land in either. The most reliable actual fix for that SPECIFIC
     class of problem is testing the full, assembled net rather than an
     isolated cut-out piece -- a boundary vertex on a piece's own free
     edge is often an interior, well-braced vertex (degree 4+) once
     neighboring pieces are back in place, with no local-minimum problem
     left to kick at all (verified directly on this project's own
     hippo.json vs. its own cut-out hippo_head.json).
5. The "Convergence History" table records one row per subdivision level
   visited this net session: the pressure last calibrated for it (n/a for
   Level 0, which has no pressure at all), how many Inflate/Relax steps
   that level has taken so far (self.iteration_count -- reset to 0 by
   every Subdivide/promotion, so it always counts from when that level's
   mesh was first created, not carried over from a coarser level), the
   stretch stats at whatever point it's currently at (RMS shown against
   THAT level's OWN target -- self._current_target_rms_pct, recorded at
   calibration time, same "gtol" pattern as point 4 above, NOT re-read
   live from the spinner -- a user reported every row wrongly showing
   whichever level's default the spinner CURRENTLY happened to show), and
   a single combined
   "Convergence" cell -- the relax's own `optimality` (whatever quantity
   stretchy_mesh._explicit_relax_loop actually compares against `gtol` --
   currently the worst vertex's own last-step displacement, a TEMPORARY
   change from its net force per explicit user request for testing; see
   that function's own docstring) against the tolerance that run
   actually used (recorded per row, not re-read live -- see point 4
   above), with a check or cross mark for whether it's below it --
   updated live while Inflate/Relax runs. This cell is deliberately
   generic about WHAT `optimality` measures, since it just displays
   whatever stretchy_mesh reports and compares it to `gtol` the same way
   regardless -- it stays correct across a change like the one above
   without needing its own update. (A former max_stretch_pct/STALL_WINDOW
   plateau shortcut could converge with optimality still numerically
   above gtol, shown as "(stalled)" -- that mechanism has since been
   removed entirely per explicit user request, so `converged` now always
   agrees with the plain optimality-vs-gtol comparison; see
   stretchy_mesh's own git history around STALL_WINDOW for why it existed
   and was removed.) INFLATE_SAFETY_STEP_CAP (currently 50000) is this
   app's own hard step-count cap per run, the only non-gtol way a run can
   end besides Stop.
6. The view below is "Net" (the flat, undeformed layout, matplotlib)
   plus one 3D panel per level, "Level 0".."Level N" (MAX_LEVEL total,
   plus Level 0). The Net panel supports its own mouse-wheel zoom
   (self.net_zoom, _on_net_scroll) scaling _draw_target_faces' own
   bounding-box-derived view, independent of every "Level N" panel's own
   zoom (see point 6 below -- different rendering stacks, matplotlib here,
   PyVista there, with no shared camera state). When the loaded
   file carries its own flat arrangement from interactive_builder_app
   (`_layout_from_net_layout`, its own "net_layout" section), that
   reconstruction also corrects a real coordinate-convention mismatch --
   interactive_builder_app's Tkinter canvas has Y increasing DOWNWARD,
   this panel's matplotlib axes have Y increasing UPWARD -- by flipping
   every point's Y sign, so the net displays right-side-up rather than
   as a mirror image of what was actually built there (see
   _layout_from_net_layout's own docstring; a user reported the
   unflipped version as appearing vertically flipped). Only the panel
   for self.subdivision_level is LIVE -- it
   redraws every Inflate/Relax progress update; every level already left
   behind (by Subdivide, or by Relax's own promotion) is frozen at
   whatever state it was left in (self.level_snapshots, captured the
   moment the user moves on from it) and never updates again; a level
   not reached yet is drawn empty. Each panel derives its own view
   bounds from its current points' bounding box every redraw (see
   _draw_level_panel) -- necessary since neither a pure-spring relax nor
   a pressure inflation has any mechanism keeping the result near the
   origin or at a familiar scale.

   Every "Level N" panel renders via PyVista/VTK
   (`_build_level_pv_panel`/`_draw_level_panel`/`_render_level_pv`), not
   matplotlib: a mesh here is routinely self-intersecting or non-convex
   (mid-relax, mid-inflate, or Level 0's own random-start-then-relax
   result), which neither mplot3d's own painter's-algorithm depth sort
   nor this app's old `_CullableFace` (exact normal-based culling, valid
   only for a closed CONVEX solid) could draw correctly -- occluded
   faces would wrongly show through. PyVista gives a real GPU depth
   buffer instead, which handles arbitrary triangle soups correctly
   regardless of convexity, blitted into a plain Tkinter Label as an
   off-screen-rendered image. Level panels share their click-drag
   rotation state (a scipy.spatial.transform.Rotation quaternion -- see
   _on_level_motion) in TWO independent groups now, not one (2026-09-17,
   explicit user request -- "separate the zoom/rotation/translation of
   level 0 from level 1-3 since they look so different"): Level 0 has its
   own (self._level0_camera), Levels 1-3 continue sharing a single one
   among themselves (self._level13_camera) -- a drag on any panel in a
   group rotates every panel in THAT group together, but leaves the other
   group untouched (_level_camera/_camera_group_levels/
   _render_camera_group). Originally every level (including 0) shared
   ONE state, matching what the old matplotlib panels' rotation sync used
   to do -- tried on Level 0 alone first, to validate the drag-rotation
   approach before applying it to every level, well before the later
   independent-groups split. An earlier version stored azimuth/elevation
   as two separate Euler angles, which hits gimbal lock near the poles
   (elevation approaching +-90 degrees) -- a quaternion has no such
   singularity, since the whole orientation is one object rather than two
   angles applied in a fixed order. Each group likewise has its own
   mouse-wheel zoom state -- scrolling over a panel zooms every panel in
   THAT panel's own group together. Both groups' zooms are clamped to the
   same 10%..1000% range (LEVEL_ZOOM_MIN/MAX, NET_ZOOM_MIN/MAX,
   2026-09-16 explicit user request) as the Net panel's own separate zoom.
   Each group ALSO has its own right-click-drag pan (a 2D NDC offset
   applied via vtkCamera's own SetWindowCenter, a pure post-projection
   viewport shift -- see its own comment in __init__ for why NOT a 3D
   world-space offset added to focal_point/position, an earlier version's
   actual bug: that desynced panels of different scale and moved the
   rotation drag's own orbit center); middle-click resets a group's own
   pan/zoom/rotation together, whichever panel it's clicked on
   (_on_level_pan_reset). The Net panel has its own SEPARATE right-click-
   drag pan (self.net_pan, a plain 2D data-space offset, _on_net_pan_
   motion/_on_net_pan_reset) -- not synced with either level-panel camera
   group, same "different rendering stacks, no shared camera state"
   reason net_zoom and the level panels' own zoom groups already don't
   share either.
7. Debug mode ("d" key) adds two developer-only diagnostics, neither of
   which affects the actual solve -- purely for inspecting whatever's
   currently loaded:
   - "Validate Mesh" (on_validate_mesh_clicked/_validate_mesh) checks
     the CURRENT self.faces (post-subdivision -- possibly finer than the
     original file's own faces) for "Structural winding consistency" --
     a PURELY COMBINATORIAL check, depending only on self.faces' own
     vertex-id loops, NEVER on self.positions (the function doesn't even
     take positions as a parameter): the same "no directed edge appears
     more than once" rule load_stretchy_mesh already enforces on a raw
     FILE at Load time, re-run here against the LIVE, possibly finer
     mesh mesh_levels.subdivide_once produced, so a developer can
     directly confirm that function (on this project's own untouchable-
     files list) hasn't corrupted the winding while subdividing. Result
     shown in a modal messagebox. An EARLIER version also reported a
     second, self.positions-dependent check here ("does the mesh's
     CURRENT shape look outward-facing from its own centroid") -- even
     though clearly labeled informational and never gating pass/fail, a
     user asked for it to be removed anyway: a `positions`-dependent
     number had no place in a tool meant to validate STRUCTURE (see
     _validate_mesh's own docstring for the reasoning that originally
     surfaced the distinction -- Level 0's random positions vs. Level
     1's relaxed ones giving different answers for the SAME unchanged
     `faces`). That question is still answerable live via "Show face
     normals" below instead.
   - "Show face normals" (self.show_normals_var, renamed 2026-09-19 from
     "Show normals" once "Show vertex normals" below was added alongside
     it) draws each triangle's own outward normal as a line segment from
     its centroid, in NORMAL_COLOR, on every populated "Level N" panel
     (_draw_level_panel) -- an inward-pointing one is then immediately
     obvious on sight; this is now the ONLY way this app answers "does
     the CURRENT embedding look inside-out", since Validate Mesh no
     longer does (see above). Each segment is scaled to
     NORMAL_LENGTH_FRACTION (0.5) of that triangle's own mean CURRENT
     edge length (not rest length), so it always reads as roughly "half
     an edge long" relative to whatever's on screen (a full edge length,
     tried first, read too long against a dense mesh), regardless of
     overall mesh scale or how far from rest it's currently stretched.
   - "Show vertex normals" (self.show_vertex_normals_var, 2026-09-19,
     explicit user request while diagnosing self-intersecting/"writhing"
     motion during an Inflate replay where the face normals alone looked
     fine) draws each VERTEX's own normal instead -- the normalized
     average of every incident face's own unit normal (see
     _vertex_normals) -- as a line segment from that vertex's own
     position, in VERTEX_NORMAL_COLOR, independent of "Show face
     normals" (either, both, or neither can be on at once). A vertex
     whose incident faces disagree sharply in orientation (a fold,
     or a genuinely inconsistent local winding a per-face check alone
     doesn't surface) shows up as a normal pointing somewhere unexpected,
     even when every individual face's own normal looks locally
     reasonable. Scaled to NORMAL_LENGTH_FRACTION of that vertex's own
     mean incident-edge length, same "reads as about half an edge"
     convention as face normals.
8. "Auto" (on_auto_clicked/_auto_step; visible and usable in BOTH modes,
   unlike debug mode's own diagnostics above) runs the WHOLE pipeline
   unattended, from wherever it currently is: Relax at Level 0, then
   Inflate/Subdivide/Inflate/.../Level MAX_LEVEL -- exactly the sequence
   a user would otherwise click through by hand, one button click.
   _auto_step decides what "next" means each time it's called (once to
   start, then again from the tail of _finish_relax/_finish_inflate
   every time a step it started actually finishes): try Relax/Inflate at
   the current level if it hasn't converged yet, Subdivide once it has
   (immediately continuing to the newly-subdivided level's own first
   Inflate attempt, since Subdivide itself is synchronous and schedules
   no callback of its own), or stop once Level MAX_LEVEL converges.
   Exactly ONE attempt per level, no retries within it -- a non-converged
   attempt just runs its own single relax_once/relax_initial_configuration
   call up to its own large step budget (INFLATE_SAFETY_STEP_CAP) rather
   than Auto cutting it short and starting a fresh one (which used to
   mean recalibrating Inflate's pressure from scratch every time, for no
   real benefit -- see INFLATE_SAFETY_STEP_CAP's own comment). If that
   one attempt still hasn't converged, Auto stops and reports this
   plainly rather than retrying or hanging.
   While running, the button itself becomes "Stop Auto" (the one
   control deliberately kept enabled through the run -- see
   _update_auto_button/_set_controls_enabled, the same "frontier button
   survives the blanket disable" exception the per-level buttons
   already use for their own "Stop"), interrupting whatever Relax/
   Inflate step is currently mid-run via the SAME stop_event a per-level
   Stop click uses -- and a per-level Stop clicked directly, instead,
   halts the Auto sequence too (_abort_auto, called from on_stop_clicked
   itself), so there's only one real way to stop things regardless of
   which button triggered it.
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

# The app's own backronym (2026-09-16, explicit user request) -- used as
# the window title (_apply_mode_visibility); ".hippo" (SESSION_FILE_
# EXTENSION, below) was named first, this is what it stands for.
APP_TITLE = "HIPPO — Hierarchical Inflatable Phabric Polyhedron Optimizer"

# File > Save/Load's own default directory for a whole SESSION (see
# on_save_session_clicked/on_load_session_clicked) -- deliberately NOT
# STRETCHY_NETS_DIR (data/input/stretchy_nets/, the hand-authored nets
# the "Choose a net" combo scans), since a saved session is a generated
# artifact of using this app, not an input to it.
SESSION_OUTPUT_DIR = DATA_DIR / "output"
# File > Save/Load's own extension (2026-09-16, explicit user request) --
# still plain JSON content (session_state.SessionStateModel's own
# model_dump_json), just a distinct extension so a saved session reads
# as this app's own file type at a glance, not an ordinary .json (e.g.
# one of the hand-authored nets under data/input/stretchy_nets/).
SESSION_FILE_EXTENSION = ".hippo"

# A fabric-subdivided net's fine mesh edges (the "Level N" panels' own
# PyVista wireframe overlay, NOT the Net panel -- see _draw_target_faces'
# own comment on why it dropped its subdivision overlay entirely) are
# drawn thin so the subdivision reads as texture rather than a bold
# wireframe competing with the per-coarse-face coloring.
SUBDIVISION_EDGE_WIDTH = 0.5


def _midpoint_color(color_a, color_b):
    """The plain RGB midpoint of two matplotlib-recognized colors (hex
    string, named color, ...), as a (r, g, b) tuple in [0, 1] -- used for
    each "Level N" panel's own wireframe edge color, halfway between
    white and that face's own fill color (2026-09-16, explicit user
    request -- was a single fixed PLOT_THEME["fg"] for every face's
    edges regardless of its own color)."""
    a, b = np.array(mcolors.to_rgb(color_a)), np.array(mcolors.to_rgb(color_b))
    return tuple((a + b) / 2)


def _vertex_normals(faces, positions):
    """faces: triangle vertex-id loops; positions: {vertex_id: pos}.
    Returns {vertex_id: (unit_normal, mean_incident_edge_length)} for
    "Show vertex normals" (_draw_level_panel) -- every vertex touched by
    at least one non-degenerate (nonzero-area) face. `unit_normal` is
    the NORMALIZED SUM of every incident face's own unit normal, each
    face weighted EQUALLY rather than by area: this is meant to show
    "which way do MY OWN faces agree this vertex points" (useful for
    spotting a fold or an inconsistency a per-face check alone won't
    surface), not to approximate a smooth continuous surface normal the
    way a render-time area/angle-weighted average would.
    `mean_incident_edge_length` is the average length of every edge (of
    any incident face) touching this vertex -- scales its own drawn
    segment the same "about half an edge" way face normals already are.
    A vertex whose own incident faces exactly cancel (sum to the zero
    vector) or that has no non-degenerate incident face at all is
    omitted -- no meaningful direction to draw."""
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

# The Net panel's own bezier connection curves (self.target_connections,
# see _draw_target_faces) -- interactive_builder_app's own gluing between
# two faces' edges, shown here purely for context (no handles: this
# panel is read-only, see module-level _connection_curve_points' own
# comment) -- solid white (explicit user request, for contrast against
# every per-face color this panel uses -- none of them are anywhere near
# white), drawn with a HIGHER zorder than every face patch/subdivision
# overlay so it always reads on top of the faces themselves, never
# tucked underneath one.
CONNECTION_CURVE_COLOR = "white"
CONNECTION_CURVE_WIDTH = 1.0
CONNECTION_CURVE_ZORDER = 5

# Convergence History's "running" row tag (_refresh_history_table) --
# its own dedicated color, NOT STATUS_COLORS["warn"] (a muddy, dark
# goldenrod tuned for warning TEXT elsewhere in this app, not a bright
# row highlight) -- brighter, explicit user request after first trying
# STATUS_COLORS["warn"] here.
RUNNING_ROW_COLOR = "#e0b400"

# Every "Level N" panel renders via PyVista/VTK instead of matplotlib
# (see _build_level_pv_panel) -- a real GPU depth buffer, needed because
# a mesh here is routinely self-intersecting/non-convex (mid-relax or
# mid-inflate, or Level 0's random-start-then-relax result itself),
# which neither mplot3d's own painter's-algorithm depth sort nor this
# app's old _CullableFace (exact culling, valid only for a closed CONVEX
# solid) could draw correctly -- tried on Level 0 alone first to
# validate the approach before applying it to every level. Pixel size
# matches figsize=(3.2, 4.5) at the ~100dpi the Net panel's matplotlib
# figure renders at, so every level panel is the same size as its
# neighbors. The Net panel's OWN figure size (figsize=(3.2, 4.5) in
# _build_menu's neighbor, the Net-panel setup code) is independent of
# this now (2026-09-18, explicit user request -- only "the level 0
# drawing area" shrinks, not Net) -- NET_PANEL_SIZE is what that literal
# figsize corresponds to in pixels, kept as its own named constant purely
# so a reader doesn't have to reverse-engineer figsize*dpi by hand.
NET_PANEL_SIZE = (320, 450)
# "Level N" panels are no longer all the same width (2026-09-18, explicit
# user request -- "make the level 0 drawing area and label 60% of its
# current width... distribute [the other 40%] evenly to level1-3 so they
# are wider"): Level 0's own panel shrinks to 60% of the ORIGINAL shared
# width (320 -> 192); the 128px this frees up is split evenly three ways
# and added to Levels 1-3's own width instead (320 -> ~363). Height is
# unchanged for every panel. `_level_panel_size(level)` returns the right
# (width, height) pair; every other constant/comment that used to say
# "LEVEL_PANEL_SIZE" for a level panel now calls that instead.
LEVEL_PANEL_HEIGHT = 450
LEVEL_PANEL_WIDTH_LEVEL_0 = round(320 * 0.6)
LEVEL_PANEL_WIDTH_LEVELS_1_3 = round(320 + (320 - LEVEL_PANEL_WIDTH_LEVEL_0) / 3)


def _level_panel_size(level):
    """(width, height) for `level`'s own panel -- see LEVEL_PANEL_WIDTH_
    LEVEL_0/_LEVELS_1_3's own comment."""
    width = LEVEL_PANEL_WIDTH_LEVEL_0 if level == 0 else LEVEL_PANEL_WIDTH_LEVELS_1_3
    return (width, LEVEL_PANEL_HEIGHT)


# How much of the panel the shape's own bounding box fills, on top of
# the aspect-ratio correction below -- 1.0 would make the shape's widest
# dimension exactly touch the panel edge; below 1.0 leaves margin around
# it (shrinks the apparent shape without resizing the panel). Was one
# shared value (0.36: 0.6, then a further "60% of that" per two rounds of
# user request -- the unzoomed 1.0 rendered noticeably too large/cropped
# against the panel, and 0.6 alone still did too). Split into two
# LEVEL-DEPENDENT defaults (2026-09-17, explicit user request -- "level 0
# should default to filling 50%... level 1-3 should default to filling
# 95%", the latter then adjusted down to 90% by explicit follow-up
# request); Level 0's OWN fill then raised to match, 0.5 -> 0.9
# (2026-09-18, explicit user request, alongside shrinking its panel's own
# width -- see LEVEL_PANEL_WIDTH_LEVEL_0's comment): both levels now fill
# the SAME 90% fraction of their own (differently-sized) panels.
LEVEL_ZOOM_FILL_LEVEL_0 = 0.9
LEVEL_ZOOM_FILL_LEVELS_1_3 = 0.90


def _level_zoom_fill(level):
    """LEVEL_ZOOM_FILL_LEVEL_0 for level 0, LEVEL_ZOOM_FILL_LEVELS_1_3 for
    every other level -- see that pair's own comment."""
    return LEVEL_ZOOM_FILL_LEVEL_0 if level == 0 else LEVEL_ZOOM_FILL_LEVELS_1_3
# Initial camera angle -- arbitrary, just a reasonable non-axis-aligned
# starting view (close to mplot3d's own default elev=30/azim=-60). Only
# used once, to build the initial self.level_rotation quaternion (see
# _initial_level_rotation) -- nothing after that decomposes back into
# separate elevation/azimuth angles, which is what avoids gimbal lock.
LEVEL_DEFAULT_ELEV = 30.0
LEVEL_DEFAULT_AZIM = -60.0
# Degrees of camera rotation per pixel of click-drag -- tuned by feel
# against mplot3d's own drag-to-rotate sensitivity this replaced.
LEVEL_DRAG_SENSITIVITY = 0.5
# Zoom multiplier applied per mouse-wheel notch (one scroll "click", i.e.
# one event.delta increment of 120 on Windows) -- >1 zooms in, so the
# factor camera.parallel_scale is multiplied by is its RECIPROCAL (a
# smaller parallel_scale means a smaller visible world height, i.e.
# zoomed in). Clamped by LEVEL_ZOOM_MIN/MAX (30%..400%, explicit user
# request -- was 10%..1000% before this) so scrolling can't shrink the
# shape to nothing or push it arbitrarily far away.
LEVEL_ZOOM_STEP = 1.1
LEVEL_ZOOM_MIN = 0.3
LEVEL_ZOOM_MAX = 4.0

# Same idea as LEVEL_ZOOM_STEP/MIN/MAX, for the Net panel's own
# mouse-wheel zoom (_on_net_scroll) -- a separate state (self.net_zoom)
# since the Net panel is matplotlib, not a PyVista camera: it scales the
# half-extent _draw_target_faces derives from the flat layout's own
# bounding box, rather than a camera parallel_scale. NET_ZOOM_MAX raised
# to 800% (2026-09-16, explicit user request -- "the net can be zoomed
# in a bit more without getting cut off"; was 400%, matching every
# "Level N" panel) -- decoupled from LEVEL_ZOOM_MAX again since this
# request is Net-panel-specific: its own bounding box now includes every
# connection's bezier curve (see _draw_target_faces), which can sweep
# much further out than the faces themselves, so a closer zoom is
# genuinely useful here in a way it isn't for the 3D panels.
NET_ZOOM_STEP = 1.1
NET_ZOOM_MIN = 0.3
NET_ZOOM_MAX = 8.0

# Overall UI text size multiplier -- applied once, at startup, to every
# named Tk/ttk font (see _scale_ui_fonts) so the whole app's text (not
# just this one label) grows together rather than each widget needing
# its own hardcoded size.
UI_FONT_SCALE = 1.3

# Every panel's title ("Net", "Level N") is a plain Tkinter Label above
# its image/canvas, not text drawn inside the image itself -- a title
# drawn INSIDE a PyVista panel's own rendered scene clipped against the
# panel's own edge (see _render_level_pv's Design notes), which a real
# widget placed above the image can't do. Can't be a plain module-level
# (family, size) tuple (as it used to be, hardcoded to "TkDefaultFont")
# since that string is a NAMED font's name, not a real family -- passed
# as a tuple's first element, Tk takes it literally as a (nonexistent)
# family and silently falls back to Arial, NOT actually matching the
# rest of the UI's real Segoe UI Variable Text look despite being scaled
# by the same UI_FONT_SCALE (2026-09-18, explicit user request -- "make
# sure ... the font is uniform. I like the size and font of 'Choose a
# net'" -- that mismatch was exactly the bug). Computed instead as
# self.LEVEL_TITLE_FONT once at startup (_init_ui_fonts), from "Choose a
# net"'s own actual rendered font (ttk.Label's default style, routed by
# sv_ttk to SunValleyBodyFont) so every title/message label genuinely
# matches it in both family and size, not just size.

# The bottom-of-panel status message ("Computing...", "Replay frame N /
# M" -- see _tick_computing_animation/_replay_step/_set_level_message),
# 2026-09-17 explicit user request: LEFT-justified (anchor=tk.W) rather
# than tk.CENTER, so its OWN start position never re-anchors on every
# update the way true centering would (a dot added, a frame count going
# from 1 to 2 digits) -- but a genuinely FIXED left inset (tried first)
# doesn't actually look centered for every message: "Computing" (no
# dots yet) is much shorter than "Replay frame 27 / 93", so a single
# constant pad tuned for one reads noticeably off-center for the other
# (observed directly). _set_level_message instead measures each specific
# string's own rendered width (tkfont.Font.measure, LEVEL_MESSAGE_FONT)
# and computes the left inset that would ACTUALLY center it, then applies
# that as a plain fixed `padx` via anchor=W -- visually equivalent to
# true centering for any one message, but the position only shifts by
# however much THAT message's own text width actually changed since the
# last update (a dot's width for "Computing" -> "Computing.", near zero
# for most frame-count changes), not a full from-scratch re-center.
# self.LEVEL_MESSAGE_FONT == self.LEVEL_TITLE_FONT (see _init_ui_fonts).

# Shown on the Pressure readout before the user has ever clicked "Auto"
# -- pressure isn't user-editable (see the "Auto" button), so this only
# matters if "Inflate" is clicked with no calibration done yet.
DEFAULT_PRESSURE = 3.0

DEFAULT_STEPS = 10

# This app's own default for the "Tolerance" spinner (self.tolerance_var)
# -- the `gtol` every relax_once/relax_initial_configuration/
# estimate_pressure_for_target_stretch call actually uses (see
# self._current_gtol), NOT stretchy_mesh.CONVERGENCE_GTOL (1e-4, that
# module's own hardcoded default for a caller that never passes gtol at
# all -- untouched, still what a bare relax_once/relax_initial_
# configuration call elsewhere defaults to). Was 1e-6, then 1e-2 (each
# per explicit user request); settled on 1e-3 -- tighter again than
# 1e-2 now that STEP_MAX_MULTIPLIER/STALL_WINDOW (stretchy_mesh.py) no
# longer need a very tight force threshold to actually finish converging
# in reasonable time, but not as loose as 1e-2 -- the stall-window
# criterion alongside it (see _refresh_history_table's "(stalled)" note)
# already catches a mesh that's visibly stopped changing well before
# force alone would settle even this tighter a threshold anyway.
#
# Tightened again, 1e-3 -> 1e-4, per explicit user request, alongside
# stretchy_mesh's own switch to checking the stopping condition only
# once every CONVERGENCE_CHECK_INTERVAL steps rather than every step
# (see that constant's own comment) -- a tighter per-step-equivalent
# rate is more affordable now that far fewer checks are actually
# performed per run.
DEFAULT_TOLERANCE = 1e-4

# Default value for each level's own "Target RMS stretch" spinner
# (self.target_rms_vars[level] -- one independent tk.DoubleVar per
# level, not one shared spinner reset on every level change). Tapered
# DOWN as level increases per explicit user request: a finer mesh
# approximates the SAME overall curvature with a SMALLER stretch per
# edge (more, shorter edges bending through the same total arc), so
# chasing the SAME target RMS stretch at every level would mean asking
# a fine mesh to bulge out FURTHER, relative to its own edge length,
# than a coarse one needs to for the same visual roundness -- these
# values keep the actual 3D shape's target consistent across levels
# instead, matching mesh_levels.py's own "ideal target shape stays
# fixed as resolution increases" design (module docstring, point 3).
# No entry for Level 0 -- it has no target RMS stretch at all
# (relax_initial_configuration is pure springs, not calibrated toward
# any target). Was {1: 60.0, 2: 30.0, 3: 15.0}, then {1: 30.0, 2: 20.0,
# 3: 10.0}, then {1: 60.0, 2: 40.0, 3: 20.0}, then {1: 200.0, 2: 100.0,
# 3: 10.0}; changed again per explicit later user request.
LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 80.0, 2: 40.0, 3: 10.0}

# Debug mode's "Show normals" toggle (_draw_level_panel) draws each
# triangle's own outward normal as a line segment in this color, from
# its centroid, scaled to that SAME triangle's own mean edge length (so
# an inward-pointing normal is immediately obvious regardless of overall
# mesh scale) -- distinct from every FACE_COLORS entry and from
# PLOT_THEME's own fg/edge color, so it reads clearly against either.
NORMAL_COLOR = "yellow"
# "Show vertex normals" toggle's own color (2026-09-19) -- distinct from
# NORMAL_COLOR so a face normal and a vertex normal drawn on the same
# panel (both toggles can be on at once) are never mistaken for each
# other.
VERTEX_NORMAL_COLOR = "cyan"
# How long each normal segment is drawn, as a fraction of its own
# triangle's mean edge length -- 1.0 (a full edge length) read too long
# against a dense/fine mesh per a user request; halved. Shared by both
# "Show face normals" and "Show vertex normals" for the same reason (a
# vertex normal is scaled by ITS OWN mean incident-edge length instead
# of a triangle's, but the same fraction of it).
NORMAL_LENGTH_FRACTION = 0.5

# Hard stop for "iterate until convergence" mode in case a mesh/pressure
# combination genuinely never reaches the current tolerance (e.g. a
# topology that can't hold that much pressure) -- without this, a run
# that plateaus just short of convergence would loop forever instead of
# settling for "as far as it got". Raised from 5000 to 20000 alongside
# stretchy_mesh.STALL_WINDOW's own 200 -> 2000 raise (see its comment) --
# with the stall shortcut no longer able to trigger from a same-size
# coincidence with INFLATE_CHUNK_MAX, a run that's genuinely still
# correcting slowly (e.g. a locally concave vertex popping out) needs
# more real budget to actually reach gtol, not just a bigger number
# before giving up on the SAME amount of real solving.
#
# Raised again, 20000 -> 50000, per explicit user request, alongside
# REMOVING _auto_step's own outer per-level retry loop (formerly
# AUTO_MAX_RETRIES_PER_LEVEL/_auto_try): recalibrating Inflate's pressure
# from scratch on every retry (on_inflate_clicked's own design -- pressure
# is never reused across clicks) was wasted work when the mesh just
# needed more plain relaxation time at the SAME pressure, not a fresh
# search. Auto now makes exactly ONE Relax/Inflate attempt per level,
# leaning on this single, larger step budget to actually reach gtol
# rather than an outer loop of many smaller, pressure-recalibrating
# attempts.
#
# The old chunk-size constants this comment's history refers to
# (INFLATE_CHUNK_START/INFLATE_CHUNK_MAX) no longer exist at all --
# _run_chunked_relax_stream stopped chunking entirely once relax_once/
# relax_initial_configuration gained their own on_progress callback (see
# that function's own docstring), so there's no chunk size left to size
# THIS constant relative to any more; it now purely bounds a single
# uninterrupted relax_once/relax_initial_configuration call's own
# max_nfev in "iterate until convergence" mode.
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
    """faces: Level 0/1's own fan-triangulated mesh, as returned by
    _build_level1_topology; base_edges: the loaded net's own explicit
    "edges" field (stretchy_mesh.load_stretchy_mesh_edges), or None.
    Returns the explicit mesh-edge list for `faces` -- for mesh_edges'
    own `edges` param, so relax_initial_configuration/relax_once/
    estimate_pressure_for_target_stretch use the correct spring topology
    at Level 0/1 -- or None if `base_edges` is None (an older file, or
    one with no ambiguity to disambiguate in the first place; the plain
    vertex-pair derivation mesh_edges already falls back to is safe).

    Fan triangulation never touches a base face's own RIM edges (see
    mesh_levels._fan_level_0_to_1's own docstring) -- they're still
    exactly `base_edges`' own vertex-id pairs, unchanged and already
    correctly disambiguated (see interactive_builder_app.
    _edges_from_shapes' own docstring for why that disambiguation
    matters). The only edges triangulation ADDS are SPOKES (a rim vertex
    to its own face's fresh centroid id), always globally unique -- a
    centroid id can never collide with anything else -- so those are
    safe to derive the plain way. This combines the two: `base_edges`
    as-is, plus every OTHER edge of `faces` (i.e. every edge NOT between
    two original base vertex ids) from a plain mesh_edges derivation."""
    if base_edges is None:
        return None
    base_vertex_ids = {v for e in base_edges for v in e}
    spokes = [e for e in mesh_edges(faces)
              if not (e[0] in base_vertex_ids and e[1] in base_vertex_ids)]
    return list(base_edges) + spokes


# interactive_builder_app/app.py's own DEFAULT_SHAPE_EDGE_LENGTH -- the
# edge length its "net_layout" section's saved cx/cy/rotation are
# expressed at (a Tkinter-canvas pixel scale, unrelated to this app's own
# EDGE_LENGTH=1.0 unit convention). Not imported directly from that app
# (a whole separate, unrelated Tkinter app -- see docs/README.md) --
# just duplicated here as the one number _layout_from_net_layout needs
# to undo that scale.
_INTERACTIVE_BUILDER_EDGE_LENGTH = 70.0


def _layout_from_net_layout(faces, net_layout):
    """faces: vertex-id loops; net_layout: interactive_builder_app's own
    saved list of per-ORIGINAL-PLACED-SHAPE placements (its "net JSON
    import/export" section). Returns {key: [2D point, ...]} -- the exact
    same shape build_stretchy_net_layout returns -- by reproducing each
    shape's saved rigid transform directly, rather than re-deriving a
    layout from scratch via a fresh BFS spanning tree. That matters
    because a BFS can't reproduce an arrangement it wasn't given: it only
    follows the FIRST shared edge it reaches an already-visited face
    through (see build_stretchy_net_layout's own docstring), so any OTHER
    edge-sharing between two faces -- entirely normal for a stretchy
    mesh, see this module's own docstring -- is silently dropped from
    the picture; a net a user carefully arranged in the interactive
    builder (and re-derived exact connections for) deserves to show up
    here exactly as left, not re-flattened from just a spanning subset
    of its real adjacency.

    Two `net_layout` shapes are understood, matching interactive_
    builder_app's own _load_faces:

    - NEW format (`net_layout[i]` has its own "shape_id"/"n", written
      since Polygon Fold): `key` is that entry's own "shape_id" and the
      polygon is built at its own "n" sides directly -- independent of
      `faces`, which no longer has one entry per placed shape once a
      folded polygon's `n` triangles are in it (see interactive_
      builder_app's module docstring's "net JSON import/export"
      section) -- so `faces` isn't even consulted for these entries.
    - LEGACY format (no "shape_id" -- any file saved before Polygon Fold
      existed, always exactly one face per shape): `key` is the entry's
      own list position (`i`, matching `faces[i]`'s own position) and
      "n" is `len(faces[i])`, reproducing today's behavior exactly.

    Rigid transforms (rotation + translation) are scale-covariant, so
    reproducing the same net at THIS app's own unit edge length (rather
    than reproducing interactive_builder_app's pixel scale verbatim) is
    just a uniform rescale by _INTERACTIVE_BUILDER_EDGE_LENGTH: build
    each polygon at edge_length=1 instead of 70, and divide every saved
    cx/cy by the same 70 -- every "touching" edge relationship survives
    exactly, only the absolute unit changes, matching what this panel's
    fixed axis padding (_draw_target_faces) already assumes.

    Also flips every reconstructed point's Y sign (a whole-picture
    reflection about the X axis, applied uniformly across every face --
    an isometry, so it preserves every relative distance/adjacency
    exactly, just mirrors the WHOLE net top-to-bottom). This undoes a
    real coordinate-convention mismatch, not a display quirk: Tkinter
    canvases (interactive_builder_app's own, where cx/cy/rotation were
    recorded) have Y increasing DOWNWARD, while matplotlib's default
    axes (this panel's own ax2d) have Y increasing UPWARD -- reproducing
    interactive_builder_app's cx/cy as-is here draws a mirror image of
    what the user actually saw and built there. A user reported exactly
    this (the net loaded from a file appeared flipped vertically)."""
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
    """True iff `net_layout` (interactive_builder_app's own saved
    section) is the post-Polygon-Fold, shape-id-keyed format rather than
    the legacy face-index-aligned one -- see _layout_from_net_layout's
    own docstring. This app is the sole writer of this format (from
    interactive_builder_app), which always tags every entry the same
    way, so checking just the first entry is enough."""
    return bool(net_layout) and "shape_id" in net_layout[0]


def _face_colors_by_group(n_faces, source_polygon_id):
    """Returns (colors, color_by_group, group_of_face): `colors[i]` is
    face `i`'s own color (a flat list, same length/indexing as
    `base_faces` -- every existing per-base-face-index caller keeps
    working unmodified); `group_of_face[i]` is which GROUP face `i`
    belongs to -- `source_polygon_id[i]` (interactive_builder_app's own
    Polygon-Fold grouping -- see its module docstring) when given, else
    `i` itself, which reduces to today's plain per-face-index coloring
    exactly for any file without it; `color_by_group` is the same colors
    keyed by that group id instead of face index, for a caller (
    _draw_level_panel) that needs to group several base faces sharing
    one source polygon into a single draw call. Every face sharing a
    group gets the SAME color -- first-seen group order picks which
    FACE_COLORS entry each group gets, the same "i-th distinct thing
    gets the i-th palette color" idea the old flat per-index list
    already used."""
    group_of_face = [source_polygon_id[i] if source_polygon_id else i for i in range(n_faces)]
    color_by_group = {}
    colors = []
    for g in group_of_face:
        if g not in color_by_group:
            color_by_group[g] = FACE_COLORS[len(color_by_group) % len(FACE_COLORS)]
        colors.append(color_by_group[g])
    return colors, color_by_group, group_of_face


# interactive_builder_app's own bezier connection curves (module
# docstring's "Bezier handles" section there) -- drawn here too, in the
# Net panel, per explicit user request ("show the connection but don't
# show the handles"): this panel is read-only, so only
# _connection_curve_points/_draw_target_faces exist here, never the
# handle hit-testing/dragging machinery that app owns.

def _placed_edge_frame(points, edge_index):
    """Same construction as interactive_builder_app's own
    _shape_edge_frame -- (origin, tangent, normal) for one edge of an
    already-placed 2D polygon (`points`, this app's own target_layout
    entries) -- but over plain placed points rather than a live shape,
    since this app has no "shape" object, just the final 2D positions.
    The outward-normal test (perpendicular to the edge, flipped if it
    doesn't point away from the polygon's own centroid) is chirality-
    agnostic, so it comes out correct whether `points` is a plain
    rotation of the original interactive_builder_app shape or (as here,
    _layout_from_net_layout's own Y-flip) a mirror image of it -- no
    separate case needed for the two."""
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
    """Same sampling idea as interactive_builder_app's own
    _cubic_bezier_points (duplicated rather than imported -- these are
    two separate, unrelated Tkinter apps, see this module's own docstring
    on why _INTERACTIVE_BUILDER_EDGE_LENGTH is duplicated rather than
    imported for the same reason), just over numpy points instead of
    plain tuples since that's what this app's own target_layout already
    uses."""
    return [(1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
            for t in np.linspace(0.0, 1.0, steps + 1)]


def _connection_curve_points(target_layout, conn, steps=24):
    """The screen/world-space (this app's own unit scale, same as
    target_layout itself) points of one saved builder_connection's cubic
    bezier -- None if either shape it references isn't in `target_layout`
    (e.g. a stale connection referencing an id out of range, which
    shouldn't happen from a file this app's own Save/interactive_
    builder_app's Save ever produces, but isn't worth a crash over).
    `conn["a_shape_id"]/["b_shape_id"]` (new format) or `conn["a_face"]/
    ["b_face"]` (legacy, index-aligned -- see _layout_from_net_layout's
    own docstring) key into `target_layout` the same way either format's
    entries were placed into it. `conn["a_handle"]/["b_handle"]` are
    interactive_builder_app's own {"t", "n"} PIXEL-scale (its
    DEFAULT_SHAPE_EDGE_LENGTH-unit) offsets -- rescaled by
    _INTERACTIVE_BUILDER_EDGE_LENGTH exactly like every cx/cy already is
    (_layout_from_net_layout), then applied against the tangent/normal
    frame RECOMPUTED from this app's own already-placed (rescaled +
    Y-flipped) points (_placed_edge_frame) rather than transformed
    alongside the frame -- since that reflection is a linear map,
    applying an unchanged coefficient to a frame recomputed after the
    transform lands on exactly the same point as transforming the
    pre-image control point would have."""
    a_key = conn["a_shape_id"] if "a_shape_id" in conn else conn["a_face"]
    b_key = conn["b_shape_id"] if "b_shape_id" in conn else conn["b_face"]
    a_points, b_points = target_layout.get(a_key), target_layout.get(b_key)
    if a_points is None or b_points is None:
        return None
    a_mid, a_tan, a_norm = _placed_edge_frame(a_points, conn["a_edge"])
    b_mid, b_tan, b_norm = _placed_edge_frame(b_points, conn["b_edge"])
    scale = _INTERACTIVE_BUILDER_EDGE_LENGTH
    # "a_handle"/"b_handle" are only present in a builder_connections
    # entry saved by a version of interactive_builder_app that tracked
    # them -- an older file's entry has neither, so it defaults to
    # {"t": 0, "n": 0} (a control point sitting exactly on the edge
    # midpoint), giving a curve close to -- though not bit-identical
    # with -- the plain straight line that entry used to draw, rather
    # than a KeyError.
    a_handle = conn.get("a_handle", {"t": 0.0, "n": 0.0})
    b_handle = conn.get("b_handle", {"t": 0.0, "n": 0.0})
    a_ctrl = a_mid + (a_handle["t"] / scale) * a_tan + (a_handle["n"] / scale) * a_norm
    b_ctrl = b_mid + (b_handle["t"] / scale) * b_tan + (b_handle["n"] / scale) * b_norm
    return _cubic_bezier_points(a_mid, a_ctrl, b_ctrl, b_mid, steps)


def _validate_mesh(faces):
    """Debug mode's "Validate Mesh" button (on_validate_mesh_clicked):
    checks the CURRENTLY LOADED self.faces (post-subdivision -- possibly
    finer than the original file's own faces) for structural winding
    consistency. Pure function of `faces` alone (no Tk, no `positions` --
    see below for why), so it's independently testable.

    Returns (ok, lines): `lines` always covers the check (never silent
    about a passing one), so a passing run confirms what was actually
    checked rather than staying silent about it.

    **Structural winding consistency** (combinatorial -- depends ONLY on
    `faces`' own vertex-id loops): per this project's winding convention
    (module docstring), if face A has some edge as v->w, any OTHER face
    sharing that same undirected edge must have it as w->v, NEVER v->w
    again -- that's what makes the two faces' normals (each via the
    right-hand rule off its own CCW loop) point consistently relative to
    each other. Checking this is exactly load_stretchy_mesh's own "no
    directed edge appears more than once" rule (a duplicate (v,w) is
    precisely two faces disagreeing on which way that shared edge runs)
    -- re-run here against the LIVE, possibly finer mesh mesh_levels.
    subdivide_once produced, not just the raw file Load already checked
    once, so a developer can directly confirm that function (on this
    project's own untouchable-files list) hasn't corrupted the winding
    while subdividing.

    An EARLIER version ALSO reported a second, `positions`-dependent
    check here ("does the mesh's CURRENT 3D shape look outward-facing
    from its own centroid") -- removed at explicit user request: even
    though it was clearly labeled informational and never affected `ok`,
    a `positions`-dependent number showing up at all in a tool meant to
    validate STRUCTURE was still the wrong thing to report here. That
    question (is the CURRENT embedding inside-out) is still answerable
    live via the separate "Show normals" toggle instead -- an
    inward-pointing arrow is directly visible there, no separate check
    needed. This function now reports ONLY what's actually structural,
    with nothing that varies between Level 0 (random positions) and a
    fully-inflated Level 3 for the exact same underlying `faces`."""
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
        # Wide enough for the Net panel (NET_PANEL_SIZE) + Level 0
        # (LEVEL_PANEL_WIDTH_LEVEL_0) + Levels 1..MAX_LEVEL
        # (LEVEL_PANEL_WIDTH_LEVELS_1_3 each -- no longer all the same
        # width as Level 0, see that pair's own comment, 2026-09-18
        # explicit user request), PLUS view_frame's own left/right
        # padx=14 -- computed rather than a bigger hardcoded literal
        # (2026-09-16, explicit user request -- a wider window left an
        # uneven, wide blank margin on the right, since every row here
        # packs its own content flush LEFT; the fix is fitting the window
        # to the content's own natural width, not centering within a
        # wider one) so it stays exactly right if MAX_LEVEL or either
        # panel width ever changes, rather than needing to be re-measured
        # by hand again. The panel row no longer stretches its frames to
        # fill extra window width (see panels_row's own comment), so this
        # only needs to fit the panels' own natural width, not leave room
        # to spread them out.
        # Tall enough for Setup + status + Convergence History + each
        # panel's own title-Label-plus-image-plus-button stack at their
        # full natural size (root.winfo_reqheight() once everything is
        # built) -- too short here silently SQUEEZES every image Label
        # below its own panel height (Tk shrinks a packed widget to
        # whatever's left rather than erroring), which visibly cropped
        # the bottom of every panel and threw off where mouse drags
        # actually land on it (see _on_level_drag_start and friends).
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
        # width=15 -- 50% of the previous width=30 (explicit user request).
        self.combo = ttk.Combobox(net_group, state="readonly", width=15,
                                   textvariable=self.net_var)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        target_group = ttk.Frame(setup_row)
        # padx=(96, 0) -- 24 -> 32 -> 96 (2026-09-16, explicit user
        # request twice over, "put some space between" then "3x the
        # current amount") -- same widened gap tolerance_group/auto_group
        # use below.
        target_group.pack(side=tk.LEFT, padx=(96, 0))
        ttk.Label(target_group, text="Target RMS stretch:").pack(side=tk.LEFT, padx=(0, 4))
        # One independent spinner per level (1-3), not a single spinner
        # reset to a new default every time the frontier level changes --
        # a user asked to be able to see/set every level's own target at
        # once, rather than only the current one. Both the manual
        # Inflate click (on_inflate_clicked) and "Auto" (on_auto_clicked/
        # _auto_step, which just calls on_inflate_clicked itself) read
        # self.target_rms_vars[self.subdivision_level] -- there's no
        # separate code path for either workflow.
        self.target_rms_vars = {}
        self.target_rms_display_vars = {}
        self.target_rms_spins = {}
        for level in (1, 2, 3):
            # padx=(20, 2), not (8, 2) -- widened (2026-09-16, explicit
            # user request, "add some space between target rms stretch,
            # level 1, level 2, level 3") -- separates "Target RMS
            # stretch:" from Level 1's own entry, and each level's own
            # entry from the next level's label, not just the group as a
            # whole from its neighbors (already widened separately, see
            # target_group's own comment).
            ttk.Label(target_group, text=f"Level {level}:").pack(side=tk.LEFT, padx=(20, 2))
            # Whole numbers only, no decimal place (2026-09-16, explicit
            # user request -- LEVEL_DEFAULT_TARGET_RMS_PCT's own values
            # already are whole numbers, so this never actually changes
            # any DEFAULT, just what the field itself can hold going
            # forward).
            var = tk.DoubleVar(value=round(LEVEL_DEFAULT_TARGET_RMS_PCT[level]))
            # A "converged" verdict only applies to the target it was
            # reached at -- editing THIS level's own target while it's
            # the current frontier means the current pressure hasn't
            # actually been (re)calibrated for the new value yet, so the
            # gate on re-clicking Inflate (see _update_level_action_buttons)
            # needs to lift, since otherwise a converged mesh would stay
            # stuck refusing to recalibrate even after the user asks for
            # a different target. Editing a level that ISN'T current
            # (e.g. tweaking Level 3's target while still on Level 1)
            # doesn't touch any gate -- there's nothing to invalidate yet.
            var.trace_add("write", lambda *_a, lv=level: self._on_target_rms_changed(lv))
            # This is the value everywhere ELSE in the app reads
            # (on_inflate_clicked, session save/load, the history table's
            # own recorded target, ...) -- UNCHANGED by the entry's own
            # "%"-suffixed display below, which is purely a presentation
            # layer over it (self.target_rms_display_vars), never read
            # anywhere else.
            var.trace_add("write", lambda *_a, lv=level: self._sync_target_rms_display(lv))
            self.target_rms_vars[level] = var

            # A plain Entry, not a Spinbox (2026-09-16, explicit user
            # request) -- restricted to numeric-looking input as it's
            # typed (_register_numeric_entry, no exponent/decimal -- a
            # whole-number percentage needs neither) and clamped into
            # [0, 100] once editing finishes (_commit_target_rms_entry,
            # on Enter or losing focus), rather than a Spinbox's own
            # from_/to_ range (which only ever gated its up/down ARROWS,
            # never free typing). Bound to its OWN display StringVar,
            # not `var` directly -- showing "N%" (the "%" appended once a
            # number's actually been entered/committed, per explicit
            # request, not something the user types themselves) while
            # NOT focused, and the bare number (easy to edit, no "%" to
            # work around) while it IS (_begin_edit_target_rms, on
            # <FocusIn>) -- `var` itself stays a plain float throughout,
            # `_sync_target_rms_display` above is what keeps this
            # StringVar showing "N%" in sync with it whenever `var`
            # changes from ANYWHERE (a commit here, a session load, ...).
            display_var = tk.StringVar(value=f"{var.get():.0f}%")
            self.target_rms_display_vars[level] = display_var
            spin = ttk.Entry(target_group, width=5, textvariable=display_var)
            self._register_numeric_entry(spin, allow_exponent=False, allow_decimal=False)
            spin.bind("<FocusIn>", lambda event, lv=level: self._begin_edit_target_rms(lv))
            spin.bind("<Return>", lambda event, lv=level: self._commit_target_rms_entry(lv))
            spin.bind("<FocusOut>", lambda event, lv=level: self._commit_target_rms_entry(lv))
            spin.pack(side=tk.LEFT)
            self.target_rms_spins[level] = spin
        # Pressure is no longer user-editable or separately displayed --
        # "Inflate" calibrates it itself (see on_inflate_clicked) and it's
        # already logged per level in the Convergence History table.
        self.pressure_value = DEFAULT_PRESSURE

        tolerance_group = ttk.Frame(setup_row)
        tolerance_group.pack(side=tk.LEFT, padx=(96, 0))
        ttk.Label(tolerance_group, text="Tolerance:").pack(side=tk.LEFT, padx=(0, 4))
        # The `gtol` every relax_once/relax_initial_configuration/
        # estimate_pressure_for_target_stretch call actually uses (see
        # self._current_gtol, set from this at the start of every
        # Relax/Inflate click, via _get_tolerance) -- previously a fixed,
        # non-user-facing stretchy_mesh.CONVERGENCE_GTOL. Same
        # "converged" gate/reset rationale as each target_rms_vars[level]
        # spinner above: a
        # looser-or-tighter tolerance than whatever a past "converged"
        # verdict was reached under means that verdict no longer
        # applies. A `tk.StringVar` (formatted scientific-notation text,
        # e.g. "1e-03"), not a `tk.DoubleVar` -- a DoubleVar's own string
        # form is whatever Tcl's default float-to-string gives it
        # ("0.001"), which only gets reformatted through `format` for a
        # value the SPINBOX ITSELF generates (its up/down arrows), never
        # for one set programmatically (the initial default here) --
        # verified directly: the default showed as "0.001", not "1e-03",
        # until switched to a StringVar. `_get_tolerance` parses it back
        # to a float wherever a numeric `gtol` is actually needed.
        self.tolerance_var = tk.StringVar(value=f"{DEFAULT_TOLERANCE:.0e}")
        self.tolerance_var.trace_add("write", self._on_tolerance_changed)
        # A plain Entry, not a Spinbox (2026-09-16, explicit user request,
        # same as each target_rms_vars[level] entry above) -- restricted
        # to numeric-looking input as it's typed (_register_numeric_entry,
        # WITH exponent this time -- this field's own scientific-notation
        # text, e.g. "1e-03", needs the "e"/sign that a plain percentage
        # never does). No commit-time clamp (unlike target RMS) -- only a
        # range was ever requested for that one; `_get_tolerance` already
        # falls back to DEFAULT_TOLERANCE for anything unparseable.
        self.tolerance_spin = ttk.Entry(tolerance_group, width=10, textvariable=self.tolerance_var)
        self._register_numeric_entry(self.tolerance_spin, allow_exponent=True)
        self.tolerance_spin.pack(side=tk.LEFT)

        # "Auto": visible/usable in BOTH modes (unlike the debug-only row
        # below), since it's just a scripted sequence of the SAME
        # Relax/Inflate/Subdivide actions a user could click by hand --
        # see on_auto_clicked/_auto_step for the actual driving logic.
        auto_group = ttk.Frame(setup_row)
        auto_group.pack(side=tk.LEFT, padx=(96, 0))
        self.auto_button = ttk.Button(auto_group, text="Run Simulation", command=self.on_auto_clicked)
        self.auto_button.pack(side=tk.LEFT)
        self.auto_button.state(["disabled"])  # no net loaded yet -- _update_auto_button syncs this

        # Debug-mode-only row: "Iterate for N steps" vs. "until
        # convergence" (the one thing that actually differs between the
        # two modes) plus "Validate Mesh"/"Show normals" (debug-only
        # diagnostics with no effect on the actual solve). Shown/hidden
        # by _apply_mode_visibility; both the iterate choice and Show
        # normals are forced back to their release-mode defaults whenever
        # leaving debug mode, so release mode never runs a stray
        # fixed-step request or shows a stale normals overlay left over
        # from before.
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
        # Per-VERTEX normals (2026-09-19, explicit user request, added
        # while diagnosing self-intersecting/"writhing" replay motion on
        # pinched_tri_hex -- face normals alone looked correct, but a
        # vertex sitting between inconsistently-angled faces can still
        # have a badly-behaved AVERAGE direction worth seeing directly).
        # Separate toggle/color from "Show face normals" -- either can be
        # on independently, so a face-normal problem and a vertex-normal
        # one are never visually conflated.
        self.show_vertex_normals_var = tk.BooleanVar(value=False)
        self.show_vertex_normals_check = ttk.Checkbutton(
            self.mode_row, text="Show vertex normals",
            variable=self.show_vertex_normals_var, command=self.draw)
        self.show_vertex_normals_check.pack(side=tk.LEFT)

        # ---- Status: debug-mode-only now (2026-09-16, explicit user
        # request -- "in release mode, don't show warning/error/progress
        # message"; used to be shared by both modes, always visible). ----
        self.status_frame = ttk.Frame(root)
        self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(self.status_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # ---- Convergence history: one row per subdivision level visited
        # this net session (including Level 0 now -- see module
        # docstring), showing the pressure last calibrated for it
        # (self.pressure_value -- only ever set by on_inflate_clicked's
        # calibration phase; "--" for Level 0, which has no pressure at
        # all, see _record_level_history), how many Inflate/Relax steps
        # that level took (self.iteration_count, reset to 0 on every
        # Subdivide/promotion -- see _subdivide_step/_finish_relax), the
        # stretch stats at whatever point it's currently at (updated live
        # while Inflate/Relax runs, finalized once it stops -- see
        # _record_level_history's callers, RMS shown against the CURRENT
        # "Target RMS stretch" spinner value -- see _refresh_history_table),
        # and a single combined "Convergence" cell -- the relax's own
        # `optimality` (whatever quantity stretchy_mesh._explicit_relax_loop
        # actually compares against gtol -- see its own docstring) against
        # the fixed CONVERGENCE_GTOL threshold, with a check/cross mark for
        # whether it's below it (see _refresh_history_table). height=MAX_LEVEL+1
        # (0..MAX_LEVEL) since that's the most rows this table will ever
        # hold -- a taller fixed height would just reserve blank space
        # below whatever's actually populated. ----
        self.history_frame = ttk.LabelFrame(root, text="Convergence History", padding=12)
        self.history_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        # "max_stretch" is debug-mode-only (2026-09-16, explicit -- release
        # mode dropped it in favor of "simulation_time"/"cumulative_time"
        # (renamed from "elapsed_time" 2026-09-17, explicit user request),
        # which used to be the debug-only ones instead); all three stay
        # DEFINED here regardless of mode (see _apply_mode_visibility,
        # which toggles Treeview's own `displaycolumns`), just shown/
        # hidden per mode, same "define once, show/hide" idea as
        # self.mode_row's own widgets.
        history_columns = ("level", "pressure", "steps", "max_stretch", "rms_stretch",
                            "simulation_time", "cumulative_time", "convergence")
        self.history_tree = ttk.Treeview(self.history_frame, columns=history_columns,
                                          show="headings", height=MAX_LEVEL + 1)
        # Per-column "weight" -- proportions (NOT fixed pixel widths) each
        # column's share of the table's total width should keep, tuned to
        # roughly what each column's own header/content needs relative to
        # the others (e.g. "RMS Stretch %" needs much more than "Level").
        # _rescale_history_columns (bound below to the widget's own
        # <Configure>, and called directly on every mode toggle) turns
        # these into actual pixel widths that always sum to the widget's
        # OWN current width, every column scaled by the SAME factor -- per
        # explicit user request, ALL columns proportionally stretched to
        # fill the app, not just fixed widths (an earlier attempt) or only
        # the last column absorbing leftover space (the attempt before
        # that). ttk.Treeview's own stretch=True doesn't do this -- it
        # distributes leftover space evenly PER COLUMN regardless of each
        # one's own configured width, which is what made an even earlier
        # attempt balloon every column equally instead of proportionally.
        # 2026-09-16, explicit user request: shifted weight FROM the last
        # 4 release-mode columns (rms_stretch/simulation_time/cumulative_
        # time/convergence -- convergence especially, which had the most
        # to give) TOWARD the first 3 (level/pressure/steps), which read
        # as too narrow for their own content relative to how much spare
        # room convergence in particular was left with.
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
            # stretch=False -- widths are set explicitly, proportionally,
            # by _rescale_history_columns instead; Tk's own stretch would
            # just fight that (see this block's own comment above).
            self.history_tree.column(col, width=self._history_column_weights[col],
                                      stretch=False, anchor=tk.CENTER)
        self.history_tree.bind("<Configure>",
                                lambda event: self._rescale_history_columns(event.width))
        self._release_mode_history_columns = tuple(
            col for col in history_columns if col != "max_stretch")
        self.history_tree.config(displaycolumns=self._release_mode_history_columns)
        # ttk.Treeview can only color a whole ROW, not one cell -- so the
        # Convergence column's check/cross (see _refresh_history_table)
        # comes with its whole row tinted to match, rather than leaving
        # the mark itself in the default text color.
        self.history_tree.tag_configure("converged", foreground=STATUS_COLORS["success"])
        self.history_tree.tag_configure("not_converged", foreground=STATUS_COLORS["error"])
        # A run actively in progress for its own row (2026-09-16, explicit
        # user request) -- see _refresh_history_table's own comment on
        # why this is distinct from "not_converged": red there is
        # reserved for an ACTUAL failure (step cap reached, or Stop
        # clicked), not just "hasn't converged yet, still going".
        self.history_tree.tag_configure("running", foreground=RUNNING_ROW_COLOR)
        self.history_tree.pack(fill=tk.X)

        # ---- Net (flat layout, matplotlib) + one 3D panel per level
        # (0..MAX_LEVEL, PyVista -- see LEVEL_PANEL_SIZE's own comment
        # for why), side by side. Each level panel is its OWN off-screen
        # Plotter/Label pair specifically so a native Tkinter
        # Inflate/Subdivide/Relax button can sit directly below it (see
        # _apply_mode_visibility) -- a single shared render target has no
        # way to embed a real button over just one panel. Level N's panel
        # is LIVE (redrawn every Inflate/Relax progress update) only
        # while self.subdivision_level == N; once the user subdivides
        # past it (or, for Level 0, once Relax converges and promotes
        # it), that level's last state is frozen into self.level_snapshots
        # and its panel stops updating -- see draw()/_subdivide_step/
        # _finish_relax. ----
        # No "Sync rotation" choice -- every level panel shares ONE
        # camera orientation (self.level_rotation, a quaternion), updated
        # by a drag on ANY panel (see _on_level_motion) and reapplied to a
        # level just revealed by Subdivide so it inherits the current
        # shared view rather than starting at some default one.
        view_frame = ttk.Frame(root)
        view_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(6, 14))

        # fill/expand=False here (unlike a plain pack default) -- each
        # panel below is a FIXED-size image (LEVEL_PANEL_SIZE) that never
        # grows to fill extra space, so letting this row stretch to the
        # window's full width just spreads the panels apart with dead
        # space between them instead of shrinking; hugging its own
        # natural (sum-of-panels) width keeps them packed together, with
        # any leftover window width left past the last panel instead.
        panels_row = ttk.Frame(view_frame)
        panels_row.pack(side=tk.TOP, anchor=tk.W)

        net_panel_frame = ttk.Frame(panels_row)
        # fill=tk.Y (2026-09-16, explicit user request -- "there
        # shouldn't be a button under the net", which is what used to
        # claim this same vertical space instead) stretches this frame to
        # match the row's own height (the tallest "Level N" panel, title
        # + image + action button) with no button/spacer widget of its
        # own needed to do it -- the net canvas below (already packed
        # with fill=tk.BOTH, expand=True) grows into whatever extra
        # height that leaves, rather than leaving dead space or a
        # meaningless disabled button.
        net_panel_frame.pack(side=tk.LEFT, fill=tk.Y)
        # A plain Label, not ax.set_title() -- drawing a title INSIDE a
        # PyVista panel's own rendered image clipped its top edge against
        # the panel boundary (see _render_level_pv's own Design notes);
        # a real Tkinter widget above the image has no such problem, and
        # this same approach is used for every "Level N" panel's title
        # too, so keeping Net's title as a matplotlib ax.set_title()
        # would leave it inconsistently positioned relative to its
        # neighbors' labels.
        ttk.Label(net_panel_frame, text="Net", font=self.LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        self.fig_net = plt.figure(figsize=(3.2, 4.5))
        # add_axes([0, 0, 1, 1]), not add_subplot -- add_subplot's own
        # default margins (left=0.125, right=0.9, bottom=0.11, top=0.88)
        # reserve room for axis labels/ticks that _style_2d_axis's own
        # set_axis_off() never draws anyway, so the actual plotting area
        # ended up noticeably SMALLER than the full LEVEL_PANEL_SIZE-
        # matched figure canvas (2026-09-16, explicit user request -- the
        # Net panel's own drawing area read as much smaller than every
        # "Level N" panel's, which has no such margin concept at all:
        # PyVista's own off-screen viewport already fills its entire
        # window_size). Filling the whole figure instead makes this
        # panel's actual drawing area match LEVEL_PANEL_SIZE exactly, the
        # same way every "Level N" panel's own PyVista viewport already
        # does.
        self.ax2d = self.fig_net.add_axes([0, 0, 1, 1])
        self.canvas_net = FigureCanvasTkAgg(self.fig_net, master=net_panel_frame)
        net_widget = self.canvas_net.get_tk_widget()
        net_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # Mouse-wheel-scroll zoom for the Net panel -- same idea as every
        # "Level N" panel's own self.level_zoom (_on_level_scroll), just
        # scaling _draw_target_faces' own bounding-box-derived half-extent
        # instead of a PyVista camera's parallel_scale, since this panel
        # is matplotlib, not PyVista (see LEVEL_PANEL_SIZE's own comment
        # for why level panels differ). Bound directly on the canvas
        # widget, not through any matplotlib event system, for the exact
        # same Windows/macOS-vs-X11 event shape every level panel already
        # handles (_on_level_scroll).
        self.net_zoom = 1.0
        net_widget.bind("<MouseWheel>", self._on_net_scroll)
        net_widget.bind("<Button-4>", self._on_net_scroll)
        net_widget.bind("<Button-5>", self._on_net_scroll)
        # Right-click-drag pans the Net panel (self.net_pan) -- its own
        # analogue of every "Level N" panel's self.level_pan, entirely
        # separate state (the Net panel isn't part of that shared-camera
        # group, see this class's own Design notes); middle-click resets
        # it to zero, same as a level panel.
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
        # TWO independent camera groups now (2026-09-17, explicit user
        # request -- "separate the zoom/rotation/translation of level 0
        # from level 1-3 since they look so different"): Level 0 (a
        # random-start-then-relax result, often tangled/widely spread) has
        # its OWN rotation/zoom/pan, while Levels 1-3 (an actual
        # settling/settled solid) continue sharing ONE set among
        # themselves, exactly as every level used to share before this
        # change. `_level_camera(level)` returns the (mutable, in-place-
        # updated) dict for whichever group `level` belongs to;
        # `_camera_group_levels(level)` returns every level panel that
        # needs re-rendering when THAT group's own state changes (`[0]`
        # for Level 0, `[1, 2, 3]` for any of Levels 1-3) -- a drag/scroll/
        # pan on one group's panel no longer re-renders the OTHER group's
        # panels at all, not just leaves their camera unchanged.
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
        # Debug-mode-only replay scrubber, one per level with an
        # Inflate/Subdivide button (levels 1..MAX_LEVEL -- Level 0's own
        # Relax has no captured frames to scrub, see on_relax_clicked's
        # own docstring: relax_initial_configuration doesn't support
        # capture_frames at all). 2026-09-19, explicit user request:
        # "add a slider ... to control the replay ... the user can use
        # the slider to replay the inflation" -- lets a user manually
        # inspect ANY point in a level's own last-captured Inflate
        # trajectory, not just the live end state or the one-shot
        # auto-played animation. self._level_frames[level] is that
        # level's own captured (positions, steps_taken) list, kept even
        # after Subdividing past that level so an OLDER level stays
        # scrubbable; self._level_scrub_index[level], when both it and
        # frames exist, OVERRIDES what draw() shows for that level's own
        # panel (see draw()'s own comment) -- self.positions/
        # level_snapshots themselves are NEVER touched by scrubbing, so
        # the next real action (Inflate/Subdivide) always continues from
        # the TRUE state regardless of wherever the slider is sitting.
        self._level_frames = {}
        self._level_scrub_index = {}
        self.level_replay_sliders = {}
        for level in range(0, MAX_LEVEL + 1):
            level_frame = ttk.Frame(panels_row)
            # No fill/expand -- see panels_row's own comment on why
            # every panel hugs its own fixed image size instead.
            level_frame.pack(side=tk.LEFT)
            self.level_frames[level] = level_frame
            button = ttk.Button(level_frame, text="Relax" if level == 0 else "Inflate")
            self.level_action_buttons[level] = button
            if level > 0:
                # Packed FIRST among this frame's own BOTTOM-side widgets
                # (Tk stacks additional bottom-packed siblings upward from
                # the true bottom edge in packing order), so it lands
                # BELOW the button once that's packed next -- "under the
                # subdivide/inflate button[s]", per the request.
                slider = ttk.Scale(level_frame, from_=0, to=0, orient=tk.HORIZONTAL,
                                    command=lambda v, lvl=level: self._on_replay_slider_moved(lvl, v))
                slider.state(["disabled"])
                self.level_replay_sliders[level] = slider
                slider.pack(side=tk.BOTTOM, in_=level_frame)
            # Button packed BEFORE the panel widget, at BOTTOM -- packing
            # it AFTER an expand=True widget would starve it of space,
            # since that widget (packed first) would already have
            # claimed the entire remaining cavity by the time it's
            # placed. No fill=tk.X (2026-09-16, explicit user request --
            # a button spanning the panel's full width read as an
            # oversized bar); left at its own natural, text-sized width
            # instead, which pack's own default center anchor centers
            # under the panel above it.
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
        # Level 0/1's own explicit spring-edge override (see
        # _fan_level_edges) and its ORIGIN, the loaded net's own explicit
        # "edges"/"face_edge_ids" fields (see load_stretchy_mesh_edges) --
        # None past Level 1, or for any net/session with no such fields.
        self.edges = None
        self.base_edges = None
        self.base_face_edge_ids = None
        self.target_layout = None
        # interactive_builder_app's own saved "builder_connections" (its
        # bezier control points included), or None -- see on_select_net's
        # own comment for when this is/isn't populated alongside
        # target_layout.
        self.target_connections = None
        self.positions = None
        self.iteration_count = 0
        self.last_stats = {}
        self.level_history = {}
        self.stop_event = None
        # Whether the CURRENT frontier level (self.subdivision_level) has
        # a Relax/Inflate run actively in progress right now -- set/
        # cleared in lockstep with _set_level_action_button_running (the
        # single source of truth for the per-level button's own "Stop"
        # state), read by _refresh_history_table to color that level's
        # row yellow ("running") instead of red ("not_converged") while
        # it's still mid-run (2026-09-16, explicit user request -- red
        # should mean "actually failed to converge", either the step cap
        # was reached or Stop was clicked, not just "hasn't converged
        # YET, still going").
        self._level_running = False
        # Backing state for the Convergence History table's "Simulation
        # Time"/"Cumulative Time" columns (release-mode columns now, see
        # history_columns' own comment) -- wall-clock time (wraps
        # time.perf_counter(), not the solve's own step count) spent in
        # the CURRENT level's own pressure-calibration phase
        # (_on_pressure_calibrated, None for Level 0/Relax, which has no
        # pressure to calibrate) and, for Level 0 only, its own streamed
        # relax phase (_run_relax_stream) -- Level 1+ no longer has a
        # separate "sim" phase at all (2026-09-17, explicit user request):
        # pressure calibration's own winning trial IS the Inflate result
        # now (see on_inflate_clicked), so all of a Level 1+ row's own
        # wall-clock time is "precomp". The `_start_time` pair marks when
        # each phase began (None between runs); the `_current_*_time_s`
        # pair is what _record_level_history actually reads -- precomp is
        # set ONCE, when calibration finishes (it has no progress callback
        # of its own to update live, though the poll loop that waits on it
        # still ticks it forward every 100ms -- see _run_background); sim
        # updates LIVE on every progress callback, same as iteration_count,
        # then again at the phase's own finish. Reset to None (see
        # on_select_net/_subdivide_step/_finish_relax's promotion branch)
        # anywhere iteration_count itself resets, so a freshly-promoted or
        # freshly-Subdivided level's row doesn't show the PREVIOUS level's
        # own timing before anything has actually run at the new one.
        # Deliberately NEVER incremented during a frame replay (see
        # _start_frame_replay) -- that's pure animation of an already-
        # finished trial's own cached positions, not new simulation work.
        self._precomp_start_time = None
        self._sim_start_time = None
        self._current_precomp_time_s = None
        self._current_sim_time_s = None
        # "Computing..." placeholder (see _start_computing_animation):
        # which level's OWN panel is currently showing it (None normally)
        # -- _render_level_pv skips that level entirely while this is set,
        # so nothing (a resize, a drag-rotate) can paint a stale image
        # over it mid-calibration. _computing_after_id is the pending
        # `root.after` callback driving its dot-cycle animation.
        self._computing_level = None
        self._computing_after_id = None
        self._computing_dots = 0
        # Frame-replay state (see _start_frame_replay/_replay_step): the
        # winning calibration trial's own cached positions (estimate_
        # pressure_for_target_stretch's capture_frames), played back
        # purely for display once calibration lands on a pressure --
        # _replay_after_id is the pending `root.after` callback driving
        # playback, None when no replay is in progress.
        self._replay_after_id = None
        self._replay_frames = None
        self._replay_index = 0
        self._replay_final_result = None
        self._replay_base_iteration_count = 0
        # The gtol actually in effect for the run currently underway (or
        # the last one that ran) -- captured from self.tolerance_var at
        # the moment Relax/Inflate starts (_on_pressure_calibrated/
        # on_relax_clicked), not re-read live while a run is in progress
        # (the spinner is disabled for the duration anyway -- see
        # _set_controls_enabled), and recorded into self.last_stats/
        # level_history so _refresh_history_table always shows the
        # threshold an already-finished run actually used, even after
        # the spinner's own value later changes.
        self._current_gtol = DEFAULT_TOLERANCE
        # Same rationale as self._current_gtol, for the current level's
        # own "Target RMS stretch" spinner instead -- captured whenever
        # it's actually USED (on_inflate_clicked, or a level's own
        # spinner value being read at _finish_relax/_subdivide_step), not
        # re-read live from self.target_rms_vars by _refresh_history_table,
        # so an already-finished level's row keeps showing the target IT
        # was actually calibrated against even if that level's spinner is
        # edited again afterward (a user reported every row showing the
        # CURRENT level's target instead of its own).
        self._current_target_rms_pct = self.target_rms_vars[1].get()
        # Whether the "Auto" button's own scripted sequence is currently
        # driving the app (see on_auto_clicked/_auto_step) --
        # _auto_attempted_level names the level Auto has already made its
        # ONE Relax/Inflate attempt at (no retries within a level, per
        # explicit user request -- see _auto_step's own docstring), reset
        # to None the moment _auto_step notices the CURRENT level has
        # changed since the last time it ran, rather than at every
        # individual Subdivide/promotion call site, so there's exactly
        # ONE place this logic lives).
        self._auto_active = False
        self._auto_attempted_level = None
        self.current_path = None
        self.current_label = None
        self.label_to_path = {}
        # The currently-loaded net's own raw file content (see
        # on_select_net/on_save_session_clicked/on_load_session_clicked)
        # -- None until a net (or a saved session carrying one) is loaded.
        self._net_file_json = None
        self._apply_plot_theme()
        self.refresh_net_list()
        self._apply_mode_visibility()
        if self.current_label:
            self.on_select_net()
        # Fits the window's own starting height to release mode's
        # (shorter) default layout -- see _refit_window_height's own
        # docstring for why this has to come AFTER on_select_net's own
        # draw() call, not right after _apply_mode_visibility above.
        self._refit_window_height()

    def _init_ui_fonts(self):
        """Computes self.LEVEL_TITLE_FONT/LEVEL_MESSAGE_FONT (and the
        File menu's own font, see _build_menu) from "Choose a net"'s own
        actual rendered font -- a plain ttk.Label with no font= override,
        so it renders via sv_ttk's default TLabel style, routed to the
        named font "SunValleyBodyFont" (see _scale_ui_fonts). Must run
        AFTER _scale_ui_fonts (needs its final, already-scaled size), and
        AFTER sv_ttk.set_theme (SunValleyBodyFont doesn't exist before
        that). Using its actual .actual() family/size (not a hardcoded
        string) is what makes every title/message label genuinely match
        "Choose a net" in both family and size (2026-09-18, explicit user
        request) -- a family name here that isn't real just silently
        falls back to a generic default (see LEVEL_TITLE_FONT's own
        comment for the bug this replaces)."""
        reference = tkfont.nametofont("SunValleyBodyFont", root=self.root).actual()
        self.LEVEL_TITLE_FONT = (reference["family"], reference["size"])
        self.LEVEL_MESSAGE_FONT = self.LEVEL_TITLE_FONT

    def _scale_ui_fonts(self):
        """Scales every named Tk/ttk font by UI_FONT_SCALE, once at
        startup, right after sv_ttk.set_theme -- covers the whole UI's
        text size in one place rather than a per-widget font= override
        everywhere. sv_ttk's dark/light themes route almost every ttk
        style (TButton, TLabel, TLabelframe.Label, Treeview, its Heading,
        ...) through a handful of its OWN named Tcl fonts
        (SunValleyBodyFont, SunValleyCaptionFont, ...) rather than the
        standard TkDefaultFont/TkTextFont/etc, so scaling only the
        standard names would miss most of the UI -- tkfont.names()
        returns every named font known to the interpreter, Sun Valley's
        included, so this reaches both in one pass. A size of 0 (some
        internal fonts use this) means "use the platform default" and
        stays that way rather than becoming 0 * scale = 0."""
        for name in tkfont.names(self.root):
            font = tkfont.nametofont(name, root=self.root)
            size = font.cget("size")
            if size == 0:
                continue
            sign = -1 if size < 0 else 1
            font.configure(size=sign * round(abs(size) * UI_FONT_SCALE))
        # Treeview's rowheight is set by sv_ttk's theme file to
        # SunValleyBodyFont's line spacing PLUS A FIXED PADDING, computed
        # once when the theme loads -- it doesn't auto-track a font
        # resize done afterward, so rows would stay sized for the OLD
        # (smaller) font, clipping the new, taller text. Recomputed here
        # the same way (see sv_ttk's dark.tcl "Treeview" style) now that
        # SunValleyBodyFont has its final scaled size.
        body_font = tkfont.nametofont("SunValleyBodyFont", root=self.root)
        ttk.Style(self.root).configure("Treeview", rowheight=body_font.metrics("linespace") + 3)

    def _build_menu(self):
        """This app's only menu bar -- File > Load.../Save..., Load above
        Save since it's the more common entry point (opening a
        previously-saved session before continuing it). See
        on_save_clicked/on_load_clicked for what the two actually do.

        Explicit `font=` on every Menu/add_command call here (2026-09-18,
        explicit user request -- "the file menu text is a bit small"):
        Windows renders the native menu bar via its OWN chrome, which
        IGNORES "TkMenuFont"'s own configured size -- _scale_ui_fonts
        already scales that named font like every other one in the app,
        with no visible effect on this specific widget, a known
        Tk-on-Windows limitation for the top-level menu bar specifically.
        An explicit per-widget/per-item font IS respected even where the
        named-font default isn't. Reuses self.LEVEL_TITLE_FONT (see
        _init_ui_fonts) -- "Choose a net"'s own actual family/size --
        rather than TkMenuFont's own family/a separately-guessed size, so
        the menu genuinely matches the rest of the UI (2026-09-18,
        explicit user request -- "make sure the font size is uniform...
        the font is uniform" -- an earlier version of this used
        TkMenuFont's family at a bigger, independently-chosen size,
        which read both mismatched AND "a tad" too large)."""
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
        """The main differences between the two modes: whether the
        steps-vs-convergence radio row (plus Validate Mesh/Show normals)
        is shown, and whether the Convergence History table's "Max
        Stretch %" column is shown (self.history_tree's own
        `displaycolumns` -- debug-only, 2026-09-16 explicit; "Simulation
        Time"/"Cumulative Time" are release-mode columns now instead --
        see history_columns' own comment in __init__ -- all three stay
        DEFINED in both modes, just hidden per mode, so no data is lost
        switching back and forth). Forces the steps choice back to
        "convergence" and Show normals off when leaving debug mode, so
        release mode never runs a stray fixed-step request or shows a
        stale normals overlay left over from before."""
        self.root.title(f"{APP_TITLE}{' (debug mode)' if self.debug_mode else ''}")
        self.history_tree.config(
            displaycolumns="#all" if self.debug_mode else self._release_mode_history_columns)
        # Changing displaycolumns doesn't resize the WIDGET itself, so no
        # <Configure> fires on its own -- re-run the same proportional
        # rescale by hand (see _rescale_history_columns's own docstring),
        # against the table's current own width.
        self._rescale_history_columns(self.history_tree.winfo_width())
        if self.debug_mode:
            self.mode_row.pack(fill=tk.X, pady=(8, 0))
            self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
            # Sliders packed BEFORE their own level's button (so they
            # land below it, same bottom-stacking order __init__ used --
            # see its own comment) -- both debug-only, same as the
            # buttons themselves.
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
            # The whole status frame, not just its text -- 2026-09-16,
            # explicit user request ("in release mode, don't show
            # warning/error/progress message").
            self.status_frame.pack_forget()
            # Per-level Relax/Inflate/Subdivide/Stop buttons are debug-
            # only now too (2026-09-16, explicit -- "release mode will
            # just use auto"): hidden here, NOT destroyed, so every other
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
        """Re-fits the window's own HEIGHT to whatever's actually visible
        right now (2026-09-16, explicit user request -- release mode used
        to keep debug mode's own taller height, leaving dead space below
        the now-hidden mode_row/status_frame/per-level buttons). Called
        from three places, every one a genuine MODE change (or the
        equivalent first-time framing) rather than routine net switching:
        once at the END of __init__ (AFTER on_select_net's own draw()
        call, not right after _apply_mode_visibility earlier in __init__
        -- see below for why that ordering matters), from _on_toggle_
        debug_mode right after _apply_mode_visibility, and from
        on_load_session_clicked's own tail (its debug_mode can differ
        from whatever was showing before the load). Deliberately NOT
        called from plain on_select_net (a fresh net pick, same mode) --
        picking a different net shouldn't fight a manual resize the user
        already made; only an actual mode change re-fits the window on
        its own.

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
        # "success" is always dropped, in both modes -- e.g. "Converged
        # after N steps..." -- since the per-level button states and the
        # Convergence History table already show that. Release mode also
        # drops routine "info" narration (e.g. "Relaxing... N steps so
        # far...", "Relaxed... Promoted to Level 1...", "Subdivided to
        # level N...") for the same reason -- the live panel redraw,
        # button state, and history row already say all of it; debug mode
        # keeps "info" since it's meant for someone working on this app,
        # not an end user. "warn"/"error" (Stop requested, a solver
        # crash) still get SET here in both modes (still meaningful
        # internal state, e.g. for a debug-mode session that toggles on
        # mid-run), but release mode never actually shows them -- the
        # whole status_frame is unpacked there (_apply_mode_visibility,
        # 2026-09-16 explicit -- used to be genuinely visible in both
        # modes, the one case this comment used to carve out).
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
        # actually populates it), so every "Level N" panel reserves the
        # exact same fixed height regardless of whether its own message
        # is in use right now. Packed BEFORE the image label below, with
        # side=tk.BOTTOM, so it claims its own strip at the bottom of the
        # frame first; the image label's fill=tk.BOTH/expand=True then
        # fills whatever's left between the title and this strip. Skipping
        # this for Level 0 (matching "only used for 1-3") would leave its
        # own frame one strip SHORTER than the others -- exactly the same
        # cross-panel height-mismatch failure mode already hit once with
        # the "Computing..." placeholder (see _tick_computing_animation's
        # own comment) -- so it's always built, just always blank at
        # Level 0. `padx` is left at 0 here -- _set_level_message computes
        # and applies it per-message instead of a static value.
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
        # Right-click-drag pans (self.level_pan, shared across every
        # level panel like level_rotation/level_zoom); middle-click
        # resets that pan back to zero -- see their own docstrings. No
        # per-level state to capture at press time (unlike rotate/zoom,
        # a pan drag needs no per-panel scale -- see self.level_pan's own
        # comment in __init__), so every level's label shares these same
        # three plain, level-agnostic handlers.
        label.bind("<ButtonPress-3>", self._on_level_pan_start)
        label.bind("<B3-Motion>", self._on_level_pan_motion)
        label.bind("<ButtonRelease-3>", self._on_level_pan_end)
        label.bind("<Button-2>", self._on_level_pan_reset)
        # Windows/macOS deliver <MouseWheel> with event.delta; Linux
        # (X11) delivers wheel motion as Button-4/Button-5 clicks instead
        # -- binding all three covers every platform this app might run
        # on.
        label.bind("<MouseWheel>", self._on_level_scroll)
        label.bind("<Button-4>", self._on_level_scroll)
        label.bind("<Button-5>", self._on_level_scroll)

    @staticmethod
    def _initial_level_rotation():
        """Builds the starting self.level_rotation quaternion so it
        reproduces the same default view LEVEL_DEFAULT_AZIM/ELEV used to
        give directly (see _render_level_pv's old azim/elev formula) --
        this is the ONLY place spherical angles are converted into a
        rotation; every update after this point (_on_level_motion) works
        with the quaternion directly and never decomposes it back into
        angles, which is what avoids gimbal lock. Constructs an explicit
        orthonormal (direction, right, up) frame for that view and reads
        the rotation straight off it as a 3x3 matrix -- a rotation matrix
        IS exactly [x-axis-image | y-axis-image | z-axis-image] as
        columns, so mapping canonical axes (1,0,0)/(0,1,0)/(0,0,1) to
        (direction, right, up) is this matrix by construction."""
        azim, elev = np.radians(LEVEL_DEFAULT_AZIM), np.radians(LEVEL_DEFAULT_ELEV)
        direction = np.array([np.cos(elev) * np.cos(azim), np.cos(elev) * np.sin(azim),
                               np.sin(elev)])
        world_up = np.array([0.0, 0.0, 1.0])
        # This cross-product order (world_up x direction, then direction x
        # right) is what makes [direction | right | up] a RIGHT-handed
        # (determinant +1) frame -- the other order is left-handed and
        # scipy's Rotation.from_matrix rejects it outright.
        right = np.cross(world_up, direction)
        right /= np.linalg.norm(right)
        up = np.cross(direction, right)
        return Rotation.from_matrix(np.column_stack([direction, right, up]))

    def _level_camera(self, level):
        """The mutable camera-state dict (`{"rotation", "zoom", "pan"}`)
        for `level`'s own group -- see __init__'s own Design notes on why
        Level 0 has an independent one from Levels 1-3's shared one.
        Callers mutate the returned dict's own keys in place (or replace
        just one key, e.g. `cam["zoom"] = ...`) rather than reassigning
        self._level0_camera/_level13_camera themselves."""
        return self._level0_camera if level == 0 else self._level13_camera

    def _camera_group_levels(self, level):
        """Every level panel sharing `level`'s own camera group -- just
        `[0]` for Level 0, every OTHER level currently built for anything
        else (Levels 1-3)."""
        if level == 0:
            return [0]
        return [lvl for lvl in self.level_plotters if lvl != 0]

    def _render_camera_group(self, level):
        """Re-renders every panel in `level`'s own camera group (NOT
        every level panel -- see _camera_group_levels) -- what a drag/
        pan/scroll on one group's panel should refresh, now that the two
        groups no longer share a single camera."""
        for lvl in self._camera_group_levels(level):
            self._render_level_pv(lvl)

    def _on_level_drag_start(self, event):
        self._level_dragging = True
        self._level_last_xy = (event.x, event.y)
        self._level_drag_group_level = self._level_of_label.get(event.widget, 1)

    def _on_level_motion(self, event):
        """Left-click-drag on a level panel rotates THAT panel's own
        camera group's orientation (self._level_drag_group_level, set at
        press time -- see _on_level_drag_start) and re-renders every
        panel in that SAME group (_render_camera_group) -- not every
        level panel any more, now that Level 0 and Levels 1-3 have
        independent cameras (see __init__'s own Design notes). This
        app's own analogue of mplot3d's built-in
        drag rotation, reimplemented here since PyVista/VTK panels are
        plain images, not interactive widgets (see _build_level_pv_panel).
        Re-rendering all four costs ~30ms (measured), well within
        real-time feel -- an earlier version of this only re-rendered the
        dragged panel, misdiagnosing a completely different bug
        (plotter.screenshot() not actually re-rendering on a camera-only
        change without an explicit render() first, see _render_level_pv)
        as a performance problem; now that that's fixed, there's no
        reason to hold the other three back until the drag ends.

        Composes two small rotations -- about the CURRENT up axis for a
        horizontal drag, about the CURRENT right axis for a vertical one
        -- onto the existing quaternion, rather than accumulating into a
        stored azimuth/elevation pair. This is a free trackball rotation:
        because "up" is whatever this group's own rotation currently says
        it is (not re-pinned to world +z every frame the way the old
        azim/elev formula did), there's no pole for elevation to
        approach and lock up near -- the earlier version had to clamp
        elevation to +-89 degrees for exactly this reason; this version
        needs no clamp at all."""
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
        # One last explicit render, in case the button release didn't
        # come with its own trailing motion event -- _on_level_motion
        # already keeps this group's panels live-updated during the drag
        # itself, so this is just a safety net for that edge case, not
        # the primary sync point.
        if self._level_drag_group_level is not None:
            self._render_camera_group(self._level_drag_group_level)
        self._level_drag_group_level = None

    def _on_level_pan_start(self, event):
        self._level_panning = True
        self._level_pan_last_xy = (event.x, event.y)
        self._level_pan_group_level = self._level_of_label.get(event.widget, 1)

    def _on_level_pan_motion(self, event):
        """Right-click-drag on a level panel translates THAT panel's own
        camera group's pan (self._level_pan_group_level, set at press
        time -- see _on_level_pan_start; the pan value itself is a 2D NDC
        offset applied via vtkCamera's own SetWindowCenter in
        _render_level_pv -- see its own comment in __init__ for why NDC
        rather than a 3D world-space offset) and re-renders every panel
        in that SAME group -- pan's own analogue of _on_level_motion's
        rotation drag. Needs no per-panel scale at all (unlike an
        earlier, world-space version of this) since NDC is already
        resolution/scale-independent -- every level panel renders at the
        same LEVEL_PANEL_SIZE, so converting the drag through that one
        fixed size, rather than through whichever panel happened to be
        dragged, is what makes the resulting shift come out visually
        IDENTICAL (same pixel count) on every panel in the group.

        Sign/scale verified directly (not just derived): rendering a
        known point with a known SetWindowCenter(x, y) showed x=+1 moves
        the image LEFT by exactly half the panel's own width, and y=+1
        moves it DOWN by half the panel's own height -- so a rightward
        drag (dx > 0) needs a NEGATIVE x term, while a downward drag
        (dy > 0, screen y already growing downward like SetWindowCenter's
        own y) needs a POSITIVE y term, unlike x."""
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
        """Middle-click on a level panel resets THAT panel's own camera
        group's pan/zoom/rotation all the way back to their defaults
        (2026-09-16, explicit user request -- this used to reset pan
        alone; 2026-09-17, explicit user request -- Level 0 and Levels
        1-3 are now independent groups, so this only resets the ONE
        group the click landed on, not every panel) -- one click gets
        every panel in that group back to its original framing, rather
        than needing pan reset plus manually scrolling/dragging zoom and
        rotation back by feel. Each group's own rotation goes back
        through _initial_level_
        rotation() (the exact same starting quaternion __init__ builds),
        not just "identity", since this app's own default view is
        deliberately non-axis-aligned (see LEVEL_DEFAULT_ELEV/AZIM).
        `event=None` (no caller currently does this) falls back to
        resetting the Levels-1-3 shared group."""
        level = self._level_of_label.get(event.widget, 1) if event is not None else 1
        cam = self._level_camera(level)
        cam["pan"] = np.zeros(2)
        cam["zoom"] = 1.0
        cam["rotation"] = self._initial_level_rotation()
        self._render_camera_group(level)

    def _on_level_scroll(self, event):
        """Mouse-wheel-scroll on a level panel zooms THAT panel's own
        camera group (self._level_camera) and re-renders every panel in
        that SAME group -- Level 0 and Levels 1-3 zoom independently now
        (see __init__'s own Design notes), not the single shared state
        every panel used to scroll together. event.num is Button-4/5 on
        X11 (no event.delta there); event.delta is Windows/macOS's own
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
        """One "Level N" panel, drawn every call from whatever
        faces/positions/face_of_fine draw() passes it (live, frozen
        snapshot, or all-None for "not reached yet this session" -- see
        draw()'s own docstring). Faces are always triangles from Level 1
        on (Level 0's own topology, and everything Subdivide derives
        from it, is all-triangle -- see module docstring), so no
        fan/n-gon handling is needed. Colors every face by its ORIGINAL
        base face (`face_of_fine`, the same per-base-face self.colors
        the Net panel and every level's panel use) as PER-CELL RGB
        scalars -- one `pv.PolyData`/`add_mesh` call for the whole mesh
        (PyVista/VTK's own depth buffer handles occlusion correctly
        regardless of face count or convexity, unlike the old
        matplotlib/`_CullableFace` rendering this replaced -- see module
        docstring).

        Debug mode's "Show normals" toggle (self.show_normals_var) also
        draws each triangle's own outward normal here, as one line
        segment per face from its centroid, in NORMAL_COLOR -- an
        inward-pointing one (see _validate_mesh) is immediately obvious
        this way, without needing to reason about winding order by hand.
        Each segment is scaled to NORMAL_LENGTH_FRACTION (0.5) of that
        SAME triangle's own mean edge length (computed directly from
        `positions`, the mesh's CURRENT -- not rest -- geometry, so the
        arrow always reads as "about half an edge long" relative to
        whatever's actually on screen, regardless of overall scale or how
        far from rest length this mesh has stretched) -- per an explicit
        user request that these stay proportionate rather than a fixed
        pixel/world length that could dwarf or vanish against a very
        small or very large mesh (a full edge length, tried first, read
        too long against a dense/fine mesh)."""
        plotter = self.level_plotters[level]
        plotter.clear()
        if faces is not None:
            vertex_ids = sorted(positions)
            idx = {v: i for i, v in enumerate(vertex_ids)}
            points = np.array([positions[v] for v in vertex_ids])
            # One add_mesh call PER BASE FACE, not one for the whole
            # mesh with a per-cell "colors" scalar array (2026-09-16,
            # explicit user request -- wireframe edges should be "the
            # color halfway between white and the polygon color", which
            # only makes sense as a PER-FACE edge color; VTK's own
            # edge_color is a single uniform color per add_mesh call, so
            # getting a different one per base face needs a separate
            # call per base face group -- still one scene/depth buffer
            # (plotter.clear() above, not between these calls), so
            # occlusion across groups still works exactly like the old
            # single-call version did.
            # Grouped by self.group_of_base_face, not raw base_face index
            # directly -- every triangle from one Polygon-Fold-subdivided
            # source polygon (interactive_builder_app's own
            # "source_polygon_id", see _face_colors_by_group) shares both
            # its color AND its own add_mesh call this way, so it reads
            # as one uniformly-colored/outlined polygon at every
            # subdivision level, same as an ordinary (non-folded) one
            # always has.
            groups_present = sorted(set(self.group_of_base_face[bf] for bf in set(face_of_fine)))
            for group in groups_present:
                face_color = self.color_by_group[group]
                group_faces = [f for f, bf in zip(faces, face_of_fine)
                               if self.group_of_base_face[bf] == group]
                face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in group_faces])
                mesh = pv.PolyData(points, face_conn)
                plotter.add_mesh(mesh, color=face_color, show_edges=True,
                                  edge_color=_midpoint_color("white", face_color),
                                  line_width=SUBDIVISION_EDGE_WIDTH)

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

            # Each level fills its OWN panel to 90% from its OWN current
            # bounding box (2026-09-18, explicit user request, superseding
            # a same-day earlier attempt at a FIXED reference framing
            # shared from Level 1's converged state -- that made the
            # camera framing itself identical across levels, verified
            # directly, but a real net showed why that alone isn't
            # enough: the app's own per-level target RMS % TAPERS down
            # (80/40/10 by default), and the converged mesh's own
            # absolute size can genuinely shrink a lot across levels as a
            # result (a Dodecahedron net's own half-extent measured
            # 2.36 -> 1.79 -> 1.41 across levels 1-3) -- a literally fixed
            # camera then just honestly displays that real shrinkage,
            # which read as "inconsistent sizes" rather than the
            # consistent LOOK actually wanted. Rotation/pan/zoom
            # (self._level13_camera) stay SHARED across Levels 1-3
            # regardless -- that's a separate, still-current mechanism
            # (see __init__'s own Design notes) this change doesn't touch;
            # only the auto-fit center/half computation reverted to being
            # per-level again.
            # `half` is the shape's own BOUNDING-SPHERE radius (largest
            # distance from center to any vertex), not half of the
            # largest single WORLD-AXIS extent as an earlier version used
            # (2026-09-18, explicit user request -- "90% zoom means both
            # width and height are at most 90%"): a single-axis measure
            # UNDERESTIMATES the true on-screen extent for a shape viewed
            # from an oblique angle (its diagonal reaches further across
            # the screen than any one axis's own half-length does), which
            # is exactly what let real renders clip past the top/bottom
            # edge despite `_level_zoom_fill` claiming "90%" -- a proper
            # radius bounds the shape from EVERY direction at once, so
            # whatever angle the shared rotation currently shows, it's
            # guaranteed to still fit. `_render_level_pv`'s own aspect
            # handling (`max(1, panel_height/panel_width)`) then makes
            # the PANEL'S OWN NARROWER dimension (width, for these
            # portrait panels) the exact `_level_zoom_fill(level)`
            # fraction of the frame, with the taller dimension getting
            # EXTRA slack rather than less -- so both width and height
            # end up at MOST that fraction, never more.
            #
            # No separate "WIREFRAME_VIEW_FILL" margin multiplied in here
            # any more, either (was 0.8, REMOVED entirely) -- it and
            # `_level_zoom_fill` were two independently-tuned "how much
            # margin" knobs that ended up COMPOUNDING as `_level_zoom_
            # fill / WIREFRAME_VIEW_FILL` (0.9 / 0.8 = 112.5%) instead of
            # each acting alone, which is the OTHER reason "fill 90%"
            # was actually rendering well past 100% and clipping --
            # `_level_zoom_fill` alone is now the single, authoritative
            # fill fraction.
            lo, hi = points.min(axis=0), points.max(axis=0)
            center = (lo + hi) / 2
            self._level_center[level] = center
            self._level_half[level] = float(np.linalg.norm(points - center, axis=1).max()) + 1e-6
        self._render_level_pv(level)

    def _render_level_pv(self, level):
        """Positions an orthographic (parallel-projection) camera from
        `level`'s OWN camera group's rotation (self._level_camera(level)
        -- see __init__'s own Design notes on why Level 0 and Levels 1-3
        no longer share one) at a distance derived from THIS level's own
        current bounding box (self._level_center/_level_half, set by
        _draw_level_panel -- necessary since neither a pure-spring relax
        nor a pressure inflation has any mechanism keeping the result
        near the origin or at a familiar scale), renders off-screen, and
        blits the result into self.level_labels[level]. Parallel rather
        than perspective projection to give every panel fixed, comparable
        axis-limit-like framing with no foreshortening.

        Skips entirely (leaving the panel's own "Computing..." text
        alone) while `level` is the one currently showing it (self.
        _computing_level, see _start_computing_animation) -- the single
        choke point every caller (draw(), a drag-rotate's own
        _render_camera_group/_render_all_level_panels, a resize) goes
        through, so nothing can paint a stale image back over the
        placeholder mid-calibration.

        The panel's
        "Level N" title is a separate Tkinter Label (see
        _build_level_pv_panel), not drawn into this image -- a title
        drawn INSIDE the rendered scene (tried first, via
        plotter.add_text) clipped against the panel's own top edge (a
        "0" losing its top arc, reading as a "U") since a VTK text
        actor's positioning/justification doesn't guarantee it stays
        fully inside the viewport the way a real widget placed above the
        image trivially does."""
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
        # Read straight off the quaternion, NOT pinned to world (0,0,1) --
        # a fixed world-up is exactly what forces elevation into a
        # separate angle that locks up near the poles (see
        # _on_level_motion's docstring); letting up rotate freely with
        # the camera is what a quaternion buys.
        camera.up = tuple(up)
        # parallel_scale sets the camera's vertical half-height in world
        # units -- the horizontal half-width it implies is narrower by
        # the window's own aspect ratio (width/height), which would crop
        # the shape's wider dimension on this portrait-shaped panel if
        # left at exactly `half`. Scaling up by height/width (when
        # portrait) guarantees the full half-extent fits in BOTH
        # directions, matching what set_box_aspect([1,1,1]) effectively
        # gave the old matplotlib panels for free; dividing by
        # _level_zoom_fill(level) (Level 0 vs Levels 1-3 default to
        # different fill fractions, see that pair's own comment) then
        # shrinks the shape within that guaranteed-fitting frame.
        panel_width, panel_height = _level_panel_size(level)
        # cam["zoom"] is a divisor here (like _level_zoom_fill) since
        # parallel_scale is a visible-world-HEIGHT, not a magnification --
        # a bigger zoom (scrolled in) must shrink parallel_scale.
        camera.parallel_scale = (half * max(1.0, panel_height / panel_width)
                                  / _level_zoom_fill(level) / cam["zoom"])
        # cam["pan"] (right-click-drag, _on_level_pan_motion) is applied
        # HERE, as a pure post-projection viewport shift, rather than by
        # moving focal_point/position above -- see its own comment in
        # __init__ for why: this way it can't desync between panels of
        # different scale, and can't move any panel's own orbit center
        # out from under a later rotation either.
        camera.SetWindowCenter(*cam["pan"])
        plotter.reset_camera_clipping_range()
        # plotter.screenshot() does NOT re-render on a camera-only change
        # by itself -- verified directly: two screenshots taken after
        # only moving the camera, with no explicit render() between them,
        # come back pixel-IDENTICAL. An explicit render() first is what
        # actually asks VTK to redraw the scene from the camera's current
        # position before screenshot() reads the framebuffer back -- this
        # was the actual cause of rotation looking "stuck" (nothing to do
        # with Tk's own redraw/event-queue timing, which earlier fixes in
        # this area wrongly assumed).
        plotter.render()
        image = plotter.screenshot(return_img=True)
        self.level_photos[level] = ImageTk.PhotoImage(Image.fromarray(image))
        # text="" clears whatever "Computing..." text _tick_computing_
        # animation last set -- harmless to leave (Label's default
        # compound="none" shows the image over it regardless), but tidier
        # than leaving stale placeholder text configured on the widget.
        self.level_labels[level].configure(image=self.level_photos[level], text="")

    # ---- "Computing..." placeholder (pressure calibration) ----

    # How often the "Computing" dot-cycle advances (nothing->1->2->3->
    # repeat) -- purely decorative, so any value that reads as "still
    # working" without being distractingly fast is fine.
    COMPUTING_DOT_INTERVAL_MS = 500

    def _set_level_message(self, level, text):
        """Sets `level`'s own bottom status message (self.
        level_message_labels), left-anchored (anchor=tk.W, set once at
        construction) but with `padx` computed HERE to make THIS specific
        `text` land visually centered under the panel -- true tk.CENTER
        anchoring was tried first and rejected (explicit user request,
        2026-09-17): it re-anchors from scratch on every update, so a
        message's own LEFT edge visibly jumps every time its length
        changes. A single fixed left inset (also tried) doesn't actually
        look centered for every message either -- "Computing" (no dots
        yet) is much shorter than "Replay frame 27 / 93", so a pad tuned
        for one read noticeably off-center for the other (observed
        directly). Measuring this specific string's own rendered width
        (self._level_message_font, a real Font object -- LEVEL_MESSAGE_
        FONT itself is just the plain (family, size) tuple Tk widgets
        take, which has no .measure()) and computing the inset that
        would ACTUALLY center it gives the best of both: visually
        equivalent to true centering for whatever message is showing
        right now, but the position only shifts by however much THIS
        message's own width actually changed since the last call (a
        dot's width for "Computing" -> "Computing.", near zero for most
        frame-count changes) rather than a full from-scratch re-center."""
        text_width = self._level_message_font.measure(text)
        pad = max(0, (_level_panel_size(level)[0] - text_width) // 2)
        self.level_message_labels[level].configure(text=text, padx=pad)

    def _start_computing_animation(self, level):
        """Blanks `level`'s own panel image (plain background, no mesh)
        and shows an animated "Computing..." in its bottom message area
        (_set_level_message) for as long as pressure calibration
        (estimate_pressure_for_target_stretch) is searching -- explicit
        user request, 2026-09-17: most of calibration's own several
        relax_once trials are thrown away (see on_inflate_clicked), so
        there's no single meaningful shape to show frame-by-frame while
        it runs, unlike Level 0's own Relax (which stays live -- there's
        only ever one run there, see _apply_relax_progress). _render_
        level_pv skips `level` entirely for as long as self._computing_
        level is set to it, so nothing else can paint back over the blank
        image (the message label needs no such guard -- nothing else
        writes to it while calibration is running).

        The blank image is rendered ONCE here, not regenerated every dot-
        cycle tick like an earlier version did (baking "Computing..." into
        the image itself, before this dedicated message area existed) --
        a flat background never changes frame to frame, so there's
        nothing to re-render; only the separate message Label's own text
        needs to keep ticking, which is far cheaper than a PIL image
        regenerate + PhotoImage conversion every 500ms."""
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
        """Cancels the dot-cycle, clears the message area, and clears
        self._computing_level -- _render_level_pv is free to draw that
        level normally again after this, but doesn't do so ON ITS OWN;
        the caller (_on_pressure_calibrated) always follows this with
        either a real draw() (the stopped-during-calibration case) or the
        start of a frame replay (whose own first _replay_step tick
        immediately overwrites the message area with "Replay frame ..."
        anyway -- clearing here first is just so the stopped-during-
        calibration case, which has nothing else to overwrite it, doesn't
        leave "Computing..." showing with nothing actually happening)."""
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
        """Recolor the Net figure's chrome to match the (fixed,
        dark-only) plot theme -- ax.cla() (called every draw()) resets
        this to matplotlib's defaults, so it has to be re-applied on
        every redraw. Every "Level N" panel is PyVista, not matplotlib
        (see LEVEL_PANEL_SIZE's own comment) -- its background/text
        color is set once, at panel construction (_build_level_pv_panel/
        _render_level_pv), not re-applied here. Returns the theme dict so
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
        """Rescan data/input/stretchy_nets/ and rebuild the dropdown. No
        more "(not computed)" distinction -- every net now starts from a
        cheap, instant random start (see module docstring), so there's no
        precomputed-vs-not state left to flag. Scans both "*.json" (every
        hand-authored net, and any older net saved before interactive_
        builder_app's own File > Save switched extensions) and "*.poly"
        (that app's own current save extension, 2026-09-16, explicit user
        request -- same plain JSON content underneath, see its own
        NET_FILE_EXTENSION) -- this app's own load_stretchy_mesh/json.load
        calls never cared about the extension at all, only the content,
        so no further change was needed to actually read one."""
        paths = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json"))
                        + glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.poly")))
        self.label_to_path = {}
        for path in paths:
            # A ".json" and a ".poly" sharing the same basename would
            # collide here (same derived label, second one silently wins)
            # -- not handled specially, since the two extensions are
            # meant to replace one another for a given net, not coexist
            # under the same name.
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
            # Default to DEFAULT_NET_BASENAME (cube.poly, or cube.json for
            # an older data/input/stretchy_nets/ that hasn't been renamed
            # -- matched by BASENAME, not one hardcoded extension, so
            # this doesn't silently stop finding "cube" the moment its
            # own file gets saved back out under the other extension) if
            # present, else just the first net alphabetically.
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

        # A LEGACY fabric-subdivided net (one carrying baked-in
        # "coarse_faces", see utils/subdivisions/mesh_subdivide.load_fabric_spec
        # and generate_subdivided_stretchy_nets.py) is loaded at ITS OWN
        # coarse_faces -- i.e. always level 0 -- rather than its pre-baked
        # fine mesh; the new "Subdivide" button refines it interactively
        # from there instead (see module docstring). An ordinary net has
        # no coarse_faces and its own "faces" already are level 0.
        legacy_coarse_faces, _, _ = load_fabric_spec(path)
        self.base_faces = legacy_coarse_faces if legacy_coarse_faces is not None else faces
        # The raw parsed file is kept as self._net_file_json -- read here,
        # up front, rather than further down, since self.colors (below)
        # already needs its own "source_polygon_id" section -- not just
        # its "net_layout" -- so on_save_session_clicked can embed a full
        # copy of it (session_state.SessionStateModel's own "net_file"),
        # letting on_load_session_clicked reproduce this exact layout
        # decision later without the original file needing to still
        # exist on disk.
        with open(path) as f:
            self._net_file_json = json.load(f)
        # base_edges/base_face_edge_ids (see _fan_level_edges/
        # mesh_levels.subdivide_once's own docstrings) and
        # "source_polygon_id" (interactive_builder_app's own Polygon-Fold
        # grouping, see its module docstring) are all keyed to the file's
        # own "faces" vertex-id/index space -- only meaningful when
        # self.base_faces IS that same "faces" (the ordinary, non-legacy
        # case); a legacy fabric net's re-derived coarse_faces use a
        # DIFFERENT vertex-id space entirely, so there's nothing to
        # disambiguate/group against and these stay None (the always-safe
        # plain-vertex-pair/per-face-index fallbacks every consumer
        # already has).
        if legacy_coarse_faces is not None:
            base_edges = base_face_edge_ids = None
            source_polygon_id = None
        else:
            source_polygon_id = self._net_file_json.get("source_polygon_id")
        self.base_edges = base_edges
        self.base_face_edge_ids = base_face_edge_ids
        self.colors, self.color_by_group, self.group_of_base_face = _face_colors_by_group(
            len(self.base_faces), source_polygon_id)

        # Precomputed once per net selection: this panel's flat net
        # layout doesn't change with subdivision level, only its
        # overlay does. A file saved BY interactive_builder_app carries
        # its own "net_layout" section (one entry per ORIGINAL placed
        # shape -- see _layout_from_net_layout's own docstring) -- when
        # present, reproduce THAT exact arrangement rather than a fresh
        # one, so a net a user actually built and connected there shows
        # up here exactly as left, not re-derived from scratch.
        # Otherwise (any hand-authored net, or a legacy fabric net with
        # no such section) fall back to build_stretchy_net_layout's own
        # breadth-first spanning tree over shared edges, attaching each
        # face to whichever neighbor discovers it first (see its own
        # docstring) -- _draw_target_faces just reuses whichever of the
        # two this is on every redraw, rather than recomputing either one
        # every time. A LEGACY net_layout (no per-entry "shape_id", see
        # _net_layout_is_new_format) is still required to match `faces`'
        # own length, exactly as before -- a NEW-format one never will
        # (by design, once a fold exists), so that length check no longer
        # applies to it at all.
        net_layout = self._net_file_json.get("net_layout")
        if net_layout is not None and (
                _net_layout_is_new_format(net_layout) or len(net_layout) == len(self.base_faces)):
            self.target_layout = _layout_from_net_layout(self.base_faces, net_layout)
            # Only meaningful (and only ever present) alongside the exact
            # "net_layout" it was saved with -- see interactive_builder_
            # app's own module docstring's "net JSON import/export"
            # section on why the two are always written/read together;
            # the BFS-fallback branch below has no matching connection
            # geometry to show, so target_connections stays None there.
            self.target_connections = self._net_file_json.get("builder_connections")
        else:
            self.target_layout = build_stretchy_net_layout(self.base_faces)
            self.target_connections = None

        # Level 0 and Level 1 share this exact fan-triangulated topology
        # (see module docstring) -- computed once here, up front, rather
        # than re-derived on promotion.
        self.faces, self.edge_length, self.face_of_fine = _build_level1_topology(self.base_faces)
        # Level 0/1's own explicit spring-edge override (see
        # _fan_level_edges' own docstring) -- None past Level 1 (Level
        # 2/3's own edges are always unambiguous, see mesh_levels.
        # subdivide_once's docstring), reset here on every net load.
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
        # A freshly-loaded net's own levels have no captured Inflate
        # frames yet -- clears every level's replay slider back to
        # disabled/empty rather than leaving the PREVIOUS net's own
        # trajectory scrubbable here.
        self._level_frames = {}
        self._level_scrub_index = {}
        for level in self.level_replay_sliders:
            self._update_replay_slider(level)
        # A fresh net starts over cleanly -- an Auto sequence from the
        # PREVIOUS net (the combo/other controls it would need are
        # disabled during a run anyway, so this can only really happen
        # between runs, but reset defensively regardless).
        self._auto_active = False
        self._auto_attempted_level = None
        # Fresh camera state for BOTH groups on every new net selection
        # (2026-09-18, explicit user request -- "every time i load a new
        # .poly file, the images should show default zoom/rotation/
        # translation") -- previously carried over unchanged from
        # whatever the PREVIOUS net's camera happened to be left at,
        # which made no sense once a totally different-looking shape is
        # now on screen. Doesn't affect File > Load (on_load_session_
        # clicked, "but if i load a .hippo, then use the zoom/rotation/
        # translation specified in that file") -- that method builds its
        # own state directly from the saved SessionStateModel, including
        # its own camera fields, and never calls this one.
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
        """File > Save -- serializes the WHOLE current session (the net,
        every "Target RMS stretch"/Tolerance spinner, the Convergence
        History table, the mesh at every subdivision level reached so
        far, and each panel's own camera view) to one JSON file via
        session_state.SessionStateModel, enough for on_load_session_
        clicked to reopen it exactly as left with no re-solving.
        self.level_snapshots holds every level already left behind (see
        _subdivide_step/_finish_relax); the current frontier level's own
        live self.faces/positions/face_of_fine/edge_length aren't in
        there yet, so this adds them under self.subdivision_level itself
        before writing. self.level_rotation (a scipy Rotation) is stored
        as its own .as_quat() (x, y, z, w) -- JSON has no quaternion type,
        and a plain tuple round-trips through Rotation.from_quat() with
        no loss (see on_load_session_clicked)."""
        if self.positions is None:
            messagebox.showwarning("Save", "No net is loaded yet.")
            return
        SESSION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # ".hippo", not ".json" (2026-09-16, explicit user request) --
        # still plain JSON underneath (model_dump_json below), just a
        # distinct extension so a saved session doesn't look like an
        # ordinary .json file (e.g. one of the hand-authored nets under
        # data/input/stretchy_nets/) in a file picker.
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
        # Falls back to DEFAULT_PRESSURE (this app's own __init__
        # default) when None -- a session saved mid-Computing (the File
        # menu isn't disabled during a run) genuinely has no real
        # pressure yet (see on_inflate_clicked's own comment); loading it
        # back shouldn't leave self.pressure_value itself as None, since
        # nothing downstream expects that (unlike level_history's own
        # rms_stretch_pct, which _refresh_history_table explicitly
        # handles as a "--" sentinel).
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

        # Each panel's own camera view -- a rotation field falls back to
        # _initial_level_rotation() (this app's own non-axis-aligned
        # default), not any baked-in quaternion, when it's None (a
        # session saved before this existed, or one saved with no panel
        # ever having been rotated -- see SessionStateModel's own comment
        # on why the default reproduces the ORIGINAL always-reset-to-
        # default behavior). Levels 1-3's own shared group reads the
        # ORIGINAL "level_*" fields (an older, pre-split session file's
        # one shared camera maps onto this group, see SessionStateModel's
        # own comment); Level 0's own independent group (2026-09-17,
        # explicit user request) reads the newer "level0_*" fields, which
        # simply aren't present in an older file -- falling back to a
        # FRESH default for Level 0 specifically in that case, not
        # whatever the old file's one shared camera happened to be. draw()
        # below re-renders with all of these live, so nothing further is
        # needed to actually apply them.
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
        # Level 0/1 share their fan-triangulated topology (see
        # on_select_net's own comment) -- only THOSE levels can still
        # have an unsplit base rim edge worth disambiguating (see
        # mesh_levels.subdivide_once's own docstring); None (the plain,
        # always-safe derivation) past that, same as _subdivide_step.
        self.edges = (_fan_level_edges(self.faces, self.base_edges)
                      if self.subdivision_level <= 1 else None)

        self.history_tree.delete(*self.history_tree.get_children())
        self.stop_event = None
        # A loaded session carries no captured Inflate frames of its own
        # (never part of SessionStateModel -- see _level_frames' own
        # comment in __init__) -- clears every level's replay slider
        # rather than leaving some OTHER net's own trajectory scrubbable
        # here.
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
        # A loaded session can carry its OWN debug_mode, different from
        # whatever was showing before -- unlike a plain net reselection,
        # this really is a mode change, so it gets the same refit
        # _on_toggle_debug_mode's own explicit toggle does (see _refit_
        # window_height's own docstring on why net selection alone
        # otherwise doesn't refit).
        self._refit_window_height()
        self._set_status(f"Session loaded from {os.path.basename(path)}.", "info")

    # ---- subdivide ----

    def _update_level_action_buttons(self):
        """Single source of truth for every level's one action button
        (see __init__'s Design notes): only the current frontier level's
        button is ever enabled -- idle it reads "Relax" (level 0) or
        "Inflate" (levels 1+), once that level converges it becomes
        "Subdivide" (clickable, advances to the next level) or "DONE!"
        (MAX_LEVEL, nothing further to subdivide to and so left
        disabled). A run in progress overrides this via
        _set_level_action_button_running instead -- this method is never
        called while one is active."""
        converged = bool(self.last_stats.get("converged"))
        for level, button in self.level_action_buttons.items():
            if level != self.subdivision_level or self.positions is None:
                # Not the current frontier -- reset its text too, not just
                # its disabled state: without this, a level that reached
                # "DONE!" (MAX_LEVEL, converged) on a PREVIOUS net keeps
                # showing "DONE!", now stuck and disabled, after selecting
                # a different net resets self.subdivision_level back to 0.
                # "Subdivide" (rather than leaving MAX_LEVEL's own idle
                # label, "Inflate") since that's the label this button
                # will actually show once every level up to it converges.
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
        """The actual level-advancing work behind on_subdivide_clicked --
        no status message or redraw of its own, so the caller reports/
        draws once itself. Only ever runs from Level 1 upward (Level 0's
        own advance to Level 1 is a promotion, not a subdivide_once call
        -- see _finish_relax).

        Freezes the level being LEFT into self.level_snapshots (its own
        "Level N" panel stops updating from here on -- see draw()) using
        whatever state that level had reached, before overwriting
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
        # Level 2+'s own edges are always unambiguous (see
        # mesh_levels.subdivide_once's own docstring) -- self.edges (the
        # Level 0/1-only spring-edge override, see _fan_level_edges) has
        # no reason to exist past this point; mesh_edges' own plain
        # derivation (edges=None) is exactly right from here on.
        self.edges = None
        # This new level's own "Target RMS stretch" spinner (its default,
        # or whatever the user already edited it to, independent of every
        # other level's own spinner) -- just for the history row this
        # method records below, before Inflate has even run once at this
        # level yet.
        if self.subdivision_level in self.target_rms_vars:
            self._current_target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        # The face set just changed entirely (more, smaller faces) --
        # recomputed fresh for the NEW mesh, same as a brand new net load.
        self.last_stats = self._compute_stretch_stats()
        # Each level's own step count starts over at 0 -- a level's
        # "how many steps to converge" is only meaningful counted from
        # when that level's mesh was first created, not carried over from
        # however many steps a coarser level happened to need. Same
        # reasoning for the Precomp/Sim time pair -- see their own comment
        # in __init__.
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
        """Records/updates the CURRENT level's row: the pressure last
        calibrated for it (None for Level 0, which has no pressure at all
        -- relax_initial_configuration is pure springs, see
        stretchy_mesh's docstring -- shown as "--" by
        _refresh_history_table), steps so far this level
        (self.iteration_count, see _subdivide_step/_finish_relax), the
        stretch stats at this point, and the actual stopping-condition
        value -- the relax's own `optimality` (None before any
        Inflate/Relax at this level, or if a Stop request aborted before
        any step ran -- see relax_once's docstring) -- all from
        self.last_stats, plus the "Simulation Time"/"Cumulative Time" columns'
        own backing state, self._current_precomp_time_s/_current_sim_
        time_s (see their own comment in __init__). Called on
        every subdivide/promotion, every live Inflate/Relax progress
        update, and when a run finishes, so the row always reflects the
        level's latest state rather than only its final converged one."""
        self.level_history[self.subdivision_level] = {
            "pressure": None if self.subdivision_level == 0 else self.pressure_value,
            "steps": self.iteration_count,
            "max_stretch_pct": self.last_stats.get("max_stretch_pct", 0.0),
            # No 0.0 fallback here (unlike max_stretch_pct above) -- None
            # is a genuine, DISTINCT state ("not known yet, still
            # computing" -- see on_inflate_clicked's own comment), shown
            # as "--" by _refresh_history_table rather than a misleading
            # "0.00" or a stale leftover number from before this run.
            "rms_stretch_pct": self.last_stats.get("rms_stretch_pct"),
            "optimality": self.last_stats.get("optimality"),
            "converged": self.last_stats.get("converged"),
            # The gtol actually used to reach this optimality/converged
            # reading (self._current_gtol at the time -- see its own
            # comment) -- NOT necessarily the tolerance spinner's CURRENT
            # value, which may have changed since. Falls back to
            # CONVERGENCE_GTOL for a row recorded before this field
            # existed (self.last_stats.get("gtol") is None then).
            "gtol": self.last_stats.get("gtol") or CONVERGENCE_GTOL,
            # Same idea as "gtol" above, for self._current_target_rms_pct
            # -- None for Level 0 (no target stretch there at all, see
            # _refresh_history_table).
            "target_rms_pct": (None if self.subdivision_level == 0
                                else self.last_stats.get("target_rms_pct")
                                or self._current_target_rms_pct),
            # Backing state for "Simulation Time"/"Cumulative Time" -- see
            # their own comment in __init__ for when each is set/reset.
            "precomp_time_s": self._current_precomp_time_s,
            "sim_time_s": self._current_sim_time_s,
            # False only for a level whose pressure calibration gave up
            # WITHOUT finding a usable pressure (see
            # estimate_pressure_for_target_stretch's own docstring on
            # `pressure_found` -- e.g. a mesh whose faces exactly cancel
            # under pressure until a later Subdivide gives it real degrees
            # of freedom). Defaults True for Level 0 (no pressure
            # calibration there at all) and for a row recorded before this
            # field existed, so _guess_pressure_from_history's own filter
            # (below) doesn't spuriously exclude either.
            "pressure_found": self.last_stats.get("pressure_found", True),
        }
        self._refresh_history_table()

    @staticmethod
    def _format_sci(value, precision=2):
        """1.23e-05 -> "1.23e-5" (no leading zero on the exponent) --
        matches the compact form used in the Convergence column.
        `precision=0` gives "1e-4" style (used for the fixed threshold,
        which doesn't need decimal places since it never varies)."""
        mantissa, exponent = f"{value:.{precision}e}".split("e")
        return f"{mantissa}e{int(exponent)}"

    @staticmethod
    def _format_mmss(seconds):
        """None (this phase hasn't run yet at this level -- see the
        Simulation Time backing-state comment in __init__) -> "--"
        (2026-09-16, explicit -- was "n/a"); otherwise mm:ss, floored to
        the second (these columns are wall-clock timings for a human to
        skim, not a stopwatch reading) -- minutes NOT capped at 59, so an
        hour-plus run still reads as one growing number ("75:03") instead
        of wrapping back to "15:03"."""
        if seconds is None:
            return "--"
        total_seconds = int(seconds)
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    def _rescale_history_columns(self, available_width):
        """Turns self._history_column_weights (proportions) into actual
        pixel widths that sum to `available_width` -- the ONLY currently
        DISPLAYED columns share out that width (release mode's 6 vs debug
        mode's 8 have different total weight, so a column's own share
        changes between modes too, not just the widget's overall width).
        Bound to self.history_tree's own <Configure> (fires on every
        resize) via a lambda passing event.width, and called directly
        (with self.history_tree.winfo_width()) from _apply_mode_visibility
        right after a displaycolumns change -- changing which columns are
        shown doesn't itself resize the WIDGET, so no <Configure> would
        otherwise fire for that case. `available_width` <= 1 (the
        widget's own placeholder size before Tk has actually laid it out
        yet) is skipped rather than dividing into that -- the real
        <Configure> once layout finishes will call this again."""
        if available_width <= 1:
            return
        # cget always returns a TUPLE (verified directly: setting
        # displaycolumns="#all" reads back as the tuple ('#all',), not the
        # bare string) -- checked against a tuple, not a string, for
        # exactly that reason.
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
            # A run actively in progress right now for THIS level colors
            # its row yellow ("running"), overriding whatever the plain
            # optimality-vs-gtol comparison below would otherwise say --
            # red ("not_converged") is reserved for an ACTUAL failure
            # (the step cap was reached, or Stop was clicked), not just
            # "hasn't converged yet, still going" (2026-09-16, explicit
            # user request). Gated on `optimality is None` too, not just
            # `self._level_running`, since 2026-09-17 (explicit user
            # request -- "during replay, the text ... is yellow, it
            # should be green because it's already reached convergence"):
            # self._level_running stays True through the WHOLE Inflate
            # click, including the purely-visual replay after a real
            # result is already known (see _on_pressure_calibrated's own
            # comment on when optimality/last_stats actually get set) --
            # "running" should mean "still WAITING on a result", which
            # ends once `optimality` is real, not once the animation
            # finishes.
            running_now = (level == self.subdivision_level and self._level_running
                           and optimality is None)
            if optimality is None:
                # "--" (2026-09-17, explicit user request -- "any cell
                # that doesn't have a value yet should be -- and not
                # n/a"), covering both "never run at this level yet" and
                # "actively computing right now" (optimality is reset to
                # None at the start of every Inflate click, same "--"
                # sentinel treatment as RMS Stretch %/Pressure -- see
                # on_inflate_clicked's own comment).
                convergence, tags = "--", (("running",) if running_now else ())
            else:
                # The checkmark tracks the algorithm's own `converged`
                # flag rather than redoing the optimality-vs-gtol
                # comparison here -- historically these could disagree
                # (a now-removed stall-window shortcut could converge
                # with optimality still numerically above gtol, shown as
                # "(stalled)"); with that shortcut gone, `converged` is
                # True only when optimality < gtol, so this always
                # agrees with the displayed comparison -- kept as the
                # single source of truth anyway rather than assuming
                # that'll always hold.
                # `running_now` is always False here -- it requires
                # `optimality is None` (see its own definition above),
                # and this branch only runs when optimality is NOT None
                # -- so this cell only ever shows two colors: green
                # ("converged"), always with a checkmark, or red
                # ("not_converged"), always with an X (2026-09-17,
                # explicit user request -- "red is only used when
                # convergence is not reached at the end... green is used
                # when convergence is reached at the end... it's never
                # any other colour" -- "--"/yellow, this cell's only other
                # possible state, is handled entirely by the `if` branch
                # above instead).
                gtol = rec["gtol"]
                converged = rec["converged"]
                op = "<" if optimality < gtol else ">"
                mark = "✔" if converged else "✘"  # colored via row tag, not the glyph itself
                convergence = (f"{self._format_sci(optimality)} {op} "
                                f"{self._format_sci(gtol, precision=0)} {mark}")
                tags = ("converged",) if converged else ("not_converged",)
            # "--" for Level 0 (2026-09-16, explicit -- was "n/a"), the
            # only level whose "pressure" is ever None (see
            # _record_level_history) since relax_initial_configuration is
            # pure springs, no pressure to calibrate at all.
            pressure_str = "--" if rec["pressure"] is None else f"{rec['pressure']:.2f}"
            # Level 0 has no target stretch to chase (relax_initial_configuration
            # is pure springs, not calibrated against the spinner at all).
            # This row's OWN target_rms_pct (recorded at the time IT was
            # calibrated, not read live from the spinner -- see this
            # field's own comment in __init__), so a level's row keeps
            # showing what it was actually chasing even after the
            # spinner later shows a different level's own default.
            # "--" (2026-09-17, explicit user request) while this run's
            # own RMS isn't known yet -- "don't calculate/show RMS
            # stretch % until convergence or step 5000 [i.e. the trial's
            # own real stopping point]; only update the value at the end
            # of the simulation" -- see on_inflate_clicked's own comment
            # for where rms_stretch_pct gets reset to None at the start
            # of a run and _on_pressure_calibrated for where it's filled
            # in with the real number, the instant it's actually known
            # (before replay even starts, same as "Convergence" above).
            # Level 0 ALWAYS shows "--" here too, regardless of its own
            # last_stats value (2026-09-17, further explicit user request
            # -- "for level 0, no need to compute rms stretch %, just
            # keep it as --") -- relax_initial_configuration's own RMS
            # reading is still computed and stored (last_stats/level_
            # history), just never actually surfaced for this level's row;
            # not worth threading a "don't compute it at all" flag all the
            # way down into _apply_relax_progress for one already-cheap
            # vectorized stat that's part of the same _positions_and_
            # stretch call max_stretch_pct (still shown for Level 0)
            # already needs.
            rms_str = ("--" if level == 0 or rec["rms_stretch_pct"] is None
                       else f"{rec['rms_stretch_pct']:.1f}")
            # "(target: ...)" is debug-mode-only now (2026-09-17, explicit
            # user request -- release mode shouldn't show it at all).
            if self.debug_mode and level != 0 and rec.get("target_rms_pct") is not None:
                rms_str += f" (target: {rec['target_rms_pct']:.1f})"
            # "Simulation Time" (renamed from "Elapsed Time" 2026-09-17,
            # explicit user request): Precomp + Sim -- except Level 0,
            # which has no precomputation at all (relax_initial_
            # configuration is pure springs, no pressure to calibrate, see
            # on_relax_clicked), so its row shows just the one (Sim)
            # value, and Level 1+, which no longer has a separate Sim
            # phase at all (2026-09-17 -- pressure calibration's own
            # winning trial IS the Inflate result now, see
            # on_inflate_clicked/_finish_frame_replay), so its row shows
            # just Precomp. A row could still show BOTH if loaded from a
            # session saved before this change; that case (and the
            # half-run "only one of the two available yet" case) still
            # shows just whichever mm:ss values are actually present, same
            # as before (2026-09-16 -- was always "precomp + sim", showing
            # e.g. "12:34 + --" for the half-run case); with NEITHER yet,
            # "--" alone, same as _format_mmss's own single-value
            # placeholder.
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
            # "Cumulative Time": running total of every row's own
            # Simulation Time SECONDS so far (both phases, level 0's
            # single one included) -- a level that hasn't run at all yet
            # contributes 0, not "n/a", since the running total up to and
            # including an untouched row is still a real, known number
            # (whatever the rows before it added up to).
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
        """max/rms edge stretch of the CURRENT self.faces/self.positions
        against self.edge_length -- the same two stats relax_once/
        relax_initial_configuration report, computed directly rather than
        via a relax, for a mesh that hasn't been relaxed at all yet (a
        fresh random start, or the freshly-interpolated positions right
        after a Subdivide click)."""
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
        """Restricts `entry` to numeric-looking input as it's typed
        (2026-09-16, explicit user request: a plain text Entry standing
        in for what used to be a Spinbox, see each caller's own comment)
        -- Tk's own `validate="key"` fires this BEFORE a keystroke is
        accepted, on every insert/delete, with `%P` the field's value AS
        IT WOULD READ if this keystroke goes through; returning False
        rejects it outright (the character never appears) rather than
        accepting then un-doing it, so this never fights the user's own
        cursor position the way a post-hoc correction would.
        `allow_exponent` permits an "e"/"E" exponent, for tolerance's own
        scientific-notation text (e.g. "1e-03") -- a plain percentage
        never needs one. `allow_decimal` permits a "." -- target RMS
        entries pass False (2026-09-16, explicit -- whole numbers only,
        no decimal place)."""
        vcmd = self.root.register(lambda proposed: self._is_valid_numeric_partial(
            proposed, allow_exponent, allow_decimal))
        entry.configure(validate="key", validatecommand=(vcmd, "%P"))

    @staticmethod
    def _is_valid_numeric_partial(proposed, allow_exponent, allow_decimal=True):
        """True if `proposed` is a full number OR a prefix a user could
        still be in the middle of typing toward one (e.g. "", "-", ".",
        "1.", "1e", "1e-" when `allow_exponent`) -- accepting these
        in-progress states, not just a complete `float()`-parseable
        string, is what lets a user type a negative number or a decimal
        point at all without the very first keystroke being rejected."""
        digits = r"\d*\.?\d*" if allow_decimal else r"\d*"
        pattern = f"-?{digits}(?:[eE][-+]?\\d*)?" if allow_exponent else f"-?{digits}"
        return re.fullmatch(pattern, proposed) is not None

    def _begin_edit_target_rms(self, level):
        """<FocusIn> on a target-RMS entry: swaps its displayed "N%" for
        the bare number alone (2026-09-16, explicit user request -- the
        "%" is something the field shows once a number's been entered,
        not something typed, so editing should start from a plain digit
        string with nothing to work around)."""
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}")

    def _sync_target_rms_display(self, level):
        """Reformats a target-RMS entry's displayed text as "N%" from its
        OWN underlying var -- fires on every write to that var, from
        ANYWHERE (a commit here, `on_load_session_clicked`, ...), so the
        "%" suffix (2026-09-16, explicit user request) is never left
        stale after a change that didn't go through this entry at all."""
        self.target_rms_display_vars[level].set(f"{self.target_rms_vars[level].get():.0f}%")

    def _commit_target_rms_entry(self, level, _event=None):
        """<Return>/<FocusOut> on a target-RMS entry: clamps whatever got
        typed into [0, 100], rounded to the nearest whole number
        (2026-09-16, explicit user request -- values outside that range
        are truncated to the nearest extreme, not rejected; no decimal
        place), or falls back to this level's own default if the field
        doesn't parse as a number at all right now (e.g. left on "-" or
        empty) -- the same silent-fallback spirit _get_tolerance already
        gives tolerance's unparseable states. Setting `self.target_rms_
        vars[level]` (not the entry's own display var directly) is what
        triggers _sync_target_rms_display to put the "%" back."""
        try:
            value = round(float(self.target_rms_display_vars[level].get()))
        except (tk.TclError, ValueError):
            value = LEVEL_DEFAULT_TARGET_RMS_PCT[level]
        self.target_rms_vars[level].set(max(0, min(100, value)))

    def _on_target_rms_changed(self, level):
        # Only the CURRENT frontier level's own spinner invalidates a
        # "converged" verdict -- editing some other level's target (one
        # already finished, or not yet reached) doesn't affect the
        # pressure just calibrated for this one.
        if level == self.subdivision_level and self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_level_action_buttons()

    def _on_tolerance_changed(self, *_args):
        # Same rationale as _on_target_rms_changed: a "converged" verdict
        # only applies to the tolerance it was reached under -- changing
        # it means the CURRENT mesh hasn't actually been checked against
        # the new threshold yet.
        if self.last_stats.get("converged"):
            self.last_stats["converged"] = None
            self._update_level_action_buttons()

    def _get_tolerance(self):
        """Parses self.tolerance_var's text (e.g. "1e-03") as a float --
        a StringVar, not a DoubleVar, specifically so it can always
        DISPLAY in scientific notation (see its own comment in __init__)
        -- falling back to DEFAULT_TOLERANCE for anything unparseable
        (e.g. a momentarily-empty field mid-edit), the same silent-
        fallback spirit a plain Spinbox gives an invalid entry."""
        try:
            return float(self.tolerance_var.get())
        except ValueError:
            return DEFAULT_TOLERANCE

    def _guess_pressure_from_history(self, target_rms_pct):
        """Estimates the pressure to hand estimate_pressure_for_target_
        stretch as its OWN starting guess (`initial_pressure_guess`),
        drawing on already-calibrated PRIOR levels' own history
        (self.level_history) instead of always falling back to that
        function's generic per-solid-derived constant. Looks at EVERY
        prior level's own (pressure, achieved rms_stretch_pct) pair and
        picks whichever one's OWN achieved stretch landed CLOSEST to the
        NEW target (not necessarily the nearest level) -- scaling just
        THAT record's own pressure by 2 per level of resolution
        difference (each Subdivide level roughly doubles resolution --
        quarters every triangle, ~halves edge length -- and empirically
        needs roughly 2x the pressure for the same target RMS stretch %).

        Deliberately NOT a `target_rms_pct / achieved` rescale any more
        (2026-09-19, explicit user request): that ratio explodes when a
        level's own achieved stretch happens to be ~0 (pressure genuinely
        had no effect there -- e.g. a mesh whose faces cancel out under
        pressure until a later Subdivide gives it real degrees of
        freedom -- see mesh_levels.subdivide_once's own docstring on
        rim-edge disambiguation for how such a mesh can even be built at
        all), producing an absurd guess for the NEXT level that overflows
        the solver before it ever gets a chance to find the shape that's
        now actually reachable. Picking the closest-achieved record
        instead never divides by anything -- a near-zero achieved value
        just makes that particular record a poor (but bounded) candidate,
        not a search-breaking one.

        A level whose own record has `pressure_found` False (see
        estimate_pressure_for_target_stretch's own docstring) is skipped
        entirely, not just deprioritized -- its own "pressure" never came
        from a real calibration in the first place (the search gave up
        because the mesh was completely unresponsive to pressure at that
        level), so it's not a usable data point for extrapolation at all,
        regardless of how close its achieved stretch happens to read.

        Returns None (falling back to the generic guess) if no level
        below the current frontier has a usable recorded pressure/stretch
        pair yet -- e.g. still at Level 1, with nothing calibrated
        before it."""
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
        """Calibrates a pressure for the current "Target RMS stretch"
        (stretchy_mesh.estimate_pressure_for_target_stretch, via
        _run_background -- see _on_pressure_calibrated) and, once found,
        that's the WHOLE run -- there's no separate second relax_once call
        at the winning pressure any more (2026-09-17, explicit user
        request). There used to be one (_run_inflate_stream), but it was
        pure duplicated work: every calibration trial already starts from
        the same `positions`, and the final trial runs at the SAME
        pressure/gtol/rng a follow-up call would use, so it retraced an
        already-computed trajectory step for step just to have something
        to show frame-by-frame. Now estimate_pressure_for_target_stretch
        itself captures the winning trial's own frames
        (capture_frames=True) and _on_pressure_calibrated replays THOSE
        (_start_frame_replay) once calibration lands on a pressure --
        same visual result, zero recomputation.

        While calibration itself is searching, this level's own panel
        shows an animated "Computing..." placeholder instead of a live
        redraw (_start_computing_animation) -- most of calibration's own
        several trials are thrown away, so there's no single meaningful
        shape to show frame-by-frame until it actually finishes. Level 0's
        Relax has no such phase (see _apply_relax_progress) and keeps
        redrawing live throughout, unchanged.

        Recalibrates fresh from wherever self.positions currently is on
        every click, since the user can no longer set pressure directly.
        Calibrates against the CURRENT "Tolerance" spinner value too. The
        search's own STARTING pressure comes from
        _guess_pressure_from_history when a usable prior level exists
        (falling back to estimate_pressure_for_target_stretch's own
        generic guess otherwise) -- a better starting point than a
        Level-1-vs-Level-3 target guess treated identically, per explicit
        user request.

        self.stop_event is created and the frontier button turned into
        "Stop" HERE, before calibration even starts (not in
        _on_pressure_calibrated, as an earlier version did) -- a user
        reported Stop/"Stop Auto" appearing to "take forever": traced
        directly to calibration never being given a stop_event at all, so
        clicking Stop during it (which, for a slow mesh, can be most of
        the wait -- calibration runs up to max_iterations *
        max_nfev_per_trial steps of its own) had truly nothing to
        interrupt."""
        if self.positions is None or self.last_stats.get("converged"):
            return
        faces, edge_length, positions = self.faces, self.edge_length, self.positions
        target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        # Captured here too, not just at the level-default sites (see its
        # own comment in __init__), in case the user edited the spinner
        # away from that default before clicking Inflate.
        self._current_target_rms_pct = target_rms_pct
        tolerance = self._get_tolerance()
        initial_pressure_guess = self._guess_pressure_from_history(target_rms_pct)
        self.stop_event = threading.Event()
        # Marks the start of the "Precomp time" column's own phase -- see
        # its own comment in __init__. Consumed (turned into
        # self._current_precomp_time_s) in _on_pressure_calibrated. Level
        # 1+ no longer has a separate "Sim time" phase after this (see
        # this method's own docstring) -- ALL of a Level 1+ row's own
        # Simulation Time is "Precomp" now.
        self._precomp_start_time = time.perf_counter()
        # Read by _on_calibration_progress, which fires from a
        # _run_background poll tick, not a call this method's own local
        # scope survives until -- has to live on self.
        self._precomp_base_iteration_count = self.iteration_count
        # Snapshot to restore if this run gets Stopped (see
        # _on_pressure_calibrated's own stop_event branch) -- and, right
        # after taking it, blank "RMS Stretch %", "Pressure", AND
        # "Convergence" to "--" for the duration of this run (2026-09-17,
        # explicit user request, three separate asks: "don't calculate
        # RMS stretch % until convergence or step 5000... show RMS
        # stretch % as -- [while computing], only update the value at the
        # end"; "the pressure should also be -- until things converge";
        # "when convergence is not reached yet, convergence should be
        # --"). Without this, the row would keep showing whatever stale
        # RMS/pressure/convergence data was left over from BEFORE this
        # click (the previous run's own result) -- not live numbers, just
        # old data sitting there looking as if it might be current.
        # `optimality=None` is what actually blanks "Convergence" --
        # _refresh_history_table's own display logic already treated
        # `None` there as "no result yet" (originally just for "never run
        # at this level"), so resetting it here reuses that same path;
        # `converged`/`gtol` don't need resetting alongside it, since the
        # display logic never reads them while optimality is None.
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
        """Live "Steps" column update while pressure calibration itself
        is computing (2026-09-17, explicit user request -- "increment
        Steps during simulation rather than replay") -- `cumulative_steps`
        is estimate_pressure_for_target_stretch's own running total across
        every trial attempted so far (see its own on_progress docstring
        for why it's not reset per trial: a live counter visibly dropping
        BACKWARDS every time a new trial starts would read as broken, not
        as progress). NOT necessarily the same number the row ends up
        showing once calibration actually finishes -- _on_pressure_
        calibrated snaps self.iteration_count to the TRUE final
        steps_taken (the winning trial's own count) the instant the real
        result comes back, before replay ever starts, exactly as that
        docstring recommends -- so any mismatch is a single, one-time
        correction at the Computing-to-Replay transition, not something
        visible mid-count."""
        self.iteration_count = self._precomp_base_iteration_count + cumulative_steps
        self._record_level_history()

    def _on_pressure_calibrated(self, result, base_iteration_count):
        if self.stop_event is not None and self.stop_event.is_set():
            # Stopped during calibration itself -- its own trial positions
            # are discarded regardless of how it ends (see
            # estimate_pressure_for_target_stretch's own docstring), so
            # there's nothing from `result` to apply; just report it the
            # same way a stopped run would (_finish_inflate). Restores
            # this level's own normal panel (it was showing "Computing..."
            # -- self.positions/faces are unchanged from before this
            # click, so there's nothing new to show, just the old image
            # back).
            self._stop_computing_animation()
            self._set_level_action_button_running(False)
            self._set_status(
                f"Stopped (during pressure calibration at level "
                f"{self.subdivision_level}).", "warn")
            # No real result to show -- restore "RMS Stretch %"/"Pressure"
            # (blanked to "--" at the start of this click, see
            # on_inflate_clicked's own comment) back to whatever they
            # genuinely were before this run started, rather than leaving
            # them stuck at "--" forever.
            self.last_stats = self._pre_computing_last_stats
            self.pressure_value = self._pre_computing_pressure_value
            self._record_level_history()
            self.draw()
            self._auto_step()  # no-op unless Auto is what actually drove this run
            return
        (pressure, new_positions, steps_taken, max_stretch, rms_stretch,
         optimality, converged, frames, pressure_found) = result
        self.pressure_value = pressure
        # "Precomp time" (see __init__): calibration has no progress
        # callback of its own to update this live, so it's set ONCE here,
        # the moment it actually finishes.
        self._current_precomp_time_s = time.perf_counter() - self._precomp_start_time
        # Captured once here, not re-read live during the run -- the
        # spinner is disabled for the duration anyway (_set_controls_
        # enabled) -- and reused by _finish_frame_replay so the recorded
        # outcome shows the SAME threshold it actually converged against,
        # even if the spinner's value changes later.
        self._current_gtol = self._get_tolerance()
        self._stop_computing_animation()
        # _run_background's own completion just re-synced every control,
        # including the frontier button, back to its normal (non-Stop)
        # state (_set_controls_enabled(True), called right before this
        # callback runs) -- re-disable them and turn the frontier button
        # back into "Stop" for the replay that's about to start (Stop
        # during replay just skips to the final frame, see _replay_step).
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self._set_status(f"Replaying the winning trial at pressure {pressure:.2f}...", "info")
        # Snaps "Steps" AND the Convergence History row's own stretch/
        # Convergence columns to their TRUE final values the instant the
        # real result is actually known -- explicit user request,
        # 2026-09-17: "once the simulation converges, the convergence
        # column should be updated. it doesn't need to wait for the
        # replay to finish." self.last_stats normally only updates once a
        # run FULLY finishes (_finish_frame_replay), but replay itself can
        # take a while (many frames at REPLAY_FPS) -- there's no reason
        # the Convergence/RMS/Max Stretch columns should sit on STALE
        # (pre-click) numbers for that whole stretch when the real answer
        # is sitting right here. self.positions is deliberately NOT
        # updated yet, though (that stays whatever _replay_step shows,
        # frame by frame, until the animation actually reaches the end)
        # -- only the STATS/history-row columns jump ahead, not the 3D
        # panel itself.
        self.iteration_count = base_iteration_count + steps_taken
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged,
                            "gtol": self._current_gtol,
                            "target_rms_pct": self._current_target_rms_pct,
                            "pressure_found": pressure_found}
        self._record_level_history()
        final_result = (new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged)
        # Made available for manual scrubbing (see this level's own
        # replay slider, built in __init__) right away, defaulted to the
        # true final frame -- not gated on the auto-played animation
        # below actually finishing, so the slider is already usable the
        # instant a result exists, even while that animation is still
        # playing.
        self._level_frames[self.subdivision_level] = frames
        self._level_scrub_index[self.subdivision_level] = len(frames) - 1
        self._update_replay_slider(self.subdivision_level)
        self._start_frame_replay(frames, final_result, base_iteration_count)

    # Target frames per second during a replay (see _start_frame_replay)
    # -- purely a display rate for an already-finished trial's own
    # positions, fast enough to read as "watching it happen" without
    # dragging out a recap of what's already done. A CEILING, not a
    # guarantee: each tick still pays the real cost of rendering one
    # "Level N" panel (_draw_level_panel), which can exceed
    # REPLAY_FRAME_INTERVAL_MS on a dense mesh -- _replay_step schedules
    # the NEXT tick only after the current one's own render finishes, so
    # a slow render just means fewer actual fps that tick, never a
    # backlog of queued redraws.
    REPLAY_FPS = 30
    REPLAY_FRAME_INTERVAL_MS = round(1000 / REPLAY_FPS)
    # Advances this many CAPTURED frames (each already CONVERGENCE_CHECK_
    # INTERVAL=200 physics steps apart, see estimate_pressure_for_target_
    # stretch's own capture_frames) per tick, not 1 -- e.g. step 800,
    # 1600, ... instead of 200, 400, ... (2026-09-17, explicit user
    # request). Effectively plays the SAME captured sequence back ~4x
    # faster in wall-clock time than one-frame-per-tick would at the same
    # REPLAY_FPS, while still ticking (and rendering) at a smooth 30fps --
    # skipping frames outright rather than just raising REPLAY_FPS
    # further, which would only make each individual render (the real
    # bottleneck, not the tick rate) more likely to fall behind its own
    # interval (see this constant's own comment above).
    REPLAY_FRAME_STRIDE = 4

    def _start_frame_replay(self, frames, final_result, base_iteration_count):
        """Plays back estimate_pressure_for_target_stretch's own captured
        `frames` (the winning trial's own `(positions, steps_taken)` pairs
        every CONVERGENCE_CHECK_INTERVAL steps, from its own starting
        point through however far it got, INCLUDING its own convergence
        top-up -- see that function's own docstring) at REPLAY_FPS -- a
        purely visual recap of a run that's already finished; no physics
        runs here, and neither a TIMER nor `iteration_count` moves during
        it (explicit user request, 2026-09-17 -- "Steps" increments during
        the actual simulation now, via _on_calibration_progress, snapped
        to its true final value by _on_pressure_calibrated BEFORE this is
        even called -- replay only re-displays a shape that already
        finished changing, so neither wall-clock time nor the step count
        should move again during it). The bottom-of-panel message
        (_set_level_message) instead shows "Replaying" + a 0-3-dot cycle
        (2026-09-17 explicit user request -- was "Replaying - N%" before
        that, "Replay frame N / M" before that) through _replay_step,
        clearing once done (_finish_frame_replay).
        `final_result` (new_positions, steps_taken, max_stretch_pct,
        rms_stretch_pct, optimality, converged) is only actually applied
        once the replay reaches its own last frame (_finish_frame_replay)
        -- every frame in between is display-only, self.positions
        temporarily set to it just so draw() shows it."""
        self._replay_frames = frames
        self._replay_index = 0
        self._replay_final_result = final_result
        self._replay_base_iteration_count = base_iteration_count
        self._replay_step()

    def _replay_step(self):
        # A Stop click during replay jumps straight to the final frame --
        # there's no live physics left to interrupt, just an animation, so
        # skipping ahead to the real outcome is more useful than replaying
        # the rest of a recap the user already asked to cut short.
        skip_ahead = self.stop_event is not None and self.stop_event.is_set()
        total = len(self._replay_frames)
        if self._replay_index < total and not skip_ahead:
            positions, _steps_taken = self._replay_frames[self._replay_index]
            self.positions = positions
            # Dot count derived from wall-clock time, not from a replay-
            # tick counter -- REPLAY_FRAME_INTERVAL_MS (~33ms at
            # REPLAY_FPS=30) is far faster than a readable dot-cycle, so
            # ticking the dots once per replay frame would flicker
            # unreadably; deriving from time.perf_counter() instead gives
            # the SAME ~500ms-per-dot pace _tick_computing_animation uses
            # (COMPUTING_DOT_INTERVAL_MS), with no separate timer/state of
            # its own needed.
            dots = int(time.perf_counter() / (self.COMPUTING_DOT_INTERVAL_MS / 1000)) % 4
            self._set_level_message(self.subdivision_level, "Replaying" + "." * dots)
            # Only THIS level's own panel actually changes frame to frame
            # -- a full draw() (Net panel plus every "Level N" panel) was
            # tried first and measured taking ~0.5s on its own for a
            # mid-size net, five-plus times slower than REPLAY_FRAME_
            # INTERVAL_MS, since it re-renders three unrelated, unchanged
            # panels on every single tick. _draw_level_panel alone keeps
            # replay actually running near REPLAY_FPS.
            self._draw_level_panel(self.subdivision_level, self.faces,
                                    self.positions, self.face_of_fine)
            # Advances by REPLAY_FRAME_STRIDE captured frames, not 1 (see
            # its own comment) -- clamped so the LAST captured frame (the
            # true final state) always gets its own tick even when the
            # stride would otherwise jump past it, rather than silently
            # skipping straight from some earlier frame to "done".
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
        # A Stop click can only ever reach here meaning "skip the replay
        # ANIMATION" (see _replay_step's own skip_ahead) -- a Stop that
        # actually interrupted the real computation is caught earlier, in
        # _on_pressure_calibrated's own stop_event branch, which returns
        # before a replay ever starts. By the time this runs, the
        # winning trial's own result is already final and complete
        # regardless of whether the animation played in full -- clearing
        # stop_event here keeps _finish_inflate's own "Stopped"/"Converged"
        # status message honest about which one actually happened.
        self.stop_event = None
        new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged = (
            self._replay_final_result)
        self.positions = new_positions
        # iteration_count/last_stats are already set to these exact
        # values by _on_pressure_calibrated, before replay even started
        # (see _start_frame_replay's own docstring) -- reassigned here
        # anyway for robustness/symmetry with the rest of this method's
        # own final-state bookkeeping, not because replay itself changed
        # them.
        self.iteration_count = self._replay_base_iteration_count + steps_taken
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged,
                            "gtol": self._current_gtol,
                            "target_rms_pct": self._current_target_rms_pct,
                            # Already set by _on_pressure_calibrated, before
                            # replay even started (see this dict's own
                            # comment above) -- carried over rather than
                            # dropped by this redundant reassignment.
                            "pressure_found": self.last_stats.get("pressure_found", True)}
        self._record_level_history()
        # "once replay is done, message disappears" -- explicit user
        # request.
        self._set_level_message(self.subdivision_level, "")
        self.draw()
        self._finish_inflate()

    def _update_replay_slider(self, level):
        """Configures level `level`'s own replay scrubber (built in
        __init__) to match self._level_frames[level] -- the slider's own
        range spans every captured frame index, enabled iff at least 2
        frames exist (a single frame has nothing to scrub between). Also
        re-syncs the slider's own displayed position to self._level_
        scrub_index[level] (set by whoever populated the frames -- see
        _on_pressure_calibrated) -- `ttk.Scale.set` DOES fire `command`
        (verified directly), so this harmlessly re-triggers
        _on_replay_slider_moved with the SAME index it was already at --
        idempotent (redraws the same already-current frame), not a real
        scrub action."""
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
        """`command` callback for level `level`'s own replay scrubber --
        `value` is ttk.Scale's own string-formatted float; rounded to the
        nearest captured frame index (clamped, since a Scale can report a
        value fractionally past its own `to` during a fast drag). Purely
        a DISPLAY override: updates self._level_scrub_index[level] (read
        by draw(), see its own comment) and redraws just this one panel
        directly, without touching self.positions/self.level_snapshots
        at all -- scrubbing an OLDER level, or scrubbing away from the
        frontier level's own true final frame, never affects what the
        next real Inflate/Subdivide click actually continues from."""
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
        """Neither mode has a separate Stop button -- instead, the
        CURRENT frontier level's own action button turns into the Stop
        control for the duration of a run, then back to its normal
        Inflate/Relax/Subdivide/DONE! state once it finishes (delegated
        to _update_level_action_buttons, the single source of truth for
        that -- see _finish_inflate/_finish_relax). Safe to assume the
        frontier level doesn't change mid-run: every other level's button
        is disabled for the whole run too (see _set_controls_enabled),
        and Relax's own promotion only happens in _finish_relax, after
        the run is over."""
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
        # A per-level Stop clicked directly (not via "Stop Auto" itself)
        # while an Auto sequence is running must ALSO halt the sequence
        # -- otherwise _auto_step (called from _finish_relax/_finish_
        # inflate once the stopped run actually winds down) would just
        # start the NEXT step right back up, ignoring the stop.
        self._abort_auto()

    # ---- "Auto": Relax -> Inflate -> Subdivide -> ... -> Level MAX_LEVEL ----

    def on_auto_clicked(self):
        """Runs the whole pipeline unattended: Relax at Level 0, then
        Inflate/Subdivide/Inflate/.../Level MAX_LEVEL, exactly the
        sequence a user would otherwise click through by hand -- see
        _auto_step, which drives one step at a time and is what actually
        decides what "next" means at any given moment. Disabled (so this
        can't even be reached) whenever a net isn't loaded or ANY run is
        already in progress -- see _update_auto_button/
        _set_controls_enabled."""
        if self.positions is None or self._auto_active:
            return
        self._auto_active = True
        self._auto_attempted_level = None
        self._update_auto_button()
        self._auto_step()

    def on_auto_stop_clicked(self):
        """The Auto button's own command while a sequence is running (see
        _update_auto_button) -- ends the sequence AND interrupts whatever
        Relax/Inflate step is currently mid-run, via the same stop_event
        on_stop_clicked already uses (a per-level Stop click reaches the
        exact same place from the other direction -- see its own
        docstring)."""
        self._abort_auto()
        self.on_stop_clicked()

    def _abort_auto(self):
        """Ends an in-progress Auto sequence without itself touching
        whatever Relax/Inflate run might currently be underway (see
        on_stop_clicked/on_auto_stop_clicked for that) -- also called
        from every worker-thread failure path (_run_background/
        _run_chunked_relax_stream's own "error" branches) that would
        otherwise leave self._auto_active stuck True with nothing left
        actually driving it forward, which would leave the button
        showing "Stop Auto" for a sequence that's already silently dead.
        A no-op if Auto isn't running."""
        if self._auto_active:
            self._auto_active = False
            self._update_auto_button()

    def _update_auto_button(self):
        """Single source of truth for the Auto button, mirroring
        _update_level_action_buttons' own state machine for the per-level
        buttons: idle (self._auto_active is False) it reads "Run
        Simulation", enabled only once a net is loaded -- otherwise disabled like
        every other control while ANY run is in progress (see
        _set_controls_enabled, which calls this itself after toggling
        everything else, and which this does NOT need to independently
        duplicate for the "disabled during a run" case). While Auto
        itself is driving a run (self._auto_active is True), it instead
        reads "Stop Simulation" and is explicitly RE-ENABLED regardless of
        what _set_controls_enabled(False) just did -- the same "frontier
        button survives the blanket disable" pattern
        _set_level_action_button_running uses for the per-level buttons
        -- so the one control that can interrupt a multi-step Auto
        sequence stays clickable throughout every step of it."""
        if self._auto_active:
            self.auto_button.config(text="Stop Simulation", command=self.on_auto_stop_clicked)
            self.auto_button.state(["!disabled"])
        else:
            self.auto_button.config(text="Run Simulation", command=self.on_auto_clicked)
            self.auto_button.state(["!disabled"] if self.positions is not None else ["disabled"])

    def _auto_step(self):
        """Decides what Auto should do next, called once from
        on_auto_clicked to kick the sequence off and again from the tail
        of _finish_relax/_finish_inflate every time a step it started
        actually finishes -- a no-op whenever Auto isn't active, so a
        plain manual button click never triggers any of this.

        - Level 0, not yet converged: Relax -- exactly ONE attempt per
          level, no retries (per explicit user request: a non-converged
          attempt just runs its own single relax_once/
          relax_initial_configuration call up to its own large step
          budget -- see INFLATE_SAFETY_STEP_CAP -- rather than Auto
          stopping that run short and starting a fresh one, which for
          Inflate used to mean recalibinating pressure from scratch for
          no real benefit). If _auto_attempted_level already names this
          level, the attempt just finished IS the one attempt -- declare
          failure and stop Auto rather than trying again.
        - Level 0, converged: _finish_relax has ALREADY promoted to
          Level 1 unconditionally by the time this runs (that promotion
          isn't Auto-specific), so there's nothing left to do here --
          the NEXT call to this function will see Level 1 instead.
        - Current level converged, below MAX_LEVEL: Subdivide, then
          immediately re-enter this function (now one level higher, not
          yet converged there) rather than waiting for a callback that
          Subdivide itself never schedules (it's synchronous, unlike
          Relax/Inflate).
        - Current level converged, AT MAX_LEVEL: done -- nothing further
          to subdivide to.
        - Current level NOT converged (below or at MAX_LEVEL): same
          one-attempt-then-stop rule as Level 0, via Inflate."""
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
        """Driver behind _run_relax_stream (Level 0's own Relax, its only
        remaining caller -- Inflate's own equivalent, _run_inflate_stream,
        was removed 2026-09-17: pressure calibration's own winning trial
        IS the Inflate result now, replayed from its cached frames rather
        than recomputed, see on_inflate_clicked). Calls
        `relax_fn(max_nfev, stop_event, queue_progress) -> result`
        (result's own shape: (positions, nfev, max_stretch_pct,
        rms_stretch_pct, optimality, converged), same for relax_once and
        relax_initial_configuration) ONCE, in a background thread --
        `max_nfev` is `target_steps` for "iterate for N steps" mode, or
        INFLATE_SAFETY_STEP_CAP otherwise (a single call already runs to
        real convergence or that cap on its own; there's no outer loop
        left to enforce it).

        No artificial chunking here any more -- an earlier version called
        `relax_once`/`relax_initial_configuration` repeatedly in a growing
        sequence of small chunks (5, 10, 20, ..., capped at 200) purely so
        the UI had SOME point to redraw at, with no relationship to the
        solver's own actual convergence-check cadence (a user traced this
        directly: an app-reported "515 steps" convergence was an artifact
        of that chunk schedule, not the mesh's real behavior -- see git
        history). `relax_once`/`relax_initial_configuration` now accept
        `on_progress` directly and call it themselves every
        CONVERGENCE_CHECK_INTERVAL steps -- exactly the same cadence the
        stopping condition is itself checked at (see
        stretchy_mesh._explicit_relax_loop's own `on_check`) -- so the UI
        now redraws in sync with real convergence checks instead of an
        unrelated schedule. `queue_progress` bridges that callback (called
        from the background thread) to this same queue/poll mechanism;
        Tk isn't thread-safe, so the worker only ever pushes to the queue,
        and the main thread (via the scheduled poll below) is the only
        one that touches Tk widgets."""
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
            # Drains the WHOLE queue every cycle, but coalesces "progress"
            # messages down to the LATEST one instead of calling
            # on_progress (hence _apply_relax_progress's own panel
            # redraw) once per queued message (2026-09-17, explicit user
            # report -- "Simulation Time" was visibly stalling then
            # jumping). If physics runs faster than a single redraw
            # (~0.2-0.3s measured for a mid-size net, still slower than
            # this poll's own 80ms interval), the worker thread can queue
            # several progress messages before poll() next runs -- older
            # ones are immediately superseded and would just be wasted
            # render time, so only the newest is ever actually drawn. This
            # is what actually fixes the stall-then-jump: rendering every
            # queued message, oldest first, meant a backlog only ever grew
            # (each render taking longer than the interval it was trying
            # to keep up with), so the display fell further and further
            # behind before catching up all at once; skipping straight to
            # whatever's newest each cycle means poll() itself always
            # finishes quickly, keeping "Simulation Time" and the panel
            # both genuinely live instead of just eventually consistent.
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
                    # Ticks "Simulation Time"/"Cumulative Time" LIVE
                    # between actual progress events (2026-09-17, explicit
                    # user request -- Level 0's own on_progress only fires
                    # every CONVERGENCE_CHECK_INTERVAL steps, which can
                    # leave the displayed time visibly frozen for a while
                    # in between; same wall-clock-not-solver-progress idea
                    # _run_background's own poll loop already uses for
                    # "Precomp time" during pressure calibration, which
                    # has no progress callback of its own at all).
                    self._current_sim_time_s = time.perf_counter() - self._sim_start_time
                    self._record_level_history()
            self.root.after(80, poll)

        self.root.after(80, poll)

    def _finish_inflate(self):
        """Tail end of an Inflate click, called once _finish_frame_replay
        has already applied the winning calibration trial's own final
        result to self.positions/last_stats/iteration_count -- this method
        only reports it (no `_current_sim_time_s` update here any more:
        Level 1+ has no separate "Sim" phase left at all, see on_inflate_
        clicked's own docstring; ALL of a Level 1+ row's own Simulation
        Time is "Precomp", already finalized in _on_pressure_calibrated)."""
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
        """Level 0's analogue of on_inflate_clicked -- no pressure to
        calibrate first (relax_initial_configuration is pure springs, no
        pressure term at all, see stretchy_mesh's docstring), so this
        goes straight to the streamed run. Always runs to convergence
        (ignores the debug-mode steps-vs-convergence choice, which only
        applies to Inflate) -- Relax's whole point is to finish the
        initial-configuration algorithm, not to be steppable."""
        if self.positions is None or self.subdivision_level != 0 or self.last_stats.get("converged"):
            return
        # Same capture-once rationale as _on_pressure_calibrated -- see
        # self._current_gtol's own comment.
        self._current_gtol = self._get_tolerance()
        self.stop_event = threading.Event()
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self._set_status("Relaxing random start into a well-separated shape...", "info")
        # Level 0 has no pressure-calibration phase at all (see this
        # method's own docstring) -- "Precomp time" stays n/a; only "Sim
        # time" (see __init__) applies here, starting now.
        self._sim_start_time = time.perf_counter()
        self._run_relax_stream(self.stop_event)

    def _run_relax_stream(self, stop_event):
        faces, edge_length = self.faces, self.edge_length
        gtol = self._current_gtol
        # KICK_WINDOW's random-perturbation mechanism (stretchy_mesh.py)
        # disabled here for now, per explicit user request -- it was found
        # to interact badly with a genuinely slow (not stuck) relaxation,
        # re-disturbing the mesh right as it was converging. See
        # LEVEL0_STEP_MAX_MULTIPLIER's own comment in stretchy_mesh.py for
        # the specific failure this caused at Level 0 before that fix.
        rng = None
        # relax_initial_configuration's own `nfev`/`steps_taken` -- both in
        # each on_progress callback and in its final return -- is the
        # CUMULATIVE count for this one call (there's no chunking to make
        # it merely incremental, see _run_chunked_relax_stream's own
        # docstring), but self.iteration_count needs to keep accumulating
        # across SEPARATE Relax clicks at Level 0 too (reset only on
        # promotion -- see _finish_relax/_record_level_history) -- so this
        # call's own contribution is `base_iteration_count + nfev`, not
        # nfev alone.
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
        # optimality/converged are stashed here (self._pending_relax_
        # stats), NOT written into self.last_stats -- Level 0's own
        # Convergence column shows "--" for the WHOLE time Relax is
        # running (2026-09-17, explicit user request -- "only show the
        # convergence value after simulation is done"), same "--"-while-
        # unknown sentinel Level 1-3's own Computing phase already uses,
        # via last_stats["optimality"] staying None throughout. _finish_
        # relax is what actually reveals it, reading the real final value
        # back from here -- it needs the true converged flag regardless
        # of whether the display shows it yet.
        self._pending_relax_stats = {"optimality": optimality, "converged": converged}
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": None, "converged": None,
                            "gtol": self._current_gtol}
        self._current_sim_time_s = time.perf_counter() - self._sim_start_time
        self._record_level_history()
        self._set_status(f"Relaxing... {self.iteration_count} steps so far "
                          f"(edges stretched up to {max_stretch:.2f}%).", "info")
        # Only Level 0's own panel actually changes here -- a full draw()
        # (Net panel plus every "Level N" panel) was the original code,
        # but measured at ~0.3-0.5s per call for a mid-size net, which is
        # SLOWER than _run_chunked_relax_stream's own 80ms poll interval.
        # That mismatch is what made "Simulation Time" look like it
        # "stalls then jumps" (2026-09-17, explicit user report) even
        # after the poll loop itself started ticking it every 80ms
        # (see that method's own comment): once a single progress event's
        # own draw() call runs longer than the poll interval, every
        # already-due `after()` callback queued up behind it gets
        # processed in the SAME burst before Tk's event loop ever returns
        # control to actually repaint the screen -- the underlying DATA
        # was updating the whole time, but the display only caught up
        # once the burst ran out. Exactly the same root cause fixed for
        # Inflate's own replay (_replay_step's own comment) -- a targeted
        # _draw_level_panel call keeps each progress tick cheap enough
        # that the poll loop's own 80ms cadence (and the live time tick
        # riding along with it) actually reaches the screen promptly.
        self._draw_level_panel(0, self.faces, self.positions, self.face_of_fine)

    def _finish_relax(self):
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        # Reveals the real optimality/converged now -- see _apply_relax_
        # progress's own comment for why these were stashed separately
        # rather than kept live in self.last_stats while Relax was still
        # running. Applies regardless of HOW this run ended (converged,
        # Stopped, or step-cap) -- all three count as "simulation is
        # done" for the purpose of finally showing a real value here.
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
            # Level 0 and Level 1 share the exact fan-triangulated
            # topology (see module docstring) -- promoting the
            # just-relaxed result into Level 1's starting position is a
            # pure relabeling, not a new subdivide_once call.
            self.level_snapshots[0] = {"faces": self.faces, "positions": self.positions,
                                        "face_of_fine": self.face_of_fine}
            level0_button = self.level_action_buttons.get(0)
            if level0_button is not None:
                level0_button.config(text="Relax", command=self.on_relax_clicked)
            self.subdivision_level = 1
            self.iteration_count = 0
            # Same reset as _subdivide_step's own -- see its comment.
            self._current_precomp_time_s = None
            self._current_sim_time_s = None
            # Level 1's own "Target RMS stretch" spinner -- same as
            # _subdivide_step's own (see its comment).
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
        """Debug-mode-only "Validate Mesh" button: runs _validate_mesh
        against the CURRENTLY loaded self.faces (whatever subdivision
        level it's at right now) and reports the result in a modal
        messagebox -- a synchronous, on-demand check, unlike Inflate/
        Relax's own background-threaded runs, since the check is cheap
        (pure index math, no iterative solve, and no dependence on
        self.positions at all -- see _validate_mesh's own docstring)."""
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
            # The frontier level's action button is deliberately left
            # alone here -- the caller (_on_pressure_calibrated/
            # on_relax_clicked) re-enables it right after this runs,
            # turned into the Stop control (see
            # _set_level_action_button_running); every OTHER level's
            # stays disabled like normal, since it was never eligible
            # anyway (see _update_level_action_buttons). Neither mode has
            # a separate Stop button to arm/disarm here.
            for level, button in self.level_action_buttons.items():
                if level != self.subdivision_level:
                    button.state(["disabled"])
        # self.auto_button was just blanket-(dis)abled above like every
        # other control -- re-sync it regardless of which branch ran:
        # while an Auto sequence itself is driving the run that's
        # starting/finishing, this RE-ENABLES it (reading "Stop Auto"),
        # the same "frontier button survives the blanket disable"
        # exception _set_level_action_button_running makes for the
        # per-level buttons -- see _update_auto_button's own docstring.
        self._update_auto_button()

    def _run_background(self, fn, on_done, on_progress=None):
        """Run fn(queue_progress) in a background thread and call
        on_done(result) on the main thread once it finishes -- used for
        on_inflate_clicked's pressure calibration
        (estimate_pressure_for_target_stretch), which can take a moment.
        `queue_progress` is a callable fn may call zero or more times
        (from the background thread -- Tk isn't thread-safe, so it only
        ever pushes to a queue) to report LIVE progress; the main thread
        (via the scheduled poll below) is the only one that touches Tk
        widgets, and calls `on_progress(payload)` with whatever fn last
        reported, if `on_progress` is given. (Relax has its own streaming
        variant, _run_relax_stream, since it needs a live PANEL redraw too
        -- Inflate used to as well, _run_inflate_stream, before pressure
        calibration's own winning trial became the entire Inflate result,
        see on_inflate_clicked.)

        Progress messages are COALESCED, same as _run_chunked_relax_
        stream's own poll (see its comment for why -- a slow on_progress
        handler could otherwise fall behind a fast-arriving backlog and
        never catch up): only the LATEST queued progress payload is ever
        passed to `on_progress` in a given poll cycle, older ones are
        dropped as superseded. "Precomp time"/"Cumulative Time" tick LIVE
        (self._current_precomp_time_s from self._precomp_start_time,
        which on_inflate_clicked sets right before calling this) on
        EVERY poll cycle UNCONDITIONALLY, same wall-clock-not-progress
        idea "Sim time" already used -- per explicit user request. This
        has to be unconditional, not an "else" alongside on_progress (an
        earlier version had it as one -- a real bug, caught directly:
        with progress messages arriving on essentially every 100ms poll
        during calibration, the timer tick's own branch almost never ran
        at all, so "Simulation Time" visibly stopped updating for Level
        1-3 specifically, the one case with an on_progress callback in
        the first place). Couples this generic-looking helper to
        calibration specifically, but so does its docstring above
        already (it has exactly one caller)."""
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
            # Unconditional -- see this method's own docstring for why an
            # "else" here (alongside on_progress below) was a real bug.
            self._current_precomp_time_s = time.perf_counter() - self._precomp_start_time
            if latest_progress is not None and on_progress is not None:
                on_progress(latest_progress)  # also refreshes the history table itself
            else:
                self._record_level_history()
            self.root.after(100, poll)

        self.root.after(100, poll)

    # ---- drawing ----

    def _draw_target_faces(self, theme):
        """The UNDEFORMED net: every face laid out flat and CONNECTED to
        its neighbors (self.target_layout, precomputed once per net
        selection by a breadth-first search over shared edges -- see
        build_stretchy_net_layout) -- what the mesh would look like cut
        out of paper and unfolded flat, before any stretching/bending
        closes it up into the solved 3D shape on the right.

        Always shows the BASE (level 0) polygons here -- not the current
        level's individual fine triangles, and (2026-09-16, explicit user
        request -- "too busy") no fine-mesh subdivision overlay either,
        whatever the current subdivision level -- just the plain base
        faces, as a 2D preview of the mesh actually being solved. When
        the loaded net carries interactive_builder_app's own saved
        connections (self.target_connections), each one's bezier curve is
        drawn too (module-level _connection_curve_points) -- the curve
        only, never its two adjustable handles, since this panel is
        read-only."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        all_pts = []
        for face_idx in sorted(self.target_layout):
            # self.target_layout's own keys are already GROUP ids (each
            # entry came from one net_layout/BFS entry directly -- see
            # _layout_from_net_layout/_face_colors_by_group), so this
            # looks color up the same way _draw_level_panel's per-group
            # add_mesh calls do, not the flat self.colors list.
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
                    # A bezier's own control points can bow it well past
                    # its two faces' combined extent (that's the whole
                    # point of dragging a handle) -- feeding its sampled
                    # points into the SAME bounding box the faces use
                    # below (2026-09-16, explicit user request) is what
                    # keeps a bulging curve from getting clipped at the
                    # panel's own edge, and keeps the default (net_pan
                    # zero) framing centered on everything actually
                    # drawn, not just the polygons.
                    all_pts.extend(curve)

        all_pts = np.array(all_pts)
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        pad = 0.6
        # self.net_zoom (1.0 = unzoomed, matching the original fixed
        # lo-pad..hi+pad framing exactly) shrinks/grows this same
        # half-extent around the layout's own center -- see
        # _on_net_scroll, the Net panel's own analogue of every "Level N"
        # panel's self.level_zoom.
        # self.net_pan (world-unit offset, right-drag -- _on_net_pan_motion)
        # shifts this same center, independently of net_zoom -- its own
        # analogue of every "Level N" panel's self.level_pan, just a plain
        # 2D offset here rather than a 3D one added to a PyVista camera.
        center = (lo + hi) / 2 + self.net_pan
        half_range = (hi - lo) / 2 + pad
        # Stretched to the PANEL's own aspect ratio (NET_PANEL_SIZE,
        # which this panel's own figure size already matches exactly --
        # see _build_level_pv_panel's own comment) before dividing by
        # zoom, rather than handing set_aspect("equal") two independent
        # half_range values and letting IT shrink whichever axis has
        # proportionally less content (its own default `adjustable=
        # "box"` behavior) -- 2026-09-16, explicit user request: that
        # shrinking is exactly what left this panel's own margins
        # visibly thicker than every "Level N" panel's, which never lets
        # equal-aspect crop its own box short this way (see camera.
        # parallel_scale's own `max(1.0, panel_height / panel_width)`
        # term in _render_level_pv, the same idea applied there).
        # Whichever axis needs MORE room (relative to the panel's own
        # aspect ratio) wins; the other is grown to match rather than
        # left as dead margin, so the box set_xlim/set_ylim request
        # already fills the panel exactly and set_aspect never has
        # anything left to shrink.
        panel_aspect = NET_PANEL_SIZE[0] / NET_PANEL_SIZE[1]
        half_y = max(half_range[1], half_range[0] / panel_aspect)
        half_range = np.array([half_y * panel_aspect, half_y]) / self.net_zoom
        self.ax2d.set_xlim(center[0] - half_range[0], center[0] + half_range[0])
        self.ax2d.set_ylim(center[1] - half_range[1], center[1] + half_range[1])
        self.ax2d.set_aspect("equal")
        # No ax.set_title() here -- "Net" is a plain Tkinter Label above
        # this canvas instead, same as every "Level N" panel's title (see
        # __init__'s Design notes on why titles live outside the drawing
        # area now).

    def _on_net_scroll(self, event):
        """Mouse-wheel-scroll on the Net panel zooms it (self.net_zoom) --
        the Net panel's own analogue of _on_level_scroll, just scaling
        _draw_target_faces' own bounding-box half-extent instead of a
        PyVista camera. Only the Net panel redraws (_draw_target_faces +
        draw_idle), not every "Level N" panel too -- net_zoom has no
        effect on them, so re-rendering PyVista's off-screen scenes on
        every Net-panel scroll tick would just be wasted work."""
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
        """Right-click-drag on the Net panel translates it (self.net_pan,
        added directly to _draw_target_faces' own bounding-box center) --
        the Net panel's own analogue of _on_level_pan_motion, just a
        plain 2D data-space offset instead of a 3D one applied through a
        PyVista camera, since this panel is matplotlib. Converts the
        screen-pixel drag into DATA units via the axes' OWN current
        x/ylim and the canvas widget's current pixel size (both already
        reflect the current zoom, so this stays a 1:1 "grabbed and slid"
        drag at any zoom level). Sign verified directly per axis (not
        just derived), since the two do NOT match: shifting the view's
        center by -dx (x) or +dy (y) in data units is what makes a fixed
        data point's SCREEN position move by the mouse's own (dx, dy) --
        the y sign flips relative to x because Tk widget pixels grow
        DOWNWARD while this axes' own data y grows UPWARD, and the two
        effects don't cancel out the way a naive "same formula, just
        matplotlib" guess would assume (an earlier version used -dy here
        and panned vertically backwards)."""
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
        """Middle-click on the Net panel resets pan AND zoom back to
        their defaults (2026-09-16, explicit user request -- same idea
        as _on_level_pan_reset, minus rotation, which this 2D panel has
        none of)."""
        self.net_pan = np.zeros(2)
        self.net_zoom = 1.0
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        self._draw_idle_all()

    def draw(self):
        """Redraws the Net panel plus every "Level N" panel: level ==
        self.subdivision_level draws LIVE from current state; a level in
        self.level_snapshots (already subdivided past, or -- for Level
        0 -- promoted away from by a converged Relax) draws its frozen
        state; any other level hasn't been reached yet and draws empty
        (see _draw_level_panel). Every level panel shares ONE camera
        orientation (self.level_rotation, see __init__'s Design notes)
        -- nothing further to sync here, since _draw_level_panel already
        renders every panel from that same shared state on every call.

        A level with an ACTIVE replay-slider scrub (self._level_frames/
        _level_scrub_index both set for it, see _update_replay_slider's
        own docstring) shows that captured frame's own positions
        INSTEAD of its live/frozen ones -- faces/face_of_fine are still
        whichever of the two above apply (a captured trajectory never
        changes a level's own topology, only its positions over time),
        so this only ever substitutes positions, and only for a level
        that's actually been reached (faces is not None) -- self.
        positions/level_snapshots themselves are left untouched either
        way, so this is purely a display override."""
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
