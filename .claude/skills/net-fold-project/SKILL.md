---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (the src/utils library, .json/.fold formats, the fold solver, the stretchy-mesh solver, the Tkinter apps in src/apps, tests). Load before making non-trivial changes to this repo instead of re-deriving the pipeline by re-reading every file.
---

# Polyhedron net-folding project

Takes a polyhedron (real 3D vertex positions + CCW face loops) and derives
how it unfolds: an auto-computed spanning tree of hinges, a flat 2D layout,
and each hinge's fold angle -- read directly off the given geometry, not
solved for (see "Pipeline" below). Three Tkinter entry points share pieces
of this:

- `polyhedron_unfolder` (`src/apps/polyhedron_unfolder/app.py`) — pick a
  **rigid** net; two tabs share one net picker / compute-cache control
  bar: "Animated Fold" (drag a slider from flat to fully folded) and "Flat
  vs Folded" (the flat 2D net and the fully folded 3D solid side by side
  at once — the 3D panel is mouse-rotatable via matplotlib's own 3D
  navigation). Also handles **open** nets (a polyhedron spec whose faces
  are a subset of a solid's — see "Open nets" below). Originally two separate apps
  (`polygon_fold_app.py` / `polyhedral_net_app.py`), merged into one
  tabbed app since they shared almost all of their net-picker/compute-
  cache/theme-toggle machinery and always used the exact same rigid
  cache — see "The apps" below.
- `polygon_subdivision_app` (`src/apps/polygon_subdivision_app/app.py`) —
  unrelated to folding: a 2D-only demo that splits a triangle/square/.../
  8-gon into a fine triangular mesh (see "Polygon subdivision demo" below).
- `inflate_polyhedron_app` (`src/apps/inflate_polyhedron_app/app.py`) — a
  DIFFERENT solver entirely, for nets that can't stay rigid and flat at
  all (e.g. a face sharing more than one edge with a neighbor). See
  "Stretchy meshes" below — this is the most algorithmically involved
  part of the project.

Each app that needs a solve cache keeps it in its own `cache/` folder,
next to its `app.py` (`src/apps/polyhedron_unfolder/cache/`,
`src/apps/inflate_polyhedron_app/cache/`) — never shared between apps,
so no app depends on another app's cache directory, even though
`polyhedron_unfolder`'s own two tabs share one cache (they're the same
app now, not two apps coordinating).

## Directory layout

