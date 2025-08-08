"""Resource loading module for Track Gardener.

This file contains functions responsible for loading external resources, like
dynamically specified functions, based on a validated configuration.
"""

from typing import Callable

from .exceptions import ConfigEnvironmentError
from .importers import (
    load_function_from_module,
    load_function_from_path,
)
from .models import TrackGardenerConfig


def load_measurement_functions(
    config: TrackGardenerConfig,
) -> dict[str | tuple, Callable]:
    """Loads all measurement functions specified in the configuration.

    This function iterates through the measurement configurations and dynamically
    loads the callable functions from either the built-in 'track_gardener'
    modules or custom user-provided Python scripts.

    Args:
        config: A validated `TrackGardenerConfig` object containing the
            measurement specifications.

    Returns:
        A dictionary mapping a unique identifier (either a function name for
        built-in functions or a (path, function_name) tuple for custom ones)
        to the actual loaded, callable function object.

    Raises:
        ConfigEnvironmentError: If any function cannot be loaded from its specified
            source module or file path.
    """

    loaded_funcs: dict[str | tuple, Callable] = {}

    for measurement in config.cell_measurements:
        # Skip regionprops as they are not dynamically loaded functions
        if measurement.source == "regionprops":
            continue

        # Determine the source and attempt to load the function
        if measurement.source == "track_gardener":
            module_path = "track_gardener.signals.calculate_signals"
            success, func_or_err = load_function_from_module(
                module_path, measurement.function
            )
            key = measurement.function
        else:  # The source is a custom script path
            success, func_or_err = load_function_from_path(
                measurement.source, measurement.function
            )
            key = (measurement.source, measurement.function)

        # Handle loading errors immediately
        if not success:
            # func_or_err contains the error message string on failure
            raise ConfigEnvironmentError(str(func_or_err))

        # On success, store the loaded function in the dictionary
        loaded_funcs[key] = func_or_err

    return loaded_funcs
