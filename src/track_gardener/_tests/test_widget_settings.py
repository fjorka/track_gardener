from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
from qtpy.QtWidgets import QPushButton

from ..config.models import SignalChannel
from ..config.pipeline import load_and_validate_config
from ..widgets.widget_settings import SettingsWidget


def test_open_yaml_dialog(viewer, mocker):
    """
    Test that the dialog to select a file opens.
    """
    set_widget = SettingsWidget(viewer)
    mock_config_object = MagicMock()
    mock_loaded_funcs = {"some_func": MagicMock()}  # A dummy dictionary

    mock_getOpenFileName = mocker.patch(
        "qtpy.QtWidgets.QFileDialog.getOpenFileName",
        return_value=("test.yaml", None),
    )
    mock_loader = mocker.patch(
        "track_gardener.widgets.widget_settings.load_and_validate_config",
        return_value=(mock_config_object, mock_loaded_funcs),
    )
    load_config_file_mock = mocker.patch(
        "track_gardener.widgets.widget_settings.SettingsWidget.load_config"
    )
    reorganize_mock = mocker.patch(
        "track_gardener.widgets.widget_settings.SettingsWidget.clean_and_load_experiment"
    )

    set_widget.open_file_dialog()

    mock_getOpenFileName.assert_called_once()
    mock_loader.assert_called_once_with("test.yaml")
    load_config_file_mock.assert_called_once()
    reorganize_mock.assert_called_once()


def test_experiment_loading(viewer, mocker):
    """
    Test that given 2 arrays, the proper number of layers is created.
    Mocks directly da.from_zarr to avoid loading actual data.
    """
    set_widget = SettingsWidget(viewer)

    # why, oh why do you need to be cleaned just after being born?
    set_widget.clean_interface()

    set_widget.channels_list = [
        SignalChannel(name="test1", lut="green", path="test1.zarr"),
        SignalChannel(name="test2", lut="blue", path="test2.zarr"),
    ]
    set_widget.labels_settings = {}

    mock_load_zarr = mocker.patch(
        "track_gardener.widgets.widget_settings.SettingsWidget.load_zarr"
    )
    mock_load_zarr.return_value = np.zeros((1, 10, 10))

    set_widget.load_layers()

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
    set_widget.clean_interface()

    set_widget.channels_list = [
        SignalChannel(name="test1", lut="green", path="test1.zarr"),
        SignalChannel(name="test2", lut="blue", path="test2.zarr"),
    ]
    set_widget.labels_settings = {}

    mock_load_zarr = mocker.patch(
        "track_gardener.widgets.widget_settings.SettingsWidget.load_zarr"
    )
    mock_load_zarr.return_value = [np.zeros((1, 10, 10)), np.zeros((1, 5, 5))]

    set_widget.load_layers()

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
    config, funcs = load_and_validate_config(config_path)
    set_widget.load_config(config, funcs)

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
        viewer.window.dock_widgets.keys()
    ), f"Expected a new graph widget to be added, but widgets are {list(viewer.window._dock_widgets.keys())}"


def test_reorg_widgets(viewer, mocker):
    """
    Test reorganizing widgets upon exp loading.
    """
    set_widget = SettingsWidget(viewer)

    mock_load_exp = mocker.patch(
        "track_gardener.widgets.widget_settings.SettingsWidget.load_layers"
    )
    mock_load_track = mocker.patch(
        "track_gardener.widgets.widget_settings.SettingsWidget.load_tracking"
    )

    set_widget.clean_and_load_experiment()

    assert mock_load_exp.called, "load_layers method should have been called"
    assert (
        mock_load_track.called
    ), "load_tracking method should have been called"

    push_buttons_in_settings = [
        x.text() for x in set_widget.findChildren(QPushButton)
    ]
    assert (
        "Add graph" in push_buttons_in_settings
    ), f'Expected "Add graph" button to be in the settings window, instead buttons: {push_buttons_in_settings}'
