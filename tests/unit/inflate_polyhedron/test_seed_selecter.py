import time

from utils.inflate_polyhedron.seed_selecter import SeedSelecter


def test_accepts_first_good_enough_attempt_without_trying_more():
    calls = []

    def attempt_fn(seed):
        calls.append(seed)
        return seed

    def score_fn(result):
        return result == 10, 0  # accepted on the very first attempt (seed == 10)

    selecter = SeedSelecter(max_attempts=5, max_search_time=10.0)
    result, seed_used, accepted, tried = selecter.select(10, attempt_fn, score_fn)
    assert (result, seed_used, accepted, tried) == (10, 10, True, 1)
    assert calls == [10]


def test_tries_up_to_max_attempts_and_keeps_best_by_rank_key_when_none_accepted():
    def attempt_fn(seed):
        return seed

    # Rank key is distance from 13 -- seed 13 is the "least bad" even though never accepted.
    def score_fn(result):
        return False, abs(result - 13)

    selecter = SeedSelecter(max_attempts=5, max_search_time=10.0)
    result, seed_used, accepted, tried = selecter.select(10, attempt_fn, score_fn)
    assert tried == 5
    assert accepted is False
    assert seed_used == 13
    assert result == 13


def test_stops_after_exactly_one_attempt_when_it_alone_exceeds_the_time_budget():
    calls = []

    def slow_attempt(seed):
        calls.append(seed)
        time.sleep(0.15)
        return seed

    def never_accept(result):
        return False, 0

    selecter = SeedSelecter(max_attempts=5, max_search_time=0.05)
    result, seed_used, accepted, tried = selecter.select(0, slow_attempt, never_accept)
    assert tried == 1
    assert calls == [0]
    assert accepted is False


def test_runs_as_many_fast_attempts_as_fit_in_the_time_budget():
    calls = []

    def fast_attempt(seed):
        calls.append(seed)
        return seed

    def never_accept(result):
        return False, 0

    selecter = SeedSelecter(max_attempts=5, max_search_time=10.0)
    result, seed_used, accepted, tried = selecter.select(0, fast_attempt, never_accept)
    assert tried == 5
    assert calls == [0, 1, 2, 3, 4]


def test_on_attempt_callback_fires_for_every_attempt():
    log = []

    def attempt_fn(seed):
        return seed

    def score_fn(result):
        return result == 2, 0

    def on_attempt(attempt_index, attempt_seed, result, accepted, rank_key):
        log.append((attempt_index, attempt_seed, result, accepted))

    selecter = SeedSelecter(max_attempts=5, max_search_time=10.0)
    selecter.select(0, attempt_fn, score_fn, on_attempt=on_attempt)
    assert log == [(0, 0, 0, False), (1, 1, 1, False), (2, 2, 2, True)]


def test_should_stop_ends_the_search_early():
    calls = []

    def attempt_fn(seed):
        calls.append(seed)
        return seed

    def never_accept(result):
        return False, 0

    selecter = SeedSelecter(max_attempts=5, max_search_time=10.0)
    result, seed_used, accepted, tried = selecter.select(
        0, attempt_fn, never_accept, should_stop=lambda: len(calls) >= 2)
    assert tried == 2
    assert calls == [0, 1]
