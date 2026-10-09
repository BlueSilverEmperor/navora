# NAVORA — Product Feature Specification

> **NAVORA** is an AI-powered autonomous procurement and inventory intelligence platform designed for supply chain managers, warehouse operators, and purchasing directors. NAVORA bridges the gap between raw ERP calculation engines and human decision-makers by delivering actionable morning briefings, multi-option mitigation strategies, and high-trust Human-in-the-Loop (HITL) execution workflows.

---

## 1. Executive Summary

NAVORA continuously monitors inventory telemetry across multi-echelon warehouse networks, predicts stockout and overstock vulnerabilities, generates evaluated mitigation pathways (inter-warehouse transfers, expedited purchase orders, spot purchases), and empowers purchasing managers to inspect, modify, and execute actions with single-click confidence.

```
┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
│   Backend Analytics     │ ──► │  NAVORA Briefing Card   │ ──► │   Human-in-the-Loop     │
│  • Lead Time Models     │     │  • Root Cause Insights  │     │   • 1-Click Approval    │
│  • Consumption Trends   │     │  • Trade-off Matrix     │     │   • Conversational Edit │
│  • Multi-Echelon Stock  │     │  • Ready-to-Execute Doc │     │   • Instant Recalc Math │
└─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
                                                                             │
                                                                             ▼
                                                                ┌─────────────────────────┐
                                                                │  Execution & Receipts   │
                                                                │  • WMS/ERP Dispatch     │
                                                                │  • Virtual Ledger Sync  │
                                                                └─────────────────────────┘
```

---

## 2. Core Functional Modules

### 2.1. Autonomous Morning Briefing Feed
- **Proactive Anomaly Detection:** Scans all active SKUs across regional nodes and hubs to identify imminent stockouts before operations are disrupted.
- **Action-Oriented Headlines:** Delivers concise, urgent notifications directly into the manager's feed (e.g., *"Gokak Stockout Risk: Heavy-Duty Oil Filters"*).
- **Automated Root-Cause Synthesis:** Distills complex supply-demand distortions into a single explanatory sentence (e.g., distinguishing between supplier delivery delays, regional demand surges, or seasonal spikes).
- **Core Telemetry At-a-Glance:**
  - *Current Stock vs. Daily Consumption Rate (Burn Rate)*
  - *Remaining Days of Cover (DoC) vs. Replenishment Lead Time Gap*
  - *Calculated Exposure Window (Days at Zero Stock)*

---

### 2.2. Multi-Option Mitigation Engine
- **Cross-Pathway Strategy Generation:** Evaluates multiple resolution pathways simultaneously instead of offering a single rigid recommendation:
  1. **Inter-Warehouse Rebalancing:** Sourcing buffer units from nearby surplus facilities (e.g., Belgaum Hub → Gokak Regional Facility).
  2. **Expedited Purchase Orders:** Air freight or priority line dispatch with incumbent contracted suppliers.
  3. **Spot Market / Local Sourcing:** Engaging secondary pre-vetted suppliers for rapid fulfillment at a premium.
- **Comparative Trade-Off Matrix:**
  | Evaluation Vector | Description |
  | :--- | :--- |
  | **Speed / Lead Time** | Elapsed transit and processing time until stock arrives on dock. |
  | **Total Cost Impact** | Quantified surcharge (freight, expedited handling, unit premium). |
  | **Recommendation Status** | Ranked confidence score (`Recommended`, `Standby`, `Rejected - Cost Prohibitive`). |

---

### 2.3. Zero-Touch Action Drafting
- **Pre-Populated Execution Payloads:** Converts backend calculations into fully drafted operational documents without manual data entry:
  - **Transfer Requests (TR):** Pre-configures Source Warehouse, Destination Warehouse, SKU/Part Number, Allocated Quantity, and Freight Estimate.
  - **Purchase Orders (PO):** Pre-configures Vendor ID, Line Item pricing, Delivery Terms (Incoterms), and Rush Logistics instructions.
- **Inline Inspection Box:** Allows purchasing managers to review all essential metadata before signing off.

---

### 2.4. Human-in-the-Loop (HITL) Governance & Conversational Overrides
- **1-Click Approval & Execution:** Immediate one-tap sign-off (`[Approve & Execute]`) that initiates downstream dispatch.
- **Interactive Human Override (`[Reject / Modify]`):**
  - Accepts natural-language or structured modifications (e.g., *"Make it 20 units instead"*, *"Switch to Supplier B"*).
  - Captures managerial reasoning for audit compliance and model reinforcement.
- **Instant Math Re-Verification:**
  - Automatically recalculates **Days of Cover**, **Total Cost Impact**, and **Surplus Hub Impact** when any parameter is changed by the user.
  - Re-presents a revised draft with highlighted delta values for final sign-off.

---

### 2.5. Execution Receipts & Real-Time Ledger Synchronization
- **Simulated & Live Dispatch Confirmation:** Outputs an explicit execution receipt upon approval (e.g., *"Transfer Request TR-8821 dispatched to Belgaum warehouse"*).
- **Immediate Virtual Inventory Adjustment:**
  - Increments **Pending In-Transit** stock at the receiving facility (+12 units).
  - Decrements **Allocated** stock at the supplying hub (-12 units).
  - Prevents double-allocation across concurrent purchasing cycles.
- **Audit Logging:** Full cryptographic or timestamped log detailing initial backend recommendation, human overrides applied, and final dispatch payload.

