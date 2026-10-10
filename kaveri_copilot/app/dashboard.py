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
import engine.config
import engine.domain_math
import engine.decision_agent
importlib.reload(engine.config)
importlib.reload(engine.domain_math)
importlib.reload(engine.decision_agent)

from engine.decision_agent import DecisionEngine, extract_network_topology
from engine.domain_math import validate_and_recalculate_transfer, generate_14day_projections
from engine.data_loader import (
    load_validated_datasets,
    load_table_records,
    save_table_records,
    get_default_data_dir,
)

DATA_DIR = get_default_data_dir()
AUDIT_LOG_FILE = os.path.join(DATA_DIR, "audit_log.json")

FACILITY_COORDS = {
    "Belgaum Central Warehouse": (74.4977, 15.8497, "Warehouse"),
    "Hubli Regional Warehouse": (75.1240, 15.3647, "Warehouse"),
    "Belgaum WH": (74.4977, 15.8497, "Warehouse"),
    "Hubli WH": (75.1240, 15.3647, "Warehouse"),
    "Gokak": (74.8229, 16.1696, "Store"),
    "Belgaum": (74.5200, 15.8600, "Store"),
    "Dharwad": (75.0078, 15.4589, "Store"),
    "Hubli": (75.1400, 15.3500, "Store"),
    "Bagalkot": (75.6980, 16.1875, "Store"),
    "Nippani": (74.3820, 16.3980, "Store"),
    "Bijapur": (75.7139, 16.8302, "Store"),
}

def render_network_topology_graph(inventory_df: pd.DataFrame, is_dark_mode: bool = None) -> go.Figure:
    """Renders interactive 2D geographic topology network graph with fallback coordinate mapping."""
    topology = extract_network_topology(inventory_df)
    fig = go.Figure()
    for loc in topology["all_locations"]:
        coords = FACILITY_COORDS.get(loc, (75.0, 15.5, "Store"))
        lon, lat, facility_type = coords
        is_wh = loc in topology["warehouses"]
        fig.add_trace(go.Scattergeo(
            lon=[lon],
            lat=[lat],
            text=[f"{loc} ({'Warehouse' if is_wh else 'Store'})"],
            mode="markers+text",
            marker=dict(
                size=14 if is_wh else 10,
                color="#8FA87B" if is_wh else "#F59E0B",
                symbol="square" if is_wh else "circle"
            ),
            name=loc
        ))
    return fig

def render_resource_network_graph(inventory_df: pd.DataFrame, is_dark_mode: bool = None) -> go.Figure:
    return render_network_topology_graph(inventory_df, is_dark_mode)

