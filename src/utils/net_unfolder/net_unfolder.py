"""NetUnfolder: given an already-built model.Polyhedron (real 3D vertex
positions -- not an abstract combinatorial spec), derives its own net:

1. Face adjacency, read directly off the Polyhedron's own face loops (no
   planar-embedding/EdgeMap needed -- a real Polyhedron already knows
   which faces share which edge).
2. An auto-computed spanning tree over that adjacency (root is always
   face index 0 -- any face works equally well as root, same reasoning
   already applied to the old JSON format's root selection).
3. An "unfoldable" flat-layout Polyhedron: each face's own REAL 3D shape,
   projected into 2D and BFS-attached to its parent's shared edge --
   vertices are shared at hinge edges (which coincide by construction)
   and separate everywhere else, exactly like net_fold_core.flatten_net
   already produces for the old (regular-polygon) net layout, just fed
   each face's real (possibly irregular) shape instead of a synthesized
   regular polygon.
4. Each hinge's fold angle, read directly off the given geometry:
   arccos(dot(face_normal(parent), face_normal(child))) -- the rotation-
   from-flat angle a real dihedral angle implies (matches this project's
   existing convention exactly: 90 degrees for a cube's self-supplementary
   dihedral, 109.47 degrees for a tetrahedron's 70.53-degree dihedral).
   There is nothing left to numerically *solve* for -- the old
   fold_solver.py existed only because an abstract combinatorial spec has
   no coordinates to read angles from.

NetUnfolder.fold(t)/face_transforms(t) then reuse net_fold_core's fold
engine exactly as before. None of this is cached: every step above is
cheap (no numerical solving anywhere), so NetUnfolder.load()/for_polyhedron()
just recompute fresh every time rather than adding cache-staleness
complexity for a negligible speedup.
"""
from collections import deque

import numpy as np

from ..model.polyhedron import Polyhedron
from ..geometry2d.polygon_geom import rigid_transform_2d, apply_rigid
from ..geometry3d.net_fold_core import (
    Net, flatten_net, fold as _fold, fold_transforms as _fold_transforms,
    cluster_faces_into_mesh)
from .hinge import Hinge


def _face_adjacency(polyhedron):
    """dict (face_idx, edge_idx) -> (other_face_idx, other_edge_idx) for
    every polygon edge that has a match in the OPPOSITE direction on some
    other face -- the CCW-from-outside convention means a shared edge is
    v->w on one face, w->v on the other."""
    edge_owner = {}
    for fi, face in enumerate(polyhedron.faces):
        k = len(face)
        for ei in range(k):
            a, b = face[ei], face[(ei + 1) % k]
            edge_owner[(a, b)] = (fi, ei)

    adjacency = {}
    for fi, face in enumerate(polyhedron.faces):
        k = len(face)
        for ei in range(k):
            a, b = face[ei], face[(ei + 1) % k]
            match = edge_owner.get((b, a))
            if match is not None:
                adjacency[(fi, ei)] = match
    return adjacency


def _spanning_tree(polyhedron, adjacency, root):
    """BFS from `root` over `adjacency`'s face graph. Returns a list of
    legacy hinge dicts (parent/child/parent_edge_idx/child_edge_idx), same
    shape net_layout.py used to produce. A face edge with no adjacency
    entry is a boundary edge (open net) -- never a hinge target."""
    visited = {root}
    hinges = []
    q = deque([root])
    while q:
        p = q.popleft()
        for pei in range(len(polyhedron.faces[p])):
            match = adjacency.get((p, pei))
            if match is None:
                continue
            c, cei = match
            if c in visited:
                continue
            visited.add(c)
            hinges.append(dict(parent=p, child=c, parent_edge_idx=pei, child_edge_idx=cei))
            q.append(c)

    unreached = set(range(len(polyhedron.faces))) - visited
    if unreached:
        raise ValueError(f"polyhedron is disconnected (by shared edges); "
                          f"face(s) {sorted(unreached)} unreachable from root {root}")
    return hinges


def _project_face_to_2d(polyhedron, face_idx):
    """This face's own REAL 3D corners, re-expressed in an orthonormal 2D
    basis within its own plane (u = first edge direction, w = its face
    normal, v = w x u) -- exact same edge lengths as the real face, just
    flattened. Works for irregular faces too, not just regular polygons."""
    pts3d = polyhedron.face_vertices(face_idx)
    origin = pts3d[0]
    u = pts3d[1] - origin
    u = u / np.linalg.norm(u)
    w = polyhedron.face_normal(face_idx)
    v = np.cross(w, u)
    return np.array([[np.dot(p - origin, u), np.dot(p - origin, v)] for p in pts3d])


