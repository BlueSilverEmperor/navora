"""
Kaveri Spares & Hydraulics - Domain Math Engine
Implements deterministic calculations for Velocity (Burn Rate), Days of Cover,
Stockout Gaps, Multi-Echelon Surplus, and Problem Classification.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import math
import numpy as np
import pandas as pd


def compute_adaptive_velocity(
    sales_df: Union[pd.DataFrame, List[Dict[str, Any]]],
    sku: str,
    location: str,
    current_stock: int,
    primary_lead_time: int
) -> dict:
    """Calculates trailing sales velocity with defensive zero-division guards."""
    if isinstance(sales_df, list):
        sales_df = pd.DataFrame(sales_df)
    elif not isinstance(sales_df, pd.DataFrame):
        sales_df = pd.DataFrame(sales_df)

    if len(sales_df) == 0:
        return {
            "v_baseline": 0.0,
            "v_recent": 0.0,
            "trend_factor": 1.0,
            "v_predicted": 0.0,
            "trend_label": "STABLE",
            "days_of_cover": 0.0 if current_stock <= 0 else 999.0,
            "stockout_gap_days": 0.0,
            "is_surge": False,
            "is_drop": False,
        }

    sub = sales_df[(sales_df["sku"] == sku) & (sales_df["location"] == location)]
    if "date" in sub.columns:
        sub = sub.sort_values("date")

    v_baseline = (
        float(sub["qty_sold"].tail(30).mean()) if len(sub) > 0 else 0.0
    )
    v_recent = (
        float(sub["qty_sold"].tail(7).mean())
        if len(sub) >= 7
        else v_baseline
    )

    # Defensive Trend Calculation: Avoid ZeroDivisionError
    if v_baseline > 0.0:
        trend_factor = round(v_recent / v_baseline, 2)
    else:
        trend_factor = 2.0 if v_recent > 0.0 else 1.0

    if trend_factor >= 1.5:
        v_predicted = v_recent
        trend_label = "ACCELERATING"
    elif trend_factor <= 0.4 and v_baseline > 0.0:
        v_predicted = v_recent
        trend_label = "DECELERATING"
    else:
        v_predicted = v_baseline
        trend_label = "STABLE"

    # Defensive Cover & Deficit Gap Calculations
    if current_stock <= 0:
        days_cover = 0.0
    elif v_predicted <= 0.0:
        days_cover = 999.0  # Dormant stock flag
    else:
        days_cover = round(float(current_stock) / v_predicted, 2)

    stockout_gap = max(0.0, round(float(primary_lead_time) - days_cover, 2))

    return {
        "v_baseline": round(v_baseline, 2),
        "v_recent": round(v_recent, 2),
        "trend_factor": round(trend_factor, 2),
        "v_predicted": round(v_predicted, 2),
        "trend_label": trend_label,
        "days_of_cover": days_cover,
        "stockout_gap_days": stockout_gap,
        "is_surge": bool(trend_factor >= 1.8 and v_recent >= 2.0),
        "is_drop": bool(trend_factor <= 0.3 and v_baseline >= 2.0),
    }


def calculate_donor_transfer_safety(donor_stock: int, donor_v: float, transfer_qty: int) -> dict:
    """Enforces donor maintains >= 15.0 days of operational cover post-transfer."""
    remaining_stock = donor_stock - transfer_qty
    remaining_cover = (remaining_stock / donor_v) if donor_v > 0.0 else 999.0
    is_safe = bool(remaining_cover >= 15.0 and remaining_stock >= 0)
    max_safe_transfer = max(0, int(donor_stock - np.ceil(15.0 * donor_v)))

    return {
        "is_safe": is_safe,
        "remaining_cover_days": round(remaining_cover, 1),
        "max_safe_transfer_qty": max_safe_transfer,
    }


def generate_14day_projections(
    current_stock: int,
    daily_burn: float,
    transfer_qty: int,
    primary_lead_time: int = 7,
    expedited_lead_time: int = 3,
    replenishment_order_qty: int = 25,
    transfer_arrival_day: int = 1,
    expedited_qty: Optional[int] = None,
    **kwargs
) -> dict:
    """Generates day-by-day simulated inventory arrays using dynamic parameters."""
    expedited_arrival_qty = expedited_qty if expedited_qty is not None else replenishment_order_qty
    status_quo_arrival_qty = replenishment_order_qty

    days = list(range(15))

    # 1. Status Quo (Primary PO arrives on primary_lead_time)
    stock_status_quo = []
    curr = float(current_stock)
    for d in days:
        if d == primary_lead_time:
            curr += status_quo_arrival_qty
        curr = max(0.0, curr - daily_burn)
        stock_status_quo.append(round(curr, 1))

    # 2. Expedited Supplier PO (Arrives on expedited_lead_time)
    stock_expedited = []
    curr = float(current_stock)
    for d in days:
        if d == expedited_lead_time:
            curr += expedited_arrival_qty
        curr = max(0.0, curr - daily_burn)
        stock_expedited.append(round(curr, 1))

    # 3. Inter-Store Network Transfer (Arrives on transfer_arrival_day)
    stock_transfer = []
    curr = float(current_stock)
    for d in days:
        if d == transfer_arrival_day:
            curr += transfer_qty
        curr = max(0.0, curr - daily_burn)
        stock_transfer.append(round(curr, 1))

    return {
        "days": days,
        "status_quo": stock_status_quo,
        "expedited": stock_expedited,
        "transfer": stock_transfer,
    }


def calculate_daily_burn_rate(
    sales_records: List[Dict[str, Any]],
    sku: str,
    location: str,
    days_observed: int = 30
) -> float:
    """
    Computes mean units sold per day over the observation window.
    Burn Rate = sum(qty_sold) / days_observed
    """
    if days_observed <= 0:
        days_observed = 30

    total_qty = sum(
        rec.get("qty_sold", 0)
        for rec in sales_records
        if rec.get("sku") == sku and rec.get("location") == location
    )
    return round(float(total_qty) / float(days_observed), 2)


def calculate_days_of_cover(stock: int, burn_rate: float) -> float:
    """
    Computes Days of Stock Cover = Current Stock / Daily Burn Rate.
    - If stock == 0: 0.0 (Immediate stockout)
    - If stock > 0 and burn_rate == 0: 999.0 (Infinity / Dead stock)
    """
    if stock <= 0:
        return 0.0
    if burn_rate <= 0.0:
        return 999.0  # Represents infinite cover / dead stock
    return round(float(stock) / float(burn_rate), 1)


def calculate_stockout_gap(days_of_cover: float, primary_lead_time_days: int) -> float:
    """
    Stockout Gap = max(0.0, primary_lead_time_days - days_of_cover).
    Positive value indicates the operational deficit window without intervention.
    """
    if days_of_cover >= primary_lead_time_days:
        return 0.0
    return round(float(primary_lead_time_days) - float(days_of_cover), 1)


def find_primary_supplier(suppliers: List[Dict[str, Any]], sku: str) -> Optional[Dict[str, Any]]:
    """Retrieves the primary supplier record for a given SKU."""
    sku_suppliers = [s for s in suppliers if s.get("sku") == sku]
    for s in sku_suppliers:
        if s.get("is_primary", False):
            return s
    return sku_suppliers[0] if sku_suppliers else None


def find_secondary_suppliers(suppliers: List[Dict[str, Any]], sku: str) -> List[Dict[str, Any]]:
    """Retrieves non-primary (expedited/alternate) suppliers for a given SKU."""
    return [s for s in suppliers if s.get("sku") == sku and not s.get("is_primary", False)]


def get_incoming_pos(
    purchase_orders: List[Dict[str, Any]],
    sku: str,
    location: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Returns pending/in-transit purchase orders for an SKU at a specific location."""
    result = []
    for po in purchase_orders:
        if po.get("sku") != sku:
            continue
        if po.get("status") in ("DELIVERED", "CANCELLED"):
            continue
        po_loc = po.get("location")
        if po_loc is not None and location is not None and po_loc != location:
            continue
        result.append(po)
    return result


