"""Factory for creating a customized cell signal calculation function.

This module provides the `create_calculate_signals_function`, which acts as a
factory to assemble a specialized function based on a validated application
configuration. It uses a pre-loaded set of callables and a configuration
object to build a closure that efficiently calculates all requested measurements
for a single cell.
"""

from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from skimage.measure import regionprops

from ..config.models import TrackGardenerConfig

if TYPE_CHECKING:
    import numpy.typing as npt
    from skimage.measure._regionprops import RegionProperties


def create_calculate_signals_function(
    config: TrackGardenerConfig, loaded_funcs: dict[str | tuple, Callable]
) -> Callable | None:
    """Creates a signal calculation function from a validated config.

    This factory acts on a pre-validated configuration object and a dictionary
    of pre-loaded functions to construct an optimized, single-purpose function
    for calculating all specified cell measurements. It pre-processes the
    configuration to make the returned function as efficient as possible.

    Args:
        config: A validated `TrackGardenerConfig` object.
        loaded_funcs: A dictionary mapping function identifiers to the actual
            pre-loaded, callable functions.

    Returns:
        A callable function `calculate_cell_signals(cell, t, ch_data_list)`
        that computes all measurements, or None if no measurements are configured.
    """
    if not config.cell_measurements:
        return None

    # Pre-process and cache information from the config for efficiency
    ch_names = [ch.name for ch in config.signal_channels]
    reg_no_signal = [
        m
        for m in config.cell_measurements
        if m.source == "regionprops" and not m.channels
    ]
    reg_signal = [
        m
        for m in config.cell_measurements
        if m.source == "regionprops" and m.channels
    ]
    gardener_signal = [
        m for m in config.cell_measurements if m.source == "track_gardener"
    ]
    custom_signal = [
        m
        for m in config.cell_measurements
        if m.source not in ["regionprops", "track_gardener"]
    ]

    # --- The Dynamically Generated Calculation Function ---
    def calculate_cell_signals(
        cell: "RegionProperties", t: int, ch_data_list: list["npt.NDArray"]
    ) -> dict[str, Any]:
        """Calculates all configured signals for a single cell at a time point.

        Note:
            This function is a dynamically generated closure created by the
            `create_calculate_signals_function` factory.

        Args:
            cell: A `RegionProperties` object for the cell from `skimage.measure`.
            t: The time point (frame index) of the measurement.
            ch_data_list: A list of numpy arrays, where each array is the
                image data for a specific signal channel.

        Returns:
            A dictionary where keys are the final measurement names and values
            are the calculated results.
        """
        cell_dict: dict[str, Any] = {}

        # 1. Direct regionprops measurements (no intensity image)
        for m in reg_no_signal:
            cell_dict[m.function] = getattr(cell, m.function)

        # 2. Regionprops measurements with an intensity image
        if reg_signal:
            min_r, min_c, max_r, max_c = cell.bbox
            signal_cube = np.zeros(
                (max_r - min_r, max_c - min_c, len(ch_names)),
                dtype=ch_data_list[0].dtype,
            )
            for i, ch_image in enumerate(ch_data_list):
                # Handle time-series (3D) or single-frame (2D) data
                img_slice = ch_image[t] if ch_image.ndim == 3 else ch_image
                signal_cube[..., i] = img_slice[min_r:max_r, min_c:max_c]

            props = regionprops(
                cell.image.astype(int), intensity_image=signal_cube
            )[0]

            for m in reg_signal:
                base_name = m.name or m.function
                prop_result = getattr(props, m.function)
                for ch_name in m.channels:
                    idx = ch_names.index(ch_name)
                    cell_dict[f"{ch_name}_{base_name}"] = prop_result[idx]

        # 3. Pre-loaded Track Gardener functions
        for m in gardener_signal:
            func = loaded_funcs[m.function]
            result = func(cell, t, ch_data_list, **m.kwargs)
            base_name = m.name or m.function
            for ch_name in m.channels:
                idx = ch_names.index(ch_name)
                cell_dict[f"{ch_name}_{base_name}"] = result[idx]

        # 4. Pre-loaded custom functions from user scripts
        for m in custom_signal:
            key = (m.source, m.function)
            func = loaded_funcs[key]
            result = func(cell, t, ch_data_list, **m.kwargs)
            base_name = m.name or m.function
            for ch_name in m.channels:
                idx = ch_names.index(ch_name)
                cell_dict[f"{ch_name}_{base_name}"] = result[idx]

        return cell_dict

    return calculate_cell_signals
