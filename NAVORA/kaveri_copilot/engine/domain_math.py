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
    DATA_QUALITY_MIN_RECORDS,
    DATA_QUALITY_MIN_VOLUME,
    DATA_QUALITY_MAX_DATE_GAP_DAYS,
    CONFIDENCE_NORMAL,
    CONFIDENCE_LOW_VOLUME,
    CONFIDENCE_DATA_GAPS,
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
        # Filter first in Python to avoid high DataFrame construction overhead for large datasets
        filtered_records = [
            r for r in sales_df 
            if (sku is None or r.get("sku") == sku) and (location is None or r.get("location") == location)
        ]
        sales_df = pd.DataFrame(filtered_records)
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
            "data_quality_flag": "LOW_VOLUME",
            "confidence_score": CONFIDENCE_LOW_VOLUME,
            "human_escalation_required": True,
            "record_count": 0,
        }

    sub = sales_df[(sales_df["sku"] == sku) & (sales_df["location"] == location)]
    if "date" in sub.columns:
        sub = sub.sort_values("date")

    window_sales = sub.tail(VELOCITY_BASELINE_WINDOW_DAYS)
    total_volume = float(window_sales["qty_sold"].sum()) if len(window_sales) > 0 else 0.0
    record_count = len(sub)
    is_low_volume = bool(total_volume < MIN_VELOCITY_VOLUME_THRESHOLD)

    # T24 Data-Quality Check: date gaps & low historical transaction volume
    has_date_gaps = False
    if record_count >= 2 and "date" in sub.columns:
        try:
            date_series = pd.to_datetime(sub["date"]).sort_values()
            diffs = date_series.diff().dt.days.dropna()
            if (diffs > DATA_QUALITY_MAX_DATE_GAP_DAYS).any():
                has_date_gaps = True
        except Exception:
            has_date_gaps = False

    is_low_data_volume = bool(record_count < DATA_QUALITY_MIN_RECORDS or total_volume < DATA_QUALITY_MIN_VOLUME)
    if is_low_data_volume:
        data_quality_flag = "LOW_VOLUME"
        confidence_score = CONFIDENCE_LOW_VOLUME
        human_escalation_required = True
    elif has_date_gaps:
        data_quality_flag = "DATA_GAPS_DETECTED"
        confidence_score = CONFIDENCE_DATA_GAPS
        human_escalation_required = True
    else:
        data_quality_flag = "NORMAL"
        confidence_score = CONFIDENCE_NORMAL
        human_escalation_required = False

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
        "record_count": record_count,
        "is_low_volume": is_low_volume,
        "trend_factor": round(trend_factor, 2),
        "v_predicted": round(v_predicted, 2),
        "trend_label": trend_label,
        "days_of_cover": days_cover,
        "stockout_gap_days": stockout_gap,
        "is_surge": bool(not is_low_volume and trend_factor >= SURGE_EXPLOSIVE_RATIO and v_recent >= SURGE_MIN_RECENT_VELOCITY),
        "is_drop": bool(not is_low_volume and trend_factor <= CLIFF_DROP_RATIO and v_baseline >= SURGE_MIN_RECENT_VELOCITY),
        "data_quality_flag": data_quality_flag,
        "confidence_score": confidence_score,
        "human_escalation_required": human_escalation_required,
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

    mc_status_quo = simulate_monte_carlo_projections(
        starting_stock=current_stock,
        daily_burn=daily_burn,
        arrival_qty=status_quo_arrival_qty,
        arrival_day=sq_arrival_day,
        horizon_days=15,
        num_runs=500,
        seed=42
    )

    mc_expedited = simulate_monte_carlo_projections(
        starting_stock=current_stock,
        daily_burn=daily_burn,
        arrival_qty=expedited_arrival_qty,
        arrival_day=expedited_lead_time,
        horizon_days=15,
        num_runs=500,
        seed=42
    )

    mc_transfer = simulate_monte_carlo_projections(
        starting_stock=current_stock,
        daily_burn=daily_burn,
        arrival_qty=transfer_qty,
        arrival_day=transfer_arrival_day,
        horizon_days=15,
        num_runs=500,
        seed=42
    )

    return {
        "days": days,
        "status_quo": stock_status_quo,
        "expedited": stock_expedited,
        "transfer": stock_transfer,
        "stockout_probability_by_day_14": {
            "status_quo": mc_status_quo["stockout_probability_by_day_14"],
            "expedited": mc_expedited["stockout_probability_by_day_14"],
            "transfer": mc_transfer["stockout_probability_by_day_14"],
        },
        "fan_chart": {
            "status_quo": mc_status_quo,
            "expedited": mc_expedited,
            "transfer": mc_transfer,
        },
        "probabilistic": {
            "num_runs": 500,
            "seed": 42,
            "status_quo": mc_status_quo,
            "expedited": mc_expedited,
            "transfer": mc_transfer,
        }
    }


