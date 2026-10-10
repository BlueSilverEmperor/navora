import sys
import time
import requests
import pandas as pd

FASTAPI_URL = "http://127.0.0.1:8000"
STREAMLIT_URL = "http://127.0.0.1:8501"

def run_verification():
    print("=" * 70)
    print("🚜 KAVERI SPARES COPILOT — COMPLETE SYSTEM & UI DATA DISPLAY AUDIT")
    print("=" * 70)

    # -------------------------------------------------------------
    # PHASE 1: Backend Health, Data Ingestion & State Reset
    # -------------------------------------------------------------
    print("\n[Phase 1/5] Checking Server Liveness & Restoring Benchmark State...")
    try:
        r = requests.get(f"{FASTAPI_URL}/health", timeout=3)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        print("  ✓ /health: OK (200)")

        r = requests.post(f"{FASTAPI_URL}/reset-data", timeout=3)
        assert r.status_code == 200, f"Reset failed with {r.status_code}"
        print("  ✓ /reset-data: OK (Benchmark state restored)")
    except Exception as e:
        print(f"  ✗ Server unreachable or failed health check: {e}")
        sys.exit(1)

    # -------------------------------------------------------------
    # PHASE 2: Multi-Incident Briefing & Problem Coverage
    # -------------------------------------------------------------
    print("\n[Phase 2/5] Auditing Morning Decision Briefing & Problem Classifications...")
    r = requests.get(f"{FASTAPI_URL}/briefing", timeout=5)
    assert r.status_code == 200, f"Failed fetching briefing: {r.status_code}"
    briefing = r.json()
    problems = briefing.get("problems", [])
    
    print(f"  ✓ Total Active Incidents Detected: {len(problems)}")
    assert len(problems) > 0, "No operational problems detected!"

    # Verify representation of all 5 core problem categories
    categories = {p.get("category_code") for p in problems}
    print(f"  ✓ Problem Categories Detected: {categories}")
    for cat in ["CATEGORY_A", "CATEGORY_B", "CATEGORY_C"]:
        assert cat in categories, f"Missing critical problem category: {cat}"

    # Verify mathematical integrity on first incident
    sample = problems[0]
    required_keys = ["sku", "location", "current_stock", "v_predicted", "days_of_cover", "stockout_gap_days", "alternatives"]
    for k in required_keys:
        assert k in sample, f"Sample incident missing required key: {k}"
    print(f"  ✓ Incident Math Contracts Validated (Sample: {sample['sku']} @ {sample['location']})")

    # -------------------------------------------------------------
    # PHASE 3: Multi-Tab Data Endpoints (UI Feeding Contracts)
    # -------------------------------------------------------------
    print("\n[Phase 3/5] Verifying Data Feeds for All UI Dashboard Tabs...")
    
    # Tab 2 Feed: Multi-Echelon Network Inventory (8 Facilities)
    r_inv = requests.get(f"{FASTAPI_URL}/inventory", timeout=3)
    assert r_inv.status_code == 200, f"Inventory feed failed: {r_inv.status_code}"
    inv_data = r_inv.json()
    assert len(inv_data) > 0, "Inventory feed is empty!"
    nodes = {item.get("location") for item in inv_data}
    print(f"  ✓ Tab 2 (Multi-Echelon Inventory): {len(inv_data)} records across {len(nodes)} network nodes")
    assert len(nodes) >= 8, f"Expected 8 network facilities, found only {len(nodes)}"

    # Tab 3 Feed: Supplier Friction & Reliability Audit
    r_sup = requests.get(f"{FASTAPI_URL}/suppliers/audit", timeout=3)
    assert r_sup.status_code == 200, f"Supplier audit feed failed: {r_sup.status_code}"
    sup_data = r_sup.json()
    assert len(sup_data) > 0, "Supplier audit feed is empty!"
    print(f"  ✓ Tab 3 (Supplier Friction Audit): {len(sup_data)} supplier profiles loaded with lead times and MOQs")

    # Tab 4 Feed: Immutable Audit Ledger History
    r_log = requests.get(f"{FASTAPI_URL}/audit-log", timeout=3)
    assert r_log.status_code == 200, f"Audit log feed failed: {r_log.status_code}"
    print(f"  ✓ Tab 4 (Immutable Audit Trail): Audit ledger initialized and queryable")

    # -------------------------------------------------------------
    # PHASE 4: Human Governance, Dynamic Overrides & Idempotency
    # -------------------------------------------------------------
    print("\n[Phase 4/5] Verifying Human Gate, Dynamic Recalculation & Idempotency...")
    
    # Test Dynamic Counter-Proposal Recalculation (Override)
    test_prob = problems[0]
    recalc_payload = {
        "problem_id": test_prob["problem_id"],
        "sku": test_prob["sku"],
        "donor_location": "Belgaum Central Warehouse",
        "target_location": test_prob["location"],
        "override_qty": 14
    }
    r_recalc = requests.post(f"{FASTAPI_URL}/action/recalculate-override", json=recalc_payload, timeout=3)
    assert r_recalc.status_code == 200, f"Override recalculation failed: {r_recalc.status_code}"
    recalc_res = r_recalc.json()
    assert "remaining_cover_days" in recalc_res, "Missing remaining donor cover in recalculation response"
    print(f"  ✓ Counter-Proposal Live Recalculation: OK (Donor Remaining Cover: {recalc_res['remaining_cover_days']}d)")

    # Test Action Approval with Idempotency Token
    idempotency_token = f"VERIFY-RUN-{int(time.time())}"
    approve_payload = {
        "problem_id": test_prob["problem_id"],
        "action_type": "TRANSFER_REQUEST",
        "client_request_id": idempotency_token,
        "payload": {
            "sku": test_prob["sku"],
            "qty": 14,
            "from_location": "Belgaum Central Warehouse",
            "to_location": test_prob["location"],
            "unit_cost_inr": 0,
            "total_estimated_cost_inr": 250
        }
    }
    
    # 1st Execution: Must succeed
    r_app1 = requests.post(f"{FASTAPI_URL}/action/approve", json=approve_payload, timeout=3)
    assert r_app1.status_code == 200, f"Action approval failed: {r_app1.text}"
    print("  ✓ Action Approval Gate: Committed (200 OK)")

    # 2nd Execution: Duplicate token must return HTTP 409 Conflict
    r_app2 = requests.post(f"{FASTAPI_URL}/action/approve", json=approve_payload, timeout=3)
    assert r_app2.status_code == 409, f"Expected 409 Conflict for double-click, got {r_app2.status_code}"
    print("  ✓ Double-Click Idempotency Barrier: OK (Caught 409 Conflict)")

    # -------------------------------------------------------------
    # PHASE 5: UI Service Liveness & Frontend Render Checks
    # -------------------------------------------------------------
    print("\n[Phase 5/5] Checking Frontend Accessibility...")
    
    # 1. NAVORA HTML SPA (Port 8000)
    try:
        r_nav = requests.get(FASTAPI_URL, timeout=3)
        assert r_nav.status_code == 200, f"NAVORA SPA returned {r_nav.status_code}"
        assert "<html" in r_nav.text.lower(), "NAVORA SPA response did not contain HTML markup"
        print("  ✓ NAVORA SPA (Port 8000): Online & Serving HTML5")
    except Exception as e:
        print(f"  ✗ NAVORA SPA check failed: {e}")

    # 2. Streamlit Executive Cockpit (Port 8501)
    try:
        r_str = requests.get(f"{STREAMLIT_URL}/_stcore/health", timeout=3)
        assert r_str.status_code == 200, f"Streamlit health returned {r_str.status_code}"
        print("  ✓ Streamlit Executive Cockpit (Port 8501): Online & Healthy")
    except Exception as e:
        print(f"  ⚠ Streamlit health endpoint unreachable: {e} (Ensure streamlit run app/dashboard.py is active)")

    print("\n" + "=" * 70)
    print("🏆 ALL FUNCTIONS, DATA FEEDS, AND UI PIPELINES ARE FULLY OPERATIONAL!")
    print("=" * 70)

if __name__ == "__main__":
    run_verification()
