---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (the src/utils library, .json/.fold formats, the fold solver, the stretchy-mesh solver, the Tkinter apps in src/apps, tests). Load before making non-trivial changes to this repo instead of re-deriving the pipeline by re-reading every file.
---

# Polyhedron net-folding project

## Untouchable files

These files are considered DONE -- the user has finished them and
deliberately doesn't want them touched, since editing them (even
additively) risks messing up code structure they've already settled on:

**As of the start of work on `src/apps/interactive_builder_app/` (a new,
unrelated shape-placement app -- see "Interactive builder" below), the
user marked EVERY file that already existed in the project untouchable,
wholesale.** The per-file annotations below (mostly about the
polyhedron-unfolder sync/deletion history) predate that wholesale marking
and are kept only as historical context for WHY each file looks the way
it does -- not as a signal that some of these are more untouchable than
others. The list:

- `src/utils/geometry/polygon_geom.py`
- `src/utils/geometry/polyhedron.py` (`Polyhedron`: pure 3D solid geometry
  -- shared, indexed vertices; CCW faces; derived `.edges`; `.face_vertices()`,
  `.face_normal()`, `.is_closed()`, `.compute_face_adjacency()`. Ported over
  from the sibling `polyhedron-unfolder` project's own `Polyhedron`, with
  `face_normal` inlined rather than imported from a fold engine, since this
  project doesn't have one.)
- `src/utils/geometry/__init__.py`
- `src/utils/inflate_polyhedron/__init__.py`
- `src/utils/inflate_polyhedron/hull_to_spec.py`
- `src/utils/inflate_polyhedron/mesh_levels.py`
- `src/utils/inflate_polyhedron/stretchy_mesh.py`
- `src/utils/inflate_polyhedron/stretchy_net_layout.py`
- `src/utils/subdivisions/__init__.py`
- `src/utils/subdivisions/polygon_subdivisions.py`
- `src/utils/subdivisions/mesh_subdivide.py`
- `src/utils/__init__.py`
- `src/apps/ui/tooltip.py`
- `src/apps/ui/cullable_face.py`
- `src/apps/ui/__init__.py`
- `src/apps/common/bounding_box.py`
- `src/apps/common/ui_theme.py`
- `src/apps/common/paths.py`
- `src/apps/common/__init__.py`
- `src/apps/polygon_subdivision_app/app.py`
- `src/apps/inflate_polyhedron_app/app.py`
- `data/input/stretchy_nets/*.json` (every shipped net)
- `docs/README.md`
- `docs/algorithm.md`
- `.gitignore`
- `requirements.txt`
- `pytest.ini`
- `.claude/settings.local.json`
- `.claude/skills/net-fold-project/SKILL.md` (this file)
- `tests/run_tests.py`
- `tests/unit/apps_common/test_bounding_box.py`
- `tests/unit/geometry/test_polygon_geom.py`
- `tests/unit/geometry/test_polyhedron.py`
- `tests/unit/inflate_polyhedron/test_hull_to_spec.py`
- `tests/unit/inflate_polyhedron/test_mesh_levels.py`
- `tests/unit/inflate_polyhedron/test_stretchy_mesh.py`
- `tests/unit/inflate_polyhedron/test_stretchy_net_layout.py`
- `tests/unit/subdivisions/test_polygon_subdivisions.py`

**Exceptions actually made to the wholesale marking, so far, each ONLY
because a specific user request could not be satisfied any other way**
(not a signal that the marking has loosened generally -- still ask, or
look for a change already made this way, before touching any of the
files above for a NEW reason): `stretchy_mesh.py` (+ its test +
`docs/README.md`), to let a stretchy mesh stay OPEN rather than
requiring a closed 2-manifold -- see "Stretchy meshes" below; and
`inflate_polyhedron_app/app.py`, to make its "Net" panel show a net
saved by `interactive_builder_app` at the EXACT flat arrangement it was
saved at, when that file has one, rather than always re-deriving a
fresh BFS spanning-tree layout -- see `_layout_from_net_layout` in the
"Interactive builder" section below.

(The `polygon_subdivision_app`/`utils/subdivisions/` entries above are
NOT part of the polyhedron-unfolder sync described below -- they're this
project's own polygon-subdivision demo, considered separately finished
and settled by the user. Most of the rest of this list is synced from the
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
behavior.)

Do not read these as a target for changes and do not modify them --
adding, removing, or "just cleaning up" anything in them is off limits --
UNLESS the user explicitly asks for a change to one of these files BY
NAME or by unambiguous description in their current request. If a task
would otherwise require touching one, stop and explicitly ask the user
for permission first, naming the file and what change is needed, rather
than proceeding or silently working around it. This list is expected to
grow -- check it before editing anything in this project, including
whatever gets newly added for `interactive_builder_app` itself, once the
user considers a given piece of it finished.

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

Three Tkinter entry points currently live in this project (a fourth,
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
- `interactive_builder_app` (`src/apps/interactive_builder_app/app.py`) —
  a 2D shape-placement canvas, unrelated to solving anything: pick a
  regular polygon (triangle..8-gon) from a left-side palette, click to
  drop instances of it into a pan/zoomable drawing area, drag/select/
  delete them. See "Interactive builder" below.

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
three folders below exist now.)
- `inflate_polyhedron_app/` — the stretchy-mesh viewer (see "Stretchy meshes" below)
  - `app.py` — entry point, class `InflatePolyhedronApp`. No `cache/`
    or `build_cache.py` any more (removed along with `solve_wireframe`
    and `stretchy_cache.py`, see "Stretchy meshes" below) — nothing here
    is precomputed ahead of time.
- `polygon_subdivision_app/` — 2D-only fine-triangle-mesh demo (see below), no cache
  - `app.py` — entry point, class `PolygonSubdivisionApp`
- `interactive_builder_app/` — 2D shape-placement canvas, unrelated to
  solving/folding (see "Interactive builder" below), no cache
  - `app.py` — entry point, class `InteractiveBuilderApp`
- `common/` — helpers SHARED by more than one app (not net-fold domain
  logic -- that's `utils/` -- and not GUI widgets -- that's `ui/`):
  - `paths.py` — the ONLY place that computes shared, cross-app
    locations: `STRETCHY_NETS_DIR` (input nets — NOT caches, those are
    per-app, above), derived from `Path(__file__)`. An app one level
    deeper than `src/apps/` first does a tiny inline bootstrap
    (`sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`)
    so `common`/`ui` are importable at all, THEN imports from
    `common.paths` before importing anything from `utils` — as an
    import side effect, `common/paths.py` inserts `src/` onto
    `sys.path`, which is what makes `from utils.<category> import ...`
    resolve when a script is run directly (`python src/apps/<app>/app.py`)
    rather than as an installed package. (`interactive_builder_app`
    needs no name from `paths.py` itself -- it has no net files to
    locate -- but still `import common.paths` for exactly this
    sys.path side effect, purely to make its own `from utils.geometry...`
    import resolve.)
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
- `docs/README.md` — user-facing usage doc (install, run the app, write a `.json` net, tests)
- `docs/algorithm.md` — the inflation algorithm itself, written up scientific-paper style

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
as seen from outside the finished solid** (or, for a deliberately OPEN net,
outside whichever side was chosen as the outside — the winding IS that
choice, nothing else records it). Concretely: for every edge shared by two
faces, one face's loop contains it as `v -> w` and the other's contains it
as `w -> v` — never the same direction twice. `load_stretchy_mesh` only
rejects a directed edge that appears **more than once** — a genuine error,
since two faces would then be claiming the same directed edge. An edge
referenced by only one face (no reverse partner at all) is a valid, free
**boundary** edge, not an error — the mesh does **not** need to be a
closed 2-manifold. (This used to be a stricter check, requiring every
edge to have exactly one reverse partner — i.e. a fully closed mesh —
until the user asked to inflate a deliberately open, hand-designed net
from `interactive_builder_app` and there turned out to be no actual reason
for the requirement: `relax_once`/`relax_initial_configuration` only ever
compute per-edge spring forces and per-face pressure forces, never
anything that assumes or needs a closed volume, so an open boundary edge
was already physically meaningful — the loader was just refusing to admit
it.) That check alone can't catch everything, though — see "Orientation
consistency" below for the subtler, solve-time half of this.

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

## Interactive builder (`src/apps/interactive_builder_app/app.py`)

A 2D shape-placement canvas -- unrelated to solving/folding anything, and
to the other two apps' domain logic (`src/utils/`) entirely. No test
file, per this project's existing convention that the rest of
`src/apps/` (beyond `apps_common`) stays untested (see "Testing" below).

- **Palette**: one icon per regular polygon, triangle through 8-gon, a
  small `tk.Canvas` drawn from `utils.geometry.polygon_geom.
  regular_polygon_vertices` -- no text label, just the shape itself.
  Every icon shares the same CIRCUMRADIUS (`ICON_RADIUS`, via
  `_vertices_with_radius`, which solves for the edge length that gives a
  regular_polygon_vertices call a chosen radius instead of a chosen edge
  length) rather than a shared edge length -- unlike a shape actually
  PLACED on the canvas (`_LOCAL_VERTICES`, built directly from
  `DEFAULT_SHAPE_EDGE_LENGTH`), where a bigger n legitimately means a
  bigger shape, sharing edge length the way every other net/mesh in this
  project does. Using a shared edge length for the ICONS too was tried
  first and clipped the 7-/8-gon icons against their own small canvas,
  since their circumradius at a fixed edge length grows faster than a
  triangle's or square's. `POLYGON_COLORS` gives each polygon type ONE
  FIXED color (never per-instance), built from `_POLYGON_HLS` -- an
  explicit `[(hue_deg, lightness, saturation), ...]` table, one entry
  per `POLYGON_NS` position, fed through `_hls_hex`
  (`colorsys.hls_to_rgb`). This started as a single FORMULA (an even hue
  gradient, green -> blue -> purple, one flat lightness/saturation for
  all 6 except a darker/less-saturated override for the first two
  GREENS in that range) rather than picking discrete swatches out of
  `ui_theme.FACE_COLORS` (tried first; triangle alone went through a
  dark navy, a bright yellow, a darkened yellow, and a user-specified
  brown before THAT per-shape-palette-lookup approach was scrapped for
  the gradient -- see git history for either abandoned approach's own
  reasoning if it matters again). The formula didn't survive later
  requests, though: dropping the first green and shifting the rest up,
  inserting a new hue between the darker blue and the purple, and
  independently lightening that darker blue while darkening the
  turquoise all left the hues unevenly spaced with several colors
  carrying their own lightness/saturation -- at that point an explicit
  per-entry table reads more clearly than a formula with a growing pile
  of exceptions bolted onto it. Current table, base lightness/saturation
  0.50/0.65 (medium / medium-high, not maxed-out) except where noted:
  triangle 136° green (0.38/0.50, darker+less saturated -- the one
  survivor of what used to be two greens, its own override untouched by
  any of this), square 172° turquoise (0.40/0.65, darkened a bit from
  base), pentagon 208° blue (base), hexagon 244° blue (0.58/0.65,
  lightened a bit from base), 7-gon 262° violet (base -- the new
  in-between entry), 8-gon 280° purple (base).
- **Pick up / drop**: clicking a palette icon "arms" that type
  (`self.armed_n`, highlighted via the icon Canvas's own
  `highlightbackground`) and shows a ghost preview following the mouse
  over the canvas, drawn via `_draw_shape(..., selected=True)` -- i.e.
  EXACTLY like a real, currently-selected placed shape (solid fill,
  `SELECTION_OUTLINE_COLOR` outline), not some lesser "not real yet"
  look. Two other looks
  were tried and dropped: a dashed-outline-only preview (didn't read as
  "this is what you're about to place" as clearly as showing the real
  fill), and before that a stippled fill (a stipple pattern is a small,
  fixed-pixel bitmap tiled across the polygon, so it read as
  increasingly coarse/pixelated on a shape this size, much bigger than a
  palette icon, rather than a smooth preview). Clicking the SAME icon
  again disarms it; clicking a DIFFERENT one swaps which type is armed
  directly. Arming a NEW type (not disarming) also deselects whatever
  shape/connection was selected on the canvas (`_on_palette_clicked`) --
  picking something up to place is a distinct action from working with
  what's already there. Clicking anywhere in the canvas while armed
  drops a real instance there and disarms the tool -- it is NOT left
  selected afterward (`_drop_shape` used to set `self.selected_id` to
  the new shape; removed at the user's request). Shapes are stored in
  `self.shapes`, a list in Z-order (back to front);
  redrawing just iterates it front-to-back, so a later drop naturally
  renders on top of anything it overlaps, with no separate Z-index
  field needed.
- **Select / drag / delete**: `_on_canvas_press` hit-tests
  (`_hit_test`, topmost-first via `reversed(self.shapes)`, each shape's
  containment via `_point_in_polygon`'s ray-casting against its CURRENT,
  possibly-rotated vertices -- see Rotate below) and either selects
  the hit shape (setting up `self._drag_state`) or, on a miss, deselects.
  Dragging is not a separate click-vs-drag code path: `_drag_state`
  records the press's starting world position and the shape's starting
  center, and `_on_canvas_drag` just re-applies that same world-space
  delta on every subsequent motion event -- a plain click that never
  moves is simply a drag by zero, so it falls out for free. The selected
  shape (`self.selected_id`, at most one at a time) is drawn with a thin
  outline in `SELECTION_OUTLINE_COLOR` (`"red"` -- plain `"white"`
  first, then an amber `"#ffb300"`, before landing here; none of
  `POLYGON_COLORS`' green/blue/purple hues (see above) are anywhere
  near red, so it stays unambiguous against any shape's own fill --
  white is now reserved for a handle's resting/not-currently-relevant
  state, see Edge connections below) at
  `SELECTION_OUTLINE_WIDTH`; Delete
  (`root.bind_all` -- this app has no text-entry widget for the key to
  collide with) removes it (`_remove_shape`, see Edge connections below
  for why deleting a shape isn't just a filter on `self.shapes`).
- **Edge connections** (`self.connections`, `_connection_pending`,
  `_pending_cursor_screen`, `_hover_shape_id`/`_hover_edge_index`): a
  connection is stored as `{"id", "a_shape", "a_edge", "b_shape",
  "b_edge"}` -- an EDGE INDEX (position in that shape's own vertex loop)
  rather than a coordinate, so it stays valid automatically as either
  shape moves or rotates;
  `_shape_edge_midpoints` re-derives the actual world-space midpoints
  fresh every time from a shape's CURRENT `_shape_world_vertices`, never
  cached.

  `_redraw` considers a handle for EVERY placed shape's EVERY edge --
  selection is NOT a gate on whether one can be started from any more
  (see below). This replaced an earlier design (`handle_points`, a SET
  built only from the selected shape's edges, the hovered shape's edges,
  and existing connections' own endpoints) at the user's explicit
  request: that design meant starting a connection needed two clicks --
  select the shape first (to make its handles appear/become clickable
  via `_hit_test_edge_handle`, which only ever looked at
  `self.selected_id`'s own handles), then click a handle -- when the
  user wanted one click, straight onto any handle, selected or not.
  `_draw_handle_circle` (`EDGE_HANDLE_RADIUS`, `EDGE_HANDLE_OUTLINE_WIDTH`)
  takes an explicit `joined` flag alongside `lit`: an edge that's the
  endpoint of a real connection draws as a solid filled dot
  (`HANDLE_COLOR`, white) and is ALWAYS drawn; one that isn't draws as an
  UNFILLED ring (empty fill, `HANDLE_COLOR` outline) but ONLY when
  `self._cursor_screen` is currently within `HANDLE_HIT_RADIUS` of it --
  the loop in `_redraw` skips the draw call entirely otherwise. Showing
  every free handle on every shape all the time was tried first (right
  after the two-click-selection design above was dropped) and immediately
  read as clutter once there was more than a couple of shapes on the
  canvas, hence the reveal-on-proximity behavior -- and it deliberately
  reuses `HANDLE_HIT_RADIUS`, the exact radius an actual click needs, so
  a handle is never visible without also being clickable or vice versa
  (the same "highlight and action must agree" principle already applied
  to the pending-connection hover check below). `self._cursor_screen`
  (tracked by `_on_canvas_motion` unconditionally -- not just while
  armed/pending, since reveal now depends on it at all times -- and
  cleared by `_on_canvas_leave` when the mouse exits the canvas) is
  `None` until the mouse has been seen at least once, so nothing reveals
  before that either. `lit` (`SELECTION_OUTLINE_COLOR`, red) always
  overrides `joined`'s color choice AND bypasses the proximity gate
  entirely (a lit handle draws regardless of the cursor): every edge of
  the SELECTED shape (`shape["id"] == self.selected_id` -- so any of its
  edges can be picked to start a connection from), the pending
  connection's own origin point (`pending_point`, which needs to stay
  lit even though clicking it is what just deselected its shape -- see
  the next paragraph), and its CURRENT hover target (`hover_point =
  (self._hover_shape_id, self._hover_edge_index)`) -- deliberately just
  that ONE edge, not the hovered shape's whole outline or every one of
  its handles. An earlier version lit the entire target shape up like a
  selection (mirroring `lit_shape_ids = {self.selected_id,
  self._hover_shape_id}`, checked against `shape["id"]` rather than a
  specific `point`) -- removed at the user's explicit request, since it
  read as "this whole shape is selected" when only one specific edge
  was actually about to be connected to; the shape-drawing loop above
  now only ever lights up `self.selected_id`, never `_hover_shape_id`,
  so a hovered target's outline stays its normal, unselected color too.
  Never drawn for the armed/not-yet-dropped ghost, since a connection
  needs a real, placed shape on both ends.

  Click-click, not click-drag (a drag-out-a-line design was tried first
  and replaced with this one at the user's explicit request -- see git
  history for that version's own reasoning if it's ever wanted back).
  `_on_canvas_press` checks handle hit-testing (`_hit_test_any_edge_handle`,
  with no exclusion -- ANY shape's handle can start a connection now, not
  just the selected one; `_hit_test_edge_handle`, the selected-shape-only
  predecessor, was removed once nothing called it any more) BEFORE the
  ordinary connection-hit-test and shape-hit-test checks, since a handle
  can sit right on top of the shape's own body. Clicking a handle arms
  `self._connection_pending` (the origin shape/edge) AND explicitly
  clears `self.selected_id` (per an earlier, separate user request --
  clicking a handle used to leave the shape looking selected the whole
  time a connection was pending; now the POINT is the selected thing
  instead, so the shape's outline drops, though EVERY edge -- including
  that one -- still shows a handle regardless, per the always-visible
  redraw above) instead of a normal shape drag/select;
  `_on_canvas_motion` (not `_on_canvas_drag` -- there's no button held
  between the two clicks) then calls `_hit_test_any_edge_handle` at the
  cursor on every motion event (excluding the pending connection's own
  origin shape this time) and sets `_hover_shape_id`/`_hover_edge_index`
  from whatever it finds -- PROXIMITY TO A HANDLE, not just being
  anywhere over the shape's body (a point-in-polygon `_hit_test` was
  used here first and was an actual bug the user reported: it lit up an
  entire shape as a valid target the moment the cursor entered its body,
  even nowhere near any of its handles, so a click that then missed
  every actual handle would cancel with no connection despite the shape
  having looked ready to connect to a moment earlier). `_redraw` lights
  up just that one `hover_point` handle in red (see above) -- not the
  hovered shape's outline or any of its OTHER handles -- without ever
  touching `self.selected_id` itself, so it's cosmetic only.

  The SECOND click, while `self._connection_pending` is set, is handled
  by `_complete_or_cancel_pending_connection` (called from
  `_on_canvas_press` before any of the normal checks). Critically, it
  does NOT re-hit-test the click's own position -- it just reads
  whatever `_hover_shape_id`/`_hover_edge_index` ALREADY say, i.e.
  exactly what `_on_canvas_motion` most recently lit up. This is what
  guarantees the fix above actually holds: highlighting and completion
  are now provably the same decision (one reads the other's output)
  rather than two separate hit-tests that could disagree, so a
  connection can never be made onto something that wasn't visibly about
  to happen a moment before the click. `_hover_shape_id is not None`
  appends the connection, deselects everything, and returns `True`;
  `None` (own shape excluded by construction, empty background, a
  shape's body away from any of its handles, or anywhere else) returns
  `False` with no connection made -- "connected to itself or to the
  background" collapses to one check, "was anything highlighted right
  now", since both named failure cases already can't set
  `_hover_shape_id` in the first place. `_on_canvas_press` only treats a
  `True` (connection made) as fully handling the click; a `False`
  deliberately does NOT consume it -- the same click still falls through
  to the ordinary handle/connection/shape checks afterward -- and since
  EVERY handle is now clickable regardless of selection, that fallthrough
  can immediately re-arm a brand-new pending connection if the click that
  canceled the first one happened to land on some OTHER handle (its own
  shape's other edge included) -- there's no special-case needed for
  that any more, it just falls out of "any handle click starts one." A
  click that hits nothing (empty background) cancels AND deselects, via
  the normal miss case. While pending, `_redraw` draws the line from the
  live cursor position with `selected=True` -- i.e. in
  `SELECTION_OUTLINE_COLOR` (red) and the thicker width, not the resting
  grey -- so an in-progress connection reads as "active" the same way
  the point it started from does. A connection line
  (`_draw_connection_line`, light grey `CONNECTION_COLOR`/`_WIDTH`, or
  `SELECTION_OUTLINE_COLOR` and thicker when HIGHLIGHTED) is hit-tested
  by `_hit_test_connection` via `_point_segment_distance` (perpendicular
  distance to the segment, not the infinite line, since a click well
  past either endpoint shouldn't count) -- selecting one clears
  `self.selected_id` (mirroring `self.selected_connection_id` being
  cleared whenever a shape gets selected instead: the two are mutually
  exclusive, never both set). A connection is "highlighted" (drawn the
  same as a selected one) under EITHER of two conditions, checked in
  `_redraw`: it's the one actually in `self.selected_connection_id`, OR
  either of its own two shapes is `self.selected_id` -- so selecting a
  shape highlights every connection touching it as a group, without
  reassigning `self.selected_connection_id` to any specific one of them,
  and WITHOUT lighting up the shape on the connection's OTHER end (the
  shape-drawing loop only lights up `self.selected_id`/`_hover_shape_id`
  itself, never a shape just because a connection links to it). Deleting
  either shape a connection touches has to remove the connection too --
  `_remove_shape` (used by `_on_delete_key`) does both together in one
  step, since a connection with a missing endpoint has nothing left to
  draw a line between; Clear (`on_clear_clicked`) empties
  `self.connections` alongside `self.shapes` for the same reason.
- **Rotate / pan (right button, mutually exclusive)**: `_on_right_press`
  decides once, at press time, which of the two right-drag means: if a
  shape is currently selected, ROTATE it (`_rotate_state`); otherwise
  PAN the view (`_pan_last_xy`) -- the two fields are never both set, so
  `_on_right_drag` just checks which one is live. Rotation is trackball-
  style, not an absolute-angle readout: each motion event measures the
  mouse's CURRENT angle around the shape's screen-space center
  (`atan2`), diffs it against the angle recorded at the previous event,
  and adds that delta straight onto the shape's own `rotation` (radians,
  stored per-shape, applied in `_shape_world_vertices` before
  translating by `(cx, cy)`) -- this is safe to do directly in SCREEN
  space rather than converting through `_screen_to_world` first, since
  the view transform is scale-plus-translate only (no shear/rotation of
  its own), so a screen-space angle and the corresponding world-space
  angle are identical. Panning adds the drag's screen delta to the view
  offset directly (a plain `+=`) -- dragging the background moves the
  view WITH the cursor, like grabbing and sliding the canvas itself (a
  `-=`, moving the view opposite the drag as if pulling the canvas out
  from under a fixed viewport, was tried per an earlier request and
  then explicitly reverted back to this `+=` version).
- **Zoom**: the scroll wheel (`<MouseWheel>` on Windows/macOS,
  `<Button-4>`/`<Button-5>` on X11 -- all three bound, same as
  `inflate_polyhedron_app`'s level-panel zoom) zooms about the CURSOR:
  `_on_zoom` solves for the world point under the cursor at the OLD
  scale, then re-derives the offset so that same world point lands back
  under the cursor at the NEW one -- without this, zooming would drift
  whatever's under the mouse sideways instead of zooming into/out of it.
- **Coordinates**: shapes are stored in "world" coordinates, entirely
  independent of the current pan/zoom; `_world_to_screen`/
  `_screen_to_world` (a single scale-plus-offset transform) are the ONLY
  two places that ever convert between the two, so panning/zooming is
  purely a transform applied at draw/hit-test/drag time, never a
  rewrite of every shape's stored position.
- **Rendering / anti-aliasing (`_rasterize_polygon`)**: a plain
  `tk.Canvas` polygon item has NO anti-aliasing in Tk at all -- every
  edge came out visibly jagged, worst on a pentagon/hexagon/etc's
  diagonal sides. Every polygon (each placed shape, the ghost preview,
  and each palette icon) is instead rasterized through Pillow at
  `SUPERSAMPLE` (4x) its final pixel size and LANCZOS-downsampled -- the
  standard supersample-then-downsample anti-aliasing trick. Only each
  polygon's own padded bounding box is rasterized (not the whole
  canvas), so cost tracks the shapes actually on screen, not canvas
  area; `main()` also calls `_enable_windows_dpi_awareness()` (a no-op
  off Windows) before creating the root Tk window, since without it
  Windows renders this (like any DPI-unaware Tk app) at a virtualized 96
  DPI and bitmap-stretches the result to the display's real scaling,
  which independently made everything look soft on a scaled display --
  a separate cause of blur from the lack of polygon anti-aliasing, and
  both needed fixing. Because rendering is a plain `tk.Canvas` with a
  solid background plus `create_image` blits (not matplotlib, unlike the
  other two apps' 2D panels), the actual hit-test/drag/rotate LOGIC never
  looks at what's drawn -- it works entirely off each shape's own stored
  world-space geometry, unaffected by how it happens to be rasterized.
  `_redraw` clears the canvas and re-rasterizes every shape from
  scratch each call (`self._shape_photos` holds this call's images so Tk
  doesn't garbage-collect them out from under the canvas) -- simple and
  fast enough given there are only ever a handful of shapes on screen; a
  palette ICON, by contrast, is rasterized ONCE at build time
  (`self._icon_photos`), since it never changes. The canvas itself is
  given a visible 1px border (`highlightthickness=1,
  highlightbackground=PLOT_THEME["fg"]`) so the drawing area reads as a
  clearly boxed-in region rather than blending into the rest of the
  (also dark) window.
- **Clear button**: `on_clear_clicked` empties `self.shapes` and clears
  the selection; no confirmation prompt.
- **Font scaling**: `_scale_ui_fonts` (called once, right after
  `sv_ttk.set_theme`) is copied from `inflate_polyhedron_app`'s own
  method of the same name -- scales every NAMED Tk/ttk font by
  `UI_FONT_SCALE` (1.3, matching the other app's value) so the whole
  app's text (the Clear button, the File menu, ...) grows together,
  including sv_ttk's own Tcl-level fonts that back most ttk widget
  styles (a per-widget `font=` override would miss those). (There used
  to also be a "Shapes" heading Label above the palette, with its own
  literal `("TkDefaultFont", ..., "bold")` tuple scaled by hand for the
  same reason -- removed at the user's request; nothing in the left
  panel needs a per-widget font override any more.)
- Dark mode only, like the other two apps: `sv_ttk.set_theme("dark")`
  for the ttk palette/Clear button, `ui_theme.PLOT_THEME["bg"]`/`["fg"]`
  for the canvas, its border, and the palette icon backgrounds.
- **File menu (`_build_menu`)**: a plain `tk.Menu` cascade, "File" ->
  "Load..."/"Save...", attached via `root.config(menu=...)` -- this
  app's only menu bar, added specifically to host these two commands.
  See "Net JSON import/export" below for what they actually do.
- **Debug mode (`self.debug_mode`, "d" key via `root.bind_all` --
  same rationale as `Delete` above, no text-entry widget to collide
  with)**: `_on_toggle_debug_mode` just flips the flag and updates the
  window title (`" (debug mode)"` suffix, same convention
  `inflate_polyhedron_app` uses for its own debug toggle). The one thing
  it actually changes is `_redraw` calling `_draw_debug_vertex_label`
  when on: finds the shape VERTEX (a corner via `_shape_world_vertices`,
  NOT an edge-midpoint handle) nearest the cursor within
  `DEBUG_VERTEX_HOVER_RADIUS`, and if one's close enough, rings it and
  labels it `"vSHAPE.CORNER"` using that corner's OWN `(shape["id"],
  corner)` -- ALWAYS that, never `_vertex_roots`' union-find ROOT for
  it, even though that root can be looked up trivially the same way
  `_validate_shapes_connections` does. The label is drawn white
  (`fill="white"`) on a small 50%-alpha black box (`Image.new("RGBA",
  ..., (0, 0, 0, 128))`, blitted via `create_image`/`ImageTk.PhotoImage`,
  kept alive in `self._shape_photos` the same way `_rasterize_polygon`'s
  shape images are -- a plain `tk.Canvas` rectangle item can't do
  translucency), sized to the label's own measured text extent
  (`tkfont.Font(font=...).measure`/`.metrics("linespace")`) -- a user
  reported the original plain colored canvas text unreadable against
  some shape colors underneath it; the original color was also yellow,
  matching `DEBUG_VERTEX_COLOR` (still used for the hover ring only, not
  the text any more).

  This "always own address" behavior is itself the SECOND of two
  reworks of what this label shows, both from real user reports against
  `hippo.json` (a big, 42-shape, 102-connection net). Originally it
  showed `_faces_from_shapes(self.shapes, self.connections)
  [self.shapes.index(shape)][corner]` -- the EXPORTED sequential
  integer -- and a user reported that as a bug: `vertex_ids[root] =
  len(vertex_ids)` assigns ids in shape/corner ITERATION ORDER, the
  first time each root is reached, so creating one new, entirely
  unrelated connection elsewhere shifts every id assigned after it down
  by one, making an untouched corner's displayed label change for no
  visible reason. That was fixed by extracting `_vertex_roots` (the raw
  `{slot: root}` union-find mapping, no numbering step) and displaying
  the ROOT SLOT instead -- stable across unrelated edits since `find()`
  has no path compression, but a root can belong to a DIFFERENT,
  genuinely-connected shape than the one hovered (e.g. shape 42's own
  corner 2 legitimately showing "v34.0", if that's really the same
  vertex as shape 34's corner 0). On a big, densely-connected net most
  corners of most shapes really are shared with some neighbor, so this
  meant most hovers showed a foreign-looking label -- reported as
  confusing on sight, even though each one was individually correct; the
  user asked for every corner to always show its own polygon's number,
  which is the current, final behavior. What's lost: hovering two
  corners that already share an id no longer shows matching text (the
  original point of computing a root here at all -- e.g. telling apart,
  for two shapes already sharing one edge, which specific pairing of
  their REMAINING edges continues the same "reverse traversal" the
  shared edge implies, per `two_pentagons_and_a_square.json`'s own
  3-edge-shared example, rather than whichever one just looks closest
  on screen). That comparison is still possible, just no longer from
  hovering here -- see the "Save" entry below for `_connection_chain`,
  added specifically to cover it a different way: a failed Save now
  spells out the actual chain of connections tying two corners together
  by name, rather than requiring a user to notice two hover labels
  match.

### Net JSON import/export (File > Load/Save)

Module-level (not on the class, since none of it touches Tk state):
`GAP`, `_faces_shared_edges`, `_layout_faces_with_gap`,
`_shape_from_placed_points`, `_infer_connections` -- plus the class
methods `on_save_clicked`/`_export_faces_and_layout` and
`on_load_clicked`/`_load_faces`/`_center_view_on_shapes`. The file
format is exactly stretchy_mesh.py's own `{"name", "faces"}` vertex-loop
spec (shared vertex ids ARE the adjacency -- see its module docstring),
PLUS two extra top-level keys that only THIS app reads or writes:
`"net_layout"`, a list, parallel to `"faces"`, of each face's own
`{"cx", "cy", "rotation"}` -- exactly the fields a shape dict already
carries -- and `"view"`, `{"scale": self.view_scale}`, the zoom level
the net was saved at. Any other program reading the file (the actual
stretchy-mesh solver included) only ever looks at `"faces"`/`"name"`
and has no reason to choke on an unrecognized top-level key, so a saved
file is still a perfectly normal net for `inflate_polyhedron_app` or
anything else that reads this format.

- **Save** (`on_save_clicked`): `filedialog.asksaveasfilename` with
  `initialdir=STRETCHY_NETS_DIR` (`common.paths`, same constant every
  other net-file-aware bit of this project uses) -- so the picker opens
  where the project's own hand-authored nets already live, though the
  user can navigate anywhere and save under any name.
  `_export_faces_and_layout` derives `"faces"` from `self.shapes`/
  `self.connections` via `_faces_from_shapes`, which itself calls
  `_vertex_roots` -- a UNION-FIND over
  `(shape_id, corner_index)` slots (`corner i` is the vertex where edge
  `i-1` meets edge `i`, i.e. edge `i` runs corner `i` -> corner
  `(i+1) % n` -- the same indexing `_shape_edge_midpoints` uses): each
  connection unions `(a_shape, a_edge)` with `(b_shape, (b_edge+1) %
  n_b)` and `(a_shape, (a_edge+1) % n_a)` with `(b_shape, b_edge)` --
  REVERSED, not edge-to-edge straight across, because a shared edge must
  appear as `v -> w` in one face's loop and `w -> v` in the other's (the
  winding convention `load_stretchy_mesh` validates) -- pairing straight
  across would instead produce the SAME direction in both, which that
  loader rejects. `_vertex_roots` returns that raw `{slot: root}`
  union-find mapping with no numbering of its own -- since `find()` has
  no path compression, an existing group's root is unaffected by any
  later, unrelated union, so it's what debug mode displays directly (see
  above) for a label that never shifts just because some unrelated
  connection was added or removed. `_faces_from_shapes` layers the
  sequential-integer-assignment step on top of `_vertex_roots`'s output
  (`vertex_ids`, filled in the order shapes/corners are visited, one
  fresh id per distinct root), since the exported JSON format needs
  simple integers -- this renumbering only ever happens at Save, never
  for anything displayed live. Each shape's own face is just its
  corners' ids in order.
  `_faces_from_shapes` is a pure function of its two arguments (not a
  method), called with the REAL `self.connections` in exactly ONE place
  -- here, at Save (debug mode calls `_vertex_roots` directly instead,
  not `_faces_from_shapes`, for the reason above).
  `net_layout` is a parallel list of each shape's own
  `{"cx","cy","rotation"}`, same order as `self.shapes` (and therefore as
  the derived `"faces"` list). An unconnected edge's two corners just
  keep their own unique ids -- nothing forces every edge to have a
  partner, so an incomplete, still-being-built net saves and reloads
  fine -- `load_stretchy_mesh` itself no longer requires closedness
  either (see "Stretchy meshes" above: an unmatched edge is a valid,
  free boundary edge, not an error), so a net exported this way with
  unconnected edges is a perfectly legitimate OPEN net to
  `inflate_polyhedron_app` too, not just to this app's own lenient
  reading of it.

  **`_validate_shapes_connections` runs in exactly ONE place: here, at
  Save -- deliberately NOT live, while a connection is being made.** This took
  two tries to get right. `_joined_points` (every `(shape_id,
  edge_index)` already an endpoint of a real connection), consulted by
  `_hit_test_any_edge_handle` to exclude an already-joined edge from its
  search entirely, was the first and is a permanent, LOCAL rule: an edge
  can only ever be joined once, full stop, independent of anything else
  in the mesh (added after this actually corrupted
  `data/input/stretchy_nets/hippo.json` in real use -- see git
  history/the file's own repair for the forensics). A SECOND version
  then also ran a full TRIAL merge (`_faces_from_shapes(self.shapes,
  self.connections + [the proposed connection])`, checked with what was
  then `_validate_faces`) before allowing any connection to complete at all,
  reasoning that "an edge can only be joined once" alone wasn't
  sufficient -- two individually-free edges sharing a corner with edges
  connected elsewhere could still transitively collapse two different
  corners of some face into one. That reasoning was correct, but
  applying it LIVE was still the wrong call, and was REVERTED once a
  user hit it directly: two edges that looked like an entirely ordinary,
  correct connection got silently rejected because of what some OTHER,
  already-existing connection elsewhere implied about a shared vertex
  label -- confusing, because that implied sharing is exactly as fluid
  as any other single connection (remove the connection causing it, and
  two "same" corners stop being the same). The actual lesson: during
  EDITING, every corner should be treated as its own, separate vertex,
  no matter what any OTHER connection's own transitive merge currently
  implies about it -- full merge-and-validate is only meaningful ONCE
  the whole net is being finalized, which is Save, not mid-edit. So
  `_export_faces_and_layout` calls `_validate_shapes_connections`
  (self-loop check: no shape's own edge may have its two corners' roots
  collapse together; duplicate-directed-edge check: mirrors
  `load_stretchy_mesh` itself) directly on `self.shapes`/
  `self.connections`, via `_vertex_roots`, BEFORE `_faces_from_shapes`
  ever runs its export-time renumbering -- so its error messages are
  phrased as "vSHAPE.CORNER" (e.g. "edge v9.4->v9.0 appears 2 times"),
  the exact same live identity debug mode's own label shows, not the
  fresh integers `_faces_from_shapes` would only assign at export
  time. An earlier version validated the ALREADY-exported `faces` list
  instead (`_validate_faces`, still present, still a plain pure function
  over a `"faces"` list, just no longer called from here) and so
  reported a failed Save in terms of numbers that only existed in the
  file about to be written -- meaningless to a user who was only ever
  looking at shapes and corners on screen, never at that JSON. Real
  case: a user asked for exactly this after chasing "self-loop edge at
  vertex 37" against a file whose corresponding vertex numbering did
  not match what was on screen.

  Every problem message also names the SPECIFIC chain of existing
  connections responsible, via `_connection_chain` (BFS over the same
  slot-to-slot links `_vertex_roots`' own union calls make, from one
  conflicting corner slot to the other): e.g. "shape 42 edge 2 (corners
  2->3) is a self-loop at v42.2 (traced through: shape 34 edge 4 <->
  shape 42 edge 1 -> shape 19 edge 5 <-> shape 34 edge 3 -> shape 42
  edge 3 <-> shape 19 edge 4)". Neither conflict is EVER caused by one
  connection in isolation -- a fresh union only merges two PREVIOUSLY
  separate groups, so a corner that was never touched by the connection
  just added can only newly collide with another if some transitive
  chain of OTHER, already-accepted connections already tied each side
  to opposite halves of it -- so naming just the connection that
  happened to trip the check, alone, would leave a user unable to tell
  which of it or some earlier connection is actually the wrong one.
  Real case this caught, on `hippo.json`: shape 42 (already attached to
  shape 34 on 3 of its 5 edges) and shape 19 (also already attached to
  shape 34) both had one matching free edge left; connecting shape 42's
  edge 3 to shape 19's edge 4 looked like an entirely reasonable closing
  move, but was off by one edge -- the chain traced straight through the
  shared shape-34 attachment and showed shape 42's OWN edge 2 becoming a
  self-loop as a result; edge 2 (not edge 3) turned out to be shape 42's
  actual matching edge for shape 19's edge 4, confirmed by trying it,
  which validated clean.

  `_validate_shapes_connections` raises `NetValidationError` (a
  `ValueError` subclass carrying `self_loop_slots`, a `{(shape_id,
  corner_index), ...}` set of every corner in a found self-loop, both
  endpoints of each one) rather than a plain `ValueError` specifically
  so a self-loop's location can be shown, not just named:
  `on_save_clicked` catches it, sets `self._self_loop_highlight` to
  those slots, and calls `_redraw` BEFORE showing the `messagebox.
  showerror` -- `_draw_self_loop_highlight` then rings each one in
  `SELF_LOOP_HIGHLIGHT_COLOR` (orange), regardless of debug mode, since
  this is feedback about an error in the CURRENT canvas state, not a
  debug-only diagnostic. A duplicate-directed-edge conflict alone
  raises the same exception type but with an empty `self_loop_slots`
  (nothing to ring -- neither endpoint of a duplicate-edge conflict is
  itself degenerate, only their pairing is), so nothing new gets
  highlighted for that case. The highlight persists across redraws
  (drags, pans, zooms) until the next actual EDIT -- a new shape/
  connection, a delete, a fresh Load -- clears `self.
  _self_loop_highlight` back to an empty set (every one of those sites
  does this explicitly; see the set's own comment in `__init__`), so it
  doesn't linger once it's stale, but also doesn't disappear on its own
  just from panning around to go look at it.
- **Load** (`on_load_clicked`): reads `"faces"` (required -- a `KeyError`
  on a missing key, or empty list, surfaces as a `messagebox.showerror`,
  same as any other read/parse failure) and `"net_layout"` (optional) via
  `_load_faces`, which fully replaces `self.shapes`/`self.connections`
  (clearing every piece of transient state -- selection, armed tool,
  pending connection, drag -- along with them) rather than merging into
  whatever was already on the canvas.
  - If `net_layout` is present and the same length as `faces`: use it
    directly, index-for-index -- reproduces the EXACT on-screen layout a
    file this app itself saved had, no BFS needed at all.
  - Otherwise (any hand-authored net, e.g. anything already under
    `data/input/stretchy_nets/`, which predates `net_layout` and will
    never have one): `_layout_faces_with_gap(faces, root=0, gap=GAP)`
    -- the SAME BFS-spanning-tree-over-shared-edges idea
    `build_stretchy_net_layout` (`utils/inflate_polyhedron/
    stretchy_net_layout.py`) already implements for the OTHER app's
    "Net" panel, reusing its own `attach_polygon`/
    `regular_polygon_vertices` primitives directly (imported, not
    reimplemented) -- but that function is on this project's
    untouchable-files list and has no gap parameter, so it can't simply
    be called and asked to leave space between faces; the short BFS
    loop itself had to be written again here (`_faces_shared_edges`,
    a local equivalent of that module's own private, unexported
    `_shared_edge_faces`), parameterized with `GAP` (=
    `DEFAULT_SHAPE_EDGE_LENGTH`, i.e. exactly one edge length of
    separation, per the user's own suggestion), rather than the whole
    algorithm being reinvented from scratch. Each child face is attached
    `gap` world units further out along the shared edge's own outward
    normal (from the parent's centroid) instead of flush against it,
    via the SAME `attach_polygon` call `build_stretchy_net_layout` uses,
    just with both target endpoints offset outward first -- the
    resulting net is still a single connected spanning tree, just
    visibly DISJOINT rather than seamlessly glued.
    `_shape_from_placed_points` then solves each face's own `(cx, cy,
    rotation)` from its placed points (their centroid, and one vertex's
    angle relative to it, compared against the same angle in
    `_LOCAL_VERTICES`) -- both are the same regular polygon, only
    translated/rotated, so this recovers the shape dict fields
    `_shape_world_vertices` needs to reproduce those exact points. A
    face BFS never reaches (a genuinely separate connected component,
    which a real closed polyhedron net never has, but nothing stops a
    hand-edited or partial file from) just gets placed off to one side
    by index, rather than crashing or stacking on the origin.
  - `_infer_connections(faces)` derives connections the OPPOSITE
    direction from `_export_faces_and_layout`'s union-find: for every
    directed edge `(v, w)` in some face, if the exact reverse `(w, v)`
    exists in (a different edge of) some face, that's one connection
    between them; an edge with no reverse partner is simply left
    unconnected -- an open net's boundary edges, same as
    `load_stretchy_mesh` itself now allows (see "Stretchy meshes"
    above). A SELF-LOOP edge (`v == w`, i.e. two adjacent corners of one
    face sharing a vertex id -- only possible from a file an earlier,
    buggy version of this app saved, since a correctly-behaving Save can
    never produce one) is explicitly skipped when building the directed-
    edge lookup, never treated as a connection: without that guard,
    `(v, v)`'s own "reverse partner" is also `(v, v)`, so a naive lookup
    would silently infer a connection from that edge to ITSELF (same
    face, same edge index on both ends) -- this is the concrete bug a
    user hit loading a stale, pre-fix `hippo.json`. `_self_loop_faces`
    (called separately, BEFORE `_infer_connections` gets a chance to
    skip anything) is purely diagnostic -- `on_load_clicked` uses it to
    show a non-blocking `messagebox.showwarning` naming which face/
    vertex was degenerate, so a malformed file still loads (rather than
    failing to open) but the user knows exactly which edge(s) were left
    unconnected and need redrawing, instead of finding out only when
    some later Save fails somewhere else in the net.

    More generally: a loaded file's own vertex-id NUMBERS are used only
    TRANSIENTLY, by `_infer_connections`/`_self_loop_faces`, to work out
    the connection graph -- they're never treated as any kind of
    ongoing internal identity. `_load_faces` immediately re-addresses
    every corner as `(shape_id, edge_index)` (fresh `self._next_shape_id`
    values, per-shape-local `range(shape["n"])` indices), the exact same
    addressing a freshly-drawn shape gets -- so the file's own labelling
    and whatever `_faces_from_shapes` computes on the next Save are
    never expected to match. This was a deliberate design point a user
    asked for explicitly, worried that treating a loaded file's vertex
    LABELS as meaningful ongoing identity (rather than a one-time
    connection-inference input) was the root cause behind bugs like the
    self-loop one above -- confirmed correct on inspection: it already
    worked this way for everything except the one self-loop gap fixed
    here.
  - `_center_view_on_shapes` accepts a `scale` parameter (`_load_faces`'s own
    `view_scale` parameter, read from the loaded file's `"view"."scale"`
    by `on_load_clicked`, or 1.0 if the file has no `"view"` section --
    any hand-authored net), sets `self.view_scale` to it, and recenters
    `offset_x/y` (scaled by that same `scale`, since
    `screen = world * view_scale + offset`) on the newly-loaded shapes'
    average center -- so a file this app itself saved reopens at the
    exact zoom level it was saved at, rather than always resetting to a
    fixed default.

### Consumed by `inflate_polyhedron_app`'s "Net" panel

`on_select_net` (`inflate_polyhedron_app/app.py`) re-reads the chosen
file's raw JSON itself (`json.load`, separate from `load_stretchy_mesh`,
which discards everything but `"faces"`/`"name"`) purely to check for a
`"net_layout"` section. When present and the same length as
`self.base_faces`, `_layout_from_net_layout(faces, net_layout)`
reproduces that EXACT saved arrangement instead of `build_stretchy_net_
layout`'s fresh BFS spanning-tree layout -- a user asked for this
specifically so a net they'd arranged and connected in the interactive
builder shows up on this OTHER app's "Net" panel exactly as left, not
re-flattened from scratch (which, per `build_stretchy_net_layout`'s own
docstring, only follows the FIRST shared edge it reaches an
already-visited face through, silently dropping any OTHER edge-sharing
between two faces -- entirely normal for a stretchy mesh).

`_layout_from_net_layout` reproduces each face's saved rigid transform
(`{"cx", "cy", "rotation"}`) directly -- same rotation-matrix math as
`interactive_builder_app`'s own `_shape_world_vertices`, verified
bit-for-bit equal (up to float precision) by reconstructing a real
saved net (`hippo.json`) both ways and diffing -- except built at THIS
app's own unit edge length (`EDGE_LENGTH = 1.0`, imported from
`stretchy_mesh.py`) rather than reproducing `interactive_builder_app`'s
`DEFAULT_SHAPE_EDGE_LENGTH = 70.0` pixel scale verbatim: since a rigid
transform is scale-covariant, building each polygon at `edge_length=1`
and dividing every saved `cx`/`cy` by that same 70 (`_INTERACTIVE_
BUILDER_EDGE_LENGTH`, duplicated as a bare constant rather than
importing the whole unrelated Tkinter app for one number) reproduces an
EXACTLY proportional net -- just uniformly rescaled, so this panel's
existing fixed axis padding (`_draw_target_faces`) still looks right.

Important: `interactive_builder_app` never snaps a connection's two
edges together spatially (see its own module docstring's "Edge
connections" section) -- shapes are positioned however the user dragged
them, and a connection is purely topological (drawn as a thin line
regardless of distance). So a saved `net_layout` reproduced here can
show two CONNECTED faces sitting nowhere near each other, with no line
between them (`_draw_target_faces` only draws the polygons themselves,
knowing nothing about the "faces" list's shared-vertex-id adjacency
beyond that) -- this is a faithful reproduction of the canvas exactly as
the user left it, not a bug, and not the same thing a physically
unfolded paper net would look like. `build_stretchy_net_layout`'s BFS
fallback (any hand-authored net, or a legacy fabric net -- neither ever
has a `"net_layout"`) is unaffected and still always produces
faces sitting edge-to-edge.

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

- **Docstring style** (`src/utils/`, and going forward `src/apps/`):
  every function/method docstring should be about 4-5 lines, succinct,
  and focused on input/output -- not the full history of why the
  function looks the way it does. Include: one line on what it
  does/returns; what each non-obvious parameter means (skip ones whose
  name already says it all); what's returned (shape/type), if not
  obvious from the name; at most one line for a genuinely load-bearing
  gotcha. Leave out: multi-paragraph "why we designed it this way"
  narratives, empirical findings, benchmark numbers, historical
  iteration ("tried X first, it broke on Y") -- that belongs in the
  MODULE-level docstring (a "Design notes" section) or git history, not
  repeated on every function that touches the decision; references to
  other functions' own internals unless the caller truly needs them;
  restating what the code obviously does. Module-level docstrings are
  NOT held to the 4-5 line limit -- keep them as long as they need to be
  to cover the bigger picture, front-loading the essential "what this
  module is" in the first paragraph. Example:

  ```python
  # Before (too long, mixes rationale into a function comment):
  def _sphere_bound_volume(faces, edge_length):
      """An optimistic (normally unreachable) target volume for
      _inflate's pressure term: the volume of the SPHERE with the same
      total surface area as the mesh's own faces (each assumed a
      regular polygon of `edge_length` sides, even though the actual
      solved faces may bend a little) -- the isoperimetric-maximal
      shape for that much surface, so no achievable inflation ever
      fully reaches it. Scaled to the mesh's own size (not some
      arbitrary huge constant) so the pressure it creates stays
      reasonable regardless of how big the mesh is: e.g. for the
      regular icosahedron this comes out to ~2.40, within 10% of its
      true volume (~2.18) ..."""

  # After (4-5 lines, input/output focused; the "why" moves to the
  # module docstring's Design notes):
  def _sphere_bound_volume(faces, edge_length):
      """Volume of the sphere with the same total surface area as
      `faces` (each assumed a regular polygon of `edge_length` sides)
      -- an optimistic, normally-unreachable inflation target, scaled
      to the mesh's own size. See module docstring's Design notes for
      why this (rather than a fixed constant) is used as _inflate's
      pressure target."""
  ```

  When editing a function in `src/utils/`, check its docstring still
  fits this convention; when adding a new function, write its docstring
  to this convention from the start rather than adding a full-length one
  and trimming later. (There used to be a separate `skills.md` at the
  repo root holding just this section -- merged in here so there's one
  skill doc, in the one place Claude actually looks for it.)
- The STRETCHY pipeline's polygon edges all have length 1
  (`stretchy_mesh.EDGE_LENGTH`) since its nets are hand-authored
  combinatorics with no coordinates of their own -- there's no runaway
  stretch cap on this any more (see "No hacky terms in the physics
  without explicit permission" above for why a stretch limit was tried
  and removed). `polygon_geom.EDGE_LENGTH` (still 1.0) is a default used by
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
