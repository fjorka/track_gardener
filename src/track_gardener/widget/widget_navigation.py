import numpy as np
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import and_

from track_gardener.db.db_model import CellDB, TrackDB

DEBOUNCE_INTERVAL_MS = 150
MAX_QUERY_LIMIT = 500
MIN_AREA_FOR_LABELS = 1000 * 2000


class TrackNavigationWidget(QWidget):
    def __init__(self, napari_viewer, sql_session):
        super().__init__()
        self.setLayout(QVBoxLayout())

        self.viewer = napari_viewer
        self.labels = self.viewer.layers["Labels"]
        self.labels.selected_label = 0  # default to no selection
        self.session = sql_session
        self.query_lim = MAX_QUERY_LIMIT

        # set a timer for different kinds of updates
        self._full_update_timer = QTimer(self)
        self._full_update_timer.setSingleShot(True)
        self._full_update_timer.setInterval(DEBOUNCE_INTERVAL_MS)
        self._full_update_timer.timeout.connect(self.full_labels_update)

        # add shortcuts
        self.init_shortcuts()

        navigation_group = QGroupBox()
        navigation_group.setLayout(QVBoxLayout())
        navigation_group.layout().addWidget(QLabel("navigate:"))

        # add track navigation
        self.navigation_row = self.add_navigation_control()
        navigation_group.layout().addWidget(self.navigation_row)

        # add checkbox for following the object
        self.follow_object_checkbox = self.add_follow_object_checkbox()
        navigation_group.layout().addWidget(self.follow_object_checkbox)
        # set initial the default status to checked
        self.follow_object_checkbox.setChecked(True)

        self.layout().addWidget(navigation_group)

        # build labels layer
        self.build_labels()

        # connect building labels to the viewer
        self.viewer.camera.events.zoom.connect(self.build_labels)
        self.viewer.camera.events.center.connect(self.build_labels)
        self.labels.events.visible.connect(self.build_labels)
        self.viewer.dims.events.current_step.connect(self.build_labels)

    #########################################################
    # shortcuts
    #########################################################

    def init_shortcuts(self):
        """
        Initialize shortcuts for the widget.
        """
        # add a shortcut for right click selection
        self.viewer.mouse_drag_callbacks.append(self.select_label)

    def select_label(self, viewer, event):
        """
        Select a label by right click.
        Works on any layer.
        """
        if event.button == 2:

            # fixed for the eraser behavior
            if self.labels.mode == "erase":
                self.labels.mode = "pan_zoom"

            # look up cursor position
            position = tuple([int(x) for x in self.viewer.cursor.position])

            # move if labels use translation
            row_translate = self.labels.translate[0]
            col_translate = self.labels.translate[1]

            if (row_translate > 0) or (col_translate > 0):
                r = int(position[1] - row_translate)
                c = int(position[2] - col_translate)
            else:
                r = int(position[1])
                c = int(position[2])

            # check which cell was clicked
            myTrackNum = self.labels.data[r, c]

            # set track as active
            self.labels.selected_label = int(myTrackNum)

    #########################################################
    # labels_layer_update
    #########################################################

    def build_labels(self):
        """
        Function to build the labels layer based on db content
        """

        # check if the labels are visible at all
        if ("Labels" in self.viewer.layers) and (self.labels.visible):

            # check if the zoom is high enough
            # assuming that data prodiding world coordinates were loaded first
            corner_pixels = self.viewer.layers[0].corner_pixels
            r_span = corner_pixels[1, 1] - corner_pixels[0, 1]
            c_span = corner_pixels[1, 2] - corner_pixels[0, 2]

            if r_span * c_span < MIN_AREA_FOR_LABELS:

                if self.labels.selected_label != 0:
                    # Light update immediately (for responsiveness)
                    self.light_labels_update()

                    # Debounce full update: restart timer
                    self._full_update_timer.stop()
                    self._full_update_timer.start()

                else:
                    self.full_labels_update()

            else:
                self.labels.data = np.zeros([1, 1], dtype=int)
                self.viewer.status = "Zoom in to display labels."

    def full_labels_update(self):
        """
        Full update
        """

        # get the current frame
        current_frame = self.viewer.dims.current_step[0]

        # get the corner pixels of the field of view
        corner_pixels = self.viewer.layers[0].corner_pixels

        # column shift for getting these as imaging data are 3D
        r_start = int(corner_pixels[0, 1])
        r_stop = int(corner_pixels[1, 1])
        c_start = int(corner_pixels[0, 2])
        c_stop = int(corner_pixels[1, 2])

        # self.viewer.status = f"Current view: {r_start}:{r_stop}, {c_start}:{c_stop} at frame {current_frame}"

        # query the database
        query = (
            self.session.query(CellDB)
            .filter(CellDB.t == current_frame)
            .filter(CellDB.bbox_0 < r_stop)
            .filter(CellDB.bbox_1 < c_stop)
            .filter(CellDB.bbox_2 > r_start)
            .filter(CellDB.bbox_3 > c_start)
            .limit(self.query_lim)
            .all()
        )

        self.viewer.status = f"Querying cells in the field: {len(query)} with view {r_start}:{r_stop}, {c_start}:{c_stop} at frame {current_frame}"

        if (len(query) < self.query_lim) and (len(query) > 0):

            # get query extent and position
            r_start_frame = min([x.bbox_0 for x in query])
            r_stop_frame = max([x.bbox_2 for x in query])
            c_start_frame = min([x.bbox_1 for x in query])
            c_stop_frame = max([x.bbox_3 for x in query])

            # build the frame
            frame = np.zeros(
                [r_stop_frame - r_start_frame, c_stop_frame - c_start_frame],
                dtype=int,
            )

            for cell in query:
                frame[
                    cell.bbox_0 - r_start_frame : cell.bbox_2 - r_start_frame,
                    cell.bbox_1 - c_start_frame : cell.bbox_3 - c_start_frame,
                ] += (
                    cell.mask.astype(int) * cell.track_id
                )

            self.labels.data = frame
            self.labels.translate = np.array([r_start_frame, c_start_frame])
            self.labels.refresh()

            # update the status
            self.viewer.status = f"Found {len(query)} cells in the field."

            # store the query with the layer
            self.labels.metadata["query"] = query

        elif len(query) == 0:
            self.labels.data = np.zeros([1, 1], dtype=int)
            self.labels.refresh()
            self.viewer.status = "No cells found in the field."

        else:
            self.labels.data = np.zeros([1, 1], dtype=int)
            self.labels.refresh()
            self.viewer.status = f"More than {self.query_lim} in the field - zoom in to display labels."

    def light_labels_update(self):
        """
        Light update
        """

        # get the current frame
        current_frame = self.viewer.dims.current_step[0]

        # query the database
        query = (
            self.session.query(CellDB)
            .filter(CellDB.track_id == self.labels.selected_label)
            .filter(CellDB.t == current_frame)
            .all()
        )

        if len(query) == 1:
            cell = query[0]

            # sent labels data to the labels layer
            self.labels.data = cell.mask.astype(int) * cell.track_id
            self.labels.translate = np.array([cell.bbox_0, cell.bbox_1])
        else:
            self.full_labels_update()

        self.labels.refresh()

    #########################################################
    # track navigation
    #########################################################

    def add_navigation_control(self):
        """
        Add a set of buttons to navigate position within the track
        """

        navigation_row = QWidget()
        navigation_row.setLayout(QGridLayout())

        self.start_track_btn = self.add_start_track_btn()
        self.center_object_btn = self.add_center_object_btn()
        self.end_track_btn = self.add_end_track_btn()

        navigation_row.layout().addWidget(self.start_track_btn, 0, 0)
        navigation_row.layout().addWidget(self.center_object_btn, 0, 1)
        navigation_row.layout().addWidget(self.end_track_btn, 0, 2)

        return navigation_row

    def add_center_object_btn(self):
        """
        Add a button to center the object.
        """
        center_object_btn = QPushButton("<>")

        center_object_btn.clicked.connect(self.center_object_function)

        return center_object_btn

    def center_object_core_function(self):
        """
        Center the object that exists on this frame.
        """
        # orient yourself
        track_id = int(
            self.labels.selected_label
        )  # because numpy.int64 is not accepted by the database
        current_frame = self.viewer.dims.current_step[0]

        # find the object
        cell = (
            self.session.query(CellDB)
            .filter(
                and_(CellDB.track_id == track_id, CellDB.t == current_frame)
            )
            .first()
        )

        if cell is not None:
            # get the position
            r = cell.row
            c = cell.col

            # check if there is movement
            _, x, y = self.viewer.camera.center

            if x == r and y == c:
                # trigger rebuilding of labels
                self.build_labels()
            else:
                # move the camera
                self.viewer.camera.center = (0, r, c)

        else:
            self.viewer.status = "No object in this frame."
            self.build_labels()

    def center_object_function(self):
        """
        Center the object.
        """

        # orient yourself
        curr_tr = int(
            self.labels.selected_label
        )  # because numpy.int64 is not accepted by the database

        if curr_tr != 0:

            curr_fr = self.viewer.dims.current_step[0]

            # find the pathway
            tr = (
                self.session.query(TrackDB).filter_by(track_id=curr_tr).first()
            )

            # move time point if beyond boundary
            if tr.t_begin > curr_fr:
                self.viewer.dims.set_point(0, tr.t_begin)
            elif tr.t_end < curr_fr:
                self.viewer.dims.set_point(0, tr.t_end)

            # center the cell
            self.center_object_core_function()

        else:
            self.viewer.status = "No object selected."
            self.build_labels()

    def add_start_track_btn(self):
        """
        Add a button to cut tracks.
        """
        start_track_btn = QPushButton("<")

        start_track_btn.clicked.connect(self.start_track_function)

        return start_track_btn

    def start_track_function(self):
        """
        Go to the beginning of the track.
        """
        # find the beginning of a track
        tr = self.labels.selected_label
        t_begin = (
            self.session.query(TrackDB).filter_by(track_id=tr).first().t_begin
        )

        # move to the beginning of a track
        self.viewer.dims.set_point(0, t_begin)

        # center the cell
        self.center_object_core_function()

    def add_end_track_btn(self):
        """
        Add a button to go to the end of the track
        """
        end_track_btn = QPushButton(">")

        end_track_btn.clicked.connect(self.end_track_function)

        return end_track_btn

    def end_track_function(self):
        """
        Go to the last point in the track
        """
        # find the beginning of a track
        tr = self.labels.selected_label
        t_end = (
            self.session.query(TrackDB).filter_by(track_id=tr).first().t_end
        )

        # move to the end of a track
        self.viewer.dims.set_point(0, t_end)

        # center the cell
        self.center_object_core_function()

    #########################################################
    # cell following
    #########################################################

    def add_follow_object_checkbox(self):
        """
        Add a checkbox to follow the object.
        """
        follow_object_checkbox = QCheckBox("follow track")

        follow_object_checkbox.stateChanged.connect(
            self.followBoxStateChanged_function
        )

        return follow_object_checkbox

    def followBoxStateChanged_function(self):
        """
        Follow the object if the checkbox is checked.
        """
        if self.follow_object_checkbox.isChecked():
            self.viewer.status = "Following the object is turned on."

            # center the cell (as at the beginning no slider is triggered)
            self.center_object_core_function()

            # connect centering to slider movement
            self.viewer.dims.events.current_step.connect(
                self.center_object_core_function
            )

            # connect centering to label selection
            self.labels.events.selected_label.connect(
                self.center_object_core_function
            )

            # disconnect building labels from the slider
            self.viewer.dims.events.current_step.disconnect(self.build_labels)

        else:
            self.viewer.status = "Following the object is turned off."

            # disconnect from slider movement
            self.viewer.dims.events.current_step.disconnect(
                self.center_object_core_function
            )

            # disconnect from label selection
            self.labels.events.selected_label.disconnect(
                self.center_object_core_function
            )

            # connect building labels to the slider
            self.viewer.dims.events.current_step.connect(self.build_labels)
