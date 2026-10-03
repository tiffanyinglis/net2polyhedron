# Interactive Inflater (web)

A from-scratch, client-side port of the stretchy-mesh solver (`src/utils/inflate_polyhedron/` in
the main Python project) plus a Three.js viewer -- no server, no backend, everything runs in the
browser. Separate from the Tkinter `interactive_inflater_app`; see that app and
`.claude/skills/net-fold-project/physics.md` for the physics this is ported from.

## Running

Needs Node.js (any recent LTS) installed on your machine.

```bash
npm install
npm run dev
```

Then open the printed `localhost` URL. `npm run build` produces a static `dist/` you can open
directly or host anywhere (it's pure client-side, no API calls).

## Current scope (v1)

- Loads one of a handful of bundled nets (`public/nets/`), copied verbatim from
  `data/input/stretchy_nets/` -- `.poly` files load exactly like `.json`, since the net format is
  the same plain `{"faces": [...]}` JSON either way, only the extension differs:
  - **Platonic solids** (tetrahedron/cube/octahedron/dodecahedron/icosahedron) -- the reliable
    baseline case.
  - **Closed "pillow" shapes** (cone, tube, ravioli, samosa) -- 2-3 faces glued along every edge,
    a real test case from `physics.md` (ravioli's own pressure-cancelling pathology).
  - **Multi-piece closed nets** (spider_leg, turtle) -- more faces/vertices, still closed.
  - **goose.poly -- a genuinely open/boundary net.** v1 has no `pressure_exclude_faces`/
    `rms_exclude_edges` support yet (see below), so this one is expected to fail to converge --
    included deliberately, to see the current limitation fail loudly rather than silently.
- Runs the full pipeline client-side: fan-triangulate -> Level 0 spring+repulsion relax (with
  orientation-consistency seed retry) -> Level 1 pressure calibration to a target RMS stretch,
  exactly mirroring `interactive_inflater_app`'s own "Full Inflate" for a single net.
- Renders the inflated result in a simple orbit/zoom Three.js viewer, with a UI modelled on the
  Python app's release mode (Setup box, Convergence History table, Net + Level 0-3 panels, Colour menu; P/M/R keys).

**Not yet ported** (future steps): open/boundary nets (`pressure_exclude_faces`/
`rms_exclude_edges`), subdivision past Level 1 (Level 2/3), the 2D builder canvas, diff-inflate/
undo/redo, saved sessions. See `src/physics/` -- each module names which Python module it mirrors.
The real crochet-animal nets (giraffe/horse/hippo/hoodie/cannoli) aren't bundled yet -- hippo/
horse/giraffe are closed but `physics.md` notes the orientation-retry search fails on them even in
the more thorough Python solver, so they're likely to need that fix ported too before they're
worth trying here.
