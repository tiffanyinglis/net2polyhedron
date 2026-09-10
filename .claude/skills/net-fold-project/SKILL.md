---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (the src/utils library, .json/.fold formats, the fold solver, the stretchy-mesh solver, the Tkinter apps in src/apps, tests). Load before making non-trivial changes to this repo instead of re-deriving the pipeline by re-reading every file.
---

# Polyhedron net-folding project

## Untouchable files

These files are considered DONE -- the user has finished them and
deliberately doesn't want them touched, since editing them (even
additively) risks messing up code structure they've already settled on:

- `src/utils/geometry/polygon_geom.py`
- `src/utils/geometry/polyhedron.py` (`Polyhedron`: pure 3D solid geometry
  -- shared, indexed vertices; CCW faces; derived `.edges`; `.face_vertices()`,
  `.face_normal()`, `.is_closed()`, `.compute_face_adjacency()`. Ported over
  from the sibling `polyhedron-unfolder` project's own `Polyhedron`, with
  `face_normal` inlined rather than imported from a fold engine, since this
  project doesn't have one.)
- `src/apps/ui/tooltip.py`
- `src/apps/ui/cullable_face.py`
- `src/apps/ui/__init__.py`
- `src/apps/common/bounding_box.py`
- `src/apps/common/ui_theme.py`
- `.gitignore`
- `requirements.txt`
- `pytest.ini`
- `.claude/settings.local.json`
- `tests/unit/apps_common/test_bounding_box.py`
- `tests/unit/geometry/test_polygon_geom.py`
- `src/apps/polygon_subdivision_app/app.py`
- `src/utils/subdivisions/__init__.py`
- `src/utils/subdivisions/polygon_subdivisions.py`
- `src/utils/subdivisions/mesh_subdivide.py`

(The `polygon_subdivision_app`/`utils/subdivisions/` entries above are
NOT part of the polyhedron-unfolder sync described below -- they're this
project's own polygon-subdivision demo, considered separately finished
and settled by the user. Everything else in this list is synced from the
sibling `polyhedron-unfolder` project --
each is either byte-identical there or differs only in import paths for
net2polyhedron's package layout, verified file-by-file. Files there that
have genuinely diverged, e.g. `src/apps/common/paths.py`, were deliberately
NOT synced since `polyhedron-unfolder`'s version lacks functionality
net2polyhedron depends on.

**The entire rigid-unfolding pipeline (`src/apps/polyhedron_unfolder/`,
`src/utils/polyhedron_unfolder/`, `src/utils/persistence/polyhedron_spec.py`,
their tests, and `data/input/nets/*.json`) has been DELETED from this
project** -- that functionality now lives solely in the sibling
`polyhedron-unfolder` project, so it no longer needs to be duplicated or
synced here. `tests/unit/inflate_polyhedron/test_hull_to_spec.py` and
`tests/unit/inflate_polyhedron/test_stretchy_mesh.py` had their own borrowed copies
of rigid-net vertex coordinates (used only as fixture data, not a real
functional dependency) inlined directly so they didn't need to change
behavior. `src/apps/common/paths.py` still defines `NETS_DIR` even though
nothing reads it anymore -- harmless, but a cleanup candidate.)

Do not read these as a target for changes and do not modify them --
adding, removing, or "just cleaning up" anything in them is off limits --
UNLESS the user explicitly asks for a change to one of these files BY
NAME or by unambiguous description in their current request. If a task
would otherwise require touching one, stop and explicitly ask the user
for permission first, naming the file and what change is needed, rather
than proceeding or silently working around it. This list is expected to
grow -- check it before editing anything in this project.

Two Tkinter entry points currently live in this project (a third,
`polyhedron_unfolder`, existed for the now-DELETED rigid-unfolding
pipeline described below — see "Untouchable files" above and "Removed:
the rigid-unfolding pipeline (historical)" further down):

- `polygon_subdivision_app` (`src/apps/polygon_subdivision_app/app.py`) —
  unrelated to folding: a 2D-only demo that splits a triangle/square/.../
  8-gon into a fine triangular mesh (see "Polygon subdivision demo" below).
- `inflate_polyhedron_app` (`src/apps/inflate_polyhedron_app/app.py`) — a
  DIFFERENT solver entirely, for nets that can't stay rigid and flat at
  all (e.g. a face sharing more than one edge with a neighbor). See
  "Stretchy meshes" below — this is the most algorithmically involved
  part of the project, and the only one that still needs a solve cache
  (`src/apps/inflate_polyhedron_app/cache/`, warmed by its own
  `build_cache.py`) since its solve is a genuine numerical optimization,
  unlike the rigid pipeline's.

## Directory layout

The project is split into `src/` (code), `tests/`, and `data/` (everything
on-disk that isn't code). Every module that used to live in the
now-removed `net_fold_utils/`/`subdivision_utils/` packages, and every
top-level script/app that used to live at the repo root or in `tools/`,
moved wholesale — no file's own content changed as part of the move
itself, only its import paths and (for apps) its data-directory constants.

`src/apps/` — one folder per GUI app, plus `common/` and `ui/` for code
shared across more than one of them. (A third app folder,
`polyhedron_unfolder/`, used to hold the merged rigid-pipeline app
described in "Removed: the rigid-unfolding pipeline (historical)" below
— it has been deleted along with the rest of that pipeline, so only the
two folders below exist now.)
- `inflate_polyhedron_app/` — the stretchy-mesh viewer (see "Stretchy meshes" below)
  - `app.py` — entry point, class `InflatePolyhedronApp`
  - `build_cache.py` — precompute/refresh this app's OWN solve cache
    (was the top-level `build_stretchy_cache.py`)
  - `cache/*.json` — the actual cache files (was `data/cache/stretchy_cache/`)
- `polygon_subdivision_app/` — 2D-only fine-triangle-mesh demo (see below), no cache
  - `app.py` — entry point, class `PolygonSubdivisionApp`
- `common/` — helpers SHARED by more than one app (not net-fold domain
  logic -- that's `utils/` -- and not GUI widgets -- that's `ui/`):
  - `paths.py` — the ONLY place that computes shared, cross-app
    locations: `NETS_DIR`/`STRETCHY_NETS_DIR` (input nets — NOT caches,
    those are per-app, above), all derived from `Path(__file__)`. An
    app one level deeper than `src/apps/` first does a tiny inline
    bootstrap (`sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`)
    so `common`/`ui` are importable at all, THEN imports from
    `common.paths` before importing anything from `utils` — as an
    import side effect, `common/paths.py` inserts `src/` onto
    `sys.path`, which is what makes `from utils.<category> import ...`
    resolve when a script is run directly (`python src/apps/<app>/app.py`)
    rather than as an installed package. `NETS_DIR` (pointing at the
    now-deleted `data/input/nets/`) is a leftover from the removed rigid
    pipeline (see "Removed: the rigid-unfolding pipeline (historical)"
    below) — nothing reads it anymore; harmless, but a cleanup candidate.
  - `ui_theme.py` — `STATUS_COLORS`/`PLOT_THEME`/`FACE_COLORS`/
    `DISABLED_SUFFIX`/`COMPUTE_TOOLTIP`, extracted here (they used to
    live in `polygon_fold_app.py`, imported by the other apps from it)
    specifically so no app depends on another app's module
  - `bounding_box.py` — `bounding_box(vertices)`: `(lo, hi)` over a list/array
    of 3D points. **Currently unused** — it was written for the
    now-deleted rigid-pipeline app's `_draw_solid` (see "Removed: the
    rigid-unfolding pipeline (historical)" below), which used it to center
    and size its 3D view. On the untouchable-files list (see top of this
    doc), so it stays even though nothing currently imports it.
  There USED TO be a `sample_polyhedra.py` here and three `generate_*.py`
  scripts (`generate_platonic_nets.py`, `generate_stretchy_platonic_nets.py`,
  `generate_open_dodecahedron_nets.py`) that derived Platonic-solid vertex
  data and wrote it out as `.json` net specs. All four are DELETED now: the
  user settled on treating the `.json` files under `data/input/` as the
  canonical, hand-kept inputs in their own right rather than regenerated
  artifacts, so nothing needs to re-derive them from raw coordinates
  anymore. See git history (`sample_polyhedra`/`generate_platonic_nets`,
  etc.) if a genuinely NEW sample solid with no existing `.json` ever needs
  the old raw-coordinates-via-`hull_to_spec` approach again.
  - `generate_subdivided_stretchy_nets.py` — writes `data/input/stretchy_nets/<name>_res<resolution>.json` fine-triangulated variants of an existing stretchy net (see "Fabric subdivision" below); reads an existing stretchy net's own faces directly, no dependency on the now-removed `sample_polyhedra.py`. This is the one remaining `generate_*.py` script; it isn't imported by anything (it's its own CLI entry point) and lives in `common/` anyway since it's maintenance tooling shared across whichever apps read the `data/input/` specs it produces, and neither `utils/` (no `__main__` scripts there, see Conventions) nor `ui/` fit
- `ui/` — generic Tkinter/matplotlib widgets, not net-fold domain logic:
  - `tooltip.py` — `Tooltip`, a small generic hover-tooltip helper for Tkinter (not net-fold-specific)
  - `cullable_face.py` — `_CullableFace`, generic matplotlib/3D backface-culling logic, not fold-solving logic. **Currently unused** — written for the now-deleted `polyhedron_unfolder` app (see "Removed: the rigid-unfolding pipeline (historical)" below); on the untouchable-files list (see top of this doc), so it stays even though nothing currently imports it.

`src/utils/` — the reusable library, split by concern (see each
sub-package's own `__init__.py` docstring for its module list):
- `geometry/` — general-purpose 2D/3D geometry with no domain-specific
  algorithm content: `polygon_geom.py` (regular polygon vertices + rigid
  2D edge attachment, shared by both `subdivisions` and
  `inflate_polyhedron`) and `polyhedron.py` (below) -- `polyhedron.py`
  is currently only used by `inflate_polyhedron`, not `subdivisions`, but
  it lives here anyway since it's general-purpose solid geometry, not
  specific to the stretchy-mesh algorithm itself; `geometry/__init__.py`
  re-exports `EDGE_LENGTH, regular_polygon_vertices, attach_polygon,
  Polyhedron, face_normal`. `stretchy_net_layout.py` looked like it
  belonged here too (it's 2D layout code) but only `inflate_polyhedron`
  ever uses it AND it's specific to the stretchy algorithm, so it lives
  in `inflate_polyhedron/` instead.
  - `polyhedron.py` — class `Polyhedron`: pure 3D solid geometry — shared,
    indexed vertices; CCW vertex-index faces; derived `.edges`; `.face_vertices()`,
    `.face_normal()`, `.is_closed()`, `.compute_face_adjacency()`. No
    awareness of nets, hinges, fold progress, or color. Re-added here after
    the rigid-unfolding pipeline (which used to own the only `Polyhedron` in
    this project, under a now-deleted `polyhedron_unfolder/` package) was
    removed entirely — this copy is self-contained (`face_normal` is
    inlined rather than shared with a fold engine, since this project no
    longer has one). **On the untouchable-files list** (see top of this
    doc) — don't edit it without asking first.
- `inflate_polyhedron/` — everything specific to the stretchy (non-rigid)
  mesh pipeline: solving, flat net layout, and disk caching (this used to
  be split across `geometry2d/` [the stretchy half], `geometry3d/`, and
  `persistence/` — merged into one package since none of it is shared
  with `subdivisions`, only with itself). Modules: `stretchy_mesh.py`,
  `hull_to_spec.py`, `stretchy_net_layout.py`, `checksums.py`,
  `stretchy_cache.py`. `stretchy_cache.py` is deliberately NOT re-exported
  from this package's own `__init__.py` (import it directly, e.g.
  `from utils.inflate_polyhedron.stretchy_cache import load_with_cache`):
  it imports `..subdivisions.mesh_subdivide`, which imports back into this
  package's own `stretchy_mesh` module, so re-exporting it eagerly at
  package-init time would make that a genuine circular import whenever
  `utils.subdivisions` happens to be the first of the two packages loaded
  in a given process.
  - `hull_to_spec.py` — `polyhedron_from_vertices(vertices, name=None)`
    builds and returns a `Polyhedron` straight from a convex solid's raw 3D
    coordinates (via `scipy.spatial.ConvexHull`, merging back the
    triangulated facets into their true polygonal faces) — face degrees and
    adjacency are then just `.faces`/`.compute_face_adjacency()`, not a
    separately-returned tuple.
  - `stretchy_mesh.py`'s `mesh_to_polyhedron(positions, faces, name=None)`
    is the bridge from the stretchy pipeline's own dict-keyed mesh
    representation (`positions`: `{vertex_id: np.ndarray(3,)}`, `faces`:
    vertex-id loops -- see this module's docstring) into a `Polyhedron`:
    vertex ids are remapped to `Polyhedron`'s dense 0..N-1 index space the
    same way `_edge_setup` does for `relax_once`, so `polyhedron.vertices[i]`
    is the position for edge/face-index `i` directly. The solve/relax
    internals themselves stay on the dict representation (vertices are
    relaxed by id, and a mid-solve mesh isn't reliably closed/convex, so
    `Polyhedron`'s dense-index assumption doesn't fit there) -- this bridge
    is for callers that want a *finished* mesh's `.edges`/`.is_closed()`/
    `.face_normal()` rather than reimplementing them, e.g.
    `inflate_polyhedron_app`'s `_draw_wireframe_result` (see "The app" below).
  - `inflate_polyhedron/__init__.py` re-exports `load_stretchy_mesh,
    solve_wireframe, relax_once, mesh_to_polyhedron, polyhedron_from_vertices,
    build_stretchy_net_layout` (not `Polyhedron` itself, which lives in
    `utils.geometry` now -- see its own bullet above -- nor `stretchy_cache`,
    see above).
  Sample solids (Platonic, etc.) have no on-disk source in this project
  anymore (the old `data/input/nets/*.json` + `sample_polyhedra.py`
  approach was removed along with the rigid pipeline) — anything that needs
  one now either has its own inline vertex coordinates (see
  `tests/unit/inflate_polyhedron/test_hull_to_spec.py`,
  `tests/unit/inflate_polyhedron/test_stretchy_mesh.py`) or loads a stretchy net
  from `data/input/stretchy_nets/*.json` instead.
- `subdivisions/` — fine-triangle-mesh subdivision: `polygon_subdivisions.py` (renamed from the old top-level `subdivision_utils/subdivisions.py` — a package can't contain a module with its own name) and `mesh_subdivide.py`, which builds a fine "fabric" triangulation of a whole stretchy net (see "Fabric subdivision" below)

  (There USED TO be a `polyhedron_unfolder/` package here too — the rigid
  pipeline's whole object model, `polyhedron.py`/`polyhedron_unfolder.py`/
  `unfoldable_polyhedron.py`/`spanning_tree.py`. It has been DELETED along
  with the rest of that pipeline — see "Removed: the rigid-unfolding
  pipeline (historical)" below and the sibling `polyhedron-unfolder`
  project. `src/utils/geometry/polyhedron.py`, above, is a self-contained
  re-add of just that package's `Polyhedron` class, not a survivor of it.)
`data/` — everything on-disk that isn't code (input specs ONLY — no
caches; those are per-app, under `src/apps/<app>/cache/`, see above):
- `input/stretchy_nets/*.json` — **human-authored** STRETCHY net specs (vertex-loop format, see below). (There USED TO also be an `input/nets/*.json` directory of RIGID net specs — deleted along with the rigid pipeline, see "Removed: the rigid-unfolding pipeline (historical)" below.) (There USED TO also be an `output/` directory of user-generated saves from `inflate_polyhedron_app`'s "Save" button — that button was removed, see "The app" below.)

`tests/` — pytest suite (see Testing below):
- `unit/<category>/` — one test file per `src/utils/<category>/` module, mirroring `src/utils/`'s own sub-package layout exactly. (There USED TO also be a `unit/polyhedron_unfolder/` directory, one test file per module of the now-deleted rigid-pipeline package, and an `integration/` directory of tests crossing `utils` sub-package boundaries plus a shared `helpers.py` — both removed along with the rigid pipeline; see "Removed: the rigid-unfolding pipeline (historical)" below.)
- `unit/apps_common/` — the (currently one-file) exception: covers `src/apps/common/` helpers that are plain functions/classes with no Tkinter/matplotlib dependency (e.g. `bounding_box.py`) -- not a `src/utils/` category, so it doesn't fit the mirroring rule above; the rest of `src/apps/` stays untested per this project's existing convention.
- `run_tests.py` — `python tests/run_tests.py [pytest args...]`

Top level:
- `pytest.ini` — sets `pythonpath = . src src/apps` so tests can `import utils` regardless of cwd, and (via the `src/apps` entry) `from common.<module> import ...` the same way the apps themselves resolve it
- `requirements.txt` — numpy, scipy, networkx, matplotlib, sv-ttk, (dev) pytest
- `README.md` — user-facing usage doc (install, run the app, write a `.json` net, the cache, tests)

## Removed: the rigid-unfolding pipeline (historical)

**Everything in this section describes a package/app that no longer
exists in this project.** As already noted under "Untouchable files"
above, the entire rigid-unfolding pipeline — `src/apps/polyhedron_unfolder/`,
`src/utils/polyhedron_unfolder/`, `src/utils/persistence/polyhedron_spec.py`,
their tests (`tests/unit/polyhedron_unfolder/`, `tests/integration/`), and
`data/input/nets/*.json` — has been DELETED from this project; that
functionality now lives solely in the sibling `polyhedron-unfolder`
project. This section is kept short and historical, only for the bits of
context that explain still-current code or conventions elsewhere in this
doc (search for "Removed: the rigid-unfolding pipeline" to find every
place that points back here).

**What it did**: took a polyhedron (real 3D vertex positions + CCW face
loops, a `{"name", "vertices", "faces"}` `.json` spec) and derived how it
unfolds — an auto-computed BFS spanning tree of hinges over face
adjacency, a flat 2D layout (each face's real corners projected into an
orthonormal 2D basis, then rigid-attached to its parent along the shared
edge), and each hinge's fold angle read directly off the given geometry
(`arccos(dot(face_normal(parent), face_normal(child)))` — the rotation
*from flat*, e.g. 90° for a cube's self-supplementary 90° dihedral,
109.47° for a tetrahedron's 70.53° dihedral) rather than solved for. It
also handled **open nets** (a spec whose `"faces"` is a subset of some
solid's — no special field needed, since face adjacency is derived
directly from whichever faces are listed; an omitted-adjacent edge just
becomes a boundary edge). Its own `Polyhedron` class (CCW vertex-index
faces, derived `.edges`, `.face_vertices()`, `.face_normal()`,
`.is_closed()`, `.compute_face_adjacency()`) is what
`src/utils/geometry/polyhedron.py` (on the untouchable-files list, see
top of this doc) is a self-contained re-add of.

**Why there was no `fold_solver.py`-style numerical solver**: an earlier,
even-older version of this project used an abstract faces/edges spec with
no coordinates, and had to numerically solve for fold angles (`scipy
least_squares`, a 17-point restart sweep, rejecting "collapsed"
self-intersecting solutions). Once specs carried real 3D coordinates,
fold angles became directly measurable instead — this is the historical
reason a `fold_solver.py`-shaped module doesn't exist anywhere in this
project anymore, and it's also the direct ancestor of the "collapsed
branch" embeddability concern that the CURRENT stretchy pipeline's
orientation-consistency search (see "Orientation consistency" under
"Stretchy meshes" below) had to solve a different way, since a stretchy
mesh has no coordinates-first shortcut available to it. Because nothing
was left to solve for, the rigid pipeline was fast even for its bushiest
net (~0.07s for a 32-face, 31-hinge truncated icosahedron) and needed no
on-disk cache at all — unlike the stretchy pipeline's
`stretchy_cache.py` (see "Caching" under "Stretchy meshes" below), which
still earns its keep since `solve_wireframe` is a genuine numerical
optimization.

**Leftover, now-unused files** (kept because they're on the
untouchable-files list, not because anything still calls them): the
`polyhedron_unfolder` app's `_draw_solid` used `_CullableFace`
(`src/apps/ui/cullable_face.py`) for exact backface culling on a closed
convex solid's fully-folded 3D view, and `bounding_box.py`
(`src/apps/common/bounding_box.py`) to center/size that same view — see
their own bullets under "Directory layout" above. `src/apps/common/paths.py`
still defines `NETS_DIR` (pointing at the now-deleted
`data/input/nets/`) for the same reason.

Both pipelines share the same **CCW-from-outside** winding convention (a
shared edge is `v -> w` in one face's loop and `w -> v` in the other's) —
see "Conventions worth knowing before editing" below, which is still
accurate for the current stretchy pipeline and for
`src/utils/geometry/polyhedron.py`.

## Polygon subdivision demo (`polygon_subdivision_app`, `utils/subdivisions/`)

Unrelated to folding — a standalone 2D demo of splitting a regular n-gon
(triangle through 8-gon) into a fine triangular mesh, e.g. as a preview of
the mesh a later fabric/cloth simulation would use. Two-stage, both
hardcoded/closed-form (no runtime search):

1. `utils.subdivisions.polygon_subdivisions.SUBDIVISIONS` — a hardcoded coarse split
   of each n-gon into a handful of triangles using only the polygon's own
   vertices plus its centroid: a centroid fan for every n = 4..8 (n
   congruent isoceles triangles, exactly equilateral at n=6). n=4 used to
   be a diagonal split (2 triangles, no centroid) instead, until that was
   found to give a polyhedron built from squares (a cube) an asymmetric
   mesh valence at some of its corners — see "Fabric subdivision" below
   for the full story.
2. `resolution_for(n, base_resolution)` picks a PER-N-GON resolution so
   that every n-gon's fine triangles end up roughly the same size for a
   given nominal resolution — since `len(SUBDIVISIONS[n])` (the coarse
   triangle count) doesn't scale exactly with a regular n-gon's own area,
   using the same literal `resolution` for every n-gon leaves bigger-sided
   polygons' fine triangles coarser than a square's. Matches fine-triangle
   AREA against `base_n=4` (the square) at `base_resolution`, via the
   closed-form regular-polygon area formula — see its docstring.
3. `_subdivide_triangle` splits each coarse triangle into `resolution ** 2`
   small ones via a regular barycentric grid (the standard geodesic/
   icosphere-style refinement) — every small triangle is a scaled copy of
   the coarse one it sits inside. `subdivide()` merges the results from all
   coarse triangles into one mesh: points shared between adjacent coarse
   triangles land on bit-for-bit identical barycentric coordinates, so they
   merge into one shared point rather than staying duplicated.

`polygon_subdivision_app`'s layout pairs a small n-gon with a big one in each
column (3-gon over 8-gon, etc.) and gives every subplot the **same** fixed
axis range (sized to the largest n-gon) rather than each auto-scaling to
its own bounding box, so a unit edge length renders at the same pixel size
everywhere and triangle sizes are directly comparable by eye.

It deliberately uses `FABRIC_APP_RESOLUTION` (imported from
`utils.subdivisions.mesh_subdivide.DEFAULT_RESOLUTION`, currently 3) as the
`base_resolution` passed to `resolution_for`, NOT
`utils.subdivisions.DEFAULT_RESOLUTION` (10, a denser default meant for a
generic standalone preview) — this demo's whole purpose is to preview
what the real stretchy fabric nets (e.g. `cube_res3.json`) actually solve,
so it shows exactly that subdivision, not an unrelated denser one.

## Stretchy meshes (`src/utils/inflate_polyhedron/stretchy_mesh.py`, `inflate_polyhedron_app`)

For nets that **cannot** be realized with perfectly rigid, flat faces —
most sharply, two faces glued along more than one shared edge. If two flat
polygons share ≥3 non-collinear points, both must lie in the one plane
those points determine — there's no dihedral fold left to make them
distinct faces of a solid. This is a genuine geometric impossibility, not
just a representational limitation of some rigid-pipeline data structure
— the now-deleted rigid pipeline's own `Polyhedron`/`UnfoldablePolyhedron`
could combinatorially describe such a face pair without any trouble
(there's no `EdgeMap`-style planar-embedding step to reject it, see
"Removed: the rigid-unfolding pipeline (historical)" above), but attempting
to actually unfold one would still fail geometrically at the flat-layout
step (two faces sharing >1 edge can't both come out flat and rigid). So
this remains a genuinely different data model and solver, not an
extension of the rigid one.

### The vertex-loop format (`data/input/stretchy_nets/*.json`)

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
  normally-unreachable target: the volume of the sphere with the mesh's
  own total rest surface area (`_total_rest_area` -- exact per-face
  regular-polygon area for a uniform `edge_length`, Heron's formula per
  triangle for a per-edge dict, e.g. a subdivided mesh's mixed rest
  lengths). Scaled to the mesh's own size rather than an arbitrary huge
  constant — e.g. ~2.40 for the icosahedron (true volume ~2.18) — so it
  gives real, well-scaled "pressure" without wildly overshooting what the
  mesh could ever hold.
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
  (`data/input/stretchy_nets/two_pentagons_and_a_square.json`) instead of stretching
  it into a mess.
- A final light planarity pass (`PLANARITY_WEIGHT`, via per-face best-fit-
  plane SVD residuals) tidies up individual faces at the same pressure
  without relaxing it back down — inflation already tends to leave faces
  close to flat on its own (a taut membrane wants to be locally flat
  wherever its edges allow), so this only has a little polishing left to
  do.

This pressure term (`_residual`) is a single GLOBAL target for the whole
mesh, specific to this automatic ramp. `inflate_polyhedron_app`'s
interactive "Inflate" button uses a DIFFERENT force entirely
(`_relax_force`, see "The app" below): a real per-face pressure force
with no target/volume at all, plus a soft per-edge stretch limit instead
of a global ceiling.

### Orientation consistency (why this needed real iteration to get right)

Plain edge-length fitting has no opinion about orientation, so a stage-1
result is often already self-intersecting — one face folded inside-out
relative to the rest (a sharper version of the "collapsed branch" problem
the now-deleted rigid pipeline's own fold solver used to reject via
`_is_embeddable`, back when rigid fold angles were numerically solved for
rather than read directly off given geometry — see "Removed: the
rigid-unfolding pipeline (historical)" above). `_orientation_signs`
detects this cheaply: for each face, the sign of `dot(face_normal,
face_centroid - mesh_centroid)`; a properly embedded mesh has every face
agree AND come out +1 (outward from the centroid) — `_is_orientation_consistent`
checks both, not just mutual agreement, since an all-faces-agree-but-all-
point-inward mesh (gone fully inside-out) would otherwise pass too.

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
   self-intersecting mesh — `inflate_polyhedron_app/build_cache.py`'s existing
   `except ValueError` failure-reporting path surfaces this per-net.

A separate, cheap guard catches what orientation-consistency can't:
`_min_pairwise_separation(pts) > MIN_SEPARATION_FRACTION * edge_length`
rejects a result where two *unrelated* (non-adjacent) vertices happen to
have collapsed onto each other — face-normal signs don't notice that on
their own, since `_mesh_volume`'s pressure term has no particular reason
to keep distinct vertices apart.

### Caching (`src/utils/inflate_polyhedron/stretchy_cache.py`)

The now-deleted rigid pipeline had no equivalent (see "Removed: the
rigid-unfolding pipeline (historical)" above) --
this one still earns its keep because `solve_wireframe` is a genuine
numerical optimization, not a direct geometric read. Records just a
positions + stats dict (no hinge tree/fold angles to write out).
`ALGORITHM_VERSION` (in `stretchy_mesh.py`) is folded into the cache key
(`stretchy_cache.source_checksum` = file hash + `"+algo{VERSION}"`) —
**bump it whenever `solve_wireframe`'s algorithm changes enough to produce
a different result for the same mesh**, e.g. adding the inflation stage.
Without this, an on-disk cache from a previous algorithm version would
keep being served forever, since its checksum only ever tracked the
*source* `.json`, not how it was solved. The cache always stores seed=0's
result (the one canonical answer) via `_solve` -- `solve_wireframe` for
an ordinary net, or `mesh_subdivide.solve_fabric_mesh` for a fabric one
(see `load_fabric_spec`) -- and is used by `inflate_polyhedron_app`'s
`build_cache.py` and `build_all`. **The interactive "Inflate" loop itself
no longer reads or writes this cache at all** (see "The app" below, a
substantial rewrite from the earlier "pick a net, see the solved answer"
design) -- the app's `on_select_net` still reads it once, via
`load_with_cache`, to get the starting shape -- caching still matters for
warming `inflate_polyhedron_app/cache/` ahead of time via `build_cache.py`,
just not for the interactive loop itself.

### Fabric subdivision (`src/utils/subdivisions/mesh_subdivide.py`, `src/apps/common/generate_subdivided_stretchy_nets.py`)

Simulates a stretchy net's faces as fabric rather than (at most gently
bending) rigid-ish panels: every coarse face is split into a fine
triangular mesh — the same hardcoded per-n-gon coarse split
(`utils.subdivisions.SUBDIVISIONS`) and barycentric refinement
(`utils.subdivisions.polygon_subdivisions._subdivide_triangle`) `polygon_subdivision_app` uses to
preview a single polygon — applied to every face of a whole net at once,
with points on a shared coarse edge merged into one global vertex so the
result is a single connected mesh, not N disconnected per-face patches.

**This is a file-generation step, not an app feature.**
`src/apps/common/generate_subdivided_stretchy_nets.py` reads an existing
`data/input/stretchy_nets/<name>.json`, calls `subdivide_mesh(coarse_faces,
resolution)`, and writes the fine triangulation straight out as an
ordinary `data/input/stretchy_nets/<name>_res<resolution>.json` — a plain
vertex-loop mesh, no different in format from any other stretchy net.
(`SUBDIVISIONS_TO_GENERATE` at the top of that script is the editable
list of `(name, resolution)` pairs to produce; `data/input/stretchy_nets/cube_res3.json`
is the one generated so far -- resolution 3, not 4, because SUBDIVISIONS[4]
switching to a 4-triangle centroid fan (see below) doubled the coarse
triangle count per face, so resolution 3 there lands close to the triangle
count resolution 4 used to give under the old 2-triangle split.) Once
written, it goes through `inflate_polyhedron_app`'s `build_cache.py` and
net picker completely unmodified — there is no separate fabric mode or
UI control for this, it's just another `.json` in the directory.

**Known simplification: rest lengths are treated as uniform, even though
they aren't.** SUBDIVISIONS' coarse triangles aren't generally
equilateral (a centroid fan has unit-length rim edges but shorter spoke
edges to the centroid, except exactly at n=6) — `subdivide_mesh`'s
`edge_lengths` return value captures each fine edge's true rest length
correctly (derived from `subdivide_polygon`'s own exact 2D coordinates for
a regular n-gon of unit edge length), but `generate_subdivided_stretchy_nets.py`
currently discards it, since the plain vertex-loop JSON format has no
field for per-edge lengths and `inflate_polyhedron_app/build_cache.py` always solves
with `solve_wireframe`'s default UNIFORM `edge_length=1.0`. Confirmed
empirically on an earlier, diagonal-split version of the subdivided cube
net (192 faces, 98 vertices): it solves successfully (6.8% max stretch,
within `STRETCH_CAP`) but settles into a generic rounded/geodesic-ball
shape, NOT a recognizable puffed-up cube — because forcing the true-length
rim and diagonal segments to be equal erases the geometric distinction
between them. The same mismatch exists just as much (rim vs. spoke) under
the current centroid-fan split, so this remains a deliberate,
known-and-accepted tradeoff (see git history around this section), not a
bug to fix reflexively — `solve_wireframe`/`_residual` already support a
per-edge `{(a, b): length}` dict plus an explicit `volume_target` (see
their docstrings) if this ever needs to be revisited for geometric
fidelity.

Also worth knowing before reusing it: `solve_fabric_mesh` in
`mesh_subdivide.py` is a *different*, more involved path that was tried
for driving this live from the app (a "Fabric subdivision" checkbox in
`inflate_polyhedron_app`, since removed at the user's request in
favor of this file-based workflow) — it drapes the fine mesh over the
coarse net's own `solve_wireframe` result as a 3D-accurate starting
guess (`_subdivide_dual` reruns the same barycentric grid construction in
3D, fed real solved corner/centroid positions) and then does one light
`_relax_seed` pass, specifically to avoid the same
orientation-consistency search that made the subdivided cube net above take
~13 minutes to solve (a resolution-2 tetrahedron subdivision — just 16
small triangles — never once reached a consistent embedding in 30 random
attempts when tried via plain `solve_wireframe(fine_faces)`, several
seconds each). `mesh_subdivide.py` is kept around specifically so
different resolutions can still be explored this way later; it's just
not wired into `generate_subdivided_stretchy_nets.py` right now, which
takes the simpler (if slower and less faithful) route of the ordinary
cache/solve pipeline instead.

### The app (`inflate_polyhedron_app`) — coarse starting shape, subdivide and inflate interactively from there

Rewritten (through a couple of iterations -- see git history if the
reasoning below seems oddly specific) from an original "pick a net, see
the one automatically-solved answer" design, then again from a
"precomputed fixed-resolution fabric mesh, interactive from there" design
(the fabric-subdivided `.json` files below, `generate_subdivided_stretchy_nets.py`,
and `mesh_subdivide.solve_fabric_mesh`'s drape were built for THAT
design) into the CURRENT one: every net is always loaded at its own
BASE (level 0) resolution, and the app's own "Subdivide" button
(`utils.inflate_polyhedron.mesh_levels.subdivide_once`) refines it
interactively, one nested level at a time, so any inflation already done
at one level carries forward as the next level's starting point instead
of being discarded for a fresh precomputed drape. A legacy
fabric-subdivided file (one with baked-in `"coarse_faces"`, e.g.
`cube_res3.json`) still loads fine -- `on_select_net` just uses ITS OWN
`coarse_faces` as level 0, ignoring its pre-baked fine mesh/cache
entirely, since a coarse solve is already cheap. Two steps, split between
the net picker and the "Subdivide" button:

1. **Coarse solve** -- `stretchy_mesh.solve_wireframe` on the net's own
   base (level 0) faces, on selecting it in the net picker. Its
   random-restart-plus-inflation-ramp search is exactly what makes this
   reliable: a coarse net has few enough faces that retrying a different
   random start when one doesn't inflate cleanly is cheap. Cached via
   `stretchy_cache` for an ORDINARY net (not a legacy fabric one, whose
   coarse solve is cheap enough not to need caching at all).
2. **Subdivide** (`mesh_levels.subdivide_once`, see its own module
   docstring) -- one press refines the CURRENT mesh by one level: a
   centroid fan at level 0 -> 1 (unchanged for an already-triangular
   face), then a "triforce" quarter of every triangle for each level
   after that, up to `MAX_LEVEL` (3), where the button greys out. New
   POSITIONS are linearly interpolated from the current mesh's own nearby
   points (so already-inflated detail survives); new REST LENGTHS are
   derived analytically from the flat, unit-edge reference geometry
   (exact circumradius for a spoke, exact halving/midsegment-theorem
   lengths for a quarter), independent of the current (possibly already
   stretched) 3D positions -- so the "ideal" target shape a relax stays
   pointed at doesn't drift as resolution increases, letting "inflate,
   then increase resolution, then inflate again" converge toward one
   consistent answer.

The "Pressure"/"Inflate" controls below work at ANY level, not just the
final one -- `CONVERGENCE_GTOL` (see `stretchy_mesh.py`) is `1e-4`: some
meshes visibly settle (near-zero stretch, positions stop moving) well
before their worst vertex's net force actually crosses a strict
tolerance, so this is deliberately looser than it might seem it needs to
be rather than making those meshes take far more steps to formally
"converge" for a shape that looked identical the whole time.

- **Net picker**: defaults to `data/input/stretchy_nets/cube.json` if present
  (`DEFAULT_NET_BASENAME`), else the first net alphabetically.
- **The "Subdivide" `LabelFrame`**: the Subdivide button plus a "Level: N"
  label (`self.subdivision_level`, 0..`MAX_LEVEL`) -- sits between "Net"
  and "Inflate" since subdividing conceptually happens before/alongside
  inflating. Greyed out once `self.positions is None` (nothing loaded
  yet) or already at `MAX_LEVEL`. `self.base_faces` (the level-0 mesh,
  fixed for the whole net session) backs the LEFT "Target faces" panel
  and its subdivision overlay at all times, regardless of the current
  level; `self.face_of_fine` is a parallel list, one entry per CURRENT
  fine face, naming which base face it came from (used for per-base-face
  coloring on both panels, rebuilt fresh by every `subdivide_once` call).
- **The "Inflate" `LabelFrame`** groups everything about running
  `relax_once`, top to bottom in the order it's used: Pressure spinner,
  then the iterate-mode radio buttons, then the Inflate/Stop buttons.
  (The net picker lives in the "Net" frame above it instead -- not an
  inflation control. There USED TO also be a "Save" button there,
  writing vertex positions/stats to a `.json` plus a PNG of the current
  view under `data/output/Save/` -- removed; see git history for
  `on_save_clicked` if this needs reviving.)
  - **"Pressure" spinner**: a user-chosen, CONSTANT pressure passed to
    `relax_once`, continuing from wherever `self.positions` currently is
    (not from scratch) -- so repeated clicks let the user watch/steer the
    shape incrementally. Default/max: `DEFAULT_PRESSURE`/`MAX_PRESSURE`
    (3.0/60.0) -- gentle by default; 60 is generous headroom above what a
    plain cube needs to stay well-behaved (see below).
  - **"Auto" button** (`on_auto_pressure_clicked` /
    `stretchy_mesh.estimate_pressure_for_target_stretch`): picks a
    pressure landing near `DEFAULT_TARGET_STRETCH_PCT` (10%) max stretch
    and applies it immediately (sets the spinner AND updates the mesh to
    that pressure's own converged shape -- not just a suggested number).
    Exists because ONE fixed default pressure is meaningless across
    different nets -- bisecting for the pressure giving ~10% stretch on
    each of the 5 Platonic solids found `pressure * total_rest_area`
    (see `_total_rest_area`) lands in a tight band (1.9-3.2) while raw
    pressure varies 12.6x (0.11-1.44) and doesn't correlate with
    vertex/face count at all. The function starts from that area-based
    geometric estimate, then refines by relaxing at that pressure and
    rescaling by (target/achieved) -- clamped to avoid a wild jump --
    up to a few times, keeping whichever trial landed closest rather
    than just the last one: the rescale assumes more pressure means more
    stretch, which is false on `three_squares.json` (a real property of
    that topology -- it stretches LESS as pressure rises), and without
    tracking the best result that case would escalate pressure forever
    chasing a target moving away from it.
  - **`stretchy_mesh._relax_force`**: a genuine mechanical force balance,
    no volume or target anywhere in it -- each edge is a Hooke's-law
    spring, each face applies a real `pressure * area * outward_normal`
    force split across its own vertices, and each edge ALSO gets a soft
    limit (`_soft_limit_stretch`) that sharply (quadratically) stiffens
    it once stretched past 2x or compressed past 0.5x its own rest
    length. The soft limit exists because plain Hooke's law alone can't
    hold pressure past a critical value: pressure's push grows with
    `area` (~length^2) while a plain spring's pull only grows linearly,
    so without it there's a real pressure above which no equilibrium
    exists at all and the mesh inflates without bound (verified directly:
    a plain cube run to convergence diverges past a few million percent
    stretch at pressure 3+ with no soft limit). `relax_once` walks small
    EXPLICIT steps along this force (see below) rather than handing it to
    a Newton-style solver, which matters for the same reason: a solver
    that re-linearizes and jumps can land on a spurious equilibrium (a
    doubled-size "solution", or a uniform implosion to near-zero volume
    that never disagrees with itself) that a genuine small-step physical
    walk starting from the same point would never reach.
  - **No orientation/fold check on the interactive Inflate loop.** An
    earlier version of `_run_inflate_stream` rejected a chunk whenever
    `stretchy_mesh.is_orientation_consistent` (the centroid-outward
    heuristic -- see its own docstring, still used by `solve_wireframe`)
    failed, on the theory that a big enough step could fold the mesh
    through itself. That heuristic false-positives on non-convex/open
    nets -- verified `data/input/stretchy_nets/two_pentagons_and_a_square.json`
    subdivided to level 1 gets flagged as "folded" even completely at
    rest, before any inflation at all. A more targeted reference-based
    replacement was tried (comparing each internal edge's own local fold
    sign against a known-good starting configuration, catching a genuine
    self-intersection independent of overall mesh shape) and correctly
    stopped flagging the at-rest false positive, but still rejected this
    net a few real steps into inflation -- tracing it showed a few of its
    folds sit nearly exactly flat at rest (a consequence of this net's
    two faces already sharing more than one edge), so a normal step can
    tip one across zero. Letting `relax_once` run to convergence with no
    check at all (rather than the check rejecting every chunk and
    reporting the pressure as unsafe) reaches a stable, sensible-looking
    result -- positive volume, reasonable stretch, force below tolerance
    -- though that one patch does stay locally self-intersecting in the
    final shape forever (verified: it never un-crosses on its own,
    however high the pressure). The user inspected the actual result
    with the check removed and was fine with it, so the check was removed
    entirely rather than kept as a safety net that was only ever refusing
    to report a passable result; `relax_once`'s own small steps (see
    above) are what actually keeps results sane now, not a post-hoc
    reject-and-retry gate.
  - **Radio buttons** control how much work one "Inflate" click does:
    "Iterate for N steps" passes `max_nfev=N` to `relax_once` (now
    literally N explicit relaxation steps); "Iterate until convergence"
    (the default) passes `max_nfev=None`, running until EITHER every
    vertex's own net force drops below `stretchy_mesh.CONVERGENCE_GTOL =
    1e-4`, OR `max_stretch_pct` stops moving for `STALL_WINDOW` steps
    (see its comment -- some meshes, e.g. a level-3-subdivided cube,
    settle into a tiny persistent numerical wobble that never crosses
    gtol even though the shape itself has visibly stopped changing) --
    picked as the default over "steps" since a large fine mesh (e.g.
    `dodecahedron_res3.json`, 1446 variables) can need many iterations
    before the shape looks settled, and there's no obvious step COUNT a
    user would otherwise know to ask for up front.
  - **Live progress, not one big jump**: `on_inflate_clicked` doesn't
    make ONE `relax_once` call for the whole request -- `_run_inflate_stream`
    calls it repeatedly in a GROWING sequence of chunks (`INFLATE_CHUNK_START
    = 5`, doubling up to `INFLATE_CHUNK_MAX = 200`), each continuing from
    the previous chunk's own final positions, pushing a "progress" message
    (redraws + bumps the iteration counter) after every chunk so the UI
    updates incrementally instead of jumping straight to the end.
    `INFLATE_SAFETY_STEP_CAP = 5000` hard-stops "until convergence" mode
    if a mesh/pressure combination genuinely never reaches
    `CONVERGENCE_GTOL`, instead of looping forever.
  - **Won't re-run once converged**: `_update_inflate_button_state`
    greys out the Inflate button whenever `self.last_stats["converged"]`
    is true, and `on_inflate_clicked` refuses to run even if clicked
    anyway, since relax_once from an already-converged point starts with
    near-zero force and has nothing left to do. Re-armed by
    `_on_pressure_changed` (a `trace_add("write", ...)` on `pressure_var`
    -- a "converged" verdict only applies to the pressure it was reached
    at) and by loading a new net; a Stop leaves `converged=False` since it
    didn't run to completion, so the button stays enabled after one.
  - **"Stop" button** sets a `threading.Event` (`self.stop_event`,
    created fresh per Inflate click) that `relax_once` checks before each
    step, aborting before starting another one rather than waiting for
    its own tolerance or the step cap -- returns whatever position was
    last reached. Disabled except while an Inflate is actually running
    (armed by `on_inflate_clicked`, disabled again by
    `_set_controls_enabled(True)` once any background job finishes --
    only `on_inflate_clicked` arms it, so it stays disabled during the
    initial cache load, which isn't usefully interruptible).
  - The bottom-of-figure annotation (`draw()`, via `fig.text` -- see
    below) shows `optimality` (the worst vertex's net force, should
    approach 0) against `CONVERGENCE_GTOL`, plus whether THIS press
    actually converged by that tolerance vs. hit the step cap (or a Stop
    request) first -- `optimality` is `None`/shown as "n/a" right after
    loading (before any Inflate press) or after a Stop, since neither
    path ran a real step to read it from.
- **Performance**: after vectorizing `_mesh_volume`/`_per_face_volumes`/
  `_face_planarity_residual` (precomputed flat index arrays -- plus, for
  the per-face case, a `np.bincount` grouping -- instead of a per-face
  Python loop with a dict lookup per vertex, built once per solve rather
  than on every single residual evaluation -- see their docstrings), a
  single `relax_once` function evaluation on `cube_res3.json` (110
  vertices, 330 variables) costs a few hundredths of a second, roughly a
  50x speedup over the original per-face-Python-loop version. Total
  wall-clock time for a full "until convergence" run still varies a lot
  by mesh size and pressure, though -- see the "Live progress" bullet
  above for how large that range gets (`dodecahedron_res3.json`'s 1446
  variables at pressure=30 is a very different proposition from
  `cube_res3.json`'s 330). `DEFAULT_STEPS = 10` predates this
  vectorization fix and is unrelated to the per-face pressure work --
  left alone since it's still a perfectly reasonable default for "Iterate
  for N steps" mode, not a stale workaround.
- **Known, accepted history**: an earlier version of this app used a
  literal random start (`stretchy_mesh.initial_relaxation`, since
  removed) with NO coarse-solve-and-drape step at all, to keep the whole
  pipeline restart-free end to end. That failed empirically: a random
  stage-1 fit for a subdivided cube net lands orientation-INCONSISTENT
  (volume ≈ -0.03 against a target of ~1.38), and applying ANY nonzero pressure
  to it made `least_squares` grind for 60-90+ seconds without returning,
  for any `max_nfev` cap tried (scipy's cap does not reliably bound
  wall-clock time on a badly-conditioned problem -- observed one case
  where `max_nfev=10` was honored in `sol.nfev`'s final reported value,
  yet the solver internally made 2068 actual calls to reach it). This is
  exactly the failure mode `_inflate`'s docstring already documents
  ("tried cold from a random point cloud... makes least_squares fail to
  converge at all") -- which is why the CURRENT design (this section)
  reintroduces the coarse solve's restart search as a precomputed,
  cached, one-time setup step, while keeping the interactive "Inflate"
  loop itself restart-free either way.
- The initial cache load runs in a background thread via `_run_background`;
  each "Inflate" click runs via the streaming variant, `_run_inflate_stream`
  (see above) -- both because either can take a while and because Tk
  isn't thread-safe, so the worker only ever pushes to a queue and the
  main thread (via a scheduled `after` poll) is the only one touching
  widgets.
- **Left panel is a real connected net, not disconnected islands**:
  `on_select_net` precomputes `self.target_layout` once via
  `src/utils/inflate_polyhedron/stretchy_net_layout.py`'s `build_stretchy_net_layout` --
  a breadth-first search over faces sharing an edge (derived directly
  from each face's own vertex-loop order, no separate combinatorics step
  needed -- unlike the now-deleted rigid pipeline's old `EdgeMap`-based
  planar embedding, which couldn't represent a stretchy mesh's
  multi-shared-edge face pairs at all; by the time that pipeline was
  removed it had stopped needing a planar embedding too, since it read
  face adjacency directly off a real `Polyhedron`'s own geometry -- see
  "Removed: the rigid-unfolding pipeline (historical)" above -- but
  multi-shared-edge face pairs still can't be laid out flat and rigid,
  which is the actual reason this stretchy path exists, not a
  representational one),
  attaching each newly-discovered face to whichever neighbor's edge found
  it first via `polygon_geom.attach_polygon` (reversed, so it unfolds
  outward -- same convention `unfoldable_polyhedron.py`'s `_build_flat_layout`
  uses for the rigid pipeline).
  A face pair sharing MORE than one edge just means extra entries that
  BFS never uses for placement (only the first edge to a still-unplaced
  face matters), same as an `edges.extra` edge would be ignored for
  layout in the rigid `.json` format. `_draw_target_faces` just reuses
  the precomputed `self.target_layout` on every redraw rather than
  recomputing the BFS each time; the per-face raw-vertex-id text label
  (e.g. "[4, 0, 2, 6]") that stood in for a real layout before is gone.
- `_draw_wireframe_result` (the right-hand 3D panel showing the CURRENT
  state) wraps `self.positions`/`self.faces` into a `Polyhedron` via
  `inflate_polyhedron.stretchy_mesh.mesh_to_polyhedron` on every redraw: `.edges`
  gives the wireframe line segments (`polyhedron.vertices[i]` is the
  position for edge endpoint `i` directly, since `mesh_to_polyhedron`
  already remapped vertex ids to `Polyhedron`'s dense index space --
  no `self.positions[...]` dict lookup needed), and `.is_closed()`
  annotates the panel title ("Wireframe result (closed)" vs "(open)") so
  it's visible at a glance whether the current shape -- coarse OR fine
  fabric mesh, mid-relax or fully settled -- is a genuinely closed solid
  yet. This is purely a rendering/reporting convenience: the solve/relax
  internals (`solve_wireframe`, `relax_once`, etc.) stay on the
  dict-keyed representation throughout, since vertices are relaxed by id
  and a mid-solve mesh isn't reliably closed or convex.

## Testing

`pytest` (from repo root, or anywhere — `pytest.ini` sets
`pythonpath = . src src/apps`, the last entry so tests can also
`from common.<module> import ...` exactly like the apps themselves do
after their own sys.path bootstrap -- currently only exercised by
`tests/unit/apps_common/test_bounding_box.py`, testing `bounding_box.py`
directly even though no current app calls it — see its own bullet under
"Directory layout" above). `tests/unit/<category>/` mirrors
`src/utils/`'s own sub-package split exactly, one test file per module:
`unit/geometry/test_polygon_geom.py`, `unit/geometry/test_polyhedron.py`
(the `Polyhedron` class in `src/utils/geometry/`), `unit/inflate_polyhedron/`
(`test_hull_to_spec.py`, `test_stretchy_mesh.py`, `test_stretchy_cache.py`,
`test_stretchy_net_layout.py`), and `unit/subdivisions/`
(`test_polygon_subdivisions.py`, `test_mesh_subdivide.py`).

(There USED TO also be a `unit/polyhedron_unfolder/` directory — one file
per module of the now-deleted rigid-pipeline package, testing
`Polyhedron`, `Hinge`/`hinge_transform`/`face_normal`/`fold_transforms`,
and `UnfoldablePolyhedron` respectively — plus `unit/persistence/` and an
`integration/` directory (`test_open_nets.py` plus `helpers.py`'s shared
`TetraNetSpec` fixture-builder). All of that was removed along with the
rest of the rigid pipeline; see "Removed: the rigid-unfolding pipeline
(historical)" above.)

The **stretchy**-pipeline suite (`unit/inflate_polyhedron/test_stretchy_mesh.py`) is slower
(~30-60s) since even the small Platonic solids run the real
`solve_wireframe` — the dodecahedron and icosahedron are deliberately kept
OUT of it (real numerical solving is slow enough on the bushiest solids
that hand verification is cheaper than paying that cost on every test
run) and verified manually instead. Includes `monkeypatch`-based tests of the orientation-consistency
failure path (forcing `_is_orientation_consistent` to always return
`False` to exercise the `ValueError`) and of the winding convention itself
(reversing one face's loop and checking `_is_orientation_consistent`
catches it). Also covers `relax_once` (the restart-free primitive
`inflate_polyhedron_app`'s interactive "Inflate" workflow is built
on -- see "The app" above), continuing from a `solve_wireframe` result
rather than a raw random start -- on the small tetrahedron and cube
(post-vectorization these are fast even at nonzero pressure; see "The
app"'s measured ~0.04-0.05s/step on a 98-vertex mesh, so cost isn't the
reason to keep tests small here anymore, just habit/consistency with the
rest of the suite). Includes a check that pressure increases stretch over
a normal working range
(`test_relax_once_pressure_increases_stretch_over_a_normal_working_range`
-- strictly increasing stretch at pressure 1/5/20 on `cube.json`).

`unit/subdivisions/test_mesh_subdivide.py` covers the fabric-subdivision pipeline (see
above): combinatorial closure of the fine mesh at several resolutions,
that shared coarse edges actually merge (not left as disconnected
per-face patches), that a pentagon face's fine edges have exactly two
distinct rest lengths (rim vs. spoke, not a uniform one), and that
`solve_fabric_mesh` produces low-stretch results for both an
already-rigid coarse net (tetrahedron) and a genuinely bendy one
(`two_pentagons_and_a_square.json`) — fast (~5s total) since the
drape-then-relax approach never needs the slow random-restart search.

`unit/inflate_polyhedron/test_stretchy_net_layout.py` covers `build_stretchy_net_layout` (see
"The app" above) across every net in `data/input/stretchy_nets/`: every face gets
placed, every placed face keeps its exact unit-edge regular-polygon shape
(rotation/translation only, no distortion), and -- reproducing the same
BFS the function itself does -- every edge the tree actually attaches
through lands its two faces' shared corners on the same two 2D points
(the ones it DOESN'T attach through, for a face pair sharing more than
one edge, are deliberately not checked -- see the module docstring for
why that's expected, not a bug).

## Conventions worth knowing before editing

- **Docstring style** (`src/utils/`, and going forward `src/apps/`): see
  `skills.md` at the repo root -- every function docstring should be
  about 4-5 lines, succinct, focused on input/output, with design
  rationale/history moved to the module-level docstring instead (module
  docstrings are NOT held to the 4-5 line limit).
- The STRETCHY pipeline's polygon edges all have length 1
  (`stretchy_mesh.EDGE_LENGTH`, capped stretch via `STRETCH_CAP`) since
  its nets are hand-authored combinatorics with no coordinates of their
  own. `polygon_geom.EDGE_LENGTH` (still 1.0) is a default used by
  `regular_polygon_vertices`/`attach_polygon`, which the stretchy
  pipeline's `stretchy_net_layout.py` calls. (The now-deleted rigid
  pipeline had no such requirement, since it read real, already-given
  coordinates straight from its `.json` specs — see "Removed: the
  rigid-unfolding pipeline (historical)" above.)
- Polygons are CCW as seen from outside the solid — `stretchy_mesh.py`'s
  module docstring has the convention for the current stretchy pipeline:
  a shared edge appears as `v -> w` in one face's loop and `w -> v` in
  the other's. (The now-deleted rigid pipeline used the exact same
  `v -> w`/`w -> v` convention in `Polyhedron.compute_face_adjacency()` —
  see "Removed: the rigid-unfolding pipeline (historical)" above — and
  `src/utils/geometry/polyhedron.py`'s current `Polyhedron` class keeps
  it too.)
- `stretchy_mesh.py`/`stretchy_cache.py` have no
  `if __name__ == "__main__"` demo blocks — that logic lives in `tests/`.
  Add new ad hoc verification as a real test, not a script block.
- (Historical: a stored "fold angle" was a rigid-pipeline-only concept —
  the rotation *from flat* rather than the dihedral angle itself, e.g.
  cube hinges rotating 90°, tetrahedron hinges rotating 109.47°. No
  fold-angle concept exists anywhere in the current codebase; see
  "Removed: the rigid-unfolding pipeline (historical)" above.)
- (Historical: rigid nets, `{"vertices": [...], "faces": [[i,j,k,...], ...]}`,
  and stretchy nets, plain vertex-id-loop lists with no coordinates —
  `data/input/stretchy_nets/*.json`, still current — used to be two
  NOT-interchangeable JSON formats that both happened to have a
  `"faces"` key. Only the stretchy format exists in this project now.)
