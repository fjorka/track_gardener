import os

import pytest
from qtpy.QtWidgets import QTabWidget

from track_gardener.config.models import Graph
from track_gardener.widgets.widget_main import TrackGardener


def test_main_creates_tabs(viewer):
    """
    Test that the main widget opens a tab widget.
    """

    main_widget = TrackGardener(viewer)

    assert (main_widget.findChildren(QTabWidget) is not None) and (
        len(main_widget.findChildren(QTabWidget)) == 1
    ), f"Expected to find one tab widget, instead got {main_widget.findChildren(QTabWidget)}"


def test_adding_widgets(viewer, db_session):
    """
    Test adding of the widgets.
    """

    main_widget = TrackGardener(viewer)

    # test creating widgets
    ch_list = []
    ch_names = []
    signal_list = []
    graph_list = [
        Graph(
            name="DHB Signals",
            signals=["ch0_nuc", "ch0_cyto"],
            colors=["yellow", "green"],
        )
    ]

    cell_tags = {}

    main_widget.create_widgets(
        viewer,
        db_session,
        ch_list=ch_list,
        ch_names=ch_names,
        signal_list=signal_list,
        graph_list=graph_list,
        cell_tags=cell_tags,
        signal_function=None,
    )

    assert (
        main_widget.navigation_widget is not None
    ), "Expected to find a navigation widget, instead got None"
    assert (
        main_widget.modification_widget is not None
    ), "Expected to find a modification widget, instead got None"
    assert (
        len(main_widget.napari_widgets) == 2
    ), f"Expected to create 2 graph widgets, instead got {len(main_widget.napari_widgets)}"


@pytest.mark.xfail(
    os.environ.get("CI") == "true",
    reason="Known teardown bug with pyqtgraph LabelItem on CI: https://github.com/pyqtgraph/pyqtgraph/issues/472",
)
def test_clearing_widgets(viewer, db_session):
    """
    Test clearing of the widgets.
    """

    main_widget = TrackGardener(viewer)

    # test creating widgets
    ch_list = []
    ch_names = []
    signal_list = []
    graph_list = [
        Graph(
            name="DHB Signals",
            signals=["ch0_nuc", "ch0_cyto"],
            colors=["yellow", "green"],
        )
    ]
    cell_tags = {}

    main_widget.create_widgets(
        viewer,
        db_session,
        ch_list=ch_list,
        ch_names=ch_names,
        signal_list=signal_list,
        graph_list=graph_list,
        cell_tags=cell_tags,
        signal_function=None,
    )

    # assert that the widgets are added
    assert (
        len(main_widget.napari_widgets) == 2
    ), f"Expected to have 2 graphs, instead got {main_widget.napari_widgets}"

    # run cleaning function
    main_widget.clear_widgets()

    # assert that the widgets are cleared
    assert (
        len(main_widget.napari_widgets) == 0
    ), f"Expected to have 0 graphs, instead got {main_widget.napari_widgets}"
