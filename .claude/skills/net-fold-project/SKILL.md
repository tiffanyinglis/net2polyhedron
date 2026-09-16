---
name: net-fold-project
description: Architecture, file layout, and conventions for this polyhedron net-folding project (the src/utils library, .json net formats, the stretchy-mesh solver, the Tkinter apps in src/apps, tests). Load before non-trivial changes instead of re-deriving from files.
---

# net2polyhedron — index

Written for Claude, not humans: terse, abbreviated, load-bearing facts only. **See
"Maintenance" at bottom before adding anything — keep it that way.**

Load only what the task needs:
- **`untouchable.md`** — check before editing ANY existing file. Non-negotiable, always relevant.
- **`physics.md`** — stretchy_mesh.py force model/solver/calibration, current tuned constants.
  Load before any change touching relax_once, relax_initial_configuration, or pressure/tolerance.
- **`apps.md`** — inflate_polyhedron_app / interactive_builder_app / polygon_subdivision_app UI
  behavior. Load before UI changes.
- **`history.md`** — removed features (rigid pipeline, fabric subdivision, old cache). Rarely
  needed — only if something references a symbol/file that no longer exists.

## Layout
```
src/utils/            reusable lib: geometry/ (Polyhedron, regular-polygon 2D), subdivisions/
                       (2D fine-mesh demo), inflate_polyhedron/ (the stretchy solver — see physics.md)
src/apps/              one dir per Tkinter app (see apps.md) + common/ + ui/ (shared, not domain logic)
data/input/stretchy_nets/*.json   human-authored nets: vertex-loop, NO coords
tests/unit/<category>/            mirrors src/utils/ sub-package layout 1:1
docs/README.md, docs/algorithm.md user-facing usage + scientific-paper-style algorithm writeup
                                   — keep in sync with physics.md when the physics changes
```
Winding: every face CCW from outside. Shared edge = `v->w` one face, `w->v` other. Checked at
load (`load_stretchy_mesh`) — duplicate directed edge is the only load-time error; an edge with
no reverse partner is a valid open boundary (mesh need not be closed).

No rigid-unfolding pipeline in this repo (deleted, lives in sibling `polyhedron-unfolder`
project) — see `history.md` before assuming any such file/symbol still exists.

## No hacky physics terms without asking
`stretchy_mesh.py`'s force model: only add a term if it's a literal physical quantity (a real
spring force, a real pressure force). Rejected before, without being asked: a target/reference-
volume pressure term (compounds stretch across repeated Subdivide-then-Inflate cycles), a
per-edge stretch clamp (papers over a pressure-model instability instead of calibrating pressure
or fixing the spring law itself). The current hardening-spring term (see `physics.md`) was added
BECAUSE the user explicitly asked for it — that's the bar. If you notice a pressure/stretch/
convergence problem, explain the actual cause and propose options; don't silently add a term to
make the symptom go away.

## Testing & docstrings
`python tests/run_tests.py` or `pytest` from repo root (`pytest.ini` sets pythonpath). Runs in a
few seconds. Mirror `src/utils/`'s sub-package layout 1:1 when adding a test file.

Function docstrings in `src/utils/` (and going forward `src/apps/`): ~4-5 lines, input/output
focused — what it does/returns, non-obvious params, load-bearing gotchas. NOT: multi-paragraph
"why we designed it this way", benchmark numbers, "tried X first" history — that goes in the
MODULE docstring's own Design-notes section (no length limit there) or git history, not repeated
per-function.

## Untouchable files — always check first
See `untouchable.md`. Summary: everything that existed before `interactive_builder_app` work
began is DONE and off-limits without explicit user permission naming the file + change. This
includes `stretchy_mesh.py` and every app's `app.py`.

## Maintenance (read before editing this skill)
This skill was massively trimmed once already — was 2300+ lines of narrative "tried X, verified
Y on nets A/B/C" investigation logs. Keep it lean going forward:
- Record CURRENT state + a 1-line why, not the investigation transcript. Git history already has
  the transcript — don't duplicate it here.
- Don't re-add exhaustive "verified on nets A/B/C at values X/Y/Z" logs. One sentence: what's
  true now, and why if it's non-obvious or someone might otherwise "fix" it back.
- Prefer a new small file over growing an existing one past ~150-200 lines. Split by concern,
  link from this index.
- Abbreviate freely, drop filler words, use fragments over full sentences — this is read by
  Claude, not humans, so optimize for fast parsing over prose quality. Not code-only either:
  plain words are fine, just terse ones.
- When a section describes something now REMOVED or CHANGED, overwrite it — don't leave the old
  description next to a "well actually now it's X" patch. Stale-but-present docs cost more than
  git history costs to search.
