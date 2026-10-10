"""
Kaveri Spares & Hydraulics - FastAPI Service
Provides operational endpoints for Morning Briefing, Human-in-the-Loop Approval Gate,
Multi-Echelon Inventory Status, and Decision Audit Logs.
"""

import json
import os
import sys
import uuid
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Set

# Ensure kaveri_copilot base directory is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.decision_agent import DecisionEngine
from engine.domain_math import validate_and_recalculate_transfer, evaluate_supplier_friction, compute_plan_diff
from engine.mock_data_gen import seed_all_data
from engine.persistence import (
    log_audit_trail,
    get_all_audit_logs,
    is_action_already_processed,
    record_action_processed,
    create_stock_reservation,
    release_stock_reservation,
    get_active_stock_reservations,
    record_rejection_memory,
    get_all_rejection_memories,
    clear_all_persistence
)

DATA_DIR = os.path.join(BASE_DIR, "data")
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.json")
ACTIVE_CHAOS_EVENTS: List[Dict[str, Any]] = []
PROCESSED_ACTION_HASHES: Set[str] = set()
ACTIVE_TRANSFER_RESERVATIONS: Dict[str, int] = {}

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
    return get_all_audit_logs()


def save_audit_log(logs: List[Dict[str, Any]]):
    pass  # Maintained for interface compatibility; SQLite handles persistence



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
    approved_by: Optional[str] = "Ramesh Kulkarni (Head of Purchasing)"
    notes: Optional[str] = "Approved via Autonomous Supply Chain Copilot"
    client_request_id: Optional[str] = None


ApproveActionRequest = ActionApprovalRequest


def log_audit_trail_entry(
    problem_id: str,
    action_type: str,
    status: str,
    payload: dict,
    approved_by: str = "Ramesh Kulkarni (Head of Purchasing)",
    execution_details: dict = None,
    notes: str = None
) -> Dict[str, Any]:
    return log_audit_trail(
        problem_id=problem_id,
        action_type=action_type,
        status=status,
        payload=payload,
        approved_by=approved_by,
        execution_details=execution_details or {},
        notes=notes or "Approved via Autonomous Supply Chain Copilot"
    )


class ActionRejectRequest(BaseModel):
    problem_id: str
    rejected_by: str = "Ramesh Kulkarni (Head of Purchasing)"
    reason: str = "Declined manual intervention"


@app.get("/", response_class=HTMLResponse)
def get_dashboard_ui():
    """Serves the standalone interactive executive cockpit UI."""
    # Check NAVORA dashboard.html in workspace root
    parent_dir = os.path.dirname(BASE_DIR)
    navora_dashboard = os.path.join(parent_dir, "NAVORA", "dashboard.html")
    if os.path.exists(navora_dashboard):
        with open(navora_dashboard, "r", encoding="utf-8") as f:
            return f.read()

    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        with open(static_file, "r", encoding="utf-8") as f:
            return f.read()

    root_file = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(root_file):
        with open(root_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>NAVORA / Kaveri Spares Copilot UI</h1>"


@app.post("/reset-data")
@app.post("/api/reset-data")
def reset_benchmark_state():
    """Resets data to pristine benchmark state and clears active chaos events and persistence."""
    ACTIVE_CHAOS_EVENTS.clear()
    PROCESSED_ACTION_HASHES.clear()
    ACTIVE_TRANSFER_RESERVATIONS.clear()
    clear_all_persistence()
    seed_all_data(DATA_DIR)
    return {"status": "SUCCESS", "message": "Pristine benchmark state restored."}


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Kaveri Supply Chain Copilot API",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/briefing")
@app.get("/api/briefing")
def get_morning_briefing(
    current_date: Optional[str] = Query(default=None),
    simulation_date: Optional[str] = Query(default="2026-11-16")
):
    """
    Runs the 6-step agentic pipeline and returns prioritized problems,
    domain metrics, evaluated options, and simulated action drafts.
    """
    sim_date = current_date if current_date is not None else (simulation_date or "2026-11-16")
    engine = DecisionEngine(
        data_dir=DATA_DIR,
        current_date=sim_date,
        chaos_events=ACTIVE_CHAOS_EVENTS,
        active_reservations=get_active_stock_reservations()
    )
    brief = engine.run_agentic_pipeline()
    for p in brief.get("problems", []):
        dm = p.get("domain_metrics", {})
        vel = p.get("adaptive_velocity", {})
        if "current_stock" not in p:
            p["current_stock"] = dm.get("current_stock", 0)
        if "v_predicted" not in p:
            p["v_predicted"] = dm.get("daily_burn_rate", vel.get("v_recent", 1.0))
        if "days_of_cover" not in p:
            p["days_of_cover"] = dm.get("days_of_cover", 0.0)
        if "stockout_gap_days" not in p:
            p["stockout_gap_days"] = dm.get("stockout_gap_days", 0.0)
        if "alternatives" not in p:
            p["alternatives"] = p.get("evaluated_options", [])
    return brief


