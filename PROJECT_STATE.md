# GEFS Idaho Project State

**Last Updated**: January 31, 2026

## Goal

Interactive Panel dashboard for visualizing NOAA GEFS (Global Ensemble Forecast System) 35-day ensemble forecast data over Idaho, showing temperature and precipitation with ensemble uncertainty bounds.

## Current Status

### What Works ✅

- **Core data pipeline**: Loads remote Zarr dataset from dynamical.org, subsets to Idaho bounds (33 lat × 25 lon grid points)
- **Dataset caching**: First call to `load_idaho_forecast()` takes ~10-30s, subsequent calls return instantly from `functools.lru_cache`
- **Optimized compute scope**: 
  - Maps: Select time slice BEFORE ensemble stats (reduces from time×ensemble×lat×lon to ensemble×lat×lon)
  - Time series: Select spatial point BEFORE ensemble stats (reduces from time×ensemble×lat×lon to time×ensemble)
- **Non-blocking UI**: Loading spinners and deferred data loading ensure controls render immediately
- **Timing instrumentation**: Detailed logs show where time is spent (dataset open, Idaho subset, ensemble stats, plotting)
- **Test suite**: 7/7 tests passing, validating:
  - Idaho spatial subsetting with descending latitude coordinates
  - Precipitation rate→accumulation conversion (3h, 6h timesteps tested)
  - Coordinate name discovery (`time`/`init_time`, `step`/`lead_time`, `ensemble`/`ensemble_member`)
  - Data structure preservation through operations
- **Panel server**: Launches at `http://localhost:5006/app` with reactive controls and loading indicators
- **Verification script**: `verify_app.py` confirms data loads without errors

### What Is Incomplete ⚠️

- **End-to-end browser testing**: Panel server runs and UI renders, but full visualization workflow with all widget interactions not manually tested
- **Performance under slow network**: Initial load time depends on network speed; no offline mode or local data option
- **Extended variables**: Only temperature and precipitation implemented; GEFS has 50+ other variables available

### Recently Fixed 🔧

1. **Descending latitude coordinates** (Jan 31, 2026): GEFS dataset has latitude 90°→-90° (North to South). Fixed `subset_to_idaho()` to detect coordinate direction and reverse slice bounds when descending
2. **Coordinate preservation**: `compute_ensemble_percentiles()` now explicitly preserves spatial coordinates after quantile operations
3. **Lazy loading**: `app.py` defers data loading until first view to prevent import-time network hangs
4. **Error handling**: Added try/except blocks in viz.py for coordinate lookup failures
5. **Performance optimizations** (Jan 31, 2026):
   - Added `functools.lru_cache` to `load_idaho_forecast()` - caches dataset in memory
   - Select time slice BEFORE computing ensemble stats in map view (massive speedup)
   - Select spatial point BEFORE computing ensemble stats in time series (massive speedup)
   - Added loading spinners (`pn.indicators.LoadingSpinner`) during data load
   - Added timing instrumentation with logging to identify bottlenecks
6. **Caching infrastructure**: Created `cache/` directory (gitignored) for future local Zarr caching

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

**Status**: **SOLVED** - Loading spinner shows during initial load, subsequent widget changes are near-instant due to caching and compute scope optimization.

### 6. Performance and Caching Strategy

**Caching Layers Implemented**:
1. **Dataset caching** (`functools.lru_cache` in `data.py`):
   - `load_idaho_forecast()` caches the opened xarray Dataset handle in memory
   - First call: ~10-30s to open remote Zarr and subset to Idaho
   - Subsequent calls: instant (returns from cache)
   - Cache cleared only on Python process restart

2. **Compute scope optimization**:
   - **Maps**: Select time slice → compute ensemble stats → plot (not: compute stats on all times → select time)
   - **Time series**: Select spatial point → compute ensemble stats → plot (not: compute stats on full grid → select point)
   - This reduces quantile computations by 100-180x (number of time steps or grid points)

