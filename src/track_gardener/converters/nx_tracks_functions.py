from typing import Any, Optional

import networkx as nx

################################################################################
################################################################################


def assign_tracklet_ids(
    G: nx.DiGraph, attribute_name: str = "tracklet_id"
) -> nx.DiGraph:
    """
    Labels nodes in a Directed Acyclic Graph (DAG) with tracklet IDs.

    This function processes a DAG, which can contain splits (out-degree > 1)
    and merges (in-degree > 1). It identifies linear paths (tracklets) and
    assigns a unique ID to all nodes within that path. The function modifies
    the graph in-place.

    A tracklet is a linear sequence of nodes where each node has exactly one
    predecessor and one successor, bounded by junction nodes (roots, leaves,
    splits, or merges).

    Args:
        G (nx.DiGraph): The input Directed Acyclic Graph. This graph is
            modified in-place.
        attribute_name (str, optional): The name for the new node attribute
            that will store the tracklet ID. Defaults to "tracklet_id".

    Returns:
        nx.DiGraph: The same input graph `G`, with nodes now containing the
            specified attribute (e.g., 'tracklet_id').
    """
    track_id = 0

    # Process each connected component of the graph independently.
    for component in nx.weakly_connected_components(G):
        subgraph = G.subgraph(component)

        for node in nx.topological_sort(subgraph):

            if attribute_name in G.nodes[node]:
                continue

            # If the node is unvisited, it's the start of a new tracklet.
            current_path = []
            current_node = node

            while True:
                current_path.append(current_node)

                # Stop if the current node is a leaf or a split node.
                if subgraph.out_degree(current_node) != 1:
                    break

                # Get the single successor
                successor = list(subgraph.successors(current_node))[0]

                # Stop if the next node is a merge node.
                if subgraph.in_degree(successor) != 1:
                    break

                # Move to the next node in the tracklet.
                current_node = successor

            # Assign the new track_id to all nodes in the discovered path.
            for n_in_path in current_path:
                G.nodes[n_in_path][attribute_name] = track_id

            # Increment the ID for the next tracklet.
            track_id += 1

    return G


################################################################################
################################################################################


def build_tracklet_graph(
    G: nx.DiGraph,
    attribute_name: str = "tracklet_id",
    prop_names: Optional[list[str]] = None,
) -> nx.DiGraph:
    """Builds a derivative graph where each node represents a tracklet.

    This function collapses a graph with a tracklet ID attribute
    on its nodes into a new graph of tracklets. It can aggregate specified
    numerical properties from the original nodes into min/max values on the
    new tracklet nodes.

    Args:
        G: The input graph where nodes must have the specified `attribute_name`
            and all listed `prop_names` as attributes.
        attribute_name: The name of the node attribute that stores the
            tracklet ID. Defaults to "tracklet_id".
        prop_names: An optional list of numerical node attribute names
            to aggregate (e.g., ['t', 'intensity']). If None, no properties
            are aggregated.

    Returns:
        A new directed graph where each node is a tracklet_id.
        For each property in `prop_names`, the nodes will contain
        '{prop_name}_min' and '{prop_name}_max' attributes. Edges connect
        tracklets that were connected in the original graph.

    Raises:
        KeyError: If a node in `G` is missing the `attribute_name` or any of
            the attributes listed in `prop_names`.
    """
    if prop_names is None:
        prop_names = []

    tracklet_graph = nx.DiGraph()
    tracklet_props: dict[int, dict[str, dict[str, Any]]] = {}

    for _, data in G.nodes(data=True):
        track_id = data[attribute_name]
        if track_id not in tracklet_props:
            tracklet_props[track_id] = {}
            tracklet_graph.add_node(track_id)

        for prop_name in prop_names:
            prop_value = data[prop_name]
            if prop_name not in tracklet_props[track_id]:
                tracklet_props[track_id][prop_name] = {
                    "min": prop_value,
                    "max": prop_value,
                }
            else:
                current_prop = tracklet_props[track_id][prop_name]
                current_prop["min"] = min(current_prop["min"], prop_value)
                current_prop["max"] = max(current_prop["max"], prop_value)

    for prop_name in prop_names:
        min_attrs = {
            tid: props[prop_name]["min"]
            for tid, props in tracklet_props.items()
            if prop_name in props
        }
        max_attrs = {
            tid: props[prop_name]["max"]
            for tid, props in tracklet_props.items()
            if prop_name in props
        }
        nx.set_node_attributes(
            tracklet_graph, min_attrs, name=f"{prop_name}_min"
        )
        nx.set_node_attributes(
            tracklet_graph, max_attrs, name=f"{prop_name}_max"
        )

    for u, v in G.edges():
        track_u = G.nodes[u][attribute_name]
        track_v = G.nodes[v][attribute_name]
        if track_u != track_v:
            tracklet_graph.add_edge(track_u, track_v)

    return tracklet_graph


################################################################################
################################################################################
