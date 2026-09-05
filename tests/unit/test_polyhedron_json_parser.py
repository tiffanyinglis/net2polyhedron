import json

import numpy as np
import pytest

from utils.polyhedron_json_parser import load_polyhedron_json, write_polyhedron_json

TETRA_VERTICES = [[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]
TETRA_FACES = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]]


def test_write_then_load_round_trips(tmp_path):
    path = tmp_path / "tetra.json"
    write_polyhedron_json(str(path), TETRA_VERTICES, TETRA_FACES, name="Tetra")

    vertices, faces, name = load_polyhedron_json(str(path))
    assert len(vertices) == 4
    assert np.allclose(vertices, TETRA_VERTICES)
    assert faces == TETRA_FACES
    assert name == "Tetra"


def test_written_file_is_valid_json(tmp_path):
    path = tmp_path / "tetra.json"
    write_polyhedron_json(str(path), TETRA_VERTICES, TETRA_FACES, name="Tetra")
    with open(path) as f:
        spec = json.load(f)
    assert spec["name"] == "Tetra"
    assert len(spec["vertices"]) == 4
    assert spec["faces"] == TETRA_FACES


def test_missing_name_is_none(tmp_path):
    path = tmp_path / "unnamed.json"
    write_polyhedron_json(str(path), TETRA_VERTICES, TETRA_FACES)
    *_, name = load_polyhedron_json(str(path))
    assert name is None


def test_no_vertices_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"vertices": [], "faces": TETRA_FACES}))
    with pytest.raises(ValueError, match="no vertices"):
        load_polyhedron_json(str(path))


def test_no_faces_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"vertices": TETRA_VERTICES, "faces": []}))
    with pytest.raises(ValueError, match="no faces"):
        load_polyhedron_json(str(path))


def test_face_referencing_out_of_range_vertex_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"vertices": TETRA_VERTICES, "faces": [[0, 1, 4]]}))
    with pytest.raises(ValueError, match="vertex 4"):
        load_polyhedron_json(str(path))


def test_malformed_json_is_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json at all")
    with pytest.raises(ValueError):
        load_polyhedron_json(str(path))


def test_open_net_is_just_a_face_subset(tmp_path):
    # An "open" net (see the module docstring) is nothing special -- just
    # a spec whose faces list happens to be a subset.
    path = tmp_path / "open_tetra.json"
    write_polyhedron_json(str(path), TETRA_VERTICES, TETRA_FACES[:3], name="Open Tetra")
    vertices, faces, name = load_polyhedron_json(str(path))
    assert len(faces) == 3
    assert name == "Open Tetra"
