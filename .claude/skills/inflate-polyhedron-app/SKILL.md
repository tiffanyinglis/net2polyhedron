---
name: inflate-polyhedron-app
description: Architecture and hard-won debugging history for `inflate_polyhedron_app` (`src/apps/inflate_polyhedron_app/app.py`) and `src/utils/inflate_polyhedron/stretchy_mesh.py` — the stretchy (non-rigid) mesh solver/viewer, the most algorithmically involved part of the project. Load before making non-trivial changes to this app, `stretchy_mesh.py`, `mesh_levels.py`, `hull_to_spec.py`, or `stretchy_net_layout.py`.
---

See the `net-fold-project` skill for the untouchable-files list, directory
layout, and testing conventions shared across this whole repo — this file
covers only `inflate_polyhedron_app`/`stretchy_mesh.py` specifics.
`reference/debugging-history.md` in this skill's folder has the detailed
incident-by-incident narratives behind the rules below — read it only when
you need the full reasoning, not for ordinary changes.

## No hacky terms in the physics without explicit permission

`stretchy_mesh.py`'s force model has repeatedly grown, then had removed, a
term that papers over a symptom instead of fixing its actual cause: a
target/reference-volume pressure term (removed — it compounded stretch
across repeated Subdivide/Inflate cycles) and a per-edge soft stretch
limit (removed once `estimate_pressure_for_target_stretch` made
calibrating an appropriate pressure per net the real fix). **Do not add a
volume term, a target/reference term, a stretch clamp, or any other term
to the force model that isn't a direct, literal physical quantity (a real
spring force, a real pressure force) without the user explicitly asking
first** — if a pressure/stretch/convergence problem shows up, explain the
actual cause and propose a fix rather than silently patching the symptom.
See `reference/debugging-history.md` for the full incidents.

## Stretchy meshes (`src/utils/inflate_polyhedron/stretchy_mesh.py`)

For nets that **cannot** be realized with rigid, flat faces — most
sharply, two faces sharing more than one edge (if two flat polygons share
≥3 non-collinear points, they must lie in one plane — a genuine geometric
impossibility, not a data-structure limitation). Genuinely different data
model/solver from any rigid pipeline, not an extension of one.

### Vertex-loop format (`data/input/stretchy_nets/*.json`)

```json
{"name": "...", "faces": [[0,1,2,3,4], [3,2,1,0,5], [0,4,3,5]]}
```

Faces are vertex-id loops (indexed face set) — shared vertices ARE the
adjacency, so a face pair sharing several edges needs no special-casing.
No root, no hinge tree, no fold angles.

**Winding**: every face loop must go CCW as seen from outside the
finished solid (or, for a deliberately open net, outside whichever side
was chosen as "outside" — nothing else records that choice). For every
edge shared by two faces, one face's loop contains it as `v -> w` and the
other's as `w -> v` — never the same direction twice. `load_stretchy_mesh`
only rejects a directed edge that appears **more than once**. An edge with
no reverse partner is a valid, free **boundary** edge (the mesh need not
be a closed 2-manifold — this used to be stricter; loosened once an open,
hand-designed net needed to inflate and nothing in `relax_once` actually
requires a closed volume). That check is purely combinatorial; see
"Orientation consistency" below for the geometric half.

### Starting configuration: random start + spring relax

Replaced an earlier `solve_wireframe` (random-restart `least_squares`
search with an on-disk cache) entirely — deleted along with
`stretchy_cache.py`/`checksums.py`/`build_cache.py`. Now:

1. **`random_initial_positions(faces, spread, seed=0)`** — independent
   uniform-random point per vertex in `[-spread/2, spread/2]^3`. Not a
   meaningful embedding — just noise for the next step to pull into shape.
2. **`relax_initial_configuration(positions, faces, edge_length, ...)`**
   — pulls that noise into a well-separated 3D shape using PURE spring
   forces (`_spring_only_force`, no pressure/planarity). Faces can cross;
   result can land anywhere in space/scale — any view must derive its own
   camera framing from the actual bounding box.
   - The mesh must be **triangulated first** (a plain wireframe is a
     flexible mechanism under springs alone, like an unbraced rectangular
     frame) — `mesh_levels.subdivide_once` at level 0 adds the needed
     diagonal bracing, which is why Level 0 and Level 1 share the exact
     same topology.
   - **Orientation is not guaranteed consistent.** A pure spring force
     doesn't care which way a normal points. A UNIFORMLY inverted result
     is free to fix (reflect every vertex through the mesh centroid — an
     isometry that flips every face's outward sign at once). A genuinely
     MIXED result (some faces each way, seen ~half the time for an
     octahedron across seeds) is returned as-is, by explicit design —
     `relax_once`'s pressure model is trusted to work it out.

`_orientation_signs`/`_is_orientation_consistent` are general
orientation-checking utilities, independent of any particular solver.

### Fabric subdivision (mostly removed)

`subdivide_mesh`/`solve_fabric_mesh` and
`generate_subdivided_stretchy_nets.py` are gone (with `solve_wireframe`).
What's left: `mesh_subdivide.load_fabric_spec(path)` still reads a legacy
fabric file's `"coarse_faces"`/`"resolution"`/`"face_of_fine"` fields —
`on_select_net` uses only its `coarse_faces` as base faces, ignoring any
pre-baked fine mesh. No shipped net currently has this field.

### The app: random start → relax → subdivide → inflate, per level

Every net starts as "Level 0" (random start on its fan-triangulated
topology); "Relax" promotes it to Level 1's starting shape; "Subdivide"
(`mesh_levels.subdivide_once`) refines one level at a time up to
`MAX_LEVEL = 3`, carrying forward whatever inflation was already done. A
legacy fabric file with baked-in `coarse_faces` loads into this same flow
using those as base faces.

1. **Level 0 (random start)**: `on_select_net` fan-triangulates the base
   faces and calls `random_initial_positions` — cheap enough to run
   synchronously.
2. **"Relax" (Level 0 only)**: runs `relax_initial_configuration` to
   convergence, streamed in growing chunks (see "Live progress" below).
   On convergence it's promoted straight to Level 1 (pure relabeling —
   Level 0 and 1 share the same mesh). A mixed-orientation result is not
   retried; Inflate is expected to sort it out.
