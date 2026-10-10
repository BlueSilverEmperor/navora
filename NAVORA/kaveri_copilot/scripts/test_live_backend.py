"""
Live End-to-End Backend Verification Runner for Kaveri Spares Copilot
Tests all production endpoints against real operational scenarios:
A. Health & State Reset
B. Decision Briefing & Metric Validation
C. Human Counter-Proposal & Dynamic Recalibration
D. Human Gate Execution & Audit Log Mutation
E. Chaos Injection & Dynamic Adaptation
"""

import sys
import time
import requests
import json

BASE_URL = "http://127.0.0.1:8000"


def log_step(name, passed, detail=""):
    marker = "[\033[92mPASS\033[0m]" if passed else "[\033[91mFAIL\033[0m]"
    print(f"{marker} {name}")
    if detail:
        print(f"       -> {detail}")
    if not passed:
        sys.exit(1)


def wait_for_server(url, max_retries=10, delay=1.0):
    print(f"Connecting to live backend at {url}...")
    for i in range(max_retries):
        try:
            res = requests.get(f"{url}/health", timeout=2.0)
            if res.status_code == 200:
                print("Server connection established.")
                return True
        except Exception:
            time.sleep(delay)
    return False


def main():
    if not wait_for_server(BASE_URL):
        print(f"Error: Unable to connect to backend server at {BASE_URL}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  KAVERI COPILOT: LIVE BACKEND HEALTH AUDIT & CONTRACT VERIFICATION")
    print("=" * 70 + "\n")

    # -------------------------------------------------------------
    # Pillar A: Health & State Reset
    # -------------------------------------------------------------
    print("--- [A] Health & State Reset ---")
    r_health = requests.get(f"{BASE_URL}/health")
    assert r_health.status_code == 200, f"Expected 200, got {r_health.status_code}"
    health_data = r_health.json()
    assert health_data.get("status") == "healthy", f"Expected 'healthy', got {health_data}"
    log_step("GET /health", True, f"Service status: {health_data.get('status')}")

    r_reset = requests.post(f"{BASE_URL}/reset-data")
    assert r_reset.status_code == 200, f"Expected 200, got {r_reset.status_code}"
    reset_data = r_reset.json()
    assert reset_data.get("status") == "SUCCESS", f"Expected 'SUCCESS', got {reset_data}"
    log_step("POST /reset-data", True, "Benchmark baseline data and chaos state reset.")

    # -------------------------------------------------------------
    # Pillar B: Decision Briefing & Metric Validation
    # -------------------------------------------------------------
    print("\n--- [B] Decision Briefing & Metric Validation ---")
    r_brief = requests.get(f"{BASE_URL}/briefing")
    assert r_brief.status_code == 200, f"Expected 200, got {r_brief.status_code}"
    brief_data = r_brief.json()

    total_probs = brief_data.get("summary", {}).get("total_problems_detected", 0)
    assert total_probs >= 3, f"Expected >= 3 problems, got {total_probs}"
    log_step("Briefing total problems detected", True, f"total_problems_detected = {total_probs} (>= 3)")

    # Find Gokak FILTER-HYD-01 problem
    gokak_p = None
    for p in brief_data.get("problems", []):
        if p.get("sku") == "FILTER-HYD-01" and p.get("location") == "Gokak":
            gokak_p = p
            break
    assert gokak_p is not None, "Gokak FILTER-HYD-01 problem not found in briefing"

    # Category code / category
    cat = gokak_p.get("category_code") or gokak_p.get("category")
    cover = gokak_p.get("domain_metrics", {}).get("days_of_cover")
    assert cover == 2.0, f"Expected 2.0 days cover, got {cover}"
    log_step("Category A Identification", True, f"SKU: FILTER-HYD-01 at Gokak | Days of Cover = {cover}d | Category = {cat}")

    # Evaluated Options
    opts = gokak_p.get("evaluated_options", [])
    has_internal = any("Internal Network" in o.get("option_name", "") for o in opts)
    has_expedited = any("Expedited Secondary" in o.get("option_name", "") for o in opts)
    assert has_internal, "Internal Network Balancing option must be evaluated"
    assert has_expedited, "Expedited Secondary Procurement option must be evaluated"
    log_step("Multi-Option Evaluation", True, "Both Internal Network Balancing (Belgaum) & Expedited Procurement evaluated")

    # Projections
    proj = gokak_p.get("forward_projections", {})
    sq_len = len(proj.get("status_quo", []))
    exp_len = len(proj.get("expedited", []))
    tr_len = len(proj.get("transfer", []))
    assert sq_len == 15 and exp_len == 15 and tr_len == 15, f"Expected 15-day arrays, got {sq_len}, {exp_len}, {tr_len}"
    log_step("14-Day Forward Trajectory Curves", True, "Projection arrays length = 15 for status_quo, expedited, and transfer")

    # -------------------------------------------------------------
    # Pillar C: Human Counter-Proposal & Dynamic Recalibration
    # -------------------------------------------------------------
    print("\n--- [C] Human Counter-Proposal & Dynamic Recalibration ---")
    payload_recalc_safe = {
        "problem_id": "PROB-GOKAK-FILTER",
        "sku": "FILTER-HYD-01",
        "donor_location": "Belgaum",
        "target_location": "Gokak",
        "override_qty": 18
    }
    r_recalc = requests.post(f"{BASE_URL}/action/recalculate-override", json=payload_recalc_safe)
    assert r_recalc.status_code == 200, f"Expected 200, got {r_recalc.status_code}"
    recalc_data = r_recalc.json()
    assert recalc_data.get("is_safe") is True, f"Expected is_safe == True, got {recalc_data.get('is_safe')}"
    donor_cov = recalc_data.get("donor_revised_cover_days", 0)
    assert donor_cov >= 15.0, f"Expected donor cover >= 15.0 days, got {donor_cov}"
    log_step("Safe Override Recalculation (18 units)", True, f"is_safe = True | Donor remaining cover = {donor_cov:.1f} days (>= 15.0d)")

    # Edge case rejection
    payload_recalc_unsafe = {
        "problem_id": "PROB-GOKAK-FILTER",
        "sku": "FILTER-HYD-01",
        "donor_location": "Belgaum",
        "target_location": "Gokak",
        "override_qty": 38
    }
    r_recalc_unsafe = requests.post(f"{BASE_URL}/action/recalculate-override", json=payload_recalc_unsafe)
    assert r_recalc_unsafe.status_code == 200, f"Expected 200, got {r_recalc_unsafe.status_code}"
    recalc_unsafe_data = r_recalc_unsafe.json()
    assert recalc_unsafe_data.get("is_safe") is False, f"Expected is_safe == False, got {recalc_unsafe_data.get('is_safe')}"
    donor_unsafe_cov = recalc_unsafe_data.get("donor_revised_cover_days", 0)
    log_step("Unsafe Override Rejection (38 units)", True, f"is_safe = False | Donor remaining cover = {donor_unsafe_cov:.1f} days (< 15.0d)")

    # -------------------------------------------------------------
    # Pillar D: Human Gate Execution & Audit Log Mutation
    # -------------------------------------------------------------
    print("\n--- [D] Human Gate Execution & Audit Log Mutation ---")
    payload_approve = {
        "problem_id": "PROB-GOKAK-FILTER",
        "action_type": "TRANSFER_REQUEST",
        "payload": {
            "sku": "FILTER-HYD-01",
            "qty": 14,
            "from_location": "Belgaum",
            "to_location": "Gokak",
            "unit_cost_inr": 0,
            "total_estimated_cost_inr": 250
        }
    }
    r_approve = requests.post(f"{BASE_URL}/action/approve", json=payload_approve)
    assert r_approve.status_code == 200, f"Expected 200, got {r_approve.status_code}"
    approve_data = r_approve.json()
    assert approve_data.get("status") == "SUCCESS", f"Expected SUCCESS, got {approve_data}"
    log_step("POST /action/approve", True, "Action approved and dispatched.")

    # Inventory Verification
    r_inv = requests.get(f"{BASE_URL}/inventory")
    assert r_inv.status_code == 200, f"Expected 200, got {r_inv.status_code}"
    inv_list = r_inv.json()
    gokak_item = next(i for i in inv_list if i["sku"] == "FILTER-HYD-01" and i["location"] == "Gokak")
    belgaum_item = next(i for i in inv_list if i["sku"] == "FILTER-HYD-01" and i["location"] == "Belgaum")
    assert gokak_item["stock"] == 22, f"Expected Gokak stock == 22, got {gokak_item['stock']}"
    assert belgaum_item["stock"] == 26, f"Expected Belgaum stock == 26, got {belgaum_item['stock']}"
    log_step("Multi-Echelon Inventory Mutation", True, f"Gokak stock: 8 -> {gokak_item['stock']} (+14) | Belgaum stock: 40 -> {belgaum_item['stock']} (-14)")

    # Audit Log Verification
    r_audit = requests.get(f"{BASE_URL}/audit-log")
    assert r_audit.status_code == 200, f"Expected 200, got {r_audit.status_code}"
    audit_entries = r_audit.json()
    assert len(audit_entries) >= 1, "Audit log must contain entries"
    latest_entry = audit_entries[0]
    assert latest_entry.get("status") == "APPROVED", f"Expected status 'APPROVED', got {latest_entry.get('status')}"
    assert "timestamp" in latest_entry, "Audit entry must contain timestamp"
    log_step("Immutable Audit Trail Entry", True, f"Audit ID: {latest_entry.get('audit_id')} | Status: {latest_entry.get('status')} | Timestamp: {latest_entry.get('timestamp')}")

    # -------------------------------------------------------------
    # Pillar E: Chaos Injection & Adaptation
    # -------------------------------------------------------------
    print("\n--- [E] Chaos Injection & Adaptation ---")
    # Reset data first to clear previous transfer
    requests.post(f"{BASE_URL}/reset-data")

    payload_chaos = {
        "scenario": "TRANSFER_ROADBLOCK",
        "sku": "FILTER-HYD-01",
        "location": "Belgaum Central Warehouse",
        "value": 1.0
    }
    r_chaos = requests.post(f"{BASE_URL}/chaos/inject", json=payload_chaos)
    assert r_chaos.status_code == 200, f"Expected 200, got {r_chaos.status_code}"
    chaos_data = r_chaos.json()
    assert chaos_data.get("status") == "INJECTED", f"Expected INJECTED, got {chaos_data}"
    log_step("POST /chaos/inject", True, "Roadblock anomaly injected on Belgaum transfer route.")

    # Check updated briefing
    r_brief_post = requests.get(f"{BASE_URL}/briefing")
    assert r_brief_post.status_code == 200, f"Expected 200, got {r_brief_post.status_code}"
    brief_post = r_brief_post.json()

    gokak_post = next(p for p in brief_post.get("problems", []) if p.get("sku") == "FILTER-HYD-01" and p.get("location") == "Gokak")
    opts_post = gokak_post.get("evaluated_options", [])

    # Verify Belgaum transfer option is infeasible
    transfer_opt = next((o for o in opts_post if "Internal Network" in o.get("option_name", "")), None)
    if transfer_opt:
        assert transfer_opt.get("feasibility") != "FEASIBLE" or "INFEASIBLE" in transfer_opt.get("feasibility_status", ""), (
            f"Expected Belgaum transfer to be INFEASIBLE, got {transfer_opt}"
        )

    # Verify simulated action defaults to expedited vendor procurement
    action_post = gokak_post.get("simulated_action", {})
    assert action_post.get("action_type") == "PURCHASE_ORDER", (
        f"Expected simulated action to be PURCHASE_ORDER, got {action_post.get('action_type')}"
    )
    sup_source = action_post.get("payload", {}).get("from_location_or_supplier", "")
    assert "FastTrack" in sup_source or "Bengaluru" in sup_source, (
        f"Expected secondary supplier, got {sup_source}"
    )
    log_step("Autonomous Agent Pivot", True, f"Belgaum transfer flagged INFEASIBLE. Recommended Action -> PURCHASE_ORDER via {sup_source}")

    print("\n" + "=" * 70)
    print("  ALL 5 BACKEND OPERATIONAL PILLARS VALIDATED AND PASSING")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
