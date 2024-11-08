from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.orm import make_transient, sessionmaker

import track_gardener.db.db_functions as fdb
from track_gardener.db.db_functions import (
    add_new_core_CellDB,
    cellsDB_after_trackDB,
    cut_trackDB,
    delete_trackDB,
    get_descendants,
    integrate_trackDB,
    newTrack_number,
    remove_CellDB,
    trackDB_after_cellDB,
)
from track_gardener.db.db_model import NO_PARENT, CellDB, TrackDB


@pytest.fixture(scope="function")
def db_session():
    # see "./tests/fixtures/test_database_content.PNG" for a visual representation of copied part of the test database
    test_db_path = str(
        Path(__file__).parent / "fixtures" / "db_2tables_test.db"
    )
    original_engine = create_engine(f"sqlite:///{test_db_path}")
    original_metadata = MetaData()
    original_metadata.reflect(bind=original_engine)

    # Create an in-memory SQLite database
    memory_engine = create_engine("sqlite:///:memory:")
    original_metadata.create_all(memory_engine)

    # Open sessions
    OriginalSession = sessionmaker(bind=original_engine)
    MemorySession = sessionmaker(bind=memory_engine)

    original_session = OriginalSession()
    memory_session = MemorySession()

    # Copy tables
    cells = original_session.query(CellDB).all()
    tracks = original_session.query(TrackDB).all()

    for cell in cells:
        # Create a new instance of CellDB
        new_cell = CellDB()

        # Deep copy
        for key, value in inspect(cell).attrs.items():
            setattr(new_cell, key, value.value)

        memory_session.add(new_cell)

    for track in tracks:
        # Create a new instance of TrackDB
        new_track = TrackDB()

        # Deep copy
        for key, value in inspect(track).attrs.items():
            setattr(new_track, key, value.value)

        memory_session.add(new_track)

    original_session.close()

    # add additional tracks (no cells)
    # 1 (0 - 10)
    # 1-2 (11 - 50)
    # 1-3 (11 - 20)
    # 3-4 (21 - 40)
    # 5 unconnected starts (41 - 45)
    # Track 20422 from 0 to 42
    # Track 20426 from 43 to 80
    new_track = TrackDB(
        track_id=1, parent_track_id=NO_PARENT, root=1, t_begin=0, t_end=10
    )
    memory_session.add(new_track)
    new_track = TrackDB(
        track_id=2, parent_track_id=1, root=1, t_begin=11, t_end=50
    )
    memory_session.add(new_track)
    new_track = TrackDB(
        track_id=3, parent_track_id=1, root=1, t_begin=11, t_end=20
    )
    memory_session.add(new_track)
    new_track = TrackDB(
        track_id=4, parent_track_id=3, root=1, t_begin=21, t_end=40
    )
    memory_session.add(new_track)

    # freely floating track
    new_track = TrackDB(
        track_id=5, parent_track_id=-1, root=5, t_begin=41, t_end=45
    )
    memory_session.add(new_track)

    memory_session.commit()

    yield memory_session  # This is where the testing happens

    memory_session.close()


def test_starting_db(db_session):
    """Verify that the test database is set up correctly."""
    assert db_session.query(TrackDB).filter_by(track_id=37401).one()


def test_getting_signals(db_session):
    """
    Test getting the list of signal names from the database.
    """
    expected_list = ["area", "ch0_nuc", "ch0_cyto", "ch1_nuc", "ch1_cyto"]

    signal_list = fdb.get_signals(db_session)

    assert (
        signal_list == expected_list
    ), f"Expected {expected_list}, got {signal_list}"


def test_adding_track(db_session):
    """Test - add a new track"""
    new_track = TrackDB(
        track_id=100, parent_track_id=None, root=0, t_begin=0, t_end=10
    )
    db_session.add(new_track)
    db_session.commit()

    # Verify the record was added
    assert db_session.query(TrackDB).filter_by(track_id=100).one()