def calculate_available_surplus(
    stock: int,
    burn_rate: float,
    min_retained_cover_days: int = 15
) -> int:
    """
    Computes surplus stock available for transfer without jeopardizing the donor node.
    Donor must retain at least min_retained_cover_days of stock.
    Surplus = max(0, stock - ceil(min_retained_cover_days * burn_rate))
    """
    if stock <= 0:
        return 0
    buffer_needed = math.ceil(min_retained_cover_days * max(burn_rate, 0.1))
    surplus = stock - buffer_needed
    return max(0, surplus)


def evaluate_sku_location(
    sku: str,
    location: str,
    stock: int,
    sales: List[Dict[str, Any]],
    suppliers: List[Dict[str, Any]],
    purchase_orders: List[Dict[str, Any]],
    current_date: str = "2026-10-09",
    days_observed: int = 30
) -> Dict[str, Any]:
    """
    Computes full domain metrics and problem flags for a single SKU at a specific node.
    """
    burn_rate = calculate_daily_burn_rate(sales, sku, location, days_observed)
    days_cover = calculate_days_of_cover(stock, burn_rate)
    primary_sup = find_primary_supplier(suppliers, sku)
    primary_lead_time = primary_sup.get("lead_time_days", 7) if primary_sup else 7
    stockout_gap = calculate_stockout_gap(days_cover, primary_lead_time)

    incoming = get_incoming_pos(purchase_orders, sku, location)
    curr_dt = datetime.strptime(current_date, "%Y-%m-%d")

    # Overdue PO detection
    overdue_pos = []
    for po in incoming:
        exp_dt_str = po.get("expected_date")
        if exp_dt_str:
            if check_is_po_overdue(exp_dt_str, po.get("status", "PENDING"), simulation_date_str=current_date):
                overdue_pos.append(po)

    # Demand shift evaluation
    demand_shift = detect_demand_shift(sales, sku, location, current_date)

    problem_type = None
    severity = "NONE"

    adaptive_velocity = compute_adaptive_velocity(sales, sku, location, stock, primary_lead_time)

    # Problem Classification (incorporates Category A, B, C, D, E)
    if overdue_pos:
        problem_type = "OVERDUE_PO"
        severity = "CRITICAL" if days_cover <= 4.0 else "HIGH"
    elif days_cover < primary_lead_time and not incoming:
        problem_type = "IMMINENT_STOCKOUT"
        severity = "CRITICAL" if days_cover <= 3.0 or stock == 0 else "HIGH"
    elif adaptive_velocity["trend_label"] in ("ACCELERATING", "DECELERATING") or demand_shift["shift_type"] in ("DEMAND_SURGE", "DEMAND_DROP"):
        problem_type = "DEMAND_VOLATILITY"
        severity = "HIGH"
    elif (days_cover > 45.0 and stock > 0) or (burn_rate == 0.0 and stock > 0):
        problem_type = "CAPITAL_TRAP"
        severity = "HIGH" if (primary_sup and stock * primary_sup.get("price", 0) > 100000) else "MEDIUM"

    return {
        "sku": sku,
        "location": location,
        "stock": stock,
        "burn_rate": burn_rate,
        "days_of_cover": days_cover,
        "primary_supplier_lead_time_days": primary_lead_time,
        "stockout_gap_days": stockout_gap,
        "incoming_pos": incoming,
        "overdue_pos": overdue_pos,
        "demand_shift": demand_shift,
        "adaptive_velocity": adaptive_velocity,
        "problem_type": problem_type,
        "severity": severity,
        "primary_supplier": primary_sup
    }


