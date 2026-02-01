"""Tests for GEFS Idaho forecast processing."""

import numpy as np
import pytest
import xarray as xr

from gefs_idaho.data import (
    subset_to_idaho,
    IDAHO_LAT_MIN,
    IDAHO_LAT_MAX,
    IDAHO_LON_MIN,
    IDAHO_LON_MAX,
)
from gefs_idaho.derive import (
    compute_precipitation_accumulation,
    add_valid_time,
    _find_time_coord,
    _find_step_coord,
    _find_ensemble_dim,
)


def create_test_dataset():
    """Create synthetic test dataset mimicking GEFS structure."""
    # Create coordinates
    time = np.array(["2026-01-31T00:00"], dtype="datetime64[ns]")
    step = np.array([3, 6, 9, 12], dtype="timedelta64[h]")  # 3-hourly steps
    ensemble = np.arange(3)
    lat = np.linspace(40, 52, 25)
    lon = np.linspace(-120, -110, 21)

    # Create test data
    shape = (len(time), len(step), len(ensemble), len(lat), len(lon))

    # Temperature: random values around 0-20°C
    temperature = 10 + 5 * np.random.randn(*shape)

    # Precipitation rate: constant 0.1 mm/s (test value)
    precipitation_rate = 0.1 * np.ones(shape)

    # Create dataset
    ds = xr.Dataset(
        {
            "temperature_2m": (
                ["time", "step", "ensemble", "latitude", "longitude"],
                temperature,
                {"units": "°C"},
            ),
            "precipitation_surface": (
                ["time", "step", "ensemble", "latitude", "longitude"],
                precipitation_rate,
                {"units": "kg m-2 s-1"},
            ),
        },
        coords={
            "time": time,
            "step": step,
            "ensemble": ensemble,
            "latitude": lat,
            "longitude": lon,
        },
    )

    return ds


def test_idaho_subset_bounds():
    """Test that Idaho subset respects latitude/longitude bounds."""
    ds = create_test_dataset()

    # Subset to Idaho
    ds_idaho = subset_to_idaho(ds)

    # Check latitude bounds
    assert ds_idaho.latitude.min() >= IDAHO_LAT_MIN
    assert ds_idaho.latitude.max() <= IDAHO_LAT_MAX

    # Check longitude bounds
    assert ds_idaho.longitude.min() >= IDAHO_LON_MIN
    assert ds_idaho.longitude.max() <= IDAHO_LON_MAX


def test_precipitation_accumulation_positive():
    """Test that accumulated precipitation is non-negative."""
    ds = create_test_dataset()

    # Get precipitation rate
    precip_rate = ds.precipitation_surface.isel(time=0, ensemble=0)

    # Compute accumulation
    accumulated = compute_precipitation_accumulation(precip_rate, window=None)

    # Check all values are non-negative
    assert (
        (accumulated >= 0).all().values
    ), "Accumulated precipitation must be non-negative"


def test_precipitation_accumulation_calculation():
    """
    Test that precipitation accumulation correctly computes rate × timestep.

    Given: constant precipitation rate of 0.1 mm/s
    Expected: over 3-hour period (10800 seconds), accumulation = 0.1 × 10800 = 1080 mm
    """
    ds = create_test_dataset()

    # Get precipitation rate (constant 0.1 mm/s in test data)
    precip_rate = ds.precipitation_surface.isel(time=0, ensemble=0)

    # Compute stepwise accumulation (no window)
    accumulated = compute_precipitation_accumulation(precip_rate, window=None)

    # Expected: 0.1 mm/s × 10800 s = 1080 mm per 3-hour step
    expected_accumulation = 0.1 * 3 * 3600  # 0.1 mm/s × 3 hours × 3600 s/hour

    # Check that accumulation is approximately correct (within 1% tolerance)
    # Using mean to account for any edge effects in implementation
    actual_mean = float(accumulated.mean().values)

    np.testing.assert_allclose(
        actual_mean,
        expected_accumulation,
        rtol=0.01,
        err_msg=f"Expected accumulation ~{expected_accumulation} mm, got {actual_mean} mm",
    )


