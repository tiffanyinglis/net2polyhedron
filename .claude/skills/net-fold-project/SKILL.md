---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (net_fold_utils library, .json/.fold formats, the fold solver, the stretchy-mesh solver, the Tkinter apps, tests). Load before making non-trivial changes to this repo instead of re-deriving the pipeline by re-reading every file.
---

# Polyhedron net-folding project

Takes a description of a polyhedron's net (which faces exist, how they're
hinged flat, and which edges only meet once folded) and computes the exact
3D fold: a 2D face layout plus a per-hinge fold angle. Four Tkinter entry
points share pieces of this:

- `polygon_fold_app.py` — pick a **rigid** net and drag a slider from flat
  (0%) to fully folded (100%).
- `polyhedral_net_app.py` — same rigid pipeline, but shows the flat 2D net
  and the fully folded 3D solid side by side at once (the 3D panel is
  mouse-rotatable via matplotlib's own 3D navigation). Also handles **open**
  nets (some faces deliberately omitted — see "Open nets" below), which
  `polygon_fold_app.py` can load too but was the app originally used to
  validate that support in.
- `polygon_subdivide.py` — unrelated to folding: a 2D-only demo that splits
  a triangle/square/.../8-gon into a fine triangular mesh (see "Polygon
  subdivision demo" below).
- `stretchy_polyhedron_init.py` — a DIFFERENT solver entirely, for nets that
  can't stay rigid and flat at all (e.g. a face sharing more than one edge
  with a neighbor). See "Stretchy meshes" below — this is the most
  algorithmically involved part of the project.

## Directory layout

- `polygon_fold_app.py` — the animated-slider Tkinter app (entry point, class `PolygonFoldApp`)
- `polyhedral_net_app.py` — the side-by-side flat/folded Tkinter app (entry point, class `PolyhedralNetApp`); imports `STATUS_COLORS`/`PLOT_THEME`/`NETS_DIR`/`DISABLED_SUFFIX`/`COMPUTE_TOOLTIP` from `polygon_fold_app.py` rather than redefining them, but otherwise deliberately duplicates the net-picker/compute-worker Tk wiring rather than factoring out a shared base class, so each entry point stays a self-contained, independently readable script
- `polygon_subdivide.py` — 2D-only fine-triangle-mesh demo (see below); shares only `PLOT_THEME` with the fold apps
- `stretchy_polyhedron_init.py` — the stretchy-mesh viewer (see below); imports `STATUS_COLORS`/`PLOT_THEME`/`FACE_COLORS`/`DISABLED_SUFFIX` from `polygon_fold_app.py`, everything else is its own pipeline
- `tooltip.py` — small generic hover-tooltip helper for Tkinter (not net-fold-specific)
- `net_fold_utils/` — the reusable library (see below), including `mesh_subdivide.py` — builds a fine "fabric" triangulation of a stretchy net (see "Fabric subdivision" below)
- `subdivision_utils/` — the (separate, simpler) fine-mesh library `polygon_subdivide.py` (and now `net_fold_utils/mesh_subdivide.py`) uses
- `tools/generate_subdivided_stretchy_nets.py` — writes `stretchy_nets/<name>_res<resolution>.json` fine-triangulated variants of an existing stretchy net (see "Fabric subdivision" below)
- `nets/*.json` — **human-authored** RIGID net specs; the only files meant to be hand-edited (for that pipeline)
- `fold_cache/*.fold` — **computed** cache, one per rigid `.json`, kept in a separate directory from `nets/` on purpose (disposable output vs. source input)
- `build_fold_cache.py` — top-level script: precompute/refresh all rigid caches, prints per-net progress
- `stretchy_nets/*.json` — **human-authored** STRETCHY net specs (vertex-loop format, see below) — a parallel, differently-shaped set of input files, not interchangeable with `nets/*.json`
- `stretchy_cache/*.json` — **computed** cache for stretchy nets, mirrors `fold_cache/` vs `nets/`
- `build_stretchy_cache.py` — top-level script: precompute/refresh all stretchy caches
- `tools/generate_platonic_nets.py` — (re)generates `nets/*.json` for the 5 Platonic solids + the truncated icosahedron from canonical 3D coordinates (`net_fold_utils/solid_coords.py`)
- `tools/generate_stretchy_platonic_nets.py` — (re)generates `stretchy_nets/*.json` for the 5 Platonic solids from the *same* coordinates, via `hull_to_spec.polyhedron_from_vertices`'s CCW face loops directly (no spanning tree needed — vertex-loop format has no hinge/root concept)
- `tools/generate_open_dodecahedron_nets.py` — generates the two open-net examples (`nets/half_dodecahedron.json`, `nets/dodecahedron_minus_one.json`)
- `tests/` — pytest suite (see Testing below)
- `run_tests.py` — top-level script: `python run_tests.py [pytest args...]`
- `pytest.ini` — sets `pythonpath = .` so tests can `import net_fold_utils` regardless of cwd
- `requirements.txt` — numpy, scipy, networkx, matplotlib, sv-ttk, (dev) pytest
- `README.md` — user-facing usage doc (install, run the app, write a `.json` net, the cache, tests)

## The `.json` format (human-writable input, RIGID pipeline)

Full grammar lives in `net_fold_utils/polyhedron_spec.py`'s docstring. Shape:

```json
{
  "name": "...",
  "faces": [{"id": 0, "sides": 4, "isRoot": true}, {"id": 1, "sides": 4}, ...],
  "edges": {
    "net": [[0, 1], ...],
    "extra": [[1, 2], ...]
  }
}
```

`faces` gives each face's number of sides (k for a regular k-gon), with an
explicit `id` per face -- checked against declaration order on load -- so
faces stay easy to number and cross-reference even in a long list. The
face the flat net is built outward from is marked `isRoot: true` (defaults
to face 0 if no face is marked; more than one marked face is an error).
`edges.net` is the (f1, f2) hinge edges forming the flat net; must be a
spanning tree over every **non-omitted** face (see "Open nets" below —
`len(net) == len(faces) - len(omitted) - 1`). `edges.extra` is the (f1, f2)
edges that only meet once folded; these pin down the fold angles.

No coordinates or angles are ever hand-written — both are derived.

### Open nets

A face can be marked `"omit": true` — it's never built into 2D/3D geometry
or physically folded, but its combinatorics still matter: `edges.hidden`
lists every edge touching an omitted face (needed so `combinatorics.EdgeMap`
sees the *complete* graph and gives the real, non-omitted faces their
correct polygon-edge index — Whitney's theorem needs the full graph, not a
hole-punched one) but is never used as a hinge or a fold-closure constraint,
since an omitted face has no 3D position to hinge from or close against.
`nets/half_dodecahedron.json` and `nets/dodecahedron_minus_one.json` are
worked examples (generated by `tools/generate_open_dodecahedron_nets.py`
from the same dodecahedron coordinates the closed `nets/dodecahedron.json`
uses, just with some faces marked omitted instead of remapped away).

An open net's fold is generally an **open, non-convex** shape even at
t=1 — `net_fold_utils.is_closed_solid(verts3d)` checks this directly and
purely geometrically (does every folded edge match exactly one other
face's edge at the same two 3D points?), with no dependency on the
`omit`/`hidden` JSON fields, so it works for legacy `.txt` nets too. Both
apps check it before applying `_CullableFace` backface culling (see
below), which is only valid for a closed convex solid.

## Pipeline (`net_fold_utils/net_io.py: load_polyhedron_net`)

1. `polyhedron_spec.py` parses `faces`/`edges.net`/`edges.extra`/`edges.hidden`/`omit` from the JSON.
2. `combinatorics.py` (`EdgeMap`) turns the full edge list (net + extra +
   hidden) into a per-face edge-index map via a `networkx` planar embedding.
   By Whitney's theorem a 3-connected planar graph's embedding — hence the
   cyclic edge order around each face — is unique up to a global mirror, so
   edge indices never need to be given explicitly. This is also exactly why
   `EdgeMap` **cannot** represent a face pair sharing more than one edge:
   its graph is a plain `networkx.Graph`, so two faces glued along multiple
   edges collapse to a single graph edge and it raises "duplicate edge in
   the edge list" — this is the hard boundary between what the rigid
   pipeline can express and what needs a stretchy mesh instead (see below).
3. `net_layout.py` BFS-attaches regular polygons (`polygon_geom.py`) along
   `net` edges to build the flat 2D net, skipping any `omitted` faces
   (`Net.add_face` accepts an explicit `fid` so a face's original id is
   preserved even when omitted ids leave gaps in the numbering — needed
   for open nets, since `EdgeMap`'s indices are keyed on the *original*
   ids).
4. `fold_solver.py` numerically solves (scipy `least_squares`) for the
   hinge angle at every `net` edge such that every `extra` edge's two faces
   coincide in 3D at fold progress `t=1`. Performance-critical internals:
   - **Restart strategy**: tries a 17-point sweep of evenly-spaced,
     all-hinges-equal starting guesses first; the 40-random-restart
     fallback only fires if that sweep finds *no* valid solution at all —
     it's not used to search for additional branches once one is found.
   - **Known gotcha**: the same closure equations can have more than one
     root. The icosahedron net, for instance, also algebraically closes
     into a smaller, self-intersecting "collapsed" shape.
     `fold_solver._is_embeddable` rejects any solution where two
     non-adjacent vertices end up closer than one edge length (checked via
     `net_fold_core.distinct_vertices`), then the smallest-total-rotation
     surviving solution is chosen. (The stretchy-mesh solver hits this same
     class of problem in a much sharper form — see "Orientation
     consistency" below.)
   - **`jac_sparsity`**: each closure residual only actually depends on the
     hinge angles that are ancestors (root-path) of the two faces
     involved — a sibling branch's angle provably can't affect it, so this
     is an *exact* sparsity pattern, not an approximation
     (`_ancestor_hinge_indices` / `_closure_jac_sparsity`). Only applied
     when `n_hinges >= SPARSITY_MIN_HINGES` (15): below that, scipy's
     forced switch to the sparse-only iterative `lsmr` trust-region solver
     costs more than it saves (measured ~2x *slower* on the 7-hinge
     octahedron); above it, it's a real win (~1.7x on a 31-hinge net).
5. `net_fold_core.fold()` is the actual rotation engine — walks the hinge
   tree, rotating each subtree rigidly by its solved angle in one batched
   array operation (`precompute_subtree_map` derives the tree's shape once
   per solve rather than once per `fold()` call, since it never changes
   across the whole optimization). Works identically for both
   `.json`-derived and legacy `.txt` nets.

Perf history (32-face truncated icosahedron, 31 hinges): ~78s naive →
~72s (subtree precompute) → ~42s (+ `jac_sparsity`). Small nets (≤~15
hinges) were already sub-second and are unaffected by the `jac_sparsity`
change (explicitly gated off for them).

## Caching (`net_fold_utils/fold_cache.py`)

Solving is the slow part for bushy/large nets. A `.fold` cache file (in
`fold_cache/`, not `nets/`) mirrors the legacy explicit-coordinate format
(2D vertex positions per face + fold angle per hinge) plus a
`CHECKSUM sha256:...` of the source `.json`. `load_net()` transparently
reuses the cache if the checksum still matches, else re-solves and
rewrites it. Face ids in the cache's `FACES` block are allowed to be
non-contiguous (`0: ... \n 5: ... \n 6: ...`, strictly increasing but with
gaps) to support open nets' omitted faces — `parse_net_body` validates
strictly-increasing rather than exactly-sequential ids.

- `is_cached(net_path)` — read-only check, never mutates anything (safe to
  call just to decide how to render a net, e.g. in the app's net list).
- `_valid_cache_or_clear_stale` — when a cache's checksum no longer matches
  its source (the `.json` was edited), the stale `.fold` file is **deleted
  immediately**, before any re-solve is attempted. This means a failed
  re-solve never leaves a misleading stale cache behind; the net correctly
  falls back to "not computed" instead.
- `build_all(nets_dir, force=False, on_progress=None)` — computes/refreshes
  every net's cache; shared by `build_fold_cache.py` (CLI, prints progress)
  and the app's "Compute Folding Pattern" button (runs in a background
  thread, reports via a `queue.Queue` polled from the main thread — Tk
  widgets must only ever be touched from the main thread).
- Run `python build_fold_cache.py` after editing a `.json` file to warm the
  cache ahead of time (`--force` recomputes unconditionally); otherwise it
  happens lazily on first load.

## The apps (`polygon_fold_app.py`, `polyhedral_net_app.py`)

Tkinter UI on the `sv_ttk` theme (dark by default, light/dark toggle
button) with a `LabelFrame`-grouped layout: net picker + Compute button +
"Show Axes" checkbox (off by default) + theme button on top, the 3D plot
in the middle, the fold slider on the bottom (`polygon_fold_app.py`) or a
flat-net panel beside the 3D one (`polyhedral_net_app.py`).

- Nets without a valid `.fold` cache show a `(not computed)` suffix and are
  greyed out in the dropdown (`_style_disabled_items` — a best-effort
  reach into ttk's Tcl popdown-listbox internals, wrapped in try/except
  since it's not public API; the text suffix + a selection guard in
  `on_select_net` are what actually make them unselectable, independent of
  whether the grey styling succeeds).
- `_apply_plot_theme` recolors the figure/axes to match sv_ttk's theme
  (`PLOT_THEME`, mirroring sv_ttk's own `-bg` colors) and honors the "Show
  Axes" toggle; `draw()` calls it fresh every redraw since `ax.cla()`
  wipes all of it back to matplotlib's defaults each time.
- `draw()` centers the view on the shape's own bounding-box center (not
  its raw min/max) with one shared half-width across all three axes, so
  the shape sits in the middle of the cubic plot regardless of which
  direction the net layout happens to extend, and `set_box_aspect([1, 1,
  1])` isn't distorted by unequal per-axis ranges.
- `_draw_box_wireframe` manually draws all 12 edges of the bounding box
  when axes are shown: matplotlib's default 3D pane borders only draw the
  9 edges belonging to the 3 panes it renders for a fixed view angle, so
  the near vertical corner where the two visible walls meet is otherwise
  left undrawn.
- `_CullableFace` (in `polygon_fold_app.py`, also imported by
  `polyhedral_net_app.py`) fixes wrong-face-on-top glitches in the fully
  folded 3D view: mplot3d's `Poly3DCollection` only depth-sorts by one
  scalar per face (`do_3d_projection`'s `np.min(pzs)`), which a face at a
  grazing view angle can trick into rendering in front of something it
  should be behind. `_CullableFace` instead does exact backface culling
  (hides itself via `alpha=0` when `dot(face_normal, view_dir) <= 0`,
  recomputed from `self.axes.elev`/`azim` on every `do_3d_projection()`
  call -- which mplot3d makes on every redraw, including mid-drag during
  interactive rotation, so it stays correct as the user rotates). This is
  only mathematically valid for a face on a **closed convex** solid (a
  face's own orientation alone then determines whether the solid's far
  side hides it, and no two visible faces of a convex solid ever overlap
  in projection either, so nothing else needs sorting) -- never apply it
  to an open/non-convex net. `polygon_fold_app.py`'s `draw(t)` therefore
  only uses it when `t == 1.0` **and** `is_closed_solid(verts)` is true;
  for `t < 1`, or for an open net even at `t=1`, it falls back to a plain
  `Poly3DCollection`. `polyhedral_net_app.py`'s folded-solid panel always
  shows `t = 1.0` but likewise only culls when `is_closed_solid(verts)`.
  `net_fold_utils.face_normal()` computes each face's outward unit normal
  via the cross product of its first two edges -- verified (see
  `test_net_fold_core.py`) to be consistently outward-pointing for every
  face of every net in `nets/`, relying on the net's CCW winding
  convention (see Conventions below).
  **Gotcha**: `_CullableFace` applies visibility by writing straight to
  `_facecolor3d`/`_edgecolor3d`, not via `set_alpha()`/`set_edgecolor()`.
  `Poly3DCollection.set_alpha()` only refreshes `_facecolor3d` -- it
  updates a *different*, unused `_edgecolors` attribute for edges instead
  of `_edgecolor3d` (apparently a matplotlib inconsistency), so
  `do_3d_projection()`'s internals (which build the actually-rendered
  `_edgecolors2d` from `_edgecolor3d`) never see an edge-alpha change:
  the face fill correctly disappears but its black outline stays fully
  opaque, visibly bleeding through whatever's in front of it. Confirmed
  with an isolated repro (`get_edgecolor()` unchanged after `set_alpha(0)`
  + `do_3d_projection()`) before switching to writing `_edgecolor3d`
  directly, which does update what's actually drawn.
- "Compute Folding Pattern" runs `build_all` in a background thread with an
  indeterminate `ttk.Progressbar` and status-line updates; on completion,
  any failures are reported via `messagebox.showerror` listing each failed
  net and its error message (not just the status line).
- `_set_status(text, kind)` centralizes status-line coloring (`info` /
  `success` / `error` / `warn` → `STATUS_COLORS`).

## Polygon subdivision demo (`polygon_subdivide.py`, `subdivision_utils/`)

Unrelated to folding — a standalone 2D demo of splitting a regular n-gon
(triangle through 8-gon) into a fine triangular mesh, e.g. as a preview of
the mesh a later fabric/cloth simulation would use. Two-stage, both
hardcoded/closed-form (no runtime search):

1. `subdivision_utils.subdivisions.SUBDIVISIONS` — a hardcoded coarse split
   of each n-gon into a handful of triangles using only the polygon's own
   vertices plus its centroid (a diagonal split for the square; a centroid
   fan — n congruent isoceles triangles, exactly equilateral at n=6 — for
   n=5..8). Triangle counts were picked so sizes stay within ~1.5x of each
   other across all six n-gons.
2. `_subdivide_triangle` splits each coarse triangle into `resolution ** 2`
   small ones via a regular barycentric grid (the standard geodesic/
   icosphere-style refinement) — every small triangle is a scaled copy of
   the coarse one it sits inside. `subdivide()` merges the results from all
   coarse triangles into one mesh: points shared between adjacent coarse
   triangles land on bit-for-bit identical barycentric coordinates, so they
   merge into one shared point rather than staying duplicated.

`polygon_subdivide.py`'s layout pairs a small n-gon with a big one in each
column (3-gon over 8-gon, etc.) and gives every subplot the **same** fixed
axis range (sized to the largest n-gon) rather than each auto-scaling to
its own bounding box, so a unit edge length renders at the same pixel size
everywhere and triangle sizes are directly comparable by eye.

## Stretchy meshes (`net_fold_utils/stretchy_mesh.py`, `stretchy_polyhedron_init.py`)

For nets that **cannot** be realized with perfectly rigid, flat faces —
most sharply, two faces glued along more than one shared edge. If two flat
polygons share ≥3 non-collinear points, both must lie in the one plane
those points determine — there's no dihedral fold left to make them
distinct faces of a solid. `combinatorics.EdgeMap` can't even represent
this combinatorially (see "duplicate edge" above), so this is a genuinely
different data model and solver, not an extension of the rigid one.

### The vertex-loop format (`stretchy_nets/*.json`)

```json
{
  "name": "...",
  "faces": [[0, 1, 2, 3, 4], [3, 2, 1, 0, 5], [0, 4, 3, 5]]
}
```

Faces are vertex-id loops (the standard "indexed face set", like an .obj
file) — shared vertices *are* the adjacency, so a face pair sharing several
edges needs no special-casing. No root, no hinge tree, no fold angles: a
bendable mesh has no single "flat net" to speak of.

**Winding convention**: every face's vertex loop must go **counterclockwise
as seen from outside the finished solid**. Concretely: for every edge
shared by two faces, one face's loop contains it as `v -> w` and the
other's contains it as `w -> v` — never the same direction twice.
`load_stretchy_mesh` checks exactly that (every directed edge matched by
exactly one reverse partner) and raises a clear error naming the offending
edge(s) otherwise. That check alone can't catch everything, though — see
"Orientation consistency" below for the subtler, solve-time half of this.

### The algorithm (`solve_wireframe`)

No hinge-and-rotate step at all: everything is a single unified
least-squares point-cloud fit (`_residual`), run in two conceptual stages.

**Stage 1 — plain edge-length fit.** From a random 3D starting guess,
`least_squares` minimizes `|p_a - p_b| - edge_length` over every mesh edge.
The system is underdetermined (3 coords × N vertices, minus 6 for rigid-
body motion, usually well over the edge count), so many solutions exist —
which one you land on is essentially arbitrary and often tangled or
skewed, since edge-length fitting alone has no opinion about the mesh's
overall shape.

**Stage 2 — inflation** (`_inflate`): the actual fix, and the most
load-bearing piece of this module. Physically the same idea as stuffing a
plush toy or blowing up a balloon: a constant outward pressure, resisted
by the fabric's own tension, settles into a smooth, rounded, convex
equilibrium.

- `_mesh_volume(pts, faces, idx)` computes the mesh's enclosed volume via
  the divergence theorem: fan-triangulate every face from its own first
  vertex and sum each triangle's signed tetrahedron volume with the origin
  (`v0 . (v1 x v2) / 6`). Smooth and singularity-free everywhere (unlike,
  say, `1/distance`), which is what makes it usable as a least-squares term
  even from a poorly-conditioned starting point.
- `_sphere_bound_volume(faces, edge_length)` computes an optimistic,
  normally-unreachable target: the volume of the sphere with the same
  total surface area as the mesh's own faces (each assumed a regular
  polygon of `edge_length` sides). Scaled to the mesh's own size rather
  than an arbitrary huge constant — e.g. ~2.40 for the icosahedron (true
  volume ~2.18) — so it gives real, well-scaled "pressure" without wildly
  overshooting what the mesh could ever hold.
- The residual term is `weight * (target - actual_volume)`: since target
  is never reached, minimizing this always has a gradient pushing volume
  up, for as long as the edge-length term lets it.
- **Ramping matters.** Applying this at full strength, or from a cold
  random start, makes `least_squares` fail to converge at all (verified
  empirically) rather than inflate cleanly — the landscape is too
  ill-conditioned early on. `_inflate` instead walks `INFLATION_WEIGHTS =
  (0.1, 0.2, 0.4, 0.8, 1.5, 3.0)` in order, each step reseeded from the
  **previous accepted** step, and stops (keeping the last good result) the
  moment a step's edge-length error would exceed `STRETCH_CAP` (8%) —
  self-limiting for a topology that genuinely can't hold much pressure
  (`stretchy_nets/two_pentagons_and_a_square.json`) instead of stretching
  it into a mess.
- A final light planarity pass (`PLANARITY_WEIGHT`, via per-face best-fit-
  plane SVD residuals) tidies up individual faces at the same pressure
  without relaxing it back down — inflation already tends to leave faces
  close to flat on its own (a taut membrane wants to be locally flat
  wherever its edges allow), so this only has a little polishing left to
  do.

### Orientation consistency (why this needed real iteration to get right)

Plain edge-length fitting has no opinion about orientation, so a stage-1
result is often already self-intersecting — one face folded inside-out
relative to the rest (a sharper version of `fold_solver._is_embeddable`'s
"collapsed branch" problem in the rigid pipeline). `_orientation_signs`
detects this cheaply: for each face, the sign of `dot(face_normal,
face_centroid - mesh_centroid)`; a consistent embedding has every face
agree (all +1 or all -1 — an arbitrary global mirror choice that doesn't
matter either way), and `_is_orientation_consistent` just checks that.

Getting this to actually help took three iterations, each falsified by a
real counter-example before landing on the current design — worth knowing
before "improving" this further:

1. *Require stage-1 already consistent, before ever inflating.* Broke the
   dodecahedron: its stage-1 output is essentially **always** inconsistent
   (random edge-length fits for 20 vertices / 30 edges are just tangled),
   but `_inflate`'s very first pressure step reliably fixes it anyway —
   inflating *is* the untangling mechanism there. Requiring consistency
   up front threw away every candidate before inflation ever got a chance,
   and every attempt exhausted the retry budget and raised.
2. *Gate every ramp step on consistency, breaking at the first
   inconsistent one.* Broke the icosahedron: its ramp genuinely passes
   *through* a couple of inconsistent intermediate weights (0.1-0.4) before
   self-correcting at higher pressure (0.8 onward) — the opposite failure
   mode from the dodecahedron. Stopping early at step 1 meant it could
   never reach the weight where it actually recovers.
3. **Current design**: no per-step orientation gating inside `_inflate` at
   all (only `STRETCH_CAP` per step); instead `solve_wireframe` tries
   whole stage-1-through-polish attempts one at a time (`CANDIDATES_PER_ROUND`
   per round, escalating up to `MAX_ORIENTATION_ATTEMPTS` total) and keeps
   the **first** one whose *final* result is orientation-consistent. Since
   repeated successes land on essentially the same result once a mesh
   inflates at all, there's no benefit to comparing many successes against
   each other (an earlier version did, and it was pure wasted computation
   for slower meshes). If every attempt is exhausted with nothing
   consistent, it raises `ValueError` naming the winding convention and
   pointing at the worked example, rather than silently returning a
   self-intersecting mesh — `build_stretchy_cache.py`'s existing
   `except ValueError` failure-reporting path surfaces this per-net.

A separate, cheap guard catches what orientation-consistency can't:
`_min_pairwise_separation(pts) > MIN_SEPARATION_FRACTION * edge_length`
rejects a result where two *unrelated* (non-adjacent) vertices happen to
have collapsed onto each other — face-normal signs don't notice that on
their own, since `_mesh_volume`'s pressure term has no particular reason
to keep distinct vertices apart.

### Caching (`net_fold_utils/stretchy_cache.py`)

Mirrors `fold_cache.py`, but as plain JSON (positions + stats dict — no
hinge tree to write out) instead of the FACES/ROOT/FOLD text format.
`ALGORITHM_VERSION` (in `stretchy_mesh.py`) is folded into the cache key
(`stretchy_cache.source_checksum` = file hash + `"+algo{VERSION}"`) —
**bump it whenever `solve_wireframe`'s algorithm changes enough to produce
a different result for the same mesh**, e.g. adding the inflation stage.
Without this, an on-disk cache from a previous algorithm version would
keep being served forever, since its checksum only ever tracked the
*source* `.json`, not how it was solved. The cache always stores
`solve_wireframe(seed=0)`'s result (the one canonical answer);
`stretchy_polyhedron_init.py`'s "Recompute Wireframe" button deliberately
bypasses the cache (it wants a *different* one of the many valid
embeddings) and never overwrites it.

### Fabric subdivision (`net_fold_utils/mesh_subdivide.py`, `tools/generate_subdivided_stretchy_nets.py`)

Simulates a stretchy net's faces as fabric rather than (at most gently
bending) rigid-ish panels: every coarse face is split into a fine
triangular mesh — the same hardcoded per-n-gon coarse split
(`subdivision_utils.SUBDIVISIONS`) and barycentric refinement
(`subdivision_utils._subdivide_triangle`) `polygon_subdivide.py` uses to
preview a single polygon — applied to every face of a whole net at once,
with points on a shared coarse edge merged into one global vertex so the
result is a single connected mesh, not N disconnected per-face patches.

**This is a file-generation step, not an app feature.**
`tools/generate_subdivided_stretchy_nets.py` reads an existing
`stretchy_nets/<name>.json`, calls `subdivide_mesh(coarse_faces,
resolution)`, and writes the fine triangulation straight out as an
ordinary `stretchy_nets/<name>_res<resolution>.json` — a plain
vertex-loop mesh, no different in format from any other stretchy net.
(`SUBDIVISIONS_TO_GENERATE` at the top of that script is the editable
list of `(name, resolution)` pairs to produce; `stretchy_nets/cube_res4.json`
is the one generated so far.) Once written, it goes through
`build_stretchy_cache.py` / `stretchy_polyhedron_init.py`'s net picker
completely unmodified — there is no separate fabric mode or UI control
for this, it's just another `.json` in the directory.

**Known simplification: rest lengths are treated as uniform, even though
they aren't.** SUBDIVISIONS' coarse triangles aren't generally
equilateral (a pentagon's centroid fan has unit-length rim edges but
shorter spoke edges to the centroid; a square's diagonal split has a unit
rim but a `sqrt(2)` diagonal) — `subdivide_mesh`'s `edge_lengths` return
value captures each fine edge's true rest length correctly (derived from
`subdivide_polygon`'s own exact 2D coordinates for a regular n-gon of
unit edge length), but `generate_subdivided_stretchy_nets.py` currently
discards it, since the plain vertex-loop JSON format has no field for
per-edge lengths and `build_stretchy_cache.py` always solves with
`solve_wireframe`'s default UNIFORM `edge_length=1.0`. Confirmed
empirically on `cube_res4.json` (192 faces, 98 vertices): it solves
successfully (6.8% max stretch, within `STRETCH_CAP`) but settles into a
generic rounded/geodesic-ball shape, NOT a recognizable puffed-up cube —
because forcing the true-length rim and diagonal segments to be equal
erases the geometric distinction between them. This was a deliberate,
known-and-accepted tradeoff (see git history around this section), not a
bug to fix reflexively — `solve_wireframe`/`_residual` already support a
per-edge `{(a, b): length}` dict plus an explicit `volume_target` (see
their docstrings) if this ever needs to be revisited for geometric
fidelity.

