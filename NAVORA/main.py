from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import datetime
import uuid
import os

app = FastAPI(
    title="NAVORA — Autonomous Procurement & Inventory Engine",
    description="Backend API and HITL Orchestrator serving real-time telemetry, mathematical recalculations, and virtual ledger execution.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# In-Memory Database / State Store
# -----------------------------------------------------------------------------
INITIAL_WAREHOUSES = {
    "FAC-GOKAK-01": {
        "facility_id": "FAC-GOKAK-01",
        "name": "Gokak Regional Facility",
        "sku": "OF-4420",
        "sku_name": "Heavy-Duty Oil Filter",
        "on_hand": 6,
        "in_transit": 0,
        "allocated": 0,
        "daily_burn_rate": 3.0,
        "safety_threshold": 15
    },
    "FAC-BELGAUM-HUB": {
        "facility_id": "FAC-BELGAUM-HUB",
        "name": "Belgaum Distribution Center",
        "sku": "OF-4420",
        "sku_name": "Heavy-Duty Oil Filter",
        "on_hand": 48,
        "in_transit": 0,
        "allocated": 0,
        "daily_burn_rate": 2.0,
        "safety_threshold": 20
    }
}

INITIAL_INCIDENT = {
    "incident_id": "INC-2026-8821",
    "facility_id": "FAC-GOKAK-01",
    "facility_name": "Gokak Regional Facility",
    "sku": "OF-4420",
    "sku_name": "Heavy-Duty Oil Filter",
    "current_stock": 6,
    "daily_burn_rate": 3.0,
    "days_of_cover": 2.0,
    "standard_lead_time_days": 6,
    "stockout_gap_days": 4,
    "root_cause": "40% maintenance demand spike combined with a 4-day primary supplier replenishment delay.",
    "status": "PENDING_REVIEW",
    "mitigation_options": [
        {
            "option_id": "OPT-1",
            "pathway_name": "Inter-Warehouse Rebalancing",
            "type": "INTER_WAREHOUSE_TRANSFER",
            "source_facility": "Belgaum Distribution Center",
            "source_facility_id": "FAC-BELGAUM-HUB",
            "speed_hours": 24,
            "cost_impact_usd": 45.0,
            "recommended": True,
            "quantity": 12
        },
        {
            "option_id": "OPT-2",
            "pathway_name": "Expedited Supplier PO",
            "type": "EXPEDITED_PO",
            "supplier_id": "SUP-ALPHA",
            "source_facility": "Alpha Auto Supply Co.",
            "speed_hours": 72,
            "cost_impact_usd": 180.0,
            "recommended": False,
            "quantity": 25
        },
        {
            "option_id": "OPT-3",
            "pathway_name": "Spot Market Local Sourcing",
            "type": "SPOT_PURCHASE",
            "supplier_id": "SUP-BETA-LOCAL",
            "source_facility": "Karnataka Local Parts Exchange",
            "speed_hours": 48,
            "cost_impact_usd": 260.0,
            "recommended": False,
            "quantity": 20
        }
    ]
}

# Runtime working memory
warehouses = {k: v.copy() for k, v in INITIAL_WAREHOUSES.items()}
active_incident = INITIAL_INCIDENT.copy()
audit_ledger: List[Dict[str, Any]] = []

# -----------------------------------------------------------------------------
# Pydantic Request & Response Schemas
# -----------------------------------------------------------------------------
class RecalculateRequest(BaseModel):
    option_id: str = "OPT-1"
    quantity: int = Field(..., gt=0, description="Target transfer or order quantity")
    user_override_text: Optional[str] = None

class RecalculateResponse(BaseModel):
    option_id: str
    original_quantity: int
    new_quantity: int
    resulting_days_of_cover: float
    new_cost_impact_usd: float
    source_remaining_stock: int
    source_is_safe: bool
    summary_notes: str

class ApproveActionRequest(BaseModel):
    action_type: str = "INTER_WAREHOUSE_TRANSFER"
    request_id: str = "TR-8821"
    source_warehouse: str = "FAC-BELGAUM-HUB"
    destination_warehouse: str = "FAC-GOKAK-01"
    sku: str = "OF-4420"
    quantity: int = 12
    freight_cost_usd: float = 45.0
    eta_hours: int = 24
    manager_override: Optional[Dict[str, Any]] = None

class RejectActionRequest(BaseModel):
    incident_id: str = "INC-2026-8821"
    reason_code: str = "SUPERSEDED_BY_MANAGER"
    notes: Optional[str] = "Alternative resolution arranged."

# -----------------------------------------------------------------------------
# REST API Endpoints
# -----------------------------------------------------------------------------

@app.get("/")
def get_dashboard():
    """Serves the interactive NAVORA frontend dashboard."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return {"message": "NAVORA FastAPI Backend Running. dashboard.html not found."}

@app.get("/api/telemetry")
def get_telemetry():
    """
    Returns the active incident telemetry and mitigation options
    conforming to NAVORA Section 3.1 schema.
    """
    # Dynamically refresh current stock in incident from warehouse state
    gokak = warehouses["FAC-GOKAK-01"]
    active_incident["current_stock"] = gokak["on_hand"]
    active_incident["days_of_cover"] = round(gokak["on_hand"] / active_incident["daily_burn_rate"], 2)
    return active_incident

@app.post("/api/recalculate", response_model=RecalculateResponse)
def recalculate_math(req: RecalculateRequest):
    """
    Executes instant mathematical re-verification for human-in-the-loop overrides.
    Recalculates Days of Cover, Freight/Landed cost, and Hub surplus impact.
    """
    current_stock = warehouses["FAC-GOKAK-01"]["on_hand"]
    burn_rate = active_incident["daily_burn_rate"]

    # Days of Cover = (Current Stock + New Qty) / Daily Burn Rate
    resulting_doc = round((current_stock + req.quantity) / burn_rate, 2)

    # Freight Model: Base $35 + $1.50 per unit
    new_cost = round(35.0 + (req.quantity * 1.50), 2)

    # Source Hub Impact
    hub_stock = warehouses["FAC-BELGAUM-HUB"]["on_hand"]
    hub_remaining = hub_stock - req.quantity
    hub_safe = hub_remaining >= warehouses["FAC-BELGAUM-HUB"]["safety_threshold"]

    return RecalculateResponse(
        option_id=req.option_id,
        original_quantity=12,
        new_quantity=req.quantity,
        resulting_days_of_cover=resulting_doc,
        new_cost_impact_usd=new_cost,
        source_remaining_stock=hub_remaining,
        source_is_safe=hub_safe,
        summary_notes=f"Recalculated with {req.quantity} units. Resulting Gokak cover is {resulting_doc} days."
    )

@app.post("/api/actions/approve")
def approve_and_execute(req: ApproveActionRequest):
    """
    Handles [Approve & Execute] click:
    1. Dispatches order payload to simulated WMS/ERP.
    2. Atomically updates virtual ledger:
       - Destination: +qty pending in-transit
       - Source: -qty allocated
    3. Issues immutable execution receipt and logs audit entry.
    """
    dest_wh = warehouses.get(req.destination_warehouse)
    src_wh = warehouses.get(req.source_warehouse)

    if not dest_wh or not src_wh:
        raise HTTPException(status_code=400, detail="Invalid source or destination warehouse identifier.")

    if src_wh["on_hand"] < req.quantity:
        raise HTTPException(
            status_code=400, 
            detail=f"Insufficient source stock at {src_wh['name']}. Available: {src_wh['on_hand']}, Requested: {req.quantity}"
        )

    # Atomic Virtual Ledger Update
    src_wh["on_hand"] -= req.quantity
    src_wh["allocated"] += req.quantity
    dest_wh["in_transit"] += req.quantity

    # Generate Audit Record
    tx_id = f"0x{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    audit_entry = {
        "transaction_id": tx_id,
        "request_id": req.request_id,
        "action_type": req.action_type,
        "source": req.source_warehouse,
        "destination": req.destination_warehouse,
        "sku": req.sku,
        "quantity": req.quantity,
        "freight_cost_usd": req.freight_cost_usd,
        "eta_hours": req.eta_hours,
        "signer": "Purchasing Manager",
        "timestamp": timestamp,
        "overrides_applied": req.manager_override or "None",
        "status": "DISPATCHED"
    }
    audit_ledger.append(audit_entry)

    # Mark active incident as resolved
    active_incident["status"] = "RESOLVED_DISPATCHED"

    return {
        "status": "DISPATCHED",
        "receipt_id": req.request_id,
        "transaction_id": tx_id,
        "dispatch_message": f"Simulated Transfer Request {req.request_id} dispatched to Belgaum warehouse.",
        "inventory_summary": f"Inventory state updated: Gokak pending in-transit (+{req.quantity} units), Belgaum allocated (-{req.quantity} units).",
        "ledger_breakdown": {
            "destination": {
                "facility": dest_wh["name"],
                "on_hand": dest_wh["on_hand"],
                "in_transit": dest_wh["in_transit"],
                "effective_total": dest_wh["on_hand"] + dest_wh["in_transit"],
                "resulting_days_of_cover": round((dest_wh["on_hand"] + dest_wh["in_transit"]) / dest_wh["daily_burn_rate"], 2)
            },
            "source": {
                "facility": src_wh["name"],
                "on_hand": src_wh["on_hand"],
                "allocated": src_wh["allocated"],
                "retained_surplus": src_wh["on_hand"],
                "threshold_compliant": src_wh["on_hand"] >= src_wh["safety_threshold"]
            }
        },
        "audit_meta": audit_entry
    }

@app.post("/api/actions/reject")
def reject_action(req: RejectActionRequest):
    """
    Handles [Reject] click: logs reason code and archives the incident.
    """
    active_incident["status"] = "REJECTED_ARCHIVED"
    audit_entry = {
        "transaction_id": f"0xREJECT-{uuid.uuid4().hex[:6].upper()}",
        "incident_id": req.incident_id,
        "event": "INCIDENT_DISMISSED",
        "reason_code": req.reason_code,
        "notes": req.notes,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    audit_ledger.append(audit_entry)
    return {"status": "ARCHIVED", "message": f"Incident {req.incident_id} dismissed.", "audit": audit_entry}

@app.get("/api/ledger")
def get_inventory_ledger():
    """Returns current real-time inventory balances and transaction audit history."""
    return {
        "warehouses": warehouses,
        "audit_transactions_count": len(audit_ledger),
        "audit_ledger": audit_ledger
    }

@app.post("/api/reset")
def reset_system_state():
    """Resets warehouses, incidents, and audit trails to initial demo condition."""
    global warehouses, active_incident, audit_ledger
    warehouses = {k: v.copy() for k, v in INITIAL_WAREHOUSES.items()}
    active_incident = INITIAL_INCIDENT.copy()
    audit_ledger = []
    return {"message": "NAVORA local state reset to initial conditions."}

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*70)
    print("🚀 Starting NAVORA FastAPI Local Server on http://127.0.0.1:8000")
    print("📖 Interactive API Docs (Swagger): http://127.0.0.1:8000/docs")
    print("🖥️ Dashboard UI: http://127.0.0.1:8000/")
    print("="*70 + "\n")
    uvicorn.run("main.py:app", host="127.0.0.1", port=8000, reload=True)
