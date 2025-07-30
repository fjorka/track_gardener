from typing import TYPE_CHECKING, Any

from qtpy.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from track_gardener.graph.signal_graph import SignalGraph

if TYPE_CHECKING:
    from napari.viewer import Viewer
    from sqlalchemy.orm import Session


class CellGraphWidget(QWidget):
    """A widget for creating and managing a signal graph plot.

    This widget allows users to dynamically add, remove, and configure
    signals to be plotted over time for a selected track. Each signal can
    be assigned a color, and the graph updates automatically based on
    user selections.
    """

    def __init__(
        self,
        napari_viewer: "Viewer",
        sql_session: "Session",
        signal_list: list[str],
        signal_sel_list: list[str] | None = None,
        color_sel_list: list[str] | None = None,
        tag_dictionary: dict[str, Any] | None = None,
    ) -> None:
        """Initializes the CellGraphWidget.

        Args:
            napari_viewer (Viewer): The napari viewer instance.
            sql_session (Session): The SQLAlchemy session for database operations.
            signal_list (list[str]): A list of all available signal names.
            signal_sel_list (Optional[list[str]]): A list of signals to pre-select
                for plotting. Defaults to None.
            color_sel_list (Optional[list[str]]): A list of colors corresponding
                to the pre-selected signals. Defaults to None.
            tag_dictionary (Optional[dict[str, Any]]): A dictionary of cell tags.
                Defaults to None.
        """
        super().__init__()

        if tag_dictionary is None:
            tag_dictionary = {}

        self.setLayout(QVBoxLayout())

        self.viewer = napari_viewer
        self.labels = self.viewer.layers["Labels"]
        self.session = sql_session
        self.signal_list = [None] + signal_list
        self.signal_sel_list = signal_sel_list
        self.color_sel_list = color_sel_list
        self.tag_dictionary = tag_dictionary
        self.btn_offset = 1

        # account for incorrect signal and color list
        if self.signal_sel_list is not None and (
            len(self.signal_sel_list) != len(self.color_sel_list)
        ):
            self.viewer.status = (
                "Signal list and color list have different lengths."
            )
            self.signal_sel_list = None
            self.color_sel_list = None

        # add graph
        self.graph = self.add_signal_graph()

        # add matching buttons
        if (self.signal_sel_list is None) or (len(self.signal_sel_list) == 0):
            self.add_row_button()
        else:
            for ind in range(len(self.signal_sel_list)):
                self.add_row_button(
                    button=None,
                    signal=self.signal_sel_list[ind],
                    color=self.color_sel_list[ind],
                )

            # trigger graph update
            self.graph.update_graph_all()

    def add_row_button(
        self,
        button: QPushButton | None = None,
        signal: str | None = None,
        color: str | None = None,
    ) -> None:
        """Adds a new row of controls for selecting a signal and color.

        Args:
            button (Optional[QPushButton]): The button that triggered the action,
                used to determine insertion position. Defaults to None.
            signal (Optional[str]): The signal to pre-select in the new row.
                Defaults to None.
            color (Optional[str]): The color to pre-select for the new row.
                Defaults to None.
        """
        # Create a new row
        rowLayout = QHBoxLayout()

        comboBox = self.create_signal_combo_box(signal)
        colorButton = self.create_color_button(color)

        add_button = QPushButton("+")
        add_button.setMaximumWidth(30)
        add_button.clicked.connect(
            lambda: self.handle_add_button_click(add_button)
        )

        min_button = QPushButton("-")
        min_button.setMaximumWidth(30)
        min_button.clicked.connect(
            lambda: self.handle_min_button_click(min_button)
        )

        rowLayout.addWidget(comboBox)
        rowLayout.addWidget(colorButton)
        rowLayout.addWidget(add_button)
        rowLayout.addWidget(min_button)

        # when it's added by click on the button
        if button is not None:

            for i in range(1, self.layout().count()):
                layout = self.layout().itemAt(i)
                if layout.layout().indexOf(button) != -1:

                    self.layout().insertLayout(i + 1, rowLayout)
        else:
            self.layout().addLayout(rowLayout)

        # disable button of the last row
        row_number = self.layout().count()
        if row_number == 2:
            self.layout().itemAt(row_number - 1).itemAt(3).widget().setEnabled(
                False
            )

        # enable button of the row before the last one
        if row_number == 3:
            self.layout().itemAt(row_number - 2).itemAt(3).widget().setEnabled(
                True
            )

    def create_signal_combo_box(self, signal: str | None = None) -> QComboBox:
        """Creates a combo box populated with available signal names.

        Args:
            signal (Optional[str]): The signal to pre-select. Defaults to None.

        Returns:
            QComboBox: The configured combo box widget.
        """
        comboBox = QComboBox()
        for sig in self.signal_list:
            comboBox.addItem(sig)

        if signal is not None:
            comboBox.setCurrentText(signal)

        comboBox.activated[str].connect(self.on_selection)

        return comboBox

    def create_color_button(self, color: str | None = None) -> QPushButton:
        """Creates a button for color selection.

        Args:
            color (str | None): The initial color for the button background.
                Defaults to None, which sets the color to white.

        Returns:
            QPushButton: The configured color button.
        """
        colorButton = QPushButton()
        colorButton.setMaximumWidth(30)  # Keep the button small
        if color:
            colorButton.setStyleSheet(f"background-color: {color}")
        else:
            colorButton.setStyleSheet("background-color: white")
        colorButton.clicked.connect(lambda: self.select_color(colorButton))

        return colorButton

    def select_color(self, button: QPushButton) -> None:
        """Opens a color dialog and updates the button's background color.

        Args:
            button (QPushButton): The button to apply the selected color to.
        """
        # Open a color dialog and set the selected color as the button's background
        color = QColorDialog.getColor()
        if color.isValid():
            button.setStyleSheet(f"background-color: {color.name()}")
            self.on_selection()

    def on_selection(self) -> None:
        """Updates the graph when a signal or color selection changes."""
        # update list of signals and colors
        signal_sel_list = []
        color_sel_list = []

        # get info about selected signals
        for i in range(self.btn_offset, self.layout().count()):
            self.viewer.status = "Selection changed"
            signal = self.layout().itemAt(i).itemAt(0).widget().currentText()
            signal_sel_list.append(signal)
            color = (
                self.layout()
                .itemAt(i)
                .itemAt(1)
                .widget()
                .palette()
                .button()
                .color()
                .name()
            )
            color_sel_list.append(color)
        self.viewer.status = "Selection changed"
        self.graph.signal_list = signal_sel_list
        self.graph.color_list = color_sel_list

        self.viewer.status = f"Selected signals: {signal_sel_list} with colors: {color_sel_list}"

        # update graph
        self.graph.update_graph_all()

    def handle_add_button_click(self, button: QPushButton) -> None:
        """Handles the click event for the add ('+') button.

        Args:
            button (QPushButton): The button that was clicked.
        """

        self.add_row_button(button)

    def handle_min_button_click(self, button: QPushButton) -> None:
        """Handles the click event for the remove ('-') button.

        Args:
            button (QPushButton): The button that was clicked.
        """

        self.remove_row_button(button)

    def remove_row_button(self, button: QPushButton) -> None:
        """Removes the row containing the specified button.

        Args:
            button (QPushButton): The button within the row to be removed.
        """

        # Find the layout that contains the button and remove it
        for i in range(1, self.layout().count()):
            layout = self.layout().itemAt(i)
            # Check if this is the layout to be removed
            if layout.layout().indexOf(button) != -1:
                self.clear_layout(layout.layout())
                self.layout().removeItem(layout)
                break

        # if only one row left
        if self.layout().count() == 2:
            last_row = self.layout().itemAt(1)
            last_row.itemAt(3).widget().setEnabled(False)

        # update what is displayed
        self.on_selection()

    def add_signal_graph(self) -> SignalGraph:
        """Adds the signal graph widget to the main layout.

        Returns:
            SignalGraph: The instance of the created graph widget.
        """
        graph_widget = SignalGraph(
            self.viewer,
            self.session,
            legend_on=False,
            selected_signals=self.signal_sel_list,
            color_list=self.color_sel_list,
            tag_dictionary=self.tag_dictionary,
        )

        self.layout().addWidget(graph_widget)

        return graph_widget

    def clear_layout(self, layout: QLayout | None) -> None:
        """Removes all widgets from a given layout.

        Args:
            layout (QLayout | None): The layout to clear. If None, the
                function does nothing.
        """
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
