import os
from typing import List, Sequence

import dask.array as da
import networkx as nx
import numpy as np
from loguru import logger
from skimage.measure import regionprops
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from track_gardener.db.config_functions import (
    create_calculate_signals_function,
)
from track_gardener.db.db_model import NO_PARENT, Base, CellDB, TrackDB

# rename these converters to more meaningful names


def convert_array_segmentations_to_cells(labeled_arrays, config, session):
    """ """

    signal_channels = config["signal_channels"]

    # Check channel path existence
    for ch in signal_channels:
        path = ch["path"]
        if not os.path.exists(path):
            logger.error("Raw image path not found: %s", path)
            raise FileNotFoundError(f"Raw image path not found: {path}")

    signal_function = create_calculate_signals_function(config)

    # Open channel arrays (assume one zarr per channel, shape = (T, H, W))
    channel_arrays = [da.from_zarr(ch["path"]) for ch in signal_channels]

    counter = 0
    for time_point, labeled_array in enumerate(labeled_arrays):
        # Extract the channel frames for this timepoint
        frame_channel_arrays = [arr[time_point] for arr in channel_arrays]
        cell_list, counter = convert_labeled_frame_to_cells(
            labeled_array=labeled_array,
            image_arrays=frame_channel_arrays,
            signal_function=signal_function,
            time_point=time_point,
            counter=counter,
        )
        session.bulk_save_objects(cell_list)
        session.commit()


def convert_array_segmentations_to_db(labeled_arrays, config):
    """ """
    db_path = config["database"]["path"]
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()

    # add cells
    convert_array_segmentations_to_cells(labeled_arrays, config, session)

    # build TrackDB based on the CellDB table
    rows = session.query(CellDB.track_id, CellDB.t).all()
    track_id_seq, t_seq = zip(*rows) if rows else ([], [])
    tracks = build_trackdb_from_celldb(track_id_seq, t_seq)
    session.bulk_save_objects(tracks)
    session.commit()


def convert_labeled_frame_to_cells(
    labeled_array,
    image_arrays,
    signal_function,
    time_point,
    counter,  # counter of cells processed so far
) -> List[CellDB]:
    """
    Process a single labeled frame and store region data in the database.
    """
    # Ensure labeled_array is numpy array
    label_np = (
        labeled_array.compute()
        if hasattr(labeled_array, "compute")
        else labeled_array
    )
    regions = regionprops(label_np)

    logger.info(f"Found {len(regions)} labeled objects at t={time_point}")

    cell_list = []
    for region in regions:
        label = region.label
        centroid = tuple(map(int, region.centroid))
        bbox = region.bbox
        mask = region.image

        # --- Signal computation ---
        signal_data = signal_function(region, time_point, image_arrays)

        # --- CellDB entry ---
        cell = CellDB(
            track_id=label,
            t=time_point,
            id=counter,
            row=centroid[0],
            col=centroid[1],
            bbox_0=bbox[0],
            bbox_1=bbox[1],
            bbox_2=bbox[2],
            bbox_3=bbox[3],
            mask=mask,
            signals=signal_data,
            tags={},
        )
        cell_list.append(cell)
        counter += 1

    return cell_list, counter


def build_trackdb_from_celldb(
    track_id_seq: Sequence[int], t_seq: Sequence[int]
) -> List[TrackDB]:
    """Builds TrackDB objects from track_id and t sequences.

    Args:
        track_id_seq: Sequence of track IDs (ints).
        t_seq: Sequence of frame indices (ints), parallel to track_id_seq.

    Returns:
        List[TrackDB]: One TrackDB object per unique track_id, with t_begin/min(t) and t_end/max(t).
    """
    track_ids = np.asarray(track_id_seq)
    ts = np.asarray(t_seq)
    if track_ids.shape != ts.shape:
        raise ValueError("track_id_seq and t_seq must be the same length.")

    # Find unique track IDs and the indices to reconstruct groups
    unique_tracks, inv = np.unique(track_ids, return_inverse=True)

    t_min = np.full(unique_tracks.shape, np.inf)
    t_max = np.full(unique_tracks.shape, -np.inf)

    # For each entry, update min/max using the unique track index
    np.minimum.at(t_min, inv, ts)
    np.maximum.at(t_max, inv, ts)

    # Construct TrackDB objects
    tracks = []
    for i, tid in enumerate(unique_tracks):
        track = TrackDB(
            track_id=int(tid),
            parent_track_id=NO_PARENT,
            root=int(tid),
            t_begin=int(t_min[i]),
            t_end=int(t_max[i]),
        )
        tracks.append(track)
    return tracks


def assign_tracks_relationships(db_path, parent_radius=20):

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
