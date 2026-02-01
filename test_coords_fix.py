"""Verify coordinate preservation fix works."""

import sys

sys.path.insert(0, "src")

import numpy as np
import xarray as xr
from gefs_idaho.derive import compute_ensemble_statistics

# Create test dataset with spatial coords
time = np.array(["2026-01-31T00:00"], dtype="datetime64[ns]")
step = np.array([3, 6, 9], dtype="timedelta64[h]")
ensemble = np.arange(5)
lat = np.linspace(42, 49, 10)
lon = np.linspace(-117, -111, 8)

data = np.random.randn(1, 3, 5, 10, 8)
da = xr.DataArray(
    data,
    dims=["time", "step", "ensemble", "latitude", "longitude"],
    coords={
        "time": time,
        "step": step,
        "ensemble": ensemble,
        "latitude": lat,
        "longitude": lon,
    },
)

print("Input DataArray:")
print(f"  Coordinates: {list(da.coords.keys())}")
print(f"  Dims: {da.dims}")

# Compute ensemble statistics
stats = compute_ensemble_statistics(da)

print("\nOutput Dataset after compute_ensemble_statistics:")
print(f"  Coordinates: {list(stats.coords.keys())}")
print(f"  Variables: {list(stats.data_vars.keys())}")

# Check that spatial coords are preserved
has_lat = "latitude" in stats.coords
has_lon = "longitude" in stats.coords
has_p50 = "p50" in stats.data_vars

print(f"\n✓ Latitude preserved: {has_lat}")
print(f"✓ Longitude preserved: {has_lon}")
print(f"✓ Percentiles computed: {has_p50}")

if has_lat and has_lon and has_p50:
    print("\n✅ Coordinate preservation fix is working!")

    # Try selecting a point
    try:
        point = stats.sel(latitude=45.0, longitude=-114.0, method="nearest")
        print(f"✅ Can select point successfully")
        print(f"   Selected lat: {float(point.latitude):.2f}")
        print(f"   Selected lon: {float(point.longitude):.2f}")
        print(f"   p50 shape: {point.p50.shape}")
    except Exception as e:
        print(f"❌ Error selecting point: {e}")
else:
    print("\n❌ Coordinate preservation failed")
    sys.exit(1)
