"""
NAVORA — Autonomous Procurement & Multi-Echelon Rebalancing
Unified Production Service integrating Kaveri Copilot Multi-Agent Decision Engine
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sibling_copilot = os.path.join(os.path.dirname(BASE_DIR), "kaveri_copilot")
nested_copilot = os.path.join(BASE_DIR, "kaveri_copilot")

if os.path.exists(sibling_copilot) and sibling_copilot not in sys.path:
    sys.path.insert(0, sibling_copilot)
elif os.path.exists(nested_copilot) and nested_copilot not in sys.path:
    sys.path.insert(0, nested_copilot)

from app.server import app

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print(">> Starting NAVORA Operations Engine on http://127.0.0.1:8000")
    print(">> Interactive API Docs (Swagger): http://127.0.0.1:8000/docs")
    print(">> Dashboard UI: http://127.0.0.1:8000/")
    print("="*70 + "\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
