"""Panel dashboard for GEFS Idaho forecast visualization."""

import panel as pn
import param

from gefs_idaho.data import load_idaho_forecast
from gefs_idaho.derive import (
    add_valid_time,
    compute_precipitation_accumulation,
    compute_ensemble_statistics,
)
from gefs_idaho.viz import (
    plot_map,
    plot_time_series,
    create_city_selector,
    get_city_coords,
)

pn.extension("tabulator")


class GEFSIdahoDashboard(param.Parameterized):
    """Interactive dashboard for GEFS Idaho forecast visualization."""

    # Controls
    variable = param.Selector(
        default="temperature_2m",
        objects=["temperature_2m", "precipitation_surface"],
        doc="Forecast variable to visualize",
    )

    city = param.Selector(
        default="Boise",
        objects=["Boise", "Twin Falls", "Idaho Falls", "Coeur d'Alene"],
        doc="City location for time series",
    )

    accumulation_window = param.Selector(
        default="24h",
        objects=["6h", "24h", "7d"],
        doc="Precipitation accumulation window",
    )

    valid_time_index = param.Integer(
        default=0,
        bounds=(0, 100),
        doc="Valid time index for map view",
    )

    def __init__(self, **params):
        super().__init__(**params)

        # Load data once at initialization
        self._ds = None
        self._load_error = None
        self._data_loaded = False

    def _load_data(self):
        """Load and preprocess GEFS Idaho forecast data with error handling."""
        if self._data_loaded or self._ds is not None:
            return

        try:
            # Load Idaho subset
            ds = load_idaho_forecast()

            # Add valid_time coordinate
            ds = add_valid_time(ds)

            self._ds = ds
            self._data_loaded = True

            # Update valid_time bounds
            # Find the step/lead_time dimension
            from gefs_idaho.derive import _find_step_coord

            step_dim = _find_step_coord(ds)
            n_steps = len(ds[step_dim])
            self.param.valid_time_index.bounds = (0, n_steps - 1)
        except Exception as e:
            self._load_error = str(e)

    @param.depends("variable", "valid_time_index", "accumulation_window")
    def map_view(self):
        """Create map visualization for selected variable and time."""
        if not self._data_loaded:
            self._load_data()

        if self._load_error:
            return pn.pane.Markdown(f"⚠️ Error loading data: {self._load_error}")

        if self._ds is None:
            return pn.pane.Markdown("Loading data... (first load may take ~30 seconds)")

        # Select variable
        if self.variable == "temperature_2m":
            da = self._ds.temperature_2m
            title = f"Temperature (°C) at {self._get_valid_time_label()}"
            cmap = "RdBu_r"
            clabel = "Temperature (°C)"
        else:  # precipitation
            da = self._ds.precipitation_surface
            # Compute accumulation
            da = compute_precipitation_accumulation(da, window=self.accumulation_window)
            title = f"Accumulated Precipitation ({self.accumulation_window}) at {self._get_valid_time_label()}"
            cmap = "Blues"
            clabel = "Precipitation (mm)"

        # Compute ensemble statistics
        stats = compute_ensemble_statistics(da)

        # Select valid time (use step index for now)
        from gefs_idaho.derive import _find_step_coord

        step_dim = _find_step_coord(stats)
        map_data = stats.p50.isel({step_dim: self.valid_time_index})

        # Create map
        plot = plot_map(
            map_data,
            title=title,
            cmap=cmap,
            clabel=clabel,
        )

        return pn.pane.HoloViews(plot)

    @param.depends("variable", "city", "accumulation_window")
    def time_series_view(self):
        """Create time series plot at selected city."""
        if not self._data_loaded:
            self._load_data()

        if self._load_error:
            return pn.pane.Markdown(f"⚠️ Error loading data: {self._load_error}")

        if self._ds is None:
            return pn.pane.Markdown("Loading data... (first load may take ~30 seconds)")

        # Get city coordinates
        lat, lon = get_city_coords(self.city)

        # Select variable
        if self.variable == "temperature_2m":
            da = self._ds.temperature_2m
            ylabel = "Temperature (°C)"
            title = f"Temperature at {self.city}"
        else:  # precipitation
            da = self._ds.precipitation_surface
            # Compute accumulation
            da = compute_precipitation_accumulation(da, window=self.accumulation_window)
            ylabel = f"Accumulated Precipitation (mm, {self.accumulation_window})"
            title = f"Precipitation at {self.city}"

        # Compute ensemble statistics
        stats = compute_ensemble_statistics(da)

        # Create time series
        plot = plot_time_series(
            stats,
            lat=lat,
            lon=lon,
            title=title,
            ylabel=ylabel,
        )

        return pn.pane.HoloViews(plot)

    def _get_valid_time_label(self) -> str:
        """Get human-readable label for current valid time."""
        if self._ds is None:
            return "N/A"

        try:
            from gefs_idaho.derive import _find_step_coord

            step_dim = _find_step_coord(self._ds)
            valid_time = self._ds.valid_time.isel(
                {step_dim: self.valid_time_index}
            ).values
            return str(valid_time)[:16]  # Truncate to date + hour
        except Exception:
            return f"Step {self.valid_time_index}"

    def view(self):
        """Create complete dashboard layout."""
        # Title
        title = pn.pane.Markdown(
            "# GEFS Idaho Forecast Visualization",
            styles={"font-size": "24pt"},
        )

        # Controls
        controls = pn.Column(
            "## Controls",
            pn.Param(
                self.param,
                parameters=[
                    "variable",
                    "city",
                    "accumulation_window",
                    "valid_time_index",
                ],
                widgets={
                    "valid_time_index": pn.widgets.IntSlider,
                },
            ),
        )

        # Layout
        dashboard = pn.Column(
            title,
            pn.Row(
                controls,
                pn.Column(
                    "## Map View",
                    self.map_view,
                ),
            ),
            pn.Column(
                "## Time Series",
                self.time_series_view,
            ),
        )

        return dashboard


def create_dashboard():
    """Create and configure the GEFS Idaho dashboard."""
    app = GEFSIdahoDashboard()
    return app.view()


# Create dashboard instance for panel serve
def create_dashboard_view():
    """Lazy dashboard creation to avoid hanging on import."""
    app = GEFSIdahoDashboard()
    return app.view()


dashboard = create_dashboard_view()

if __name__ == "__main__":
    dashboard.show()
elif __name__.startswith("bokeh_app"):
    # For panel serve
    dashboard.servable()