def _build_flat_layout(polyhedron, root, hinges):
    """BFS-attach each hinge's child (its own projected 2D shape) onto the
    parent's already-placed shared edge, reversed -- the same
    rigid_transform_2d/apply_rigid call net_layout.attach_polygon made,
    just fed a real face shape instead of a synthesized regular polygon.
    Returns (vertices, faces) -- Polyhedron-shaped flat-net data, via
    flatten_net (shared hinge-edge vertices, separate everywhere else)."""
    local2d = {fi: _project_face_to_2d(polyhedron, fi) for fi in range(len(polyhedron.faces))}
    placed = {root: local2d[root]}
    for h in hinges:
        p, c = h["parent"], h["child"]
        pi, ci = h["parent_edge_idx"], h["child_edge_idx"]
        pverts = placed[p]
        p1, p2 = pverts[pi], pverts[(pi + 1) % len(pverts)]
        local = local2d[c]
        a, b = local[ci], local[(ci + 1) % len(local)]
        R, t = rigid_transform_2d(a, b, p2, p1)  # reversed -- unfolds outward
        placed[c] = apply_rigid(local, R, t)

    net = Net()
    for fi in sorted(placed):
        net.add_face(placed[fi], fid=fi)
    return flatten_net(net)


def _hinge_fold_angle(polyhedron, parent_idx, child_idx):
    """The rotation-from-flat angle a real dihedral angle implies --
    arccos(dot(face_normal(parent), face_normal(child))). See this
    module's docstring for the geometric reasoning/examples."""
    n_p = polyhedron.face_normal(parent_idx)
    n_c = polyhedron.face_normal(child_idx)
    return np.arccos(np.clip(np.dot(n_p, n_c), -1.0, 1.0))


class NetUnfolder:
    def __init__(self, polyhedron, root, hinges, flat):
        self.polyhedron = polyhedron   # the given closed (or open) solid
        self.root = root               # face index, always 0
        self.hinges = hinges            # list[Hinge]
        self.flat = flat                # model.Polyhedron, the unfoldable net at z=0
        self._hinge_by_child = {h.child_id: h for h in hinges}

    # ---- construction ----

    @classmethod
    def _compute(cls, polyhedron, root):
        adjacency = _face_adjacency(polyhedron)
        legacy_hinges = _spanning_tree(polyhedron, adjacency, root)
        vertices, faces = _build_flat_layout(polyhedron, root, legacy_hinges)
        flat = Polyhedron(vertices=vertices, faces=faces, name=polyhedron.name)
        hinges = [Hinge(parent_id=h["parent"], child_id=h["child"],
                         parent_edge_idx=h["parent_edge_idx"],
                         child_edge_idx=h["child_edge_idx"],
                         angle=_hinge_fold_angle(polyhedron, h["parent"], h["child"]))
                  for h in legacy_hinges]
        return cls(polyhedron, root, hinges, flat)

    @classmethod
    def for_polyhedron(cls, polyhedron, root=0):
        """Compute the spanning tree, flat layout, and fold angles for an
        already-built Polyhedron. No caching -- this is fast enough
        (microseconds to low-milliseconds even for a bushy net, since
        nothing is numerically solved for, see this module's docstring)
        that recomputing on every load isn't worth the complexity a cache
        would add."""
        return cls._compute(polyhedron, root)

    @classmethod
    def load(cls, path):
        """Parse `path` (persistence.polyhedron_spec's vertices+faces
        format) into a Polyhedron, then for_polyhedron() it."""
        from ..persistence.polyhedron_spec import load_polyhedron_spec

        vertices, faces, name = load_polyhedron_spec(path)
        polyhedron = Polyhedron(vertices=vertices, faces=faces, name=name)
        return cls.for_polyhedron(polyhedron, root=0)

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
        completes)."""
        legacy_hinges = [h.to_legacy_dict() for h in self.hinges]
        verts3d = _fold(self.flat, self.root, legacy_hinges, self.fold_angles,
                         t, fold_signs=fold_signs)
        vertices, faces = cluster_faces_into_mesh(verts3d)
        return Polyhedron(vertices=vertices, faces=faces, name=self.polyhedron.name)

    def face_transforms(self, t=1.0, fold_signs=None):
        """dict[face_index -> np.ndarray(4,4)] -- each face's cumulative
        affine transform at fold progress t, the unfolding's "path" as
        explicit matrices (net_fold_core.fold_transforms(), bridged
        through this net's flat layout/hinges)."""
        legacy_hinges = [h.to_legacy_dict() for h in self.hinges]
        return _fold_transforms(self.flat, self.root, legacy_hinges,
                                 self.fold_angles, t, fold_signs=fold_signs)

    def __repr__(self):
        return (f"NetUnfolder(name={self.polyhedron.name!r}, "
                f"faces={len(self.polyhedron.faces)}, hinges={len(self.hinges)})")
