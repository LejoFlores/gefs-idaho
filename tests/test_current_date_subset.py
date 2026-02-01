from datetime import date

import pandas as pd
import pytest

from gefs_idaho.data import load_idaho_forecast
from gefs_idaho.derive import add_valid_time


@pytest.mark.network
def test_current_date_in_valid_time_range():
    """Functional test: current date should be within valid_time range."""
    ds = load_idaho_forecast(cache_local=True)
    ds = add_valid_time(ds)

    valid_time = ds["valid_time"]

    vt_min = pd.to_datetime(valid_time.min().compute().values).date()
    vt_max = pd.to_datetime(valid_time.max().compute().values).date()
    today = date.today()

    assert vt_min <= today <= vt_max, (
        f"Current date {today} not in valid_time range {vt_min}..{vt_max}."
    )
