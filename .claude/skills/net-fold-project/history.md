# Removed features (historical — rarely relevant, don't resurrect w/o asking)

**Rigid-unfolding pipeline** (`src/apps/polyhedron_unfolder/`, `src/utils/polyhedron_unfolder/`,
`src/utils/persistence/polyhedron_spec.py`, their tests, `data/input/nets/*.json`) — DELETED,
lives only in sibling `polyhedron-unfolder` project now. Handled ordinary one-shared-edge nets:
real 3D coords in, BFS spanning tree of hinges, flat 2D layout, fold angles read directly off
given geometry (no solve needed, since coords were given). `src/utils/geometry/polyhedron.py`
(Polyhedron class) is a self-contained re-add of that pipeline's own class, still used here.
`bounding_box.py`/`cullable_face.py` were written for its 3D view, now unused but kept
(untouchable list).

**`solve_wireframe`** (random-restart least_squares search for a stretchy mesh's starting
shape, + its on-disk cache `stretchy_cache.py`/`checksums.py`/`build_cache.py`) — DELETED,
replaced by the current `random_initial_positions` + `relax_initial_configuration` spring-relax
approach (see physics.md). No caching anywhere in this project any more.

**Fabric subdivision** (`subdivide_mesh`, `solve_fabric_mesh`, `generate_subdivided_stretchy_nets.py`
— wrote fixed-resolution `<name>_res<N>.json` files for the old cache) — DELETED along with
`solve_wireframe`. `mesh_subdivide.load_fabric_spec` still reads a legacy file's `coarse_faces`
field if present (untested by any shipped net) but ignores its baked-in fine mesh.

**Old `inflate_polyhedron_app` designs**: "pick a net, see the one auto-solved answer" →
"precomputed fixed-resolution fabric mesh" → current "random start + live Relax/Inflate/
Subdivide, no cache". Also removed along the way: a "Save" button (wrote positions+PNG to
`data/output/Save/`), a standalone "Auto"-calibrate-pressure-only button + pressure readout
label (superseded once Inflate itself calibrates and the history table shows pressure per row).

**Sample-solid generator scripts** (`sample_polyhedra.py`, `generate_platonic_nets.py`,
`generate_stretchy_platonic_nets.py`, `generate_open_dodecahedron_nets.py`) — DELETED. The
`data/input/*.json` files are hand-kept canonical inputs now, not regenerated artifacts.
