import os

import numpy as np
import pytest

from net_fold_utils import fold_cache

TETRA_POLY = """# Tetra
FACES
3
3
3
3

ROOT 0

NET
0 1
0 2
0 3

EXTRA
1 2
1 3
2 3
"""

# Same combinatorics, different bytes (trailing whitespace) -> different checksum
TETRA_POLY_TOUCHED = TETRA_POLY + "\n"

# Structurally broken: missing an EXTRA edge, so a face's degree no longer
# matches its edge count -- EdgeMap will reject it.
TETRA_POLY_BROKEN = TETRA_POLY.replace("1 2\n1 3\n2 3\n", "1 2\n")


def _make_net_dir(tmp_path, content, filename="tetra.poly"):
    nets_dir = tmp_path / "nets"
    nets_dir.mkdir(exist_ok=True)
    poly_path = nets_dir / filename
    poly_path.write_text(content)
    return str(poly_path)


def test_is_cached_false_before_any_solve(tmp_path):
    poly_path = _make_net_dir(tmp_path, TETRA_POLY)
    assert fold_cache.is_cached(poly_path) is False


def test_load_with_cache_solves_once_then_reuses(tmp_path, monkeypatch):
    poly_path = _make_net_dir(tmp_path, TETRA_POLY)

    net, root, hinges, fold_angles, name = fold_cache.load_with_cache(poly_path)
    assert os.path.exists(fold_cache.cache_path_for(poly_path))
    assert fold_cache.is_cached(poly_path) is True

    def _boom(*a, **k):
        raise AssertionError("should not re-solve a valid cache")

    monkeypatch.setattr(fold_cache, "load_polyhedron_net", _boom)
    # this must succeed by reading the cache, NOT by calling the (now
    # exploding) solver
    _, _, _, cached_angles, _ = fold_cache.load_with_cache(poly_path)
    assert set(cached_angles) == set(fold_angles)
    for k in fold_angles:
        assert np.isclose(cached_angles[k], fold_angles[k], atol=1e-4)


def test_editing_the_source_invalidates_the_cache(tmp_path):
    poly_path = _make_net_dir(tmp_path, TETRA_POLY)
    fold_cache.load_with_cache(poly_path)
    first_checksum = fold_cache.source_checksum(poly_path)

    with open(poly_path, "w") as f:
        f.write(TETRA_POLY_TOUCHED)
    second_checksum = fold_cache.source_checksum(poly_path)
    assert second_checksum != first_checksum
    assert fold_cache.is_cached(poly_path) is False

    fold_cache.load_with_cache(poly_path)  # re-solves and refreshes the cache
    assert fold_cache.is_cached(poly_path) is True


def test_build_all_deletes_stale_cache_on_failed_resolve(tmp_path):
    poly_path = _make_net_dir(tmp_path, TETRA_POLY)
    fold_cache.load_with_cache(poly_path)
    cache_path = fold_cache.cache_path_for(poly_path)
    assert os.path.exists(cache_path)

    with open(poly_path, "w") as f:
        f.write(TETRA_POLY_BROKEN)

    results = fold_cache.build_all(os.path.dirname(poly_path))
    assert len(results) == 1
    path, ok, message = results[0]
    assert ok is False
    assert not os.path.exists(cache_path)  # stale cache must not survive the failure


def test_build_all_skips_up_to_date_nets(tmp_path):
    poly_path = _make_net_dir(tmp_path, TETRA_POLY)
    fold_cache.load_with_cache(poly_path)  # pre-warm the cache

    events = []
    results = fold_cache.build_all(os.path.dirname(poly_path),
                                    on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["skip"]
    assert results == [(poly_path, True, "up to date")]


def test_build_all_force_resolves_even_when_cached(tmp_path):
    poly_path = _make_net_dir(tmp_path, TETRA_POLY)
    fold_cache.load_with_cache(poly_path)

    events = []
    fold_cache.build_all(os.path.dirname(poly_path), force=True,
                          on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["start", "done"]
