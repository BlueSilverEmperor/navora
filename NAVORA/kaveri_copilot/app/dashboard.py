"""
Kaveri Spares & Hydraulics — Autonomous Supply Chain Copilot & NAVORA Engine
Interactive Streamlit Cockpit for Ramesh Kulkarni (Head of Purchasing)
Provides Morning Feed, Mathematical Explainability, Dynamic Human Override Counter-Proposals,
Chaos / Judge Injection, and Supplier Friction Auditing.
Dark Cyber-Amber Theme & Master-Detail Two-Column Architecture.
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
    page_title="Kaveri Spares Copilot — NAVORA Engine",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 1. DARK CYBER-AMBER THEME INJECTION (MATCHING PIC 2 PALETTE & PIC 1 HIERARCHY)
# ==============================================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    /* Global Dark Cyber-Amber Backgrounds */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #120E0E !important;
        color: #F3F4F6 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    [data-testid="stSidebar"] {
        background-color: #181313 !important;
        border-right: 1px solid #2B1E1E !important;
        color: #F3F4F6 !important;
    }
    
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4 {
        color: #F3F4F6 !important;
    }

    /* Top Banner Card */
    .top-banner {
        background: linear-gradient(135deg, #1E1717 0%, #151010 100%);
        border: 1px solid #332424;
        border-radius: 12px;
        padding: 24px 30px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
    }

    /* 4 KPI Summary Strip Metric Cards */
    .kpi-card {
        background-color: #1A1414;
        border: 1px solid #2D2020;
        border-radius: 10px;
        padding: 16px 20px;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .kpi-card:hover {
        border-color: #FF5733;
        transform: translateY(-2px);
    }
    .kpi-val {
        font-size: 2.1rem;
        font-weight: 700;
        color: #FFFFFF;
        line-height: 1.1;
        margin: 4px 0;
        font-family: 'JetBrains Mono', monospace;
    }
    .kpi-label {
        font-size: 0.78rem;
        color: #9CA3AF;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
    }
    .kpi-sub-green {
        color: #10B981;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .kpi-sub-red {
        color: #EF4444;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .kpi-sub-amber {
        color: #FF6B4A;
        font-size: 0.8rem;
        font-weight: 600;
    }

    /* Master-Detail Task Cards (Left Column) */
    .task-card {
        background-color: #1A1414;
        border: 1px solid #2E2222;
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 12px;
        transition: all 0.2s ease;
    }
    .task-card:hover {
        border-color: rgba(255, 87, 51, 0.5);
    }
    .task-card-active {
        background-color: #241818 !important;
        border: 1.5px solid #FF5733 !important;
        box-shadow: 0 0 14px rgba(255, 87, 51, 0.2);
    }

    /* Pill Badges */
    .badge-critical {
        background-color: #3B1212;
        color: #EF4444;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #7F1D1D;
    }
    .badge-high {
        background-color: #3B2A12;
        color: #F59E0B;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #78350F;
    }
    .badge-medium {
        background-color: #132B3A;
        color: #38BDF8;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #0369A1;
    }
    .badge-cat {
        background-color: #1F242D;
        color: #93C5FD;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 4px;
        border: 1px solid #1E3A8A;
        margin-left: 6px;
    }

    /* Diagnostic Cockpit Container */
    .diag-container {
        background-color: #1A1414;
        border: 1px solid #2D2020;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }

    /* 6 Core Metrics Cards (Right Column) */
    .cyber-metric-card {
        background-color: #161111;
        border: 1px solid #2B1E1E;
        border-radius: 8px;
        padding: 12px 14px;
        text-align: center;
    }
    .cyber-metric-label {
        font-size: 0.72rem;
        color: #9CA3AF;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .cyber-metric-val {
        font-size: 1.35rem;
        font-weight: 700;
        color: #FFFFFF;
        font-family: 'JetBrains Mono', monospace;
    }

    /* Closed-Form Math Telemetry Proof Card */
    .telemetry-card {
        background-color: #0F0C0C !important;
        border: 1px solid #2B1E1E !important;
        border-left: 4px solid #FF5733 !important;
        border-radius: 8px !important;
        padding: 16px 20px !important;
        margin-bottom: 20px !important;
        font-family: 'JetBrains Mono', monospace !important;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4) !important;
    }
    .telemetry-header {
        color: #FF8566 !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        margin-bottom: 8px !important;
        letter-spacing: 0.02em !important;
    }
    .telemetry-line {
        color: #D1D5DB !important;
        font-size: 0.85rem !important;
        line-height: 1.7 !important;
        margin-bottom: 4px !important;
    }
    .telemetry-tag-cyan { color: #38BDF8 !important; font-weight: 600 !important; }
    .telemetry-tag-yellow { color: #FACC15 !important; font-weight: 600 !important; }
    .telemetry-tag-red { color: #EF4444 !important; font-weight: 700 !important; }
    .telemetry-tag-green { color: #10B981 !important; font-weight: 600 !important; }
    .telemetry-tag-amber { color: #FF6B4A !important; font-weight: 600 !important; }

    /* Commercial Impact Scorecard Cards */
    .scorecard-card {
        background: #161111;
        border: 1px solid #2B1E1E;
        border-radius: 8px;
        padding: 14px 16px;
        text-align: center;
    }
    .scorecard-label {
        font-size: 0.74rem;
        color: #9CA3AF;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 4px;
    }
    .scorecard-val {
        font-size: 1.3rem;
        font-weight: 700;
        color: #FFFFFF;
        font-family: 'JetBrains Mono', monospace;
    }
    .scorecard-sub {
        font-size: 0.72rem;
        color: #7E7067;
        margin-top: 4px;
    }

    /* Simulated Action Box */
    .action-box {
        background-color: #131915;
        border: 1.5px solid #10B981;
        border-radius: 10px;
        padding: 18px 20px;
        margin-top: 16px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.08);
    }
    .badge-action {
        background-color: #064E3B;
        color: #34D399;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.78rem;
        border: 1px solid #059669;
    }

    /* Buttons */
    div.stButton > button {
        background-color: #241A1A !important;
        color: #F3F4F6 !important;
        border: 1px solid #3D2929 !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        padding: 8px 16px !important;
        transition: all 0.15s ease !important;
    }
    div.stButton > button:hover {
        border-color: #FF5733 !important;
        color: #FF5733 !important;
        box-shadow: 0 0 10px rgba(255, 87, 51, 0.25) !important;
    }
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #FF5733 0%, #E04322 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(255, 87, 51, 0.35) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        color: #FFFFFF !important;
        transform: translateY(-1px) !important;
    }

    /* Tabs Styling */
    button[data-baseweb="tab"] {
        background-color: transparent !important;
        color: #9CA3AF !important;
        font-weight: 600 !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #FF5733 !important;
        border-bottom-color: #FF5733 !important;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# AUDIT & ENGINE HELPER FUNCTIONS
# ==============================================================================
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


def inject_chaos(scenario_type):
    if scenario_type == "DEMAND_SPIKE":
        st.session_state.chaos_events.append({
            "scenario": "DEMAND_SPIKE",
            "event_type": "DEMAND_SURGE",
            "sku": "FILTER-HYD-01",
            "location": "Gokak",
            "multiplier_or_days": 3.0
        })
        st.toast("⚡ Injected: 3x Demand Surge at Gokak!")
    elif scenario_type == "TRANSFER_ROADBLOCK":
        st.session_state.chaos_events.append({
            "scenario": "TRANSFER_ROADBLOCK",
            "event_type": "TRANSFER_BLOCKED",
            "sku": "FILTER-HYD-01",
            "from_location": "Belgaum",
            "to_location": "Gokak",
            "multiplier_or_days": 1.0
        })
        st.toast("⚡ Injected: Belgaum-to-Gokak Road Blocked!")
    elif scenario_type == "SUPPLIER_HIKE":
        st.session_state.chaos_events.append({
            "scenario": "SUPPLIER_HIKE",
            "event_type": "SUPPLIER_DELAY",
            "sku": "FILTER-HYD-01",
            "location": "Gokak",
            "multiplier_or_days": 5.0
        })
        st.toast("⚡ Injected: Supplier Lead Time +5 Days!")
    st.rerun()


def reset_baseline():
    st.session_state.chaos_events = []
    seed_all_data(DATA_DIR)
    if os.path.exists(AUDIT_LOG_FILE):
        os.remove(AUDIT_LOG_FILE)
    st.success("Benchmark state restored!")
    st.rerun()


# Session state for Chaos events
if "chaos_events" not in st.session_state:
    st.session_state.chaos_events = []

# ==============================================================================
# 2. SIDEBAR CONFIGURATION (EXACT PIC 1 STRUCTURE WITH DARK CYBER STYLING)
# ==============================================================================
with st.sidebar:
    st.markdown("### ⚙️ Operating Controls")
    sim_date = st.text_input("Simulation Date", value="2026/10/09")

    st.markdown("---")
    st.markdown("#### User Persona:")
    st.markdown("👨‍💼 **Ramesh Kulkarni**  \n*Head of Purchasing*")

    st.markdown("#### Operations Network:")
    st.caption("🏬 **6 Retail Stores:** Gokak, Belgaum, Dharwad, Hubli, Bagalkot, Nippani")
    st.caption("🏭 **2 Central Warehouses:** Belgaum Central, Hubli Regional")

    st.markdown("---")
    st.markdown("#### ⚡ Judge / Chaos Test Suite")
    st.caption("Inject live operational shocks to test autonomous resilience:")
    
    if st.button("🌪️ 3x Surge (Gokak)", use_container_width=True):
        inject_chaos("DEMAND_SPIKE")
    if st.button("🚧 Block Belgaum Route", use_container_width=True):
        inject_chaos("TRANSFER_ROADBLOCK")
    if st.button("📈 Vendor Lead Time +5d", use_container_width=True):
        inject_chaos("SUPPLIER_HIKE")
    if st.button("🔄 Reset Baseline State", use_container_width=True):
        reset_baseline()

    if st.session_state.chaos_events:
        st.warning(f"⚠️ {len(st.session_state.chaos_events)} active chaos event(s)")
        if st.button("🧹 Clear Injected Chaos", use_container_width=True):
            st.session_state.chaos_events = []
            st.rerun()


# ==============================================================================
# 3. RUN ENGINE & DATA LOAD
# ==============================================================================
current_date_str = "2026-10-09"
engine = DecisionEngine(
    data_dir=DATA_DIR,
    current_date=current_date_str,
    chaos_events=st.session_state.chaos_events
)
briefing = engine.run_agentic_pipeline()
audit_log = load_audit()
approved_problem_ids = {a["problem_id"] for a in audit_log}

with open(os.path.join(DATA_DIR, "inventory.json"), "r", encoding="utf-8") as f:
    raw_inventory = json.load(f)
with open(os.path.join(DATA_DIR, "sales.json"), "r", encoding="utf-8") as f:
    raw_sales = json.load(f)


# ==============================================================================
# 4. TOP EXECUTIVE HEADER BANNER (MATCHING PIC 1 LAYOUT WITH PIC 2 PALETTE)
# ==============================================================================
st.markdown("""
<div class="top-banner">
    <div>
        <h1 style="margin: 0; font-size: 1.85rem; font-weight: 800; color: #FFFFFF;">Kaveri Spares & Hydraulics</h1>
        <p style="margin: 6px 0 0 0; color: #9CA3AF; font-size: 0.95rem;">
            Autonomous Supply Chain Copilot & Purchasing Colleague for Ramesh Kulkarni
        </p>
    </div>
    <div style="background-color: #231919; border: 1px solid #3E2929; border-radius: 8px; padding: 6px 14px; font-size: 0.85rem; font-weight: 600; color: #E5E7EB;">
        Cypher 2026 • Challenge 01
    </div>
