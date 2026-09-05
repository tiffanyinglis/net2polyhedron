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
so it's usable immediately. See `src/utils/polyhedron_json_parser.py`
for the full format reference, and the existing files in
`data/input/nets/` for more examples.

## Running the tests

```bash
python tests/run_tests.py
```

or just `pytest` from the repo root. Extra arguments pass straight
through to pytest, e.g. `python tests/run_tests.py -k cube -v`.

## Project layout

```
src/
  utils/                          the reusable library, one flat module
                                  per concern (no sub-packages)
    polygon_geom.py                 flat 2D polygon geometry
    polyhedron.py                   Polyhedron: pure 3D solid geometry
    polyhedron_unfolder.py          the generic fold engine: Hinge,
                                    hinge_transform, face_normal,
                                    fold_transforms
    unfoldable_polyhedron.py       UnfoldablePolyhedron: derives a net's
                                    spanning tree, flat layout, and fold
                                    angles from a Polyhedron, and folds
                                    it at any unfold amount
    spanning_tree.py                generic BFS spanning tree
    polyhedron_json_parser.py       parse/write the on-disk .json format
                                    (no cache -- unfolding is cheap
                                    enough not to need one)
  apps/
    polyhedron_unfolder/            pick a net, see it fold (two tabs --
                                    animated slider, flat-vs-folded)
      app.py                         entry point, class PolyhedronUnfolderApp
    common/                        helpers shared across apps
      paths.py                       cross-app locations: input nets, output saves
      ui_theme.py                    shared Tk/matplotlib look-and-feel constants
      bounding_box.py                bounding_box(vertices): a rendering helper
    ui/                            generic Tk/matplotlib widgets, not domain logic
      tooltip.py                     Tooltip: hover-tooltip for any Tk widget
      cullable_face.py                _CullableFace: backface culling for a
                                    closed convex solid's 3D render

data/
  input/nets/*.json        human-authored net descriptions (edit these)
  output/                  user-generated saves

tests/
  unit/                   one test file per src/utils/ module (plus
                          unit/apps_common/ for the handful of
                          src/apps/common/ helpers with no
                          Tkinter/matplotlib dependency)
  integration/            tests that exercise multiple utils modules
                          together, plus shared fixture-builder helpers
  run_tests.py            run the test suite
```

For a deeper dive into how the fold pipeline works, the non-obvious
conventions in the code, and comment style, see
`.claude/skills/net-fold-project/SKILL.md`.
