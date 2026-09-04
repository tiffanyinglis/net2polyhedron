"""Turn a coarse stretchy-mesh (vertex-loop faces, see stretchy_mesh.py) into
a fine triangular "fabric" mesh, using the same hardcoded per-n-gon coarse
split (subdivision_utils.SUBDIVISIONS) and barycentric refinement
(subdivision_utils._subdivide_triangle) that polygon_subdivide.py uses to
preview a single polygon's mesh -- applied here to every face of a whole
net at once, with points on a shared coarse edge merged into one global
vertex, so the result is a single connected mesh spanning the whole
polyhedron rather than N disconnected per-face patches.

Motivation: stretchy_mesh.solve_wireframe normally treats each whole
polygon face as a single (at most gently bending) patch -- realistic for
a rigid material, but real fabric flexes and drapes at a much finer scale
than that. Subdivided into many small triangles wired together edge to
edge, the same solve_wireframe machinery instead behaves like a proper
triangulated cloth mesh: each small triangle is always flat (3 points
span a unique plane), but neighboring triangles can fold relative to
each other freely, letting the whole face bend far more than a single
rigid-ish polygon ever could.

WHY THIS DOESN'T JUST CALL solve_wireframe(fine_faces) DIRECTLY: tried
first, and it doesn't scale -- solve_wireframe's random-restart search
(a fresh random 3D point cloud, relaxed by edge length alone, then
inflated) works well for a coarse mesh with a handful of large faces, but
for a mesh of hundreds of small triangles a random start has WAY more
independent ways to fold some tiny triangle inside-out relative to the
whole, so _is_orientation_consistent essentially never passes within the
attempt budget -- verified empirically: a resolution-2 tetrahedron
subdivision (just 16 small triangles) never once reached a consistent
embedding in 30 attempts, at several seconds each.

Instead: solve the UN-subdivided coarse net first (fast, reliable --
solve_wireframe already handles this well), then DRAPE the fine mesh over
that already-correct, already-inflated coarse shape using the exact same
barycentric grid subdivide() uses in 2D, just fed the coarse solve's real
3D corner/centroid positions instead of a flat reference polygon's. This
gives every fine vertex an excellent starting guess for free -- already
properly oriented, already roughly the right overall shape, since it's
built directly from a shape solve_wireframe already validated. Only a
light, single-pass edge-length relaxation (_relax_seed) is needed after
that, to fix up the small discrepancies between the drape's exact rest
lengths and what solve_wireframe's coarse solve actually produced (exact
only where the coarse face landed perfectly flat and unit-length, e.g.
the Platonic solids; a genuinely bent/stretched coarse face like
stretchy_nets/two_pentagons_and_a_square.json needs a bit more).

Unlike solve_wireframe's usual uniform edge_length, a subdivided mesh's
edges do NOT all share one rest length: SUBDIVISIONS' coarse triangles
aren't generally equilateral (e.g. a pentagon's centroid fan has
unit-length rim edges but shorter spoke edges to the centroid), so every
fine edge's target length is read directly off the flat 2D reference
subdivision's own exact coordinates for a regular n-gon of unit edge
length -- correct for every edge regardless of which coarse triangle or
n-gon it came from.
"""
import json

import numpy as np
from scipy.optimize import least_squares

from subdivision_utils.subdivisions import SUBDIVISIONS, _resolve, _subdivide_triangle
from .polygon_geom import regular_polygon_vertices
from .stretchy_mesh import (
    EDGE_LENGTH, mesh_edges, _pair_index_arrays, _residual, solve_wireframe,
)

DEFAULT_RESOLUTION = 3  # kept low: mesh size (and _relax_seed's cost) grows with resolution**2
_POINT_TOL = 1e-7


def _subdivide_dual(n, verts2d, verts3d, resolution):
    """Like subdivision_utils.subdivide(), but (when verts3d is given)
    simultaneously builds a matching list of 3D points -- one per unique
    2D point -- by running the identical barycentric grid construction
    over verts3d/its own centroid instead. _subdivide_triangle is purely
    vector arithmetic (no assumption about dimensionality), and iterates
    in an order that depends only on `resolution`, not the corner values,
    so zipping the 2D and 3D calls pairs up matching points automatically
    without needing to duplicate any of the deduplication logic. Points
    are deduplicated by their 2D key only (verts3d may come from a
    genuinely bent/stretched coarse face, where two combinatorially
    distinct points could otherwise coincide numerically in 3D by
    accident). Returns (points2d, points3d, triangles); points3d is None
    if verts3d is None."""
    centroid2d = sum(verts2d) / len(verts2d)
    centroid3d = sum(verts3d) / len(verts3d) if verts3d is not None else None

    points2d, points3d, index_of = [], [], {}

    def point_index(p2d, p3d):
        key = (round(p2d[0], 9), round(p2d[1], 9))
        idx = index_of.get(key)
        if idx is None:
            idx = len(points2d)
            index_of[key] = idx
            points2d.append(p2d)
            if verts3d is not None:
                points3d.append(p3d)
        return idx

    triangles = []
    for tri in SUBDIVISIONS[n]:
        a2, b2, c2 = (_resolve(ref, verts2d, centroid2d) for ref in tri)
        grid2d = _subdivide_triangle(a2, b2, c2, resolution)
        if verts3d is not None:
            a3, b3, c3 = (_resolve(ref, verts3d, centroid3d) for ref in tri)
            grid3d = _subdivide_triangle(a3, b3, c3, resolution)
        else:
            grid3d = [(None, None, None)] * len(grid2d)
        for (pa2, pb2, pc2), (pa3, pb3, pc3) in zip(grid2d, grid3d):
            triangles.append((point_index(pa2, pa3), point_index(pb2, pb3), point_index(pc2, pc3)))

    return points2d, (points3d if verts3d is not None else None), triangles


