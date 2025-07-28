from unittest.mock import MagicMock

import numpy as np
import pytest
from sqlalchemy.orm import Session, make_transient

import track_gardener.db.db_functions as fdb
from track_gardener.db.db_functions import (
    add_new_core_CellDB,
    cellsDB_after_trackDB,
    cut_trackDB,
    delete_trackDB,
    get_descendants,
    integrate_trackDB,
    newCell_number,
    newTrack_number,
    remove_CellDB,
    trackDB_after_cellDB,
)
from track_gardener.db.db_model import NO_PARENT, CellDB, TrackDB


@pytest.fixture
def extended_db_session(db_session: Session):
    """
    Extends the base `db_session` by adding additional tracks to the database.
    """
    # Add additional tracks to the session
    new_tracks = [
        TrackDB(
            track_id=1, parent_track_id=NO_PARENT, root=1, t_begin=0, t_end=10
        ),
        TrackDB(track_id=2, parent_track_id=1, root=1, t_begin=11, t_end=50),
        TrackDB(track_id=3, parent_track_id=1, root=1, t_begin=11, t_end=20),
        TrackDB(track_id=4, parent_track_id=3, root=1, t_begin=21, t_end=40),
        TrackDB(track_id=5, parent_track_id=-1, root=5, t_begin=41, t_end=45),
    ]

    # Add tracks to the session
    for track in new_tracks:
        db_session.add(track)

    # Commit the changes
    db_session.commit()

    yield db_session  # Provide the modified session for testing


def test_starting_db(extended_db_session):
    """Verify that the test database is set up correctly."""
    assert extended_db_session.query(TrackDB).filter_by(track_id=204).one()


def test_getting_signals(extended_db_session):
    """
    Test getting the list of signal names from the database.
    """
    expected_list = ["area", "ch0_nuc"]

    signal_list = fdb.get_signals(extended_db_session)

    assert (
        signal_list == expected_list
    ), f"Expected {expected_list}, got {signal_list}"


def test_adding_track(extended_db_session):
    """Test - add a new track"""
    new_track = TrackDB(
        track_id=100, parent_track_id=None, root=0, t_begin=0, t_end=10
    )
    extended_db_session.add(new_track)
    extended_db_session.commit()

    # Verify the record was added
    assert extended_db_session.query(TrackDB).filter_by(track_id=100).one()


def test_remove_track(extended_db_session):
    """Test - remove a track"""
    to_del = 1
    status = delete_trackDB(extended_db_session, to_del)
    assert status == f"Track {to_del} has been deleted."

    # Verify the record was removed
    assert (
        not extended_db_session.query(TrackDB).filter_by(track_id=to_del).all()
    )

    # Verify that the offspring has expected properties
    offspring = extended_db_session.query(TrackDB).filter_by(track_id=2).one()
    assert offspring.parent_track_id == NO_PARENT
    assert offspring.root == 2

    offspring = extended_db_session.query(TrackDB).filter_by(track_id=3).one()
    assert offspring.parent_track_id == NO_PARENT
    assert offspring.root == 3

    # check grandchildren
    grandchild = extended_db_session.query(TrackDB).filter_by(track_id=4).one()
    assert grandchild.parent_track_id == 3
    assert grandchild.root == 3


def test_remove_none_track(extended_db_session):
    """Test - remove a track"""
    to_del = 6
    init_len = extended_db_session.query(TrackDB).all()
    status = delete_trackDB(extended_db_session, to_del)
    assert status == "Track not found"
    assert len(extended_db_session.query(TrackDB).all()) == len(init_len)


def test_newTrack_number(extended_db_session):
    """Test - getting a new track number."""

    new_track = newTrack_number(extended_db_session)
    assert new_track == 235

    new_track_number = 6e10
    new_track = TrackDB(
        track_id=new_track_number,
        parent_track_id=None,
        root=0,
        t_begin=0,
        t_end=10,
    )
    extended_db_session.add(new_track)
    extended_db_session.commit()

    new_track = newTrack_number(extended_db_session)
    assert new_track == new_track_number + 1


