"""persistence: parse/write the on-disk .json net format, plus checksum
utilities used by the stretchy pipeline's cache.

Modules:
  polyhedron_spec -- parse/write the vertices+faces .json format (rigid nets,
                      a direct encoding of a polyhedron_unfolder.Polyhedron)
  checksums       -- source_checksum(path), used by stretchy_cache.py
  stretchy_cache  -- checksummed JSON cache for stretchy (vertex-loop) nets

Loading a rigid net is utils.polyhedron_unfolder.UnfoldablePolyhedron.load(),
which parses polyhedron_spec.py's format itself and recomputes fresh every
time -- unfolding is cheap enough that the rigid pipeline has no cache at all
(see utils.polyhedron_unfolder's module docstring).
"""
from . import stretchy_cache

__all__ = ["stretchy_cache"]
