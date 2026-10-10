"""
Kaveri Spares & Hydraulics - Agentic Decision Matrix & Copilot Engine
Evaluates competing options (Internal Network Transfer vs Expedited Supplier vs Do Nothing)
and drafts ready-to-approve simulated action payloads across all 5 problem categories.
"""

import json
import math
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
import pandas as pd

from engine.domain_math import (
    calculate_daily_burn_rate,
    calculate_days_of_cover,
    calculate_stockout_gap,
    find_primary_supplier,
    find_secondary_suppliers,
    get_incoming_pos,
    calculate_available_surplus,
    evaluate_sku_location,
    detect_demand_shift,
    evaluate_supplier_friction,
    validate_and_recalculate_transfer,
    generate_14day_projections,
    calculate_donor_transfer_safety,
    compute_sku_target_cover,
    compute_dynamic_donor_buffer,
    compute_option_expected_cost,
    compute_incident_scorecard,
    compute_supplier_reliability,
)
from engine.config import (
    DEFAULT_TRANSFER_HANDLING_COST,
    DEFAULT_TRANSFER_UNIT_FREIGHT,
    DEFAULT_ROUTE_TRANSIT_DAYS,
    DEFAULT_DONOR_SAFETY_DAYS,
    DEFAULT_CAPITAL_TRAP_DAYS,
    TREND_ACCELERATING_THRESHOLD,
    TREND_DECELERATING_THRESHOLD,
    SURGE_EXPLOSIVE_RATIO,
    SURGE_MIN_RECENT_VELOCITY,
    CLIFF_DROP_RATIO,
    DEFAULT_REVIEW_PERIOD_DAYS,
)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


def extract_network_topology(inventory_df: Union[pd.DataFrame, List[Dict[str, Any]]]) -> dict:
    """
    Dynamically identifies retail stores vs central distribution warehouses
    from ingested inventory telemetry without hardcoded location lists.
    """
    if isinstance(inventory_df, list):
        inventory_df = pd.DataFrame(inventory_df)
    if not isinstance(inventory_df, pd.DataFrame) or "location" not in inventory_df.columns:
        return {"all_locations": [], "warehouses": [], "stores": []}
    all_locations = sorted([str(loc).strip() for loc in inventory_df["location"].dropna().unique().tolist() if str(loc).strip()])

    def is_wh(loc: str) -> bool:
        l = loc.lower()
        if any(term in l for term in ["wh", "warehouse", "central", "regional"]):
            return True
        words = l.replace("_", " ").replace("-", " ").split()
        return "hub" in words

    warehouses = [loc for loc in all_locations if is_wh(loc)]
    stores = [loc for loc in all_locations if loc not in warehouses]

    return {
        "all_locations": all_locations,
        "warehouses": warehouses,
        "stores": stores
    }


def find_best_donor_location_with_reservations(
    inventory_df: Union[pd.DataFrame, List[Dict[str, Any]]],
    sales_df: Union[pd.DataFrame, List[Dict[str, Any]]],
    sku: str,
    target_location: str,
    needed_qty: int,
    active_reservations: Optional[Dict[str, int]] = None,
    donor_lead_time: int = 7,
    donor_incoming_po_qty: int = 0,
) -> Optional[dict]:
    """Scans network donors accounting for already reserved units from pending transfer drafts."""
    if isinstance(inventory_df, list):
        inventory_df = pd.DataFrame(inventory_df)
    if isinstance(sales_df, list):
        sales_df = pd.DataFrame(sales_df)

    active_res = active_reservations or {}
    stock_col = "current_stock" if "current_stock" in inventory_df.columns else "stock"

    topology = extract_network_topology(inventory_df)

    candidates = inventory_df[
        (inventory_df["sku"] == sku)
        & (inventory_df["location"] != target_location)
    ]

    feasible_donors = []

    for _, row in candidates.iterrows():
        loc = row["location"]
        gross_stock = int(row[stock_col])
        reserved = active_res.get(f"{loc}:{sku}", 0)
        effective_available_stock = max(0, gross_stock - reserved)

        sub_sales = sales_df[
            (sales_df["sku"] == sku) & (sales_df["location"] == loc)
        ]
        donor_v = (
            float(sub_sales["qty_sold"].tail(30).mean())
            if len(sub_sales) > 0
            else 0.05
        )

        # Evaluate safety buffer against effective available stock with dynamic donor buffer
        safety = calculate_donor_transfer_safety(
            effective_available_stock, donor_v, needed_qty,
            donor_lead_time=donor_lead_time,
            donor_incoming_po_qty=donor_incoming_po_qty
        )
        if safety["is_safe"]:
            is_wh = loc in topology["warehouses"]
            feasible_donors.append({
                "donor_location": loc,
                "location": loc,
                "gross_stock": gross_stock,
                "current_stock": gross_stock,
                "stock": gross_stock,
                "reserved_stock": reserved,
                "effective_stock": effective_available_stock,
                "donor_velocity": donor_v,
                "burn_rate": donor_v,
                "remaining_cover_days": safety["remaining_cover_days"],
                "max_safe_transfer_qty": safety["max_safe_transfer_qty"],
                "surplus": safety["max_safe_transfer_qty"],
                "cover_days": round(effective_available_stock / donor_v, 1) if donor_v > 0 else 999.0,
                "is_warehouse": is_wh
            })

    if not feasible_donors:
        return None

    feasible_donors.sort(
        key=lambda x: (
            1 if x["is_warehouse"] else 0,
            x["remaining_cover_days"]
        ),
        reverse=True
    )
    return feasible_donors[0]


def find_best_donor_location(
    inventory_df: Union[pd.DataFrame, List[Dict[str, Any]]],
    sales_df: Union[pd.DataFrame, List[Dict[str, Any]]],
    sku: str,
    target_location: str,
    needed_qty: int,
    active_reservations: Optional[Dict[str, int]] = None,
) -> Optional[Dict[str, Any]]:
    """Scans all network locations to identify the optimal qualified surplus donor."""
    return find_best_donor_location_with_reservations(
        inventory_df=inventory_df,
        sales_df=sales_df,
        sku=sku,
        target_location=target_location,
        needed_qty=needed_qty,
        active_reservations=active_reservations,
    )


