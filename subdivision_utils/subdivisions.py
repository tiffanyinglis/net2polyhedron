"""Fine triangle mesh generation for regular n-gons (n = 3..8), aimed at
a later fabric/cloth simulation: each face needs enough points spread
evenly across it for realistic stretching, not just a handful of large
triangles.

Two-stage, both hardcoded/closed-form (no runtime search or meshing
library, so this stays cheap even redrawn on every UI toggle):

1. `SUBDIVISIONS` -- a coarse split of each n-gon into a handful of
   triangles, using the polygon's own vertices plus its centroid as the
   only extra point. As close to equilateral as an n-gon's vertex count
   allows: n=3 is already a triangle; n=4 uses a diagonal split (two
   45-45-90 triangles -- the most regular split possible with only 2
   pieces); n=5..8 use a centroid fan (n congruent isoceles triangles,
   exactly equilateral at n=6, since the fan's apex angle is 360/n).
   Coarse triangle counts (1, 2, 5, 6, 7, 8) were picked so their sizes
   stay within about 1.5x of each other across all six n-gons (they all
   share an edge length), rather than growing with n unchecked.
2. `_subdivide_triangle` -- splits each coarse triangle into
   `resolution ** 2` small ones via a regular barycentric grid (the
   standard geodesic/icosphere-style refinement): every small triangle
   is a scaled copy of the coarse one it sits inside, so a mesh this way
   stays as regular as its coarse triangle was, just finer. `subdivide`
   runs this over every coarse triangle and merges the results into one
   mesh -- points shared between adjacent coarse triangles (every
   internal seam, including the centroid) land on bit-for-bit identical
   barycentric coordinates and so get merged into a single shared point
   rather than staying as disconnected duplicates, which matters once
   this mesh feeds a spring/particle simulation: a seam has to be one
   particle, not two coincident ones that can drift apart.
"""

DEFAULT_RESOLUTION = 10

SUBDIVISIONS = {
    3: [(0, 1, 2)],
    4: [(0, 1, 2), (0, 2, 3)],
    5: [(0, 1, "C"), (1, 2, "C"), (2, 3, "C"), (3, 4, "C"), (4, 0, "C")],
    6: [(0, 1, "C"), (1, 2, "C"), (2, 3, "C"), (3, 4, "C"), (4, 5, "C"),
        (5, 0, "C")],
    7: [(0, 1, "C"), (1, 2, "C"), (2, 3, "C"), (3, 4, "C"), (4, 5, "C"),
        (5, 6, "C"), (6, 0, "C")],
    8: [(0, 1, "C"), (1, 2, "C"), (2, 3, "C"), (3, 4, "C"), (4, 5, "C"),
        (5, 6, "C"), (6, 7, "C"), (7, 0, "C")],
}


def _resolve(ref, vertices, centroid):
    return centroid if ref == "C" else vertices[ref]


def _subdivide_triangle(a, b, c, resolution):
    """Split triangle (a, b, c) into resolution**2 small triangles via a
    regular barycentric grid: grid[(i, j)] = (i*a + j*b + k*c) / r for
    every i, j, k >= 0 with i + j + k == r, i.e. (r+1)(r+2)/2 points.
    Each unit cell of the grid is either one "upward" triangle (always
    present) or an upward/downward pair (where a neighboring cell still
    fits within the i+j<=r boundary), which is what tiles the grid into
    exactly r**2 same-orientation-as-the-original small triangles."""
    r = resolution
    grid = {(i, j): (i * a + j * b + (r - i - j) * c) / r
            for i in range(r + 1) for j in range(r + 1 - i)}
    triangles = []
    for i in range(r):
        for j in range(r - i):
            triangles.append((grid[(i, j)], grid[(i + 1, j)], grid[(i, j + 1)]))
            if j < r - i - 1:
                triangles.append((grid[(i + 1, j)], grid[(i + 1, j + 1)], grid[(i, j + 1)]))
    return triangles


def subdivide(n, vertices, resolution=DEFAULT_RESOLUTION):
    """Build a fine triangular mesh for a regular n-gon (given its CCW
    vertex list, e.g. from polygon_geom.regular_polygon_vertices).

    Returns (points, triangles): `points` a list of unique 2D vertex
    coordinates, `triangles` a list of (i, j, k) index triples into
    `points`, each edge length roughly 1/resolution of the polygon's
    own edge length."""
    if n not in SUBDIVISIONS:
        raise ValueError(f"no hardcoded subdivision for a {n}-gon")
    centroid = sum(vertices) / len(vertices)

    points = []
    index_of = {}

    def point_index(p):
        key = (round(p[0], 9), round(p[1], 9))
        idx = index_of.get(key)
        if idx is None:
            idx = len(points)
            index_of[key] = idx
            points.append(p)
        return idx

    triangles = []
    for tri in SUBDIVISIONS[n]:
        a, b, c = (_resolve(ref, vertices, centroid) for ref in tri)
        for pa, pb, pc in _subdivide_triangle(a, b, c, resolution):
            triangles.append((point_index(pa), point_index(pb), point_index(pc)))

    return points, triangles