</div>
""", unsafe_allow_html=True)

if st.session_state.chaos_events:
    st.error(f"🚨 **CHAOS INJECTION ACTIVE:** System is running under {len(st.session_state.chaos_events)} live operational shock(s). Observe the agent automatically adapting its options!")


# ==============================================================================
# 5. KPI SUMMARY STRIP (4 COLUMNS - EXACT PIC 1 METRICS WITH PIC 2 CYBER STYLING)
# ==============================================================================
summary = briefing["summary"]
k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Total Operational Issues</div>
        <div class="kpi-val">{summary["total_problems_detected"]}</div>
        <div class="kpi-sub-green">↑ Across 8 Nodes</div>
    </div>
    """, unsafe_allow_html=True)
with k2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Critical Stockouts</div>
        <div class="kpi-val" style="color: #EF4444;">{summary["critical_actions_required"]}</div>
        <div class="kpi-sub-red">↑ Immediate Action Needed</div>
    </div>
    """, unsafe_allow_html=True)
with k3:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Top Attention SKU</div>
        <div class="kpi-val" style="font-size: 1.45rem; line-height: 1.4; color: #FF6B4A;">{summary["top_focus_sku"]}</div>
        <div class="kpi-sub-amber">↑ Hydraulic Filtration</div>
    </div>
    """, unsafe_allow_html=True)
