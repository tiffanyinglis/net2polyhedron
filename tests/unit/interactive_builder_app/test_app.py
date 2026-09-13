"""Unit tests for interactive_builder_app.app's pure net-validation logic
(_validate_shapes_connections, _faces_from_shapes, _connection_pairs,
_true_edge_slots) -- the combinatorial core behind File > Save, with no
Tkinter dependency at all. This is an explicit, user-requested exception
to this project's usual "src/apps/ beyond apps_common stays untested"
convention, added after a real bug (two hexagons sharing 2 edges failing
to save) reportedly recurred -- these tests exist to pin down exactly
what does and doesn't work so a change here can't silently regress any
of it again.

A shape's "flipped" bit (see the module docstring's "Flip" section) is
set directly by the user (select shapes, press F) -- there is no
automatic search for a working combination any more (an earlier version,
_infer_shape_flips, tried exactly that and was removed: for any mesh with
a real cycle in its connections, more than one flip combination often
validates, so an automatic search could only ever produce "a" valid
answer, not necessarily the one the user actually intends). Every test
below constructs shapes with whichever "flipped" values it wants to check
and calls _validate_shapes_connections directly, rather than searching
for them.

Ground truth for every "does/doesn't this net need a flip to be valid"
claim below was independently verified by a plain corner-level
union-find script checking BOTH failure modes _validate_shapes_connections
itself checks (a self-loop AND a duplicate directed edge). See each
test's own docstring for what was actually checked.

Connecting a shape to one of its OWN (different) edges is not something
this app supports at all (_hit_test_any_edge_handle refuses a handle on
the pending connection's own origin SHAPE, not just its origin edge), so
there is deliberately no test coverage here for a_shape == b_shape --
_connection_pairs is never called with one."""
import glob
import itertools
import json
import os

import pytest

import interactive_builder_app.app as builder_app
from interactive_builder_app.app import NetValidationError

STRETCHY_NETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "input", "stretchy_nets")


def shape(shape_id, n, flipped=False):
    return {"id": shape_id, "n": n, "flipped": flipped}


def conn(conn_id, a_shape, a_edge, b_shape, b_edge):
    return {"id": conn_id, "a_shape": a_shape, "a_edge": a_edge, "b_shape": b_shape, "b_edge": b_edge}


def shapes_and_connections_from_faces(faces):
    """Converts a plain vertex-loop `faces` list (the on-disk net format)
    into (shapes, connections) the way interactive_builder_app's own
    _load_faces does: one shape per face (n = its length, never
    flipped), connections inferred from shared reversed directed edges
    (_infer_connections) -- so a shipped net can be run back through the
    app's own Save-time validation as a regression check."""
    shapes = [shape(i, len(f)) for i, f in enumerate(faces)]
    raw_conns = builder_app._infer_connections(faces)
    connections = [conn(k, c["a_face"], c["a_edge"], c["b_face"], c["b_edge"])
                   for k, c in enumerate(raw_conns)]
    return shapes, connections


def is_valid_net(faces):
    """True iff `faces` has no self-loop and no duplicate directed edge
    -- the exact two rules stretchy_mesh.load_stretchy_mesh itself
    enforces (see its own module docstring)."""
    counts = {}
    for face in faces:
        n = len(face)
        for i in range(n):
            v, w = face[i], face[(i + 1) % n]
            if v == w:
                return False
            counts[(v, w)] = counts.get((v, w), 0) + 1
    return all(c == 1 for c in counts.values())


# ---- shipped nets: every one must already validate unflipped ----

SHIPPED_NET_PATHS = sorted(glob.glob(os.path.join(STRETCHY_NETS_DIR, "*.json")))


@pytest.mark.parametrize("net_path", SHIPPED_NET_PATHS, ids=[os.path.basename(p) for p in SHIPPED_NET_PATHS])
def test_shipped_net_validates_unflipped(net_path):
    """Every net already shipped under data/input/stretchy_nets/ was
    hand-built and saved successfully -- loading it back always starts
    every shape unflipped (_load_faces), so it must still validate that
    way: _infer_connections derives connections straight from the
    file's own already-consistent winding, never from _connection_pairs,
    so there's nothing for a shape-level flip to fix in a freshly
    reloaded file regardless of what the original builder session's
    shapes happened to be flipped to."""
    with open(net_path) as f:
        faces = json.load(f)["faces"]
    shapes, connections = shapes_and_connections_from_faces(faces)
    builder_app._validate_shapes_connections(shapes, connections)  # must not raise


# ---- the tetrahedron "3 tops + flipped base" case (first bug fixed) ----

class TestTetrahedronFlip:
    """3 triangles connected pairwise around a shared apex, plus a 4th
    "base" triangle closing all 3 of their remaining edges -- the base
    needs to be read the OTHER way (a shape-level flip) relative to the
    other 3, or it's a duplicate-directed-edge conflict. This is the
    original bug report that first motivated a per-shape "flipped" bit
    at all."""

    SHAPES = [shape(1, 3), shape(2, 3), shape(3, 3), shape(4, 3)]
    CONNECTIONS = [
        conn(1, 1, 0, 2, 2),
        conn(2, 1, 2, 3, 0),
        conn(3, 2, 0, 3, 2),
        conn(4, 1, 1, 4, 1),
        conn(5, 2, 1, 4, 0),
        conn(6, 3, 1, 4, 2),
    ]

    def test_fails_unflipped(self):
        with pytest.raises(NetValidationError):
            builder_app._validate_shapes_connections(self.SHAPES, self.CONNECTIONS)

    def test_validates_once_the_base_is_flipped(self):
        trial_shapes = [dict(s, flipped=(s["id"] == 4)) for s in self.SHAPES]
        builder_app._validate_shapes_connections(trial_shapes, self.CONNECTIONS)  # must not raise
        faces = builder_app._faces_from_shapes(trial_shapes, self.CONNECTIONS)
        assert len(faces) == 4
        assert is_valid_net(faces)
        assert len({v for f in faces for v in f}) == 4, "a tetrahedron has exactly 4 vertices"


