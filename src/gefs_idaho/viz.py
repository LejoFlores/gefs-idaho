"""Visualization helpers using hvPlot and HoloViews."""

from typing import Optional
import hvplot.xarray  # noqa: F401 (enables .hvplot() accessor)
import holoviews as hv
import panel as pn
import xarray as xr

# Idaho cities for quick selection
IDAHO_CITIES = {
    "Boise": {"lat": 43.6150, "lon": -116.2023},
    "Twin Falls": {"lat": 42.5630, "lon": -114.4608},
    "Idaho Falls": {"lat": 43.4916, "lon": -112.0339},
    "Coeur d'Alene": {"lat": 47.6777, "lon": -116.7805},
}


def plot_map(
    da: xr.DataArray,
    title: str = "",
    cmap: str = "viridis",
    clabel: str = "",
    width: int = 600,
    height: int = 400,
) -> hv.QuadMesh:
    """
    Create interactive map visualization using hvPlot.

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

    Returns
    -------
    hv.QuadMesh
        Interactive map plot

    Notes
    -----
    Uses Datashader for efficient rendering of large grids.
    Data should be lazy (not computed) when passed to this function.
    """
    # Find coordinate names
    lat_name = _find_coord(da, ["latitude", "lat", "y"])
    lon_name = _find_coord(da, ["longitude", "lon", "x"])

    plot = da.hvplot.quadmesh(
        x=lon_name,
        y=lat_name,
        cmap=cmap,
        title=title,
        clabel=clabel,
        width=width,
        height=height,
        rasterize=True,  # Use Datashader for large grids
        geo=False,  # Disable geographic projection to avoid geoviews requirement
    )

    return plot


def plot_time_series(
    da_or_ds,
    lat: float,
    lon: float,
    title: str = "",
    ylabel: str = "",
    width: int = 800,
    height: int = 300,
) -> hv.Overlay:
    """
    Create time series plot at a point location.

    Parameters
    ----------
    da_or_ds : xr.DataArray or xr.Dataset
        Data with time/step dimension and optional percentile variables
    lat, lon : float
        Point location
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
    """
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

    time_name = _find_coord(da_or_ds, ["valid_time", "time", "step", "lead_time"])

    # Select point (nearest neighbor) with error handling
    try:
        point_data = da_or_ds.sel(
            {lat_name: lat, lon_name: lon},
            method="nearest",
        )
    except KeyError as e:
        return hv.Text(0.5, 0.5, f"Error: Could not select point ({lat}, {lon}). {e}")

    # If Dataset with percentiles, plot median with uncertainty
    if isinstance(point_data, xr.Dataset) and "p50" in point_data:
        median = point_data.p50.hvplot.line(
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
