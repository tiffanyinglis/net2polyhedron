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

Then open the printed `localhost` URL. **Run > Run All** inflates every `.poly` in `data/inputs/` and
saves each result as `data/outputs/<name>.hippo`. Because a browser can't write into
the project folder, this needs the dev server; the static `dist/` build can't use it. `npm run build` produces a static `dist/` you can open
directly or host anywhere (it's pure client-side, no API calls).

## Current scope (v1)

- Loads one of a handful of bundled nets (`data/inputs/`), copied verbatim from
  `data/input/stretchy_nets/` -- `.poly` files load exactly like `.json`, since the net format is
  the same plain `{"faces": [...]}` JSON either way, only the extension differs:
  - **Platonic solids** (tetrahedron/cube/octahedron/dodecahedron/icosahedron) -- the reliable
    baseline case.
  - **Closed "pillow" shapes** (cone, tube, ravioli, samosa) -- 2-3 faces glued along every edge,
    a real test case from `physics.md` (ravioli's own pressure-cancelling pathology).
  - **Multi-piece closed nets** (spider_leg, turtle) -- more faces/vertices, still closed.
  - **Self-joined nets** (spider_leg, cannoli_open, cannoli_semiclosed) -- a polygon whose own
    edges are glued to each other (a pinched leg, a folded cannoli). Two distinct edges can join the
    same two vertices, so edges are identified by the id in the file's `face_edge_ids`, not by
    vertex pair. Runs through the whole pipeline.
  - **goose.poly -- a genuinely open/boundary net.** Open wedges get no pressure and their edges
    are left out of the RMS stat, as in the Python app, so it runs like any other net.
- Runs the full pipeline client-side: fan-triangulate -> Level 0 spring+repulsion relax (with
  orientation-consistency seed retry) -> Level 1 pressure calibration to a target RMS stretch,
  exactly mirroring `interactive_inflater_app`'s own "Full Inflate" for a single net.
- **File menu**: Load Model... opens a `.poly` (or `.json`) net from your computer; Save Session... /
  Load Session... write and read a `.hippo` file holding the whole session (net, parameters, colours,
  camera, and every computed level), so a run can be reopened without re-solving. A `.hippo` written
  here is this web app's own format and isn't interchangeable with the Python app's `.hippo` files.
- Renders the inflated result in a simple orbit/zoom Three.js viewer, with a UI modelled on the
  Python app's release mode (Setup box, Convergence History table, Net + Level 0-3 panels, Colour menu; P/M/R keys).
- **View menu** (same as `inflate_polyhedron_app`'s View > Inflater/Viewer):
  - **Inflater** -- the view described above.
  - **Viewer** -- browses every `.hippo` in `data/outputs/` (dev server only, like Run All), four
    levels at once in a 2x2 grid sharing one camera per file. Left/Right or A/D step through files.
    Camera and Colour changes are per file; leaving the Viewer (or closing the page) with unsaved
    changes prompts to save. Ctrl+S saves the file on screen.
- **Edit menu / Ctrl+Z / Ctrl+Y**: undo and redo for camera moves and Colour changes, one stack per
  view. The Viewer's stack covers the file on screen and resets when you move to another file.

**Not yet ported** (future steps): the 2D builder canvas (net editing, so Inflater's own undo doesn't
yet cover net edits), diff-inflate, Python-compatible session files. See `utils/physics/` -- each module
names which Python module it mirrors.
The real crochet-animal nets (giraffe/horse/hippo/hoodie/cannoli) aren't bundled yet -- hippo/
horse/giraffe are closed but `physics.md` notes the orientation-retry search fails on them even in
the more thorough Python solver, so they're likely to need that fix ported too before they're
worth trying here.
