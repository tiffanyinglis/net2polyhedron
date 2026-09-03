"""Split a polyhedron's full edge list into a spanning-tree net layout plus
the remaining closure edges, via plain BFS from a chosen root face."""
from collections import defaultdict, deque


def split_spanning_tree(n, edges, root=0):
    """Return (net_edges, extra_edges): net_edges is a BFS spanning tree of
    the face-adjacency graph rooted at `root`, extra_edges is everything
    else."""
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)

    visited = {root}
    net_edges = []
    q = deque([root])
    while q:
        node = q.popleft()
        for nbr in adj[node]:
            if nbr not in visited:
                visited.add(nbr)
                net_edges.append((node, nbr))
                q.append(nbr)

    if len(visited) != n:
        raise ValueError(f"graph is disconnected; unreached faces: "
                          f"{sorted(set(range(n)) - visited)}")

    tree_set = {frozenset(e) for e in net_edges}
    extra_edges = [e for e in edges if frozenset(e) not in tree_set]
    return net_edges, extra_edges
