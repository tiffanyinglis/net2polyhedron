---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (net_fold_utils library, .poly/.fold formats, the fold solver, the Tkinter app). Load before making non-trivial changes to this repo instead of re-deriving the pipeline by re-reading every file.
---

# Polyhedron net-folding project

Takes a description of a polyhedron's net (which faces exist, how they're
hinged flat, and which edges only meet once folded) and computes the exact
3D fold: a 2D face layout plus a per-hinge fold angle. `polygon_fold_app.py`
is a Tkinter viewer that lets you pick a net and drag a slider from flat
(0%) to fully folded (100%).

## Directory layout

- `polygon_fold_app.py` — the Tkinter GUI app (entry point, class `PolygonFoldApp`)
- `net_fold_utils/` — the reusable library (see below)
- `nets/*.poly` — **human-authored** net specs; the only files meant to be hand-edited
- `fold_cache/*.fold` — **computed** cache, one per `.poly`, kept in a separate directory from `nets/` on purpose (disposable output vs. source input)
- `build_fold_cache.py` — top-level script: precompute/refresh all caches, prints per-net progress
- `tools/generate_platonic_nets.py` — regenerates the 5 Platonic solids' `.poly` files from canonical 3D coordinates
- `requirements.txt` — numpy, scipy, networkx, matplotlib

## The `.poly` format (human-writable input)

Full grammar lives in `net_fold_utils/polyhedron_spec.py`'s docstring. Shape:

```
FACES        <- one line per face: its integer degree (k for a regular k-gon)
4
4
ROOT 0
NET          <- (f1 f2) hinge edges forming the flat net; must be a spanning tree (n-1 edges)
0 1
EXTRA        <- (f1 f2) edges that only meet once folded; these pin down the fold angles
1 2
```

No coordinates or angles are ever hand-written — both are derived.

## Pipeline (`net_fold_utils/net_io.py: load_polyhedron_net`)

1. `polyhedron_spec.py` parses `FACES`/`NET`/`EXTRA`.
2. `combinatorics.py` (`EdgeMap`) turns the full edge list into a per-face
   edge-index map via a `networkx` planar embedding. By Whitney's theorem a
   3-connected planar graph's embedding — hence the cyclic edge order
   around each face — is unique up to a global mirror, so edge indices
   never need to be given explicitly.
3. `net_layout.py` BFS-attaches regular polygons (`polygon_geom.py`) along
   `NET` edges to build the flat 2D net.
4. `fold_solver.py` numerically solves (scipy `least_squares`, many random
   restarts) for the hinge angle at every `NET` edge such that every
   `EXTRA` edge's two faces coincide in 3D at fold progress `t=1`.
   - **Known gotcha**: the same closure equations can have more than one
     root. The icosahedron net, for instance, also algebraically closes
     into a smaller, self-intersecting "collapsed" shape. `fold_solver.
     _is_embeddable` rejects any solution where two non-adjacent vertices
     end up closer than one edge length (checked via `net_fold_core.
     distinct_vertices`), then the smallest-total-rotation surviving
     solution is chosen.
5. `net_fold_core.fold()` is the actual rotation engine — walks the hinge
   tree, rotating each subtree rigidly by its solved angle. It works
   identically for both `.poly`-derived and legacy `.txt` nets.

## Caching (`net_fold_utils/fold_cache.py`)

Solving is the slow part — up to ~60s for the icosahedron because of the
random-restart search. A `.fold` cache file (in `fold_cache/`, not `nets/`)
mirrors the legacy explicit-coordinate format (2D vertex positions per face
+ fold angle per hinge) plus a `CHECKSUM sha256:...` of the source `.poly`.
`load_net()` transparently reuses the cache if the checksum still matches,
else re-solves and rewrites it. Run `python build_fold_cache.py` after
editing a `.poly` file to warm the cache ahead of time (`--force` to
recompute everything unconditionally); otherwise it happens lazily on first
load.

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
  automatically by file extension in `net_io.load_net`.
