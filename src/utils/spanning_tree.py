"""Generic BFS spanning tree over abstract nodes and edge "ports" -- knows
nothing about polyhedra; callers translate their own adjacency into
(node, port, node, port) tuples.
"""
from collections import defaultdict, deque


def create_spanning_tree_BFS(node_indices, adjacencies, root):
    """BFS spanning tree over `node_indices`, given `adjacencies` (a list
    of (node_a, port_a, node_b, port_b) tuples). Returns a list of
    tree-edge dicts: {parent, child, parent_edge_idx, child_edge_idx}.
    Raises ValueError if any node is unreachable from `root`."""
    neighbors = defaultdict(list)
    for a, port_a, b, port_b in adjacencies:
        neighbors[a].append((b, port_a, port_b))
        neighbors[b].append((a, port_b, port_a))

    visited = {root}
    tree_edges = []
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for neighbor, my_port, neighbor_port in neighbors[node]:
            if neighbor in visited:
                continue
            visited.add(neighbor)
            tree_edges.append(dict(parent=node, child=neighbor,
                                    parent_edge_idx=my_port, child_edge_idx=neighbor_port))
            queue.append(neighbor)

    unreached = set(node_indices) - visited
    if unreached:
        raise ValueError(f"graph is disconnected; node(s) {sorted(unreached)} "
                          f"unreachable from root {root}")
    return tree_edges
