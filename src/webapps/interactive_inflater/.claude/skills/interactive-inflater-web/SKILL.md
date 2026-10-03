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
- **UI**: net dropdown (from `public/nets/index.json`), one "Inflate" button, status panel
  (stage, steps, RMS stretch %, pressure). `main.ts` wires it; errors -> `alert` + console.
- **Pipeline** (`physics/pipeline.ts` `fullInflate`): loadNet -> fan-triangulate (Level 0->1) ->
  Level 0 spring+repulsion relax with orientation-retry seeds -> pressure calibration to target
  RMS (default 10%). Mirrors Python app's "Full Inflate" for a single net. Throws if L0 fails
  to converge or no pressure works.
- **Physics modules**: vec3, mesh (NetSpec/loadNet validation), meshLevels, edgeSetup, forces,
  explicitRelaxLoop (shared driver, yields to UI; no worker), relaxOnce, relaxInitial,
  orientationRetry, seedSelecter, insideOutChecker, convergence, kabsch (rigid-motion removal),
  pressureCalibration.
- **Viewer** (`viewer.ts`): Three.js, drag-orbit (camera-axis quaternion), wheel zoom, key/fill/
  headlight rig matching Python plotter_lighting, per-base-face random colors (`colors.ts`) +
  wireframe.
- **Nets** (`public/nets/`, copied from `data/input/stretchy_nets/`; `.poly` == `.json` format):
  5 Platonic, cone, tube, ravioli, samosa, spider_leg, turtle, goose.
  goose is open -> **expected to error** (deliberate).
- **Tests** (`physics/__tests__/`): `pipeline.test.ts` (loadNet, fullInflate on tetra/cube);
  `pythonParity.test.ts` — fixed-input values pinned against Python
  (`tests/unit/inflate_polyhedron/test_web_port_reference_values.py` in main repo; keep in sync).

## Not implemented
Open/boundary nets (`pressure_exclude_faces`/`rms_exclude_edges`), Level 2/3 subdivision, 2D
builder canvas, diff-inflate/undo/redo, saved sessions, worker thread, real animal nets
(giraffe/horse/hippo/hoodie/cannoli; orientation-retry fails on some even in Python).
