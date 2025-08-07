"""
A collection of functions to check the integrity of a tracking database.

This module provides functions to validate the database schema, check for data
consistency issues like orphaned cells, and verify the logical integrity of
the lineage graph, such as preventing cycles and ensuring root consistency.
"""

from pathlib import Path
from typing import Sequence, Type

import networkx as nx
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.decl_api import DeclarativeMeta

from track_gardener.db.db_model import NO_PARENT, CellDB, TrackDB

####################################################
# Database Connections Check
####################################################


def check_database_connection(database_path: str | Path) -> tuple[bool, str]:
    """Tests the connection to a SQLite database file.

    This function attempts to create a SQLAlchemy engine and initialize a
    session to verify that the database file is accessible and valid.

    Args:
        database_path (str | Path): The file path to the SQLite database.

    Returns:
        tuple[bool, str]: A tuple containing:
            - A boolean indicating connection success (True) or failure (False).
            - A string with a corresponding status message.
    """

    try:
        # Create the database engine
        engine = create_engine(f"sqlite:///{database_path}")
        # Initialize a session
        sessionmaker(bind=engine)()

        return True, "Database connection successful."
    except SQLAlchemyError as e:
        return False, f"Database connection failed: {e}"


####################################################
# Database Integrity Checks
####################################################


def check_tables_present(
    session: Session, models: list[Type[DeclarativeMeta]]
) -> list[str]:
    """Checks if the required tables for the given models exist in the database.

    Args:
        session (Session): The SQLAlchemy session connected to the database.
        models (list[Type[DeclarativeMeta]]): A list of SQLAlchemy model classes
            to check for.

    Returns:
        list[str]: A list of error messages. Returns an empty list if all
            tables exist.
    """
    inspector = inspect(session.bind)
    required_tables = {model.__tablename__ for model in models}
    existing_tables = set(inspector.get_table_names())
    missing = required_tables - existing_tables
    if missing:
        return [f"Missing tables: {missing}"]
    return []


def check_columns_present(
    session: Session, models: list[Type[DeclarativeMeta]]
) -> list[str]:
    """Checks if all columns defined in the models exist in the database tables.

    Args:
        session (Session): The SQLAlchemy session connected to the database.
        models (list[Type[DeclarativeMeta]]): A list of SQLAlchemy model classes
            to check.

    Returns:
        list[str]: A list of error messages for any missing columns. Returns
            an empty list if all columns are present.
    """
    inspector = inspect(session.bind)
    errors = []
    for model in models:
        table = model.__tablename__
        if table in inspector.get_table_names():
            expected = {col.name for col in model.__table__.columns}
            actual = {col["name"] for col in inspector.get_columns(table)}
            missing = expected - actual
            if missing:
                errors.append(f"Missing columns in '{table}': {missing}")
    return errors


def check_no_orphan_cells(session: Session) -> list[str]:
    """Checks for cells that reference a non-existent track ID.

    Args:
        session (Session): The SQLAlchemy session connected to the database.

    Returns:
        list[str]: A list containing an error message if orphaned cells are
            found. Returns an empty list otherwise.
    """
    orphaned = (
        session.execute(
            select(CellDB)
            .outerjoin(TrackDB, CellDB.track_id == TrackDB.track_id)
            .where(TrackDB.track_id.is_(None))
        )
        .scalars()
        .all()
    )
    if orphaned:
        return [f"Orphaned cells found: {len(orphaned)}"]
    return []


def check_no_orphan_tracks(session: Session) -> list[str]:
    """Checks for tracks that have no associated cell objects.

    Args:
        session (Session): The SQLAlchemy session connected to the database.

    Returns:
        list[str]: A list containing an error message if unused tracks are
            found. Returns an empty list otherwise.
    """
    unused = (
        session.execute(
            select(TrackDB)
            .outerjoin(CellDB, TrackDB.track_id == CellDB.track_id)
            .where(CellDB.track_id.is_(None))
        )
        .scalars()
        .all()
    )
    if unused:
        return [f"Tracks with no associated cells: {unused}"]
    return []


####################################################
# Graph Checks
####################################################