def test_remove_track(db_session):
    """Test - remove a track"""
    to_del = 1
    status = delete_trackDB(db_session, to_del)
    assert status == f"Track {to_del} has been deleted."

    # Verify the record was removed
    assert not db_session.query(TrackDB).filter_by(track_id=to_del).all()

    # Verify that the offspring has expected properties
    offspring = db_session.query(TrackDB).filter_by(track_id=2).one()
    assert offspring.parent_track_id == NO_PARENT
    assert offspring.root == 2

    offspring = db_session.query(TrackDB).filter_by(track_id=3).one()
    assert offspring.parent_track_id == NO_PARENT
    assert offspring.root == 3

    # check grandchildren
    grandchild = db_session.query(TrackDB).filter_by(track_id=4).one()
    assert grandchild.parent_track_id == 3
    assert grandchild.root == 3


def test_remove_none_track(db_session):
    """Test - remove a track"""
    to_del = 6
    init_len = db_session.query(TrackDB).all()
    status = delete_trackDB(db_session, to_del)
    assert status == "Track not found"
    assert len(db_session.query(TrackDB).all()) == len(init_len)


def test_newTrack_number(db_session):
    """Test - getting a new track number."""

    new_track = newTrack_number(db_session)
    assert new_track == 37404

    new_track_number = 6e10
    new_track = TrackDB(
        track_id=new_track_number,
        parent_track_id=None,
        root=0,
        t_begin=0,
        t_end=10,
    )
    db_session.add(new_track)
    db_session.commit()

    new_track = newTrack_number(db_session)
    assert new_track == new_track_number + 1


def test_newTrack_number_empty_db(db_session):
    """Test - getting a new track number
    while the database is empty"""

    # clear the database
    query = db_session.query(TrackDB).all()
    ids_list = [x.track_id for x in query]
    for run_id in ids_list:
        _ = delete_trackDB(db_session, run_id)

    # check that it's empty
    query = db_session.query(TrackDB).all()
    assert len(query) == 0, f"Expected database to be empty, got {len(query)}"

    # asssert the correct new track number
    new_track = newTrack_number(db_session)
    assert new_track == 1, f"Expected 1, got {new_track}"


def test_get_descendants(db_session):
    """Test checking we get correct descendants."""

    # test at the root level
    active_label = 37401
    descendants = get_descendants(db_session, active_label)

    assert len(descendants) == 3

    descendants_list = [x.track_id for x in descendants]
    descendants_list.sort()
    assert descendants[0].track_id == active_label
    assert descendants_list == [37401, 37402, 37403]

    # test lower in the tree
    active_label = 3
    descendants = get_descendants(db_session, active_label)

    assert len(descendants) == 2

    descendants_list = [x.track_id for x in descendants]
    descendants_list.sort()
    assert descendants[0].track_id == active_label
    assert descendants_list == [3, 4]


def test_cut_trackDB(db_session):
    """Test checking that a track is modified correctly."""

    active_label = 20422
    current_frame = 5

    new_track_expected = newTrack_number(db_session)

    mitosis, new_track = cut_trackDB(db_session, active_label, current_frame)

    # assert expected output of the function
    assert mitosis is False
    assert new_track == new_track_expected

    # assert that the new track is in the database
    assert db_session.query(TrackDB).filter_by(track_id=new_track).one()

    # assert that the new track has expected properties
    assert (
        db_session.query(TrackDB).filter_by(track_id=new_track).one().t_begin
        == 5
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=new_track).one().t_end
        == 42
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=new_track)
        .one()
        .parent_track_id
        == -1
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=new_track).one().root
        == new_track
    )

    # assert that the old track is modified
    assert (
        db_session.query(TrackDB).filter_by(track_id=active_label).one().t_end
        == 4
    )

    # assert that the children are modified
    assert (
        db_session.query(TrackDB).filter_by(track_id=20423).one().root
        == new_track
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=20423)
        .one()
        .parent_track_id
        == new_track
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=20426).one().root
        == new_track
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=20426)
        .one()
        .parent_track_id
        == new_track
    )

    # assert that the grandchildren are modified
    assert (
        db_session.query(TrackDB).filter_by(track_id=20425).one().root
        == new_track
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=20425)
        .one()
        .parent_track_id
        == 20423
    )


