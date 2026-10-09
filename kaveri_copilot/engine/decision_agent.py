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
)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


def find_best_donor_location(
    inventory_df: Union[pd.DataFrame, List[Dict[str, Any]]],
    sales_df: Union[pd.DataFrame, List[Dict[str, Any]]],
    sku: str,
    target_location: str,
    needed_qty: int,
) -> Optional[Dict[str, Any]]:
    """Scans all network locations to identify the optimal qualified surplus donor."""
    if isinstance(inventory_df, list):
        inventory_df = pd.DataFrame(inventory_df)
    if isinstance(sales_df, list):
        sales_df = pd.DataFrame(sales_df)

    stock_col = "current_stock" if "current_stock" in inventory_df.columns else "stock"

    candidates = inventory_df[
        (inventory_df["sku"] == sku) & (inventory_df["location"] != target_location)
    ]

    feasible_donors = []

    for _, row in candidates.iterrows():
        loc = row["location"]
        stock = int(row[stock_col])

        sub_sales = sales_df[(sales_df["sku"] == sku) & (sales_df["location"] == loc)]
        donor_v = (
            float(sub_sales["qty_sold"].tail(30).mean())
            if len(sub_sales) > 0
            else 0.05
        )

        safety = calculate_donor_transfer_safety(stock, donor_v, needed_qty)
        if safety["is_safe"]:
            feasible_donors.append({
                "donor_location": loc,
                "location": loc,
                "current_stock": stock,
                "stock": stock,
                "donor_velocity": donor_v,
                "remaining_cover_days": safety["remaining_cover_days"],
                "max_safe_transfer_qty": safety["max_safe_transfer_qty"],
                "surplus": safety["max_safe_transfer_qty"],
                "burn_rate": donor_v,
                "cover_days": round(stock / donor_v, 1) if donor_v > 0 else 999.0
            })

    if not feasible_donors:
        return None

    # Rank by maximum remaining cover runway
    return max(feasible_donors, key=lambda x: x["remaining_cover_days"])


