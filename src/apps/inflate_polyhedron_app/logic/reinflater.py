"""Pressure-guess pure logic, moved out of inflate_polyhedron_app/app.py (2026-09-30
modularization). Algorithmically identical to the sibling interactive_inflater_app's own
`logic/reinflater.py` -- duplicated rather than cross-imported, matching this project's own
stated convention of not importing between the two sibling apps.
"""

__all__ = ["guess_pressure_from_history"]


def guess_pressure_from_history(level_history, subdivision_level, target_rms_pct):
    """Estimates the pressure to hand estimate_pressure_for_target_stretch as its own starting
    guess, drawing on already-calibrated prior levels' history instead of falling back to the
    generic per-solid-derived constant. Looks at every prior level's (pressure, achieved
    rms_stretch_pct) pair and picks whichever one's achieved stretch landed closest to the new
    target -- scaling that record's pressure by 2 per level of resolution difference (each
    Subdivide roughly doubles resolution, and empirically needs ~2x the pressure for the same
    target RMS stretch %).

    Deliberately not a `target_rms_pct / achieved` rescale -- that ratio explodes when a level's
    achieved stretch is ~0 (pressure genuinely had no effect there, e.g. a mesh whose faces
    cancel out under pressure until a later Subdivide gives it real degrees of freedom),
    producing an absurd guess that overflows the solver. Picking the closest-achieved record
    instead never divides by anything.

    A level whose record has `pressure_found` False is skipped entirely -- its "pressure" never
    came from a real calibration (the search gave up because the mesh was unresponsive to
    pressure there), so it's not a usable extrapolation point.

    Returns None (falling back to the generic guess) if no level below `subdivision_level` has a
    usable recorded pressure/stretch pair yet."""
    best = None
    for level, record in level_history.items():
        if level >= subdivision_level or not record:
            continue
        if not record.get("pressure_found", True):
            continue
        prior_pressure = record.get("pressure")
        prior_rms = record.get("rms_stretch_pct")
        if not prior_pressure or prior_rms is None:
            continue
        error = abs(prior_rms - target_rms_pct)
        if best is None or error < best[0]:
            best = (error, level, prior_pressure)
    if best is None:
        return None
    _, level, prior_pressure = best
    return prior_pressure * (2 ** (subdivision_level - level))
