"""SQLAlchemy ORM models for storing cell tracking data.

This module defines the database schema for storing information about individual
cells and their corresponding tracks over time.

- `CellDB`: Represents a single cell observation at a specific timepoint.
- `TrackDB`: Represents a complete cell track (linear but not maximum possible length, analog to cell cycle).
"""

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    PickleType,
    String,
)
from sqlalchemy.orm import declarative_base

# --- Constants ---
# Constant value to indicate a track has no parent
NO_PARENT: int = -1
# Constant value to indicate a cell has no shape/mask information
NO_SHAPE: int = -1
# Constant value for an empty dictionary for signal or tag data
NO_SIGNAL: dict[str, Any] = {}

Base = declarative_base()


class CellDB(Base):
    """
    SQLAlchemy model for an individual cell at a single timepoint.

    This table stores the state of a cell, including its position, bounding box,
    mask, and any associated measurements (signals) or annotations (tags) for
    a given frame. Each entry is uniquely identified by a composite key of
    its track ID and timepoint.

    Attributes:
        track_id (int): Foreign key linking to the TrackDB table. Part of the
            composite primary key.
        t (int): The timepoint or frame number for this cell observation. Part
            of the composite primary key.
        id (int): A unique identifier for the cell observation (only for
            external referencing)
        row (int): The row coordinate of the cell's centroid.
        col (int): The column coordinate of the cell's centroid.
        bbox_0 (int): The minimum row coordinate of the cell's bounding box.
        bbox_1 (int): The minimum column coordinate of the cell's bounding box.
        bbox_2 (int): The maximum row coordinate of the cell's bounding box.
        bbox_3 (int): The maximum column coordinate of the cell's bounding box.
        mask (Any): The pickled binary mask of the cell.
        signals (dict): A JSON field to store arbitrary quantitative
            measurements (e.g., fluorescence intensity).
        tags (dict): A JSON field to store arbitrary qualitative labels or
            annotations.
    """

    __tablename__ = "cells"
    __table_args__ = (
        # Index to optimize spatial (FOV) queries at a given timepoint
        Index("idx_t_bboxes", "t", "bbox_0", "bbox_1", "bbox_2", "bbox_3"),
    )

    # Composite primary key for fast and unique (track_id, t) lookups
    track_id = Column(Integer, ForeignKey("tracks.track_id"), primary_key=True)
    t = Column(Integer, primary_key=True)

    # Keep id for external reference, but not a PK
    id = Column(BigInteger, unique=True)

    row = Column(Integer)
    col = Column(Integer)

    # Bounding box columns for spatial queries
    bbox_0 = Column(Integer, default=NO_SHAPE, nullable=False)
    bbox_1 = Column(Integer, default=NO_SHAPE, nullable=False)
    bbox_2 = Column(Integer, default=NO_SHAPE, nullable=False)
    bbox_3 = Column(Integer, default=NO_SHAPE, nullable=False)

    mask = Column(PickleType, default=NO_SHAPE)
    signals = Column(JSON, default=NO_SIGNAL)
    tags = Column(JSON, default=NO_SIGNAL)

    def __repr__(self):
        """String representation of the cell observation."""
        return (
            f"{self.id} from frame {self.t} with track_id {self.track_id} "
            f"at ({self.row},{self.col})"
        )


class TrackDB(Base):
    """
    SQLAlchemy model for a cell track.

    This table represents a single continuous track, linking a sequence of
    CellDB objects over time. It includes lineage information (parent and root)
    and metadata such as annotations and notes.

    Attributes:
        track_id (int): The unique primary key for the track.
        parent_track_id (int): The track_id of the parent track in a division
            event. Defaults to NO_PARENT (-1) if there is no parent.
        root (int): The track_id of the root of the lineage tree. Indexed for
            efficient querying of entire cell families.
        t_begin (int): The starting timepoint or frame of the track.
        t_end (int): The ending timepoint or frame of the track.
        accepted_tag (bool): A boolean flag, often used to mark tracks that
            have been manually reviewed and accepted.
        tags (dict): A JSON field to store arbitrary qualitative labels or
            annotations for the entire track.
        notes (str): A string field for free-text user notes about the track.
    """

    __tablename__ = "tracks"

    track_id = Column(Integer, primary_key=True)
    parent_track_id = Column(Integer)

    # indexed to speed up queries for entire families
    root = Column(Integer, index=True)

    t_begin = Column(Integer)
    t_end = Column(Integer)

    # Boolean column to flag tracks
    accepted_tag = Column(Boolean, default=False)

    # JSON column for dynamic tagging
    tags = Column(JSON, default={})

    # Text column for notes
    notes = Column(String, default="")

    def __repr__(self):
        """String representation of the track."""
        return f"Track {self.track_id} from {self.t_begin} to {self.t_end}"
