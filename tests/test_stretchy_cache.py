import os

import numpy as np
import pytest

from net_fold_utils import stretchy_cache

TETRA_JSON = """{
  "name": "Tetra",
  "faces": [
    [0, 1, 2],
    [0, 3, 1],
    [1, 3, 2],
    [2, 3, 0]
  ]
}
"""

# Same combinatorics, different bytes (trailing whitespace) -> different checksum
TETRA_JSON_TOUCHED = TETRA_JSON + "\n"

# Structurally broken: drops the last face, so most edges lose their
# reverse-direction partner -- load_stretchy_mesh will reject it.
TETRA_JSON_BROKEN = TETRA_JSON.replace(",\n    [2, 3, 0]\n", "\n")


def _make_net_dir(tmp_path, content, filename="tetra.json"):
    nets_dir = tmp_path / "stretchy_nets"
    nets_dir.mkdir(exist_ok=True)
    net_path = nets_dir / filename
    net_path.write_text(content)
    return str(net_path)


def test_is_cached_false_before_any_solve(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    assert stretchy_cache.is_cached(net_path) is False


def test_load_with_cache_solves_once_then_reuses(tmp_path, monkeypatch):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)

    faces, positions, stats, name = stretchy_cache.load_with_cache(net_path)
    assert os.path.exists(stretchy_cache.cache_path_for(net_path))
    assert stretchy_cache.is_cached(net_path) is True

    def _boom(*a, **k):
        raise AssertionError("should not re-solve a valid cache")

    monkeypatch.setattr(stretchy_cache, "solve_wireframe", _boom)
    # this must succeed by reading the cache, NOT by calling the (now
    # exploding) solver
    _, cached_positions, cached_stats, cached_name = stretchy_cache.load_with_cache(net_path)
    assert cached_name == name
    assert cached_stats == stats
    assert set(cached_positions) == set(positions)
    for vid in positions:
        assert np.allclose(cached_positions[vid], positions[vid], atol=1e-6)


def test_editing_the_source_invalidates_the_cache(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    stretchy_cache.load_with_cache(net_path)
    first_checksum = stretchy_cache.source_checksum(net_path)

    with open(net_path, "w") as f:
        f.write(TETRA_JSON_TOUCHED)
    second_checksum = stretchy_cache.source_checksum(net_path)
    assert second_checksum != first_checksum
    assert stretchy_cache.is_cached(net_path) is False

    stretchy_cache.load_with_cache(net_path)  # re-solves and refreshes the cache
    assert stretchy_cache.is_cached(net_path) is True


def test_build_all_deletes_stale_cache_on_failed_resolve(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    stretchy_cache.load_with_cache(net_path)
    cache_path = stretchy_cache.cache_path_for(net_path)
    assert os.path.exists(cache_path)

    with open(net_path, "w") as f:
        f.write(TETRA_JSON_BROKEN)

    results = stretchy_cache.build_all(os.path.dirname(net_path))
    assert len(results) == 1
    path, ok, message = results[0]
    assert ok is False
    assert not os.path.exists(cache_path)  # stale cache must not survive the failure


def test_build_all_skips_up_to_date_nets(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    stretchy_cache.load_with_cache(net_path)  # pre-warm the cache

    events = []
    results = stretchy_cache.build_all(os.path.dirname(net_path),
                                        on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["skip"]
    assert results == [(net_path, True, "up to date")]


def test_build_all_force_resolves_even_when_cached(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    stretchy_cache.load_with_cache(net_path)

    events = []
    stretchy_cache.build_all(os.path.dirname(net_path), force=True,
                              on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["start", "done"]
