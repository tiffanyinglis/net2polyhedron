# Docstring convention

Every function/method docstring in `src/utils/` (and, going forward, `src/apps/`)
should be **about 4-5 lines long**: succinct, and focused on describing
**input and output** -- not the full history of why the function looks the
way it does.

## What to include

- One line saying what the function does/returns, in plain terms.
- What each non-obvious parameter means (skip params whose name already
  says it all).
- What's returned (shape/type), if not obvious from the function name.
- At most one line for a genuinely load-bearing gotcha (something that
  would cause a caller to misuse the function if they didn't know it) --
  not general design rationale.

## What to leave out

- Multi-paragraph "why we designed it this way" narratives, empirical
  findings, benchmark numbers, and historical iteration ("tried X first,
  it broke on Y, so we did Z instead"). That reasoning is valuable, but it
  belongs in the **module-level docstring** (a "Design notes" section) or
  in git history/commit messages -- not repeated on every function that
  touches the design decision.
- References to other functions' own internals unless the caller truly
  needs them to use this function correctly.
- Restating what the code obviously does (e.g. don't explain a one-line
  arithmetic expression line by line).

## Module-level docstrings

Not held to the 4-5 line limit -- a module's docstring is the right place
for the bigger picture (what problem this module solves, the algorithm's
overall shape, why a non-obvious design was chosen). Keep it as long as it
needs to be, but still front-load the essential "what this module is"
in the first paragraph so a skim gets the gist.

## Example

Before (too long, mixes rationale into a function comment):

```python
def _sphere_bound_volume(faces, edge_length):
    """An optimistic (normally unreachable) target volume for _inflate's
    pressure term: the volume of the SPHERE with the same total surface
    area as the mesh's own faces (each assumed a regular polygon of
    `edge_length` sides, even though the actual solved faces may bend a
    little) -- the isoperimetric-maximal shape for that much surface,
    so no achievable inflation ever fully reaches it. Scaled to the
    mesh's own size (not some arbitrary huge constant) so the pressure
    it creates stays reasonable regardless of how big the mesh is: e.g.
    for the regular icosahedron this comes out to ~2.40, within 10% of
    its true volume (~2.18) ..."""
```

After (4-5 lines, input/output focused; the "why" moves to the module
docstring's Design notes):

```python
def _sphere_bound_volume(faces, edge_length):
    """Volume of the sphere with the same total surface area as `faces`
    (each assumed a regular polygon of `edge_length` sides) -- an
    optimistic, normally-unreachable inflation target, scaled to the
    mesh's own size. See module docstring's Design notes for why this
    (rather than a fixed constant) is used as _inflate's pressure target."""
```

## Maintaining this

When editing a function in `src/utils/`, check its docstring still fits
this convention; when adding a new function, write its docstring to this
convention from the start rather than adding a full-length one and
trimming later.
