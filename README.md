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

A net is a plain text `.poly` file in `nets/`. You only ever describe the
*combinatorics* — which faces exist and which ones touch — and everything
else (the flat layout, every fold angle) is worked out for you. For
example, a cube:

```
FACES        # one line per face: its number of sides
4
4
4
4
4
4

ROOT 0       # which face the flat net is built outward from

NET          # hinges in the flat net -- must connect every face (a
0 1          # spanning tree: exactly one fewer edge than there are faces)
0 2
0 3
0 4
1 5

EXTRA        # every other edge of the solid: faces that only touch once
1 2          # folded, not in the flat layout. These are what pin down
1 3          # the fold angles -- without them there'd be nothing forcing
3 4          # the net to close into one particular shape.
2 4
3 5
2 5
4 5
```

Drop a new `.poly` file into `nets/` and it shows up in the app's dropdown
automatically. See `net_fold_utils/polyhedron_spec.py` for the full format
reference, and the existing files in `nets/` for more examples.

If you already know a solid's exact 3D vertex coordinates and just want a
`.poly` file generated from them, see `net_fold_utils/hull_to_spec.py` and
`tools/generate_platonic_nets.py` for a worked example.

### Legacy format

If you need to hand-specify exact vertex positions and fold angles instead
(e.g. for a shape the automatic solver can't handle), a `.txt` net format
is also supported — see `net_fold_utils/net_io.py:load_net_txt` for its
format. Both `.poly` and `.txt` files in `nets/` show up in the app.

## The fold cache

Working out how a net folds involves solving a system of equations, which
can take anywhere from under a second to about a minute for a large net
(the included truncated icosahedron takes tens of seconds). To avoid
re-solving on every launch, results are cached in `fold_cache/` alongside
a checksum of the source `.poly` file — editing a net automatically
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

nets/*.poly             human-authored net descriptions (edit these)
fold_cache/*.fold       computed fold results (generated, not hand-edited)
tools/                  one-off generator scripts
tests/                  pytest suite
```

For a deeper dive into how the solver works, the combinatorics behind it,
and the non-obvious conventions in the code, see
`.claude/skills/net-fold-project/SKILL.md`.