def test_cut_trackDB_beyond_track(db_session):
    """Test checking that calling cut on a frame where a track doesn't exist doesn't modify the track."""

    active_label = 2
    current_frame = 1

    t1_org = db_session.query(TrackDB).filter_by(track_id=active_label).one()
    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    mitosis, new_track = cut_trackDB(db_session, active_label, current_frame)

    t1_new = db_session.query(TrackDB).filter_by(track_id=active_label).one()

    # assert that t1 new and t1 are the same
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            assert getattr(t1_new, key) == getattr(t1, key)


def test_cut_trackDB_mitosis(db_session):
    """
    Test cut_TrackDB function when cutting from mitosis.
    """

    active_label = 37402

    record = db_session.query(TrackDB).filter_by(track_id=active_label).one()

    t_begin_org = record.t_begin
    t_end_org = record.t_end

    new_track_hypothesis = newTrack_number(db_session)

    mitosis, new_track = cut_trackDB(db_session, active_label, t_begin_org)

    # assert expected output of the function
    assert mitosis is True
    assert new_track is None

    # assert that the active label track is in the database
    assert db_session.query(TrackDB).filter_by(track_id=active_label).one()

    # assert that the changed track has expected properties
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_begin
        == t_begin_org
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=active_label).one().t_end
        == t_end_org
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .parent_track_id
        == -1
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=active_label).one().root
        == active_label
    )

    # assert that the new track was not created
    assert (
        len(
            db_session.query(TrackDB)
            .filter_by(track_id=new_track_hypothesis)
            .all()
        )
        == 0
    )


def test_cut_merge_trackDB(db_session):
    """Test checking that a track is modified correctly."""

    active_label = 20422
    current_frame = 5

    new_track_expected = newTrack_number(db_session)

    mitosis, new_track = cut_trackDB(db_session, active_label, current_frame)

    # assert expected output of the function
    assert mitosis is False
    assert new_track == new_track_expected

    # re-merge new to old
    t1_ind = 20422
    t2_ind = new_track
    _ = integrate_trackDB(db_session, "merge", t1_ind, t2_ind, current_frame)

    # assert that the new track is in the database
    assert (
        len(db_session.query(TrackDB).filter_by(track_id=new_track).all()) == 0
    )

    # assert that the new track has expected properties
    assert (
        db_session.query(TrackDB).filter_by(track_id=t1_ind).one().t_begin == 0
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=t1_ind).one().t_end == 42
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=t1_ind)
        .one()
        .parent_track_id
        == -1
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=t1_ind).one().root
        == t1_ind
    )

    # assert that the children are not modified
    assert (
        db_session.query(TrackDB).filter_by(track_id=20423).one().root
        == t1_ind
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=20423)
        .one()
        .parent_track_id
        == t1_ind
    )
    assert (
        db_session.query(TrackDB).filter_by(track_id=20426).one().root
        == t1_ind
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=20426)
        .one()
        .parent_track_id
        == t1_ind
    )

    # assert that the grandchildren are not modified
    assert (
        db_session.query(TrackDB).filter_by(track_id=20425).one().root
        == t1_ind
    )
    assert (
        db_session.query(TrackDB)
        .filter_by(track_id=20425)
        .one()
        .parent_track_id
        == 20423
    )


def test_cellsDB_after_trackDB_nonsense_call(db_session):
    """Test nonsense call response"""

    active_label = 20422

    current_frame = 3
    new_track = 100

    with pytest.raises(ValueError) as exc_info:
        _ = cellsDB_after_trackDB(
            db_session,
            active_label,
            current_frame,
            new_track,
            direction="left",
        )

    exp_status = "Direction should be 'all', 'before' or 'after'."
    assert str(exc_info.value) == exp_status


