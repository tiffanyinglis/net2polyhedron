"""
Core engine for folding a polygonal net into a 3D solid.

Model:
- A "Net" is a set of flat polygonal faces defined in 2D "net space".
- Faces that share an edge (matching endpoint coordinates) are glued.
- The glue graph must be a TREE (no cycles) -- that's what makes a valid net.
- Folding = walk the tree from a root face; at each hinge, rotate the
  entire subtree beyond that hinge around the 3D line of the shared edge.
"""

import numpy as np
from itertools import combinations
from collections import defaultdict, deque

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


def _rotation_matrix(axis_dir, angle):
    """The 3x3 rotation matrix for `angle` radians about a 3D direction
    (Rodrigues' formula). Split out from rotate_points so fold() can build
    it once per hinge and reuse it across every face in that hinge's
    subtree, instead of rebuilding it per face."""
    axis_dir = axis_dir / np.linalg.norm(axis_dir)
    K = np.array([[0, -axis_dir[2], axis_dir[1]],
                  [axis_dir[2], 0, -axis_dir[0]],
                  [-axis_dir[1], axis_dir[0], 0]])
    return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)


def rotate_points(points, axis_point, axis_dir, angle):
    """Rotate an (N,3) array of points by `angle` radians around the 3D line
    through axis_point with direction axis_dir (Rodrigues' formula)."""
    R = _rotation_matrix(axis_dir, angle)
    return (points - axis_point) @ R.T + axis_point


def _children_map(hinges):
    children = defaultdict(list)
    for h in hinges:
        children[h["parent"]].append(h["child"])
    return children


def _subtree_from_children(children, node):
    members = []
    stack = [node]
    while stack:
        n = stack.pop()
        members.append(n)
        stack.extend(children[n])
    return members


def precompute_subtree_map(hinges):
    """Precompute, once, every hinge's subtree member list (and each
    member's vertex count). The hinge tree's *shape* never changes across
    the many fold() calls a caller like the fold solver makes (only the
    angles/t do), so this lets fold() skip re-deriving it -- pass the
    result back in as fold()'s `subtree_map` argument."""
    children = _children_map(hinges)
    return {h["child"]: _subtree_from_children(children, h["child"]) for h in hinges}


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
    before relying on backface culling (_CullableFace in
    polygon_fold_app.py): that trick's assumption -- a face's own
    orientation alone determines whether the solid's far side hides it
    from the camera -- only holds for a closed, convex solid; an open
    net has no "far side" to hide anything, so culling by orientation
    alone can wrongly hide faces that are genuinely visible (e.g. from
    inside the open side, looking at faces that would be interior in the
    closed original)."""
    edge_count = {}
    for pts in verts3d.values():
        k = len(pts)
        for i in range(k):
            a, b = pts[i], pts[(i + 1) % k]
            key = frozenset((tuple(np.round(a / tol)), tuple(np.round(b / tol))))
            edge_count[key] = edge_count.get(key, 0) + 1
    return all(count == 2 for count in edge_count.values())


def distinct_vertices(verts3d, tol=1e-4):
    """Merge the (possibly many, per-face-corner) points in a folded
    vertex dict into the solid's actual distinct 3D vertices, by
    transitively clustering points within `tol` of each other."""
    pts = [p for arr in verts3d.values() for p in arr]
    n = len(pts)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if np.linalg.norm(pts[i] - pts[j]) < tol:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(pts[i])
    return [np.mean(c, axis=0) for c in clusters.values()]


def fold(net, root, hinges, fold_angles, t, fold_signs=None, subtree_map=None):
    """Return dict face_id -> (N,3) np.array of folded 3D coordinates,
    at fold progress t in [0, 1].

    fold_angles: dict child_face_id -> target rotation-from-flat, radians
                 (e.g. pi/2 for a right-angle fold like a cube).
    fold_signs:  optional dict child_face_id -> +1/-1 to flip fold direction.
    subtree_map: optional, from precompute_subtree_map(hinges) -- since the
                 hinge tree's shape is the same on every call, a caller that
                 folds the same (net, hinges) many times (e.g. the fold
                 solver's inner optimization loop) can compute this once and
                 reuse it, instead of fold() re-deriving it from `hinges` on
                 every single call.
    """
    fold_signs = fold_signs or {}
    verts3d = {fid: np.array([[x, y, 0.0] for x, y in pts])
               for fid, pts in net.faces.items()}

    if subtree_map is None:
        subtree_map = precompute_subtree_map(hinges)

    # BFS order guarantees a parent is fully positioned before its hinge is used
    for h in hinges:
        parent, child = h["parent"], h["child"]
        pi = h["parent_edge_idx"]
        pts_parent = net.faces[parent]

        # find those same two points in the parent's CURRENT (already-rotated) coords
        # by matching against the parent's original 2D layout order/index.
        axis_p1 = verts3d[parent][pi]
        axis_p2 = verts3d[parent][(pi + 1) % len(pts_parent)]

        sign = fold_signs.get(child, 1)
        angle = fold_angles.get(child, np.pi / 2) * t * sign

        # Every face in this hinge's subtree gets the exact same rotation,
        # so build the rotation matrix once and apply it to all of their
        # points in a single batched array op, rather than once per face.
        members = subtree_map[child]
        R = _rotation_matrix(axis_p2 - axis_p1, angle)
        sizes = [len(verts3d[fid]) for fid in members]
        stacked = np.concatenate([verts3d[fid] for fid in members], axis=0)
        rotated = (stacked - axis_p1) @ R.T + axis_p1
        offset = 0
        for fid, size in zip(members, sizes):
            verts3d[fid] = rotated[offset:offset + size]
            offset += size

    return verts3d