# Streamlit Page Config
st.set_page_config(
    page_title="Kaveri Spares Copilot — NAVORA Engine",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# SAGE GREEN DESIGN SYSTEM & UNIVERSAL LIGHT/DARK THEME ENGINE
# ==============================================================================
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Dark"  # Default mode

# Sidebar Theme Toggle
with st.sidebar:
    st.markdown("### 🎨 Visual Theme")
    theme_choice = st.radio(
        "Appearance Mode",
        ["Dark", "Light"],
        index=0 if st.session_state.theme_mode == "Dark" else 1,
        horizontal=True,
        label_visibility="collapsed",
        key="app_theme_toggle_radio"
    )
    if theme_choice != st.session_state.theme_mode:
        st.session_state.theme_mode = theme_choice
        st.rerun()

is_dark = (st.session_state.theme_mode == "Dark")

# Official Sage Design Tokens Matrix
tokens = {
    "bg_primary": "#0E120E" if is_dark else "#F4F6F0",
    "surface": "#171D16" if is_dark else "#FFFFFF",
    "surface_alt": "#20291F" if is_dark else "#E8EDE0",
    "border": "#2C3A2A" if is_dark else "#CBD5C0",
    "sage_primary": "#8FA87B" if is_dark else "#5B7053",
    "sage_accent": "#B2CF9C" if is_dark else "#7D9D71",
    "alert_crimson": "#FF5C5C" if is_dark else "#C84B31",
    "alert_crimson_bg": "#331414" if is_dark else "#FBEBE8",
    "alert_amber": "#F59E0B" if is_dark else "#D9822B",
    "alert_amber_bg": "#2E2210" if is_dark else "#FDF6E2",
    "text_primary": "#F1F5EE" if is_dark else "#1E241B",
    "text_secondary": "#9DAE97" if is_dark else "#5D6656",
    "card_shadow": "0 8px 24px rgba(0,0,0,0.35)" if is_dark else "0 4px 12px rgba(91,112,83,0.08)",
}

st.markdown(f"""
<style>
    /* Global Base */
    .stApp, [data-testid="stAppViewContainer"] {{
        background-color: {tokens['bg_primary']} !important;
        color: {tokens['text_primary']} !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}

    [data-testid="stHeader"] {{
        background-color: {tokens['bg_primary']} !important;
        height: 2.2rem !important;
        min-height: 2.2rem !important;
        z-index: 99 !important;
    }}
    .block-container, [data-testid="stAppViewBlockContainer"], div[data-testid="stMainBlockContainer"], .main .block-container {{
        padding-top: 0.6rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }}
    
    /* Sidebar High-Contrast Styling */
    [data-testid="stSidebar"], [data-testid="stSidebarContent"], [data-testid="stSidebar"] > div {{
        background-color: {tokens['surface']} !important;
        border-right: 1px solid {tokens['border']} !important;
        color: {tokens['text_primary']} !important;
    }}
    
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, 
    [data-testid="stSidebar"] h3, [data-testid="stSidebar"] h4,
    [data-testid="stSidebar"] h5, [data-testid="stSidebar"] h6 {{
        color: {tokens['text_primary']} !important;
        font-weight: 700 !important;
    }}

    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div {{
        color: {tokens['text_secondary']} !important;
    }}

    /* Form Labels (e.g. Simulation Date) */
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] label p,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] span {{
        color: {tokens['sage_primary']} !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
    }}

    /* Captions and Secondary Text */
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebar"] small {{
        color: {tokens['text_secondary']} !important;
        font-size: 0.86rem !important;
        line-height: 1.45 !important;
        font-weight: 500 !important;
    }}

    /* Sidebar Divider Lines */
    [data-testid="stSidebar"] hr {{
        border-color: {tokens['border']} !important;
        margin: 1.1rem 0 !important;
    }}

    /* Sidebar Action Buttons */
    [data-testid="stSidebar"] .stButton > button {{
        background-color: {tokens['surface_alt']} !important;
        border: 1px solid {tokens['border']} !important;
        color: {tokens['text_primary']} !important;
        font-weight: 600 !important;
        transition: all 0.15s ease !important;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        background-color: {tokens['surface']} !important;
        border-color: {tokens['sage_accent']} !important;
        color: {tokens['sage_accent']} !important;
    }}

    /* Input & Select Elements Uniformity */
    .stTextInput input, .stNumberInput input {{
        background-color: {tokens['surface']} !important;
        color: {tokens['text_primary']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 6px !important;
    }}
    .stTextInput input:focus, .stNumberInput input:focus {{
        border-color: {tokens['sage_accent']} !important;
        box-shadow: 0 0 6px {'rgba(178, 207, 156, 0.4)' if is_dark else 'rgba(91, 112, 83, 0.3)'} !important;
    }}

    /* Selectbox Dropdown Menu Theme */
    div[data-baseweb="select"] {{
        background-color: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 6px !important;
        color: {tokens['text_primary']} !important;
    }}
    div[data-baseweb="select"] > div {{
        background-color: {tokens['surface']} !important;
        color: {tokens['text_primary']} !important;
        border: none !important;
    }}
    div[data-baseweb="select"]:focus-within {{
        border-color: {tokens['sage_accent']} !important;
    }}
    div[data-baseweb="popover"], div[data-baseweb="popover"] > div, ul[role="listbox"], ul[data-testid="stVirtualDropdown"] {{
        background-color: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        color: {tokens['text_primary']} !important;
    }}
    li[role="option"] {{
        background-color: {tokens['surface']} !important;
        color: {tokens['text_primary']} !important;
    }}
    li[role="option"]:hover, li[role="option"][aria-selected="true"] {{
        background-color: {tokens['surface_alt']} !important;
        color: {tokens['sage_accent']} !important;
    }}

    /* Pixel-Perfect Sage Table System */
    .cyber-table-container {{
        width: 100%;
        overflow-x: auto;
        background-color: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 10px;
        margin: 12px 0 20px 0;
        box-shadow: {tokens['card_shadow']};
    }}
    table.cyber-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.86rem;
        text-align: left;
        color: {tokens['text_primary']} !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    table.cyber-table thead tr {{
        background-color: {tokens['surface_alt']} !important;
        border-bottom: 2px solid {tokens['border']} !important;
    }}
    table.cyber-table th {{
        padding: 12px 16px;
        color: {tokens['sage_primary']} !important;
        font-weight: 700;
        text-transform: uppercase;
        font-size: 0.76rem;
        letter-spacing: 0.04em;
        white-space: nowrap;
    }}
    table.cyber-table tbody tr {{
        border-bottom: 1px solid {tokens['border']} !important;
        transition: background-color 0.15s ease;
    }}
    table.cyber-table tbody tr:hover {{
        background-color: {tokens['surface_alt']} !important;
    }}
    table.cyber-table tbody tr:last-child {{
        border-bottom: none;
    }}
    table.cyber-table td {{
        padding: 12px 16px;
        color: {tokens['text_primary']} !important;
        vertical-align: middle;
    }}

    /* Navigation Tabs */
    button[data-baseweb="tab"] {{
        background-color: transparent !important;
        color: {tokens['text_secondary']} !important;
        font-weight: 600 !important;
        border-bottom: 2px solid transparent !important;
        padding: 10px 18px !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {tokens['sage_accent']} !important;
        border-bottom: 2px solid {tokens['sage_accent']} !important;
    }}

    /* Top Executive Banner */
    .top-banner {{
        background: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 12px;
        padding: 22px 28px;
        margin-top: 0px !important;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: {tokens['card_shadow']};
    }}

    /* KPI Cards */
    .kpi-box, .kpi-card {{
        background-color: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 10px;
        padding: 16px 20px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: {tokens['card_shadow']};
        transition: transform 0.15s ease, border-color 0.15s ease;
    }}
    .kpi-box:hover, .kpi-card:hover {{
        border-color: {tokens['sage_accent']} !important;
        transform: translateY(-2px);
    }}
    .kpi-title, .kpi-label {{
        font-size: 0.78rem;
        color: {tokens['text_secondary']};
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.5px;
    }}
    .kpi-number, .kpi-val {{
        font-size: 2.1rem;
        font-weight: 800;
        color: {tokens['text_primary']};
        margin: 4px 0;
        line-height: 1.1;
        font-family: 'JetBrains Mono', 'Courier New', monospace;
    }}
    .kpi-foot-green, .kpi-sub-green {{ color: {tokens['sage_accent']}; font-size: 0.8rem; font-weight: 600; }}
    .kpi-foot-red, .kpi-sub-red {{ color: {tokens['alert_crimson']}; font-size: 0.8rem; font-weight: 600; }}
    .kpi-sub-amber {{ color: {tokens['alert_amber']}; font-size: 0.8rem; font-weight: 600; }}

    /* Task Incident Feed Cards */
    .incident-card, .task-card {{
        background-color: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 10px;
        transition: border 0.15s ease, background 0.15s ease;
    }}
    .incident-card:hover, .task-card:hover {{
        border-color: {tokens['sage_accent']};
    }}
    .incident-card-active, .task-card-active {{
        background-color: {tokens['surface_alt']} !important;
        border: 1.5px solid {tokens['sage_accent']} !important;
        box-shadow: 0 0 12px {'rgba(178, 207, 156, 0.25)' if is_dark else 'rgba(125, 157, 113, 0.25)'} !important;
    }}
    
    /* Monospace Math Block */
    .math-terminal, .telemetry-card {{
        background-color: {tokens['bg_primary']} !important;
        border: 1px solid {tokens['border']} !important;
        border-left: 4px solid {tokens['sage_primary']} !important;
        border-radius: 6px !important;
        padding: 14px 18px !important;
        font-family: "Courier New", "Roboto Mono", monospace !important;
        font-size: 0.84rem !important;
        color: {tokens['sage_accent']} !important;
        line-height: 1.6 !important;
        margin-bottom: 18px !important;
    }}

    /* Badges */
    .badge-critical {{
        background-color: {tokens['alert_crimson_bg']} !important;
        color: {tokens['alert_crimson']} !important;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 7px;
        border-radius: 4px;
        border: 1px solid {tokens['alert_crimson']};
    }}
    .badge-tag, .badge-cat {{
        background-color: {tokens['surface_alt']} !important;
        color: {tokens['sage_primary']} !important;
        font-size: 0.72rem;
        font-weight: 600;
        padding: 2px 7px;
        border-radius: 4px;
        border: 1px solid {tokens['border']};
        margin-left: 4px;
    }}
    .badge-high {{
        background-color: {tokens['alert_amber_bg']} !important;
        color: {tokens['alert_amber']} !important;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 7px;
        border-radius: 4px;
        border: 1px solid {tokens['alert_amber']};
    }}
    .badge-medium {{
        background-color: {tokens['surface_alt']} !important;
        color: {tokens['sage_accent']} !important;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 7px;
        border-radius: 4px;
        border: 1px solid {tokens['border']};
    }}

    /* Diagnostic Cockpit Container */
    .diag-container {{
        background-color: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 18px;
        box-shadow: {tokens['card_shadow']};
    }}

    /* 6 Core Metrics Cards (Right Column) */
    .cyber-metric-card {{
        background-color: {tokens['surface_alt']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 8px;
        padding: 12px 14px;
        text-align: center;
    }}
    .cyber-metric-label {{
        font-size: 0.72rem;
        color: {tokens['text_secondary']};
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 4px;
    }}
    .cyber-metric-val {{
        font-size: 1.35rem;
        font-weight: 700;
        color: {tokens['text_primary']};
        font-family: 'JetBrains Mono', 'Courier New', monospace;
    }}

    /* Commercial Impact Scorecard Cards */
    .scorecard-card {{
        background: {tokens['surface']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 8px;
        padding: 14px 16px;
        text-align: center;
        box-shadow: {tokens['card_shadow']};
    }}
    .scorecard-label {{
        font-size: 0.74rem;
        color: {tokens['text_secondary']};
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 4px;
    }}
    .scorecard-val {{
        font-size: 1.3rem;
        font-weight: 700;
        color: {tokens['text_primary']};
        font-family: 'JetBrains Mono', 'Courier New', monospace;
    }}
    .scorecard-sub {{
        font-size: 0.72rem;
        color: {tokens['text_secondary']};
        margin-top: 4px;
    }}

    /* Simulated Action Box */
    .action-box {{
        background-color: {tokens['surface_alt']} !important;
        border: 1.5px solid {tokens['sage_accent']} !important;
        border-radius: 10px;
        padding: 18px 20px;
        margin-top: 16px;
        margin-bottom: 16px;
        box-shadow: {tokens['card_shadow']};
    }}
    .badge-action {{
        background-color: {tokens['surface']} !important;
        color: {tokens['sage_accent']} !important;
        padding: 4px 10px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.78rem;
        border: 1px solid {tokens['sage_accent']};
    }}

    /* Form Inputs & Buttons */
    div.stButton > button {{
        background-color: {tokens['surface_alt']} !important;
        color: {tokens['text_primary']} !important;
        border: 1px solid {tokens['border']} !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        padding: 8px 16px !important;
        transition: all 0.15s ease !important;
    }}
    div.stButton > button:hover {{
        border-color: {tokens['sage_accent']} !important;
        color: {tokens['sage_accent']} !important;
    }}
    div.stButton > button[kind="primary"] {{
        background: {tokens['sage_primary']} !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 14px {'rgba(143, 168, 123, 0.35)' if is_dark else 'rgba(91, 112, 83, 0.25)'} !important;
    }}
    div.stButton > button[kind="primary"]:hover {{
        color: #FFFFFF !important;
        background: {tokens['sage_accent']} !important;
    }}
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
    inventory = load_table_records(DATA_DIR, "inventory")
    pos = load_table_records(DATA_DIR, "purchase_orders")

    sku = payload["sku"]
    qty = payload["qty"]
    from_src = payload["from_location_or_supplier"]
    to_loc = payload["to_location"]

    if action_type == "TRANSFER_REQUEST":
        for item in inventory:
            if item["sku"] == sku and item["location"] == from_src:
                item["stock"] = max(0, int(item["stock"]) - qty)
            elif item["sku"] == sku and item["location"] == to_loc:
                item["stock"] = int(item["stock"]) + qty
        save_table_records(DATA_DIR, "inventory", inventory)

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
        save_table_records(DATA_DIR, "purchase_orders", pos)

    elif action_type == "SUPPLIER_EXPEDITE_NOTICE":
        for po in pos:
            if po["sku"] == sku and po["supplier"] == from_src and po.get("status") not in ("DELIVERED", "CANCELLED"):
                po["status"] = "EXPEDITED"
        save_table_records(DATA_DIR, "purchase_orders", pos)

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
    if os.path.exists(os.path.join(DATA_DIR, "inventory.json")):
        seed_all_data(DATA_DIR)
    if os.path.exists(AUDIT_LOG_FILE):
        os.remove(AUDIT_LOG_FILE)
    st.success("Benchmark state restored!")
    st.rerun()


# Session state for Chaos events
if "chaos_events" not in st.session_state:
    st.session_state.chaos_events = []

raw_inventory = []
raw_sales = []
inv_json = os.path.join(DATA_DIR, "inventory.json")
inv_csv = os.path.join(DATA_DIR, "inventory.csv")
if os.path.exists(inv_json):
    with open(inv_json, "r", encoding="utf-8") as f:
        raw_inventory = json.load(f)
elif os.path.exists(inv_csv):
    raw_inventory = pd.read_csv(inv_csv).to_dict("records")

sales_json = os.path.join(DATA_DIR, "sales.json")
sales_csv = os.path.join(DATA_DIR, "sales.csv")
if os.path.exists(sales_json):
    with open(sales_json, "r", encoding="utf-8") as f:
        raw_sales = json.load(f)
elif os.path.exists(sales_csv):
    raw_sales = pd.read_csv(sales_csv).to_dict("records")

inventory_df = pd.DataFrame(raw_inventory) if raw_inventory else pd.DataFrame(columns=["sku", "location", "stock"])
network_topology = extract_network_topology(inventory_df)

# ---------------------------------------------------------
# SIDEBAR CONTROLS
# ---------------------------------------------------------
with st.sidebar:
    st.markdown(f"<h3 style='color: {tokens['text_primary']}; margin-top: 0; font-size: 1.25rem; font-weight: 700;'>⚙️ Operating Controls</h3>", unsafe_allow_html=True)
    sim_date_input = st.text_input("Simulation Date", value="2026-11-16")
    current_date_str = sim_date_input.replace("/", "-").strip() or "2026-11-16"

    st.markdown(f"<hr style='border: none; border-top: 1px solid {tokens['border']}; margin: 16px 0;'>", unsafe_allow_html=True)
    
    st.markdown(f"<h4 style='color: {tokens['text_primary']}; font-size: 1.05rem; font-weight: 700; margin-bottom: 8px;'>User Persona:</h4>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="background-color: {tokens['surface_alt']}; border: 1px solid {tokens['border']}; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px;">
        <div style="font-size: 1.0rem; font-weight: 700; color: {tokens['text_primary']};">👨‍💼 Ramesh Kulkarni</div>
        <div style="font-size: 0.88rem; color: {tokens['sage_accent']}; font-style: italic; margin-top: 2px;">Head of Purchasing</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"<h4 style='color: {tokens['text_primary']}; font-size: 1.05rem; font-weight: 700; margin-bottom: 8px;'>Operations Network:</h4>", unsafe_allow_html=True)
    stores_list = network_topology["stores"]
    hubs_list = network_topology["warehouses"]
    st.markdown(f"""
    <div style="background-color: {tokens['surface_alt']}; border: 1px solid {tokens['border']}; border-radius: 8px; padding: 12px 14px; margin-bottom: 16px; font-size: 0.9rem; line-height: 1.6;">
        <div style="color: {tokens['text_primary']}; margin-bottom: 8px;"><strong style="color: {tokens['sage_primary']};">🏬 {len(stores_list)} Stores:</strong> {', '.join(stores_list)}</div>
        <div style="color: {tokens['text_primary']};"><strong style="color: {tokens['sage_primary']};">🏭 {len(hubs_list)} Hubs:</strong> {', '.join(hubs_list)}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"<hr style='border: none; border-top: 1px solid {tokens['border']}; margin: 16px 0;'>", unsafe_allow_html=True)
    st.markdown(f"<h4 style='color: {tokens['text_primary']}; font-size: 1.05rem; font-weight: 700; margin-bottom: 6px;'>⚡ Chaos Engine</h4>", unsafe_allow_html=True)
    st.markdown(f"<p style='color: {tokens['text_secondary']}; font-size: 0.9rem; font-weight: 500; margin-bottom: 12px;'>Inject shocks to evaluate real-time agent adaptability:</p>", unsafe_allow_html=True)
    
    if st.button("🌪️ 3x Demand Spike (Gokak)", use_container_width=True):
        inject_chaos("DEMAND_SPIKE")
    if st.button("🚧 Block Belgaum Route", use_container_width=True):
        inject_chaos("TRANSFER_ROADBLOCK")
    if st.button("📈 Vendor Delay (+5 Days)", use_container_width=True):
        inject_chaos("SUPPLIER_HIKE")
    if st.button("🔄 Reset to Benchmark Baseline", use_container_width=True):
        reset_baseline()

    if st.session_state.chaos_events:
        st.warning(f"⚠️ {len(st.session_state.chaos_events)} active chaos event(s)")
        if st.button("🧹 Clear Injected Chaos", use_container_width=True):
            st.session_state.chaos_events = []
            st.rerun()


# ==============================================================================
# 3. RUN ENGINE & DATA LOAD
# ==============================================================================
engine = DecisionEngine(
    data_dir=DATA_DIR,
    current_date=current_date_str,
    chaos_events=st.session_state.chaos_events
)
briefing = engine.run_agentic_pipeline()
audit_log = load_audit()
approved_problem_ids = {a["problem_id"] for a in audit_log}


# ---------------------------------------------------------
# EXECUTIVE HEADER & KPI STRIP
# ---------------------------------------------------------
st.markdown(f"""
<div class="top-banner">
    <div>
        <h1 style="margin: 0; font-size: 1.85rem; font-weight: 800; color: {tokens['text_primary']};">Kaveri Spares & Hydraulics</h1>
        <p style="margin: 4px 0 0 0; color: {tokens['text_secondary']}; font-size: 0.92rem;">
            Autonomous Supply Chain Copilot & Purchasing Colleague for Ramesh Kulkarni
        </p>
    </div>
    <div style="background-color: {tokens['surface_alt']}; border: 1px solid {tokens['border']}; border-radius: 8px; padding: 6px 14px; font-size: 0.85rem; font-weight: 600; color: {tokens['text_secondary']};">
        Cypher 2026 • Challenge 01
    </div>
</div>
""", unsafe_allow_html=True)

if st.session_state.chaos_events:
    from engine.domain_math import compute_plan_diff
    engine_base = DecisionEngine(data_dir=DATA_DIR, current_date=current_date_str, chaos_events=[])
    brief_base = engine_base.run_agentic_pipeline()
    plan_diff = compute_plan_diff(brief_base, briefing, st.session_state.chaos_events[-1])

    st.error(f"🚨 **CHAOS INJECTION ACTIVE:** System is operating under {len(st.session_state.chaos_events)} live operational shock(s).")
    with st.expander("⚡ **CHAOS PLAN DIFF (Before-Shock vs After-Shock Adaptation)**", expanded=True):
        st.markdown(f"<div style='font-size: 0.88rem; color: {tokens['text_secondary']}; margin-bottom: 8px;'><b>Autonomous Adaptations:</b> {plan_diff['total_changed_plans']} of {plan_diff['total_problems']} recommendations shifted dynamically.</div>", unsafe_allow_html=True)
        for d in plan_diff["diffs"]:
            if d["has_changed"]:
                bp = d["before_plan"] or {}
                ap = d["after_plan"] or {}
                st.markdown(f"""
                <div style="background-color: {tokens['surface_alt']}; border: 1px solid {tokens['border']}; border-left: 4px solid {tokens['alert_amber']}; border-radius: 6px; padding: 10px 14px; margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; font-weight: 700; color: {tokens['text_primary']}; font-size: 0.92rem;">
                        <span>📍 {d['location']} — {d['sku']} ({d['problem_id']})</span>
                        <span style="color: {tokens['alert_amber']}; font-size: 0.82rem; font-weight: 700;">PLAN ADAPTATION</span>
                    </div>
                    <div style="display: flex; gap: 20px; font-size: 0.84rem; margin: 6px 0; font-family: monospace; flex-wrap: wrap;">
                        <span style="color: {tokens['text_secondary']};">BEFORE: {bp.get('action_type', 'N/A')} from {bp.get('source', 'N/A')} ({bp.get('qty', 0)}u @ ₹{bp.get('cost_inr', 0):,.0f})</span>
                        <span style="color: {tokens['sage_accent']};">➔ AFTER: {ap.get('action_type', 'N/A')} from {ap.get('source', 'N/A')} ({ap.get('qty', 0)}u @ ₹{ap.get('cost_inr', 0):,.0f})</span>
                    </div>
                    <div style="font-size: 0.84rem; color: {tokens['text_secondary']};"><b>Reason for Change:</b> {d['change_reason']}</div>
                </div>
                """, unsafe_allow_html=True)


summary = briefing["summary"]
pending_count = sum(1 for p in briefing["problems"] if p["problem_id"] not in approved_problem_ids)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""
    <div class="kpi-box">
        <span class="kpi-title">Total Operational Issues</span>
        <div class="kpi-number">{summary["total_problems_detected"]}</div>
        <span class="kpi-foot-green">↑ Across 8 Nodes</span>
    </div>
    """, unsafe_allow_html=True)
with k2:
    st.markdown(f"""
    <div class="kpi-box">
        <span class="kpi-title">Critical Stockouts</span>
        <div class="kpi-number" style="color: {tokens['alert_crimson']};">{summary["critical_actions_required"]}</div>
        <span class="kpi-foot-red">↑ Immediate Action Needed</span>
    </div>
    """, unsafe_allow_html=True)
with k3:
    st.markdown(f"""
    <div class="kpi-box">
        <span class="kpi-title">Top Attention SKU</span>
        <div class="kpi-number" style="font-size: 1.55rem; line-height: 1.35; color: {tokens['sage_primary']};">{summary["top_focus_sku"]}</div>
        <span class="kpi-foot-green">↑ Hydraulic Filtration</span>
    </div>
    """, unsafe_allow_html=True)
with k4:
    st.markdown(f"""
    <div class="kpi-box">
        <span class="kpi-title">Pending Human Gate</span>
        <div class="kpi-number">{pending_count}</div>
        <span class="kpi-foot-green">↑ {len(audit_log)} Decisions Logged</span>
    </div>
    """, unsafe_allow_html=True)

# Historical Backtest Headline Strip
@st.cache_data(ttl=3600)
def load_backtest_headline():
    try:
        from scripts.backtest import run_backtest
        return run_backtest(DATA_DIR, days=60)
    except Exception:
        return None

bt_data = load_backtest_headline()
if bt_data:
    st.markdown(f"""
    <div style="background: {tokens['surface_alt']}; border: 1px solid {tokens['border']}; border-left: 4px solid {tokens['sage_primary']}; border-radius: 8px; padding: 10px 16px; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
        <div style="font-size: 0.88rem; color: {tokens['text_primary']};">
            <strong style="color: {tokens['sage_primary']};">📈 60-Day Historical Backtest:</strong> Replayed {bt_data['days_simulated']} days across 8 network facilities.
        </div>
        <div style="display: flex; gap: 18px; font-family: monospace; font-size: 0.86rem; flex-wrap: wrap;">
            <span>Stockouts Prevented: <strong style="color: {tokens['sage_accent']};">+{bt_data['stockouts_prevented']}</strong></span>
            <span>Lost Units Averted: <strong style="color: {tokens['sage_primary']};">+{bt_data['lost_units_averted']}</strong></span>
            <span>Capital Saved: <strong style="color: {tokens['alert_amber']};">₹{bt_data['rs_saved']:,.0f}</strong></span>
            <span>Net ROI: <strong style="color: {tokens['sage_accent']};">+{bt_data['roi_percent']}%</strong></span>
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
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
# 3. PLOTLY THEME UNIFICATION FUNCTION
# ==============================================================================
def format_cyber_plotly_figure(fig: go.Figure, is_dark_mode: bool = None) -> go.Figure:
    """Enforces Sage Green dual-mode theme across Plotly trajectory curves."""
    if is_dark_mode is None:
        is_dark_mode = (st.session_state.get("theme_mode", "Dark") == "Dark")
        
    bg_color = "#121711" if is_dark_mode else "#F4F6F0"
    paper_color = "#171D16" if is_dark_mode else "#FFFFFF"
    text_color = "#9DAE97" if is_dark_mode else "#5D6656"
    grid_color = "#2C3A2A" if is_dark_mode else "#CBD5C0"
    
    fig.update_layout(
        plot_bgcolor=bg_color,
        paper_bgcolor=paper_color,
        font=dict(color=text_color, family='-apple-system, BlinkMacSystemFont, Segoe UI, Roboto'),
        xaxis=dict(gridcolor=grid_color, zerolinecolor=grid_color, linecolor=grid_color),
        yaxis=dict(gridcolor=grid_color, zerolinecolor=grid_color, linecolor=grid_color),
        legend=dict(
            bgcolor=paper_color,
            bordercolor=grid_color,
            borderwidth=1,
            font=dict(color=text_color, size=10),
            orientation='h',
            yanchor='top',
            y=-0.22,
            xanchor='center',
            x=0.5
        ),
        margin=dict(l=35, r=25, t=40, b=65)
    )
    return fig


def render_sage_trajectory_chart(projections: dict, title: str, is_dark_mode: bool = None) -> go.Figure:
    """Adaptive 14-day forward visual trajectory graph adhering to Sage Design Tokens."""
    if is_dark_mode is None:
        is_dark_mode = (st.session_state.get("theme_mode", "Dark") == "Dark")
        
    days = projections["days"]
    bg_color = "#121711" if is_dark_mode else "#F4F6F0"
    paper_color = "#171D16" if is_dark_mode else "#FFFFFF"
    text_color = "#9DAE97" if is_dark_mode else "#5D6656"
    grid_color = "#2C3A2A" if is_dark_mode else "#CBD5C0"
    line_sage = "#B2CF9C" if is_dark_mode else "#5B7053"
    fill_sage = "rgba(178, 207, 156, 0.12)" if is_dark_mode else "rgba(91, 112, 83, 0.12)"
    alert_red = "#FF5C5C" if is_dark_mode else "#C84B31"
    alert_amber = "#F59E0B" if is_dark_mode else "#D9822B"

    fig = go.Figure()

    # Monte Carlo fan chart if present
    fan = projections.get("fan_chart", {}).get("transfer") or projections.get("probabilistic", {}).get("transfer")
    if fan and "p10" in fan and "p90" in fan:
        fig.add_trace(go.Scatter(
            x=days + days[::-1],
            y=fan["p90"] + fan["p10"][::-1],
            fill="toself",
            fillcolor=fill_sage,
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="skip",
            showlegend=True,
            name="80% Projection Range"
        ))

    # Option 1: Network Transfer
    fig.add_trace(go.Scatter(
        x=days, y=projections["transfer"],
        mode="lines+markers",
        name="Opt 1: Inter-Store Transfer (Day 1)",
        line=dict(color=line_sage, width=3.5),
        marker=dict(size=7, color=line_sage)
    ))

    # Option 2: Expedited Vendor PO
    fig.add_trace(go.Scatter(
        x=days, y=projections["expedited"],
        mode="lines+markers",
        name="Opt 2: Expedited PO (Day 3)",
        line=dict(color=alert_amber, width=2.5, dash="dash"),
        marker=dict(size=6, color=alert_amber)
    ))

    # Option 3: Status Quo
    fig.add_trace(go.Scatter(
        x=days, y=projections["status_quo"],
        mode="lines+markers",
        name="Opt 3: Status Quo Baseline",
        line=dict(color=alert_red, width=2.5, dash="dot"),
        marker=dict(size=6, color=alert_red)
    ))

    # Stockout Hazard Area / Line
    fig.add_hline(
        y=0,
        line_dash="dash",
        line_color=alert_red,
        line_width=1.5,
        annotation_text="⚠️ Stockout Hazard Line (Zero Stock)",
        annotation_position="top right",
        annotation_font=dict(color=alert_red, size=10)
    )

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=13, color="#F1F5EE" if is_dark_mode else "#1E241B"),
            x=0.01,
            y=0.98,
            xanchor="left",
            yanchor="top"
        ),
        xaxis=dict(title="Days Ahead", dtick=1, gridcolor=grid_color, zerolinecolor=grid_color),
        yaxis=dict(title="Projected Stock (Units)", gridcolor=grid_color, zerolinecolor=grid_color),
        hovermode="x unified",
        height=340
    )
    fig = format_cyber_plotly_figure(fig, is_dark_mode=is_dark_mode)
    return fig


