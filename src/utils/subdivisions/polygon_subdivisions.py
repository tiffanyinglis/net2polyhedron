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

   n=4 used to be a diagonal split (two 45-45-90 triangles from the
   square's own corners, no centroid) instead of a fan -- "the most
   regular split possible with only 2 pieces", per an earlier version of
   this docstring. That turned out to have a real cost once these
   n-gons are glued edge-to-edge into a whole polyhedron: a diagonal
   split only adds an extra edge between TWO of a square's four corners
   (whichever two the diagonal connects), so a polyhedron built entirely
   out of squares -- a cube -- ends up with two opposite corners at a
   LOWER mesh valence (fewer edges, hence less resistance to stretching)
   than the other six, purely as an accident of which corner each square
   face's diagonal happened to touch. Verified directly on the
   diagonal-split version of data/input/stretchy_nets/cube_res3.json (then
   still named cube_res4.json, at resolution 4 -- regenerated at
   resolution 3 as part of this same fix, see
   generate_subdivided_stretchy_nets.py's comment on why the resolution
   changed too): 2 of the cube's 8 corners
   at valence 3, the other 6 at valence 5 -- invisible at modest
   inflation pressure, but a visibly lopsided bulge at high pressure,
   since the two weaker corners give more than the rest. A centroid fan
   doesn't have this problem: EVERY corner of a fan-subdivided face gets
   exactly one spoke edge to that face's own centroid, so a polyhedron
   built from congruent faces (any Platonic solid) gets the SAME valence
   increase at every one of its corners, symmetric by construction.

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
    """The resolution to use for an n-sided polygon so its fine triangles
    end up roughly the same SIZE as a `base_n`-gon's at `base_resolution`
    -- i.e. so `subdivide(n, ..., resolution_for(n, base_resolution))`'s
    fine triangles have about the same area as
    `subdivide(base_n, ..., base_resolution)`'s, regardless of n.

    Each coarse triangle in SUBDIVISIONS[n] has area
    `_regular_polygon_area(n) / len(SUBDIVISIONS[n])` (they're always
    congruent within one n-gon, by construction -- a fan's slices are
    congruent for a regular polygon, and n=3 is just the one triangle).
    Refining a coarse triangle at some resolution r divides its area by
    r**2, so matching `base_n`'s fine-triangle area means solving
    `coarse_area(n) / r**2 == coarse_area(base_n) / base_resolution**2`
    for r. Rounded to the nearest positive integer, since resolution is
    a literal grid subdivision count, not a continuous quantity.

    `base_n` defaults to 4 (the square) since that's the shape this
    project's own worked examples (data/input/stretchy_nets/cube_res3.json,
    DEFAULT_RESOLUTION in utils/subdivisions/mesh_subdivide.py) are built
    around -- `base_resolution` is the resolution that shape actually
    uses, and every other n-gon is scaled relative to it.

    Not safe to use independently for adjacent faces of DIFFERENT n that
    share an edge (e.g. a pentagon glued to a square): the two faces
    would want different resolutions, but a shared edge needs both sides
    to agree on how many points it's split into. See
    utils.subdivisions.mesh_subdivide.subdivide_mesh's docstring for how
    (and when) that's actually enforced."""
    base_triangle_area = _regular_polygon_area(base_n) / len(SUBDIVISIONS[base_n])
    target_fine_area = base_triangle_area / base_resolution ** 2
    triangle_area = _regular_polygon_area(n) / len(SUBDIVISIONS[n])
    return max(1, round(math.sqrt(triangle_area / target_fine_area)))


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
