"""Build the flat 2D net layout (physical face positions on paper) from the
net's spanning-tree edges and the polyhedron's combinatorial edge map."""
from collections import defaultdict, deque

from .net_fold_core import Net
from .polygon_geom import regular_polygon_vertices, attach_polygon


def build_net_layout(degrees, net_edges, edge_map, root):
    """Lay out each face as a regular polygon, attaching children to their
    parent's shared edge (reversed, so the child unfolds to the outside --
    the same convention a paper net uses). Returns (Net, hinges), where
    hinges has the same shape as Net.build_tree()'s second return value."""
    adj = defaultdict(list)
    for a, b in net_edges:
        adj[a].append(b)
        adj[b].append(a)

    n = len(degrees)
    placed = {root: regular_polygon_vertices(degrees[root])}
    hinges = []
    visited = {root}
    q = deque([root])
    while q:
        parent = q.popleft()
        for child in adj[parent]:
            if child in visited:
                continue
            visited.add(child)
            p_idx = edge_map.edge_index(parent, child)
            c_idx = edge_map.edge_index(child, parent)
            pverts = placed[parent]
            p1, p2 = pverts[p_idx], pverts[(p_idx + 1) % len(pverts)]
            placed[child] = attach_polygon(degrees[child], c_idx, p2, p1)
            hinges.append(dict(parent=parent, child=child,
                                parent_edge_idx=p_idx, child_edge_idx=c_idx))
            q.append(child)

    if len(visited) != n:
        missing = sorted(set(range(n)) - visited)
        raise ValueError(f"NET edges do not connect all faces; "
                          f"unreached face(s): {missing}")

    net = Net()
    for fid in range(n):
        net.add_face(placed[fid])
    return net, hinges
