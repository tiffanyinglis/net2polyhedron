import numpy as np

from net_fold_utils.polygon_geom import regular_polygon_vertices
from subdivision_utils import SUBDIVISIONS, subdivide


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


def test_mesh_triangle_sizes_stay_within_2x_of_each_other_across_ngons():
    # Not exactly equal by design (see subdivision_utils/subdivisions.py),
    # but should stay in the same ballpark across all six n-gons.
    resolution = 10
    all_areas = []
    for n in SUBDIVISIONS:
        verts = regular_polygon_vertices(n)
        points, triangles = subdivide(n, verts, resolution=resolution)
        all_areas.extend(mesh_triangle_areas(points, triangles))
    assert max(all_areas) / min(all_areas) < 2.0
