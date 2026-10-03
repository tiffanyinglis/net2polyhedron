---
name: interactive-inflater-web
description: Status, layout, and conventions of the client-side TypeScript/Three.js port of the stretchy-mesh inflater (src/webapps/interactive_inflater). Load before changing the web app.
---

# interactive_inflater (web) — what exists

> **MAINTENANCE: keep this file succinct. No bloat.** Terse, load-bearing facts only; update
> existing lines rather than appending; delete stale items. All web-app docs/skills live in this
> folder (`src/webapps/interactive_inflater/`) so the app can move to its own repo — never put
> web-app notes in the main project's `.claude/`. User-facing docs go in `README.md`.

Pure client-side (Vite + TS + three). Run: `npm install`, `npm run dev`; `npm test` (vitest);
`npm run build`. Port of Python `src/utils/inflate_polyhedron/` (physics reference: main repo's
`.claude/skills/net-fold-project/physics.md` — external to this folder; copy facts here when
the repo is split). Each `src/physics/*.ts` header names the Python module it mirrors.

## Implemented (v1)
- **UI** (same top-to-bottom layout as Python `inflate_polyhedron_app`; dark, `style.css` uses
  ui_theme colours): Colour menu (Polygon-specific[P]/Multi-colour[M]/Randomize[R]); "Setup" box
  (net combobox, Target RMS stretch L1-L3 each editable, Tolerance = gtol, Run/Stop
  Simulation button); coloured status line; "Convergence History" table (Level, Pressure, Steps,
  RMS %, Sim/Cumulative time (running level ticks live via `historyTimer` in `main.ts`),
  Convergence = optimality vs gtol; row text green/red/yellow = converged/not/running); one row of
  5 equal panels: Net (2D, `netPanel.ts`, canvas from `net_layout` + read-only white bezier
  `builder_connections`, handles from the saved file), Level 0-3 (one `Viewer` each, ONE `SharedCamera`: drag/
  zoom any panel moves all; each auto-fits own mesh). L0 redraws live; L1 shows "Computing..."
  until solved; L2/L3 likewise once solved. Choosing a net only loads it (no auto-run). Default colour =
  polygon-specific (`colors.ts`). `main.ts` wires it.
- **File menu** (`index.html`, wired in `main.ts`): Load Model... (`.poly`/`.json` from disk ->
  `installNet`, shown as a custom "Choose a net" option), Load Session... / Save Session... (`.hippo`).
  File > Include Replay Frames is a checkable option (default off). Save opens the system save
  picker (`showSaveFilePicker`, startIn downloads, suggested `<netName>.hippo`; fallback where
  unsupported: plain anchor download). Disabled while running / with no net. Format + (de)serialization
  lives in `src/session.ts` (pure, tested in `src/__tests__/session.test.ts`): own schema, tagged
  `format: "hippo-session"`, `version: 1` -- NOT the Python app's `.hippo` schema (not compatible).
  Saves net spec, colour mode/multi colours, Target RMS, tolerance, camera (orientation/zoom/pan),
  history, each level's topology+positions, and per-level replay frames as
  `replay: {vertexIds, frames: [{steps, xyz}]}` (always written; optional on load, so older
  frame-less files still open).
  Not saved: Net-panel zoom/pan.
- **Debug mode** ("d" key, same as Python; title gets " (debug mode)"): reveals a Setup-box row of
  three toggles -- face normals (yellow), vertex normals (cyan), repulsive-force arrows (magenta)
  -- drawn per panel by `Viewer.setOverlays` (`viewer.ts`). Turning debug off clears them. No
  per-level buttons, no steps-vs-convergence radio (Inflate only converges).
