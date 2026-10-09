"""
Automated Test Suite for Kaveri Spares & Hydraulics Copilot
Validates domain arithmetic, problem detection, multi-option evaluation,
and the benchmark Gokak vs Belgaum scenario.
"""

import json
import os
import sys
from datetime import datetime, timedelta
import pytest
import pandas as pd
from fastapi.testclient import TestClient

# Ensure kaveri_copilot is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.domain_math import (
    calculate_daily_burn_rate,
    calculate_days_of_cover,
    calculate_stockout_gap,
    calculate_available_surplus,
    evaluate_sku_location,
    detect_demand_shift,
    evaluate_supplier_friction,
    validate_and_recalculate_transfer,
    compute_adaptive_velocity,
    calculate_donor_transfer_safety,
    generate_14day_projections,
    check_is_po_overdue,
    clamp_inventory_projection
)
from engine.decision_agent import (
    DecisionEngine,
    find_best_donor_location,
    find_best_donor_location_with_reservations
)
from engine.mock_data_gen import seed_all_data
from app.server import (
    app,
    PROCESSED_ACTION_HASHES,
    ACTIVE_TRANSFER_RESERVATIONS,
    ACTIVE_CHAOS_EVENTS
)


@pytest.fixture(autouse=True)
def reset_test_data():
    """Ensure clean benchmark data before each test."""
    data_dir = os.path.join(BASE_DIR, "data")
    seed_all_data(data_dir)
    audit_file = os.path.join(data_dir, "audit_log.json")
    if os.path.exists(audit_file):
        os.remove(audit_file)
    PROCESSED_ACTION_HASHES.clear()
    ACTIVE_TRANSFER_RESERVATIONS.clear()
    ACTIVE_CHAOS_EVENTS.clear()



class TestDomainMathEngine:
    def test_burn_rate_and_cover(self):
        # 120 sold in 30 days = 4.0/day
        sales = [{"sku": "FILTER-HYD-01", "location": "Gokak", "qty_sold": 4} for _ in range(30)]
        burn = calculate_daily_burn_rate(sales, "FILTER-HYD-01", "Gokak", 30)
        assert burn == 4.0

        # Stock = 8, Burn = 4.0 -> Cover = 2.0 days
        cover = calculate_days_of_cover(8, burn)
        assert cover == 2.0

        # Zero stock
        assert calculate_days_of_cover(0, burn) == 0.0

        # Zero sales, positive stock -> 999.0 (infinity/dead stock)
        assert calculate_days_of_cover(15, 0.0) == 999.0

    def test_stockout_gap(self):
        # Lead time 7 days, cover 2.0 days -> Gap = 5.0 days
        gap = calculate_stockout_gap(2.0, 7)
        assert gap == 5.0

        # Cover exceeds lead time -> Gap = 0.0
        assert calculate_stockout_gap(10.0, 7) == 0.0

    def test_available_surplus(self):
        # Belgaum has 40 units, burn rate 0.5. To retain 15 days, needs 8 units. Surplus = 32.
        surplus = calculate_available_surplus(stock=40, burn_rate=0.5, min_retained_cover_days=15)
        assert surplus >= 32