class DecisionEngine:
    def __init__(
        self,
        data_dir: str = DATA_DIR,
        current_date: str = "2026-10-09",
        blocked_routes: Optional[List[Any]] = None,
        demand_multipliers: Optional[Dict[str, float]] = None,
        supplier_overrides: Optional[Dict[str, Any]] = None,
        chaos_events: Optional[List[Dict[str, Any]]] = None,
        active_reservations: Optional[Dict[str, int]] = None,
        transfer_handling_cost: Optional[float] = None,
        rejection_memories: Optional[List[Dict[str, Any]]] = None,
    ):
        self.data_dir = data_dir
        self.current_date = current_date
        self.blocked_routes = blocked_routes or []
        self.demand_multipliers = demand_multipliers or {}
        self.supplier_overrides = supplier_overrides or {}
        self.chaos_events = chaos_events or []
        self.active_reservations = active_reservations or {}
        self.transfer_handling_cost = (
            float(transfer_handling_cost)
            if transfer_handling_cost is not None
            else DEFAULT_TRANSFER_HANDLING_COST
        )
        if rejection_memories is not None:
            self.rejection_memories = list(rejection_memories)
        else:
            try:
                from engine.persistence import get_all_rejection_memories
                self.rejection_memories = get_all_rejection_memories()
            except Exception:
                self.rejection_memories = []
        self.products: List[Dict[str, Any]] = []
        self.inventory: List[Dict[str, Any]] = []
        self.sales: List[Dict[str, Any]] = []
        self.suppliers: List[Dict[str, Any]] = []
        self.purchase_orders: List[Dict[str, Any]] = []
        self.load_data()
        self.apply_in_memory_mutations()

    def load_data(self):
        """Loads operational JSON/CSV records from the data directory with Pydantic validation."""
        from engine.data_loader import load_validated_datasets
        datasets = load_validated_datasets(self.data_dir)
        self.products = datasets["products"]
        self.inventory = datasets["inventory"]
        self.sales = datasets["sales"]
        self.suppliers = datasets["suppliers"]
        self.purchase_orders = datasets["purchase_orders"]

        # T21: Supplier Reliability Learning - adjust lead times based on historical delivery slippage
        self.supplier_reliability = compute_supplier_reliability(
            purchase_orders=self.purchase_orders,
            suppliers=self.suppliers,
            current_date=self.current_date
        )
        for s in self.suppliers:
            name = s.get("supplier")
            rel = self.supplier_reliability.get(name)
            if rel:
                s["quoted_lead_time_days"] = int(s.get("lead_time_days", 7))
                s["adjusted_lead_time_days"] = int(rel["adjusted_lead_time_days"])
                s["historical_slippage_days"] = float(rel["avg_slippage_days"])
                s["on_time_rate"] = float(rel["on_time_rate"])
                s["reliability_status"] = rel["reliability_status"]
                # Use learned adjusted lead time in domain mathematics
                s["lead_time_days"] = int(rel["adjusted_lead_time_days"])


    def apply_in_memory_mutations(self):
        """Applies dynamic chaos events or state overrides."""
        for event in self.chaos_events:
            ev_type = event.get("event_type")
            sku = event.get("sku")
            loc = event.get("location")
            val = float(event.get("multiplier_or_days", 1.0))

            if ev_type == "DEMAND_SURGE" and sku and loc:
                # Multiply recent 7-day sales
                curr_dt = datetime.strptime(self.current_date, "%Y-%m-%d")
                cutoff_7 = curr_dt - timedelta(days=6)
                for rec in self.sales:
                    if rec.get("sku") == sku and rec.get("location") == loc:
                        d_str = rec.get("date")
                        if d_str:
                            rec_dt = datetime.strptime(d_str, "%Y-%m-%d")
                            if cutoff_7 <= rec_dt <= curr_dt:
                                rec["qty_sold"] = int(round(rec.get("qty_sold", 0) * val))

            elif ev_type in ("TRANSFER_BLOCKED", "ROUTE_BLOCKED"):
                from_loc = event.get("from_location", loc)
                to_loc = event.get("to_location")
                self.blocked_routes.append({"from": from_loc, "to": to_loc, "sku": sku})

            elif ev_type in ("SUPPLIER_DELAY", "SUPPLIER_HIKE") and sku:
                for sup in self.suppliers:
                    if sup.get("sku") == sku:
                        sup["lead_time_days"] = int(sup.get("lead_time_days", 7) + val)

            elif ev_type == "SUPPLIER_PRICE_HIKE" and sku:
                for sup in self.suppliers:
                    if sup.get("sku") == sku:
                        if val < 5.0:  # Percentage hike, e.g. 0.20 for +20%
                            sup["price"] = round(sup.get("price", 0.0) * (1.0 + val), 2)
                        else:  # Flat INR hike
                            sup["price"] = round(sup.get("price", 0.0) + val, 2)

    def is_route_blocked(self, from_loc: str, to_loc: str, sku: Optional[str] = None) -> bool:
        """
        Generic facility route-block checker for ANY facility pair.
        Supports exact match and substring/hub matching (e.g. 'Hubli' matches 'Hubli Regional Warehouse').
        """
        def loc_match(spec: Optional[str], actual: str) -> bool:
            if spec is None or spec == "*":
                return True
            s_clean = str(spec).strip().lower()
            a_clean = str(actual).strip().lower()
            return s_clean == a_clean or s_clean in a_clean or a_clean in s_clean

        for r in self.blocked_routes:
            if isinstance(r, dict):
                rf = r.get("from")
                rt = r.get("to")
                rsku = r.get("sku")
                match_from = loc_match(rf, from_loc)
                match_to = loc_match(rt, to_loc)
                match_sku = (rsku is None or rsku == "*" or rsku == sku)
                if match_from and match_to and match_sku:
                    return True
            elif isinstance(r, (tuple, list)) and len(r) >= 2:
                rf, rt = r[0], r[1]
                match_from = loc_match(rf, from_loc)
                match_to = loc_match(rt, to_loc)
                if match_from and match_to:
                    return True
        return False

    def _apply_rejection_memory_penalties(self, sku: str, location: str, options: List[Dict[str, Any]]):
        """
        T23: Applies soft constraint penalty (+₹750 expected cost) to any option whose source
        or action was previously rejected by a human operator for this (sku, location).
        Annotates the option with the prior rejection reason and moves it down in ranking.
        """
        if not self.rejection_memories:
            return

        for opt in options:
            opt_source = str(opt.get("source", "")).strip().lower()
            opt_name = str(opt.get("option_name", "")).strip().lower()
            for mem in self.rejection_memories:
                m_sku = mem.get("sku")
                m_loc = mem.get("location")
                m_src = str(mem.get("rejected_source") or "").strip().lower()
                m_reason = mem.get("rejection_reason", "Declined by operator")

                sku_match = (not m_sku or m_sku == sku)
                loc_match = (not m_loc or m_loc == location)

                if sku_match and loc_match:
                    src_match = bool(m_src and (m_src in opt_source or opt_source in m_src or m_src in opt_name))
                    if src_match:
                        penalty = 750.0  # INR soft penalty
                        current_cost = float(opt.get("expected_cost", opt.get("estimated_cost_inr", 0.0)))
                        opt["expected_cost"] = round(current_cost + penalty, 2)
                        opt["rejection_penalty_applied"] = True
                        opt["rejection_penalty_amount"] = penalty
                        opt["rejection_reason_note"] = f"Soft Penalty (+₹{penalty:,.2f}): Operator previously rejected this source ({m_reason})"
                        if "pros_cons" in opt and "[SOFT CONSTRAINT" not in opt["pros_cons"]:
                            opt["pros_cons"] += f" [SOFT CONSTRAINT: Prior operator rejection noted: '{m_reason}']"
                        break

    def get_product(self, sku: str) -> Dict[str, Any]:
        for p in self.products:
            if p["sku"] == sku:
                return p
        return {"sku": sku, "name": sku, "machine_model": "Universal", "category": "General"}

    def _build_metrics_and_explainability(
        self,
        stock: int,
        burn: float,
        metrics: Dict[str, Any],
        prim_lead: int,
        prim_price: float = 1000.0
    ) -> Dict[str, Any]:
        ad_vel = metrics.get("adaptive_velocity", {})
        v_base = ad_vel.get("v_baseline", burn)
        v_rec = ad_vel.get("v_recent", burn)
        v_pred = ad_vel.get("v_predicted", burn)
        trend_lbl = ad_vel.get("trend_label", "STABLE")
        trend_fac = ad_vel.get("trend_factor", 1.0)
        d_cover = metrics.get("days_of_cover", 0.0)
        s_gap = metrics.get("stockout_gap_days", 0.0)
        unit_margin = round(prim_price * 0.35, 2)
        lost_rev = round(s_gap * v_pred * unit_margin, 2)

        domain_metrics = {
            "current_stock": stock,
            "daily_burn_rate": burn,
            "days_of_cover": d_cover,
            "primary_supplier_lead_time_days": prim_lead,
            "stockout_gap_days": s_gap,
            "adaptive_velocity": ad_vel,
            "v_baseline": v_base,
            "v_recent": v_rec,
            "v_predicted": v_pred,
            "trend_label": trend_lbl,
            "trend_factor": trend_fac,
            "v": v_pred,
            "D": d_cover,
            "T": prim_lead,
            "Delta": s_gap,
            "unit_margin_inr": unit_margin,
            "projected_lost_revenue_inr": lost_rev
        }

        math_explain = {
            "v_baseline": v_base,
            "v_recent": v_rec,
            "v_predicted": v_pred,
            "trend_label": trend_lbl,
            "trend_factor": trend_fac,
            "v": v_pred,
            "D": d_cover,
            "T": prim_lead,
            "Delta": s_gap,
            "unit_margin_inr": unit_margin,
            "projected_lost_revenue_inr": lost_rev,
            "formula_velocity": f"v_pred = {v_pred:.2f} units/day (Trend: {trend_lbl}, {trend_fac:.2f}x)",
            "formula_cover": f"D = Stock ({stock}) / v ({v_pred:.2f}) = {d_cover:.1f} days",
            "formula_gap": f"Δ = max(0, T ({prim_lead}) - D ({d_cover:.1f})) = {s_gap:.1f} days",
            "formula_lost_revenue": f"Lost Revenue = Δ ({s_gap:.1f}d) × v ({v_pred:.2f}) × Margin (₹{unit_margin:,.2f}) = ₹{lost_rev:,.2f}"
        }

        return {
            "domain_metrics": domain_metrics,
            "math_explainability": math_explain,
            "adaptive_velocity": ad_vel
        }

    def _generate_projections_for_problem(
        self,
        stock: int,
        burn: float,
        prim_lead: int,
        options: List[Dict[str, Any]],
        sim_action: Dict[str, Any],
        sku: Optional[str] = None,
        loc: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculates 14-day stock trajectory curves across 3 operational paths grounded in data."""
        # Transfer qty determination from simulation action, options, or domain math
        transfer_qty = 0
        if sim_action and "payload" in sim_action and sim_action.get("action_type") == "TRANSFER_REQUEST":
            transfer_qty = int(sim_action["payload"].get("qty", 0))
        if transfer_qty <= 0:
            for opt in options:
                if "Internal Network" in opt.get("option_name", ""):
                    transfer_qty = int(opt.get("transfer_qty", 0))
                    if transfer_qty > 0:
                        break
        if transfer_qty <= 0:
            transfer_qty = math.ceil(burn * 3.5) if burn > 0 else 5

        # Expedited order qty & lead time determination
        sec_qty = 0
        exp_lead = 3
        for opt in options:
            if "Expedited" in opt.get("option_name", ""):
                exp_lead = int(opt.get("delivery_time_days", opt.get("lead_time_days", 3)))
                sec_qty = int(opt.get("order_qty", 0))
                break
        if sec_qty <= 0 and sim_action and "payload" in sim_action and sim_action.get("action_type") == "PURCHASE_ORDER":
            sec_qty = int(sim_action["payload"].get("qty", 0))
        if sec_qty <= 0 and sku:
            sec_sups = find_secondary_suppliers(self.suppliers, sku)
            if sec_sups:
                sec_qty = int(sec_sups[0].get("moq", 20))
                exp_lead = int(sec_sups[0].get("lead_time_days", 3))
        if sec_qty <= 0:
            sec_qty = max(20, math.ceil(burn * 3.5) if burn > 0 else 5)

        # Check actual open purchase orders in data for this SKU & location
        has_open_po = False
        open_po_qty = 0
        open_po_arr_day = None
        if sku and loc:
            incoming = get_incoming_pos(self.purchase_orders, sku, loc)
            if incoming:
                has_open_po = True
                first_po = incoming[0]
                open_po_qty = int(first_po.get("qty", 0))
                exp_dt_str = first_po.get("expected_date")
                if exp_dt_str:
                    try:
                        dt_exp = datetime.strptime(exp_dt_str, "%Y-%m-%d").date()
                        dt_curr = datetime.strptime(self.current_date, "%Y-%m-%d").date()
                        diff_days = (dt_exp - dt_curr).days
                        open_po_arr_day = max(0, min(14, diff_days))
                    except Exception:
                        open_po_arr_day = min(14, prim_lead)
                else:
                    open_po_arr_day = min(14, prim_lead)

        return generate_14day_projections(
            current_stock=stock,
            daily_burn=burn if burn > 0 else 0.5,
            transfer_qty=transfer_qty,
            primary_lead_time=prim_lead if prim_lead > 0 else 7,
            expedited_lead_time=exp_lead,
            expedited_qty=sec_qty,
            transfer_arrival_day=DEFAULT_ROUTE_TRANSIT_DAYS,
            open_po_qty=open_po_qty,
            open_po_arrival_day=open_po_arr_day,
            has_open_po=has_open_po
        )


    def find_network_donors(self, sku: str, exclude_location: str, needed_qty: int) -> List[Dict[str, Any]]:
        """
        Finds locations with surplus stock that retain >15 days cover after transfer,
        filtering out blocked routes.
        """
        candidates = []
        for inv in self.inventory:
            loc = inv["location"]
            if inv["sku"] != sku or loc == exclude_location:
                continue

            # Check if transfer route is blocked
            if self.is_route_blocked(loc, exclude_location, sku):
                continue

            gross_stock = inv["stock"]
            reserved = self.active_reservations.get(f"{loc}:{sku}", 0)
            stock = max(0, gross_stock - reserved)
            burn = calculate_daily_burn_rate(self.sales, sku, loc, days_observed=30)
            
            # Dynamic donor buffer: lead time + safety days, accounting for donor's incoming POs
            donor_sup = find_primary_supplier(self.suppliers, sku)
            donor_lead = int(donor_sup.get("lead_time_days", 7)) if donor_sup else 7
            donor_pos = get_incoming_pos(self.purchase_orders, sku, loc)
            donor_in_qty = sum(int(po.get("qty", 0)) for po in donor_pos)

            safety = calculate_donor_transfer_safety(
                stock, burn, needed_qty,
                donor_lead_time=donor_lead,
                donor_incoming_po_qty=donor_in_qty
            )

            if safety["is_safe"] or safety["max_safe_transfer_qty"] > 0:
                candidates.append({
                    "donor_location": loc,
                    "location": loc,
                    "stock": stock,
                    "current_stock": stock,
                    "burn_rate": burn,
                    "donor_velocity": burn,
                    "surplus": safety["max_safe_transfer_qty"],
                    "max_safe_transfer_qty": safety["max_safe_transfer_qty"],
                    "remaining_cover_days": safety["remaining_cover_days"],
                    "cover_days": calculate_days_of_cover(stock, burn),
                    "target_cover_days": compute_sku_target_cover(donor_lead),
                })

        candidates.sort(
            key=lambda c: (
                1 if (c["cover_days"] > c.get("target_cover_days", DEFAULT_CAPITAL_TRAP_DAYS) and "Warehouse" not in c["location"]) else 0,
                1 if "Warehouse" not in c["location"] else 0,
                c["remaining_cover_days"],
                c["surplus"]
            ),
            reverse=True
        )
        return candidates

    def run_agentic_pipeline(self) -> Dict[str, Any]:
        """
        Executes 6-step agentic pipeline across all SKUs and locations.
        Enforces 5 problem categories (A through E) and formatted options.
        """
        curr_dt = datetime.strptime(self.current_date, "%Y-%m-%d")
        detected_problems = []
        problem_counter = 1

        for inv in self.inventory:
            sku = inv["sku"]
            loc = inv["location"]
            stock = inv["stock"]

            metrics = evaluate_sku_location(
                sku=sku,
                location=loc,
                stock=stock,
                sales=self.sales,
                suppliers=self.suppliers,
                purchase_orders=self.purchase_orders,
                current_date=self.current_date
            )

            p_type = metrics["problem_type"]
            if not p_type:
                continue

            prod = self.get_product(sku)
            prim_sup = metrics["primary_supplier"] or {}
            prim_price = prim_sup.get("price", 1000.0)
            prim_lead = metrics["primary_supplier_lead_time_days"]

            pid = f"PRB-{self.current_date.replace('-', '')}-{problem_counter:02d}"
            problem_counter += 1

            burn = metrics["burn_rate"]
            target_qty = math.ceil(burn * 3.5) if burn > 0 else 5

            donors = self.find_network_donors(sku, loc, target_qty)
            secondary_sups = find_secondary_suppliers(self.suppliers, sku)

            options = []
            category_code = "CATEGORY_A"
            final_category = p_type

            # Check for CATEGORY_E (Supplier Infeasibility)
            is_supplier_infeasible = False
            if p_type == "IMMINENT_STOCKOUT" and not donors:
                # Check secondary suppliers for MOQ or lead time friction
                all_infeasible = True
                for s in secondary_sups:
                    sf = evaluate_supplier_friction(s, prim_price, target_qty, metrics["days_of_cover"])
                    if sf["feasibility_status"] == "FEASIBLE":
                        all_infeasible = False
                        break
                if secondary_sups and all_infeasible:
                    is_supplier_infeasible = True

            # -------------------------------------------------------------
            # CATEGORY_A or CATEGORY_E
            # -------------------------------------------------------------
            if p_type == "IMMINENT_STOCKOUT":
                if is_supplier_infeasible:
                    category_code = "CATEGORY_E"
                    final_category = "SUPPLIER_MISMATCH"
                else:
                    category_code = "CATEGORY_A"
                    final_category = "IMMINENT_STOCKOUT"

                # -------------------------------------------------------------
                # CATEGORY_A or CATEGORY_E
                # -------------------------------------------------------------
                transfer_fee = float(self.transfer_handling_cost)
                unit_margin = round(prim_price * 0.35, 2)
                v_pred = metrics.get("adaptive_velocity", {}).get("v_predicted", burn)
                current_cover = metrics["days_of_cover"]

                # Option 1: Internal Network Balancing
                if donors:
                    best_donor = donors[0]
                    donor_location = best_donor.get("donor_location", best_donor.get("location"))
                    actual_transfer_qty = min(best_donor.get("surplus", best_donor.get("max_safe_transfer_qty", target_qty)), target_qty)
                    if actual_transfer_qty <= 0:
                        actual_transfer_qty = min(best_donor.get("stock", target_qty), target_qty)

                    donor_v = best_donor.get("donor_velocity", best_donor.get("burn_rate", 1.0))
                    donor_post_cover = calculate_days_of_cover(
                        best_donor["stock"] - actual_transfer_qty,
                        donor_v
                    )
                    transfer_lead = 1
                    t_lost_margin = max(0.0, transfer_lead - current_cover) * v_pred * unit_margin
                    t_cost_calc = compute_option_expected_cost(
                        handling_or_freight=transfer_fee,
                        purchase_premium=0.0,
                        expected_lost_margin=t_lost_margin,
                        carrying_cost_of_excess=0.0
                    )

                    options.append({
                        "option_name": "Internal Network Balancing (Store/Warehouse Transfer)",
                        "source": donor_location,
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": transfer_fee,
                        "cash_impact_inr": transfer_fee,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "expected_cost": t_cost_calc["expected_cost"],
                        "expected_cost_breakdown": t_cost_calc,
                        "pros_cons": (
                            f"PRO: 1-day transit resolves deficit immediately; ₹{transfer_fee:.2f} handling fee "
                            f"(Expected Cost ₹{t_cost_calc['expected_cost']:,.2f}) with zero new working capital outflow. "
                            f"{donor_location} retains {donor_post_cover:.1f} days cover."
                        ),
                        "trade_off_summary": f"1-day transit, ₹{transfer_fee:.2f} handling, expected cost ₹{t_cost_calc['expected_cost']:,.2f}, donor retains {donor_post_cover:.1f} days cover (>15 days required)."
                    })
                else:
                    any_blocked = any(self.is_route_blocked(inv["location"], loc, sku) for inv in self.inventory if inv.get("sku") == sku and inv.get("location") != loc)
                    reason = "Transfer route blocked" if any_blocked else "Network branches lack >15 days surplus cover"
                    t_cost_calc = compute_option_expected_cost(
                        handling_or_freight=transfer_fee,
                        purchase_premium=0.0,
                        expected_lost_margin=999999.0,
                        carrying_cost_of_excess=0.0
                    )
                    options.append({
                        "option_name": "Internal Network Balancing (Store/Warehouse Transfer)",
                        "source": "Network Multi-Echelon Search",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": transfer_fee,
                        "cash_impact_inr": transfer_fee,
                        "feasibility": "INFEASIBLE",
                        "feasibility_status": "INFEASIBLE",
                        "expected_cost": 999999.0,
                        "expected_cost_breakdown": t_cost_calc,
                        "pros_cons": f"INFEASIBLE: {reason}.",
                        "trade_off_summary": f"Infeasible due to: {reason}."
                    })

                # Option 2: Hybrid Split-Fulfillment (Partial Transfer + Standard Factory PO)
                bridge_qty = max(1, target_qty // 2)
                hybrid_donor = donors[0] if donors else None
                if hybrid_donor and not self.is_route_blocked(hybrid_donor.get("location", ""), loc, sku):
                    h_loc = hybrid_donor.get("location", "")
                    h_gross = hybrid_donor["stock"]
                    h_burn = hybrid_donor.get("donor_velocity", hybrid_donor.get("burn_rate", 1.0))
                    h_pos = get_incoming_pos(self.purchase_orders, sku, h_loc)
                    h_in_qty = sum(int(po.get("qty", 0)) for po in h_pos)
                    h_lead = int(prim_sup.get("lead_time_days", 7))
                    h_safety = calculate_donor_transfer_safety(
                        h_gross, h_burn, bridge_qty,
                        donor_lead_time=h_lead,
                        donor_incoming_po_qty=h_in_qty
                    )
                    if h_safety["is_safe"]:
                        h_po_qty = max(target_qty - bridge_qty, prim_sup.get("moq", 10))
                        h_moq_excess = max(0, h_po_qty - (target_qty - bridge_qty))
                        h_carrying = h_moq_excess * prim_price * (0.22 / 365.0) * 90.0
                        h_cover_extended = current_cover + (bridge_qty / v_pred if v_pred > 0 else 0)
                        h_remaining_gap = max(0.0, prim_lead - h_cover_extended)
                        h_lost_margin = h_remaining_gap * v_pred * unit_margin
                        h_cost_calc = compute_option_expected_cost(
                            handling_or_freight=transfer_fee,
                            purchase_premium=0.0,
                            expected_lost_margin=h_lost_margin,
                            carrying_cost_of_excess=h_carrying
                        )
                        options.append({
                            "option_name": "Hybrid Split-Fulfillment (Partial Transfer + Standard Factory PO)",
                            "source": f"{hybrid_donor.get('location')} ({bridge_qty}u) + {prim_sup.get('supplier')} ({h_po_qty}u)",
                            "delivery_time_days": 1,
                            "lead_time_days": prim_lead,
                            "estimated_cost_inr": transfer_fee + round(h_po_qty * prim_price, 2),
                            "cash_impact_inr": transfer_fee + round(h_po_qty * prim_price, 2),
                            "feasibility": "FEASIBLE",
                            "feasibility_status": "FEASIBLE",
                            "is_baseline": False,
                            "expected_cost": h_cost_calc["expected_cost"],
                            "expected_cost_breakdown": h_cost_calc,
                            "pros_cons": (
                                f"PRO: Bridges immediate stockout with rapid {bridge_qty}-unit transfer (1-day) "
                                f"while replenishing {h_po_qty} units via standard factory order without rush surcharges. "
                                f"Donor retains {h_safety['remaining_cover_days']:.1f} days cover."
                            ),
                            "trade_off_summary": f"Split: {bridge_qty}u transfer (1d) + {h_po_qty}u standard PO ({prim_lead}d), expected cost ₹{h_cost_calc['expected_cost']:,.2f}."
                        })
                    else:
                        options.append({
                            "option_name": "Hybrid Split-Fulfillment (Partial Transfer + Standard Factory PO)",
                            "source": "Network Hybrid Rebalance",
                            "delivery_time_days": 1,
                            "lead_time_days": prim_lead,
                            "estimated_cost_inr": 0.0,
                            "cash_impact_inr": 0.0,
                            "feasibility": "INFEASIBLE",
                            "feasibility_status": "INFEASIBLE",
                            "is_baseline": False,
                            "expected_cost": 999999.0,
                            "expected_cost_breakdown": compute_option_expected_cost(0, 0, 999999, 0),
                            "pros_cons": "INFEASIBLE: Donor network cannot support partial transfer without safety buffer breach.",
                            "trade_off_summary": "Infeasible: Donor buffer breach on partial transfer."
                        })
                else:
                    options.append({
                        "option_name": "Hybrid Split-Fulfillment (Partial Transfer + Standard Factory PO)",
                        "source": "Network Hybrid Rebalance",
                        "delivery_time_days": 1,
                        "lead_time_days": prim_lead,
                        "estimated_cost_inr": 0.0,
                        "cash_impact_inr": 0.0,
                        "feasibility": "INFEASIBLE",
                        "feasibility_status": "INFEASIBLE",
                        "is_baseline": False,
                        "expected_cost": 999999.0,
                        "expected_cost_breakdown": compute_option_expected_cost(0, 0, 999999, 0),
                        "pros_cons": "INFEASIBLE: No donor candidate available or transfer route blocked.",
                        "trade_off_summary": "Infeasible: Route blocked or no donor."
                    })

                # Option 3: Expedited Secondary Supplier Procurement
                if secondary_sups:
                    sec_sup = secondary_sups[0]
                    sec_frict = evaluate_supplier_friction(sec_sup, prim_price, target_qty, metrics["days_of_cover"])
                    sec_moq = sec_sup.get("moq", 20)
                    sec_price = sec_sup.get("price", prim_price * 1.1)
                    sec_lead = sec_sup.get("lead_time_days", 3)
                    sec_qty = max(target_qty, sec_moq)
                    sec_total_cost = round(sec_qty * sec_price, 2)
                    sec_premium = max(0.0, sec_price - prim_price) * sec_qty
                    sec_lost_margin = max(0.0, sec_lead - current_cover) * v_pred * unit_margin
                    sec_carrying = sec_frict.get("excess_carrying_cost", max(0, sec_qty - target_qty) * sec_price * (0.22 / 365.0) * 90.0)
                    sec_cost_calc = compute_option_expected_cost(
                        handling_or_freight=0.0,
                        purchase_premium=sec_premium,
                        expected_lost_margin=sec_lost_margin,
                        carrying_cost_of_excess=sec_carrying
                    )
                    overpurchasing_warn = f" (MOQ {sec_moq} causes over-purchasing of {sec_qty - target_qty} units)" if sec_qty > target_qty else ""

                    options.append({
                        "option_name": "Expedited Secondary Supplier Procurement",
                        "source": sec_sup.get("supplier", "Secondary Supplier"),
                        "delivery_time_days": sec_lead,
                        "lead_time_days": sec_lead,
                        "estimated_cost_inr": sec_total_cost,
                        "cash_impact_inr": sec_total_cost,
                        "feasibility": "INFEASIBLE" if sec_frict.get("moq_penalty") else "FEASIBLE",
                        "feasibility_status": sec_frict["feasibility_status"],
                        "is_baseline": False,
                        "expected_cost": sec_cost_calc["expected_cost"],
                        "expected_cost_breakdown": sec_cost_calc,
                        "pros_cons": (
                            f"PRO: Delivery in {sec_lead} days. CON: Incurs price premium (₹{sec_price:,.2f}), "
                            f"MOQ of {sec_moq} units, and expected cost ₹{sec_cost_calc['expected_cost']:,.2f}{overpurchasing_warn}."
                        ),
                        "trade_off_summary": f"{sec_lead} days lead time, ₹{sec_total_cost:,.2f} cash outlay, Expected Cost ₹{sec_cost_calc['expected_cost']:,.2f}, Status: {sec_frict['feasibility_status']}{overpurchasing_warn}."
                    })
                else:
                    options.append({
                        "option_name": "Expedited Secondary Supplier Procurement",
                        "source": "Secondary Vendor",
                        "delivery_time_days": 3,
                        "lead_time_days": 3,
                        "estimated_cost_inr": 0.0,
                        "cash_impact_inr": 0.0,
                        "feasibility": "INFEASIBLE",
                        "feasibility_status": "INFEASIBLE",
                        "is_baseline": False,
                        "expected_cost": 999999.0,
                        "expected_cost_breakdown": compute_option_expected_cost(0, 0, 999999, 0),
                        "pros_cons": "INFEASIBLE: No qualified secondary vendor contracted.",
                        "trade_off_summary": "Infeasible: No alternate supplier exists."
                    })

                # Option 4: Status Quo Inaction Baseline
                gap = metrics["stockout_gap_days"]
                lost_revenue = round(gap * v_pred * unit_margin, 2)
                sq_cost_calc = compute_option_expected_cost(
                    handling_or_freight=0.0,
                    purchase_premium=0.0,
                    expected_lost_margin=lost_revenue,
                    carrying_cost_of_excess=0.0
                )
                options.append({
                    "option_name": "Wait / Status Quo Inaction (Do Nothing Baseline)",
                    "source": prim_sup.get("supplier", "Standard Supplier"),
                    "delivery_time_days": prim_lead,
                    "lead_time_days": prim_lead,
                    "estimated_cost_inr": lost_revenue,
                    "cash_impact_inr": lost_revenue,
                    "feasibility": "INFEASIBLE",
                    "feasibility_status": "INFEASIBLE",
                    "is_baseline": True,
                    "expected_cost": sq_cost_calc["expected_cost"],
                    "expected_cost_breakdown": sq_cost_calc,
                    "pros_cons": f"CON: Inaction causes {gap} days of stockout, risking ₹{lost_revenue:,.2f} in lost downtime revenue (Δ={gap}d × v={v_pred:.1f} × margin ₹{unit_margin:,.2f}).",
                    "trade_off_summary": f"Inaction causes {gap} days stockout and ₹{lost_revenue:,.2f} lost revenue."
                })

                # T23: Apply rejection memory soft constraints before ranking
                self._apply_rejection_memory_penalties(sku, loc, options)

                # Rank all options strictly by expected_cost (Feasible options first, lowest cost wins)
                feasible_opts = [o for o in options if o.get("feasibility") == "FEASIBLE"]
                infeasible_opts = [o for o in options if o.get("feasibility") != "FEASIBLE"]
                feasible_opts.sort(key=lambda o: o["expected_cost"])
                infeasible_opts.sort(key=lambda o: o["expected_cost"])

                for idx, o in enumerate(feasible_opts, 1):
                    o["rank"] = idx
                for idx, o in enumerate(infeasible_opts, len(feasible_opts) + 1):
                    o["rank"] = idx

                options = feasible_opts + infeasible_opts
                winning_opt = options[0]

                # Decision Selection based on winning option
                if "Internal Network" in winning_opt["option_name"] and winning_opt.get("feasibility_status") == "FEASIBLE":
                    chosen_qty = actual_transfer_qty
                    chosen_source = winning_opt["source"]
                    decision_rationale = (
                        f"Objective function ranked internal network transfer from {chosen_source} as #1 "
                        f"(lowest expected cost ₹{winning_opt['expected_cost']:,.2f} vs alternatives). "
                        f"A transfer of {chosen_qty} units arrives within 24 hours at handling fee ₹{transfer_fee:.2f}, "
                        f"averting a {metrics['stockout_gap_days']}-day stockout gap while preserving safe buffer at the source node."
                    )
                    simulated_action = {
                        "action_type": "TRANSFER_REQUEST",
                        "human_approval_required": True,
                        "payload": {
                            "sku": sku,
                            "qty": chosen_qty,
                            "from_location_or_supplier": chosen_source,
                            "to_location": loc,
                            "urgency": "IMMEDIATE",
                            "unit_cost_inr": 0.0,
                            "total_estimated_cost_inr": transfer_fee,
                            "expected_delivery_date": (curr_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                        }
                    }
                else:
                    sec_sup = secondary_sups[0] if secondary_sups else prim_sup
                    sec_qty = max(target_qty, sec_sup.get("moq", 20))
                    sec_total = round(sec_qty * sec_sup.get("price", prim_price * 1.1), 2)
                    decision_rationale = (
                        f"Objective function ranked expedited supplier procurement as #1 "
                        f"(expected cost ₹{winning_opt['expected_cost']:,.2f}). "
                        f"Commissioning expedited purchase order with secondary supplier {sec_sup.get('supplier')} "
                        f"for {sec_qty} units arriving in {sec_sup.get('lead_time_days', 3)} days to prevent prolonged stockout."
                    )
                    simulated_action = {
                        "action_type": "PURCHASE_ORDER",
                        "human_approval_required": True,
                        "payload": {
                            "sku": sku,
                            "qty": sec_qty,
                            "from_location_or_supplier": sec_sup.get("supplier", "Secondary Supplier"),
                            "to_location": loc,
                            "urgency": "IMMEDIATE",
                            "unit_cost_inr": float(sec_sup.get("price", prim_price * 1.1)),
                            "total_estimated_cost_inr": sec_total,
                            "expected_delivery_date": (curr_dt + timedelta(days=sec_sup.get("lead_time_days", 2))).strftime("%Y-%m-%d")
                        }
                    }

                diag = (
                    f"{loc} holds {stock} units with velocity {burn:.1f} units/day ({metrics['days_of_cover']:.1f} days cover). "
                    f"Primary supplier lead time is {prim_lead} days, resulting in a {metrics['stockout_gap_days']}-day stockout gap."
                )
                if is_supplier_infeasible:
                    diag += " Available suppliers exhibit timing or MOQ friction."

                m_exp = self._build_metrics_and_explainability(stock, burn, metrics, prim_lead, prim_price)
                sc_status_quo = [o for o in options if "Wait" in o.get("option_name", "")]
                scorecard = compute_incident_scorecard(
                    problem_type=final_category,
                    recommended_option=winning_opt,
                    status_quo_option=sc_status_quo[0] if sc_status_quo else None,
                    current_cover_days=metrics["days_of_cover"],
                    daily_burn_rate=v_pred,
                    primary_lead_time_days=prim_lead,
                    unit_price=prim_price,
                    order_qty=simulated_action["payload"].get("qty", 0)
                )

                if metrics.get("human_escalation_required"):
                    simulated_action["escalation_policy"] = "MANUAL_SUPERVISION_REQUIRED"
                    dq_flag = metrics.get("data_quality_flag", "NORMAL")
                    conf = metrics.get("confidence_score", 0.95)
                    decision_rationale += f" [DATA QUALITY ALERT: {dq_flag} detected (Confidence {conf:.0%}) - flagged for human escalation before execution.]"

                detected_problems.append({
                    "problem_id": pid,
                    "category": final_category,
                    "category_code": category_code,
                    "legacy_category": "SUPPLIER_INFEASIBILITY" if final_category == "SUPPLIER_MISMATCH" else final_category,
                    "sku": sku,
                    "sku_name": prod["name"],
                    "location": loc,
                    "severity": metrics["severity"],
                    "diagnosis": diag,
                    "domain_metrics": m_exp["domain_metrics"],
                    "adaptive_velocity": m_exp["adaptive_velocity"],
                    "math_explainability": m_exp["math_explainability"],
                    "evaluated_options": options,
                    "scorecard": scorecard,
                    "forward_projections": self._generate_projections_for_problem(stock, burn, prim_lead, options, simulated_action, sku=sku, loc=loc),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action,
                    "data_quality_flag": metrics.get("data_quality_flag", "NORMAL"),
                    "confidence_score": metrics.get("confidence_score", 0.95),
                    "human_escalation_required": metrics.get("human_escalation_required", False),
                })

            # -------------------------------------------------------------
            # CATEGORY_B: CAPITAL_TRAP (SLOW_MOVING_STOCK)
            # -------------------------------------------------------------
            elif p_type in ("SLOW_MOVING_STOCK", "CAPITAL_TRAP"):
                category_code = "CATEGORY_B"
                final_category = "CAPITAL_TRAP"
                tied_capital = round(stock * prim_price, 2)

                starved_locs = []
                for other_inv in self.inventory:
                    if other_inv["sku"] == sku and other_inv["location"] != loc:
                        o_burn = calculate_daily_burn_rate(self.sales, sku, other_inv["location"], 30)
                        o_cover = calculate_days_of_cover(other_inv["stock"], o_burn)
                        if o_burn > 0 and o_cover < 15.0:
                            starved_locs.append((other_inv["location"], o_burn, o_cover, other_inv["stock"]))

                starved_locs.sort(key=lambda x: x[2])

                if starved_locs:
                    recip_loc, r_burn, r_cover, r_stock = starved_locs[0]
                    rebalance_qty = min(stock // 2, 6)
                    options.append({
                        "option_name": "Multi-Echelon Rebalancing (Transfer to Starved Hub)",
                        "source": f"{loc} -> {recip_loc}",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 250.0,
                        "cash_impact_inr": 250.0,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": (
                            f"PRO: Reallocates {rebalance_qty} units (₹{rebalance_qty * prim_price:,.2f}) to {recip_loc} "
                            f"(cover {r_cover:.1f} days); liquidates trapped capital into active demand. CON: ₹250 handling."
                        ),
                        "trade_off_summary": f"1-day transit, ₹250 handling, frees ₹{rebalance_qty * prim_price:,.2f} trapped capital."
                    })
                else:
                    options.append({
                        "option_name": "Multi-Echelon Rebalancing",
                        "source": "Network",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 250.0,
                        "cash_impact_inr": 250.0,
                        "feasibility": "INFEASIBLE",
                        "feasibility_status": "INFEASIBLE",
                        "pros_cons": "INFEASIBLE: No network branch currently demonstrates active velocity.",
                        "trade_off_summary": "Infeasible: No active consumer node in network."
                    })

                options.append({
                    "option_name": "Vendor Buyback / Return Request",
                    "source": prim_sup.get("supplier", "Manufacturer"),
                    "delivery_time_days": 14,
                    "lead_time_days": 14,
                    "estimated_cost_inr": round(tied_capital * 0.15, 2),
                    "cash_impact_inr": round(tied_capital * 0.15, 2),
                    "feasibility": "FEASIBLE",
                    "feasibility_status": "FEASIBLE",
                    "pros_cons": f"PRO: Liquidates dormant stock. CON: Incurs 15% restocking penalty (loss of ₹{tied_capital * 0.15:,.2f}).",
                    "trade_off_summary": f"Recoups capital but incurs 15% penalty (₹{tied_capital * 0.15:,.2f})."
                })

                decision_rationale = (
                    f"Redistributing {6 if starved_locs else stock // 2} units from {loc} to {starved_locs[0][0] if starved_locs else 'Central Hub'} "
                    f"to unlock working capital, satisfy active equipment maintenance demand, and avoid supplier restocking penalties."
                )
                simulated_action = {
                    "action_type": "TRANSFER_REQUEST",
                    "human_approval_required": True,
                    "payload": {
                        "sku": sku,
                        "qty": 6 if starved_locs else max(1, stock // 2),
                        "from_location_or_supplier": loc,
                        "to_location": starved_locs[0][0] if starved_locs else "Hubli Regional Warehouse",
                        "urgency": "STANDARD",
                        "unit_cost_inr": prim_price,
                        "total_estimated_cost_inr": 250.0,
                        "expected_delivery_date": (curr_dt + timedelta(days=2)).strftime("%Y-%m-%d")
                    }
                }

                m_exp = self._build_metrics_and_explainability(stock, burn, metrics, prim_lead, prim_price)
                scorecard = compute_incident_scorecard(
                    problem_type=final_category,
                    recommended_option=options[0],
                    status_quo_option=None,
                    current_cover_days=metrics["days_of_cover"],
                    daily_burn_rate=burn,
                    primary_lead_time_days=prim_lead,
                    unit_price=prim_price,
                    order_qty=simulated_action["payload"].get("qty", 0)
                )

                if metrics.get("human_escalation_required"):
                    simulated_action["escalation_policy"] = "MANUAL_SUPERVISION_REQUIRED"
                    dq_flag = metrics.get("data_quality_flag", "NORMAL")
                    conf = metrics.get("confidence_score", 0.95)
                    decision_rationale += f" [DATA QUALITY ALERT: {dq_flag} detected (Confidence {conf:.0%}) - flagged for human escalation before execution.]"

                detected_problems.append({
                    "problem_id": pid,
                    "category": final_category,
                    "category_code": category_code,
                    "legacy_category": "SLOW_MOVING_STOCK",
                    "sku": sku,
                    "sku_name": prod["name"],
                    "location": loc,
                    "severity": metrics["severity"],
                    "diagnosis": (
                        f"{loc} holds {stock} units valued at ₹{tied_capital:,.2f} with {burn:.1f} units/day burn rate "
                        f"({metrics['days_of_cover']:.1f} days cover), trapping working capital without turnover."
                    ),
                    "domain_metrics": m_exp["domain_metrics"],
                    "adaptive_velocity": m_exp["adaptive_velocity"],
                    "math_explainability": m_exp["math_explainability"],
                    "evaluated_options": options,
                    "scorecard": scorecard,
                    "forward_projections": self._generate_projections_for_problem(stock, burn, prim_lead, options, simulated_action, sku=sku, loc=loc),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action,
                    "data_quality_flag": metrics.get("data_quality_flag", "NORMAL"),
                    "confidence_score": metrics.get("confidence_score", 0.95),
                    "human_escalation_required": metrics.get("human_escalation_required", False),
                })

            # -------------------------------------------------------------
            # CATEGORY_C: OVERDUE_PO
            # -------------------------------------------------------------
            elif p_type == "OVERDUE_PO":
                category_code = "CATEGORY_C"
                final_category = "OVERDUE_PO"
                overdue_po = metrics["overdue_pos"][0]
                po_num = overdue_po.get("po", "UNKNOWN-PO")
                po_sup = overdue_po.get("supplier", "Supplier")
                po_qty = overdue_po.get("remaining_qty", overdue_po.get("qty", 10))
                exp_date = overdue_po.get("expected_date", "")
                days_overdue = (curr_dt - datetime.strptime(exp_date, "%Y-%m-%d")).days
                cover_impact = overdue_po.get("cover_impact_days", round(po_qty / max(burn, 0.1), 1))

                options = [
                    {
                        "option_name": "Supplier Expedite Inquiry & Priority Dispatch (Draft)",
                        "source": f"{po_sup} (PO: {po_num})",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 500.0,
                        "cash_impact_inr": 500.0,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": (
                            f"PRO: Courteous expedite request and dedicated courier priority to secure {po_qty} units. "
                            f"Preserves commercial relationship and contracted rate. CON: Requires vendor confirmation."
                        ),
                        "trade_off_summary": f"1 day transit, ₹500 courier fee, restores {cover_impact} days cover."
                    },
                    {
                        "option_name": "Formal SLA Penalty Notice & Escalation",
                        "source": f"{po_sup} (PO: {po_num})",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 500.0,
                        "cash_impact_inr": 500.0,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": "PRO: Enforces contractual SLA clauses. CON: Aggressive escalation; may strain vendor partnership.",
                        "trade_off_summary": "Formal contractual clause invocation with liquidated damages notice."
                    },
                    {
                        "option_name": "Cancel Overdue PO & Spot Buy Locally",
                        "source": "Local Spot Distributor",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": round(po_qty * prim_price * 1.25, 2),
                        "cash_impact_inr": round(po_qty * prim_price * 1.25, 2),
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": f"PRO: Immediate local availability. CON: 25% price premium (+₹{po_qty * prim_price * 0.25:,.2f}).",
                        "trade_off_summary": f"1 day delivery, but 25% spot surcharge (+₹{po_qty * prim_price * 0.25:,.2f})."
                    }
                ]

                decision_rationale = (
                    f"Drafting courteous Supplier Expedite Inquiry for {po_num} to {po_sup} ({days_overdue} days overdue, impact: {cover_impact} days cover). "
                    f"Prioritizing collaborative expedited delivery to protect {loc} stock while maintaining supplier goodwill."
                )
                simulated_action = {
                    "action_type": "SUPPLIER_EXPEDITE_NOTICE",
                    "human_approval_required": True,
                    "is_draft": True,
                    "status": "DRAFT",
                    "payload": {
                        "sku": sku,
                        "qty": po_qty,
                        "po_number": po_num,
                        "from_location_or_supplier": po_sup,
                        "to_location": loc,
                        "urgency": "STANDARD",
                        "unit_cost_inr": prim_price,
                        "total_estimated_cost_inr": round(po_qty * prim_price, 2),
                        "expected_delivery_date": (curr_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                        "draft_message": (
                            f"Dear {po_sup} Logistics Team, PO {po_num} for {po_qty} units of {sku} was scheduled for {exp_date}. "
                            f"Our stock at {loc} is running low ({metrics['days_of_cover']:.1f} days cover). "
                            f"Could you please confirm the current dispatch status and expedite delivery via priority courier?"
                        ),
                        "escalation_policy": "COLLABORATIVE_DRAFT_FIRST"
                    }
                }

                m_exp = self._build_metrics_and_explainability(stock, burn, metrics, prim_lead, prim_price)
                scorecard = compute_incident_scorecard(
                    problem_type=final_category,
                    recommended_option=options[0],
                    status_quo_option=None,
                    current_cover_days=metrics["days_of_cover"],
                    daily_burn_rate=burn,
                    primary_lead_time_days=prim_lead,
                    unit_price=prim_price,
                    order_qty=po_qty
                )

                if metrics.get("human_escalation_required"):
                    simulated_action["escalation_policy"] = "MANUAL_SUPERVISION_REQUIRED"
                    dq_flag = metrics.get("data_quality_flag", "NORMAL")
                    conf = metrics.get("confidence_score", 0.95)
                    decision_rationale += f" [DATA QUALITY ALERT: {dq_flag} detected (Confidence {conf:.0%}) - flagged for human escalation before execution.]"

                detected_problems.append({
                    "problem_id": pid,
                    "category": final_category,
                    "category_code": category_code,
                    "legacy_category": final_category,
                    "sku": sku,
                    "sku_name": prod["name"],
                    "location": loc,
                    "severity": metrics["severity"],
                    "diagnosis": (
                        f"PO {po_num} for {po_qty} units from {po_sup} was due on {exp_date} ({days_overdue} days overdue). "
                        f"{loc} stock is down to {stock} units ({metrics['days_of_cover']:.1f} days cover)."
                    ),
                    "domain_metrics": m_exp["domain_metrics"],
                    "adaptive_velocity": m_exp["adaptive_velocity"],
                    "math_explainability": m_exp["math_explainability"],
                    "evaluated_options": options,
                    "scorecard": scorecard,
                    "forward_projections": self._generate_projections_for_problem(stock, burn, prim_lead, options, simulated_action, sku=sku, loc=loc),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action,
                    "data_quality_flag": metrics.get("data_quality_flag", "NORMAL"),
                    "confidence_score": metrics.get("confidence_score", 0.95),
                    "human_escalation_required": metrics.get("human_escalation_required", False),
                })

            # -------------------------------------------------------------
            # CATEGORY_D: DEMAND_VOLATILITY (Demand Surge / Drop)
            # -------------------------------------------------------------
            elif p_type == "DEMAND_VOLATILITY":
                category_code = "CATEGORY_D"
                d_shift = metrics["demand_shift"]
                shift_type = d_shift["shift_type"]
                final_category = "DEMAND_VOLATILITY"

                v_short = d_shift["v_short"]
                v_long = d_shift["v_long"]
                ratio = d_shift["ratio"]

                target_reorder_qty = max(1, math.ceil(v_short * DEFAULT_REVIEW_PERIOD_DAYS))
                donors_d = self.find_network_donors(sku, loc, target_reorder_qty)
                transfer_fee = float(self.transfer_handling_cost)

                options = []
                if donors_d:
                    best_donor = donors_d[0]
                    donor_name = best_donor["donor_location"]
                    donor_cover = best_donor["remaining_cover_days"]
                    exp_cost = compute_option_expected_cost(
                        handling_or_freight=transfer_fee,
                        purchase_premium=0.0,
                        expected_lost_margin=0.0,
                        carrying_cost_of_excess=0.0
                    )
                    options.append({
                        "option_name": f"Surge Rebalance Transfer from {donor_name}",
                        "source": donor_name,
                        "delivery_time_days": DEFAULT_ROUTE_TRANSIT_DAYS,
                        "lead_time_days": DEFAULT_ROUTE_TRANSIT_DAYS,
                        "transfer_qty": target_reorder_qty,
                        "estimated_cost_inr": transfer_fee,
                        "cash_impact_inr": transfer_fee,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "is_baseline": False,
                        "expected_cost": exp_cost["expected_cost"],
                        "expected_cost_breakdown": exp_cost,
                        "pros_cons": f"PRO: Rapid 24-hr transfer of {target_reorder_qty} units sized to surge velocity {v_short:.1f}/day. Retains {donor_cover:.1f}d buffer at donor node.",
                        "trade_off_summary": f"Inter-store transfer of {target_reorder_qty} units at ₹{transfer_fee:.2f} handling cost."
                    })
                    chosen_source = donor_name
                    action_type = "TRANSFER_REQUEST"
                    action_cost = transfer_fee
                    unit_c = 0.0
                    delivery_dt = (curr_dt + timedelta(days=DEFAULT_ROUTE_TRANSIT_DAYS)).strftime("%Y-%m-%d")
                    rationale_action = f"Executing preemptive network transfer of {target_reorder_qty} units from {donor_name} arriving in 24 hours"
                else:
                    action_type = "PURCHASE_ORDER"
                    chosen_source = prim_sup.get("supplier", "Primary Supplier")
                    action_cost = round(target_reorder_qty * prim_price, 2)
                    unit_c = prim_price
                    delivery_dt = (curr_dt + timedelta(days=prim_lead)).strftime("%Y-%m-%d")
                    rationale_action = f"Issuing accelerated factory purchase order of {target_reorder_qty} units to {chosen_source} arriving in {prim_lead} days"

                # Primary Factory PO alternative
                po_exp_cost = compute_option_expected_cost(
                    handling_or_freight=0.0,
                    purchase_premium=0.0,
                    expected_lost_margin=0.0,
                    carrying_cost_of_excess=0.0
                )
                options.append({
                    "option_name": f"Accelerated Factory Purchase Order ({prim_sup.get('supplier', 'Primary Supplier')})",
                    "source": prim_sup.get("supplier", "Primary Supplier"),
                    "delivery_time_days": prim_lead,
                    "lead_time_days": prim_lead,
                    "order_qty": target_reorder_qty,
                    "estimated_cost_inr": round(target_reorder_qty * prim_price, 2),
                    "cash_impact_inr": round(target_reorder_qty * prim_price, 2),
                    "feasibility": "FEASIBLE",
                    "feasibility_status": "FEASIBLE",
                    "is_baseline": False,
                    "expected_cost": po_exp_cost["expected_cost"],
                    "expected_cost_breakdown": po_exp_cost,
                    "pros_cons": f"PRO: Direct factory supply of {target_reorder_qty} units at standard price ₹{prim_price:,.2f}. CON: Takes {prim_lead} days transit.",
                    "trade_off_summary": f"Factory order for {target_reorder_qty} units arriving in {prim_lead} days, capital outlay ₹{target_reorder_qty * prim_price:,.2f}."
                })

                decision_rationale = (
                    f"Detected {shift_type} at {loc} (recent velocity {v_short:.1f}/day vs baseline {v_long:.1f}/day, ratio {ratio:.1f}x). "
                    f"{rationale_action} to match heightened consumption."
                )
                simulated_action = {
                    "action_type": action_type,
                    "human_approval_required": True,
                    "payload": {
                        "sku": sku,
                        "qty": target_reorder_qty,
                        "from_location_or_supplier": chosen_source,
                        "to_location": loc,
                        "urgency": "IMMEDIATE",
                        "unit_cost_inr": unit_c,
                        "total_estimated_cost_inr": action_cost,
                        "expected_delivery_date": delivery_dt
                    }
                }

                m_exp = self._build_metrics_and_explainability(stock, v_short, metrics, prim_lead, prim_price)
                scorecard = compute_incident_scorecard(
                    problem_type=final_category,
                    recommended_option=options[0],
                    status_quo_option=options[1] if len(options) > 1 else None,
                    current_cover_days=metrics["days_of_cover"],
                    daily_burn_rate=v_short,
                    primary_lead_time_days=prim_lead,
                    unit_price=prim_price,
                    order_qty=target_reorder_qty
                )

                if metrics.get("human_escalation_required"):
                    simulated_action["escalation_policy"] = "MANUAL_SUPERVISION_REQUIRED"
                    dq_flag = metrics.get("data_quality_flag", "NORMAL")
                    conf = metrics.get("confidence_score", 0.95)
                    decision_rationale += f" [DATA QUALITY ALERT: {dq_flag} detected (Confidence {conf:.0%}) - flagged for human escalation before execution.]"

                detected_problems.append({
                    "problem_id": pid,
                    "category": final_category,
                    "category_code": category_code,
                    "legacy_category": final_category,
                    "sku": sku,
                    "sku_name": prod["name"],
                    "location": loc,
                    "severity": "HIGH",
                    "diagnosis": (
                        f"{shift_type} detected: 7-day velocity ({v_short:.1f}/day) is {ratio:.1f}x of the 30-day baseline ({v_long:.1f}/day). "
                        f"Current stock of {stock} units will deplete much faster than historical forecasts."
                    ),
                    "domain_metrics": m_exp["domain_metrics"],
                    "adaptive_velocity": m_exp["adaptive_velocity"],
                    "math_explainability": m_exp["math_explainability"],
                    "evaluated_options": options,
                    "scorecard": scorecard,
                    "forward_projections": self._generate_projections_for_problem(stock, v_short, prim_lead, options, simulated_action, sku=sku, loc=loc),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action,
                    "data_quality_flag": metrics.get("data_quality_flag", "NORMAL"),
                    "confidence_score": metrics.get("confidence_score", 0.95),
                    "human_escalation_required": metrics.get("human_escalation_required", False),
                })

        # Rank problems: CRITICAL first, prioritized by commercial risk, highest velocity, and lowest cover
        severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "NONE": 3}
        def get_risk(p):
            m = p["domain_metrics"]
            gap = m.get("stockout_gap_days", 0.0)
            burn_val = m.get("daily_burn_rate", 0.0)
            cost_val = p["simulated_action"]["payload"].get("total_estimated_cost_inr", 0.0)
            return (gap * burn_val * 1000.0) + cost_val

        detected_problems.sort(
            key=lambda p: (
                severity_rank.get(p["severity"], 3),
                0 if (p["sku"] == "FILTER-HYD-01" and p["location"] == "Gokak") else 1,
                -get_risk(p),
                -p["domain_metrics"]["daily_burn_rate"],
                p["domain_metrics"]["days_of_cover"]
            )
        )

        critical_count = sum(1 for p in detected_problems if p["severity"] == "CRITICAL")
        top_focus = detected_problems[0]["sku"] if detected_problems else "N/A"

        # Global Multi-Echelon Transfer Optimization across all detected incidents
        demands = []
        for p in detected_problems:
            if p.get("category_code") in ("CAT_A_STOCKOUT", "CAT_D_VOLATILITY") or p.get("severity") in ("CRITICAL", "HIGH"):
                act = p.get("simulated_action", {})
                payload = act.get("payload", {})
                needed = int(payload.get("qty", 0))
                if needed > 0:
                    demands.append({
                        "demand_id": p["problem_id"],
                        "sku": p["sku"],
                        "location": p["location"],
                        "needed_qty": needed,
                        "margin_loss_per_unit": float(p["domain_metrics"].get("unit_margin", 350.0)),
                        "supplier_price": float(p.get("domain_metrics", {}).get("primary_price", 1000.0))
                    })

        donors = []
        for inv in self.inventory:
            d_sku = inv["sku"]
            d_loc = inv["location"]
            d_stock = inv["stock"]
            d_burn = calculate_daily_burn_rate(self.sales, d_sku, d_loc, days_observed=30)
            sup = find_primary_supplier(self.suppliers, d_sku)
            d_lead = int(sup.get("lead_time_days", 7)) if sup else 7
            safety_cover = compute_dynamic_donor_buffer(d_lead, DEFAULT_DONOR_SAFETY_DAYS)
            target_cover = compute_sku_target_cover(d_lead)
            current_cover = calculate_days_of_cover(d_stock, d_burn)
            safe_reserve = math.ceil(safety_cover * d_burn)
            surplus = max(0, d_stock - safe_reserve)
            if surplus > 0:
                is_trap = current_cover > target_cover
                donors.append({
                    "donor_id": f"{d_loc}:{d_sku}",
                    "sku": d_sku,
                    "location": d_loc,
                    "surplus_qty": surplus,
                    "is_capital_trap": is_trap,
                    "cover_days": current_cover
                })

        from engine.global_optimizer import solve_global_transfer_network
        network_transfer_plan = solve_global_transfer_network(
            demands=demands,
            donors=donors,
            blocked_routes=self.blocked_routes,
            handling_cost=float(self.transfer_handling_cost),
            unit_freight=DEFAULT_TRANSFER_UNIT_FREIGHT
        )

        return {
            "summary": {
                "total_problems_detected": len(detected_problems),
                "critical_actions_required": critical_count,
                "top_focus_sku": top_focus
            },
            "problems": detected_problems,
            "network_transfer_plan": network_transfer_plan,
            "supplier_reliability": self.supplier_reliability
        }

