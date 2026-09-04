"""
Core engine for folding a polygonal net into a 3D solid.

Model:
- A "Net" is a set of flat polygonal faces defined in 2D "net space".
- Faces that share an edge (matching endpoint coordinates) are glued.
- The glue graph must be a TREE (no cycles) -- that's what makes a valid net.
- Folding = walk the tree from a root face; at each hinge, compose that
  hinge's rotation (about the 3D line of the shared edge, scaled by fold
  progress t) with its parent's already-computed transform, giving each
  face one cumulative 4x4 affine matrix -- see fold_transforms().
"""

import numpy as np
from itertools import combinations
from collections import defaultdict, deque

from scipy.spatial.transform import Rotation

TOL = 1e-6


class Net:
    def __init__(self):
        self.faces = {}      # face_id -> list of 2D np.array points (ordered polygon)
        self._next_id = 0

    def add_face(self, points2d, fid=None):
        """fid: explicit face id to use (e.g. to preserve a polyhedron
        spec's original face numbering when some ids are skipped, as for
        an OPEN net's omitted faces -- see net_layout.build_net_layout).
        Defaults to the next sequential id, as before."""
        if fid is None:
            fid = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, fid + 1)
        self.faces[fid] = [np.array(p, dtype=float) for p in points2d]
        return fid

    def find_shared_edges(self):
        """Return list of (faceA, iA, faceB, iB): edge iA of A (verts iA,iA+1)
        matches edge iB of B (possibly reversed)."""
        found = []
        ids = list(self.faces.keys())
        for a, b in combinations(ids, 2):
            pa, pb = self.faces[a], self.faces[b]
            for i in range(len(pa)):
                p1, p2 = pa[i], pa[(i + 1) % len(pa)]
                for j in range(len(pb)):
                    q1, q2 = pb[j], pb[(j + 1) % len(pb)]
                    same = np.allclose(p1, q1, atol=TOL) and np.allclose(p2, q2, atol=TOL)
                    rev = np.allclose(p1, q2, atol=TOL) and np.allclose(p2, q1, atol=TOL)
                    if same or rev:
                        found.append((a, i, b, j))
        return found

    def build_tree(self, root=None):
        """Build a spanning tree of the glue graph via BFS.
        Returns (root, list of hinges), each hinge =
        dict(parent, child, parent_edge_idx, child_edge_idx)."""
        edges = self.find_shared_edges()
        adj = defaultdict(list)
        for (a, i, b, j) in edges:
            adj[a].append((b, i, j))
            adj[b].append((a, j, i))

        if root is None:
            root = next(iter(self.faces))

        visited = {root}
        hinges = []
        q = deque([root])
        while q:
            node = q.popleft()
            for (nbr, my_idx, nbr_idx) in adj[node]:
                if nbr not in visited:
                    visited.add(nbr)
                    hinges.append(dict(parent=node, child=nbr,
                                        parent_edge_idx=my_idx, child_edge_idx=nbr_idx))
                    q.append(nbr)

        unreached = set(self.faces) - visited
        if unreached:
            raise ValueError(f"Net is disconnected or has a cycle; "
                              f"faces {unreached} unreachable from root {root}.")
        return root, hinges


def hinge_transform(axis_point, axis_dir, angle):
    """4x4 homogeneous affine matrix: rotate by `angle` radians about the
    3D line through axis_point with direction axis_dir. The rotation
    itself is scipy.spatial.transform.Rotation's axis-angle
    construction; translating the axis to the origin, rotating, then
    translating back is folded into one matrix so the whole rigid motion
    -- rotation AND the translation needed to pivot around an off-origin
    axis -- composes with other such matrices via plain matrix
    multiplication (see fold_transforms)."""
    axis_dir = axis_dir / np.linalg.norm(axis_dir)
    R = Rotation.from_rotvec(axis_dir * angle).as_matrix()
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = axis_point - R @ axis_point
    return M


