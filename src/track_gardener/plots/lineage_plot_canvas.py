"""
A PyQtGraph widget for displaying a lineage plot.

This module defines the `LineagePlotCanvas` class, a PyQtGraph-based widget that
visualizes cell lineage trees. It interacts with a napari viewer and a database
session to display, select, and modify track data. The lineage tree layout
is determined using a custom implementation of the Reingold-Tilford algorithm.
"""

from typing import TYPE_CHECKING

import networkx as nx
import numpy as np
from pyqtgraph import (
    GraphicsLayoutWidget,
    TextItem,
    mkColor,
    mkPen,
)
from qtpy.QtCore import Qt

from track_gardener.db.db_functions import get_tracks_nx_from_root
from track_gardener.db.db_model import TrackDB
from track_gardener.plots.utils_plot import set_y_with_walkerlayout

if TYPE_CHECKING:
    from napari import Viewer
    from qtpy.QtGui import QMouseEvent
    from sqlalchemy.orm import Session


class LineagePlotCanvas(GraphicsLayoutWidget):
    """
    A PyQtGraph widget to display and interact with cell lineage trees.

    This canvas renders a lineage tree based on track data from a database.
    It allows users to select tracks, jump to time points, and modify track
    properties through mouse interactions.
    """

    def __init__(self, viewer: "Viewer", session: "Session"):
        """
        Initializes the LineagePlotCanvas.

        Args:
            viewer (Viewer): The napari viewer instance.
            session (Session): The SQLAlchemy database session for data retrieval.
        """
        super().__init__()

        self.setContextMenuPolicy(Qt.NoContextMenu)

        self.session = session
        self.viewer = viewer
        self.labels = self.viewer.layers["Labels"]
        self.tree = None

        # initialize graph
        self.plot_view = self.addPlot(
            title="Lineage tree", labels={"bottom": "Time"}
        )
        self.plot_view.hideAxis("left")
        self.t_max = self.viewer.dims.range[0][1]
        self.plot_view.setXRange(0, self.t_max)
        self.plot_view.setMouseEnabled(x=True, y=True)
        self.plot_view.setMenuEnabled(False)

        # Connect the plotItem's mouse click event
        self.plot_view.scene().sigMouseClicked.connect(self.on_mouse_click)

        # initialize time line
        pen = mkPen(color=(255, 255, 255), xwidth=1)
        init_position = self.viewer.dims.current_step[0]
        self.time_line = self.plot_view.addLine(x=init_position, pen=pen)

        # connect time slider event
        self.viewer.dims.events.current_step.connect(self.update_time_line)

        # connect label selection event
        self.labels.events.selected_label.connect(self.update_lineage_display)

    def on_mouse_click(self, event: "QMouseEvent") -> None:
        """
        Handles mouse click events on the plot.

        Left-clicking selects a track and moves the napari time slider.
        Right-clicking toggles the 'accepted' status of the selected track.

        Args:
            event (QMouseEvent): The mouse click event.
        """
        vb = self.plot_view.vb
        scene_coords = event.scenePos()

        if self.plot_view.sceneBoundingRect().contains(scene_coords):
            mouse_point = vb.mapSceneToView(scene_coords)
            x_val = mouse_point.x()
            y_val = mouse_point.y()

            ############################################################
            # find which track was selected
            dist = float("inf")
            selected_n = None

            if self.tree is not None:  # self.tree is the NetworkX graph
                for n in self.tree.nodes():
                    # Get node data (attributes)
                    node_data = self.tree.nodes[n]

                    # Extract node attributes (e.g., start, stop, and y values)
                    start = node_data.get("start")
                    stop = node_data.get("stop")
                    y_val_node = node_data.get("y")

                    # Check if the x_val falls within the start-stop range of the node
                    if (start <= x_val) and (stop >= x_val):
                        dist_track = abs(y_val_node - y_val)

                        # Update the selected node if this node is closer to the clicked point
                        if dist_track < dist:
                            dist = dist_track
                            selected_n = n
            ############################################################
            if selected_n is not None and selected_n in self.tree.nodes:

                # left click - select a track
                if event.button() == Qt.LeftButton:
                    # move in time
                    self.viewer.dims.set_point(0, round(x_val))
                    self.viewer.status = f"Selected track: {selected_n}"
                    self.labels.selected_label = selected_n

                # right click - change of status
                elif event.button() == Qt.RightButton:

                    # flip the status
                    track = (
                        self.session.query(TrackDB)
                        .filter(TrackDB.track_id == selected_n)
                        .first()
                    )
                    track.accepted_tag = not track.accepted_tag
                    self.session.commit()

                    # update the tree
                    self.update_lineage_display()

                    # update viewer status
                    self.viewer.status = f"Track {track.track_id} accepted status: {track.accepted_tag}."
                else:
                    pass

            else:
                self.viewer.status = f"No track at position ({x_val:.2f}, {y_val:.2f}). Click on a track to select it."

        else:
            self.viewer.status = "No tree to select from."

    def update_time_line(self) -> None:
        """Updates the position of the time line when the slider is moved."""
        line_position = self.viewer.dims.current_step[0]
        self.time_line.setValue(line_position)

    def update_lineage_display(self) -> None:
        """
        Updates the lineage display when a new label is selected.

        Clears the existing plot and redraws the lineage tree corresponding
        to the currently selected label in the napari viewer.
        """

        # Clear all elements except the time line
        items_to_remove = self.plot_view.items[
            1:
        ]  # Get all items except the time line
        for item in items_to_remove:
            self.plot_view.removeItem(item)

        # get an active label
        if self.labels.selected_label > 0:
            self.active_label = int(self.labels.selected_label)
        else:
            self.active_label = int(self.labels.metadata["persistent_label"])

        # check if the label is in the database
        query = (
            self.session.query(TrackDB)
            .filter(TrackDB.track_id == self.active_label)
            .first()
        )

        # actions based on finding the label in the database
        if query is not None:
            # get the root value
            root_id = query.root

            # update viewer status
            self.viewer.status = f"Family of track number {root_id}."

            # build the tree
            self.tree = get_tracks_nx_from_root(self.session, root_id)

            # add y-positions to the nodes
            self.tree = set_y_with_walkerlayout(self.tree, root_id)

            # update the widget with the tree
            self.render_tree_view(self.tree)

        else:
            self.viewer.status = "Error - no such label in the database."
            self.tree = None

    def render_tree_view(self, G: nx.DiGraph) -> None:
        """
        Renders the lineage tree using NetworkX and PyQtGraph.

        Args:
            G (nx.DiGraph): The NetworkX graph with node positions stored in 'y' attributes.
        """
        y_max = -0.1
        y_min = 0.1

        # Iterate over nodes in the graph
        for track_id, node_data in G.nodes(data=True):

            # Get position in time (x-coordinates: start and stop)
            x1 = node_data["start"]
            x2 = node_data["stop"]
            x_signal = [x1, x2]

            # Get y-coordinate from the node's 'pos' attribute
            y_signal = np.array([node_data["y"]]).repeat(2)
            y_max = np.max([y_signal[0], y_max])
            y_min = np.min([y_signal[0], y_min])

            # Get color based on the label
            label_color = self.labels.get_color(track_id)

            # Pen color and style adjustments based on the node's state
            if track_id == self.active_label:
                pen_color = mkColor((label_color * 255).astype(int))
                pen = mkPen(color=pen_color, width=4)
            else:
                label_color[-1] = 0.4
                pen_color = mkColor((label_color * 255).astype(int))
                pen = mkPen(color=pen_color, width=2)

            if not node_data["accepted"]:
                pen.setStyle(Qt.DotLine)

            # Plot the horizontal line for the node
            self.plot_view.plot(x_signal, y_signal, pen=pen)

            # Add text label for the node
            if node_data["accepted"]:
                text_item = TextItem(
                    str(track_id), anchor=(1, 1), color="green"
                )
            else:
                text_item = TextItem(str(track_id), anchor=(1, 1))

            text_item.setPos(x2, node_data["y"])
            self.plot_view.addItem(text_item)

            # Plot vertical lines to children
            for child in G.successors(track_id):
                child_data = G.nodes[child]

                # Get vertical line (constant x and different y values)
                x_signal = [x2, x2]
                y_signal = [node_data["y"], child_data["y"]]
                self.plot_view.plot(x_signal, y_signal, pen=pen)

        # Set plot axis limits
        self.plot_view.setXRange(0, self.t_max)
        self.plot_view.setYRange(
            y_min - 0.1 * abs(y_min), y_max + 0.1 * abs(y_max)
        )
