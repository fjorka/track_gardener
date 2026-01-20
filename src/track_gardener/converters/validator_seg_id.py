from typing import Dict, List, Tuple, Union

import numpy as np
import zarr
from loguru import logger
from tqdm import tqdm


def validate_geff_seg_ids(
    geff_group_path: str,
    segmentation_path: str,
    seg_id_field: str = "seg_id",
    check_xy_position: bool = True,
    check_extra_segmentations: bool = False,
) -> Tuple[
    bool, Dict[str, Union[List[Tuple[int, str]], Dict[int, List[int]]]]
]:
    """
    Validates seg_id-like field in GEFF nodes against segmentation array.

    Parameters:
    - geff_group_path: Path to Zarr group containing GEFF structure (e.g., "store.zarr/tracks").
    - segmentation_path: Path to segmentation array within Zarr store (e.g., "store.zarr/segmentation").
    - seg_id_field: Name of node property to use as seg_id (e.g., "track_id").
    - check_xy_position: Whether to verify (x,y) falls within the segmented object.
    - check_extra_segmentations: Whether to report segmented objects not found in GEFF.

    Returns:
    - Tuple: (boolean indicating success, dictionary of validation results)
    """

    logger.info(f"Opening GEFF group from: {geff_group_path}")
    geff_group = zarr.open_group(geff_group_path, mode="r")
    seg_array = zarr.open_array(segmentation_path, mode="r")

    props = geff_group["nodes"]["props"]
    t_vals = props["t"]["values"][:].astype(int)
    seg_ids = props[seg_id_field]["values"][:]

    if check_xy_position:
        x_vals = props["x"]["values"][:].astype(int)
        y_vals = props["y"]["values"][:].astype(int)

    # check if masking is available
    if "missing" in props[seg_id_field]:
        missing_mask = props[seg_id_field]["missing"][:]
        seg_ids = np.ma.masked_array(seg_ids, mask=missing_mask)
        t_vals = np.ma.masked_array(t_vals, mask=missing_mask)
        if check_xy_position:
            x_vals = np.ma.masked_array(x_vals, mask=missing_mask)
            y_vals = np.ma.masked_array(y_vals, mask=missing_mask)

    logger.info("Beginning node validation...")
    results = []

    # Sort by time to optimize IO
    sorted_indices = np.argsort(t_vals)

    current_t = -1
    label_frame = None
    frame_load_failed = False
    current_frame_labels = None

    for idx in tqdm(sorted_indices):
        t = t_vals[idx]
        seg_id = seg_ids[idx]

        if np.ma.is_masked(seg_id):
            logger.warning(
                f"Seg ID is masked for {seg_id} at frame {t}, skipping."
            )
            continue

        # Load frame if time changed
        if t != current_t:
            current_t = t
            try:
                label_frame = seg_array[int(t)]
                frame_load_failed = False
                # Pre-calculate unique labels for O(1) lookup
                current_frame_labels = set(np.unique(label_frame))
            except IndexError:
                frame_load_failed = True
                label_frame = None
                current_frame_labels = None

        if frame_load_failed:
            logger.warning(f"Frame {t} is out of bounds at index {idx}")
            results.append((idx, "frame_out_of_bounds"))
            continue

        if seg_id not in current_frame_labels:
            logger.warning(
                f"Seg ID {seg_id} not found in frame {t} at index {idx}"
            )
            results.append((idx, "seg_id_missing"))
            continue

        if check_xy_position:
            x, y = x_vals[idx], y_vals[idx]
            if not (
                0 <= y < label_frame.shape[0] and 0 <= x < label_frame.shape[1]
            ):
                logger.warning(
                    f"XY position ({x},{y}) out of bounds in frame {t} at index {idx}"
                )
                results.append((idx, "xy_out_of_bounds"))
                continue
            if label_frame[y, x] != seg_id:
                logger.warning(
                    f"XY mismatch for index {seg_id} at frame {t}: expected position: ({x},{y})"
                )
                results.append((idx, "xy_mismatch"))
                continue

    extra_segments = {}
    if check_extra_segmentations:
        logger.info(
            "Checking for extra segmentations not referenced in GEFF..."
        )
        geff_seg_ids_by_frame = {}
        for t, seg_id in zip(t_vals, seg_ids):
            geff_seg_ids_by_frame.setdefault(t, set()).add(seg_id)

        for t in range(seg_array.shape[0]):
            frame = seg_array[t]
            seg_ids_in_frame = set(np.unique(frame)) - {0}
            extra = seg_ids_in_frame - geff_seg_ids_by_frame.get(t, set())
            if extra:
                logger.debug(f"Frame {t} has extra seg_ids: {extra}")
                extra_segments[t] = sorted(extra)

    passed = (
        all(result[1] == "valid" for result in results) and not extra_segments
    )
    if passed:
        logger.success("All validations passed successfully.")
    else:
        logger.warning("Validation failed for one or more nodes.")

    return passed, {
        "node_issues": results,
        "extra_segments": (
            extra_segments if check_extra_segmentations else None
        ),
    }
