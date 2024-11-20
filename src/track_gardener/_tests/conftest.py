import sqlite3
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="function")
def db_session():
    """
    Create an exact in-memory copy of the SQLite database for testing.
    """
    # Path to the original database
    test_db_path = Path(__file__).parent / "fixtures" / "db_2tables_test.db"

    # Open connections to the original and in-memory databases
    original_connection = sqlite3.connect(test_db_path)
    memory_connection = sqlite3.connect(":memory:")

    # Use SQLite's backup feature to copy the original database to the in-memory database
    original_connection.backup(memory_connection)

    # Close the connection to the original database
    original_connection.close()

    # Create an SQLAlchemy engine and session for the in-memory database
    memory_engine = create_engine(
        "sqlite://", creator=lambda: memory_connection
    )
    MemorySession = sessionmaker(bind=memory_engine)

    # Provide the session for the test
    memory_session = MemorySession()

    yield memory_session

    # Close the session but NOT the memory connection
    memory_session.close()


@pytest.fixture(scope="function")
def viewer(make_napari_viewer):

    viewer = make_napari_viewer()
    viewer.add_labels(data=np.zeros([10000, 10000], dtype=int))

    yield viewer

    viewer.close()
