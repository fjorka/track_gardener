"""Main pipeline for loading and validating the configuration file.

This module provides the primary orchestration function, `load_and_validate_config`.
It coordinates the various stages of processing, including parsing,
data model validation, resource loading, and runtime environment checks, to
produce a fully validated and ready-to-use configuration state.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import yaml
from pydantic import ValidationError

from .exceptions import ConfigFormatError
from .loader import load_measurement_functions
from .models import TrackGardenerConfig
from .runtime_validator import RuntimeValidator

if TYPE_CHECKING:
    from .models import TrackGardenerConfig


def load_and_validate_config(
    config_path: str,
) -> tuple["TrackGardenerConfig", dict[str | tuple, Callable]]:
    """Orchestrates the full config loading and validation pipeline.

    This function executes a multi-stage process:
    - Parses the YAML file and validates its structure against Pydantic models.
    - Resolves all relative file paths within the config to be absolute.
    - Loads all external measurement functions.
    - Performs runtime validation checks on the loaded resources.

    Args:
        config_path: The file path to the YAML configuration file.

    Returns:
        A tuple containing:
            - config_obj: A fully validated TrackGardenerConfig object.
            - loaded_functions: A dictionary of all pre-loaded measurement
              functions, ready to be passed to a factory.

    Raises:
        ConfigFormatError: If the file is not found, cannot be parsed, or fails
            the initial Pydantic data model validation.
        ConfigEnvironmentError: If the configuration references non-existent files,
            invalid functions, or fails other runtime checks.
    """

    # Parse and validate the config file's structure and types
    try:
        config_file_path = Path(config_path)
        with config_file_path.open("r") as f:
            raw_config = yaml.safe_load(f)
        config_obj = TrackGardenerConfig.model_validate(raw_config)
    except (
        FileNotFoundError,
        yaml.YAMLError,
        ValidationError,
        ValueError,
    ) as e:
        raise ConfigFormatError(
            f"Invalid config file format or content: {e}"
        ) from e

    # Resolve all relative paths
    config_dir = config_file_path.parent
    if not config_obj.database.path.is_absolute():
        config_obj.database.path = (
            config_dir / config_obj.database.path
        ).resolve()

    for channel in config_obj.signal_channels:
        if not channel.path.is_absolute():
            channel.path = (config_dir / channel.path).resolve()

    for measurement in config_obj.cell_measurements:
        if measurement.source not in ["regionprops", "track_gardener"]:
            source_path = Path(measurement.source)
            if not source_path.is_absolute():
                measurement.source = str((config_dir / source_path).resolve())

    # Load all external function resources
    loaded_functions = load_measurement_functions(config_obj)

    # Perform runtime validation using the loaded resources
    validator = RuntimeValidator(config_obj, loaded_functions)
    validator.validate()

    return config_obj, loaded_functions
