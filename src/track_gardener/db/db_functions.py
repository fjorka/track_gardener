"""A collection of functions to manipulate cell and track data in the database.

This module provides an API for common track editing operations, such as
creating, deleting, cutting, merging, and connecting tracks. It also includes
functions for managing individual cells, notes, and tags.
"""

from copy import deepcopy
from typing import TYPE_CHECKING, Callable, Sequence

import dask.array as da
import networkx as nx
from sqlalchemy import and_, func
from sqlalchemy.orm import aliased
from sqlalchemy.orm.attributes import flag_modified

from track_gardener.db.db_model import NO_PARENT, CellDB, TrackDB

if TYPE_CHECKING:
    from skimage.measure._regionprops import RegionProperties
    from sqlalchemy.orm import Session


def get_new_track_id(session: "Session") -> int:
    """Gets the next available track ID.

    This is determined by finding the maximum existing track ID and adding one.

    Args:
        session ("Session"): The SQLAlchemy session connected to the database.

    Returns:
        int: The new, unique track ID.
    """
    max_id = session.query(func.max(TrackDB.track_id)).scalar() or 0

    return max_id + 1


def get_new_cell_id(session: "Session") -> int:
    """Gets the next available unique cell ID.

    This is determined by finding the maximum existing cell ID and adding one.

    Args:
        session ("Session"): The SQLAlchemy session connected to the database.

    Returns:
        int: The new, unique cell ID.
    """
    max_id = session.query(func.max(CellDB.id)).scalar() or 0
    return max_id + 1


def get_signals(session: "Session") -> list[str]:
    """Gets a list of all signal names from the database.

    It inspects the 'signals' JSON field of the first available cell.

    Args:
        session ("Session"): The SQLAlchemy session connected to the database.

    Returns:
        list[str]: A list of signal names (keys in the signals dictionary).
    """
    example_cell = session.query(CellDB).first()
    if not example_cell:
        return []
    signal_list = list(example_cell.signals.keys())
    return signal_list


def get_descendants(
    session: "Session", active_label: int
) -> Sequence[TrackDB]:
    """Recursively gets all descendants of a given track, including itself.

    Args:
        session ("Session"): The SQLAlchemy session connected to the database.
        active_label (int): The track_id to start the search from.

    Returns:
        Sequence[TrackDB]: A list of TrackDB objects representing the full
            lineage descending from the active_label.
    """

    # Create a recursive Common Table Expression (CTE)
    cte = (
        session.query(TrackDB)
        .filter(TrackDB.track_id == active_label)
        .cte(recursive=True)
    )

    cte_alias = aliased(cte, name="cte_alias")

    # Define the recursive part of the CTE
    cte = cte.union_all(
        session.query(TrackDB).filter(
            TrackDB.parent_track_id == cte_alias.c.track_id
        )
    )

    # Query all tracks that are part of the recursive hierarchy
    descendants = (
        session.query(TrackDB)
        .join(cte, TrackDB.track_id == cte.c.track_id)
        .all()
    )
    return descendants


def delete_trackDB(session: "Session", active_label: int) -> str:
    """Deletes a track and detaches its direct children.

    This function deletes the specified track. Any direct children of the
    deleted track become new root tracks.

    Args:
        session ("Session"): The SQLAlchemy session connected to the database.
        active_label (int): The track_id of the track to delete.

    Returns:
        str: A status message indicating the result of the operation.
    """
    record = session.query(TrackDB).filter_by(track_id=active_label).first()
    if record is not None:
        # Process descendants to detach children
        descendants = get_descendants(session, active_label)
        for track in [x for x in descendants if x.track_id != active_label]:
            if track.parent_track_id == active_label:
                cut_trackDB(session, track.track_id, track.t_begin)
        # Delete the track itself
        session.delete(record)
        session.commit()
        status = f"Track {active_label} has been deleted."
    else:
        status = "Track not found"
    return status


