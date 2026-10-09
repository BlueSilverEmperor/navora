# Kaveri Spares & Hydraulics — Autonomous Supply Chain Copilot

[![Tests](https://img.shields.io/badge/pytest-64%20passed-brightgreen.svg)](tests/test_decisions.py)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-teal.svg)](app/server.py)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.32+-red.svg)](app/dashboard.py)

**Track:** Cypher 2026 — Hackathon Challenge 01 (Agentic AI for Supply Chain)  
**Persona:** AI Purchasing Colleague for **Ramesh Kulkarni** (Head of Purchasing)  
**Operational Scope:** 6 Retail Branches (Gokak, Belgaum, Dharwad, Hubli, Bagalkot, Nippani) & 2 Distribution Hubs (Belgaum Central Warehouse, Hubli Regional Warehouse) across North Karnataka.

---

## 🚀 Executive Summary

The **Kaveri Supply Chain Copilot** is a production-hardened, deterministic multi-echelon decision engine and executive cockpit. It monitors industrial equipment spare parts consumption across North Karnataka, detects emerging supply chain friction points, balances network inventory via lateral transfers, executes mathematical integer linear programming optimization, and generates simulated Human-in-the-Loop approval actions.

### Core Architectural Principles
1. **Deterministic Domain Mathematics:** All velocities, days of cover, stockout gaps, costs, margins, and forward trajectories are computed deterministically in Python (`engine/domain_math.py`, `engine/decision_agent.py`, `engine/global_optimizer.py`). An LLM never computes or hallucinates numbers.
2. **Grounded Ingestions:** Every operational value is grounded in the 5 core operational tables (`products`, `inventory`, `sales`, `suppliers`, `purchase_orders`) or configured in `engine/config.py`.
3. **Pydantic Validation & Schema Resilience:** Ingestion pipeline validates inputs with case-insensitivity, column order tolerance, alias resolution, and supports both JSON and CSV formats (`engine/data_loader.py`).
4. **Autonomous Global Optimization:** Multi-echelon lateral inventory transfers solved via Integer Linear Programming (SciPy HiGHS MIP) preventing donor over-allocation and liquidating dead capital traps into active deficits (`engine/global_optimizer.py`).
5. **Monte Carlo Probabilistic Projections:** Seeded 500-run stochastic demand simulations produce 14-day fan charts (p10, p50, p90) and cumulative day-14 stockout risk curves (`engine/domain_math.py`).
6. **Supplier Reliability Learning:** Dynamically learns vendor slippage from historical delivery performance and adjusts operational lead times (`engine/domain_math.py`).
7. **Operator Rejection Memory & Soft Constraints:** Persistent SQLite memory remembers human rejection rationale and applies soft constraint penalties to elevate viable alternatives (`engine/persistence.py`).
8. **Plan Diff on Chaos:** Dynamic runtime anomaly injection evaluates before vs after operational plans with transparent reasoning (`engine/domain_math.py`).

---

## 🏛️ Comprehensive Problem Coverage

| Category | Problem Type | Operational Root Cause | Autonomous Copilot Policy |
| :--- | :--- | :--- | :--- |
| **Category A** | `IMMINENT_STOCKOUT` | Days of Cover $< T_{\text{lead}}$, zero incoming POs | Lateral network transfer from qualified donor retaining $\ge 15.0$ days cover, or expedited vendor PO |
| **Category B** | `CAPITAL_TRAP` | Days of Cover $>$ dynamic SKU target cover ($\text{Lead} + \text{Review} + \text{Safety}$) | Multi-echelon rebalancing to starved network branches or vendor buyback request |
| **Category C** | `OVERDUE_PO` | Active PO past expected arrival date | Prioritized by days of cover impact; generates collaborative expedite notice draft |
| **Category D** | `DEMAND_VOLATILITY` | Recent 7-day velocity deviates sharply from 30-day baseline ($v_{\text{recent}} / v_{\text{base}} \ge 1.8$) | Surge transfer or factory replenishment sized to heightened burn rate over review period |
| **Category E** | `SUPPLIER_MISMATCH` | Supplier minimum order quantity (MOQ) or lead time friction | Evaluates carrying cost of excess MOQ and surfaces alternative fulfillment pathways |

---

## ⚡ Quick Start (Fresh Clone)

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/BlueSilverEmperor/navora.git
cd navora/kaveri_copilot
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Automated Test Suite (64 Verified Tests)
```bash
pytest -q
```
*Expected Output: `64 passed in ~10s` (0 warnings, 0 failures)*

### 4. Launch Application Services

**Option A — Automated Launcher (Windows):**
```cmd
run.bat
```

**Option B — Manual Launch:**
```bash
# Terminal 1: FastAPI Backend Service (Port 8000)
python -m uvicorn app.server:app --port 8000 --reload

# Terminal 2: Streamlit Executive Cockpit (Port 8501)
streamlit run app/dashboard.py --server.port 8501
```

Access the Streamlit Cockpit at: `http://localhost:8501`  
Access the FastAPI Interactive API Docs at: `http://localhost:8000/docs`

---

## 📁 Repository Directory Structure

```
kaveri_copilot/
├── app/
│   ├── dashboard.py             # Streamlit Executive Decision Cockpit
│   └── server.py                # FastAPI REST API (unified /api/* and /action/* routes)
├── data/
│   ├── products.json            # 6 industrial hydraulic SKUs
│   ├── inventory.json           # Multi-echelon stock levels across 8 locations
│   ├── sales.json               # 30-day transactional sales history
│   ├── suppliers.json           # Contracted vendors with lead times and MOQs
│   ├── purchase_orders.json     # Active, delayed, and in-transit purchase orders
│   └── copilot_storage.db       # SQLite WAL database (audit logs, reservations, rejection memory)
├── engine/
│   ├── config.py                # Single source of truth for all operational thresholds
│   ├── data_loader.py           # Pydantic schemas, alias resolution & CSV/JSON loader
│   ├── decision_agent.py        # DecisionEngine, option evaluator & action drafter
│   ├── domain_math.py           # Deterministic arithmetic, Monte Carlo, supplier reliability
│   ├── global_optimizer.py      # SciPy HiGHS MIP integer linear programming solver
│   ├── llm_layer.py             # Provider-agnostic LLM interface with strict NumberGuard
│   ├── mock_data_gen.py         # Seeds pristine benchmark data
│   └── persistence.py           # SQLite WAL transactions, idempotency & reservations
├── scripts/
│   └── backtest.py              # 60-day historical replay simulator vs naive baseline
├── tests/
│   └── test_decisions.py        # 64 automated unit and integration tests
├── requirements.txt             # Locked Python dependencies
├── run.bat                      # Windows launcher
├── run.sh                       # Linux/macOS launcher
├── FEATURES.md                  # Detailed 12-rule compliance audit & features
└── README.md                    # System documentation
```

---

## 🧪 Verified Test Suite Summary (64 Tests)

All 64 tests pass with zero warnings:

- **Mathematical Determinism & Safety:** `test_burn_rate_calculation`, `test_days_of_cover_calculation`, `test_stockout_gap_calculation`, `test_edge_case_zero_stock_and_zero_velocity_no_stockout`, `test_velocity_robustness_minimum_volume_and_ewma`
- **Objective Function Scoring:** `test_objective_function_scoring_and_ranking`, `test_objective_function_vendor_wins_when_transfer_expensive`, `test_objective_function_vendor_wins_when_no_safe_donor`, `test_scorecard_differentiates_across_incidents`
- **Grounded Projections & Monte Carlo:** `test_grounded_projections_data_driven_and_category_a_no_arrival`, `test_probabilistic_projections_monte_carlo_fan_chart_and_day_14_stockout_risk`
- **Global Optimizer & Backtest:** `test_global_transfer_optimizer_joint_solution_and_capital_trap`, `test_backtest_simulation_metrics`
- **Supplier Learning & Overdue POs:** `test_supplier_reliability_learning_slippage_and_adjusted_lead_time`, `test_overdue_po_cancellation_partial_delivery_and_softer_draft`
- **Chaos Resilience & Plan Diff:** `test_generic_route_block_and_supplier_delay_vs_price_hike`, `test_chaos_plan_diff_before_and_after_adaptation_with_reason`
- **Persistence & Rejection Memory:** `test_sqlite_persistence_idempotency_restart_409`, `test_sqlite_reservation_lifecycle_and_rejection_frees_hold`, `test_rejection_memory_soft_constraint_application`
- **Data Quality & Schemas:** `test_data_quality_flags_low_volume_and_gaps`, `test_ingestion_schemas_case_insensitivity_and_csv_support`
- **Consolidated APIs & HITL Gates:** `test_consolidated_api_unified_aliases`, `TestFastAPIFlow`

Run verification at any time:
```bash
pytest -q
```

---

## 🎬 3-Minute Hackathon Demonstration Script

### Minute 1: The Morning Briefing & Mathematical Rigor
1. Open Streamlit Dashboard (`http://localhost:8501`).
2. Point out the **Executive Backtest Headline Strip**:
   - *165 stockouts prevented | 197 lost units averted | ₹421,365 capital saved | 212.2% Net ROI*.
3. Highlight **Incident PRB-20261009-01** (Gokak Store — `FILTER-HYD-01`):
   - Current stock: 8 units, velocity: 4.0 units/day $\rightarrow$ 2.0 days cover.
   - Primary vendor lead time: 7 days $\rightarrow$ 5.0-day deficit gap.
4. Explain the **Transparent Decision Matrix**:
   - Compares Option 1 (Lateral transfer from Belgaum, ₹250 handling), Option 2 (Expedited vendor order, ₹18,700), Option 3 (Status quo inaction, ₹7,000 lost revenue).
   - Ranked #1 strictly by deterministic expected cost objective function.
5. Show the **Probabilistic Monte Carlo 14-Day Trajectory**:
   - 80% confidence fan chart (p10, p50, p90) visually demonstrates how the 1-day transfer completely averts the stockout curve.

### Minute 2: Global Optimizer & Supplier Reliability Learning
1. Navigate to the **Global Multi-Echelon Transfer Optimizer** panel:
   - Point out how the Integer Linear Programming (SciPy HiGHS MIP) solver balances transfers globally across all incidents, pulling surplus from Bagalkot and Belgaum to satisfy active demands while saving ₹11,350 vs uncoordinated greedy actions.
2. Inspect the **Supplier Reliability Audit Table**:
   - Show how the engine learned that *Danfoss Hydraulics* has a +2.0 day average delivery slippage, automatically adjusting its operational lead time from 15 days to 17 days.

### Minute 3: Chaos Injection, Plan Diff & Rejection Memory
1. In the **Chaos Engine Sidebar**, trigger **Transfer Roadblock (Block Belgaum Transfer Route)**.
2. Click **Inject Disruption**:
   - Point out the **Structured Plan Diff**: the copilot immediately detects that the Belgaum route is blocked, shifts the recommendation to the expedited vendor or alternate warehouse, and displays the exact reason: *"Route blocked between Belgaum and Gokak; shifted from Belgaum to secondary vendor Deccan Fluid Power"*.
3. Demonstrate **Rejection Memory**:
   - Reject an option with reason *"Packaging defect reported"*.
   - Re-run briefing: the engine retains the soft constraint (+₹750 penalty) and elevates the alternate pathway with an explicit human-in-the-loop note.
4. Click **Approve Action**:
   - Mutates inventory balances atomically, logs cryptographic idempotency hash in SQLite WAL, and dispatches the execution payload.
