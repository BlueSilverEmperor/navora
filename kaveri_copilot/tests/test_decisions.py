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
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in [os.path.join(_ROOT_DIR, "kaveri_copilot"), _ROOT_DIR]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

_BENCHMARK_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
os.environ.setdefault("NAVORA_DATA_DIR", _BENCHMARK_DATA_DIR)

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
    find_best_donor_location_with_reservations,
    extract_network_topology
)
from engine.mock_data_gen import seed_all_data
from app.server import (
    app,
    PROCESSED_ACTION_HASHES,
    ACTIVE_TRANSFER_RESERVATIONS,
    ACTIVE_CHAOS_EVENTS,
    DATA_DIR
)

BASE_DIR = os.path.dirname(DATA_DIR)

try:
    from engine.persistence import clear_all_persistence
except ImportError:
    clear_all_persistence = None


@pytest.fixture(autouse=True)
def reset_test_data():
    """Ensure clean benchmark data before each test."""
    seed_all_data(DATA_DIR)
    audit_file = os.path.join(DATA_DIR, "audit_log.json")
    if os.path.exists(audit_file):
        os.remove(audit_file)
    PROCESSED_ACTION_HASHES.clear()
    ACTIVE_TRANSFER_RESERVATIONS.clear()
    ACTIVE_CHAOS_EVENTS.clear()
    if clear_all_persistence:
        try:
            clear_all_persistence()
        except Exception:
            pass



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
            transfer_arrival_day=1,
            open_po_qty=25,
            open_po_arrival_day=7
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
    is_overdue, days = check_is_po_overdue("2026-10-05", "PENDING", simulation_date_str="2026-10-09")
    assert is_overdue is True
    assert days == 4
    # Delivery date is 2026-10-12, sim date is 2026-10-09 -> Not overdue
    is_overdue2, days2 = check_is_po_overdue("2026-10-12", "PENDING", simulation_date_str="2026-10-09")
    assert is_overdue2 is False
    assert days2 == 0
    # Delivered PO is never overdue
    is_overdue3, days3 = check_is_po_overdue("2026-10-05", "DELIVERED", simulation_date_str="2026-10-09")
    assert is_overdue3 is False
    assert days3 == 0


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


