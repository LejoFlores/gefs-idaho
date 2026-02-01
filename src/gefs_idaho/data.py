"""Data loading and subsetting for GEFS forecast data.

TODO: Investigate accessing raw GRIB2 data directly from AWS S3
--------------------------------------------------------------
The current data source (dynamical.org Zarr store) may have latency issues
between when NOAA NCEP generates forecasts and when they become available.
Direct access to GRIB2 files on AWS could provide:
- Lower latency (real-time access)
- More control over processing pipeline
- Access to additional variables not in Zarr store

Resources:
- NOAA GEFS AWS Registry: https://registry.opendata.aws/noaa-gefs/
- AWS S3 bucket: s3://noaa-gefs-pds/
- Consider using cfgrib + xarray for GRIB2 → xarray conversion
"""

import functools
import logging
import time
from pathlib import Path
from typing import Optional
import xarray as xr

logger = logging.getLogger(__name__)

# Western US bounding box
IDAHO_LAT_MIN = 30.0
IDAHO_LAT_MAX = 50.0
IDAHO_LON_MIN = -125.0
IDAHO_LON_MAX = -100.0

# GEFS data source
GEFS_ZARR_URL = "https://data.dynamical.org/noaa/gefs/forecast-35-day/latest.zarr"

# Cache directory
CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)
LOCAL_IDAHO_ZARR = CACHE_DIR / "idaho_latest.zarr"


def open_gefs_dataset(
    url: str = GEFS_ZARR_URL,
    chunks: Optional[dict] = None,
) -> xr.Dataset:
    """
    Open GEFS forecast dataset from Zarr store with lazy loading.

    Parameters
    ----------
    url : str
        URL to Zarr dataset (default: latest GEFS 35-day forecast)
    chunks : dict, optional
        Dask chunking specification. If None, uses auto chunking.

    Returns
    -------
    xr.Dataset
        Lazily loaded dataset with all forecast variables

    Notes
    -----
    Dataset dimensions typically include:
    - time: forecast initialization time
    - step: forecast lead time
    - ensemble/member: ensemble member number
    - latitude, longitude: spatial coordinates
    """
    if chunks is None:
        chunks = "auto"

    ds = xr.open_zarr(url, chunks=chunks, consolidated=True)
    return ds


def subset_to_idaho(
    ds: xr.Dataset,
    lat_min: float = IDAHO_LAT_MIN,
    lat_max: float = IDAHO_LAT_MAX,
    lon_min: float = IDAHO_LON_MIN,
    lon_max: float = IDAHO_LON_MAX,
) -> xr.Dataset:
    """
    Subset dataset to Western US bounding box.

    Parameters
    ----------
    ds : xr.Dataset
        Input dataset with latitude/longitude coordinates
    lat_min, lat_max : float
        Latitude bounds (degrees North)
    lon_min, lon_max : float
        Longitude bounds (degrees East, -180 to 180 convention)

    Returns
    -------
    xr.Dataset
        Subset dataset covering Western US region (30-50°N, -125 to -100°W)

    Notes
    -----
    Always call this function before any computations to avoid
    loading global data into memory.
    """
    # Handle different possible coordinate names
    lat_name = _find_coord_name(ds, ["latitude", "lat", "y"])
    lon_name = _find_coord_name(ds, ["longitude", "lon", "x"])
    
    # Check if latitude is descending (e.g., 90 to -90)
    lat_coord = ds[lat_name]
    if len(lat_coord) > 1 and lat_coord[0] > lat_coord[-1]:
        # Descending latitude: use reversed slice
        lat_slice = slice(lat_max, lat_min)
    else:
        # Ascending latitude: normal slice
        lat_slice = slice(lat_min, lat_max)

    subset = ds.sel(
        {
            lat_name: lat_slice,
            lon_name: slice(lon_min, lon_max),
        }
    )

    return subset


@functools.lru_cache(maxsize=1)
def _cached_load_idaho_forecast_impl(url: str, chunks_str: str) -> xr.Dataset:
    """
    Internal cached implementation of Idaho forecast loading.
    
    Uses string for chunks to be hashable for lru_cache.
    """
    logger.info("Loading GEFS dataset from remote Zarr (this may take 10-30 seconds)...")
    t0 = time.time()
    
    # Parse chunks back from string
    chunks = None if chunks_str == "None" else eval(chunks_str)
    
    # Open with lazy loading
    ds = open_gefs_dataset(url=url, chunks=chunks)
    t1 = time.time()
    logger.info(f"✓ Dataset opened in {t1-t0:.1f}s")
    
    # Subset immediately to avoid global data access
    logger.info("Subsetting to Idaho bounds...")
    ds_idaho = subset_to_idaho(ds)
    t2 = time.time()
    logger.info(f"✓ Idaho subset created in {t2-t1:.1f}s")
    logger.info(f"  Idaho dimensions: {dict(ds_idaho.sizes)}")
    
    return ds_idaho


