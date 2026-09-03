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
python polygon_fold_app.py
```

Pick a net from the dropdown and drag the **Fold** slider from *Flat* to
*Folded* to watch it close up into the solid.

Five Platonic solids and a soccer-ball-style truncated icosahedron are
included out of the box in `nets/`.

## Describing your own net

A net is a JSON `.json` file in `nets/`. You only ever describe the
*combinatorics* — which faces exist and which ones touch — and everything
else (the flat layout, every fold angle) is worked out for you. For
example, a cube:

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

Drop a new `.json` file into `nets/` and it shows up in the app's dropdown
automatically. See `net_fold_utils/polyhedron_spec.py` for the full format
reference, and the existing files in `nets/` for more examples.

If you already know a solid's exact 3D vertex coordinates and just want a
`.json` file generated from them, see `net_fold_utils/hull_to_spec.py` and
`tools/generate_platonic_nets.py` for a worked example.

### Legacy format

If you need to hand-specify exact vertex positions and fold angles instead
(e.g. for a shape the automatic solver can't handle), a `.txt` net format
is also supported — see `net_fold_utils/net_io.py:load_net_txt` for its
format. Both `.json` and `.txt` files in `nets/` show up in the app.

## The fold cache

Working out how a net folds involves solving a system of equations, which
can take anywhere from under a second to about a minute for a large net
(the included truncated icosahedron takes tens of seconds). To avoid
re-solving on every launch, results are cached in `fold_cache/` alongside
a checksum of the source `.json` file — editing a net automatically
invalidates its stale cache.

A net with no cached fold yet shows up **greyed out** in the app's
dropdown. Either:

- click **Compute Folding Pattern** in the app (solves everything that
  isn't cached yet, with a progress indicator — this can take a few
  minutes if several nets need solving), or
- run it from the command line ahead of time:

```bash
python build_fold_cache.py            # only nets whose cache is stale
python build_fold_cache.py --force    # recompute every net regardless
```

## Running the tests

```bash
python run_tests.py
```

The suite runs in a few seconds (it deliberately only exercises small nets
for the numerical solver, so it stays fast). Pass extra arguments straight
through to pytest, e.g. `python run_tests.py -k fold_cache -v`.

## Project layout

```
polygon_fold_app.py     the app (entry point)
build_fold_cache.py     precompute the fold cache for every net, with progress output
run_tests.py            run the test suite
tooltip.py              small generic Tkinter hover-tooltip helper

net_fold_utils/         the reusable library -- net format parsing, the
                         combinatorics -> geometry pipeline, the fold
                         solver, and the fold cache

nets/*.json             human-authored net descriptions (edit these)
fold_cache/*.fold       computed fold results (generated, not hand-edited)
tools/                  one-off generator scripts
tests/                  pytest suite
```

For a deeper dive into how the solver works, the combinatorics behind it,
and the non-obvious conventions in the code, see
`.claude/skills/net-fold-project/SKILL.md`.
