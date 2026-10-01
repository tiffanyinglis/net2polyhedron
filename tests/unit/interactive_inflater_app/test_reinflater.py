from interactive_inflater_app.logic import reinflater


def test_guess_pressure_from_history_none_when_nothing_recorded():
    assert reinflater.guess_pressure_from_history({}, subdivision_level=1, target_rms_pct=5.0) is None


def test_guess_pressure_from_history_picks_closest_rms_and_scales_by_level_gap():
    level_history = {
        1: {"pressure": 10.0, "rms_stretch_pct": 4.0, "pressure_found": True},
        2: {"pressure": 20.0, "rms_stretch_pct": 6.0, "pressure_found": True},
    }
    # At level 3, target 5.0 is equidistant from both -- level 2 (closer index) wins per the
    # strict "<" comparison keeping the FIRST-seen best on a tie.
    guess = reinflater.guess_pressure_from_history(level_history, subdivision_level=3,
                                                     target_rms_pct=4.5)
    # Level 1's rms (4.0) is closer to 4.5 than level 2's (6.0) -- picks level 1, scaled by
    # 2 ** (3 - 1) = 4.
    assert guess == 10.0 * 4


def test_guess_pressure_from_history_skips_unfound_and_future_levels():
    level_history = {
        1: {"pressure": 10.0, "rms_stretch_pct": 4.0, "pressure_found": False},
        3: {"pressure": 99.0, "rms_stretch_pct": 4.0, "pressure_found": True},  # not yet reached
    }
    assert reinflater.guess_pressure_from_history(level_history, subdivision_level=2,
                                                    target_rms_pct=4.0) is None
