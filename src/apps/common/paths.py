"""Shared, cross-app filesystem locations: human-authored input nets.
NOT per-app caches -- each app that needs one keeps it in its own folder,
specifically so the apps don't depend on each other's cache directory.

Every app/script should import from here (or from its own local `paths`
sibling module, if it has one) BEFORE importing anything from `utils` --
as a side effect, importing this module inserts src/ onto sys.path, which
is what makes `from utils.<category> import ...` resolve when an app is
run directly (`python src/apps/<app>/app.py`) rather than as an installed
package. An app one level deeper than src/apps/ must add src/apps/ to
sys.path itself first, before it can `from common.paths import ...` at
all -- see any such app.py's top of file for that small bootstrap.
"""
import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parent.parent
_SRC_DIR = _APPS_DIR.parent
for _p in (_SRC_DIR, _APPS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

REPO_ROOT = _SRC_DIR.parent
DATA_DIR = REPO_ROOT / "data"

STRETCHY_NETS_DIR = DATA_DIR / "input" / "stretchy_nets"
