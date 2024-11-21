from qtpy.QtGui import QColor

from track_gardener.widget.signal_graph_widget import CellGraphWidget


def test_init_signal_graph(viewer, db_session):
    """
    Test signal graph initialization.
    """

    signal_graph = CellGraphWidget(
        napari_viewer=viewer, sql_session=db_session, signal_list=["Area"]
    )

    # assert the widget calling the graph
    assert signal_graph.graph is not None


def test_color_menu(viewer, db_session):
    """
    Test opening of the color menu after clicking a color button.
    """

    signal_graph = CellGraphWidget(
        napari_viewer=viewer, sql_session=db_session, signal_list=["Area"]
    )
    button = signal_graph.createColorButton()

    assert callable(button.clicked)


def test_selectColor_valid_color(viewer, db_session, mocker):
    """
    Test changing button color upon selection.
    """

    signal_graph = CellGraphWidget(
        napari_viewer=viewer, sql_session=db_session, signal_list=["Area"]
    )
    button = signal_graph.createColorButton()

    mocker.patch(
        "qtpy.QtWidgets.QColorDialog.getColor", return_value=QColor("#FF0000")
    )
    signal_graph.selectColor(button)
    assert "background-color: #ff0000" in button.styleSheet()


def test_adding_row(viewer, db_session):
    """
    Test adding a new row to the graph.
    """

    # check that default is created with a single row of buttons
    signal_graph = CellGraphWidget(
        napari_viewer=viewer,
        sql_session=db_session,
        signal_list=["Area"],
        signal_sel_list=["Area"],
        color_sel_list=["white"],
    )
    assert len(signal_graph.layout()) == 2

    # add a new row and assert the number of buttons
    signal_graph.addRowButton(
        button=signal_graph.layout().itemAt(1).layout().itemAt(2)
    )
    assert len(signal_graph.layout()) == 3

    # remove row button
    signal_graph.removeRowButton(
        button=signal_graph.layout().itemAt(1).layout().itemAt(3)
    )
    assert len(signal_graph.layout()) == 2


def test_status_last_row(viewer, db_session):
    """
    Test that last row has disabled button for removing rows.
    """

    signal_graph = CellGraphWidget(
        napari_viewer=viewer,
        sql_session=db_session,
        signal_list=["Area"],
        signal_sel_list=["Area"],
        color_sel_list=["white"],
    )
    org_last_row = signal_graph.layout().itemAt(1)

    assert (
        not org_last_row.layout().itemAt(3).widget().isEnabled()
    ), "Expected last row to have disabled remove button"

    # add new row and check that the original last row now has enabled remove button
    signal_graph.addRowButton()
    assert (
        org_last_row.layout().itemAt(3).widget().isEnabled()
    ), "Expected the original last row to have enabled remove button now after adding a new row."


def test_wrong_init(viewer, db_session):
    """
    Test init with mismatched lists
    """

    signal_graph = CellGraphWidget(  # noqa: F841
        napari_viewer=viewer,
        sql_session=db_session,
        signal_list=[],
        signal_sel_list=["Area"],
        color_sel_list=["white", "red"],
    )

    expected_status = "Signal list and color list have different lengths."

    assert (
        viewer.status == expected_status
    ), f"Expected status to be {expected_status}, got {viewer.status}"
