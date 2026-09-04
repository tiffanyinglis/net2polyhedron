# Net2Polyhedron

Design a polyhedron by describing which faces it has and how they're
hinged together — no coordinates, no angles, no math — and watch it fold
up from flat into the 3D solid in an interactive viewer. Handy for
designing crochet patterns for polyhedral (n-gon) shapes: lay out your net
of crocheted panels, then check how it actually closes up into a solid.

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
included out of the box in `data/input/nets/`.

## Describing your own net

A net is a JSON `.json` file in `data/input/nets/`. You only ever describe
the *combinatorics* — which faces exist and which ones touch — and
everything else (the flat layout, every fold angle) is worked out for you.
For example, a cube:

```json
{
  "name": "Cube",
  "faces": [
    {"id": 0, "sides": 4, "isRoot": true},
    {"id": 1, "sides": 4},
    {"id": 2, "sides": 4},
    {"id": 3, "sides": 4},
    {"id": 4, "sides": 4},
    {"id": 5, "sides": 4}
  ],
  "edges": {
    "net": [
      [0, 1],
      [0, 2],
      [0, 3],
      [0, 4],
      [1, 5]
    ],
    "extra": [
      [1, 2],
      [1, 3],
      [3, 4],
      [2, 4],
      [3, 5],
      [2, 5],
      [4, 5]
    ]
  }
}
```

`faces` gives each face's number of sides, with an explicit `id` per face
so they're easy to number and cross-reference even in a long list. The
face the flat net is built outward from is marked `"isRoot": true` (face 0
if none is marked). `edges.net` lists the hinges in the flat net — it must
connect every face (a spanning tree: exactly one fewer edge than there are
faces). `edges.extra` lists every other edge of the solid: faces that only
touch once folded, not in the flat layout. These are what pin down the
fold angles — without them there'd be nothing forcing the net to close
into one particular shape.

Drop a new `.json` file into `data/input/nets/` and it shows up in the
app's dropdown automatically. See `src/utils/persistence/polyhedron_spec.py`
for the full format reference, and the existing files in
`data/input/nets/` for more examples.

If you already know a solid's exact 3D vertex coordinates and just want a
`.json` file generated from them, see `src/utils/geometry3d/hull_to_spec.py`
and `src/apps/common/generate_platonic_nets.py` for a worked example.

### Legacy format

If you need to hand-specify exact vertex positions and fold angles instead
(e.g. for a shape the automatic solver can't handle), a `.txt` net format
is also supported — see `src/utils/model/polyhedral_net.py:PolyhedralNet.load`
for its format. Both `.json` and `.txt` files in `data/input/nets/` show up
in the app.

## The fold cache

Working out how a net folds involves solving a system of equations, which
can take anywhere from under a second to about a minute for a large net
(the included truncated icosahedron takes tens of seconds). To avoid
re-solving on every launch, results are cached in
`src/apps/polyhedron_unfolder/cache/` alongside a checksum of the source
`.json` file — editing a net automatically invalidates its stale cache.
This cache is polyhedron_unfolder's own — no other app reads or writes it.

A net with no cached fold yet shows up **greyed out** in the app's
dropdown. Either:

- click **Compute Folding Pattern** in the app (solves everything that
  isn't cached yet, with a progress indicator — this can take a few
  minutes if several nets need solving), or
- run it from the command line ahead of time:

```bash
python src/apps/polyhedron_unfolder/build_cache.py            # only nets whose cache is stale
python src/apps/polyhedron_unfolder/build_cache.py --force    # recompute every net regardless
```

## Other apps

- **`src/apps/inflate_polyhedron_app/app.py`** — a separate, non-rigid
  pipeline for nets that can't stay flat and rigid (e.g. a face sharing
  more than one edge with a neighbor): interactively inflate a stretchy
  mesh from `data/input/stretchy_nets/`. Has its own cache
  (`src/apps/inflate_polyhedron_app/cache/`) and its own
  `build_cache.py`.
- **`src/apps/polygon_subdivision_app/app.py`** — an unrelated 2D-only
  demo of splitting a regular polygon into a fine triangular mesh, as a
  preview of the mesh a later fabric/cloth simulation would use. No cache.

## Running the tests

```bash
python tests/run_tests.py
```

The suite runs in a few seconds (it deliberately only exercises small nets
for the numerical solver, so it stays fast). Pass extra arguments straight
through to pytest, e.g. `python tests/run_tests.py -k fold_cache -v`.

## Project layout

```
src/
  utils/                        the reusable library
    geometry2d/                  flat 2D polygon geometry and net layout
    geometry3d/                  3D fold solving, stretchy-mesh solving, coordinates
    subdivisions/                fine-triangle-mesh subdivision (2D preview + 3D fabric)
    combinatorics/               face-adjacency graph algorithms
    persistence/                 parse/load/write/cache the on-disk .json/.fold
                                  formats -- build_all() takes an explicit
                                  cache_dir, since caches live per-app
                                  (below), never in one shared location
    model/                       Face/Hinge/Vertex/PolyhedralNet/Polyhedron
                                  object model for the rigid pipeline --
                                  PolyhedralNet.load() is the public loading
                                  entry point
  apps/
    polyhedron_unfolder/          rigid pipeline: pick a net, see it fold
                                  (two tabs -- animated slider, flat-vs-folded)
      app.py                       entry point, class PolyhedronUnfolderApp
      build_cache.py                precompute this app's OWN fold cache
      cache/*.fold                  ...that cache lives here, not in data/
    inflate_polyhedron_app/       stretchy pipeline: interactive fabric inflation
      app.py                       entry point, class InflatePolyhedronApp
      build_cache.py                precompute this app's OWN solve cache
      cache/*.json                  ...that cache lives here, not in data/
    polygon_subdivision_app/      unrelated 2D-only subdivision demo, no cache
      app.py                       entry point, class PolygonSubdivisionApp
    common/                       helpers SHARED by more than one app
      paths.py                     cross-app locations: input nets, output saves
                                    (NOT caches -- those are per-app, above)
      ui_theme.py                  shared Tk/matplotlib look-and-feel constants
      generate_*.py                 one-off scripts that (re)generate the
                                    data/input/ specs the apps read
    ui/                          generic Tk/matplotlib widgets, not domain logic
      tooltip.py                    Tooltip: hover-tooltip for any Tk widget
      cullable_face.py               _CullableFace: backface culling for a
                                    closed convex solid's 3D render

data/
  input/                 human-authored net descriptions (edit these)
    nets/*.json            rigid nets
    stretchy_nets/*.json    stretchy (vertex-loop) nets
  output/                 user-generated saves from inflate_polyhedron_app

tests/
  unit/                   one test file per utils module, mirroring src/utils/'s
                          own sub-package layout
  integration/            tests that exercise multiple utils sub-packages
                          together, plus shared fixture-builder helpers
  run_tests.py            run the test suite
```

Each app's cache is deliberately its own, not shared even between
`polyhedron_unfolder` and any future rigid-pipeline app: an app never
depends on another app's cache directory.

For a deeper dive into how the solver works, the combinatorics behind it,
and the non-obvious conventions in the code, see
`.claude/skills/net-fold-project/SKILL.md`.
