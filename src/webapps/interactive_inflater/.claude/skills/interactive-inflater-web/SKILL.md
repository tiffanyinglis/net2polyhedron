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
  (net combobox, Target RMS stretch L1 active / L2,L3 disabled, Tolerance = gtol, Run/Stop
  Simulation button); coloured status line; "Convergence History" table (Level, Pressure, Steps,
  RMS %, Sim/Cumulative time, Convergence = optimality vs gtol; row text green/red/yellow =
  converged/not/running); one row of 5 equal panels: Net (2D, `netPanel.ts`, canvas from
  `net_layout`, no bezier connections), Level 0-3 (one `Viewer` each, ONE `SharedCamera`: drag/
  zoom any panel moves all; each auto-fits own mesh). L0 redraws live; L1 shows "Computing..."
  until solved; L2/L3 empty. Choosing a net only loads it (no auto-run). Default colour =
  polygon-specific (`colors.ts`). No debug-mode/per-level buttons. `main.ts` wires it.
- **Pipeline** (`physics/pipeline.ts` `fullInflate`): loadNet -> fan-triangulate (Level 0->1) ->
  Level 0 spring+repulsion relax with orientation-retry seeds -> pressure calibration to target
  RMS (default 10%). Emits `onRecord` (LevelRecord for the history table), `onLevelPositions`, `onTopology`. Mirrors Python app's "Full Inflate" for a single net. Throws if L0 fails
  to converge or no pressure works.
- **Physics modules**: vec3, mesh (NetSpec/loadNet validation), meshLevels, edgeSetup, forces,
  explicitRelaxLoop (shared driver, yields to UI; no worker), relaxOnce, relaxInitial,
  orientationRetry, seedSelecter, insideOutChecker, convergence, kabsch (rigid-motion removal),
  pressureCalibration.
- **Viewer** (`viewer.ts`): Three.js, drag-orbit (camera-axis quaternion), wheel zoom, key/fill/
  headlight rig matching Python plotter_lighting, per-base-face colors (`setBaseColors`
  recolours in place) + wireframe.
- **Nets** (`public/nets/`, copied from `data/input/stretchy_nets/`; `.poly` == `.json` format):
  5 Platonic, cone, tube, ravioli, samosa, spider_leg, turtle, goose.
  goose is open -> **expected to error** (deliberate).
- **Tests** (`physics/__tests__/`): `pipeline.test.ts` (loadNet, fullInflate on tetra/cube);
  `pythonParity.test.ts` — fixed-input values pinned against Python
  (`tests/unit/inflate_polyhedron/test_web_port_reference_values.py` in main repo; keep in sync).

## Not implemented
Open/boundary nets (`pressure_exclude_faces`/`rms_exclude_edges`), Level 2/3 subdivision (panels/targets exist but are empty/disabled), 2D
builder canvas, Net-panel connection curves, diff-inflate/undo/redo, saved sessions, worker thread, debug-mode UI, real
animal nets (giraffe/horse/hippo/hoodie/cannoli; orientation-retry fails on some even in Python).
