# Apps

3 Tkinter entry points. `src/apps/common/` (paths, ui_theme, bounding_box) + `src/apps/ui/`
(tooltip, cullable_face) hold code shared across >1 app — not domain logic.

`common/paths.py` is the only place computing cross-app locations (`STRETCHY_NETS_DIR`); an app
one level under `src/apps/` bootstraps `sys.path` via `import common.paths` before importing
`utils.*`.

## inflate_polyhedron_app (`src/apps/inflate_polyhedron_app/app.py`)
The solver viewer. See `physics.md` for the actual algorithm; this is UI wiring.

- **Net picker** → Level 0 (random start, fan-triangulated). **Relax** → `relax_initial_configuration`
  to convergence → auto-promotes to Level 1 (no re-subdivide, same topology). **Inflate**
  recalibrates pressure FRESH every click (`on_inflate_clicked`: calibrate via `_run_background`,
  then stream via `_run_inflate_stream`) — pressure is never stored/reused across clicks.
  **Subdivide** up to `MAX_LEVEL=3`, carries forward current (stretched) shape.
- **Stop**: `self.stop_event` now created and the frontier button turned into "Stop" BEFORE
  calibration starts (was: only after, in `_on_pressure_calibrated`) — fixed a real bug where
  clicking Stop during calibration did nothing (no `stop_event` existed yet, and calibration's
  own `estimate_pressure_for_target_stretch` call wasn't given one either). `stop_event` now
  forwarded into that calibration call too.
- **Auto**: one Relax/Inflate attempt per level (`_auto_attempted_level`), no retry-loop (see
  physics.md). Button becomes "Stop Auto" while running.
- **Convergence History table**: one row/level. "Convergence" cell shows `optimality op gtol
  mark` — generic display, doesn't hardcode what `optimality` measures (currently displacement,
  see physics.md), so it stays correct if that changes again. No more "(stalled)" case possible
  (the mechanism producing it was removed) — `converged` now always agrees with the plain
  comparison, kept as the source of truth anyway rather than assumed.
- **3D panels**: PyVista off-screen render blitted into a Tk Label per level (`pv.Plotter(
  off_screen=True)` + `PIL.ImageTk`) — needed because meshes here are routinely non-convex/
  self-intersecting mid-relax, which plain mplot3d/backface-culling can't draw correctly. One
  shared camera angle across all "Level N" panels (drag any → all rotate together). "Net" panel
  (flat undeformed layout) is still matplotlib, own independent zoom.
  If the loaded net has `net_layout` (saved by `interactive_builder_app`), the Net panel shows
  that EXACT flat arrangement (with a Y-flip: Tk canvas Y-down vs matplotlib Y-up) instead of a
  fresh BFS spanning-tree layout.
- **Debug mode** ("d" key): adds steps-vs-convergence radio, **Validate Mesh** (combinatorial
  winding check only — geometric inside/out check is informational, not gating), **Show
  normals** (draws each face's outward normal, live equivalent of Validate Mesh's info note).
  Release mode and debug mode are otherwise IDENTICAL — don't add new differences w/o asking.
- **No caching, no chunking**: solve starts fresh each session; UI progress synced to
  `on_progress` callback fired by the solver itself every `CONVERGENCE_CHECK_INTERVAL` steps
  (see physics.md) — not an app-side chunk schedule.

## interactive_builder_app (`src/apps/interactive_builder_app/app.py`)
Unrelated 2D shape-placement canvas, no relation to solving. Palette of regular polygons
(triangle..8-gon) → click to drop instances → drag/select/delete/rotate(right-drag)/pan
(right-drag on empty). Click a handle then another shape's handle to connect them (click-click,
not drag — a drag design was tried and reverted per explicit request). Every corner shown as
`(shape_id, corner_index)`, not a shared vertex-id — that identity is only computed at Save
(union-find over connections), never live, since live merging surprised the user once (a
transitively-implied merge blocked an unrelated, individually-correct connection).

**File > Save** writes the stretchy vertex-loop JSON format + this app's own `net_layout`
(`{cx,cy,rotation}` per face) and `view` (`{scale}`) extension fields — any other reader (incl.
the solver) ignores the extra keys. Validation (self-loop / duplicate-directed-edge) runs ONLY
at Save, never live while editing — an edge can only be joined once (enforced live), but
transitive vertex identity is only finalized at export. **File > Load** replays `net_layout`
exactly if present; otherwise BFS-spanning-tree-lays-out fresh (same algorithm as
`stretchy_net_layout.build_stretchy_net_layout`, reimplemented locally with a gap parameter that
function doesn't have).

## polygon_subdivision_app (`src/apps/polygon_subdivision_app/app.py`)
Unrelated 2D-only demo: splits a regular n-gon into a fine triangular mesh, preview only, no
solving. Two-stage hardcoded/closed-form split (`utils/subdivisions/`): coarse centroid-fan
(`SUBDIVISIONS`) then barycentric refinement (`_subdivide_triangle`). Uses
`FABRIC_APP_RESOLUTION=3` (matches what the real stretchy pipeline solves over), not the
generic `DEFAULT_RESOLUTION=10`.