3. **Subdivide**: one press refines the current mesh by one level (a
   "triforce" quarter of every triangle, up to `MAX_LEVEL`). New
   positions interpolate from the current mesh (preserving inflated
   detail); new rest lengths come from the flat unit-edge reference
   geometry, independent of current 3D positions, so repeated
   inflate-then-subdivide converges toward one consistent target shape.

Pressure/Inflate controls work at any level. `CONVERGENCE_GTOL = 1e-4` is
deliberately loose — many meshes visibly settle well before crossing a
strict force tolerance.

**UI layout notes**: net picker defaults to `cube.json`
(`DEFAULT_NET_BASENAME`) or first alphabetically. "Choose a net"/"Target
RMS stretch"/"Tolerance" are tiled horizontally in one row (an untouchable
`app.py` exception, done to save vertical space against the debug-mode
row below it). The Net panel (matplotlib, left side) has its own
scroll-to-zoom (`self.net_zoom`) independent of each "Level N" panel's
own PyVista zoom. `self.base_faces` (level-0 mesh, fixed per net) backs
the Net panel at all levels; `self.face_of_fine` maps each current fine
face back to its base face for consistent per-base-face coloring.

### The "Inflate" controls

Top to bottom: Target RMS stretch spinner → iterate-mode radio buttons →
Inflate/Stop button. There is no standalone "Auto pressure" button, no
Pressure readout, and no Save button any more (see
`reference/debugging-history.md` for why each was removed).

- **Pressure is not user-editable.** `self.pressure_value` is set fresh
  every Inflate click by the calibration phase below; it's only shown
  per-level in the Convergence History table.
- **"Target RMS stretch" spinner** (`self.target_rms_var`, %, default
  10.0) feeds calibration's `target_rms_pct`. Per-level defaults
  (`LEVEL_DEFAULT_TARGET_RMS_PCT = {1: 30.0, 2: 20.0, 3: 10.0}`) are
  applied automatically the moment a level is first reached (still
  user-editable after) — tapered down because a finer mesh needs less
  *relative* stretch per edge to trace the same curvature, keeping the
  actual target 3D shape consistent across levels.
- **`on_inflate_clicked` calibrates pressure before inflating**: phase 1
  runs `estimate_pressure_for_target_stretch` in the background to find a
  pressure landing near the target RMS stretch (discarding its own trial
  positions); phase 2 feeds just that pressure number into the normal
  streamed inflate. Targets RMS (not max) stretch since an irregular or
  subdivided mesh stretches unevenly. Calibration starts from an
  area-based geometric estimate (`pressure * total_rest_area` lands in a
  tight band across all 5 Platonic solids even though raw pressure
  varies 12x), then refines by relaxing at that pressure and
  bracket-then-bisecting toward the target once both an under- and an
  over-target pressure are known (needed because a single
  rescale-by-ratio can oscillate forever between the same two pressures
  on a topology whose stretch response is sharply nonlinear — see
  `reference/debugging-history.md`).
- **`stretchy_mesh._relax_force`**: a genuine small-step mechanical force
  balance (Hooke's-law edge springs + `pressure * area * outward_normal`
  per face), not a Newton-style solver — a re-linearizing solver can land
  on a spurious equilibrium a genuine small-step walk never would.
  Explicit step size (`_explicit_relax_loop`) scales with the mesh's own
  current rest-edge-length scale so a fixed relative step stays equally
  safe/fast across subdivision levels (`STEP_MAX_MULTIPLIER = 0.2`).
  `STALL_WINDOW = 2000` steps of a flat `max_stretch_pct` also counts as
  converged, alongside the gtol force check.
