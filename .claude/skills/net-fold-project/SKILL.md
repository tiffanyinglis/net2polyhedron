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

## No hacky terms in the physics without explicit permission

`stretchy_mesh.py`'s force model (see "Stretchy meshes" below) has
repeatedly grown, then had removed, a term that papers over a symptom of
the CURRENT model instead of fixing its actual cause -- each time
because it "felt like it would work" in the moment, not because the user
asked for it:

- A target-volume/reference-volume pressure term, removed because it
  silently followed wherever the mesh currently was, compounding stretch
  across repeated Subdivide-then-Inflate cycles even at the same nominal
  pressure.
- A per-edge soft stretch limit (quadratic stiffening past 2x/0.5x rest
  length), added to keep pressure from having no equilibrium at all past
  a critical value, removed once `estimate_pressure_for_target_stretch`
  made calibrating an appropriate pressure per net the actual fix,
  rather than clamping a badly-chosen one after the fact.

Both were reasonable-sounding in isolation and both turned out to be the
wrong layer to fix the problem at. **Do not add a volume term, a target/
reference term, a stretch clamp, or any other term to the force model
that isn't a direct, literal physical quantity (a real spring force, a
real pressure force) without the user explicitly asking for it first** --
if a pressure/stretch/convergence problem shows up, explain the actual
cause and propose the fix (including a new term, if one is genuinely
warranted) rather than silently adding one to make a symptom go away.

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
  part of the project. No solve cache (removed along with `solve_wireframe`
  itself, see "Stretchy meshes" below) — every net's starting
  configuration is now a cheap random start plus a live-in-the-UI spring
  relax (the "Relax" button, "Level 0"), not a precomputed/cached search.

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
  - `app.py` — entry point, class `InflatePolyhedronApp`. No `cache/`
    or `build_cache.py` any more (removed along with `solve_wireframe`
    and `stretchy_cache.py`, see "Stretchy meshes" below) — nothing here
    is precomputed ahead of time.
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
  There USED TO also be a `generate_subdivided_stretchy_nets.py` here,
  writing fixed-resolution fabric-mesh `.json` variants via
  `mesh_subdivide.subdivide_mesh`/`solve_fabric_mesh` — DELETED along with
  `solve_wireframe` and the rest of that pipeline (see "Stretchy meshes"
  below): nothing reads a fabric file's baked-in fine mesh any more, only
  its `coarse_faces` (`mesh_subdivide.load_fabric_spec`, still kept), so
  there's nothing left worth generating that format for.
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
  mesh pipeline: solving and flat net layout (this used to be split across
  `geometry2d/` [the stretchy half], `geometry3d/`, and `persistence/` —
  merged into one package since none of it is shared with `subdivisions`,
  only with itself). Modules: `stretchy_mesh.py`, `hull_to_spec.py`,
  `stretchy_net_layout.py`. No disk caching any more — `checksums.py` and
  `stretchy_cache.py` were DELETED along with `solve_wireframe` (see
  "Stretchy meshes" below): a cache existed to avoid re-running
  `solve_wireframe`'s expensive random-restart search on every net
  selection, and nothing here does that kind of search any more.
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
    relax_initial_configuration, random_initial_positions, relax_once,
    mesh_to_polyhedron, polyhedron_from_vertices, build_stretchy_net_layout`
    (not `Polyhedron` itself, which lives in `utils.geometry` now -- see
    its own bullet above).
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
project anymore, and it's also the direct ancestor of the orientation
concern the stretchy pipeline's own `_orientation_signs`/
`_is_orientation_consistent` check a different way (see "The
starting-configuration algorithm" under "Stretchy meshes" below), since a
stretchy mesh has no coordinates-first shortcut available to it. Because
nothing was left to solve for, the rigid pipeline was fast even for its
bushiest net (~0.07s for a 32-face, 31-hinge truncated icosahedron) and
needed no on-disk cache at all. Neither does the stretchy pipeline any
more, now that `solve_wireframe` (the one genuine numerical optimization
it used to run) is gone -- see "The starting-configuration algorithm"
below.

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

### The starting-configuration algorithm (`random_initial_positions` + `relax_initial_configuration`)

Replaced an earlier `solve_wireframe` (a random-restart-plus-inflation-ramp
`least_squares` search, with its own on-disk cache to avoid re-running it)
entirely -- DELETED along with `stretchy_cache.py`/`checksums.py` and
`inflate_polyhedron_app`'s `build_cache.py`/`cache/` -- see git history
around this section if any of that machinery's own reasoning is ever
needed again. The replacement is deliberately simpler and more general,
inspired by ordinary force-directed graph layout:

1. **`random_initial_positions(faces, spread=INITIAL_RANDOM_SPREAD, seed=0)`**
   -- an independent uniform-random point in `[-spread/2, spread/2]^3` for
   every vertex. Deliberately NOT a meaningful embedding (doesn't even
   look at `edge_length`) -- just noise spread out enough for the next
   step to pull into a well-separated 3D shape on its own.
2. **`relax_initial_configuration(positions, faces, edge_length, ...)`**
   -- pulls that noise into a well-separated shape using PURE spring
   forces only (`_spring_only_force`: the same per-edge Hooke's-law term
   `_relax_force` uses, with no pressure and no planarity) -- no volume,
   no target, no random restarts. Faces are free to cross each other and
   the result can land anywhere in space at any scale (nothing here
   constrains overall position or keeps non-adjacent vertices apart) --
   the only goal is a well-separated, edge-length-plausible starting point
   to hand off to `relax_once`'s real per-face pressure model afterward.
   Any view of this result must derive its own camera framing from its
   actual bounding box (see `_draw_level_panel` in "The app" below)
   rather than assuming it lands near the origin.
   - **Why the mesh must already be triangulated first.** A plain
     polyhedron wireframe (e.g. a cube's own 12 edges, no face diagonals)
     is a flexible MECHANISM under springs alone, not a rigid structure --
     exactly like an unbraced rectangular frame. Fan-triangulating first
     (`mesh_levels.subdivide_once` at level 0 -- see "The app" below for
     why Level 0 and Level 1 share this exact topology) adds the diagonal
     bracing a spring relaxation needs to settle into a well-defined 3D
     shape at all.
   - **Orientation is NOT guaranteed consistent.** Nothing in a pure
     spring force cares which way a face's normal points, so the result
     lands globally inside-out about as often as right-side-out. A
     UNIFORMLY inverted result is fixed for free: reflecting every vertex
     through the mesh's own centroid (`pts = 2*centroid - pts`) is an
     isometry (preserves every edge length/stretch stat) that flips every
     face's outward-from-centroid sign AT ONCE (see `_orientation_signs`)
     -- so a consistent wrong answer becomes a consistent right one at no
     cost. A genuinely MIXED result (some faces each way -- verified this
     happens too, e.g. roughly half the time for an octahedron across
     seeds) can't be fixed this cheaply and is returned as-is, by explicit
     user decision: `relax_once`'s subsequent pressure model is trusted to
     work it out rather than adding a retry-a-different-seed loop here.

`_orientation_signs`/`_is_orientation_consistent` (and their public
wrappers `is_orientation_consistent` etc.) are still exactly what they
were before -- general orientation-checking utilities, just no longer
built around `solve_wireframe`'s own random-restart search.

### Fabric subdivision (REMOVED -- `src/utils/subdivisions/mesh_subdivide.py` now holds only `load_fabric_spec`)

This used to be a whole file-generation feature: `subdivide_mesh` split a
coarse net's faces into a fine triangular "fabric" mesh, `solve_fabric_mesh`
draped it over a `solve_wireframe`-solved coarse shape, and
`src/apps/common/generate_subdivided_stretchy_nets.py` wrote the result out
as a fixed-resolution `data/input/stretchy_nets/<name>_res<resolution>.json`
(e.g. the now-deleted `cube_res3.json`) for `inflate_polyhedron_app`'s old
cache to pick up. **All of that was DELETED** once `solve_wireframe` itself
was (see "The starting-configuration algorithm" above): the app no longer
reads a fabric file's baked-in fine mesh at all -- see "The app" below --
so generating one served no purpose left. See git history around this
section (and `solve_fabric_mesh`'s own former docstring) if a from-scratch
fine-fabric-mesh generator is ever wanted again; it would need its own
starting-configuration strategy now, not a resurrected `solve_wireframe`.

**What's left**: `mesh_subdivide.load_fabric_spec(path)` still reads the
`"coarse_faces"`/`"resolution"`/`"face_of_fine"` fields a legacy
fabric-subdivided `.json` may carry alongside its ordinary `"faces"` --
`inflate_polyhedron_app`'s `on_select_net` still calls it to detect such a
file and use ITS `coarse_faces` as the net's own base faces (ignoring the
file's pre-baked fine mesh entirely). No shipped net under
`data/input/stretchy_nets/` currently has this field, so this path is
currently untested by real data -- kept only because it doesn't depend on
anything else being removed and a hand-authored file could still use it.

### The app (`inflate_polyhedron_app`) — random start, relax, subdivide and inflate interactively from there

Rewritten several times -- see git history if the reasoning below seems
oddly specific -- from an original "pick a net, see the one
automatically-solved answer" design, through a "precomputed
fixed-resolution fabric mesh, interactive from there" design (the
fabric-subdivided `.json` format, `generate_subdivided_stretchy_nets.py`,
and `mesh_subdivide.solve_fabric_mesh`'s drape were built for THAT design
-- see "Fabric subdivision" above, now removed), into the CURRENT one:
every net starts as "Level 0" -- a random start on its own fan-triangulated
topology (see "The starting-configuration algorithm" above) -- and a
"Relax" button turns that into Level 1's actual starting shape; from
there, the "Subdivide" button (`utils.inflate_polyhedron.mesh_levels.subdivide_once`)
refines it interactively, one nested level at a time, so any inflation
already done at one level carries forward as the next level's starting
point. A legacy fabric-subdivided file (one with baked-in
`"coarse_faces"`) still loads fine -- `on_select_net` just uses ITS OWN
`coarse_faces` as the base faces for this same random-start-then-relax
flow, ignoring its pre-baked fine mesh entirely. The steps, in order:

1. **Level 0: random start** -- on selecting a net, `on_select_net`
   fan-triangulates its base faces (`mesh_levels.subdivide_once` at level
   0 -- this is exactly Level 1's own topology too, see below) and calls
   `random_initial_positions` for a fresh random start. Cheap enough
   (no numerical solve at all) to happen synchronously, so there's no
   background thread or cache for this step any more.
2. **"Relax" (Level 0 only)** -- runs `relax_initial_configuration` to
   convergence (see "The starting-configuration algorithm" above),
   streamed in growing chunks the same way "Inflate" is (see "Live
   progress" below). Once it converges, the result is PROMOTED straight
   into Level 1's starting position -- a pure relabeling
   (`self.subdivision_level = 1`), not a new `subdivide_once` call, since
   Level 0 and Level 1 already share the exact same fan-triangulated
   `self.faces`/`self.face_of_fine`/`self.edge_length`. A tangled (mixed
   face-orientation) result is possible and deliberately NOT retried --
   the subsequent Inflate/pressure step is expected to work it out (see
   "The starting-configuration algorithm" above).
3. **Subdivide** (`mesh_levels.subdivide_once`, see its own module
   docstring) -- one press refines the CURRENT mesh by one level: a
   "triforce" quarter of every triangle, up to `MAX_LEVEL` (3), where the
   button greys out. New POSITIONS are linearly interpolated from the
   current mesh's own nearby points (so already-inflated detail
   survives); new REST LENGTHS are derived analytically from the flat,
   unit-edge reference geometry (exact halving/midsegment-theorem lengths
   for a quarter), independent of the current (possibly already
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
  `relax_once`, top to bottom in the order it's used: the "Target RMS
  stretch" spinner, then the iterate-mode radio buttons, then the
  Inflate/Stop buttons. (The net picker lives in the "Net" frame above it
  instead -- not an inflation control. There USED TO also be a "Save"
  button there, writing vertex positions/stats to a `.json` plus a PNG of
  the current view under `data/output/Save/` -- removed; see git history
  for `on_save_clicked` if this needs reviving. There USED TO also be a
  separate "Auto" button and a Pressure readout label -- removed once
  "Inflate" itself started calibrating pressure, and once the
  Convergence History table started showing it per level, respectively;
  see git history for `on_auto_pressure_clicked`/`_on_auto_pressure_done`
  if a standalone calibrate-without-inflating action is wanted again.)
  - **Pressure is NOT user-editable** -- `self.pressure_value` (a plain
    attribute, with no dedicated display of its own; it's logged per
    level in the Convergence History table instead) is only ever set by
    `on_inflate_clicked`'s own calibration phase (see below), fresh on
    EVERY click, since there's no longer a separate action that sets it
    once for the user to reuse.
  - **"Target RMS stretch" spinner** (`self.target_rms_var`, % of rest
    edge length, default `DEFAULT_TARGET_RMS_STRETCH_PCT` = 8.0) --
    user-editable; feeds `on_inflate_clicked`'s calibration call into
    `estimate_pressure_for_target_stretch` as `target_rms_pct`.
  - **`on_inflate_clicked` calibrates pressure before inflating**: phase
    1 runs `stretchy_mesh.estimate_pressure_for_target_stretch` (in the
    background, via `_run_background`) to find a pressure landing near
    the "Target RMS stretch" spinner's value from wherever
    `self.positions` currently is; phase 2 (`_on_pressure_calibrated`)
    takes JUST the resulting pressure number (calibration's own trial
    positions are discarded, not applied to `self.positions`) and feeds
    it into the normal streamed `_run_inflate_stream`, so the
    steps-vs-convergence radio mode and the Stop button behave exactly
    as before -- calibration only decides WHAT pressure to use, it
    isn't itself the inflation. Targets RMS stretch specifically (not
    max) -- on a regular Platonic solid the two coincide (every edge
    stretches equally), but an irregular or subdivided mesh stretches
    unevenly and RMS is the metric the spinner actually asks for.
    Calibration exists because ONE fixed default pressure is meaningless
    across different nets -- bisecting for the pressure giving ~10%
    stretch on each of the 5 Platonic solids found `pressure *
    total_rest_area` (see `_total_rest_area`) lands in a tight band
    (1.9-3.2) while raw pressure varies 12.6x (0.11-1.44) and doesn't
    correlate with vertex/face count at all. The function starts from
    that area-based geometric estimate, then refines by relaxing at that
    pressure and rescaling by (target/achieved) -- clamped to avoid a
    wild jump -- up to a few times, keeping whichever trial landed
    closest rather than just the last one: the rescale assumes more
    pressure means more stretch, which is false on `three_squares.json`
    (a real property of that topology -- it stretches LESS as pressure
    rises), and without tracking the best result that case would
    escalate pressure forever chasing a target moving away from it.
  - **`stretchy_mesh._relax_force`**: a genuine mechanical force balance,
    no volume or target anywhere in it -- each edge is a Hooke's-law
    spring, each face applies a real `pressure * area * outward_normal`
    force split across its own vertices. `relax_once` walks small
    EXPLICIT steps along this force (see below) rather than handing it to
    a Newton-style solver: a solver that re-linearizes and jumps can land
    on a spurious equilibrium (a doubled-size "solution", or a uniform
    implosion to near-zero volume that never disagrees with itself) that
    a genuine small-step physical walk starting from the same point would
    never reach. Plain Hooke's-law springs genuinely can't hold pressure
    past a critical value (pressure's push grows with `area` ~
    length^2, a spring's pull only grows linearly, so past some pressure
    there's no equilibrium at all and the mesh inflates without bound) --
    a per-edge soft stretch limit was tried here to force an equilibrium
    to exist at any pressure, and removed again once
    `estimate_pressure_for_target_stretch` (below) made the actual fix
    available: calibrate an appropriate pressure per net up front, rather
    than clamp a badly-chosen one after the fact. **Do not re-add a term
    like this (or a volume/target term, per the compounding-across-
    Subdivide bug they caused earlier in this project's history) without
    the user explicitly asking for it** -- both were tried, both work
    around a symptom instead of the actual cause, and both were removed
    once a better fix existed.
  - **No orientation/fold check on the interactive Inflate loop.** An
    earlier version of `_run_inflate_stream` rejected a chunk whenever
    `stretchy_mesh.is_orientation_consistent` (the centroid-outward
    heuristic -- see its own docstring, also used by
    `relax_initial_configuration`'s free flip fix) failed, on the theory
    that a big enough step could fold the mesh
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
  - **Convergence History's checkmark tracks the algorithm's own
    `converged` flag, not a fresh `optimality < CONVERGENCE_GTOL`
    comparison redone in the table.** `_explicit_relax_loop` (shared by
    `relax_once`/`relax_initial_configuration`) can declare convergence
    via EITHER of two criteria -- the worst vertex's force below
    `CONVERGENCE_GTOL`, or `max_stretch_pct` stalled for `STALL_WINDOW`
    steps (see its own comment) -- so a stall-converged result can still
    show `optimality` numerically ABOVE `CONVERGENCE_GTOL` even though
    the algorithm is genuinely done; recomputing the checkmark from that
    comparison alone would then wrongly show a cross on a run that
    actually converged and visibly looks fine. `_refresh_history_table`
    stores/uses the real `converged` boolean instead, with the numeric
    comparison kept alongside for reference. The mark itself is a plain
    ✔/✘ (not a colored emoji, which ttk doesn't reliably render in
    color) whose color comes from a per-ROW Treeview tag
    (`"converged"`/`"not_converged"`, `foreground=STATUS_COLORS["success"/"error"]`)
    -- ttk.Treeview can only tint a whole row, not one cell, so the
    Convergence column's color choice ends up applied to that row's
    other columns too.
  - **Level 0's history row has no target/pressure to speak of.**
    `relax_initial_configuration` is pure springs -- no pressure
    parameter, no target RMS stretch to calibrate toward -- so its row
    shows `pressure` as `"n/a"` (`_record_level_history` stores `None`
    for `subdivision_level == 0`) and its RMS Stretch % cell omits the
    `"(target: N)"` suffix every other level's row has. The target
    itself, when shown, uses one decimal place (`{target_rms_pct:.1f}`),
    matching the "Target RMS stretch" spinner's own `format="%.1f"`.
  - **Won't re-run once converged**: `_update_level_action_buttons`
    (see the single-action-button bullet below) turns the button into
    "Subdivide"/"DONE!" once `self.last_stats["converged"]` is true, and
    `on_inflate_clicked` refuses to run even if invoked anyway, since
    relax_once from an already-converged point starts with near-zero
    force and has nothing left to do. Re-armed by `_on_target_rms_changed`
    (a `trace_add("write", ...)` on `target_rms_var` -- a "converged"
    verdict only applies to the target it was reached at, and pressure is
    recalibrated fresh every click anyway) and by loading a new net; a
    Stop leaves `converged=False` since it didn't run to completion, so
    the button goes back to "Inflate"/"Relax" after one.
  - **"Stop" button** sets a `threading.Event` (`self.stop_event`,
    created fresh per Inflate/Relax click) that the relax loop checks
    before each step, aborting before starting another one rather than
    waiting for its own tolerance or the step cap -- returns whatever
    position was last reached. Only active while a run is in progress (see
    `_set_level_action_button_running` below).
  - There USED TO be a bottom-of-figure annotation (`draw()`, via
    `fig.text`) repeating the current level/iteration/stretch/optimality
    numbers under the plots -- removed as redundant once the
    Convergence History table already showed all of it per level.
- **Performance**: after vectorizing `_mesh_volume`/`_per_face_volumes`
  (precomputed flat index arrays -- plus, for the per-face case, a
  `np.bincount` grouping -- instead of a per-face Python loop with a dict
  lookup per vertex, built once per call rather than on every single
  force evaluation -- see their docstrings), a single `relax_once`
  function evaluation on a level-3-subdivided mesh (hundreds of
  variables) costs a few hundredths of a second, roughly a 50x speedup
  over the original per-face-Python-loop version. Total wall-clock time
  for a full "until convergence" run still varies a lot by mesh size and
  pressure, though -- see the "Live progress" bullet above for how large
  that range gets. `DEFAULT_STEPS = 10` predates this vectorization fix
  and is unrelated to the per-face pressure work -- left alone since it's
  still a perfectly reasonable default for "Iterate for N steps" mode,
  not a stale workaround.
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
- **Debug mode vs. release mode -- ONE difference only.** `self.debug_mode`
  (starts `False` -- release mode, the one meant for an actual user, is
  what a session starts in) toggles via the "d" key
  (`root.bind_all("<KeyPress-d>", self._on_toggle_debug_mode)` --
  `bind_all` rather than `bind` so it fires regardless of which widget
  has focus; safe here since nothing in this app is a free-text field a
  stray "d" could collide with) and sets the window title to "Inflate
  Polyhedron (debug mode)" or plain "Inflate Polyhedron". The two modes
  used to have substantially different layouts (a whole separate set of
  "Net"/"Subdivide"/"Inflate" frames for debug, a "Sync rotation"
  checkbox only in one mode, workflow enforcement only in the other,
  the green "success" message only suppressed in one) -- ALL of that was
  deliberately unified away at the user's request, down to the ONE thing
  that's actually still allowed to differ: whether "Iterate for N steps"
  is offered at all. `_apply_mode_visibility` is now just:
  ```python
  if self.debug_mode:
      self.mode_row.pack(fill=tk.X, pady=(8, 0))
  else:
      self.mode_row.pack_forget()
      self.iterate_mode_var.set("convergence")
  ```
  Everything else below applies identically regardless of `self.debug_mode`
  -- don't reintroduce a mode check into any of it without the user
  explicitly asking for a new difference between the two modes.
  - **One "Setup" frame** (net picker + target RMS spinner --
    `self.combo`/`self.target_rms_var`, single widgets now, no more
    debug/release duplicates) always visible, with `self.mode_row` (the
    steps-vs-convergence radio choice) as the one part that shows/hides
    per mode.
  - **ONE action button per "Level N" panel, below it only -- no button
    above.** `self.level_action_buttons` is a single `{level: ttk.Button}`
    dict spanning `range(0, MAX_LEVEL + 1)` (Level 0 included), packed
    into its level's frame BEFORE the canvas with `side=tk.BOTTOM`
    (packing it AFTER the canvas, which has `expand=True`, would starve
    it of space entirely, since the canvas would already have claimed
    the whole remaining cavity by the time a later-packed sibling asks
    for its share). `_update_level_action_buttons` is the single source
    of truth for what it shows: only the current frontier level's button
    is ever enabled, cycling **"Relax"** (Level 0 only) or **"Inflate"**
    (Level 1+, idle) -> **"Stop"** (a run in progress, see
    `_set_level_action_button_running` below) -> **"Subdivide"**
    (converged, clickable, advances to the next level) or **"DONE!"**
    (converged at `MAX_LEVEL`, nothing further to subdivide to, so left
    disabled) -- every other level's button is just disabled, left
    however it last read when the user moved on from it. This replaced
    an earlier two-button-per-level design (a top Inflate/Relax button
    plus a bottom Subdivide button or "DONE!"/blank label) at the user's
    explicit request to consolidate down to one control, always below.
  - **No separate Stop button, in either mode.** The CURRENT frontier
    level's own action button turns into the Stop control for the
    duration of a run (`_set_level_action_button_running(True)`, called
    from `_on_pressure_calibrated`/`on_relax_clicked`) -- text and
    `command` both swap (to `self.on_stop_clicked`) while running, and
    `_set_level_action_button_running(False)` (called from
    `_finish_inflate`/`_finish_relax`) delegates back to
    `_update_level_action_buttons` to restore its normal state
    afterward. `_set_controls_enabled`'s disabled branch deliberately
    leaves the frontier level's button alone (every other level's stays
    disabled as normal) so it's still clickable as Stop.
  - **No "Sync rotation" choice at all -- rotation is just always
    synced**, in both modes. There's no checkbox or variable for it:
    every level panel shares ONE camera angle
    (`self.level_azim`/`self.level_elev`) -- a drag on any panel updates
    it and re-renders every panel from it (`_on_level_motion` ->
    `_render_all_level_panels`), and `draw()` always renders every panel
    from that same shared state too, so a level just revealed by
    Subdivide inherits whatever view the others are already at rather
    than starting at some default one.
  - **The "success" (green) status message is always suppressed**
    (`_set_status`: `if kind == "success": text = ""`) -- e.g. "Converged
    after N steps..." -- since the per-level button states, the green
    "DONE!" label, and the Convergence History table already show that;
    other kinds (info/warn/error) still show, since those carry feedback
    while something's running or has gone wrong rather than just
    repeating what's already visible elsewhere.
  - `on_inflate_clicked`/`on_subdivide_clicked` are shared by both modes
    -- every per-level button is wired to the exact same callback
    (there's no per-level branching inside them), since only the current
    frontier level's button is ever enabled anyway, so "which one was
    clicked" never actually varies.
  - Status/progress (`self.progress`/`self.status_var`) and the
    Convergence History table were already shared before the
    unification and still are -- placed once, always visible.
- **Every "Level N" panel renders via PyVista/VTK, not matplotlib --
  only "Net" is still matplotlib.** Tried on Level 0 alone first (its
  mesh is the one guaranteed non-convex/self-intersecting case, a
  random-start-then-relax result), then applied to every level at the
  user's request once it looked right. The reason: a mesh here is
  routinely self-intersecting or non-convex -- not just Level 0's own
  starting point, but ANY level mid-relax or mid-inflate before pressure
  has had a chance to round it out -- which neither mplot3d's own
  painter's-algorithm depth sort nor this app's OLD `_CullableFace`
  (exact normal-based culling, valid only for a closed CONVEX solid --
  see its own docstring, still on the untouchable-files list but no
  longer imported by this app) could draw correctly: occluded faces
  would wrongly show through. PyVista gives a real GPU depth buffer
  instead, which handles arbitrary triangle soups correctly regardless
  of convexity or face count -- no per-face visibility object to build
  at all, unlike the old one-`_CullableFace`-per-face approach.
- **Rendered off-screen to a plain image, not a live interactive VTK
  widget.** Each level panel is a `pv.Plotter(off_screen=True,
  window_size=LEVEL_PANEL_SIZE)` (`self.level_plotters[level]`) whose
  `.screenshot(return_img=True)` result gets wrapped in a
  `PIL.ImageTk.PhotoImage` and set on a plain `tk.Label`
  (`self.level_labels[level]`) -- keeps this app on ONE interaction
  toolkit (Tkinter) rather than also embedding VTK's own
  widget/event-loop integration. `self.level_photos[level]` holds the
  live `PhotoImage` reference -- required, since Tk drops (blanks) an
  image whose only reference gets garbage-collected. `LEVEL_PANEL_SIZE =
  (320, 450)` matches the Net panel's matplotlib `figsize=(3.2, 4.5)` at
  ~100dpi, so every panel is the same size.
- **Building the mesh** (`_draw_level_panel`): faces are always
  triangles from Level 0 on (see "The algorithm" above), so unlike the
  old `_draw_wireframe_panel` there's no fan/n-gon handling needed.
  Builds ONE `pv.PolyData` for the whole mesh with per-CELL RGB color
  scalars (`mesh.cell_data["colors"]`, from `face_of_fine` indexing the
  same per-base-face `self.colors` the Net panel uses) and ONE
  `add_mesh(..., scalars="colors", rgb=True, show_edges=True)` call --
  a single draw call handles occlusion, face coloring, AND edges
  together, which is what replaces the old per-face `_CullableFace` loop
  plus a separate `Line3DCollection` wireframe-overlay fallback.
- **Camera**: parallel (orthographic) projection, not perspective, to
  match fixed-axis-limit framing with no foreshortening -- the closest
  equivalent PyVista offers to what `ax.set_xlim/ylim/zlim` gave the old
  matplotlib panels. `_render_level_pv` derives the camera direction from
  the SHARED `self.level_azim`/`self.level_elev` (see the rotation
  bullet below) and the distance/`parallel_scale` from THIS level's own
  bounding box (`self._level_center[level]`/`self._level_half[level]`,
  set by `_draw_level_panel` -- necessary since neither a pure-spring
  relax nor a pressure inflation has any mechanism keeping the result
  near the origin or at a familiar scale). `parallel_scale` needs an
  aspect-ratio correction (multiply by `panel_height/panel_width` when
  portrait, as this panel is) since it only directly controls the
  vertical half-height -- left uncorrected, the shape's WIDER dimension
  gets cropped on a portrait-shaped panel; `LEVEL_ZOOM_FILL` (0.6) then
  shrinks the shape within that guaranteed-fitting frame, per user
  request (the un-zoomed framing looked too large/cropped).
  `WIREFRAME_VIEW_FILL` (0.8) is a separate, earlier zoom factor folded
  into `self._level_half` itself, kept from the original matplotlib
  version's tuning.
- **Title text must be added as a plain, explicitly centered text actor,
  not a named "upper_edge" position.** `add_text(..., position="upper_edge")`
  returns a `vtkCornerAnnotation`, which despite the name renders
  LEFT-justified starting AT the horizontal center -- visibly off-center
  to the right, not centered. The fix: `add_text(f"Level {level}",
  position=(0.5, 0.92), viewport=True, name="level_title")` followed by
  `title_actor.GetTextProperty().SetJustification(vtk.VTK_TEXT_CENTERED)`
  -- a plain text actor at a normalized-viewport position, explicitly
  told to center itself on that point, which is what a matplotlib
  `ax.set_title()` gives for free and this had to be reproduced by hand.
- **Rotation sync, one shared angle across every panel.** No "Sync
  rotation" checkbox (see its own bullet above) -- `self.level_azim`/
  `self.level_elev` are single, SHARED floats, not per-level state. A
  left-click-drag on ANY level panel's Label (`_on_level_drag_start`/
  `_on_level_motion`/`_on_level_drag_end`, plain Tkinter mouse bindings
  reimplementing what mplot3d's own drag-to-rotate gave the old panels
  for free) updates them by the drag delta (`LEVEL_DRAG_SENSITIVITY`
  degrees per pixel, elevation clamped to ±89° to avoid flipping through
  the poles) and calls `_render_all_level_panels()`, which re-renders
  EVERY level's plotter from the same updated angle -- a direct
  recomputation from shared state each time, not a relative nudge
  copied panel-to-panel, so every panel always agrees exactly.

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
(`test_hull_to_spec.py`, `test_stretchy_mesh.py`, `test_mesh_levels.py`,
`test_stretchy_net_layout.py`), and `unit/subdivisions/`
(`test_polygon_subdivisions.py`). (There USED TO also be `test_stretchy_cache.py`
and `test_mesh_subdivide.py` -- DELETED along with `stretchy_cache.py`/
`checksums.py` and `mesh_subdivide.py`'s `subdivide_mesh`/`solve_fabric_mesh`,
see "Stretchy meshes" below.)

(There USED TO also be a `unit/polyhedron_unfolder/` directory — one file
per module of the now-deleted rigid-pipeline package, testing
`Polyhedron`, `Hinge`/`hinge_transform`/`face_normal`/`fold_transforms`,
and `UnfoldablePolyhedron` respectively — plus `unit/persistence/` and an
`integration/` directory (`test_open_nets.py` plus `helpers.py`'s shared
`TetraNetSpec` fixture-builder). All of that was removed along with the
rest of the rigid pipeline; see "Removed: the rigid-unfolding pipeline
(historical)" above.)

The **stretchy**-pipeline suite (`unit/inflate_polyhedron/test_stretchy_mesh.py`)
is fast now (a couple of seconds total) -- it used to run the real,
genuinely slow `solve_wireframe` search (deliberately keeping the
dodecahedron/icosahedron OUT of it and verifying those by hand instead),
but that function is gone; wherever a test just needs SOME concrete,
non-degenerate positions to work with, `_relaxed_positions` (a small
helper in the test file itself) builds them via the same
`random_initial_positions`-plus-`relax_initial_configuration` pipeline
the app now uses for its own starting configuration. Includes a test of
the winding convention itself (reversing one face's loop and checking
`_is_orientation_consistent` catches it). Also covers `relax_once` (the
restart-free primitive `inflate_polyhedron_app`'s interactive "Inflate"
workflow is built on -- see "The app" above) on the small tetrahedron and
cube, and a check that pressure increases stretch over a normal working
range (`test_relax_once_pressure_increases_stretch_over_a_normal_working_range`
-- strictly increasing stretch at pressure 0.1/0.3/0.8 on `cube.json`).

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
- `stretchy_mesh.py` has no `if __name__ == "__main__"` demo block --
  that logic lives in `tests/`. Add new ad hoc verification as a real
  test, not a script block.
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