def cut_trackDB(
    session: "Session", active_label: int, current_frame: int
) -> tuple[bool, int | None]:
    """Cuts a track at a specific frame.

    This can result in two outcomes:
    1.  If cut at its start (`t_begin`), the track is detached from its parent.
    2.  If cut in the middle, the track is truncated, and a new track is
        created for the subsequent cells.

    Args:
        session ("Session"): The SQLAlchemy session connected to the database.
        active_label (int): The ID of the track to cut.
        current_frame (int): The frame at which to perform the cut.

    Returns:
        tuple[bool, int | None]: A tuple containing:
            - mitosis (bool): True if the cut resulted in detachment from a parent.
            - new_track (int | None): The ID of the new track created, if any.
    """

    record = session.query(TrackDB).filter_by(track_id=active_label).first()

    # Handle cases where the cut is invalid or has no effect
    if (
        (record.t_end < current_frame)
        or (record.t_begin > current_frame)
        or (
            (record.parent_track_id == -1)
            and (record.t_begin == current_frame)
        )
    ):
        return False, None

    # Case 1: Cutting from a parent (detaching at t_begin)
    elif (record.parent_track_id > -1) and (record.t_begin == current_frame):
        record.parent_track_id = -1
        descendants = get_descendants(session, active_label)
        for track in descendants:
            track.root = active_label
        session.commit()
        return True, None

    # Case 2: Splitting a track in the middle
    elif record.t_begin < current_frame:
        org_t_end = record.t_end
        # Find the precise start/end times around the gap to handle sparse tracks
        cells_t = (
            session.query(CellDB.t).filter_by(track_id=active_label).all()
        )
        t_start = min(
            [cell[0] for cell in cells_t if cell[0] >= current_frame]
        )
        t_stop = max([cell[0] for cell in cells_t if cell[0] < current_frame])
        record.t_end = t_stop

        # Create a new track for the second part
        new_track = get_new_track_id(session)
        track = TrackDB(
            track_id=new_track,
            parent_track_id=-1,
            root=new_track,
            t_begin=t_start,
            t_end=org_t_end,
        )
        session.add(track)

        # Update descendants to point to the new track where appropriate
        descendants = get_descendants(session, active_label)
        for track in [x for x in descendants if x.track_id != active_label]:
            track.root = new_track
            if track.parent_track_id == active_label:
                track.parent_track_id = new_track
        session.commit()
        return False, new_track
    else:
        raise ValueError("Track cutting scenario is not accounted for.")


def _merge_t2(
    session: "Session", t2: TrackDB, t1: TrackDB, current_frame: int
) -> None:
    """
    Helper to merge track t2 into t1.
    Args:
        session ("Session"): The SQLAlchemy session.
        t2 (TrackDB): The secondary track (child/absorbed).
        t1 (TrackDB): The ID of the primary track (parent/absorber).
        current_frame (int): The frame where the t2 will start in mitosis.
    """

    # process descendants
    descendants = get_descendants(session, t2.track_id)

    # if there is remaining part at the beginning
    if t2.t_begin < current_frame:
        t2.t_end = current_frame - 1

    # the t2 track in merge stops existing
    else:
        session.delete(t2)

    # for everyone except the t2 track
    for track in [x for x in descendants if x.track_id != t2.track_id]:
        # change the value of the root track
        track.root = t1.root

        # change for children
        if track.parent_track_id == t2.track_id:
            track.parent_track_id = t1.track_id

    session.commit()


def _connect_t2(
    session: "Session", t2: TrackDB, t1: TrackDB, current_frame: int
) -> int | None:
    """
    Helper to connect t2 as a child of t1.
    Args:
        session ("Session"): The SQLAlchemy session.
        t2 (TrackDB): The secondary track (child/absorbed).
        t1 (TrackDB): The ID of the primary track (parent/absorber).
        current_frame (int): The frame where the t2 will start in mitosis.
    """

    # if there is a remaining part at the beginning
    if t2.t_begin < current_frame:
        # create a new track
        new_track = get_new_track_id(session)

        # check if the t2_before needs to become its own root
        new_root = new_track if t2.root == t2.track_id else deepcopy(t2.root)

        track = TrackDB(
            track_id=new_track,
            parent_track_id=deepcopy(t2.parent_track_id),
            root=new_root,
            t_begin=deepcopy(t2.t_begin),
            t_end=current_frame - 1,
        )

        session.add(track)

        # modify t2
        t2.t_begin = current_frame

    else:
        new_track = None

    # modify family relations
    t2.parent_track_id = t1.track_id

    # process descendants
    descendants = get_descendants(session, t2.track_id)

    for tr in descendants:
        # change the value of the root track
        tr.root = t1.root

    session.commit()

    # return the new track number (1st part of t2)
    return new_track


