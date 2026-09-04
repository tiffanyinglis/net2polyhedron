import numpy as np

from utils.model import PolyhedralNet

TETRA_JSON = """{
  "name": "Tetra",
  "faces": [
    {"id": 0, "sides": 3},
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

# Two triangles sharing one edge (face 1's edge, reversed, matches face 0's
# edge 0->1) -- a minimal legacy .txt net, just enough to exercise
# PolyhedralNet._load_legacy_txt's coincident-2D-point hinge derivation.
# No ROOT line: the root is always the first (lowest-id) face declared.
TWO_TRIANGLE_TXT = """# Two Triangles
FACES
0: 0,0 1,0 0.5,0.866025
1: 1,0 0,0 0.5,-0.866025

FOLD 1 90.0
"""


def _write(tmp_path, content, filename):
    path = tmp_path / filename
    path.write_text(content)
    return str(path)


def _load_json(tmp_path, content=TETRA_JSON, filename="tetra.json"):
    """Every .json load in this file goes through PolyhedralNet.load(),
    which caches to cache_path_for's DEFAULT location (a sibling of the
    net's own parent directory) unless told otherwise -- passing each
    test's own tmp_path as cache_dir keeps that cache scoped to this one
    test, instead of colliding with every other test in this file that
    also happens to use the filename "tetra.json" under pytest's one
    shared session tmp root."""
    path = _write(tmp_path, content, filename)
    return PolyhedralNet.load(path, cache_dir=str(tmp_path / "cache"))


def test_load_json_builds_faces_and_hinges(tmp_path):
    net = _load_json(tmp_path)

    assert set(net.faces) == {0, 1, 2, 3}
    assert net.name == "Tetra"
    assert len(net.hinges) == 3
    assert {h.child_id for h in net.hinges} == {1, 2, 3}
    for h in net.hinges:
        assert h.angle is not None


def test_hinge_for_looks_up_by_child_id(tmp_path):
    net = _load_json(tmp_path)
    hinge = net.hinge_for(1)
    assert hinge.child_id == 1
    assert hinge.parent_id == 0


def test_fold_angles_property_matches_hinges(tmp_path):
    net = _load_json(tmp_path)
    assert set(net.fold_angles) == {1, 2, 3}
    for h in net.hinges:
        assert net.fold_angles[h.child_id] == h.angle


def test_fold_at_t1_produces_a_closed_solid(tmp_path):
    net = _load_json(tmp_path)
    solid = net.fold(1.0)
    assert solid.is_closed
    assert set(solid.faces) == {0, 1, 2, 3}


def test_fold_at_t0_is_flat(tmp_path):
    net = _load_json(tmp_path)
    solid = net.fold(0.0)
    # Flat: every face's z-coordinate is 0.
    for face in solid.faces.values():
        assert np.allclose(face.vertices3d[:, 2], 0.0)


def test_assign_colors_cycles_and_survives_fold(tmp_path):
    net = _load_json(tmp_path)
    net.assign_colors(["red", "green"])
    assert net.faces[0].color == "red"
    assert net.faces[1].color == "green"
    assert net.faces[2].color == "red"
    assert net.faces[3].color == "green"

    solid = net.fold(1.0)
    assert solid.faces[0].color == "red"
    assert solid.faces[3].color == "green"


def test_load_legacy_txt(tmp_path):
    path = _write(tmp_path, TWO_TRIANGLE_TXT, "two_triangles.txt")
    net = PolyhedralNet.load(path)

    assert net.name == "Two Triangles"
    assert set(net.faces) == {0, 1}
    assert len(net.hinges) == 1
    hinge = net.hinges[0]
    assert hinge.parent_id == 0
    assert hinge.child_id == 1
    assert np.isclose(hinge.angle, np.radians(90.0))

    solid = net.fold(1.0)
    assert not solid.is_closed  # two triangles never close up into a solid


def test_load_legacy_txt_root_is_first_face_even_when_faces_declared_from_a_higher_id(tmp_path):
    # Same two triangles, but face 1 declared before face 2 -- root must
    # still be the lowest-id face present (1), not just "whichever came
    # first in the file" or "face 0" (there is no face 0 here at all).
    txt = """# Shifted Triangles
FACES
1: 0,0 1,0 0.5,0.866025
2: 1,0 0,0 0.5,-0.866025

FOLD 2 90.0
"""
    path = _write(tmp_path, txt, "shifted.txt")
    net = PolyhedralNet.load(path)
    assert net.root_id == 1
    assert net.hinges[0].parent_id == 1
    assert net.hinges[0].child_id == 2
