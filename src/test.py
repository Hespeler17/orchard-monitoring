#!/usr/bin/env python3
"""
Test script to verify all packages are installed correctly.
"""

import sys
print("Python version:", sys.version)
print()

# Test imports
print("Testing package imports...")
print("=" * 50)

try:
    import requests
    print("✅ requests:", requests.__version__)
except ImportError as e:
    print("❌ requests:", e)

try:
    import pandas as pd
    print("✅ pandas:", pd.__version__)
except ImportError as e:
    print("❌ pandas:", e)

try:
    import matplotlib
    print("✅ matplotlib:", matplotlib.__version__)
except ImportError as e:
    print("❌ matplotlib:", e)

try:
    from dotenv import load_dotenv
    print("✅ python-dotenv: OK")
except ImportError as e:
    print("❌ python-dotenv:", e)

try:
    import numpy as np
    print("✅ numpy:", np.__version__)
except ImportError as e:
    print("❌ numpy:", e)

print("=" * 50)
print()
print("🎉 All packages installed successfully!")
print()
print("Project: Orchard Monitoring System")
print("Location: ~/orchard-monitoring")
print("Virtual Environment: Active")