- **Rigid-motion removal every step** (`_remove_rigid_motion`): a
  free-floating mesh has no fixed orientation of its own; an OPEN net's
  pressure forces can accumulate genuine net torque (unlike a closed
  mesh's, which cancel by a hydrostatic identity) and visibly spin in
  place. Fixed via Kabsch/orthogonal-Procrustes best-fit rigid alignment
  back to the previous step's frame after every update — an isometry, so
  it never changes stretch/convergence.
- **Escaping a genuine local minimum: the "kick"** (`rng` parameter on
  the relax functions, `KICK_WINDOW/KICK_STALL_RATIO/KICK_MAGNITUDE_
  FRACTION`): when `max_force` hasn't dropped enough over `KICK_WINDOW`
  steps, every vertex gets a small Gaussian nudge weighted by its own
  current force relative to the worst one. Opt-in via `rng=None` default
  (deterministic, matches existing tests) — the app passes a real
  Generator. Does not fully rescue every pathological case (a genuinely
  weakly-braced isolated vertex can still fail to converge) — see
  `reference/debugging-history.md`.
- **No orientation/fold check on the interactive Inflate loop** — an
  earlier reject-on-fold check false-positived on non-convex/open nets
  and was removed entirely at the user's request; `relax_once`'s own
  small steps are what keeps results sane now.
- **Radio buttons**: "Iterate for N steps" (`max_nfev=N`) vs "Iterate
  until convergence" (default; force below tolerance OR stretch stalled).
- **Live progress**: `_run_inflate_stream` calls `relax_once` in a
  growing sequence of chunks (`INFLATE_CHUNK_START=5` doubling to
  `INFLATE_CHUNK_MAX=200`), redrawing after each. `INFLATE_SAFETY_
  STEP_CAP = 20000` hard-stops "until convergence" mode.
- **Tolerance spinner** (`self.tolerance_var`, default `1e-3`, a
  `tk.StringVar` not `DoubleVar` — ttk's Spinbox `format` only reformats
  values from its own arrows) sets the actual `gtol` for
  Relax/Inflate/calibration, captured once per click into
  `self._current_gtol` and recorded per level-history row.
- **Convergence History table**: shows the algorithm's own `converged`
  flag (not a fresh `optimality < gtol` recheck, since a stall-converged
  run can still show `optimality >= gtol`) — appends `" (stalled)"` in
  that case. Level 0's row has no pressure/target (pure springs, shows
  "n/a").
- **Won't re-run once converged** — the level's action button reads
  "Subdivide"/"DONE!" and a click is refused; re-armed by changing the
  target RMS or loading a new net. "Stop" sets a `threading.Event`
  checked before each step.

### "Auto" button

Runs the whole pipeline unattended from wherever it is (Relax → repeated
Inflate/Subdivide → Level `MAX_LEVEL`), driven by the same click handlers
a manual run would use. Retries an unconverged level up to
`AUTO_MAX_RETRIES_PER_LEVEL = 10` before giving up and reporting so.
Stays enabled (as "Stop Auto") through the run despite the blanket
control-disable everything else gets. See `reference/debugging-history.md`
for the state-machine details and verification.

### Debug-mode-only diagnostics

Toggled with the "d" key; the ONLY behavioral difference from release
mode is whether "Iterate for N steps" is offered — see
`reference/debugging-history.md` for the full list of what used to differ
and was unified away.

- **"Validate Mesh"**: reports two things on the currently-loaded (not
  raw-file) mesh — a purely combinatorial "structural winding
  consistency" check (same duplicate-directed-edge rule as
  `load_stretchy_mesh`, re-run post-subdivision; this is authoritative for
  pass/fail) and a geometric, non-gating "current embedding: inward vs.
  outward" note (globally inside-out is undetectable from `faces` alone,
  only from where vertices currently sit).
- **"Show normals"**: draws each triangle's outward normal, half an edge
  long relative to current (not rest) edge length.

### Rendering

Every "Level N" panel renders via PyVista/VTK (off-screen, blitted as a
`PhotoImage` onto a plain `tk.Label` — keeps the app on one toolkit); only
"Net" is still matplotlib. Needed because a mid-solve mesh is routinely
self-intersecting/non-convex, which neither mplot3d's painter's-algorithm
sort nor the old convex-only `_CullableFace` could draw correctly.
Orthographic (parallel) projection to match fixed-axis framing. All level
panels share one camera angle (`self.level_azim`/`self.level_elev`) — a
drag on any panel re-renders all of them from the same updated state. See
`reference/debugging-history.md` for VTK-specific gotchas (title
centering, aspect-ratio correction).

**Left panel is a real connected net**: `on_select_net` precomputes
`self.target_layout` once via `stretchy_net_layout.build_stretchy_net_layout`
— a BFS over faces sharing an edge, using `polygon_geom.attach_polygon`
for each newly-discovered face. A face pair sharing more than one edge
just means BFS ignores the extra edges for placement.

## Conventions specific to the stretchy pipeline

- All polygon edges have length 1 (`stretchy_mesh.EDGE_LENGTH`,
  `polygon_geom.EDGE_LENGTH`) since nets are hand-authored combinatorics
  with no coordinates of their own. No stretch cap (see "No hacky terms"
  above).
- Polygons are CCW as seen from outside the solid — shared edge is
  `v -> w` in one face's loop, `w -> v` in the other's.
- `stretchy_mesh.py` has no `if __name__ == "__main__"` demo block — add
  new ad hoc verification as a real test in `tests/`, not a script block.
