"""Pressure calibration for Level 1+: runs several relax_once trials at
different pressures to find one whose result lands within tolerance of
a target RMS stretch %, keeping whichever SANE trial got closest. See
physics.md's Pressure calibration section for the full bracket-then-
bisect search strategy.

Depends on stretchy_mesh (relax_once, _total_rest_area) -- not the other
way around, so stretchy_mesh never needs to import this module."""
import numpy as np

from .stretchy_mesh import relax_once, _total_rest_area
from .convergence_checker import CONVERGENCE_GTOL
from .inside_out_checker import InsideOutChecker

# Empirical starting point: required pressure scales with how much total rest AREA it's pushing
# against, not vertex/face count -- see physics.md's Pressure calibration section for the
# derivation. A decent first guess, not exact, which is why estimate_pressure_for_target_stretch
# refines it against an actual relax_once result rather than trusting it alone.
_PRESSURE_AREA_PRODUCT_ESTIMATE = 25.0

# How far a single calibration step is allowed to rescale pressure -- guards against a wild jump
# if one trial's stretch reading is degenerate (e.g. near zero), while still letting normal cases
# converge in a couple of iterations (stretch responds roughly linearly to pressure in the
# low-stretch regime this targets).
_PRESSURE_RATIO_CLAMP = (0.2, 5.0)

# Matches inflate_polyhedron_app's own LEVEL_DEFAULT_TARGET_RMS_PCT default.
DEFAULT_TARGET_RMS_STRETCH_PCT = 5.0

# A trial reading RMS stretch beyond this multiple of the target (and beyond this ABSOLUTE
# floor, so a tiny target doesn't make an ordinary 20% stretch look "insane") is treated as the
# mesh having blown up rather than settled, in estimate_pressure_for_target_stretch's own
# bracket search -- not a usable data point for "how stretchy is this pressure", since a diverged
# run's own stretch number reflects numerical blow-up, not the mesh's real response to pressure.
_INSANE_STRETCH_FLOOR_PCT = 500.0
_INSANE_STRETCH_TARGET_MULTIPLE = 5.0

# Sentinel RMS/max stretch reading for a calibration trial whose integrator diverged into
# NaN/Inf positions before relax_once could even compute real stretch stats -- always >=
# _INSANE_STRETCH_FLOOR_PCT so it's treated exactly like any other insane/blown-up trial by the
# bracket search. Never surfaced to a user in practice.
_DIVERGED_SENTINEL_STRETCH_PCT = 1e6