- **Levels 2-3** (`meshLevels.ts` `quarterTriangles`, mirrors `mesh_levels._quarter_triangles`,
  closed meshes only): midpoint split of the previous SOLVED mesh; rest lengths halve analytically.
  Each level's pressure guess = prior level closest to target, x2 per level (`guessPressureFromHistory`).
  Inflate-level repulsion acts on the base net's corners only, at strength 1/2^(level-1) per vertex
  (matches Python's `_repulsion_vertex_ids`/`_multipliers`); L0 relax keeps all-pairs (parity-pinned).
- **Pipeline** (`physics/pipeline.ts` `fullInflate`): loadNet -> fan-triangulate (Level 0->1) ->
  Level 0 spring+repulsion relax with orientation-retry seeds -> pressure calibration to target
  RMS (default 10%). Emits `onRecord` (LevelRecord for the history table), `onLevelPositions`, `onTopology`. Mirrors Python app's "Full Inflate" for a single net. Throws if L0 fails
  to converge or no pressure works.
- **Edge identity** (`physics/mesh.ts` `Mesh`): faces = vertex loops, `faceEdgeIds[f][i]` = id of
  edge `faces[f][i]->faces[f][i+1]`; `edgeEnds`/`restLengths` indexed by id. Physics keys springs and
  rest lengths by id, never vertex pair (mirrors Python `face_edge_ids`), so two distinct edges
  joining the same vertex pair (self-joined polygon: spider_leg, cannoli) stay separate. A `.poly`
  with `face_edge_ids` uses them as-is. Without them (`meshFromPairs`), edges are vertex pairs and a
  face with a repeated vertex is fan-split from a centroid (Python `self_join_triangulator`); a pair
  shared by two faces is then ambiguous and throws -- such nets need `face_edge_ids` (Save writes them).
- **Physics modules**: vec3, mesh (NetSpec/loadNet validation), meshLevels, edgeSetup, forces,
  explicitRelaxLoop (shared driver, yields to UI; no worker), relaxOnce, relaxInitial,
  orientationRetry, seedSelecter, insideOutChecker, convergence, kabsch (rigid-motion removal),
  pressureCalibration.
- **Viewer** (`viewer.ts`): Three.js, drag-orbit (camera-axis quaternion), wheel zoom, key/fill/
  headlight rig matching Python plotter_lighting, per-base-face colors (`setBaseColors`
  recolours in place) + wireframe.
- **Nets** (`data/inputs/`, copied from `data/input/stretchy_nets/`; `.poly` == `.json` format):
  5 Platonic, cone, tube, ravioli, samosa, spider_leg, turtle, goose, cannoli_open, cannoli_semiclosed.
  goose is open; runs like the other nets (open wedges excluded from pressure and RMS).
- **Tests** (`physics/__tests__/`): `pipeline.test.ts` (loadNet, fullInflate on tetra/cube);
  `pythonParity.test.ts` — fixed-input values pinned against Python
  (`tests/unit/inflate_polyhedron/test_web_port_reference_values.py` in main repo; keep in sync).

- **View menu** (Inflater | Viewer; mirrors `inflate_polyhedron_app`'s ViewerPane): `viewerPane.ts`
  browses `data/outputs/*.hippo` (listed via dev-only `/api/output-names`, read via `/outputs/<name>`,
  saved via POST `/api/outputs/<name>`). 2x2 grid of Viewers sharing one `SharedCamera` per file;
  `#viewer-view` vs `#inflater-view` toggled with `hidden`. Leaving with dirty files -> `#unsaved-dialog`.
- **Undo/redo** (`editState.ts`, `UndoStack`, mirrors Python's `_inflater_*`/`_viewer_*` undo): one
  stack per view; entries are `{camera, colors}` snapshots taken BEFORE a change. Camera gestures use
  `CameraHooks` (`viewer.ts`): a drag/pan pushes ONE step on release only if the camera moved; wheel
  ticks and middle-click reset push each step. Viewer stack resets on file change; Inflater's never
  resets (as in Python). Ctrl+Z/Ctrl+Y, Edit menu.

## Not implemented
2D builder canvas (so no net-edit undo), diff-inflate, Python-compatible session files, worker thread,
per-level debug buttons, real animal nets (giraffe/horse/hippo/hoodie; orientation-retry fails on some even in Python).
