"Utility functions for converters."

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import dask.array as da
import networkx as nx
import zarr
from skimage.measure import regionprops
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from track_gardener.config.loader import load_measurement_functions
from track_gardener.config.models import TrackGardenerConfig
from track_gardener.db.db_model import NO_PARENT, CellDB, TrackDB
from track_gardener.signals.factory import create_calculate_signals_function

if TYPE_CHECKING:
    from numpy import ndarray
    from skimage.measure._regionprops import RegionProperties
    from sqlalchemy.orm import Session

################################################################################
################################################################################
# processing segmentation to Track Gardener database


def labeled_frame_to_regionprops(
    labeled_array: "ndarray | da.Array",
    image_arrays: list["ndarray | da.Array"],
    signal_function: Callable[
        ["RegionProperties", int, list["ndarray | da.Array"]], Any
    ],
    time_point: int,
    counter: int,
) -> tuple[list["RegionProperties"], int]:
    """Processes a single labeled frame to extract region properties.

    This function takes a 2D labeled array (a segmentation mask), computes
    region properties for each unique label, calculates additional signals,
    and assigns metadata like time point and a unique ID.

    Args:
        labeled_array: A labeled 2D dask or numpy array segmentation array.
        image_arrays: A list of the raw image data arrays (dask or numpy),
            with each entry in the list corresponding to a specific channel.
        signal_function: A callable that computes signal values for a
            given region. It receives the region's properties, the current
            time point, and the list of image arrays.
        time_point: The integer time point (frame number) of the analysis.
        counter: The starting integer ID for the cells processed in this frame.

    Returns:
        A tuple containing:
            - A list of expanded regionprops objects, each representing a cell with
              its properties, signals, time point, and ID.
            - The updated counter value after processing all cells in the frame.
    """

    # Ensure labeled_array is numpy array
    label_np = (
        labeled_array.compute()
        if hasattr(labeled_array, "compute")
        else labeled_array
    )

    # calculate regions' properties
    regions = regionprops(label_np)

    cell_list = []
    for region in regions:

        # Calculate signals
        signal_data = signal_function(region, time_point, image_arrays)

        # Add additional properties to the region
        region.signals = signal_data
        region.t = time_point
        region.id = counter

        cell_list.append(region)
        counter += 1

    return cell_list, counter


def regionprops_to_cellDB_objects(
    region_list: list["RegionProperties"],
    id_assigner: Callable[["RegionProperties"], tuple[int, int]],
) -> list["CellDB"]:
    """Converts a list of region properties into CellDB database objects.

    Args:
        region_list: A list of region properties objects.
        id_assigner: A callable that takes a region's properties and returns
            a tuple containing the final cell ID and track ID.

    Returns:
        A list of `CellDB` objects ready for database insertion.
    """

    sql_cell_list = []
    for region in region_list:

        cell_id, track_id = id_assigner(region)

        # create CellDB object
        cell = CellDB(
            id=cell_id,
            track_id=track_id,
            t=region.t,
            row=int(region.centroid[0]),
            col=int(region.centroid[1]),
            bbox_0=region.bbox[0],
            bbox_1=region.bbox[1],
            bbox_2=region.bbox[2],
            bbox_3=region.bbox[3],
            mask=region.image,
            signals=region.signals,
            tags={},
        )
        sql_cell_list.append(cell)

    return sql_cell_list


def segmentation_to_cellDB_table(
    segmentation_stack: "ndarray | da.Array",
    config: dict[str, Any],
    session: "Session",
    id_assigner: Callable[["RegionProperties"], tuple[int, int]],
) -> None:
    """Orchestrates the conversion of a segmentation stack to a database table.

    This function serves as a high-level pipeline that takes a full
    labeled segmentation stack, processes each frame to
    extract cell properties, and populates a database table.

    Args:
        segmentation_stack: A dask or numpy array representing the labeled
            segmentation masks over time.
        config: A dictionary containing configuration parameters for the
            analysis pipeline.
        session: An active SQLAlchemy session object for database transactions.
        id_assigner: A callable that determines the final cell ID and track ID
            for a given detected cell.
    """

    signal_channels = config["signal_channels"]

    # Check channel path existence
    for ch in signal_channels:
        path = ch["path"]
        if not os.path.exists(path):
            raise FileNotFoundError(f"Raw image path not found: {path}")

    # Create a function to calculate signals
    config_obj = TrackGardenerConfig.model_validate(config)
    loaded_funcs = load_measurement_functions(config_obj)
    signal_function = create_calculate_signals_function(
        config_obj, loaded_funcs
    )

    # Open channel arrays (assume one zarr per channel, shape = (T, H, W))
    channel_arrays = [da.from_zarr(ch["path"]) for ch in signal_channels]

    counter = 0
    for time_point, labeled_array in enumerate(segmentation_stack):

        # Extract the channel frames for this timepoint
        frame_channel_arrays = [arr[time_point] for arr in channel_arrays]

        # Get regionprops with signals
        cell_list, counter = labeled_frame_to_regionprops(
            labeled_array=labeled_array,
            image_arrays=frame_channel_arrays,
            signal_function=signal_function,
            time_point=time_point,
            counter=counter,
        )

        # Get CellDB objects
        cell_sql_objects = regionprops_to_cellDB_objects(
            cell_list,
            id_assigner=id_assigner,
        )

        # Commit to the database
        session.bulk_save_objects(cell_sql_objects)
        session.commit()


