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

from engine.config import (
    VELOCITY_RECENT_WINDOW_DAYS,
    VELOCITY_BASELINE_WINDOW_DAYS,
    TREND_ACCELERATING_THRESHOLD,
    TREND_DECELERATING_THRESHOLD,
    SURGE_EXPLOSIVE_RATIO,
    SURGE_MIN_RECENT_VELOCITY,
    CLIFF_DROP_RATIO,
    DEFAULT_DONOR_MIN_COVER_DAYS,
    DEFAULT_DONOR_SAFETY_DAYS,
    DEFAULT_SAFETY_STOCK_DAYS,
    DEFAULT_REVIEW_PERIOD_DAYS,
    MOQ_OVERPURCHASE_RATIO_THRESHOLD,
    ANNUAL_HOLDING_COST_RATE,
    DAILY_HOLDING_COST_RATE,
    SEVERITY_CRITICAL_RATIO,
    SEVERITY_HIGH_RATIO,
    MIN_VELOCITY_VOLUME_THRESHOLD,
    VELOCITY_BLENDING_ALPHA,
)




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

    window_sales = sub.tail(VELOCITY_BASELINE_WINDOW_DAYS)
    total_volume = float(window_sales["qty_sold"].sum()) if len(window_sales) > 0 else 0.0
    is_low_volume = bool(total_volume < MIN_VELOCITY_VOLUME_THRESHOLD)

    v_baseline = (
        float(sub["qty_sold"].tail(VELOCITY_BASELINE_WINDOW_DAYS).mean()) if len(sub) > 0 else 0.0
    )
    v_recent = (
        float(sub["qty_sold"].tail(VELOCITY_RECENT_WINDOW_DAYS).mean())
        if len(sub) >= VELOCITY_RECENT_WINDOW_DAYS
        else v_baseline
    )

    # EWMA across observed historical records
    if len(sub) > 0:
        v_ewma = float(sub["qty_sold"].ewm(span=VELOCITY_RECENT_WINDOW_DAYS, adjust=False).mean().iloc[-1])
    else:
        v_ewma = 0.0

    # Blended velocity: weighted combination of recent and baseline
    v_blended = round(VELOCITY_BLENDING_ALPHA * v_recent + (1.0 - VELOCITY_BLENDING_ALPHA) * v_baseline, 2)

    # Defensive Trend Calculation & Minimum Volume Guard
    if is_low_volume:
        # Minimum-volume check prevents noisy sparse sales from triggering overreaction
        trend_factor = 1.0
        trend_label = "STABLE"
        v_predicted = v_baseline
    elif v_baseline > 0.0:
        trend_factor = round(v_recent / v_baseline, 2)
        if trend_factor >= TREND_ACCELERATING_THRESHOLD:
            v_predicted = v_recent
            trend_label = "ACCELERATING"
        elif trend_factor <= TREND_DECELERATING_THRESHOLD:
            v_predicted = v_recent
            trend_label = "DECELERATING"
        else:
            v_predicted = v_baseline
            trend_label = "STABLE"
    else:
        trend_factor = 2.0 if v_recent > 0.0 else 1.0
        if v_recent > 0.0:
            v_predicted = v_recent
            trend_label = "ACCELERATING"
        else:
            v_predicted = 0.0
            trend_label = "STABLE"

    # Defensive Cover & Deficit Gap Calculations
    if v_predicted <= 0.0:
        days_cover = 999.0  # Zero velocity: not exhausting inventory
    elif current_stock <= 0:
        days_cover = 0.0
    else:
        days_cover = round(float(current_stock) / v_predicted, 2)

    stockout_gap = max(0.0, round(float(primary_lead_time) - days_cover, 2))

    return {
        "v_baseline": round(v_baseline, 2),
        "v_recent": round(v_recent, 2),
        "v_ewma": round(v_ewma, 2),
        "v_blended": round(v_blended, 2),
        "total_volume": int(total_volume),
        "is_low_volume": is_low_volume,
        "trend_factor": round(trend_factor, 2),
        "v_predicted": round(v_predicted, 2),
        "trend_label": trend_label,
        "days_of_cover": days_cover,
        "stockout_gap_days": stockout_gap,
        "is_surge": bool(not is_low_volume and trend_factor >= SURGE_EXPLOSIVE_RATIO and v_recent >= SURGE_MIN_RECENT_VELOCITY),
        "is_drop": bool(not is_low_volume and trend_factor <= CLIFF_DROP_RATIO and v_baseline >= SURGE_MIN_RECENT_VELOCITY),
    }