def test_precipitation_rate_to_accumulation_units():
    """
    Test the unit conversion from precipitation rate to accumulation.

    Verifies: (kg m⁻² s⁻¹) × seconds = kg m⁻² = mm
    """
    # Create simple test case
    time = np.array(["2026-01-31T00:00"], dtype="datetime64[ns]")
    step = np.array([1, 2, 3], dtype="timedelta64[h]")  # 1-hour steps

    # Constant rate: 1 kg m⁻² s⁻¹ (= 1 mm/s)
    rate_data = np.ones((len(time), len(step), 5, 5))

    precip_rate = xr.DataArray(
        rate_data,
        dims=["time", "step", "lat", "lon"],
        coords={"time": time, "step": step},
    )

    # Compute accumulation
    accumulated = compute_precipitation_accumulation(precip_rate, window=None)

    # Expected: 1 mm/s × 3600 s = 3600 mm per hour
    expected = 3600.0

    # Check (with tolerance for numerical precision)
    np.testing.assert_allclose(
        accumulated.mean().values,
        expected,
        rtol=0.01,
    )


def test_subset_preserves_data_structure():
    """Test that subsetting preserves all dimensions and variables."""
    ds = create_test_dataset()

    ds_idaho = subset_to_idaho(ds)

    # Check that all variables are preserved
    assert "temperature_2m" in ds_idaho
    assert "precipitation_surface" in ds_idaho

    # Check that non-spatial dimensions are unchanged
    assert len(ds_idaho.time) == len(ds.time)
    assert len(ds_idaho.step) == len(ds.step)
    assert len(ds_idaho.ensemble) == len(ds.ensemble)


def test_coordinate_name_discovery():
    """Test that helper functions find coordinates with various naming conventions."""
    # Test with GEFS-style names (lead_time, init_time, ensemble_member)
    time = np.array(["2026-01-31T00:00"], dtype="datetime64[ns]")
    lead_time = np.array([3, 6, 9], dtype="timedelta64[h]")
    ensemble_member = np.arange(5)
    lat = np.linspace(42, 49, 10)
    lon = np.linspace(-117, -111, 10)

    ds_gefs = xr.Dataset(
        {
            "temperature_2m": (
                ["init_time", "lead_time", "ensemble_member", "latitude", "longitude"],
                np.random.randn(1, 3, 5, 10, 10),
            ),
        },
        coords={
            "init_time": time,
            "lead_time": lead_time,
            "ensemble_member": ensemble_member,
            "latitude": lat,
            "longitude": lon,
        },
    )

    # Test coordinate finding with GEFS names
    assert _find_time_coord(ds_gefs) == "init_time"
    assert _find_step_coord(ds_gefs) == "lead_time"
    assert _find_ensemble_dim(ds_gefs.temperature_2m) == "ensemble_member"

    # Test with generic names (time, step, ensemble)
    ds_generic = create_test_dataset()
    assert (
        _find_time_coord(ds_generic) == "time"
        or _find_time_coord(ds_generic) == "init_time"
    )
    assert _find_step_coord(ds_generic) in ["step", "lead_time"]
    assert _find_ensemble_dim(ds_generic.temperature_2m) in [
        "ensemble",
        "ensemble_member",
    ]


def test_add_valid_time_with_gefs_coordinates():
    """Test that add_valid_time works with GEFS coordinate names."""
    time = np.array(["2026-01-31T00:00"], dtype="datetime64[ns]")
    lead_time = np.array([3, 6, 9], dtype="timedelta64[h]")

    ds = xr.Dataset(
        {
            "temperature_2m": (
                ["init_time", "lead_time"],
                np.random.randn(1, 3),
            ),
        },
        coords={
            "init_time": time,
            "lead_time": lead_time,
        },
    )

    # Add valid_time coordinate
    ds_with_vt = add_valid_time(ds)

    # Check that valid_time was added
    assert "valid_time" in ds_with_vt.coords

    # Verify valid_time calculation is correct
    expected_vt = time[0] + lead_time
    np.testing.assert_array_equal(ds_with_vt.valid_time.values.flatten(), expected_vt)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