def detect_demand_shift(
    sales_records: List[Dict[str, Any]],
    sku: str,
    location: str,
    current_date: str = "2026-10-09"
) -> Dict[str, Any]:
    """
    Computes v_short (rolling 7-day average sales) and v_long (30-day average sales).
    - If v_short / v_long >= 1.8 and v_short >= 2.0: flags DEMAND_SURGE
    - If v_short / v_long <= 0.3 and v_long >= 2.0: flags DEMAND_DROP
    """
    try:
        curr_dt = datetime.strptime(current_date, "%Y-%m-%d")
    except Exception:
        curr_dt = datetime.now()

    cutoff_7 = curr_dt - timedelta(days=6)
    cutoff_30 = curr_dt - timedelta(days=29)

    qty_7 = 0
    qty_30 = 0

    for rec in sales_records:
        if rec.get("sku") == sku and rec.get("location") == location:
            d_str = rec.get("date")
            if d_str:
                try:
                    rec_dt = datetime.strptime(d_str, "%Y-%m-%d")
                    if cutoff_30 <= rec_dt <= curr_dt:
                        q = int(rec.get("qty_sold", 0))
                        qty_30 += q
                        if cutoff_7 <= rec_dt <= curr_dt:
                            qty_7 += q
                except Exception:
                    pass

    v_short = round(float(qty_7) / 7.0, 2)
    v_long = round(float(qty_30) / 30.0, 2)

    if v_long > 0:
        ratio = round(v_short / v_long, 2)
    elif v_short > 0:
        ratio = 9.99
    else:
        ratio = 1.0

    shift_type = "STABLE"
    if v_long > 0 and ratio >= 1.8 and v_short >= 2.0:
        shift_type = "DEMAND_SURGE"
    elif v_long >= 2.0 and ratio <= 0.3:
        shift_type = "DEMAND_DROP"

    return {
        "shift_type": shift_type,
        "v_short": v_short,
        "v_long": v_long,
        "ratio": ratio
    }


