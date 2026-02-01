"""Cache a specific init_time with valid precipitation data for testing."""
import sys
sys.path.insert(0, 'src')

import xarray as xr
import logging
from pathlib import Path

from gefs_idaho.data import (
    GEFS_ZARR_URL, 
    subset_to_idaho, 
    filter_initial_lead_time,
    validate_precipitation_data,
    CACHE_DIR,
    LOCAL_IDAHO_ZARR
)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Init time from working notebook
VALID_INIT_TIME = '2025-12-20T00'

def cache_specific_init_time(init_time: str):
    """Load and cache a specific init_time from remote GEFS data."""
    logger.info(f"Loading GEFS data for init_time={init_time}...")
    
    # Open remote dataset
    ds = xr.open_zarr(GEFS_ZARR_URL, chunks="auto", consolidated=True, decode_timedelta=True)
    logger.info(f"✓ Remote dataset opened")
    
    # Select specific init_time
    ds_single = ds.sel(init_time=init_time)
    logger.info(f"✓ Selected init_time: {init_time}")
    
    # Subset to Western US
    ds_idaho = subset_to_idaho(ds_single)
    logger.info(f"✓ Subset to Western US: {dict(ds_idaho.sizes)}")
    
    # Filter out lead_time=0
    ds_idaho = filter_initial_lead_time(ds_idaho)
    logger.info(f"✓ Filtered lead_time=0: {len(ds_idaho.lead_time)} lead_times remaining")
    
    # Validate precipitation
    validate_precipitation_data(ds_idaho)
    
    # Compute data to avoid chunking conflicts with Zarr v3
    logger.info("Computing data (this will take a moment)...")
    ds_idaho = ds_idaho.compute()
    logger.info("✓ Data computed")
    
    # Drop zarr v3 encoding to allow v2 write
    for var in ds_idaho.data_vars:
        ds_idaho[var].encoding = {}
    for coord in ds_idaho.coords:
        ds_idaho[coord].encoding = {}
    logger.info("✓ Encoding cleared for Zarr v2 compatibility")
    
    # Write to cache
    CACHE_DIR.mkdir(exist_ok=True)
    logger.info(f"Writing to cache: {LOCAL_IDAHO_ZARR}")
    ds_idaho.to_zarr(
        LOCAL_IDAHO_ZARR,
        mode='w',
        consolidated=True,
        zarr_format=2,  # Use Zarr v2 format for compatibility
    )
    logger.info(f"✓ Cache written successfully")
    
    # Verify cache
    logger.info("Verifying cached data...")
    ds_cached = xr.open_zarr(LOCAL_IDAHO_ZARR, consolidated=True)
    logger.info(f"  Cached dimensions: {dict(ds_cached.sizes)}")
    logger.info(f"  Init time: {ds_cached.init_time.values}")
    logger.info(f"  Lead time range: {ds_cached.lead_time.min().values} to {ds_cached.lead_time.max().values}")
    
    # Check precipitation
    import numpy as np
    precip_sample = ds_cached['precipitation_surface'].isel(lead_time=0, ensemble_member=0).values
    finite = np.isfinite(precip_sample).sum()
    logger.info(f"  Precipitation sample: {finite}/{precip_sample.size} finite values")
    
    if finite > 0:
        logger.info(f"✅ SUCCESS! Cache has valid precipitation data")
    else:
        logger.warning(f"⚠️  Cache still has all-NaN precipitation")
    
    return ds_cached

if __name__ == '__main__':
    print(f"\n{'='*60}")
    print(f"Caching GEFS data with valid precipitation")
    print(f"Init time: {VALID_INIT_TIME}")
    print(f"{'='*60}\n")
    
    ds = cache_specific_init_time(VALID_INIT_TIME)
    
    print(f"\n{'='*60}")
    print(f"Cache ready for testing!")
    print(f"Restart Panel server: panel serve app.py --show")
    print(f"{'='*60}\n")
