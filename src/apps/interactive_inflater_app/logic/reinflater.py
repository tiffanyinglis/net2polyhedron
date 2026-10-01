"""Full-cold-reinflate pure decisions, moved out of InflaterPane (2026-09-30 modularization).

The reinflate pipeline itself (`on_full_inflate_clicked`/`_run_inflate_step`/
`_on_inflate_step_done`) stays in app.py almost entirely as-is: it's an inherently stateful,
multi-callback, background-threaded state machine (`_run_background`'s queue/poll loop,
`self.faces`/`self.positions`/`self.subdivision_level` mutated in lockstep with each level's own
background relax/calibration call) where splitting the sequencing itself out would risk
regressing a lot of carefully-tuned behavior for little real decoupling benefit. Only the one
genuinely pure, self-contained DECISION inside that pipeline -- picking a warm-start pressure
guess from this run's own history -- is extracted here.
"""

__all__ = ["guess_pressure_from_history"]


def guess_pressure_from_history(level_history, subdivision_level, target_rms_pct):
    """Looks at every level ALREADY completed this Full Inflate run (`level_history`) and picks
    whichever one's own ACHIEVED RMS stretch landed closest to `target_rms_pct`, scaling that
    record's pressure by 2 per level of resolution difference (each Subdivide roughly doubles
    resolution, empirically needing ~2x the pressure for the same target RMS stretch %).
    Deliberately not a `target_rms_pct / achieved` rescale -- that ratio explodes when a level's
    achieved stretch is ~0. A level whose search never found a working pressure at all
    (`pressure_found` False) is skipped -- not a usable extrapolation point. Returns None (the
    caller then falls back to `estimate_pressure_for_target_stretch`'s own generic guess) if
    nothing usable is recorded yet -- e.g. Level 1, the very first calibration of a run."""
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