def evaluate_supplier_friction(
    supplier: Dict[str, Any],
    baseline_price: float,
    Q_needed: int,
    days_of_cover: float
) -> Dict[str, Any]:
    """
    Evaluates supplier feasibility based on:
    - MOQ_Penalty: If supplier.moq > 3 * Q_needed -> EXCESSIVE_MOQ_RISK / INFEASIBLE_MOQ
    - Price_Premium: (supplier.price - baseline_price) / baseline_price
    - Lead_Time_Breach: If supplier.lead_time_days > Days_of_Cover -> TIMING_INFEASIBLE / INFEASIBLE_LEAD_TIME
    """
    moq = supplier.get("moq", 1)
    lead_time = supplier.get("lead_time_days", 7)
    price = float(supplier.get("price", baseline_price))

    moq_penalty = bool(moq > (3 * Q_needed)) if Q_needed > 0 else False
    price_premium = round(((price - baseline_price) / baseline_price) * 100.0, 1) if baseline_price > 0 else 0.0
    lead_time_breach = bool(lead_time > days_of_cover)

    if moq_penalty and lead_time_breach:
        feasibility_status = "INFEASIBLE_MOQ"
    elif moq_penalty:
        feasibility_status = "INFEASIBLE_MOQ"
    elif lead_time_breach:
        feasibility_status = "INFEASIBLE_LEAD_TIME"
    else:
        feasibility_status = "FEASIBLE"

    return {
        "supplier": supplier.get("supplier", "Unknown"),
        "moq": moq,
        "lead_time_days": lead_time,
        "price": price,
        "moq_penalty": moq_penalty,
        "price_premium_pct": price_premium,
        "lead_time_breach": lead_time_breach,
        "feasibility_status": feasibility_status
    }


