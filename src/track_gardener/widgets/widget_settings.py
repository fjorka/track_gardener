"""A napari widget for loading and managing tracking experiment configurations.

This module defines the `SettingsWidget`, which serves as the primary user
interface for initiating a tracking session. It provides controls to load a
YAML configuration file, which specifies paths to image data and the tracking
database. Upon loading, this widget orchestrates the setup of the napari
environment by clearing old data, loading new image and label layers,
establishing a database connection, and triggering the creation of all other
interactive widgets for curation and visualization.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import dask.array as da
import napari
import numpy as np
import zarr
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtGui import QPixmap
from qtpy.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import track_gardener.db.db_functions as fdb
from track_gardener.config.exceptions import (
    ConfigEnvironmentError,
    ConfigFormatError,
)
from track_gardener.config.models import TrackGardenerConfig
from track_gardener.config.pipeline import load_and_validate_config
from track_gardener.signals.factory import (
    create_calculate_signals_function,
)
from track_gardener.widgets.widget_signal_plot_controller import (
    SignalPlotControlPanel,
)

if TYPE_CHECKING:
    from napari.viewer import Viewer


class SettingsWidget(QWidget):
    """A widget for loading and managing tracking experiment settings.

    This widget provides the UI for loading a YAML configuration file, which
    defines the experiment data, database path, and visualization settings.
    It handles loading data into napari and triggering the creation of
    other interactive widgets.
    """

    def __init__(
        self,
        viewer: "Viewer",
        create_widgets_callback: Callable | None = None,
        clear_widgets_callback: Callable | None = None,
    ) -> None:
        """Initializes the SettingsWidget.

        Args:
            viewer (Viewer): The napari viewer instance.
            create_widgets_callback (Optional[Callable]): Callback to create
                the tracking widgets. Defaults to None.
            clear_widgets_callback (Optional[Callable]): Callback to clear
                the tracking widgets. Defaults to None.
        """

        super().__init__()

        self.viewer = viewer
        self.create_widgets_callback = create_widgets_callback
        self.clear_widgets_callback = clear_widgets_callback
        self.added_widgets = []

        self.setStyleSheet(napari.qt.get_stylesheet(theme_id="dark"))

        self.mWidget = self.create_main_widget()
        self.mWidget.layout().setAlignment(Qt.AlignTop)

        self.setLayout(QVBoxLayout())
        self.layout().setAlignment(Qt.AlignTop)
        self.layout().addWidget(self.mWidget)

    def create_main_widget(self) -> QWidget:
        """Creates the main container widget for the settings tab.

        Returns:
            QWidget: The main widget containing the logo and load button.
        """

        widget = QWidget()
        widget.setLayout(QGridLayout())
        widget.layout().setAlignment(Qt.AlignTop)

        self.logo_widget = self.create_logo_widget()

        btn_load = QtWidgets.QPushButton("Load Tracking")
        btn_load.clicked.connect(self.open_file_dialog)

        widget.layout().addWidget(self.logo_widget, 0, 0)
        widget.layout().addWidget(btn_load, 1, 0)

        self.widget_line = 2

        return widget

    def create_logo_widget(self) -> QWidget:
        """Creates a widget to display the TrackGardener logo.

        Returns:
            QWidget: A widget containing the centered logo image.
        """

        # get logo image
        logo_path = (
            Path(__file__).parent.parent
            / "icons"
            / "track_gardener_logo_transparent.png"
        )
        # logo_path = r'../icons/track_gardener_logo.png'
        logo = QPixmap(str(logo_path))

        logo_label = QLabel()
        logo_label.setPixmap(logo)
        logo_label.setMaximumHeight(300)
        logo_label.setMaximumWidth(300)
        logo_label.setScaledContents(True)

        sp1 = QWidget()
        sp1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        sp2 = QWidget()
        sp2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        widget = QWidget()
        widget.setLayout(QHBoxLayout())
        widget.layout().setAlignment(Qt.AlignTop)
        widget.layout().addWidget(sp1)
        widget.layout().addWidget(logo_label)
        widget.layout().addWidget(sp2)

        return widget

    def open_file_dialog(self) -> None:
        """Opens a file dialog to select and load a YAML configuration file."""

        options = QtWidgets.QFileDialog.Options()
        fileName, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "QFileDialog.getOpenFileName()",
            "",
            "YAML Files (*.yaml);;All Files (*)",
            options=options,
        )
        if fileName:

            # test if the config file is correct
            self.viewer.status = "Checking the config file..."
            try:
                config_obj, loaded_functions = load_and_validate_config(
                    fileName
                )
                self.load_config(config_obj, loaded_functions)
                self.clean_and_load_experiment()

            except (ConfigFormatError, ConfigEnvironmentError) as e:

                msgBox = QtWidgets.QMessageBox(self.viewer.window._qt_window)
                msgBox.setText(str(e))
                msgBox.exec()

    def clean_interface(self) -> None:
        """Clears all widgets and resets the main widget layout."""

        # clear main widgets
        if self.clear_widgets_callback is not None:
            self.clear_widgets_callback()

        # remove 'Add Graph' button
        if len(self.added_widgets) > 0:
            self.added_widgets[0].hide()
            self.mWidget.layout().removeWidget(self.added_widgets[0])

        self.added_widgets = []

        self.viewer.layers.events.removed.disconnect(self.clean_interface)
        self.viewer.layers.clear()

    def clean_and_load_experiment(self) -> None:
        """Clears old widgets and loads the new experiment and tracking data."""

        self.clean_interface()

        self.load_layers()
        self.load_tracking()

        # display load widgets button
        pb = QPushButton("Add graph")
        pb.clicked.connect(self.add_new_graph_widget)
        self.added_widgets.append(pb)
        self.mWidget.layout().addWidget(pb, self.widget_line, 0)
        self.widget_line += 1

    def load_config(
        self,
        config: TrackGardenerConfig,
        loaded_functions: dict[str | tuple, Callable],
    ) -> None:
        """Loads the configuration from a TrackGardenerConfig object.

        Args:
            config (TrackGardenerConfig): The configuration object to load.
        """

        self.experiment_name = config.experiment_settings.experiment_name
        self.experiment_description = (
            config.experiment_settings.description or ""
        )
        self.database_path = str(config.database.path)
        self.channels_list = config.signal_channels
        self.graphs_list = config.graphs or []
        self.cell_tags = config.cell_tags or {}
        self.labels_settings = config.labels_settings or {}
        self.signal_function = create_calculate_signals_function(
            config, loaded_functions
        )

    def load_zarr(self, channel_path: str) -> list[da.Array]:
        """Loads data from a zarr store.

        Handles both single-scale and multi-scale zarr arrays.

        Args:
            channel_path (str): The path to the zarr store.

        Returns:
            list[da.Array]: A list of dask arrays, one for each resolution level.
        """

        store = zarr.open(channel_path, mode="r")

        if isinstance(store, zarr.Group):

            # check number of levels
            root_group = zarr.open_group(channel_path, mode="r")
            levels_list = sorted([key for key in root_group if key.isdigit()])
            data = []
            for level in levels_list:
                data.append(da.from_zarr(channel_path, level))

        else:

            data = [da.from_zarr(channel_path)]

        return data

    def load_layers(self) -> None:
        """Loads experiment data (images, labels) into the napari viewer."""

        # load images
        self.channels_data_list = []
        for ch in self.channels_list:

            # get data from zarr
            # multiple arrays if multiscale
            data = self.load_zarr(ch.path)

            # necessary to send to the modification widget
            # to recalculate signals when object changes
            self.channels_data_list.append(data[0])

            # because napari cannot accept a single array within a list
            data_viewer = data[0] if len(data) == 1 else data

            self.viewer.add_image(
                data_viewer,
                name=ch.name,
                colormap=ch.lut,
                blending="additive",
                contrast_limits=ch.contrast_limits,
            )

        # ensure reset view
        self.viewer.reset_view()

        # add labels to the viewer
        empty_labels = np.zeros([1, 1], dtype=int)

        labels_layer = self.viewer.add_labels(
            empty_labels, name="Labels", metadata={"persistent_label": -1}
        )

        # set labels settings
        labels_layer.selected_label = 0
        if self.labels_settings:
            for key, value in self.labels_settings.items():
                # Check if the layer has this attribute to avoid errors from typos
                if hasattr(labels_layer, key):
                    setattr(labels_layer, key, value)
                else:
                    # Optionally, warn the user about an unknown setting
                    print(f"Warning: Ignoring unknown labels_setting '{key}'")

        # set viewer status
        self.viewer.status = "Experiment loaded"

        # clear widgets if labels are removed
        self.viewer.layers.events.removed.connect(self.clean_interface)

    def load_tracking(self) -> None:
        """Establishes the database connection and creates tracking widgets."""

        # establish connection to the database
        engine = create_engine(f"sqlite:///{self.database_path}")
        self.session = sessionmaker(bind=engine)()

        # get a list of signals
        self.signal_list = fdb.get_signals(self.session)

        # Trigger populating of tab2 in the main widget with tracking widgets
        ch_names = [ch.name for ch in self.channels_list]
        if self.create_widgets_callback is not None:
            self.create_widgets_callback(
                self.viewer,
                self.session,
                self.channels_data_list,
                ch_names,
                self.signal_list,
                self.graphs_list,
                self.cell_tags,
                self.signal_function,
            )

        self.viewer.status = "Tracking loaded"

    def add_new_graph_widget(self) -> None:
        """Creates a new SignalPlotControlPanel and adds it to the viewer."""

        graph_widget = SignalPlotControlPanel(
            self.viewer,
            self.session,
            self.signal_list,
            tag_dictionary=self.cell_tags,
        )

        self.viewer.window.add_dock_widget(
            graph_widget, area="bottom", name="New Graph"
        )

        self.added_widgets.append(graph_widget)
