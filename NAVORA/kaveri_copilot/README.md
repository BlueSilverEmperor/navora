# Kaveri Spares & Hydraulics — Autonomous Supply Chain Copilot
**Track:** Cypher 2026 - Hackathon Challenge 01 (Agentic AI for Supply Chain)  
**Persona:** AI Purchasing Colleague for **Ramesh Kulkarni** (Head of Purchasing)  
**Operations Scope:** 6 Retail Stores (Gokak, Belgaum, Dharwad, Hubli, Bagalkot, Nippani) & 2 Central Warehouses (Belgaum Central Warehouse, Hubli Regional Warehouse) across North Karnataka.

---

## 🚀 Overview

The **Kaveri Supply Chain Copilot with Adaptive Velocity Engine** is an agentic, deterministic decision engine and executive cockpit designed to proactively manage inventory, eliminate stockout risks, unfreeze working capital, and expedite overdue shipments across North Karnataka.

### 🏛️ The 12-Agent Rules Mandate:
1. **Grounded Telemetry:** Ground every observation directly in the 5 raw records (`products`, `inventory`, `sales`, `suppliers`, `purchase_orders`).
2. **Deterministic Velocity Math:** Closed-form arithmetic (zero LLM hallucination of velocity or days of cover).
3. **Full 5-Problem Coverage:** `IMMINENT_STOCKOUT`, `CAPITAL_TRAP`, `OVERDUE_PO`, `DEMAND_VOLATILITY`, and `SUPPLIER_MISMATCH`.
4. **Mandated Alternatives ($N \ge 2$):** Every problem evaluates at least two options with explicit trade-offs.
5. **Commercial Quantification:** Trade-offs quantified in days, direct INR expenditure, and stockout revenue loss.
6. **Network Balancing Priority:** Favors internal transfers over new vendor POs when donors retain $\ge 15$ days cover.
7. **Supplier Constraint Checks:** MOQ feasibility evaluated against local consumption rate.
8. **Structured Artifacts:** Emits machine-readable draft payloads (`TRANSFER_REQUEST`, `PURCHASE_ORDER`, `EXPEDITE_NOTICE`).
9. **Mandatory Human Gate:** All state changes simulated until approved by Ramesh Kulkarni.
10. **Dynamic Recalibration:** Recalculates cover and cash impact dynamically when user overrides quantities.
11. **Transparent Explainability:** Exposes exact underlying metrics ($v$, $D$, $\Delta$, $T$).
12. **Chaos Resilience:** Live runtime injection of operational disruptions with autonomous adaptation.

---

## 📁 Repository Structure

```
kaveri_copilot/
├── data/
│   ├── products.json            # 6 industrial hydraulic SKUs
│   ├── inventory.json           # Multi-echelon stock levels across 8 nodes
│   ├── sales.json               # 30-day recorded sales history
│   ├── suppliers.json           # Primary & secondary vendors with lead times and MOQs
│   ├── purchase_orders.json     # Active, delayed, and in-transit POs
│   └── audit_log.json           # Immutable trace of approved/rejected actions
├── engine/
│   ├── domain_math.py           # Burn rate, cover days, stockout gaps, surplus formulas
│   ├── decision_agent.py        # 3-option evaluator & action drafter
│   └── mock_data_gen.py         # Seeds North Karnataka operational dataset
├── app/
│   ├── server.py                # FastAPI backend (GET /briefing, POST /action/approve)
│   └── dashboard.py             # Streamlit Executive Dashboard
├── tests/
│   └── test_decisions.py        # Automated test suite (Gokak benchmark & edge cases)
├── requirements.txt
├── run.sh                       # Linux/Mac startup script
└── run.bat                      # Windows startup script
```

---

## 🎯 Benchmark Scenario (Gokak vs Belgaum)

- **Node Deficit:** SKU `FILTER-HYD-01` (Return Line Hydraulic Filter - JCB 3DX) at **Gokak Store**:
  - Current stock: **8 units**
  - Daily Velocity: **4.0 units/day**
  - Days of Cover: **2.0 days**
  - Primary Supplier: **7 days** lead time $\rightarrow$ **5.0-day stockout gap**!
- **Network Surplus:** **Belgaum Store**:
  - Current stock: **40 units**
  - Daily Velocity: **0.5 units/day**
  - Days of Cover: **80.0 days** (Capital trapped in slow-moving stock)
- **Agent Action:** 
  - Generates `TRANSFER_REQUEST` of **14 units** from Belgaum to Gokak.
  - Cost: **₹250 flat handling** (vs ₹18,700 for secondary vendor PO).
  - Arrival: **1 day** (resolves deficit before stockout occurs).
  - Belgaum retains **52.0 days cover** (well above the 15-day safety threshold).

---

## ⚡ Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Test Suite
```bash
pytest tests/test_decisions.py -v
```

### 3. Launch Application
On Windows:
```cmd
run.bat
```
Or manually:
```bash
# Terminal 1: FastAPI Backend
uvicorn app.server:app --port 8000

# Terminal 2: Streamlit Dashboard
streamlit run app/dashboard.py --server.port 8501
```
Navigate to `http://localhost:8501` to access the dashboard.
