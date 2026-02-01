"""Visualization helpers using hvPlot and HoloViews."""

from typing import Optional
import hvplot.xarray  # noqa: F401 (enables .hvplot() accessor)
import holoviews as hv
import panel as pn
import xarray as xr
import geoviews as gv
import cartopy.crs as ccrs
import cartopy.feature as cfeature

# Western US cities for quick selection
IDAHO_CITIES = {
    "Boise": {"lat": 43.6150, "lon": -116.2023},
    "Twin Falls": {"lat": 42.5630, "lon": -114.4608},
    "Idaho Falls": {"lat": 43.4916, "lon": -112.0339},
    "Coeur d'Alene": {"lat": 47.6777, "lon": -116.7805},
    "Denver": {"lat": 39.7392, "lon": -104.9903},
    "Reno": {"lat": 39.5296, "lon": -119.8138},
    "Salt Lake City": {"lat": 40.7608, "lon": -111.8910},
    "Jackson, WY": {"lat": 43.4799, "lon": -110.7624},
    "Vail, CO": {"lat": 39.6403, "lon": -106.3742},
}


def plot_map(
    da: xr.DataArray,
    title: str = "",
    cmap: str = "viridis",
    clabel: str = "",
    width: int = 600,
    height: int = 400,
    clim: tuple = None,
) -> hv.QuadMesh:
    """
    Create interactive map visualization using hvPlot with cartopy features.

    Parameters
    ----------
    da : xr.DataArray
        2D data array with latitude/longitude coordinates
    title : str
        Plot title
    cmap : str
        Colormap name
    clabel : str
        Colorbar label
    width, height : int
        Plot dimensions in pixels
    clim : tuple of (min, max), optional
        Fixed color scale limits to prevent colorbar jumping

    Returns
    -------
    hv.QuadMesh
        Interactive map plot with state/national boundaries and coastlines

    Notes
    -----
    Uses Datashader for efficient rendering of large grids.
    Data should be lazy (not computed) when passed to this function.
    """
    # Find coordinate names
    lat_name = _find_coord(da, ["latitude", "lat", "y"])
    lon_name = _find_coord(da, ["longitude", "lon", "x"])

    # Create base quadmesh plot with geo enabled
    plot = da.hvplot.quadmesh(
        x=lon_name,
        y=lat_name,
        cmap=cmap,
        title=title,
        clabel=clabel,
        width=width,
        height=height,
        clim=clim,
        rasterize=True,  # Use Datashader for large grids
        projection=ccrs.PlateCarree(),
        geo=True,
        coastline=True,
        global_extent=False,
    )
    
    # Add cartopy features matching notebook style
    states = gv.feature.states(line_width=0.5, line_color='black')
    countries = gv.feature.borders(line_width=1.0, line_color='black')
    coastlines = gv.feature.coastline(line_width=1.0, line_color='black')
    
    # Combine base plot with features
    return plot * states * countries * coastlines


