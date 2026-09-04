"""persistence: parse/load/write/cache the on-disk .json/.fold net formats.

Modules:
  polyhedron_spec -- parse/write the faces/edges .json format (rigid nets)
  net_io          -- shared FACES/ROOT/FOLD text parsing (parse_net_body),
                      used by both the legacy .txt loader and fold_cache
  fold_cache      -- checksummed .fold cache for rigid nets, so a solve only
                      runs once per unchanged source .json
  stretchy_cache  -- checksummed JSON cache for stretchy (vertex-loop) nets

Loading a rigid net (either format) is model.PolyhedralNet.load(), not
anything in this package directly -- fold_cache's is_cached/build_all are
the pieces PolyhedralNet.load() and each app's build_cache.py/"Compute"
button build on for cache warming and status checks.

stretchy_cache defines its own same-named load_with_cache/is_cached/
build_all/cache_path_for -- always reached via the qualified submodule
(`from utils.persistence import stretchy_cache`), never flattened into this
top-level namespace alongside fold_cache's, to avoid the name clash.
"""
from .fold_cache import is_cached, build_all
from . import stretchy_cache

__all__ = [
    "is_cached", "build_all",
    "stretchy_cache",
]