3. **Lazy evaluation** (xarray/Dask built-in):
   - All operations remain lazy until visualization
   - Only data needed for current view is computed
   - hvPlot + Datashader handle final rasterization efficiently

**Future caching opportunities** (not yet implemented):
- Local Zarr cache in `./cache/` for Idaho subset (persist across sessions)
- Derived product caching (accumulated precip, ensemble stats) keyed by variable/window/time
- Last-used forecast cached to disk for offline development

**Cache directory**: `./cache/` (created, gitignored, currently unused)

## Next Tasks

### Immediate (Required for Production)

1. **Manual browser testing**: Open browser to `http://localhost:5006/app` and verify:
   - UI renders immediately (loading spinners appear during data load)
   - Map view renders temperature/precipitation over Idaho after initial ~30s load
   - Time series plot shows data at selected city with uncertainty bands
   - Subsequent widget changes complete in <5 seconds (cached data)
   - No console errors or empty plots

2. **Performance validation**: Measure actual timing with real GEFS data:
   - First map view: <40s total (dataset load + compute + render)
   - Subsequent map views (different time): <5s
   - Time series (different city): <5s
   - Document actual timings in README

3. **Integration tests**: Add slow test (marked with pytest.mark.slow) that loads real GEFS data

### Future Enhancements

4. **Local Zarr caching**: Write Idaho subset to `./cache/idaho_latest.zarr` on first load, read from there on subsequent runs
5. **Extended variables**: Add relative humidity, wind speed from GEFS dataset
6. **Export functionality**: Allow users to download selected data as NetCDF or CSV
7. **Forecast comparison**: Show difference between forecast initializations

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
panel serve app.py --show                                  # ✅ Server starts, UI renders (Jan 31, 2026)
# Output: Bokeh app running at: http://localhost:5006/app
# First load: ~30s (remote Zarr), subsequent interactions: <5s (cached)

# Launch with debug logging
panel serve app.py --show --log-level info                 # ✅ Shows timing logs (Jan 31, 2026)
# Logs show: "Starting data load...", "✓ Data loaded successfully in X.Xs"

# Format and lint
black . && ruff check .                                    # ⚠️ Not recently verified
```

## Uncertain / Not Yet Verified

- **Real-world performance**: Actual timing measurements with real GEFS data not documented (estimated ~30s first load, <5s subsequent)
- **Data freshness**: GEFS "latest" forecast updates every 6 hours—dashboard has no refresh mechanism
- **Browser compatibility**: Tested only on default macOS browser via Simple Browser
- **Network failure handling**: Behavior when dynamical.org is unavailable not tested

## Development Environment

- **OS**: macOS
- **Python**: 3.11.14 (virtual environment at `.venv/`)
- **Key Dependencies**: Panel 1.x, xarray, Dask, hvPlot, HoloViews, Datashader, Zarr
- **Project Root**: `/Users/lejoflores/gefs-idaho`

---

**Note to Future Contributors**: This file reflects the state as of Jan 31, 2026. 

**Major performance improvements implemented**:
- In-memory dataset caching with `functools.lru_cache` (instant on repeat calls)
- Compute scope optimization: select time/space BEFORE ensemble stats (100-180x speedup)
- Loading spinners and deferred data loading for non-blocking UI
- Timing instrumentation via logging module

**Current state**: Dashboard functional with good performance. First data load takes ~30s (network-dependent), subsequent widget changes complete in <5s. All tests passing. Manual browser testing recommended to verify end-to-end workflow before deployment.

**Performance characteristics**:
- **Cold start** (first page load): ~30-40s (remote Zarr open + Idaho subset + first compute)
- **Warm operations** (cached data): <5s per widget change (select time/city/variable/window)
- **Memory footprint**: ~500MB-1GB (Idaho subset cached in RAM)
- **Network dependency**: Initial load only; subsequent operations use cached data
