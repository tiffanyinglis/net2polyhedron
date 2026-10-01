from interactive_inflater_app.logic import face_selecter as fs


def test_toggle_selection_replaces_when_not_additive():
    assert fs.toggle_selection({1, 2}, 3, additive=False) == {3}


def test_toggle_selection_adds_when_additive_and_not_present():
    assert fs.toggle_selection({1, 2}, 3, additive=True) == {1, 2, 3}


def test_toggle_selection_removes_when_additive_and_already_present():
    assert fs.toggle_selection({1, 2, 3}, 2, additive=True) == {1, 3}


def test_effective_hover_groups_filters_stale_and_subtracts_selected():
    requested = {1, 2, 3}
    groups_present = {1, 2}  # group 3 no longer exists (stale)
    selected = {2}
    assert fs.effective_hover_groups(requested, groups_present, selected) == {1}