def compute_dynamic_donor_buffer(
    donor_lead_time_days: int = 7,
    safety_days: float = DEFAULT_DONOR_SAFETY_DAYS,
    floor_days: float = DEFAULT_DONOR_MIN_COVER_DAYS
) -> float:
    """Donor minimum cover = max(15, donor_lead_time + safety_days)."""
    return max(float(floor_days), float(donor_lead_time_days) + float(safety_days))


def compute_sku_target_cover(
    primary_lead_time_days: int = 7,
    review_period_days: float = DEFAULT_REVIEW_PERIOD_DAYS,
    safety_days: float = DEFAULT_SAFETY_STOCK_DAYS
) -> float:
    """
    Computes per-SKU target inventory cover (days):
    target_cover = lead_time + review_period + safety_stock
    Replaces flat 45-day benchmark with grounded target cover per SKU.
    """
    return float(primary_lead_time_days) + float(review_period_days) + float(safety_days)


def compute_severity(
    margin_at_risk: float,
    time_to_stockout: float,
    critical_threshold: float = SEVERITY_CRITICAL_RATIO,
    high_threshold: float = SEVERITY_HIGH_RATIO,
) -> Dict[str, Any]:
    """
    Computes deterministic severity level using the explicit formula:
    severity_score = margin_at_risk / time_to_stockout

    Thresholds:
    - severity_score >= critical_threshold -> CRITICAL
    - severity_score >= high_threshold     -> HIGH
    - otherwise                            -> MEDIUM

    Standardizes on 'margin at risk' as the single operational term.
    """
    t_safe = max(0.5, float(time_to_stockout))
    score = float(margin_at_risk) / t_safe

    if score >= critical_threshold:
        level = "CRITICAL"
    elif score >= high_threshold:
        level = "HIGH"
    else:
        level = "MEDIUM"

    return {
        "severity": level,
        "severity_score": round(score, 2),
        "margin_at_risk": round(margin_at_risk, 2),
        "time_to_stockout": round(t_safe, 1),
    }




def calculate_donor_transfer_safety(
    donor_stock: int,
    donor_v: float,
    transfer_qty: int,
    min_cover_days: Optional[float] = None,
    donor_lead_time: int = 7,
    safety_days: float = DEFAULT_DONOR_SAFETY_DAYS,
    donor_incoming_po_qty: int = 0
) -> dict:
    """
    Enforces dynamic donor safety buffer:
    required_min_cover = min_cover_days if explicitly passed, else max(15, donor_lead_time + safety_days).
    Accounts for donor's incoming POs in physical availability.
    """
    effective_donor_stock = donor_stock + donor_incoming_po_qty
    remaining_stock = effective_donor_stock - transfer_qty
    remaining_cover = (remaining_stock / donor_v) if donor_v > 0.0 else 999.0

    required_cover = (
        float(min_cover_days)
        if min_cover_days is not None
        else compute_dynamic_donor_buffer(donor_lead_time, safety_days)
    )

    is_safe = bool(remaining_cover >= required_cover and remaining_stock >= 0)
    max_safe_transfer = max(0, int(effective_donor_stock - np.ceil(required_cover * donor_v)))

    return {
        "is_safe": is_safe,
        "remaining_cover_days": round(remaining_cover, 1),
        "required_cover_days": round(required_cover, 1),
        "max_safe_transfer_qty": max_safe_transfer,
        "effective_donor_stock": effective_donor_stock,
    }