@app.get("/api/backtest")
def get_backtest_metrics(days: int = 60):
    """
    Replays historical sales across the multi-echelon network and returns
    stockouts prevented, lost units averted, and Rs. saved vs baseline.
    """
    from scripts.backtest import run_backtest
    return run_backtest(data_dir=DATA_DIR, days=days)


@app.get("/api/optimizer/transfers")
def get_global_network_transfers(
    current_date: Optional[str] = Query(default=None),
    simulation_date: Optional[str] = Query(default="2026-11-16")
):
    """
    Solves all lateral inventory transfers jointly across the network using
    PuLP Integer Linear Programming with greedy comparison and fallback.
    """
    sim_date = current_date if current_date is not None else (simulation_date or "2026-11-16")
    engine = DecisionEngine(
        data_dir=DATA_DIR,
        current_date=sim_date,
        chaos_events=ACTIVE_CHAOS_EVENTS,
        active_reservations=get_active_stock_reservations()
    )
    brief = engine.run_agentic_pipeline()
    return brief.get("network_transfer_plan", {})


@app.get("/api/suppliers/reliability")
def get_supplier_reliability_audit(
    current_date: Optional[str] = Query(default=None),
    simulation_date: Optional[str] = Query(default="2026-11-16")
):
    """
    Computes actual vs promised delivery slippage per supplier and returns
    learned adjusted lead times and reliability statuses.
    """
    sim_date = current_date if current_date is not None else (simulation_date or "2026-11-16")
    engine = DecisionEngine(
        data_dir=DATA_DIR,
        current_date=sim_date,
        chaos_events=ACTIVE_CHAOS_EVENTS,
        active_reservations=get_active_stock_reservations()
    )
    brief = engine.run_agentic_pipeline()
    return brief.get("supplier_reliability", {})






