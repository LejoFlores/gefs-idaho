"""Data loading and subsetting for GEFS forecast data."""

import functools
import logging
import time
from pathlib import Path
from typing import Optional
import xarray as xr

logger = logging.getLogger(__name__)

# Idaho bounding box
IDAHO_LAT_MIN = 42.0
IDAHO_LAT_MAX = 50.0
IDAHO_LON_MIN = -117.0
IDAHO_LON_MAX = -111.0

# GEFS data source
GEFS_ZARR_URL = "https://data.dynamical.org/noaa/gefs/forecast-35-day/latest.zarr"

# Cache directory
CACHE_DIR = Path("./cache")
CACHE_DIR.mkdir(exist_ok=True)


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
    Subset dataset to Idaho bounding box.

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
        Subset dataset covering Idaho region

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
    logger.info(f"  Idaho dimensions: {dict(ds_idaho.dims)}")
    
    return ds_idaho


def load_idaho_forecast(
    url: str = GEFS_ZARR_URL,
    chunks: Optional[dict] = None,
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

    Examples
    --------
    >>> ds = load_idaho_forecast()
    >>> ds.temperature_2m  # Access without computing
    """
    # Convert chunks to string for hashability
    chunks_str = str(chunks) if chunks is not None else "None"
    return _cached_load_idaho_forecast_impl(url, chunks_str)


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