---

## 3. Data Flow & Integration Architecture

### 3.1. Backend Input Schema (JSON Contract)
```json
{
  "incident_id": "INC-2026-8821",
  "facility_id": "FAC-GOKAK-01",
  "sku": "OF-4420",
  "sku_name": "Heavy-Duty Oil Filter",
  "current_stock": 6,
  "daily_burn_rate": 3.0,
  "days_of_cover": 2.0,
  "standard_lead_time_days": 6,
  "stockout_gap_days": 4,
  "root_cause": "40% maintenance demand spike combined with 4-day vendor shipment delay.",
  "mitigation_options": [
    {
      "option_id": "OPT-1",
      "type": "INTER_WAREHOUSE_TRANSFER",
      "source_facility": "FAC-BELGAUM-HUB",
      "speed_hours": 24,
      "cost_impact_usd": 45.0,
      "recommended": true,
      "quantity": 12
    },
    {
      "option_id": "OPT-2",
      "type": "EXPEDITED_PO",
      "supplier_id": "SUP-ALPHA",
      "speed_hours": 72,
      "cost_impact_usd": 180.0,
      "recommended": false,
      "quantity": 25
    }
  ]
}
```

### 3.2. Action Payload Schema (Execution Contract)
```json
{
  "action_type": "TRANSFER_ORDER",
  "request_id": "TR-8821",
  "source_warehouse": "Belgaum Distribution Center",
  "destination_warehouse": "Gokak Regional Facility",
  "sku": "OF-4420",
  "quantity": 12,
  "freight_cost": 45.00,
  "eta_hours": 24,
  "status": "DISPATCHED",
  "approval_metadata": {
    "approved_by": "Purchasing Manager",
    "timestamp": "2026-10-09T17:34:00Z",
    "overrides_applied": null
  }
}
```

---

## 4. Key Performance Indicators (KPIs) Impacted

| Metric | Traditional Workflow | With NAVORA |
| :--- | :--- | :--- |
| **Stockout Discovery Time** | 4–12 hours (manual reports / EOD sync) | **< 60 seconds (continuous)** |
| **Mitigation Decision Cycle** | 90 minutes (phone calls, spreadsheets, RFQs) | **< 3 minutes (review & sign-off)** |
| **Emergency Sourcing Premium** | High (frequent spot market buys) | **Optimized via multi-echelon transfers** |
| **Inventory Carrying Cost** | Inflated safety stock buffers | **Lean safety stock with fast cross-hub transfers** |
| **Audit Compliance** | Fragmented email trails | **100% centralized digital ledger receipts** |

---

## 5. Roadmap & Extensibility

- **Phase 1 (Current):** Stockout Risk Detection, Inter-Warehouse Transfer & PO Drafting, HITL Approval Flow, Simulated WMS Dispatches.
- **Phase 2:** Automated Carrier API Booking (Freight rate shopping & direct dispatch), Multi-Tier Supplier SLA tracking.
- **Phase 3:** Predictive Weather & Port Congestion Ingestion, Autonomous Counter-Offer Negotiation Bot with Suppliers.

---

## 6. Design System: "Terracotta & Warm Cream" Aesthetic

NAVORA features a bespoke, editorial UI/UX theme with dual Light Mode and Dark Mode support:

### 6.1. Light Mode Tokens
* **Background (`--bg`):** Soft warm cream `#FAF6F0`
* **Surface Containers (`--surface`):** Pure crisp white `#FFFFFF` with soft ambient diffusion
* **Secondary Containers (`--surface-muted`):** Light warm stone `#F0EAE1`
* **Primary Typography (`--text-main`):** Deep espresso brown `#2C221E`
* **Secondary Typography (`--text-sub`):** Muted warm taupe `#6B5E57`
* **Buttons & Call-to-Actions (`--primary`):** Vibrant terracotta `#C85A32` (Hover: `#B04B26`)
* **Alert & Error Panels (`--danger`):** Electric Neon Red `#FF0033` (High-intensity neon glow, eliminating clash with warm terracotta)
* **Borders & Dividers (`--border`):** Soft warm tone `#E2D7CB`

### 6.2. Dark Mode Tokens
* **Background (`--bg`):** Deep charcoal brown `#181412`
* **Surface Containers (`--surface`):** Elevated warm dark `#241E1B`
* **Secondary Containers (`--surface-muted`):** Muted brown-grey `#322B27`
* **Primary Typography (`--text-main`):** Creamy off-white `#FAF6F0`
* **Secondary Typography (`--text-sub`):** Warm soft sand `#B0A298`
* **Buttons & Call-to-Actions (`--primary`):** Luminous warm terracotta `#E07A5F` (Hover: `#EA8E75`)
* **Alert & Error Panels (`--danger`):** Radiant Neon Red `#FF1744` (Vivid neon aura `0 0 22px rgba(255, 23, 68, 0.5)`)
* **Borders & Dividers (`--border`):** Subtle dark brown `#3B312C`

### 6.3. Typography Hierarchy
* **Editorial Headlines:** `Fraunces` serif (weights 600, 700, 800) for high-impact briefing titles.
* **Interface Body & Controls:** `Plus Jakarta Sans` for responsive layouts and tables.
* **Data & Financial Telemetry:** `JetBrains Mono` for SKU IDs, quantities, and audit timestamps.