@app.post("/action/approve")
@app.post("/api/action/approve")
def approve_action(req: ActionApprovalRequest):
    """
    Human-in-the-loop signoff gate.
    Executes the simulated action payload, updates inventory/PO records,
    and logs the decision into the audit trail with idempotency and safety buffer guards.
    """
    if isinstance(req.payload, dict):
        payload_dict = req.payload
        sku = payload_dict.get("sku")
        qty = int(payload_dict.get("qty", 0))
        from_loc = payload_dict.get("from_location") or payload_dict.get("from_location_or_supplier") or ""
        to_loc = payload_dict.get("to_location", "")
        exp_date = payload_dict.get("expected_delivery_date", "")
    else:
        payload_dict = req.payload.model_dump() if hasattr(req.payload, "model_dump") else req.payload.dict()
        sku = req.payload.sku
        qty = int(req.payload.qty)
        from_loc = req.payload.from_location or req.payload.from_location_or_supplier or ""
        to_loc = req.payload.to_location
        exp_date = req.payload.expected_delivery_date

    # 1. Idempotency Check
    action_payload_signature = hashlib.sha256(
        f"{req.problem_id}:{req.action_type}:{sku}:{from_loc}:{to_loc}:{qty}".encode()
    ).hexdigest()

    idempotency_key = req.client_request_id or action_payload_signature
    if (
        is_action_already_processed(idempotency_key)
        or is_action_already_processed(action_payload_signature)
        or idempotency_key in PROCESSED_ACTION_HASHES
        or action_payload_signature in PROCESSED_ACTION_HASHES
    ):
        raise HTTPException(
            status_code=409,
            detail="Duplicate action detected: this proposal has already been approved and executed."
        )

    execution_details = {}

    # 2. Atomic Pre-Commit Balance & Donor Buffer Verification
    if req.action_type == "TRANSFER_REQUEST":
        state = get_runtime_state()
        inv_df = state["inventory"]

        # Match donor location
        donor_rows = inv_df[(inv_df["sku"] == sku) & (inv_df["location"] == from_loc)]
        if donor_rows.empty and from_loc:
            prefix = from_loc.split()[0]
            donor_rows = inv_df[(inv_df["sku"] == sku) & (inv_df["location"].str.contains(prefix, case=False, na=False))]

        if donor_rows.empty:
            raise HTTPException(
                status_code=400,
                detail=f"Donor location {from_loc} does not carry SKU {sku}."
            )

        matched_from_loc = donor_rows.iloc[0]["location"]
        current_donor_stock = int(donor_rows.iloc[0]["current_stock"])

        sales_df = state["sales"]
        sub_sales = sales_df[(sales_df["sku"] == sku) & (sales_df["location"] == matched_from_loc)]
        donor_v = (
            float(sub_sales["qty_sold"].tail(30).mean())
            if len(sub_sales) > 0
            else 0.05
        )

        # Validate physical availability
        if current_donor_stock < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock: {matched_from_loc} has {current_donor_stock} units, cannot transfer {qty}."
            )

        # Validate 15-day safety retention constraint
        post_transfer_cover = (current_donor_stock - qty) / (
            donor_v if donor_v > 0 else 0.05
        )
        if post_transfer_cover < 15.0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Safety buffer violation: Transfer would leave donor {matched_from_loc} with "
                    f"{round(post_transfer_cover, 1)} days cover (< 15.0 days minimum)."
                )
            )

        # 3. Apply State Mutation to inventory.json
        inventory_path = os.path.join(DATA_DIR, "inventory.json")
        with open(inventory_path, "r", encoding="utf-8") as f:
            inventory = json.load(f)

        donor_found = False
        recip_found = False
        for inv in inventory:
            if inv["sku"] == sku and inv["location"] == matched_from_loc:
                inv["stock"] = max(0, inv["stock"] - qty)
                donor_found = True
            elif inv["sku"] == sku and (inv["location"] == to_loc or to_loc in inv["location"]):
                inv["stock"] = inv["stock"] + qty
                recip_found = True

        if not recip_found and to_loc:
            inventory.append({"sku": sku, "location": to_loc, "stock": qty})

        with open(inventory_path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2)

        # Release any reservations
        res_key = f"{matched_from_loc}:{sku}"
        if res_key in ACTIVE_TRANSFER_RESERVATIONS:
            ACTIVE_TRANSFER_RESERVATIONS[res_key] = max(
                0, ACTIVE_TRANSFER_RESERVATIONS[res_key] - qty
            )

        execution_details = {
            "type": "STOCK_REBALANCED",
            "transferred_qty": qty,
            "from": matched_from_loc,
            "to": to_loc
        }

    elif req.action_type == "PURCHASE_ORDER":
        po_path = os.path.join(DATA_DIR, "purchase_orders.json")
        with open(po_path, "r", encoding="utf-8") as f:
            purchase_orders = json.load(f)

        po_id = f"PO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        new_po = {
            "po": po_id,
            "supplier": from_loc,
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
            "supplier": from_loc,
            "qty": qty
        }

    elif req.action_type in ("SUPPLIER_EXPEDITE_NOTICE", "EXPEDITE_NOTICE"):
        po_path = os.path.join(DATA_DIR, "purchase_orders.json")
        with open(po_path, "r", encoding="utf-8") as f:
            purchase_orders = json.load(f)

        for po in purchase_orders:
            if po["sku"] == sku and (po.get("supplier") == from_loc or po.get("location") == to_loc) and po.get("status") not in ("DELIVERED", "CANCELLED"):
                po["status"] = "EXPEDITED"

        with open(po_path, "w", encoding="utf-8") as f:
            json.dump(purchase_orders, f, indent=2)

        execution_details = {
            "type": "EXPEDITE_NOTICE_DISPATCHED",
            "supplier": from_loc,
            "sku": sku
        }

    # 4. Mark Idempotency Signature & Release Reservation & Record Audit Log
    PROCESSED_ACTION_HASHES.add(idempotency_key)
    PROCESSED_ACTION_HASHES.add(action_payload_signature)
    record_action_processed(idempotency_key, req.problem_id)
    if action_payload_signature != idempotency_key:
        record_action_processed(action_payload_signature, req.problem_id)
    release_stock_reservation(req.problem_id)
    record_entry = log_audit_trail_entry(
        problem_id=req.problem_id,
        action_type=req.action_type,
        status="APPROVED",
        payload=payload_dict,
        approved_by=req.approved_by or "Ramesh Kulkarni (Head of Purchasing)",
        execution_details=execution_details,
        notes=req.notes or "Approved via Autonomous Supply Chain Copilot"
    )

    return {
        "status": "SUCCESS",
        "action_id": idempotency_key,
        "message": f"Action {req.action_type} successfully approved and balances mutated for {sku}.",
        "audit_entry": record_entry,
        "audit_record": record_entry
    }


