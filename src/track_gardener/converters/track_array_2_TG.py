"""Converter from track ID segmentation arrays to Track-Gardener database."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from track_gardener.converters.utils import segmentation_to_cellDB_table
from track_gardener.db.db_functions import build_trackdb_from_celldb
from track_gardener.db.db_model import Base, CellDB

if TYPE_CHECKING:
    import dask.array as da
    from numpy import ndarray


def trackID_array_to_TG(
    segmentation_stack: "ndarray | da.Array", config: dict[str, Any]
) -> None:
    """Converts a track ID segmentation stack to a Track-Gardener database.

    This function processes a segmentation stack where each unique label
    corresponds to a track ID. It populates the `CellDB` and `TrackDB` tables
    in a SQLite database.

    Args:
        segmentation_stack: A 3D NumPy array of shape (T, Y, X) where each
            labeled region corresponds to a cell and the label value is its
            track ID.
        config: A dictionary containing configuration, including the database
            path under `config["database"]["path"]`.
    """
    db_path = config["database"]["path"]
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = Session()

    # create cells table
    def id_assigner(region):
        """Assigns cell ID and track ID based on the region."""
        return region.id, region.label

    segmentation_to_cellDB_table(
        segmentation_stack, config, session, id_assigner
    )

    # build TrackDB based on the CellDB table
    rows = session.query(CellDB.track_id, CellDB.t).all()
    track_id_seq, t_seq = zip(*rows) if rows else ([], [])
    tracks = build_trackdb_from_celldb(track_id_seq, t_seq)
    session.bulk_save_objects(tracks)
    session.commit()
