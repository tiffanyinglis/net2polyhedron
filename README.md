# Net2Polyhedron

Design a polyhedron-like net out of flat polygon panels and watch it
inflate into a rounded 3D solid in an interactive viewer — handy for
designing crochet patterns for polyhedral (n-gon) shapes: lay out your
net of crocheted panels, then check how it actually closes up into a
puffy, stuffed-toy-like solid.

## Quick start

Install the dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
python src/apps/inflate_polyhedron_app/app.py
```

Pick a net from the dropdown. Every net starts as **Level 0**: a random,
meaningless starting position for its vertices. Click **Relax** to pull
that into a well-separated 3D shape using pure spring forces (no
pressure yet) — once it converges, it's promoted to **Level 1**. From
there:

- **Inflate** calibrates a pressure for the "Target RMS stretch" spinner
  and runs one relaxation pass at that pressure, rounding the shape out
  like blowing up a balloon or stuffing a plush toy. Click repeatedly to
  keep steering it.
- **Subdivide** refines the current mesh into finer triangles (up to a
  max level), carrying forward whatever shape you've already inflated.

Drag any 3D panel to rotate it (every panel shares one camera, so they
all turn together); scroll to zoom. The left "Net" panel always shows
the flat, unfolded layout for reference.

## Describing your own net

A net is a JSON `.json` file in `data/input/stretchy_nets/`: a list of
faces, each a loop of vertex ids, with **no coordinates at all** — just
combinatorics. Shared vertex ids *are* the adjacency, so a face pair
sharing more than one edge (which would force two rigid, flat faces into
the same plane — geometrically impossible) needs no special-casing; the
mesh is left free to stretch and bend there instead. For example, a cube:

```json
{
  "name": "Cube",
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

Every face must be wound **counterclockwise as seen from outside the
finished solid**: for any edge shared by two faces, one face's loop lists
it as `v -> w` and the other's lists it as `w -> v` — never the same
direction twice. `load_stretchy_mesh` (in
`src/utils/inflate_polyhedron/stretchy_mesh.py`) checks exactly that and
raises a clear error naming the offending edge(s) if it's violated.

Drop a new `.json` file into `data/input/stretchy_nets/` and it shows up
in the app's dropdown automatically — there's no cache and no precompute
step, so it's usable immediately. See the existing files in that
directory for more examples, including nets (like
`two_pentagons_and_a_square.json`) that genuinely can't stay flat and
rigid. See [algorithm.md](algorithm.md) for how the solver itself works.

If you already know a solid's exact 3D vertex coordinates and want to
recover its face structure from them,
`src/utils/inflate_polyhedron/hull_to_spec.py`'s `polyhedron_from_vertices`
derives each face's vertex loop straight from the raw coordinates via a
convex hull.

## Other apps

- **`src/apps/polygon_subdivision_app/app.py`** — an unrelated 2D-only
  demo of splitting a regular polygon (triangle through octagon) into a
  fine triangular mesh, as a preview of the kind of mesh the stretchy
  pipeline solves over once subdivided.

## Running the tests

```bash
python tests/run_tests.py
```

or just `pytest` from the repo root. The whole suite runs in a couple of
seconds. Pass extra arguments straight through to pytest, e.g.
`python tests/run_tests.py -k stretchy -v`.

## Project layout

```
src/
  utils/                     the reusable library
    geometry/                  general-purpose 2D/3D geometry: regular
                              polygons + rigid edge attachment
                              (polygon_geom.py), and Polyhedron -- pure
                              3D solid geometry (polyhedron.py)
    subdivisions/              fine-triangle-mesh subdivision (2D preview)
    inflate_polyhedron/        the stretchy (non-rigid) mesh pipeline:
                              stretchy_mesh.py (solver), hull_to_spec.py,
                              stretchy_net_layout.py (flat 2D layout),
                              mesh_levels.py (incremental subdivision)
  apps/
    inflate_polyhedron_app/    the stretchy pipeline: interactive
                              relax/inflate/subdivide viewer
      app.py                    entry point, class InflatePolyhedronApp
    polygon_subdivision_app/  unrelated 2D-only subdivision demo
      app.py                    entry point, class PolygonSubdivisionApp
    common/                    helpers SHARED by more than one app
      paths.py                   cross-app filesystem locations
      ui_theme.py                shared Tk/matplotlib look-and-feel constants
      bounding_box.py            bounding_box(vertices): a rendering helper
    ui/                        generic Tk/matplotlib widgets, not domain logic
      tooltip.py                 Tooltip: hover-tooltip for any Tk widget
      cullable_face.py           _CullableFace: backface culling for a
                                closed convex solid's 3D render

data/
  input/
    stretchy_nets/*.json       human-authored stretchy (vertex-loop) nets

tests/
  unit/                       one test file per utils module, mirroring
                              src/utils/'s own sub-package layout (plus
                              unit/apps_common/ for the one src/apps/common/
                              helper with no Tkinter/matplotlib dependency)
  run_tests.py                run the test suite
```

For a deeper dive into how the solver works, the non-obvious conventions
in the code, and the full architecture, see
`.claude/skills/net-fold-project/SKILL.md` (project internals) and
[algorithm.md](algorithm.md) (the inflation algorithm itself).
