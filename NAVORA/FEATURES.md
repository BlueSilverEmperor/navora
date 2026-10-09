# Kaveri Spares & Hydraulics — Supply Chain Copilot: Complete Features & Architecture

**Track:** Cypher 2026 - Hackathon Challenge 01 (Agentic AI for Supply Chain)  
**Operating Persona:** Autonomous AI Purchasing Colleague for **Ramesh Kulkarni** (Head of Purchasing)  
**Operating Network:** 6 Retail Stores (*Gokak, Belgaum, Dharwad, Hubli, Bagalkot, Nippani*) & 2 Central Distribution Warehouses (*Belgaum Central Warehouse, Hubli Regional Warehouse*) across North Karnataka.  
**Tech Stack & Design:** Python 3.10+, FastAPI, Dark Cyber-Amber Design System (Streamlit), NAVORA Terracotta/Cream UI (HTML5/Vanilla CSS/JS), Pandas, Plotly, Pydantic, Pytest  

---

## 🌟 Executive Overview

The **Kaveri Supply Chain Copilot** is a deterministic, domain-specialized agentic AI system built to empower Ramesh Kulkarni in managing multi-echelon industrial spare parts across North Karnataka.

Rather than merely displaying static reports or relying on unreliable LLM arithmetic approximations, the Copilot runs an autonomous **Observe $\rightarrow$ Reason $\rightarrow$ Evaluate $\rightarrow$ Decide $\rightarrow$ Draft $\rightarrow$ Gate** pipeline that:
- **Enforces the 12 Agent Rules Mandate** with 100% deterministic arithmetic grounded directly in the 5 core domain tables.
- **Scans & Classifies 5 Distinct Problem Categories** (`IMMINENT_STOCKOUT`, `CAPITAL_TRAP`, `OVERDUE_PO`, `DEMAND_VOLATILITY`, `SUPPLIER_MISMATCH`).
- **Formulates Mandated Alternatives ($N \ge 2$)** with quantified commercial trade-offs in days, direct INR expenditure, and stockout revenue risk.
- **Renders 14-Day Forward Visual Trajectory Projections** via interactive Plotly curves with a zero-stock hazard line.
- **Provides a Commercial Impact Scorecard** summarizing Net Cost, Lost Units, Working Capital Outflow, and Downtime Risk.
- **Empowers Ramesh's Human Gate & Counter-Proposals** with real-time dynamic recalculation of donor safety buffers ($\ge 15.0$ days) and trajectory adjustments.
- **Demonstrates Chaos Resilience** by dynamically adapting to judge-injected runtime shocks (demand surges, route roadblocks, supplier delays).

---

## 🛡️ The 12 Agent Rules Mandate Compliance

