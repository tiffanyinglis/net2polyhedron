import os

import numpy as np
import pytest

from utils.net_unfolder import cache as _cache
from utils.net_unfolder import NetUnfolder
from utils.persistence.polyhedron_spec import write_polyhedron_spec

TETRA_VERTICES = [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]
TETRA_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]]


def _make_net_dir(tmp_path, filename="tetra.json"):
    nets_dir = tmp_path / "nets"
    nets_dir.mkdir(exist_ok=True)
    net_path = nets_dir / filename
    write_polyhedron_spec(str(net_path), TETRA_VERTICES, TETRA_FACES, name="Tetra")
    return str(net_path)


def test_is_cached_false_before_any_load(tmp_path):
    net_path = _make_net_dir(tmp_path)
    assert _cache.is_cached(net_path) is False


def test_load_computes_once_then_reuses(tmp_path, monkeypatch):
    net_path = _make_net_dir(tmp_path)

    net = NetUnfolder.load(net_path)
    angles = net.fold_angles
    assert os.path.exists(_cache.cache_path_for(net_path))
    assert _cache.is_cached(net_path) is True

    def _boom(*a, **k):
        raise AssertionError("should not recompute a valid cache")

    monkeypatch.setattr(NetUnfolder, "_compute", classmethod(lambda cls, *a, **k: _boom()))
    # this must succeed by reading the cache, NOT by calling the (now
    # exploding) compute path
    cached_net = NetUnfolder.load(net_path)
    cached_angles = cached_net.fold_angles
    assert set(cached_angles) == set(angles)
    for k in angles:
        assert np.isclose(cached_angles[k], angles[k], atol=1e-4)


def test_editing_the_source_invalidates_the_cache(tmp_path):
    net_path = _make_net_dir(tmp_path)
    NetUnfolder.load(net_path)
    first_checksum = _cache.read_cache(_cache.cache_path_for(net_path))["checksum"]

    write_polyhedron_spec(net_path, TETRA_VERTICES, TETRA_FACES, name="Tetra (edited)")
    second_checksum_data = _cache.read_cache(_cache.cache_path_for(net_path))
    assert second_checksum_data["checksum"] == first_checksum  # stale, not yet refreshed
    assert _cache.is_cached(net_path) is False

    NetUnfolder.load(net_path)  # re-computes and refreshes the cache
    assert _cache.is_cached(net_path) is True


def test_build_all_skips_up_to_date_nets(tmp_path):
    net_path = _make_net_dir(tmp_path)
    NetUnfolder.load(net_path)  # pre-warm the cache

    events = []
    results = _cache.build_all(os.path.dirname(net_path),
                                on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["skip"]
    assert results == [(net_path, True, "up to date")]


def test_build_all_force_recomputes_even_when_cached(tmp_path):
    net_path = _make_net_dir(tmp_path)
    NetUnfolder.load(net_path)

    events = []
    _cache.build_all(os.path.dirname(net_path), force=True,
                      on_progress=lambda i, n, l, s, e=None: events.append(s))
    assert events == ["start", "done"]


def test_build_all_deletes_stale_cache_on_failed_recompute(tmp_path):
    net_path = _make_net_dir(tmp_path)
    NetUnfolder.load(net_path)
    cache_path = _cache.cache_path_for(net_path)
    assert os.path.exists(cache_path)

    # Break the source: a face referencing a vertex that doesn't exist --
    # load_polyhedron_spec rejects this before NetUnfolder ever sees it.
    import json
    with open(net_path, "w") as f:
        json.dump({"vertices": TETRA_VERTICES, "faces": [[0, 1, 99]]}, f)

    results = _cache.build_all(os.path.dirname(net_path))
    assert len(results) == 1
    path, ok, message = results[0]
    assert ok is False
    assert not os.path.exists(cache_path)  # stale cache must not survive the failure
