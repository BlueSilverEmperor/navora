"""
Kaveri Spares & Hydraulics - FastAPI Service
Provides operational endpoints for Morning Briefing, Human-in-the-Loop Approval Gate,
Multi-Echelon Inventory Status, and Decision Audit Logs.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

# Ensure kaveri_copilot base directory is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.decision_agent import DecisionEngine
from engine.domain_math import validate_and_recalculate_transfer, evaluate_supplier_friction
from engine.mock_data_gen import seed_all_data

DATA_DIR = os.path.join(BASE_DIR, "data")
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.json")
ACTIVE_CHAOS_EVENTS: List[Dict[str, Any]] = []

app = FastAPI(
    title="Kaveri Spares & Hydraulics - Supply Chain Copilot API",
    description="Agentic Decision Engine & Purchasing Workflow for Ramesh Kulkarni (Head of Purchasing)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_audit_log() -> List[Dict[str, Any]]:
    if not os.path.exists(AUDIT_LOG_FILE):
        return []
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_audit_log(logs: List[Dict[str, Any]]):
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


class ActionPayload(BaseModel):
    sku: str
    qty: int
    from_location_or_supplier: Optional[str] = None
    from_location: Optional[str] = None
    to_location: str
    urgency: str = "IMMEDIATE"
    unit_cost_inr: float = 0.0
    total_estimated_cost_inr: float = 0.0
    expected_delivery_date: str = ""


class ActionApprovalRequest(BaseModel):
    problem_id: str
    action_type: str = Field(..., description="TRANSFER_REQUEST, PURCHASE_ORDER, or SUPPLIER_EXPEDITE_NOTICE")
    payload: Union[ActionPayload, Dict[str, Any]]
    approved_by: str = "Ramesh Kulkarni (Head of Purchasing)"
    notes: Optional[str] = "Approved via Autonomous Supply Chain Copilot"


class ActionRejectRequest(BaseModel):
    problem_id: str
    rejected_by: str = "Ramesh Kulkarni (Head of Purchasing)"
    reason: str = "Declined manual intervention"


@app.get("/", response_class=HTMLResponse)
def get_dashboard_ui():
    """Serves the standalone interactive executive cockpit UI."""
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        with open(static_file, "r", encoding="utf-8") as f:
            return f.read()
    root_file = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(root_file):
        with open(root_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Kaveri Spares Copilot UI</h1>"


@app.post("/reset-data")
def reset_benchmark_state():
    """Resets data to pristine benchmark state and clears active chaos events."""
    ACTIVE_CHAOS_EVENTS.clear()
    seed_all_data(DATA_DIR)
    if os.path.exists(AUDIT_LOG_FILE):
        os.remove(AUDIT_LOG_FILE)
    return {"status": "SUCCESS", "message": "Pristine benchmark state restored."}


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Kaveri Supply Chain Copilot API",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/briefing")
def get_morning_briefing(current_date: str = "2026-10-09"):
    """
    Runs the 6-step agentic pipeline and returns prioritized problems,
    domain metrics, evaluated options, and simulated action drafts.
    """
    engine = DecisionEngine(data_dir=DATA_DIR, current_date=current_date, chaos_events=ACTIVE_CHAOS_EVENTS)
    brief = engine.run_agentic_pipeline()
    return brief


@app.post("/action/approve")
def approve_action(req: ActionApprovalRequest):
    """
    Human-in-the-loop signoff gate.
    Executes the simulated action payload, updates inventory/PO records,
    and logs the decision into the audit trail.
    """
    inventory_path = os.path.join(DATA_DIR, "inventory.json")
    po_path = os.path.join(DATA_DIR, "purchase_orders.json")

    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    with open(po_path, "r", encoding="utf-8") as f:
        purchase_orders = json.load(f)

    if isinstance(req.payload, dict):
        sku = req.payload.get("sku")
        qty = req.payload.get("qty", 0)
        from_loc_or_sup = req.payload.get("from_location_or_supplier") or req.payload.get("from_location") or ""
        to_loc = req.payload.get("to_location", "")
        exp_date = req.payload.get("expected_delivery_date", "")
        payload_dict = req.payload
    else:
        sku = req.payload.sku
        qty = req.payload.qty
        from_loc_or_sup = req.payload.from_location_or_supplier or req.payload.from_location or ""
        to_loc = req.payload.to_location
        exp_date = req.payload.expected_delivery_date
        payload_dict = req.payload.model_dump()

    execution_details = {}

    if req.action_type == "TRANSFER_REQUEST":
        donor_loc = from_loc_or_sup
        if "Belgaum" in donor_loc and any(inv["sku"] == sku and inv["location"] == "Belgaum" for inv in inventory):
            donor_loc = "Belgaum"

        donor_found = False
        recip_found = False
        for inv in inventory:
            if inv["sku"] == sku and inv["location"] == donor_loc:
                inv["stock"] = max(0, inv["stock"] - qty)
                donor_found = True
            elif inv["sku"] == sku and inv["location"] == to_loc:
                inv["stock"] = inv["stock"] + qty
                recip_found = True

        if not recip_found and to_loc:
            inventory.append({"sku": sku, "location": to_loc, "stock": qty})

        with open(inventory_path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2)

        execution_details = {
            "type": "STOCK_REBALANCED",
            "transferred_qty": qty,
            "from": from_loc_or_sup,
            "to": to_loc
        }

    elif req.action_type == "PURCHASE_ORDER":
        po_id = f"PO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        new_po = {
            "po": po_id,
            "supplier": from_loc_or_sup,
            "sku": sku,
            "location": to_loc,
            "qty": qty,
            "expected_date": exp_date,
            "status": "ORDERED"
        }
        purchase_orders.append(new_po)
        with open(po_path, "w", encoding="utf-8") as f:
            json.dump(purchase_orders, f, indent=2)

        execution_details = {
            "type": "PURCHASE_ORDER_ISSUED",
            "po_number": po_id,
            "supplier": from_loc_or_sup,
            "qty": qty
        }

    elif req.action_type in ("SUPPLIER_EXPEDITE_NOTICE", "EXPEDITE_NOTICE"):
        # Update matching overdue PO
        updated = False
        for po in purchase_orders:
            if po["sku"] == sku and (po.get("supplier") == from_loc_or_sup or po.get("location") == to_loc) and po.get("status") != "DELIVERED":
                po["status"] = "EXPEDITED"
                updated = True

        with open(po_path, "w", encoding="utf-8") as f:
            json.dump(purchase_orders, f, indent=2)

        execution_details = {
            "type": "EXPEDITE_NOTICE_DISPATCHED",
            "supplier": from_loc_or_sup,
            "sku": sku
        }

    # Record Audit Entry
    logs = load_audit_log()
    audit_entry = {
        "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": datetime.now().isoformat(),
        "problem_id": req.problem_id,
        "action_type": req.action_type,
        "status": "APPROVED",
        "approved_by": req.approved_by,
        "payload": payload_dict,
        "execution_details": execution_details,
        "notes": req.notes
    }
    logs.insert(0, audit_entry)
    save_audit_log(logs)

    return {
        "status": "SUCCESS",
        "message": f"Action {req.action_type} successfully approved and executed.",
        "audit_entry": audit_entry
    }


@app.post("/action/reject")
def reject_action(req: ActionRejectRequest):
    """Logs rejection of a proposed action."""
    logs = load_audit_log()
    audit_entry = {
        "audit_id": f"AUD-{uuid.uuid4().hex[:8].upper()}",
        "timestamp": datetime.now().isoformat(),
        "problem_id": req.problem_id,
        "action_type": "REJECTION",
        "status": "REJECTED",
        "approved_by": req.rejected_by,
        "payload": {},
        "notes": req.reason
    }
    logs.insert(0, audit_entry)
    save_audit_log(logs)

    return {
        "status": "REJECTED",
        "message": f"Problem {req.problem_id} marked as rejected by {req.rejected_by}."
    }


@app.get("/inventory")
def get_inventory():
    """Returns current multi-echelon stock levels joined with product metadata."""
    inventory_path = os.path.join(DATA_DIR, "inventory.json")
    products_path = os.path.join(DATA_DIR, "products.json")

    with open(inventory_path, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    with open(products_path, "r", encoding="utf-8") as f:
        products = json.load(f)

    prod_map = {p["sku"]: p for p in products}

    enriched = []
    for inv in inventory:
        prod = prod_map.get(inv["sku"], {})
        enriched.append({
            "sku": inv["sku"],
            "name": prod.get("name", "Unknown"),
            "machine_model": prod.get("machine_model", "Unknown"),
            "category": prod.get("category", "General"),
            "location": inv["location"],
            "stock": inv["stock"]
        })

    return enriched


@app.get("/audit-log")
def get_audit_log():
    """Returns historical log of human decisions."""
    return load_audit_log()


class OverrideRecalculateRequest(BaseModel):
    problem_id: Optional[str] = "OVERRIDE"
    sku: Optional[str] = None
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    donor_location: Optional[str] = None
    target_location: Optional[str] = None
    override_qty: int


class RecalculateOverrideRequest(BaseModel):
    problem_id: Optional[str] = "OVERRIDE"
    sku: str
    donor_location: str
    target_location: str
    override_qty: int


class ChaosInjectionRequest(BaseModel):
    scenario: Optional[str] = None
    event_type: Optional[str] = None
    sku: Optional[str] = "FILTER-HYD-01"
    location: Optional[str] = "Gokak"
    value: Optional[float] = None
    multiplier_or_days: float = 1.0
    from_location: Optional[str] = None
    to_location: Optional[str] = None


@app.post("/action/recalculate-override")
def recalculate_override(req: RecalculateOverrideRequest):
    """
    Invokes calculate_donor_transfer_safety and returns revised cover days and 14-day projections without mutating state.
    """
    inv_file = os.path.join(DATA_DIR, "inventory.json")
    sales_file = os.path.join(DATA_DIR, "sales.json")

    with open(inv_file, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    with open(sales_file, "r", encoding="utf-8") as f:
        sales = json.load(f)

    from engine.domain_math import (
        calculate_daily_burn_rate,
        calculate_days_of_cover,
        calculate_donor_transfer_safety,
        generate_14day_projections,
    )

    donor_loc = req.donor_location
    if "Belgaum" in donor_loc and any(inv.get("sku") == req.sku and inv.get("location") == "Belgaum" for inv in inventory):
        donor_loc = "Belgaum"

    v_donor = calculate_daily_burn_rate(sales, req.sku, donor_loc, 30)
    v_target = calculate_daily_burn_rate(sales, req.sku, req.target_location, 30)

    donor_stock = 0
    target_stock = 0
    for inv in inventory:
        if inv.get("sku") == req.sku:
            if inv.get("location") == donor_loc:
                donor_stock = inv.get("stock", 0)
            elif inv.get("location") == req.target_location:
                target_stock = inv.get("stock", 0)

    safety = calculate_donor_transfer_safety(donor_stock, v_donor, req.override_qty)

    donor_remaining = donor_stock - req.override_qty
    target_new = target_stock + req.override_qty
    donor_revised_cover = calculate_days_of_cover(donor_remaining, v_donor)
    target_revised_cover = calculate_days_of_cover(target_new, v_target)

    projections = generate_14day_projections(
        current_stock=target_stock,
        daily_burn=v_target if v_target > 0 else 1.0,
        transfer_qty=req.override_qty,
        primary_lead_time=7,
        expedited_lead_time=3,
        expedited_qty=20,
        transfer_arrival_day=1
    )

    return {
        "status": "SUCCESS",
        "problem_id": req.problem_id,
        "sku": req.sku,
        "donor_location": req.donor_location,
        "target_location": req.target_location,
        "override_qty": req.override_qty,
        "donor_stock_remaining": donor_remaining,
        "donor_revised_cover_days": donor_revised_cover,
        "target_new_stock": target_new,
        "target_revised_cover_days": target_revised_cover,
        "revised_cost_inr": 250.0,
        "is_safe": safety["is_safe"],
        "max_safe_transfer_qty": safety["max_safe_transfer_qty"],
        "forward_projections": projections
    }


@app.post("/action/override-recalculate")
def override_recalculate(req: OverrideRecalculateRequest):
    """Alias for recalculate-override supporting legacy schema."""
    inv_file = os.path.join(DATA_DIR, "inventory.json")
    sales_file = os.path.join(DATA_DIR, "sales.json")

    with open(inv_file, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    with open(sales_file, "r", encoding="utf-8") as f:
        sales = json.load(f)

    from_loc = req.from_location
    to_loc = req.to_location
    sku = req.sku

    if not (from_loc and to_loc and sku):
        engine = DecisionEngine(data_dir=DATA_DIR)
        brief = engine.run_agentic_pipeline()
        for p in brief.get("problems", []):
            if p["problem_id"] == req.problem_id:
                pay = p["simulated_action"]["payload"]
                sku = sku or pay["sku"]
                from_loc = from_loc or pay["from_location_or_supplier"]
                to_loc = to_loc or pay["to_location"]
                break

    if not (from_loc and to_loc and sku):
        raise HTTPException(status_code=400, detail="Unable to resolve SKU or route for override recalculation")

    recalc = validate_and_recalculate_transfer(
        from_loc=from_loc,
        to_loc=to_loc,
        sku=sku,
        requested_qty=req.override_qty,
        inventory=inventory,
        sales=sales
    )

    return {
        "status": "SUCCESS",
        "problem_id": req.problem_id,
        "recalculation": recalc
    }


@app.post("/chaos/inject")
def inject_chaos(req: ChaosInjectionRequest):
    """
    Directly injects operational anomalies (Demand Surges, Route Closures, Supplier Delays)
    into the active engine state and immediately triggers agent re-evaluation.
    """
    event_dict = req.model_dump()
    # Normalize scenario vs event_type
    if req.scenario:
        if req.scenario in ("DEMAND_SPIKE", "Inject 3x Surge at Gokak"):
            event_dict["event_type"] = "DEMAND_SURGE"
            event_dict["multiplier_or_days"] = req.value if req.value is not None else 3.0
            event_dict["sku"] = req.sku or "FILTER-HYD-01"
            event_dict["location"] = req.location or "Gokak"
        elif req.scenario in ("TRANSFER_ROADBLOCK", "Block Belgaum Transfer Route"):
            event_dict["event_type"] = "TRANSFER_BLOCKED"
            event_dict["from_location"] = req.from_location or req.location or "Belgaum"
            event_dict["to_location"] = req.to_location or "Gokak"
            event_dict["sku"] = req.sku or "FILTER-HYD-01"
            event_dict["multiplier_or_days"] = 1.0
        elif req.scenario in ("SUPPLIER_HIKE", "Increase Supplier Lead Time by 5 Days"):
            event_dict["event_type"] = "SUPPLIER_DELAY"
            event_dict["sku"] = req.sku or "FILTER-HYD-01"
            event_dict["location"] = req.location or "Gokak"
            event_dict["multiplier_or_days"] = req.value if req.value is not None else 5.0
    elif not req.event_type:
        event_dict["event_type"] = "DEMAND_SURGE"
        if req.value is not None:
            event_dict["multiplier_or_days"] = req.value

    ACTIVE_CHAOS_EVENTS.append(event_dict)

    engine = DecisionEngine(
        data_dir=DATA_DIR,
        chaos_events=ACTIVE_CHAOS_EVENTS
    )
    new_brief = engine.run_agentic_pipeline()

    return {
        "status": "INJECTED",
        "scenario": req.scenario or event_dict.get("event_type"),
        "event": event_dict,
        "active_events_count": len(ACTIVE_CHAOS_EVENTS),
        "updated_briefing": new_brief
    }


@app.get("/suppliers/audit")
def audit_suppliers():
    """
    Evaluates supplier reliability and friction metrics:
    price variance against contract baseline, lead time feasibility, and MOQ risk.
    """
    sup_file = os.path.join(DATA_DIR, "suppliers.json")
    with open(sup_file, "r", encoding="utf-8") as f:
        suppliers = json.load(f)

    # Determine baseline price per SKU from primary supplier
    baseline_map = {}
    for s in suppliers:
        if s.get("is_primary", False):
            baseline_map[s["sku"]] = s["price"]

    audit_records = []
    for s in suppliers:
        sku = s["sku"]
        base_price = baseline_map.get(sku, s["price"])
        variance = round(((s["price"] - base_price) / base_price) * 100.0, 1) if base_price > 0 else 0.0

        audit_records.append({
            "supplier": s["supplier"],
            "sku": sku,
            "contract_type": "PRIMARY" if s.get("is_primary", False) else "SECONDARY",
            "unit_price_inr": s["price"],
            "baseline_price_inr": base_price,
            "price_variance_pct": variance,
            "lead_time_days": s["lead_time_days"],
            "moq": s["moq"],
            "moq_risk": "HIGH" if s["moq"] >= 50 else ("MEDIUM" if s["moq"] >= 20 else "LOW"),
            "status": "ACTIVE"
        })

    return audit_records


@app.post("/reset-data")
def reset_mock_data():
    """Re-seeds initial benchmark data and clears audit trail and chaos events."""
    global ACTIVE_CHAOS_EVENTS
    ACTIVE_CHAOS_EVENTS = []
    seed_all_data(DATA_DIR)
    if os.path.exists(AUDIT_LOG_FILE):
        os.remove(AUDIT_LOG_FILE)
    return {"status": "SUCCESS", "message": "Benchmark dataset and chaos state reset to initial state."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=True)


