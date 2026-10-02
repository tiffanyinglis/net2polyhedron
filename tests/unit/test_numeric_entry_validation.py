from utils.numeric_entry_validation import is_valid_numeric_partial


def test_accepts_empty_string_as_in_progress():
    assert is_valid_numeric_partial("", allow_exponent=False) is True


def test_accepts_a_bare_minus_sign_as_in_progress():
    assert is_valid_numeric_partial("-", allow_exponent=False) is True


def test_accepts_a_complete_integer():
    assert is_valid_numeric_partial("42", allow_exponent=False) is True


def test_rejects_decimal_point_when_not_allowed():
    assert is_valid_numeric_partial("1.5", allow_exponent=False, allow_decimal=False) is False


def test_accepts_decimal_point_when_allowed():
    assert is_valid_numeric_partial("1.5", allow_exponent=False, allow_decimal=True) is True
    assert is_valid_numeric_partial("1.", allow_exponent=False, allow_decimal=True) is True


def test_rejects_exponent_when_not_allowed():
    assert is_valid_numeric_partial("1e-03", allow_exponent=False) is False


def test_accepts_exponent_and_in_progress_exponent_when_allowed():
    assert is_valid_numeric_partial("1e-03", allow_exponent=True) is True
    assert is_valid_numeric_partial("1e-", allow_exponent=True) is True
    assert is_valid_numeric_partial("1e", allow_exponent=True) is True


def test_rejects_non_numeric_text():
    assert is_valid_numeric_partial("abc", allow_exponent=False) is False
    assert is_valid_numeric_partial("1.2.3", allow_exponent=False) is False
