"""Tk numeric-entry validation, shared by inflate_polyhedron_app and interactive_inflater_app
(2026-10-01, explicit: "make sure they are using shared code whenever possible. shared code
should be moved to utils" -- previously duplicated, byte-identical, as each app's own
`_is_valid_numeric_partial`). Not inflate_polyhedron-specific (a plain regex check against Tk's
own `%P` validate-key string), so this lives at the top level rather than under a domain
sub-package."""
import re

__all__ = ["is_valid_numeric_partial"]


def is_valid_numeric_partial(proposed, allow_exponent, allow_decimal=True):
    """True if `proposed` is a full number or a prefix a user could still be typing toward one
    (e.g. "", "-", ".", "1.", "1e", "1e-" when `allow_exponent`) -- accepting these in-progress
    states, not just a complete `float()`-parseable string, lets a user type a negative number
    or decimal point without the first keystroke being rejected. `allow_exponent` permits an
    "e"/"E" exponent; `allow_decimal` permits a "."."""
    digits = r"\d*\.?\d*" if allow_decimal else r"\d*"
    pattern = f"-?{digits}(?:[eE][-+]?\\d*)?" if allow_exponent else f"-?{digits}"
    return re.fullmatch(pattern, proposed) is not None
