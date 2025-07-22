from typing import Dict, NamedTuple, Optional

import networkx as nx


class TrackletInfo(NamedTuple):
    parent_map: Dict[int, Optional[int]]
    t_min: Dict[int, int]
    t_max: Dict[int, int]


# this function can be re-written into a more general one accepting more than time as a feature
# for the purpose of geff it will probably be faster to work through array and not networkx
def collect_tracklet_info(G: nx.DiGraph) -> TrackletInfo:
    """
    Traverse G once to collect parent map, t_min, t_max per track_id.

    Args:
        G (networkx.DiGraph): Graph where nodes have 'track_id' and 't' attributes.

    Returns:
        TrackletInfo: NamedTuple with parent_map, t_min, t_max dictionaries.
    """
    first_nodes: Dict[int, int] = {}
    parent_map: Dict[int, Optional[int]] = {}
    t_min: Dict[int, int] = {}
    t_max: Dict[int, int] = {}

    for n in G.nodes:
        tid: int = G.nodes[n]["track_id"]
        t: int = G.nodes[n]["t"]
        # Track t_min, t_max
        if tid not in t_min or t < t_min[tid]:
            t_min[tid] = t
        if tid not in t_max or t > t_max[tid]:
            t_max[tid] = t
        # Find first node for parent map
        if tid not in first_nodes or t < G.nodes[first_nodes[tid]]["t"]:
            first_nodes[tid] = n

    # Build parent_map
    for tid, n in first_nodes.items():
        preds = list(G.predecessors(n))
        parent_map[tid] = G.nodes[preds[0]]["track_id"] if preds else None

    return TrackletInfo(parent_map, t_min, t_max)


def tracklet_roots_map(parent_map):
    """
    Maps each track_id to its root tracklet in a forest.

    Args:
        parent_map (dict): {track_id: parent_track_id or None}

    Returns:
        dict: {track_id: root_track_id}
    """
    roots = {}

    for tid in parent_map:
        if tid in roots:
            continue  # Already resolved
        current = tid
        path = []
        while True:
            parent = parent_map.get(current, None)
            # Catch self-parent and missing-parent
            if parent is None or parent == current:
                root = current
                break
            if parent not in parent_map:
                root = parent
                break
            path.append(current)
            if parent in roots:
                root = roots[parent]
                break
            current = parent
        for seen in path:
            roots[seen] = root
        roots[tid] = root
    return roots
