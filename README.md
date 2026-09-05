# Net2Polyhedron

Design a polyhedron by describing its real 3D vertex positions and which
faces it has, and watch it fold up from flat into the 3D solid in an
interactive viewer. Handy for designing crochet patterns for polyhedral
(n-gon) shapes: lay out your net of crocheted panels, then check how it
actually closes up into a solid.

## Quick start

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
python src/apps/polyhedron_unfolder/app.py
```

Pick a net from the dropdown, then switch between its two tabs:
**Animated Fold** (drag the slider from *Flat* to *Folded* to watch it
close up into the solid) and **Flat vs Folded** (the flat net and the
fully folded solid shown side by side at once — drag the folded solid
with the mouse to rotate it).

Five Platonic solids and a soccer-ball-style truncated icosahedron are
included out of the box in `data/input/nets/`, plus two **open** nets
(`half_dodecahedron.json`, `dodecahedron_minus_one.json`) that don't fold
up into a closed solid — useful for seeing how the app handles a net
with faces missing.

## Describing your own net

A net is a JSON `.json` file in `data/input/nets/`: real 3D vertex
positions plus each face's vertex-index loop (CCW as seen from outside
the solid). Everything else — the flat layout, every fold angle — is
worked out for you from that geometry. For example, a cube:

```json
{
  "name": "Cube",
  "vertices": [
    [-1.0, -1.0, -1.0],
    [-1.0, -1.0, 1.0],
    [-1.0, 1.0, -1.0],
    [-1.0, 1.0, 1.0],
    [1.0, -1.0, -1.0],
    [1.0, -1.0, 1.0],
    [1.0, 1.0, -1.0],
    [1.0, 1.0, 1.0]
  ],
  "faces": [
    [4, 0, 2, 6],
    [1, 0, 4, 5],
    [5, 4, 6, 7],
    [2, 0, 1, 3],
    [6, 2, 3, 7],
    [3, 1, 5, 7]
  ]
}
```

`vertices` is a list of `[x, y, z]` positions; `faces` is a list of
vertex-index loops, one per face, each ordered counterclockwise as seen
from outside the finished solid. There's no root to pick and no spanning
tree to specify — the app derives all of that itself from whichever
faces you give it, picking any face as the starting point (the choice
doesn't matter). An "open" net (one that won't close into a full solid)
is just a spec whose `faces` are a subset of some solid's — see
`half_dodecahedron.json`/`dodecahedron_minus_one.json` for worked
examples, and only include vertices your listed faces actually
reference.

Drop a new `.json` file into `data/input/nets/` and it shows up in the
app's dropdown automatically — there's no cache and no precompute step,
so it's usable immediately. See `src/utils/persistence/polyhedron_spec.py`
for the full format reference, and the existing files in
`data/input/nets/` for more examples.

If you already know a solid's exact 3D vertex coordinates and just want a
`.json` file generated from them, `src/utils/geometry3d/hull_to_spec.py`'s
`polyhedron_from_vertices` derives each face's vertex-index loop straight
from the raw coordinates via a convex hull — see its docstring.

## Other apps

- **`src/apps/inflate_polyhedron_app/app.py`** — a separate, non-rigid
  pipeline for nets that can't stay flat and rigid (e.g. a face sharing
  more than one edge with a neighbor): interactively inflate a stretchy
  mesh from `data/input/stretchy_nets/`. Unlike the rigid pipeline above,
  this one genuinely solves a numerical optimization, so it keeps its own
  cache (`src/apps/inflate_polyhedron_app/cache/`) and its own
  `build_cache.py` to precompute it:

  ```bash
  python src/apps/inflate_polyhedron_app/build_cache.py            # only nets whose cache is stale
  python src/apps/inflate_polyhedron_app/build_cache.py --force    # recompute every net regardless
  ```

- **`src/apps/polygon_subdivision_app/app.py`** — an unrelated 2D-only
  demo of splitting a regular polygon into a fine triangular mesh, as a
  preview of the mesh a later fabric/cloth simulation would use. No cache.

## Running the tests

```bash
python tests/run_tests.py
```

or just `pytest` from the repo root. The rigid-pipeline suite is fast
(no numerical solving involved at all); the stretchy-pipeline suite is
slower (~30-60s) since it runs the real inflation solver. Pass extra
arguments straight through to pytest, e.g. `python tests/run_tests.py -k stretchy -v`.

## Project layout

```
src/
  utils/                          the reusable library
    geometry2d/                    flat 2D polygon geometry and net layout
    geometry3d/                    stretchy-mesh solving and hull-to-spec
                                    coordinate derivation
    subdivisions/                  fine-triangle-mesh subdivision (2D
                                    preview + 3D fabric)
    polyhedron_unfolder/           Polyhedron (pure 3D solid geometry) plus
                                    UnfoldablePolyhedron: derives a net's
                                    spanning tree, flat layout, and fold
                                    angles from an already-built Polyhedron
    persistence/                   parse/write the on-disk .json formats,
                                    plus the stretchy pipeline's own
                                    checksummed cache (the rigid pipeline
                                    has no cache -- unfolding is cheap
                                    enough not to need one)
  apps/
    polyhedron_unfolder/            rigid pipeline: pick a net, see it fold
                                    (two tabs -- animated slider, flat-vs-folded)
      app.py                         entry point, class PolyhedronUnfolderApp
    inflate_polyhedron_app/        stretchy pipeline: interactive fabric inflation
      app.py                         entry point, class InflatePolyhedronApp
      build_cache.py                 precompute this app's OWN solve cache
      cache/*.json                   ...that cache lives here, not in data/
    polygon_subdivision_app/       unrelated 2D-only subdivision demo, no cache
      app.py                         entry point, class PolygonSubdivisionApp
    common/                        helpers SHARED by more than one app
      paths.py                       cross-app locations: input nets, output saves
                                    (NOT caches -- those are per-app, above)
      ui_theme.py                    shared Tk/matplotlib look-and-feel constants
      bounding_box.py                bounding_box(vertices): a rendering helper
      generate_subdivided_stretchy_nets.py
                                    one-off script that writes fine-triangulated
                                    variants of an existing stretchy net
    ui/                            generic Tk/matplotlib widgets, not domain logic
      tooltip.py                     Tooltip: hover-tooltip for any Tk widget
      cullable_face.py                _CullableFace: backface culling for a
                                    closed convex solid's 3D render

data/
  input/                 human-authored net descriptions (edit these)
    nets/*.json            rigid nets
    stretchy_nets/*.json    stretchy (vertex-loop) nets
  output/                 user-generated saves from inflate_polyhedron_app

tests/
  unit/                   one test file per utils module, mirroring src/utils/'s
                          own sub-package layout (plus unit/apps_common/ for
                          the handful of src/apps/common/ helpers with no
                          Tkinter/matplotlib dependency)
  integration/            tests that exercise multiple utils sub-packages
                          together, plus shared fixture-builder helpers
  run_tests.py            run the test suite
```

Each app's cache is deliberately its own, not shared even between
`inflate_polyhedron_app` and any future stretchy-pipeline app: an app
never depends on another app's cache directory.

For a deeper dive into how the fold pipeline works, the non-obvious
conventions in the code, and the full architecture of both pipelines, see
`.claude/skills/net-fold-project/SKILL.md`.