def integrate_trackDB(
    session: "Session",
    operation: str,
    t1_ind: int,
    t2_ind: int,
    current_frame: int,
) -> tuple[int | None, int | None]:
    """Merges or connects two tracks.

    Args:
        session ("Session"): The SQLAlchemy session.
        operation (str): The operation to perform ("merge" or "connect").
        t1_ind (int): The ID of the primary track (parent/absorber).
        t2_ind (int): The ID of the secondary track (child/absorbed).
        current_frame (int): The frame where the integration occurs.

    Returns:
        tuple[int | None, int | None]: A tuple containing the new track IDs
            created from splitting t1 and t2, respectively.
    """

    # get tracks of interest
    t1 = session.query(TrackDB).filter_by(track_id=t1_ind).first()
    t2 = session.query(TrackDB).filter_by(track_id=t2_ind).first()

    # if t1 doesn't start yet
    if t1.t_begin >= current_frame:
        return -1, None

    # if t1 is to be cut
    if (t1.t_begin < current_frame) and (t1.t_end >= current_frame):
        _, t1_after = cut_trackDB(session, t1.track_id, current_frame)

    # if t1 is ending before current_frame
    elif t1.t_end < current_frame:
        t1_after = None

        # if there is t1 offsprint detach them as separate trees
        descendants = get_descendants(session, t1.track_id)

        for track in [x for x in descendants if x.track_id != t1.track_id]:
            # cut off the children if they start at a different time
            if (track.parent_track_id == t1.track_id) and (
                track.t_begin != current_frame
            ):
                # this route will call descendants twice but I expect it to be rare
                _, _ = cut_trackDB(session, track.track_id, track.t_begin)

    if operation == "merge":
        # change t1_before
        # does it account for merging with gaps only?
        t1.t_end = t2.t_end

        # merge t2 to t1
        _merge_t2(session, t2, t1, current_frame)
        t2_before = None

    elif operation == "connect":
        # change t1
        t1.t_end = current_frame - 1
        t2_before = _connect_t2(session, t2, t1, current_frame)

    else:
        raise ValueError(
            f"Unknown operation '{operation}'. Use 'merge' or 'connect'."
        )

    return t1_after, t2_before


def update_cellsDB_after_trackDB(
    session: "Session",
    active_label: int,
    current_frame: int,
    new_track: int | None,
    direction: str = "after",
) -> None:
    """Updates cells after a track has been modified.

    This function reassigns or deletes cells based on a track operation
    (e.g., a cut).

    Args:
        session ("Session"): The SQLAlchemy session.
        active_label (int): The original track ID.
        current_frame (int): The frame of the track modification.
        new_track (int | None): The ID of the new track to assign cells to.
            If None, the cells will be deleted.
        direction (str): A filter for which cells to affect: "after",
            "before", or "all". Defaults to "after".
    """

    # query CellDB
    # order by time
    if direction == "after":
        query = (
            session.query(CellDB)
            .filter(
                and_(
                    CellDB.track_id == active_label, CellDB.t >= current_frame
                )
            )
            .order_by(CellDB.t)
            .all()
        )
    elif direction == "before":
        query = (
            session.query(CellDB)
            .filter(
                and_(CellDB.track_id == active_label, CellDB.t < current_frame)
            )
            .order_by(CellDB.t)
            .all()
        )
    elif direction == "all":
        query = (
            session.query(CellDB).filter(CellDB.track_id == active_label).all()
        )
    else:
        raise ValueError("Direction should be 'all', 'before' or 'after'.")

    assert len(query) > 0, "No cells found for the given track"

    # change track_ids
    if new_track is not None:
        for cell in query:
            cell.track_id = new_track
    # or delete the cells
    else:
        for cell in query:
            session.delete(cell)

    session.commit()