def test_newTrack_number_empty_db(extended_db_session):
    """Test - getting a new track number
    while the database is empty"""

    # clear the database
    query = extended_db_session.query(TrackDB).all()
    ids_list = [x.track_id for x in query]
    for run_id in ids_list:
        _ = delete_trackDB(extended_db_session, run_id)

    # check that it's empty
    query = extended_db_session.query(TrackDB).all()
    assert len(query) == 0, f"Expected database to be empty, got {len(query)}"

    # asssert the correct new track number
    new_track = newTrack_number(extended_db_session)
    assert new_track == 1, f"Expected 1, got {new_track}"


def test_newCell_number(extended_db_session):
    """Test - getting a new cell number."""

    new_cell_number = 6e10
    new_cell = CellDB(id=new_cell_number, t=0, track_id=100)
    extended_db_session.add(new_cell)
    extended_db_session.commit()

    new_cell = newCell_number(extended_db_session)
    assert new_cell == new_cell_number + 1


def test_get_descendants(extended_db_session):
    """Test checking we get correct descendants."""

    # test at the root level
    active_label = 227
    descendants = get_descendants(extended_db_session, active_label)

    assert len(descendants) == 3

    descendants_list = [x.track_id for x in descendants]
    descendants_list.sort()
    assert descendants[0].track_id == active_label
    assert descendants_list == [227, 233, 234]

    # test lower in the tree
    active_label = 3
    descendants = get_descendants(extended_db_session, active_label)

    assert len(descendants) == 2

    descendants_list = [x.track_id for x in descendants]
    descendants_list.sort()
    assert descendants[0].track_id == active_label
    assert descendants_list == [3, 4]


def test_cut_trackDB(extended_db_session):
    """Test checking that a track is modified correctly."""

    active_label = 225
    current_frame = 2

    new_track_expected = newTrack_number(extended_db_session)

    mitosis, new_track = cut_trackDB(
        extended_db_session, active_label, current_frame
    )

    # assert expected output of the function
    assert mitosis is False
    assert new_track == new_track_expected

    # assert that the new track is in the database
    assert (
        extended_db_session.query(TrackDB).filter_by(track_id=new_track).one()
    )

    # assert that the new track has expected properties
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=new_track)
        .one()
        .t_begin
        == current_frame
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=new_track)
        .one()
        .t_end
        == 5
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=new_track)
        .one()
        .parent_track_id
        == -1
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=new_track)
        .one()
        .root
        == new_track
    )

    # assert that the old track is modified
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_end
        == current_frame - 1
    )

    # assert that the children are modified
    assert (
        extended_db_session.query(TrackDB).filter_by(track_id=227).one().root
        == new_track
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=227)
        .one()
        .parent_track_id
        == new_track
    )
    assert (
        extended_db_session.query(TrackDB).filter_by(track_id=228).one().root
        == new_track
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=228)
        .one()
        .parent_track_id
        == new_track
    )

    # assert that the grandchildren are modified
    assert (
        extended_db_session.query(TrackDB).filter_by(track_id=230).one().root
        == new_track
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=230)
        .one()
        .parent_track_id
        == 228
    )


def test_cut_trackDB_beyond_track(extended_db_session):
    """Test checking that calling cut on a frame where a track doesn't exist doesn't modify the track."""

    active_label = 2
    current_frame = 1

    t1_org = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
    )
    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    mitosis, new_track = cut_trackDB(
        extended_db_session, active_label, current_frame
    )

    t1_new = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
    )

    # assert that t1 new and t1 are the same
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            assert getattr(t1_new, key) == getattr(t1, key)


