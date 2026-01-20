"""Converts between Track-Gardener databases and GEFF files."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import dask.array as da
import geff
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from track_gardener.converters.nx_tracks_functions import (
    assign_tracklet_ids,
    build_tracklet_graph,
)
from track_gardener.converters.utils import (
    TG_to_cell_graph,
    build_geff_id_assigner,
    segmentation_to_cellDB_table,
    tracklet_graph_to_TrackDB,
)
from track_gardener.db.db_model import Base

if TYPE_CHECKING:
    from numpy import ndarray


################################################################################
################################################################################


def segm_and_geff_to_TG(
    segmentation_stack: "ndarray | da.Array",
    geff_group_path: str,
    config: dict[str, Any],
) -> None:
    """Converts labeled stack and GEFF data into a database based on the config.

    This function orchestrates the process of creating a SQLite database from
    a segmentation stack and a GEFF graph.
    Tracks table is created from the GEFF graph.
    Cells table is created based on the segmentation stack and the configuration file, it assumes that the node properties of geff contain segm_id that corresponds to the cell ID in the segmentation stack.

    Args:
        segmentation_stack: A 3D dask or NumPy array representing the labeled
            segmentation stack, with dimensions (T, Y, X).
        geff_group_path: The file path to the GEFF Zarr group.
        config: A dictionary containing configuration parameters for TrackGardener.
    """

    # Create the database engine
    db_path = config["database"]["path"]
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    # Get the assigner
    id_assigner = build_geff_id_assigner(geff_group_path)

    # Create the cells table
    # This function commits to the database by frame
    with Session() as session:
        segmentation_to_cellDB_table(
            segmentation_stack, config, session, id_assigner
        )

    # Create the tracks table
    geff_reader = geff.GeffReader(geff_group_path)

    # Load all node and edge properties (or select specific ones)
    geff_reader.read_node_props()
    geff_reader.read_edge_props()

    # Read the data into memory
    in_memory_geff = geff_reader.build()

    # Construct a graph representation using the "networkx" backend
    G = geff.construct(**in_memory_geff, backend="networkx")

    G = assign_tracklet_ids(G, attribute_name="track_id")
    G_tracklets = build_tracklet_graph(
        G, attribute_name="track_id", prop_names=["t"]
    )
    tracks_sql_objects = tracklet_graph_to_TrackDB(
        G_tracklets, time_prop_name="t"
    )

    with Session() as session:
        session.bulk_save_objects(tracks_sql_objects)
        session.commit()


################################################################################
################################################################################


def TG_to_geff(db_path: Path | str, geff_path: Path | str) -> None:
    """Converts a Track-Gardener database to a GEFF file.

    This function reads a Track-Gardener (TG) SQLite database, converts its
    contents into a NetworkX graph representing cell lineages, and then writes
    that graph to a Zarr store using the GEFF specification.

    Args:
        db_path: The file path to the source Track-Gardener SQLite database.
        geff_path: The destination file path for the output GEFF Zarr store.
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)

    with Session() as session:
        g = TG_to_cell_graph(session)

    geff.write_nx(
        graph=g,
        store=geff_path,
        axis_names=["t", "y", "x"],
        axis_types=["time", "space", "space"],
        zarr_format=2,
    )


################################################################################
################################################################################
