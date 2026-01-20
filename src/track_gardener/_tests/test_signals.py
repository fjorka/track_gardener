# conftest.py
# This file defines reusable fixtures for our tests.

from typing import Callable

import dask.array as da
import numpy as np
import pytest
from skimage.measure import regionprops

from ..config.models import (
    CellMeasurement,
    DatabaseSettings,
    ExperimentSettings,
    SignalChannel,
    TrackGardenerConfig,
)
from ..signals.calculate_signals import cell_signal, ring_signal
from ..signals.factory import create_calculate_signals_function

# --- Pytest Fixtures ---


@pytest.fixture
def mock_image_data() -> tuple[np.ndarray, np.ndarray]:
    """Creates a mock label image and a corresponding signal image."""
    label_img = np.zeros((100, 100), dtype=np.uint8)
    # A 10x10 cell at position (20, 20)
    label_img[20:30, 20:30] = 1
    # A cell at the edge
    label_img[0:10, 80:90] = 2

    signal_img = np.zeros_like(label_img, dtype=np.float32)
    # Cell 1 has a constant signal of 10.0
    # and a signal of 2.0
    signal_img[15:35, 15:35] = 2.0
    signal_img[20:30, 20:30] = 10.0
    signal_img[25, 25] = 1000
    # Cell 2 has a signal of 5.0
    signal_img[0:15, 75:95] = 1.0
    signal_img[0:10, 80:90] = 5.0

    return label_img, signal_img


@pytest.fixture
def mock_dask_array(mock_image_data) -> list[da.Array]:
    """Converts the mock signal image to a dask array list."""
    _, signal_img = mock_image_data
    # Create a 3D dask array (T, H, W) and return it in a list
    dask_arr = da.from_array(signal_img[np.newaxis, ...], chunks=(1, 100, 100))
    return [dask_arr]


@pytest.fixture
def cell_props(mock_image_data):
    """Provides the regionprops for the primary test cell (ID=1)."""
    label_img, _ = mock_image_data
    return regionprops(label_img)[0]


@pytest.fixture
def edge_cell_props(mock_image_data):
    """Provides the regionprops for the cell at the image edge (ID=2)."""
    label_img, _ = mock_image_data
    return regionprops(label_img)[1]


@pytest.fixture
def basic_config(tmp_path) -> TrackGardenerConfig:
    """A basic, valid config for factory testing."""
    # Use pytest's tmp_path fixture to create dummy file paths for validation
    db_path = tmp_path / "test.db"
    zarr_path = tmp_path / "test.zarr"

    return TrackGardenerConfig(
        experiment_settings=ExperimentSettings(experiment_name="test_exp"),
        signal_channels=[SignalChannel(name="CH1", path=zarr_path)],
        database=DatabaseSettings(path=db_path),
        cell_measurements=[
            CellMeasurement(function="area", source="regionprops"),
            CellMeasurement(
                function="ring_signal",
                source="track_gardener",
                channels=["CH1"],
                ring_width=5,
                statistics="mean",
            ),
            CellMeasurement(
                function="custom_sum",
                source="my_plugin",
                channels=["CH1"],
            ),
        ],
    )


@pytest.fixture
def loaded_funcs() -> dict[str | tuple, Callable]:
    """A dictionary simulating pre-loaded functions."""
    from ..signals.calculate_signals import cell_signal, ring_signal

    def custom_sum(cell, t, ch_data_list, **kwargs):
        return [42.0]

    return {
        "ring_signal": ring_signal,
        "cell_signal": cell_signal,
        ("my_plugin", "custom_sum"): custom_sum,
    }


# --- Tests for cell_signal ---


def test_cell_signal_median(cell_props, mock_dask_array):
    """Verify median calculation within the cell body."""
    result = cell_signal(cell_props, 0, mock_dask_array, statistics="median")
    assert isinstance(result, list)
    assert result[0] == pytest.approx(10.0)


def test_cell_signal_mean(cell_props, mock_dask_array):
    """Verify mean calculation within the cell body."""
    result = cell_signal(cell_props, 0, mock_dask_array, statistics="mean")
    assert result[0] > 11


def test_cell_signal_sum(cell_props, mock_dask_array):
    """Verify sum of pixels within the cell body."""
    expected_sum = (99 * 10.0) + 1000
    result = cell_signal(cell_props, 0, mock_dask_array, statistics="sum")
    assert result[0] == pytest.approx(expected_sum)


def test_cell_signal_unsupported_statistic(cell_props, mock_dask_array):
    """Ensure an unsupported statistic raises a ValueError."""
    with pytest.raises(ValueError, match="Unsupported statistic"):
        cell_signal(cell_props, 0, mock_dask_array, statistics="variance")


# --- Tests for ring_signal ---


def test_ring_signal_mean(cell_props, mock_dask_array):
    """Verify mean calculation in the ring around the cell."""
    # The ring area in the mock data has a constant value of 2.0
    result = ring_signal(
        cell_props, 0, mock_dask_array, ring_width=5, statistics="mean"
    )
    assert isinstance(result, list)
    assert result[0] == pytest.approx(2.0)


def test_ring_signal_at_edge(edge_cell_props, mock_dask_array):
    """Test ring calculation for a cell at the image boundary."""
    result = ring_signal(edge_cell_props, 0, mock_dask_array, ring_width=5)
    assert isinstance(result, list)
    assert result[0] == pytest.approx(1.0)


def test_ring_signal_missing_ring_width(cell_props, mock_dask_array):
    """Ensure a missing ring_width raises a KeyError."""
    with pytest.raises(
        KeyError, match="Missing required keyword argument: 'ring_width'"
    ):
        ring_signal(cell_props, 0, mock_dask_array)


def test_ring_signal_unsupported_statistic(cell_props, mock_dask_array):
    """Ensure an unsupported statistic raises a ValueError."""
    with pytest.raises(ValueError, match="Unsupported statistic"):
        ring_signal(
            cell_props, 0, mock_dask_array, ring_width=5, statistics="mode"
        )


# --- Tests for factory function ---


def test_factory_returns_none_for_no_measurements(basic_config, loaded_funcs):
    """Test that the factory returns None if no measurements are configured."""
    basic_config.cell_measurements = []
    func = create_calculate_signals_function(basic_config, loaded_funcs)
    assert func is None


def test_factory_returns_callable(basic_config, loaded_funcs):
    """Test that the factory returns a callable function with a valid config."""
    func = create_calculate_signals_function(basic_config, loaded_funcs)
    assert callable(func)


def test_factory_end_to_end_calculation(
    basic_config, loaded_funcs, cell_props, mock_dask_array
):
    """
    Test the full workflow: create the function, run it, and check the output.
    """
    calculate_signals = create_calculate_signals_function(
        basic_config, loaded_funcs
    )
    assert callable(calculate_signals)

    result_dict = calculate_signals(cell_props, 0, mock_dask_array)

    assert isinstance(result_dict, dict)
    assert "area" in result_dict
    assert result_dict["area"] == 100
    assert "CH1_ring_signal" in result_dict
    assert result_dict["CH1_ring_signal"] == pytest.approx(2.0)
    assert "CH1_custom_sum" in result_dict
    assert result_dict["CH1_custom_sum"] == 42.0
    assert len(result_dict) == 3