def test_cut_trackDB_mitosis(extended_db_session):
    """
    Test cut_TrackDB function when cutting from mitosis.
    """

    active_label = 3

    record = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
    )

    t_begin_org = record.t_begin
    t_end_org = record.t_end

    new_track_hypothesis = newTrack_number(extended_db_session)

    mitosis, new_track = cut_trackDB(
        extended_db_session, active_label, t_begin_org
    )

    # assert expected output of the function
    assert mitosis is True
    assert new_track is None

    # assert that the active label track is in the database
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
    )

    # assert that the changed track has expected properties
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_begin
        == t_begin_org
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_end
        == t_end_org
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .parent_track_id
        == -1
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .root
        == active_label
    )

    # assert that the new track was not created
    assert (
        len(
            extended_db_session.query(TrackDB)
            .filter_by(track_id=new_track_hypothesis)
            .all()
        )
        == 0
    )


def test_cut_merge_trackDB(extended_db_session):
    """Test checking that a track is modified correctly."""

    active_label = 225
    current_frame = 2

    new_track_expected = newTrack_number(extended_db_session)

    mitosis, new_track = cut_trackDB(
        extended_db_session, active_label, current_frame
    )

    # assert expected output of the function
    assert mitosis is False
    assert new_track == new_track_expected

    # re-merge new to old
    t1_ind = 225
    t2_ind = new_track
    _ = integrate_trackDB(
        extended_db_session, "merge", t1_ind, t2_ind, current_frame
    )

    # assert that the new track is in the database
    assert (
        len(
            extended_db_session.query(TrackDB)
            .filter_by(track_id=new_track)
            .all()
        )
        == 0
    )

    # assert that the new track has expected properties
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=t1_ind)
        .one()
        .t_begin
        == 0
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=t1_ind)
        .one()
        .t_end
        == 5
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=t1_ind)
        .one()
        .parent_track_id
        == -1
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=t1_ind)
        .one()
        .root
        == t1_ind
    )

    # assert that the children are not modified
    assert (
        extended_db_session.query(TrackDB).filter_by(track_id=227).one().root
        == t1_ind
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=227)
        .one()
        .parent_track_id
        == t1_ind
    )
    assert (
        extended_db_session.query(TrackDB).filter_by(track_id=228).one().root
        == t1_ind
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=228)
        .one()
        .parent_track_id
        == t1_ind
    )

    # assert that the grandchildren are not modified
    assert (
        extended_db_session.query(TrackDB).filter_by(track_id=230).one().root
        == t1_ind
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=230)
        .one()
        .parent_track_id
        == 228
    )


def test_cellsDB_after_trackDB_nonsense_call(extended_db_session):
    """Test nonsense call response"""

    active_label = 20422

    current_frame = 3
    new_track = 100

    with pytest.raises(ValueError) as exc_info:
        _ = cellsDB_after_trackDB(
            extended_db_session,
            active_label,
            current_frame,
            new_track,
            direction="left",
        )

    exp_status = "Direction should be 'all', 'before' or 'after'."
    assert str(exc_info.value) == exp_status


def test_cellsDB_after_trackDB(extended_db_session):
    """Test modifications in the cells table after a track is moodified."""

    active_label = 228

    # check how long the track is before the cut
    org_stop = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_end
    )

    org_start = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_begin
    )

    current_frame = 9
    new_track = 100

    _ = cellsDB_after_trackDB(
        extended_db_session,
        active_label,
        current_frame,
        new_track,
        direction="after",
    )

    # assert that there are only 3 objects of old track in the cell table after cut
    assert (
        len(
            extended_db_session.query(CellDB)
            .filter_by(track_id=active_label)
            .all()
        )
        == current_frame - org_start
    )

    # assert that there is expected number of objects in new track
    assert len(
        extended_db_session.query(CellDB).filter_by(track_id=new_track).all()
    ) == (org_stop - current_frame + 1)


def test_modify_track_cellsDB_before(extended_db_session):
    """Test checking whether the cellsDB_after_trackDB - in before direction."""

    active_label = 228

    # check how long the track is before the cut
    org_stop = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_end
    )

    org_start = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
        .t_begin
    )

    current_frame = 8
    new_track = 100

    _ = cellsDB_after_trackDB(
        extended_db_session,
        active_label,
        current_frame,
        new_track,
        direction="before",
    )

    # assert that there are only n objects of old track in the cell table after cut
    assert len(
        extended_db_session.query(CellDB)
        .filter_by(track_id=active_label)
        .all()
    ) == (org_stop - current_frame + 1)

    # assert that there is expected number of objects in new track
    assert (
        len(
            extended_db_session.query(CellDB)
            .filter_by(track_id=new_track)
            .all()
        )
        == current_frame - org_start
    )


