import os

import dask.array as da
import geff
import zarr
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

from track_gardener.config.config_functions import (
    create_calculate_signals_function,
)
from track_gardener.converters.nx_2_gardener import graph_to_trackdb
from track_gardener.converters.track_array_2_gardener import (
    convert_labeled_frame_to_cells,
)
from track_gardener.db.db_model import Base


def build_geff_mapping_from_zarr(
    zarr_path, track_id_prop="track_id", segm_id_prop="segm_id", t_prop="t"
):
    """
    Loads mapping arrays from a GEFF-format Zarr group and constructs:
        mapping[(t, segm_id)] = (geff_id, geff_track_id)

    Args:
        zarr_path (str): Path to the Zarr group containing GEFF data.
        track_id_prop (str): Field name for track IDs (default 'track_id')
        segm_id_prop (str): Field name for segmentation labels (default 'segm_id')
        t_field_prop (str): Field name for time (default 't')

    Returns:
        dict: mapping[(t, segm_id)] = (geff_id, geff_track_id)
    """

    zarr_group = zarr.open(zarr_path, mode="r")

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
    return mapping

    return mapping


def segm_geff_to_cellDB(labeled_arrays, config, geff_group_path, session):
    """ """
    # Check channel path existence
    signal_channels = config["signal_channels"]

    for ch in signal_channels:
        path = ch["path"]
        if not os.path.exists(path):
            logger.error("Raw image path not found: %s", path)
            raise FileNotFoundError(f"Raw image path not found: {path}")
    channel_arrays = [da.from_zarr(ch["path"]) for ch in signal_channels]

    # create a function to calculate signals
    signal_function = create_calculate_signals_function(config)

    # get mapping from GEFF Zarr group
    mapping = build_geff_mapping_from_zarr(geff_group_path)

    counter = 0
    for time_point, labeled_array in tqdm(
        enumerate(labeled_arrays), total=len(labeled_arrays)
    ):
        frame_channel_arrays = [arr[time_point] for arr in channel_arrays]
        cell_list, counter = convert_labeled_frame_to_cells(
            labeled_array=labeled_array,
            image_arrays=frame_channel_arrays,
            signal_function=signal_function,
            time_point=time_point,
            id=counter,  # counter of cells processed so far
        )
        for cell in cell_list:
            key = (cell.t, cell.track_id)
            mapped = mapping.get(key)
            if mapped is not None:
                cell.id, cell.track_id = mapped
            else:
                print(
                    f"[WARNING] No mapping for cell at (t={cell.t}, track_id={cell.track_id})"
                )
        session.bulk_save_objects(cell_list)
        session.commit()


def segm_geff_to_db(labeled_arrays, config, geff_group_path) -> None:
    """ """
    db_path = config["database"]["path"]
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()

    segm_geff_to_cellDB(labeled_arrays, config, geff_group_path, session)

    G, g_meta = geff.read_nx(geff_group_path)
    tracks = graph_to_trackdb(G)
    with Session() as session:
        session.bulk_save_objects(tracks)
        session.commit()
