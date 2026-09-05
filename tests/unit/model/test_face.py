from utils.model.face import Face


def test_face_holds_id_sides_and_color():
    face = Face(0, sides=3)
    assert face.id == 0
    assert face.sides == 3
    assert face.color is None


def test_color_is_a_plain_mutable_attribute():
    face = Face(0, sides=4)
    face.color = "red"
    assert face.color == "red"