def test_freely_floating_merge(extended_db_session):
    """Test merging when no cut is needed."""

    t1_ind = 4
    t2_ind = 5
    current_frame = 41

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    t2_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )

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

    _ = integrate_trackDB(
        extended_db_session, "merge", t1_ind, t2_ind, current_frame
    )

    # assert that the merger from track is not in the database
    assert (
        len(
            extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).all()
        )
        == 0
    )

    # assert that the merger to has expected properties
    new_t1 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert new_t1.t_end == t2.t_end
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root


def test_double_cut_merge(extended_db_session):
    """Test merging tracks when both need to be cut."""

    t1_ind = 234
    t2_ind = 208
    current_frame = 42

    expected_new_track = newTrack_number(extended_db_session)

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    t2_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )

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

    _ = integrate_trackDB(
        extended_db_session, "merge", t1_ind, t2_ind, current_frame
    )

    # assert that the merger from track is not in the database
    assert extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t1_new = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    t2_new = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=expected_new_track)
        .one()
    )
    t_new = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=expected_new_track)
        .one()
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


def test_after_t1_end_track_merge(extended_db_session):
    """
    Track 1 - ended before the cutting frame
    Track 2 - running at the cutting frame
    T2 after should get id of T1. T1 offspring become roots.
    T2 before should just be shorter.
    """

    t1_ind = 204
    t2_ind = 228
    current_frame = 10

    expected_new_track = newTrack_number(extended_db_session)

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    t2_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )

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
    descendants = get_descendants(extended_db_session, t1_ind)
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

    _ = integrate_trackDB(
        extended_db_session, "merge", t1_ind, t2_ind, current_frame
    )

    # assert single objects of t1 and t2
    assert extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t1_new = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    t2_new = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )
    # no new track was created
    assert (
        len(
            extended_db_session.query(TrackDB)
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
    ch1 = extended_db_session.query(TrackDB).filter_by(track_id=child1).one()

    assert ch1.parent_track_id == -1
    assert ch1.root == child1


def test_before_t2_start_track_merge(extended_db_session):
    """Test checking if a freely floating track can be merged.
    No descendants on neither side."""

    t1_ind = 227
    t2_ind = 211
    current_frame = 20

    expected_new_track = newTrack_number(extended_db_session)

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    t2_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )

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
    descendants = get_descendants(extended_db_session, t1_ind)
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

    _ = integrate_trackDB(
        extended_db_session, "merge", t1_ind, t2_ind, current_frame
    )

    # assert single objects of t1 and t2
    assert extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    t1_new = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=expected_new_track)
        .one()
    )
    t_new = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=expected_new_track)
        .one()
    )
    # no t2 remaining
    assert (
        len(
            extended_db_session.query(TrackDB)
            .filter_by(track_id=t2.track_id)
            .all()
        )
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
    ch1 = extended_db_session.query(TrackDB).filter_by(track_id=child1).one()

    assert ch1.parent_track_id == expected_new_track
    assert ch1.root == expected_new_track


def test_freely_floating_connect(extended_db_session):
    """Test connecting parent-offspring when no cut is needed."""

    t1_ind = 4
    t2_ind = 5
    current_frame = 41

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    t2_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )

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
        extended_db_session, "connect", t1_ind, t2_ind, current_frame
    )

    # assert that the merger to has expected properties
    new_t1 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert new_t1.t_end == t1.t_end
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root

    # assert that the merger to has expected properties
    new_t2 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )
    assert new_t2.t_end == t2.t_end
    assert new_t2.t_begin == t2.t_begin
    assert new_t2.parent_track_id == t1.track_id
    assert new_t2.root == t1.root

    # assert that the new track was not created
    assert t1_after is None
    assert t2_before is None

    t1_ind = 207
    t2_ind = 227
    current_frame = 30

    expected_t1_after = newTrack_number(extended_db_session)
    expected_t2_before = newTrack_number(extended_db_session) + 1

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    t2_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )

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
        extended_db_session, "connect", t1_ind, t2_ind, current_frame
    )

    assert expected_t1_after == t1_after
    assert expected_t2_before == t2_before

    # assert that the merger to has expected properties

    # t1
    new_t1 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.t_end == current_frame - 1
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root

    # t2
    new_t2 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_ind).one()
    )
    assert new_t2.t_end == t2.t_end
    assert new_t2.t_begin == current_frame
    assert new_t2.parent_track_id == t1.track_id
    assert new_t2.root == t1.root

    # t1_after
    t1_after = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_after).one()
    )
    assert t1_after.t_begin == current_frame
    assert t1_after.t_end == t1.t_end
    assert t1_after.parent_track_id == -1
    assert t1_after.root == t1_after.track_id

    # t2_before
    t2_before = (
        extended_db_session.query(TrackDB).filter_by(track_id=t2_before).one()
    )
    assert t2_before.t_begin == t2.t_begin
    assert t2_before.t_end == current_frame - 1
    assert t2_before.parent_track_id == t2.parent_track_id
    if t2.parent_track_id == -1:
        assert t2_before.root == t2_before.track_id
    else:
        assert t2_before.root == t2.root


