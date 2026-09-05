"""PolyhedralNet: the flat net (now a model.Polyhedron at z=0, see `flat`
below) + hinge tree + fold angles -- the pre-fold state of the rigid
pipeline. PolyhedralNet.load() is the one public loading entry point,
replacing the old net_io.load_net()/load_polyhedron_net()/load_net_txt()
and fold_cache.load_with_cache().

Construction always ends by assembling a flat model.Polyhedron (built once,
from either net_layout.build_net_layout's BFS-attach output or a legacy
Net.build_tree() derivation -- see net_fold_core.flatten_net for how either
becomes Polyhedron-shaped data) plus Hinge objects, via _finalize/
_from_legacy. The derivation logic itself -- EdgeMap, build_net_layout,
solve_fold_angles, Net.build_tree -- is called exactly as it is today,
unchanged."""
import numpy as np

from ..persistence.polyhedron_spec import load_polyhedron_spec
from ..persistence.net_io import parse_net_body
from ..combinatorics.edge_map import EdgeMap
from ..geometry2d.net_layout import build_net_layout
from ..geometry3d.net_fold_core import (
    Net, flatten_net, fold as _fold, fold_transforms as _fold_transforms,
    cluster_faces_into_mesh)
from ..geometry3d.fold_solver import solve_fold_angles
from .face import Face
from .hinge import Hinge
from .polyhedron import Polyhedron


class PolyhedralNet:
    def __init__(self, name, root_id, flat, fid_to_index, faces, hinges):
        self.name = name
        self.root_id = root_id
        self.flat = flat                    # model.Polyhedron, the flat net at z=0
        self.fid_to_index = fid_to_index    # dict: original face id -> flat.faces position
        self.faces = faces                  # dict[fid -> Face], metadata only (id/sides/color)
        self.hinges = hinges                # list[Hinge], BFS order
        self._hinge_by_child = {h.child_id: h for h in hinges}

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
        Same call sequence as before -- build_net_layout now returns
        Polyhedron-shaped flat-net data directly (see its docstring)
        instead of a net_fold_core.Net, so it's wrapped into a Polyhedron
        here rather than inside _finalize.

        For an OPEN net (some faces marked "omit"), edge_map is built from
        every edge -- including "hidden" ones touching an omitted face --
        so the faces that ARE present still recover their correct
        polygon-edge index, but only net_edges and extra_edges (never
        hidden_edges) go on to actually build geometry or constrain the
        fold, since an omitted face has neither."""
        degrees, net_edges, extra_edges, hidden_edges, omitted, root, name = \
            load_polyhedron_spec(path)
        edge_map = EdgeMap(degrees, net_edges + extra_edges + hidden_edges)
        vertices, faces, fid_to_index, hinges = build_net_layout(
            degrees, net_edges, edge_map, root, omitted)
        flat = Polyhedron(vertices=vertices, faces=faces)
        fold_angles = solve_fold_angles(flat, fid_to_index, root, hinges, extra_edges, edge_map)
        return cls._finalize(flat, fid_to_index, root, hinges, fold_angles, name)

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
        """Build from a raw net_fold_core.Net (legacy .txt loading and
        fold_cache's .fold-cache reading both have one of these, not
        Polyhedron-shaped data directly) -- flattens it into a Polyhedron
        via net_fold_core.flatten_net, then hands off to _finalize."""
        vertices, faces, fid_to_index = flatten_net(legacy_net)
        flat = Polyhedron(vertices=vertices, faces=faces)
        return cls._finalize(flat, fid_to_index, root_id, legacy_hinges, fold_angles, name)

    @classmethod
    def _finalize(cls, flat, fid_to_index, root_id, legacy_hinges, fold_angles, name):
        """Shared final assembly step: build Face (metadata only -- side
        count read straight off the flat Polyhedron's own face-index
        tuples) and Hinge objects, then construct the PolyhedralNet."""
        faces = {fid: Face(fid, sides=len(flat.faces[pos]))
                  for fid, pos in fid_to_index.items()}
        hinges = [Hinge(parent_id=h["parent"], child_id=h["child"],
                         parent_edge_idx=h["parent_edge_idx"],
                         child_edge_idx=h["child_edge_idx"],
                         angle=fold_angles[h["child"]])
                  for h in legacy_hinges]
        return cls(name=name, root_id=root_id, flat=flat, fid_to_index=fid_to_index,
                   faces=faces, hinges=hinges)

    # ---- queries ----

    def hinge_for(self, child_id):
        return self._hinge_by_child[child_id]

    @property
    def fold_angles(self):
        """dict child_id -> radians -- for feeding the unchanged
        net_fold_core.fold() internals."""
        return {h.child_id: h.angle for h in self.hinges}

    # ---- folding ----

    def fold(self, t=1.0, fold_signs=None):
        """Return a model.Polyhedron at fold progress t (not just t=1 --
        every intermediate slider position is an equally valid Polyhedron,
        with .is_closed simply reporting False until the fold actually
        completes). Each face's own flat corners (read from self.flat) are
        folded to 3D via net_fold_core.fold(), then cluster_faces_into_mesh()
        merges coincident corners (real hinge-glued edges at any t;
        closure/extra edges too, once t reaches the solved angle) into
        shared vertex indices -- Polyhedron.faces is therefore always
        ordered by ascending original face id, so a caller needing
        per-original-face metadata (e.g. color) can zip it against
        sorted(self.faces)."""
        legacy_hinges = [h.to_legacy_dict() for h in self.hinges]
        verts3d = _fold(self.flat, self.fid_to_index, self.root_id, legacy_hinges,
                         self.fold_angles, t, fold_signs=fold_signs)
        vertices, faces = cluster_faces_into_mesh(verts3d)
        return Polyhedron(vertices=vertices, faces=faces, name=self.name)

    def face_transforms(self, t=1.0, fold_signs=None):
        """dict[fid -> np.ndarray(4,4)] -- each face's cumulative affine
        transform at fold progress t (net_fold_core.fold_transforms(),
        bridged through this net's self.flat/hinges). This is the
        unfolding's "path" as explicit matrices, independent of fold()'s
        Polyhedron-building step -- useful for inspecting/animating the
        motion itself rather than just its t=1 (or any single-t) result."""
        legacy_hinges = [h.to_legacy_dict() for h in self.hinges]
        return _fold_transforms(self.flat, self.fid_to_index, self.root_id, legacy_hinges,
                                 self.fold_angles, t, fold_signs=fold_signs)

    # ---- app-facing convenience ----

    def assign_colors(self, palette):
        """Assign each face a color from `palette` (a list of color
        strings), cycling if there are more faces than colors, in
        ascending face-id order. Color lives on Face (per-original-face
        metadata) only -- a folded Polyhedron is pure geometry and
        deliberately carries no color; a caller wanting per-face color for
        a folded solid zips sorted(self.faces) against solid.faces (see
        fold()'s docstring). self.flat (the pre-fold net) is likewise
        color-free -- render it the same way, zipping colors in by
        sorted face id."""
        for i, fid in enumerate(sorted(self.faces)):
            self.faces[fid].color = palette[i % len(palette)]

    def __repr__(self):
        return f"PolyhedralNet(name={self.name!r}, faces={len(self.faces)}, hinges={len(self.hinges)})"
