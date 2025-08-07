from unittest.mock import Mock

import numpy as np

from track_gardener.widgets.widget_navigation import TrackNavigationWidget


def test_select_label(qtbot, viewer, db_session):
    """
    Test selection of a cell with a right click.
    """

    track_navigation_widget = TrackNavigationWidget(viewer, db_session)

    # position for a cell to test selection
    pos = (22, 60, 60)
    viewer.dims.set_point(0, pos[0])

    # set corner pixels for the image layer
    rad = 20
    viewer.layers[0].corner_pixels = np.array(
        [[0, pos[0] - rad, pos[1] - rad], [0, pos[0] + rad, pos[1] + rad]]
    )

    viewer.cursor.position = pos
    # create mock event objects
    event = Mock()
    event.button = 2  # Right mouse button
    event.position = pos

    track_navigation_widget.select_label(viewer, event)

    # Check if the label was selected correctly
    expected_label = 207
    assert (
        track_navigation_widget.labels.selected_label == expected_label
    ), f"Expected label {expected_label}, but got {track_navigation_widget.labels.selected_label}"


def test_go_to_track_beginning(qtbot, viewer, db_session):
    """
    Test moving to the beginning of the track.
    """

    track_navigation_widget = TrackNavigationWidget(viewer, db_session)

    qtbot.addWidget(track_navigation_widget)

    # set viewer position to 10
    viewer.dims.set_point(0, 10)

    # select active track
    track_navigation_widget.labels.selected_label = 227

    # Simulate clicking the "start track" button
    track_navigation_widget.start_track_function()
    # qtbot.mouseClick(track_navigation_widget.start_track_btn, Qt.LeftButton)

    assert viewer.dims.current_step[0] == 6


def test_go_to_track_end(qtbot, viewer, db_session):
    """
    Test moving to the end of the track.
    """

    track_navigation_widget = TrackNavigationWidget(viewer, db_session)

    qtbot.addWidget(track_navigation_widget)

    # set viewer position to 10
    viewer.dims.set_point(0, 10)

    # select active track
    track_navigation_widget.labels.selected_label = 228

    # Simulate clicking the "start track" button
    track_navigation_widget.end_track_function()

    assert viewer.dims.current_step[0] == 36


def test_center_on_cell(qtbot, viewer, db_session):
    """
    Test that the viewer centers on cell when requested.
    """

    track_navigation_widget = TrackNavigationWidget(viewer, db_session)

    qtbot.addWidget(track_navigation_widget)

    # set viewer position to 28
    viewer.dims.set_point(0, 28)

    # select active track
    track_navigation_widget.labels.selected_label = 227

    # test of default which is following the selected cell
    np.testing.assert_allclose(
        viewer.camera.center, (0.0, 92, 107)
    ), f"Expected camera position (0.0, 93, 107) but instead {viewer.camera.center}."

    # test upon changing frame
    viewer.dims.set_point(0, 30)
    np.testing.assert_allclose(
        viewer.camera.center, (0.0, 89, 104)
    ), f"Expected camera position (0.0, 89, 104) but instead {viewer.camera.center}."

    # test upon unclicking following
    track_navigation_widget.follow_object_checkbox.setChecked(False)
    viewer.dims.set_point(0, 15)
    np.testing.assert_allclose(
        viewer.camera.center, (0.0, 89, 104)
    ), f"Expected camera position (0.0, 91, 108) but instead {viewer.camera.center}."

    # test upon clicking centering
    track_navigation_widget.center_object_function()
    np.testing.assert_allclose(
        viewer.camera.center, (0.0, 96, 104)
    ), f"Expected camera position (0.0, 96, 104) but instead {viewer.camera.center}."

    # test upon activating following
    viewer.dims.set_point(0, 30)
    track_navigation_widget.follow_object_checkbox.setChecked(True)
    np.testing.assert_allclose(
        viewer.camera.center, (0.0, 89, 104)
    ), f"Expected camera position (0.0, 89, 104) but instead {viewer.camera.center}."


def test_center_on_cell_no_selection(qtbot, viewer, db_session):
    """
    Test that the viewer centers on cell when requested.
    """

    track_navigation_widget = TrackNavigationWidget(viewer, db_session)

    qtbot.addWidget(track_navigation_widget)

    # set viewer position to 10
    viewer.dims.set_point(0, 10)

    # select background
    track_navigation_widget.labels.selected_label = 0
    center_before = viewer.camera.center

    # center
    track_navigation_widget.center_object_function()
    center_after = viewer.camera.center

    # assert no movement
    assert (
        center_before == center_after
    ), f"Expected camera position {center_before} but instead {center_after}."


def test_center_on_cell_beyond_track(qtbot, viewer, db_session):
    """
    Test that the viewer centers on cell when requested.
    """

    track_navigation_widget = TrackNavigationWidget(viewer, db_session)

    qtbot.addWidget(track_navigation_widget)

    # select background
    track_navigation_widget.labels.selected_label = 227

    # set viewer position to 10
    viewer.dims.set_point(0, 44)
    # center
    track_navigation_widget.center_object_function()

    # assert change of the frame
    assert viewer.dims.current_step[0] == 39
    # assert proper position
    np.testing.assert_allclose(viewer.camera.center, (0.0, 100, 114))

    # set viewer position to 10
    viewer.dims.set_point(0, 0)

    # center
    track_navigation_widget.center_object_function()

    # assert change of the frame
    assert viewer.dims.current_step[0] == 6
    # assert proper position
    np.testing.assert_allclose(viewer.camera.center, (0.0, 91, 95))


def test_build_labels_too_many(qtbot, viewer, db_session):
    """
    Test situation with too many labels.
    """

    track_navigation_widget = TrackNavigationWidget(viewer, db_session)

    qtbot.addWidget(track_navigation_widget)

    # change query limit to low value
    track_navigation_widget.query_lim = 2

    # trigger update
    viewer.dims.set_point(0, 40)

    # ensure that labels are empty
    assert (
        np.max(viewer.layers["Labels"].data) == 0
    ), f'Expected no labels, instead get max label {np.max(viewer.layers["Labels"].data)}'
