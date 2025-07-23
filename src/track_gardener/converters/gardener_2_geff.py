from pathlib import Path

import geff
import networkx as nx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from track_gardener.db.db_model import Base, CellDB, TrackDB

# refactor to work directly with arrays instead of networkx
# add choosing which properties to export
# def build_cell_graph_streamed(session: Session) -> nx.DiGraph:
#     """
#     Track Database to NetworkX DiGraph conversion.
#     """

#     G = nx.DiGraph()

#     # Fetch all track IDs (as list of tuples), and flatten it
#     track_ids = session.query(TrackDB.track_id).all()
#     track_ids = [track_id for (track_id,) in track_ids]

#     for track_id in track_ids:
#         # Query cells from this track ordered by time
#         cells = (
#             session.query(CellDB)
#             .filter(CellDB.track_id == track_id)
#             .order_by(CellDB.t)
#             .all()
#         )

#         num_cells = len(cells)
#         if num_cells == 0:
#             continue

#         # Add nodes
#         for cell in cells:
#             G.add_node(
#                 cell.id,
#                 t=cell.t,
#                 y=cell.row,
#                 x=cell.col,
#                 track_id=cell.track_id,
#                 segm_id=cell.track_id,
#             )

#         # Add edges: from each cell to the closest next in time
#         for i in range(num_cells - 1):
#             source_cell = cells[i]
#             for j in range(i + 1, num_cells):
#                 target_cell = cells[j]
#                 if target_cell.t > source_cell.t:
#                     G.add_edge(
#                         source_cell.id,
#                         target_cell.id,
#                         track_id=track_id,
#                         dt=target_cell.t - source_cell.t,
#                     )
#                     break  # only the nearest future one
#     return G


def build_cell_graph_streamed(session: Session) -> nx.DiGraph:
    """
    Track Database to NetworkX DiGraph conversion, including inter-track (parent-child) edges.
    """

    G = nx.DiGraph()

    # Fetch all tracks, mapping track_id to parent_track_id
    track_info = session.query(TrackDB.track_id, TrackDB.parent_track_id).all()
    track_to_parent = dict(track_info)

    # Fetch all track IDs
    track_ids = list(track_to_parent.keys())

    # For each track, get all its cells ordered by time
    track_cells = {}
    for track_id in track_ids:
        cells = (
            session.query(CellDB)
            .filter(CellDB.track_id == track_id)
            .order_by(CellDB.t)
            .all()
        )
        if cells:
            track_cells[track_id] = cells
            # Add nodes for these cells
            for cell in cells:
                G.add_node(
                    cell.id,
                    t=cell.t,
                    y=cell.row,
                    x=cell.col,
                    track_id=cell.track_id,
                    segm_id=cell.track_id,
                )
            # Add intra-track edges (successive in time)
            for i in range(len(cells) - 1):
                G.add_edge(
                    cells[i].id,
                    cells[i + 1].id,
                    track_id=track_id,
                    dt=cells[i + 1].t - cells[i].t,
                )

    # Now add inter-track (parent-child) edges
    for child_track_id, parent_track_id in track_to_parent.items():
        if (
            parent_track_id is not None
            and parent_track_id in track_cells
            and child_track_id in track_cells
        ):
            parent_cells = track_cells[parent_track_id]
            child_cells = track_cells[child_track_id]
            # Find the last cell in the parent track
            last_parent_cell = parent_cells[-1]
            # Find the first cell in the child track
            first_child_cell = child_cells[0]
            # Add edge from last parent to first child cell
            G.add_edge(
                last_parent_cell.id,
                first_child_cell.id,
                track_id=child_track_id,  # Optionally use child or parent track
                dt=first_child_cell.t - last_parent_cell.t,
                lineage=True,  # mark as a lineage edge
            )

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
        zarr_format=2,
    )
