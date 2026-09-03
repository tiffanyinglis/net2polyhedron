---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (net_fold_utils library, .json/.fold formats, the fold solver, the Tkinter app, tests). Load before making non-trivial changes to this repo instead of re-deriving the pipeline by re-reading every file.
---

# Polyhedron net-folding project

Takes a description of a polyhedron's net (which faces exist, how they're
hinged flat, and which edges only meet once folded) and computes the exact
3D fold: a 2D face layout plus a per-hinge fold angle. `polygon_fold_app.py`
is a Tkinter app that lets you pick a net and drag a slider from flat (0%)
to fully folded (100%).

## Directory layout

- `polygon_fold_app.py` — the Tkinter GUI app (entry point, class `PolygonFoldApp`)
- `tooltip.py` — small generic hover-tooltip helper for Tkinter (not net-fold-specific)
- `net_fold_utils/` — the reusable library (see below)
- `nets/*.json` — **human-authored** net specs; the only files meant to be hand-edited
- `fold_cache/*.fold` — **computed** cache, one per `.json`, kept in a separate directory from `nets/` on purpose (disposable output vs. source input)
- `build_fold_cache.py` — top-level script: precompute/refresh all caches, prints per-net progress
- `tools/generate_platonic_nets.py` — (re)generates `nets/*.json` for the 5 Platonic solids + the truncated icosahedron from canonical 3D coordinates (`net_fold_utils/solid_coords.py`)
- `tests/` — pytest suite (see Testing below)
- `run_tests.py` — top-level script: `python run_tests.py [pytest args...]`
- `pytest.ini` — sets `pythonpath = .` so tests can `import net_fold_utils` regardless of cwd
- `requirements.txt` — numpy, scipy, networkx, matplotlib, sv-ttk, (dev) pytest
- `README.md` — user-facing usage doc (install, run the app, write a `.json` net, the cache, tests)

## The `.json` format (human-writable input)

Full grammar lives in `net_fold_utils/polyhedron_spec.py`'s docstring. Shape:

```json
{
  "name": "...",
  "faces": [{"id": 0, "sides": 4, "isRoot": true}, {"id": 1, "sides": 4}, ...],
  "edges": {
    "net": [[0, 1], ...],
    "extra": [[1, 2], ...]
  }
}
```

`faces` gives each face's number of sides (k for a regular k-gon), with an
explicit `id` per face -- checked against declaration order on load -- so
faces stay easy to number and cross-reference even in a long list. The
face the flat net is built outward from is marked `isRoot: true` (defaults
to face 0 if no face is marked; more than one marked face is an error).
`edges.net` is the (f1, f2) hinge edges forming the flat net; must be a
spanning tree (n-1 edges). `edges.extra` is the (f1, f2) edges that only
meet once folded; these pin down the fold angles.

No coordinates or angles are ever hand-written — both are derived.

## Pipeline (`net_fold_utils/net_io.py: load_polyhedron_net`)

1. `polyhedron_spec.py` parses `faces`/`edges.net`/`edges.extra` from the JSON.
2. `combinatorics.py` (`EdgeMap`) turns the full edge list into a per-face
   edge-index map via a `networkx` planar embedding. By Whitney's theorem a
   3-connected planar graph's embedding — hence the cyclic edge order
   around each face — is unique up to a global mirror, so edge indices
   never need to be given explicitly.
3. `net_layout.py` BFS-attaches regular polygons (`polygon_geom.py`) along
   `net` edges to build the flat 2D net.
4. `fold_solver.py` numerically solves (scipy `least_squares`) for the
   hinge angle at every `net` edge such that every `extra` edge's two faces
   coincide in 3D at fold progress `t=1`. Performance-critical internals:
   - **Restart strategy**: tries a 17-point sweep of evenly-spaced,
     all-hinges-equal starting guesses first; the 40-random-restart
     fallback only fires if that sweep finds *no* valid solution at all —
     it's not used to search for additional branches once one is found.
   - **Known gotcha**: the same closure equations can have more than one
     root. The icosahedron net, for instance, also algebraically closes
     into a smaller, self-intersecting "collapsed" shape.
     `fold_solver._is_embeddable` rejects any solution where two
     non-adjacent vertices end up closer than one edge length (checked via
     `net_fold_core.distinct_vertices`), then the smallest-total-rotation
     surviving solution is chosen.
   - **`jac_sparsity`**: each closure residual only actually depends on the
     hinge angles that are ancestors (root-path) of the two faces
     involved — a sibling branch's angle provably can't affect it, so this
     is an *exact* sparsity pattern, not an approximation
     (`_ancestor_hinge_indices` / `_closure_jac_sparsity`). Only applied
     when `n_hinges >= SPARSITY_MIN_HINGES` (15): below that, scipy's
     forced switch to the sparse-only iterative `lsmr` trust-region solver
     costs more than it saves (measured ~2x *slower* on the 7-hinge
     octahedron); above it, it's a real win (~1.7x on a 31-hinge net).
5. `net_fold_core.fold()` is the actual rotation engine — walks the hinge
   tree, rotating each subtree rigidly by its solved angle in one batched
   array operation (`precompute_subtree_map` derives the tree's shape once
   per solve rather than once per `fold()` call, since it never changes
   across the whole optimization). Works identically for both
   `.json`-derived and legacy `.txt` nets.

Perf history (32-face truncated icosahedron, 31 hinges): ~78s naive →
~72s (subtree precompute) → ~42s (+ `jac_sparsity`). Small nets (≤~15
hinges) were already sub-second and are unaffected by the `jac_sparsity`
change (explicitly gated off for them).