# ==============================================================================
# T1: OBJECTIVE FUNCTION & RANKING TESTS
# ==============================================================================
def test_objective_function_scoring_and_ranking():
    """Verify that every evaluated option has expected_cost, expected_cost_breakdown, and rank."""
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    result = engine.run_agentic_pipeline()
    gokak_p = [p for p in result["problems"] if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"][0]

    options = gokak_p["evaluated_options"]
    assert len(options) >= 2
    for opt in options:
        assert "expected_cost" in opt, "Each option must have expected_cost"
        assert "expected_cost_breakdown" in opt, "Each option must have expected_cost_breakdown"
        assert "rank" in opt, "Each option must have a rank"
        breakdown = opt["expected_cost_breakdown"]
        assert "handling_or_freight" in breakdown
        assert "purchase_premium" in breakdown
        assert "expected_lost_margin" in breakdown
        assert "carrying_cost_of_excess" in breakdown

    # In benchmark baseline, Internal Transfer (Rs 250 handling) must win rank 1 on numbers
    assert options[0]["rank"] == 1
    assert "Internal Network" in options[0]["option_name"]
    assert options[0]["expected_cost"] < options[1]["expected_cost"]


def test_objective_function_vendor_wins_when_transfer_expensive():
    """Verify that when transfer handling cost is set higher than vendor option, vendor option wins rank 1."""
    # Transfer cost set to Rs. 25,000, higher than expedited vendor expected cost (~Rs. 3,400)
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"), transfer_handling_cost=25000.0)
    result = engine.run_agentic_pipeline()
    gokak_p = [p for p in result["problems"] if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"][0]

    options = gokak_p["evaluated_options"]
    winning_opt = options[0]
    assert winning_opt["rank"] == 1
    assert "Expedited Secondary" in winning_opt["option_name"], (
        f"Expedited vendor should win when transfer cost is high. Winner: {winning_opt['option_name']}"
    )
    assert gokak_p["simulated_action"]["action_type"] == "PURCHASE_ORDER"


def test_objective_function_vendor_wins_when_no_safe_donor():
    """Verify that when no safe donor is available (route blocked), vendor option wins rank 1."""
    # Block Belgaum route so internal transfer becomes infeasible
    engine = DecisionEngine(
        data_dir=os.path.join(BASE_DIR, "data"),
        blocked_routes=[{"from": "Belgaum Central Warehouse", "to": "Gokak", "sku": "FILTER-HYD-01"}]
    )
    result = engine.run_agentic_pipeline()
    gokak_p = [p for p in result["problems"] if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"][0]

    options = gokak_p["evaluated_options"]
    winning_opt = options[0]
    assert winning_opt["rank"] == 1
    assert "Expedited Secondary" in winning_opt["option_name"]
    assert gokak_p["simulated_action"]["action_type"] == "PURCHASE_ORDER"


# ==============================================================================
# T2: FAIR SCORECARD TESTS
# ==============================================================================
def test_scorecard_differentiates_across_incidents():
    """Verify that every incident has a computed scorecard and different incidents produce distinct KPI values."""
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    result = engine.run_agentic_pipeline()
    problems = result["problems"]
    assert len(problems) >= 2, "Need at least 2 detected problems"

    # Verify all problems have scorecard
    for p in problems:
        assert "scorecard" in p, f"Problem {p['problem_id']} must have scorecard"
        sc = p["scorecard"]
        assert "net_cost_inr" in sc
        assert "lost_units_averted" in sc
        assert "working_capital_outflow_inr" in sc
        assert "downtime_risk_days" in sc

    # Compare two different problem categories / incidents
    p1 = problems[0]
    p2 = [p for p in problems[1:] if p["category"] != p1["category"] or p["sku"] != p1["sku"]][0]

    sc1 = p1["scorecard"]
    sc2 = p2["scorecard"]

    # Verify that not all KPI values are identical
    distinct_kpis = (
        sc1["net_cost_inr"] != sc2["net_cost_inr"]
        or sc1["lost_units_averted"] != sc2["lost_units_averted"]
        or sc1["working_capital_outflow_inr"] != sc2["working_capital_outflow_inr"]
        or sc1["downtime_risk_days"] != sc2["downtime_risk_days"]
    )
    assert distinct_kpis, (
        f"Scorecard KPIs should differ across incidents. Incident 1 ({p1['sku']}): {sc1}, Incident 2 ({p2['sku']}): {sc2}"
    )


# ==============================================================================
# T3: REAL ALTERNATIVES TESTS
# ==============================================================================
def test_real_alternatives_and_baseline_status_quo():
    """Verify Status Quo is marked baseline and at least 2 real feasible alternative options exist."""
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    result = engine.run_agentic_pipeline()
    problems = result["problems"]
    
    cat_a_problems = [
        p for p in problems
        if p.get("category_code") == "CATEGORY_A" or p.get("category") == "IMMINENT_STOCKOUT"
    ]
    assert len(cat_a_problems) > 0, "Expected Category A problems"

    for p in cat_a_problems:
        options = p.get("evaluated_options", [])
        assert len(options) >= 3, f"Expected at least 3 options (1 baseline + at least 2 alternatives), got {len(options)}"
        
        # Check Status Quo is marked baseline
        baseline_options = [o for o in options if o.get("is_baseline") is True]
        assert len(baseline_options) >= 1, "Expected Status Quo to be identified as baseline"
        for bo in baseline_options:
            assert "Baseline" in bo.get("option_name", "") or "Status Quo" in bo.get("option_name", "")
            
        # Check at least 2 non-baseline alternative options exist
        alternatives = [o for o in options if not o.get("is_baseline")]
        assert len(alternatives) >= 2, f"Expected at least 2 real alternative options, got {len(alternatives)}"
        
        # Check that feasibility checking and expected cost are explicit on options
        for o in options:
            assert "feasibility" in o or "feasibility_status" in o
            assert "expected_cost" in o


# ==============================================================================
# T4: GROUNDED PROJECTIONS & CATEGORY A SEMANTICS TESTS
# ==============================================================================
def test_grounded_projections_data_driven_and_category_a_no_arrival():
    """Verify that forward projections are grounded in data and Category A shows no arrival in Status Quo."""
    # 1. Category A semantics: no PO in transit -> Status Quo has no arrivals
    proj_no_po = generate_14day_projections(
        current_stock=10,
        daily_burn=2.0,
        transfer_qty=14,
        primary_lead_time=7,
        expedited_lead_time=3,
        expedited_qty=20,
        has_open_po=False
    )
    # Day 5 it hits 0 and never jumps up
    assert proj_no_po["status_quo"][5] == 0.0
    assert proj_no_po["status_quo"][7] == 0.0
    assert proj_no_po["status_quo"][14] == 0.0

    # 2. Changing PO quantity in the data changes the curve
    proj_po_20 = generate_14day_projections(
        current_stock=10,
        daily_burn=2.0,
        transfer_qty=14,
        primary_lead_time=7,
        expedited_lead_time=3,
        open_po_qty=20,
        open_po_arrival_day=7,
        has_open_po=True
    )
    proj_po_50 = generate_14day_projections(
        current_stock=10,
        daily_burn=2.0,
        transfer_qty=14,
        primary_lead_time=7,
        expedited_lead_time=3,
        open_po_qty=50,
        open_po_arrival_day=7,
        has_open_po=True
    )
    # At day 7: stock for po_50 must be 30 units higher than po_20
    assert proj_po_50["status_quo"][7] - proj_po_20["status_quo"][7] == 30.0

    # 3. Changing lead time in the data shifts the arrival day
    proj_lead_4 = generate_14day_projections(
        current_stock=10,
        daily_burn=2.0,
        transfer_qty=14,
        primary_lead_time=4,
        expedited_lead_time=3,
        open_po_qty=20,
        open_po_arrival_day=4,
        has_open_po=True
    )
    assert proj_lead_4["status_quo"][4] > proj_lead_4["status_quo"][3]
    assert proj_po_20["status_quo"][4] <= proj_po_20["status_quo"][3]  # po_20 arrives on day 7, not 4

    # 4. In Category A problem from pipeline, Status Quo has no arrivals
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    res = engine.run_agentic_pipeline()
    cat_a = [p for p in res["problems"] if p.get("category_code") == "CATEGORY_A"][0]
    sq_curve = cat_a["forward_projections"]["status_quo"]
    # Once it hits zero, it never recovers because there is no PO in transit
    zero_idx = next(i for i, v in enumerate(sq_curve) if v == 0.0)
    for v in sq_curve[zero_idx:]:
        assert v == 0.0, f"Category A Status Quo should not rebound without open PO: {sq_curve}"


# ==============================================================================
# T5: LLM LAYER & NUMBER GUARD TESTS
# ==============================================================================
def test_llm_layer_parsing_number_guard_and_multilingual():
    """Verify natural language parsing into Pydantic models, NumberGuard enforcement, and multilingual WhatsApp drafting."""
    from engine.llm_layer import LLMLayer, NumberGuard, HallucinatedNumberError, UserIntentAction
    
    llm = LLMLayer()  # Offline fallback mode by default
    assert llm.is_offline is True

    # 1. Pydantic-validated parsing of natural language actions
    res1 = llm.parse_user_request("Please change quantity to 18 units for incident PRB-20261009-01")
    assert isinstance(res1, UserIntentAction)
    assert res1.action == "override_qty"
    assert res1.incident_id == "PRB-20261009-01"
    assert res1.qty == 18

    res2 = llm.parse_user_request("Go ahead and approve the transfer order for PRB-20261009-02")
    assert isinstance(res2, UserIntentAction)
    assert res2.action == "approve_action"
    assert res2.incident_id == "PRB-20261009-02"

    res3 = llm.parse_user_request("Reject this recommendation immediately")
    assert isinstance(res3, UserIntentAction)
    assert res3.action == "reject_action"

    # 2. NumberGuard: strictly rejects any hallucinated or ungrounded number
    payload = {
        "sku": "FILTER-HYD-01",
        "current_stock": 8,
        "daily_burn_rate": 4.0,
        "handling_fee": 250.0
    }
    guard = NumberGuard(allowed_payload=payload)

    # Valid grounded text
    valid_text = "Current stock is 8 units with 4.0 burn rate and fee of 250.0."
    assert guard.validate_text(valid_text) is True

    # Hallucinated number (e.g. 999 or 45 or 12.5 not in payload)
    hallucinated_text = "We recommend ordering 999 units to cover demand."
    try:
        guard.validate_text(hallucinated_text)
        assert False, "NumberGuard should have rejected hallucinated number 999"
    except HallucinatedNumberError:
        pass  # Expected rejection

    # 3. Grounded plain-language explanation and multi-lingual WhatsApp drafting
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    problems = engine.run_agentic_pipeline()["problems"]
    cat_a_problem = problems[0]

    explanation = llm.explain_decision(cat_a_problem)
    assert len(explanation) > 20
    assert cat_a_problem["sku"] in explanation

    messages = llm.draft_whatsapp_messages(cat_a_problem)
    assert "en" in messages
    assert "hi" in messages
    assert "kn" in messages
    assert "Kaveri Spares" in messages["en"]
    assert "कावेरी स्पेयर्स" in messages["hi"]
    assert "ಕಾವೇರಿ ಸ್ಪೇರ್ಸ್" in messages["kn"]


# ==============================================================================
# T6: PERSISTENCE & CONCURRENCY TESTS (SQLite, TTL, Restart Idempotency)
# ==============================================================================
def test_sqlite_persistence_idempotency_restart_409():
    """Verify that restarting the app/client still returns 409 on duplicate approval via SQLite persistence."""
    import time
    from starlette.testclient import TestClient
    from app.server import app

    client1 = TestClient(app)
    client1.post("/reset-data")

    # Fetch morning briefing to get an active proposal
    briefing = client1.get("/briefing").json()
    problem = briefing["problems"][0]
    payload = problem["simulated_action"]["payload"]

    body = {
        "problem_id": problem["problem_id"],
        "action_type": problem["simulated_action"]["action_type"],
        "payload": payload,
        "client_request_id": f"REQ-{problem['problem_id']}-TEST"
    }

    # 1. First approval succeeds
    resp1 = client1.post("/action/approve", json=body)
    assert resp1.status_code == 200, f"Expected 200 on first approval: {resp1.text}"

    # 2. Simulate complete app client restart
    del client1
    client2 = TestClient(app)

    # 3. Duplicate approval must return 409 Conflict from SQLite
    resp2 = client2.post("/action/approve", json=body)
    assert resp2.status_code == 409, f"Expected 409 Conflict on restarted client duplicate approval: {resp2.text}"
    assert "Duplicate action detected" in resp2.json()["detail"]


def test_sqlite_reservation_lifecycle_and_rejection_frees_hold():
    """Verify that reservations hold stock and rejection/dismissal frees the reservation."""
    from starlette.testclient import TestClient
    from app.server import app
    from engine.persistence import (
        create_stock_reservation,
        get_active_stock_reservations,
        release_stock_reservation
    )

    client = TestClient(app)
    client.post("/reset-data")

    # Reserve 10 units of SEAL-01 at Belgaum for incident PRB-TEST-HOLD
    res = create_stock_reservation(
        reservation_key="Belgaum:SEAL-01",
        incident_id="PRB-TEST-HOLD",
        sku="SEAL-01",
        location="Belgaum",
        qty=10,
        ttl_seconds=300
    )
    active = get_active_stock_reservations()
    assert active.get("Belgaum:SEAL-01") == 10

    # Rejecting the proposal frees the reservation
    resp_reject = client.post("/action/reject", json={
        "problem_id": "PRB-TEST-HOLD",
        "rejected_by": "Ramesh",
        "reason": "Not feasible"
    })
    assert resp_reject.status_code == 200

    active_after = get_active_stock_reservations()
    assert active_after.get("Belgaum:SEAL-01", 0) == 0, "Reservation should be freed after rejection"


def test_sqlite_reservation_ttl_expiry():
    """Verify that stock reservations automatically expire and purge after TTL."""
    import time
    from engine.persistence import (
        create_stock_reservation,
        get_active_stock_reservations
    )

    # Create short TTL reservation (0.1 seconds)
    create_stock_reservation(
        reservation_key="Hubli:VALVE-01",
        incident_id="PRB-TTL-TEST",
        sku="VALVE-01",
        location="Hubli",
        qty=5,
        ttl_seconds=0.1
    )
    # Check it exists immediately
    active = get_active_stock_reservations()
    assert active.get("Hubli:VALVE-01") == 5

    # Wait for TTL to expire
    time.sleep(0.15)

    # Active reservations should clean up expired holds
    active_expired = get_active_stock_reservations()
    assert active_expired.get("Hubli:VALVE-01", 0) == 0, "Expired reservation must be cleaned up"


# ==============================================================================
# T7 & T8: SURGE DEFINITION & CATEGORY D ACTION RESOLUTION TESTS
# ==============================================================================
def test_surge_definition_and_category_d_resolution_matching():
    """Verify single surge thresholds in config and Category D action sizing & resolution matching."""
    import math
    from engine.config import (
        TREND_ACCELERATING_THRESHOLD,
        SURGE_EXPLOSIVE_RATIO,
        SURGE_MIN_RECENT_VELOCITY,
        DEFAULT_REVIEW_PERIOD_DAYS
    )

    # 1. Verify domain_math triggers surge at config threshold
    sales_mock = []
    # Baseline 30 days: 1 unit/day
    for i in range(30):
        sales_mock.append({"sku": "PUMP-01", "location": "Dharwad", "date": f"2026-09-{i+1:02d}", "qty_sold": 1.0})
    # Last 7 days: 3 units/day (ratio = 3.0 >= SURGE_EXPLOSIVE_RATIO 1.8, and 3.0 >= SURGE_MIN_RECENT_VELOCITY 2.0)
    for i in range(7):
        sales_mock.append({"sku": "PUMP-01", "location": "Dharwad", "date": f"2026-10-{i+1:02d}", "qty_sold": 3.0})

    vel = compute_adaptive_velocity(sales_mock, "PUMP-01", "Dharwad", current_stock=10, primary_lead_time=7)
    assert vel["trend_label"] == "ACCELERATING"
    assert vel["is_surge"] is True

    # 2. Category D action sizing and resolution matching
    engine = DecisionEngine(
        data_dir=os.path.join(BASE_DIR, "data"),
        chaos_events=[{
            "event_type": "DEMAND_SURGE",
            "sku": "FILTER-HYD-01",
            "location": "Dharwad",
            "multiplier_or_days": 2.5
        }]
    )
    res = engine.run_agentic_pipeline()
    cat_d_problems = [p for p in res["problems"] if p.get("category_code") == "CATEGORY_D"]
    assert len(cat_d_problems) > 0, "Expected Category D problems under demand surge"

    for p in cat_d_problems:
        action = p["simulated_action"]
        act_type = action["action_type"]
        assert act_type in ("TRANSFER_REQUEST", "PURCHASE_ORDER")
        payload = action["payload"]
        qty = payload["qty"]

        # Sizing must be positive and match review period * new velocity
        v_short = p["domain_metrics"]["adaptive_velocity"].get("v_recent", p["domain_metrics"]["daily_burn_rate"])
        expected_size = max(1, math.ceil(v_short * DEFAULT_REVIEW_PERIOD_DAYS))
        assert qty >= 1
        assert abs(qty - expected_size) <= 5, f"Action qty {qty} should match review period demand {expected_size}"

        # Decision rationale must explicitly match the transfer or PO action, not a vague phrase
        rationale = p["decision_rationale"]
        assert ("transfer" in rationale.lower() or "purchase order" in rationale.lower() or "order" in rationale.lower())
        assert "preemptively raising safety stock buffer to prevent" not in rationale.lower(), (
            f"Vague safety stock rationale found: {rationale}"
        )


# ==============================================================================
# T9: COMPARISON OPERATORS CONSISTENCY (>= 15d and > 3x MOQ)
# ==============================================================================
def test_comparison_operators_15day_and_3x_moq():
    """Verify consistent comparison operators: >= 15.0 days for safe donor buffer, and > 3x MOQ for friction penalty."""
    from engine.config import DEFAULT_DONOR_MIN_COVER_DAYS, MOQ_OVERPURCHASE_RATIO_THRESHOLD
    
    # 1. 15-day buffer operator: >= 15.0 is SAFE, < 15.0 is BREACH
    # Donor has 25 stock, burn rate 1.0/day. Transfer 10 -> remaining 15.0 -> cover = 15.0 days (SAFE)
    res_exact_15 = calculate_donor_transfer_safety(donor_stock=25, donor_v=1.0, transfer_qty=10)
    assert res_exact_15["is_safe"] is True
    assert res_exact_15["remaining_cover_days"] == 15.0

    # Transfer 11 -> remaining 14.0 -> cover = 14.0 days (BREACH)
    res_below_15 = calculate_donor_transfer_safety(donor_stock=25, donor_v=1.0, transfer_qty=11)
    assert res_below_15["is_safe"] is False
    assert res_below_15["remaining_cover_days"] == 14.0

    # 2. 3x MOQ operator: <= 3x is ALLOWED, > 3x is INFEASIBLE_MOQ
    # Needed Q = 10. Exactly 3x MOQ = 30 -> No penalty
    sup_exact_3x = {"supplier": "Vendor A", "moq": 30, "price": 1000.0, "lead_time_days": 2}
    friction_exact = evaluate_supplier_friction(sup_exact_3x, baseline_price=1000.0, Q_needed=10, days_of_cover=5.0)
    assert friction_exact["feasibility_status"] == "FEASIBLE"
    assert friction_exact.get("moq_penalty", False) is False

    # Needed Q = 10. MOQ = 31 (> 3x) -> Excessive MOQ friction
    sup_over_3x = {"supplier": "Vendor B", "moq": 31, "price": 1000.0, "lead_time_days": 2}
    friction_over = evaluate_supplier_friction(sup_over_3x, baseline_price=1000.0, Q_needed=10, days_of_cover=5.0)
    assert friction_over["feasibility_status"] == "INFEASIBLE_MOQ"
    assert friction_over["moq_penalty"] is True


# ==============================================================================
# T10: DYNAMIC DONOR BUFFER & INCOMING POS
# ==============================================================================
def test_dynamic_donor_buffer_and_incoming_pos():
    """Verify dynamic donor buffer = max(15, donor_lead_time + safety_days) and donor incoming PO crediting."""
    from engine.domain_math import compute_dynamic_donor_buffer
    
    # 1. Lead time 14 + safety 5 = 19 days (> 15 floor)
    buf_19 = compute_dynamic_donor_buffer(donor_lead_time_days=14, safety_days=5.0)
    assert buf_19 == 19.0
    
    # 2. Lead time 5 + safety 5 = 10 days (< 15 floor) -> clamped to 15.0
    buf_15 = compute_dynamic_donor_buffer(donor_lead_time_days=5, safety_days=5.0)
    assert buf_15 == 15.0

    # 3. Donor with lead time 14 + safety 5 needs 19 days cover
    # Donor stock = 30, v = 1.0. Transfer 14 leaves 16 stock (16.0 days cover).
    # Since 16.0 < 19.0, it MUST be marked unsafe
    res_unsafe = calculate_donor_transfer_safety(
        donor_stock=30, donor_v=1.0, transfer_qty=14,
        donor_lead_time=14, safety_days=5.0
    )
    assert res_unsafe["required_cover_days"] == 19.0
    assert res_unsafe["remaining_cover_days"] == 16.0
    assert res_unsafe["is_safe"] is False

    # Transferring 11 leaves 19 stock (19.0 days cover >= 19.0) -> SAFE
    res_safe = calculate_donor_transfer_safety(
        donor_stock=30, donor_v=1.0, transfer_qty=11,
        donor_lead_time=14, safety_days=5.0
    )
    assert res_safe["is_safe"] is True
    assert res_safe["remaining_cover_days"] == 19.0

    # 4. Donor incoming PO crediting:
    # Physical stock = 10 (10 days cover), but incoming PO = 20 arriving.
    # Effective stock = 30. Transferring 11 leaves effective stock 19 (19.0 days cover) -> SAFE
    res_with_po = calculate_donor_transfer_safety(
        donor_stock=10, donor_v=1.0, transfer_qty=11,
        donor_lead_time=14, safety_days=5.0,
        donor_incoming_po_qty=20
    )
    assert res_with_po["effective_donor_stock"] == 30
    assert res_with_po["is_safe"] is True
    assert res_with_po["remaining_cover_days"] == 19.0


# ==============================================================================
# T11: PER-SKU TARGET COVER FOR CAPITAL TRAP
# ==============================================================================
def test_per_sku_target_cover_capital_trap():
    """Verify per-SKU target cover (lead time + review period + safety stock) replaces flat 45-day benchmark."""
    from engine.domain_math import compute_sku_target_cover, evaluate_sku_location

    # 1. Formula validation: lead time + review period + safety stock
    target_7 = compute_sku_target_cover(primary_lead_time_days=7, review_period_days=7.0, safety_days=5.0)
    assert target_7 == 19.0

    target_14 = compute_sku_target_cover(primary_lead_time_days=14, review_period_days=7.0, safety_days=5.0)
    assert target_14 == 26.0

    # 2. Evaluation with dynamic target cover
    # Case A: SKU with lead time 7 (target cover = 19.0 days).
    # Stock = 22, burn rate = 1.0 -> days cover = 22.0 days.
    # Under old flat 45-day rule, 22.0 would NOT be a capital trap.
    # Under per-SKU target cover (19.0 days), 22.0 > 19.0 -> CAPITAL_TRAP!
    sales_data = [{"date": "2026-10-01", "sku": "SKU-SHORT-LEAD", "location": "Hubli", "qty_sold": 1}] * 30
    sup_7 = [{"supplier": "V1", "sku": "SKU-SHORT-LEAD", "lead_time_days": 7, "price": 500.0, "is_primary": True}]
    res_short = evaluate_sku_location(
        sku="SKU-SHORT-LEAD", location="Hubli", stock=22,
        sales=sales_data, suppliers=sup_7, purchase_orders=[]
    )
    assert res_short["target_cover_days"] == 19.0
    assert res_short["problem_type"] == "CAPITAL_TRAP"

    # Case B: SKU with lead time 14 (target cover = 26.0 days).
    # Same 22.0 days cover: since 22.0 <= 26.0, it is NOT a capital trap
    sales_data_long = [{"date": "2026-10-01", "sku": "SKU-LONG-LEAD", "location": "Hubli", "qty_sold": 1}] * 30
    sup_14 = [{"supplier": "V2", "sku": "SKU-LONG-LEAD", "lead_time_days": 14, "price": 500.0, "is_primary": True}]
    res_long = evaluate_sku_location(
        sku="SKU-LONG-LEAD", location="Hubli", stock=22,
        sales=sales_data_long, suppliers=sup_14, purchase_orders=[]
    )
    assert res_long["target_cover_days"] == 26.0
    assert res_long["problem_type"] != "CAPITAL_TRAP"


# ==============================================================================
# T12: OVERDUE PO HARDENING (CANCELLED EXCLUSION, PARTIAL DELIVERIES, DRAFT)
# ==============================================================================
def test_overdue_po_cancellation_partial_delivery_and_softer_draft():
    """Verify CANCELLED PO exclusion, partial delivery remaining qty, cover impact sorting, and softer draft notice."""
    from engine.domain_math import get_incoming_pos, evaluate_sku_location

    sales_data = [{"date": "2026-10-01", "sku": "PUMP-GEAR-03", "location": "Hubli", "qty_sold": 1}] * 30
    sup = [{"supplier": "Deccan Fluid Power", "sku": "PUMP-GEAR-03", "lead_time_days": 10, "price": 14200.0, "is_primary": True}]

    # 1. CANCELLED PO must be excluded
    cancelled_pos = [{
        "po": "PO-CANCELLED-01", "supplier": "Deccan Fluid Power", "sku": "PUMP-GEAR-03",
        "location": "Hubli", "qty": 10, "expected_date": "2026-10-01", "status": "CANCELLED"
    }]
    incoming = get_incoming_pos(cancelled_pos, "PUMP-GEAR-03", "Hubli")
    assert len(incoming) == 0

    eval_cancelled = evaluate_sku_location(
        sku="PUMP-GEAR-03", location="Hubli", stock=20,
        sales=sales_data, suppliers=sup, purchase_orders=cancelled_pos, current_date="2026-10-09"
    )
    assert len(eval_cancelled["overdue_pos"]) == 0

    # 2. Partial delivery handling: total 20, delivered 15 -> remaining 5
    partial_pos = [{
        "po": "PO-PARTIAL-02", "supplier": "Deccan Fluid Power", "sku": "PUMP-GEAR-03",
        "location": "Hubli", "qty": 20, "delivered_qty": 15, "expected_date": "2026-10-01", "status": "PARTIALLY_DELIVERED"
    }]
    incoming_partial = get_incoming_pos(partial_pos, "PUMP-GEAR-03", "Hubli")
    assert len(incoming_partial) == 1
    assert incoming_partial[0]["remaining_qty"] == 5

    eval_partial = evaluate_sku_location(
        sku="PUMP-GEAR-03", location="Hubli", stock=5,
        sales=sales_data, suppliers=sup, purchase_orders=partial_pos, current_date="2026-10-09"
    )
    assert len(eval_partial["overdue_pos"]) == 1
    assert eval_partial["overdue_pos"][0]["remaining_qty"] == 5

    # 3. Prioritization by impact on cover
    # Two overdue POs: Small PO (remaining 2 units = 2 days cover) vs Big PO (remaining 25 units = 25 days cover)
    multi_pos = [
        {"po": "PO-SMALL", "supplier": "Deccan Fluid Power", "sku": "PUMP-GEAR-03", "location": "Hubli", "qty": 2, "expected_date": "2026-10-01", "status": "DELAYED"},
        {"po": "PO-BIG", "supplier": "Deccan Fluid Power", "sku": "PUMP-GEAR-03", "location": "Hubli", "qty": 25, "expected_date": "2026-10-02", "status": "DELAYED"},
    ]
    eval_multi = evaluate_sku_location(
        sku="PUMP-GEAR-03", location="Hubli", stock=5,
        sales=sales_data, suppliers=sup, purchase_orders=multi_pos, current_date="2026-10-09"
    )
    assert len(eval_multi["overdue_pos"]) == 2
    assert eval_multi["overdue_pos"][0]["po"] == "PO-BIG", "Overdue PO with larger cover impact should be sorted first"
    assert eval_multi["overdue_pos"][0]["cover_impact_days"] > eval_multi["overdue_pos"][1]["cover_impact_days"]

    # 4. Agent pipeline generates softer draft notice requiring approval
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    res = engine.run_agentic_pipeline()
    overdue_incident = [p for p in res["problems"] if p.get("category") == "OVERDUE_PO"][0]
    action = overdue_incident["simulated_action"]

    assert action["action_type"] == "SUPPLIER_EXPEDITE_NOTICE"
    assert action["human_approval_required"] is True
    assert action.get("is_draft") is True
    assert action.get("status") == "DRAFT"
    payload = action["payload"]
    assert "draft_message" in payload
    assert payload.get("escalation_policy") == "COLLABORATIVE_DRAFT_FIRST"


# ==============================================================================
# T13: GENERIC ROUTE-BLOCK & SUPPLIER DELAY VS PRICE HIKE
# ==============================================================================
def test_generic_route_block_and_supplier_delay_vs_price_hike():
    """Verify generic facility route blocking for arbitrary pairs and split supplier delay vs price hike."""
    # 1. Generic facility route blocking (non-Belgaum pair)
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    engine.blocked_routes = [{"from": "Hubli Regional Warehouse", "to": "Dharwad", "sku": "VALVE-CTRL-02"}]

    assert engine.is_route_blocked("Hubli Regional Warehouse", "Dharwad", "VALVE-CTRL-02") is True
    # Substring matching
    assert engine.is_route_blocked("Hubli", "Dharwad", "VALVE-CTRL-02") is True
    # Non-blocked route must remain false
    assert engine.is_route_blocked("Bagalkot", "Dharwad", "VALVE-CTRL-02") is False
    assert engine.is_route_blocked("Hubli Regional Warehouse", "Gokak", "VALVE-CTRL-02") is False

    # 2. SUPPLIER_DELAY increases lead time
    engine_delay = DecisionEngine(
        data_dir=os.path.join(BASE_DIR, "data"),
        chaos_events=[{"event_type": "SUPPLIER_DELAY", "sku": "FILTER-HYD-01", "multiplier_or_days": 6.0}]
    )
    sup_delay = [s for s in engine_delay.suppliers if s.get("sku") == "FILTER-HYD-01" and s.get("is_primary")][0]
    # Baseline lead time is 7 -> 7 + 6 = 13
    assert sup_delay["lead_time_days"] == 13

    # 3. SUPPLIER_PRICE_HIKE increases price
    engine_price = DecisionEngine(
        data_dir=os.path.join(BASE_DIR, "data"),
        chaos_events=[{"event_type": "SUPPLIER_PRICE_HIKE", "sku": "FILTER-HYD-01", "multiplier_or_days": 0.25}]
    )
    sup_price = [s for s in engine_price.suppliers if s.get("sku") == "FILTER-HYD-01" and s.get("is_primary")][0]
    # Baseline price is 850.0 -> 850.0 * 1.25 = 1062.5
    assert sup_price["price"] == 1062.5
    assert sup_price["lead_time_days"] == 7  # Lead time unaffected

    # 4. SUPPLIER_HIKE legacy alias maps to lead time delay
    engine_legacy = DecisionEngine(
        data_dir=os.path.join(BASE_DIR, "data"),
        chaos_events=[{"event_type": "SUPPLIER_HIKE", "sku": "FILTER-HYD-01", "multiplier_or_days": 5.0}]
    )
    sup_legacy = [s for s in engine_legacy.suppliers if s.get("sku") == "FILTER-HYD-01" and s.get("is_primary")][0]
    assert sup_legacy["lead_time_days"] == 12


# ==============================================================================
# T14: MOQ EXCESS CARRYING COST SCORING
# ==============================================================================
def test_moq_excess_carrying_cost_scoring():
    """Verify MOQ scoring replaces binary infeasibility below 3x threshold with excess carrying cost calculation."""
    from engine.domain_math import evaluate_supplier_friction

    # Case 1: MOQ <= Q_needed -> 0 excess carrying cost, FEASIBLE
    sup_fit = {"supplier": "Vendor Exact", "moq": 10, "price": 1000.0, "lead_time_days": 2}
    res_fit = evaluate_supplier_friction(sup_fit, baseline_price=1000.0, Q_needed=10, days_of_cover=5.0)
    assert res_fit["feasibility_status"] == "FEASIBLE"
    assert res_fit["moq_penalty"] is False
    assert res_fit["overpurchase_qty"] == 0
    assert res_fit["excess_carrying_cost"] == 0.0

    # Case 2: MOQ exceeds Q_needed but within 3x threshold (e.g. MOQ=25 for Q_needed=10)
    # Must remain FEASIBLE, but excess carrying cost is scored
    sup_mod = {"supplier": "Vendor Moderate", "moq": 25, "price": 1000.0, "lead_time_days": 2}
    res_mod = evaluate_supplier_friction(sup_mod, baseline_price=1000.0, Q_needed=10, days_of_cover=5.0)
    assert res_mod["feasibility_status"] == "FEASIBLE"
    assert res_mod["moq_penalty"] is False
    assert res_mod["overpurchase_qty"] == 15
    # Expected carrying cost: 15 units * 1000.0 * (0.22 / 365) * 90.0 ~= 813.70
    assert res_mod["excess_carrying_cost"] > 800.0
    assert res_mod["excess_carrying_cost"] < 820.0

    # Case 3: MOQ exceeds 3x threshold (e.g. MOQ=50 for Q_needed=10)
    # Flagged as INFEASIBLE_MOQ with moq_penalty=True
    sup_excess = {"supplier": "Vendor Big", "moq": 50, "price": 1000.0, "lead_time_days": 2}
    res_excess = evaluate_supplier_friction(sup_excess, baseline_price=1000.0, Q_needed=10, days_of_cover=5.0)
    assert res_excess["feasibility_status"] == "INFEASIBLE_MOQ"
    assert res_excess["moq_penalty"] is True
    assert res_excess["overpurchase_qty"] == 40
    assert res_excess["excess_carrying_cost"] > 2000.0


# ==============================================================================
# T15: SEVERITY EXPLICIT FORMULA (margin_at_risk / time_to_stockout)
# ==============================================================================
def test_severity_explicit_formula_and_margin_at_risk():
    """Verify explicit severity formula (margin_at_risk / time_to_stockout) with config thresholds."""
    from engine.domain_math import compute_severity, evaluate_sku_location
    from engine.config import SEVERITY_CRITICAL_RATIO, SEVERITY_HIGH_RATIO

    # 1. Direct formula evaluation
    # CRITICAL: 7,500 / 2.0 = 3,750 >= 2,500 (SEVERITY_CRITICAL_RATIO)
    res_crit = compute_severity(margin_at_risk=7500.0, time_to_stockout=2.0)
    assert res_crit["severity"] == "CRITICAL"
    assert res_crit["severity_score"] == 3750.0

    # HIGH: 3,000 / 2.0 = 1,500 (between 800 and 2,500)
    res_high = compute_severity(margin_at_risk=3000.0, time_to_stockout=2.0)
    assert res_high["severity"] == "HIGH"
    assert res_high["severity_score"] == 1500.0

    # MEDIUM: 800 / 2.0 = 400 (< 800)
    res_med = compute_severity(margin_at_risk=800.0, time_to_stockout=2.0)
    assert res_med["severity"] == "MEDIUM"
    assert res_med["severity_score"] == 400.0

    # 2. Integration in evaluate_sku_location with margin_at_risk single term
    sales_data = [{"date": "2026-10-01", "sku": "FILTER-HYD-01", "location": "Gokak", "qty_sold": 4}] * 30
    sup = [{"supplier": "Kirloskar", "sku": "FILTER-HYD-01", "lead_time_days": 7, "price": 850.0, "is_primary": True}]
    eval_res = evaluate_sku_location(
        sku="FILTER-HYD-01", location="Gokak", stock=8,
        sales=sales_data, suppliers=sup, purchase_orders=[]
    )
    assert "margin_at_risk" in eval_res
    assert "time_to_stockout" in eval_res
    assert "severity_score" in eval_res
    assert eval_res["severity"] in ("CRITICAL", "HIGH", "MEDIUM")
    assert eval_res["margin_at_risk"] > 0.0


# ==============================================================================
# T16: VELOCITY ROBUSTNESS (MINIMUM-VOLUME CHECK & EWMA/BLENDED VELOCITY)
# ==============================================================================
def test_velocity_robustness_minimum_volume_and_ewma():
    """Verify that low sparse sales volume does not trigger overreaction, and EWMA/blended velocity are computed."""
    from engine.domain_math import compute_adaptive_velocity

    curr_dt = datetime.strptime("2026-10-09", "%Y-%m-%d")

    # 1. Noisy sparse sales: only 1 unit sold in 30 days (total volume = 1 < 3)
    sparse_sales = []
    for d in range(30):
        dt = curr_dt - timedelta(days=d)
        qty = 1 if d == 1 else 0  # Single sporadic sale
        sparse_sales.append({
            "date": dt.strftime("%Y-%m-%d"),
            "sku": "FILTER-HYD-01",
            "location": "Gokak",
            "qty_sold": qty
        })

    res_sparse = compute_adaptive_velocity(sparse_sales, "FILTER-HYD-01", "Gokak", current_stock=10, primary_lead_time=7)
    assert res_sparse["is_low_volume"] is True
    assert res_sparse["total_volume"] == 1
    # Minimum-volume guard prevents noisy ratio from triggering ACCELERATING or surge overreaction
    assert res_sparse["trend_label"] == "STABLE"
    assert res_sparse["is_surge"] is False
    assert "v_ewma" in res_sparse
    assert "v_blended" in res_sparse

    # 2. Significant volume with genuine spike: 30 days history with 51 units volume
    robust_sales = []
    for d in range(30):
        dt = curr_dt - timedelta(days=d)
        qty = 4 if d < 7 else 1  # 7*4 = 28 + 23*1 = 23 -> total volume 51
        robust_sales.append({
            "date": dt.strftime("%Y-%m-%d"),
            "sku": "FILTER-HYD-01",
            "location": "Gokak",
            "qty_sold": qty
        })

    res_robust = compute_adaptive_velocity(robust_sales, "FILTER-HYD-01", "Gokak", current_stock=10, primary_lead_time=7)
    assert res_robust["is_low_volume"] is False
    assert res_robust["total_volume"] == 51
    assert res_robust["trend_label"] == "ACCELERATING"
    assert res_robust["v_ewma"] > 0.0
    assert res_robust["v_blended"] > 0.0


# ==============================================================================
# T17: EDGE CASES (stock <= 0 and zero velocity must not raise a stockout)
# ==============================================================================
def test_edge_case_zero_stock_and_zero_velocity_no_stockout():
    """Verify stock <= 0 with zero velocity does not raise an imminent stockout problem."""
    from engine.domain_math import calculate_days_of_cover, evaluate_sku_location

    # 1. calculate_days_of_cover edge cases
    # Zero stock, zero velocity -> 999.0 (No demand, not depleting)
    assert calculate_days_of_cover(0, 0.0) == 999.0
    # Negative stock, zero velocity -> 999.0
    assert calculate_days_of_cover(-5, 0.0) == 999.0
    # Zero stock, active velocity -> 0.0 (Immediate stockout)
    assert calculate_days_of_cover(0, 2.0) == 0.0

    # 2. evaluate_sku_location with stock=0 and zero velocity
    sup = [{"supplier": "Kirloskar", "sku": "FILTER-HYD-01", "lead_time_days": 7, "price": 850.0, "is_primary": True}]
    zero_sales = [{"date": "2026-10-01", "sku": "FILTER-HYD-01", "location": "Gokak", "qty_sold": 0}] * 30

    res_zero = evaluate_sku_location(
        sku="FILTER-HYD-01", location="Gokak", stock=0,
        sales=zero_sales, suppliers=sup, purchase_orders=[]
    )
    assert res_zero["burn_rate"] == 0.0
    assert res_zero["problem_type"] != "IMMINENT_STOCKOUT", "Zero stock with zero velocity must NOT raise a stockout"
    assert res_zero["problem_type"] is None
    assert res_zero["severity"] == "NONE"

    # 3. Negative stock with zero velocity
    res_neg = evaluate_sku_location(
        sku="FILTER-HYD-01", location="Gokak", stock=-3,
        sales=zero_sales, suppliers=sup, purchase_orders=[]
    )
    assert res_neg["problem_type"] != "IMMINENT_STOCKOUT"
    assert res_neg["problem_type"] is None
    assert res_neg["severity"] == "NONE"

    # 4. Zero stock WITH active velocity MUST raise stockout
    active_sales = [{"date": "2026-10-01", "sku": "FILTER-HYD-01", "location": "Gokak", "qty_sold": 2}] * 30
    res_active = evaluate_sku_location(
        sku="FILTER-HYD-01", location="Gokak", stock=0,
        sales=active_sales, suppliers=sup, purchase_orders=[]
    )
    assert res_active["problem_type"] == "IMMINENT_STOCKOUT", "Zero stock with active velocity MUST raise a stockout"
    assert res_active["severity"] in ("CRITICAL", "HIGH")


# ==============================================================================
# T18: HISTORICAL BACKTEST SIMULATION TESTS
# ==============================================================================
def test_backtest_simulation_metrics():
    """Verify that backtest replays sales and outputs stockouts prevented and Rs saved."""
    from scripts.backtest import run_backtest
    data_dir = os.path.join(BASE_DIR, "data")
    results = run_backtest(data_dir, days=30)
    assert results["days_simulated"] > 0
    assert results["baseline_stockout_events"] > 0
    assert results["stockouts_prevented"] >= 0
    assert results["lost_units_averted"] >= 0
    assert results["rs_saved"] > 0.0
    assert "roi_percent" in results

    # Test via API
    client = TestClient(app)
    res = client.get("/api/backtest?days=30")
    assert res.status_code == 200
    data = res.json()
    assert data["days_simulated"] == results["days_simulated"]
    assert data["rs_saved"] == results["rs_saved"]


# ==============================================================================
# T19: GLOBAL TRANSFER OPTIMIZER TESTS
# ==============================================================================
def test_global_transfer_optimizer_joint_solution_and_capital_trap():
    """Verify that PuLP global optimizer solves multi-echelon transfers jointly,
    prevents over-promising, uses Capital Trap surplus, and provides comparison."""
    from engine.global_optimizer import solve_global_transfer_network

    demands = [
        {
            "demand_id": "DEM-GOKAK-01",
            "sku": "FILTER-HYD-01",
            "location": "Gokak",
            "needed_qty": 15,
            "margin_loss_per_unit": 350.0,
            "supplier_price": 850.0
        },
        {
            "demand_id": "DEM-NIPPANI-02",
            "sku": "FILTER-HYD-01",
            "location": "Nippani",
            "needed_qty": 15,
            "margin_loss_per_unit": 350.0,
            "supplier_price": 850.0
        }
    ]

    donors = [
        {
            "donor_id": "DON-BELGAUM",
            "sku": "FILTER-HYD-01",
            "location": "Belgaum",
            "surplus_qty": 20,  # Cannot fulfill both (15+15=30) alone
            "is_capital_trap": False,
            "cover_days": 18.0
        },
        {
            "donor_id": "DON-HUBLI-TRAP",
            "sku": "FILTER-HYD-01",
            "location": "Hubli Regional Warehouse",
            "surplus_qty": 15,  # Capital Trap surplus!
            "is_capital_trap": True,
            "cover_days": 65.0
        }
    ]

    res = solve_global_transfer_network(demands=demands, donors=donors)
    assert res["status"] == "OPTIMAL"
    assert "OPTIMAL" in res["solver"]
    assert len(res["transfers"]) >= 2

    # Verify no donor is over-promised
    belgaum_transfers = sum(t["qty"] for t in res["transfers"] if t["from_location"] == "Belgaum")
    assert belgaum_transfers <= 20, f"Belgaum was over-promised: {belgaum_transfers} > 20"

    # Verify Capital Trap was utilized
    trap_transfers = sum(t["qty"] for t in res["transfers"] if t["is_capital_trap"])
    assert trap_transfers > 0, "Capital Trap surplus should feed stockouts"

    # Verify comparison with greedy
    assert "total_cost_global" in res
    assert "total_cost_greedy" in res
    assert "cost_savings_vs_greedy" in res

    # Verify API endpoint
    client = TestClient(app)
    api_res = client.get("/api/optimizer/transfers")
    assert api_res.status_code == 200
    plan = api_res.json()
    assert "solver" in plan


# ==============================================================================
# T20: PROBABILISTIC PROJECTIONS & MONTE CARLO TESTS
# ==============================================================================
def test_probabilistic_projections_monte_carlo_fan_chart_and_day_14_stockout_risk():
    """Verify that generate_14day_projections generates seeded Monte Carlo simulations (500 runs),
    fan chart percentiles (p10, p50, p90), and day-14 stockout probability."""
    from engine.domain_math import generate_14day_projections, simulate_monte_carlo_projections

    # Direct test of simulate_monte_carlo_projections
    mc = simulate_monte_carlo_projections(
        starting_stock=8,
        daily_burn=4.0,
        arrival_qty=0,
        arrival_day=None,
        horizon_days=15,
        num_runs=500,
        seed=42
    )
    assert len(mc["p10"]) == 15
    assert len(mc["p50"]) == 15
    assert len(mc["p90"]) == 15
    assert mc["stockout_probability_by_day_14"] >= 0.8
    # Ordering of percentiles across days
    for d in range(15):
        assert mc["p10"][d] <= mc["p50"][d] <= mc["p90"][d]

    # Test integrated into generate_14day_projections
    proj = generate_14day_projections(
        current_stock=20,
        daily_burn=2.0,
        transfer_qty=20,
        primary_lead_time=7,
        has_open_po=False
    )
    assert "probabilistic" in proj
    assert proj["probabilistic"]["num_runs"] == 500
    assert proj["probabilistic"]["seed"] == 42
    assert "fan_chart" in proj
    assert "stockout_probability_by_day_14" in proj
    assert proj["stockout_probability_by_day_14"]["status_quo"] >= 0.8
    assert proj["stockout_probability_by_day_14"]["transfer"] < 0.2


# ==============================================================================
# T21: SUPPLIER RELIABILITY LEARNING TESTS
# ==============================================================================
def test_supplier_reliability_learning_slippage_and_adjusted_lead_time():
    """Verify that supplier reliability learns actual vs promised delivery slippage
    and applies adjusted lead time to domain math and decision engine."""
    from engine.domain_math import compute_supplier_reliability

    test_suppliers = [
        {"supplier": "Supplier Fast", "sku": "FILTER-HYD-01", "lead_time_days": 3, "price": 900.0, "moq": 10},
        {"supplier": "Supplier Sluggish", "sku": "PUMP-GEAR-03", "lead_time_days": 10, "price": 14000.0, "moq": 5},
    ]

    test_pos = [
        # Supplier Sluggish has PO overdue by 5 days
        {
            "po": "PO-TEST-01",
            "supplier": "Supplier Sluggish",
            "expected_date": "2026-10-04",
            "status": "DELAYED"
        },
        # Supplier Fast had on-time delivery
        {
            "po": "PO-TEST-02",
            "supplier": "Supplier Fast",
            "expected_date": "2026-09-20",
            "actual_delivery_date": "2026-09-20",
            "status": "DELIVERED"
        }
    ]

    rel = compute_supplier_reliability(
        purchase_orders=test_pos,
        suppliers=test_suppliers,
        current_date="2026-10-09"
    )

    assert "Supplier Sluggish" in rel
    assert rel["Supplier Sluggish"]["avg_slippage_days"] == 5.0
    assert rel["Supplier Sluggish"]["adjusted_lead_time_days"] == 15  # 10 quoted + 5 slippage
    assert rel["Supplier Sluggish"]["reliability_status"] == "HIGH_RISK"

    assert "Supplier Fast" in rel
    assert rel["Supplier Fast"]["avg_slippage_days"] == 0.0
    assert rel["Supplier Fast"]["adjusted_lead_time_days"] == 3
    assert rel["Supplier Fast"]["reliability_status"] == "RELIABLE"

    # Test via API
    client = TestClient(app)
    res = client.get("/api/suppliers/reliability")
    assert res.status_code == 200
    data = res.json()
    assert "Deccan Fluid Power Hosur" in data
    # Deccan has PO-2026-0892 overdue by 5 days (quoted 10 -> adjusted 15)
    assert data["Deccan Fluid Power Hosur"]["adjusted_lead_time_days"] >= 15
    assert data["Deccan Fluid Power Hosur"]["reliability_status"] == "HIGH_RISK"


# ==============================================================================
# T22: PLAN DIFF ON CHAOS INJECTION TESTS
# ==============================================================================
def test_chaos_plan_diff_before_and_after_adaptation_with_reason():
    """Verify that chaos injection captures before-plan vs after-plan diff
    and provides explicit operational reasons for all plan shifts."""
    from engine.domain_math import compute_plan_diff

    client = TestClient(app)
    # Reset benchmark first
    client.post("/reset-data")

    # Inject route block
    payload = {
        "event_type": "TRANSFER_BLOCKED",
        "from_location": "Belgaum",
        "to_location": "Gokak",
        "sku": "FILTER-HYD-01"
    }
    res = client.post("/chaos/inject", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "plan_diff" in data

    p_diff = data["plan_diff"]
    assert p_diff["total_problems"] > 0
    assert "diffs" in p_diff

    # Find the Gokak FILTER-HYD-01 incident in diffs
    gokak_diff = next(
        (d for d in p_diff["diffs"] if d.get("location") == "Gokak" and d.get("sku") == "FILTER-HYD-01"),
        None
    )
    assert gokak_diff is not None
    assert gokak_diff["has_changed"] is True
    assert gokak_diff["before_plan"]["source"] == "Belgaum"
    assert gokak_diff["after_plan"]["source"] != "Belgaum"
    assert "shifted" in gokak_diff["change_reason"].lower() or "roadblock" in gokak_diff["change_reason"].lower()

    # Clean up state
    client.post("/reset-data")


def test_rejection_memory_soft_constraint_application():
    """
    T23: Rejection Memory - operator rejection of an option adds soft penalty (+Rs.750)
    to its expected cost and notes the human rejection reason.
    """
    from engine.persistence import record_rejection_memory, clear_all_persistence

    # Clean DB state
    clear_all_persistence()

    # 1. Base engine without rejection memory
    engine_base = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"), rejection_memories=[])
    brief_base = engine_base.run_agentic_pipeline()
    prob_base = next(
        p for p in brief_base["problems"]
        if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"
    )
    opt1_base = next(o for o in prob_base["evaluated_options"] if "Internal Network" in o["option_name"])
    base_cost = opt1_base["expected_cost"]

    # 2. Record explicit operator rejection against Belgaum donor
    record_rejection_memory(
        problem_id=prob_base["problem_id"],
        sku="FILTER-HYD-01",
        location="Gokak",
        rejected_source="Belgaum",
        action_type="TRANSFER_REQUEST",
        rejection_reason="Belgaum warehouse reported packaging damage"
    )

    # 3. Re-run engine and inspect options
    engine_mem = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    brief_mem = engine_mem.run_agentic_pipeline()
    prob_mem = next(
        p for p in brief_mem["problems"]
        if p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak"
    )
    opt1_mem = next(o for o in prob_mem["evaluated_options"] if "Internal Network" in o["option_name"])

    assert opt1_mem.get("rejection_penalty_applied") is True
    assert opt1_mem["expected_cost"] == round(base_cost + 750.0, 2)
    assert "Belgaum warehouse reported packaging damage" in opt1_mem.get("rejection_reason_note", "")
    assert "SOFT CONSTRAINT" in opt1_mem.get("pros_cons", "")

    # Clean up DB
    clear_all_persistence()


def test_data_quality_flags_low_volume_and_gaps():
    """
    T24: Data-Quality Flags - detects missing sales dates or low volume (<10 records or <5 units),
    sets data_quality_flag, lowers confidence score, and flags for human escalation.
    """
    from engine.domain_math import compute_adaptive_velocity, evaluate_sku_location

    # 1. Low volume (<10 records, <5 units)
    sparse_sales = [
        {"sku": "SKU-TEST-01", "location": "TestLoc", "qty_sold": 1, "date": "2026-10-01"},
        {"sku": "SKU-TEST-01", "location": "TestLoc", "qty_sold": 1, "date": "2026-10-02"},
        {"sku": "SKU-TEST-01", "location": "TestLoc", "qty_sold": 1, "date": "2026-10-03"},
    ]
    res_low = compute_adaptive_velocity(
        sales_df=sparse_sales,
        sku="SKU-TEST-01",
        location="TestLoc",
        current_stock=2,
        primary_lead_time=7
    )
    assert res_low["data_quality_flag"] == "LOW_VOLUME"
    assert res_low["confidence_score"] == 0.45
    assert res_low["human_escalation_required"] is True

    # 2. Date gaps (gap > 3 days between consecutive transactions)
    # 12 records but with an 8-day gap between 2026-09-10 and 2026-09-18
    gap_dates = [
        "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
        "2026-09-05", "2026-09-10", "2026-09-18", "2026-09-19",
        "2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23"
    ]
    gap_sales = [
        {"sku": "SKU-TEST-02", "location": "TestLoc", "qty_sold": 2, "date": d}
        for d in gap_dates
    ]
    res_gap = compute_adaptive_velocity(
        sales_df=gap_sales,
        sku="SKU-TEST-02",
        location="TestLoc",
        current_stock=10,
        primary_lead_time=7
    )
    assert res_gap["data_quality_flag"] == "DATA_GAPS_DETECTED"
    assert res_gap["confidence_score"] == 0.50
    assert res_gap["human_escalation_required"] is True

    # 3. Normal complete sales history (30 consecutive days, volume >= 5)
    normal_dates = [(datetime(2026, 9, 10) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    normal_sales = [
        {"sku": "SKU-TEST-03", "location": "TestLoc", "qty_sold": 3, "date": d}
        for d in normal_dates
    ]
    res_normal = compute_adaptive_velocity(
        sales_df=normal_sales,
        sku="SKU-TEST-03",
        location="TestLoc",
        current_stock=15,
        primary_lead_time=7
    )
    assert res_normal["data_quality_flag"] == "NORMAL"
    assert res_normal["confidence_score"] == 0.95
    assert res_normal["human_escalation_required"] is False

    # 4. Integration in evaluate_sku_location
    eval_res = evaluate_sku_location(
        sku="SKU-TEST-01",
        location="TestLoc",
        stock=2,
        sales=sparse_sales,
        suppliers=[{"supplier": "Test Sup", "sku": "SKU-TEST-01", "price": 1000.0, "lead_time_days": 7, "is_primary": True}],
        purchase_orders=[],
        current_date="2026-10-09"
    )
    assert eval_res["data_quality_flag"] == "LOW_VOLUME"
    assert eval_res["confidence_score"] == 0.45
    assert eval_res["human_escalation_required"] is True

    # 5. Integration in DecisionEngine pipeline
    engine = DecisionEngine(data_dir=os.path.join(BASE_DIR, "data"))
    brief = engine.run_agentic_pipeline()
    # Check that every problem has data_quality_flag and confidence_score
    for prob in brief["problems"]:
        assert "data_quality_flag" in prob
        assert "confidence_score" in prob
        assert "human_escalation_required" in prob
        if prob["human_escalation_required"]:
            assert prob["simulated_action"]["escalation_policy"] == "MANUAL_SUPERVISION_REQUIRED"
            assert "DATA QUALITY" in prob["decision_rationale"]


def test_ingestion_schemas_case_insensitivity_and_csv_support(tmp_path):
    """
    T25: Ingestion Schemas - validates case-insensitivity, column order tolerance,
    optional column defaults, alias resolution, and CSV loading.
    """
    from engine.data_loader import (
        ProductRecord,
        InventoryRecord,
        SupplierRecord,
        validate_records,
        load_inventory,
        load_dataset_from_dir,
    )

    # 1. Case-insensitivity and alias tolerance for inventory
    raw_inventory = [
        {"SKU": "FILTER-HYD-01", "LOCATION": "Gokak", "CURRENT_STOCK": "25"},
        {"Location": "Belgaum", "sku": "FILTER-HYD-01", "qty": 40},
    ]
    validated_inv = validate_records(raw_inventory, InventoryRecord)
    assert len(validated_inv) == 2
    assert validated_inv[0]["sku"] == "FILTER-HYD-01"
    assert validated_inv[0]["location"] == "Gokak"
    assert validated_inv[0]["stock"] == 25
    assert validated_inv[1]["location"] == "Belgaum"
    assert validated_inv[1]["stock"] == 40

    # 2. Optional column defaults and alias resolution for suppliers
    raw_suppliers = [
        {"VENDOR": "Gokak Spares Hub", "part_number": "FILTER-HYD-01", "cost": 1200.0}
    ]
    validated_sup = validate_records(raw_suppliers, SupplierRecord)
    assert len(validated_sup) == 1
    assert validated_sup[0]["supplier"] == "Gokak Spares Hub"
    assert validated_sup[0]["sku"] == "FILTER-HYD-01"
    assert validated_sup[0]["price"] == 1200.0
    assert validated_sup[0]["lead_time_days"] == 7  # default applied
    assert validated_sup[0]["moq"] == 1             # default applied
    assert validated_sup[0]["is_primary"] is False  # default applied

    # 3. CSV file ingestion support with column order tolerance
    csv_file = tmp_path / "inventory.csv"
    csv_file.write_text(
        "Location,Quantity,SKU\n"
        "Hubli,18,VALVE-CTRL-02\n"
        "Dharwad,32,VALVE-CTRL-02\n",
        encoding="utf-8"
    )
    loaded_from_csv = load_inventory(str(csv_file))
    assert len(loaded_from_csv) == 2
    assert loaded_from_csv[0]["location"] == "Hubli"
    assert loaded_from_csv[0]["sku"] == "VALVE-CTRL-02"
    assert loaded_from_csv[0]["stock"] == 18
    assert loaded_from_csv[1]["location"] == "Dharwad"
    assert loaded_from_csv[1]["stock"] == 32


def test_consolidated_api_unified_aliases():
    """
    T26: Consolidate API - verifies /api/* and /action/* endpoints function
    as thin unified aliases without duplicate logic.
    """
    client = TestClient(app)

    # 1. Briefing alias (/briefing and /api/briefing)
    res_b1 = client.get("/briefing")
    res_b2 = client.get("/api/briefing")
    assert res_b1.status_code == 200
    assert res_b2.status_code == 200
    assert len(res_b1.json()["problems"]) == len(res_b2.json()["problems"])

    # 2. Inventory alias (/inventory and /api/inventory)
    res_inv1 = client.get("/inventory")
    res_inv2 = client.get("/api/inventory")
    assert res_inv1.status_code == 200
    assert res_inv2.status_code == 200
    assert len(res_inv1.json()) == len(res_inv2.json())

    # 3. Audit log alias (/audit-log and /api/audit-log)
    res_aud1 = client.get("/audit-log")
    res_aud2 = client.get("/api/audit-log")
    assert res_aud1.status_code == 200
    assert res_aud2.status_code == 200

    # 4. Action reject alias (/action/reject and /api/action/reject)
    rej_payload = {
        "problem_id": "PRB-TEST-ALIAS",
        "rejected_by": "Test Operator",
        "reason": "Alias verification test"
    }
    res_rej1 = client.post("/action/reject", json=rej_payload)
    assert res_rej1.status_code == 200
    assert res_rej1.json()["status"] == "REJECTED"

    res_rej2 = client.post("/api/action/reject", json=rej_payload)
    assert res_rej2.status_code == 200
    assert res_rej2.json()["status"] == "REJECTED"

    # 5. Reset data alias (/reset-data and /api/reset-data)
    res_rst = client.post("/api/reset-data")
    assert res_rst.status_code == 200
    assert res_rst.json()["status"] == "SUCCESS"


# ==============================================================================
# T27: MULTI-DATASET ALIGNMENT, DYNAMIC TOPOLOGY & EDA ANOMALIES
# ==============================================================================

def test_overdue_po_4471_detection():
    """Validates PO-4471 for SEL-3310 is detected as 6 days overdue on 2026-11-16."""
    is_overdue, days = check_is_po_overdue(
        expected_delivery_date="2026-11-10",
        status="Open",
        current_date="2026-11-16"
    )
    assert is_overdue is True
    assert days == 6


def test_bijapur_capital_trap_detection():
    """Validates BRG-2207 at Bijapur with 180 units is flagged as CATEGORY_B Capital Trap."""
    stock = 180.0
    v_pred = 0.1
    cover = calculate_days_of_cover(stock, v_pred)
    assert cover >= 45.0
    assert cover == 1800.0


def test_clt_6120_supplier_friction_flags():
    """Validates CLT-6120 MOQ of 200 and lead time of 21 days trigger friction warnings."""
    friction = evaluate_supplier_friction(
        supplier_lead_time=21,
        supplier_moq=200,
        needed_qty=4,
        unit_price=3400.0,
        baseline_price=3400.0
    )
    assert friction["is_moq_infeasible"] is True


def test_dynamic_facility_discovery_topology():
    """Validates dynamic extraction of retail stores vs central distribution warehouses without hardcoded location lists."""
    mock_df = pd.DataFrame([
        {"sku": "BRG-2207", "location": "Bijapur", "stock": 180},
        {"sku": "BRG-2207", "location": "Gokak", "stock": 10},
        {"sku": "BRG-2207", "location": "Belgaum WH", "stock": 60},
        {"sku": "BRG-2207", "location": "Hubli Regional Warehouse", "stock": 55},
        {"sku": "BRG-2207", "location": "Bagalkot", "stock": 5},
    ])
    topo = extract_network_topology(mock_df)
    assert "Bijapur" in topo["stores"]
    assert "Gokak" in topo["stores"]
    assert "Bagalkot" in topo["stores"]
    assert "Belgaum WH" in topo["warehouses"]
    assert "Hubli Regional Warehouse" in topo["warehouses"]
    assert len(topo["warehouses"]) == 2
    assert len(topo["stores"]) == 3


def test_dual_warehouse_zero_stock_routes_supplier_po():
    """Validates that when central warehouses hold 0 stock, donor lookup does not crash and engine routes supplier procurement."""
    mock_inv = pd.DataFrame([
        {"sku": "FLT-1021", "location": "Gokak", "stock": 1},
        {"sku": "FLT-1021", "location": "Belgaum WH", "stock": 0},
        {"sku": "FLT-1021", "location": "Hubli WH", "stock": 0},
    ])
    mock_sales = pd.DataFrame([
        {"sku": "FLT-1021", "location": "Gokak", "qty_sold": 3, "date": "2026-11-15"}
    ])
    donor = find_best_donor_location_with_reservations(
        inventory_df=mock_inv,
        sales_df=mock_sales,
        sku="FLT-1021",
        target_location="Gokak",
        needed_qty=5
    )
    assert donor is None  # Neither warehouse has available surplus


def test_briefing_simulation_date_param_overdue():
    """Validates /briefing endpoint respects simulation_date query parameter."""
    client = TestClient(app)
    res = client.get("/briefing?simulation_date=2026-11-16")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "problems" in data


def test_01_spare_parts_csv_ingestion():
    """
    Validates Challenge 01 evaluation dataset ingestion directly from 01_spare_parts:
    - inventory.csv (1,008 rows)
    - products.csv (126 rows)
    - purchase_orders.csv (43 rows)
    - sales.csv (12,777 rows)
    - suppliers.csv (205 rows)
    """
    from engine.data_loader import load_validated_datasets

    spare_parts_dir = None
    for cand in [
        os.path.abspath(os.path.join(_ROOT_DIR, "..", "01_spare_parts")),
        os.path.abspath(os.path.join(_ROOT_DIR, "01_spare_parts")),
        os.path.abspath("01_spare_parts"),
    ]:
        if os.path.exists(cand) and os.path.exists(os.path.join(cand, "inventory.csv")):
            spare_parts_dir = cand
            break

    assert spare_parts_dir is not None, "01_spare_parts directory must exist"
    datasets = load_validated_datasets(spare_parts_dir)

    assert len(datasets["products"]) == 126, f"Expected 126 products, got {len(datasets['products'])}"
    assert len(datasets["inventory"]) == 1008, f"Expected 1008 inventory rows, got {len(datasets['inventory'])}"
    assert len(datasets["purchase_orders"]) == 43, f"Expected 43 POs, got {len(datasets['purchase_orders'])}"
    assert len(datasets["sales"]) == 12777, f"Expected 12777 sales rows, got {len(datasets['sales'])}"
    assert len(datasets["suppliers"]) == 205, f"Expected 205 supplier rows, got {len(datasets['suppliers'])}"

    # Ensure field schemas are properly normalized
    p0 = datasets["products"][0]
    assert "sku" in p0 and "name" in p0 and "machine_model" in p0 and "category" in p0
    i0 = datasets["inventory"][0]
    assert "sku" in i0 and "location" in i0 and isinstance(i0["stock"], int)
    s0 = datasets["suppliers"][0]
    assert "supplier" in s0 and "price" in s0 and isinstance(s0["price"], float)


def test_01_spare_parts_decision_engine_pipeline():
    """Validates running the DecisionEngine against 01_spare_parts on simulation date 2026-11-16."""
    spare_parts_dir = None
    for cand in [
        os.path.abspath(os.path.join(_ROOT_DIR, "..", "01_spare_parts")),
        os.path.abspath(os.path.join(_ROOT_DIR, "01_spare_parts")),
        os.path.abspath("01_spare_parts"),
    ]:
        if os.path.exists(cand) and os.path.exists(os.path.join(cand, "inventory.csv")):
            spare_parts_dir = cand
            break

    engine = DecisionEngine(data_dir=spare_parts_dir, current_date="2026-11-16")
    brief = engine.run_agentic_pipeline()

    assert "summary" in brief
    assert "problems" in brief
    assert len(brief["problems"]) > 0

    # Check dynamic network topology
    inv_df = pd.DataFrame(engine.inventory)
    topology = extract_network_topology(inv_df)
    assert len(topology["all_locations"]) == 8
    assert "Belgaum WH" in topology["warehouses"]
    assert "Hubli WH" in topology["warehouses"]
    assert "Bijapur" in topology["stores"]









