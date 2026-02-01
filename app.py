"""Panel dashboard for GEFS Idaho forecast visualization."""

import logging
import time
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

        # Data will be loaded on first access
        self._ds = None
        self._load_error = None
        self._data_loaded = False
        self._loading = False

    def _load_data(self):
        """Load and preprocess GEFS Idaho forecast data with error handling and timing."""
        if self._data_loaded or self._ds is not None or self._loading:
            return

        self._loading = True
        logger.info("Starting data load...")
        t_start = time.time()
        
        try:
            # Load Idaho subset (cached after first call)
            logger.info("Calling load_idaho_forecast()...")
            ds = load_idaho_forecast()

            # Add valid_time coordinate
            logger.info("Adding valid_time coordinate...")
            ds = add_valid_time(ds)

            self._ds = ds
            self._data_loaded = True

            # Update valid_time bounds
            from gefs_idaho.derive import _find_step_coord

            step_dim = _find_step_coord(ds)
            n_steps = len(ds[step_dim])
            self.param.valid_time_index.bounds = (0, n_steps - 1)
            
            t_end = time.time()
            logger.info(f"✓ Data loaded successfully in {t_end - t_start:.1f}s")
            logger.info(f"  Dimensions: {dict(ds.dims)}")
            logger.info(f"  Variables: {list(ds.data_vars.keys())}")
            
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"Error loading data: {e}", exc_info=True)
        finally:
            self._loading = False

    @param.depends("variable", "valid_time_index", "accumulation_window")
    def map_view(self):
        """Create map visualization for selected variable and time."""
        # Show loading indicator while data loads
        if self._loading:
            return pn.indicators.LoadingSpinner(value=True, size=50)
        
        if not self._data_loaded:
            self._load_data()
            # After triggering load, return loading message
            if self._loading or not self._data_loaded:
                return pn.pane.Markdown("⏳ Loading data from remote Zarr... (first load: ~30 seconds)")

        if self._load_error:
            return pn.pane.Markdown(f"⚠️ Error loading data: {self._load_error}")

        if self._ds is None:
            return pn.pane.Markdown("Initializing...")

        try:
            logger.info(f"Computing map view: variable={self.variable}, time_idx={self.valid_time_index}, window={self.accumulation_window}")
            t0 = time.time()
            
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

            # OPTIMIZATION: Select time slice BEFORE computing ensemble stats
            # This reduces computation from (time × ensemble × lat × lon) to (ensemble × lat × lon)
            from gefs_idaho.derive import _find_step_coord
            step_dim = _find_step_coord(da)
            da_time_slice = da.isel({step_dim: self.valid_time_index})
            
            t1 = time.time()
            logger.info(f"  Selected time slice in {t1-t0:.2f}s")
            
            # Compute ensemble statistics on reduced data
            stats = compute_ensemble_statistics(da_time_slice)
            
            t2 = time.time()
            logger.info(f"  Computed ensemble stats in {t2-t1:.2f}s")
            
            # Get median for map
            map_data = stats.p50

            # Create map
            plot = plot_map(
                map_data,
                title=title,
                cmap=cmap,
                clabel=clabel,
            )
            
            t3 = time.time()
            logger.info(f"✓ Map view ready in {t3-t0:.2f}s total")

            return pn.pane.HoloViews(plot)
            
        except Exception as e:
            logger.error(f"Error in map_view: {e}", exc_info=True)
            return pn.pane.Markdown(f"⚠️ Error creating map: {e}")

    @param.depends("variable", "city", "accumulation_window")
    def time_series_view(self):
        """Create time series plot at selected city."""
        # Show loading indicator while data loads
        if self._loading:
            return pn.indicators.LoadingSpinner(value=True, size=50)
            
        if not self._data_loaded:
            self._load_data()
            if self._loading or not self._data_loaded:
                return pn.pane.Markdown("⏳ Loading data from remote Zarr... (first load: ~30 seconds)")

        if self._load_error:
            return pn.pane.Markdown(f"⚠️ Error loading data: {self._load_error}")

        if self._ds is None:
            return pn.pane.Markdown("Initializing...")

        try:
            logger.info(f"Computing time series: variable={self.variable}, city={self.city}, window={self.accumulation_window}")
            t0 = time.time()
            
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

            # OPTIMIZATION: Select spatial point BEFORE computing ensemble stats
            # This reduces computation from (time × ensemble × lat × lon) to (time × ensemble)
            # Use nearest neighbor selection for the city
            da_point = da.sel(latitude=lat, longitude=lon, method="nearest")
            
            t1 = time.time()
            logger.info(f"  Selected spatial point in {t1-t0:.2f}s")
            
            # Compute ensemble statistics on 1D time series
            stats = compute_ensemble_statistics(da_point)
            
            t2 = time.time()
            logger.info(f"  Computed ensemble stats in {t2-t1:.2f}s")

            # Create time series - pass stats directly (already at point)
            # Pass lat/lon=None to skip spatial selection in plot function
            plot = plot_time_series(
                stats,
                lat=None,
                lon=None,
                title=title,
                ylabel=ylabel,
            )
            
            t3 = time.time()
            logger.info(f"✓ Time series ready in {t3-t0:.2f}s total")

            return pn.pane.HoloViews(plot)
            
        except Exception as e:
            logger.error(f"Error in time_series_view: {e}", exc_info=True)
            return pn.pane.Markdown(f"⚠️ Error creating time series: {e}")

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
    logger.info("Creating dashboard instance...")
    app = GEFSIdahoDashboard()
    return app.view()


# For panel serve - use pn.serve with a function callback
# This ensures dashboard is created per session, not at module import
def _make_dashboard():
    """Factory function for Panel server - called once per browser session."""
    return create_dashboard()


# This will be evaluated when Panel loads the app
_dashboard = _make_dashboard()

if __name__ == "__main__":
    _dashboard.show()
elif __name__.startswith("bokeh_app"):
    # For panel serve
    _dashboard.servable()