################################################################################
################################################################################
# nx - Track Gardener database conversions


def tracklet_graph_to_TrackDB(
    tracklet_graph: nx.DiGraph, time_prop_name: str = "t"
) -> list[TrackDB]:
    """Converts a tracklet graph into a list of TrackDB SQLAlchemy objects.

    This function analyzes the topology of a tracklet graph, which is assumed
    to be a forest of trees. It iterates over each tree (component), finds
    its unique root, and then creates a TrackDB object for each node,
    assigning the correct parent and root IDs.

    Args:
        tracklet_graph: The input graph where each node is a tracklet_id.
        time_prop_name: The base name of the time property (e.g., 't') to
            find 't_min' and 't_max' attributes on the nodes.

    Returns:
        A list of TrackDB objects ready to be added to a database session.
    """
    sql_objects = []

    for component in nx.weakly_connected_components(tracklet_graph):

        # find the single root node
        root_id = next(
            n for n in component if tracklet_graph.in_degree(n) == 0
        )

        for node_id in component:
            attrs = tracklet_graph.nodes[node_id]

            parent = tracklet_graph.predecessors(node_id)
            parent_id = next(parent, NO_PARENT)

            accepted_tab = attrs.get("accepted_tag", False)

            # Create the SQLAlchemy object
            track_obj = TrackDB(
                track_id=node_id,
                parent_track_id=parent_id,
                root=root_id,
                t_begin=attrs.get(f"{time_prop_name}_min"),
                t_end=attrs.get(f"{time_prop_name}_max"),
                accepted_tag=accepted_tab,
            )
            sql_objects.append(track_obj)

    return sql_objects


def cell_graph_to_CellDB():
    pass  # Placeholder for future implementation


def TG_to_cell_graph(session: "Session") -> nx.DiGraph:
    """Converts tracking database records into a NetworkX directed graph.

    This function queries a database session for cell and track data to
    construct a complete cell lineage graph. The graph contains nodes for
    each cell and two types of edges:
    1.  **Intra-track edges**: Connect cells sequentially within the same track.
    2.  **Inter-track edges**: Connect the last cell of a parent track to the
        first cell of a child track, representing cell division.

    Args:
        session: An active SQLAlchemy session connected to the tracking database.

    Returns:
        A NetworkX `DiGraph` where nodes are cells and edges represent
        temporal succession or lineage relationships.
    """

    G = nx.DiGraph()

    # Fetch all tracks, mapping track_id to parent_track_id
    track_info = session.query(TrackDB.track_id, TrackDB.parent_track_id).all()
    track_to_parent = dict(track_info)

    # Fetch all track IDs
    track_ids = list(track_to_parent.keys())

    # For each track, get all its cells ordered by time
    track_cells = {}
    for track_id in track_ids:
        cells = (
            session.query(CellDB)
            .filter(CellDB.track_id == track_id)
            .order_by(CellDB.t)
            .all()
        )
        if cells:
            track_cells[track_id] = cells
            # Add nodes for these cells
            for cell in cells:
                G.add_node(
                    cell.id,
                    t=cell.t,
                    y=cell.row,
                    x=cell.col,
                    track_id=cell.track_id,
                    segm_id=cell.track_id,
                )
            # Add intra-track edges (successive in time)
            for i in range(len(cells) - 1):
                G.add_edge(
                    cells[i].id,
                    cells[i + 1].id,
                    track_id=track_id,
                    dt=cells[i + 1].t - cells[i].t,
                )

    # Add inter-track (parent-child) edges
    for child_track_id, parent_track_id in track_to_parent.items():
        if (
            parent_track_id is not None
            and parent_track_id in track_cells
            and child_track_id in track_cells
        ):
            parent_cells = track_cells[parent_track_id]
            child_cells = track_cells[child_track_id]
            # Find the last cell in the parent track
            last_parent_cell = parent_cells[-1]
            # Find the first cell in the child track
            first_child_cell = child_cells[0]
            # Add edge from last parent to first child cell
            G.add_edge(
                last_parent_cell.id,
                first_child_cell.id,
                track_id=child_track_id,  # Optionally use child or parent track
                dt=first_child_cell.t - last_parent_cell.t,
                lineage=True,  # mark as a lineage edge
            )

    return G