def validate_and_recalculate_transfer(
    from_loc: str,
    to_loc: str,
    sku: str,
    requested_qty: int,
    inventory: List[Dict[str, Any]],
    sales: List[Dict[str, Any]],
    days_observed: int = 30
) -> Dict[str, Any]:
    """
    Dynamic Rebalancer with Override:
    - Checks if donor_stock - requested_qty >= 15 * donor_velocity
    - If valid, returns updated cover days for both donor and recipient
    - If invalid, returns maximum safe transfer quantity and flags warning
    """
    donor_stock = 0
    recip_stock = 0
    for item in inventory:
        if item.get("sku") == sku:
            if item.get("location") == from_loc:
                donor_stock = item.get("stock", 0)
            elif item.get("location") == to_loc:
                recip_stock = item.get("stock", 0)

    v_donor = calculate_daily_burn_rate(sales, sku, from_loc, days_observed)
    v_recip = calculate_daily_burn_rate(sales, sku, to_loc, days_observed)

    min_required_donor_stock = 15.0 * max(v_donor, 0.1)
    max_safe_qty = max(0, math.floor(donor_stock - min_required_donor_stock))

    new_donor_stock = donor_stock - requested_qty
    new_recip_stock = recip_stock + requested_qty

    donor_cover = calculate_days_of_cover(new_donor_stock, v_donor)
    recip_cover = calculate_days_of_cover(new_recip_stock, v_recip)

    is_valid = bool((donor_stock - requested_qty) >= (15.0 * v_donor) and requested_qty > 0)

    warning = None
    if not is_valid:
        warning = (
            f"Requested quantity {requested_qty} breaches donor 15-day safety threshold. "
            f"Donor will retain {new_donor_stock} units ({donor_cover:.1f} days cover vs 15.0 required). "
            f"Maximum safe transfer is {max_safe_qty} units."
        )

    return {
        "is_valid": is_valid,
        "sku": sku,
        "from_location": from_loc,
        "to_location": to_loc,
        "requested_qty": requested_qty,
        "max_safe_qty": max_safe_qty,
        "donor_velocity": v_donor,
        "recipient_velocity": v_recip,
        "donor_stock_before": donor_stock,
        "donor_stock_after": new_donor_stock,
        "donor_cover_days": donor_cover,
        "recipient_stock_before": recip_stock,
        "recipient_stock_after": new_recip_stock,
        "recipient_cover_days": recip_cover,
        "warning": warning
    }


def check_is_po_overdue(
    expected_delivery_date_str: str,
    po_status: str,
    simulation_date_str: str = "2026-10-09",
) -> bool:
    """Evaluates overdue PO status against explicit simulation date, never system clock."""
    if str(po_status).upper() in ["DELIVERED", "CANCELLED"]:
        return False

    sim_date = datetime.strptime(simulation_date_str, "%Y-%m-%d").date()
    expected_date = datetime.strptime(expected_delivery_date_str, "%Y-%m-%d").date()
    return expected_date < sim_date


def clamp_inventory_projection(
    starting_stock: float,
    daily_burn: float,
    horizon_days: int = 15,
    incoming_shipments: Optional[Dict[int, float]] = None,
) -> Dict[str, List[float]]:
    """Clamps physical inventory to 0.0 and accumulates unfulfilled demand."""
    incoming = incoming_shipments or {}
    stock_path = []
    unmet_demand_path = []

    curr_stock = max(0.0, float(starting_stock))
    accumulated_lost = 0.0

    for day in range(horizon_days):
        if day in incoming:
            curr_stock += incoming[day]

        if curr_stock >= daily_burn:
            curr_stock -= daily_burn
        else:
            deficit = daily_burn - curr_stock
            curr_stock = 0.0
            accumulated_lost += deficit

        stock_path.append(round(curr_stock, 1))
        unmet_demand_path.append(round(accumulated_lost, 1))

    return {
        "projected_stock": stock_path,
        "unmet_demand_lost_units": unmet_demand_path,
    }