| Rule | Operational Requirement | Architectural Implementation | Verification |
| :--- | :--- | :--- | :--- |
| **1. Grounded Telemetry** | Extract facts strictly from 5 core records | Ingests exclusively from `products`, `inventory`, `sales`, `suppliers`, and `purchase_orders` | [`mock_data_gen.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/engine/mock_data_gen.py) |
| **2. Deterministic Domain Math** | Closed-form arithmetic (zero LLM calculation) | Python functions for $v_{30}$, $v_{7}$, $D$, $\Delta$, and lost revenue | [`domain_math.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/engine/domain_math.py) |
| **3. Full 5-Problem Coverage** | Scan and classify all 5 supply chain failure modes | Imminent Stockouts, Capital Traps, Overdue POs, Demand Volatility, and Supplier Mismatches | [`decision_agent.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/engine/decision_agent.py) |
| **4. Mandated Alternatives ($N \ge 2$)** | Model $\ge 2$ feasible options with quantified trade-offs | Evaluates Network Transfer, Expedited Vendor PO, and Status Quo Inaction | [`decision_agent.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/engine/decision_agent.py) |
| **5. Commercial Quantification** | Trade-offs in days, direct INR outlay, lost margins | ₹250 handling vs supplier purchase outlays, unit margins, and lost sales | [`dashboard.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/app/dashboard.py) |
| **6. Network Balancing Priority** | Reallocate internal surplus before external capital | Donor locations with $>15$ days post-transfer cover prioritized over vendor POs | [`domain_math.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/engine/domain_math.py#L83-L95) |
| **7. Supplier Constraint Checks** | Check MOQs and lead-time feasibilities | Flags `INFEASIBLE_MOQ` if $\text{MOQ} > 3 \times Q_{\text{needed}}$ and flags delivery lead-time friction | [`domain_math.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/engine/domain_math.py) |
| **8. Structured Artifacts** | Generate fully populated machine-readable payloads | Pre-drafts `TRANSFER_REQUEST`, `PURCHASE_ORDER`, and `SUPPLIER_EXPEDITE_NOTICE` | [`decision_agent.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/engine/decision_agent.py) |
| **9. Mandatory Human Gate** | Explicit user approval before state modification | Simulated uncommitted drafts; state mutates only upon `/action/approve` | [`server.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/app/server.py#L125-L223) |
| **10. Dynamic Recalibration** | Instant recalculation when user modifies quantities | Dynamic cover and forward trajectory recalculated without state mutation | [`server.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/app/server.py#L310-L360) |
| **11. Transparent Explainability** | Explicit mathematical ratios ($v$, $D$, $\Delta$, $T$) | Formatted formulas displayed on every card with Plotly forward visual curves | [`dashboard.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/app/dashboard.py) |
| **12. Chaos Resilience** | Ingest real-time state perturbations & adapt | Live runtime injection testing (`DEMAND_SPIKE`, `TRANSFER_ROADBLOCK`, `SUPPLIER_HIKE`) | [`server.py`](file:///c:/Users/sridh/Desktop/navora/kaveri_copilot/app/server.py#L424-L450) |

---

## 🔄 The 6-Step Agentic Execution Loop

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         AUTONOMOUS AGENT EXECUTION LOOP                      │
└──────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
[Step 1: OBSERVE & COMPUTE] ──► 7-day vs 30-day Velocity, Cover Days, Stockout Gaps, Projections
      │
      ▼
[Step 2: REASON & CLASSIFY] ──► 5 Categories (Stockout, Capital Trap, Overdue PO,
      │                         Demand Volatility, Supplier Mismatch)
      │
      ▼
[Step 3: EVALUATE OPTIONS]  ──► Internal Network Balancing vs Expedited Supplier vs Status Quo
      │                         (Lead Time vs Direct Outlay vs Feasibility & MOQ friction)
      │
      ▼
[Step 4: DECIDE OPTIMUM]    ──► Mathematically minimal cost (Zero new working capital outlay)
      │
      ▼
[Step 5: DRAFT ARTIFACTS]   ──► TRANSFER_REQUEST, PURCHASE_ORDER, SUPPLIER_EXPEDITE_NOTICE
      │
      ▼
[Step 6: HUMAN GATE & POST] ──► Ramesh Kulkarni Counter-Proposal, Approve & Commit to Audit Trail
```

---

## 📋 Complete Feature Catalog

### 1. Deterministic Domain Math Engine (`engine/domain_math.py`)

- **Adaptive Multi-Horizon Velocity (`compute_adaptive_velocity`):**
  $$v_{\text{baseline}} = \frac{1}{30}\sum_{t=1}^{30} q_t, \quad v_{\text{recent}} = \frac{1}{7}\sum_{t=1}^{7} q_t, \quad \text{Trend} = \frac{v_{\text{recent}}}{v_{\text{baseline}}}$$
  - **`ACCELERATING`**: Trend factor $\ge 1.5$ (uses $v_{\text{recent}}$ to prevent imminent under-forecasting).
  - **`DECELERATING`**: Trend factor $\le 0.4$ (uses $v_{\text{recent}}$ to prevent over-stocking).
  - **`STABLE`**: Defaults to $v_{\text{baseline}}$.
  - Detects explosive surge ($\ge 1.8\times$ and $v_{\text{recent}} \ge 2.0$) and cliff drop ($\le 0.3\times$).

- **Days of Inventory Cover ($D$):**
  $$D = \begin{cases} 0.0 & \text{if } \text{Stock} \le 0 \\ 999.0 \ (\text{Dead Stock}) & \text{if } v_{\text{predicted}} \le 0 \\ \frac{\text{Stock}}{v_{\text{predicted}}} & \text{otherwise} \end{cases}$$

- **Deficit Stockout Gap ($\Delta$):**
  $$\Delta = \max(0.0, T_{\text{lead}} - D)$$

- **Donor Safety Margin Calculation (`calculate_donor_transfer_safety` & `find_best_donor_location_with_reservations`):**
  Ensures donor locations strictly maintain $\ge 15.0$ operational cover days post-transfer, factoring in active reservation locks:
  $$\text{Effective Stock} = \max(0, \text{Gross Stock}_{\text{donor}} - \text{Reserved Stock}_{\text{donor}})$$
  $$\text{Remaining Cover} = \frac{\text{Effective Stock} - Q_{\text{transfer}}}{v_{\text{donor}}} \ge 15.0$$
  $$\text{Max Safe Transfer Qty} = \max(0, \text{Effective Stock} - \lceil 15.0 \times v_{\text{donor}} \rceil)$$

- **Simulation Date Anchored PO Evaluation (`check_is_po_overdue`):**
  - Uncouples overdue checking from host system clock (`datetime.today()` / `datetime.now()`).
  - Evaluates delivery dates against explicit simulation date (`"2026-10-09"` default).
  - Terminal statuses (`DELIVERED`, `CANCELLED`) are never marked overdue.

- **Physical Inventory Floor Clamping & Unfulfilled Demand Metrics (`clamp_inventory_projection`):**
  - Physical stock is strictly clamped at $\ge 0.0$ at each step of consumption.
  - Excess daily demand deficit is accumulated into an `unmet_demand_lost_units` path.

- **14-Day Forward Trajectory Projections (`generate_14day_projections`):**
  Generates day-by-day simulated inventory arrays over $t \in [0, 14]$ days for all three paths:
  - **Status Quo**: Stock burns at $v_{\text{daily}}$; primary PO arrives on day $T_{\text{primary}}$ (+25 units).
  - **Expedited Vendor PO**: Stock burns at $v_{\text{daily}}$; expedited vendor delivery arrives on day $T_{\text{expedited}}$ (+20 units).
  - **Inter-Store Network Transfer**: Stock burns at $v_{\text{daily}}$; rapid transfer arrives on day 1 (+$Q_{\text{transfer}}$ units).
  - Floor constraint: stock levels never dip below 0.0 with lost unit accounting.

- **Supplier Friction & MOQ Scoring (`evaluate_supplier_friction`):**
  - Flags `INFEASIBLE_MOQ` if vendor MOQ causes over-purchasing exceeding $3 \times Q_{\text{needed}}$.
  - Computes unit contract price variance: $\frac{P_{\text{vendor}} - P_{\text{baseline}}}{P_{\text{baseline}}} \times 100\%$.
  - Flags `TIMING_INFEASIBLE` if vendor lead time exceeds remaining days of cover.

---

### 2. 5-Problem Classification & Resolution Matrix (`engine/decision_agent.py`)

| Category Code | Classification | Trigger Criteria | Action Draft Type | Primary Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **`CATEGORY_A`** | **Imminent Stockout** | Days of Cover < Primary Lead Time, no active PO in transit | `TRANSFER_REQUEST` | Rapid 24-hr transfer from internal surplus donor |
| **`CATEGORY_B`** | **Capital Trap** | Cover > 45 days OR 0 sales over 14+ days with positive stock | `TRANSFER_REQUEST` | Rebalance trapped capital into starved high-velocity hubs |
| **`CATEGORY_C`** | **Overdue PO** | `expected_date < current_date` and `status != DELIVERED` | `SUPPLIER_EXPEDITE_NOTICE` | Formal SLA penalty notice & hot-shot courier dispatch |
| **`CATEGORY_D`** | **Demand Volatility** | $v_{7}$ surges $\ge 1.8\times$ over $v_{30}$ baseline | `TRANSFER_REQUEST` | Preemptively raise safety stock buffer |
| **`CATEGORY_E`** | **Supplier Mismatch** | Stockout exists and vendor lead time or MOQ $\ge 3\times Q_{\text{needed}}$ | `PURCHASE_ORDER` / Alert | Escalate MOQ friction and reorder via qualified alternate supplier |

---

### 3. User Interfaces: NAVORA Operations Engine & Streamlit Cockpit

#### 3.1. NAVORA Autonomous Operations Engine Dashboard (`NAVORA/dashboard.html` & `NAVORA/main.py`)
Served directly at `http://127.0.0.1:8000/` as an executive-grade, standalone single-page application built with modern terracotta & warm cream glassmorphic aesthetics:
- **Multi-Incident Network Dropdown Scanner:** Dynamically scans and switches across all 19 detected network problems across the 8 North Karnataka facilities (covering all 5 problem categories).
- **Dark / Light Mode Toggle:** Seamless color scheme transitions between rich dark terracotta (`#181412`) and warm cream light mode (`#FAF6F0`).
- **Closed-Form Mathematical Telemetry Proof Box (Rule 2 & Rule 11):** Explicitly renders formula proofs for Adaptive Consumption Velocity ($v_{\text{pred}}$, Trend $T$), Inventory Cover ($D$), Deficit Gap ($\Delta$), and Projected Margin at Risk.
- **14-Day Forward Trajectory Projections (Rule 4):** Interactive SVG visualization displaying day-by-day projected inventory levels for Status Quo (🔴 cliff), Expedited Vendor PO (🟡), and Inter-Warehouse Transfer (🔵) with a dashed **Zero-Stock Hazard Line** and dynamic Counter-Proposal curve (🟢).
- **Commercial Impact Scorecard (Rule 5):** 4 executive KPI cards demonstrating Net Direct Outlay (₹250 vs ₹28,000+), Lost Units Averted (14 units), Working Capital Outflow (₹0.00), and Downtime Risk (0 Days).
- **Human-in-the-Loop Counter-Proposal Drawer (Rule 6, Rule 9, Rule 10):** Natural-language quantity adjustments with real-time recalculation and a dynamic **Donor Safety Buffer Alert** (green compliant badge for $\ge 15.0$ days cover; red glowing alert for buffer breach $< 15.0$ days with maximum safe transfer guidance).
- **Live Chaos Injection Toolbar (Rule 12):** Quick-action perturbation buttons directly in the top command bar (`🌪️ Demand Surge 3x`, `🚧 Block Route`, `📈 Supplier Delay +5d`, and `🔄 Reset Baseline`) with active perturbations tracking.
- **Embedded Inspection Modals:** Direct access to `🏢 Network Inventory (8 Facilities)`, `📜 Audit Ledger History`, and `Inspect JSON Telemetry`.

#### 3.2. Interactive Streamlit Executive Cockpit (`app/dashboard.py`)
Served at `http://127.0.0.1:8501/` as an industrial, high-velocity analytical workstation custom-engineered for Ramesh Kulkarni:

##### 🎨 Dark Cyber-Amber Design System
Built with a sleek, high-contrast industrial aesthetic engineered for intense supply chain operations:
- **Base Surfaces:** Deep Obsidian (`#110E0E` / `#141010`) background with elevated dark charcoal card containers (`#181212` / `#1E1717`, border: `1px solid #332626`).
- **Primary Accent & Glow:** Vibrant coral/amber (`#FF5733` / `#FF6B4A` / `#F97316`) for primary alerts, buttons, and active focus outlines.
- **Secondary Accents:** Electric Emerald (`#10B981`) for safety/buffer stability; Critical Crimson (`#EF4444`, background: `#3D1212`, border: `#7F1D1D`) for stockout emergencies; Muted Slate (`#9CA3AF`) for secondary metrics; Mono Orange (`#FF8566`) for mathematical terms.
- **Zero-Padding Viewport Flush:** Overrides Streamlit default top margins via `.block-container { padding-top: 0.6rem !important; }`, ensuring the title and executive command bar sit immediately at the top of the viewport with zero wasted blank space.
- **Native Theme Configuration:** Standardized `.streamlit/config.toml` enforcing dark background, card surfaces, and coral accents across all environments.
- **Custom Pixel-Perfect Dark Cyber Table System (`render_cyber_table`):** Completely eliminates Streamlit's white-canvas dataframe rendering glitch. Features sticky obsidian headers (`#181212`), high-contrast monospace numeric values, smooth row-hover illumination (`#221A1A`), and automatic status pill badges (`CRITICAL`, `FEASIBLE`, `HIGH`, `MEDIUM`).
- **Unified Plotly Dark Theming (`format_cyber_plotly_figure`):** Custom figure transformer applying obsidian plot backgrounds (`#141010`), muted grid lines (`#2A2020`), crisp white labels (`#F3F4F6`), and high-contrast projection curves.

##### 🖥️ Master-Detail Layout & Workflow (Pic 1 Architecture + Pic 2 Cyber-Amber Styling)
- **Top Executive Command Header:** Displays system mode (`LIVE OPERATIONAL SIMULATION`), active persona (`Ramesh Kulkarni - Head of Purchasing`), and simulation anchor date (`2026/10/09`).
- **4-Column High-Impact KPI Overview Strip:**
  1. *Active Incidents:* Real-time count with breakdown pills (`CRITICAL`, `HIGH`, `MEDIUM`).
  2. *Capital at Risk:* Total network INR margin exposure across active stockout threats.
  3. *Network Inventory Cover:* Network-wide weighted inventory runway in days.
  4. *Autonomous Resolutions Ready:* Zero-working-capital rebalancing actions pre-drafted for execution.
- **In-Pane Severity Filter Dropdown Menu:**
  - Located directly above the task feed (`Filter Severity: [All, CRITICAL, HIGH, MEDIUM]`).
  - Allows Ramesh to instantly filter the feed by operational urgency without jarring page jumps.
- **Master Incident Feed (Left Column — 38% Width):**
  - Vertically stacked clickable Incident Cards (`.incident-card` vs `.incident-card-active`).
  - Active card illumination: Glowing coral border (`border: 1px solid #FF5733`) and amber box shadow (`0 0 12px rgba(255, 87, 51, 0.4)`).
  - High-density card telemetry: Severity pill badge, SKU Name & ID, Category Code, Facility Location, Inventory Cover ($D$), and Deficit Stockout Gap ($\Delta$).
  - Instant selection: Clicking any card updates `st.session_state.selected_problem_id` and populates the right-hand cockpit without resetting scroll position.
- **Detailed Incident Resolution Cockpit (Right Column — 62% Width):**
  - **Primary Action Recommendation Banner:** Clear operational headline (e.g. `RECOMMENDED ACTION: 24-Hour Inter-Store Stock Transfer`).
  - **Closed-Form Telemetry Terminal (`.math-terminal`):** 4-cell telemetry grid covering Stock vs Adaptive Velocity ($v_{30}, v_7$), Days of Cover vs Stockout Gap ($D, \Delta$), Primary Lead Time vs In-Transit PO Status, and Deterministic Classification Proof.
  - **Commercial Impact Scorecard (Rule 5):** 4-metric executive summary: Net Cost (₹250 Handling vs ₹28,000+ External Purchase), Lost Units Averted, Capital Outlay Saved, and Stockout Risk Averted.
  - **Comparative Resolution Alternatives Table (Rule 4):** Evaluates Feasible Internal Transfer, Expedited Vendor PO, and Status Quo Inaction with cost, lead time, and stockout risk rendered in the custom cyber table.
  - **Interactive 14-Day Forward Trajectory Plotly Chart:** Day-by-day projected inventory curves comparing Status Quo (cliff drop), Expedited Vendor PO, and Inter-Store Transfer with a dashed red Zero-Stock Hazard Line.
  - **1-Click Human Approval & Dispatch:** One-click `Approve & Dispatch` (mutates multi-echelon stock, generates transfer request, logs transaction into audit ledger) and `Dismiss / Reject` with operator feedback.
  - **Ramesh's Counter-Proposal Tool (Rule 6, Rule 9, Rule 10):** Numeric quantity override slider/input with instant live recalculation of recipient cover days and dynamic **Donor Safety Buffer Alert** ($\ge 15.0$ days compliance vs $< 15.0$ days violation warnings with maximum safe transfer calculation).

##### 📑 Multi-Tab Governance Control Plane
1. **`🚨 Morning Action Feed`:** The master-detail operational triage cockpit described above.
2. **`🏭 Multi-Echelon Network Inventory`:** Comprehensive stock explorer across all 8 facilities (6 retail stores + 2 central warehouses), rendered using `render_cyber_table` with SKU, Category, On-Hand Units, Reserved, In-Transit, and Unit Value.
3. **`🔍 Supplier Friction & Reliability Audit`:** Supplier audit tracking purchase order lead times, contract markup variances, MOQ feasibility constraints, and reliability ratings.
4. **`📜 Immutable Audit Trail`:** Chronological ledger of all approved and rejected human decisions with timestamps, operator identity, and mutated balances.

##### ⚡ Dedicated Sidebar Operating Controls & Chaos Engine
- Operating Persona & Network config (6 retail stores + 2 central distribution hubs).
- **Chaos Engine Controls (Rule 12):** Isolated in the sidebar to prevent UI overlap collisions, featuring runtime triggers for `🌪️ Demand Surge 3x`, `🚧 Block Route Gokak-Belgaum`, `📈 Supplier Delay +5d`, and `🔄 Reset Baseline`.

---

### 4. Production REST API Endpoints (`app/server.py`)

#### Core Kaveri Copilot & Governance Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service liveness health check |
| `GET` | `/briefing` | Ingests data, triggers domain math and agent evaluation, and returns ranked problems with calculated alternatives and 14-day forward projections |
| `POST` | `/action/recalculate-override` | Recalculates updated donor cover, recipient cover, safety margin, and 14-day trajectory projections without committing state |
| `POST` | `/action/override-recalculate` | Legacy compatibility alias for counter-proposal recalculation |
| `POST` | `/action/approve` | Idempotent transaction approval: checks SHA-256 signature / `client_request_id` (`409 Conflict` on duplicate), verifies donor physical stock and post-transfer cover $\ge 15.0$ days (`400 Bad Request` on violation), mutates multi-echelon stock balances, and appends to `data/audit_log.json` |
| `POST` | `/action/reject` | Records user rejection with an operational rationale in audit log |
| `POST` | `/chaos/inject` | Mutates runtime memory (`DEMAND_SPIKE`, `TRANSFER_ROADBLOCK`, `SUPPLIER_HIKE`) with custom `value` parameters |
| `GET` | `/inventory` | Returns multi-echelon inventory joined with product metadata |
| `GET` | `/suppliers/audit` | Audits supplier price markup variance, lead times, and MOQ friction |
| `GET` | `/audit-log` | Returns historical record of all human decisions |
| `POST` | `/reset-data` | Restores benchmark state and clears active chaos events |

#### NAVORA Direct Frontend Integration Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/telemetry` | Returns structured telemetry for selected problem (or Gokak benchmark default) plus `all_incidents` list for the UI switcher |
| `POST` | `/api/recalculate` | Instant closed-form recalculation with donor safety buffer ($\ge 15.0$ days) checks and forward projections |
| `POST` | `/api/actions/approve` | Executes action approval, mutates inventory balances, and generates dispatch receipt with transaction ID |
| `POST` | `/api/actions/reject` | Dismisses incident and records rejection reason code into audit trail |
| `GET` | `/api/ledger` | Returns real-time multi-echelon inventory and transaction audit ledger |
| `POST` | `/api/chaos` | Injects operational chaos perturbations (`DEMAND_SPIKE`, `TRANSFER_ROADBLOCK`, `SUPPLIER_HIKE`) |
| `POST` | `/api/reset` | Resets data to pristine benchmark state and clears active chaos perturbations |

---

### 5. Automated Verification Suite (`tests/test_decisions.py`)

All **35 automated test assertions** pass cleanly:

```bash
python -m pytest tests/test_decisions.py -v
```

#### Core Mandate Verification Highlights (35/35 Passing):
1. `test_adaptive_velocity_surge`: A 2x jump in 7-day sales triggers `ACCELERATING` and adjusts days of cover.
2. `test_donor_safety_margin`: Transfer proposals that leave a donor store with $<15$ days of cover are rejected (`is_safe: False`).
3. `test_benchmark_gokak_belgaum`: Gokak hydraulic filter stockout selects a Belgaum transfer of 12–16 units over expedited vendor procurement.
4. `test_forward_projection_math`: Day-by-day trajectory curves correctly reflect daily burn rates and planned delivery arrivals.
5. `test_human_override_flow`: Overriding a transfer quantity updates destination cover while maintaining donor constraints.
6. `test_gokak_filter_stockout_and_belgaum_transfer`: Complete end-to-end benchmark validation with structured payload check.
7. `test_capital_trap_detection`: Validates capital trap classification at Bagalkot (`VALVE-CTRL-02`).
8. `test_overdue_po_detection`: Validates overdue PO detection at Hubli (`PUMP-GEAR-03`).
9. `test_supplier_moq_friction`: Verifies supplier with MOQ 100 for a 10-unit stockout is flagged `INFEASIBLE_MOQ`.
10. `test_chaos_injection_resilience`: Injects route block and asserts autonomous agent fallback to expedited procurement.
11. `test_briefing_and_approval_api`: Validates FastAPI approval pipeline and inventory balance mutations.
12. `test_reject_action_api`: Verifies action rejection recording and audit trail updates.
13. `test_chaos_inject_api`: Confirms runtime chaos injection mutates state dynamically.
14. `test_demand_surge_detection`: Asserts surge detection on custom multi-horizon velocity thresholds.
15. `test_zero_sales_division_guard`: Defensive zero-division guard returns safe defaults when sales data is completely zero or empty.
16. `test_dynamic_donor_selection_non_belgaum`: Dynamically resolves alternate donors across network without hardcoded facility biases.
17. `test_dynamic_forward_projection_lead_times`: Trajectory math accounts for dynamic supplier lead times and varying delivery days.
18. `test_telemetry_endpoint_404_on_nonexistent`: Validates `404 Not Found` response when telemetry is requested for an unknown problem ID.
19. `test_simulation_date_overdue_anchor`: Verifies overdue detection anchors to explicit `simulation_date` (`"2026-10-09"`) rather than system clock.
20. `test_negative_stock_clamping_and_lost_units`: Asserts physical inventory never drops below 0.0 and accumulates deficits into `unmet_demand_lost_units`.
21. `test_shared_donor_reservation_deduction`: Rejects candidates with gross surplus if active draft reservations leave $<15.0$ days cover.
22. `test_approval_idempotency_duplicate_conflict`: Verifies duplicate `/action/approve` calls return `HTTP 409 Conflict`.
23. `test_approval_safety_buffer_violation_400`: Verifies approval endpoint blocks transfers leaving donor with $<15.0$ days cover (`HTTP 400 Bad Request`).

#### Live End-to-End Backend Audit Script:
```bash
python kaveri_copilot/scripts/test_live_backend.py
```
Validates all 5 operational pillars against real running HTTP endpoints with pass/fail markers.

---

## ⚡ Quick-Start Execution Commands

```bash
# 1. Run Automated Test Suite (35/35 tests passing)
pytest tests/test_decisions.py -v

# 2. Run Live Backend Contract Audit
python kaveri_copilot/scripts/test_live_backend.py

# 3. Launch NAVORA Modern Operations Engine UI & Backend (Port 8000)
python NAVORA/main.py
# Or: uvicorn app.server:app --host 0.0.0.0 --port 8000
# Access UI: http://127.0.0.1:8000/
# API Docs:  http://127.0.0.1:8000/docs

# 4. Launch Streamlit Executive Cockpit (Port 8501)
streamlit run app/dashboard.py --server.port 8501

# 5. Launch both via runner script
./run.sh
```

---

## 🛡️ Production Vulnerability Hardening (35/35 Tests Passing)

1. **Simulation Date Desync Eliminated:**
   - Business logic uncoupled from system clock (`datetime.today()` / `datetime.now()`).
   - All overdue checks anchored to configurable `simulation_date` (`"2026-10-09"` default) via `check_is_po_overdue()`.
2. **Double-Action Race & Idempotency Protection:**
   - In-memory `PROCESSED_ACTION_HASHES` tracking with SHA-256 signatures or client-supplied `client_request_id`.
   - `POST /action/approve` immediately rejects duplicate calls with `HTTP 409 Conflict`.
3. **Shared Donor Contention Guard:**
   - Multi-store transfer conflicts prevented through active reservation tracking (`ACTIVE_TRANSFER_RESERVATIONS`).
   - Donor viability evaluated against `effective_available_stock = max(0, gross_stock - reserved)`.
   - Transfers verified before commit to ensure donor retains $\ge 15.0$ days cover, returning `HTTP 400 Bad Request` on breach.
4. **Physical Floor Clamping & Unfulfilled Demand Metrics:**
   - `clamp_inventory_projection()` guarantees projected inventory never dips below `0.0`.
   - Accumulated unfulfilled stockout deficits are tracked in `unmet_demand_lost_units`.