################################################################################
################################################################################


def build_geff_id_assigner(
    geff_path: str,
    track_id_prop: str = "track_id",
    segm_id_prop: str = "segm_id",
    t_prop: str = "t",
) -> Callable[["RegionProperties"], tuple[int, int] | None]:
    """Builds a function that assigns GEFF and track IDs to region properties.

    This function reads a GEFF (Graph Exchange File Format) graph to
    create a mapping from a time frame and label to the corresponding
    GEFF node ID and track ID (node property). It then returns a callable that uses this
    mapping to facilitate ID assignment.

    Args:
        geff_path: The file path to the GEFF Zarr group.
        track_id_prop: The name of the node property for the track ID.
        segm_id_prop: The name of the node property for the segmentation ID.
        t_prop: The name of the node property for the time frame.

    Returns:
        A function that takes a scikit-image `RegionProperties` object and
        returns a tuple containing the (GEFF ID, track ID), or None if no
        corresponding entry is found in the mapping.
    """

    # Build the mapping dictionary.
    zarr_group = zarr.open(geff_path, mode="r")
    geff_ids = zarr_group["nodes"]["ids"][:]
    geff_track_ids = zarr_group["nodes"]["props"][track_id_prop]["values"][:]
    geff_segm_ids = zarr_group["nodes"]["props"][segm_id_prop]["values"][:]
    geff_times = zarr_group["nodes"]["props"][t_prop]["values"][:]

    mapping = {
        (int(t), int(segm_id)): (int(geff_id), int(track_id))
        for t, segm_id, geff_id, track_id in zip(
            geff_times, geff_segm_ids, geff_ids, geff_track_ids
        )
    }

    # Create the ID assigner function.
    def id_assigner(region: "RegionProperties") -> tuple[int, int] | None:
        """Assigns GEFF ID and track ID based on the region's properties."""
        mapping_key = (region.t, region.label)
        if mapping_key in mapping:
            geff_id, track_id = mapping[mapping_key]
            return geff_id, track_id
        else:
            return None

    return id_assigner


################################################################################
################################################################################


def assign_tracks_relationships(
    db_path: Path | str, parent_radius: float = 20.0
) -> None:
    """Infers and assigns parent-child relationships between tracks in a database.

    This function analyzes all tracks in a database to identify cell division
    events. It assigns a parent to a track if its first cell appears near the
    last cell of a preceding track. It then identifies the root of each
    lineage tree and updates all tracks in that tree with the root's ID.

    Args:
        db_path: The file path to the SQLite tracking database.
        parent_radius: The maximum distance (in pixels) between a parent's
            last cell and a child's first cell to be considered a valid
            lineage link.
    """

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    tracks = {t.track_id: t for t in session.query(TrackDB).all()}

    # Pre-load cell positions: {(track_id, t): (row, col)}
    cell_positions = {}
    for c in session.query(CellDB).all():
        cell_positions[(c.track_id, c.t)] = (c.row, c.col)

    G = nx.DiGraph()
    for t in tracks.values():
        G.add_node(t.track_id)

    # Assign parent relationships
    for child in tracks.values():
        if child.t_begin == 0 or child.parent_track_id != NO_PARENT:
            continue

        t_start = child.t_begin
        child_pos = cell_positions.get((child.track_id, t_start))

        # Find possible parents (tracks that end at t_start - 1)
        possible_parents = [
            t for t in tracks.values() if t.t_end == t_start - 1
        ]

        # Get parent cells at t_start - 1
        best_parent, best_dist = None, float("inf")
        for p in possible_parents:
            parent_pos = cell_positions.get((p.track_id, t_start - 1))
            if parent_pos:
                dist = (
                    (child_pos[0] - parent_pos[0]) ** 2
                    + (child_pos[1] - parent_pos[1]) ** 2
                ) ** 0.5
                if dist < parent_radius and dist < best_dist:
                    best_dist, best_parent = dist, p

        if best_parent:
            child.parent_track_id = best_parent.track_id
            G.add_edge(best_parent.track_id, child.track_id)

    # Now assign roots: For each weakly connected component (lineage)
    for component in nx.weakly_connected_components(G):
        subgraph = G.subgraph(component)
        roots = [n for n in subgraph.nodes if subgraph.in_degree(n) == 0]
        if len(roots) != 1:
            continue  # Or handle error
        root_id = roots[0]

        # Traverse down and set root for all descendants
        for node in nx.descendants(subgraph, root_id) | {root_id}:
            tracks[node].root = root_id

    # Commit all changes
    session.commit()
    session.close()