def face_normal(points):
    """Outward unit normal of a folded (3D) planar CCW polygon face, via
    the cross product of its first two edges. "Outward" relies on the
    net's CCW winding convention (see net_layout.py / polygon_geom.py) --
    verified empirically for every net in nets/: the fold always produces
    consistent outward normals this way, for every face, with no need to
    know the solid's centroid."""
    p0, p1, p2 = points[0], points[1], points[2]
    n = np.cross(p1 - p0, p2 - p0)
    return n / np.linalg.norm(n)


def _cluster_point_ids(points, tol):
    """Transitively cluster `points` (a list of (3,) arrays) into groups of
    mutually-within-`tol` points, via union-find. Returns a list of
    cluster-root ids, one per point, in the same order as `points` --
    two points that are "the same" up to floating-point/solver noise
    always get the SAME id, however their raw coordinates happen to fall
    relative to any arbitrary grid. Shared by distinct_vertices() (merge
    per-face corners into real vertices) and is_closed_solid() (match
    edge endpoints) so both use one actual distance check instead of
    independently rounding coordinates to a tol-sized grid, which two
    genuinely-coincident points can straddle the boundary of (see
    is_closed_solid's docstring)."""
    n = len(points)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if np.linalg.norm(points[i] - points[j]) < tol:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    return [find(i) for i in range(n)]


def is_closed_solid(verts3d, tol=1e-4):
    """True if the folded shape is a closed 2-manifold -- every face's
    every polygon edge is matched by exactly one other face's edge at the
    same two 3D points (in either order) -- and False if any edge is a
    free/boundary edge belonging to only one face, as for an OPEN net
    (e.g. a polyhedron with one or more faces omitted; see
    polyhedron_spec.py's module docstring).

    This is purely geometric (just the already-folded points, no
    combinatorial bookkeeping needed), so it works the same for a JSON
    net's omitted faces and a legacy .txt net alike, and for the .fold
    cache -- which drops the JSON's "omit"/"hidden" info entirely,
    keeping only folded coordinates. It's what callers should check
    before relying on backface culling (ui.cullable_face._CullableFace,
    used by polyhedron_unfolder): that trick's assumption -- a face's own
    orientation alone determines whether the solid's far side hides it
    from the camera -- only holds for a closed, convex solid; an open
    net has no "far side" to hide anything, so culling by orientation
    alone can wrongly hide faces that are genuinely visible (e.g. from
    inside the open side, looking at faces that would be interior in the
    closed original).

    Endpoint identity is decided by _cluster_point_ids' real distance
    check, not by independently rounding each point to a tol-sized grid
    (`round(x / tol)`) -- two points within `tol` of each other but on
    opposite sides of a rounding-grid boundary would otherwise round to
    DIFFERENT buckets and wrongly count as two unmatched edges. Confirmed
    to actually happen on data/input/nets/icosahedron.json: 4 of its 32
    edges had endpoints straddling a grid boundary this way, making a
    genuinely closed icosahedron incorrectly report is_closed_solid=False."""
    fids = list(verts3d.keys())
    all_points = [p for fid in fids for p in verts3d[fid]]
    cluster_ids = _cluster_point_ids(all_points, tol)

    edge_count = {}
    offset = 0
    for fid in fids:
        k = len(verts3d[fid])
        ids = cluster_ids[offset:offset + k]
        offset += k
        for i in range(k):
            key = frozenset((ids[i], ids[(i + 1) % k]))
            edge_count[key] = edge_count.get(key, 0) + 1
    return all(count == 2 for count in edge_count.values())


def distinct_vertices(verts3d, tol=1e-4):
    """Merge the (possibly many, per-face-corner) points in a folded
    vertex dict into the solid's actual distinct 3D vertices, by
    transitively clustering points within `tol` of each other."""
    pts = [p for arr in verts3d.values() for p in arr]
    cluster_ids = _cluster_point_ids(pts, tol)

    clusters = defaultdict(list)
    for i, cid in enumerate(cluster_ids):
        clusters[cid].append(pts[i])
    return [np.mean(c, axis=0) for c in clusters.values()]


