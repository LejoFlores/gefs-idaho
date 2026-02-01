"""Quick verification that app can load GEFS data without errors."""

import warnings

warnings.filterwarnings("ignore")

from gefs_idaho.data import load_idaho_forecast
from gefs_idaho.derive import add_valid_time, _find_step_coord

print("Loading GEFS Idaho forecast data...")
try:
    ds = load_idaho_forecast()
    print(f"✓ Dataset loaded successfully")
    print(f"  Dimensions: {dict(ds.dims)}")
    print(f"  Variables: {list(ds.data_vars.keys())[:5]}...")

    # Test add_valid_time
    ds = add_valid_time(ds)
    print(f"✓ valid_time coordinate added")

    # Test finding step coordinate
    step_dim = _find_step_coord(ds)
    print(f"✓ Step dimension found: {step_dim}")

    # Test accessing step length (what app does)
    n_steps = len(ds[step_dim])
    print(f"✓ Number of forecast steps: {n_steps}")

    print("\n✅ All checks passed! App should work correctly.")

except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()