def test_trackDB_after_cellDB_no_change(extended_db_session):
    """
    Tests if the modification happened at a time frame inside of a track
    """

    t1_ind = 227
    current_frame = 10

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    trackDB_after_cellDB(extended_db_session, t1_ind, current_frame)

    # assert that t1_ind track is not changed
    new_t1 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert new_t1.t_end == t1.t_end
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root


def test_trackDB_after_cellDB_new_track(extended_db_session):
    """
    Tests if the new cell is added to the database.
    """

    t1_ind = 400000
    current_frame = 10

    # assert there is no such track at the beginning
    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).all()
    )
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
    add_new_core_CellDB(extended_db_session, current_frame, cell)
    # modify tracks table after adding this fake cell
    trackDB_after_cellDB(extended_db_session, t1_ind, current_frame)

    # assert that t1_ind track is not changed
    new_t1 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert new_t1.t_end == current_frame
    assert new_t1.t_begin == current_frame
    assert new_t1.parent_track_id == -1
    assert new_t1.root == t1_ind


def test_trackDB_after_cellDB_added_after(extended_db_session):
    """
    Tests a modification that extends the track.
    """

    t1_ind = 204
    current_frame = 10
    d1_ind = 220

    t1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )

    # make deep copies because otherwise the objects stay connected to the database
    t1 = TrackDB()
    for key in t1_org.__dict__:
        if (
            key != "_sa_instance_state"
        ):  # Exclude the SQLAlchemy instance state
            setattr(t1, key, getattr(t1_org, key))

    # Detach the copy from the session
    make_transient(t1)

    d1_org = (
        extended_db_session.query(TrackDB).filter_by(track_id=d1_ind).one()
    )

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
        "centroid": [0, 0],
        "bbox": [0, 0, 0, 0],
        "image": np.zeros([2, 2]),
    }
    cell = MagicMock()
    for key in cell_dict:
        setattr(cell, key, cell_dict[key])

    add_new_core_CellDB(extended_db_session, current_frame, cell)
    trackDB_after_cellDB(extended_db_session, t1_ind, current_frame)

    # assert that t1_ind track is not changed
    new_t1 = (
        extended_db_session.query(TrackDB).filter_by(track_id=t1_ind).one()
    )
    assert new_t1.t_end == current_frame
    assert new_t1.t_begin == t1.t_begin
    assert new_t1.parent_track_id == t1.parent_track_id
    assert new_t1.root == t1.root

    # assert that the offspring is modified
    new_d1 = (
        extended_db_session.query(TrackDB).filter_by(track_id=d1_ind).one()
    )
    assert new_d1.t_end == d1.t_end
    assert new_d1.t_begin == d1.t_begin
    assert new_d1.parent_track_id == -1
    assert new_d1.root == d1_ind


