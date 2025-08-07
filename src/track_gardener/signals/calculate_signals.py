from typing import TYPE_CHECKING, Any

import dask.array as da
import numpy as np
from skimage.morphology import binary_dilation, disk

if TYPE_CHECKING:
    from skimage.measure._regionprops import RegionProperties


def ring_intensity(
    cell: "RegionProperties",
    t: int,
    ch_data_list: list[da.Array],
    kwargs: dict[str, Any],
) -> list[float]:
    """Calculates the mean signal intensity in a ring around a cell.

    Args:
        cell ("RegionProperties"): The cell object.
        t (int): The timepoint.
        ch_data_list (list[da.Array]): A list of dask arrays, one per channel.
        kwargs (dict[str, Any]): Additional keyword arguments, e.g., 'ring_width'.

    Returns:
        list[float]: A list of mean ring intensities, one for each channel.
    """
    # get the ring width
    ring_width = kwargs.get("ring_width", 5)

    image_shape = ch_data_list[0].shape

    min_row, min_col, max_row, max_col = cell.bbox

    min_row_padded = max(min_row - ring_width, 0)
    min_col_padded = max(min_col - ring_width, 0)
    max_row_padded = min(max_row + ring_width, image_shape[1])
    max_col_padded = min(max_col + ring_width, image_shape[2])

    # Dimensions of the padded region
    padded_rows = max_row_padded - min_row_padded
    padded_cols = max_col_padded - min_col_padded

    # create a mask
    cell_mask_padded = np.zeros((padded_rows, padded_cols), dtype=bool)
    # Calculate the position of the original cell mask within the padded mask
    mask_row_start = min_row - min_row_padded
    mask_row_end = mask_row_start + (max_row - min_row)
    mask_col_start = min_col - min_col_padded
    mask_col_end = mask_col_start + (max_col - min_col)

    # Place the original cell mask into the padded cell mask
    cell_mask_padded[
        mask_row_start:mask_row_end, mask_col_start:mask_col_end
    ] = cell.image

    # Dilate the cell mask to create the outer boundary (ring)
    dilated_mask = binary_dilation(
        cell_mask_padded, footprint=disk(ring_width)
    )

    # Create the ring mask by subtracting the original mask from the dilated mask
    ring_mask = dilated_mask & (~cell_mask_padded)

    signal_list = []
    # Extract the signal region corresponding to the padded bounding box
    for signal_cube in ch_data_list:
        signal_roi = signal_cube[
            t, min_row_padded:max_row_padded, min_col_padded:max_col_padded
        ]

        # Extract the signal values within the ring
        signal_in_ring = signal_roi[ring_mask]

        # Compute the desired statistic (e.g., mean or sum)
        ring_signal_mean = signal_in_ring.mean()

        if isinstance(ring_signal_mean, da.core.Array):
            ring_signal_mean = ring_signal_mean.compute()

        signal_list.append(ring_signal_mean)

    return signal_list
