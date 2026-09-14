---
name: net-fold-project
description: Entry-point architecture, file layout, and conventions for this polyhedron net-folding project (the src/utils library, .json/.fold formats, tests) shared across all three apps in src/apps — plus the untouchable-files list. Load this first for any non-trivial change; load the matching per-app skill (polygon-subdivision-app, inflate-polyhedron-app, interactive-builder-app) for that app's own deep detail.
---

# Polyhedron net-folding project

## Doc maintenance (read this before adding to any SKILL.md)

Keep skill docs trimmed and organized — do not let one file become a giant
history log. Each `SKILL.md` should hold only what's needed to make a
change safely: current behavior, hard rules, file locations. Deep
debugging narratives / rejected-approach post-mortems belong in that
skill's own `reference/*.md`, linked from the `SKILL.md`, read only when
actually relevant. When you add substantial new history to a skill,
move older history out to a `reference/` file in the same pass rather
than appending forever.

## Untouchable files

The user has finished these — do not add, remove, or "clean up" anything
in them, even additively, unless the user asks for a change to one BY
NAME or unambiguous description. If a task would require touching one,
stop and ask first, naming the file and the change needed. This list only
grows; check it before editing anything in this project. See
`reference/history.md` for why each file looks the way it does and the
few narrow exceptions granted so far.

- `src/utils/geometry/polygon_geom.py`, `polyhedron.py`, `__init__.py`
- `src/utils/inflate_polyhedron/__init__.py`, `hull_to_spec.py`,
  `mesh_levels.py`, `stretchy_mesh.py`, `stretchy_net_layout.py`
- `src/utils/subdivisions/__init__.py`, `polygon_subdivisions.py`,
  `mesh_subdivide.py`
- `src/utils/__init__.py`
- `src/apps/ui/tooltip.py`, `cullable_face.py`, `__init__.py`
- `src/apps/common/bounding_box.py`, `ui_theme.py`, `paths.py`, `__init__.py`
- `src/apps/polygon_subdivision_app/app.py`
- `src/apps/inflate_polyhedron_app/app.py`
- `data/input/stretchy_nets/*.json` (every shipped net)
- `docs/README.md`, `docs/algorithm.md`
- `.gitignore`, `requirements.txt`, `pytest.ini`, `.claude/settings.local.json`
- `.claude/skills/net-fold-project/SKILL.md` (this file)
- `tests/run_tests.py` and every existing file under `tests/unit/`

## Apps

Three Tkinter entry points. Each has its own skill covering it in depth —
load that skill instead of re-deriving an app's history from its source.

- `polygon_subdivision_app` (`src/apps/polygon_subdivision_app/app.py`) —
  unrelated to folding: splits a regular n-gon (triangle..8-gon) into a
  fine triangular mesh. See `polygon-subdivision-app` skill.
- `inflate_polyhedron_app` (`src/apps/inflate_polyhedron_app/app.py`) —
  solves nets that can't stay rigid/flat (e.g. a face sharing >1 edge with
  a neighbor) via a spring/pressure relaxation. The most algorithmically
  involved part of the project. See `inflate-polyhedron-app` skill.
- `interactive_builder_app` (`src/apps/interactive_builder_app/app.py`) —
  a 2D shape-placement canvas for hand-building nets. See
  `interactive-builder-app` skill.

A fourth app, the rigid-unfolding pipeline (`polyhedron_unfolder`), has
been deleted entirely — see `reference/history.md` if its old approach
is ever relevant again.

## Directory layout

- `src/apps/` — one folder per GUI app (`app.py` entry point each), plus:
  - `common/` — cross-app helpers, not domain logic. `paths.py` is the
    only place computing shared paths (`STRETCHY_NETS_DIR`); importing it
    is also how `src/` gets onto `sys.path` for `from utils... import`
    when running an app directly. `ui_theme.py` holds shared
    colors/theme constants. `bounding_box.py` is currently unused (kept,
    untouchable).
  - `ui/` — generic Tkinter/matplotlib widgets (`tooltip.py`). `cullable_face.py`
    is currently unused (kept, untouchable).
- `src/utils/` — the reusable library:
  - `geometry/` — domain-agnostic 2D/3D geometry: `polygon_geom.py`
    (regular polygon vertices + rigid 2D edge attachment) and
    `polyhedron.py` (class `Polyhedron`: indexed vertices, CCW faces,
    `.edges`, `.face_vertices()`, `.face_normal()`, `.is_closed()`,
    `.compute_face_adjacency()`).
  - `inflate_polyhedron/` — the stretchy (non-rigid) mesh pipeline:
    `stretchy_mesh.py` (solver), `hull_to_spec.py`
    (`polyhedron_from_vertices` via `scipy.spatial.ConvexHull`),
    `stretchy_net_layout.py` (flat BFS layout for the app's "Net" panel),
    `mesh_levels.py` (subdivision). No disk caching. See
    `inflate-polyhedron-app` skill for all of this in depth.
  - `subdivisions/` — `polygon_subdivisions.py` + `mesh_subdivide.py`
    (fine "fabric" triangulation). See `polygon-subdivision-app` skill.
- `data/input/stretchy_nets/*.json` — human-authored stretchy net specs
  (vertex-loop format — see `inflate-polyhedron-app` skill). No caches
  live under `data/`; those are per-app.
- `tests/unit/<category>/` — one test file per `src/utils/<category>/`
  module, mirroring its layout exactly, plus `unit/apps_common/` for the
  rare `src/apps/common/` helper with no Tk/matplotlib dependency. The
  rest of `src/apps/` is untested by convention. Run via
  `python tests/run_tests.py [pytest args...]` or plain `pytest`.
- `pytest.ini` sets `pythonpath = . src src/apps`.
- `requirements.txt` — numpy, scipy, networkx, matplotlib, sv-ttk, pytest (dev).
- `docs/README.md` — user-facing usage doc. `docs/algorithm.md` — the
  inflation algorithm, written up scientific-paper style.

See `reference/history.md` for the deleted rigid-unfolding pipeline and
other "used to exist" archaeology behind these choices.

## Conventions

- **Docstrings** (`src/utils/`, `src/apps/`): 4-5 lines, input/output
  focused. Include: what it does/returns, non-obvious parameters, return
  shape/type if not obvious, at most one load-bearing gotcha. Leave out:
  design-rationale narratives, empirical findings, iteration history —
  that belongs in the module docstring's "Design notes" or git history,
  not repeated per function. Module docstrings aren't length-limited.
  When editing a function, bring its docstring to this convention; when
  adding one, write it this way from the start.
- Winding convention (stretchy pipeline, current): every face loop is CCW
  as seen from outside; a shared edge is `v -> w` in one face's loop and
  `w -> v` in the other's. See `inflate-polyhedron-app` skill for the
  full stretchy-pipeline conventions (edge length, no `__main__` block, etc).