class TestGokakBelgaumBenchmarkScenario:
    def test_gokak_filter_stockout_and_belgaum_transfer(self):
        """
        Validates the Hackathon Challenge Benchmark:
        - SKU FILTER-HYD-01 at Gokak flagged as CRITICAL.
        - Evaluates both Belgaum transfer and expedited supplier options.
        - Recommended action is an inter-store transfer of 12-16 units from Belgaum to Gokak.
        - Payload contains all required fields: from, to, sku, qty, cost.
        """
        engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
        result = engine.run_agentic_pipeline()

        # Find Gokak problem
        gokak_problems = [
            p for p in result["problems"]
            if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"
        ]
        assert len(gokak_problems) == 1, "Gokak FILTER-HYD-01 problem must be detected"
        gokak_p = gokak_problems[0]

        # 1. Flagged as CRITICAL
        assert gokak_p["severity"] == "CRITICAL", f"Expected CRITICAL severity, got {gokak_p['severity']}"
        assert gokak_p["category"] == "IMMINENT_STOCKOUT"

        # Check metrics
        metrics = gokak_p["domain_metrics"]
        assert metrics["current_stock"] == 8
        assert metrics["daily_burn_rate"] == 4.0
        assert metrics["days_of_cover"] == 2.0
        assert metrics["primary_supplier_lead_time_days"] == 7
        assert metrics["stockout_gap_days"] == 5.0

        # 2. Agent evaluates both Belgaum transfer and expedited supplier
        options = gokak_p["evaluated_options"]
        opt_names = [o["option_name"] for o in options]
        assert any("Internal Network" in name for name in opt_names), "Must evaluate network transfer"
        assert any("Expedited Secondary" in name for name in opt_names), "Must evaluate expedited supplier"

        transfer_opt = [o for o in options if "Internal Network" in o["option_name"]][0]
        assert "Belgaum" in transfer_opt["source"]
        assert transfer_opt["delivery_time_days"] == 1
        assert transfer_opt["estimated_cost_inr"] == 250.0
        assert transfer_opt["feasibility"] == "FEASIBLE"

        expedited_opt = [o for o in options if "Expedited Secondary" in o["option_name"]][0]
        assert "FastTrack" in expedited_opt["source"] or "Bengaluru" in expedited_opt["source"]
        assert expedited_opt["delivery_time_days"] == 3
        assert expedited_opt["feasibility"] == "FEASIBLE"

        # 3. Recommended action is an inter-store transfer of 12-16 units from Belgaum to Gokak
        action = gokak_p["simulated_action"]
        assert action["action_type"] == "TRANSFER_REQUEST"
        assert action["human_approval_required"] is True

        payload = action["payload"]
        assert payload["sku"] == "FILTER-HYD-01"
        assert "Belgaum" in payload["from_location_or_supplier"]
        assert payload["to_location"] == "Gokak"
        assert 12 <= payload["qty"] <= 16, f"Transfer quantity must be between 12 and 16 units, got {payload['qty']}"

        # 4. Drafted transfer request payload contains all required fields
        assert "from_location_or_supplier" in payload
        assert "to_location" in payload
        assert "sku" in payload
        assert "qty" in payload
        assert "total_estimated_cost_inr" in payload
        assert payload["total_estimated_cost_inr"] == 250.0
        assert payload["urgency"] == "IMMEDIATE"


class TestMultiCategoryDetection:
    def test_capital_trap_detection(self):
        """Validates detection of dead stock / capital trap at Bagalkot."""
        engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
        result = engine.run_agentic_pipeline()

        bagalkot_problems = [
            p for p in result["problems"]
            if p["sku"] == "VALVE-CTRL-02" and p["location"] == "Bagalkot"
        ]
        assert len(bagalkot_problems) >= 1
        p = bagalkot_problems[0]
        assert p["category"] in ("CAPITAL_TRAP", "SLOW_MOVING_STOCK")
        assert p["domain_metrics"]["daily_burn_rate"] == 0.0
        assert p["simulated_action"]["action_type"] == "TRANSFER_REQUEST"

    def test_overdue_po_detection(self):
        """Validates detection of overdue PO at Hubli."""
        engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
        result = engine.run_agentic_pipeline()

        hubli_pos = [
            p for p in result["problems"]
            if p["sku"] == "PUMP-GEAR-03" and p["location"] == "Hubli" and p["category"] == "OVERDUE_PO"
        ]
        assert len(hubli_pos) >= 1
        p = hubli_pos[0]
        assert p["category"] == "OVERDUE_PO"
        assert p["simulated_action"]["action_type"] == "SUPPLIER_EXPEDITE_NOTICE"


