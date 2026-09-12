"""
Inflate Polyhedron -- interactive fabric relaxation for stretchy meshes.

    python src/apps/inflate_polyhedron_app/app.py

Nets here (data/input/stretchy_nets/*.json, see utils/inflate_polyhedron/stretchy_mesh.py
for the vertex-loop format) are specified directly as vertex loops --
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
   (30/20/10% respectively, tapered down as resolution increases since a
   finer mesh needs LESS relative stretch per edge to trace the SAME
   overall curvature) but independently user-editable at any time, and
   used identically by a manual Inflate click and by "Auto" (both just
   call on_inflate_clicked, which always reads whichever level is
   current). Then applies ONE relaxation pass
   (stretchy_mesh.relax_once) at that pressure, continuing from wherever
   the mesh currently is -- so repeated clicks let you watch/steer the
   shape settle incrementally, and re-calibrate each time since pressure
   is no longer something the user sets directly (required pressure
   varies a lot between nets -- it scales with total surface area, not
   vertex/face count -- so a single fixed number would be either too
   gentle or wildly excessive depending which net is loaded). relax_once
   walks small explicit steps along a genuine spring-vs-pressure force
   (see stretchy_mesh's Design notes) -- no volume or remembered state
   anywhere in it, so it can't compound across a Subdivide.
   - The radio buttons control how much work the actual inflation part of
     each "Inflate" click does (after calibration): either a capped
     number of relax_once steps (`max_nfev`, literally N iterations now),
     or an uncapped run to relax_once's own convergence tolerance -- the
     "Tolerance" spinner in Setup (self.tolerance_var, default
     DEFAULT_TOLERANCE, NOT the fixed stretchy_mesh.CONVERGENCE_GTOL a
     bare relax_once/relax_initial_configuration call would otherwise
     default to -- some meshes have a long, slow-shrinking tail after the
     shape has visibly settled, so a looser tolerance than it might seem
     it needs to be is often the right call). Captured once per Relax/
     Inflate click (self._current_gtol), not re-read live mid-run (the
     spinner is disabled for the run's duration anyway), and forwarded to
     pressure calibration too (estimate_pressure_for_target_stretch's own
     `gtol`) so a run's calibration phase and its actual inflation settle
     against the SAME threshold.
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
   "Convergence" cell -- the relax's own `max_force` (the worst vertex's
   net force) against the tolerance that run actually used (recorded per
   row, not re-read live -- see point 4 above), with a check or cross
   mark for whether it's below it -- updated live while Inflate/Relax
   runs. A checkmark can appear next to a `max_force` that's still ABOVE
   that threshold: relax_once/relax_initial_configuration also declare
   convergence via a separate stall-window criterion (max_stretch_pct
   unchanged for many steps -- see stretchy_mesh's own STALL_WINDOW
   comment) when force alone never quite settles; the cell adds
   "(stalled)" in that specific case so it's self-explanatory rather than
   looking like a contradiction. STALL_WINDOW (200 -> 2000) and this
   app's own INFLATE_SAFETY_STEP_CAP (5000 -> 20000) were both raised
   together after a user reported a single, locally concave vertex
   sometimes getting stuck failing to "pop out" -- a genuinely slow but
   real correction could plateau-trigger the OLD, shorter stall window
   well before actually finishing, mistaking "changing very slowly" for
   "done changing" (see stretchy_mesh.STALL_WINDOW's own comment for why
   this specifically mattered for THIS app's own chunked streaming, not
   just a raw uncapped relax_once call).
6. The view below is "Net" (the flat, undeformed layout, matplotlib)
   plus one 3D panel per level, "Level 0".."Level N" (MAX_LEVEL total,
   plus Level 0). The Net panel supports its own mouse-wheel zoom
   (self.net_zoom, _on_net_scroll) scaling _draw_target_faces' own
   bounding-box-derived view, independent of every "Level N" panel's own
   self.level_zoom (they're different rendering stacks -- matplotlib
   here, PyVista there -- with no shared camera state). When the loaded
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
   off-screen-rendered image. Every level panel shares ONE click-drag
   rotation state (self.level_rotation, a scipy.spatial.transform.Rotation
   quaternion -- see _on_level_motion) -- a drag on any panel rotates all
   of them together, matching what the old matplotlib panels' rotation
   sync used to do. (Tried on Level 0 alone first, to validate the
   approach before applying it to every level.) An earlier version stored
   azimuth/elevation as two separate Euler angles, which hits gimbal lock
   near the poles (elevation approaching +-90 degrees) -- a quaternion has
   no such singularity, since the whole orientation is one object rather
   than two angles applied in a fixed order. Every level panel likewise
   shares ONE mouse-wheel zoom state (self.level_zoom) -- scrolling over
   any panel zooms all of them together, same rationale.
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
     `faces`). That question is still answerable live via "Show normals"
     below instead.
   - "Show normals" (self.show_normals_var) draws each triangle's own
     outward normal as a line segment from its centroid, in
     NORMAL_COLOR, on every populated "Level N" panel (_draw_level_panel)
     -- an inward-pointing one is then immediately obvious on sight; this
     is now the ONLY way this app answers "does the CURRENT embedding
     look inside-out", since Validate Mesh no longer does (see above).
     Each segment is scaled to NORMAL_LENGTH_FRACTION (0.5) of that
     triangle's own mean CURRENT edge length (not rest length), so it
     always reads as roughly "half an edge long" relative to whatever's
     on screen (a full edge length, tried first, read too long against a
     dense mesh), regardless of overall mesh scale or how far from rest
     it's currently stretched.
8. "Auto" (on_auto_clicked/_auto_step; visible and usable in BOTH modes,
   unlike debug mode's own diagnostics above) runs the WHOLE pipeline
   unattended, from wherever it currently is: Relax at Level 0, then
   Inflate/Subdivide/Inflate/.../Level MAX_LEVEL -- exactly the sequence
   a user would otherwise click through by hand, one button click.
   _auto_step decides what "next" means each time it's called (once to
   start, then again from the tail of _finish_relax/_finish_inflate
   every time a step it started actually finishes): (re)try Relax/
   Inflate at the current level if it hasn't converged yet, Subdivide
   once it has (immediately continuing to the newly-subdivided level's
   own first Inflate attempt, since Subdivide itself is synchronous and
   schedules no callback of its own), or stop once Level MAX_LEVEL
   converges. "If inflation doesn't reach convergence, it keeps trying
   at the same level" per an explicit user request -- bounded by
   AUTO_MAX_RETRIES_PER_LEVEL (_auto_try) so a target that's genuinely
   unreachable for some mesh doesn't retry forever with no way to
   notice; Auto stops and reports this plainly rather than hanging.
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
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont

import numpy as np
from scipy.spatial.transform import Rotation
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import pyvista as pv
import sv_ttk

from common.paths import STRETCHY_NETS_DIR
from common.ui_theme import STATUS_COLORS, PLOT_THEME, FACE_COLORS
from utils.inflate_polyhedron.stretchy_mesh import (
    load_stretchy_mesh, relax_once, relax_initial_configuration, random_initial_positions,
    estimate_pressure_for_target_stretch, mesh_edges, EDGE_LENGTH,
    PLANARITY_WEIGHT, CONVERGENCE_GTOL,
)
from utils.inflate_polyhedron.mesh_levels import MAX_LEVEL, subdivide_once
from utils.subdivisions.mesh_subdivide import load_fabric_spec
from utils.inflate_polyhedron.stretchy_net_layout import build_stretchy_net_layout
from utils.geometry.polygon_geom import regular_polygon_vertices, apply_rigid
from utils.subdivisions import subdivide as subdivide_polygon

DEFAULT_NET_BASENAME = "cube"

# A fabric-subdivided net's fine mesh edges are drawn thin/faint so the
# subdivision reads as texture rather than a bold wireframe competing
# with the per-coarse-face coloring -- see load_fabric_spec.
SUBDIVISION_EDGE_ALPHA = 0.35
SUBDIVISION_EDGE_WIDTH = 0.5

# How much of each "Level N" panel's frame the shape's own bounding
# box fills: axis half-range = shape's half-extent * this. 1.0 would
# exactly touch the frame edge; below 1.0 crops in past it, making the
# shape look bigger within the same panel ("zooming in" without actually
# resizing the panel/window). 0.8 (was 1.2, a 20% MARGIN, before any
# zooming) makes the shape 1.2/0.8 = 50% larger within the frame than
# that original size.
WIREFRAME_VIEW_FILL = 0.8

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
# neighbors.
LEVEL_PANEL_SIZE = (320, 450)
# How much of the panel the shape's own bounding box fills, on top of
# the aspect-ratio correction below -- 1.0 would make the shape's widest
# dimension exactly touch the panel edge; below 1.0 leaves margin around
# it (shrinks the apparent shape without resizing the panel). 0.6, then
# a further "60% of that" per two rounds of user request (the unzoomed
# 1.0 rendered noticeably too large/cropped against the panel, and 0.6
# alone still did too) -- 0.6 * 0.6 = 0.36.
LEVEL_ZOOM_FILL = 0.36
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
# zoomed in). Clamped by LEVEL_ZOOM_MIN/MAX so scrolling can't shrink the
# shape to nothing or push it arbitrarily far away.
LEVEL_ZOOM_STEP = 1.1
LEVEL_ZOOM_MIN = 0.1
LEVEL_ZOOM_MAX = 10.0

# Same idea as LEVEL_ZOOM_STEP/MIN/MAX, for the Net panel's own
# mouse-wheel zoom (_on_net_scroll) -- a separate state (self.net_zoom)
# since the Net panel is matplotlib, not a PyVista camera: it scales the
# half-extent _draw_target_faces derives from the flat layout's own
# bounding box, rather than a camera parallel_scale.
NET_ZOOM_STEP = 1.1
NET_ZOOM_MIN = 0.2
NET_ZOOM_MAX = 10.0

# Overall UI text size multiplier -- applied once, at startup, to every
# named Tk/ttk font (see _scale_ui_fonts) so the whole app's text (not
# just this one label) grows together rather than each widget needing
# its own hardcoded size.
UI_FONT_SCALE = 1.3

# Every panel's title ("Net", "Level N") is a plain Tkinter Label above
# its image/canvas, not text drawn inside the image itself -- a title
# drawn INSIDE a PyVista panel's own rendered scene clipped against the
# panel's own edge (see _render_level_pv's Design notes), which a real
# widget placed above the image can't do. Scaled by UI_FONT_SCALE like
# every other font (see _scale_ui_fonts) since it's a plain (family,
# size) tuple, not a named Tk font _scale_ui_fonts can reach on its own.
LEVEL_TITLE_FONT = ("TkDefaultFont", round(11 * UI_FONT_SCALE))

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
DEFAULT_TOLERANCE = 1e-3

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
# any target). Was {1: 60.0, 2: 30.0, 3: 15.0}; lowered per explicit
# user request.
LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 30.0, 2: 20.0, 3: 10.0}

# Debug mode's "Show normals" toggle (_draw_level_panel) draws each
# triangle's own outward normal as a line segment in this color, from
# its centroid, scaled to that SAME triangle's own mean edge length (so
# an inward-pointing normal is immediately obvious regardless of overall
# mesh scale) -- distinct from every FACE_COLORS entry and from
# PLOT_THEME's own fg/edge color, so it reads clearly against either.
NORMAL_COLOR = "yellow"
# How long each normal segment is drawn, as a fraction of its own
# triangle's mean edge length -- 1.0 (a full edge length) read too long
# against a dense/fine mesh per a user request; halved.
NORMAL_LENGTH_FRACTION = 0.5

# on_inflate_clicked runs relax_once in a growing sequence of chunks
# (5, 10, 20, ...) instead of one big max_nfev call, so the iteration
# counter/plot update incrementally instead of jumping straight from the
# start count to the end one -- each chunk continues from the previous
# one's own final positions, so nothing is lost by splitting the run up.
INFLATE_CHUNK_START = 5
INFLATE_CHUNK_MAX = 200
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
INFLATE_SAFETY_STEP_CAP = 20000

# "Auto" (on_auto_clicked/_auto_step): how many consecutive un-converged
# Relax/Inflate clicks it will (re)try at the SAME level -- each one
# already runs up to INFLATE_SAFETY_STEP_CAP steps on its own, so this
# is a second, outer safety net specifically for "keeps trying at the
# same level" per an explicit user request, not a substitute for that
# per-click cap. Without SOME bound here, a mesh that can genuinely
# never reach the current tolerance (e.g. an unreachable Target RMS
# stretch) would make Auto retry that level forever with no way to
# notice or report it short of the user clicking "Stop Auto" by hand.
AUTO_MAX_RETRIES_PER_LEVEL = 10


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
    saved [{"cx", "cy", "rotation"}, ...], one entry per face, same
    order as `faces` (its "Net JSON import/export" section). Returns
    {face_idx: [2D point, ...]} -- the exact same shape
    build_stretchy_net_layout returns -- by reproducing each face's
    saved rigid transform directly, rather than re-deriving a layout
    from scratch via a fresh BFS spanning tree. That matters because a
    BFS can't reproduce an arrangement it wasn't given: it only follows
    the FIRST shared edge it reaches an already-visited face through
    (see build_stretchy_net_layout's own docstring), so any OTHER
    edge-sharing between two faces -- entirely normal for a stretchy
    mesh, see this module's own docstring -- is silently dropped from
    the picture; a net a user carefully arranged in the interactive
    builder (and re-derived exact connections for) deserves to show up
    here exactly as left, not re-flattened from just a spanning subset
    of its real adjacency.

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
    for face_idx, (face, layout) in enumerate(zip(faces, net_layout)):
        theta = layout["rotation"]
        c, s = np.cos(theta), np.sin(theta)
        R = np.array([[c, -s], [s, c]])
        t = np.array([layout["cx"], layout["cy"]]) / _INTERACTIVE_BUILDER_EDGE_LENGTH
        points = apply_rigid(regular_polygon_vertices(len(face)), R, t)
        placed[face_idx] = [np.array([p[0], -p[1]]) for p in points]
    return placed


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
    winding_lines = [f"  edge {v}->{w} runs the SAME direction in {c} faces {owners[(v, w)]} "
                      f"(should be reversed in all but one)"
                      for (v, w), c in counts.items() if c > 1]
    ok = not winding_lines

    if ok:
        lines = [f"Structural winding: all {len(faces)} faces agree with their "
                 f"neighbors -- no shared edge runs the same direction twice (OK)."]
    else:
        lines = [f"Structural winding: {len(winding_lines)} edge(s) where neighboring "
                 f"faces disagree:"]
        lines += winding_lines
    return ok, lines


class InflatePolyhedronApp:
    def __init__(self, root):
        self.root = root
        # Wide enough for Net + Level 0..MAX_LEVEL (5 panels), each a
        # fixed LEVEL_PANEL_SIZE-wide image -- the panel row no longer
        # stretches its frames to fill extra window width (see
        # panels_row's own comment), so this only needs to fit the
        # panels' own natural width, not leave room to spread them out.
        # Tall enough for Setup + status + Convergence History + each
        # panel's own title-Label-plus-image-plus-button stack at their
        # full natural size (root.winfo_reqheight() once everything is
        # built) -- too short here silently SQUEEZES every image Label
        # below LEVEL_PANEL_SIZE's own height (Tk shrinks a packed widget
        # to whatever's left rather than erroring), which visibly cropped
        # the bottom of every panel and threw off where mouse drags
        # actually land on it (see _on_level_drag_start and friends).
        root.geometry("1700x880")
        root.minsize(820, 600)

        sv_ttk.set_theme("dark")
        self._scale_ui_fonts()

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
        self.combo = ttk.Combobox(net_group, state="readonly", width=30,
                                   textvariable=self.net_var)
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self.on_select_net)

        target_group = ttk.Frame(setup_row)
        target_group.pack(side=tk.LEFT, padx=(24, 0))
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
        self.target_rms_spins = {}
        for level in (1, 2, 3):
            ttk.Label(target_group, text=f"L{level}:").pack(side=tk.LEFT, padx=(8, 2))
            var = tk.DoubleVar(value=LEVEL_DEFAULT_TARGET_RMS_PCT[level])
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
            spin = ttk.Spinbox(target_group, from_=0.1, to=200.0,
                                increment=1.0, width=5,
                                textvariable=var, format="%.1f")
            spin.pack(side=tk.LEFT)
            ttk.Label(target_group, text="%").pack(side=tk.LEFT, padx=(2, 0))
            self.target_rms_vars[level] = var
            self.target_rms_spins[level] = spin
        # Pressure is no longer user-editable or separately displayed --
        # "Inflate" calibrates it itself (see on_inflate_clicked) and it's
        # already logged per level in the Convergence History table.
        self.pressure_value = DEFAULT_PRESSURE

        tolerance_group = ttk.Frame(setup_row)
        tolerance_group.pack(side=tk.LEFT, padx=(24, 0))
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
        self.tolerance_spin = ttk.Spinbox(tolerance_group, from_=1e-10, to=1e-1,
                                           increment=1e-7, width=10,
                                           textvariable=self.tolerance_var, format="%.0e")
        self.tolerance_spin.pack(side=tk.LEFT)

        # "Auto": visible/usable in BOTH modes (unlike the debug-only row
        # below), since it's just a scripted sequence of the SAME
        # Relax/Inflate/Subdivide actions a user could click by hand --
        # see on_auto_clicked/_auto_step for the actual driving logic.
        auto_group = ttk.Frame(setup_row)
        auto_group.pack(side=tk.LEFT, padx=(24, 0))
        self.auto_button = ttk.Button(auto_group, text="Auto", command=self.on_auto_clicked)
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
        self.show_normals_check = ttk.Checkbutton(self.mode_row, text="Show normals",
                                                    variable=self.show_normals_var,
                                                    command=self.draw)
        self.show_normals_check.pack(side=tk.LEFT)

        # ---- Status/progress: shared by both modes, always visible,
        # positioned right after Setup. ----
        status_frame = ttk.Frame(root)
        status_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=160)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var)
        self.status_label.pack(side=tk.LEFT)

        # ---- Convergence history: one row per subdivision level visited
        # this net session (including Level 0 now -- see module
        # docstring), showing the pressure last calibrated for it
        # (self.pressure_value -- only ever set by on_inflate_clicked's
        # calibration phase; "n/a" for Level 0, which has no pressure at
        # all, see _record_level_history), how many Inflate/Relax steps
        # that level took (self.iteration_count, reset to 0 on every
        # Subdivide/promotion -- see _subdivide_step/_finish_relax), the
        # stretch stats at whatever point it's currently at (updated live
        # while Inflate/Relax runs, finalized once it stops -- see
        # _record_level_history's callers, RMS shown against the CURRENT
        # "Target RMS stretch" spinner value -- see _refresh_history_table),
        # and a single combined "Convergence" cell -- the relax's own
        # `optimality` (the worst vertex's net force) against the fixed
        # CONVERGENCE_GTOL threshold, with a check/cross mark for whether
        # it's below it (see _refresh_history_table). height=MAX_LEVEL+1
        # (0..MAX_LEVEL) since that's the most rows this table will ever
        # hold -- a taller fixed height would just reserve blank space
        # below whatever's actually populated. ----
        self.history_frame = ttk.LabelFrame(root, text="Convergence History", padding=12)
        self.history_frame.pack(side=tk.TOP, fill=tk.X, padx=14, pady=(0, 8))
        history_columns = ("level", "pressure", "steps", "max_stretch", "rms_stretch",
                            "convergence")
        self.history_tree = ttk.Treeview(self.history_frame, columns=history_columns,
                                          show="headings", height=MAX_LEVEL + 1)
        for col, heading, width in (
                ("level", "Level", 50), ("pressure", "Pressure", 80), ("steps", "Steps", 70),
                ("max_stretch", "Max Stretch %", 110), ("rms_stretch", "RMS Stretch %", 150),
                ("convergence", "Convergence", 220)):
            self.history_tree.heading(col, text=heading)
            self.history_tree.column(col, width=width, anchor=tk.CENTER)
        # ttk.Treeview can only color a whole ROW, not one cell -- so the
        # Convergence column's check/cross (see _refresh_history_table)
        # comes with its whole row tinted to match, rather than leaving
        # the mark itself in the default text color.
        self.history_tree.tag_configure("converged", foreground=STATUS_COLORS["success"])
        self.history_tree.tag_configure("not_converged", foreground=STATUS_COLORS["error"])
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
        net_panel_frame.pack(side=tk.LEFT)
        # A plain Label, not ax.set_title() -- drawing a title INSIDE a
        # PyVista panel's own rendered image clipped its top edge against
        # the panel boundary (see _render_level_pv's own Design notes);
        # a real Tkinter widget above the image has no such problem, and
        # this same approach is used for every "Level N" panel's title
        # too, so keeping Net's title as a matplotlib ax.set_title()
        # would leave it inconsistently positioned relative to its
        # neighbors' labels.
        ttk.Label(net_panel_frame, text="Net", font=LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        # A disabled, blank button matching every "Level N" panel's own
        # action button below it -- purely to claim the same vertical
        # space, so the Net canvas ends up the same height as every level
        # panel (keeping content aligned in a row rather than Net's
        # canvas rendering visibly larger for having no button competing
        # for space underneath it).
        net_bottom_spacer = ttk.Button(net_panel_frame, text="")
        net_bottom_spacer.state(["disabled"])
        net_bottom_spacer.pack(side=tk.BOTTOM, fill=tk.X)
        self.fig_net = plt.figure(figsize=(3.2, 4.5))
        self.ax2d = self.fig_net.add_subplot(1, 1, 1)
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

        self.level_frames = {}
        self.level_plotters = {}
        self.level_labels = {}
        self.level_photos = {}
        self._level_center = {}
        self._level_half = {}
        # ONE shared camera orientation across every level panel (see this
        # section's own Design notes above) -- updated by a drag on any
        # panel (_on_level_motion), applied to all of them
        # (_render_all_level_panels). A quaternion (scipy Rotation) rather
        # than a separate azimuth/elevation pair -- two Euler angles hit
        # gimbal lock near the poles (elevation -> +-90 degrees, where a
        # horizontal drag stops rotating around a sensible axis); a
        # quaternion represents the whole orientation as one object with
        # no such singularity. _initial_level_rotation() reproduces the
        # old LEVEL_DEFAULT_AZIM/ELEV starting view as a Rotation.
        self.level_rotation = self._initial_level_rotation()
        # ONE shared zoom factor across every level panel, same rationale
        # as level_rotation above -- a scroll on any panel updates
        # it and re-renders all of them (see _on_level_scroll).
        self.level_zoom = 1.0
        self._level_dragging = False
        self._level_last_xy = None
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
        for level in range(0, MAX_LEVEL + 1):
            level_frame = ttk.Frame(panels_row)
            # No fill/expand -- see panels_row's own comment on why
            # every panel hugs its own fixed image size instead.
            level_frame.pack(side=tk.LEFT)
            self.level_frames[level] = level_frame
            button = ttk.Button(level_frame, text="Relax" if level == 0 else "Inflate")
            self.level_action_buttons[level] = button
            # Button packed BEFORE the panel widget, at BOTTOM -- packing
            # it AFTER an expand=True widget would starve it of space,
            # since that widget (packed first) would already have
            # claimed the entire remaining cavity by the time it's
            # placed.
            button.pack(side=tk.BOTTOM, fill=tk.X, in_=level_frame)
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
        self.target_layout = None
        self.positions = None
        self.iteration_count = 0
        self.last_stats = {}
        self.level_history = {}
        self.stop_event = None
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
        # driving the app (see on_auto_clicked/_auto_step) -- _auto_retry_
        # count/_auto_retry_level track how many consecutive Relax/Inflate
        # retries have been spent on the level named by _auto_retry_level
        # (reset to 0 the moment _auto_step notices the CURRENT level has
        # changed since the last time it ran, rather than at every
        # individual Subdivide/promotion call site, so there's exactly
        # ONE place this logic lives).
        self._auto_active = False
        self._auto_retry_count = 0
        self._auto_retry_level = None
        self.current_path = None
        self.current_label = None
        self.label_to_path = {}
        self._apply_plot_theme()
        self.refresh_net_list()
        self._apply_mode_visibility()
        if self.current_label:
            self.on_select_net()

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

    def _on_toggle_debug_mode(self, _event=None):
        self.debug_mode = not self.debug_mode
        self._apply_mode_visibility()

    def _apply_mode_visibility(self):
        """The only actual difference between the two modes: whether the
        steps-vs-convergence radio row (plus Validate Mesh/Show normals)
        is shown. Forces the steps choice back to "convergence" and Show
        normals off when leaving debug mode, so release mode never runs a
        stray fixed-step request or shows a stale normals overlay left
        over from before."""
        self.root.title(f"Inflate Polyhedron{' (debug mode)' if self.debug_mode else ''}")
        if self.debug_mode:
            self.mode_row.pack(fill=tk.X, pady=(8, 0))
        else:
            self.mode_row.pack_forget()
            self.iterate_mode_var.set("convergence")
            if self.show_normals_var.get():
                self.show_normals_var.set(False)
                if self.faces is not None:  # nothing to redraw before a net's ever been loaded
                    self.draw()

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
        # crash) always show in both modes -- those aren't otherwise
        # visible anywhere else.
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
        ttk.Label(level_frame, text=f"Level {level}", font=LEVEL_TITLE_FONT,
                  anchor=tk.CENTER).pack(side=tk.TOP, fill=tk.X)
        label = tk.Label(level_frame, bg=PLOT_THEME["bg"], bd=0)
        label.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        plotter = pv.Plotter(off_screen=True, window_size=list(LEVEL_PANEL_SIZE))
        plotter.set_background(PLOT_THEME["bg"])
        self.level_labels[level] = label
        self.level_plotters[level] = plotter
        self.level_photos[level] = None  # keeps a reference alive -- Tk drops a GC'd PhotoImage
        self._level_center[level] = np.zeros(3)
        self._level_half[level] = 1.0
        label.bind("<ButtonPress-1>", self._on_level_drag_start)
        label.bind("<B1-Motion>", self._on_level_motion)
        label.bind("<ButtonRelease-1>", self._on_level_drag_end)
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

    def _on_level_drag_start(self, event):
        self._level_dragging = True
        self._level_last_xy = (event.x, event.y)

    def _on_level_motion(self, event):
        """Left-click-drag on ANY level panel rotates the shared camera
        orientation (self.level_rotation) and re-renders EVERY panel with
        it in real time -- this app's own analogue of mplot3d's built-in
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
        because "up" is whatever self.level_rotation currently says it
        is (not re-pinned to world +z every frame the way the old
        azim/elev formula did), there's no pole for elevation to
        approach and lock up near -- the earlier version had to clamp
        elevation to +-89 degrees for exactly this reason; this version
        needs no clamp at all."""
        if not self._level_dragging or self._level_last_xy is None:
            return
        last_x, last_y = self._level_last_xy
        dx, dy = event.x - last_x, event.y - last_y
        up = self.level_rotation.apply([0.0, 0.0, 1.0])
        right = self.level_rotation.apply([0.0, 1.0, 0.0])
        sensitivity = np.radians(LEVEL_DRAG_SENSITIVITY)
        yaw = Rotation.from_rotvec(-dx * sensitivity * up)
        pitch = Rotation.from_rotvec(-dy * sensitivity * right)
        self.level_rotation = pitch * yaw * self.level_rotation
        self._level_last_xy = (event.x, event.y)
        self._render_all_level_panels()

    def _on_level_drag_end(self, event):
        self._level_dragging = False
        self._level_last_xy = None
        # One last explicit render, in case the button release didn't
        # come with its own trailing motion event -- _on_level_motion
        # already keeps every panel live-updated during the drag itself,
        # so this is just a safety net for that edge case, not the
        # primary sync point.
        self._render_all_level_panels()

    def _on_level_scroll(self, event):
        """Mouse-wheel-scroll on ANY level panel zooms the shared camera
        (self.level_zoom) and re-renders EVERY panel with it -- the same
        shared-state-across-all-panels approach _on_level_motion uses for
        rotation (see this class's own Design notes in __init__), just
        for zoom instead of angle. event.num is Button-4/5 on X11 (no
        event.delta there); event.delta is Windows/macOS's own signed
        notch count (positive delta zooms in)."""
        if getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            factor = 1.0 / LEVEL_ZOOM_STEP
        else:
            factor = LEVEL_ZOOM_STEP
        self.level_zoom = max(LEVEL_ZOOM_MIN, min(LEVEL_ZOOM_MAX, self.level_zoom * factor))
        self._render_all_level_panels()

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
            face_conn = np.hstack([[3, idx[a], idx[b], idx[c]] for a, b, c in faces])
            mesh = pv.PolyData(points, face_conn)
            colors = np.array(
                [np.array(mcolors.to_rgb(self.colors[c % len(self.colors)])) * 255
                 for c in face_of_fine], dtype=np.uint8)
            mesh.cell_data["colors"] = colors
            plotter.add_mesh(mesh, scalars="colors", rgb=True, show_edges=True,
                              edge_color=PLOT_THEME["fg"], line_width=SUBDIVISION_EDGE_WIDTH)

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

            lo, hi = points.min(axis=0), points.max(axis=0)
            self._level_center[level] = (lo + hi) / 2
            self._level_half[level] = (hi - lo).max() / 2 * WIREFRAME_VIEW_FILL + 1e-6
        self._render_level_pv(level)

    def _render_level_pv(self, level):
        """Positions an orthographic (parallel-projection) camera from
        the SHARED self.level_rotation (see the drag handlers) at a
        distance derived from THIS level's own current bounding box
        (self._level_center/_level_half, set by _draw_level_panel --
        necessary since neither a pure-spring relax nor a pressure
        inflation has any mechanism keeping the result near the origin
        or at a familiar scale), renders off-screen, and blits the
        result into self.level_labels[level]. Parallel rather than
        perspective projection to give every panel fixed, comparable
        axis-limit-like framing with no foreshortening. The panel's
        "Level N" title is a separate Tkinter Label (see
        _build_level_pv_panel), not drawn into this image -- a title
        drawn INSIDE the rendered scene (tried first, via
        plotter.add_text) clipped against the panel's own top edge (a
        "0" losing its top arc, reading as a "U") since a VTK text
        actor's positioning/justification doesn't guarantee it stays
        fully inside the viewport the way a real widget placed above the
        image trivially does."""
        direction = self.level_rotation.apply([1.0, 0.0, 0.0])
        up = self.level_rotation.apply([0.0, 0.0, 1.0])
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
        # LEVEL_ZOOM_FILL then shrinks the shape within that
        # guaranteed-fitting frame.
        panel_width, panel_height = LEVEL_PANEL_SIZE
        # self.level_zoom is a divisor here (like LEVEL_ZOOM_FILL) since
        # parallel_scale is a visible-world-HEIGHT, not a magnification --
        # a bigger level_zoom (scrolled in) must shrink parallel_scale.
        camera.parallel_scale = (half * max(1.0, panel_height / panel_width)
                                  / LEVEL_ZOOM_FILL / self.level_zoom)
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
        self.level_labels[level].configure(image=self.level_photos[level])

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
        precomputed-vs-not state left to flag."""
        paths = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json")))
        self.label_to_path = {}
        for path in paths:
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
            # Default to DEFAULT_NET_BASENAME (cube.json) if present,
            # else just the first net alphabetically.
            default_path = os.path.join(STRETCHY_NETS_DIR, DEFAULT_NET_BASENAME + ".json")
            default_label = next((l for l, p in self.label_to_path.items() if p == default_path), None)
            self.current_label = default_label or (labels[0] if labels else None)

        if self.current_label:
            self.net_var.set(self.current_label)

    def on_select_net(self, event=None):
        chosen = self.net_var.get()
        self.current_label = chosen
        path = self.label_to_path[chosen]
        try:
            faces, self.mesh_name = load_stretchy_mesh(path)
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
        self.colors = [FACE_COLORS[i % len(FACE_COLORS)] for i in range(len(self.base_faces))]

        # Precomputed once per net selection: this panel's flat net
        # layout doesn't change with subdivision level, only its
        # overlay does. A file saved BY interactive_builder_app carries
        # its own "net_layout" section (one {"cx", "cy", "rotation"} per
        # face, same order as "faces") -- when present and the right
        # length, reproduce THAT exact arrangement (_layout_from_
        # net_layout) rather than a fresh one, so a net a user actually
        # built and connected there shows up here exactly as left, not
        # re-derived from scratch. Otherwise (any hand-authored net, or
        # a legacy fabric net with no such section) fall back to
        # build_stretchy_net_layout's own breadth-first spanning tree
        # over shared edges, attaching each face to whichever neighbor
        # discovers it first (see its own docstring) -- _draw_target_
        # faces just reuses whichever of the two this is on every
        # redraw, rather than recomputing either one every time.
        with open(path) as f:
            net_layout = json.load(f).get("net_layout")
        if net_layout is not None and len(net_layout) == len(self.base_faces):
            self.target_layout = _layout_from_net_layout(self.base_faces, net_layout)
        else:
            self.target_layout = build_stretchy_net_layout(self.base_faces)

        # Level 0 and Level 1 share this exact fan-triangulated topology
        # (see module docstring) -- computed once here, up front, rather
        # than re-derived on promotion.
        self.faces, self.edge_length, self.face_of_fine = _build_level1_topology(self.base_faces)
        self.current_path = path
        self.subdivision_level = 0
        self.positions = random_initial_positions(self.faces, seed=0)
        self.iteration_count = 0
        self.last_stats = self._compute_stretch_stats()
        self.level_history = {}
        self.level_snapshots = {}
        self.history_tree.delete(*self.history_tree.get_children())
        self.stop_event = None
        # A fresh net starts over cleanly -- an Auto sequence from the
        # PREVIOUS net (the combo/other controls it would need are
        # disabled during a run anyway, so this can only really happen
        # between runs, but reset defensively regardless).
        self._auto_active = False
        self._auto_retry_count = 0
        self._auto_retry_level = None
        self._record_level_history()
        self._update_level_action_buttons()
        self._update_auto_button()
        self.draw()

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
            self.subdivision_level)
        self.subdivision_level += 1
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
        # however many steps a coarser level happened to need.
        self.iteration_count = 0
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
        stretchy_mesh's docstring -- shown as "n/a" by
        _refresh_history_table), steps so far this level
        (self.iteration_count, see _subdivide_step/_finish_relax), the
        stretch stats at this point, and the actual stopping-condition
        value -- the relax's own `optimality` (None before any
        Inflate/Relax at this level, or if a Stop request aborted before
        any step ran -- see relax_once's docstring) -- all from
        self.last_stats. Called on every subdivide/promotion, every live
        Inflate/Relax progress update, and when a run finishes, so the row
        always reflects the level's latest state rather than only its
        final converged one."""
        self.level_history[self.subdivision_level] = {
            "pressure": None if self.subdivision_level == 0 else self.pressure_value,
            "steps": self.iteration_count,
            "max_stretch_pct": self.last_stats.get("max_stretch_pct", 0.0),
            "rms_stretch_pct": self.last_stats.get("rms_stretch_pct", 0.0),
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

    def _refresh_history_table(self):
        for level in sorted(self.level_history):
            rec = self.level_history[level]
            optimality = rec["optimality"]
            if optimality is None:
                convergence, tags = "n/a", ()
            else:
                # The checkmark tracks the algorithm's own `converged`
                # flag, not a fresh optimality-vs-gtol comparison redone
                # here -- convergence can also come from the stall-window
                # criterion (see _explicit_relax_loop) with optimality
                # still numerically above this row's own gtol, and the
                # mark would otherwise wrongly call that a failure. When
                # that's what actually happened -- converged is True but
                # optimality is still >= gtol -- "(stalled)" says so
                # explicitly, rather than leaving a checkmark next to a
                # ">" comparison looking like a contradiction (a user
                # asked about exactly this after seeing it unexplained).
                gtol = rec["gtol"]
                converged = rec["converged"]
                op = "<" if optimality < gtol else ">"
                mark = "✔" if converged else "✘"  # colored via row tag, not the glyph itself
                stalled_note = " (stalled)" if converged and optimality >= gtol else ""
                convergence = (f"{self._format_sci(optimality)} {op} "
                                f"{self._format_sci(gtol, precision=0)} {mark}{stalled_note}")
                tags = ("converged",) if converged else ("not_converged",)
            pressure_str = "n/a" if rec["pressure"] is None else f"{rec['pressure']:.4g}"
            # Level 0 has no target stretch to chase (relax_initial_configuration
            # is pure springs, not calibrated against the spinner at all).
            # This row's OWN target_rms_pct (recorded at the time IT was
            # calibrated, not read live from the spinner -- see this
            # field's own comment in __init__), so a level's row keeps
            # showing what it was actually chasing even after the
            # spinner later shows a different level's own default.
            rms_str = f"{rec['rms_stretch_pct']:.2f}"
            if level != 0 and rec.get("target_rms_pct") is not None:
                rms_str += f" (target: {rec['target_rms_pct']:.1f})"
            values = (level, pressure_str, rec["steps"], f"{rec['max_stretch_pct']:.2f}",
                      rms_str, convergence)
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
        edges = mesh_edges(self.faces)
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

    def on_inflate_clicked(self):
        """Two phases: first calibrate a pressure for the current "Target
        RMS stretch" (stretchy_mesh.estimate_pressure_for_target_stretch,
        via _run_background -- see _on_pressure_calibrated), THEN actually
        inflate at that pressure via the normal streamed _run_inflate_stream
        (respecting the steps-vs-convergence mode and the Stop button, same
        as always). Recalibrates fresh from wherever self.positions
        currently is on every click, since the user can no longer set
        pressure directly. Calibrates against the CURRENT "Tolerance"
        spinner value too, so the pressure search settles at the same
        threshold the actual inflate run right after it will use."""
        if self.positions is None or self.last_stats.get("converged"):
            return
        faces, edge_length, positions = self.faces, self.edge_length, self.positions
        target_rms_pct = self.target_rms_vars[self.subdivision_level].get()
        # Captured here too, not just at the level-default sites (see its
        # own comment in __init__), in case the user edited the spinner
        # away from that default before clicking Inflate.
        self._current_target_rms_pct = target_rms_pct
        tolerance = self._get_tolerance()
        target_steps = max(1, self.steps_var.get()) if self.iterate_mode_var.get() == "steps" else None
        self._set_status(f"Finding a pressure that settles around {target_rms_pct:.1f}% "
                          "RMS stretch...", "info")
        self._run_background(
            lambda: estimate_pressure_for_target_stretch(positions, faces, edge_length,
                                                           target_rms_pct=target_rms_pct,
                                                           gtol=tolerance,
                                                           rng=np.random.default_rng()),
            (), lambda result: self._on_pressure_calibrated(result, target_steps))

    def _on_pressure_calibrated(self, result, target_steps):
        pressure = result[0]
        self.pressure_value = pressure
        # Captured once here, not re-read live during the run -- the
        # spinner is disabled for the duration anyway (_set_controls_
        # enabled) -- and reused by _apply_inflate_progress so every
        # progress update this run records the SAME threshold it's
        # actually converging against, even if the spinner's value
        # changes later (after the run finishes).
        self._current_gtol = self._get_tolerance()
        self.stop_event = threading.Event()
        self._set_controls_enabled(False)
        self._set_level_action_button_running(True)
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        status = (f"Inflating at pressure {pressure:.4g} for {target_steps} steps..."
                   if target_steps is not None else
                   f"Inflating at pressure {pressure:.4g} until convergence...")
        self._set_status(status, "info")
        self._run_inflate_stream(pressure, target_steps, self.stop_event)

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
        self._auto_retry_count = 0
        self._auto_retry_level = None
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
        buttons: idle (self._auto_active is False) it reads "Auto",
        enabled only once a net is loaded -- otherwise disabled like
        every other control while ANY run is in progress (see
        _set_controls_enabled, which calls this itself after toggling
        everything else, and which this does NOT need to independently
        duplicate for the "disabled during a run" case). While Auto
        itself is driving a run (self._auto_active is True), it instead
        reads "Stop Auto" and is explicitly RE-ENABLED regardless of
        what _set_controls_enabled(False) just did -- the same "frontier
        button survives the blanket disable" pattern
        _set_level_action_button_running uses for the per-level buttons
        -- so the one control that can interrupt a multi-step Auto
        sequence stays clickable throughout every step of it."""
        if self._auto_active:
            self.auto_button.config(text="Stop Auto", command=self.on_auto_stop_clicked)
            self.auto_button.state(["!disabled"])
        else:
            self.auto_button.config(text="Auto", command=self.on_auto_clicked)
            self.auto_button.state(["!disabled"] if self.positions is not None else ["disabled"])

    def _auto_step(self):
        """Decides what Auto should do next, called once from
        on_auto_clicked to kick the sequence off and again from the tail
        of _finish_relax/_finish_inflate every time a step it started
        actually finishes -- a no-op whenever Auto isn't active, so a
        plain manual button click never triggers any of this.

        - Level 0, not yet converged: (re)try Relax.
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
        - Current level NOT converged (below or at MAX_LEVEL): (re)try
          Inflate -- "if inflation doesn't reach convergence, it keeps
          trying at the same level", per an explicit user request,
          bounded by AUTO_MAX_RETRIES_PER_LEVEL (_auto_try) so a mesh
          that can genuinely never converge doesn't retry forever with
          no way to notice."""
        if not self._auto_active:
            return
        if self._auto_retry_level != self.subdivision_level:
            self._auto_retry_level = self.subdivision_level
            self._auto_retry_count = 0
        if self.subdivision_level == 0:
            if not self.last_stats.get("converged"):
                self._auto_try(self.on_relax_clicked)
            return
        if self.last_stats.get("converged"):
            if self.subdivision_level < MAX_LEVEL:
                self.on_subdivide_clicked()
                self._auto_step()
            else:
                self._auto_active = False
                self._update_auto_button()
                self._set_status(f"Auto: reached Level {MAX_LEVEL} and converged.", "success")
        else:
            self._auto_try(self.on_inflate_clicked)

    def _auto_try(self, action):
        """Runs `action` (on_relax_clicked or on_inflate_clicked) as
        Auto's next attempt at the CURRENT level, unless
        AUTO_MAX_RETRIES_PER_LEVEL has already been spent there -- see
        its own comment for why some bound has to exist."""
        if self._auto_retry_count >= AUTO_MAX_RETRIES_PER_LEVEL:
            self._auto_active = False
            self._update_auto_button()
            self._set_status(
                f"Auto: Level {self.subdivision_level} still hasn't converged after "
                f"{AUTO_MAX_RETRIES_PER_LEVEL} attempts -- stopping the automatic sequence "
                f"(Inflate is still available to keep trying by hand).", "warn")
            return
        self._auto_retry_count += 1
        action()

    def _run_chunked_relax_stream(self, step_fn, target_steps, stop_event, on_progress, on_finished):
        """Shared driver behind _run_inflate_stream and _run_relax_stream:
        calls `step_fn(chunk, stop_event) -> result` (result's own shape:
        (positions, nfev, max_stretch_pct, rms_stretch_pct, optimality,
        converged), same for relax_once and relax_initial_configuration)
        in a growing sequence of chunks (5, 10, 20, ..., capped at
        INFLATE_CHUNK_MAX) in a background thread, pushing a "progress"
        message to the queue after every chunk so the main thread can
        update the iteration counter/plot incrementally instead of
        jumping straight from the start count to the end one. Tk isn't
        thread-safe, so the worker only ever pushes to the queue; the
        main thread (via the scheduled poll below) is the only one that
        touches Tk widgets."""
        q = queue.Queue()

        def worker():
            completed = 0
            chunk = INFLATE_CHUNK_START
            try:
                while True:
                    this_chunk = max(1, chunk if target_steps is None
                                      else min(chunk, target_steps - completed))
                    result = step_fn(this_chunk, stop_event)
                    nfev, converged = result[1], result[5]
                    stopped = stop_event is not None and stop_event.is_set()

                    completed += nfev
                    q.put(("progress", result))
                    reached_target = target_steps is not None and completed >= target_steps
                    safety_cap_hit = target_steps is None and completed >= INFLATE_SAFETY_STEP_CAP
                    if converged or stopped or reached_target or safety_cap_hit:
                        break
                    chunk = min(chunk * 2, INFLATE_CHUNK_MAX)
                q.put(("final", None))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "progress":
                        on_progress(payload)
                    elif kind == "final":
                        on_finished()
                        return
                    elif kind == "error":
                        self.progress.stop()
                        self.progress.pack_forget()
                        self._set_controls_enabled(True)
                        self._set_status(f"Failed: {payload}", "error")
                        self._abort_auto()  # nothing left to call _auto_step from otherwise
                        return
            except queue.Empty:
                pass
            self.root.after(80, poll)

        self.root.after(80, poll)

    def _run_inflate_stream(self, pressure, target_steps, stop_event):
        faces, edge_length = self.faces, self.edge_length
        gtol = self._current_gtol
        rng = np.random.default_rng()
        state = {"positions": self.positions}

        def step_fn(chunk, stop_event):
            result = relax_once(state["positions"], faces, edge_length, pressure,
                                 PLANARITY_WEIGHT, max_nfev=chunk, stop_event=stop_event,
                                 gtol=gtol, rng=rng)
            state["positions"] = result[0]
            return result

        self._run_chunked_relax_stream(step_fn, target_steps, stop_event,
                                        self._apply_inflate_progress, self._finish_inflate)

    def _apply_inflate_progress(self, result):
        positions, nfev, max_stretch, rms_stretch, optimality, converged = result
        self.positions = positions
        self.iteration_count += nfev
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged,
                            "gtol": self._current_gtol,
                            "target_rms_pct": self._current_target_rms_pct}
        self._record_level_history()
        self._set_status(f"Inflating at level {self.subdivision_level}... "
                          f"{self.iteration_count} steps so far "
                          f"(edges stretched up to {max_stretch:.2f}%).", "info")
        self.draw()

    def _finish_inflate(self):
        self.progress.stop()
        self.progress.pack_forget()
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
                f"(RMS {rms_stretch:.2f}%).", "warn")
        elif converged:
            self._set_status(
                f"Converged after {self.iteration_count} steps at level "
                f"{self.subdivision_level}: edges stretched up to {max_stretch:.2f}% from rest "
                f"length (RMS {rms_stretch:.2f}%).", "success")
        else:
            self._set_status(
                f"Inflated ({self.iteration_count} steps at level {self.subdivision_level}, "
                f"step cap reached): edges stretched up to {max_stretch:.2f}% from rest length "
                f"(RMS {rms_stretch:.2f}%).",
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
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        self._set_status("Relaxing random start into a well-separated shape...", "info")
        self._run_relax_stream(self.stop_event)

    def _run_relax_stream(self, stop_event):
        faces, edge_length = self.faces, self.edge_length
        gtol = self._current_gtol
        rng = np.random.default_rng()
        state = {"positions": self.positions}

        def step_fn(chunk, stop_event):
            result = relax_initial_configuration(state["positions"], faces, edge_length,
                                                  max_nfev=chunk, stop_event=stop_event,
                                                  gtol=gtol, rng=rng)
            state["positions"] = result[0]
            return result

        self._run_chunked_relax_stream(step_fn, None, stop_event,
                                        self._apply_relax_progress, self._finish_relax)

    def _apply_relax_progress(self, result):
        positions, nfev, max_stretch, rms_stretch, optimality, converged = result
        self.positions = positions
        self.iteration_count += nfev
        self.last_stats = {"max_stretch_pct": max_stretch, "rms_stretch_pct": rms_stretch,
                            "optimality": optimality, "converged": converged,
                            "gtol": self._current_gtol}
        self._record_level_history()
        self._set_status(f"Relaxing... {self.iteration_count} steps so far "
                          f"(edges stretched up to {max_stretch:.2f}%).", "info")
        self.draw()

    def _finish_relax(self):
        self.progress.stop()
        self.progress.pack_forget()
        was_stopped = self.stop_event is not None and self.stop_event.is_set()
        converged = self.last_stats.get("converged")
        max_stretch = self.last_stats.get("max_stretch_pct", 0.0)
        rms_stretch = self.last_stats.get("rms_stretch_pct", 0.0)
        self._record_level_history()
        if was_stopped:
            self._set_status(
                f"Stopped ({self.iteration_count} relax steps): edges stretched up to "
                f"{max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%).", "warn")
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
            # Level 1's own "Target RMS stretch" spinner -- same as
            # _subdivide_step's own (see its comment).
            self._current_target_rms_pct = self.target_rms_vars[1].get()
            self.last_stats = self._compute_stretch_stats()
            self._record_level_history()
            self._set_status(
                f"Relaxed (edges stretched up to {max_stretch:.2f}% from rest length, RMS "
                f"{rms_stretch:.2f}%). Promoted to Level 1 -- press Inflate to continue.", "info")
        else:
            self._set_status(
                f"Relaxed ({self.iteration_count} steps, step cap reached): edges stretched up "
                f"to {max_stretch:.2f}% from rest length (RMS {rms_stretch:.2f}%). Press Relax "
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

    def _run_background(self, fn, args, on_done):
        """Run fn(*args) in a background thread and call on_done(result)
        on the main thread once it finishes -- used for on_inflate_clicked's
        pressure calibration (estimate_pressure_for_target_stretch), which
        can take a moment. Tk isn't thread-safe, so the worker only ever
        pushes to a queue; the main thread (via the scheduled poll below)
        is the only one that touches Tk widgets. (Inflate/Relax each have
        their own streaming variant, _run_inflate_stream/_run_relax_stream,
        since they report incremental progress rather than one final
        result.)"""
        self._set_controls_enabled(False)
        self.progress.pack(side=tk.LEFT, padx=(10, 0))
        self.progress.start(12)
        q = queue.Queue()

        def worker():
            try:
                q.put(("done", fn(*args)))
            except Exception as e:  # surface a solver crash instead of hanging forever
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            self.progress.stop()
            self.progress.pack_forget()
            self._set_controls_enabled(True)
            if kind == "error":
                self._set_status(f"Failed: {payload}", "error")
                self._abort_auto()  # nothing left to call _auto_step from otherwise
                return
            on_done(payload)

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
        level's individual fine triangles -- with a faint subdivision
        overlay at the CURRENT subdivision level (see mesh_levels'
        docstring: level L's overlay is subdivide_polygon's own
        resolution 2**(L-1), the absolute-resolution equivalent of this
        app's own incremental fan-then-quarter scheme), as a 2D preview of
        the mesh actually being solved."""
        self.ax2d.cla()
        self._style_2d_axis(self.ax2d, theme)
        overlay_level = self.subdivision_level
        faces = self.base_faces
        all_pts = []
        for face_idx in sorted(self.target_layout):
            face = faces[face_idx]
            color = self.colors[face_idx % len(self.colors)]
            placed = self.target_layout[face_idx]
            self.ax2d.add_patch(Polygon(placed, closed=True, facecolor=color,
                                         edgecolor="k", alpha=0.9))
            if overlay_level > 0:
                sub_points, sub_triangles = subdivide_polygon(
                    len(face), placed, 2 ** (overlay_level - 1))
                segments = []
                for i, j, k in sub_triangles:
                    segments += [(sub_points[i], sub_points[j]),
                                 (sub_points[j], sub_points[k]),
                                 (sub_points[k], sub_points[i])]
                self.ax2d.add_collection(LineCollection(
                    segments, colors="k", linewidths=SUBDIVISION_EDGE_WIDTH,
                    alpha=SUBDIVISION_EDGE_ALPHA, zorder=3))
            all_pts.extend(placed)

        all_pts = np.array(all_pts)
        lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
        pad = 0.6
        # self.net_zoom (1.0 = unzoomed, matching the original fixed
        # lo-pad..hi+pad framing exactly) shrinks/grows this same
        # half-extent around the layout's own center -- see
        # _on_net_scroll, the Net panel's own analogue of every "Level N"
        # panel's self.level_zoom.
        center = (lo + hi) / 2
        half_range = ((hi - lo) / 2 + pad) / self.net_zoom
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

    def draw(self):
        """Redraws the Net panel plus every "Level N" panel: level ==
        self.subdivision_level draws LIVE from current state; a level in
        self.level_snapshots (already subdivided past, or -- for Level
        0 -- promoted away from by a converged Relax) draws its frozen
        state; any other level hasn't been reached yet and draws empty
        (see _draw_level_panel). Every level panel shares ONE camera
        orientation (self.level_rotation, see __init__'s Design notes)
        -- nothing further to sync here, since _draw_level_panel already
        renders every panel from that same shared state on every call."""
        theme = self._apply_plot_theme()
        self._draw_target_faces(theme)
        for level in self.level_plotters:
            if level == self.subdivision_level:
                self._draw_level_panel(level, self.faces, self.positions, self.face_of_fine)
            elif level in self.level_snapshots:
                snap = self.level_snapshots[level]
                self._draw_level_panel(level, snap["faces"], snap["positions"],
                                        snap["face_of_fine"])
            else:
                self._draw_level_panel(level, None, None, None)
        self._draw_idle_all()


def main():
    root = tk.Tk()
    InflatePolyhedronApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