def test_cellsDB_after_trackDB(db_session):
    """Test modifications in the cells table after a track is moodified."""

    active_label = 20422

    # check how long the track is before the cut
    org_stop = (
        db_session.query(TrackDB).filter_by(track_id=active_label).one().t_end
    )

    current_frame = 3
    new_track = 100

    _ = cellsDB_after_trackDB(
        db_session, active_label, current_frame, new_track, direction="after"
    )

    # assert that there are only 3 objects of old track in the cell table after cut
    assert (
        len(db_session.query(CellDB).filter_by(track_id=active_label).all())
        == current_frame
    )

    # assert that there is expected number of objects in new track
    assert len(
        db_session.query(CellDB).filter_by(track_id=new_track).all()
    ) == (org_stop - current_frame + 1)


def test_modify_track_cellsDB_before(db_session):
    """Test checking whether the cellsDB_after_trackDB - in before direction."""

    active_label = 20422

    # check how long the track is before the cut
    org_stop = (
        db_session.query(TrackDB).filter_by(track_id=active_label).one().t_end
    )

    current_frame = 5
    new_track = 100

    _ = cellsDB_after_trackDB(
        db_session, active_label, current_frame, new_track, direction="before"
    )

    # assert that there are only n objects of old track in the cell table after cut
    assert len(
        db_session.query(CellDB).filter_by(track_id=active_label).all()
    ) == (org_stop - current_frame + 1)

    # assert that there is expected number of objects in new track
    assert (
        len(db_session.query(CellDB).filter_by(track_id=new_track).all())
        == current_frame
    )


def test_freely_floating_merge(db_session):
    """Test merging when no cut is needed."""

    t1_ind = 4
    t2_ind = 5
    current_frame = 41

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t2_org = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    t2 = TrackDB()
    for key in t2_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t2, key, getattr(t2_org, key))

    # Detach the copy from the session
    make_transient(t2)

    _ = integrate_trackDB(db_session, "merge", t1_ind, t2_ind, current_frame)

    # assert that the merger from track is not in the database
    assert len(db_session.query(TrackDB).filter_by(track_id=t2_ind).all()) == 0

    # assert that the merger to has expected properties
    new_t1 = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert new_t1.t_end == t2.t_end
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root


def test_double_cut_merge(db_session):
    """Test merging tracks when both need to be cut."""

    t1_ind = 37401
    t2_ind = 20422
    current_frame = 30

    expected_new_track = newTrack_number(db_session)

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t2_org = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    # copies are necessary for comparison of properties later in the test
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    t2 = TrackDB()
    for key in t2_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t2, key, getattr(t2_org, key))

    # Detach the copy from the session
    make_transient(t2)

    _ = integrate_trackDB(db_session, "merge", t1_ind, t2_ind, current_frame)

    # assert that the merger from track is not in the database
    assert db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t1_new = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    t2_new = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    assert (
        db_session.query(TrackDB).filter_by(track_id=expected_new_track).one()
    )
    t_new = (
        db_session.query(TrackDB).filter_by(track_id=expected_new_track).one()
    )

    # assert that the merger to has expected properties
    assert t1_new.t_end == t2.t_end
    assert t1_new.t_begin == t1.t_begin
    assert t1_new.parent_track_id == t1.parent_track_id
    assert t1_new.root == t1.root

    assert t2_new.t_end == current_frame - 1
    assert t2_new.t_begin == t2.t_begin
    assert t2_new.parent_track_id == t2.parent_track_id
    assert t2_new.root == t2.root

    assert t_new.t_end == t1.t_end
    assert t_new.t_begin == current_frame
    assert t_new.parent_track_id == -1
    assert t_new.root == expected_new_track


