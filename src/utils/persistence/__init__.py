"""persistence: parse/load/write/cache the on-disk .json/.fold net formats.

Modules:
  polyhedron_spec -- parse/write the faces/edges .json format (rigid nets)
  net_io          -- load_net(): dispatches .json / legacy .txt loaders
  fold_cache      -- checksummed .fold cache for rigid nets, so a solve only
                      runs once per unchanged source .json
  stretchy_cache  -- checksummed JSON cache for stretchy (vertex-loop) nets

stretchy_cache defines its own same-named load_with_cache/is_cached/
build_all/cache_path_for -- always reached via the qualified submodule
(`from utils.persistence import stretchy_cache`), never flattened into this
top-level namespace alongside fold_cache's, to avoid the name clash.
"""
from .net_io import load_net, load_polyhedron_net, load_net_txt
from .fold_cache import load_with_cache, is_cached, build_all
from . import stretchy_cache

__all__ = [
    "load_net", "load_polyhedron_net", "load_net_txt",
    "load_with_cache", "is_cached", "build_all",
    "stretchy_cache",
]
