"""Generic time- and count-bounded "try several seeded attempts, keep the best" policy
(2026-10-01, explicit user request: "create a class called seed_selecter that chooses the best
seed from our 5 attempts"). Factored out of `pre_inflation_relaxer.relax_initial_configuration_
with_orientation_retry` so BOTH apps' own Full Inflate can share one seed-selection policy
(previously `interactive_inflater_app` called `relax_initial_configuration` directly, with no
retry at all, while `inflate_polyhedron_app` had its own retry loop inlined into that one
function) -- `SeedSelecter` itself knows nothing about orientation/meshes at all, just "run an
attempt, score it, keep the best, stop early on a good-enough score or a time/count budget."
"""
import time

__all__ = ["SeedSelecter"]

# Defaults (2026-10-01, explicit): up to 5 attempts, but never spend more than 10s total
# searching for one. A model big/complex enough for a single attempt to approach this budget is
# also, empirically, unlikely to land in the all-faces-flipped failure mode this search exists
# for in the first place (more bracing faces leaves less room for the whole shape to silently
# settle backwards) -- so it's not worth chasing a problem that mostly affects SMALL, fast-to-
# relax nets by spending proportionally MORE time on exactly the inputs that need it least.
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_MAX_SEARCH_TIME = 10.0


class SeedSelecter:
    """Runs up to `max_attempts` seeded attempts (seed, seed+1, seed+2, ...), stopping at the
    first one `score_fn` reports as good enough, or -- failing that -- keeping whichever scored
    best. Time-bounded: the FIRST attempt always runs regardless of how long it takes (a budget
    can't retroactively un-run something), but every attempt AFTER that only starts if the
    cumulative time spent so far is still under `max_search_time` -- so a single slow attempt
    that alone exceeds the budget naturally means "try once, accept whatever that gives."
    """

    def __init__(self, max_attempts=DEFAULT_MAX_ATTEMPTS, max_search_time=DEFAULT_MAX_SEARCH_TIME):
        self.max_attempts = max_attempts
        self.max_search_time = max_search_time

    def select(self, seed, attempt_fn, score_fn, on_attempt=None, should_stop=None):
        """`attempt_fn(attempt_seed) -> result` runs one attempt. `score_fn(result) ->
        (accepted, rank_key)` -- `accepted` True stops the search immediately and returns this
        attempt; otherwise `rank_key` ranks it against other rejected attempts (SMALLER is
        better). `on_attempt(attempt_index, attempt_seed, result, accepted, rank_key)`, if given,
        is called after every attempt (accepted or not) -- purely for the caller's own logging/
        diagnostics, this class does none of its own. `should_stop()`, if given, is checked after
        every attempt alongside the time/count budget (e.g. a caller's own cancellation request).

        Returns (result, attempt_seed, accepted, attempts_tried). `accepted` False means every
        attempt tried came back not-good-enough and `result` is just the least-bad one by
        `rank_key`."""
        best = None
        elapsed_total = 0.0
        attempts_tried = 0
        for attempt_index in range(self.max_attempts):
            attempt_seed = seed + attempt_index
            attempt_start = time.monotonic()
            result = attempt_fn(attempt_seed)
            elapsed_total += time.monotonic() - attempt_start
            attempts_tried += 1

            accepted, rank_key = score_fn(result)
            if on_attempt is not None:
                on_attempt(attempt_index, attempt_seed, result, accepted, rank_key)
            if accepted:
                return result, attempt_seed, True, attempts_tried
            if best is None or rank_key < best[0]:
                best = (rank_key, result, attempt_seed)

            if elapsed_total >= self.max_search_time:
                break
            if should_stop is not None and should_stop():
                break
        _, result, attempt_seed = best
        return result, attempt_seed, False, attempts_tried
