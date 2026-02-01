"""Diagnose the GEFS data to understand why Idaho subset is empty."""

import sys
sys.path.insert(0, 'src')

import xarray as xr
from gefs_idaho.data import GEFS_ZARR_URL, IDAHO_LAT_MIN, IDAHO_LAT_MAX, IDAHO_LON_MIN, IDAHO_LON_MAX

print("Opening GEFS dataset...")
ds = xr.open_zarr(GEFS_ZARR_URL, chunks="auto", consolidated=True)

print(f"\n📊 Dataset Overview:")
print(f"  Dimensions: {dict(ds.dims)}")
print(f"  Variables: {list(ds.data_vars.keys())[:10]}...")

# Check latitude coordinate
lat_names = [n for n in ['latitude', 'lat', 'y'] if n in ds.coords or n in ds.dims]
if lat_names:
    lat_name = lat_names[0]
    lat_coord = ds[lat_name]
    print(f"\n🌍 Latitude coordinate '{lat_name}':")
    print(f"  Range: {float(lat_coord.min()):.2f} to {float(lat_coord.max()):.2f}")
    print(f"  Size: {len(lat_coord)}")
    print(f"  First 5 values: {lat_coord[:5].values}")
    print(f"  Last 5 values: {lat_coord[-5:].values}")
else:
    print("\n❌ No latitude coordinate found!")

# Check longitude coordinate  
lon_names = [n for n in ['longitude', 'lon', 'x'] if n in ds.coords or n in ds.dims]
if lon_names:
    lon_name = lon_names[0]
    lon_coord = ds[lon_name]
    print(f"\n🌍 Longitude coordinate '{lon_name}':")
    print(f"  Range: {float(lon_coord.min()):.2f} to {float(lon_coord.max()):.2f}")
    print(f"  Size: {len(lon_coord)}")
    print(f"  First 5 values: {lon_coord[:5].values}")
    print(f"  Last 5 values: {lon_coord[-5:].values}")
else:
    print("\n❌ No longitude coordinate found!")

# Idaho bounds
print(f"\n🏔️  Idaho bounds:")
print(f"  Latitude: {IDAHO_LAT_MIN} to {IDAHO_LAT_MAX}°N")
print(f"  Longitude: {IDAHO_LON_MIN} to {IDAHO_LON_MAX}°E")

# Try subset
if lat_names and lon_names:
    print(f"\n🔍 Testing subset with slice(lat_min, lat_max)...")
    try:
        subset1 = ds.sel({lat_name: slice(IDAHO_LAT_MIN, IDAHO_LAT_MAX)})
        print(f"  Result: {len(subset1[lat_name])} latitude points")
    except Exception as e:
        print(f"  Error: {e}")
    
    print(f"\n🔍 Testing with slice(lat_max, lat_min) (reversed)...")
    try:
        subset2 = ds.sel({lat_name: slice(IDAHO_LAT_MAX, IDAHO_LAT_MIN)})
        print(f"  Result: {len(subset2[lat_name])} latitude points")
    except Exception as e:
        print(f"  Error: {e}")
        
    print(f"\n🔍 Finding values in range manually...")
    lat_vals = lat_coord.values
    in_range = (lat_vals >= IDAHO_LAT_MIN) & (lat_vals <= IDAHO_LAT_MAX)
    print(f"  Points in Idaho lat range: {in_range.sum()}")
    if in_range.sum() > 0:
        print(f"  Values: {lat_vals[in_range][:10]}")