def generate_14day_projections(
    current_stock: int,
    daily_burn: float,
    transfer_qty: int,
    primary_lead_time: int = 7,
    expedited_lead_time: int = 3,
    replenishment_order_qty: Optional[int] = None,
    transfer_arrival_day: int = 1,
    expedited_qty: Optional[int] = None,
    open_po_qty: int = 0,
    open_po_arrival_day: Optional[int] = None,
    has_open_po: Optional[bool] = None,
    **kwargs
) -> dict:
    """
    Generates day-by-day simulated inventory arrays using grounded operational parameters.
    - Status Quo: Grounded in open purchase orders. If has_open_po is False (or open_po_qty==0 and no PO open),
      Status Quo shows NO arrival (Category A 'no PO in transit' semantics).
    - Expedited: Arrival happens on expedited_lead_time with expedited_qty.
    - Transfer: Arrival happens on transfer_arrival_day with transfer_qty.
    """
    if has_open_po is False:
        status_quo_arrival_qty = 0
        sq_arrival_day = None
    elif has_open_po is True or open_po_qty > 0:
        status_quo_arrival_qty = open_po_qty if open_po_qty > 0 else (replenishment_order_qty or 0)
        sq_arrival_day = open_po_arrival_day if open_po_arrival_day is not None else primary_lead_time
    elif replenishment_order_qty is not None and replenishment_order_qty > 0:
        # Compatibility fallback for direct caller specifying non-zero replenishment qty
        status_quo_arrival_qty = replenishment_order_qty
        sq_arrival_day = primary_lead_time
    else:
        # Default: no PO in transit -> 0 arrival units in Status Quo
        status_quo_arrival_qty = 0
        sq_arrival_day = None

    expedited_arrival_qty = expedited_qty if expedited_qty is not None else (replenishment_order_qty or 20)

    days = list(range(15))

    # 1. Status Quo
    stock_status_quo = []
    curr = float(current_stock)
    for d in days:
        if sq_arrival_day is not None and d == sq_arrival_day:
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
    - If burn_rate <= 0.0: 999.0 (No demand -> infinite cover / no stockout risk)
    - If stock <= 0 and burn_rate > 0.0: 0.0 (Immediate active stockout)
    - Otherwise: round(stock / burn_rate, 1)
    """
    if burn_rate <= 0.0:
        return 999.0  # Zero demand: inventory is not depleting
    if stock <= 0:
        return 0.0
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
    """Returns pending/in-transit purchase orders for an SKU at a specific location,
    excluding DELIVERED and CANCELLED POs, and accounting for partial deliveries.
    """
    result = []
    for po in purchase_orders:
        if po.get("sku") != sku:
            continue
        status = str(po.get("status", "")).upper()
        if status in ("DELIVERED", "CANCELLED"):
            continue
        po_loc = po.get("location")
        if po_loc is not None and location is not None and po_loc != location:
            continue

        # Handle partial deliveries: remaining qty = total - delivered
        total_qty = int(po.get("qty", 0))
        delivered_qty = int(po.get("delivered_qty", po.get("received_qty", 0)))
        remaining_qty = max(0, total_qty - delivered_qty)
        if remaining_qty <= 0:
            continue  # Fully fulfilled

        po_copy = dict(po)
        po_copy["remaining_qty"] = remaining_qty
        result.append(po_copy)
    return result


def calculate_available_surplus(
    stock: int,
    burn_rate: float,
    min_retained_cover_days: float = DEFAULT_DONOR_MIN_COVER_DAYS
) -> int:
    """
    Computes surplus stock available for transfer without jeopardizing the donor node.
    Donor must retain >= min_retained_cover_days of stock (cover >= min_retained_cover_days).
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

    # Overdue PO detection: exclude CANCELLED, handle partial delivery, prioritize by impact on cover
    overdue_pos = []
    for po in incoming:
        exp_dt_str = po.get("expected_date")
        status = po.get("status", "PENDING")
        if str(status).upper() in ("DELIVERED", "CANCELLED"):
            continue
        rem_qty = po.get("remaining_qty", max(0, int(po.get("qty", 0)) - int(po.get("delivered_qty", po.get("received_qty", 0)))))
        if rem_qty <= 0:
            continue
        if exp_dt_str and check_is_po_overdue(exp_dt_str, status, simulation_date_str=current_date):
            po_copy = dict(po)
            po_copy["remaining_qty"] = rem_qty
            po_copy["cover_impact_days"] = round(rem_qty / max(burn_rate, 0.1), 1)
            overdue_pos.append(po_copy)

    # Prioritize overdue POs by largest impact on cover
    overdue_pos.sort(key=lambda p: p.get("cover_impact_days", 0.0), reverse=True)

    # Demand shift evaluation
    demand_shift = detect_demand_shift(sales, sku, location, current_date)

    problem_type = None
    severity = "NONE"

    adaptive_velocity = compute_adaptive_velocity(sales, sku, location, stock, primary_lead_time)

    target_cover = compute_sku_target_cover(
        primary_lead_time_days=primary_lead_time,
        review_period_days=DEFAULT_REVIEW_PERIOD_DAYS,
        safety_days=DEFAULT_SAFETY_STOCK_DAYS,
    )

    # Problem Classification (incorporates Category A, B, C, D, E)
    if overdue_pos:
        problem_type = "OVERDUE_PO"
    elif days_cover < primary_lead_time and not incoming:
        # Edge Case T17: stock <= 0 and zero velocity must not raise a stockout
        active_demand = (burn_rate > 0.0 or adaptive_velocity.get("v_predicted", 0.0) > 0.0 or adaptive_velocity.get("v_recent", 0.0) > 0.0)
        if active_demand:
            problem_type = "IMMINENT_STOCKOUT"
    elif adaptive_velocity["trend_label"] in ("ACCELERATING", "DECELERATING") or demand_shift["shift_type"] in ("DEMAND_SURGE", "DEMAND_DROP"):
        problem_type = "DEMAND_VOLATILITY"
    elif (days_cover > target_cover and stock > 0) or (burn_rate == 0.0 and stock > 0):
        problem_type = "CAPITAL_TRAP"

    # Deterministic Severity via explicit formula: severity_score = margin_at_risk / time_to_stockout
    unit_price = float(primary_sup.get("price", 1000.0)) if primary_sup else 1000.0
    unit_margin = unit_price * 0.35

    if problem_type in ("IMMINENT_STOCKOUT", "OVERDUE_PO", "DEMAND_VOLATILITY"):
        gap = max(0.0, float(primary_lead_time) - float(days_cover))
        effective_v = max(burn_rate, adaptive_velocity.get("v_recent", 0.1))
        margin_at_risk = round(max(unit_margin, gap * effective_v * unit_margin), 2)
        time_to_stockout = max(0.5, float(days_cover))
    elif problem_type == "CAPITAL_TRAP":
        excess_units = max(0, stock - math.ceil(target_cover * burn_rate)) if burn_rate > 0 else stock
        margin_at_risk = round(excess_units * unit_price * ANNUAL_HOLDING_COST_RATE, 2)
        time_to_stockout = max(1.0, float(days_cover) if days_cover < 90 else 90.0)
    else:
        margin_at_risk = 0.0
        time_to_stockout = max(1.0, float(days_cover))

    if problem_type:
        sev_data = compute_severity(
            margin_at_risk=margin_at_risk,
            time_to_stockout=time_to_stockout,
            critical_threshold=SEVERITY_CRITICAL_RATIO,
            high_threshold=SEVERITY_HIGH_RATIO
        )
        severity = sev_data["severity"]
        severity_score = sev_data["severity_score"]
    else:
        severity = "NONE"
        severity_score = 0.0

    return {
        "sku": sku,
        "location": location,
        "stock": stock,
        "burn_rate": burn_rate,
        "days_of_cover": days_cover,
        "primary_supplier_lead_time_days": primary_lead_time,
        "target_cover_days": round(target_cover, 1),
        "stockout_gap_days": stockout_gap,
        "incoming_pos": incoming,
        "overdue_pos": overdue_pos,
        "demand_shift": demand_shift,
        "adaptive_velocity": adaptive_velocity,
        "problem_type": problem_type,
        "severity": severity,
        "severity_score": severity_score,
        "margin_at_risk": margin_at_risk,
        "time_to_stockout": time_to_stockout,
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

    cutoff_7 = curr_dt - timedelta(days=VELOCITY_RECENT_WINDOW_DAYS - 1)
    cutoff_30 = curr_dt - timedelta(days=VELOCITY_BASELINE_WINDOW_DAYS - 1)

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

    v_short = round(float(qty_7) / float(VELOCITY_RECENT_WINDOW_DAYS), 2)
    v_long = round(float(qty_30) / float(VELOCITY_BASELINE_WINDOW_DAYS), 2)

    if v_long > 0:
        ratio = round(v_short / v_long, 2)
    elif v_short > 0:
        ratio = 9.99
    else:
        ratio = 1.0

    shift_type = "STABLE"
    if v_long > 0 and ratio >= SURGE_EXPLOSIVE_RATIO and v_short >= SURGE_MIN_RECENT_VELOCITY:
        shift_type = "DEMAND_SURGE"
    elif v_long >= SURGE_MIN_RECENT_VELOCITY and ratio <= CLIFF_DROP_RATIO:
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
    days_of_cover: float,
    holding_days: float = 90.0,
    holding_cost_rate: float = ANNUAL_HOLDING_COST_RATE
) -> Dict[str, Any]:
    """
    Evaluates supplier feasibility with excess-cost scoring:
    - Carrying cost of excess over-purchase = overpurchase_qty * price * (annual_holding_cost_rate / 365.0) * holding_days
    - Keeps binary INFEASIBLE_MOQ flag only when moq > MOQ_OVERPURCHASE_RATIO_THRESHOLD * Q_needed.
    - Otherwise feasible with scored excess carrying cost.
    """
    moq = int(supplier.get("moq", 1))
    lead_time = int(supplier.get("lead_time_days", 7))
    price = float(supplier.get("price", baseline_price))

    overpurchase_qty = max(0, moq - Q_needed)
    daily_rate = holding_cost_rate / 365.0
    excess_carrying_cost = round(overpurchase_qty * price * daily_rate * holding_days, 2)

    moq_penalty = bool(moq > (MOQ_OVERPURCHASE_RATIO_THRESHOLD * Q_needed)) if Q_needed > 0 else False
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
        "overpurchase_qty": overpurchase_qty,
        "excess_carrying_cost": excess_carrying_cost,
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


