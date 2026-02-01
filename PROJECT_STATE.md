# GEFS Idaho Project State

**Last Updated**: January 31, 2026

## Goal

Interactive Panel dashboard for visualizing NOAA GEFS (Global Ensemble Forecast System) 35-day ensemble forecast data over Idaho, showing temperature and precipitation with ensemble uncertainty bounds.

## Current Status

### What Works ✅

- **Core data pipeline**: Loads remote Zarr dataset from dynamical.org, subsets to Idaho bounds (33 lat × 25 lon grid points)
- **Test suite**: 7/7 tests passing, validating:
  - Idaho spatial subsetting with descending latitude coordinates
  - Precipitation rate→accumulation conversion (3h, 6h timesteps tested)
  - Coordinate name discovery (`time`/`init_time`, `step`/`lead_time`, `ensemble`/`ensemble_member`)
  - Data structure preservation through operations
- **Panel server**: Launches at `http://localhost:5006/app` with reactive controls
- **Verification script**: `verify_app.py` confirms data loads without errors

### What Is Incomplete ⚠️

- **Actual dashboard functionality**: Panel server runs but whether visualizations render with real GEFS data is **unverified in browser**
  - Last manual test showed coordinate axes and selector widgets appearing
  - Map and time series rendering with live data not confirmed working end-to-end
- **Error handling**: Limited user-facing error messages if data unavailable or network issues occur
- **Performance**: Initial load time (~30 seconds for remote Zarr) has no progress indicator
- **Testing coverage**: No integration tests for full dashboard workflow or real data loading

### Recently Fixed 🔧

1. **Descending latitude coordinates** (Jan 31, 2026): GEFS dataset has latitude 90°→-90° (North to South). Fixed `subset_to_idaho()` to detect coordinate direction and reverse slice bounds when descending
2. **Coordinate preservation**: `compute_ensemble_percentiles()` now explicitly preserves spatial coordinates after quantile operations
3. **Lazy loading**: `app.py` defers data loading until first view to prevent import-time network hangs
4. **Error handling**: Added try/except blocks in viz.py for coordinate lookup failures

## Key Design Decisions

### Architecture (Three-Layer Design)

1. **`src/gefs_idaho/data.py`**: Data loading and spatial subsetting
   - Always subset to Idaho bounds **before** any computation
   - Handles flexible coordinate names (`latitude`/`lat`, `longitude`/`lon`)
   - Detects descending vs ascending coordinate ordering
2. **`src/gefs_idaho/derive.py`**: Derived products (valid time, accumulations, ensemble stats)
   - Never hard-codes timestep durations—derives from coordinate differences
   - Computes ensemble percentiles (p10, p50, p90) for uncertainty visualization
3. **`src/gefs_idaho/viz.py`**: Visualization using hvPlot accessor on xarray objects
   - Returns HoloViews objects wrapped in `pn.pane.HoloViews()` for Panel
   - Uses `rasterize=True` for efficient large-grid rendering via Datashader
4. **`app.py`**: Panel dashboard with `param.Parameterized` reactive state management
   - `@param.depends()` decorators trigger plot updates on control changes
   - Data loaded once in `__init__`, cached in `self._ds`

### Data Source

- **URL**: `https://data.dynamical.org/noaa/gefs/forecast-35-day/latest.zarr`
- **Format**: Cloud-optimized Zarr store opened with xarray + Dask (lazy evaluation)
- **Dimensions**: `init_time` (1949), `ensemble_member` (31), `lead_time` (181), `latitude` (721, **descending 90° to -90°**), `longitude` (1440)
- **Variables**: `temperature_2m` (°C), `precipitation_surface` (kg m⁻² s⁻¹ **rate**, not accumulated)

### Lazy Evaluation Throughout

- All xarray/Dask operations remain lazy until visualization
- hvPlot `.hvplot()` accessor handles computation for display
- **Never call `.compute()` before passing to plotting functions**—defeats purpose of lazy evaluation

## Known Pitfalls / Gotchas

### 1. Descending Latitude Coordinates (CRITICAL)

**Problem**: GEFS latitude runs 90° (North Pole) to -90° (South Pole) in descending order. Standard xarray `slice(42, 50)` returns **empty array** for descending coordinates.

**Solution**: Detect coordinate direction and reverse slice bounds:
```python
if lat_coord[0] > lat_coord[-1]:  # Descending
    lat_slice = slice(lat_max, lat_min)  # slice(50, 42)
else:
    lat_slice = slice(lat_min, lat_max)  # slice(42, 50)
```

**Location**: `src/gefs_idaho/data.py::subset_to_idaho()`  
**Test**: `tests/test_derive.py::test_idaho_subset_bounds`

### 2. Precipitation Rate vs Accumulation

**Problem**: `precipitation_surface` is a **rate** (kg m⁻² s⁻¹) averaged since previous forecast step, **not** accumulated precipitation.

**Solution**: Multiply by timestep duration derived from coordinate differences:
```python
accumulation (mm) = rate (mm/s) × timestep_duration (seconds)
```

**Location**: `src/gefs_idaho/derive.py::compute_precipitation_accumulation()`  
**Test**: `tests/test_derive.py::test_precipitation_accumulation_calculation`  
**Critical**: Never hard-code timestep—GEFS intervals may vary

### 3. Coordinate Name Variability

