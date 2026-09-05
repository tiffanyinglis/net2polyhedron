---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (the src/utils library, the .json net format, the fold pipeline, the Tkinter app, tests). Load before making non-trivial changes to this repo instead of re-deriving the pipeline by re-reading every file.
---

# Polyhedron net-folding project

## Untouchable files

These files are considered DONE -- the user has finished them and
deliberately doesn't want them touched, since editing them (even
additively) risks messing up code structure they've already settled on:

- `src/utils/polyhedron.py` (`Polyhedron`)
- `src/apps/polyhedron_unfolder/app.py`
- `src/utils/polyhedron_unfolder.py` (`Hinge`, `hinge_transform`, `face_normal`, `fold_transforms`)

Do not read these as a target for changes and do not modify them --
adding, removing, or "just cleaning up" anything in them is off limits --
UNLESS the user explicitly asks for a change to one of these files BY
NAME or by unambiguous description in their current request. If a task
would otherwise require touching one, stop and explicitly ask the user
for permission first, naming the file and what change is needed. This
list is expected to grow -- check it before editing anything here.

## What this project does

Takes a polyhedron (real 3D vertex positions + CCW face loops) and derives
how it unfolds: an auto-computed spanning tree of hinges, a flat 2D
layout, and each hinge's fold angle -- read directly off the given
geometry, not solved for numerically (see "Pipeline" below). One Tkinter
app, `polyhedron_unfolder` (`src/apps/polyhedron_unfolder/app.py`, class
`PolyhedronUnfolderApp`), shares one net picker across two tabs:
"Animated Fold" (drag a slider from flat to fully folded) and "Flat vs
Folded" (the flat 2D net and the fully folded 3D solid side by side at
once -- the 3D panel is mouse-rotatable via matplotlib's own 3D
navigation). Also handles **open** nets (a spec whose faces are a subset
of a solid's -- see "Open nets" below). No cache, no precompute step --
unfolding is cheap enough (no numerical solving) that picking a net just
unfolds it on the spot, in a background thread so the UI stays
responsive.

## Directory layout

`src/utils/` -- the reusable library, one flat module per concern (no
sub-packages):
- `polygon_geom.py` -- flat 2D polygon geometry: regular-polygon vertices
  and rigid 2D edge attachment (`rigid_transform_2d`/`apply_rigid`, also
  used by `unfoldable_polyhedron.py`'s flat-layout construction)
- `polyhedron.py` -- `Polyhedron`: pure 3D solid geometry (shared,
  indexed vertices; CCW vertex-index faces; derived edges; `is_closed()`)
  -- no awareness of nets, hinges, roots, fold progress, or color; those
  live in `unfoldable_polyhedron.py` instead
- `polyhedron_unfolder.py` -- the generic fold engine: `Hinge`
  (parent/child face, parent/child edge index, fold angle),
  `hinge_transform`, `face_normal`, `fold_transforms` (walks a list of
  `Hinge`, composing each one's rotation into a per-face cumulative 4x4
  transform). Not polyhedron-aware itself -- a flat net here is just a
  dict of per-face 2D points.
- `unfoldable_polyhedron.py` -- `UnfoldablePolyhedron`: derives a net
  (spanning tree, flat layout, fold angles) from an already-built
  `Polyhedron`, and folds it at any unfold amount.
  `UnfoldablePolyhedron.load(path)` is the public loading entry point.
- `spanning_tree.py` -- `create_spanning_tree_BFS`: a generic graph BFS,
  no polyhedron knowledge of its own
- `polyhedron_json_parser.py` -- parse/write the on-disk `.json` format

`src/apps/`:
- `polyhedron_unfolder/app.py` -- the app (see above)
- `common/` -- helpers shared across apps: `paths.py` (`NETS_DIR`/
  `OUTPUT_DIR`/`SAVE_DIR`, and the sys.path bootstrap that makes
  `from utils.<module> import ...` resolve when an app is run directly),
  `ui_theme.py` (shared Tk/matplotlib theme constants), `bounding_box.py`
  (rendering helper, not a `Polyhedron` method since it's a rendering
  concern, not domain geometry)
- `ui/` -- generic Tk/matplotlib widgets: `tooltip.py` (`Tooltip`),
  `cullable_face.py` (`_CullableFace`, exact backface culling for a
  closed convex solid's 3D render)

`data/input/nets/*.json` -- the canonical, hand-kept RIGID net specs: the
5 Platonic solids, a truncated icosahedron, and two open
dodecahedron-derived nets. Nothing regenerates these; anything that needs
one of these solids loads it straight from here.

`tests/`:
- `unit/` -- one test file per `src/utils/` module (e.g.
  `test_polyhedron.py` tests `polyhedron.py`), plus `unit/apps_common/`
  for the handful of `src/apps/common/` helpers with no Tkinter/
  matplotlib dependency (the rest of `src/apps/` stays untested)
- `integration/` -- tests that deliberately exercise multiple `utils`
  modules together, plus `helpers.py`'s shared fixture-builder classes
- `run_tests.py` -- `python tests/run_tests.py [pytest args...]`

Top level: `pytest.ini` (sets `pythonpath = . src src/apps`),
`requirements.txt`, `README.md`.

## The `.json` format

A direct encoding of a `Polyhedron`, nothing more:

```json
{
  "name": "...",
  "vertices": [[1, 1, 1], [1, 1, -1], ...],
  "faces": [[0, 1, 2, 3], [4, 5, 6, 7], ...]
}
```

`vertices` is real 3D positions; `faces` is each face's CCW
(viewed-from-outside) vertex-index loop. There's no root, no net/extra
edge split, no fold-angle field -- `UnfoldablePolyhedron` derives the
spanning tree, flat layout, and every fold angle itself from whatever
geometry is given here.

### Open nets

An "open" net (one that doesn't fold up into a closed solid) is just a
spec whose `"faces"` list is a face SUBSET of some solid's -- face
adjacency is derived directly from whichever faces are actually listed;
a face that would be adjacent to an omitted one just ends up with a
boundary edge instead of a hinge. Only include the vertices the listed
faces actually reference (an unreferenced vertex would still enlarge
`bounding_box()` around an invisible point).
`data/input/nets/half_dodecahedron.json` and
`dodecahedron_minus_one.json` are worked examples.

`Polyhedron.is_closed()` checks closure directly and purely
combinatorially (does every edge, by shared vertex index, appear in
exactly 2 faces?) -- no float tolerance involved.

## Pipeline (`unfoldable_polyhedron.py`)

`UnfoldablePolyhedron.load(path)` parses a `.json` spec and funnels into
these steps, all computed fresh (no cache -- see below):

1. **Face adjacency** (`Polyhedron.compute_face_adjacency`) -- for every
   polygon edge of every face, is there another face with the SAME two
   vertices in the OPPOSITE order (a shared edge is v->w on one face,
   w->v on the other)? Read directly off the given faces, O(total edges).
2. **Spanning tree** (`spanning_tree.create_spanning_tree_BFS`) -- BFS
   from root (always face index 0) over that adjacency, giving a list of
   hinges; an unreached face raises `ValueError`.
3. **Flat layout** (`_build_flat_layout`) -- each face's own REAL 3D
   corners are projected into an orthonormal 2D basis within its own
   plane (`_project_face_to_2d`), then BFS-attached to its parent's
   already-placed shared edge, reversed, via `polygon_geom.rigid_transform_2d`/
   `apply_rigid`. The result is a genuinely DUPLICATED-vertex mesh --
   every face keeps its own private corners, nothing is merged even at
   hinge edges (a hinge-glued pair of corners lands at the identical 2D
   position anyway, so there's nothing to gain from bookkeeping the
   shared index).
4. **Fold angle** (`_hinge_fold_angle`) -- `arccos(dot(face_normal(parent), face_normal(child)))`,
   read directly off the given geometry's two adjacent face normals --
   this is the rotation-FROM-FLAT convention (see Conventions below),
   not the dihedral angle itself. Nothing is solved for, since the
   dihedral angle is already known from real coordinates.
5. `fold_transforms()` (in `polyhedron_unfolder.py`) is the actual
   rotation engine -- walks the hinge tree in BFS order, giving each face
   one cumulative 4x4 affine transform (`hinge_transform` builds each
   hinge's rotation, pivoting around the hinge's axis point so it
   composes with the parent's matrix via plain matrix multiplication:
   `M_child = hinge_M @ M_parent`). A nested hinge's axis is the
   parent's own flat edge mapped through the parent's already-computed
   matrix, which is why hinges must be processed in BFS order.
   `UnfoldablePolyhedron.get_unfolded_state(amount_unfolded)` applies
   each face's matrix to that face's own flat (z=0) points --
   `amount_unfolded=0` returns the original polyhedron directly (no
   reconstruction needed), `amount_unfolded=1` returns the flat layout
   directly (every fold angle scales to 0).

## No caching

Recomputes fresh on every `load()`/`for_polyhedron()` call -- caching
exists to avoid redundant *expensive* work, and this pipeline has no
numerical solving step to make expensive (worst case ~0.07s for the
32-face truncated icosahedron). The app still runs `load()` in a
background thread since Tk is single-threaded and any blocking call on
the main thread would freeze the UI regardless of how fast it is.

## Conventions worth knowing before editing

- Polygons are CCW as seen from outside the solid -- a shared edge
  appears as `v -> w` in one face's loop and `w -> v` in the other's, and
  a child face attaches to its parent via a *reversed* edge mapping,
  matching how a physical paper net unfolds to the outside.
- A stored "fold angle" is the rotation *from flat* (180° between
  coplanar faces), not the dihedral angle itself -- e.g. a cube's hinges
  rotate 90° (dihedral is also 90°, self-supplementary), a tetrahedron's
  hinges rotate 109.47° (dihedral is 70.53°).
- `polyhedron_unfolder.py` has no `if __name__ == "__main__"` demo block
  -- add new ad hoc verification as a real test in `tests/`, not a script
  block.
- **Comments and docstrings should be short: 3-5 lines, stating what the
  class/function does.** Go longer only for a genuine enumerated list
  (e.g. documenting several parameters or several cases). Avoid restating
  the "why" at length or re-explaining what a well-named identifier
  already makes obvious.
