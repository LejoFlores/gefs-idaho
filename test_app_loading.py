"""Test script to manually instantiate dashboard and catch errors."""

import sys
import traceback

try:
    print("Importing app module...")
    import app
    print("✓ App module imported successfully")
    
    print("\nChecking dashboard object...")
    print(f"  Dashboard type: {type(app.dashboard)}")
    print(f"  Dashboard: {app.dashboard}")
    
    print("\n✅ No errors during import!")
    
except Exception as e:
    print(f"\n❌ ERROR during import:")
    print(f"  {type(e).__name__}: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
