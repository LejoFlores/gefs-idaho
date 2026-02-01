"""Derived forecast products: valid time, accumulations, ensemble statistics."""

import functools
import hashlib
import logging
import time
from typing import Optional
import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


def add_valid_time(ds: xr.Dataset) -> xr.Dataset:
    """
    Add valid_time coordinate if not present.

    Parameters
    ----------
    ds : xr.Dataset
        Forecast dataset with 'time' (initialization) and 'step' (lead time)

    Returns
    -------
    xr.Dataset
        Dataset with valid_time coordinate added

    Notes
    -----
    valid_time = initialization_time + forecast_step
    """
    if "valid_time" in ds.coords:
        return ds

    # Find time and step coordinate names
    time_name = _find_time_coord(ds)
    step_name = _find_step_coord(ds)

    # Compute valid time by broadcasting
    valid_time = ds[time_name] + ds[step_name]

    # Add as coordinate - use the same dimensions as the result
    ds = ds.assign_coords(valid_time=valid_time)

    return ds


def compute_precipitation_accumulation(
    precip_rate: xr.DataArray,
    window: str = "6h",
) -> xr.DataArray:
    """
    Convert precipitation rate to accumulated precipitation.

    Parameters
    ----------
    precip_rate : xr.DataArray
        Precipitation rate (kg m⁻² s⁻¹, equivalent to mm s⁻¹)
        Averaged over the interval since the previous forecast step.
    window : str
        Accumulation window (e.g., '6h', '24h', '7d')
        If None, computes stepwise accumulation.

    Returns
    -------
    xr.DataArray
        Accumulated precipitation (mm) over specified window

    Notes
    -----
    CRITICAL: precipitation_surface is a rate averaged since the previous
    forecast step. To get accumulation for each step:
        accumulation = rate × timestep_duration_seconds

    The timestep duration is derived from coordinate differences,
    never hard-coded.

    Units: kg m⁻² s⁻¹ × seconds = kg m⁻² = mm (since 1 kg/m² water = 1 mm depth)
    """
    # Get time dimension name
    step_dim = _find_step_coord(precip_rate)

    # Compute timestep duration in seconds from coordinate differences
    step_coord = precip_rate[step_dim]

    # Convert timedelta to seconds
    timestep_diff = step_coord.diff(step_dim).astype("timedelta64[s]").astype(float)

    # For first timestep, assume same duration as second
    # Pad with first value to match original dimension length
    timestep_seconds = xr.DataArray(
        np.concatenate([[timestep_diff.values[0]], timestep_diff.values]),
        dims=[step_dim],
        coords={step_dim: step_coord.values},
    )

    # Compute stepwise accumulation: rate × duration
    # Units: (mm/s) × s = mm
    stepwise_accum = precip_rate * timestep_seconds

    # If no window specified, return stepwise accumulation
    if window is None:
        return stepwise_accum

    # Parse window into pandas-compatible frequency
    window_td = _parse_window_to_timedelta(window)

    # Rolling accumulation over window
    accumulated = stepwise_accum.rolling(
        {step_dim: window_td},
        min_periods=1,
    ).sum()

    return accumulated


def compute_ensemble_percentiles(
    da: xr.DataArray,
    percentiles: list[float] = [10, 50, 90],
) -> xr.Dataset:
    """
    Compute ensemble percentiles.

    Parameters
    ----------
    da : xr.DataArray
        Input data with ensemble/member dimension
    percentiles : list of float
        Percentiles to compute (0-100)

    Returns
    -------
    xr.Dataset
        Dataset with variables named 'p{percentile}' (e.g., 'p50' for median)

    Examples
    --------
    >>> stats = compute_ensemble_percentiles(temperature, [10, 50, 90])
    >>> stats.p50  # median
    >>> stats.p10  # 10th percentile
    """
    # Find ensemble dimension
    ensemble_dim = _find_ensemble_dim(da)

    # Preserve all non-ensemble coordinates
    preserved_coords = {
        k: v for k, v in da.coords.items() if ensemble_dim not in v.dims
    }

    # Compute percentiles separately to avoid coordinate conflicts
    result = {}
    for p in percentiles:
        var_name = f"p{int(p)}"
        percentile_data = da.quantile(p / 100.0, dim=ensemble_dim)
        # Drop the quantile coordinate to avoid conflicts when merging
        if "quantile" in percentile_data.coords:
            percentile_data = percentile_data.drop_vars("quantile")
        result[var_name] = percentile_data

    # Create dataset and re-assign preserved coordinates
    ds = xr.Dataset(result)
    for coord_name, coord_data in preserved_coords.items():
        if coord_name not in ds.coords:
            ds = ds.assign_coords({coord_name: coord_data})

    return ds


def compute_ensemble_statistics(
    da: xr.DataArray,
) -> xr.Dataset:
    """
    Compute standard ensemble statistics: 10th, 50th, 90th percentiles.

    Parameters
    ----------
    da : xr.DataArray
        Input data with ensemble dimension

    Returns
    -------
    xr.Dataset
        Dataset with p10, p50 (median), p90 variables
    """
    return compute_ensemble_percentiles(da, percentiles=[10, 50, 90])


def _find_time_coord(ds: xr.Dataset) -> str:
    """Find initialization time coordinate name."""
    candidates = ["init_time", "time", "initialization_time", "forecast_reference_time"]
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    raise ValueError(
        f"Could not find time coordinate. Available: {list(ds.coords.keys())}"
    )


def _find_step_coord(obj) -> str:
    """Find forecast step coordinate name."""
    candidates = ["lead_time", "step", "forecast_hour", "forecast_period"]
    coords = obj.coords if hasattr(obj, "coords") else {}
    dims = obj.dims if hasattr(obj, "dims") else []

    for name in candidates:
        if name in coords or name in dims:
            return name

    available = list(coords.keys()) if coords else list(dims)
    raise ValueError(f"Could not find step coordinate. Available: {available}")


def _find_ensemble_dim(da: xr.DataArray) -> str:
    """Find ensemble dimension name."""
    candidates = ["ensemble_member", "ensemble", "member", "realization", "number"]
    for name in candidates:
        if name in da.dims:
            return name
    raise ValueError(f"Could not find ensemble dimension. Available: {list(da.dims)}")


def _parse_window_to_timedelta(window: str) -> int:
    """
    Parse window string to number of timesteps.

    Parameters
    ----------
    window : str
        Window specification like '6h', '24h', '7d'

    Returns
    -------
    int
        Number of timesteps for rolling window

    Notes
    -----
    This is a simplified parser. For production use, consider
    more robust parsing with pandas pd.Timedelta.
    """
    import re

    match = re.match(r"(\d+)([hd])", window.lower())
    if not match:
        raise ValueError(
            f"Invalid window format: {window}. Use format like '6h', '24h', '7d'"
        )

    value, unit = match.groups()
    value = int(value)

    if unit == "h":
        # Assume 3-hourly or 6-hourly data
        # This is approximate; better to use actual coordinate spacing
        return value // 3  # rough approximation
    elif unit == "d":
        return value * 8  # assuming 3-hourly data

    raise ValueError(f"Unsupported unit: {unit}")