def test_after_t1_end_track_merge(db_session):
    """ """

    t1_ind = 37401
    t2_ind = 20422
    current_frame = 40

    expected_new_track = newTrack_number(db_session)

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t2_org = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    # get children of t1
    descendants = get_descendants(db_session, t1_ind)
    children_list = []
    for track in descendants[1:]:
        # change for children
        if track.parent_track_id == t1.track_id:
            children_list.append(track.track_id)

    t2 = TrackDB()
    for key in t2_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t2, key, getattr(t2_org, key))

    # Detach the copy from the session
    make_transient(t2)

    _ = integrate_trackDB(db_session, "merge", t1_ind, t2_ind, current_frame)

    # assert single objects of t1 and t2
    assert db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t1_new = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    t2_new = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    # no new track was created
    assert (
        len(
            db_session.query(TrackDB)
            .filter_by(track_id=expected_new_track)
            .all()
        )
        == 0
    )

    # assert that the merger to has expected properties
    assert t1_new.t_end == t2.t_end
    assert t1_new.t_begin == t1.t_begin
    assert t1_new.parent_track_id == t1.parent_track_id
    assert t1_new.root == t1.root

    assert t2_new.t_end == current_frame - 1
    assert t2_new.t_begin == t2.t_begin
    assert t2_new.parent_track_id == t2.parent_track_id
    assert t2_new.root == t2.root

    # get descendants of t1
    child1 = children_list[0]
    ch1 = db_session.query(TrackDB).filter_by(track_id=child1).one()

    assert ch1.parent_track_id == -1
    assert ch1.root == child1


def test_before_t2_start_track_merge(db_session):
    """Test checking if a freely floating track can be merged.
    No descendants on neither side."""

    t1_ind = 20422
    t2_ind = 37401
    current_frame = 20

    expected_new_track = newTrack_number(db_session)

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t2_org = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    # get children of t1
    descendants = get_descendants(db_session, t1_ind)
    children_list = []
    for track in descendants[1:]:
        # change for children
        if track.parent_track_id == t1.track_id:
            children_list.append(track.track_id)

    t2 = TrackDB()
    for key in t2_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t2, key, getattr(t2_org, key))

    # Detach the copy from the session
    make_transient(t2)

    _ = integrate_trackDB(db_session, "merge", t1_ind, t2_ind, current_frame)

    # assert single objects of t1 and t2
    assert db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t1_new = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert (
        db_session.query(TrackDB).filter_by(track_id=expected_new_track).one()
    )
    t_new = (
        db_session.query(TrackDB).filter_by(track_id=expected_new_track).one()
    )
    # no t2 remaining
    assert (
        len(db_session.query(TrackDB).filter_by(track_id=t2.track_id).all())
        == 0
    )

    # assert that the merger to has expected properties
    assert t1_new.t_end == t2.t_end
    assert t1_new.t_begin == t1.t_begin
    assert t1_new.parent_track_id == t1.parent_track_id
    assert t1_new.root == t1.root

    assert t_new.t_begin == current_frame
    assert t_new.t_end == t1.t_end
    assert t_new.parent_track_id == -1
    assert t_new.root == expected_new_track

    # get descendants of t1
    child1 = children_list[0]
    ch1 = db_session.query(TrackDB).filter_by(track_id=child1).one()

    assert ch1.parent_track_id == expected_new_track
    assert ch1.root == expected_new_track


def test_freely_floating_connect(db_session):
    """Test connecting parent-offspring when no cut is needed."""

    t1_ind = 4
    t2_ind = 5
    current_frame = 41

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t2_org = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    t2 = TrackDB()
    for key in t2_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t2, key, getattr(t2_org, key))

    # Detach the copy from the session
    make_transient(t2)

    t1_after, t2_before = integrate_trackDB(
        db_session, "connect", t1_ind, t2_ind, current_frame
    )

    # assert that the merger to has expected properties
    new_t1 = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert new_t1.t_end == t1.t_end
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root

    # assert that the merger to has expected properties
    new_t2 = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    assert new_t2.t_end == t2.t_end
    assert new_t2.t_begin == t2.t_begin
    assert new_t2.parent_track_id == t1.track_id
    assert new_t2.root == t1.root

    # assert that the new track was not created
    assert t1_after is None
    assert t2_before is None


