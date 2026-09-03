import json

import pytest

from net_fold_utils.polyhedron_spec import load_polyhedron_spec, write_polyhedron_spec

DEGREES = [3, 3, 3, 3]
NET_EDGES = [(0, 1), (0, 2), (0, 3)]
EXTRA_EDGES = [(1, 2), (1, 3), (2, 3)]


def test_write_then_load_round_trips(tmp_path):
    path = tmp_path / "tetra.json"
    write_polyhedron_spec(str(path), DEGREES, NET_EDGES, EXTRA_EDGES, root=0, name="Tetra")

    degrees, net_edges, extra_edges, hidden_edges, omitted, root, name = \
        load_polyhedron_spec(str(path))
    assert degrees == DEGREES
    assert net_edges == NET_EDGES
    assert extra_edges == EXTRA_EDGES
    assert hidden_edges == []
    assert omitted == set()
    assert root == 0
    assert name == "Tetra"


def test_written_file_is_valid_json(tmp_path):
    path = tmp_path / "tetra.json"
    write_polyhedron_spec(str(path), DEGREES, NET_EDGES, EXTRA_EDGES, root=0, name="Tetra")
    with open(path) as f:
        spec = json.load(f)
    assert spec["name"] == "Tetra"
    assert spec["faces"] == [
        {"id": 0, "sides": 3, "isRoot": True},
        {"id": 1, "sides": 3},
        {"id": 2, "sides": 3},
        {"id": 3, "sides": 3},
    ]
    assert spec["edges"]["net"] == [[0, 1], [0, 2], [0, 3]]
    assert spec["edges"]["extra"] == [[1, 2], [1, 3], [2, 3]]


def test_nonzero_root_round_trips(tmp_path):
    path = tmp_path / "tetra.json"
    write_polyhedron_spec(str(path), DEGREES, [(2, 0), (2, 1), (2, 3)],
                           [(0, 1), (0, 3), (1, 3)], root=2, name="Tetra")
    with open(path) as f:
        spec = json.load(f)
    assert [f.get("isRoot", False) for f in spec["faces"]] == [False, False, True, False]

    *_, root, _ = load_polyhedron_spec(str(path))
    assert root == 2


def test_missing_name_falls_back_to_path(tmp_path):
    path = tmp_path / "unnamed.json"
    write_polyhedron_spec(str(path), DEGREES, NET_EDGES, EXTRA_EDGES, root=0)
    *_, name = load_polyhedron_spec(str(path))
    assert name == str(path)


def test_no_isroot_face_defaults_to_face_0(tmp_path):
    path = tmp_path / "noroot.json"
    path.write_text(json.dumps({
        "faces": [{"id": i, "sides": 3} for i in range(4)],
        "edges": {"net": [[0, 1], [0, 2], [0, 3]], "extra": [[1, 2], [1, 3], [2, 3]]},
    }))
    *_, root, _ = load_polyhedron_spec(str(path))
    assert root == 0


def test_multiple_isroot_faces_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "faces": [{"id": 0, "sides": 3, "isRoot": True},
                  {"id": 1, "sides": 3, "isRoot": True},
                  {"id": 2, "sides": 3},
                  {"id": 3, "sides": 3}],
        "edges": {"net": [[0, 1], [0, 2], [0, 3]], "extra": [[1, 2], [1, 3], [2, 3]]},
    }))
    with pytest.raises(ValueError, match="more than one face marked isRoot"):
        load_polyhedron_spec(str(path))


def test_wrong_net_edge_count_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "faces": [{"id": i, "sides": 3} for i in range(4)],
        "edges": {"net": [[0, 1]], "extra": [[1, 2]]},
    }))
    with pytest.raises(ValueError, match="spanning tree"):
        load_polyhedron_spec(str(path))


def test_face_ids_out_of_order_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "faces": [{"id": 0, "sides": 3}, {"id": 2, "sides": 3}],
        "edges": {"net": [[0, 1]], "extra": []},
    }))
    with pytest.raises(ValueError, match="declared in order"):
        load_polyhedron_spec(str(path))


def test_malformed_json_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json at all")
    with pytest.raises(ValueError):
        load_polyhedron_spec(str(path))


def test_omit_and_hidden_edges_round_trip(tmp_path):
    # A tetrahedron with face 3 omitted: net/extra span only faces 0-2,
    # hidden carries every edge that touches the omitted face.
    path = tmp_path / "open_tetra.json"
    write_polyhedron_spec(str(path), DEGREES, [(0, 1), (0, 2)], [(1, 2)], root=0,
                           name="Open Tetra", omitted={3},
                           hidden_edges=[(0, 3), (1, 3), (2, 3)])

    degrees, net_edges, extra_edges, hidden_edges, omitted, root, name = \
        load_polyhedron_spec(str(path))
    assert degrees == DEGREES
    assert net_edges == [(0, 1), (0, 2)]
    assert extra_edges == [(1, 2)]
    assert hidden_edges == [(0, 3), (1, 3), (2, 3)]
    assert omitted == {3}
    assert root == 0
    assert name == "Open Tetra"


def test_omitted_face_is_marked_in_written_json(tmp_path):
    path = tmp_path / "open_tetra.json"
    write_polyhedron_spec(str(path), DEGREES, [(0, 1), (0, 2)], [(1, 2)], root=0,
                           omitted={3}, hidden_edges=[(0, 3), (1, 3), (2, 3)])
    with open(path) as f:
        spec = json.load(f)
    assert [f.get("omit", False) for f in spec["faces"]] == [False, False, False, True]
    assert spec["edges"]["hidden"] == [[0, 3], [1, 3], [2, 3]]


def test_root_face_cannot_be_omitted(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "faces": [{"id": 0, "sides": 3, "isRoot": True, "omit": True},
                  {"id": 1, "sides": 3}, {"id": 2, "sides": 3}, {"id": 3, "sides": 3}],
        "edges": {"net": [[1, 2], [1, 3]], "extra": [[2, 3]],
                  "hidden": [[0, 1], [0, 2], [0, 3]]},
    }))
    with pytest.raises(ValueError, match="cannot be omitted"):
        load_polyhedron_spec(str(path))


def test_net_edge_count_check_accounts_for_omitted_faces(tmp_path):
    # 4 faces, 1 omitted -> spanning tree over the remaining 3 needs
    # exactly 2 edges, not 3.
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({
        "faces": [{"id": 0, "sides": 3}, {"id": 1, "sides": 3},
                  {"id": 2, "sides": 3}, {"id": 3, "sides": 3, "omit": True}],
        "edges": {"net": [[0, 1], [0, 2], [1, 2]], "extra": [], "hidden": []},
    }))
    with pytest.raises(ValueError, match="spanning tree"):
        load_polyhedron_spec(str(path))
