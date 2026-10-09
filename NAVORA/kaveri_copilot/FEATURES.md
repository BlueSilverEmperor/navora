# Kaveri Spares & Hydraulics — Supply Chain Copilot: Complete Features & Architecture

**Track:** Cypher 2026 - Hackathon Challenge 01 (Agentic AI for Supply Chain)  
**Operating Persona:** Autonomous AI Purchasing Colleague for **Ramesh Kulkarni** (Head of Purchasing)  
**Operating Network:** 6 Retail Stores (*Gokak, Belgaum, Dharwad, Hubli, Bagalkot, Nippani*) & 2 Central Distribution Warehouses (*Belgaum Central Warehouse, Hubli Regional Warehouse*) across North Karnataka.

---

## 🌟 Executive Overview

The **Kaveri Supply Chain Copilot** is a deterministic, domain-specialized multi-agent system built to empower Ramesh Kulkarni in managing multi-echelon industrial spare parts across North Karnataka.

Rather than merely displaying reports, the Copilot runs an autonomous **Observe $\rightarrow$ Reason $\rightarrow$ Evaluate $\rightarrow$ Decide $\rightarrow$ Draft $\rightarrow$ Gate** pipeline that:
- Continuously monitors demand velocity, buffer cover days, and supplier performance.
- Classifies operational risks across **5 distinct problem categories** ($A$ through $E$).
- Evaluates multi-option commercial trade-offs (Internal Transfer vs Secondary Rush PO vs Inaction).
- Enables **dynamic human counter-proposals and overrides** with real-time arithmetic recalculation.
- Responds resiliently to **runtime chaos injections** (e.g. road blocks, sudden demand spikes, vendor price hikes).

---

## 🔄 The 6-Step Agentic Execution Loop

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         AUTONOMOUS AGENT EXECUTION LOOP                      │
└──────────────────────────────────────────────────────────────────────────────┘
      │
      ▼
[Step 1: OBSERVE & COMPUTE] ──► 7-day vs 30-day Velocity, Cover Days, Stockout Gaps
      │
      ▼
[Step 2: REASON & CLASSIFY] ──► 5 Categories (Stockout, Capital Trap, Overdue PO,
                                Demand Volatility, Supplier Infeasibility)
      │
      ▼
[Step 3: EVALUATE OPTIONS]  ──► Internal Network Balancing vs Expedited Supplier vs Wait
      │                         (Speed vs Cash Impact vs Feasibility Status)
      │
      ▼
[Step 4: DECIDE OPTIMUM]    ──► Mathematically minimal cost (Zero new working capital)
      │
      ▼
[Step 5: DRAFT ACTIONS]     ──► TRANSFER_REQUEST, PURCHASE_ORDER, EXPEDITE_NOTICE
      │
      ▼
