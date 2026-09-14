# Project history (net-fold-project)

Read this only when you need the "why" behind an untouchable file or a
deleted subsystem — not needed for ordinary changes.

## Untouchable-file exceptions granted so far

Only these specific, narrow exceptions have been made to the wholesale
untouchable marking (not a sign it's loosening — still ask first for
anything else):

- `stretchy_mesh.py` (+ its test + `docs/README.md`): to let a stretchy
  mesh stay OPEN rather than requiring a closed 2-manifold; later again to
  add `estimate_pressure_for_target_stretch`'s optional `gtol` parameter.
- `inflate_polyhedron_app/app.py`, repeatedly, each for one specific
  feature only that file could hold: showing a net exactly as
  `interactive_builder_app` saved it (`_layout_from_net_layout`, with a
  Y-flip fix, and Net-panel scroll-to-zoom); tiling the net
  picker/Target RMS/Tolerance controls horizontally; a "(stalled)" label
  next to a converged-but-above-threshold checkmark; two debug-only
  diagnostics ("Validate Mesh", "Show normals"). All documented in the
  `inflate-polyhedron-app` skill.

Most of the untouchable list is synced from the sibling
`polyhedron-unfolder` project (byte-identical or differing only in import
paths) — files that have genuinely diverged (e.g. `paths.py`) were
deliberately NOT synced since this project's version has functionality
the sibling's lacks.

## Removed: the rigid-unfolding pipeline

`src/apps/polyhedron_unfolder/`, `src/utils/polyhedron_unfolder/`,
`src/utils/persistence/polyhedron_spec.py`, their tests, and
`data/input/nets/*.json` have been **deleted** from this project — that
functionality now lives solely in the sibling `polyhedron-unfolder`
project.

**What it did**: took a polyhedron (real 3D vertex positions + CCW face
loops, a `{"name","vertices","faces"}` spec) and derived how it unfolds —
an auto BFS spanning tree of hinges over face adjacency, a flat 2D layout,
and each hinge's fold angle read directly off the given geometry
(`arccos(dot(face_normal(parent), face_normal(child)))`, the rotation
*from flat*) rather than solved for. It also handled open nets (a subset
of some solid's faces; an omitted-adjacent edge just becomes a boundary
edge). Its `Polyhedron` class is what `src/utils/geometry/polyhedron.py`
(untouchable) is a self-contained re-add of, with `face_normal` inlined
since this project has no fold engine to share it with.

**Why no numerical fold solver**: an even older version had no
coordinates and had to solve for fold angles (`scipy least_squares`, a
17-point restart sweep rejecting self-intersecting solutions). Once specs
carried real coordinates, fold angles became directly measurable — the
reason no `fold_solver.py`-shaped module exists anywhere in this project,
and the direct ancestor of the orientation check the stretchy pipeline
does differently (see `inflate-polyhedron-app` skill's starting-config
section), since a stretchy mesh has no coordinates-first shortcut.

**Leftover untouched, now-unused files**: `_CullableFace`
(`src/apps/ui/cullable_face.py`, exact backface culling for a closed
convex solid) and `bounding_box.py` (`src/apps/common/bounding_box.py`,
centering/sizing that view) — both were the deleted app's, kept only
because they're on the untouchable list. `paths.py` still defines
`NETS_DIR` pointing at the now-deleted `data/input/nets/` for the same
reason.

Both the deleted rigid pipeline and the current stretchy one share the
same CCW-from-outside winding convention (a shared edge is `v -> w` in
one face's loop, `w -> v` in the other's).

## Other deleted machinery

- `src/apps/common/sample_polyhedra.py` and three `generate_*_nets.py`
  scripts used to derive Platonic-solid vertex data into `.json` net
  specs. Deleted — `data/input/*.json` is now the canonical, hand-kept
  input, not a regenerated artifact. See git history if a genuinely new
  sample solid ever needs the old raw-coordinates-via-`hull_to_spec`
  approach again.
- `generate_subdivided_stretchy_nets.py` wrote fixed-resolution fabric
  `.json` variants via `mesh_subdivide.subdivide_mesh`/`solve_fabric_mesh`.
  Deleted along with `solve_wireframe` (see `inflate-polyhedron-app`
  skill's "Stretchy meshes" section) — nothing reads a fabric file's
  baked-in fine mesh any more, only its `coarse_faces`.
- `unit/polyhedron_unfolder/`, `unit/persistence/`, and `integration/`
  test directories (plus a shared `helpers.py` fixture builder) were
  removed along with the rigid pipeline.
- `test_stretchy_cache.py`/`test_mesh_subdivide.py`'s removed coverage —
  deleted along with `stretchy_cache.py`/`checksums.py` and
  `mesh_subdivide.py`'s `subdivide_mesh`/`solve_fabric_mesh`.
- The old top-level `net_fold_utils/`/`subdivision_utils/` packages were
  moved wholesale into `src/utils/` — no content changed, only import
  paths and (for apps) data-directory constants.
- There used to be a separate `skills.md` at the repo root holding just
  the docstring-style convention — merged into this file.