def estimate_pressure_for_target_stretch(positions, faces, edge_length,
                                          target_rms_pct=DEFAULT_TARGET_RMS_STRETCH_PCT,
                                          max_iterations=8,
                                          tol_pct=1.0, max_nfev_per_trial=5000, stop_event=None,
                                          gtol=CONVERGENCE_GTOL, rng=None,
                                          initial_pressure_guess=None,
                                          capture_frames=False, on_progress=None, edges=None,
                                          repulsion_strength=None,
                                          repulsion_vertex_ids=None,
                                          repulsion_vertex_multipliers=None,
                                          rms_exclude_edges=None,
                                          pressure_exclude_faces=None):
    """positions/faces/edge_length/edges: as relax_once. `repulsion_strength`/
    `repulsion_vertex_ids`/`repulsion_vertex_multipliers`/`rms_exclude_edges`/
    `pressure_exclude_faces` are forwarded unchanged to every relax_once call this makes (every
    trial and the final top-up) -- note this means `target_rms_pct` is calibrated against the
    EXCLUDED-edges-aside RMS too, so an open polygon's own stretch never drives the pressure
    search. Finds a pressure whose relax_once result lands within `tol_pct` of `target_rms_pct`
    RMS stretch (RMS, not max -- an irregular/subdivided mesh stretches unevenly). Every trial
    runs at the exact same step size and step budget a real Inflate run would use
    (`max_nfev_per_trial`); a trial that still diverges numerically is caught and treated as an
    ordinary insane/blown-up trial rather than raising (see _DIVERGED_SENTINEL_STRETCH_PCT).
    `gtol` and `rng` are both forwarded to every trial's own relax_once call unchanged, so a
    caller with its own convergence tolerance and/or stuck-vertex kick calibrates pressure
    against the SAME settings it'll actually inflate with. Every trial starts fresh from the
    given `positions` (not chained from the previous trial's result), since different pressures
    can have very different equilibria and this is searching for the pressure, not steering a
    shape.

    `repulsion_strength=None` forwards relax_once's own default (REPULSION_STRENGTH) unchanged --
    kept as an explicit param here rather than importing that constant directly, so this module
    only depends on stretchy_mesh's public relax_once entry point.

    Starts from _PRESSURE_AREA_PRODUCT_ESTIMATE's geometric guess, unless
    `initial_pressure_guess` is given -- a caller with a BETTER starting point (e.g.
    inflate_polyhedron_app's `_guess_pressure_from_history`, see physics.md's Pressure
    calibration section) can land the search closer on the FIRST trial, needing fewer of the
    `max_iterations` budget. The search is BRACKET-then-BISECT rather than a single
    multiplicative rescale repeated blindly: as long as every trial so far has landed on the SAME
    side of the target (all under it, or all "insane"), it keeps rescaling by (target /
    achieved), clamped by _PRESSURE_RATIO_CLAMP. The MOMENT a trial lands on the OPPOSITE side
    from the best one seen so far, pressure is bracketed between them and every remaining trial
    bisects the bracket instead -- the only way to actually converge on an intermediate pressure
    once the mesh's own response to pressure turns out highly nonlinear near some critical value.

    Keeps whichever SANE trial got CLOSEST to the target rather than just the last one (an
    insane/diverged trial is never a candidate): the rescale step assumes more pressure means
    more stretch, which fails on at least one known net (three_squares stretches LESS as pressure
    rises) -- without keeping the best-so-far, a net where that assumption is wrong would
    escalate pressure every iteration chasing a target it's moving away from. Returns (pressure,
    new_positions, steps_taken, max_stretch_pct, rms_stretch_pct, optimality, converged,
    pressure_found) -- the middle five exactly as relax_once's own return, from whichever trial
    this settled on (if every single trial was insane, the LAST one anyway, so this never raises
    for an irrecoverably bad target).

    `pressure_found` is True unless this gave up WITHOUT ever finding a usable pressure: every
    trial was insane within `max_iterations`.

    The WINNING trial, if it hasn't actually converged yet (it only ran `max_nfev_per_trial`
    steps, a search-time budget, not a real convergence criterion), is topped up with one further
    UNCAPPED `relax_once` call from wherever it left off, at the same pressure/gtol/rng, before
    returning -- this function always returns a trial that's either genuinely converged or hit
    relax_once's own MAX_UNBOUNDED_STEPS runaway cap. `steps_taken` in the return already
    includes this top-up's own steps. Skipped entirely if no sane trial was ever found, or
    `stop_event` was set.

    `capture_frames`, if True, adds an 8th return value: the WINNING trial's own positions every
    CONVERGENCE_CHECK_INTERVAL steps (relax_once's own on_progress cadence) as `(positions,
    cumulative_steps_taken)` pairs, from its starting `positions` (step 0) through however far it
    got -- INCLUDING the convergence top-up above, so a caller replaying these sees one
    continuous run rather than a break at `max_nfev_per_trial`. Every trial captures its own
    frames as it runs (there's no way to know in advance which will end up best), but only the
    winning trial's list is kept. When False (the default), no frames are captured and the return
    shape is unchanged from before this param existed.

    `on_progress(cumulative_steps)`, if given, is called every CONVERGENCE_CHECK_INTERVAL steps
    of EVERY trial attempted (and of the convergence top-up), with the TOTAL number of relax_once
    steps actually computed so far across every trial -- including insane/thrown-away ones, since
    that's still real computation. Deliberately NOT reset to 0 between trials (so a live "Steps"
    counter never jumps backwards) -- monotonically increasing for the whole call, though NOT
    necessarily ending exactly at the final returned `steps_taken` (only the WINNING trial's own
    count), since the search can keep probing after a good-enough candidate if nothing satisfies
    `tol_pct` outright; a caller should snap its own displayed count to the real returned
    `steps_taken` once this function returns."""
    relax_once_kwargs = dict(
        edges=edges, rng=rng,
        repulsion_vertex_ids=repulsion_vertex_ids,
        repulsion_vertex_multipliers=repulsion_vertex_multipliers,
        rms_exclude_edges=rms_exclude_edges,
        pressure_exclude_faces=pressure_exclude_faces,
    )
    if repulsion_strength is not None:
        relax_once_kwargs["repulsion_strength"] = repulsion_strength

    if initial_pressure_guess is not None:
        pressure = initial_pressure_guess
    else:
        total_area = _total_rest_area(faces, edge_length)
        pressure = _PRESSURE_AREA_PRODUCT_ESTIMATE * (target_rms_pct / 100.0) / total_area
    insane_ceiling = max(_INSANE_STRETCH_FLOOR_PCT, target_rms_pct * _INSANE_STRETCH_TARGET_MULTIPLE)
    # Catches a trial that settled into a genuinely converged, but globally INSIDE-OUT,
    # equilibrium (see InsideOutChecker's own module docstring) -- built once against the
    # search's own starting `positions`, reused for every trial.
    inside_out_checker = InsideOutChecker(positions, faces)
    best_error, best_pressure, best_result, best_frames = None, None, None, None
    # Once both are set, every remaining trial bisects between them:
    # lo_pressure is the LARGEST pressure so far confirmed sane and AT OR
    # UNDER target; hi_pressure is the SMALLEST pressure so far confirmed
    # either insane or over target.
    lo_pressure = hi_pressure = None
    result = None
    trial_frames = None
    cumulative_steps = 0
    pressure_found = True
    for _ in range(max_iterations):
        # `(positions, 0)` -- this trial's own starting point at step 0
        # (the same starting `positions` for every trial) -- is the very
        # first frame, so a replay of the winning trial's own frames
        # starts from where it actually did.
        trial_frames = [(positions, 0)] if capture_frames else None
        # `trial_base` (NOT `cumulative_steps` directly) is captured by
        # value via this default-arg trick, not by reference -- a plain
        # closure over the loop's own `cumulative_steps` would see
        # whatever it's grown to by the time the callback actually FIRES
        # (mid-relax_once, on a LATER iteration's value), not the value
        # at the moment THIS trial started.
        def _relax_progress(new_positions, steps_taken, *_rest, trial_base=cumulative_steps):
            if capture_frames:
                trial_frames.append((new_positions, steps_taken))
            if on_progress is not None:
                on_progress(trial_base + steps_taken)
        need_progress = capture_frames or on_progress is not None
        try:
            # A trial pressure far outside the sane range is EXPECTED to blow the integrator up
            # toward NaN/Inf before the LinAlgError below catches it -- silence the resulting
            # float overflow warnings for this deliberately-tried bad trial only; overflow/
            # invalid warnings anywhere else in the codebase (a real bug) still surface normally.
            with np.errstate(over='ignore', invalid='ignore'):
                result = relax_once(positions, faces, edge_length, pressure,
                                     max_nfev=max_nfev_per_trial, stop_event=stop_event, gtol=gtol,
                                     on_progress=_relax_progress if need_progress else None,
                                     **relax_once_kwargs)
            trial_positions, trial_steps, _, rms_stretch, _, _ = result
        except np.linalg.LinAlgError:
            # A pathological trial (e.g. a pressure far outside any sane range) can still blow
            # the explicit integrator up into NaN/Inf positions -- _remove_rigid_motion's Kabsch
            # SVD then can't converge on garbage input. Not worth crashing calibration over:
            # treated exactly like an ordinary insane/blown-up trial instead (see
            # _DIVERGED_SENTINEL_STRETCH_PCT). Its own frames (if any) are meaningless --
            # discarded rather than kept for replay.
            result = (positions, 0, _DIVERGED_SENTINEL_STRETCH_PCT,
                      _DIVERGED_SENTINEL_STRETCH_PCT, None, False)
            trial_positions = positions
            rms_stretch = _DIVERGED_SENTINEL_STRETCH_PCT
            trial_frames = None
            trial_steps = 0
        cumulative_steps += trial_steps
        sane = rms_stretch < insane_ceiling
        # A sane-by-magnitude trial can still be WRONG: a globally inside-out equilibrium (see
        # InsideOutChecker) reads as ordinary sane-but-over-target stretch, which would otherwise
        # make the bracket search rescale pressure DOWNWARD -- deeper into the spurious branch,
        # never discovering the real (higher-pressure) one. `usable` excludes it from both
        # best-candidacy and the normal target-comparison bracket logic below.
        inside_out = sane and inside_out_checker.is_inside_out(trial_positions)
        usable = sane and not inside_out
        if usable:
            error = abs(rms_stretch - target_rms_pct)
            if best_error is None or error < best_error:
                best_error, best_pressure, best_result, best_frames = (
                    error, pressure, result, trial_frames)
        stopped = stop_event is not None and stop_event.is_set()
        if stopped or (usable and error < tol_pct):
            break
        if inside_out:
            # Always escalate, regardless of this trial's own (meaningless, in this spurious
            # branch) rms_stretch reading -- the mesh needs MORE pressure to escape the inverted
            # equilibrium, never less. Still recorded as a confirmed lower bound so a later
            # genuine over-target/insane trial at higher pressure brackets correctly against it.
            lo_pressure = pressure
            pressure = ((lo_pressure + hi_pressure) / 2 if hi_pressure is not None
                        else pressure * _PRESSURE_RATIO_CLAMP[1])
            continue
        if usable and rms_stretch <= target_rms_pct:
            lo_pressure = pressure
        else:
            hi_pressure = pressure
        if lo_pressure is not None and hi_pressure is not None:
            pressure = (lo_pressure + hi_pressure) / 2
        elif hi_pressure is not None:
            # No sane/under-target trial yet to bracket against -- the
            # very first guess was already too high; keep halving until
            # one shows up (then the branch above takes over).
            pressure = hi_pressure / 2
        elif rms_stretch > 0:
            ratio = target_rms_pct / rms_stretch
            ratio = min(max(ratio, _PRESSURE_RATIO_CLAMP[0]), _PRESSURE_RATIO_CLAMP[1])
            pressure *= ratio
        else:
            # Degenerate reading (zero stretch) with nothing to bracket against yet and no ratio
            # to rescale by -- give up on this trial path rather than looping forever on the same
            # zero reading.
            break
    stopped = stop_event is not None and stop_event.is_set()
    if best_result is None:
        # Every trial was insane -- no sane candidate exists at all within max_iterations; report
        # the last attempt anyway rather than raising, same as the original algorithm's own
        # contract (always returns SOMETHING derived from an actual relax_once call). Not a real
        # trial worth topping up to convergence.
        best_pressure, best_result, best_frames = pressure, result, trial_frames
        pressure_found = False
    else:
        new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged = best_result
        if not converged and not stopped:
            # Seeded with the SAME duplicate-first-frame convention `trial_frames` uses above:
            # `top_up_frames[0]` here is `(new_positions, steps_taken)`, exactly
            # `best_frames[-1]`, so the `[1:]` slice below drops that genuine duplicate rather
            # than the top-up's own first real checkpoint.
            top_up_frames = [(new_positions, steps_taken)] if capture_frames else None

            def _topup_progress(p, s, *_rest):
                if capture_frames:
                    top_up_frames.append((p, steps_taken + s))
                if on_progress is not None:
                    on_progress(cumulative_steps + s)

            need_progress = capture_frames or on_progress is not None
            try:
                best_result = relax_once(new_positions, faces, edge_length, best_pressure,
                                          max_nfev=None, stop_event=stop_event, gtol=gtol,
                                          on_progress=_topup_progress if need_progress else None,
                                          **relax_once_kwargs)
                (new_positions, top_up_steps, max_stretch, rms_stretch,
                 optimality, converged) = best_result
                best_result = (new_positions, steps_taken + top_up_steps, max_stretch,
                                rms_stretch, optimality, converged)
                if capture_frames:
                    # top_up_frames[0] (its own step-0 checkpoint) is the exact same position as
                    # best_frames[-1] -- merged in as one continuous run, not duplicated.
                    best_frames = best_frames + top_up_frames[1:]
            except np.linalg.LinAlgError:
                # The winning trial was itself sane -- a genuine divergence during its OWN top-up
                # would be surprising, but not worth losing the already-good `best_result` over;
                # keep it exactly as the bracket search left it.
                pass
    new_positions, steps_taken, max_stretch, rms_stretch, optimality, converged = best_result
    if capture_frames:
        return (best_pressure, new_positions, steps_taken, max_stretch, rms_stretch,
                optimality, converged, best_frames or [], pressure_found)
    return (best_pressure, new_positions, steps_taken, max_stretch, rms_stretch, optimality,
            converged, pressure_found)