def plot_time_series(
    da_or_ds,
    lat: float = None,
    lon: float = None,
    title: str = "",
    ylabel: str = "",
    width: int = 800,
    height: int = 300,
) -> hv.Overlay:
    """
    Create time series plot at a point location or for already-selected point data.

    Parameters
    ----------
    da_or_ds : xr.DataArray or xr.Dataset
        Data with time/step dimension and optional percentile variables.
        Can be already subsetted to a point (lat/lon=None) or a full grid
        (requires lat/lon for selection)
    lat, lon : float or None
        Point location for spatial selection. If None, assumes data is already
        at a single point.
    title : str
        Plot title
    ylabel : str
        Y-axis label
    width, height : int
        Plot dimensions

    Returns
    -------
    hv.Overlay
        Time series plot with median line and optional uncertainty band

    Notes
    -----
    If input is a Dataset with p10, p50, p90 variables, plots median
    with shaded 10-90% range. Otherwise plots single line.
    
    If lat/lon are None, assumes data is already at a point and skips
    spatial selection.
    """
    # If lat/lon provided, perform spatial selection
    if lat is not None and lon is not None:
        # Find coordinate names with error handling
        try:
            lat_name = _find_coord(da_or_ds, ["latitude", "lat", "y"])
            lon_name = _find_coord(da_or_ds, ["longitude", "lon", "x"])
        except ValueError as e:
            # If spatial coords not found, return error message
            available = list(da_or_ds.coords.keys())
            return hv.Text(
                0.5, 0.5, f"Error: Could not find lat/lon coords. Available: {available}"
            )

        # Select point (nearest neighbor) with error handling
        try:
            point_data = da_or_ds.sel(
                {lat_name: lat, lon_name: lon},
                method="nearest",
            )
        except KeyError as e:
            return hv.Text(0.5, 0.5, f"Error: Could not select point ({lat}, {lon}). {e}")
    else:
        # Data already at point
        point_data = da_or_ds

    time_name = _find_coord(point_data, ["valid_time", "time", "step", "lead_time"])

    # If Dataset with percentiles, plot mean with uncertainty
    if isinstance(point_data, xr.Dataset) and "mean" in point_data:
        # Use bracket notation to avoid conflict with .mean() method
        mean_line = point_data['mean'].hvplot.line(
            x=time_name,
            label="Ensemble Mean",
            title=title,
            ylabel=ylabel,
            width=width,
            height=height,
            line_width=2,
        )

        # Add uncertainty band (mean ± 1 std dev)
        if "std" in point_data:
            # Compute upper and lower bounds
            upper_data = point_data['mean'] + point_data['std']
            lower_data = point_data['mean'] - point_data['std']
            
            # Clip lower bound to zero for non-negative variables (e.g., precipitation)
            # This prevents non-physical negative values
            import numpy as np
            lower_data = xr.where(lower_data < 0, 0, lower_data)
            
            # Create uncertainty band using hv.Area
            # Convert to pandas-friendly format for HoloViews
            time_coord = point_data[time_name]
            time_vals = time_coord.values
            
            # Create the area plot by manually building HoloViews elements
            import pandas as pd
            df = pd.DataFrame({
                time_name: time_vals,
                'upper': upper_data.values,
                'lower': lower_data.values,
                'mean': point_data['mean'].values,
            })
            
            # Sort by time for proper area rendering
            if hasattr(time_vals[0], '__iter__') and not isinstance(time_vals[0], str):
                pass  # Already sortable
            else:
                df = df.sort_values(time_name)
            
            # Create mean curve separately for better styling
            curve = hv.Curve(df, time_name, 'mean', label='Ensemble Mean').opts(
                line_width=2, color='steelblue'
            )
            
            # Combine: area plot + mean line
            # Use .opts() for styling parameters like alpha
            area_plot = hv.Area(df, time_name, ['lower', 'upper'], label='±1 std dev').opts(
                alpha=0.2, color='steelblue'
            )
            
            return (area_plot * curve).opts(
                width=width, 
                height=height, 
                title=title,
                xlabel=time_name,
                ylabel=ylabel
            )
        
        return mean_line
    
    # Fallback to p50 if mean not available (backwards compatibility)
    if isinstance(point_data, xr.Dataset) and "p50" in point_data:
        median = point_data['p50'].hvplot.line(
            x=time_name,
            label="Median",
            title=title,
            ylabel=ylabel,
            width=width,
            height=height,
            line_width=2,
        )

        # Add uncertainty band
        if "p10" in point_data and "p90" in point_data:
            area = point_data.hvplot.area(
                x=time_name,
                y="p10",
                y2="p90",
                alpha=0.2,
                label="10-90% range",
            )
            return area * median

        return median

    # Single line plot
    plot = point_data.hvplot.line(
        x=time_name,
        title=title,
        ylabel=ylabel,
        width=width,
        height=height,
    )

    return plot


def create_city_selector() -> pn.widgets.Select:
    """
    Create dropdown widget for Idaho city selection.

    Returns
    -------
    pn.widgets.Select
        Panel select widget with Idaho cities
    """
    return pn.widgets.Select(
        name="Location",
        options=list(IDAHO_CITIES.keys()),
        value="Boise",
    )


def get_city_coords(city_name: str) -> tuple[float, float]:
    """
    Get coordinates for named city.

    Parameters
    ----------
    city_name : str
        City name from IDAHO_CITIES

    Returns
    -------
    lat, lon : float
        Latitude and longitude in degrees
    """
    coords = IDAHO_CITIES.get(city_name, IDAHO_CITIES["Boise"])
    return coords["lat"], coords["lon"]


def _find_coord(obj, candidates: list[str]) -> str:
    """Find coordinate name from candidates."""
    coords = obj.coords if hasattr(obj, "coords") else {}
    dims = obj.dims if hasattr(obj, "dims") else []

    for name in candidates:
        if name in coords or name in dims:
            return name

    available = list(coords.keys()) if coords else list(dims)
    raise ValueError(
        f"Could not find coordinate from {candidates}. Available: {available}"
    )