def update_trackDB_after_cellDB(
    session: "Session", cell_id: int, current_frame: int
) -> None:
    """Updates a track's time span after a cell is added or removed.

    Ensures that `t_begin` and `t_end` of a track accurately reflect the
    min and max timepoints of its associated cells.

    Args:
        session ("Session"): The SQLAlchemy session.
        cell_id (int): The track ID of the cell that was modified.
        current_frame (int): The frame of the modification.
    """

    track = session.query(TrackDB).filter(TrackDB.track_id == cell_id).first()

    # create a new track object if necessary
    if track is None:

        track = TrackDB(
            track_id=cell_id,
            t_begin=current_frame,
            t_end=current_frame,
            parent_track_id=-1,
            root=cell_id,
        )
        session.add(track)
        session.commit()

    # query for cells
    cells_t = session.query(CellDB.t).filter(CellDB.track_id == cell_id).all()

    # there are cells - adjust the track
    if len(cells_t) > 0:

        cells_t = [cell[0] for cell in cells_t]

        t_min = min(cells_t)
        t_max = max(cells_t)

        if track.t_begin != t_min:
            # cell added to the left
            # cut off this track
            _, new_track = cut_trackDB(session, cell_id, track.t_begin)
            track.t_begin = t_min

        if track.t_end != t_max:
            # cell added to the right
            # cut off the offspring
            offspring = (
                session.query(TrackDB)
                .filter(TrackDB.parent_track_id == cell_id)
                .all()
            )

            for child in offspring:
                _, new_track = cut_trackDB(
                    session, child.track_id, child.t_begin
                )

            track.t_end = t_max

    # remove the track
    else:
        session.delete(track)

    session.commit()


def remove_CellDB(
    session: "Session", cell_id: int, current_frame: int
) -> None:
    """Removes a cell from the database and updates its track.

    Args:
        session ("Session"): The SQLAlchemy session.
        cell_id (int): The track ID of the cell to remove.
        current_frame (int): The frame of the cell to remove.
    """
    cell = (
        session.query(CellDB)
        .filter(CellDB.track_id == cell_id, CellDB.t == current_frame)
        .first()
    )
    if cell is not None:
        session.delete(cell)
        session.commit()
        update_trackDB_after_cellDB(session, cell_id, current_frame)
    else:
        print("Cell not found")


def create_CellDB_core(
    session: "Session", current_frame: int, cell: "RegionProperties"
) -> CellDB:
    """Creates a core CellDB object from regionprops data.

    Args:
        session ("Session"): The SQLAlchemy session.
        current_frame (int): The frame of the new cell.
        cell ("RegionProperties"): The cell data from scikit-image regionprops.

    Returns:
        CellDB: The newly created (but not yet complete) CellDB object.
    """

    # start the object

    # new object starts with a new id because id enforces uniqueness
    new_id = get_new_cell_id(session)
    cell_db = CellDB(id=new_id, t=current_frame, track_id=cell.label)

    cell_db.row = int(cell.centroid[0])
    cell_db.col = int(cell.centroid[1])

    cell_db.bbox_0 = int(cell.bbox[0])
    cell_db.bbox_1 = int(cell.bbox[1])
    cell_db.bbox_2 = int(cell.bbox[2])
    cell_db.bbox_3 = int(cell.bbox[3])

    cell_db.mask = cell.image

    session.add(cell_db)
    session.commit()

    return cell_db