def fold_transforms(net, root, hinges, fold_angles, t, fold_signs=None):
    """Return dict face_id -> 4x4 np.ndarray: each face's cumulative
    affine transform at fold progress t in [0, 1], mapping that face's
    own flat (net-space, z=0) points to their 3D position at t. This IS
    the "path" of the unfolding -- evaluate at any t to get that face's
    placement; t=0 gives every non-root face's transform as pure
    rotation-in-progress from flat, t=1 the fully folded pose.

    fold_angles: dict child_face_id -> target rotation-from-flat, radians
                 (e.g. pi/2 for a right-angle fold like a cube).
    fold_signs:  optional dict child_face_id -> +1/-1 to flip fold direction.

    Root gets the identity (it never moves). For a non-root face, a
    nested hinge's axis is the PARENT's own flat edge
    (net.faces[parent][pi]) mapped through the parent's already-computed
    transform -- physically, the shared edge moves wherever the parent
    face has already rotated to, which is exactly why hinges must be
    processed in BFS order (each parent's transform is ready before its
    children's hinges use it)."""
    fold_signs = fold_signs or {}
    transforms = {root: np.eye(4)}
    for h in hinges:
        parent, child = h["parent"], h["child"]
        pi = h["parent_edge_idx"]
        pts_parent = net.faces[parent]
        p1 = np.array([*pts_parent[pi], 0.0, 1.0])
        p2 = np.array([*pts_parent[(pi + 1) % len(pts_parent)], 0.0, 1.0])

        M_parent = transforms[parent]
        axis_point = (M_parent @ p1)[:3]
        axis_dir = M_parent[:3, :3] @ (p2 - p1)[:3]

        sign = fold_signs.get(child, 1)
        angle = fold_angles.get(child, np.pi / 2) * t * sign

        transforms[child] = hinge_transform(axis_point, axis_dir, angle) @ M_parent
    return transforms


def fold(net, root, hinges, fold_angles, t, fold_signs=None):
    """Return dict face_id -> (N,3) np.array of folded 3D coordinates,
    at fold progress t in [0, 1] -- each face's own flat points run
    through its fold_transforms() matrix."""
    transforms = fold_transforms(net, root, hinges, fold_angles, t, fold_signs)
    result = {}
    for fid, pts2d in net.faces.items():
        pts_h = np.array([[x, y, 0.0, 1.0] for x, y in pts2d])
        result[fid] = (pts_h @ transforms[fid].T)[:, :3]
    return result


def cluster_faces_into_mesh(verts3d, tol=1e-4):
    """Turn a fold()-shaped dict (face_id -> per-face-corner 3D points,
    with the same corner potentially duplicated once per adjacent face)
    into a proper indexed mesh: (vertices, faces) where vertices is a
    list of distinct 3D positions and faces is a list of vertex-index
    tuples, one per face_id in ascending order, CCW as fold() already
    produces them. Reuses _cluster_point_ids (the same real-distance
    union-find is_closed_solid/distinct_vertices use) so this is the
    ONE place float-tolerance merging happens when building a
    model.Polyhedron -- once vertices are indices, is_closed/edges on
    the resulting Polyhedron are pure integer combinatorics."""
    fids = sorted(verts3d)
    all_points = [p for fid in fids for p in verts3d[fid]]
    cluster_ids = _cluster_point_ids(all_points, tol)

    clusters = defaultdict(list)
    for cid, p in zip(cluster_ids, all_points):
        clusters[cid].append(p)
    index_of_cluster = {cid: i for i, cid in enumerate(clusters)}
    vertices = [np.mean(clusters[cid], axis=0) for cid in clusters]

    faces = []
    offset = 0
    for fid in fids:
        k = len(verts3d[fid])
        face_ids = cluster_ids[offset:offset + k]
        offset += k
        faces.append(tuple(index_of_cluster[cid] for cid in face_ids))

    return vertices, faces
