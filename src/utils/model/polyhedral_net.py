"""PolyhedralNet: the flat net (2D layout) + hinge tree + fold angles --
the pre-fold state of the rigid pipeline. PolyhedralNet.load() is the one
public loading entry point, replacing the old net_io.load_net()/
load_polyhedron_net()/load_net_txt() and fold_cache.load_with_cache().

Construction always ends by wrapping a net_fold_core.Net plus a list of
legacy hinge dicts (however they were derived -- see _load_json_uncached/
_load_legacy_txt) into Face/Hinge objects via _from_legacy. The derivation
logic itself -- EdgeMap, build_net_layout, solve_fold_angles,
Net.build_tree -- is called exactly as it is today, unchanged."""
import numpy as np

from ..persistence.polyhedron_spec import load_polyhedron_spec
from ..persistence.net_io import parse_net_body
from ..combinatorics.edge_map import EdgeMap
from ..geometry2d.net_layout import build_net_layout
from ..geometry3d.net_fold_core import Net, fold as _fold, precompute_subtree_map
from ..geometry3d.fold_solver import solve_fold_angles
from .face import Face
from .hinge import Hinge
from .polyhedron import Polyhedron


class PolyhedralNet:
    def __init__(self, name, root_id, faces, hinges):
        self.name = name
        self.root_id = root_id
        self.faces = faces          # dict[fid -> Face], 2D only
        self.hinges = hinges        # list[Hinge], BFS order
        self._hinge_by_child = {h.child_id: h for h in hinges}
        self._subtree_map = None    # lazy; the hinge tree's shape never changes

    # ---- loading ----

    @classmethod
    def load(cls, path, cache_dir=None):
        """Dispatch by file extension: .json for the abstract combinatorial
        spec (via the .fold cache, see persistence.fold_cache), .txt for
        the legacy explicit-coordinate format.

        cache_dir, if given, overrides where the .fold cache is looked up/
        written -- needed whenever the cache directory isn't simply a
        sibling of path's own parent directory."""
        if str(path).endswith(".json"):
            return cls._load_json(path, cache_dir)
        return cls._load_legacy_txt(path)

    @classmethod
    def _load_json(cls, path, cache_dir):
        # Local import: persistence.fold_cache imports PolyhedralNet at
        # module level (to build/read cached nets), so importing it back
        # at PolyhedralNet's own module level would be circular. This is
        # the same technique net_io.load_net used for the same reason.
        from ..persistence import fold_cache

        cache_path = fold_cache.cache_path_for(path, cache_dir)
        checksum = fold_cache.source_checksum(path)

        cached = fold_cache._valid_cache_or_clear_stale(cache_path, checksum)
        if cached is not None:
            _, net = cached
            return net

        net = cls._load_json_uncached(path)
        fold_cache.write_fold_cache(cache_path, checksum, net)
        return net

    @classmethod
    def _load_json_uncached(cls, path):
        """The slow path: full combinatorial + numerical solve, no cache.
        Same call sequence as the old net_io.load_polyhedron_net.

        For an OPEN net (some faces marked "omit"), edge_map is built from
        every edge -- including "hidden" ones touching an omitted face --
        so the faces that ARE present still recover their correct
        polygon-edge index, but only net_edges and extra_edges (never
        hidden_edges) go on to actually build geometry or constrain the
        fold, since an omitted face has neither."""
        degrees, net_edges, extra_edges, hidden_edges, omitted, root, name = \
            load_polyhedron_spec(path)
        edge_map = EdgeMap(degrees, net_edges + extra_edges + hidden_edges)
        legacy_net, legacy_hinges = build_net_layout(degrees, net_edges, edge_map, root, omitted)
        fold_angles = solve_fold_angles(legacy_net, root, legacy_hinges, extra_edges, edge_map)
        return cls._from_legacy(legacy_net, root, legacy_hinges, fold_angles, name)

    @classmethod
    def _load_legacy_txt(cls, path):
        """Legacy explicit-coordinate format (no solving needed): hinges
        are derived from coincident 2D points (Net.build_tree), not from
        any edge-id list. The unfold root is always the first (lowest-id)
        face declared -- Net.build_tree(root=None) picks that automatically."""
        with open(path) as f:
            faces_raw, fold_angles_deg, name, _ = parse_net_body(f)

        legacy_net = Net()
        for fid, pts in faces_raw:
            legacy_net.add_face(pts, fid=fid)

        root_id, legacy_hinges = legacy_net.build_tree(root=None)
        fold_angles = {fid: np.radians(deg) for fid, deg in fold_angles_deg.items()}

        missing = [h["child"] for h in legacy_hinges if h["child"] not in fold_angles]
        if missing:
            raise ValueError(f"{path}: missing FOLD angle for face(s) {missing}")

        return cls._from_legacy(legacy_net, root_id, legacy_hinges, fold_angles, name or str(path))

    @classmethod
    def _from_legacy(cls, legacy_net, root_id, legacy_hinges, fold_angles, name):
        faces = {fid: Face(fid, sides=len(pts), vertices2d=pts)
                  for fid, pts in legacy_net.faces.items()}
        hinges = [Hinge(parent_id=h["parent"], child_id=h["child"],
                         parent_edge_idx=h["parent_edge_idx"],
                         child_edge_idx=h["child_edge_idx"],
                         angle=fold_angles[h["child"]])
                  for h in legacy_hinges]
        return cls(name=name, root_id=root_id, faces=faces, hinges=hinges)

    # ---- queries ----

    def hinge_for(self, child_id):
        return self._hinge_by_child[child_id]

    @property
    def fold_angles(self):
        """dict child_id -> radians -- for feeding the unchanged
        net_fold_core.fold() internals."""
        return {h.child_id: h.angle for h in self.hinges}

    # ---- folding ----

    def _as_legacy(self):
        legacy_net = Net()
        for fid, face in self.faces.items():
            legacy_net.add_face(face.vertices2d, fid=fid)
        return legacy_net, [h.to_legacy_dict() for h in self.hinges]

    def fold(self, t=1.0, fold_signs=None):
        """Return a Polyhedron at fold progress t. self._subtree_map is
        cached on this instance (the hinge tree's shape never changes
        across many calls, e.g. dragging a fold slider), so repeated calls
        only re-run net_fold_core.fold()'s per-call rotation work, not its
        precompute -- the same precompute-once/reuse-many pattern
        fold_solver.py already applies during solving, applied here to
        repeated rendering instead."""
        legacy_net, legacy_hinges = self._as_legacy()
        if self._subtree_map is None:
            self._subtree_map = precompute_subtree_map(legacy_hinges)
        verts3d = _fold(legacy_net, self.root_id, legacy_hinges, self.fold_angles,
                         t, fold_signs=fold_signs, subtree_map=self._subtree_map)
        faces3d = {fid: face.with_vertices3d(verts3d[fid]) for fid, face in self.faces.items()}
        return Polyhedron(name=self.name, faces=faces3d, t=t, root_id=self.root_id)

    # ---- app-facing convenience ----

    def assign_colors(self, palette):
        """Assign each face a color from `palette` (a list of color
        strings), cycling if there are more faces than colors, in
        ascending face-id order. Color then lives on the Face and
        survives into any Polyhedron folded from this net (see
        Face.with_vertices3d)."""
        for i, fid in enumerate(sorted(self.faces)):
            self.faces[fid].color = palette[i % len(palette)]

    def __repr__(self):
        return f"PolyhedralNet(name={self.name!r}, faces={len(self.faces)}, hinges={len(self.hinges)})"
