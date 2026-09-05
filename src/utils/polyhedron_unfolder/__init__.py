"""polyhedron_unfolder: derive a net (spanning tree, unfoldable flat
layout, fold angles) from an already-built geometry3d.Polyhedron.

Modules:
  polyhedron_unfolder  -- NetUnfolder: takes a Polyhedron, computes its
                    spanning tree/flat layout/fold angles (reading angles
                    directly off the given geometry -- see its module
                    docstring), and folds at any progress t. Nothing is
                    cached -- computing all of this is cheap enough (no
                    numerical solving anywhere) that it isn't worth the
                    complexity. Also Hinge (one fold hinge, identified by
                    its child face index) and is_closed(polyhedron) --
                    whether a Polyhedron is closed is a fact about fold
                    progress, not pure static geometry, so it lives here
                    rather than as a property on geometry3d.Polyhedron
                    itself. Hinge used to be its own module (hinge.py)
                    but had no consumers outside NetUnfolder, so it was
                    folded in here rather than kept as a separate
                    one-class file. (This package used to be named
                    net_unfolder -- renamed since NetUnfolder's whole job
                    is unfolding a Polyhedron, matching the naming used
                    elsewhere in the project, e.g. apps/polyhedron_unfolder/.)
"""
from .polyhedron_unfolder import NetUnfolder, Hinge, is_closed

__all__ = ["NetUnfolder", "Hinge", "is_closed"]
