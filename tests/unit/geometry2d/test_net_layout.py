import numpy as np
import pytest

from utils.combinatorics.edge_map import EdgeMap
from utils.geometry2d.net_layout import build_net_layout

TETRAHEDRON_DEGREES = [3, 3, 3, 3]
TETRAHEDRON_EDGES = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
TETRAHEDRON_NET_EDGES = [(0, 1), (0, 2), (0, 3)]


def test_build_net_layout_places_every_face_with_touching_hinge_edges():
    edge_map = EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES)
    net, hinges = build_net_layout(TETRAHEDRON_DEGREES, TETRAHEDRON_NET_EDGES, edge_map, root=0)

    assert set(net.faces.keys()) == {0, 1, 2, 3}
    assert len(hinges) == 3
    assert {h["child"] for h in hinges} == {1, 2, 3}

    # each hinge's parent/child edge must physically coincide (reversed) in
    # the flat layout -- that's what makes it a valid net hinge
    for h in hinges:
        p_verts = net.faces[h["parent"]]
        c_verts = net.faces[h["child"]]
        p1 = p_verts[h["parent_edge_idx"]]
        p2 = p_verts[(h["parent_edge_idx"] + 1) % len(p_verts)]
        c1 = c_verts[h["child_edge_idx"]]
        c2 = c_verts[(h["child_edge_idx"] + 1) % len(c_verts)]
        assert np.allclose(c1, p2, atol=1e-9)
        assert np.allclose(c2, p1, atol=1e-9)


def test_build_net_layout_rejects_disconnected_net_edges():
    edge_map = EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES)
    with pytest.raises(ValueError, match="unreached"):
        build_net_layout(TETRAHEDRON_DEGREES, [(0, 1)], edge_map, root=0)


def test_build_net_layout_skips_omitted_faces():
    # edge_map still needs the full (closed) graph so faces bordering the
    # omitted one recover their correct edge index -- only net_edges
    # (never touching face 3) says which faces actually get built.
    edge_map = EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES)
    net, hinges = build_net_layout(TETRAHEDRON_DEGREES, [(0, 1), (0, 2)], edge_map,
                                    root=0, omitted={3})

    assert set(net.faces.keys()) == {0, 1, 2}
    assert {h["child"] for h in hinges} == {1, 2}


def test_build_net_layout_still_rejects_an_unreached_non_omitted_face():
    edge_map = EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES)
    with pytest.raises(ValueError, match="unreached"):
        # face 2 is not omitted but net_edges never reaches it
        build_net_layout(TETRAHEDRON_DEGREES, [(0, 1)], edge_map, root=0, omitted={3})


def test_build_net_layout_preserves_original_face_ids_with_a_gap():
    # faces are kept as their ORIGINAL ids (0, 1, 2), not renumbered to
    # close the gap left by the omitted face (3) -- hinges reference the
    # same ids net.faces uses.
    edge_map = EdgeMap(TETRAHEDRON_DEGREES, TETRAHEDRON_EDGES)
    net, hinges = build_net_layout(TETRAHEDRON_DEGREES, [(0, 1), (0, 2)], edge_map,
                                    root=0, omitted={3})
    for h in hinges:
        assert h["parent"] in net.faces
        assert h["child"] in net.faces
