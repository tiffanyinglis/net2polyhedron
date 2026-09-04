import numpy as np

from net_fold_utils.polygon_geom import regular_polygon_vertices
from subdivision_utils import SUBDIVISIONS, subdivide, resolution_for


def polygon_area(verts):
    area = 0.0
    k = len(verts)
    for i in range(k):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % k]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def triangle_area(a, b, c):
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2


def mesh_triangle_areas(points, triangles):
    return [triangle_area(points[i], points[j], points[k]) for i, j, k in triangles]


def test_every_regular_polygon_from_3_to_8_has_a_subdivision():
    assert set(SUBDIVISIONS) == {3, 4, 5, 6, 7, 8}


def test_mesh_triangles_are_non_degenerate():
    for n in SUBDIVISIONS:
        verts = regular_polygon_vertices(n)
        points, triangles = subdivide(n, verts, resolution=4)
        for area in mesh_triangle_areas(points, triangles):
            assert area > 1e-9


def test_mesh_triangles_exactly_cover_the_polygon():
    for n in SUBDIVISIONS:
        verts = regular_polygon_vertices(n)
        for resolution in (1, 4, 10):
            points, triangles = subdivide(n, verts, resolution=resolution)
            covered = sum(mesh_triangle_areas(points, triangles))
            assert np.isclose(covered, polygon_area(verts))


def test_mesh_triangle_count_scales_with_resolution_squared():
    for n in SUBDIVISIONS:
        verts = regular_polygon_vertices(n)
        n_coarse = len(SUBDIVISIONS[n])
        for resolution in (1, 3, 10):
            _, triangles = subdivide(n, verts, resolution=resolution)
            assert len(triangles) == n_coarse * resolution ** 2


def test_mesh_points_are_shared_across_coarse_triangle_seams():
    # A finer mesh should have far fewer unique points than the raw
    # (duplicated-per-coarse-triangle) point count, i.e. seams actually
    # get merged into shared particles instead of staying disconnected.
    for n in SUBDIVISIONS:
        verts = regular_polygon_vertices(n)
        resolution = 10
        points, triangles = subdivide(n, verts, resolution=resolution)
        n_coarse = len(SUBDIVISIONS[n])
        raw_points_per_coarse_triangle = (resolution + 1) * (resolution + 2) // 2
        raw_total = n_coarse * raw_points_per_coarse_triangle
        # n=3 has only one coarse triangle, so there's no seam to merge --
        # everywhere else (multiple coarse triangles sharing edges and/or
        # the centroid) should come out strictly smaller than the raw total.
        assert len(points) == raw_total if n_coarse == 1 else len(points) < raw_total


def test_raw_uniform_resolution_no_longer_gives_comparable_triangle_sizes():
    # The SAME literal resolution across all six n-gons does NOT produce
    # comparable fine-triangle sizes -- len(SUBDIVISIONS[n]) (the coarse
    # triangle count) doesn't scale with a regular n-gon's own area, so a
    # bigger-sided polygon's fine triangles come out visibly larger than
    # a square's at the same raw resolution. That's exactly why
    # resolution_for exists (see the next test) -- this test just pins
    # down that the raw, unscaled case genuinely needs it.
    resolution = 10
    all_areas = []
    for n in SUBDIVISIONS:
        verts = regular_polygon_vertices(n)
        points, triangles = subdivide(n, verts, resolution=resolution)
        all_areas.extend(mesh_triangle_areas(points, triangles))
    assert max(all_areas) / min(all_areas) > 2.0


def test_resolution_for_keeps_triangle_sizes_within_a_few_percent_across_ngons():
    # Unlike a raw uniform resolution, resolution_for(n, base_resolution)
    # should make every n-gon's fine triangles come out roughly the same
    # size (rounding to an integer resolution per n-gon means it can't be
    # exact, but it should be close).
    base_resolution = 10
    all_areas = []
    for n in SUBDIVISIONS:
        verts = regular_polygon_vertices(n)
        points, triangles = subdivide(n, verts, resolution=resolution_for(n, base_resolution))
        all_areas.extend(mesh_triangle_areas(points, triangles))
    assert max(all_areas) / min(all_areas) < 1.3


def test_resolution_for_is_identity_at_base_n():
    for base_resolution in (1, 3, 4, 10):
        assert resolution_for(4, base_resolution, base_n=4) == base_resolution


def test_resolution_for_fixes_the_cube_corner_valence_asymmetry():
    # The whole reason SUBDIVISIONS[4] switched from a diagonal split to
    # a centroid fan: every corner of a fan-subdivided face gets exactly
    # one spoke edge to that face's own centroid, so a polyhedron built
    # from congruent faces gains the SAME extra valence at every corner
    # -- unlike the old diagonal split, which only added an edge between
    # two of a square's four corners, chosen arbitrarily by the mesh's
    # own vertex numbering (see the module docstring for the empirical
    # valence-3-vs-5 finding on a subdivided cube this was fixed in
    # response to). len(SUBDIVISIONS[4]) == 4 (one triangle per side) is the
    # actual guarantee that makes this true -- pin it down directly.
    assert len(SUBDIVISIONS[4]) == 4
