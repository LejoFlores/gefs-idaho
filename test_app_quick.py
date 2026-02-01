"""Quick test that app loads without hanging."""

import sys
import signal


def timeout_handler(signum, frame):
    print("❌ App import timed out (likely data loading issue)")
    sys.exit(1)


# Set 15 second timeout
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(15)

try:
    print("Importing app module...")
    import app

    signal.alarm(0)  # Cancel alarm
    print("✅ App module imported successfully!")
    print(f"Dashboard callable: {callable(app.dashboard)}")
    print("✅ Panel server should start without hanging")
except Exception as e:
    signal.alarm(0)
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