# ---- two DIFFERENT shapes sharing 2 edges (a real "bend") ----

class TestTwoShapeBend:
    """Two hexagons sharing TWO adjacent edges each (a genuine bend --
    see the crochet photo this was reported against) needs a shape-level
    flip on one of them, with NO self-loop involved at all (a pure
    duplicate-directed-edge conflict)."""

    SHAPES = [shape(1, 6), shape(6, 6)]
    CONNECTIONS = [conn(1, 1, 0, 6, 3), conn(2, 1, 5, 6, 2)]

    def test_fails_unflipped_with_a_pure_duplicate_edge_conflict_no_self_loop(self):
        try:
            builder_app._validate_shapes_connections(self.SHAPES, self.CONNECTIONS)
            pytest.fail("expected a NetValidationError")
        except NetValidationError as e:
            assert not e.self_loop_slots, "this failure must be a pure duplicate-edge conflict"

    def test_validates_once_one_hexagon_is_flipped(self):
        trial_shapes = [dict(s, flipped=(s["id"] == 6)) for s in self.SHAPES]
        builder_app._validate_shapes_connections(trial_shapes, self.CONNECTIONS)
        faces = builder_app._faces_from_shapes(trial_shapes, self.CONNECTIONS)
        assert is_valid_net(faces)
        # the two hexagons should share exactly 3 vertices (2 edges' worth)
        shared = set(faces[0]) & set(faces[1])
        assert len(shared) == 3, faces


# ---- two SEPARATE, already-internally-connected groups, one needing a
# ---- whole-group flip once they're first connected to each other ----

class TestTwoGroupsNeedAWholeGroupFlip:
    """Two SEPARATE triangle-fans (1+2+3 around one apex, 4+5+6 around
    another -- each internally rigid exactly like TestTetrahedronFlip's
    own 3-triangle fan, with no flip needed on its own) are then joined
    by TWO connections between them -- one triangle from each fan to a
    DIFFERENT triangle of the other fan. Ground truth (exhaustive 2**6
    brute force over every shape's flip bit) found exactly 2 working
    assignments out of 64: flip shapes {1, 2, 3} ALL together, or flip
    {4, 5, 6} ALL together -- no individual shape, pair, or any other
    combination works. This is exactly why flipping is a per-SHAPE
    action the user applies to a whole selection at once (press F with
    an entire fan selected), not something that could ever be resolved
    one shape at a time: flipping only PART of a fan would break that
    fan's own internal (already-satisfied) connections."""

    SHAPES = [shape(i, 3) for i in range(1, 7)]
    CONNECTIONS = [
        conn(1, 1, 0, 2, 2), conn(2, 1, 2, 3, 0), conn(3, 2, 0, 3, 2),  # fan A: 1+2+3
        conn(4, 4, 0, 5, 2), conn(5, 4, 2, 6, 0), conn(6, 5, 0, 6, 2),  # fan B: 4+5+6
        conn(7, 1, 1, 4, 1), conn(8, 2, 1, 5, 1),                      # joining the two fans
    ]

    def test_fails_unflipped(self):
        with pytest.raises(NetValidationError):
            builder_app._validate_shapes_connections(self.SHAPES, self.CONNECTIONS)

    @pytest.mark.parametrize("flip_set", [{1, 2, 3}, {4, 5, 6}])
    def test_validates_once_one_whole_fan_is_flipped(self, flip_set):
        trial_shapes = [dict(s, flipped=(s["id"] in flip_set)) for s in self.SHAPES]
        builder_app._validate_shapes_connections(trial_shapes, self.CONNECTIONS)  # must not raise
        faces = builder_app._faces_from_shapes(trial_shapes, self.CONNECTIONS)
        assert is_valid_net(faces)

    @pytest.mark.parametrize("flip_set", [{1, 2, 3}, {4, 5, 6}])
    def test_fails_if_only_PART_of_a_fan_is_flipped(self, flip_set):
        for missing in flip_set:
            partial = flip_set - {missing}
            trial = [dict(s, flipped=(s["id"] in partial)) for s in self.SHAPES]
            with pytest.raises(NetValidationError):
                builder_app._validate_shapes_connections(trial, self.CONNECTIONS)


# ---- a genuinely impossible net (no flip can ever fix it) ----

class TestGenuinelyImpossibleNet:
    """Two squares connected along two edges each -- (a_edge 0, 1) to
    (b_edge 0, 2) -- a "twisted" pairing that forces a duplicate
    directed edge under EVERY one of the 4 possible flip combinations
    (ground truth: brute-forced directly, see test_fails_regardless_of_flip)."""

    SHAPES = [shape(1, 4), shape(2, 4)]
    CONNECTIONS = [conn(1, 1, 0, 2, 0), conn(2, 1, 1, 2, 2)]

    def test_fails_regardless_of_flip(self):
        for flip1, flip2 in itertools.product([False, True], repeat=2):
            trial_shapes = [dict(self.SHAPES[0], flipped=flip1), dict(self.SHAPES[1], flipped=flip2)]
            with pytest.raises(NetValidationError):
                builder_app._validate_shapes_connections(trial_shapes, self.CONNECTIONS)