[Step 6: HUMAN-IN-THE-LOOP] ──► Ramesh Kulkarni Counter-Proposal & Approval Gate
```

---

## 📋 Comprehensive Feature Catalog

### 1. Advanced Domain Math Engine (`engine/domain_math.py`)

- **Dual-Horizon Demand Velocity & Surge Detection:**
  $$v_{\text{short}} = \frac{\sum_{t=1}^{7} \text{qty\_sold}_t}{7}, \quad v_{\text{long}} = \frac{\sum_{t=1}^{30} \text{qty\_sold}_t}{30}$$
  - **Demand Surge:** Triggered when $\frac{v_{\text{short}}}{v_{\text{long}}} \ge 1.8$ and $v_{\text{short}} \ge 2.0$.
  - **Demand Drop:** Triggered when $\frac{v_{\text{short}}}{v_{\text{long}}} \le 0.3$ and $v_{\text{long}} \ge 2.0$.
- **Days of Stock Cover ($D$):**
  $$D = \begin{cases} 0.0 & \text{if } \text{Stock} = 0 \\ 999.0 \ (\infty) & \text{if } \text{Stock} > 0 \text{ and } v = 0 \\ \frac{\text{Stock}}{v} & \text{if } v > 0 \end{cases}$$
- **Stockout Gap Analysis ($\Delta$):**
  $$\Delta = \max(0.0, L_{\text{primary}} - D)$$
- **Multi-Echelon Surplus Safety Calculation:**
  $$\text{Surplus}_j = \max(0, \text{Stock}_j - \lceil 15 \times v_j \rceil)$$
- **Supplier Friction & Infeasibility Scoring (`evaluate_supplier_friction`):**
  - **MOQ Penalty:** Flags `INFEASIBLE_MOQ` if $\text{MOQ} > 3 \times Q_{\text{needed}}$ (avoids locking up working capital).
  - **Price Premium:** Quantifies markup against contracted baseline: $\frac{\text{Price} - P_{\text{base}}}{P_{\text{base}}} \times 100\%$.
  - **Timing Breach:** Flags `TIMING_INFEASIBLE` if $L_{\text{supplier}} > D$.
- **Dynamic Rebalancer with Override (`validate_and_recalculate_transfer`):**
  - Validates human counter-proposals against donor safety threshold: $S_{\text{donor}} - Q_{\text{override}} \ge 15 \times v_{\text{donor}}$.
  - If valid: returns updated days of cover for both donor and recipient nodes.
  - If invalid: flags warning and calculates the exact maximum safe transfer quantity.

---

### 2. 5 Distinct Problem Categories (`engine/decision_agent.py`)

| Category Code | Classification | Trigger Criteria | Example in Dataset | Severity |
| :--- | :--- | :--- | :--- | :--- |
| **`CATEGORY_A`** | **Imminent Stockout** | Days of Cover < Primary Lead Time, no arriving PO | `FILTER-HYD-01` at Gokak (2.0d cover vs 7d lead time) | `CRITICAL` |
| **`CATEGORY_B`** | **Capital Trap / Dead Stock** | Cover > 45 days OR 0 sales over 14+ days with positive stock | `VALVE-CTRL-02` at Bagalkot (15 dormant units, ₹367,500 locked) | `HIGH` / `MEDIUM` |
| **`CATEGORY_C`** | **Overdue Purchase Order** | `expected_date < Current Date` and `status != DELIVERED` | `PUMP-GEAR-03` at Hubli (PO-2026-0892 overdue by 5 days) | `CRITICAL` / `HIGH` |
| **`CATEGORY_D`** | **Sudden Demand Volatility** | 7-day velocity $\ge 1.8\times$ of 30-day baseline | Seasonal harvesting surges on hydraulic spares | `HIGH` |
| **`CATEGORY_E`** | **Supplier Infeasibility** | Stockout exists, internal transfer unavailable, and vendors blocked by MOQ/Lead time | Specialized excavator components with 100-unit MOQs | `CRITICAL` |

---

### 3. Multi-Option Commercial Evaluation Matrix

Every problem item formulates competing commercial alternatives with standardized fields:
- `option_name`
- `lead_time_days`
- `cash_impact_inr` (flat handling fee vs total order cash outlay)
- `feasibility_status` (`FEASIBLE`, `INFEASIBLE_MOQ`, `TIMING_INFEASIBLE`, or `INFEASIBLE`)
- `trade_off_summary` (concise commercial reasoning)

---

### 4. Benchmark Scenario & Resilience Showcase

#### A. Benchmark Gokak vs Belgaum Rebalancing
- **Gokak Deficit:** 8 units, velocity 4.0/day $\rightarrow$ 2.0 days cover, 5.0-day stockout gap.
- **Belgaum Surplus:** 40 units, velocity 0.5/day $\rightarrow$ 80.0 days cover.
- **Decision:** Transfers **14 units** (within 12–16 units range) from Belgaum to Gokak.
- **Economics:** ₹250 flat handling vs ₹18,700 for secondary rush PO. Belgaum retains **52.0 days cover** ($> 15$ days).

#### B. Chaos Injection & Automatic Fallback
- When the **Belgaum-to-Gokak road is blocked** (or transfer rendered infeasible), the agent automatically re-evaluates the network, identifies that internal transfers are blocked, and pivots recommendation to **Option 2: Expedited Purchase Order** with `FastTrack Spares Bengaluru`!

---

### 5. Interactive Streamlit Cockpit (`app/dashboard.py`)

- **Morning Feed:** Ranked cards with severity tags (`CRITICAL`, `HIGH`, `MEDIUM`), category codes, and domain metrics badges.
- **Ramesh's Counter-Proposal Tool:** Real-time quantity override input with instant live recalculation of recipient cover days, donor buffer retention, and maximum safe quantity limits.
- **Judge & Mentor Chaos Simulator Panel (Sidebar):**
  - 🌪️ *3x Sales Spike at Gokak*
  - 🚧 *Belgaum Road Blocked (Transfer Infeasible)*
  - 📈 *FastTrack Lead Time Delay (+3 Days)*
  - 🧹 *Clear Injected Chaos*
- **Multi-Echelon Network View:** Complete inventory visibility across all 8 nodes with SKU filters.
- **Supplier Friction & Reliability Audit Tab:** Transparent tracking of vendor price variance against contract baseline, delivery timing, and MOQ friction risks.
- **Governance Audit Trail:** Real-time log of approved and rejected human decisions.

---

### 6. Production REST API Endpoints (`app/server.py`)

| Endpoint | Method | Payload / Description |
| :--- | :--- | :--- |
| `/health` | `GET` | Service liveness health check |
| `/briefing` | `GET` | Generates schema-compliant JSON briefing for all 5 problem types |
| `/action/approve` | `POST` | Executes transfer/PO/expedite notice, mutates inventory, and logs audit |
| `/action/reject` | `POST` | Records human rejection rationale |
| `/action/override-recalculate` | `POST` | Validates custom transfer quantity; returns donor and recipient cover days |
| `/chaos/inject` | `POST` | Injects runtime shocks (`DEMAND_SURGE`, `TRANSFER_BLOCKED`, `SUPPLIER_DELAY`) |
| `/suppliers/audit` | `GET` | Audits supplier reliability, price markups, and MOQ risk levels |
| `/inventory` | `GET` | Multi-echelon stock levels joined with machine models and categories |
| `/audit-log` | `GET` | Complete immutable audit history |
| `/reset-data` | `POST` | Re-seeds initial benchmark data and clears active chaos |

---

### 7. Automated Test Suite (`tests/test_decisions.py`)

All 11 automated pytest test cases pass cleanly:

1. `test_burn_rate_and_cover`: Verifies velocity and cover math.
2. `test_stockout_gap`: Validates lead time deficit logic.
3. `test_available_surplus`: Ensures source node protection $> 15$ days cover.
4. `test_gokak_filter_stockout_and_belgaum_transfer`: Validates the primary hackathon benchmark.
5. `test_capital_trap_detection`: Verifies dead stock detection at Bagalkot (`VALVE-CTRL-02`).
6. `test_overdue_po_detection`: Verifies overdue PO flagging at Hubli (`PUMP-GEAR-03`).
7. `test_briefing_and_approval_api`: Validates REST briefing and approval inventory mutation.
8. `test_demand_surge_detection`: Verifies 7-day velocity surge is detected and classified.
9. `test_supplier_moq_friction`: Verifies supplier with MOQ 100 for 10 units is flagged `INFEASIBLE_MOQ`.
10. `test_human_override_recalculation`: Asserts that requesting 20 units adjusts Gokak cover to 7.0 days while keeping Belgaum cover above 15 days.
11. `test_chaos_injection_resilience`: Injects transfer block and verifies agent automatically pivots to expedited procurement.

---

## ⚡ Quick-Start Commands

```bash
# 1. Run all 11 automated tests
pytest kaveri_copilot/tests/test_decisions.py -v

# 2. Launch FastAPI Service (Port 8000)
uvicorn kaveri_copilot.app.server:app --port 8000

# 3. Launch Streamlit Executive Cockpit (Port 8501)
streamlit run kaveri_copilot/app/dashboard.py --server.port 8501
```
