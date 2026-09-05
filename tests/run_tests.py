"""Run the full test suite.

    python tests/run_tests.py
    python tests/run_tests.py -k cube -v   # any extra args are passed to pytest
"""
import sys

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv[1:]))
