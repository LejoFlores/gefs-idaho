# GEFS Idaho Forecast Visualization

**🎯 MVP Milestone Achieved (Jan 31, 2026)** — Interactive dashboard with maps, time series, and ensemble uncertainty for Western US temperature and precipitation forecasts.

Interactive Panel dashboard for visualizing NOAA GEFS (Global Ensemble Forecast System) 35-day forecast data over the Western US.

## Overview

This application provides:
- **Interactive maps** showing ensemble median temperature or accumulated precipitation
- **Time series plots** at selected Idaho cities with ensemble uncertainty (10-90% range)
- **Flexible controls** for variable, time, location, and precipitation accumulation windows

## Quick Start

```bash
# Install package and dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Launch dashboard
panel serve app.py --show
```

The dashboard will open in your browser at `http://localhost:5006/app`.

## Data Source

- **Dataset**: NOAA GEFS 35-day forecast from dynamical.org
- **URL**: `https://data.dynamical.org/noaa/gefs/forecast-35-day/latest.zarr`
- **Format**: Zarr store, opened with xarray using Dask for lazy evaluation
- **Spatial subset**: Idaho bounding box (lat 42–50°N, lon 117–111°W)

### Variables

1. **temperature_2m** (°C)
   - 2-meter air temperature
   - Direct ensemble forecast values

2. **precipitation_surface** (kg m⁻² s⁻¹)
   - Precipitation rate averaged since previous forecast step
   - **Converted to accumulated precipitation (mm)** for visualization

## Key Assumptions and Design Decisions

### Precipitation Rate to Accumulation Conversion

**CRITICAL**: The `precipitation_surface` variable is a **rate** (kg m⁻² s⁻¹, equivalent to mm s⁻¹) averaged over the interval since the previous forecast step. To obtain accumulated precipitation:

```
Accumulation (mm) = Rate (mm/s) × Timestep Duration (seconds)
```

**Implementation details**:
- Timestep duration is **derived from coordinate differences**, never hard-coded
- This accounts for potentially irregular forecast output intervals
- Units: kg m⁻² = mm (1 kg of water per m² = 1 mm depth)

See `src/gefs_idaho/derive.py::compute_precipitation_accumulation()` for implementation.

### Spatial Subsetting

All data loading immediately subsets to Idaho bounds **before any computation** to avoid loading global datasets into memory. Coordinates:

- Latitude: 42.0 to 50.0°N
- Longitude: -117.0 to -111.0°W (using -180 to 180 convention)

### Ensemble Statistics

Forecast uncertainty is represented using ensemble percentiles:
- **p10**: 10th percentile (lower bound)
- **p50**: 50th percentile (median, primary forecast)
- **p90**: 90th percentile (upper bound)

Maps display the median (p50), while time series show median with shaded 10-90% range.

### Lazy Evaluation

The application uses **Dask** throughout to:
- Avoid loading the full global dataset
- Enable interactive exploration without memory constraints
- Compute only what's needed for visualization

All computations are lazy until explicitly needed for display.

## Project Structure

```
gefs-idaho/
├── src/gefs_idaho/
│   ├── __init__.py
│   ├── data.py          # Data loading and spatial subsetting
│   ├── derive.py        # Derived products (accumulation, statistics)
│   └── viz.py           # Visualization helpers (hvPlot)
├── app.py               # Panel dashboard application
├── tests/
│   └── test_derive.py   # Unit tests for scientific computations
├── pyproject.toml       # Package configuration
└── README.md           # This file
```

### Module Responsibilities

- **data.py**: Opens Zarr dataset, implements spatial subsetting, provides caching-friendly chunking
- **derive.py**: Computes valid_time, converts precipitation rate to accumulation, calculates ensemble statistics
- **viz.py**: hvPlot wrappers for maps and time series, city location helpers
- **app.py**: Panel layout with reactive components and controls

## Dashboard Features

### Controls

- **Variable**: Temperature or precipitation
- **City**: Boise, Twin Falls, Idaho Falls, or Coeur d'Alene
- **Accumulation Window**: 6-hour, 24-hour, or 7-day (for precipitation only)
- **Valid Time**: Slider to select forecast valid time

### Map View

- Geographic map with Idaho bounds
- Displays ensemble median (p50)
- Uses Datashader for efficient rendering of high-resolution grids
- OpenStreetMap background tiles

### Time Series View

- Shows full forecast period at selected city
- Median line (p50) with shaded 10-90% uncertainty range
- Automatically updates based on controls

## Testing

Tests verify scientific constraints:

```bash
pytest tests/ -v
```

**Test coverage**:
1. **Precipitation accumulation correctness**: Rate × timestep = accumulation
2. **Non-negativity**: Accumulated precipitation ≥ 0
3. **Spatial subsetting**: Idaho bounds are respected
4. **Data structure preservation**: All dimensions and variables maintained

See `tests/test_derive.py` for implementation.

## Code Conventions

Following scientific Python best practices:

- **Clarity over brevity**: Small functions with docstrings and type hints
- **Explicit units**: All conversions documented and testable
- **Lazy evaluation**: Use xarray + Dask; never compute full global datasets
- **Modular design**: Separate data access, computation, and visualization
- **No global state**: Pure functions with clear inputs/outputs

## Dependencies

Core scientific stack:
- xarray: Multi-dimensional labeled arrays
- dask: Parallel/chunked computation
- zarr: Cloud-native array storage
- netcdf4: NetCDF backend for xarray

Visualization:
- panel: Dashboard framework
- hvplot: High-level plotting API
- holoviews: Data visualization library
- datashader: Large dataset rendering

HTTP/Remote Data Access:
- fsspec: Filesystem interface abstraction
- s3fs: S3 filesystem support
- **aiohttp**: Required by fsspec's HTTPFileSystem for remote Zarr access over HTTPS
- **requests**: Required by fsspec's HTTPFileSystem for remote Zarr access

Development:
- pytest: Testing framework
- black: Code formatter
- ruff: Fast Python linter

**Note**: `aiohttp` and `requests` are critical runtime dependencies for accessing the remote GEFS Zarr dataset via HTTPS. Without them, the app will fail with `ImportError: HTTPFileSystem requires "requests" and "aiohttp" to be installed`.

## Development Workflow

```bash
# Install in editable mode
pip install -e ".[dev]"

# Format code
black .

# Lint code
ruff check .

# Run tests
pytest

# Run dashboard locally
panel serve app.py --show
```

## Future Extensions

Potential enhancements:
- Add more forecast variables (wind, humidity, etc.)
- Implement forecast skill metrics (if observations available)
- Add export functionality for time series data
- Support custom point selection via map clicking
- Cache processed data in local Zarr store for faster reloading

## References

- NOAA GEFS: https://www.ncei.noaa.gov/products/weather-climate-models/global-ensemble-forecast
- Dataset source: https://dynamical.org
- Panel documentation: https://panel.holoviz.org
- xarray documentation: https://docs.xarray.dev
