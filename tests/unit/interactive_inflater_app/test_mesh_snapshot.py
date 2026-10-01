from interactive_inflater_app.state.mesh_snapshot import MeshSnapshotManager


class FakeBuilder:
    def __init__(self, connections):
        self.connections = connections


class FakeInflaterPane:
    """Minimal stand-in exposing exactly the attributes/method MeshSnapshotManager needs."""

    def __init__(self):
        self.base_faces = [[0, 1, 2]]
        self.base_edges = [(0, 1)]
        self.base_face_edge_ids = [[1, 2, 3]]
        self.faces = [[0, 1, 2]]
        self.edge_length = 1.0
        self.face_of_fine = [0]
        self.edges = None
        self.positions = {0: "p0", 1: "p1", 2: "p2"}
        self.subdivision_level = 2
        self._pending_source_polygon_id = [10]
        self._pending_pendants = []
        self.is_fully_inflated = True
        self._builder = FakeBuilder([{"id": 1}])

    def builder_getter(self):
        return self._builder


def test_take_captures_every_field_plus_builder_connections():
    subject = FakeInflaterPane()
    manager = MeshSnapshotManager(subject)
    snapshot = manager.take()
    assert snapshot["base_faces"] == [[0, 1, 2]]
    assert snapshot["pending_source_polygon_id"] == [10]
    assert snapshot["pending_pendants"] == []
    assert snapshot["is_fully_inflated"] is True
    assert snapshot["builder_connections"] == [{"id": 1}]


def test_take_copies_builder_connections_not_a_live_reference():
    subject = FakeInflaterPane()
    manager = MeshSnapshotManager(subject)
    snapshot = manager.take()
    subject._builder.connections.append({"id": 2})
    assert snapshot["builder_connections"] == [{"id": 1}]  # unaffected by the later mutation


def test_restore_writes_every_field_back_except_builder_connections():
    subject = FakeInflaterPane()
    manager = MeshSnapshotManager(subject)
    snapshot = manager.take()

    # Mutate everything, as a real pipeline run would.
    subject.base_faces = [[9, 9, 9]]
    subject.faces = [[9, 9, 9]]
    subject.subdivision_level = 3
    subject._pending_source_polygon_id = [99]
    subject.is_fully_inflated = False
    subject._builder.connections = [{"id": 2}, {"id": 3}]

    manager.restore(snapshot)

    assert subject.base_faces == [[0, 1, 2]]
    assert subject.faces == [[0, 1, 2]]
    assert subject.subdivision_level == 2
    assert subject._pending_source_polygon_id == [10]
    assert subject.is_fully_inflated is True
    # builder_connections is deliberately never restored -- the live builder net is a separate
    # concern from this pane's own mesh fields.
    assert subject._builder.connections == [{"id": 2}, {"id": 3}]


def test_round_trip_is_a_no_op_when_nothing_changed():
    subject = FakeInflaterPane()
    manager = MeshSnapshotManager(subject)
    snapshot = manager.take()
    manager.restore(snapshot)
    assert subject.base_faces == [[0, 1, 2]]
    assert subject.subdivision_level == 2
