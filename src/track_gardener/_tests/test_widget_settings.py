from pathlib import Path

import numpy as np
from qtpy.QtWidgets import QPushButton

from track_gardener.widget.widget_settings import SettingsWidget


def test_open_yaml_dialog(viewer, mocker):
    """
    Test that the dialog to select a file opens.
    """
    set_widget = SettingsWidget(viewer)

    mock_getOpenFileName = mocker.patch(
        "qtpy.QtWidgets.QFileDialog.getOpenFileName",
        return_value=("test.yaml", None),
    )
    validateConfigFile_mock = mocker.patch(
        "track_gardener.widget.widget_settings.validateConfigFile",
        return_value=(True, ""),
    )
    loadConfigFile_mock = mocker.patch(
        "track_gardener.widget.widget_settings.SettingsWidget.loadConfigFile"
    )
    reorganize_mock = mocker.patch(
        "track_gardener.widget.widget_settings.SettingsWidget.reorganizeWidgets"
    )

    set_widget.openFileDialog()

    mock_getOpenFileName.assert_called_once()
    validateConfigFile_mock.assert_called_once_with("test.yaml")
    loadConfigFile_mock.assert_called_once()
    reorganize_mock.assert_called_once()


def test_experiment_loading(viewer, mocker):
    """
    Test that given 2 arrays, the proper number of layers is created.
    Mocks directly da.from_zarr to avoid loading actual data.
    """
    set_widget = SettingsWidget(viewer)

    set_widget.channels_list = [{"path": "test1.zarr"}, {"path": "test2.zarr"}]
    set_widget.labels_settings = {}

    mock_load_zarr = mocker.patch(
        "track_gardener.widget.widget_settings.SettingsWidget.load_zarr"
    )
    mock_load_zarr.return_value = np.zeros((1, 10, 10))

    set_widget.loadExperiment()

    # test number of image layers
    layer_im_num = len([x for x in viewer.layers if x._type_string == "image"])
    assert layer_im_num == 2, f"Expected 2 image layers, got {layer_im_num}"

    # test number of labels layers
    layer_labels_num = len(
        [x for x in viewer.layers if x._type_string == "labels"]
    )
    assert (
        layer_labels_num == 1
    ), f"Expected 1 labels layers, got {layer_labels_num}"


def test_experiment_loading_multiscale(viewer, mocker):
    """
    Test that given 2 multiscale data sets, the proper number of layers is created.
    Mocks method load_zarr to return 2 arrays.
    """
    set_widget = SettingsWidget(viewer)

    set_widget.channels_list = [{"path": "test1.zarr"}, {"path": "test2.zarr"}]
    set_widget.labels_settings = {}

    mock_load_zarr = mocker.patch(
        "track_gardener.widget.widget_settings.SettingsWidget.load_zarr"
    )
    mock_load_zarr.return_value = [np.zeros((1, 10, 10)), np.zeros((1, 5, 5))]

    set_widget.loadExperiment()

    # test number of image layers
    layer_im_num = len([x for x in viewer.layers if x._type_string == "image"])
    assert layer_im_num == 2, f"Expected 2 image layers, got {layer_im_num}"

    # test number of labels layers
    layer_labels_num = len(
        [x for x in viewer.layers if x._type_string == "labels"]
    )
    assert (
        layer_labels_num == 1
    ), f"Expected 1 labels layers, got {layer_labels_num}"


def test_yaml_loading(viewer):
    """
    Test that yaml file is loaded properly.
    """
    set_widget = SettingsWidget(viewer)

    config_path = str(
        Path(__file__).parent / "fixtures" / "example_config.yaml"
    )
    set_widget.loadConfigFile(config_path)

    assert (
        set_widget.experiment_name == "Test experiment"
    ), f'Expected experiment name to be "Test experiment", got "{set_widget.experiment_name}"'


def test_add_graph(viewer, db_session):
    """
    Test adding a new graph.
    """
    set_widget = SettingsWidget(viewer)
    set_widget.viewer = viewer
    set_widget.session = db_session
    set_widget.signal_list = ["area"]
    set_widget.cell_tags = {"tag1": "t"}
    set_widget.napari_widgets = []

    set_widget.add_new_graph_widget()

    assert "New Graph" in list(
        viewer.window._dock_widgets.keys()
    ), f"Expected a new graph widget to be added, but widgets are {list(viewer.window._dock_widgets.keys())}"


def test_reorg_widgets(viewer, mocker):
    """
    Test reorganizing widgets upon exp loading.
    """
    set_widget = SettingsWidget(viewer)

    mock_load_exp = mocker.patch(
        "track_gardener.widget.widget_settings.SettingsWidget.loadExperiment"
    )
    mock_load_track = mocker.patch(
        "track_gardener.widget.widget_settings.SettingsWidget.loadTracking"
    )

    set_widget.reorganizeWidgets()

    assert (
        mock_load_exp.called
    ), "loadExperiment method should have been called"
    assert (
        mock_load_track.called
    ), "loadTracking method should have been called"

    push_buttons_in_settings = [
        x.text() for x in set_widget.findChildren(QPushButton)
    ]
    assert (
        "Add graph" in push_buttons_in_settings
    ), f'Expected "Add graph" button to be in the settings window, instead buttons: {push_buttons_in_settings}'