def test_double_cut_connect(db_session):
    """Test merging tracks when both need to be cut."""

    t1_ind = 37401
    t2_ind = 20422
    current_frame = 30

    expected_t1_after = newTrack_number(db_session)
    expected_t2_before = newTrack_number(db_session) + 1

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t2_org = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    # copies are necessary for comparison of properties later in the test
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    t2 = TrackDB()
    for key in t2_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t2, key, getattr(t2_org, key))

    # Detach the copy from the session
    make_transient(t2)

    t1_after, t2_before = integrate_trackDB(
        db_session, "connect", t1_ind, t2_ind, current_frame
    )

    assert expected_t1_after == t1_after
    assert expected_t2_before == t2_before

    # assert that the merger to has expected properties

    # t1
    new_t1 = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.t_end == current_frame - 1
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root

    # t2
    new_t2 = db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    assert new_t2.t_end == t2.t_end
    assert new_t2.t_begin == current_frame
    assert new_t2.parent_track_id == t1.track_id
    assert new_t2.root == t1.root

    # t1_after
    t1_after = db_session.query(TrackDB).filter_by(track_id=t1_after).one()
    assert t1_after.t_begin == current_frame
    assert t1_after.t_end == t1.t_end
    assert t1_after.parent_track_id == -1
    assert t1_after.root == t1_after.track_id

    # t2_before
    t2_before = db_session.query(TrackDB).filter_by(track_id=t2_before).one()
    assert t2_before.t_begin == t2.t_begin
    assert t2_before.t_end == current_frame - 1
    assert t2_before.parent_track_id == t2.parent_track_id
    if t2.parent_track_id == -1:
        assert t2_before.root == t2_before.track_id
    else:
        assert t2_before.root == t2.root


def test_trackDB_after_cellDB_no_change(db_session):
    """
    Tests if the modification happened at a time frame inside of a track
    """

    t1_ind = 20422
    current_frame = 10

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    trackDB_after_cellDB(db_session, t1_ind, current_frame)

    # assert that t1_ind track is not changed
    new_t1 = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert new_t1.t_end == t1.t_end
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root


def test_trackDB_after_cellDB_new_track(db_session):
    """
    Tests if the new cell is added to the database.
    """

    t1_ind = 400000
    current_frame = 10

    # assert there is no such track at the beginning
    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).all()
    assert len(t1_org) == 0

    # add mock cell
    cell_dict = {
        "label": t1_ind,
        "area": 0,
        "bbox": [0, 0, 0, 0],
        "image": np.zeros([2, 2]),
    }
    cell = MagicMock()
    for key in cell_dict:
        setattr(cell, key, cell_dict[key])
    add_new_core_CellDB(db_session, current_frame, cell)
    # modify tracks table after adding this fake cell
    trackDB_after_cellDB(db_session, t1_ind, current_frame)

    # assert that t1_ind track is not changed
    new_t1 = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert new_t1.t_end == current_frame
    assert new_t1.t_begin == current_frame
    assert new_t1.parent_track_id == -1
    assert new_t1.root == t1_ind


def test_trackDB_after_cellDB_added_after(db_session):
    """
    Tests a modification that extends the track.
    """

    t1_ind = 20422
    current_frame = 50
    d1_ind = 20426

    t1_org = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    d1_org = db_session.query(TrackDB).filter_by(track_id=d1_ind).one()

    # make deep copies because otherwise the objects stay connected to the database
    d1 = TrackDB()
    for key in d1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(d1, key, getattr(d1_org, key))

    # Detach the copy from the session
    make_transient(d1)

    # modify tracks table
    cell_dict = {
        "label": t1_ind,
        "area": 0,
        "bbox": [0, 0, 0, 0],
        "image": np.zeros([2, 2]),
    }
    cell = MagicMock()
    for key in cell_dict:
        setattr(cell, key, cell_dict[key])

    add_new_core_CellDB(db_session, current_frame, cell)
    trackDB_after_cellDB(db_session, t1_ind, current_frame)

    # assert that t1_ind track is not changed
    new_t1 = db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    assert new_t1.t_end == current_frame
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root

    # assert that the offspring is modified
    new_d1 = db_session.query(TrackDB).filter_by(track_id=d1_ind).one()
    assert new_d1.t_end == d1.t_end
    assert new_d1.t_begin == d1.t_begin
    assert new_d1.parent_track_id == -1
    assert new_d1.root == d1_ind