def compute_option_expected_cost(
    handling_or_freight: float,
    purchase_premium: float,
    expected_lost_margin: float,
    carrying_cost_of_excess: float,
) -> Dict[str, float]:
    """
    Computes expected_cost = handling_or_freight + purchase_premium + expected_lost_margin + carrying_cost_of_excess
    Returns total expected cost and breakdown of components.
    """
    h_or_f = max(0.0, float(handling_or_freight))
    p_prem = max(0.0, float(purchase_premium))
    l_marg = max(0.0, float(expected_lost_margin))
    c_excess = max(0.0, float(carrying_cost_of_excess))
    total = h_or_f + p_prem + l_marg + c_excess
    return {
        "expected_cost": round(total, 2),
        "handling_or_freight": round(h_or_f, 2),
        "purchase_premium": round(p_prem, 2),
        "expected_lost_margin": round(l_marg, 2),
        "carrying_cost_of_excess": round(c_excess, 2),
    }


def compute_incident_scorecard(
    problem_type: str,
    recommended_option: Dict[str, Any],
    status_quo_option: Optional[Dict[str, Any]],
    current_cover_days: float,
    daily_burn_rate: float,
    primary_lead_time_days: int,
    unit_price: float,
    order_qty: int = 0
) -> Dict[str, Any]:
    """
    Computes fair commercial scorecard per incident:
    - net_cost_inr: incremental cost (freight + expedite premium + carrying cost), NOT full inventory PO value
    - lost_units_averted: difference in unfulfilled demand between Status Quo and recommended action
    - working_capital_outflow_inr: actual new capital committed
    - downtime_risk_days: remaining stockout days under recommended action
    """
    rec_breakdown = recommended_option.get("expected_cost_breakdown", {})
    rec_lead = float(recommended_option.get("delivery_time_days", 1))
    
    # 1. Net Incremental Cost
    # Incremental expenditure incurred specifically by this decision
    handling_or_freight = float(rec_breakdown.get("handling_or_freight", recommended_option.get("estimated_cost_inr", 0.0)))
    purchase_premium = float(rec_breakdown.get("purchase_premium", 0.0))
    carrying_excess = float(rec_breakdown.get("carrying_cost_of_excess", 0.0))
    net_cost = round(handling_or_freight + purchase_premium + carrying_excess, 2)

    # 2. Lost Units Averted
    # Status Quo unfulfilled demand vs Recommended unfulfilled demand
    sq_lost_days = max(0.0, float(primary_lead_time_days) - float(current_cover_days))
    rec_lost_days = max(0.0, rec_lead - float(current_cover_days))
    sq_lost_units = sq_lost_days * float(daily_burn_rate)
    rec_lost_units = rec_lost_days * float(daily_burn_rate)
    lost_units_averted = round(max(0.0, sq_lost_units - rec_lost_units), 1)

    # 3. Working Capital Outflow
    # Transfers reallocate owned inventory -> Rs 0.00 new cash committed
    # External purchases commit order_qty * unit_price
    is_transfer = "Internal" in recommended_option.get("option_name", "") or "Rebalancing" in recommended_option.get("option_name", "")
    if is_transfer:
        wc_outflow = 0.0
    else:
        # If external purchase order
        wc_outflow = round(float(order_qty) * float(unit_price), 2)

    # 4. Downtime Risk
    downtime_days = round(rec_lost_days, 1)

    return {
        "net_cost_inr": net_cost,
        "net_cost_str": f"₹{net_cost:,.2f}",
        "lost_units_averted": lost_units_averted,
        "lost_units_str": f"{lost_units_averted} units",
        "working_capital_outflow_inr": wc_outflow,
        "working_capital_outflow_str": f"₹{wc_outflow:,.2f}",
        "downtime_risk_days": downtime_days,
        "downtime_risk_str": f"{int(downtime_days)} Days" if downtime_days == int(downtime_days) else f"{downtime_days} Days",
    }