def build_track_graph(
    tracks: Sequence[TrackDB], no_parent: int = NO_PARENT
) -> tuple[nx.DiGraph, list[str]]:
    """
    Builds a lineage graph from track data and checks for inconsistencies.

    This function constructs a directed graph where nodes are tracks and edges
    represent parent-child relationships. It simultaneously validates that
    parent tracks exist and that their time frames are consistent with their
    children's.

    Args:
        tracks (Sequence[TrackDB]): A sequence of TrackDB objects from the database.
        no_parent (int): The integer value representing no parent.

    Returns:
        tuple[nx.DiGraph, list[str]]: A tuple containing the constructed
            lineage graph and a list of any errors found during the build.
    """
    G = nx.DiGraph()
    track_map = {tr.track_id: tr for tr in tracks}
    errors = []
    for tr in tracks:
        G.add_node(
            tr.track_id, root=tr.root, t_begin=tr.t_begin, t_end=tr.t_end
        )
        if tr.parent_track_id is not None and tr.parent_track_id != no_parent:
            parent = track_map.get(tr.parent_track_id)
            if parent is None:
                errors.append(
                    f"Parent {tr.parent_track_id} not found for child {tr.track_id}"
                )
                continue
            if parent.t_end >= tr.t_begin:
                errors.append(
                    f"Parent {parent.track_id} ends at {parent.t_end}, but child {tr.track_id} begins at {tr.t_begin}."
                )
                continue
            G.add_edge(tr.parent_track_id, tr.track_id)
    return G, errors


def check_no_cycles(G: nx.DiGraph) -> list[str]:
    """Checks for cycles in the lineage graph.

    Args:
        G (nx.DiGraph): The lineage graph, where nodes are tracks.

    Returns:
        list[str]: A list containing an error message if a cycle is found.
            Returns an empty list otherwise.
    """
    try:
        cycle = nx.find_cycle(G)
        return [f"Cycle detected in lineage graph: {cycle}"]
    except nx.NetworkXNoCycle:
        return []


def check_roots_present(G: nx.DiGraph) -> list[str]:
    """Verifies that all tracks in a connected component share the same root ID.

    Args:
        G (nx.DiGraph): The lineage graph with 'root' as a node attribute.

    Returns:
        list[str]: A list of error messages for components with multiple root
            values. Returns an empty list if all are consistent.
    """
    errors = []
    for component in nx.weakly_connected_components(G):
        roots = {G.nodes[node]["root"] for node in component}
        if len(roots) > 1:
            errors.append(
                f"Component {component} has multiple root values: {roots}"
            )
    return errors


def check_roots_consistency(G: nx.DiGraph) -> list[str]:
    """Checks if each track's root ID matches all of its ancestors' root IDs.

    Args:
        G (nx.DiGraph): The lineage graph with 'root' as a node attribute.

    Returns:
        list[str]: A list of error messages for any inconsistencies found.
            Returns an empty list otherwise.
    """
    errors = []
    for node in G.nodes:
        root_val = G.nodes[node]["root"]
        # For each node, walk up to the "real" root and compare with .root
        pred = list(G.predecessors(node))
        while pred:
            parent = pred[0]
            if G.nodes[parent]["root"] != root_val:
                errors.append(
                    f"Track {node} has root {root_val} but parent {parent} has root {G.nodes[parent]['root']}"
                )
            pred = list(G.predecessors(parent))
    return errors


####################################################
# Combined test
####################################################


def run_tracking_db_checks(session: Session) -> list[str]:
    """
    Runs a comprehensive suite of integrity checks on the tracking database.

    Args:
        session (Session): The SQLAlchemy session connected to the database.

    Returns:
        list[str]: A consolidated list of all error messages found during the
            checks. Returns an empty list if the database is valid.
    """
    errors = []
    models = [CellDB, TrackDB]
    # Database integrity checks
    errors += check_tables_present(session, models)
    errors += check_columns_present(session, models)
    errors += check_no_orphan_cells(session)
    errors += check_no_orphan_tracks(session)

    # If previous checks passed, proceed to lineage checks
    if not errors:
        tracks = session.query(TrackDB).all()
        G, build_errors = build_track_graph(tracks)
        errors += build_errors
        errors += check_no_cycles(G)
        errors += check_roots_present(G)
        errors += check_roots_consistency(G)
    return errors
