import heapq


def find_shortest_path(edges, source, destination):
    """
    Finds the shortest route between source and destination using Dijkstra's algorithm.
    edges is a list of dicts: [{'source': '...', 'destination': '...', 'latency': 12.5}, ...]
    Returns (total_latency, path) or None if no path exists.
    """
    if source == destination:
        return 0.0, [source]

    # Build adjacency list: node -> list of (neighbor, latency)
    graph = {}
    for edge in edges:
        u = edge["source"]
        v = edge["destination"]
        w = float(edge["latency"])
        if u not in graph:
            graph[u] = []
        graph[u].append((v, w))

    # Min-heap priority queue stores tuples of: (current_distance, node)
    pq = [(0.0, source)]
    distances = {source: 0.0}
    previous = {}
    visited = set()

    while pq:
        curr_dist, curr_node = heapq.heappop(pq)

        if curr_node in visited:
            continue
        visited.add(curr_node)

        # Early exit if we reached our target
        if curr_node == destination:
            break

        for neighbor, weight in graph.get(curr_node, []):
            new_dist = curr_dist + weight
            if neighbor not in distances or new_dist < distances[neighbor]:
                distances[neighbor] = new_dist
                previous[neighbor] = curr_node
                heapq.heappush(pq, (new_dist, neighbor))

    # If destination was not reached
    if destination not in distances:
        return None

    # Reconstruct the path backwards from destination
    path = []
    curr = destination
    while curr is not None:
        path.append(curr)
        curr = previous.get(curr)
    path.reverse()

    # Round to avoid float precision issues (e.g. 23.400000000000002 -> 23.4)
    total_latency = round(distances[destination], 4)
    return total_latency, path