**Problem**: GEFS data uses `init_time`, `lead_time`, `ensemble_member` while test data may use `time`, `step`, `ensemble`.

**Solution**: Use helper functions with priority order:
- `_find_time_coord(ds)`: checks `['init_time', 'time', 't']`
- `_find_step_coord(ds)`: checks `['lead_time', 'step', 'forecast_time']`
- `_find_ensemble_dim(ds)`: checks `['ensemble_member', 'ensemble', 'member']`

**Location**: `src/gefs_idaho/derive.py` (lines 170-232)  
**Test**: `tests/test_derive.py::test_coordinate_name_discovery`

### 4. Coordinate Loss in Quantile Operations

**Problem**: `xr.DataArray.quantile()` can drop non-quantile coordinates (like lat/lon) from output.

**Solution**: Explicitly preserve and reassign coordinates:
```python
preserved_coords = {k: v for k, v in da.coords.items() if ensemble_dim not in v.dims}
# ... perform quantile operation ...
for coord_name, coord_data in preserved_coords.items():
    if coord_name not in ds.coords:
        ds = ds.assign_coords({coord_name: coord_data})
```

**Location**: `src/gefs_idaho/derive.py::compute_ensemble_percentiles()` (lines 135-162)

### 5. Initial Load Time

**Problem**: First data access fetches metadata + data chunks from remote Zarr (~30 seconds).

**Status**: No progress indicator implemented. Dashboard shows "Loading data..." message but no progress bar.

## Next Tasks

### Immediate (Required for Production)

1. **Verify dashboard with real data**: Open browser to `http://localhost:5006/app` and confirm:
   - Map view renders temperature/precipitation over Idaho
   - Time series plot shows data at selected city with uncertainty bands
   - All controls (variable, city, accumulation window, time slider) function correctly
   - No console errors or empty plots

2. **Add progress indicator**: Implement Panel `pn.indicators.Progress` during initial ~30s data load

3. **Improve error messages**: Display user-friendly messages when:
   - Network unavailable (cannot reach dynamical.org)
   - Data format changes (missing expected variables/coordinates)
   - Invalid selections (city outside Idaho bounds)

### Future Enhancements

4. **Integration tests**: Test full dashboard workflow with real GEFS data (slow, requires network)
5. **Caching**: Store Idaho subset locally to avoid repeated remote fetches during development
6. **Extended variables**: Add relative humidity, wind speed from GEFS dataset
7. **Export functionality**: Allow users to download selected data as NetCDF or CSV

## Entry Points

### Running the Dashboard

```bash
# Launch Panel server (opens browser automatically)
panel serve app.py --show

# Or manual URL after starting server
panel serve app.py
# Then navigate to: http://localhost:5006/app
```

**Working Directory**: `/Users/lejoflores/gefs-idaho`  
**Python Environment**: `.venv/bin/python` (Python 3.11.14)

### Quick Verification

```bash
# Check data loading works (no visualization)
python verify_app.py

# Run test suite
pytest -v

# Check code style
black . && ruff check .
```

### Key Modules

- **`app.py`**: Main dashboard application (`GEFSIdahoDashboard` class)
- **`src/gefs_idaho/data.py`**: `load_idaho_forecast()` entry point for data loading
- **`src/gefs_idaho/derive.py`**: `compute_precipitation_accumulation()`, `compute_ensemble_statistics()`
- **`src/gefs_idaho/viz.py`**: `plot_map()`, `plot_time_series()`

## Last Verified Working Commands

```bash
# Install dependencies (development mode)
pip install -e ".[dev]"                                    # ✅ Working (Jan 31, 2026)

# Run test suite
pytest -v                                                   # ✅ 7/7 passed (Jan 31, 2026)

# Verify data loading
python verify_app.py                                       # ✅ All checks passed (Jan 31, 2026)
# Output: Dimensions: {'latitude': 33, 'longitude': 25, ...}

# Launch Panel server
panel serve app.py --show                                  # ✅ Server starts (Jan 31, 2026)
# Output: Bokeh app running at: http://localhost:5006/app
# Browser rendering status: UNVERIFIED

# Format and lint
black . && ruff check .                                    # ⚠️ Not recently verified
```

## Uncertain / Not Yet Verified

- **Dashboard rendering**: Panel server runs but end-to-end visualization with real GEFS data **not confirmed working in browser**. Last agent-reported test showed widgets appearing but data rendering uncertain.
- **Performance at scale**: How dashboard handles large accumulation windows (7-day) or slow network connections is untested
- **Browser compatibility**: Only tested on default macOS browser (likely Safari or Chrome)
- **Data freshness**: GEFS "latest" forecast updates every 6 hours—dashboard has no refresh mechanism

## Development Environment

- **OS**: macOS
- **Python**: 3.11.14 (virtual environment at `.venv/`)
- **Key Dependencies**: Panel 1.x, xarray, Dask, hvPlot, HoloViews, Datashader, Zarr
- **Project Root**: `/Users/lejoflores/gefs-idaho`

---

**Note to Future Contributors**: This file reflects the state as of Jan 31, 2026. Recent fixes resolved critical data loading bugs (descending coordinates, coordinate preservation). Dashboard **should** work but browser rendering not manually confirmed. Start by verifying visualizations render correctly at `http://localhost:5006/app` before making further changes.
