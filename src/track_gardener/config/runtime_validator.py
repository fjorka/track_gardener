"""Contains the RuntimeValidator for context-dependent config checks.

This module provides the `RuntimeValidator` class, which is responsible for the
second stage of the configuration validation pipeline. After the configuration
file has been successfully parsed and its basic structure has been validated by
Pydantic, this validator performs checks that depend on the runtime environment,
such as verifying file paths, database connectivity, and the signatures of
dynamically loaded functions.
"""

import inspect
from typing import TYPE_CHECKING, Callable

from skimage.measure._regionprops import COL_DTYPES, _require_intensity_image
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from .exceptions import ConfigEnvironmentError

if TYPE_CHECKING:
    from .models import CellMeasurement, TrackGardenerConfig


class RuntimeValidator:
    """Performs I/O-heavy and context-dependent validation checks."""

    def __init__(
        self,
        config: "TrackGardenerConfig",
        loaded_funcs: dict[str | tuple, Callable],
    ):
        """Initializes the validator with a config and pre-loaded functions.

        Args:
            config: A structurally valid `TrackGardenerConfig` object.
            loaded_funcs: A dictionary of pre-loaded, callable functions that
                correspond to the measurements defined in the config.
        """
        self.config = config
        self.loaded_functions = loaded_funcs

    def validate(self) -> None:
        """Runs all runtime validation checks in sequence.

        Raises:
            ConfigEnvironmentError: If any validation check fails.
        """
        self._validate_all_measurements()
        self._validate_database()

    def _validate_all_measurements(self) -> None:
        """Validates all measurement sources and function signatures."""
        for m in self.config.cell_measurements:
            if m.source == "regionprops":
                self._validate_regionprops_function(m)
            else:
                self._validate_function_signature(m)

    def _validate_regionprops_function(self, m: "CellMeasurement") -> None:
        """Validates that a requested regionprops function is supported."""
        if m.channels:
            if m.function not in _require_intensity_image:
                raise ConfigEnvironmentError(
                    f"Regionprops function '{m.function}' with channels is not supported."
                )
        else:
            if m.function not in COL_DTYPES:
                raise ConfigEnvironmentError(
                    f"Regionprops function '{m.function}' without channels is not supported."
                )

    def _validate_function_signature(self, m: "CellMeasurement") -> None:
        """Validates a pre-loaded function's kwargs against its signature."""
        key = (
            m.function
            if m.source == "track_gardener"
            else (m.source, m.function)
        )
        # The key is guaranteed to exist because the loader would have failed otherwise
        loaded_func = self.loaded_functions[key]

        sig = inspect.signature(loaded_func)
        func_params = set(sig.parameters.keys())

        for kwarg_name in m.kwargs:
            if kwarg_name not in func_params:
                raise ConfigEnvironmentError(
                    f"Config provides an unknown argument '{kwarg_name}' for function "
                    f"'{m.function}'. Valid arguments are: {list(func_params)}"
                )

    def _validate_database(self) -> None:
        """Validates database connectivity and signals presence."""
        db_path = str(self.config.database.path)
        if not self.config.database.path.exists():
            raise ConfigEnvironmentError(f"Database file not found: {db_path}")

        try:
            engine = create_engine(f"sqlite:///{db_path}")
            # The session is created just to test connectivity
            _ = sessionmaker(bind=engine)()
        except SQLAlchemyError as e:
            raise ConfigEnvironmentError(
                f"Failed to connect to or validate database at '{db_path}': {e}"
            ) from e

        # Validate that all signals requested by graphs exist
        for graph in self.config.graphs or []:
            for signal in graph.signals:
                if signal not in self.config.measurement_names:
                    raise ConfigEnvironmentError(
                        f"Graph '{graph.name}' requests an unknown signal: '{signal}'."
                    )
