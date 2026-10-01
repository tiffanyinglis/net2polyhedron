from interactive_inflater_app.logic import inflation_type_chooser as itc


def test_pendant_add_always_attaches_flat():
    assert itc.choose_action("add_face", 5, True, True) == itc.PENDANT_ATTACH
    assert itc.choose_action("add_face", 5, False, True) == itc.PENDANT_ATTACH


def test_not_fully_inflated_redirects_to_full_inflate():
    for kind in itc.DIFF_ELIGIBLE_KINDS:
        assert itc.choose_action(kind, None, False, False) == itc.FULL_INFLATE_REDIRECT


def test_dispatches_each_eligible_kind_once_fully_inflated():
    assert itc.choose_action("add_face", 5, True, False) == itc.DIFF_ADD_FACE
    assert itc.choose_action("remove_face", frozenset({5}), True, False) == itc.DIFF_REMOVE_FACE
    assert itc.choose_action("add_connection", None, True, False) == itc.DIFF_CONNECTION_CHANGE
    assert itc.choose_action("remove_connection", None, True, False) == itc.DIFF_CONNECTION_CHANGE


def test_complex_or_none_change_is_unsupported():
    assert itc.choose_action("complex", None, True, False) == itc.UNSUPPORTED
    assert itc.choose_action("none", None, True, False) == itc.UNSUPPORTED