def test_remove_CellDB(db_session):
    """Test - remove a cell"""
    cell_id = 20422
    current_frame = 20

    remove_CellDB(db_session, cell_id, current_frame)

    c = (
        db_session.query(CellDB)
        .filter_by(track_id=cell_id)
        .filter_by(t=current_frame)
        .all()
    )
    assert len(c) == 0


def test_remove_CellDB_first(db_session):
    """Test - remove a cell"""
    cell_id = 20426
    current_frame = 43

    remove_CellDB(db_session, cell_id, current_frame)

    c = (
        db_session.query(CellDB)
        .filter_by(track_id=cell_id)
        .filter_by(t=current_frame)
        .all()
    )
    assert len(c) == 0

    t = db_session.query(TrackDB).filter_by(track_id=cell_id).one()
    assert t.t_begin == current_frame + 1
    assert t.parent_track_id == -1
    assert t.root == cell_id


def test_remove_cell_cut_track(db_session):
    """
    Test after encountering a bug of cutting a cell at a next position after removed cell.
    """

    active_label = 20422
    current_frame = 20

    remove_CellDB(db_session, active_label, current_frame)

    current_frame = 21
    new_track = newTrack_number(db_session)

    mitosis, new_track = cut_trackDB(db_session, active_label, current_frame)

    t = db_session.query(TrackDB).filter_by(track_id=active_label).one()
    # because cell was removed at 20
    assert t.t_end == current_frame - 2

    t = db_session.query(TrackDB).filter_by(track_id=new_track).one()
    assert t.t_begin == current_frame


def test_add_note_no_track(db_session):
    """
    Test adding a note to a non-existing track.
    """

    active_label = 20
    note = "This is a note. No kidding."

    sts = fdb.save_track_note(db_session, active_label, note)

    exp_status = (
        f"Error - track {active_label} is not present in the database."
    )
    assert (
        sts == exp_status
    ), f"Expected status of the viewer to be {exp_status}, instead it is {sts}"


def test_get_note_no_track(db_session):
    """
    Test adding a note to a non-existing track.
    """

    active_label = 20

    sts = fdb.get_track_note(db_session, active_label)

    assert sts is None, f"Expected return to be None, instead it is {sts}"


def test_add_retrieve_track_note(db_session):
    """
    Test adding and retrieving a note for a track.
    """

    active_label = 20422
    note = "This is a note. No kidding."

    sts = fdb.save_track_note(db_session, active_label, note)

    exp_status = f"Note for track {active_label} saved in the database."
    assert (
        sts == exp_status
    ), f"Expected status to be {exp_status}, instead it is {sts}"

    new_note = fdb.get_track_note(db_session, active_label)

    assert new_note == note, f"Expected {note}, got {new_note}"


def test_add_tags(db_session):
    """
    Test adding and retrieving a note for a track.
    """

    active_cell = 20422
    frame = 20
    annotation = "apoptosis"

    cell_list = (
        db_session.query(CellDB)
        .filter(CellDB.t == frame)
        .filter(CellDB.track_id == active_cell)
        .first()
    )

    assert cell_list.tags == {}, f"Expected no tag, got {cell_list.tags}"

    _ = fdb.tag_cell(db_session, active_cell, frame, annotation)

    cell_list = (
        db_session.query(CellDB)
        .filter(CellDB.t == frame)
        .filter(CellDB.track_id == active_cell)
        .first()
    )

    assert cell_list.tags["apoptosis"], f"Expected True, got {cell_list.tags}"
