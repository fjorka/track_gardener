import os

import pytest
import yaml

from track_gardener.db.config_functions import validateConfigFile


@pytest.fixture
def relative_db_path():
    # Dynamically calculate the database path based on the test file location
    return os.path.join(
        os.path.dirname(__file__), "fixtures", "db_2tables_test.db"
    )


@pytest.mark.parametrize(
    "config,expected_status,expected_message",
    [
        # Test valid configuration
        (
            lambda db_path: {
                "database": {"path": db_path},
                "signal_channels": [{"name": "ch1", "path": "signal.zarr"}],
                "cell_measurements": [
                    {"function": "area", "source": "regionprops"},
                    {
                        "function": "intensity_mean",
                        "source": "regionprops",
                        "channels": ["ch1"],
                        "name": "nuc",
                    },
                ],
                "graphs": [{"signals": ["area"]}],
            },
            True,
            "Config file is executable.",
        ),
        # Test missing database
        (
            lambda db_path: {
                "signal_channels": [{"path": "signal.zarr"}],
                "cell_measurements": [
                    {"function": "area", "source": "regionprops"}
                ],
                "graphs": [{"signals": ["area"]}],
            },
            False,
            "The database path is missing in the config file.",
        ),
        # Test unsupported signal channel format
        (
            lambda db_path: {
                "database": {"path": db_path},
                "signal_channels": [{"path": "signal.txt"}],
                "cell_measurements": [
                    {"function": "area", "source": "regionprops"}
                ],
                "graphs": [{"signals": ["area"]}],
            },
            False,
            "Accepting only zarr files as signal channels.",
        ),
        # Test unsupported signal channel format
        (
            lambda db_path: {
                "database": {"path": db_path},
                "signal_channels": [{"path": "signal.zarr"}],
                "cell_measurements": [
                    {"function": "areas", "source": "regionprops"}
                ],
                "graphs": [{"signals": ["area"]}],
            },
            False,
            "Requested regionprops functions without signals are not supported.",
        ),
        (
            lambda db_path: {
                "database": {"path": db_path},
                "signal_channels": [{"path": "signal.zarr"}],
                "cell_measurements": [
                    {
                        "function": "average_intensity",
                        "source": "regionprops",
                        "channels": ["ch1"],
                    }
                ],
                "graphs": [{"signals": ["area"]}],
            },
            False,
            "Requested regionprops functions with signals are not supported.",
        ),
        # Test non unique names
        (
            lambda db_path: {
                "database": {"path": db_path},
                "signal_channels": [{"path": "signal.zarr"}],
                "cell_measurements": [
                    {"function": "area", "source": "regionprops"},
                    {"function": "area", "source": "regionprops"},
                ],
                "graphs": [{"signals": ["area"]}],
            },
            False,
            "Measurement names are not unique.",
        ),
    ],
)
def test_validate_config_file(
    config, expected_status, expected_message, relative_db_path
):
    # Generate the dynamic configuration using the fixture
    config_dict = config(relative_db_path)

    # Write the configuration to a temporary YAML file
    with open("test_config.yaml", "w") as f:
        yaml.dump(config_dict, f)

    # Validate the configuration file
    status, message = validateConfigFile("test_config.yaml")
    assert status == expected_status
    assert message == expected_message

    # Clean up
    os.remove("test_config.yaml")
