"""persistence: parse/write the on-disk .json net format, plus checksum
utilities shared across caches.

Modules:
  polyhedron_spec -- parse/write the vertices+faces .json format (rigid nets,
                      a direct encoding of a model.Polyhedron)
  checksums       -- source_checksum(path), shared by net_unfolder/cache.py
                      (rigid pipeline) and stretchy_cache.py (stretchy pipeline)
  stretchy_cache  -- checksummed JSON cache for stretchy (vertex-loop) nets

Loading a rigid net is utils.net_unfolder.NetUnfolder.load(), not anything
in this package directly -- net_unfolder.cache's is_cached/build_all are
the pieces NetUnfolder.load() and each app's build_cache.py/"Compute"
button build on for cache warming and status checks.
"""
from . import stretchy_cache

__all__ = ["stretchy_cache"]