def render_cyber_table(df: pd.DataFrame, is_dark_mode: bool = None):
    """Renders a pixel-perfect Sage HTML table adapting to active theme."""
    if is_dark_mode is None:
        is_dark_mode = (st.session_state.get("theme_mode", "Dark") == "Dark")

    if df.empty:
        st.info("No records to display.")
        return
    headers = "".join(f"<th>{col}</th>" for col in df.columns)
    
    txt_col = "#F1F5EE" if is_dark_mode else "#1E241B"
    badge_green_bg = "#20291F" if is_dark_mode else "#E8EDE0"
    badge_green_txt = "#8FA87B" if is_dark_mode else "#5B7053"
    badge_green_border = "#2C3A2A" if is_dark_mode else "#CBD5C0"
    
    rows_html = []
    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            val = str(row[col])
            if "HIGH (Locked Capital)" in val or val == "CRITICAL" or "REJECTED" in val or "INFEASIBLE" in val:
                cells.append(f'<td><span class="badge-critical" style="padding: 3px 8px;">{val}</span></td>')
            elif "MEDIUM" in val or val == "HIGH":
                cells.append(f'<td><span class="badge-high" style="padding: 3px 8px;">{val}</span></td>')
            elif "LOW" in val or "FEASIBLE" in val or "APPROVED" in val:
                cells.append(f'<td><span style="background-color: {badge_green_bg}; color: {badge_green_txt}; border: 1px solid {badge_green_border}; padding: 3px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 700;">{val}</span></td>')
            elif "Primary" in val:
                cells.append(f'<td><span class="badge-tag" style="padding: 3px 8px;">{val}</span></td>')
            elif col in ["Current Stock", "MOQ (Units)", "qty", "Lead Time (Days)", "Delivery Time"]:
                cells.append(f'<td style="font-family: \'JetBrains Mono\', monospace; font-weight: 600; color: {txt_col};">{val}</td>')
            elif col in ["Contract Price", "Total Cash Outlay", "cost_inr"]:
                cells.append(f'<td style="font-family: \'JetBrains Mono\', monospace; font-weight: 600; color: {badge_green_txt};">{val}</td>')
            else:
                cells.append(f'<td style="color: {txt_col};">{val}</td>')
        rows_html.append(f"<tr>{''.join(cells)}</tr>")
    
    table_html = f"""
    <div class="cyber-table-container">
        <table class="cyber-table">
            <thead>
                <tr>{headers}</tr>
            </thead>
            <tbody>
                {''.join(rows_html)}
            </tbody>
        </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ==============================================================================
# RESOLUTION COCKPIT RENDERER (RIGHT COLUMN 62% IN PIC 1 WITH PIC 2 PALETTE)
# ==============================================================================
def render_cyber_detail_cockpit(p, approved_problem_ids, raw_inventory, raw_sales):
    pid = p["problem_id"]
    is_handled = pid in approved_problem_ids
    cat_code = p.get("category_code", "CATEGORY_A")

    sev = p.get("severity", "MEDIUM")
    badge_cls = "badge-critical" if sev == "CRITICAL" else ("badge-high" if sev == "HIGH" else "badge-medium")
    sev_color = tokens['alert_crimson'] if sev == "CRITICAL" else (tokens['alert_amber'] if sev == "HIGH" else tokens['sage_accent'])
    status_banner = "✅ ALREADY EXECUTED" if is_handled else "⚡ AWAITING RAMESH KULKARNI APPROVAL"

    # 1. Headline Container
    st.markdown(f"""
    <div class="diag-container" style="border-left: 4px solid {sev_color};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div>
                <span class="{badge_cls}">[{sev}]</span>
                <span class="badge-cat">{cat_code}</span>
                <span style="font-weight: 700; font-size: 1.15rem; color: {tokens['text_primary']}; margin-left: 8px;">{p['sku_name']} ({p['sku']})</span>
                <span style="color: {tokens['text_secondary']}; margin-left: 8px;">📍 <b>{p['location']}</b></span>
            </div>
            <div>
                <span style="font-size: 0.8rem; font-weight: 700; color: {tokens['sage_accent'] if is_handled else tokens['alert_amber']};">
                    {status_banner}
                </span>
            </div>
        </div>
        <p style="color: {tokens['text_secondary']}; margin: 6px 0 0 0; font-size: 0.95rem;">
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

    trend_color = tokens['alert_crimson'] if trend_label == "ACCELERATING" else (tokens['alert_amber'] if trend_label == "DECELERATING" else tokens['sage_accent'])
    cover_color = tokens['alert_crimson'] if m['days_of_cover'] <= 3.0 else (tokens['alert_amber'] if m['days_of_cover'] <= 7.0 else tokens['sage_accent'])
    gap_color = tokens['alert_crimson'] if m['stockout_gap_days'] > 0 else tokens['sage_accent']

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
<div class="math-terminal">
    <div style="color: {tokens['sage_primary']}; font-weight: 700; font-size: 0.92rem; margin-bottom: 8px; letter-spacing: 0.02em;">📐 DETERMINISTIC DOMAIN MATH &amp; TELEMETRY AUDIT:</div>
    <div style="margin-bottom: 4px;">• <b>Velocity:</b> <span style="color: {tokens['sage_accent']}; font-weight: 600;">{me.get('formula_velocity', '')}</span></div>
    <div style="margin-bottom: 4px;">• <b>Days of Cover:</b> <span style="color: {tokens['alert_amber']}; font-weight: 600;">{me.get('formula_cover', '')}</span></div>
    <div style="margin-bottom: 4px;">• <b>Deficit Gap:</b> <span style="color: {tokens['alert_crimson']}; font-weight: 700;">{me.get('formula_gap', '')}</span></div>
    <div>• <b>Commercial Risk Exposure:</b> Lead Time T = <span style="color: {tokens['sage_primary']}; font-weight: 600;">{me.get('T', 7)}d</span> | Margin = <span style="color: {tokens['sage_accent']}; font-weight: 600;">₹{me.get('unit_margin_inr', 0):,.2f}/unit</span> | Potential Lost Revenue = <span style="color: {tokens['alert_crimson']}; font-weight: 700;">₹{me.get('projected_lost_revenue_inr', 0):,.2f}</span></div>
