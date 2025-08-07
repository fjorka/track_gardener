import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import your models and checks
from track_gardener.db.db_model import NO_PARENT, Base, CellDB, TrackDB
from track_gardener.db.db_validate import (
    build_track_graph,
    check_columns_present,
    check_no_orphan_cells,
    check_no_orphan_tracks,
    check_tables_present,
)


@pytest.fixture(scope="function")
def session():
    """Provide a session with an empty in-memory SQLite DB and tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


@pytest.fixture
def add_tracks_cells(session):
    """Populate the DB with tracks and cells for testing."""
    # Create 3 tracks, 2 cells for the first two tracks
    t1 = TrackDB(track_id=1, parent_track_id=None, root=1, t_begin=0, t_end=5)
    t2 = TrackDB(track_id=2, parent_track_id=1, root=1, t_begin=6, t_end=10)
    t3 = TrackDB(track_id=3, parent_track_id=None, root=3, t_begin=0, t_end=3)
    c1 = CellDB(track_id=1, t=0, id=100, row=0, col=0)
    c2 = CellDB(track_id=2, t=6, id=200, row=0, col=0)
    session.add_all([t1, t2, t3, c1, c2])
    session.commit()
    return (t1, t2, t3), (c1, c2)


def test_check_tables_present_exists(session):
    errors = check_tables_present(session, [CellDB, TrackDB])
    assert errors == []


def test_check_tables_present_missing(session):
    Base.metadata.tables["tracks"].drop(session.bind)
    errors = check_tables_present(session, [CellDB, TrackDB])
    assert errors
    assert "tracks" in errors[0]


def test_check_columns_present_ok(session):
    print("CellDB __table__ exists:", hasattr(CellDB, "__table__"))
    errors = check_columns_present(session, [CellDB, TrackDB])
    assert errors == []


def test_check_no_orphan_cells(session, add_tracks_cells):
    # Remove track 2, so cell c2 becomes orphaned
    session.query(TrackDB).filter(TrackDB.track_id == 2).delete()
    session.commit()
    errors = check_no_orphan_cells(session)
    assert errors
    assert (
        "Orphaned cells found" in errors[0]
    ), f"Expected orphaned cells error, got: {errors[0]}"


def test_check_no_orphan_cells_none(session, add_tracks_cells):
    errors = check_no_orphan_cells(session)
    assert errors == []


def test_check_no_orphan_tracks(session, add_tracks_cells):
    """
    Fixture provides a track without cells.
    """

    errors = check_no_orphan_tracks(session)
    assert errors == ["Tracks with no associated cells: [Track 3 from 0 to 3]"]


def test_check_no_orphan_tracks_none(session):
    # Add a track and associated cell
    t1 = TrackDB(track_id=1, parent_track_id=None, root=1, t_begin=0, t_end=5)
    c1 = CellDB(track_id=1, t=0, id=100, row=0, col=0)
    session.add_all([t1, c1])
    session.commit()
    errors = check_no_orphan_tracks(session)
    assert errors == []


def test_build_track_graph_missing_parent():
    t1 = TrackDB(
        track_id=1, parent_track_id=NO_PARENT, root=1, t_begin=0, t_end=4
    )
    t2 = TrackDB(track_id=2, parent_track_id=999, root=1, t_begin=5, t_end=8)
    tracks = [t1, t2]
    G, errors = build_track_graph(tracks, no_parent=NO_PARENT)
    assert any("Parent 999 not found" in e for e in errors)


def test_build_track_graph_time_error():
    t1 = TrackDB(
        track_id=1, parent_track_id=NO_PARENT, root=1, t_begin=0, t_end=10
    )
    t2 = TrackDB(track_id=2, parent_track_id=1, root=1, t_begin=5, t_end=8)
    tracks = [t1, t2]
    G, errors = build_track_graph(tracks, no_parent=NO_PARENT)
    assert any(
        "Parent 1 ends at 10, but child 2 begins at 5." in e for e in errors
    )
