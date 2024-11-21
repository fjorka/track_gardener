from unittest.mock import Mock

import pyqtgraph as pg
from qtpy.QtCore import QPointF, Qt

import track_gardener.db.db_functions as fdb
from track_gardener.graph.signal_graph import SignalGraph


def test_init_signal_graph(viewer, db_session):
    """
    Test signal graph initialization.
    """

    signal_graph = SignalGraph(viewer=viewer, session=db_session)

    assert signal_graph.legend_on
    assert signal_graph.signal_list is None
    assert signal_graph.color_list is None
    assert signal_graph.tag_dictionary == {}
    assert signal_graph.plot_view is not None


def test_time_line(viewer, db_session):
    """
    Test a time line to the signal graph.
    """

    signal_graph = SignalGraph(viewer=viewer, session=db_session)

    assert signal_graph.time_line is not None
    assert signal_graph.time_line.value() == viewer.dims.current_step[0]

    # move the slider of the viewer
    viewer.dims.set_point(0, 10)

    assert (
        signal_graph.time_line.value() == 10
    ), "Expected to get a time line at 10, instead got {signal_graph.time_line.value()}"


def test_mouse_click(viewer, db_session):
    """
    Test mouse click event on the signal graph.
    """

    signal_graph = SignalGraph(viewer=viewer, session=db_session)

    # set up a mock event

    # Set up a mock event with proper coordinate translation
    vb = signal_graph.plot_view.vb

    # Desired data coordinates
    data_x, data_y = 20, 0.0

    # Translate data coordinates into scene coordinates
    scene_point = vb.mapViewToScene(QPointF(data_x, data_y))

    # Create a mock event at the translated scene coordinates
    mock_event = Mock()
    mock_event.scenePos = Mock(return_value=scene_point)
    mock_event.button = Mock(return_value=Qt.LeftButton)  # Left mouse button

    signal_graph.onMouseClick(mock_event)

    # assert position of the line
    assert (
        signal_graph.time_line.value() == data_x
    ), f"Expected to get a time line at {data_x}, instead got {signal_graph.time_line.value()}"

    # assert position of the viewer
    assert (
        viewer.dims.current_step[0] == data_x
    ), f"Expected to get a viewer at {data_x}, instead got {viewer.dims.current_step[0]}"


def test_ploting_cell(viewer, db_session):
    """
    Test plotting a cell on the signal graph.
    """

    signal_graph = SignalGraph(
        viewer=viewer,
        session=db_session,
        selected_signals=["area"],
        color_list=["red"],
    )

    viewer.layers["Labels"].selected_label = 37401

    assert (
        signal_graph.query is not None
    ), "Expected to get a query after selecting a new object."


def test_plotting_non_existent_cell(viewer, db_session):
    """
    Test plotting a non-existent cell on the signal graph.
    """

    signal_graph = SignalGraph(  # noqa: F841
        viewer=viewer,
        session=db_session,
        selected_signals=["area"],
        color_list=["red"],
    )

    viewer.layers["Labels"].selected_label = 777

    expected_status = "Error - no such label in the database."

    assert (
        viewer.status == expected_status
    ), f"Expected status to be {expected_status}, got {viewer.status}"


def test_using_tags(viewer, db_session):
    """
    Test using tags on the signal graph.
    """

    signal_graph = SignalGraph(
        viewer=viewer,
        session=db_session,
        selected_signals=["area"],
        color_list=["red"],
        tag_dictionary={"apoptosis": "A"},
    )

    active_cell = 37401
    frame = 30
    annotation = "apoptosis"

    # add annotation to the cell
    _ = fdb.tag_cell(db_session, active_cell, frame, annotation)

    # select the cell
    viewer.layers["Labels"].selected_label = active_cell

    # assert the tag is printed on the graph
    text_items = [
        item
        for item in signal_graph.plot_view.items
        if isinstance(item, pg.TextItem)
    ]
    assert any(
        text_item.toPlainText() == "A" for text_item in text_items
    ), "Text 'A' not found in plot"
