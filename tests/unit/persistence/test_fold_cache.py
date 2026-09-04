import os

import numpy as np
import pytest

from utils.persistence import fold_cache
from utils.model import PolyhedralNet

TETRA_JSON = """{
  "name": "Tetra",
  "faces": [
    {"id": 0, "sides": 3, "isRoot": true},
    {"id": 1, "sides": 3},
    {"id": 2, "sides": 3},
    {"id": 3, "sides": 3}
  ],
  "edges": {
    "net": [
      [0, 1],
      [0, 2],
      [0, 3]
    ],
    "extra": [
      [1, 2],
      [1, 3],
      [2, 3]
    ]
  }
}
"""

# Same combinatorics, different bytes (trailing whitespace) -> different checksum
TETRA_JSON_TOUCHED = TETRA_JSON + "\n"

# Structurally broken: missing two EXTRA edges, so a face's degree no longer
# matches its edge count -- EdgeMap will reject it.
TETRA_JSON_BROKEN = TETRA_JSON.replace(
    '    "extra": [\n      [1, 2],\n      [1, 3],\n      [2, 3]\n    ]',
    '    "extra": [\n      [1, 2]\n    ]')


def _make_net_dir(tmp_path, content, filename="tetra.json"):
    nets_dir = tmp_path / "nets"
    nets_dir.mkdir(exist_ok=True)
    net_path = nets_dir / filename
    net_path.write_text(content)
    return str(net_path)


def test_is_cached_false_before_any_solve(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    assert fold_cache.is_cached(net_path) is False


def test_load_solves_once_then_reuses(tmp_path, monkeypatch):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)

    net = PolyhedralNet.load(net_path)
    fold_angles = net.fold_angles
    assert os.path.exists(fold_cache.cache_path_for(net_path))
    assert fold_cache.is_cached(net_path) is True

    def _boom(*a, **k):
        raise AssertionError("should not re-solve a valid cache")

    monkeypatch.setattr(PolyhedralNet, "_load_json_uncached", _boom)
    # this must succeed by reading the cache, NOT by calling the (now
    # exploding) solver
    cached_net = PolyhedralNet.load(net_path)
    cached_angles = cached_net.fold_angles
    assert set(cached_angles) == set(fold_angles)
    for k in fold_angles:
        assert np.isclose(cached_angles[k], fold_angles[k], atol=1e-4)


def test_editing_the_source_invalidates_the_cache(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    PolyhedralNet.load(net_path)
    first_checksum = fold_cache.source_checksum(net_path)

    with open(net_path, "w") as f:
        f.write(TETRA_JSON_TOUCHED)
    second_checksum = fold_cache.source_checksum(net_path)
    assert second_checksum != first_checksum
    assert fold_cache.is_cached(net_path) is False

    PolyhedralNet.load(net_path)  # re-solves and refreshes the cache
    assert fold_cache.is_cached(net_path) is True


def test_build_all_deletes_stale_cache_on_failed_resolve(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    PolyhedralNet.load(net_path)
    cache_path = fold_cache.cache_path_for(net_path)
    assert os.path.exists(cache_path)

    with open(net_path, "w") as f:
        f.write(TETRA_JSON_BROKEN)

    results = fold_cache.build_all(os.path.dirname(net_path))
    assert len(results) == 1
    path, ok, message = results[0]
    assert ok is False
    assert not os.path.exists(cache_path)  # stale cache must not survive the failure


def test_build_all_skips_up_to_date_nets(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    PolyhedralNet.load(net_path)  # pre-warm the cache

    events = []
    results = fold_cache.build_all(os.path.dirname(net_path),
                                    on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["skip"]
    assert results == [(net_path, True, "up to date")]


def test_build_all_force_resolves_even_when_cached(tmp_path):
    net_path = _make_net_dir(tmp_path, TETRA_JSON)
    PolyhedralNet.load(net_path)

    events = []
    fold_cache.build_all(os.path.dirname(net_path), force=True,
                          on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["start", "done"]
