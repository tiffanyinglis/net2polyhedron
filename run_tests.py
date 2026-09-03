"""Run the full test suite.

    python run_tests.py
    python run_tests.py -k fold_cache   # any extra args are passed to pytest
"""
import sys

import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv[1:]))