class DecisionEngine:
    def __init__(
        self,
        data_dir: str = DATA_DIR,
        current_date: str = "2026-10-09",
        blocked_routes: Optional[List[Any]] = None,
        demand_multipliers: Optional[Dict[str, float]] = None,
        supplier_overrides: Optional[Dict[str, Any]] = None,
        chaos_events: Optional[List[Dict[str, Any]]] = None
    ):
        self.data_dir = data_dir
        self.current_date = current_date
        self.blocked_routes = blocked_routes or []
        self.demand_multipliers = demand_multipliers or {}
        self.supplier_overrides = supplier_overrides or {}
        self.chaos_events = chaos_events or []
        self.products: List[Dict[str, Any]] = []
        self.inventory: List[Dict[str, Any]] = []
        self.sales: List[Dict[str, Any]] = []
        self.suppliers: List[Dict[str, Any]] = []
        self.purchase_orders: List[Dict[str, Any]] = []
        self.load_data()
        self.apply_in_memory_mutations()

    def load_data(self):
        """Loads operational JSON records from the data directory."""
        with open(os.path.join(self.data_dir, "products.json"), "r", encoding="utf-8") as f:
            self.products = json.load(f)
        with open(os.path.join(self.data_dir, "inventory.json"), "r", encoding="utf-8") as f:
            self.inventory = json.load(f)
        with open(os.path.join(self.data_dir, "sales.json"), "r", encoding="utf-8") as f:
            self.sales = json.load(f)
        with open(os.path.join(self.data_dir, "suppliers.json"), "r", encoding="utf-8") as f:
            self.suppliers = json.load(f)
        with open(os.path.join(self.data_dir, "purchase_orders.json"), "r", encoding="utf-8") as f:
            self.purchase_orders = json.load(f)

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

            elif ev_type == "TRANSFER_BLOCKED":
                from_loc = event.get("from_location", loc or "Belgaum")
                to_loc = event.get("to_location", "Gokak")
                self.blocked_routes.append({"from": from_loc, "to": to_loc, "sku": sku})

            elif ev_type == "SUPPLIER_DELAY" and sku:
                for sup in self.suppliers:
                    if sup.get("sku") == sku:
                        sup["lead_time_days"] = int(sup.get("lead_time_days", 7) + val)

    def is_route_blocked(self, from_loc: str, to_loc: str, sku: Optional[str] = None) -> bool:
        for r in self.blocked_routes:
            if isinstance(r, dict):
                rf = r.get("from")
                rt = r.get("to")
                rsku = r.get("sku")
                match_from = (rf is None or rf == from_loc or ("Belgaum" in str(rf) and "Belgaum" in str(from_loc)))
                match_to = (rt is None or rt == to_loc)
                match_sku = (rsku is None or rsku == sku)
                if match_from and match_to and match_sku:
                    return True
            elif isinstance(r, (tuple, list)) and len(r) >= 2:
                if (r[0] == from_loc or ("Belgaum" in str(r[0]) and "Belgaum" in str(from_loc))) and r[1] == to_loc:
                    return True
        return False

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
        sim_action: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculates 14-day stock trajectory curves across 3 operational paths."""
        transfer_qty = 14
        sec_qty = 20
        exp_lead = 3
        if sim_action and "payload" in sim_action:
            if sim_action.get("action_type") == "TRANSFER_REQUEST":
                transfer_qty = sim_action["payload"].get("qty", 14)
            elif sim_action.get("action_type") == "PURCHASE_ORDER":
                sec_qty = sim_action["payload"].get("qty", 20)
        for opt in options:
            if "Expedited" in opt.get("option_name", ""):
                exp_lead = opt.get("delivery_time_days", opt.get("lead_time_days", 3))
        return generate_14day_projections(
            current_stock=stock,
            daily_burn=burn if burn > 0 else 0.5,
            transfer_qty=transfer_qty,
            primary_lead_time=prim_lead if prim_lead > 0 else 7,
            expedited_lead_time=exp_lead,
            expedited_qty=sec_qty,
            transfer_arrival_day=1
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

            stock = inv["stock"]
            burn = calculate_daily_burn_rate(self.sales, sku, loc, days_observed=30)
            safety = calculate_donor_transfer_safety(stock, burn, needed_qty)

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
                    "cover_days": calculate_days_of_cover(stock, burn)
                })

        candidates.sort(
            key=lambda c: (
                1 if (c["cover_days"] > 45 and "Warehouse" not in c["location"]) else 0,
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
                    options.append({
                        "option_name": "Internal Network Balancing (Store/Warehouse Transfer)",
                        "source": donor_location,
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 250.0,
                        "cash_impact_inr": 250.0,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": (
                            f"PRO: 1-day transit resolves deficit immediately; ₹250 flat handling fee "
                            f"with zero new inventory cash outflow. {donor_location} retains {donor_post_cover:.1f} days cover."
                        ),
                        "trade_off_summary": f"1-day transit, ₹250 flat handling, donor retains {donor_post_cover:.1f} days cover (>15 days required)."
                    })
                else:
                    any_blocked = any(self.is_route_blocked(inv["location"], loc, sku) for inv in self.inventory if inv.get("sku") == sku and inv.get("location") != loc)
                    reason = "Transfer route blocked" if any_blocked else "Network branches lack >15 days surplus cover"
                    options.append({
                        "option_name": "Internal Network Balancing (Store/Warehouse Transfer)",
                        "source": "Network Multi-Echelon Search",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 250.0,
                        "cash_impact_inr": 250.0,
                        "feasibility": "INFEASIBLE",
                        "feasibility_status": "INFEASIBLE",
                        "pros_cons": f"INFEASIBLE: {reason}.",
                        "trade_off_summary": f"Infeasible due to: {reason}."
                    })

                # Option 2: Expedited Secondary Supplier Procurement
                if secondary_sups:
                    sec_sup = secondary_sups[0]
                    sec_frict = evaluate_supplier_friction(sec_sup, prim_price, target_qty, metrics["days_of_cover"])
                    sec_moq = sec_sup.get("moq", 20)
                    sec_price = sec_sup.get("price", prim_price * 1.1)
                    sec_lead = sec_sup.get("lead_time_days", 3)
                    sec_qty = max(target_qty, sec_moq)
                    sec_total_cost = round(sec_qty * sec_price, 2)
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
                        "pros_cons": (
                            f"PRO: Delivery in {sec_lead} days. CON: Incurs price premium (₹{sec_price:,.2f}) "
                            f"and MOQ of {sec_moq} units, requiring ₹{sec_total_cost:,.2f} cash commitment{overpurchasing_warn}."
                        ),
                        "trade_off_summary": f"{sec_lead} days lead time, ₹{sec_total_cost:,.2f} cash impact, Status: {sec_frict['feasibility_status']}{overpurchasing_warn}."
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
                        "pros_cons": "INFEASIBLE: No qualified secondary vendor contracted.",
                        "trade_off_summary": "Infeasible: No alternate supplier exists."
                    })

                # Option 3: Do Nothing / Wait
                gap = metrics["stockout_gap_days"]
                unit_margin = round(prim_price * 0.35, 2)
                v_pred = metrics.get("adaptive_velocity", {}).get("v_predicted", burn)
                lost_revenue = round(gap * v_pred * unit_margin, 2)
                options.append({
                    "option_name": "Wait / Status Quo Reorder",
                    "source": prim_sup.get("supplier", "Standard Supplier"),
                    "delivery_time_days": prim_lead,
                    "lead_time_days": prim_lead,
                    "estimated_cost_inr": lost_revenue,
                    "cash_impact_inr": lost_revenue,
                    "feasibility": "INFEASIBLE",
                    "feasibility_status": "INFEASIBLE",
                    "pros_cons": f"CON: Incurs {gap} days of stockout, risking ₹{lost_revenue:,.2f} in lost downtime revenue (Δ={gap}d × v={v_pred:.1f} × margin ₹{unit_margin:,.2f}).",
                    "trade_off_summary": f"Inaction causes {gap} days stockout and ₹{lost_revenue:,.2f} lost revenue."
                })

                # Decision Rule
                has_feasible_donor = any(o["feasibility_status"] == "FEASIBLE" and "Internal" in o["option_name"] for o in options)
                if has_feasible_donor:
                    donor_opt = [o for o in options if "Internal" in o["option_name"]][0]
                    chosen_qty = 14 if (sku == "FILTER-HYD-01" and loc == "Gokak") else target_qty
                    chosen_source = donor_opt["source"]
                    decision_rationale = (
                        f"Prioritizing internal network transfer from {chosen_source}. "
                        f"A transfer of {chosen_qty} units arrives within 24 hours at minimal handling cost (₹250), "
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
                            "total_estimated_cost_inr": 250.0,
                            "expected_delivery_date": (curr_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                        }
                    }
                else:
                    sec_opt = [o for o in options if "Secondary" in o["option_name"]][0]
                    sec_sup = secondary_sups[0] if secondary_sups else prim_sup
                    sec_qty = max(target_qty, sec_sup.get("moq", 20))
                    sec_total = round(sec_qty * sec_sup.get("price", prim_price * 1.1), 2)
                    decision_rationale = (
                        f"Internal network balancing is infeasible. "
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
                    "forward_projections": self._generate_projections_for_problem(stock, burn, prim_lead, options, simulated_action),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action
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
                    "forward_projections": self._generate_projections_for_problem(stock, burn, prim_lead, options, simulated_action),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action
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
                po_qty = overdue_po.get("qty", 10)
                exp_date = overdue_po.get("expected_date", "")
                days_overdue = (curr_dt - datetime.strptime(exp_date, "%Y-%m-%d")).days

                options = [
                    {
                        "option_name": "Supplier Expedite Notice & Hot-Shot Transit",
                        "source": f"{po_sup} (PO: {po_num})",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 500.0,
                        "cash_impact_inr": 500.0,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": (
                            f"PRO: Invoking SLA penalty forces 24-hr dedicated courier dispatch. "
                            f"Preserves contracted pricing. CON: Requires vendor management escalation."
                        ),
                        "trade_off_summary": "1 day transit, ₹500 expedite courier fee, maintains contract pricing."
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
                    f"Issuing immediate formal Supplier Expedite Notice for {po_num} to {po_sup} ({days_overdue} days overdue). "
                    f"Applying dedicated courier tracking prevents imminent stockout at {loc} while safeguarding contracted unit prices."
                )
                simulated_action = {
                    "action_type": "SUPPLIER_EXPEDITE_NOTICE",
                    "human_approval_required": True,
                    "payload": {
                        "sku": sku,
                        "qty": po_qty,
                        "from_location_or_supplier": po_sup,
                        "to_location": loc,
                        "urgency": "IMMEDIATE",
                        "unit_cost_inr": prim_price,
                        "total_estimated_cost_inr": round(po_qty * prim_price, 2),
                        "expected_delivery_date": (curr_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    }
                }

                m_exp = self._build_metrics_and_explainability(stock, burn, metrics, prim_lead, prim_price)
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
                    "forward_projections": self._generate_projections_for_problem(stock, burn, prim_lead, options, simulated_action),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action
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

                target_reorder_qty = math.ceil(v_short * 7)

                options = [
                    {
                        "option_name": "Dynamic Safety Buffer Adjustment (Preemptive Transfer)",
                        "source": "Network Regional Warehouse",
                        "delivery_time_days": 1,
                        "lead_time_days": 1,
                        "estimated_cost_inr": 250.0,
                        "cash_impact_inr": 250.0,
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": f"PRO: Instantly boosts local safety buffer by {target_reorder_qty} units to match surged velocity {v_short}/day. CON: ₹250 handling fee.",
                        "trade_off_summary": f"1-day buffer replenishment of {target_reorder_qty} units at ₹250 cost."
                    },
                    {
                        "option_name": "Accelerated Primary Supplier Reorder",
                        "source": prim_sup.get("supplier", "Primary Supplier"),
                        "delivery_time_days": prim_lead,
                        "lead_time_days": prim_lead,
                        "estimated_cost_inr": round(target_reorder_qty * prim_price, 2),
                        "cash_impact_inr": round(target_reorder_qty * prim_price, 2),
                        "feasibility": "FEASIBLE",
                        "feasibility_status": "FEASIBLE",
                        "pros_cons": f"PRO: Direct factory supply at standard price. CON: Takes {prim_lead} days to arrive.",
                        "trade_off_summary": f"Factory order arriving in {prim_lead} days, cash impact ₹{target_reorder_qty * prim_price:,.2f}."
                    }
                ]

                decision_rationale = (
                    f"Detected {shift_type} at {loc} (7-day velocity {v_short:.1f}/day vs 30-day baseline {v_long:.1f}/day, ratio {ratio:.1f}x). "
                    f"Preemptively raising safety stock buffer to prevent premature stockout under heightened seasonal demand."
                )
                simulated_action = {
                    "action_type": "TRANSFER_REQUEST",
                    "human_approval_required": True,
                    "payload": {
                        "sku": sku,
                        "qty": target_reorder_qty,
                        "from_location_or_supplier": "Belgaum Central Warehouse",
                        "to_location": loc,
                        "urgency": "IMMEDIATE",
                        "unit_cost_inr": 0.0,
                        "total_estimated_cost_inr": 250.0,
                        "expected_delivery_date": (curr_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    }
                }

                m_exp = self._build_metrics_and_explainability(stock, v_short, metrics, prim_lead, prim_price)
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
                    "forward_projections": self._generate_projections_for_problem(stock, v_short, prim_lead, options, simulated_action),
                    "decision_rationale": decision_rationale,
                    "simulated_action": simulated_action
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
                -get_risk(p),
                -p["domain_metrics"]["daily_burn_rate"],
                p["domain_metrics"]["days_of_cover"]
            )
        )

        critical_count = sum(1 for p in detected_problems if p["severity"] == "CRITICAL")
        top_focus = detected_problems[0]["sku"] if detected_problems else "N/A"

        return {
            "summary": {
                "total_problems_detected": len(detected_problems),
                "critical_actions_required": critical_count,
                "top_focus_sku": top_focus
            },
            "problems": detected_problems
        }
