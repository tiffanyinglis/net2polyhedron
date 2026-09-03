import pytest

from net_fold_utils.polyhedron_spec import load_polyhedron_spec, write_polyhedron_spec

DEGREES = [3, 3, 3, 3]
NET_EDGES = [(0, 1), (0, 2), (0, 3)]
EXTRA_EDGES = [(1, 2), (1, 3), (2, 3)]


def test_write_then_load_round_trips(tmp_path):
    path = tmp_path / "tetra.poly"
    write_polyhedron_spec(str(path), DEGREES, NET_EDGES, EXTRA_EDGES, root=0, name="Tetra")

    degrees, net_edges, extra_edges, root, name = load_polyhedron_spec(str(path))
    assert degrees == DEGREES
    assert net_edges == NET_EDGES
    assert extra_edges == EXTRA_EDGES
    assert root == 0
    assert name == "Tetra"


def test_missing_name_falls_back_to_path(tmp_path):
    path = tmp_path / "unnamed.poly"
    write_polyhedron_spec(str(path), DEGREES, NET_EDGES, EXTRA_EDGES, root=0)
    *_, name = load_polyhedron_spec(str(path))
    assert name == str(path)


def test_wrong_net_edge_count_is_rejected(tmp_path):
    path = tmp_path / "bad.poly"
    path.write_text("FACES\n3\n3\n3\n3\n\nROOT 0\n\nNET\n0 1\n\nEXTRA\n1 2\n")
    with pytest.raises(ValueError, match="spanning tree"):
        load_polyhedron_spec(str(path))


def test_line_outside_any_section_is_rejected(tmp_path):
    path = tmp_path / "bad.poly"
    path.write_text("3 4\nFACES\n3\n")
    with pytest.raises(ValueError, match="outside any section"):
        load_polyhedron_spec(str(path))
