from pathlib import Path

import pytest
import yaml

from ..config.exceptions import ConfigEnvironmentError, ConfigFormatError
from ..config.models import TrackGardenerConfig
from ..config.pipeline import load_and_validate_config


# A minimal valid config structure that we can modify for each test.
@pytest.fixture
def minimal_config(tmp_path: Path) -> dict:
    """Provides a minimal, structurally valid config dictionary."""
    # Use pytest's tmp_path fixture for safe, temporary file creation
    db_path = tmp_path / "test.db"
    db_path.touch()  # Create the dummy db file so the path exists

    return {
        "experiment_settings": {"experiment_name": "Test"},
        "database": {"path": str(db_path)},
        "signal_channels": [
            {"name": "ch0", "path": "signal.zarr", "lut": "gray"}
        ],
        "cell_measurements": [{"function": "area", "source": "regionprops"}],
    }


def test_valid_config_succeeds(minimal_config: dict, tmp_path: Path):
    """
    Tests that a valid configuration loads without raising any exceptions.
    """
    config_path = tmp_path / "config.yaml"
    with config_path.open("w") as f:
        yaml.dump(minimal_config, f)

    # The test passes if this function runs without raising an exception
    config_obj, loaded_functions = load_and_validate_config(str(config_path))

    # Also assert that we got the correct object type back
    assert isinstance(config_obj, TrackGardenerConfig)
    assert config_obj.experiment_settings.experiment_name == "Test"


# This single parametrize decorator can now handle all failure cases
@pytest.mark.parametrize(
    "modification, expected_exception, expected_message_match",
    [
        # --- ConfigFormatError Tests (problems with the file's content/shape) ---
        (
            {"database": None},
            ConfigFormatError,
            "Input should be a valid dictionary",  # Pydantic's message for missing required fields
        ),
        (
            {"signal_channels": "not_a_list"},
            ConfigFormatError,
            "Input should be a valid list",
        ),
        (
            {
                "cell_measurements": [
                    {"function": "area", "source": "regionprops"},
                    {
                        "function": "area_filled",
                        "source": "regionprops",
                        "name": "area",
                    },
                ]
            },
            ConfigFormatError,
            "Measurement names are not unique. Duplicates found: ['area']",
        ),
        # --- ConfigEnvironmentError Tests (structurally valid but contextually wrong) ---
        (
            {"database": {"path": "/path/to/non_existent.db"}},
            ConfigEnvironmentError,
            "Database file not found",
        ),
        (
            {
                "cell_measurements": [
                    {"function": "invalid_prop", "source": "regionprops"}
                ]
            },
            ConfigEnvironmentError,
            "Regionprops function 'invalid_prop' without channels is not supported",
        ),
        (
            {
                "graphs": [
                    {
                        "name": "Test",
                        "signals": ["unknown_signal"],
                        "colors": ["red"],
                    }
                ]
            },
            ConfigEnvironmentError,
            "requests an unknown signal: 'unknown_signal'",
        ),
    ],
)
def test_invalid_configs_fail(
    minimal_config: dict,
    tmp_path: Path,
    modification: dict,
    expected_exception: type[Exception],
    expected_message_match: str,
):
    """

    Tests that various invalid configurations fail with the correct exception
    and error message.

    Args:
        minimal_config: The base valid configuration fixture.
        tmp_path: The pytest fixture for creating temporary directories.
        modification: A dictionary of changes to apply to the minimal config
            to make it invalid for a specific test case.
        expected_exception: The custom exception class we expect to be raised.
        expected_message_match: A substring of the error message to check for.
    """
    # Apply the modification to create the invalid config for this test case
    minimal_config.update(modification)

    config_path = tmp_path / "config.yaml"
    with config_path.open("w") as f:
        yaml.dump(minimal_config, f)

    # Use pytest.raises as a context manager to assert that an exception is raised
    with pytest.raises(expected_exception) as excinfo:
        load_and_validate_config(str(config_path))

    # Assert that the error message contains the expected text
    assert expected_message_match in str(excinfo.value)
