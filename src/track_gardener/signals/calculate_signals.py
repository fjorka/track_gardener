"""Functions for quantifying signals statistics in cellular regions.

This module provides high-level functions to calculate statistics (e.g., mean,
median, sum) on pixel intensities within a cell's primary region (e.g. nucleus) or in a
surrounding perineighborhood ring. It is designed to work with Dask arrays
and integrates with configuration models by accepting
flexible keyword arguments.
"""

from functools import partial
from typing import TYPE_CHECKING, Any, Callable

import dask.array as da
import numpy as np
from skimage.morphology import binary_dilation, disk

if TYPE_CHECKING:
    from skimage.measure._regionprops import RegionProperties

# A dictionary mapping statistic names to their dask array functions
STATISTIC_FUNCS: dict[str, Callable[[da.Array], da.Array]] = {
    "mean": da.mean,
    "median": partial(da.percentile, q=50),
    "sum": da.sum,
    "max": da.max,
    "min": da.min,
}

# -----------------------------------------------------------------------------
# Private Helper Functions
# -----------------------------------------------------------------------------


def _compute_if_dask(value: Any) -> Any:
    """Computes a value if it is a Dask array, otherwise returns it.

    Args:
        value: The input value, which may or may not be a Dask array.

    Returns:
        The computed value if the input was a Dask array, otherwise the
        original value.
    """
    if isinstance(value, da.core.Array):
        value = value.compute()

    if isinstance(value, (np.ndarray, np.generic)) and value.size == 1:
        return value.item()

    return value


# -----------------------------------------------------------------------------
# Public Measurement Functions
# -----------------------------------------------------------------------------


def cell_signal(
    cell: "RegionProperties",
    t: int,
    ch_data_list: list[da.Array],
    statistics: str = "median",
    **kwargs: Any,
) -> list[float]:
    """Calculates a signal statistic within the primary body of a cell.

    Args:
        cell: The scikit-image region property object for the cell.
        t: The timepoint (frame) to analyze. Ignored for 2D arrays.
        ch_data_list: A list of Dask arrays (2D or 3D), one for each image channel.
        statistics: The name of the statistic to compute. Defaults to 'median'.
            Options include 'mean', 'median', 'sum', 'max', and 'min'.
        **kwargs: Keyword arguments for the measurement.

    Returns:
        A list of the calculated signal values, one for each channel.

    Raises:
        ValueError: If the requested statistic is not supported.
    """
    # Handle potential alias (e.g. 'statistic' vs 'statistics')
    if "statistic" in kwargs:
        statistics = kwargs["statistic"]

    if statistics not in STATISTIC_FUNCS:
        raise ValueError(
            f"Unsupported statistic: '{statistics}'. "
            f"Use one of {list(STATISTIC_FUNCS.keys())}."
        )

    agg_func = STATISTIC_FUNCS[statistics]
    min_r, min_c, max_r, max_c = cell.bbox
    cell_mask = cell.image > 0

    results = []
    for signal_da in ch_data_list:
        if signal_da.ndim == 3:
            roi = signal_da[t, min_r:max_r, min_c:max_c]
        else:
            roi = signal_da[min_r:max_r, min_c:max_c]
        masked_signal = roi[cell_mask]
        result = agg_func(masked_signal)
        results.append(_compute_if_dask(result))

    return results


def ring_signal(
    cell: "RegionProperties",
    t: int,
    ch_data_list: list[da.Array],
    ring_width: int | None = None,
    statistics: str = "median",
    **kwargs: Any,
) -> list[float]:
    """Calculates a signal statistic in a ring around a cell.

    This function defines a "ring" around the cell's primary body by dilating
    its mask and subtracting the original mask. It then calculates the
    requested statistic on the pixel intensities within this ring.

    Args:
        cell: The scikit-image region property object for the cell.
        t: The timepoint (frame) to analyze. Ignored for 2D arrays.
        ch_data_list: A list of Dask arrays (2D or 3D), one for each image channel.
        ring_width: The required width of the ring in pixels.
        statistics: The name of the statistic to compute. Defaults to 'mean'.
        **kwargs: Keyword arguments for the measurement.

    Returns:
        A list of the calculated ring signal values, one for each channel.

    Raises:
        KeyError: If the required 'ring_width' argument is not provided.
        ValueError: If the requested statistic is not supported.
        AssertionError: If an internal logic error leads to a shape mismatch
            between the image ROI and the generated ring mask.
    """
    if ring_width is None:
        # Fallback if passed in kwargs but not captured (unlikely with explicit arg)
        if "ring_width" in kwargs:
            ring_width = kwargs["ring_width"]
        else:
            raise KeyError("Missing required keyword argument: 'ring_width'")

    if "statistic" in kwargs:
        statistics = kwargs["statistic"]

    if statistics not in STATISTIC_FUNCS:
        raise ValueError(
            f"Unsupported statistic: '{statistics}'. "
            f"Use one of {list(STATISTIC_FUNCS.keys())}."
        )

    agg_func = STATISTIC_FUNCS[statistics]
    img_shape = ch_data_list[0].shape

    # 1. Define the padded bounding box, clamped to image boundaries.
    min_r, min_c, max_r, max_c = cell.bbox
    pad_min_r = max(0, min_r - ring_width)
    pad_min_c = max(0, min_c - ring_width)

    if ch_data_list[0].ndim == 3:
        img_h, img_w = img_shape[1], img_shape[2]
    else:
        img_h, img_w = img_shape[0], img_shape[1]
    pad_max_r = min(img_h, max_r + ring_width)
    pad_max_c = min(img_w, max_c + ring_width)

    # 2. Create the ring mask, which will have the same dimensions as the ROI.
    pad_top = min_r - pad_min_r
    pad_bottom = pad_max_r - max_r
    pad_left = min_c - pad_min_c
    pad_right = pad_max_c - max_c

    padded_cell_mask = np.pad(
        cell.image,
        pad_width=((pad_top, pad_bottom), (pad_left, pad_right)),
        mode="constant",
    )

    dilated_mask = binary_dilation(
        padded_cell_mask, footprint=disk(ring_width)
    )
    ring_mask = dilated_mask & ~padded_cell_mask

    # 3. Apply mask and calculate statistic for each channel.
    results = []
    for signal_da in ch_data_list:
        if signal_da.ndim == 3:
            roi = signal_da[t, pad_min_r:pad_max_r, pad_min_c:pad_max_c]
        else:
            roi = signal_da[pad_min_r:pad_max_r, pad_min_c:pad_max_c]

        # This is a sanity check. Under the current logic, this should never fail.
        # It protects against future regressions or unexpected array-like inputs.
        if roi.shape != ring_mask.shape:
            raise AssertionError(
                "Internal logic error: The generated ring mask shape does not match "
                f"the sliced ROI shape ({ring_mask.shape} vs {roi.shape}). "
                "This indicates a bug in the padding or slicing calculation."
            )

        masked_signal = roi[ring_mask]
        result = agg_func(masked_signal)
        results.append(_compute_if_dask(result))

    return results