The project is split into `src/` (code), `tests/`, and `data/` (everything
on-disk that isn't code). Every module that used to live in the
now-removed `net_fold_utils/`/`subdivision_utils/` packages, and every
top-level script/app that used to live at the repo root or in `tools/`,
moved wholesale — no file's own content changed as part of the move
itself, only its import paths and (for apps) its data-directory constants.

`src/apps/` — one folder per GUI app, plus `common/` and `ui/` for code
shared across more than one of them:
- `polyhedron_unfolder/` — the merged rigid-pipeline app (see above)
  - `app.py` — entry point, class `PolyhedronUnfolderApp`. Builds ONE
    shared control bar (net picker, "Compute Folding Pattern", theme
    toggle, "Show Axes", status line) plus a `ttk.Notebook` with two
    tabs, each with its own matplotlib figure/canvas but reading the
    SAME loaded `self.net`/`self.colors` state — switching tabs never
    re-picks or re-solves anything. This consolidation is *why* the
    merge made sense: the two original apps duplicated all of that
    control-bar wiring on purpose (see git history), a tradeoff that
    stopped paying for itself once they became tabs of one app instead
    of two independent scripts.
  - `build_cache.py` — precompute/refresh this app's OWN unfolding cache
    (was the top-level `build_fold_cache.py`)
  - `cache/*.json` — the actual cache files (was `data/cache/fold_cache/`)
    — not shared with `inflate_polyhedron_app` (a different pipeline
    entirely) or any other app
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
    locations: `NETS_DIR`/`STRETCHY_NETS_DIR`/`OUTPUT_DIR`/`SAVE_DIR`
    (input nets and the interactive apps' saved output — NOT caches,
    those are per-app, above), all derived from `Path(__file__)`. An
    app one level deeper than `src/apps/` (e.g.
    `polyhedron_unfolder/app.py`) first does a tiny inline bootstrap
    (`sys.path.insert(0, str(Path(__file__).resolve().parent.parent))`)
    so `common`/`ui` are importable at all, THEN imports from
    `common.paths` before importing anything from `utils` — as an
    import side effect, `common/paths.py` inserts `src/` onto
    `sys.path`, which is what makes `from utils.<category> import ...`
    resolve when a script is run directly (`python src/apps/<app>/app.py`)
    rather than as an installed package
  - `ui_theme.py` — `STATUS_COLORS`/`PLOT_THEME`/`FACE_COLORS`/
    `DISABLED_SUFFIX`/`COMPUTE_TOOLTIP`, extracted here (they used to
    live in `polygon_fold_app.py`, imported by the other apps from it)
    specifically so no app depends on another app's module
  - `generate_platonic_nets.py` — (re)generates `data/input/nets/*.json` for the 5 Platonic solids + the truncated icosahedron from canonical 3D coordinates (`utils/geometry3d/solid_coords.py`) via `hull_to_spec.polyhedron_from_vertices`'s CCW face loops directly written out (no spanning tree to compute here — `net_unfolder.NetUnfolder` derives its own at load time, see "Pipeline" below)
  - `generate_stretchy_platonic_nets.py` — (re)generates `data/input/stretchy_nets/*.json` for the 5 Platonic solids from the *same* coordinates, via `hull_to_spec.polyhedron_from_vertices`'s CCW face loops directly (no spanning tree needed — vertex-loop format has no hinge/root concept)
  - `generate_open_dodecahedron_nets.py` — generates the two open-net examples (`data/input/nets/half_dodecahedron.json`, `data/input/nets/dodecahedron_minus_one.json`) by writing out a face SUBSET of the full dodecahedron's coordinates (remapped to only the vertices those faces reference)
  - `generate_subdivided_stretchy_nets.py` — writes `data/input/stretchy_nets/<name>_res<resolution>.json` fine-triangulated variants of an existing stretchy net (see "Fabric subdivision" below). These 4 `generate_*.py` scripts aren't imported by anything (each is its own CLI entry point); they live in `common/` anyway since they're maintenance tooling shared across whichever apps read the `data/input/` specs they produce, and neither `utils/` (no `__main__` scripts there, see Conventions) nor `ui/` fit
- `ui/` — generic Tkinter/matplotlib widgets, not net-fold domain logic:
  - `tooltip.py` — `Tooltip`, a small generic hover-tooltip helper for Tkinter (not net-fold-specific)
  - `cullable_face.py` — `_CullableFace` (see "The apps" below), extracted here since `polyhedron_unfolder` is now the only user but the class itself is still generic matplotlib/3D rendering logic, not fold-solving logic

`src/utils/` — the reusable library, split by concern (see each
sub-package's own `__init__.py` docstring for its module list):
- `geometry2d/` — flat 2D polygon geometry: `polygon_geom.py`, `stretchy_net_layout.py`
- `geometry3d/` — the rigid fold engine, stretchy-mesh solving, coordinates: `net_fold_core.py`, `stretchy_mesh.py`, `solid_coords.py`, `hull_to_spec.py`
- `subdivisions/` — fine-triangle-mesh subdivision: `polygon_subdivisions.py` (renamed from the old top-level `subdivision_utils/subdivisions.py` — a package can't contain a module with its own name) and `mesh_subdivide.py`, which builds a fine "fabric" triangulation of a whole stretchy net (see "Fabric subdivision" below)
- `model/` — `Polyhedron`: pure 3D solid geometry (shared, indexed vertices; CCW vertex-index faces; derived edges), with **no** awareness of nets, hinges, roots, fold progress, or color — used by both the rigid and stretchy pipelines. Unfolding-specific logic/objects live in `net_unfolder/` instead, never here.
- `net_unfolder/` — `NetUnfolder`: derives a net (spanning tree, unfoldable flat layout, fold angles) from an already-built `Polyhedron` — see "Pipeline" below. Also `hinge.py` (`Hinge`) and `cache.py` (checksummed cache for the computed net).
- `persistence/` — parse/write the on-disk `.json` polyhedron-spec format, plus shared checksum utilities: `polyhedron_spec.py`, `checksums.py`, `stretchy_cache.py`. `net_unfolder.cache.build_all` (and the stretchy-cache equivalent) take an explicit optional `cache_dir` param, threaded in by each app's own `CACHE_DIR` constant — `cache_path_for`'s OLD default (still used when `cache_dir` is omitted, e.g. in tests with `tmp_path`) derives the cache directory as a sibling of the net's own parent directory, which doesn't hold once caches live per-app under `src/apps/<app>/cache/` instead

`data/` — everything on-disk that isn't code (input specs and app output
ONLY — no caches; those are per-app, under `src/apps/<app>/cache/`, see
above):
- `input/nets/*.json` — RIGID net specs: a direct encoding of a `model.Polyhedron` (real 3D vertex positions + CCW face loops), hand-editable but usually generated from known coordinates (see `generate_platonic_nets.py` above)
- `input/stretchy_nets/*.json` — **human-authored** STRETCHY net specs (vertex-loop format, see below) — a parallel, differently-shaped set of input files, not interchangeable with `input/nets/*.json`
- `output/` — user-generated saves from `inflate_polyhedron_app`'s "Save" button (see "The app" below), created on demand

`tests/` — pytest suite (see Testing below):
- `unit/<category>/` — one test file per `src/utils/<category>/` module, mirroring `src/utils/`'s own sub-package layout exactly
- `integration/` — tests that deliberately exercise multiple `utils` sub-packages together, plus `helpers.py`, shared fixture-builder classes that keep an integration test reading as "build a net, load it, check a property" rather than repeating multi-argument setup calls inline
- `run_tests.py` — `python tests/run_tests.py [pytest args...]`

Top level:
- `pytest.ini` — sets `pythonpath = . src` so tests can `import utils` regardless of cwd
- `requirements.txt` — numpy, scipy, networkx, matplotlib, sv-ttk, (dev) pytest
- `README.md` — user-facing usage doc (install, run the app, write a `.json` net, the cache, tests)

## The `.json` format (RIGID pipeline)

Full grammar lives in `src/utils/persistence/polyhedron_spec.py`'s docstring --
a direct encoding of a `model.Polyhedron`, nothing more:

```json
{
  "name": "...",
  "vertices": [[1, 1, 1], [1, 1, -1], ...],
  "faces": [[0, 1, 2, 3], [4, 5, 6, 7], ...]
}
```

`vertices` is real 3D positions; `faces` is each face's CCW
(viewed-from-outside) vertex-index loop. There's no root, no net/extra
edge split, no per-face degree list, no coordinates-vs-combinatorics
distinction at all -- `net_unfolder.NetUnfolder` (see "Pipeline" below)
derives the spanning tree, flat layout, and every fold angle itself from
whatever geometry is given here. This is a deliberate simplification from
an earlier abstract faces/edges spec format (no coordinates, fold angles
numerically solved for): seeing this project's own history is useful if
you're wondering why a `fold_solver.py`-shaped module doesn't exist
anymore -- there's nothing left to solve for once real coordinates are
given (see "Pipeline" below for exactly why).

### Open nets

An "open" net (one that doesn't fold up into a closed solid) is simply a
spec whose `"faces"` list is a face SUBSET of some solid's -- no special
field or bookkeeping needed, since `NetUnfolder` derives face adjacency
directly from whichever faces are actually listed; a face that would be
adjacent to an omitted one just ends up with a boundary edge instead of a
hinge. The one rule: only include the vertices the listed faces actually
reference (an unreferenced vertex would still count toward
`Polyhedron.bounding_box()`, silently enlarging it around an invisible
point). `data/input/nets/half_dodecahedron.json` and
`data/input/nets/dodecahedron_minus_one.json` are worked examples
(generated by `src/apps/common/generate_open_dodecahedron_nets.py` from
the same dodecahedron coordinates the closed `data/input/nets/dodecahedron.json`
uses, remapped to a face subset instead of the full set).

An open net's fold is generally an **open, non-convex** shape even at
t=1 -- `model.Polyhedron.is_closed` checks this directly and purely
combinatorially (does every edge, by shared vertex INDEX, appear in
exactly 2 faces?) once vertices are merged into indices (see
"Pipeline" below) -- no float tolerance involved at that point at all.
`polyhedron_unfolder` checks it (both tabs, independently) before applying
`_CullableFace` backface culling (see below), which is only valid for a
closed convex solid.

## Pipeline (`src/utils/net_unfolder/net_unfolder.py: NetUnfolder`)

The object model is split across two packages on purpose:
`src/utils/model/` holds only `Polyhedron` -- pure 3D-mesh geometry
(shared, indexed `vertices`, CCW vertex-index `faces`, derived `edges`)
with **no** awareness of nets, hinges, roots, fold progress, or color --
while `src/utils/net_unfolder/` holds everything unfolding-specific:
`Hinge` (parent/child face indices, edge indices, angle) and `NetUnfolder`
itself. `Polyhedron` describes BOTH the pre-fold flat net (`NetUnfolder.flat`,
at z=0) and every fold stage in between and after (`NetUnfolder.fold(t)`),
not just the final closed solid -- this works because an unfolded net is
exactly the kind of mesh `Polyhedron` already handles without
modification: a hinge-glued edge is *genuinely* shared (two faces meet
there at any `t`, even `t=0`), while a non-hinge closure edge is *not yet*
shared (its two faces only coincide once folded) -- "one edge becomes
two, one vertex becomes several" until folding brings them together, and
`Polyhedron.is_closed` simply reports this honestly at whatever `t` you
ask.

`NetUnfolder.load(path, cache_dir=None)` is the one public loading entry
point for a `.json` spec (via the cache, see below); `NetUnfolder.for_polyhedron(polyhedron, root=0, cache_path=None)`
is the same thing for an already-built `Polyhedron` with no source file.
Both funnel into `NetUnfolder._compute`, which derives everything fresh:

1. **Face adjacency** (`_face_adjacency`) -- for every polygon edge of
   every face, is there another face with the SAME two vertices in the
   OPPOSITE order (the CCW-from-outside convention: a shared edge is
   v->w on one face, w->v on the other)? Read directly off the given
   `Polyhedron`'s own face loops, in O(total edges) -- no planar
   embedding, no `networkx`, no possibility of "duplicate edge" failure
   for a face pair sharing more than one edge (that combinatorial
   ambiguity only existed because the OLD abstract format had no
   coordinates to disambiguate with; a real `Polyhedron` already knows
   exactly which edge is which).
2. **Spanning tree** (`_spanning_tree`) -- BFS from `root` (always face
   index 0; any face works equally well as root, same reasoning as the
   old format's root selection) over that adjacency, giving a list of
   hinges (parent/child face index, parent/child edge index) -- an
   unreached face after the BFS (some faces disconnected by shared
   edges) raises.
3. **Flat layout** (`_build_flat_layout`) -- each face's own REAL 3D
   corners are projected into an orthonormal 2D basis within its own
   plane (`_project_face_to_2d`; u = first edge direction, w = face
   normal, v = w x u -- exact same edge lengths as the real face, works
   for irregular faces too, not just regular polygons), then BFS-attached
   to its parent's already-placed shared edge, reversed, via
   `polygon_geom.rigid_transform_2d`/`apply_rigid` (the same rigid-2D-attach
   math the old regular-polygon-only net layout used). The result is
   wrapped into a `net_fold_core.Net` and passed through
   `net_fold_core.flatten_net` -- z=0-padding + clustering coincident
   corners into shared vertex indices (unchanged, see step 5) -- giving
   `NetUnfolder.flat`, a `Polyhedron` at z=0.
4. **Fold angle** (`_hinge_fold_angle`) -- `arccos(dot(face_normal(parent), face_normal(child)))`,
   read directly off the GIVEN geometry's two adjacent face normals. This
   is this project's existing rotation-from-flat convention exactly (90°
   for a cube's self-supplementary 90° dihedral, 109.47° for a
   tetrahedron's 70.53° dihedral -- see "Conventions" below) -- there is
   nothing to *solve* for, since the dihedral angle is already known.
   This is the whole reason the old `fold_solver.py` (scipy
   `least_squares`, a 17-point restart sweep, exact Jacobian sparsity,
   rejecting "collapsed" self-intersecting solutions -- see this
   project's git history if you're ever tempted to reintroduce a
   solving step) doesn't exist anymore: it solved for something that's
   directly measurable once real coordinates are given.
5. `net_fold_core.fold_transforms()` is the actual rotation engine --
   walks the hinge tree in BFS order, giving each face one cumulative 4x4
   affine transform matrix (`scipy.spatial.transform.Rotation` builds
   each hinge's rotation; `hinge_transform()` embeds it into a 4x4 that
   also pivots around the hinge's axis point, so it composes with the
   parent's matrix via plain matrix multiplication: `M_child = hinge_M @
   M_parent`). A nested hinge's axis is the parent's own flat edge
   (a pair of shared vertex indices) mapped through the parent's
   already-computed matrix, which is exactly why hinges must be
   processed in BFS order. `fold()` is a thin wrapper that applies each
   face's matrix to that face's own flat (z=0) points, returning
   `dict[face_index -> (N,3) ndarray]`. `NetUnfolder.fold(t)` goes one
   step further: `net_fold_core.cluster_faces_into_mesh()` merges the
   per-face-corner points this produces into a proper indexed mesh
   (shared vertices, CCW vertex-index faces) -- the SAME merge used to
   build `NetUnfolder.flat` in step 3, reused rather than reinvented.

Since solving is gone, this whole pipeline is now fast even for the
bushiest net -- the 32-face, 31-hinge truncated icosahedron went from
the old solving pipeline's ~30-45s down to ~0.07s. Caching (below) is
therefore more "avoid redundant recomputation" than "avoid an expensive
solve" now, but the contract is unchanged.

## Caching (`src/utils/net_unfolder/cache.py`)

A cache file (in `src/apps/polyhedron_unfolder/cache/`, not
`data/input/nets/`) is plain JSON: the flat layout's 2D vertices/faces,
the hinge list (parent/child/edge indices/angle in degrees), and a
`checksum` of the source `.json`. `NetUnfolder.load()` transparently
reuses the cache if the checksum still matches, else recomputes and
rewrites it.

- `is_cached(net_path)` -- read-only check, never mutates anything, and
  never needs to construct a `Polyhedron` (just compares the cache file's
  own stored checksum field) -- safe to call just to decide how to render
  a net (e.g. in the app's net list).
- `_clear_stale_cache` -- the same cheap, `Polyhedron`-free checksum
  check `is_cached` uses; when a cache's checksum no longer matches its
  source (the `.json` was edited, possibly into something that no longer
  even parses), the stale cache file is **deleted immediately**, before
  the source is even parsed. This means a failed recompute never leaves a
  misleading stale cache behind; the net correctly falls back to "not
  computed" instead. `_valid_cache_or_clear_stale` does the same check
  but additionally reconstructs a ready `NetUnfolder` (needs an
  already-parsed `Polyhedron`, unlike the cheap checksum-only variants
  above) -- what `NetUnfolder.load`/`for_polyhedron` need for an actual
  cache hit.
- `build_all(nets_dir, cache_dir=None, force=False, on_progress=None)` --
  computes/refreshes every net's cache; shared by `build_cache.py` (CLI,
  prints progress) and the app's "Compute Folding Pattern" button (runs
  in a background thread, reports via a `queue.Queue` polled from the
  main thread -- Tk widgets must only ever be touched from the main
  thread).
- Run `python src/apps/polyhedron_unfolder/build_cache.py` after editing a `.json` file to warm the
  cache ahead of time (`--force` recomputes unconditionally); otherwise it
  happens lazily on first load.

## The apps (`polyhedron_unfolder`)

Tkinter UI on the `sv_ttk` theme (dark by default, light/dark toggle
button). ONE shared `LabelFrame`-grouped control bar sits on top: net
picker + Compute button + "Show Axes" checkbox (off by default) + theme
button + status line — built once in `PolyhedronUnfolderApp.__init__`,
not duplicated per tab. Below it, a `ttk.Notebook` with two tabs, each
built by its own `_build_*_tab` method: "Animated Fold" (a single 3D plot
plus the fold slider) and "Flat vs Folded" (a flat-net panel beside a
folded-3D panel, always at `t=1.0`, no slider). Both tabs read the same
`self.net`/`self.colors`/etc. state, set once by `on_select_net`, and are
redrawn together (`_refresh_plot` calls both `draw_fold`/`draw_compare`)
on any state change (net selection, theme, axes) — only the slider,
`on_slider`, redraws just the "Animated Fold" tab.

- Nets without a valid cache file show a `(not computed)` suffix and are
  greyed out in the dropdown (`_style_disabled_items` — a best-effort
  reach into ttk's Tcl popdown-listbox internals, wrapped in try/except
  since it's not public API; the text suffix + a selection guard in
  `on_select_net` are what actually make them unselectable, independent of
  whether the grey styling succeeds).
- `_apply_plot_theme` recolors BOTH tabs' figures/axes to match sv_ttk's
  theme (`common.ui_theme.PLOT_THEME`, mirroring sv_ttk's own `-bg`
  colors) and honors the "Show Axes" toggle; `draw_fold`/`draw_compare`
  call it fresh every redraw since `ax.cla()` wipes all of it back to
  matplotlib's defaults each time.
- `_draw_solid` (shared by both tabs -- the "Animated Fold" tab's single
  3D view and the "Flat vs Folded" tab's right-hand panel) centers the
  view on the shape's own bounding-box center (not its raw min/max) with
  one shared half-width across all three axes, so the shape sits in the
  middle of the cubic plot regardless of which direction the net layout
  happens to extend, and `set_box_aspect([1, 1, 1])` isn't distorted by
  unequal per-axis ranges.
- `_draw_box_wireframe` manually draws all 12 edges of the bounding box
  when axes are shown: matplotlib's default 3D pane borders only draw the
  9 edges belonging to the 3 panes it renders for a fixed view angle, so
  the near vertical corner where the two visible walls meet is otherwise
  left undrawn.
- `_CullableFace` (`src/apps/ui/cullable_face.py`, imported by
  `polyhedron_unfolder`) fixes wrong-face-on-top glitches in the fully
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
  to an open/non-convex net. `_draw_solid` therefore only uses it when
  `solid.is_closed` (a `model.Polyhedron` property) is true (for the
  "Animated Fold" tab this in practice also means `t == 1.0`, since
  mid-fold edges don't yet coincide and an open net -- a face subset --
  never closes even at t=1; for the "Flat vs Folded" tab, always at
  `t = 1.0`, it's the ONLY gate); for anything else it falls back to a
  plain `Poly3DCollection`.
  `Polyhedron.face_normal()` computes each face's outward unit normal
  via the cross product of its first two edges -- verified (see
  `test_net_fold_core.py`) to be consistently outward-pointing for every
  face of every net in `data/input/nets/`, relying on the net's CCW winding
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
  `success` / `error` / `warn` → `common.ui_theme.STATUS_COLORS`).

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

## Stretchy meshes (`src/utils/geometry3d/stretchy_mesh.py`, `inflate_polyhedron_app`)

For nets that **cannot** be realized with perfectly rigid, flat faces —
most sharply, two faces glued along more than one shared edge. If two flat
polygons share ≥3 non-collinear points, both must lie in the one plane
those points determine — there's no dihedral fold left to make them
distinct faces of a solid. This is a genuine geometric impossibility, not
just a representational limitation of some rigid-pipeline data structure
— the rigid pipeline's own `Polyhedron`/`NetUnfolder` could combinatorially
describe such a face pair without any trouble (there's no more `EdgeMap`
planar-embedding step to reject it, see "Pipeline" above), but attempting
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
  (`data/input/stretchy_nets/two_pentagons_and_a_square.json`) instead of stretching
  it into a mess.
- A final light planarity pass (`PLANARITY_WEIGHT`, via per-face best-fit-
  plane SVD residuals) tidies up individual faces at the same pressure
  without relaxing it back down — inflation already tends to leave faces
  close to flat on its own (a taut membrane wants to be locally flat
  wherever its edges allow), so this only has a little polishing left to
  do.

This target-based pressure term (`_residual`) is specific to this
AUTOMATIC ramp, where a bounded target is exactly what lets it know when
to stop without a human watching. `inflate_polyhedron_app`'s
interactive "Inflate" button uses a DIFFERENT, target-free residual
(`_relax_residual`, see "The app" below) for the opposite reason: once
volume nears a fixed target, more pressure stops changing anything,
which is backwards for a human turning a pressure dial and expecting
"more pressure → more inflated".

### Orientation consistency (why this needed real iteration to get right)

Plain edge-length fitting has no opinion about orientation, so a stage-1
result is often already self-intersecting — one face folded inside-out
relative to the rest (a sharper version of the "collapsed branch" problem
the old rigid-pipeline fold solver used to reject via `_is_embeddable`,
back when rigid fold angles were numerically solved for rather than read
directly off given geometry — see "Pipeline" above). `_orientation_signs`
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
   self-intersecting mesh — `inflate_polyhedron_app/build_cache.py`'s existing
   `except ValueError` failure-reporting path surfaces this per-net.

A separate, cheap guard catches what orientation-consistency can't:
`_min_pairwise_separation(pts) > MIN_SEPARATION_FRACTION * edge_length`
rejects a result where two *unrelated* (non-adjacent) vertices happen to
have collapsed onto each other — face-normal signs don't notice that on
their own, since `_mesh_volume`'s pressure term has no particular reason
to keep distinct vertices apart.

### Caching (`src/utils/persistence/stretchy_cache.py`)

Mirrors `net_unfolder/cache.py` for the rigid pipeline, but recording just
a positions + stats dict (no hinge tree/fold angles to write out).
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

### The app (`inflate_polyhedron_app`) — precomputed starting shape, interactive from there

Rewritten (through a couple of iterations -- see git history if the
reasoning below seems oddly specific) from the original "pick a net, see
the one automatically-solved answer" design into a **three-stage
pipeline**, split between an offline precompute and an interactive app:

1. **Coarse solve** -- `stretchy_mesh.solve_wireframe` on the
   UN-subdivided coarse net. Its random-restart-plus-inflation-ramp
   search is exactly what makes this reliable: a coarse net has few
   enough faces that retrying a different random start when one doesn't
   inflate cleanly is cheap.
2. **Drape** -- for a fabric-subdivided net (see "Fabric subdivision"
   above), `mesh_subdivide.solve_fabric_mesh` drapes the fine mesh over
   that already-solved coarse shape, then does one light edge-length
   relaxation pass. (Applying pressure directly to a raw random start,
   skipping 1 and 2 entirely, was tried first and doesn't work: see
   "known, accepted risk" below for what that looked like empirically.)
3. **Interactive**: THIS app loads the result of 1+2 as iteration 0, then
   lets the user push further.

Steps 1-2 are precomputed/cached by `src/utils/persistence/stretchy_cache.py`
(same cache `inflate_polyhedron_app/build_cache.py` warms -- see "Caching" above) --
`on_select_net` calls `load_with_cache`, so opening the app on an
already-cached net (e.g. `cube_res3.json`, already warm) lands on a fully
rounded starting shape in about a second, not from a blank/random state.
`refresh_net_list` shows the old "(not computed)" suffix again for any
net that isn't cached yet (selecting it still works, it's just a fresh
solve instead of an instant read).

- **Net picker**: defaults to `data/input/stretchy_nets/cube_res3.json` if present
  (`DEFAULT_NET_BASENAME`), else the first net alphabetically.
- **The "Inflate" `LabelFrame`** groups everything about running
  `relax_once`, top to bottom in the order it's used: Pressure spinner,
  then the iterate-mode radio buttons, then the Inflate/Stop buttons.
  ("Save" and the net picker live in the "Net" frame above it instead --
  not inflation controls.)
  - **"Pressure" spinner**: a user-chosen, CONSTANT pressure passed to
    `relax_once`, continuing from wherever `self.positions` currently is
    (not from scratch) -- so repeated clicks let the user watch/steer the
    shape incrementally, rather than the app silently retrying different
    random starts under the hood. Default/max: 30.0 / 60.0 -- 30 reaches
    roughly 73% max stretch on `cube_res3.json` (see
    `stretchy_mesh._relax_residual` below for why these numbers, and why
    that's a much bigger number than an earlier ~5.5%-at-default
    calibration).
  - **`stretchy_mesh._relax_residual`: pressure has NO target volume,
    unlike `_inflate`/`solve_wireframe`'s `_residual`, AND is PER FACE,
    not one global term for the whole mesh.** These are two separate
    design points, addressing two separate problems:
    1. *No target*: `_residual`'s pressure term is `inflation_weight *
       (inflation_target - volume)` -- a TWO-SIDED penalty, zero exactly
       at a fixed, precomputed `_sphere_bound_volume` target, growing
       whether volume over- or undershoots it. That's exactly right for
       the automatic coarse-solve ramp (`INFLATION_WEIGHTS`), which needs
       a bounded target to know when to stop on its own -- but it means
       more pressure eventually does NOTHING: once volume is close to
       that fixed ceiling, no amount of extra weight can ask for more
       (verified on an earlier version of the default cube net: max
       stretch plateaus at ~5.5% from pressure ~100 all the way past 300).
       For a human dialing pressure by hand and expecting "more pressure
       = more inflated", that's backwards. `relax_once` uses
       `_relax_residual` instead: `pressure * exp(-v_f / reference_volume)`
       per face `f` -- no target, shrinks toward (but never reaches) zero
       as that face's own volume contribution grows, so there's always a
       gradient rewarding more volume, with no ceiling.
    2. *Per face, not one global term*: a single global
       `pressure * exp(-total_volume)` residual (an earlier version of
       this function) gives the optimizer a CHEAP way to satisfy it on a
       mesh with many vertices/faces that doesn't involve genuinely
       inflating at all -- fold one small local patch of the mesh through
       itself. That fold spikes `_mesh_volume`'s naive divergence-theorem
       sum (a self-intersecting surface can integrate to an arbitrarily
       large SIGNED volume) while leaving nearly every edge, and every
       OTHER face's own local geometry, completely untouched -- cheaper,
       in a sum-of-squares sense, than genuinely stretching the whole
       mesh a little. A coarse mesh (few faces, e.g. `cube.json`) has no
       room for this: every vertex has too much leverage over too large a
       fraction of the mesh's edges. A subdivided FINE mesh (hundreds of
       small faces, e.g. `cube_res3.json`) is exactly where the cheat has
       room to hide. Splitting the SAME formula into one residual PER
       FACE closes the loophole: folding one face's own patch now only
       reduces THAT face's own residual, while every other face's
       residual still wants ITS OWN volume to increase -- so a local fold
       is no longer numerically cheaper than genuine, mesh-wide expansion.
       This also happens to match real pressure's physics more directly
       than a global term ever did: the gradient of one face's own volume
       contribution with respect to moving that face outward is
       proportional to that face's own AREA (`dV/d(extrusion distance) =
       surface area`), so this residual's local gradient is naturally a
       force-per-area quantity -- much closer to what "pressure" means
       physically than a single mesh-wide scalar ever was.
    `exp`, not `1/v_f`, specifically to stay smooth and finite even for a
    negative/near-zero volume (a tangled starting configuration) --
    `_mesh_volume`'s docstring already flags a `1/distance`-style
    singularity as exactly what this residual family needs to avoid.
    `reference_volume` normalizes each face's `v_f` against that mesh's
    OWN characteristic scale (a dodecahedron's faces individually enclose
    much more volume at edge_length=1 than a cube's, so the SAME raw
    pressure means very different things unnormalized) -- computed once
    per net via `stretchy_mesh.per_face_volumes` on that net's own
    starting shape (`_on_loaded`, stored as `self.reference_volume`, an
    array with one entry per face) and reused for every subsequent
    Inflate click on that net, so a given pressure value keeps meaning a
    consistent thing across repeated clicks. **Getting an accurate read
    on any of this requires the mesh's CORRECT, non-uniform per-edge rest
    lengths** (`self.edge_length`, from `subdivide_mesh` -- see "Fabric
    subdivision" above): testing this residual with a uniform
    `edge_length=1.0` on a fine mesh (whose real rest lengths are much
    shorter, e.g. ~0.24-0.33 on `cube_res3.json`) manufactures a huge,
    unrelated built-in stretch demand that has nothing to do with the
    pressure term at all, and is easy to mistake for a solver bug.
    At sufficiently high pressure, the old diagonal-split n=4 subdivision
    (see "Polygon subdivision demo" above) also showed a visible lopsided
    bulge, traced to an asymmetric mesh valence at some of a cube's
    corners -- fixed by switching SUBDIVISIONS[4] to a centroid fan (see
    "Fabric subdivision" above), not by anything in this residual.
  - **`stretchy_mesh.is_orientation_consistent`** (public wrapper around
    `_is_orientation_consistent`) is used by `_run_inflate_stream` as a
    cheap, general-purpose safety net on top of the per-face fix above:
    after every chunk, if the result is no longer orientation-consistent,
    it's REJECTED (positions not updated) and retried at half the chunk
    size; once a size is found to cause this, a `ceiling` permanently
    caps how far that Inflate click's chunk is ever allowed to grow back
    to again, so the loop can't oscillate forever between "too small to
    move anything" and "big enough to fold" -- it settles on some safe
    operating size instead. If even a single-evaluation chunk fails this
    check, inflation stops there and is reported to the user as unsafe at
    this pressure, rather than looping forever or silently accepting a
    corrupted result.
  - **Radio buttons** control how much work one "Inflate" click does:
    "Iterate for N steps" passes `max_nfev=N` to `relax_once` (the
    closest thing scipy's trust-region solver exposes to "N steps" --
    there's no clean "run exactly N iterations" knob); "Iterate until
    convergence" (the default) passes `max_nfev=None`, running to the
    solver's own tolerance (`stretchy_mesh.CONVERGENCE_GTOL = 1e-8`,
    passed explicitly to `least_squares` so it's a known, displayable
    value rather than relying on scipy's own default staying put across
    versions) -- picked as the default over "steps" since a large fine
    mesh (e.g. `dodecahedron_res3.json`, 1446 variables) can need many
    iterations before the shape looks settled, and there's no obvious
    step COUNT a user would otherwise know to ask for up front.
  - **Live progress, not one big jump**: `on_inflate_clicked` doesn't
    make ONE `relax_once` call for the whole request -- `_run_inflate_stream`
    calls it repeatedly in a GROWING sequence of chunks (`INFLATE_CHUNK_START
    = 5`, doubling up to `INFLATE_CHUNK_MAX = 200`), pushing a "progress"
    message (redraws + bumps the iteration counter) after every chunk.
    Growing matters: each chunk is a fresh `least_squares` call with no
    memory of the previous one's shrunk trust-region radius, so a FIXED
    small chunk size can get stuck re-exploring the same neighborhood
    forever without ever reaching real convergence, even after hundreds
    of total steps. Starting small keeps early feedback frequent while
    steps are cheap, then growing lets later chunks actually be large
    enough to finish. How long a full "until convergence" run actually
    takes varies enormously by mesh size and pressure -- a few seconds
    for `cube_res3.json` (330 variables) at modest pressure, but each
    individual chunk on `dodecahedron_res3.json` (1446 variables) at
    pressure=30 was measured taking 30-90+ seconds on its own, since a
    numerical-Jacobian evaluation's cost scales with variable count; the
    live progress updates (and the Stop button) exist specifically so a
    slow run like that stays visibly alive and interruptible rather than
    looking hung.
    `INFLATE_SAFETY_STEP_CAP = 5000` hard-stops "until convergence" mode
    if a mesh/pressure combination genuinely never reaches
    `CONVERGENCE_GTOL`, instead of looping forever.
  - **Won't re-run once converged**: `_update_inflate_button_state`
    greys out the Inflate button whenever `self.last_stats["converged"]`
    is true, and `on_inflate_clicked` refuses to run even if clicked
    anyway. This isn't just cosmetic -- verified empirically that
    re-running `relax_once` from an already-converged point can burn
    real steps without moving anything (a fresh `least_squares` call has
    no memory of how far the previous one's trust region had already
    shrunk, so it doesn't just no-op, it can wander a while
    re-discovering the same spot). Re-armed by `_on_pressure_changed` (a
    `trace_add("write", ...)` on `pressure_var` -- a "converged" verdict
    only applies to the pressure it was reached at) and by loading a new
    net; a Stop leaves `converged=False` since it didn't run to
    completion, so the button stays enabled after one.
  - **"Stop" button** sets a `threading.Event` (`self.stop_event`,
    created fresh per Inflate click) that `relax_once`'s residual wrapper
    checks on every evaluation, raising `stretchy_mesh.RelaxStopped`
    internally to abort at the next evaluation rather than waiting for
    scipy's own stopping criteria or the step cap -- returns whatever
    position was last evaluated. Disabled except while an Inflate is
    actually running (armed by `on_inflate_clicked`, disabled again by
    `_set_controls_enabled(True)` once any background job finishes --
    only `on_inflate_clicked` arms it, so it stays disabled during the
    initial cache load, which isn't usefully interruptible).
  - `relax_once`'s reported step count is scipy's own `sol.nfev`, NOT the
    residual wrapper's raw call count -- the wrapper counts every actual
    invocation (including numerical-Jacobian perturbations), which can
    run to hundreds or thousands past `max_nfev`'s nominal value before
    scipy checks the cap again; `sol.nfev` is what keeps a "10 steps"
    request corresponding to a reported step count near 10, not some much
    larger multiple. The raw count is used as a fallback ONLY when a Stop
    request aborts before scipy ever returns a result (no `sol` to read
    `nfev` from in that case) -- and even then it's capped at that call's
    own `max_nfev`, so a Stop can never look like it consumed more steps
    than the chunk it interrupted actually asked for.
  - The bottom-of-figure annotation (`draw()`, via `fig.text` -- see
    below) shows `optimality` (scipy's first-order optimality measure,
    should approach 0) against `CONVERGENCE_GTOL`, plus whether THIS
    press actually converged by scipy's own tolerance vs. hit the step
    cap (or a Stop request) first -- `optimality` is `None`/shown as
    "n/a" right after loading (before any Inflate press) or after a
    Stop, since neither path has a real scipy result to read it from.
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
- **"Save" button** (in the "Net" frame, not "Inflate" -- it isn't an
  inflation control) writes the current vertex positions (plus
  `iteration`, `pressure`, `stats` -- including `optimality`/`converged`
  -- `faces`, and -- for a fabric net --
  `coarse_faces`/`resolution`/`face_of_fine`) to `data/output/Save/<source>_<timestamp>.json`,
  and the current figure (which embeds the "Iteration: N | ..." line via
  `fig.text` at the bottom -- so it's part of the rendered image, not
  just a separate Tk label, and gets captured by `savefig` too) to
  `data/output/Save/<source>_<timestamp>.png` -- same stem, so the two files are easy
  to pair up later.
- The initial cache load runs in a background thread via `_run_background`;
  each "Inflate" click runs via the streaming variant, `_run_inflate_stream`
  (see above) -- both because either can take a while and because Tk
  isn't thread-safe, so the worker only ever pushes to a queue and the
  main thread (via a scheduled `after` poll) is the only one touching
  widgets.
- **Left panel is a real connected net, not disconnected islands**:
  `on_select_net` precomputes `self.target_layout` once via
  `src/utils/geometry2d/stretchy_net_layout.py`'s `build_stretchy_net_layout` --
  a breadth-first search over faces sharing an edge (derived directly
  from each face's own vertex-loop order, no separate combinatorics step
  needed -- unlike the rigid pipeline's old `EdgeMap`-based planar
  embedding, which couldn't represent a stretchy mesh's multi-shared-edge
  face pairs at all; the rigid pipeline no longer needs a planar
  embedding either, since it now reads face adjacency directly off a real
  `Polyhedron`'s own geometry -- see "Pipeline" above -- but multi-shared-edge
  face pairs still can't be laid out flat and rigid, which is the actual
  reason this stretchy path exists, not a representational one),
  attaching each newly-discovered face to whichever neighbor's edge found
  it first via `polygon_geom.attach_polygon` (reversed, so it unfolds
  outward -- same convention `net_unfolder.py`'s `_build_flat_layout`
  uses for the rigid pipeline).
  A face pair sharing MORE than one edge just means extra entries that
  BFS never uses for placement (only the first edge to a still-unplaced
  face matters), same as an `edges.extra` edge would be ignored for
  layout in the rigid `.json` format. `_draw_target_faces` just reuses
  the precomputed `self.target_layout` on every redraw rather than
  recomputing the BFS each time; the per-face raw-vertex-id text label
  (e.g. "[4, 0, 2, 6]") that stood in for a real layout before is gone.

## Testing

`pytest` (from repo root, or anywhere — `pytest.ini` sets
`pythonpath = . src`). `tests/unit/<category>/` mirrors `src/utils/`'s own
sub-package split exactly, one test file per module; `tests/integration/`
holds the tests that deliberately cross sub-package boundaries (currently
just `test_open_nets.py` — see below) plus `helpers.py`'s shared
fixture-builder classes. The **rigid**-pipeline suite is fast (no
numerical solver left to run at all — see "Pipeline" above) and still
deliberately only exercises small nets directly (tetrahedron, cube, a
synthetic paper-cube net, a tiny open net); there's no test that builds
the icosahedron/truncated-icosahedron by hand, though `NetUnfolder` is
exercised against every real net in `data/input/nets/` via
`build_cache.py`/the app itself. Files map roughly 1:1 to `src/utils/`
modules (`unit/geometry2d/test_polygon_geom.py`,
`unit/geometry3d/test_net_fold_core.py`, `unit/persistence/test_polyhedron_spec.py`,
`unit/geometry3d/test_hull_to_spec.py`, `integration/test_open_nets.py`,
`unit/subdivisions/test_polygon_subdivisions.py`), plus `unit/model/test_polyhedron.py`
(the pure-geometry class, index-based `is_closed`/`edges`, no unfolding
knowledge) and `unit/net_unfolder/*.py` (one file per `Hinge`/`NetUnfolder`
class, covering spanning-tree derivation, flat-layout vertex sharing,
fold angles matching known dihedral angles, folding at several `t`, and
`cache.py`'s reuse/staleness contract, which mirrors
`unit/persistence/test_stretchy_cache.py`'s for the stretchy pipeline).

The **stretchy**-pipeline suite (`unit/geometry3d/test_stretchy_mesh.py`) is slower
(~30-60s) since even the small Platonic solids run the real
`solve_wireframe` — the dodecahedron and icosahedron are deliberately kept
OUT of it (same rationale as the rigid suite) and verified manually
instead. Includes `monkeypatch`-based tests of the orientation-consistency
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
rest of the suite). Includes a check that pressure genuinely has no
plateau (`test_relax_once_pressure_has_no_plateau_unlike_a_fixed_target`
-- strictly increasing stretch at pressure 1/5/20 on `cube.json`), the
property `_relax_residual` exists specifically to have, unlike
`_residual`'s target-based term.

`unit/subdivisions/test_mesh_subdivide.py` covers the fabric-subdivision pipeline (see
above): combinatorial closure of the fine mesh at several resolutions,
that shared coarse edges actually merge (not left as disconnected
per-face patches), that a pentagon face's fine edges have exactly two
distinct rest lengths (rim vs. spoke, not a uniform one), and that
`solve_fabric_mesh` produces low-stretch results for both an
already-rigid coarse net (tetrahedron) and a genuinely bendy one
(`two_pentagons_and_a_square.json`) — fast (~5s total) since the
drape-then-relax approach never needs the slow random-restart search.

`unit/geometry2d/test_stretchy_net_layout.py` covers `build_stretchy_net_layout` (see
"The app" above) across every net in `data/input/stretchy_nets/`: every face gets
placed, every placed face keeps its exact unit-edge regular-polygon shape
(rotation/translation only, no distortion), and -- reproducing the same
BFS the function itself does -- every edge the tree actually attaches
through lands its two faces' shared corners on the same two 2D points
(the ones it DOESN'T attach through, for a face pair sharing more than
one edge, are deliberately not checked -- see the module docstring for
why that's expected, not a bug).

## Conventions worth knowing before editing

- The STRETCHY pipeline's polygon edges all have length 1
  (`stretchy_mesh.EDGE_LENGTH`, capped stretch via `STRETCH_CAP`) since
  its nets are hand-authored combinatorics with no coordinates of their
  own. The RIGID pipeline has no such requirement anymore -- since
  `NetUnfolder` reads real, already-given coordinates (`data/input/nets/*.json`),
  edge length is simply whatever the input `Polyhedron` says (e.g.
  `solid_coords.cube()`'s raw canonical coordinates have edge length 2,
  not 1) -- `polygon_geom.EDGE_LENGTH` (still 1.0) is now only a default
  used by `regular_polygon_vertices`/`attach_polygon`, which the stretchy
  pipeline's `stretchy_net_layout.py` still calls, not anything in the
  rigid pipeline's own `net_unfolder.py`.
- Polygons are CCW as seen from outside the solid, in **both** pipelines
  (rigid: `net_unfolder._face_adjacency`/`_build_flat_layout` — a shared
  edge appears as `v -> w` in one face's loop and `w -> v` in the other's,
  and a child face attaches to its parent via a *reversed* edge mapping,
  matching how a physical paper net unfolds to the outside; stretchy:
  `stretchy_mesh.py`'s module docstring — the same `v -> w`/`w -> v`
  convention).
- A stored "fold angle" (rigid pipeline only) is the rotation *from flat*
  (180° between coplanar faces), not the dihedral angle itself — e.g. cube
  hinges rotate 90° (dihedral is also 90°, self-supplementary), tetrahedron
  hinges rotate 109.47° (dihedral is 70.53°). Read directly off the given
  geometry now (`net_unfolder._hinge_fold_angle`), not solved for.
- `net_fold_core.py` and `stretchy_mesh.py`/`stretchy_cache.py` have no
  `if __name__ == "__main__"` demo blocks — that logic lives in `tests/`.
  Add new ad hoc verification as a real test, not a script block.
- Rigid nets (`data/input/nets/*.json`) and stretchy nets (`data/input/stretchy_nets/*.json`) are
  NOT interchangeable formats, even though both are JSON with a `"faces"`
  key — one is `{"vertices": [[x,y,z], ...], "faces": [[i,j,k,...], ...]}`
  (real coordinates + CCW vertex-index loops), the other is plain
  vertex-id-loop lists with no coordinates at all. Loading one with the
  other pipeline's loader will fail (usually confusingly) rather than
  "just working".
