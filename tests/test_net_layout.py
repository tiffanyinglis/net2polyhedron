import numpy as np
import pytest

from net_fold_utils.combinatorics import EdgeMap
from net_fold_utils.net_layout import build_net_layout

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
