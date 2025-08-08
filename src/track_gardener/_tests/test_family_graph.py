from unittest.mock import Mock

from qtpy.QtCore import QPointF, Qt

from track_gardener.db.db_functions import get_tracks_nx_from_root
from track_gardener.db.db_model import TrackDB
from track_gardener.plots.lineage_plot_canvas import LineagePlotCanvas


def test_basic_lineage_plot_canvas(db_session):
    """
    Test creation of the family graph based on the test database.
    """

    track_id = 225
    track_descendant = 227

    t = get_tracks_nx_from_root(db_session, track_id)

    print(f"Nodes in tree: {t.nodes}")
    print(f"Edges in tree: {t.edges}")

    # basic test to check if the tree contains the expected node
    assert (
        track_descendant in t.nodes
    ), f"Expected to get a tree containing node {track_descendant}"

    assert (
        t.nodes[track_id]["start"] == 0
    ), f"Expected to get a tree containing node {track_id} with start time 0"

    # test that reingold-tilford tree layout is working
    # assert (
    #     t.nodes[track_id]["y"] == 0.5
    # ), f"Expected to get a tree containing node {track_id} with y-coordinate 0.5"


def test_generating_tree_upon_selection(viewer, db_session):
    """
    Test generating a tree upon selecting a new object.
    """

    track_id = 204
    track_descendant = 211

    lineage_plot_canvas = LineagePlotCanvas(viewer, db_session)

    viewer.layers["Labels"].selected_label = track_id

    assert (
        lineage_plot_canvas.tree is not None
    ), "Expected to get a tree after selecting a new object."

    assert (
        track_descendant in lineage_plot_canvas.tree.nodes
    ), f"Expected to get a tree containing node {track_descendant}"


def test_selection_of_track(viewer, db_session):
    """
    Test selecting a track in the family graph.
    """

    track_id = 204

    lineage_plot_canvas = LineagePlotCanvas(viewer, db_session)

    viewer.layers["Labels"].selected_label = track_id

    # Assert the expected outcome
    expected_label = track_id
    assert (
        lineage_plot_canvas.labels.selected_label == expected_label
    ), f"Expected to select track {expected_label}, got {lineage_plot_canvas.labels.selected_label}"

    # Set up a mock event with proper coordinate translation
    vb = lineage_plot_canvas.plot_view.vb

    # Desired data coordinates
    data_x, data_y = 10, -0.8
    expected_label = 207

    # Translate data coordinates into scene coordinates
    scene_point = vb.mapViewToScene(QPointF(data_x, data_y))

    # Create a mock event at the translated scene coordinates
    mock_event = Mock()
    mock_event.scenePos = Mock(return_value=scene_point)
    mock_event.button = Mock(return_value=Qt.LeftButton)  # Left mouse button

    # Perform the click
    lineage_plot_canvas.on_mouse_click(mock_event)

    # Assert the expected outcome
    assert (
        lineage_plot_canvas.labels.selected_label == expected_label
    ), f"Expected to select track {expected_label}, got {lineage_plot_canvas.labels.selected_label}"


def test_selection_of_non_existant_track(viewer, db_session):
    """
    Test asking for a track that does not exist in the database.
    """

    # Retain reference to ensure it remains active
    lineage_plot_canvas = LineagePlotCanvas(viewer, db_session)  # noqa: F841

    viewer.layers["Labels"].selected_label = 777

    # Assert the expected outcome
    expected_status = "Error - no such label in the database."
    assert (
        viewer.status == expected_status
    ), f"Expected status to be {expected_status}, got {viewer.status}"


def test_change_track_status(viewer, db_session):
    """
    Test changing the status of a track in the family graph with a right click.
    """
    lineage_plot_canvas = LineagePlotCanvas(viewer, db_session)

    viewer.layers["Labels"].selected_label = 204

    # Set up a mock event with proper coordinate translation
    vb = lineage_plot_canvas.plot_view.vb

    # Desired data coordinates
    data_x, data_y = 10, -0.5

    # Translate data coordinates into scene coordinates
    scene_point = vb.mapViewToScene(QPointF(data_x, data_y))

    # Create a mock event at the translated scene coordinates
    mock_event = Mock()
    mock_event.scenePos = Mock(return_value=scene_point)
    mock_event.button = Mock(return_value=Qt.RightButton)  # Left mouse button

    # Perform the click
    lineage_plot_canvas.on_mouse_click(mock_event)

    # Assert the expected outcome
    expected_status = True
    track = db_session.query(TrackDB).filter_by(track_id=207).all()[0]

    assert (
        track.accepted_tag == expected_status
    ), f"Expected track status to be {expected_status}, got {track.accepted_tag}"
