from pathlib import Path

import geff
import networkx as nx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from track_gardener.db.db_model import Base, CellDB, TrackDB


def build_cell_graph_streamed(session: Session) -> nx.DiGraph:
    """
    Track Database to NetworkX DiGraph conversion.
    """

    G = nx.DiGraph()

    # Fetch all track IDs (as list of tuples), and flatten it
    track_ids = session.query(TrackDB.track_id).all()
    track_ids = [track_id for (track_id,) in track_ids]

    for track_id in track_ids:
        # Query cells from this track ordered by time
        cells = (
            session.query(CellDB)
            .filter(CellDB.track_id == track_id)
            .order_by(CellDB.t)
            .all()
        )

        num_cells = len(cells)
        if num_cells == 0:
            continue

        # Add nodes
        for cell in cells:
            G.add_node(
                cell.id,
                t=cell.t,
                y=cell.row,
                x=cell.col,
                track_id=track_id,
                position=(cell.t, cell.row, cell.col),
            )

        # Add edges: from each cell to the closest next in time
        for i in range(num_cells - 1):
            source_cell = cells[i]
            for j in range(i + 1, num_cells):
                target_cell = cells[j]
                if target_cell.t > source_cell.t:
                    G.add_edge(
                        source_cell.id,
                        target_cell.id,
                        track_id=track_id,
                        dt=target_cell.t - source_cell.t,
                    )
                    break  # only the nearest future one
    return G


def db_to_geff(db_path: Path | str, g_path: Path | str):
    """
    Convert Track Gardener database to geff format.
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    session = Session(bind=engine)
    g = build_cell_graph_streamed(session)

    geff.write_nx(
        graph=g,
        path=g_path,
        axis_names=["t", "y", "x"],
        position_prop="position",
        zarr_format=2,
        validate=True,
    )
