"""Fine triangle mesh generation for regular n-gons (n = 3..8), aimed at
a later fabric/cloth simulation: each face needs enough points spread
evenly across it for realistic stretching, not just a handful of large
triangles.

Two-stage, both hardcoded/closed-form (no runtime search or meshing
library, so this stays cheap even redrawn on every UI toggle):

1. `SUBDIVISIONS` -- a coarse split of each n-gon into a handful of
   triangles, using the polygon's own vertices plus its centroid as the
   only extra point: n=3 is already a triangle (no centroid needed); n=4
   through n=8 all use a centroid fan (n congruent isoceles triangles,
   exactly equilateral at n=6, since the fan's apex angle is 360/n).
   A centroid fan gives every corner of every face exactly one spoke
   edge to that face's own centroid, so a polyhedron built from
   congruent faces (any Platonic solid) gets the same mesh valence
   increase at every corner, symmetric by construction -- unlike a
   diagonal split, which would leave some corners weaker than others.

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

`resolution_for` picks a PER-N-GON resolution so that every n-gon's fine
triangles end up roughly the same SIZE for a given nominal resolution --
without it, using the same literal `resolution` for every n-gon (as an
earlier version of this module did) makes bigger-sided polygons' fine
triangles coarser than a square's at that same resolution, since
`len(SUBDIVISIONS[n])` (the coarse triangle count) doesn't scale exactly
with a regular n-gon's own area. See its docstring for the formula.

`subdivide_at_level` is a separate, NESTED subdivision scheme (level
0..MAX_LEVEL): unlike `resolution_for`'s per-n-gon-sized scaling, each
level's points/edges are an exact subset of the next level's, since
doubling a barycentric grid's resolution only adds new points, never
moves existing ones. That nesting is what lets a later solver carry a
solved level-k shape forward as level k+1's starting guess instead of
resolving from scratch.
"""
import math

DEFAULT_RESOLUTION = 10

SUBDIVISIONS = {
    3: [(0, 1, 2)],
    4: [(0, 1, "C"), (1, 2, "C"), (2, 3, "C"), (3, 0, "C")],
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


def _regular_polygon_area(n, edge_length=1.0):
    """Area of a regular n-gon with the given edge length -- the standard
    closed form, side_count * side^2 / (4 * tan(pi / side_count))."""
    return (n / 4.0) / math.tan(math.pi / n) * edge_length ** 2


def resolution_for(n, base_resolution, base_n=4):
    """n: polygon side count to solve for; base_resolution/base_n: the
    reference polygon and resolution to match fine-triangle AREA against
    (base_n defaults to the square). Returns the (rounded, >=1) resolution
    for n so subdivide(n, ..., that resolution) gives roughly the same
    triangle size as subdivide(base_n, ..., base_resolution). Not safe to
    use independently for two different-n faces sharing an edge -- see
    mesh_subdivide.subdivide_mesh for how that's enforced."""
    base_triangle_area = _regular_polygon_area(base_n) / len(SUBDIVISIONS[base_n])
    target_fine_area = base_triangle_area / base_resolution ** 2
    triangle_area = _regular_polygon_area(n) / len(SUBDIVISIONS[n])
    return max(1, round(math.sqrt(triangle_area / target_fine_area)))


def _subdivide_triangle(a, b, c, resolution):
    """a, b, c: triangle corners (any dimension -- pure vector arithmetic).
    Splits it into resolution**2 small triangles via a regular barycentric
    grid (grid[(i,j)] = (i*a + j*b + k*c)/r for i+j+k==r). Returns a list
    of (corner, corner, corner) small triangles, same winding as input."""
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


MAX_LEVEL = 3

_level_cache = {}


def subdivide_at_level(n, vertices, level):
    """n: polygon side count; vertices: its CCW corners; level: 0..MAX_LEVEL.
    Level 0 is the bare polygon (no triangles); level 1 is SUBDIVISIONS[n];
    each level after that quarters every triangle from the level before
    (resolution 2**(level-1) applied to level 1). Returns (points,
    triangles), same shape as subdivide(). Each level's points/edges are
    an exact subset of the next level's (see module docstring), and
    results are cached by (n, level, vertices)."""
    if not (0 <= level <= MAX_LEVEL):
        raise ValueError(f"level must be between 0 and {MAX_LEVEL}, got {level}")

    key = (n, level, tuple((round(x, 9), round(y, 9)) for x, y in vertices))
    cached = _level_cache.get(key)
    if cached is not None:
        points, triangles = cached
        return list(points), list(triangles)

    if level == 0:
        points, triangles = list(vertices), []
    else:
        points, triangles = subdivide(n, vertices, resolution=2 ** (level - 1))

    _level_cache[key] = (list(points), list(triangles))
    return points, triangles


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
