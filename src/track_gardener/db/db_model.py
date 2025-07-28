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

# constant value to indicate it has no parent
NO_PARENT = -1
NO_SHAPE = -1
NO_SIGNAL = {}

Base = declarative_base()


class CellDB(Base):
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
        return (
            f"{self.id} from frame {self.t} with track_id {self.track_id} "
            f"at ({self.row},{self.col})"
        )


class TrackDB(Base):
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
        return f"Track {self.track_id} from {self.t_begin} to {self.t_end}"
