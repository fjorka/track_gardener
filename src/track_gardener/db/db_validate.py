import networkx as nx
from sqlalchemy import inspect, select

from track_gardener.db.db_model import NO_PARENT, CellDB, TrackDB

####################################################
# Database Integrity Checks
####################################################


def check_table_existence(session, models):
    inspector = inspect(session.bind)
    required_tables = {model.__tablename__ for model in models}
    existing_tables = set(inspector.get_table_names())
    missing = required_tables - existing_tables
    if missing:
        return [f"Missing tables: {missing}"]
    return []


def check_column_existence(session, models):
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


def check_orphan_cells(session):
    """
    Check for orphaned cells in the database.
    Orphaned cells are those that do not have a corresponding track.
    """
    orphaned = (
        session.execute(
            select(CellDB)
            .outerjoin(TrackDB, CellDB.track_id == TrackDB.track_id)
            .where(TrackDB.track_id is None)
        )
        .scalars()
        .all()
    )
    if orphaned:
        return [f"Orphaned cells found: {len(orphaned)}"]
    return []


def check_unused_tracks(session):

    unused = (
        session.execute(
            select(TrackDB)
            .outerjoin(CellDB, TrackDB.track_id == CellDB.track_id)
            .where(CellDB.track_id is None)
        )
        .scalars()
        .all()
    )
    if unused:
        return [f"Tracks with no associated cells: {len(unused)}"]
    return []


####################################################
# Graph Checks
####################################################


def build_track_graph(tracks, no_parent=NO_PARENT):
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


def check_no_cycles(G):
    try:
        cycle = nx.find_cycle(G)
        return [f"Cycle detected in lineage graph: {cycle}"]
    except nx.NetworkXNoCycle:
        return []


def check_roots_in_components(G):
    errors = []
    for component in nx.weakly_connected_components(G):
        roots = {G.nodes[node]["root"] for node in component}
        if len(roots) > 1:
            errors.append(
                f"Component {component} has multiple root values: {roots}"
            )
    return errors


def check_all_descendants_root_consistency(G):
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


def run_tracking_db_checks(session):
    errors = []
    models = [CellDB, TrackDB]
    # Database integrity checks
    errors += check_table_existence(session, models)
    errors += check_column_existence(session, models)
    errors += check_orphan_cells(session)
    errors += check_unused_tracks(session)

    # If previous checks passed, proceed to lineage checks
    if not errors:
        tracks = session.query(TrackDB).all()
        G, build_errors = build_track_graph(tracks)
        errors += build_errors
        errors += check_no_cycles(G)
        errors += check_roots_in_components(G)
        errors += check_all_descendants_root_consistency(G)
    return errors