def add_new_CellDB(
    session: "Session",
    current_frame: int,
    cell: "RegionProperties",
    modified: bool = True,
    ch_list: list[da.Array] | None = None,
    signal_function: Callable | None = None,
) -> None:
    """Adds a complete cell with signals and tags to the database.

    Args:
        session ("Session"): The SQLAlchemy session.
        current_frame (int): The frame of the new cell.
        cell ("RegionProperties"): The cell data from scikit-image regionprops.
        modified (bool): Whether to tag the cell as 'modified'. Defaults to True.
        ch_list (list[da.Array] | None): List of dask arrays for signal extraction.
        signal_function (Callable | None): Function to calculate signals.
    """

    cell_db = create_CellDB_core(session, current_frame, cell)

    # add signals to the cell
    if signal_function is not None:
        new_signals = signal_function(cell, current_frame, ch_list)
    else:
        new_signals = {}
    cell_db.signals = new_signals

    # add modified tag to the cell
    tags = {}
    if modified:
        tags["modified"] = True
        cell_db.tags = tags

    session.commit()

    # Update the corresponding track
    update_trackDB_after_cellDB(session, cell_db.track_id, current_frame)


def get_track_note(session: "Session", active_label: int) -> str | None:
    """Retrieves the note for a given track.

    Args:
        session ("Session"): The SQLAlchemy session.
        active_label (int): The ID of the track.

    Returns:
        str | None: The note string, or None if the track is not found.
    """

    query = session.query(TrackDB).filter_by(track_id=active_label).first()

    if query is None:
        return None

    return query.notes


def save_track_note(session: "Session", active_label: int, note: str) -> str:
    """Saves a note for a given track.

    Args:
        session ("Session"): The SQLAlchemy session.
        active_label (int): The ID of the track.
        note (str): The note content to save.

    Returns:
        str: A status message.
    """

    track = session.query(TrackDB).filter_by(track_id=active_label).first()

    if track is None:
        sts = f"Error - track {active_label} is not present in the database."

    else:
        track.notes = note
        flag_modified(track, "notes")
        session.commit()

        sts = f"Note for track {active_label} saved in the database."

    return sts


def toggle_cell_tag(
    session: "Session", active_cell: int, frame: int, annotation: str
) -> str:
    """Toggles a boolean tag for a specific cell.

    Args:
        session ("Session"): The SQLAlchemy session.
        active_cell (int): The track ID of the cell.
        frame (int): The timepoint of the cell.
        annotation (str): The name of the tag to toggle.

    Returns:
        str: A status message.
    """

    cell_list = (
        session.query(CellDB)
        .filter(CellDB.t == frame)
        .filter(CellDB.track_id == active_cell)
        .all()
    )

    if len(cell_list) == 0:
        sts = "Error - no cell found at this frame."
    elif len(cell_list) > 1:
        sts = f"Error - Multiple cells found for {active_cell} at {frame}."
    else:
        cell = cell_list[0]
        tags = cell.tags

        current_state = tags.get(annotation, False)

        tags[annotation] = not current_state

        cell.tags = tags
        flag_modified(cell, "tags")
        session.commit()

        # set status and update graph
        sts = f"Tag {annotation} was set to {not current_state}."

    return sts


def get_tracks_nx_from_root(session: "Session", root_id: int) -> nx.DiGraph:
    """
    Builds a NetworkX graph directly from a database query in a single pass.

    Args:
        session ("Session"): The SQLAlchemy database session.
        root_id (int): The root ID of the track family to build.

    Returns:
        nx.DiGraph: A directed graph representing the lineage tree.
    """
    # Fetch all relevant tracks
    family_tracks = (
        session.query(TrackDB).filter(TrackDB.root == root_id).all()
    )

    # Return an empty graph if no data
    if not family_tracks:
        return nx.DiGraph()

    # Initialize the graph
    G = nx.DiGraph()

    # Iterate through results once to build the graph
    for track in family_tracks:
        G.add_node(
            track.track_id,
            start=track.t_begin,
            stop=track.t_end,
            accepted=track.accepted_tag,
        )

        # If the track has a parent, create an edge
        if track.parent_track_id is not NO_PARENT:
            G.add_edge(track.parent_track_id, track.track_id)

    return G