def _classify_point(p, verts2d, resolution):
    """Where a subdivided 2D point sits relative to the n-gon's own
    corners: ("corner", i) for polygon corner i, ("edge", i, k) for the
    k-th of resolution-1 interior points along boundary edge (i, i+1),
    counted from corner i (k = 1..resolution-1), or ("interior",) for
    anything else (the centroid, an internal fan/diagonal seam, or a
    point strictly inside a coarse triangle)."""
    n = len(verts2d)
    for i, v in enumerate(verts2d):
        if np.allclose(p, v, atol=_POINT_TOL):
            return ("corner", i)
    for i in range(n):
        a, b = verts2d[i], verts2d[(i + 1) % n]
        d = b - a
        t = float(np.dot(p - a, d) / np.dot(d, d))
        if _POINT_TOL < t < 1 - _POINT_TOL and np.allclose(p, a + t * d, atol=_POINT_TOL):
            k = round(t * resolution)
            if 0 < k < resolution:
                return ("edge", i, k)
    return ("interior",)


def subdivide_mesh(coarse_faces, resolution=DEFAULT_RESOLUTION, coarse_positions=None):
    """Subdivide every face of a coarse vertex-loop mesh into a fine
    triangular mesh, merging points shared across coarse edges into
    single global vertices.

    If `coarse_positions` (a {vertex_id: 3D point} dict, e.g. from
    stretchy_mesh.solve_wireframe on the SAME coarse_faces) is given, also
    computes a 3D seed position for every fine vertex by draping the
    subdivision over those real 3D positions (see module docstring) --
    otherwise seed_positions is None.

    Returns (fine_faces, face_of_fine, edge_lengths, seed_positions):
      fine_faces     -- list of (a, b, c) global-vertex-id triangles, CCW
                        (same winding as the coarse face they came from).
      face_of_fine   -- fine_faces[i] belongs to coarse face
                        face_of_fine[i] (e.g. for coloring every fine
                        triangle by the original face it subdivides).
      edge_lengths   -- {(a, b): length} for a < b, for every undirected
                        edge in fine_faces -- the rest length that edge
                        should hold in a physically-accurate fabric of
                        unit-edge coarse faces (NOT uniform across the
                        mesh, see module docstring).
      seed_positions -- {vertex_id: np.array([x, y, z])} or None.
    """
    next_id = 1 + max(v for face in coarse_faces for v in face)
    edge_chain = {}  # (lo, hi) coarse vertex ids -> [resolution-1 new global ids], ordered lo->hi
    fine_faces = []
    face_of_fine = []
    edge_lengths = {}
    seed_positions = {} if coarse_positions is not None else None

    for face_idx, face in enumerate(coarse_faces):
        n = len(face)
        verts2d = regular_polygon_vertices(n)
        verts3d = [coarse_positions[v] for v in face] if coarse_positions is not None else None
        points2d, points3d, triangles = _subdivide_dual(n, verts2d, verts3d, resolution)

        local_to_global = [None] * len(points2d)
        for li, p in enumerate(points2d):
            kind, *rest = _classify_point(p, verts2d, resolution)
            if kind == "corner":
                gid = face[rest[0]]
            elif kind == "edge":
                i, k = rest
                a, b = face[i], face[(i + 1) % n]
                lo, hi = (a, b) if a < b else (b, a)
                chain = edge_chain.get((lo, hi))
                if chain is None:
                    chain = list(range(next_id, next_id + resolution - 1))
                    next_id += resolution - 1
                    edge_chain[(lo, hi)] = chain
                pos_from_lo = k if a == lo else resolution - k
                gid = chain[pos_from_lo - 1]
            else:
                gid = next_id
                next_id += 1
            local_to_global[li] = gid
            if seed_positions is not None and gid not in seed_positions:
                seed_positions[gid] = points3d[li]

        for tri in triangles:
            g = tuple(local_to_global[i] for i in tri)
            fine_faces.append(g)
            face_of_fine.append(face_idx)
            for a in range(3):
                b = (a + 1) % 3
                la, lb = tri[a], tri[b]
                ga, gb = g[a], g[b]
                lo, hi = (ga, gb) if ga < gb else (gb, ga)
                if (lo, hi) not in edge_lengths:
                    edge_lengths[(lo, hi)] = float(np.linalg.norm(points2d[la] - points2d[lb]))

    return fine_faces, face_of_fine, edge_lengths, seed_positions


