# GEFS Idaho - Weather Forecast Visualization

## Overview
Panel dashboard for visualizing GEFS (Global Ensemble Forecast System) 35-day forecast data for Idaho using xarray/Dask for data processing and Panel/hvPlot for interactive visualization.

## Architecture & Data Flow

**Three-layer design** (`src/gefs_idaho/`):
1. **data.py**: Load remote Zarr dataset, subset to Idaho bounds immediately (prevents global data in memory)
2. **derive.py**: Compute derived products (valid time, precipitation accumulation, ensemble statistics)
3. **viz.py**: Create interactive plots using hvPlot accessor on xarray objects
4. **app.py**: Panel dashboard with `param.Parameterized` for reactive state management

**Key pattern**: Data flows through xarray lazy chains → `param.depends` watchers trigger updates → plots recomputed only when controls change.

## Data Source & Critical Constraints

- **Zarr dataset**: `https://data.dynamical.org/noaa/gefs/forecast-35-day/latest.zarr`
- **Dimensions**: `time` (init), `step` (lead time), `ensemble_member` (varies), `latitude`, `longitude`
- **Variables**: `temperature_2m` (°C), `precipitation_surface` (kg m⁻² s⁻¹)
- **Idaho bounds**: lat 42–50°N, lon -117 to -111°W (uses -180 to 180 convention)

### Precipitation Rate → Accumulation (CRITICAL)
`precipitation_surface` is a **rate** averaged since previous forecast step, NOT accumulated. Conversion:
```python
accumulation (mm) = rate (mm/s) × timestep_duration (seconds)
```
- **Never hard-code timestep duration** — derive from coordinate differences (see `derive.py::compute_precipitation_accumulation`)
- Units: kg m⁻² s⁻¹ × s = kg m⁻² = mm (1 kg water/m² = 1 mm depth)
- Test this with `test_derive.py::test_precipitation_accumulation_calculation()`

## Development Setup
```bash
pip install -e ".[dev]"          # Install with dev dependencies
pytest                            # Run tests
black . && ruff check .          # Format & lint
panel serve app.py --show        # Launch dashboard at localhost:5006/app
```

## Code Patterns & Implementation Details

**Coordinate name discovery** (`derive.py`, `viz.py`):
- GEFS data uses `init_time`, `lead_time`, `ensemble_member` — but also `time`, `step`, `ensemble` in tests
- Use `_find_time_coord()`, `_find_step_coord()`, `_find_ensemble_dim()` helper functions
- Priority order in function docstrings; raise `ValueError` with available coords if not found
- See test_derive.py::test_coordinate_name_discovery() for validation patterns

**Panel dashboard** (`app.py`):
- Subclass `param.Parameterized` with `@param.depends()` watchers on control parameters
- Load data once in `__init__`, cache in `self._ds` — don't reload per update
- Return `pn.pane.HoloViews()` for plots (not raw HoloViews objects)
- Use `panel serve app.py` (NOT `jupyter notebook`) for deployment; Panel handles Bokeh backend

**Lazy evaluation** (`data.py`, viz.py):
- Pass lazy xarray objects to plotting functions; only compute for display
- Do NOT call `.compute()` before visualization — hvPlot handles rasterization with Datashader
- `rasterize=True` in hvplot.quadmesh() enables efficient rendering without downsampling

**Ensemble statistics** (`derive.py`):
- Compute percentiles (p10, p50, p90) using `xr.quantile()` on ensemble dimension
- Drop `quantile` coordinate after quantile operation to avoid merging conflicts
- Maps show p50 (median); time series show median + shaded 10-90% range

## Testing Conventions

Located in `tests/test_derive.py`:
- **Unit tests verify scientific correctness**, not just type checking
- Example: `test_precipitation_accumulation_calculation()` validates units with numerical tolerance
- Create synthetic test datasets with `create_test_dataset()` — 3-hourly steps, ensemble size 3, 25×21 grid
- Use `np.testing.assert_allclose()` for floating-point comparisons (rtol=0.01 default)

## Coding Conventions

**Prefer clarity and inspectability over brevity**
- Use small, named functions with docstrings and type hints (see `compute_precipitation_accumulation()` for model)
- Separate data access, computation, visualization into distinct modules — NO monolithic files
- Document scientific assumptions in docstrings (e.g., units, averaging methods)

**Data Processing**
- **Never compute global or multi-day datasets** — subset Idaho bounds first
- Use xarray labeled selection: `ds.sel(time='2026-01-31', lat=slice(42, 49))`
- Always subset to Idaho bounds in `load_idaho_forecast()` before returning
- Chunk before computation if needed: `ds.chunk({'time': 10, 'lat': 100, 'lon': 100})`

**Visualization**
- Use hvPlot `.hvplot()` accessor (NOT matplotlib/seaborn) — returns HoloViews objects
- Set `geo=False` to avoid geoviews dependency
- Test interactivity in notebooks first, deploy with Panel

**Tooling**
- No unnecessary abstractions; use standard Python tools (venv, pyproject.toml, pytest)
- Python 3.10+; fsspec + aiohttp required for remote Zarr access
- Format with Black, lint with Ruff
