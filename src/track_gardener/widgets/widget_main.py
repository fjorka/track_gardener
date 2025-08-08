"""The main napari widget for curating and visualizing cell tracking data.

This module defines the `TrackGardener` class, a QWidget that serves as the
main user interface for the plugin. It orchestrates the layout and interaction
of various sub-widgets for settings, navigation, track modification, and data
visualization, organizing them into a tabbed interface.
"""

from contextlib import suppress
from typing import TYPE_CHECKING, Any, Callable, Optional

import napari
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QGridLayout,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from track_gardener.plots.lineage_plot_canvas import LineagePlotCanvas
from track_gardener.widgets.widget_modifications import ModificationWidget
from track_gardener.widgets.widget_navigation import TrackNavigationWidget
from track_gardener.widgets.widget_settings import SettingsWidget
from track_gardener.widgets.widget_signal_plot_controller import (
    SignalPlotControlPanel,
)

if TYPE_CHECKING:
    from napari import Viewer
    from sqlalchemy.orm import Session


class TrackGardener(QWidget):
    """
    A napari widget for viewing and curating tracking data.

    This widget provides a tabbed interface for setting up a tracking session
    and interacting with the data through various sub-widgets.
    """

    def __init__(self, viewer: Optional["Viewer"] = None) -> None:
        """
        Initializes the TrackGardener widget.

        Args:
            viewer (Optional[Viewer]): The napari viewer instance. If None,
                the current viewer is retrieved using napari.current_viewer().
        """

        super().__init__()
        viewer = napari.current_viewer() if viewer is None else viewer
        self.viewer = viewer

        self.napari_widgets = []
        self.navigation_widget = None
        self.modification_widget = None

        self.setStyleSheet(napari.qt.get_stylesheet(theme_id="dark"))
        self.setLayout(QGridLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        # QTabwidget
        self.tabwidget = QTabWidget()

        # 1st tab
        self.settings_window = SettingsWidget(
            viewer, self.create_widgets, self.clear_widgets
        )
        self.tabwidget.addTab(self.settings_window, "settings")

        # 2nd tab (initially empty)
        self.tab2 = QWidget()
        self.tab2.setLayout(QVBoxLayout())
        self.tab2.layout().setContentsMargins(0, 0, 0, 0)
        self.tabwidget.addTab(self.tab2, "interact")

        # add tab widget to the layout
        self.layout().addWidget(self.tabwidget, 0, 0)

    def clear_widgets(self) -> None:
        """
        Removes all interactive widgets and disconnects event callbacks.

        This method cleans up the 'interact' tab and removes any dock widgets
        that were created during the session, effectively resetting the UI to
        its initial state. It also disconnects napari event listeners to
        prevent errors from lingering callbacks.
        """

        # remove graph widgets
        if len(self.napari_widgets) > 0:

            events_list = [
                self.viewer.camera.events.zoom,
                self.viewer.camera.events.center,
                self.viewer.layers["Labels"].events.visible,
                self.viewer.dims.events.current_step,
            ]
            callbacks_list = [
                self.navigation_widget.build_labels,
                self.navigation_widget.center_object_core_function,
            ]

            for event in events_list:
                for callback in callbacks_list:
                    with suppress(TypeError, ValueError):
                        event.disconnect(callback)

            for widget in self.napari_widgets:
                self.viewer.window.remove_dock_widget(widget)
            self.napari_widgets = []

            # remove added graphs
            if len(self.settings_window.added_widgets) > 1:
                for widget in self.settings_window.added_widgets[1:]:
                    self.viewer.window.remove_dock_widget(widget)

        # remove widgets from tab2
        if self.navigation_widget is not None:
            self.navigation_widget.setParent(None)
            self.navigation_widget.deleteLater()

        if self.modification_widget is not None:
            self.modification_widget.setParent(None)
            self.modification_widget.deleteLater()

    def create_widgets(
        self,
        viewer: "Viewer",
        session: "Session",
        ch_list: list[Any],
        ch_names: list[str],
        signal_list: list[Any],
        graph_list: list[dict[str, Any]],
        cell_tags: dict[Any, Any],
        signal_function: Callable,
    ) -> None:
        """
        Creates and populates the interactive widgets in the 'interact' tab.

        Args:
            viewer (Viewer): The napari viewer instance.
            session (Session): The SQLAlchemy session object for database interaction.
            ch_list (List[Any]): List of channels.
            ch_names (List[str]): Names corresponding to the channels.
            signal_list (List[Any]): List of available signals for plotting.
            graph_list (List[Dict[str, Any]]): A list of dictionaries, where each
                dictionary defines a graph to be plotted, including its name,
                signals, and colors.
            cell_tags (Dict[Any, Any]): Dictionary of cell tags.
            signal_function (Callable): A function used for signal-related operations.
        """

        # Create the scroll area that will fill the entire tab
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Create a separate widget to hold ALL of your content
        content_widget = QWidget()
        content_widget.setLayout(QGridLayout())
        content_widget.layout().setContentsMargins(0, 0, 0, 0)
        content_widget.layout().setAlignment(Qt.AlignTop)
        content_widget.layout().setSpacing(0)

        # Add navigation widget to the content layout
        self.navigation_widget = TrackNavigationWidget(viewer, session)
        content_widget.layout().addWidget(self.navigation_widget, 0, 0)

        # add modification widget
        self.modification_widget = ModificationWidget(
            viewer,
            session,
            ch_list=ch_list,
            ch_names=ch_names,
            tag_dictionary=cell_tags,
            signal_function=signal_function,
        )
        self.modification_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        content_widget.layout().addWidget(self.modification_widget, 1, 0)

        # Set the content widget as the scroll area's main widget
        scroll_area.setWidget(content_widget)

        # Add the single scroll_area to tab2 layout
        self.tab2.layout().addWidget(scroll_area, 1)

        # add lineage graph
        fam_plot_widget = LineagePlotCanvas(self.viewer, session)
        self.viewer.window.add_dock_widget(fam_plot_widget, area="bottom")
        self.napari_widgets.append(fam_plot_widget)

        # add graph widgets
        for gr in graph_list:
            graph_name = gr.name
            graph_signals = gr.signals
            graph_colors = gr.colors
            graph_widget = SignalPlotControlPanel(
                viewer,
                session,
                signal_list,
                signal_sel_list=graph_signals,
                color_sel_list=graph_colors,
                tag_dictionary=cell_tags,
            )

            self.viewer.window.add_dock_widget(
                graph_widget, area="bottom", name=graph_name
            )
            self.napari_widgets.append(graph_widget)

        # switch to the second tab
        self.tabwidget.setCurrentIndex(1)