Also worth knowing before reusing it: `solve_fabric_mesh` in
`mesh_subdivide.py` is a *different*, more involved path that was tried
for driving this live from the app (a "Fabric subdivision" checkbox in
`stretchy_polyhedron_init.py`, since removed at the user's request in
favor of this file-based workflow) — it drapes the fine mesh over the
coarse net's own `solve_wireframe` result as a 3D-accurate starting
guess (`_subdivide_dual` reruns the same barycentric grid construction in
3D, fed real solved corner/centroid positions) and then does one light
`_relax_seed` pass, specifically to avoid the same
orientation-consistency search that made `cube_res4.json` above take
~13 minutes to solve (a resolution-2 tetrahedron subdivision — just 16
small triangles — never once reached a consistent embedding in 30 random
attempts when tried via plain `solve_wireframe(fine_faces)`, several
seconds each). `mesh_subdivide.py` is kept around specifically so
different resolutions can still be explored this way later; it's just
not wired into `generate_subdivided_stretchy_nets.py` right now, which
takes the simpler (if slower and less faithful) route of the ordinary
cache/solve pipeline instead.

### The app (`stretchy_polyhedron_init.py`)

Same `sv_ttk` shell as the rigid apps, but the two panels mean something
different: left is each face's own **undeformed** regular-polygon target
(unconnected, side by side — there's no flat "net" for bendable faces),
right is the actual solved (generally non-planar, edges not quite unit
length) wireframe, drawn as translucent faces + edge lines + vertex dots.
There is no fabric-specific UI here — a subdivided net (see "Fabric
subdivision" above) is just another `stretchy_nets/*.json` file and shows
up in the same picker as anything else.
Solving always runs in a background thread (`_solve_worker` +
`queue.Queue`, same pattern as the rigid apps' "Compute" button) since a
cache miss on a bigger mesh (e.g. the dodecahedron) can take ~10s+. Net
selection tries the cache first (near-instant on a hit); "Compute All
Wireframes" warms every net's cache at once, same idea as the rigid
pipeline's "Compute Folding Pattern".

## Testing

`pytest` (from repo root, or anywhere — `pytest.ini` sets `pythonpath`).
The **rigid**-pipeline suite runs in ~3s; it deliberately only exercises
small nets (tetrahedron, cube, a synthetic paper-cube net, a tiny open
net) for the numerical solver so it stays fast — there's no test that runs
the icosahedron/truncated-icosahedron solve. Files map roughly 1:1 to
`net_fold_utils` modules (`test_polygon_geom.py`, `test_combinatorics.py`,
`test_net_layout.py`, `test_net_fold_core.py`, `test_fold_solver.py`,
`test_polyhedron_spec.py`, `test_fold_cache.py`, `test_hull_to_spec.py`,
`test_spanning_tree.py`, `test_open_nets.py`, `test_subdivision_utils.py`).
`test_fold_cache.py` uses `tmp_path` + `monkeypatch` to verify cache
reuse (patches `load_polyhedron_net` to raise, proving a cache hit never
calls it) and stale-cache deletion on a failed re-solve;
`test_stretchy_cache.py` mirrors this for the stretchy pipeline.

The **stretchy**-pipeline suite (`test_stretchy_mesh.py`) is slower
(~30-60s) since even the small Platonic solids run the real
`solve_wireframe` — the dodecahedron and icosahedron are deliberately kept
OUT of it (same rationale as the rigid suite) and verified manually
instead. Includes `monkeypatch`-based tests of the orientation-consistency
failure path (forcing `_is_orientation_consistent` to always return
`False` to exercise the `ValueError`) and of the winding convention itself
(reversing one face's loop and checking `_is_orientation_consistent`
catches it).

`test_mesh_subdivide.py` covers the fabric-subdivision pipeline (see
above): combinatorial closure of the fine mesh at several resolutions,
that shared coarse edges actually merge (not left as disconnected
per-face patches), that a pentagon face's fine edges have exactly two
distinct rest lengths (rim vs. spoke, not a uniform one), and that
`solve_fabric_mesh` produces low-stretch results for both an
already-rigid coarse net (tetrahedron) and a genuinely bendy one
(`two_pentagons_and_a_square.json`) — fast (~5s total) since the
drape-then-relax approach never needs the slow random-restart search.

## Conventions worth knowing before editing

- All polygon edges have length 1 (`polygon_geom.EDGE_LENGTH` /
  `stretchy_mesh.EDGE_LENGTH`) — faces are glued edge-to-edge exactly in
  the rigid pipeline; the stretchy pipeline lets edges stretch a little
  (capped at `STRETCH_CAP`) but still targets the same unit length.
- Polygons are CCW as seen from outside the solid, in **both** pipelines
  (rigid: `net_layout.py` — a child face attaches to its parent via a
  *reversed* edge mapping, matching how a physical paper net unfolds to
  the outside; stretchy: `stretchy_mesh.py`'s module docstring — a shared
  edge appears as `v -> w` in one face's loop and `w -> v` in the other's).
- A stored "fold angle" (rigid pipeline only) is the rotation *from flat*
  (180° between coplanar faces), not the dihedral angle itself — e.g. cube
  hinges rotate 90° (dihedral is also 90°, self-supplementary), tetrahedron
  hinges rotate 109.47° (dihedral is 70.53°).
- Legacy `.txt` nets (explicit coordinates + fold angles, no solving
  needed) are still supported via `net_io.load_net_txt`, dispatched
  automatically by file extension in `net_io.load_net` (`.json` vs `.txt`).
- `net_fold_core.py`, `fold_solver.py`, `fold_cache.py`, and
  `stretchy_mesh.py`/`stretchy_cache.py` have no `if __name__ ==
  "__main__"` demo blocks — that logic lives in `tests/`. Add new ad hoc
  verification as a real test, not a script block.
- Rigid nets (`nets/*.json`) and stretchy nets (`stretchy_nets/*.json`) are
  NOT interchangeable formats, even though both are JSON with a `"faces"`
  key — one is `{"id", "sides", "isRoot"?, "omit"?}` objects with a
  separate `edges.net`/`edges.extra`/`edges.hidden`, the other is plain
  vertex-id-loop lists. Loading one with the other pipeline's loader will
  fail (usually confusingly) rather than "just working".