def test_remove_CellDB(extended_db_session):
    """Test - remove a cell"""
    cell_id = 220
    current_frame = 20

    remove_CellDB(extended_db_session, cell_id, current_frame)

    c = (
        extended_db_session.query(CellDB)
        .filter_by(track_id=cell_id)
        .filter_by(t=current_frame)
        .all()
    )
    assert len(c) == 0


def test_remove_CellDB_first(extended_db_session):
    """Test - remove a cell
    Removing the first cell after mitosis breaks parent-child relationship."""
    cell_id = 220
    current_frame = 3

    remove_CellDB(extended_db_session, cell_id, current_frame)

    c = (
        extended_db_session.query(CellDB)
        .filter_by(track_id=cell_id)
        .filter_by(t=current_frame)
        .all()
    )
    assert len(c) == 0

    t = extended_db_session.query(TrackDB).filter_by(track_id=cell_id).one()
    assert t.t_begin == current_frame + 1
    assert t.parent_track_id == -1
    assert t.root == cell_id


def test_remove_cell_cut_track(extended_db_session):
    """
    Test after encountering a bug of cutting a cell at a next position after removed cell.
    """

    active_label = 207
    current_frame = 20

    remove_CellDB(extended_db_session, active_label, current_frame)

    current_frame = 21
    new_track = newTrack_number(extended_db_session)

    mitosis, new_track = cut_trackDB(
        extended_db_session, active_label, current_frame
    )

    t = (
        extended_db_session.query(TrackDB)
        .filter_by(track_id=active_label)
        .one()
    )
    # because cell was removed at 20
    assert t.t_end == current_frame - 2

    t = extended_db_session.query(TrackDB).filter_by(track_id=new_track).one()
    assert t.t_begin == current_frame


def test_add_note_no_track(extended_db_session):
    """
    Test adding a note to a non-existing track.
    """

    active_label = 20
    note = "This is a note. No kidding."

    sts = fdb.save_track_note(extended_db_session, active_label, note)

    exp_status = (
        f"Error - track {active_label} is not present in the database."
    )
    assert (
        sts == exp_status
    ), f"Expected status of the viewer to be {exp_status}, instead it is {sts}"


def test_get_note_no_track(extended_db_session):
    """
    Test adding a note to a non-existing track.
    """

    active_label = 20

    sts = fdb.get_track_note(extended_db_session, active_label)

    assert sts is None, f"Expected return to be None, instead it is {sts}"


def test_add_retrieve_track_note(extended_db_session):
    """
    Test adding and retrieving a note for a track.
    """

    active_label = 208
    note = "This is a note. No kidding."

    sts = fdb.save_track_note(extended_db_session, active_label, note)

    exp_status = f"Note for track {active_label} saved in the database."
    assert (
        sts == exp_status
    ), f"Expected status to be {exp_status}, instead it is {sts}"

    new_note = fdb.get_track_note(extended_db_session, active_label)

    assert new_note == note, f"Expected {note}, got {new_note}"


def test_add_tags(extended_db_session):
    """
    Test adding and retrieving a note for a track.
    """

    active_cell = 207
    frame = 20
    annotation = "apoptosis"

    cell_list = (
        extended_db_session.query(CellDB)
        .filter(CellDB.t == frame)
        .filter(CellDB.track_id == active_cell)
        .first()
    )

    assert cell_list.tags == {}, f"Expected no tag, got {cell_list.tags}"

    _ = fdb.tag_cell(extended_db_session, active_cell, frame, annotation)

    cell_list = (
        extended_db_session.query(CellDB)
        .filter(CellDB.t == frame)
        .filter(CellDB.track_id == active_cell)
        .first()
    )

    assert cell_list.tags["apoptosis"], f"Expected True, got {cell_list.tags}"
