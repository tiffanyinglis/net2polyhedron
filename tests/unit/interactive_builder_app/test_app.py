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
itself checks (a vertex merge error -- two different corners of one face
resolving to the same vertex -- AND a duplicate directed edge). See each
test's own docstring for what was actually checked.

Connecting a shape to one of its OWN (different) edges is not supported
yet (planned for later -- _hit_test_any_edge_handle refuses a handle on
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
    """True iff `faces` has no degenerate (v->v) edge and no duplicate
    directed edge -- the exact two rules stretchy_mesh.load_stretchy_mesh
    itself enforces (see its own module docstring)."""
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

    def test_fails_unflipped_is_a_vertex_merge_error(self):
        """The other example in this file (TestVertexMergeErrorOnFlip)
        shows a consistently-oriented tetrahedron breaking when ONE face
        is flipped away from its neighbors; this is the mirror image --
        this net only validates with the base flipped AWAY from the
        other 3, so leaving every face facing the same way (all
        unflipped) is itself what breaks it, with a genuine VME (not
        just a duplicate edge) at the root of it."""
        with pytest.raises(NetValidationError) as excinfo:
            builder_app._validate_shapes_connections(self.SHAPES, self.CONNECTIONS)
        assert excinfo.value.vertex_merge_error_slots, "expected a genuine vertex merge error"

    def test_validates_once_the_base_is_flipped(self):
        trial_shapes = [dict(s, flipped=(s["id"] == 4)) for s in self.SHAPES]
        builder_app._validate_shapes_connections(trial_shapes, self.CONNECTIONS)  # must not raise
        faces = builder_app._faces_from_shapes(trial_shapes, self.CONNECTIONS)
        assert len(faces) == 4
        assert is_valid_net(faces)
        assert len({v for f in faces for v in f}) == 4, "a tetrahedron has exactly 4 vertices"


# ---- a consistently-oriented tetrahedron (every face facing the same
# ---- way) that breaks the moment any ONE face is flipped ----

class TestVertexMergeErrorOnFlip:
    """A tetrahedron over vertices A/B/C/D with faces (A,B,C), (A,D,B),
    (B,D,C), (A,C,D), each CCW-from-outside -- the standard way to
    consistently orient a tetrahedron's 4 triangles. Every shape starts
    UNFLIPPED (all faces "facing the same way") and validates with no
    vertex merge error (VME) at all: the default (unflipped) pairing
    IS the CCW-from-outside convention, so nothing here needs a flip
    the way TestTetrahedronFlip's own net does. Flipping any single
    face then reverses just that face's own edges' true direction
    relative to every neighbor still expecting the default pairing,
    which introduces a genuine VME -- the exact opposite failure mode
    from TestTetrahedronFlip, where leaving every face unflipped is
    what breaks it and flipping one face is what fixes it."""

    SHAPES = [shape(1, 3), shape(2, 3), shape(3, 3), shape(4, 3)]
    CONNECTIONS = [
        conn(1, 1, 0, 2, 2),  # shared edge A-B: shape 1 = (A,B,C), shape 2 = (A,D,B)
        conn(2, 1, 1, 3, 2),  # shared edge B-C: shape 1 = (A,B,C), shape 3 = (B,D,C)
        conn(3, 1, 2, 4, 0),  # shared edge C-A: shape 1 = (A,B,C), shape 4 = (A,C,D)
        conn(4, 2, 0, 4, 2),  # shared edge A-D: shape 2 = (A,D,B), shape 4 = (A,C,D)
        conn(5, 2, 1, 3, 0),  # shared edge D-B: shape 2 = (A,D,B), shape 3 = (B,D,C)
        conn(6, 3, 1, 4, 1),  # shared edge D-C: shape 3 = (B,D,C), shape 4 = (A,C,D)
    ]

    def test_validates_with_every_face_facing_the_same_way(self):
        builder_app._validate_shapes_connections(self.SHAPES, self.CONNECTIONS)  # must not raise
        faces = builder_app._faces_from_shapes(self.SHAPES, self.CONNECTIONS)
        assert len(faces) == 4
        assert is_valid_net(faces)
        assert len({v for f in faces for v in f}) == 4, "a tetrahedron has exactly 4 vertices"

    @pytest.mark.parametrize("flip_id", [1, 2, 3, 4])
    def test_flipping_any_one_face_introduces_a_vertex_merge_error(self, flip_id):
        trial_shapes = [dict(s, flipped=(s["id"] == flip_id)) for s in self.SHAPES]
        with pytest.raises(NetValidationError) as excinfo:
            builder_app._validate_shapes_connections(trial_shapes, self.CONNECTIONS)
        assert excinfo.value.vertex_merge_error_slots, "expected a genuine vertex merge error"


# ---- two DIFFERENT shapes sharing 2 edges (a real "bend") ----

class TestTwoShapeBend:
    """Two hexagons sharing TWO adjacent edges each (a genuine bend --
    see the crochet photo this was reported against) needs a shape-level
    flip on one of them, with NO vertex merge error involved at all (a
    pure duplicate-directed-edge conflict)."""

    SHAPES = [shape(1, 6), shape(6, 6)]
    CONNECTIONS = [conn(1, 1, 0, 6, 3), conn(2, 1, 5, 6, 2)]

    def test_fails_unflipped_with_a_pure_duplicate_edge_conflict_no_vertex_merge_error(self):
        try:
            builder_app._validate_shapes_connections(self.SHAPES, self.CONNECTIONS)
            pytest.fail("expected a NetValidationError")
        except NetValidationError as e:
            assert not e.vertex_merge_error_slots, "this failure must be a pure duplicate-edge conflict"

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


# ---- vertex labelling (debug mode's always-on dedup vertex display,
# ---- _draw_dedup_vertex_labels) -- pinned down as a regression
# ---- baseline before further work touches any of this ----

def dedup_groups(shapes, connections):
    """The CURRENT vertex-labelling PARTITION -- a frozenset of
    frozensets of (shape_id, corner_index) slots that _vertex_roots (and
    therefore _draw_dedup_vertex_labels, see interactive_builder_app.app's
    own module docstring under "Debug mode") currently consider to be
    the SAME vertex. Deliberately label-independent:
    _draw_dedup_vertex_labels assigns its displayed NUMBERS fresh, in
    shape/corner visiting order, on every redraw -- a pure display
    convenience that can shift across calls or future versions with no
    real behavior change (see its own docstring). Comparing this
    partition instead of any assigned number means a test only fails if
    two corners that used to be the same deduped vertex stop being (or
    vice versa), not just because a number happened to shift."""
    roots = builder_app._vertex_roots(shapes, connections)
    groups = {}
    for slot, root in roots.items():
        groups.setdefault(root, set()).add(slot)
    return frozenset(frozenset(g) for g in groups.values())


class TestDedupVertexGrouping:
    """Ground truth below was read directly off dedup_groups' own output
    (not re-derived by hand) for each case, so these pin down CURRENT,
    verified behavior as a regression baseline -- not a claim that this
    is the only correct grouping imaginable, just that it's what this
    code does right now and shouldn't change without a test noticing."""

    def test_no_connections_every_corner_is_its_own_group(self):
        shapes = [shape(1, 3), shape(2, 4)]
        groups = dedup_groups(shapes, [])
        assert groups == frozenset(
            frozenset([(sid, c)]) for sid, n in [(1, 3), (2, 4)] for c in range(n))

    def test_one_connection_merges_exactly_its_two_shared_corners(self):
        shapes = [shape(1, 3), shape(2, 3)]
        connections = [conn(1, 1, 0, 2, 0)]
        groups = dedup_groups(shapes, connections)
        assert groups == frozenset({
            frozenset({(1, 0), (2, 1)}),
            frozenset({(1, 1), (2, 0)}),
            frozenset({(1, 2)}),
            frozenset({(2, 2)}),
        })

    def test_consistently_oriented_tetrahedron_has_4_groups_of_3(self):
        """TestVertexMergeErrorOnFlip's own net, unflipped -- a real
        vertex of a tetrahedron touches exactly 3 faces, so each of the
        4 groups should have exactly 3 corners in it."""
        groups = dedup_groups(TestVertexMergeErrorOnFlip.SHAPES, TestVertexMergeErrorOnFlip.CONNECTIONS)
        assert groups == frozenset({
            frozenset({(1, 0), (2, 0), (4, 0)}),
            frozenset({(1, 1), (2, 2), (3, 0)}),
            frozenset({(1, 2), (3, 2), (4, 1)}),
            frozenset({(2, 1), (3, 1), (4, 2)}),
        })

    def test_flipping_one_face_collapses_two_of_the_four_groups_together(self):
        """The same net with shape 4 flipped (a genuine vertex merge
        error, see TestVertexMergeErrorOnFlip) -- 3 of its 4 real
        vertices collapse into ONE 9-corner group, leaving only the
        vertex shape 4 doesn't touch (B) still on its own; the grouping
        itself changes shape, not just which numbers get assigned."""
        trial_shapes = [dict(s, flipped=(s["id"] == 4)) for s in TestVertexMergeErrorOnFlip.SHAPES]
        groups = dedup_groups(trial_shapes, TestVertexMergeErrorOnFlip.CONNECTIONS)
        assert groups == frozenset({
            frozenset({(1, 0), (1, 2), (2, 0), (2, 1), (3, 1), (3, 2), (4, 0), (4, 1), (4, 2)}),
            frozenset({(1, 1), (2, 2), (3, 0)}),
        })

    def test_tetrahedron_flip_net_has_4_groups_of_3_once_the_base_is_flipped(self):
        """TestTetrahedronFlip's own net -- the mirror image of the
        above: needs the base (shape 4) flipped to validate at all."""
        trial_shapes = [dict(s, flipped=(s["id"] == 4)) for s in TestTetrahedronFlip.SHAPES]
        groups = dedup_groups(trial_shapes, TestTetrahedronFlip.CONNECTIONS)
        assert groups == frozenset({
            frozenset({(1, 0), (2, 0), (3, 0)}),
            frozenset({(1, 1), (2, 2), (4, 1)}),
            frozenset({(1, 2), (3, 1), (4, 2)}),
            frozenset({(2, 1), (3, 2), (4, 0)}),
        })

    def test_tetrahedron_flip_net_collapses_to_2_groups_left_unflipped(self):
        trial_shapes = TestTetrahedronFlip.SHAPES  # every shape unflipped
        groups = dedup_groups(trial_shapes, TestTetrahedronFlip.CONNECTIONS)
        assert groups == frozenset({
            frozenset({(1, 0), (2, 0), (3, 0)}),
            frozenset({(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2), (4, 0), (4, 1), (4, 2)}),
        })

    def test_two_shape_bend_has_3_shared_pairs_once_one_hexagon_is_flipped(self):
        """TestTwoShapeBend's own net -- two hexagons sharing 2 edges (3
        vertices' worth), each of those 3 vertices its own 2-corner
        group; the other 6 corners (3 per hexagon) stay singletons."""
        trial_shapes = [dict(s, flipped=(s["id"] == 6)) for s in TestTwoShapeBend.SHAPES]
        groups = dedup_groups(trial_shapes, TestTwoShapeBend.CONNECTIONS)
        assert groups == frozenset({
            frozenset({(1, 0), (6, 3)}),
            frozenset({(1, 1), (6, 4)}),
            frozenset({(1, 5), (6, 2)}),
            frozenset({(1, 2)}), frozenset({(1, 3)}), frozenset({(1, 4)}),
            frozenset({(6, 0)}), frozenset({(6, 1)}), frozenset({(6, 5)}),
        })