def load_idaho_forecast(
    url: str = GEFS_ZARR_URL,
    chunks: Optional[dict] = None,
    cache_local: bool = True,
    force_refresh: bool = False,
) -> xr.Dataset:
    """
    Load GEFS forecast data subset to Idaho with caching.

    Parameters
    ----------
    url : str
        URL to Zarr dataset
    chunks : dict, optional
        Dask chunking specification

    Returns
    -------
    xr.Dataset
        Idaho-subset forecast dataset with lazy loading
        
    Notes
    -----
    Results are cached in memory using functools.lru_cache.
    The first call takes 10-30 seconds to open the remote Zarr dataset.
    Subsequent calls return instantly from cache.

    If cache_local is True, a local Idaho subset Zarr store is used when available.
    Set force_refresh=True to rebuild the local cache from the remote source.

    Examples
    --------
    >>> ds = load_idaho_forecast()
    >>> ds.temperature_2m  # Access without computing
    """
    # Use local cache if available
    if cache_local and LOCAL_IDAHO_ZARR.exists() and not force_refresh:
        try:
            logger.info(f"Loading Idaho subset from local cache: {LOCAL_IDAHO_ZARR}")
            ds_idaho = xr.open_zarr(LOCAL_IDAHO_ZARR, chunks=chunks or "auto", consolidated=True)
        except Exception as e:
            logger.warning(f"Failed to load local cache: {e}. Loading from remote...")
            chunks_str = str(chunks) if chunks is not None else "None"
            ds_idaho = _cached_load_idaho_forecast_impl(url, chunks_str)
            # Try to write new cache
            if cache_local:
                try:
                    logger.info(f"Writing local Idaho cache to: {LOCAL_IDAHO_ZARR}")
                    ds_idaho.to_zarr(
                        LOCAL_IDAHO_ZARR,
                        mode="w",
                        consolidated=True,
                        safe_chunks=False,
                    )
                except Exception as e2:
                    logger.warning(f"Failed to write local cache: {e2}")
    else:
        # Convert chunks to string for hashability
        chunks_str = str(chunks) if chunks is not None else "None"
        ds_idaho = _cached_load_idaho_forecast_impl(url, chunks_str)

        # Write local cache if requested
        if cache_local:
            try:
                logger.info(f"Writing local Idaho cache to: {LOCAL_IDAHO_ZARR}")
                ds_idaho.to_zarr(
                    LOCAL_IDAHO_ZARR,
                    mode="w",
                    consolidated=True,
                    safe_chunks=False,
                )
            except Exception as e:
                logger.warning(f"Failed to write local cache: {e}")
    
    # Filter out lead_time=0 (always NaN for precipitation)
    ds_idaho = filter_initial_lead_time(ds_idaho)
    
    # Validate precipitation data and warn if all NaN
    validate_precipitation_data(ds_idaho)

    return ds_idaho


def filter_initial_lead_time(ds: xr.Dataset) -> xr.Dataset:
    """
    Filter out lead_time=0 which always has NaN precipitation values.
    
    GEFS precipitation is a forecast variable, not an initialization variable.
    The first forecast step (lead_time=0) consistently has no valid data.
    
    Parameters
    ----------
    ds : xr.Dataset
        Dataset with lead_time coordinate
    
    Returns
    -------
    xr.Dataset
        Dataset with lead_time=0 removed
    """
    # Find lead_time coordinate name
    lead_coord = _find_coord_name(ds, ["lead_time", "step", "forecast_time"])
    
    # Skip first lead_time (index 0)
    filtered = ds.isel({lead_coord: slice(1, None)})
    logger.info(f"Filtered out {lead_coord}=0 (always NaN for precipitation)")
    
    return filtered


def validate_precipitation_data(ds: xr.Dataset) -> None:
    """
    Check if precipitation_surface has valid data and log warnings.
    
    Parameters
    ----------
    ds : xr.Dataset
        Dataset to validate
    """
    if "precipitation_surface" not in ds.data_vars:
        return
    
    import numpy as np
    
    # Sample a small slice to check for valid data
    try:
        # Get latest init_time, first few lead_times, first ensemble member
        sample = ds["precipitation_surface"].isel(
            init_time=-1,
            lead_time=slice(0, min(5, len(ds.lead_time))),
            ensemble_member=0
        )
        finite_count = np.isfinite(sample.values).sum()
        total_count = sample.size
        
        if finite_count == 0:
            logger.warning(
                "⚠️  All sampled precipitation values are NaN! "
                "Latest GEFS forecast may not have valid data yet. "
                "This can occur due to data latency between NOAA NCEP and dynamical.org."
            )
        else:
            pct = (finite_count / total_count) * 100
            logger.info(f"✓ Precipitation data validated: {pct:.1f}% valid values in sample")
    except Exception as e:
        logger.debug(f"Could not validate precipitation data: {e}")


def _find_coord_name(ds: xr.Dataset, candidates: list[str]) -> str:
    """
    Find coordinate name from list of candidates.

    Parameters
    ----------
    ds : xr.Dataset
        Dataset to search
    candidates : list of str
        Possible coordinate names in priority order

    Returns
    -------
    str
        First matching coordinate name

    Raises
    ------
    ValueError
        If no matching coordinate found
    """
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name

    raise ValueError(
        f"Could not find coordinate from candidates {candidates}. "
        f"Available: {list(ds.coords.keys())}"
    )
