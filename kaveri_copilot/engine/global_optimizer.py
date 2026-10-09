"""
Kaveri Spares & Hydraulics — Global Multi-Echelon Transfer Optimizer
Solves joint lateral replenishment across all network nodes using PuLP (Integer Linear Programming).

Ensures:
1. No donor location is over-promised across multiple concurrent stockout incidents.
2. Capital Trap surplus stock explicitly feeds Stockout incidents across the network.
3. Fallback to greedy heuristic if solver fails or PuLP is unavailable.
4. Outputs comparison between Global LP and Greedy Allocation.
"""

import os
import sys
import logging
from typing import Dict, Any, List, Optional, Tuple

# Ensure base dir is accessible
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.config import (
    DEFAULT_TRANSFER_HANDLING_COST,
    DEFAULT_TRANSFER_UNIT_FREIGHT,
    DEFAULT_MARGIN_RATE
)

logger = logging.getLogger(__name__)


def solve_global_transfer_network(
    demands: List[Dict[str, Any]],
    donors: List[Dict[str, Any]],
    blocked_routes: Optional[List[Any]] = None,
    handling_cost: float = DEFAULT_TRANSFER_HANDLING_COST,
    unit_freight: float = DEFAULT_TRANSFER_UNIT_FREIGHT
) -> Dict[str, Any]:
    """
    Jointly optimizes lateral inventory rebalancing across the multi-echelon network.

    Parameters:
    - demands: List of dicts, each with:
        {"demand_id": str, "sku": str, "location": str, "needed_qty": int,
         "margin_loss_per_unit": float, "supplier_price": float}
    - donors: List of dicts, each with:
        {"donor_id": str, "sku": str, "location": str, "surplus_qty": int,
         "is_capital_trap": bool, "cover_days": float}
    - blocked_routes: List of dicts or tuples indicating blocked (from, to, sku) pairs.
    """
    if not demands:
        return {
            "status": "NO_DEMAND",
            "solver": "NONE",
            "transfers": [],
            "external_purchases": [],
            "unmet_demands": [],
            "total_cost_global": 0.0,
            "total_cost_greedy": 0.0,
            "cost_savings_vs_greedy": 0.0,
            "allocations_by_demand_id": {}
        }

    # Helper to check route block
    def is_blocked(from_loc: str, to_loc: str, sku: str) -> bool:
        if not blocked_routes:
            return False
        for r in blocked_routes:
            if isinstance(r, dict):
                rf = r.get("from")
                rt = r.get("to")
                rsku = r.get("sku")
                if (rf in (None, "*", from_loc)) and (rt in (None, "*", to_loc)) and (rsku in (None, "*", sku)):
                    return True
            elif isinstance(r, (tuple, list)) and len(r) >= 2:
                if r[0] == from_loc and r[1] == to_loc:
                    return True
        return False

    # -------------------------------------------------------------
    # 1. GREEDY HEURISTIC PATH (ALWAYS COMPUTED FOR COMPARISON & FALLBACK)
    # -------------------------------------------------------------
    greedy_donor_surplus = {d["donor_id"]: int(d["surplus_qty"]) for d in donors}
    greedy_transfers = []
    greedy_purchases = []
    greedy_unmet = []
    greedy_cost = 0.0

    # Sort demands by urgency (highest margin loss per unit first)
    sorted_demands = sorted(demands, key=lambda d: d.get("margin_loss_per_unit", 1000.0), reverse=True)

    for dem in sorted_demands:
        dem_id = dem["demand_id"]
        sku = dem["sku"]
        to_loc = dem["location"]
        rem_needed = int(dem["needed_qty"])
        sup_price = float(dem.get("supplier_price", 1000.0))
        margin_loss = float(dem.get("margin_loss_per_unit", sup_price * DEFAULT_MARGIN_RATE))

        # Look for eligible donors for this SKU (prefer Capital Trap first)
        eligible_donors = [
            d for d in donors
            if d["sku"] == sku and d["location"] != to_loc and not is_blocked(d["location"], to_loc, sku)
        ]
        eligible_donors.sort(key=lambda d: (1 if d.get("is_capital_trap") else 0, d.get("cover_days", 0.0)), reverse=True)

        dem_transfers = []
        for d in eligible_donors:
            if rem_needed <= 0:
                break
            d_id = d["donor_id"]
            avail = greedy_donor_surplus.get(d_id, 0)
            if avail > 0:
                alloc = min(avail, rem_needed)
                greedy_donor_surplus[d_id] -= alloc
                rem_needed -= alloc
                t_cost = handling_cost + (alloc * unit_freight)
                greedy_transfers.append({
                    "demand_id": dem_id,
                    "from_location": d["location"],
                    "to_location": to_loc,
                    "sku": sku,
                    "qty": alloc,
                    "is_capital_trap": d.get("is_capital_trap", False),
                    "cost_inr": round(t_cost, 2)
                })
                greedy_cost += t_cost

        if rem_needed > 0:
            # Procure from external supplier
            po_cost = rem_needed * sup_price
            greedy_purchases.append({
                "demand_id": dem_id,
                "location": to_loc,
                "sku": sku,
                "qty": rem_needed,
                "cost_inr": round(po_cost, 2)
            })
            greedy_cost += po_cost

    # -------------------------------------------------------------
    # 2. GLOBAL MIP SOLVER VIA SCIPY HIGHS
    # -------------------------------------------------------------
    mip_success = False
    global_transfers = []
    global_purchases = []
    global_unmet = []
    global_cost = 0.0

    try:
        from scipy.optimize import linprog

        # Map donors and demands
        donor_lookup = {d["donor_id"]: d for d in donors}
        demand_lookup = {dem["demand_id"]: dem for dem in demands}

        # Build list of decision variables
        # Variable types:
        # 1. ("transfer", donor_id, demand_id)
        # 2. ("po", demand_id)
        # 3. ("unmet", demand_id)
        var_defs = []
        c_list = []
        bounds_list = []

        # Transfer variables
        transfer_var_indices = {}
        for dem in demands:
            dem_id = dem["demand_id"]
            sku = dem["sku"]
            to_loc = dem["location"]
            needed = int(dem["needed_qty"])

            for d in donors:
                if d["sku"] == sku and d["location"] != to_loc and not is_blocked(d["location"], to_loc, sku):
                    d_id = d["donor_id"]
                    surplus = int(d["surplus_qty"])
                    idx = len(var_defs)
                    var_defs.append(("transfer", d_id, dem_id))
                    transfer_var_indices[(d_id, dem_id)] = idx

                    # Effective transfer cost: unit freight + amortized handling
                    # Capital trap surplus receives 20% discount incentive to liberate trapped cash
                    base_unit_cost = unit_freight + (handling_cost / max(1, needed))
                    eff_cost = base_unit_cost * 0.8 if d.get("is_capital_trap") else base_unit_cost
                    c_list.append(eff_cost)
                    bounds_list.append((0, min(surplus, needed)))

        # PO and unmet variables for each demand
        po_var_indices = {}
        unmet_var_indices = {}
        for dem in demands:
            dem_id = dem["demand_id"]
            needed = int(dem["needed_qty"])
            sup_price = float(dem.get("supplier_price", 1000.0))
            margin_loss = float(dem.get("margin_loss_per_unit", sup_price * DEFAULT_MARGIN_RATE))

            idx_po = len(var_defs)
            var_defs.append(("po", dem_id))
            po_var_indices[dem_id] = idx_po
            c_list.append(sup_price)
            bounds_list.append((0, needed))

            idx_unmet = len(var_defs)
            var_defs.append(("unmet", dem_id))
            unmet_var_indices[dem_id] = idx_unmet
            c_list.append(margin_loss * 2.0)
            bounds_list.append((0, needed))

        num_vars = len(var_defs)

        # Equality Constraints: sum(transfers) + po + unmet == needed for each demand
        A_eq = []
        b_eq = []
        for dem in demands:
            dem_id = dem["demand_id"]
            needed = int(dem["needed_qty"])
            row = [0.0] * num_vars

            for d in donors:
                d_id = d["donor_id"]
                if (d_id, dem_id) in transfer_var_indices:
                    row[transfer_var_indices[(d_id, dem_id)]] = 1.0

            row[po_var_indices[dem_id]] = 1.0
            row[unmet_var_indices[dem_id]] = 1.0

            A_eq.append(row)
            b_eq.append(float(needed))

        # Inequality Constraints: sum(transfers from donor) <= donor surplus
        A_ub = []
        b_ub = []
        for d in donors:
            d_id = d["donor_id"]
            surplus = float(d["surplus_qty"])
            row = [0.0] * num_vars
            has_transfer = False
            for dem in demands:
                dem_id = dem["demand_id"]
                if (d_id, dem_id) in transfer_var_indices:
                    row[transfer_var_indices[(d_id, dem_id)]] = 1.0
                    has_transfer = True
            if has_transfer:
                A_ub.append(row)
                b_ub.append(surplus)

        integrality = [1] * num_vars

        res = linprog(
            c=c_list,
            A_ub=A_ub if A_ub else None,
            b_ub=b_ub if b_ub else None,
            A_eq=A_eq if A_eq else None,
            b_eq=b_eq if b_eq else None,
            bounds=bounds_list,
            integrality=integrality
        )

        if res.success:
            mip_success = True
            for (d_id, dem_id), idx in transfer_var_indices.items():
                qty = int(round(res.x[idx]))
                if qty > 0:
                    d = donor_lookup[d_id]
                    dem = demand_lookup[dem_id]
                    t_cost = handling_cost + (qty * unit_freight)
                    global_transfers.append({
                        "demand_id": dem_id,
                        "from_location": d["location"],
                        "to_location": dem["location"],
                        "sku": dem["sku"],
                        "qty": qty,
                        "is_capital_trap": d.get("is_capital_trap", False),
                        "cost_inr": round(t_cost, 2)
                    })
                    global_cost += t_cost

            for dem_id, idx in po_var_indices.items():
                qty = int(round(res.x[idx]))
                if qty > 0:
                    dem = demand_lookup[dem_id]
                    po_cost = qty * float(dem.get("supplier_price", 1000.0))
                    global_purchases.append({
                        "demand_id": dem_id,
                        "location": dem["location"],
                        "sku": dem["sku"],
                        "qty": qty,
                        "cost_inr": round(po_cost, 2)
                    })
                    global_cost += po_cost

            for dem_id, idx in unmet_var_indices.items():
                qty = int(round(res.x[idx]))
                if qty > 0:
                    dem = demand_lookup[dem_id]
                    global_unmet.append({
                        "demand_id": dem_id,
                        "location": dem["location"],
                        "sku": dem["sku"],
                        "qty": qty
                    })

    except Exception as exc:
        logger.warning(f"MIP solver failed: {exc}. Falling back to greedy.")
        mip_success = False

    # -------------------------------------------------------------
    # 3. BUILD COMPARATIVE RESULT
    # -------------------------------------------------------------
    if mip_success:
        chosen_transfers = global_transfers
        chosen_purchases = global_purchases
        chosen_unmet = global_unmet
        chosen_cost = global_cost
        solver_name = "GLOBAL_MIP_OPTIMAL"
    else:
        chosen_transfers = greedy_transfers
        chosen_purchases = greedy_purchases
        chosen_unmet = greedy_unmet
        chosen_cost = greedy_cost
        solver_name = "GREEDY_FALLBACK"

    # Group allocations by demand_id for easy lookup
    alloc_map = {}
    for t in chosen_transfers:
        alloc_map.setdefault(t["demand_id"], {"transfers": [], "purchases": []})
        alloc_map[t["demand_id"]]["transfers"].append(t)
    for p in chosen_purchases:
        alloc_map.setdefault(p["demand_id"], {"transfers": [], "purchases": []})
        alloc_map[p["demand_id"]]["purchases"].append(p)

    return {
        "status": "OPTIMAL" if mip_success else "FALLBACK",
        "solver": solver_name,
        "transfers": chosen_transfers,
        "external_purchases": chosen_purchases,
        "unmet_demands": chosen_unmet,
        "total_cost_global": round(chosen_cost, 2),
        "total_cost_greedy": round(greedy_cost, 2),
        "cost_savings_vs_greedy": round(max(0.0, greedy_cost - chosen_cost), 2),
        "allocations_by_demand_id": alloc_map
    }
