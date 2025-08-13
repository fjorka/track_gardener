import networkx as nx
import pytest

from ..converters.nx_tracks_functions import (
    assign_tracklet_ids,
    build_tracklet_graph,
)

################################################################################
################################################################################
# tests for assign_tracklet_ids function


def test_linear_forest():
    """
    Tests two disconnected chains: A->B and X->Y.
    This should succeed as it processes components independently.
    """
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("X", "Y")])

    assign_tracklet_ids(G)

    for g in G.nodes:
        assert G.nodes[g]["tracklet_id"] is not None

    assert G.nodes["A"]["tracklet_id"] == G.nodes["B"]["tracklet_id"]
    assert G.nodes["X"]["tracklet_id"] == G.nodes["Y"]["tracklet_id"]
    assert G.nodes["A"]["tracklet_id"] != G.nodes["X"]["tracklet_id"]


def test_simple_split():
    """
    Tests a split: A -> B, A -> C.
    """
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("A", "C")])

    assign_tracklet_ids(G)

    for g in G.nodes:
        assert G.nodes[g]["tracklet_id"] is not None

    assert (
        G.nodes["A"]["tracklet_id"]
        != G.nodes["B"]["tracklet_id"]
        != G.nodes["C"]["tracklet_id"]
    )


def test_split_extended():
    """
    Tests a split: A -> B, A -> C.
    """
    G = nx.DiGraph()
    G.add_edges_from([("X", "A"), ("A", "B"), ("A", "C")])

    assign_tracklet_ids(G)

    for g in G.nodes:
        assert G.nodes[g]["tracklet_id"] is not None

    assert (
        G.nodes["A"]["tracklet_id"]
        != G.nodes["B"]["tracklet_id"]
        != G.nodes["C"]["tracklet_id"]
    )
    assert G.nodes["A"]["tracklet_id"] == G.nodes["X"]["tracklet_id"]


def test_simple_merge():
    """
    Tests a split: A -> B, C -> B.
    """
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("C", "B")])

    assign_tracklet_ids(G)

    for g in G.nodes:
        assert G.nodes[g]["tracklet_id"] is not None

    assert (
        G.nodes["A"]["tracklet_id"]
        != G.nodes["B"]["tracklet_id"]
        != G.nodes["C"]["tracklet_id"]
    )


def test_merge_extended():
    """
    Tests a split: A -> B, C -> B, B -> D.
    """
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("C", "B"), ("B", "D")])

    assign_tracklet_ids(G)

    for g in G.nodes:
        assert G.nodes[g]["tracklet_id"] is not None

    assert (
        G.nodes["A"]["tracklet_id"]
        != G.nodes["B"]["tracklet_id"]
        != G.nodes["C"]["tracklet_id"]
    )
    assert G.nodes["B"]["tracklet_id"] == G.nodes["D"]["tracklet_id"]


def test_double_split():
    """
    Tests a split: A -> B, A -> C, C -> D, C -> E.
    """
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("A", "C"), ("C", "D"), ("C", "E")])

    assign_tracklet_ids(G)

    for g in G.nodes:
        assert G.nodes[g]["tracklet_id"] is not None

    tracklet_ids = {G.nodes[g]["tracklet_id"] for g in G.nodes}
    assert len(tracklet_ids) == len(set(tracklet_ids))


def test_double_merge():
    """
    Tests a split: A -> B, C -> B, C -> D, C -> E.
    """
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("C", "B"), ("B", "D"), ("E", "D")])

    assign_tracklet_ids(G)

    for g in G.nodes:
        assert G.nodes[g]["tracklet_id"] is not None

    tracklet_ids = {G.nodes[g]["tracklet_id"] for g in G.nodes}
    assert len(tracklet_ids) == len(set(tracklet_ids))


################################################################################
################################################################################
# tests for build_tracklet_graph function


@pytest.fixture
def sample_graph_and_tracklet_graph():
    r"""Pytest fixture to create a sample graph and its corresponding tracklet graph.
        [Tracklet 0]
        +--------+
        | Node 0 | t=10
        +--------+
                |
                v
        +--------+
        | Node 1 | t=11  (Split)
        +--------+
        /        \
        /          \
        v            v
    [Tracklet 1]    [Tracklet 2]
    +--------+      +--------+
    | Node 2 | t=12 | Node 4 | t=12
    +--------+      +--------+
        |              |
        v              |
    +--------+          |
    | Node 3 | t=14     |
    +--------+          |
        \            /
        \          /
            v        v
        [Tracklet 3] (Merge)
        +--------+
        | Node 5 | t=15
        +--------+
                |
                v
        +--------+
        | Node 6 | t=16
        +--------+
    """

    G = nx.DiGraph()

    # Tracklet 0 (Root) -> splits into 1 and 2
    G.add_node(0, tracklet_id=0, t=10)
    G.add_node(1, tracklet_id=0, t=11)

    # Tracklet 1 (Branch A)
    G.add_node(2, tracklet_id=1, t=12)
    G.add_node(3, tracklet_id=1, t=14)

    # Tracklet 2 (Branch B)
    G.add_node(4, tracklet_id=2, t=12)

    # Tracklet 3 (Merges from 1 and 2)
    G.add_node(5, tracklet_id=3, t=15)
    G.add_node(6, tracklet_id=3, t=16)

    # Edges
    G.add_edges_from([(0, 1), (1, 2), (1, 4), (3, 5), (4, 5), (5, 6)])

    # The expected tracklet graph derived from G
    tracklet_graph = build_tracklet_graph(
        G, attribute_name="tracklet_id", prop_names=["t"]
    )
    return G, tracklet_graph


def test_build_tracklet_graph_nodes(sample_graph_and_tracklet_graph):
    """Test if the tracklet graph has the correct nodes and attributes."""
    _, tracklet_graph = sample_graph_and_tracklet_graph

    assert set(tracklet_graph.nodes()) == {0, 1, 2, 3}

    # Check attributes for tracklet 0 (root)
    assert tracklet_graph.nodes[0]["t_min"] == 10
    assert tracklet_graph.nodes[0]["t_max"] == 11

    # Check attributes for tracklet 1 (branch)
    assert tracklet_graph.nodes[1]["t_min"] == 12
    assert tracklet_graph.nodes[1]["t_max"] == 14

    # Check attributes for tracklet 3 (merged)
    assert tracklet_graph.nodes[3]["t_min"] == 15
    assert tracklet_graph.nodes[3]["t_max"] == 16


def test_build_tracklet_graph_edges(sample_graph_and_tracklet_graph):
    """Test if the tracklet graph has the correct edges."""
    _, tracklet_graph = sample_graph_and_tracklet_graph
    expected_edges = {(0, 1), (0, 2), (1, 3), (2, 3)}
    assert set(tracklet_graph.edges()) == expected_edges


def test_no_feature():
    """
    Test creating a tracklet graph with no features.
    """
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("B", "C")])
    for node in G.nodes:
        G.nodes[node]["tracklet_id"] = 1
        G.nodes[node]["t"] = 0

    tracklet_graph = build_tracklet_graph(G)
    assert len(tracklet_graph.nodes) == 1
    for node in tracklet_graph.nodes:
        assert "t_min" not in tracklet_graph.nodes[node]
        assert "t_max" not in tracklet_graph.nodes[node]
