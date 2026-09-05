"""utils: the reusable geometry/topology/persistence library behind every
app in src/apps/.

Modules, grouped by concern:
  polygon_geom          -- flat 2D polygon geometry (regular polygon
                            vertices, rigid 2D edge attachment)
  polyhedron             -- Polyhedron: pure 3D solid geometry (shared,
                            indexed vertices; CCW faces; derived edges;
                            is_closed()), no unfolding knowledge
  polyhedron_unfolder    -- the generic fold engine: Hinge, hinge_transform,
                            face_normal, fold_transforms
  unfoldable_polyhedron -- UnfoldablePolyhedron: derives a net (spanning
                            tree, flat layout, fold angles) from a
                            Polyhedron and folds it at any unfold amount;
                            UnfoldablePolyhedron.load() is the public
                            loading entry point for the rigid pipeline
  spanning_tree          -- create_spanning_tree_BFS: a generic graph BFS,
                            no polyhedron knowledge of its own
  polyhedron_json_parser -- parse/write the on-disk .json format

Import the specific module rather than this top-level package, e.g.
`from utils.unfoldable_polyhedron import UnfoldablePolyhedron` -- there is
no flattened top-level re-export here on purpose, to keep each module the
single source of truth for what it exports.
"""