@app.post("/action/reject")
@app.post("/api/action/reject")
def reject_action(req: ActionRejectRequest):
    """Logs rejection of a proposed action, frees held stock reservations, and stores rejection memory."""
    release_stock_reservation(req.problem_id)
    audit_entry = log_audit_trail_entry(
        problem_id=req.problem_id,
        action_type="REJECTION",
        status="REJECTED",
        payload={},
        approved_by=req.rejected_by,
        notes=req.reason
    )

    # Resolve incident metadata to record rejection memory
    engine = DecisionEngine(data_dir=DATA_DIR)
    brief = engine.run_agentic_pipeline()
    prob = next((p for p in brief.get("problems", []) if p["problem_id"] == req.problem_id), None)
    sku = prob.get("sku") if prob else None
    loc = prob.get("location") if prob else None
    src = prob.get("simulated_action", {}).get("payload", {}).get("from_location_or_supplier") if prob else None
    act_type = prob.get("simulated_action", {}).get("action_type") if prob else None

    mem = record_rejection_memory(
        problem_id=req.problem_id,
        sku=sku,
        location=loc,
        rejected_source=src,
        action_type=act_type,
        rejection_reason=req.reason
    )

    return {
        "status": "REJECTED",
        "message": f"Problem {req.problem_id} marked as rejected by {req.rejected_by}.",
        "rejection_memory": mem
    }


@app.post("/action/dismiss")
@app.post("/api/action/dismiss")
def dismiss_action(req: ActionRejectRequest):
    """Dismisses an incident and releases any associated reservations."""
    release_stock_reservation(req.problem_id)
    audit_entry = log_audit_trail_entry(
        problem_id=req.problem_id,
        action_type="DISMISSAL",
        status="DISMISSED",
        payload={},
        approved_by=req.rejected_by,
        notes=req.reason
    )
    return {
        "status": "DISMISSED",
        "message": f"Problem {req.problem_id} dismissed."
    }


@app.get("/inventory")
@app.get("/api/inventory")
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
@app.get("/api/audit-log")
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


def get_runtime_state(current_date: str = "2026-10-09") -> Dict[str, Any]:
    """Fetches current memory/JSON records and runs agentic pipeline."""
    import pandas as pd
    engine = DecisionEngine(data_dir=DATA_DIR, current_date=current_date, chaos_events=ACTIVE_CHAOS_EVENTS)
    brief = engine.run_agentic_pipeline()
    inv_df = pd.DataFrame(engine.inventory)
    sales_df = pd.DataFrame(engine.sales)
    sup_df = pd.DataFrame(engine.suppliers)
    prod_df = pd.DataFrame(engine.products)
    po_df = pd.DataFrame(engine.purchase_orders)
    if "stock" in inv_df.columns and "current_stock" not in inv_df.columns:
        inv_df["current_stock"] = inv_df["stock"]
    elif "current_stock" in inv_df.columns and "stock" not in inv_df.columns:
        inv_df["stock"] = inv_df["current_stock"]

    return {
        "engine": engine,
        "problems": brief.get("problems", []),
        "inventory": inv_df,
        "sales": sales_df,
        "suppliers": sup_df,
        "products": prod_df,
        "purchase_orders": po_df,
    }


