"""Pydantic models for parsing and validating the Track Gardener config file.

This module defines a set of Pydantic models that correspond to the structure
of the project's YAML configuration file. These models provide a single source
of truth for data validation, type coercion, and error handling.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, model_validator


class ExperimentSettings(BaseModel):
    """Defines the experiment's metadata."""

    experiment_name: str
    description: str | None = None


class SignalChannel(BaseModel):
    """Defines a single imaging channel.

    Attributes:
        name: A short, unique identifier for the channel (e.g., 'ch0', 'gfp').
        path: The file path to the Zarr store containing the image data.
        lut: The look-up table (e.g., 'gray', 'green') for visualization.
        contrast_limits: Optional list of [min, max] values for display contrast.
    """

    name: str
    path: Path
    lut: str = "gray"
    contrast_limits: list[int | float] | None = None


class CellMeasurement(BaseModel):
    """Defines a single measurement to be performed on cells.

    Attributes:
        function: The name of the measurement function to apply.
        source: The origin of the function.
        name: An optional short name for the measurement.
        channels: An optional list of channel names to apply this measurement to.
        kwargs: A dictionary to hold any additional keyword arguments for the
            measurement function (e.g., 'ring_width').
    """

    function: str
    source: str
    name: str | None = None
    channels: list[str] | None = None
    kwargs: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _capture_extra_fields(cls, data: Any) -> Any:
        """Captures all unknown fields into the 'kwargs' dictionary.

        This pre-processing step ensures that any parameters in the config
        not explicitly defined in the model (like 'ring_width') are collected
        and made available for the measurement function.

        Args:
            data: The raw dictionary data for this model.

        Returns:
            The modified dictionary with extra fields moved into 'kwargs'.
        """
        if not isinstance(data, dict):
            return data

        defined_fields = set(cls.model_fields)
        extra_kwargs = {}

        for field_name, _value in list(data.items()):
            if field_name not in defined_fields:
                extra_kwargs[field_name] = data.pop(field_name)

        # Ensure kwargs from previous steps are merged, not overwritten
        if "kwargs" in data:
            data["kwargs"].update(extra_kwargs)
        else:
            data["kwargs"] = extra_kwargs

        return data


class DatabaseSettings(BaseModel):
    """Defines the database connection settings.

    Attributes:
        path: The file path to the SQLite database file.
    """

    path: Path


class Graph(BaseModel):
    """Defines settings for a single plot in the output analysis.

    Attributes:
        name: The name of the graph.
        signals: A list of measurement names to plot on this graph.
        colors: A list of color names corresponding to each signal.
    """

    name: str
    signals: list[str]
    colors: list[str]


class TrackGardenerConfig(BaseModel):
    """The root model for the entire Track Gardener configuration.

    This class acts as the main entry point for parsing and validating the
    complete YAML configuration file.

    Attributes:
        experiment_settings: Metadata for the experiment.
        signal_channels: A list of imaging channels to be used.
        cell_measurements: A list of measurements to be calculated.
        database: Database connection settings.
        graphs: An optional list of graph configurations for plotting.
        cell_tags: An optional dictionary mapping labels to keyboard shortcuts.
    """

    experiment_settings: ExperimentSettings
    signal_channels: list[SignalChannel]
    cell_measurements: list[CellMeasurement]
    database: DatabaseSettings
    graphs: list[Graph] | None = None
    cell_tags: dict[str, str] | None = None
    labels_settings: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _compute_and_validate_measurement_names(self) -> "TrackGardenerConfig":
        """
        Eagerly computes the list of measurement names and validates their
        uniqueness as soon as the model is created. The result is stored
        for later use.
        """
        name_list: list[str] = []
        for f_config in self.cell_measurements:
            base_name = f_config.name or f_config.function
            if f_config.channels:
                for ch in f_config.channels:
                    name_list.append(f"{ch}_{base_name}")
            else:
                name_list.append(base_name)

        # Perform the validation
        if len(name_list) != len(set(name_list)):
            seen = set()
            duplicates = {n for n in name_list if n in seen or seen.add(n)}
            raise ValueError(
                f"Measurement names are not unique. Duplicates found: {list(duplicates)}"
            )

        # If valid, store the result in our private attribute
        self._measurement_names = name_list

        # Return the model instance to complete validation
        return self

    @property
    def measurement_names(self) -> list[str]:
        """Provides read-only access to the computed measurement names."""
        return self._measurement_names