def _relax_seed(fine_faces, edge_lengths, seed_positions):
    """A single light edge-length least_squares fit starting from
    seed_positions -- NOT the full solve_wireframe search (no random
    restarts, no inflation ramp, no orientation-consistency retries):
    the seed is already properly oriented and already close to every
    fine edge's rest length (see module docstring), so this only needs
    to iron out the small discrepancies left by draping possibly-bent
    coarse faces, not find an embedding from scratch."""
    vertex_ids = sorted({v for face in fine_faces for v in face})
    idx = {v: i for i, v in enumerate(vertex_ids)}
    edges = mesh_edges(fine_faces)
    edge_ai, edge_bi = _pair_index_arrays(edges, idx)
    length_arr = np.array([edge_lengths[e] for e in edges])

    pts0 = np.array([seed_positions[v] for v in vertex_ids])
    # volume_indices/planarity_groups are unused at zero inflation/planarity
    # weight (both default to 0.0 below), so there's nothing to precompute.
    sol = least_squares(_residual, pts0.flatten(), args=(edge_ai, edge_bi, None, None, length_arr))
    pts = sol.x.reshape(-1, 3)
    positions = {v: pts[i] for i, v in enumerate(vertex_ids)}

    lengths = np.array([np.linalg.norm(positions[a] - positions[b]) for a, b in edges])
    stretch_pct = 100 * (lengths - length_arr) / length_arr
    stats = dict(residual=float(np.max(np.abs(sol.fun[:len(edges)]))),
                 max_stretch_pct=float(np.max(np.abs(stretch_pct))),
                 rms_stretch_pct=float(np.sqrt(np.mean(stretch_pct ** 2))))
    return positions, stats


def load_fabric_spec(path):
    """If `path` is a fabric-subdivided stretchy net -- one written by
    tools/generate_subdivided_stretchy_nets.py, carrying the extra
    "coarse_faces"/"resolution"/"face_of_fine" fields alongside the
    ordinary "faces" -- returns (coarse_faces, resolution, face_of_fine).
    Otherwise (an ordinary stretchy_nets/*.json with no "coarse_faces")
    returns (None, None, None).

    net_fold_utils.stretchy_cache uses this to solve a fabric net via
    solve_fabric_mesh (which reproduces the coarse net's own correct,
    rounded shape, colorable by original face) instead of plain
    solve_wireframe(faces) at a uniform edge length -- tried directly on
    a fine mesh, that either takes a very long time (the random-restart
    search struggles badly with hundreds of small triangles) or, worse,
    settles into a generically-inflated rounded blob that doesn't
    resemble the source polyhedron at all, since forcing every edge
    (rim, diagonal, spoke -- see this module's docstring) to the same
    length erases the shape information those different lengths encode.
    stretchy_polyhedron_init.py uses `coarse_faces`/`face_of_fine` again
    at render time: the left panel shows the COARSE polygons (with a
    faint subdivision overlay) instead of hundreds of individual fine
    triangles, and every fine triangle in the right panel is colored by
    its ORIGINAL coarse face via `face_of_fine`."""
    with open(path) as f:
        spec = json.load(f)
    coarse_faces = spec.get("coarse_faces")
    if not coarse_faces:
        return None, None, None
    return coarse_faces, spec["resolution"], spec["face_of_fine"]


def solve_fabric_mesh(coarse_faces, resolution=DEFAULT_RESOLUTION, seed=0):
    """Solve the coarse net (stretchy_mesh.solve_wireframe, unmodified),
    then drape a fine fabric mesh over that solved shape and lightly
    relax it (see module docstring for why this drape-then-relax approach
    is used instead of solve_wireframe(fine_faces) directly).

    Returns (fine_faces, face_of_fine, positions, stats) -- the first two
    as from subdivide_mesh, the last two describing the RELAXED fine mesh
    (positions is {vertex_id: np.array([x, y, z])}, stats has
    "max_stretch_pct"/"rms_stretch_pct"/"residual", same shape as
    solve_wireframe's)."""
    coarse_positions, _ = solve_wireframe(coarse_faces, edge_length=EDGE_LENGTH, seed=seed)
    fine_faces, face_of_fine, edge_lengths, seed_positions = subdivide_mesh(
        coarse_faces, resolution, coarse_positions=coarse_positions)
    positions, stats = _relax_seed(fine_faces, edge_lengths, seed_positions)
    return fine_faces, face_of_fine, positions, stats