def simulate_monte_carlo_projections(
    starting_stock: float,
    daily_burn: float,
    arrival_qty: float = 0.0,
    arrival_day: Optional[int] = None,
    horizon_days: int = 15,
    num_runs: int = 500,
    seed: int = 42,
    demand_std_dev: Optional[float] = None
) -> Dict[str, Any]:
    """
    Monte Carlo demand variance simulation (seeded, 500 runs).
    Returns fan chart percentiles (p10, p50, p90) and cumulative stockout probability by day 14.
    """
    np.random.seed(seed)
    mu = max(0.05, float(daily_burn))
    sigma = demand_std_dev if demand_std_dev is not None else max(0.3 * mu, 0.4)

    # Matrix of shape (num_runs, horizon_days)
    simulated_demand = np.maximum(0.0, np.random.normal(loc=mu, scale=sigma, size=(num_runs, horizon_days)))

    # Track inventory paths across runs
    inv_paths = np.zeros((num_runs, horizon_days))
    curr = np.full(num_runs, float(starting_stock))
    stockout_occurred = np.zeros(num_runs, dtype=bool)
    stockout_prob_curve = []

    for d in range(horizon_days):
        if arrival_day is not None and d == arrival_day:
            curr += arrival_qty
        curr = np.maximum(0.0, curr - simulated_demand[:, d])
        inv_paths[:, d] = curr
        stockout_occurred |= (curr <= 0.0)
        stockout_prob_curve.append(round(float(np.mean(stockout_occurred)), 3))

    p10 = [round(float(x), 1) for x in np.percentile(inv_paths, 10, axis=0)]
    p50 = [round(float(x), 1) for x in np.percentile(inv_paths, 50, axis=0)]
    p90 = [round(float(x), 1) for x in np.percentile(inv_paths, 90, axis=0)]
    stockout_prob_14 = stockout_prob_curve[-1]

    return {
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "stockout_probability_by_day_14": stockout_prob_14,
        "stockout_probability_curve": stockout_prob_curve
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


def compute_supplier_reliability(
    purchase_orders: List[Dict[str, Any]],
    suppliers: List[Dict[str, Any]],
    current_date: str = "2026-10-09"
) -> Dict[str, Dict[str, Any]]:
    """
    Computes actual vs promised delivery slippage per supplier and adjusts quoted lead time.
    Slippage = actual delivery date (or current date if delayed) - promised expected date.
    Adjusted lead time = promised_lead_time + max(0, ceil(avg_slippage)).
    """
    try:
        curr_dt = datetime.strptime(str(current_date)[:10], "%Y-%m-%d").date()
    except Exception:
        curr_dt = datetime(2026, 10, 9).date()

    pos_by_supplier: Dict[str, List[Dict[str, Any]]] = {}
    for po in purchase_orders:
        sup_name = po.get("supplier")
        if sup_name:
            pos_by_supplier.setdefault(sup_name, []).append(po)

    reliability_map: Dict[str, Dict[str, Any]] = {}

    for sup in suppliers:
        name = sup.get("supplier", "")
        quoted_lead = int(sup.get("lead_time_days", 7))
        sup_pos = pos_by_supplier.get(name, [])

        slippages: List[float] = []
        delayed_count = 0
        delivered_count = 0

        for po in sup_pos:
            status = str(po.get("status", "")).upper()
            exp_str = po.get("expected_date") or po.get("promised_date")
            act_str = po.get("actual_delivery_date") or po.get("delivered_date")

            if not exp_str:
                continue

            try:
                exp_dt = datetime.strptime(str(exp_str)[:10], "%Y-%m-%d").date()
            except Exception:
                continue

            if status in ("DELIVERED", "RECEIVED") and act_str:
                delivered_count += 1
                try:
                    act_dt = datetime.strptime(str(act_str)[:10], "%Y-%m-%d").date()
                    slip = (act_dt - exp_dt).days
                    slippages.append(max(0.0, float(slip)))
                    if slip > 0:
                        delayed_count += 1
                except Exception:
                    slippages.append(0.0)
            elif status in ("DELAYED", "OVERDUE") or (status not in ("CANCELLED", "DELIVERED") and exp_dt < curr_dt):
                delayed_count += 1
                slip = (curr_dt - exp_dt).days
                slippages.append(max(0.0, float(slip)))
            else:
                slippages.append(0.0)

        total_orders = len(sup_pos)
        avg_slip = round(float(np.mean(slippages)), 1) if slippages else 0.0
        on_time_rate = round(float(sum(1 for s in slippages if s <= 0.0)) / float(max(1, total_orders)), 2) if slippages else 1.0
        adj_lead = int(quoted_lead + math.ceil(max(0.0, avg_slip)))

        if avg_slip <= 0.0:
            status_label = "RELIABLE"
        elif avg_slip <= 2.0:
            status_label = "WATCHLIST"
        else:
            status_label = "HIGH_RISK"

        reliability_map[name] = {
            "supplier": name,
            "quoted_lead_time_days": quoted_lead,
            "avg_slippage_days": avg_slip,
            "adjusted_lead_time_days": adj_lead,
            "total_orders": total_orders,
            "delayed_orders": delayed_count,
            "on_time_rate": on_time_rate,
            "reliability_status": status_label
        }

    return reliability_map



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
    # Pre-filter sales once for this (sku, location) to avoid repetitive scans across thousands of records
    if isinstance(sales, list) and len(sales) > 100:
        sub_sales = [rec for rec in sales if rec.get("sku") == sku and rec.get("location") == location]
    else:
        sub_sales = sales

    burn_rate = calculate_daily_burn_rate(sub_sales, sku, location, days_observed)
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
    demand_shift = detect_demand_shift(sub_sales, sku, location, current_date)

    problem_type = None
    severity = "NONE"

    adaptive_velocity = compute_adaptive_velocity(sub_sales, sku, location, stock, primary_lead_time)

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
        "primary_supplier": primary_sup,
        "data_quality_flag": adaptive_velocity.get("data_quality_flag", "NORMAL"),
        "confidence_score": adaptive_velocity.get("confidence_score", CONFIDENCE_NORMAL),
        "human_escalation_required": adaptive_velocity.get("human_escalation_required", False),
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
    supplier: Optional[Dict[str, Any]] = None,
    baseline_price: float = 1000.0,
    Q_needed: Optional[int] = None,
    days_of_cover: Optional[float] = None,
    holding_days: float = 90.0,
    holding_cost_rate: float = ANNUAL_HOLDING_COST_RATE,
    *,
    supplier_lead_time: Optional[int] = None,
    supplier_moq: Optional[int] = None,
    needed_qty: Optional[int] = None,
    unit_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates supplier feasibility with excess-cost scoring:
    - Carrying cost of excess over-purchase = overpurchase_qty * price * (annual_holding_cost_rate / 365.0) * holding_days
    - Keeps binary INFEASIBLE_MOQ flag only when moq > MOQ_OVERPURCHASE_RATIO_THRESHOLD * Q_needed.
    - Otherwise feasible with scored excess carrying cost.
    """
    sup_dict = supplier or {}
    moq = int(supplier_moq if supplier_moq is not None else sup_dict.get("moq", 1))
    lead_time = int(supplier_lead_time if supplier_lead_time is not None else sup_dict.get("lead_time_days", 7))
    price = float(unit_price if unit_price is not None else sup_dict.get("price", baseline_price))
    req_qty = int(needed_qty if needed_qty is not None else (Q_needed if Q_needed is not None else 1))
    cover = float(days_of_cover if days_of_cover is not None else 10.0)

    overpurchase_qty = max(0, moq - req_qty)
    daily_rate = holding_cost_rate / 365.0
    excess_carrying_cost = round(overpurchase_qty * price * daily_rate * holding_days, 2)

    moq_penalty = bool(moq > (MOQ_OVERPURCHASE_RATIO_THRESHOLD * req_qty)) if req_qty > 0 else False
    price_premium = round(((price - baseline_price) / baseline_price) * 100.0, 1) if baseline_price > 0 else 0.0
    lead_time_breach = bool(lead_time > cover)

    if moq_penalty and lead_time_breach:
        feasibility_status = "INFEASIBLE_MOQ"
    elif moq_penalty:
        feasibility_status = "INFEASIBLE_MOQ"
    elif lead_time_breach:
        feasibility_status = "INFEASIBLE_LEAD_TIME"
    else:
        feasibility_status = "FEASIBLE"

    return {
        "supplier": sup_dict.get("supplier", "Unknown"),
        "moq": moq,
        "lead_time_days": lead_time,
        "price": price,
        "overpurchase_qty": overpurchase_qty,
        "excess_carrying_cost": excess_carrying_cost,
        "moq_penalty": moq_penalty,
        "is_moq_infeasible": moq_penalty,
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


DEFAULT_SIMULATION_DATE = "2026-11-16"


class OverdueResult(tuple):
    """
    Two-tuple representing (is_overdue, days_overdue) that also evaluates
    boolean truthiness according to is_overdue and supports equality comparisons.
    """
    def __new__(cls, is_overdue: bool, days_overdue: int):
        return super().__new__(cls, (bool(is_overdue), int(days_overdue)))

    @property
    def is_overdue(self) -> bool:
        return self[0]

    @property
    def days_overdue(self) -> int:
        return self[1]

    def __bool__(self) -> bool:
        return self[0]

    def __eq__(self, other):
        if isinstance(other, bool):
            return self[0] == other
        return super().__eq__(other)


def check_is_po_overdue(
    expected_delivery_date: str = "",
    status: str = "PENDING",
    current_date: str = DEFAULT_SIMULATION_DATE,
    simulation_date_str: Optional[str] = None,
    expected_delivery_date_str: Optional[str] = None,
    po_status: Optional[str] = None,
) -> OverdueResult:
    """
    Evaluates whether an open purchase order is overdue relative to simulation date.
    Terminal statuses ('Received', 'Delivered', 'Cancelled') are strictly excluded.
    """
    exp_date_raw = expected_delivery_date or expected_delivery_date_str or ""
    stat_raw = po_status if po_status is not None else status
    sim_date_val = simulation_date_str if simulation_date_str is not None else current_date

    if str(stat_raw).strip().lower() in ["received", "delivered", "cancelled"]:
        return OverdueResult(False, 0)

    try:
        exp_dt = datetime.strptime(str(exp_date_raw).strip(), "%Y-%m-%d").date()
        sim_dt = datetime.strptime(str(sim_date_val).strip(), "%Y-%m-%d").date()
    except Exception:
        return OverdueResult(False, 0)

    if exp_dt < sim_dt:
        days_overdue = (sim_dt - exp_dt).days
        return OverdueResult(True, days_overdue)

    return OverdueResult(False, 0)


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


def compute_plan_diff(
    before_brief: Dict[str, Any],
    after_brief: Dict[str, Any],
    chaos_event: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Computes structured diff between before-shock and after-shock recommendation plans with reasons.
    """
    before_problems = {p["problem_id"]: p for p in before_brief.get("problems", [])}
    after_problems = {p["problem_id"]: p for p in after_brief.get("problems", [])}

    all_pids = sorted(list(set(before_problems.keys()) | set(after_problems.keys())))
    diffs = []

    for pid in all_pids:
        b_p = before_problems.get(pid)
        a_p = after_problems.get(pid)

        if not b_p and a_p:
            diffs.append({
                "problem_id": pid,
                "sku": a_p.get("sku"),
                "location": a_p.get("location"),
                "change_type": "NEW_PROBLEM_EMERGED",
                "has_changed": True,
                "before_plan": None,
                "after_plan": {
                    "action_type": a_p.get("simulated_action", {}).get("action_type"),
                    "source": a_p.get("simulated_action", {}).get("payload", {}).get("from_location_or_supplier"),
                    "qty": a_p.get("simulated_action", {}).get("payload", {}).get("qty", 0),
                    "cost_inr": a_p.get("simulated_action", {}).get("payload", {}).get("total_estimated_cost_inr", 0.0),
                },
                "change_reason": f"Operational shock triggered new incident at {a_p.get('location')}."
            })
            continue

        if b_p and not a_p:
            diffs.append({
                "problem_id": pid,
                "sku": b_p.get("sku"),
                "location": b_p.get("location"),
                "change_type": "PROBLEM_RESOLVED",
                "has_changed": True,
                "before_plan": {
                    "action_type": b_p.get("simulated_action", {}).get("action_type"),
                    "source": b_p.get("simulated_action", {}).get("payload", {}).get("from_location_or_supplier"),
                    "qty": b_p.get("simulated_action", {}).get("payload", {}).get("qty", 0),
                    "cost_inr": b_p.get("simulated_action", {}).get("payload", {}).get("total_estimated_cost_inr", 0.0),
                },
                "after_plan": None,
                "change_reason": "Incident resolved or cleared by operational change."
            })
            continue

        b_act = b_p.get("simulated_action", {})
        a_act = a_p.get("simulated_action", {})
        b_pay = b_act.get("payload", {})
        a_pay = a_act.get("payload", {})

        b_src = b_pay.get("from_location_or_supplier")
        a_src = a_pay.get("from_location_or_supplier")
        b_type = b_act.get("action_type")
        a_type = a_act.get("action_type")
        b_qty = b_pay.get("qty", 0)
        a_qty = a_pay.get("qty", 0)
        b_cost = b_pay.get("total_estimated_cost_inr", 0.0)
        a_cost = a_pay.get("total_estimated_cost_inr", 0.0)

        has_changed = (b_src != a_src) or (b_type != a_type) or (b_qty != a_qty)

        reason_parts = []
        if b_src != a_src:
            reason_parts.append(f"Fulfillment source shifted from {b_src} to {a_src}")
        if b_type != a_type:
            reason_parts.append(f"Action escalated from {b_type} to {a_type}")
        if b_qty != a_qty:
            reason_parts.append(f"Order quantity adjusted from {b_qty} to {a_qty} units")

        if not reason_parts:
            change_reason = "Plan maintained: current recommendation remains optimal."
        else:
            ev_desc = ""
            if chaos_event:
                ev_type = str(chaos_event.get("event_type", ""))
                if "BLOCK" in ev_type:
                    ev_desc = "due to lateral route roadblock disruption"
                elif "SURGE" in ev_type:
                    ev_desc = "due to sudden demand acceleration"
                elif "DELAY" in ev_type:
                    ev_desc = "due to supplier delivery slippage"
            change_reason = "; ".join(reason_parts) + (f" ({ev_desc})" if ev_desc else "") + "."

        diffs.append({
            "problem_id": pid,
            "sku": a_p.get("sku"),
            "location": a_p.get("location"),
            "change_type": "PLAN_MUTATION" if has_changed else "UNCHANGED",
            "has_changed": has_changed,
            "before_plan": {
                "action_type": b_type,
                "source": b_src,
                "qty": b_qty,
                "cost_inr": b_cost,
            },
            "after_plan": {
                "action_type": a_type,
                "source": a_src,
                "qty": a_qty,
                "cost_inr": a_cost,
            },
            "change_reason": change_reason
        })

    changed_count = sum(1 for d in diffs if d["has_changed"])
    return {
        "total_problems": len(diffs),
        "total_changed_plans": changed_count,
        "diffs": diffs
    }