@app.post("/action/recalculate-override")
@app.post("/api/action/recalculate-override")
@app.post("/api/recalculate-override")
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
    matched_donor = next(
        (inv.get("location") for inv in inventory if inv.get("sku") == req.sku and (inv.get("location") == donor_loc or donor_loc in str(inv.get("location")))),
        donor_loc
    )
    donor_loc = matched_donor

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

    # Dynamic supplier lead time lookup
    prim_lead = 7
    exp_lead = 3
    replenish_qty = 20
    sup_file = os.path.join(DATA_DIR, "suppliers.json")
    if os.path.exists(sup_file):
        try:
            with open(sup_file, "r", encoding="utf-8") as f:
                suppliers = json.load(f)
            sku_sups = [s for s in suppliers if s.get("sku") == req.sku]
            if sku_sups:
                prim_lead = int(sku_sups[0].get("lead_time_days", 7))
                replenish_qty = int(sku_sups[0].get("moq", 20))
                if len(sku_sups) > 1:
                    exp_lead = int(sku_sups[1].get("lead_time_days", 3))
        except Exception:
            pass

    projections = generate_14day_projections(
        current_stock=target_stock,
        daily_burn=v_target if v_target > 0 else 1.0,
        transfer_qty=req.override_qty,
        primary_lead_time=prim_lead,
        expedited_lead_time=exp_lead,
        replenishment_order_qty=replenish_qty,
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
        "remaining_cover_days": donor_revised_cover,
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
@app.post("/api/chaos/inject")
def inject_chaos(req: ChaosInjectionRequest):
    """
    Directly injects operational anomalies (Demand Surges, Route Closures, Supplier Delays)
    into the active engine state and immediately triggers agent re-evaluation.
    """
    event_dict = req.model_dump()
    # Normalize scenario vs event_type
    ev = req.scenario or req.event_type or ""
    if ev in ("DEMAND_SPIKE", "DEMAND_SURGE", "Inject 3x Surge at Gokak"):
        event_dict["event_type"] = "DEMAND_SURGE"
        event_dict["multiplier_or_days"] = req.value if req.value is not None else 3.0
        event_dict["sku"] = req.sku or "FILTER-HYD-01"
        event_dict["location"] = req.location or "Gokak"
    elif ev in ("TRANSFER_ROADBLOCK", "TRANSFER_BLOCKED", "ROUTE_BLOCKED", "Block Belgaum Transfer Route"):
        event_dict["event_type"] = "TRANSFER_BLOCKED"
        event_dict["from_location"] = req.from_location or req.location or "Belgaum"
        event_dict["to_location"] = req.to_location or "Gokak"
        event_dict["sku"] = req.sku or "FILTER-HYD-01"
        event_dict["multiplier_or_days"] = 1.0
    elif ev in ("SUPPLIER_HIKE", "SUPPLIER_DELAY", "Increase Supplier Lead Time by 5 Days"):
        event_dict["event_type"] = "SUPPLIER_DELAY"
        event_dict["sku"] = req.sku or "FILTER-HYD-01"
        event_dict["location"] = req.location or "Gokak"
        event_dict["multiplier_or_days"] = req.value if req.value is not None else 5.0
    elif ev in ("SUPPLIER_PRICE_HIKE", "PRICE_HIKE"):
        event_dict["event_type"] = "SUPPLIER_PRICE_HIKE"
        event_dict["sku"] = req.sku or "FILTER-HYD-01"
        event_dict["location"] = req.location or "Gokak"
        event_dict["multiplier_or_days"] = req.value if req.value is not None else 0.20
    elif not req.event_type:
        event_dict["event_type"] = "DEMAND_SURGE"
        if req.value is not None:
            event_dict["multiplier_or_days"] = req.value

    # Capture plan before chaos injection
    before_engine = DecisionEngine(
        data_dir=DATA_DIR,
        chaos_events=list(ACTIVE_CHAOS_EVENTS)
    )
    before_brief = before_engine.run_agentic_pipeline()

    ACTIVE_CHAOS_EVENTS.append(event_dict)

    # Capture plan after chaos injection
    after_engine = DecisionEngine(
        data_dir=DATA_DIR,
        chaos_events=list(ACTIVE_CHAOS_EVENTS)
    )
    after_brief = after_engine.run_agentic_pipeline()

    # Compute structured before vs after plan diff with reasons
    plan_diff = compute_plan_diff(before_brief, after_brief, event_dict)

    return {
        "status": "INJECTED",
        "scenario": req.scenario or event_dict.get("event_type"),
        "event": event_dict,
        "active_events_count": len(ACTIVE_CHAOS_EVENTS),
        "plan_diff": plan_diff,
        "updated_briefing": after_brief
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


# -----------------------------------------------------------------------------
# NAVORA Direct Integration Endpoints
# -----------------------------------------------------------------------------

def _format_navora_telemetry(selected_p: Dict[str, Any], problems: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Transform evaluated_options to NAVORA format
    mitigation_options = []
    for idx, opt in enumerate(selected_p.get("evaluated_options", [])):
        opt_id = f"OPT-{idx+1}"
        is_transfer = "Internal" in opt.get("option_name", "") or "Transfer" in opt.get("option_name", "")
        opt_type = "INTER_WAREHOUSE_TRANSFER" if is_transfer else "EXPEDITED_PO"
        mitigation_options.append({
            "option_id": opt_id,
            "pathway_name": opt.get("option_name", f"Option {idx+1}"),
            "type": opt_type,
            "source_facility": opt.get("source", "Central Distribution Center"),
            "source_facility_id": opt.get("source", "Belgaum"),
            "speed_hours": int(opt.get("lead_time_days", opt.get("delivery_time_days", 1)) * 24),
            "lead_time_days": opt.get("lead_time_days", opt.get("delivery_time_days", 1)),
            "cost_impact_inr": opt.get("estimated_cost_inr", 0.0),
            "cost_impact_usd": round(opt.get("estimated_cost_inr", 0.0) / 83.0, 2),
            "recommended": (idx == 0 and opt.get("feasibility_status") == "FEASIBLE"),
            "feasibility": opt.get("feasibility", "FEASIBLE"),
            "feasibility_status": opt.get("feasibility_status", "FEASIBLE"),
            "quantity": selected_p.get("simulated_action", {}).get("payload", {}).get("qty", 14),
            "trade_off_summary": opt.get("trade_off_summary", opt.get("pros_cons", ""))
        })

    # Summary list of all detected incidents for the dropdown switcher
    all_incidents = []
    for p in problems:
        all_incidents.append({
            "problem_id": p.get("problem_id"),
            "sku": p.get("sku"),
            "sku_name": p.get("sku_name", p.get("sku")),
            "location": p.get("location"),
            "severity": p.get("severity"),
            "category": p.get("category"),
            "category_code": p.get("category_code"),
            "days_of_cover": p.get("domain_metrics", {}).get("days_of_cover", 0.0),
            "burn_rate": p.get("domain_metrics", {}).get("daily_burn_rate", 0.0),
            "label": f"[{p.get('severity')}] {p.get('location')} — {p.get('sku')} ({p.get('category_code', p.get('category'))})"
        })

    m = selected_p.get("domain_metrics", {})
    return {
        **selected_p,
        "incident_id": selected_p.get("problem_id"),
        "problem_id": selected_p.get("problem_id"),
        "facility_id": selected_p.get("location"),
        "facility_name": f"{selected_p.get('location')} Facility",
        "sku": selected_p.get("sku"),
        "sku_name": selected_p.get("sku_name", selected_p.get("sku")),
        "severity": selected_p.get("severity"),
        "category": selected_p.get("category"),
        "category_code": selected_p.get("category_code"),
        "current_stock": m.get("current_stock", 0),
        "daily_burn_rate": m.get("daily_burn_rate", 1.0),
        "days_of_cover": m.get("days_of_cover", 0.0),
        "standard_lead_time_days": m.get("primary_supplier_lead_time_days", 7),
        "stockout_gap_days": m.get("stockout_gap_days", 0.0),
        "root_cause": selected_p.get("diagnosis", ""),
        "decision_rationale": selected_p.get("decision_rationale", ""),
        "status": "PENDING_REVIEW",
        "mitigation_options": mitigation_options,
        "math_explainability": selected_p.get("math_explainability", {}),
        "forward_projections": selected_p.get("forward_projections", {}),
        "simulated_action": selected_p.get("simulated_action", {}),
        "all_incidents": all_incidents
    }


@app.get("/api/telemetry")
def get_telemetry(
    problem_id: Optional[str] = None,
    sku: Optional[str] = None,
    location: Optional[str] = None,
    current_date: str = "2026-10-09"
):
    state = get_runtime_state(current_date=current_date)
    problems = state["problems"]

    # 1. Lookup by problem_id across dynamically detected incidents
    if problem_id:
        prob = next((p for p in problems if p.get("problem_id") == problem_id), None)
        if prob:
            return _format_navora_telemetry(prob, problems)
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry not found for query (problem_id={problem_id}, sku={sku}, location={location})"
        )

    # 2. Dynamic on-the-fly telemetry computation for unseen SKU & location
    if sku and location:
        inv = state["inventory"]
        row = inv[(inv["sku"] == sku) & (inv["location"] == location)]
        if not row.empty:
            stock = int(row.iloc[0]["current_stock"])
            sup = state["suppliers"][state["suppliers"]["sku"] == sku]
            lead_time = int(sup.iloc[0]["lead_time_days"]) if not sup.empty else 7

            from engine.domain_math import compute_adaptive_velocity
            telemetry = compute_adaptive_velocity(
                state["sales"], sku, location, stock, lead_time
            )
            return {
                "sku": sku,
                "location": location,
                "current_stock": stock,
                **telemetry
            }
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry not found for query (problem_id={problem_id}, sku={sku}, location={location})"
        )

    # 3. Default call (e.g. initial frontend load without parameters)
    if not problems:
        raise HTTPException(
            status_code=404,
            detail=f"Telemetry not found for query (problem_id={problem_id}, sku={sku}, location={location})"
        )

    selected_p = next((p for p in problems if p.get("sku") == "FILTER-HYD-01" and p.get("location") == "Gokak"), problems[0])
    return _format_navora_telemetry(selected_p, problems)


class NavoraRecalculateRequest(BaseModel):
    option_id: Optional[str] = "OPT-1"
    quantity: int
    user_override_text: Optional[str] = None
    problem_id: Optional[str] = None
    sku: Optional[str] = None
    donor_location: Optional[str] = None
    target_location: Optional[str] = None


@app.post("/api/recalculate")
def recalculate_navora(req: NavoraRecalculateRequest):
    """
    Instant mathematical recalculation for NAVORA UI overrides.
    """
    sku = req.sku or "FILTER-HYD-01"
    target_loc = req.target_location or "Gokak"
    donor_loc = req.donor_location or "Belgaum"

    recalc_req = RecalculateOverrideRequest(
        problem_id=req.problem_id or "PROB-GOKAK-FILTER",
        sku=sku,
        donor_location=donor_loc,
        target_location=target_loc,
        override_qty=req.quantity
    )
    res = recalculate_override(recalc_req)
    
    return {
        "option_id": req.option_id,
        "original_quantity": 14,
        "new_quantity": req.quantity,
        "resulting_days_of_cover": res["target_revised_cover_days"],
        "new_cost_impact_inr": res["revised_cost_inr"],
        "new_cost_impact_usd": round(res["revised_cost_inr"] / 83.0, 2),
        "source_remaining_stock": res["donor_stock_remaining"],
        "source_remaining_cover": res["donor_revised_cover_days"],
        "source_is_safe": res["is_safe"],
        "max_safe_transfer_qty": res["max_safe_transfer_qty"],
        "forward_projections": res["forward_projections"],
        "summary_notes": (
            f"Recalculated with {req.quantity} units. Resulting {target_loc} cover: {res['target_revised_cover_days']:.1f} days. "
            f"Donor {donor_loc} retaining {res['donor_revised_cover_days']:.1f} days cover (Safe >= 15d: {res['is_safe']})."
        )
    }


class NavoraApproveRequest(BaseModel):
    action_type: str = "INTER_WAREHOUSE_TRANSFER"
    request_id: Optional[str] = "TR-8821"
    source_warehouse: Optional[str] = "Belgaum"
    destination_warehouse: Optional[str] = "Gokak"
    sku: Optional[str] = "FILTER-HYD-01"
    quantity: int = 14
    freight_cost_usd: Optional[float] = None
    freight_cost_inr: Optional[float] = 250.0
    eta_hours: Optional[int] = 24
    manager_override: Optional[Any] = None
    problem_id: Optional[str] = "PROB-GOKAK-FILTER"


@app.post("/api/actions/approve")
def approve_navora(req: NavoraApproveRequest):
    """
    Executes approval via NAVORA UI.
    """
    action_type_mapped = "TRANSFER_REQUEST" if "TRANSFER" in req.action_type.upper() else "PURCHASE_ORDER"
    payload = {
        "sku": req.sku or "FILTER-HYD-01",
        "qty": req.quantity,
        "from_location": req.source_warehouse or "Belgaum",
        "from_location_or_supplier": req.source_warehouse or "Belgaum",
        "to_location": req.destination_warehouse or "Gokak",
        "unit_cost_inr": 0.0,
        "total_estimated_cost_inr": req.freight_cost_inr or 250.0
    }
    
    appr_req = ActionApprovalRequest(
        problem_id=req.problem_id or "PROB-GOKAK-FILTER",
        action_type=action_type_mapped,
        payload=payload,
        approved_by="Ramesh Kulkarni (Head of Purchasing)",
        notes=f"Approved via NAVORA HITL Cockpit. Override: {req.manager_override or 'None'}"
    )
    res = approve_action(appr_req)
    audit_entry = res["audit_entry"]
    
    inv_path = os.path.join(DATA_DIR, "inventory.json")
    with open(inv_path, "r", encoding="utf-8") as f:
        inv = json.load(f)
    
    src_stock = next((i["stock"] for i in inv if i["sku"] == (req.sku or "FILTER-HYD-01") and i["location"] == (req.source_warehouse or "Belgaum")), 26)
    dest_stock = next((i["stock"] for i in inv if i["sku"] == (req.sku or "FILTER-HYD-01") and i["location"] == (req.destination_warehouse or "Gokak")), 22)
    
    return {
        "status": "DISPATCHED",
        "receipt_id": req.request_id,
        "transaction_id": audit_entry["audit_id"],
        "dispatch_message": f"Action {req.action_type} ({req.request_id}) dispatched to {req.source_warehouse or 'Belgaum'} hub.",
        "inventory_summary": f"Inventory state updated: {req.destination_warehouse or 'Gokak'} (+{req.quantity} units, total {dest_stock}), {req.source_warehouse or 'Belgaum'} (-{req.quantity} units, remaining {src_stock}).",
        "ledger_breakdown": {
            "destination": {
                "facility": req.destination_warehouse or "Gokak",
                "on_hand": dest_stock,
                "in_transit": req.quantity,
                "effective_total": dest_stock,
                "resulting_days_of_cover": round(dest_stock / 4.0, 1)
            },
            "source": {
                "facility": req.source_warehouse or "Belgaum",
                "on_hand": src_stock,
                "allocated": req.quantity,
                "retained_surplus": src_stock,
                "threshold_compliant": src_stock >= 8
            }
        },
        "audit_meta": audit_entry
    }


@app.post("/api/actions/reject")
def reject_navora(req: Dict[str, Any]):
    rej_req = ActionRejectRequest(
        problem_id=req.get("incident_id") or req.get("problem_id") or "PROB-REJECT",
        rejected_by="Ramesh Kulkarni (Head of Purchasing)",
        reason=req.get("notes") or req.get("reason_code") or "Manual manager rejection"
    )
    return reject_action(rej_req)


@app.get("/api/ledger")
def get_navora_ledger():
    return {
        "inventory": get_inventory(),
        "audit_ledger": load_audit_log(),
        "audit_transactions_count": len(load_audit_log())
    }


@app.post("/api/reset")
def reset_navora_state():
    return reset_benchmark_state()


@app.post("/api/chaos")
def inject_chaos_navora(req: ChaosInjectionRequest):
    return inject_chaos(req)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.server:app", host="127.0.0.1", port=8000, reload=True)


