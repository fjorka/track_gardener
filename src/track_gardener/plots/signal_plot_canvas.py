"""A PyQtGraph widget for plotting cell signals and tags over time."""

from typing import TYPE_CHECKING, Optional

import numpy as np
from pyqtgraph import (
    GraphicsLayoutWidget,
    LegendItem,
    PlotDataItem,
    TextItem,
    mkPen,
)
from qtpy.QtCore import Qt

from track_gardener.db.db_model import CellDB

if TYPE_CHECKING:
    from napari import Viewer
    from pyqtgraph import InfiniteLine, PlotDataItem
    from qtpy.QtGui import QMouseEvent
    from sqlalchemy.orm import Session


class SignalPlotCanvas(GraphicsLayoutWidget):
    """A canvas for plotting cell signals against time.

    Integrates with a napari viewer to display time-series data for
    selected cell tracks from a database. It visualizes signals, displays
    tags, and includes an interactive time cursor synced with the viewer.
    """

    def __init__(
        self,
        viewer: "Viewer",
        session: "Session",
        legend_on: bool = True,
        selected_signals: Optional[list[str]] = None,
        color_list: Optional[list[tuple[int, int, int]]] = None,
        tag_dictionary: Optional[dict[str, str]] = None,
    ) -> None:
        """Initializes the SignalPlotCanvas.

        Args:
            viewer: The napari viewer instance.
            session: The SQLAlchemy database session for querying data.
            legend_on: If True, a legend is displayed on the plot.
            selected_signals: A list of signal names to plot.
            color_list: A list of RGB color tuples for the signal plots.
            tag_dictionary: A mapping of tag names to their marker symbols.
        """
        super().__init__()

        self.setContextMenuPolicy(Qt.NoContextMenu)

        # --- Basic Attributes ---
        self.session = session
        self.viewer = viewer
        self.labels = self.viewer.layers["Labels"]
        self.legend_on = legend_on
        self.signal_list = selected_signals
        self.color_list = color_list
        self.tag_dictionary = tag_dictionary if tag_dictionary else {}

        # --- Initialize Graph ---
        self.plot_view = self.addPlot(title="", labels={"bottom": "Time"})
        t_max = self.viewer.dims.range[0][1]
        self.plot_view.setXRange(0, t_max)
        self.plot_view.setMouseEnabled(x=True, y=True)
        self.plot_view.setMenuEnabled(False)
        # add time line
        self.time_line = self.add_time_line()

        # --- Connect Events ---
        self.viewer.dims.events.current_step.connect(self.update_time_line)
        self.labels.events.selected_label.connect(self.update_graph_all)
        self.plot_view.scene().sigMouseClicked.connect(self.on_mouse_click)

    def add_time_line(self) -> "InfiniteLine":
        """Adds a vertical line to the graph that follows the time slider.

        Returns:
            The created InfiniteLine object.
        """
        pen = mkPen(color=(255, 255, 255), xwidth=1)
        init_position = self.viewer.dims.current_step[0]
        time_line = self.plot_view.addLine(x=init_position, pen=pen)
        return time_line

    def on_mouse_click(self, event: "QMouseEvent") -> None:
        """Handles mouse click events on the plot.

        A left-click sets the napari viewer's time slider to the clicked
        time point.

        Args:
            event: The mouse click event from the plot scene.
        """
        if (
            self.plot_view.sceneBoundingRect().contains(event.scenePos())
            and event.button() == Qt.LeftButton
        ):

            mouse_point = self.plot_view.vb.mapSceneToView(event.scenePos())
            x_val = mouse_point.x()
            self.viewer.dims.set_point(0, round(x_val))

    def get_db_info(self) -> None:
        """Queries the database for the currently active label.

        Fetches time points, signals, and tags for the selected track ID,
        storing the results in `self.query` and `self.active_label`.
        """
        # get a label or a persistent label
        if self.labels.selected_label > 0:
            self.active_label = int(self.labels.selected_label)
        else:
            self.active_label = int(self.labels.metadata["persistent_label"])

        self.query = (
            self.session.query(CellDB.t, CellDB.signals, CellDB.tags)
            .filter(CellDB.track_id == self.active_label)
            .order_by(CellDB.t)
            .all()
        )

    def redraw_tags(self) -> None:
        """Removes existing tags and draws updated ones on the plot."""

        # remove previous tags
        for item in self.plot_view.items:
            if isinstance(item, TextItem):
                self.plot_view.removeItem(item)

        # reset view
        self.plot_view.enableAutoRange(
            self.plot_view.getViewBox().XYAxes, True
        )

        y_view_range = self.plot_view.viewRange()[1]
        y_range = y_view_range[1] - y_view_range[0]
        row_height = 0.1 * y_range

        # add tags
        if len(self.query) > 0:
            if len(self.tag_dictionary) > 0:
                sorted_tags = self.tag_dictionary.items()
                for index, (tag, tag_mark) in enumerate(sorted_tags):
                    x_list = [
                        item[0]
                        for item in self.query
                        if (
                            item[2].get(tag) == "True"
                            or item[2].get(tag) is True
                        )
                    ]
                    if x_list:
                        y = y_view_range[1] + (index * row_height)
                        for x in x_list:
                            text = TextItem(text=tag_mark, anchor=(0.5, 0))
                            self.plot_view.addItem(text)
                            text.setPos(x, y)
            else:
                self.viewer.status = "No tags to display."

        else:
            self.viewer.status = "Error - no such label in the database."

    def redraw_signals(self) -> None:
        """Removes existing signals and plots updated ones."""

        # remove previous signals
        for item in self.plot_view.items[1:]:
            if isinstance(item, PlotDataItem):
                self.plot_view.removeItem(item)

        if len(self.query) > 0:
            x_signal = [x[0] for x in self.query]
            full_x_range = list(range(min(x_signal), max(x_signal) + 1))

            y_signals = {
                sig: [np.nan] * len(full_x_range) for sig in self.signal_list
            }

            for t, signals, _ in self.query:
                index = full_x_range.index(t)
                for sig in self.signal_list:
                    if sig in signals:
                        y_signals[sig][index] = signals[sig]

            # reset view
            self.plot_view.enableAutoRange(
                self.plot_view.getViewBox().XYAxes, True
            )

            if self.legend_on:
                legend = LegendItem(
                    offset=(70, 30)
                )  # Offset for the position of the legend in the view
                legend.setParentItem(self.plot_view.graphicsItem())

            for sig, col in zip(self.signal_list, self.color_list):
                if sig is not None:
                    y_signal_with_gaps = y_signals[sig]
                    pl = self.plot_view.plot(
                        full_x_range,
                        y_signal_with_gaps,
                        pen=mkPen(color=col, width=2),
                        name=sig,
                    )
                    if self.legend_on:
                        legend.addItem(pl, sig)
        else:
            self.viewer.status = "Error - no such label in the database."

    def update_time_line(self) -> None:
        """Updates the time line position based on the viewer's slider."""
        line_position = self.viewer.dims.current_step[0]
        self.time_line.setValue(line_position)

    def update_tags(self) -> None:
        """Fetches the latest data and redraws only the tags."""
        self.get_db_info()
        self.redraw_tags()

    def update_signals(self) -> None:
        """Fetches the latest data and redraws only the signals."""
        self.get_db_info()
        self.redraw_signals()

    def update_graph_all(self) -> None:
        """Updates the entire graph when a new label is selected."""
        if self.labels.selected_label != 0:
            self.get_db_info()
            self.redraw_signals()
            self.redraw_tags()
