from unittest.mock import Mock

from qtpy.QtCore import QPointF, Qt

from track_gardener.graph.family_graph import (
    FamilyGraphWidget,
    build_Newick_tree,
)


def test_basic_family_graph(db_session):
    """
    Test creation of the family graph based on the test database.
    """

    t = build_Newick_tree(db_session, 37401)

    print(f"Nodes in tree: {t.nodes}")
    print(f"Edges in tree: {t.edges}")

    # basic test to check if the tree contains the expected node
    assert 37403 in t.nodes, "Expected to get a tree containing node 37403"

    assert (
        t.nodes[37401]["start"] == 21.0
    ), "Expected to get a tree containing node 37401 with start time 21.0"

    # test that reingold-tilford tree layout is working
    assert (
        t.nodes[37401]["y"] == 0.5
    ), "Expected to get a tree containing node 37401 with y-coordinate 0.5"


def test_generating_tree_upon_selection(viewer, db_session):
    """
    Test generating a tree upon selecting a new object.
    """

    family_graph = FamilyGraphWidget(viewer, db_session)

    viewer.layers["Labels"].selected_label = 37401

    assert (
        family_graph.tree is not None
    ), "Expected to get a tree after selecting a new object."

    assert (
        37403 in family_graph.tree.nodes
    ), "Expected to get a tree containing node 37403"


def test_selection_of_track(viewer, db_session):
    """
    Test selecting a track in the family graph.
    """

    family_graph = FamilyGraphWidget(viewer, db_session)

    viewer.layers["Labels"].selected_label = 37401

    # Assert the expected outcome
    expected_label = 37401  # Replace with expected value for the mock setup
    assert (
        family_graph.labels.selected_label == expected_label
    ), f"Expected to select track {expected_label}, got {family_graph.labels.selected_label}"

    # Set up a mock event with proper coordinate translation
    vb = family_graph.plot_view.vb

    # Desired data coordinates
    data_x, data_y = 50, 0.0

    # Translate data coordinates into scene coordinates
    scene_point = vb.mapViewToScene(QPointF(data_x, data_y))

    # Create a mock event at the translated scene coordinates
    mock_event = Mock()
    mock_event.scenePos = Mock(return_value=scene_point)
    mock_event.button = Mock(return_value=Qt.LeftButton)  # Left mouse button

    # Perform the click
    family_graph.onMouseClick(mock_event)

    # Assert the expected outcome
    expected_label = 37402  # Replace with expected value for the mock setup
    assert (
        family_graph.labels.selected_label == expected_label
    ), f"Expected to select track {expected_label}, got {family_graph.labels.selected_label}"


def test_change_track_status(viewer, db_session):
    """
    Test changing the status of a track in the family graph with a right click.
    """