</div>
""", unsafe_allow_html=True)

    # 4. Commercial Impact Scorecard (Rule 5)
    sc = p.get("scorecard", {})
    m_gap = m.get("stockout_gap_days", 0.0)
    net_cost_str = sc.get("net_cost_str", "₹250.00")
    lost_units_str = sc.get("lost_units_str", "0.0 units")
    wc_outflow_str = sc.get("working_capital_outflow_str", "₹0.00")
    dt_risk_str = sc.get("downtime_risk_str", "0 Days")

    st.markdown("##### 💳 Commercial Impact Scorecard (Options Trade-off Matrix)")
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        st.markdown(f"""
        <div class="scorecard-card">
            <div class="scorecard-label">Net Direct Cost</div>
            <div class="scorecard-val" style="color: {tokens['sage_accent']};">{net_cost_str}</div>
            <div class="scorecard-sub">Incremental Decision Outlay</div>
        </div>
        """, unsafe_allow_html=True)
    with sc2:
        st.markdown(f"""
        <div class="scorecard-card">
            <div class="scorecard-label">Lost Units Averted</div>
            <div class="scorecard-val" style="color: {tokens['sage_primary']};">{lost_units_str}</div>
            <div class="scorecard-sub">Protected vs Inaction Deficit</div>
        </div>
        """, unsafe_allow_html=True)
    with sc3:
        st.markdown(f"""
        <div class="scorecard-card">
            <div class="scorecard-label">Working Capital Outflow</div>
            <div class="scorecard-val" style="color: {tokens['sage_accent']};">{wc_outflow_str}</div>
            <div class="scorecard-sub">New Capital Committed</div>
        </div>
        """, unsafe_allow_html=True)
    with sc4:
        is_safe_dt = (dt_risk_str == "0 Days" or dt_risk_str == "0.0 Days")
        st.markdown(f"""
        <div class="scorecard-card">
            <div class="scorecard-label">Downtime Risk</div>
            <div class="scorecard-val" style="color: {tokens['sage_accent'] if is_safe_dt else tokens['alert_crimson']};">{dt_risk_str}</div>
            <div class="scorecard-sub">Deficit Runway Remaining</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # 5. Interactive Sage Plotly Forward Trajectory Graph
    fp = p.get("forward_projections")
    if fp and "days" in fp:
        st.markdown("##### 📈 14-Day Forward Visual Inventory Trajectories")
        
        # Probabilistic Monte Carlo Telemetry Badge
        prob_data = fp.get("stockout_probability_by_day_14", {})
        sq_risk = prob_data.get("status_quo", 0.0)
        tr_risk = prob_data.get("transfer", 0.0)
        ex_risk = prob_data.get("expedited", 0.0)
        
        st.markdown(f"""
        <div style="background-color: {tokens['surface_alt']}; border: 1px solid {tokens['border']}; border-radius: 6px; padding: 6px 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; font-size: 0.84rem; flex-wrap: wrap; gap: 8px;">
            <div style="color: {tokens['text_primary']};"><strong style="color: {tokens['sage_primary']};">🎲 Monte Carlo Risk (500 seeded runs):</strong> Stockout Probability by Day 14</div>
            <div style="display: flex; gap: 14px; font-family: monospace;">
                <span>Status Quo: <strong style="color: {tokens['alert_crimson'] if sq_risk > 0.5 else tokens['alert_amber']};">{sq_risk * 100:.1f}%</strong></span>
                <span>Expedited PO: <strong style="color: {tokens['alert_amber'] if ex_risk > 0.2 else tokens['sage_accent']};">{ex_risk * 100:.1f}%</strong></span>
                <span>Inter-Store Transfer: <strong style="color: {tokens['sage_accent']};">{tr_risk * 100:.1f}%</strong></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        fig = render_sage_trajectory_chart(fp, f"Projected Inventory Levels: {p['sku_name']} @ {p['location']}", is_dark_mode=is_dark)
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
    render_cyber_table(pd.DataFrame(opt_data), is_dark_mode=is_dark)
    st.markdown(f"**🎯 AI Agent Recommendation Rationale:** {p['decision_rationale']}")

    # 7. Action Draft Execution Box
    act = p["simulated_action"]
    pay = act["payload"]
    
    st.markdown(f"""
    <div class="action-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <div>
                <span class="badge-action">Simulated Action: {act['action_type']}</span>
                <span style="margin-left: 0.5rem; font-weight: 700; font-size: 0.95rem; color: {tokens['sage_accent']};">
                    Quantity: {pay['qty']} units • Total Estimated Cost: ₹{pay['total_estimated_cost_inr']:,.2f}
                </span>
            </div>
            <div style="font-size: 0.85rem; color: {tokens['sage_primary']}; font-weight: 600;">
                Expected Arrival: {pay['expected_delivery_date']}
            </div>
        </div>
        <div style="font-size: 0.9rem; color: {tokens['text_secondary']};">
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
                    name=f"Counter-Proposal ({override_qty}u)",
                    line=dict(color=tokens['sage_accent'], width=3),
                    marker=dict(size=6, color=tokens['sage_accent'])
                ))
                if fp and "transfer" in fp:
                    fig_ov.add_trace(go.Scatter(
                        x=fp["days"],
                        y=fp["transfer"],
                        mode="lines+markers",
                        name=f"AI Draft Baseline ({pay['qty']}u)",
                        line=dict(color=tokens['text_secondary'], width=2, dash="dash"),
                        marker=dict(size=5, color=tokens['text_secondary'])
                    ))
                fig_ov.add_hline(
                    y=0,
                    line_dash="dash",
                    line_color=tokens['alert_crimson'],
                    annotation_text="Hazard Line",
                    annotation_position="top right",
                    annotation_font=dict(color=tokens['alert_crimson'], size=10)
                )
                fig_ov.update_layout(
                    title=dict(
                        text=f"Dynamic Recalibration: Ramesh ({override_qty}u) vs AI Draft ({pay['qty']}u)",
                        font=dict(size=12, color=tokens['text_primary']),
                        x=0.01,
                        y=0.98,
                        xanchor="left",
                        yanchor="top"
                    ),
                    xaxis=dict(title="Days Ahead", dtick=1),
                    yaxis=dict(title="Stock (Units)"),
                    height=270
                )
                fig_ov = format_cyber_plotly_figure(fig_ov)
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


