"""
Kaveri Spares & Hydraulics - Supply Chain Copilot Dashboard
Interactive Streamlit Cockpit for Ramesh Kulkarni (Head of Purchasing)
Provides Morning Feed, Mathematical Explainability, Dynamic Human Override Counter-Proposals,
Chaos / Judge Injection, and Supplier Friction Auditing.
"""

import os
import sys
import json
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# Setup paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import importlib
import engine.domain_math
import engine.decision_agent
importlib.reload(engine.domain_math)
importlib.reload(engine.decision_agent)

from engine.decision_agent import DecisionEngine
from engine.domain_math import validate_and_recalculate_transfer, generate_14day_projections
from engine.mock_data_gen import seed_all_data

DATA_DIR = os.path.join(BASE_DIR, "data")
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.json")

# Streamlit Page Config
st.set_page_config(
    page_title="Kaveri Spares Copilot | Cypher 2026",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    .badge-critical {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.75rem;
        border: 1px solid #f87171;
    }
    
    .badge-high {
        background-color: #ffedd5;
        color: #9a3412;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.75rem;
        border: 1px solid #fb923c;
    }
    
    .badge-medium {
        background-color: #fef9c3;
        color: #854d0e;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.75rem;
        border: 1px solid #facc15;
    }

    .badge-action {
        background-color: #dbeafe;
        color: #1e40af;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.8rem;
        border: 1px solid #93c5fd;
    }

    .badge-friction {
        background-color: #fef3c7;
        color: #92400e;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.75rem;
        border: 1px solid #fcd34d;
    }

    .badge-surge {
        background-color: #fef2f2;
        color: #b91c1c;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.75rem;
        border: 1px solid #f87171;
    }

    .badge-stable {
        background-color: #f0fdf4;
        color: #15803d;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.75rem;
        border: 1px solid #86efac;
    }

    .badge-drop {
        background-color: #fefce8;
        color: #a16207;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.75rem;
        border: 1px solid #fde047;
    }
    
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        text-align: center;
    }
    .metric-label {
        font-size: 0.75rem;
        color: #64748b;
        text-transform: uppercase;
        font-weight: 600;
    }
    .metric-val {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0f172a;
    }
    
    .action-box {
        background-color: #f0fdf4;
        border: 1.5px solid #86efac;
        border-radius: 10px;
        padding: 1rem 1.25rem;
        margin-top: 0.75rem;
    }

    .scorecard-card {
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        text-align: center;
    }
    .scorecard-label {
        font-size: 0.75rem;
        color: #475569;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    .scorecard-val {
        font-size: 1.25rem;
        font-weight: 700;
        color: #0f172a;
    }
    .scorecard-sub {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 0.2rem;
    }

    .telemetry-card {
        background-color: #0f172a !important;
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-left: 6px solid #3b82f6 !important;
        border-radius: 8px !important;
        padding: 1.1rem 1.35rem !important;
        margin-bottom: 1.25rem !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2) !important;
        font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace !important;
    }
    .telemetry-card, .telemetry-card * {
        font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace !important;
    }
    .telemetry-header {
        color: #93c5fd !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        margin-bottom: 0.65rem !important;
        letter-spacing: 0.01em !important;
    }
    .telemetry-line {
        color: #f1f5f9 !important;
        font-size: 0.88rem !important;
        line-height: 1.7 !important;
        margin-bottom: 0.35rem !important;
    }
    .telemetry-line b {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    .telemetry-tag-cyan {
        color: #38bdf8 !important;
        font-weight: 600 !important;
    }
    .telemetry-tag-yellow {
        color: #facc15 !important;
        font-weight: 600 !important;
    }
    .telemetry-tag-red {
        color: #f87171 !important;
        font-weight: 700 !important;
    }
    .telemetry-tag-blue {
        color: #93c5fd !important;
        font-weight: 600 !important;
    }
    .telemetry-tag-green {
        color: #4ade80 !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)


def load_audit():
    if not os.path.exists(AUDIT_LOG_FILE):
        return []
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_audit(logs):
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)


def apply_action_approval(problem_id, action_type, payload):
    inv_file = os.path.join(DATA_DIR, "inventory.json")
    po_file = os.path.join(DATA_DIR, "purchase_orders.json")

    with open(inv_file, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    with open(po_file, "r", encoding="utf-8") as f:
        pos = json.load(f)

    sku = payload["sku"]
    qty = payload["qty"]
    from_src = payload["from_location_or_supplier"]
    to_loc = payload["to_location"]

    if action_type == "TRANSFER_REQUEST":
        for item in inventory:
            if item["sku"] == sku and item["location"] == from_src:
                item["stock"] = max(0, item["stock"] - qty)
            elif item["sku"] == sku and item["location"] == to_loc:
                item["stock"] += qty
        with open(inv_file, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2)

    elif action_type == "PURCHASE_ORDER":
        po_id = f"PO-{datetime.now().strftime('%m%d%H%M')}"
        pos.append({
            "po": po_id,
            "supplier": from_src,
            "sku": sku,
            "location": to_loc,
            "qty": qty,
            "expected_date": payload["expected_delivery_date"],
            "status": "ORDERED"
        })
        with open(po_file, "w", encoding="utf-8") as f:
            json.dump(pos, f, indent=2)

    elif action_type == "SUPPLIER_EXPEDITE_NOTICE":
        for po in pos:
            if po["sku"] == sku and po["supplier"] == from_src and po.get("status") != "DELIVERED":
                po["status"] = "EXPEDITED"
        with open(po_file, "w", encoding="utf-8") as f:
            json.dump(pos, f, indent=2)

    # Append audit log
    logs = load_audit()
    logs.insert(0, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "problem_id": problem_id,
        "action_type": action_type,
        "status": "APPROVED",
        "approved_by": "Ramesh Kulkarni (Head of Purchasing)",
        "sku": sku,
        "qty": qty,
        "from": from_src,
        "to": to_loc,
        "cost_inr": payload.get("total_estimated_cost_inr", 0.0)
    })
    save_audit(logs)


def apply_action_rejection(problem_id):
    logs = load_audit()
    logs.insert(0, {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "problem_id": problem_id,
        "action_type": "REJECTION",
        "status": "REJECTED",
        "approved_by": "Ramesh Kulkarni (Head of Purchasing)",
        "sku": "-",
        "qty": 0,
        "from": "-",
        "to": "-",
        "cost_inr": 0.0
    })
    save_audit(logs)


# Session state for Chaos events
if "chaos_events" not in st.session_state:
    st.session_state.chaos_events = []

# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    st.markdown("### ⚙️ Operating Controls")
    current_date = st.date_input("Simulation Date", value=datetime(2026, 10, 9)).strftime("%Y-%m-%d")
    st.markdown("---")
    st.markdown("**User Persona:**")
    st.markdown("🧑‍💼 **Ramesh Kulkarni**  \n*Head of Purchasing*")
    st.markdown("**Operations Network:**")
    st.caption("🏪 6 Retail Stores: Gokak, Belgaum, Dharwad, Hubli, Bagalkot, Nippani")
    st.caption("🏢 2 Central Warehouses: Belgaum Central, Hubli Regional")
    st.markdown("---")

    # Chaos Simulator Section
    st.markdown("### ⚡ Judge / Chaos Test Suite")
    st.caption("Inject live operational shocks to test autonomous resilience:")

    chaos_options = [
        "-- Select Pre-Built Scenario --",
        "Inject 3x Surge at Gokak",
        "Block Belgaum Transfer Route",
        "Increase Supplier Lead Time by 5 Days"
    ]
    selected_scenario = st.selectbox("Pre-Built Chaos Scenario:", chaos_options, key="chaos_dropdown")

    if st.button("⚡ Inject Selected Scenario", use_container_width=True, type="primary"):
        if selected_scenario == "Inject 3x Surge at Gokak":
            st.session_state.chaos_events.append({
                "scenario": "DEMAND_SPIKE",
                "event_type": "DEMAND_SURGE",
                "sku": "FILTER-HYD-01",
                "location": "Gokak",
                "multiplier_or_days": 3.0
            })
            st.toast("⚡ Injected: 3x demand surge at Gokak!")
            st.rerun()
        elif selected_scenario == "Block Belgaum Transfer Route":
            st.session_state.chaos_events.append({
                "scenario": "TRANSFER_ROADBLOCK",
                "event_type": "TRANSFER_BLOCKED",
                "sku": "FILTER-HYD-01",
                "from_location": "Belgaum",
                "to_location": "Gokak",
                "multiplier_or_days": 1.0
            })
            st.toast("⚡ Injected: Belgaum-to-Gokak road blocked!")
            st.rerun()
        elif selected_scenario == "Increase Supplier Lead Time by 5 Days":
            st.session_state.chaos_events.append({
                "scenario": "SUPPLIER_HIKE",
                "event_type": "SUPPLIER_DELAY",
                "sku": "FILTER-HYD-01",
                "location": "Gokak",
                "multiplier_or_days": 5.0
            })
            st.toast("⚡ Injected: Supplier lead time +5 days!")
            st.rerun()
        else:
            st.warning("Please choose a valid scenario from the dropdown.")

    st.markdown("#### Quick Action Injectors:")
    q_col1, q_col2 = st.columns(2)
    with q_col1:
        if st.button("🌪️ 3x Surge", use_container_width=True):
            st.session_state.chaos_events.append({
                "scenario": "DEMAND_SPIKE",
                "event_type": "DEMAND_SURGE",
                "sku": "FILTER-HYD-01",
                "location": "Gokak",
                "multiplier_or_days": 3.0
            })
            st.toast("Injected 3x Surge!")
            st.rerun()
    with q_col2:
        if st.button("🚧 Block Route", use_container_width=True):
            st.session_state.chaos_events.append({
                "scenario": "TRANSFER_ROADBLOCK",
                "event_type": "TRANSFER_BLOCKED",
                "sku": "FILTER-HYD-01",
                "from_location": "Belgaum",
                "to_location": "Gokak",
                "multiplier_or_days": 1.0
            })
            st.toast("Injected Route Block!")
            st.rerun()

    if st.session_state.chaos_events:
        st.warning(f"⚠️ {len(st.session_state.chaos_events)} Chaos event(s) currently active in runtime.")
        if st.button("🧹 Clear Injected Chaos", use_container_width=True):
            st.session_state.chaos_events = []
            st.success("Chaos events cleared.")
            st.rerun()

    st.markdown("---")
    if st.button("🔄 Reset to Benchmark Data", use_container_width=True):
        st.session_state.chaos_events = []
        seed_all_data(DATA_DIR)
        if os.path.exists(AUDIT_LOG_FILE):
            os.remove(AUDIT_LOG_FILE)
        st.success("Benchmark state restored!")
        st.rerun()

# Run Engine with Chaos Events
engine = DecisionEngine(
    data_dir=DATA_DIR,
    current_date=current_date,
    chaos_events=st.session_state.chaos_events
)
briefing = engine.run_agentic_pipeline()
audit_log = load_audit()
approved_problem_ids = {a["problem_id"] for a in audit_log}

# Load Raw Data for overrides
with open(os.path.join(DATA_DIR, "inventory.json"), "r", encoding="utf-8") as f:
    raw_inventory = json.load(f)
with open(os.path.join(DATA_DIR, "sales.json"), "r", encoding="utf-8") as f:
    raw_sales = json.load(f)

# ==============================================================================
# HEADER
# ==============================================================================
st.markdown("""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h1 style="margin: 0; font-size: 1.8rem; font-weight: 700;">Kaveri Spares & Hydraulics</h1>
            <p style="margin: 0.25rem 0 0 0; color: #94a3b8; font-size: 1rem;">
                Autonomous Supply Chain Copilot & Purchasing Colleague for Ramesh Kulkarni
            </p>
        </div>
        <div style="text-align: right;">
            <span style="background: rgba(255,255,255,0.15); padding: 0.4rem 0.8rem; border-radius: 6px; font-size: 0.85rem; font-weight: 600;">
                Cypher 2026 • Challenge 01
            </span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if st.session_state.chaos_events:
    st.error(f"🚨 **CHAOS INJECTION ACTIVE:** System is running under {len(st.session_state.chaos_events)} live operational shock(s). Observe the agent automatically adapting its options!")

# KPI RIBBON
summary = briefing["summary"]
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Operational Issues", summary["total_problems_detected"], delta="Across 8 Nodes")
with col2:
    st.metric("Critical Stockouts", summary["critical_actions_required"], delta="Immediate Action Needed", delta_color="inverse")
with col3:
    st.metric("Top Attention SKU", summary["top_focus_sku"], delta="Hydraulic Filtration")
with col4:
    pending_count = sum(1 for p in briefing["problems"] if p["problem_id"] not in approved_problem_ids)
    st.metric("Pending Human Gate Approvals", pending_count, delta=f"{len(audit_log)} Decisions Logged")

# ==============================================================================
# MAIN NAVIGATION TABS
# ==============================================================================
tab_feed, tab_inventory, tab_suppliers, tab_audit = st.tabs([
    "🚨 Morning Action Feed & Approval Gate",
    "🏭 Multi-Echelon Network Inventory",
    "🔍 Supplier Friction & Reliability Audit",
    "📜 Immutable Audit Trail"
])

# ------------------------------------------------------------------------------
# TAB 1: MORNING FEED
# ------------------------------------------------------------------------------
with tab_feed:
    st.subheader("Today's Prioritized Purchasing Queue")
    st.caption("5 Problem Categories: Imminent Stockouts, Capital Traps, Overdue POs, Demand Volatility, and Supplier Infeasibility.")

    # Filter by category/severity
    filter_col1, filter_col2 = st.columns([1, 2])
    with filter_col1:
        sev_filter = st.selectbox("Filter Severity:", ["All", "CRITICAL", "HIGH", "MEDIUM"])

    filtered_problems = briefing["problems"]
    if sev_filter != "All":
        filtered_problems = [p for p in filtered_problems if p["severity"] == sev_filter]

    st.info("💡 **Benchmark Scenario Focus:** SKU `FILTER-HYD-01` at **Gokak Store** (2.0 days cover vs 7-day supplier lead time). Belgaum Store holds 40 units (80 days cover). Use the Counter-Proposal box below to test dynamic human override.")

    for p in filtered_problems:
        pid = p["problem_id"]
        is_handled = pid in approved_problem_ids
        cat_code = p.get("category_code", "CATEGORY_A")

        badge_class = "badge-critical" if p["severity"] == "CRITICAL" else ("badge-high" if p["severity"] == "HIGH" else "badge-medium")
        card_border = "#f87171" if p["severity"] == "CRITICAL" else "#cbd5e1"
        status_banner = "✅ ALREADY EXECUTED" if is_handled else "⚡ AWAITING RAMESH KULKARNI APPROVAL"

        # Check for supplier friction
        has_friction = any("INFEASIBLE_MOQ" in o.get("feasibility_status", "") for o in p["evaluated_options"])

        with st.container():
            st.markdown(f"""
            <div style="border: 1px solid {card_border}; border-radius: 10px; padding: 1.25rem; margin-bottom: 1.25rem; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <div>
                        <span class="{badge_class}">{p['severity']}</span>
                        <span style="background: #e0f2fe; color: #0369a1; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; margin-left: 0.3rem;">{cat_code}</span>
                        <span style="font-weight: 700; font-size: 1.1rem; margin-left: 0.5rem;">{p['sku_name']} ({p['sku']})</span>
                        <span style="color: #64748b; margin-left: 0.5rem;">📍 <b>{p['location']}</b></span>
                    </div>
                    <div>
                        <span style="font-size: 0.8rem; font-weight: 600; color: {'#16a34a' if is_handled else '#d97706'};">
                            {status_banner}
                        </span>
                    </div>
                </div>
                <p style="color: #334155; margin: 0.4rem 0 0.8rem 0; font-size: 0.95rem;">
                    <b>Diagnosis:</b> {p['diagnosis']}
                </p>
            </div>
            """, unsafe_allow_html=True)

            # Adaptive velocity metrics & domain metrics
            m = p["domain_metrics"]
            ad = p.get("adaptive_velocity", m.get("adaptive_velocity", {}))
            v_base = ad.get("v_baseline", m.get("daily_burn_rate", 0.0))
            v_rec = ad.get("v_recent", m.get("daily_burn_rate", 0.0))
            trend_factor = ad.get("trend_factor", 1.0)
            trend_label = ad.get("trend_label", "STABLE")

            trend_badge_class = "badge-surge" if trend_label == "ACCELERATING" else ("badge-drop" if trend_label == "DECELERATING" else "badge-stable")
            trend_display = f"{trend_label} ({trend_factor:.1f}x)"

            vc1, vc2, vc3, vc4, vc5, vc6 = st.columns(6)
            with vc1:
                st.markdown(f"""<div class="metric-card"><div class="metric-label">v_baseline (30d)</div><div class="metric-val">{v_base:.2f}/day</div></div>""", unsafe_allow_html=True)
            with vc2:
                st.markdown(f"""<div class="metric-card"><div class="metric-label">v_recent (7d)</div><div class="metric-val">{v_rec:.2f}/day</div></div>""", unsafe_allow_html=True)
            with vc3:
                st.markdown(f"""<div class="metric-card"><div class="metric-label">Trend Factor</div><div class="metric-val"><span class="{trend_badge_class}">{trend_display}</span></div></div>""", unsafe_allow_html=True)
            with vc4:
                st.markdown(f"""<div class="metric-card"><div class="metric-label">Current Stock</div><div class="metric-val">{m['current_stock']} units</div></div>""", unsafe_allow_html=True)
            with vc5:
                cover_color = "#dc2626" if m['days_of_cover'] <= 3.0 else ("#d97706" if m['days_of_cover'] <= 7.0 else "#16a34a")
                st.markdown(f"""<div class="metric-card"><div class="metric-label">Days of Cover (D)</div><div class="metric-val" style="color: {cover_color};">{m['days_of_cover']} days</div></div>""", unsafe_allow_html=True)
            with vc6:
                gap_color = "#dc2626" if m['stockout_gap_days'] > 0 else "#16a34a"
                st.markdown(f"""<div class="metric-card"><div class="metric-label">Stockout Gap (Δ)</div><div class="metric-val" style="color: {gap_color};">{m['stockout_gap_days']} days</div></div>""", unsafe_allow_html=True)

            # Option Evaluation Table & Explainability
            with st.expander("📊 View Side-by-Side Trade-off Table & Mathematical Explainability", expanded=(p["severity"] == "CRITICAL" and not is_handled)):
                if "math_explainability" in p:
                    me = p["math_explainability"]
                    st.markdown(f"""
<div class="telemetry-card">
    <div class="telemetry-header">📐 Deterministic Velocity Math &amp; Telemetry:</div>
    <div class="telemetry-line">• <b>Velocity:</b> <span class="telemetry-tag-cyan">{me.get('formula_velocity', '')}</span></div>
    <div class="telemetry-line">• <b>Days of Cover:</b> <span class="telemetry-tag-yellow">{me.get('formula_cover', '')}</span></div>
    <div class="telemetry-line">• <b>Deficit Gap:</b> <span class="telemetry-tag-red">{me.get('formula_gap', '')}</span></div>
    <div class="telemetry-line">• <b>Commercial Risk Exposure:</b> Lead Time T = <span class="telemetry-tag-blue">{me.get('T', 7)}d</span> | Margin = <span class="telemetry-tag-green">₹{me.get('unit_margin_inr', 0):,.2f}/unit</span> | Potential Lost Revenue = <span class="telemetry-tag-red">₹{me.get('projected_lost_revenue_inr', 0):,.2f}</span></div>
</div>
""", unsafe_allow_html=True)

                # Commercial Impact Scorecard
                m_gap = m.get("stockout_gap_days", 0.0)
                ad_v = p.get("adaptive_velocity", {}).get("v_predicted", m.get("daily_burn_rate", 1.0))
                lost_units = round(m_gap * ad_v, 1) if m_gap > 0 else 0.0
                has_transfer = any("Internal" in o["option_name"] and o.get("feasibility_status") == "FEASIBLE" for o in p["evaluated_options"])

                st.markdown("##### 💳 Commercial Impact Scorecard (Options Trade-off Matrix)")
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1:
                    net_cost_str = "₹250.00" if has_transfer else (f"₹{p['simulated_action']['payload'].get('total_estimated_cost_inr', 0):,.2f}")
                    st.markdown(f"""
                    <div class="scorecard-card">
                        <div class="scorecard-label">Net Direct Cost</div>
                        <div class="scorecard-val" style="color: #16a34a;">{net_cost_str}</div>
                        <div class="scorecard-sub">Flat Handling vs Vendor Premium</div>
                    </div>
                    """, unsafe_allow_html=True)
                with sc2:
                    st.markdown(f"""
                    <div class="scorecard-card">
                        <div class="scorecard-label">Lost Units Averted</div>
                        <div class="scorecard-val" style="color: #2563eb;">{lost_units} units</div>
                        <div class="scorecard-sub">Protected vs Inaction Deficit</div>
                    </div>
                    """, unsafe_allow_html=True)
                with sc3:
                    wc_outflow = "₹0.00" if has_transfer else f"₹{p['simulated_action']['payload'].get('total_estimated_cost_inr', 0):,.2f}"
                    st.markdown(f"""
                    <div class="scorecard-card">
                        <div class="scorecard-label">Working Capital Outflow</div>
                        <div class="scorecard-val" style="color: #16a34a;">{wc_outflow}</div>
                        <div class="scorecard-sub">{"Internal Inventory Reallocation" if has_transfer else "New Vendor Capital Outlay"}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with sc4:
                    dt_risk = "0 Days" if has_transfer else (f"{min(3, int(m_gap))} Days" if m_gap > 0 else "0 Days")
                    st.markdown(f"""
                    <div class="scorecard-card">
                        <div class="scorecard-label">Downtime Risk</div>
                        <div class="scorecard-val" style="color: {'#16a34a' if dt_risk == '0 Days' else '#dc2626'};">{dt_risk}</div>
                        <div class="scorecard-sub">Eliminates {m_gap}d Stockout Gap</div>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<div style='margin-bottom: 0.75rem;'></div>", unsafe_allow_html=True)

                # Interactive Plotly Forward Trajectory Graph
                fp = p.get("forward_projections")
                if fp and "days" in fp:
                    st.markdown("##### 📈 14-Day Forward Visual Inventory Trajectories")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=fp["days"],
                        y=fp["status_quo"],
                        mode="lines+markers",
                        name="Option 3: Status Quo (Wait for Primary Vendor PO)",
                        line=dict(color="#ef4444", width=3, dash="dot"),
                        marker=dict(size=6)
                    ))
                    fig.add_trace(go.Scatter(
                        x=fp["days"],
                        y=fp["expedited"],
                        mode="lines+markers",
                        name="Option 2: Expedited Vendor PO (Day 3 Arrival)",
                        line=dict(color="#f59e0b", width=3, dash="dash"),
                        marker=dict(size=6)
                    ))
                    fig.add_trace(go.Scatter(
                        x=fp["days"],
                        y=fp["transfer"],
                        mode="lines+markers",
                        name="Option 1: Inter-Store Transfer (Day 1 Arrival)",
                        line=dict(color="#2563eb", width=3.5),
                        marker=dict(size=7)
                    ))
                    fig.add_hline(
                        y=0,
                        line_dash="dash",
                        line_color="#dc2626",
                        line_width=2,
                        annotation_text="⚠️ Stockout Hazard Line (Zero Stock)",
                        annotation_position="bottom right",
                        annotation_font_color="#dc2626"
                    )
                    fig.update_layout(
                        title=dict(
                            text=f"Projected Inventory Levels (Next 14 Days): {p['sku_name']} @ {p['location']}",
                            font=dict(size=13, color="#1e293b")
                        ),
                        xaxis=dict(title="Days Ahead", dtick=1, gridcolor="#f1f5f9"),
                        yaxis=dict(title="Projected Stock (Units)", gridcolor="#f1f5f9"),
                        hovermode="x unified",
                        height=340,
                        margin=dict(l=40, r=40, t=50, b=40),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        plot_bgcolor="white",
                        paper_bgcolor="white"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                opt_data = []
                for opt in p["evaluated_options"]:
                    opt_data.append({
                        "Option Name": f"{opt['option_name']} [{opt.get('source', '')}]",
                        "Delivery Time": f"{opt.get('lead_time_days', opt.get('delivery_time_days', 1))} days",
                        "Total Cash Outlay": f"₹{opt.get('cash_impact_inr', opt.get('estimated_cost_inr', 0.0)):,.2f}",
                        "Feasibility": opt.get("feasibility_status", opt.get("feasibility", "FEASIBLE")),
                        "Summary": opt.get("trade_off_summary", opt.get("pros_cons", ""))
                    })
                st.dataframe(pd.DataFrame(opt_data), use_container_width=True, hide_index=True)
                st.markdown(f"**🎯 AI Agent Recommendation Rationale:** {p['decision_rationale']}")

            # Simulated Action Box
            act = p["simulated_action"]
            pay = act["payload"]
            
            st.markdown(f"""
            <div class="action-box">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <div>
                        <span class="badge-action">Simulated Action: {act['action_type']}</span>
                        <span style="margin-left: 0.5rem; font-weight: 600; font-size: 0.9rem; color: #14532d;">
                            Quantity: {pay['qty']} units • Total Estimated Cost: ₹{pay['total_estimated_cost_inr']:,.2f}
                        </span>
                    </div>
                    <div style="font-size: 0.85rem; color: #166534; font-weight: 600;">
                        Expected Arrival: {pay['expected_delivery_date']}
                    </div>
                </div>
                <div style="font-size: 0.9rem; color: #1f2937;">
                    <b>Route:</b> {pay['from_location_or_supplier']} ➔ <b>{pay['to_location']}</b> &nbsp;|&nbsp; 
                    <b>Urgency:</b> {pay['urgency']} &nbsp;|&nbsp; 
                    <b>Human Gate:</b> Simulated Draft (Mandatory Ramesh Kulkarni Approval Required)
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Human-in-the-Loop Counter-Proposal & Approval Gate
            if not is_handled:
                # Dynamic Override Input for Transfers
                if act["action_type"] == "TRANSFER_REQUEST":
                    with st.expander("✏️ Ramesh's Counter-Proposal (Override Proposed Transfer Qty)", expanded=False):
                        override_qty = st.number_input(
                            f"Proposed Transfer Qty for {p['sku']} ({pay['from_location_or_supplier']} ➔ {pay['to_location']}):",
                            min_value=1,
                            max_value=100,
                            value=pay["qty"],
                            key=f"ov_{pid}"
                        )
                        recalc = validate_and_recalculate_transfer(
                            from_loc=pay["from_location_or_supplier"],
                            to_loc=pay["to_location"],
                            sku=pay["sku"],
                            requested_qty=override_qty,
                            inventory=raw_inventory,
                            sales=raw_sales
                        )
                        
                        rc1, rc2, rc3 = st.columns(3)
                        with rc1:
                            st.metric("Recipient Cover Post-Override", f"{recalc['recipient_cover_days']} days", delta=f"{recalc['recipient_cover_days'] - m['days_of_cover']:.1f} days")
                        with rc2:
                            donor_status = "SAFE (>=15d)" if recalc["is_valid"] else "BREACH (<15d)"
                            st.metric("Donor Cover Post-Override", f"{recalc['donor_cover_days']} days", delta=donor_status, delta_color="normal" if recalc["is_valid"] else "inverse")
                        with rc3:
                            st.metric("Revised Handling Outlay", "₹250.00", delta="Zero New Working Capital")

                        # Dynamic Forward Trajectory Recalibration
                        v_burn = ad.get("v_predicted", m.get("daily_burn_rate", 1.0))
                        ov_proj = generate_14day_projections(
                            current_stock=m["current_stock"],
                            daily_burn=v_burn if v_burn > 0 else 1.0,
                            transfer_qty=override_qty,
                            primary_lead_time=m["primary_supplier_lead_time_days"],
                            expedited_lead_time=3,
                            expedited_qty=20,
                            transfer_arrival_day=1
                        )
                        fig_ov = go.Figure()
                        fig_ov.add_trace(go.Scatter(
                            x=ov_proj["days"],
                            y=ov_proj["transfer"],
                            mode="lines+markers",
                            name=f"Counter-Proposal Curve ({override_qty} units)",
                            line=dict(color="#10b981", width=3),
                            marker=dict(size=6)
                        ))
                        if fp and "transfer" in fp:
                            fig_ov.add_trace(go.Scatter(
                                x=fp["days"],
                                y=fp["transfer"],
                                mode="lines+markers",
                                name=f"AI Proposed Baseline ({pay['qty']} units)",
                                line=dict(color="#94a3b8", width=2, dash="dash"),
                                marker=dict(size=5)
                            ))
                        fig_ov.add_hline(y=0, line_dash="dash", line_color="#dc2626", annotation_text="Hazard Line")
                        fig_ov.update_layout(
                            title=f"Dynamic Recalibration: Ramesh's Counter-Proposal ({override_qty} units) vs AI Draft ({pay['qty']} units)",
                            xaxis_title="Days",
                            yaxis_title="Stock (Units)",
                            height=250,
                            margin=dict(l=30, r=30, t=40, b=30),
                            template="plotly_white"
                        )
                        st.plotly_chart(fig_ov, use_container_width=True)
                        
                        if not recalc["is_valid"]:
                            st.error(f"⚠️ {recalc['warning']}")
                        else:
                            st.success(f"✅ Safe transfer! Donor retains {recalc['donor_cover_days']} days buffer (>=15 days required).")
                            if st.button(f"🚀 Approve & Execute Counter-Proposal ({override_qty} units)", key=f"app_ov_{pid}", type="primary"):
                                mod_pay = dict(pay)
                                mod_pay["qty"] = override_qty
                                apply_action_approval(pid, act["action_type"], mod_pay)
                                st.success(f"Counter-proposal approved with {override_qty} units! Inventory updated.")
                                st.rerun()

                btn_col1, btn_col2, btn_col3 = st.columns([2, 1.5, 4])
                with btn_col1:
                    if st.button(f"✅ Approve & Execute Draft", key=f"app_{pid}", type="primary"):
                        apply_action_approval(pid, act["action_type"], pay)
                        st.success(f"Action {act['action_type']} approved by Ramesh Kulkarni! State committed.")
                        st.rerun()
                with btn_col2:
                    if st.button(f"❌ Reject", key=f"rej_{pid}"):
                        apply_action_rejection(pid)
                        st.warning(f"Action for {pid} rejected and recorded.")
                        st.rerun()
            else:
                st.caption(f"Status: Handled in audit log.")

            st.markdown("---")

# ------------------------------------------------------------------------------
# TAB 2: MULTI-ECHELON INVENTORY
# ------------------------------------------------------------------------------
with tab_inventory:
    st.subheader("North Karnataka Multi-Echelon Stock Levels")
    
    with open(os.path.join(DATA_DIR, "inventory.json"), "r", encoding="utf-8") as f:
        inv_raw = json.load(f)
    with open(os.path.join(DATA_DIR, "products.json"), "r", encoding="utf-8") as f:
        prods_raw = json.load(f)
        
    p_map = {p["sku"]: p for p in prods_raw}
    enriched_inv = []
    for row in inv_raw:
        prod = p_map.get(row["sku"], {})
        enriched_inv.append({
            "SKU": row["sku"],
            "Product Name": prod.get("name", "Unknown"),
            "Category": prod.get("category", "General"),
            "Machine Model": prod.get("machine_model", "Universal"),
            "Location": row["location"],
            "Current Stock": row["stock"]
        })
    df_inv = pd.DataFrame(enriched_inv)
    
    sku_filter = st.selectbox("Filter by SKU:", ["All"] + sorted(list(df_inv["SKU"].unique())))
    if sku_filter != "All":
        df_inv = df_inv[df_inv["SKU"] == sku_filter]
        
    st.dataframe(df_inv, use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 3: SUPPLIER FRICTION & RELIABILITY AUDIT
# ------------------------------------------------------------------------------
with tab_suppliers:
    st.subheader("Contracted Supplier Friction & Reliability Audit")
    st.caption("Assesses suppliers on price markup against contract baseline, delivery timing feasibility, and MOQ lock-up risks.")
    
    with open(os.path.join(DATA_DIR, "suppliers.json"), "r", encoding="utf-8") as f:
        sup_data = json.load(f)
    
    base_map = {s["sku"]: s["price"] for s in sup_data if s.get("is_primary", False)}
    aud_rows = []
    for s in sup_data:
        bp = base_map.get(s["sku"], s["price"])
        var = round(((s["price"] - bp) / bp) * 100.0, 1) if bp > 0 else 0.0
        aud_rows.append({
            "Supplier Name": s["supplier"],
            "Target SKU": s["sku"],
            "Tier": "Primary" if s.get("is_primary", False) else "Secondary / Rush",
            "Contract Price": f"₹{s['price']:,.2f}",
            "Price Variance": f"+{var}%" if var > 0 else "0%",
            "Lead Time (Days)": s["lead_time_days"],
            "MOQ (Units)": s["moq"],
            "MOQ Friction Risk": "HIGH (Locked Capital)" if s["moq"] >= 50 else ("MEDIUM" if s["moq"] >= 20 else "LOW")
        })
    st.dataframe(pd.DataFrame(aud_rows), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
# TAB 4: AUDIT TRAIL
# ------------------------------------------------------------------------------
with tab_audit:
    st.subheader("Governance & Human Sign-off Audit Trail")
    st.caption("Immutable record of purchasing colleague interactions and approval gates.")
    
    if audit_log:
        df_audit = pd.DataFrame(audit_log)
        st.dataframe(df_audit, use_container_width=True, hide_index=True)
    else:
        st.info("No approval actions executed yet today. Review the Morning Feed to approve proposed actions.")