with k4:
    pending_count = sum(1 for p in briefing["problems"] if p["problem_id"] not in approved_problem_ids)
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Pending Human Gate Approvals</div>
        <div class="kpi-val">{pending_count}</div>
        <div class="kpi-sub-green">↑ {len(audit_log)} Decisions Logged</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)


# ==============================================================================
# 6. NAVIGATION TABS (MATCHING PIC 1 EXACT TABS)
# ==============================================================================
tab_feed, tab_inv, tab_sup, tab_audit = st.tabs([
    "🚨 Morning Action Feed & Approval Gate",
    "🏭 Multi-Echelon Network Inventory",
    "🔍 Supplier Friction & Reliability Audit",
    "📜 Immutable Audit Trail"
])


# ==============================================================================
# RESOLUTION COCKPIT RENDERER (RIGHT COLUMN 62% IN PIC 1 WITH PIC 2 PALETTE)
# ==============================================================================
def render_cyber_detail_cockpit(p, approved_problem_ids, raw_inventory, raw_sales):
    pid = p["problem_id"]
    is_handled = pid in approved_problem_ids
    cat_code = p.get("category_code", "CATEGORY_A")

    sev = p.get("severity", "MEDIUM")
    badge_cls = "badge-critical" if sev == "CRITICAL" else ("badge-high" if sev == "HIGH" else "badge-medium")
    sev_color = "#EF4444" if sev == "CRITICAL" else ("#F59E0B" if sev == "HIGH" else "#38BDF8")
    status_banner = "✅ ALREADY EXECUTED" if is_handled else "⚡ AWAITING RAMESH KULKARNI APPROVAL"

    # 1. Headline Container
    st.markdown(f"""
    <div class="diag-container" style="border-left: 4px solid {sev_color};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div>
                <span class="{badge_cls}">[{sev}]</span>
                <span class="badge-cat">{cat_code}</span>
                <span style="font-weight: 700; font-size: 1.15rem; color: #FFFFFF; margin-left: 8px;">{p['sku_name']} ({p['sku']})</span>
                <span style="color: #9CA3AF; margin-left: 8px;">📍 <b>{p['location']}</b></span>
            </div>
            <div>
                <span style="font-size: 0.8rem; font-weight: 700; color: {'#10B981' if is_handled else '#F59E0B'};">
                    {status_banner}
                </span>
            </div>
        </div>
        <p style="color: #D1D5DB; margin: 6px 0 0 0; font-size: 0.95rem;">
            <b>Diagnosis:</b> {p['diagnosis']}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 2. 6 Core Telemetry Metric Cards
    m = p["domain_metrics"]
    ad = p.get("adaptive_velocity", m.get("adaptive_velocity", {}))
    v_base = ad.get("v_baseline", m.get("daily_burn_rate", 0.0))
    v_rec = ad.get("v_recent", m.get("daily_burn_rate", 0.0))
    trend_factor = ad.get("trend_factor", 1.0)
    trend_label = ad.get("trend_label", "STABLE")

    trend_color = "#EF4444" if trend_label == "ACCELERATING" else ("#F59E0B" if trend_label == "DECELERATING" else "#10B981")
    cover_color = "#EF4444" if m['days_of_cover'] <= 3.0 else ("#F59E0B" if m['days_of_cover'] <= 7.0 else "#10B981")
    gap_color = "#EF4444" if m['stockout_gap_days'] > 0 else "#10B981"

    vc1, vc2, vc3, vc4, vc5, vc6 = st.columns(6)
    with vc1:
        st.markdown(f"""<div class="cyber-metric-card"><div class="cyber-metric-label">v_baseline (30d)</div><div class="cyber-metric-val">{v_base:.2f}/d</div></div>""", unsafe_allow_html=True)
    with vc2:
        st.markdown(f"""<div class="cyber-metric-card"><div class="cyber-metric-label">v_recent (7d)</div><div class="cyber-metric-val">{v_rec:.2f}/d</div></div>""", unsafe_allow_html=True)
    with vc3:
        st.markdown(f"""<div class="cyber-metric-card"><div class="cyber-metric-label">Trend Factor</div><div class="cyber-metric-val" style="color:{trend_color}; font-size: 1.15rem;">{trend_factor:.1f}x {trend_label}</div></div>""", unsafe_allow_html=True)
    with vc4:
        st.markdown(f"""<div class="cyber-metric-card"><div class="cyber-metric-label">Current Stock</div><div class="cyber-metric-val">{m['current_stock']} u</div></div>""", unsafe_allow_html=True)
    with vc5:
        st.markdown(f"""<div class="cyber-metric-card"><div class="cyber-metric-label">Cover (D)</div><div class="cyber-metric-val" style="color: {cover_color};">{m['days_of_cover']}d</div></div>""", unsafe_allow_html=True)
    with vc6:
        st.markdown(f"""<div class="cyber-metric-card"><div class="cyber-metric-label">Gap (Δ)</div><div class="cyber-metric-val" style="color: {gap_color};">{m['stockout_gap_days']}d</div></div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # 3. Closed-Form Mathematical Telemetry Proof (Rule 2 & Rule 11)
    if "math_explainability" in p:
        me = p["math_explainability"]
        st.markdown(f"""
<div class="telemetry-card">
    <div class="telemetry-header">📐 DETERMINISTIC DOMAIN MATH &amp; TELEMETRY AUDIT:</div>
    <div class="telemetry-line">• <b>Velocity:</b> <span class="telemetry-tag-cyan">{me.get('formula_velocity', '')}</span></div>
    <div class="telemetry-line">• <b>Days of Cover:</b> <span class="telemetry-tag-yellow">{me.get('formula_cover', '')}</span></div>
    <div class="telemetry-line">• <b>Deficit Gap:</b> <span class="telemetry-tag-red">{me.get('formula_gap', '')}</span></div>
    <div class="telemetry-line">• <b>Commercial Risk Exposure:</b> Lead Time T = <span class="telemetry-tag-cyan">{me.get('T', 7)}d</span> | Margin = <span class="telemetry-tag-green">₹{me.get('unit_margin_inr', 0):,.2f}/unit</span> | Potential Lost Revenue = <span class="telemetry-tag-red">₹{me.get('projected_lost_revenue_inr', 0):,.2f}</span></div>
</div>
""", unsafe_allow_html=True)

    # 4. Commercial Impact Scorecard (Rule 5)
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
            <div class="scorecard-val" style="color: #10B981;">{net_cost_str}</div>
            <div class="scorecard-sub">Flat Handling vs Vendor Premium</div>
        </div>
        """, unsafe_allow_html=True)
    with sc2:
        st.markdown(f"""
        <div class="scorecard-card">
            <div class="scorecard-label">Lost Units Averted</div>
            <div class="scorecard-val" style="color: #38BDF8;">{lost_units} units</div>
            <div class="scorecard-sub">Protected vs Inaction Deficit</div>
        </div>
        """, unsafe_allow_html=True)
    with sc3:
        wc_outflow = "₹0.00" if has_transfer else f"₹{p['simulated_action']['payload'].get('total_estimated_cost_inr', 0):,.2f}"
        st.markdown(f"""
        <div class="scorecard-card">
            <div class="scorecard-label">Working Capital Outflow</div>
            <div class="scorecard-val" style="color: #10B981;">{wc_outflow}</div>
            <div class="scorecard-sub">{"Internal Inventory Reallocation" if has_transfer else "New Vendor Capital Outlay"}</div>
        </div>
        """, unsafe_allow_html=True)
    with sc4:
        dt_risk = "0 Days" if has_transfer else (f"{min(3, int(m_gap))} Days" if m_gap > 0 else "0 Days")
        st.markdown(f"""
        <div class="scorecard-card">
            <div class="scorecard-label">Downtime Risk</div>
            <div class="scorecard-val" style="color: {'#10B981' if dt_risk == '0 Days' else '#EF4444'};">{dt_risk}</div>
            <div class="scorecard-sub">Eliminates {m_gap}d Stockout Gap</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # 5. Interactive Dark Cyber Plotly Forward Trajectory Graph
    fp = p.get("forward_projections")
    if fp and "days" in fp:
        st.markdown("##### 📈 14-Day Forward Visual Inventory Trajectories")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=fp["days"],
            y=fp["status_quo"],
            mode="lines+markers",
            name="Option 3: Status Quo (Wait for Primary Vendor PO)",
            line=dict(color="#EF4444", width=2.5, dash="dot"),
            marker=dict(size=6, color="#EF4444")
        ))
        fig.add_trace(go.Scatter(
            x=fp["days"],
            y=fp["expedited"],
            mode="lines+markers",
            name="Option 2: Expedited Vendor PO (Day 3 Arrival)",
            line=dict(color="#F59E0B", width=2.5, dash="dash"),
            marker=dict(size=6, color="#F59E0B")
        ))
        fig.add_trace(go.Scatter(
            x=fp["days"],
            y=fp["transfer"],
            mode="lines+markers",
            name="Option 1: Inter-Store Transfer (Day 1 Arrival)",
            line=dict(color="#38BDF8", width=3.5),
            marker=dict(size=7, color="#38BDF8")
        ))
        fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="#EF4444",
            line_width=1.5,
            annotation_text="⚠️ Stockout Hazard Line (Zero Stock)",
            annotation_position="bottom right",
            annotation_font_color="#EF4444"
        )
        fig.update_layout(
            title=dict(
                text=f"Projected Inventory Levels: {p['sku_name']} @ {p['location']}",
                font=dict(size=13, color="#F3F4F6")
            ),
            xaxis=dict(title="Days Ahead", dtick=1, gridcolor="#2B1E1E", color="#9CA3AF"),
            yaxis=dict(title="Projected Stock (Units)", gridcolor="#2B1E1E", color="#9CA3AF"),
            hovermode="x unified",
            height=320,
            margin=dict(l=40, r=40, t=50, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#D1D5DB", size=10)),
            plot_bgcolor="#141010",
            paper_bgcolor="#1A1414"
        )
        st.plotly_chart(fig, use_container_width=True)

    # 6. Feasible Mitigation Pathways Table ($N >= 2$)
    opt_data = []
    for opt in p["evaluated_options"]:
        opt_data.append({
            "Option Name": f"{opt['option_name']} [{opt.get('source', '')}]",
            "Delivery Time": f"{opt.get('lead_time_days', opt.get('delivery_time_days', 1))} days",
            "Total Cash Outlay": f"₹{opt.get('cash_impact_inr', opt.get('estimated_cost_inr', 0.0)):,.2f}",
            "Feasibility": opt.get("feasibility_status", opt.get("feasibility", "FEASIBLE")),
            "Summary": opt.get("trade_off_summary", opt.get("pros_cons", ""))
        })
    st.markdown(r"##### ⚖️ Feasible Mitigation Pathways ($N \ge 2$)")
    st.dataframe(pd.DataFrame(opt_data), use_container_width=True, hide_index=True)
    st.markdown(f"**🎯 AI Agent Recommendation Rationale:** {p['decision_rationale']}")

    # 7. Action Draft Execution Box
    act = p["simulated_action"]
    pay = act["payload"]
    
    st.markdown(f"""
    <div class="action-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <div>
                <span class="badge-action">Simulated Action: {act['action_type']}</span>
                <span style="margin-left: 0.5rem; font-weight: 700; font-size: 0.95rem; color: #34D399;">
                    Quantity: {pay['qty']} units • Total Estimated Cost: ₹{pay['total_estimated_cost_inr']:,.2f}
                </span>
            </div>
            <div style="font-size: 0.85rem; color: #10B981; font-weight: 600;">
                Expected Arrival: {pay['expected_delivery_date']}
            </div>
        </div>
        <div style="font-size: 0.9rem; color: #D1D5DB;">
            <b>Route:</b> {pay['from_location_or_supplier']} ➔ <b>{pay['to_location']}</b> &nbsp;|&nbsp; 
            <b>Urgency:</b> {pay['urgency']} &nbsp;|&nbsp; 
            <b>Human Gate:</b> Simulated Draft (Mandatory Ramesh Kulkarni Approval Required)
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 8. Human-in-the-Loop Counter-Proposal & Approval Gate
    if not is_handled:
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
                    line=dict(color="#10B981", width=3),
                    marker=dict(size=6)
                ))
                if fp and "transfer" in fp:
                    fig_ov.add_trace(go.Scatter(
                        x=fp["days"],
                        y=fp["transfer"],
                        mode="lines+markers",
                        name=f"AI Proposed Baseline ({pay['qty']} units)",
                        line=dict(color="#9CA3AF", width=2, dash="dash"),
                        marker=dict(size=5)
                    ))
                fig_ov.add_hline(y=0, line_dash="dash", line_color="#EF4444", annotation_text="Hazard Line")
                fig_ov.update_layout(
                    title=dict(
                        text=f"Dynamic Recalibration: Ramesh's Counter-Proposal ({override_qty} units) vs AI Draft ({pay['qty']} units)",
                        font=dict(size=12, color="#F3F4F6")
                    ),
                    xaxis=dict(title="Days", dtick=1, gridcolor="#2B1E1E", color="#9CA3AF"),
                    yaxis=dict(title="Stock (Units)", gridcolor="#2B1E1E", color="#9CA3AF"),
                    height=240,
                    margin=dict(l=30, r=30, t=40, b=30),
                    plot_bgcolor="#141010",
                    paper_bgcolor="#1A1414",
                    legend=dict(font=dict(color="#D1D5DB", size=10))
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
        st.caption("Status: Handled in audit log.")


# ==============================================================================
# TAB 1: MORNING FEED & MASTER-DETAIL WORKSPACE (PORTING PIC 1 WORKFLOW)
# ==============================================================================
with tab_feed:
    # 1. Initialize session state for selected problem
    if "selected_problem_id" not in st.session_state:
        gokak_prob = next((p for p in briefing.get("problems", []) if p.get("sku") == "FILTER-HYD-01" and p.get("location") == "Gokak"), None)
        if gokak_prob:
            st.session_state.selected_problem_id = gokak_prob["problem_id"]
        elif briefing.get("problems"):
            st.session_state.selected_problem_id = briefing["problems"][0]["problem_id"]
        else:
            st.session_state.selected_problem_id = None

    # 2. Chaos Injection Bar (Separated Above Worklist - Matching Pic 1)
    c_hdr, c_rig = st.columns([0.38, 0.62])
    with c_hdr:
        st.markdown("### 📋 Morning Operational Tasks")
    with c_rig:
        st.markdown("<div style='text-align: right; color: #9CA3AF; font-size: 0.85rem; margin-bottom: 4px; font-weight: 600;'>Chaos Injection Rig:</div>", unsafe_allow_html=True)
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("🌪️ Demand Surge (3x)", key="btn_chaos_surge", use_container_width=True):
            inject_chaos("DEMAND_SPIKE")
        if b2.button("🚧 Block Route", key="btn_chaos_block", use_container_width=True):
            inject_chaos("TRANSFER_ROADBLOCK")
        if b3.button("📈 Supplier Delay (+5d)", key="btn_chaos_delay", use_container_width=True):
            inject_chaos("SUPPLIER_HIKE")
        if b4.button("🔄 Reset Baseline", key="btn_chaos_reset", use_container_width=True):
            reset_baseline()

    st.markdown("<hr style='border: 0.5px solid #2B1E1E; margin: 12px 0 20px 0;'>", unsafe_allow_html=True)

    # 3. Master-Detail Split (Left 38% Stacked Task Cards, Right 62% Resolution Cockpit)
    col_list, col_detail = st.columns([0.38, 0.62], gap="large")

    # --- LEFT COLUMN: STACKED TASK CARDS (NO DROPDOWNS) ---
    with col_list:
        st.markdown(f"#### Active Incidents ({len(briefing.get('problems', []))})")

        # In-pane quick filter
        sev_filter = st.selectbox("Filter Severity:", ["All", "CRITICAL", "HIGH", "MEDIUM"], key="pane_sev_filter")
        filtered_problems = briefing.get("problems", [])
        if sev_filter != "All":
            filtered_problems = [p for p in filtered_problems if p["severity"] == sev_filter]

        if not filtered_problems:
            st.info("No incidents match the selected severity filter.")

        for prob in filtered_problems:
            pid = prob["problem_id"]
            is_active = (pid == st.session_state.selected_problem_id)
            is_handled = pid in approved_problem_ids

            active_cls = "task-card-active" if is_active else ""
            sev = prob.get("severity", "MEDIUM")
            badge_cls = "badge-critical" if sev == "CRITICAL" else ("badge-high" if sev == "HIGH" else "badge-medium")

            m_prob = prob.get("domain_metrics", {})
            stock_val = m_prob.get("current_stock", 0)
            cover_val = m_prob.get("days_of_cover", 0.0)
            gap_val = m_prob.get("stockout_gap_days", 0.0)

            st.markdown(
                f"""
                <div class="task-card {active_cls}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <div>
                            <span class="{badge_cls}">[{sev}]</span>
                            <span class="badge-cat">{prob.get('category_code', 'CAT_A')}</span>
                        </div>
                        <span style="font-size: 0.75rem; color: {'#10B981' if is_handled else '#F59E0B'}; font-weight: 600;">
                            {'✓ Done' if is_handled else '⚡ AWAITING APPROVAL'}
                        </span>
                    </div>
                    <div style="font-weight: 700; font-size: 1.05rem; color: #FFFFFF; margin-bottom: 2px;">
                        {prob.get('location', '')} — {prob.get('sku', '')}
                    </div>
                    <div style="font-size: 0.8rem; color: #9CA3AF; margin-bottom: 8px;">
                        {prob.get('sku_name', '')}
                    </div>
                    <div style="font-size: 0.82rem; color: #9CA3AF; font-family: 'JetBrains Mono', monospace;">
                        Stock: <b style="color: #FFF;">{stock_val}</b> | 
                        Cover: <b style="color: #FFF;">{cover_val:.1f}d</b> | 
                        Gap: <b style="color: {'#EF4444' if gap_val > 0 else '#10B981'};">{gap_val:.1f}d</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            btn_label = "● Viewing Active Task" if is_active else "Select & Resolve ➔"
            if st.button(btn_label, key=f"card_btn_{pid}", use_container_width=True, disabled=is_active):
                st.session_state.selected_problem_id = pid
                st.rerun()

    # --- RIGHT COLUMN: ACTIVE RESOLUTION COCKPIT ---
    with col_detail:
        active_prob = next(
            (p for p in briefing.get("problems", []) if p["problem_id"] == st.session_state.selected_problem_id),
            None
        )
        if not active_prob and filtered_problems:
            active_prob = filtered_problems[0]
            st.session_state.selected_problem_id = active_prob["problem_id"]

        if active_prob:
            render_cyber_detail_cockpit(active_prob, approved_problem_ids, raw_inventory, raw_sales)
        else:
            st.info("Select a morning incident card on the left to inspect evidence.")


# ==============================================================================
# TAB 2: MULTI-ECHELON INVENTORY
# ==============================================================================
with tab_inv:
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


# ==============================================================================
# TAB 3: SUPPLIER FRICTION & RELIABILITY AUDIT
# ==============================================================================
with tab_sup:
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


# ==============================================================================
# TAB 4: AUDIT TRAIL
# ==============================================================================
with tab_audit:
    st.subheader("Governance & Human Sign-off Audit Trail")
    st.caption("Immutable record of purchasing colleague interactions and approval gates.")
    
    if audit_log:
        df_audit = pd.DataFrame(audit_log)
        st.dataframe(df_audit, use_container_width=True, hide_index=True)
    else:
        st.info("No approval actions executed yet today. Review the Morning Feed to approve proposed actions.")