class TestFastAPIFlow:
    def test_briefing_and_approval_api(self):
        client = TestClient(app)

        # 1. Health
        res = client.get("/health")
        assert res.status_code == 200

        # 2. Briefing
        res = client.get("/briefing")
        assert res.status_code == 200
        data = res.json()
        assert "summary" in data
        assert "problems" in data
        assert data["summary"]["critical_actions_required"] >= 1

        # 3. Approve Action
        gokak_p = [p for p in data["problems"] if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"][0]
        approval_body = {
            "problem_id": gokak_p["problem_id"],
            "action_type": gokak_p["simulated_action"]["action_type"],
            "payload": gokak_p["simulated_action"]["payload"],
            "approved_by": "Ramesh Kulkarni",
            "notes": "Fast-tracked morning transfer"
        }
        approve_res = client.post("/action/approve", json=approval_body)
        assert approve_res.status_code == 200
        res_json = approve_res.json()
        assert res_json["status"] == "SUCCESS"

        # 4. Verify inventory was updated
        inv_res = client.get("/inventory")
        assert inv_res.status_code == 200
        inv_data = inv_res.json()
        gokak_inv = [i for i in inv_data if i["sku"] == "FILTER-HYD-01" and i["location"] == "Gokak"][0]
        # Initially 8, transferred 14 -> should now be 22
        assert gokak_inv["stock"] == 8 + gokak_p["simulated_action"]["payload"]["qty"]

        # 5. Check audit log
        audit_res = client.get("/audit-log")
        assert audit_res.status_code == 200
        audit_data = audit_res.json()
        assert len(audit_data) >= 1
        assert audit_data[0]["approved_by"] == "Ramesh Kulkarni"

    def test_reject_action_api(self):
        client = TestClient(app)
        rej_body = {
            "problem_id": "PRB-20261009-02",
            "rejected_by": "Ramesh Kulkarni",
            "reason": "Holding stock for impending planned overhaul"
        }
        res = client.post("/action/reject", json=rej_body)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "REJECTED"

        audit_res = client.get("/audit-log")
        audit_data = audit_res.json()
        assert any(a["problem_id"] == "PRB-20261009-02" and a["status"] == "REJECTED" for a in audit_data)

    def test_chaos_inject_api(self):
        client = TestClient(app)
        chaos_body = {
            "scenario": "DEMAND_SPIKE",
            "sku": "FILTER-HYD-01",
            "location": "Gokak"
        }
        res = client.post("/chaos/inject", json=chaos_body)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "INJECTED"
        assert "updated_briefing" in data
        assert data["active_events_count"] >= 1


class TestExtendedChallengeFeatures:
    def test_demand_surge_detection(self):
        """Verifies 7-day velocity surge is classified with severity HIGH."""
        curr_dt = datetime.strptime("2026-10-09", "%Y-%m-%d")
        sales = []
        for d in range(30):
            dt = curr_dt - timedelta(days=d)
            qty = 8 if d < 7 else 2
            sales.append({
                "date": dt.strftime("%Y-%m-%d"),
                "sku": "FILTER-HYD-01",
                "location": "Gokak",
                "qty_sold": qty
            })
        shift = detect_demand_shift(sales, "FILTER-HYD-01", "Gokak", "2026-10-09")
        assert shift["shift_type"] == "DEMAND_SURGE"
        assert shift["v_short"] >= 2.0
        assert shift["ratio"] >= 1.8

    def test_supplier_moq_friction(self):
        """Verifies that a supplier requiring MOQ 100 for a 10-unit stockout is flagged as INFEASIBLE_MOQ."""
        supplier = {
            "supplier": "Heavy Bulk Industrial",
            "sku": "VALVE-CTRL-02",
            "price": 25000.0,
            "lead_time_days": 2,
            "moq": 100
        }
        res = evaluate_supplier_friction(
            supplier=supplier,
            baseline_price=24500.0,
            Q_needed=10,
            days_of_cover=4.0
        )
        assert res["feasibility_status"] == "INFEASIBLE_MOQ"
        assert res["moq_penalty"] is True

    def test_human_override_recalculation(self):
        """Asserts that requesting 20 units instead of 14 adjusts Gokak cover to 7.0 days while keeping Belgaum cover above 15 days."""
        with open(os.path.join(BASE_DIR, "data", "inventory.json"), "r") as f:
            inv = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "sales.json"), "r") as f:
            sales = json.load(f)

        res = validate_and_recalculate_transfer(
            from_loc="Belgaum",
            to_loc="Gokak",
            sku="FILTER-HYD-01",
            requested_qty=20,
            inventory=inv,
            sales=sales
        )
        assert res["is_valid"] is True
        assert res["recipient_cover_days"] == 7.0
        assert res["donor_cover_days"] >= 15.0

    def test_chaos_injection_resilience(self):
        """Injects a transfer block and verifies the agent automatically falls back to secondary expedited procurement."""
        engine = DecisionEngine(
            data_dir=os.path.join(BASE_DIR, "data"),
            blocked_routes=[{"from": "Belgaum", "to": "Gokak", "sku": "FILTER-HYD-01"}]
        )
        result = engine.run_agentic_pipeline()
        gokak_p = [p for p in result["problems"] if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"][0]

        action = gokak_p["simulated_action"]
        assert action["action_type"] == "PURCHASE_ORDER"
        assert "FastTrack" in action["payload"]["from_location_or_supplier"] or "Bengaluru" in action["payload"]["from_location_or_supplier"]

    def test_adaptive_velocity_surge(self):
        """Assert that a SKU with doubling 7-day sales triggers ACCELERATING and uses v_recent."""
        curr_dt = datetime.strptime("2026-10-09", "%Y-%m-%d")
        sales = []
        for d in range(30):
            dt = curr_dt - timedelta(days=d)
            qty = 4 if d < 7 else 2
            sales.append({
                "date": dt.strftime("%Y-%m-%d"),
                "sku": "FILTER-HYD-01",
                "location": "Gokak",
                "qty_sold": qty
            })
        res = compute_adaptive_velocity(sales, "FILTER-HYD-01", "Gokak", current_stock=20, primary_lead_time=7)
        assert res["trend_label"] == "ACCELERATING"
        assert res["v_predicted"] == res["v_recent"]
        assert res["v_recent"] > res["v_baseline"]

    def test_donor_safety_threshold(self):
        """Assert that transferring 30 units when donor stock is 35 (with v=1.0) is rejected due to violating the 15-day safety margin."""
        safety = calculate_donor_transfer_safety(donor_stock=35, donor_v=1.0, transfer_qty=30)
        assert safety["is_safe"] is False
        assert safety["remaining_cover_days"] == 5.0
        assert safety["max_safe_transfer_qty"] == 20

    def test_override_recalculation(self):
        """Assert that changing Gokak transfer from 14 to 18 units properly adjusts projected cover and cost."""
        client = TestClient(app)
        body = {
            "problem_id": "PRB-20261009-01",
            "sku": "FILTER-HYD-01",
            "donor_location": "Belgaum",
            "target_location": "Gokak",
            "override_qty": 18
        }
        res = client.post("/action/recalculate-override", json=body)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["is_safe"] is True
        assert data["revised_cost_inr"] == 250.0
        assert data["target_revised_cover_days"] == 6.5

    def test_gokak_benchmark_execution(self):
        """Verify the primary hackathon scenario: Gokak filter stockout evaluates Belgaum transfer vs. rush vendor and selects Belgaum."""
        engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
        result = engine.run_agentic_pipeline()
        gokak_p = [p for p in result["problems"] if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"][0]

        assert gokak_p["severity"] == "CRITICAL"
        assert gokak_p["simulated_action"]["action_type"] == "TRANSFER_REQUEST"
        assert "Belgaum" in gokak_p["simulated_action"]["payload"]["from_location_or_supplier"]
        assert gokak_p["simulated_action"]["payload"]["to_location"] == "Gokak"
        assert 12 <= gokak_p["simulated_action"]["payload"]["qty"] <= 16

    def test_donor_safety_margin(self):
        """Transfer proposals that leave a donor store with <15 days of cover are rejected."""
        safety = calculate_donor_transfer_safety(donor_stock=35, donor_v=1.0, transfer_qty=30)
        assert safety["is_safe"] is False
        assert safety["remaining_cover_days"] == 5.0
        assert safety["max_safe_transfer_qty"] == 20

        # Safe transfer
        safety_ok = calculate_donor_transfer_safety(donor_stock=35, donor_v=1.0, transfer_qty=10)
        assert safety_ok["is_safe"] is True
        assert safety_ok["remaining_cover_days"] == 25.0

    def test_benchmark_gokak_belgaum(self):
        """Gokak hydraulic filter stockout selects a Belgaum transfer of 12–16 units over expedited vendor procurement."""
        engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
        result = engine.run_agentic_pipeline()
        gokak_p = [p for p in result["problems"] if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"][0]

        assert gokak_p["severity"] == "CRITICAL"
        assert gokak_p["category"] == "IMMINENT_STOCKOUT"
        assert gokak_p["simulated_action"]["action_type"] == "TRANSFER_REQUEST"
        assert "Belgaum" in gokak_p["simulated_action"]["payload"]["from_location_or_supplier"]
        assert gokak_p["simulated_action"]["payload"]["to_location"] == "Gokak"
        assert 12 <= gokak_p["simulated_action"]["payload"]["qty"] <= 16

    def test_forward_projection_math(self):
        """Day-by-day trajectory curves correctly reflect daily burn rates and planned delivery arrivals."""
        proj = generate_14day_projections(
            current_stock=8,
            daily_burn=4.0,
            transfer_qty=14,
            primary_lead_time=7,
            expedited_lead_time=3,
            expedited_qty=20,
            transfer_arrival_day=1
        )
        assert len(proj["days"]) == 15
        assert len(proj["status_quo"]) == 15
        assert len(proj["expedited"]) == 15
        assert len(proj["transfer"]) == 15

        # Day 0: start with 8, daily burn 4 -> stock = 4.0
        assert proj["status_quo"][0] == 4.0
        assert proj["transfer"][0] == 4.0
        assert proj["expedited"][0] == 4.0

        # Day 1: Transfer arrives (+14)
        assert proj["transfer"][1] == 14.0
        # Status quo reaches 0
        assert proj["status_quo"][1] == 0.0

        # Day 3: Expedited PO arrives (+20) -> 0 + 20 - 4 = 16.0
        assert proj["expedited"][3] == 16.0

        # Day 7: Primary vendor arrives (+25) -> 0 + 25 - 4 = 21.0
        assert proj["status_quo"][7] == 21.0

        # Floor constraint: stock values never negative
        assert min(proj["status_quo"]) >= 0.0
        assert min(proj["expedited"]) >= 0.0
        assert min(proj["transfer"]) >= 0.0

    def test_human_override_flow(self):
        """Overriding a transfer quantity updates destination cover while maintaining donor constraints."""
        with open(os.path.join(BASE_DIR, "data", "inventory.json"), "r") as f:
            inv = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "sales.json"), "r") as f:
            sales = json.load(f)

        # Valid override to 20 units
        res = validate_and_recalculate_transfer(
            from_loc="Belgaum",
            to_loc="Gokak",
            sku="FILTER-HYD-01",
            requested_qty=20,
            inventory=inv,
            sales=sales
        )
        assert res["is_valid"] is True
        assert res["recipient_cover_days"] == 7.0
        assert res["donor_cover_days"] >= 15.0

        # Excessive override violating donor safety
        res_unsafe = validate_and_recalculate_transfer(
            from_loc="Belgaum",
            to_loc="Gokak",
            sku="FILTER-HYD-01",
            requested_qty=35,
            inventory=inv,
            sales=sales
        )
        assert res_unsafe["is_valid"] is False
        assert res_unsafe["donor_cover_days"] < 15.0


# Standalone module-level test functions for direct runner execution
def test_adaptive_velocity_surge():
    TestExtendedChallengeFeatures().test_adaptive_velocity_surge()


def test_donor_safety_margin():
    TestExtendedChallengeFeatures().test_donor_safety_margin()


def test_benchmark_gokak_belgaum():
    TestExtendedChallengeFeatures().test_benchmark_gokak_belgaum()


def test_forward_projection_math():
    TestExtendedChallengeFeatures().test_forward_projection_math()


def test_human_override_flow():
    TestExtendedChallengeFeatures().test_human_override_flow()


def test_zero_sales_division_guard():
    """Verify that zero sales history produces no division errors and flags dead stock."""
    empty_sales = pd.DataFrame(columns=["date", "sku", "location", "qty_sold"])
    res = compute_adaptive_velocity(empty_sales, "NEW-PART-01", "Dharwad", current_stock=10, primary_lead_time=7)
    
    assert res["v_baseline"] == 0.0
    assert res["v_recent"] == 0.0
    assert res["trend_factor"] == 1.0
    assert res["trend_label"] == "STABLE"
    assert res["days_of_cover"] == 999.0
    assert res["stockout_gap_days"] == 0.0


def test_dynamic_donor_selection_non_belgaum():
    """Verify donor matching selects a non-Belgaum hub if it possesses the surplus."""
    mock_inv = pd.DataFrame([
        {"sku": "SEAL-XYZ", "location": "Nippani", "current_stock": 2},
        {"web_id": 1, "sku": "SEAL-XYZ", "location": "Belgaum Central Warehouse", "current_stock": 5},
        {"web_id": 2, "sku": "SEAL-XYZ", "location": "Hubli Regional Warehouse", "current_stock": 50}
    ])
    mock_sales = pd.DataFrame([
        {"sku": "SEAL-XYZ", "location": "Belgaum Central Warehouse", "qty_sold": 1.0},
        {"sku": "SEAL-XYZ", "location": "Hubli Regional Warehouse", "qty_sold": 0.5}
    ])
    
    donor = find_best_donor_location(mock_inv, mock_sales, "SEAL-XYZ", "Nippani", needed_qty=10)
    assert donor is not None
    assert donor["donor_location"] == "Hubli Regional Warehouse"
    assert donor["remaining_cover_days"] >= 15.0


def test_dynamic_forward_projection_lead_times():
    """Verify that forward projections plot delivery arrivals on dynamic lead time days."""
    proj = generate_14day_projections(
        current_stock=5,
        daily_burn=2.0,
        transfer_qty=10,
        primary_lead_time=10,
        expedited_lead_time=4,
        replenishment_order_qty=30,
        transfer_arrival_day=1
    )
    assert len(proj["days"]) == 15
    # Expedited step-up must occur on Day 4
    assert proj["expedited"][4] > proj["expedited"][3]
    # Primary step-up must occur on Day 10
    assert proj["status_quo"][10] > proj["status_quo"][9]


def test_telemetry_endpoint_404_on_nonexistent():
    """Verify that the FastAPI endpoints return HTTP 404 for non-existent entities rather than silently defaulting to the benchmark scenario."""
    client = TestClient(app)
    response = client.get("/api/telemetry?problem_id=PRB-NONEXISTENT-99")
    assert response.status_code == 404
    response2 = client.get("/api/telemetry?sku=UNKNOWN-SKU&location=UNKNOWN-LOC")
    assert response2.status_code == 404


def test_simulation_date_overdue_anchor():
    """Verify overdue detection uses explicit simulation date rather than system clock."""
    # Delivery date is 2026-10-05, sim date is 2026-10-09 -> Must be overdue
    assert check_is_po_overdue("2026-10-05", "PENDING", simulation_date_str="2026-10-09") is True
    # Delivery date is 2026-10-12, sim date is 2026-10-09 -> Not overdue
    assert check_is_po_overdue("2026-10-12", "PENDING", simulation_date_str="2026-10-09") is False
    # Delivered PO is never overdue
    assert check_is_po_overdue("2026-10-05", "DELIVERED", simulation_date_str="2026-10-09") is False


def test_negative_stock_clamping_and_lost_units():
    """Ensure projection values never fall below 0.0 even under severe demand spikes."""
    res = clamp_inventory_projection(starting_stock=5.0, daily_burn=4.0, horizon_days=5)
    # Day 0: 5 - 4 = 1.0; Day 1: 1 - 4 = 0.0 (lost: 3.0); Day 2: lost: +4 = 7.0
    assert min(res["projected_stock"]) == 0.0
    assert res["projected_stock"] == [1.0, 0.0, 0.0, 0.0, 0.0]
    assert res["unmet_demand_lost_units"][-1] == 15.0


def test_shared_donor_reservation_deduction():
    """Verify candidate with gross surplus is rejected if existing reservations leave <15d cover."""
    mock_inv = pd.DataFrame([{"sku": "SEAL-01", "location": "Belgaum Central Warehouse", "current_stock": 20}])
    mock_sales = pd.DataFrame([{"sku": "SEAL-01", "location": "Belgaum Central Warehouse", "qty_sold": 1.0}])
    
    # 20 stock - 10 already reserved = 10 effective stock.
    # Needing 5 leaves 5 units -> 5 / 1.0 = 5 days cover (< 15d min) -> must be rejected
    donor = find_best_donor_location_with_reservations(
        mock_inv, mock_sales, "SEAL-01", "Gokak", needed_qty=5,
        active_reservations={"Belgaum Central Warehouse:SEAL-01": 10}
    )
    assert donor is None


def test_approval_idempotency_duplicate_conflict():
    """Verify that duplicate POST /action/approve calls return HTTP 409 Conflict."""
    client = TestClient(app)
    body = {
        "problem_id": "PRB-TEST-IDEMPOTENT-01",
        "action_type": "TRANSFER_REQUEST",
        "payload": {
            "sku": "FILTER-HYD-01",
            "from_location": "Belgaum",
            "to_location": "Gokak",
            "qty": 5
        }
    }
    res1 = client.post("/action/approve", json=body)
    assert res1.status_code == 200
    res2 = client.post("/action/approve", json=body)
    assert res2.status_code == 409


def test_approval_safety_buffer_violation_400():
    """Verify that transfer attempting to over-draft donor below 15 days returns HTTP 400."""
    client = TestClient(app)
    body = {
        "problem_id": "PRB-TEST-UNSAFE-01",
        "action_type": "TRANSFER_REQUEST",
        "payload": {
            "sku": "FILTER-HYD-01",
            "from_location": "Belgaum",
            "to_location": "Gokak",
            "qty": 35  # Belgaum has 40 stock, burn 2.0 -> needs 30 safe reserve. Transferring 35 leaves 5 (2.5d cover < 15.0d)
        }
    }
    res = client.post("/action/approve", json=body)
    assert res.status_code == 400
    assert "Safety buffer violation" in res.json()["detail"] or "15.0" in res.json()["detail"]



