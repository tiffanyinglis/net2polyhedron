"""net_unfolder: derive a net (spanning tree, unfoldable flat layout, fold
angles) from an already-built model.Polyhedron.

Modules:
  hinge         -- Hinge: one fold hinge, identified by its child face index
  net_unfolder  -- NetUnfolder: takes a Polyhedron, computes its spanning
                    tree/flat layout/fold angles (reading angles directly
                    off the given geometry -- see its module docstring),
                    and folds at any progress t. Nothing is cached --
                    computing all of this is cheap enough (no numerical
                    solving anywhere) that it isn't worth the complexity.
                    Also is_closed(polyhedron) -- whether a Polyhedron is
                    closed is a fact about fold progress, not pure static
                    geometry, so it lives here rather than as a property
                    on model.Polyhedron itself.
"""
from .hinge import Hinge
from .net_unfolder import NetUnfolder, is_closed

__all__ = ["Hinge", "NetUnfolder", "is_closed"]