# ---------------------------------------------------------
# MAIN WORKSPACE & TABS
# ---------------------------------------------------------
with tab_feed:
    # Split: Left (Task List 38%) | Right (Cockpit Workspace 62%)
    col_feed, col_cockpit = st.columns([0.38, 0.62], gap="large")

    # --- LEFT COLUMN: STACKED TASK WORKLIST ---
    with col_feed:
        st.markdown("#### 📋 Morning Operational Tasks")
        st.caption("Select an incident to evaluate alternatives and take action:")

        all_problems = briefing.get("problems", [])

        # Severity Filter Dropdown Menu
        sev_filter = st.selectbox(
            "Filter Severity:",
            ["All", "CRITICAL", "HIGH", "MEDIUM"],
            index=0,
            key="task_severity_filter"
        )

        if sev_filter != "All":
            problems = [p for p in all_problems if p.get("severity") == sev_filter]
        else:
            problems = all_problems

        if not st.session_state.get("selected_problem_id") and problems:
            st.session_state.selected_problem_id = problems[0]["problem_id"]
        elif st.session_state.get("selected_problem_id") and problems and not any(p["problem_id"] == st.session_state.selected_problem_id for p in problems):
            st.session_state.selected_problem_id = problems[0]["problem_id"]

        if not problems:
            st.info(f"No active incidents match severity filter '{sev_filter}'.")

        for prob in problems:
            pid = prob["problem_id"]
            is_active = pid == st.session_state.get("selected_problem_id")
            active_class = "incident-card-active" if is_active else ""
            sev = prob.get("severity", "MEDIUM")
            badge_style = "badge-critical" if sev == "CRITICAL" else "badge-tag"

            m_p = prob.get("domain_metrics", {})
            stock_v = m_p.get("current_stock", prob.get("current_stock", 0))
            cover_v = m_p.get("days_of_cover", prob.get("days_of_cover", 0.0))
            gap_v = m_p.get("stockout_gap_days", prob.get("stockout_gap_days", 0.0))

            st.markdown(
                f"""
                <div class="incident-card {active_class}">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <div>
                            <span class="{badge_style}">{sev}</span>
                            <span class="badge-tag">{prob.get('category_code', '')}</span>
                        </div>
                        <span style="font-size: 0.72rem; color: {tokens['alert_amber']}; font-weight: 600;">⚡ ACTION REQUIRED</span>
                    </div>
                    <div style="font-weight: 700; font-size: 1.0rem; color: {tokens['text_primary']}; margin-bottom: 2px;">
                        {prob.get('location', '')} — {prob.get('sku', '')}
                    </div>
                    <div style="font-size: 0.8rem; color: {tokens['text_secondary']};">
                        Stock: <b style="color: {tokens['text_primary']};">{stock_v}</b> | 
                        Cover: <b style="color: {tokens['text_primary']};">{cover_v:.1f}d</b> | 
                        Gap: <b style="color: {tokens['alert_crimson']};">{gap_v:.1f}d</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            btn_label = "● Active Task" if is_active else "Inspect Evidence ➔"
            if st.button(btn_label, key=f"task_btn_{pid}", use_container_width=True, disabled=is_active):
                st.session_state.selected_problem_id = pid
                st.rerun()

    # --- RIGHT COLUMN: COCKPIT, MATH AUDIT & PROJECTIONS ---
    with col_cockpit:
        active_pid = st.session_state.get("selected_problem_id")
        active_item = next((p for p in problems if p["problem_id"] == active_pid), None)

        if active_item:
            render_cyber_detail_cockpit(active_item, approved_problem_ids, raw_inventory, raw_sales)
        else:
            st.info("Select an active incident from the morning queue.")


# ==============================================================================
# TAB 2: MULTI-ECHELON INVENTORY
# ==============================================================================
with tab_inv:
    st.subheader("North Karnataka Multi-Echelon Stock Levels")
    
    datasets = load_validated_datasets(DATA_DIR)
    inv_raw = datasets["inventory"]
    prods_raw = datasets["products"]
        
    p_map = {p["sku"]: p for p in prods_raw}
    enriched_inv = []
    for row in inv_raw:
        prod = p_map.get(row["sku"], {})
        enriched_inv.append({
            "SKU": row["sku"],
            "Product Name": prod.get("name") or prod.get("product_name", "Unknown"),
            "Category": prod.get("category", "General"),
            "Machine Model": prod.get("machine_model", "Universal"),
            "Location": row["location"],
            "Current Stock": row["stock"]
        })
    df_inv = pd.DataFrame(enriched_inv)
    
    sku_filter = st.selectbox("Filter by SKU:", ["All"] + sorted(list(df_inv["SKU"].unique())))
    if sku_filter != "All":
        df_inv = df_inv[df_inv["SKU"] == sku_filter]
        
    render_cyber_table(df_inv)


# ==============================================================================
# TAB 3: SUPPLIER FRICTION & RELIABILITY AUDIT
# ==============================================================================
with tab_sup:
    st.subheader("Contracted Supplier Friction & Reliability Learning Audit")
    st.caption("Assesses suppliers on price markup, MOQ lock-up, historical delivery slippage, and learned adjusted lead times.")
    
    datasets = load_validated_datasets(DATA_DIR)
    sup_data = datasets["suppliers"]
    
    rel_map = briefing.get("supplier_reliability", {})
    base_map = {}
    for s in sup_data:
        if s.get("is_primary", False) and s["sku"] not in base_map:
            base_map[s["sku"]] = float(s["price"])
    for s in sup_data:
        if s["sku"] not in base_map:
            base_map[s["sku"]] = float(s["price"])
    aud_rows = []
    for s in sup_data:
        bp = base_map.get(s["sku"], s["price"])
        var = round(((s["price"] - bp) / bp) * 100.0, 1) if bp > 0 else 0.0
        rel = rel_map.get(s["supplier"], {})
        slip = rel.get("avg_slippage_days", 0.0)
        adj_lead = rel.get("adjusted_lead_time_days", s.get("lead_time_days", 7))
        ot_rate = rel.get("on_time_rate", 1.0)
        rel_status = rel.get("reliability_status", "RELIABLE")

        aud_rows.append({
            "Supplier Name": s["supplier"],
            "Target SKU": s["sku"],
            "Tier": "Primary" if s.get("is_primary", False) else "Secondary / Rush",
            "Contract Price": f"₹{s['price']:,.2f}",
            "Quoted Lead Time": f"{s.get('quoted_lead_time_days', s.get('lead_time_days', 7))}d",
            "Historical Slippage": f"+{slip:.1f}d" if slip > 0 else "0.0d",
            "Adjusted Lead Time": f"{adj_lead}d",
            "On-Time Rate": f"{int(ot_rate * 100)}%",
            "Reliability Status": rel_status,
            "MOQ (Units)": s["moq"],
            "MOQ Friction Risk": "HIGH (Locked Capital)" if s["moq"] >= 50 else ("MEDIUM" if s["moq"] >= 20 else "LOW")
        })
    render_cyber_table(pd.DataFrame(aud_rows))


# ==============================================================================
# TAB 4: AUDIT TRAIL
# ==============================================================================
with tab_audit:
    st.subheader("Governance & Human Sign-off Audit Trail")
    st.caption("Immutable record of purchasing colleague interactions and approval gates.")
    
    if audit_log:
        df_audit = pd.DataFrame(audit_log)
        render_cyber_table(df_audit)
    else:
        st.info("No approval actions executed yet today. Review the Morning Feed to approve proposed actions.")
