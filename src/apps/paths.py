"""Shared filesystem locations for every src/apps entry point.

Every app/script here should import from this module BEFORE importing
anything from `utils` -- as a side effect, importing this module inserts
src/ onto sys.path, which is what makes `from utils.<category> import ...`
resolve when an app is run directly (`python src/apps/polygon_fold_app.py`)
rather than as an installed package.
"""
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

REPO_ROOT = _SRC_DIR.parent
DATA_DIR = REPO_ROOT / "data"

NETS_DIR = DATA_DIR / "input" / "nets"
STRETCHY_NETS_DIR = DATA_DIR / "input" / "stretchy_nets"

FOLD_CACHE_DIR = DATA_DIR / "cache" / "fold_cache"
STRETCHY_CACHE_DIR = DATA_DIR / "cache" / "stretchy_cache"

OUTPUT_DIR = DATA_DIR / "output"
SAVE_DIR = OUTPUT_DIR / "Save"