## Caching (`net_fold_utils/fold_cache.py`)

Solving is the slow part for bushy/large nets. A `.fold` cache file (in
`fold_cache/`, not `nets/`) mirrors the legacy explicit-coordinate format
(2D vertex positions per face + fold angle per hinge) plus a
`CHECKSUM sha256:...` of the source `.json`. `load_net()` transparently
reuses the cache if the checksum still matches, else re-solves and
rewrites it.

- `is_cached(net_path)` — read-only check, never mutates anything (safe to
  call just to decide how to render a net, e.g. in the app's net list).
- `_valid_cache_or_clear_stale` — when a cache's checksum no longer matches
  its source (the `.json` was edited), the stale `.fold` file is **deleted
  immediately**, before any re-solve is attempted. This means a failed
  re-solve never leaves a misleading stale cache behind; the net correctly
  falls back to "not computed" instead.
- `build_all(nets_dir, force=False, on_progress=None)` — computes/refreshes
  every net's cache; shared by `build_fold_cache.py` (CLI, prints progress)
  and the app's "Compute Folding Pattern" button (runs in a background
  thread, reports via a `queue.Queue` polled from the main thread — Tk
  widgets must only ever be touched from the main thread).
- Run `python build_fold_cache.py` after editing a `.json` file to warm the
  cache ahead of time (`--force` recomputes unconditionally); otherwise it
  happens lazily on first load.

## The app (`polygon_fold_app.py`)

Tkinter UI on the `sv_ttk` theme (dark by default, light/dark toggle
button) with a `LabelFrame`-grouped layout: net picker + Compute button +
"Show Axes" checkbox (off by default) + theme button on top, the 3D plot
in the middle, the fold slider on the bottom.

- Nets without a valid `.fold` cache show a `(not computed)` suffix and are
  greyed out in the dropdown (`_style_disabled_items` — a best-effort
  reach into ttk's Tcl popdown-listbox internals, wrapped in try/except
  since it's not public API; the text suffix + a selection guard in
  `on_select_net` are what actually make them unselectable, independent of
  whether the grey styling succeeds).
- `_apply_plot_theme` recolors the figure/axes to match sv_ttk's theme
  (`PLOT_THEME`, mirroring sv_ttk's own `-bg` colors) and honors the "Show
  Axes" toggle; `draw()` calls it fresh every redraw since `ax.cla()`
  wipes all of it back to matplotlib's defaults each time.
- `draw()` centers the view on the shape's own bounding-box center (not
  its raw min/max) with one shared half-width across all three axes, so
  the shape sits in the middle of the cubic plot regardless of which
  direction the net layout happens to extend, and `set_box_aspect([1, 1,
  1])` isn't distorted by unequal per-axis ranges.
- `_draw_box_wireframe` manually draws all 12 edges of the bounding box
  when axes are shown: matplotlib's default 3D pane borders only draw the
  9 edges belonging to the 3 panes it renders for a fixed view angle, so
  the near vertical corner where the two visible walls meet is otherwise
  left undrawn.
- "Compute Folding Pattern" runs `build_all` in a background thread with an
  indeterminate `ttk.Progressbar` and status-line updates; on completion,
  any failures are reported via `messagebox.showerror` listing each failed
  net and its error message (not just the status line).
- `_set_status(text, kind)` centralizes status-line coloring (`info` /
  `success` / `error` / `warn` → `STATUS_COLORS`).

## Testing

`pytest` (from repo root, or anywhere — `pytest.ini` sets `pythonpath`).
Suite runs in ~3s; it deliberately only exercises small nets (tetrahedron,
cube, a synthetic paper-cube net) for the numerical solver so it stays
fast — there's no test that runs the icosahedron/truncated-icosahedron
solve. Files map roughly 1:1 to `net_fold_utils` modules
(`test_polygon_geom.py`, `test_combinatorics.py`, `test_net_layout.py`,
`test_net_fold_core.py`, `test_fold_solver.py`, `test_polyhedron_spec.py`,
`test_fold_cache.py`, `test_hull_to_spec.py`, `test_spanning_tree.py`).
`test_fold_cache.py` uses `tmp_path` + `monkeypatch` to verify cache
reuse (patches `load_polyhedron_net` to raise, proving a cache hit never
calls it) and stale-cache deletion on a failed re-solve.

## Conventions worth knowing before editing

- All polygon edges have length 1 (`polygon_geom.EDGE_LENGTH`) — faces are
  glued edge-to-edge exactly, no scaling anywhere in the pipeline.
- Polygons are CCW; a child face is attached to its parent via a
  *reversed* edge mapping (child edge `j` maps onto the parent edge
  traversed backwards), matching how a physical paper net unfolds to the
  outside.
- A stored "fold angle" is the rotation *from flat* (180° between coplanar
  faces), not the dihedral angle itself — e.g. cube hinges rotate 90°
  (dihedral is also 90°, self-supplementary), tetrahedron hinges rotate
  109.47° (dihedral is 70.53°).
- Legacy `.txt` nets (explicit coordinates + fold angles, no solving
  needed) are still supported via `net_io.load_net_txt`, dispatched
  automatically by file extension in `net_io.load_net` (`.json` vs `.txt`).
- `net_fold_core.py`, `fold_solver.py`, and `fold_cache.py` have no
  `if __name__ == "__main__"` demo blocks anymore — that logic now lives in
  `tests/`. Add new ad hoc verification as a real test, not a script block.
