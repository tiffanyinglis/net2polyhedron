"""net_unfolder: derive a net (spanning tree, unfoldable flat layout, fold
angles) from an already-built model.Polyhedron.

Modules:
  hinge         -- Hinge: one fold hinge, identified by its child face index
  net_unfolder  -- NetUnfolder: takes a Polyhedron, computes its spanning
                    tree/flat layout/fold angles (reading angles directly
                    off the given geometry -- see its module docstring),
                    and folds at any progress t
  cache         -- checksummed cache for a NetUnfolder's computed net, so
                    an unchanged source .json is just a fast parse
"""
from .hinge import Hinge
from .net_unfolder import NetUnfolder

__all__ = ["Hinge", "NetUnfolder"]
