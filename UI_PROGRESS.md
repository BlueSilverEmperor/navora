# Kaveri Spares Copilot — UI Refresh Progress

## Code Map
- **Entry Point**: `kaveri_copilot/app/dashboard.py` (run via `streamlit run app/dashboard.py` from `kaveri_copilot/`)
- **Backend API**: `kaveri_copilot/app/server.py`
- **CSS / Styling**:
  - Embedded CSS currently in `kaveri_copilot/app/dashboard.py` lines 48–467.
  - Cyber-amber/obsidian theme tokens to be migrated to `.streamlit/config.toml` and a unified CSS file in `ui/`.
- **Chart Styling**:
  - `format_cyber_plotly_figure()` in `dashboard.py` (lines 796–817).
  - Main forward trajectory chart (lines 1002–1065).
  - Counter-proposal recalibration chart (lines 1150–1185).
- **State & Domain Engine**:
  - `engine/decision_agent.py` (`DecisionEngine.run_agentic_pipeline()`)
  - `engine/domain_math.py` (`validate_and_recalculate_transfer()`, `generate_14day_projections()`, `compute_plan_diff()`)
  - `engine/data_loader.py` (`DataLoader`)
  - `engine/persistence.py` (`load_audit()`, `save_audit()`)
  - `data/` (`inventory.json`, `sales.json`, `suppliers.json`, `products.json`, `audit_log.json`)
- **App Structure & Tabs**:
  - **Sidebar**: Simulation Date, Persona (Ramesh Kulkarni), Operations Network (6 stores, 2 hubs), Chaos Engine controls.
  - **Top Banner & KPIs**: Executive header, Chaos plan diff banner (if active), 4 KPI cards (Total Operational Issues, Critical Stockouts, Top Attention SKU, Pending Human Gate), 60-day historical backtest strip.
  - **Tab 1: 🚨 Morning Action Feed & Approval Gate**:
    - Left column (38%): Task worklist cards with severity filter and active task selection.
    - Right column (62%): Resolution Cockpit with diagnosis banner, AI recommendation, Commercial impact scorecard, 14-day trajectory chart, Feasible pathways table, Simulated action execution box with Ramesh counter-proposal override slider, and Approve/Reject buttons.
  - **Tab 2: 🏭 Multi-Echelon Network Inventory**:
    - Enriched multi-echelon stock table across 6 stores and 2 hubs with SKU filter dropdown.
  - **Tab 3: 🔍 Supplier Friction & Reliability Audit**:
    - Supplier table evaluating contract price, quoted vs adjusted lead time, slippage, on-time rate, reliability status, and MOQ friction risk.
  - **Tab 4: 📜 Immutable Audit Trail**:
    - Complete log of Ramesh Kulkarni's approvals, overrides, and rejections.

## Baseline Evidence
Saved baseline screenshots in `ui_shots/before/`:
- `ui_shots/before/baseline_1440x900.png` — Main dashboard at 1440x900
- `ui_shots/before/baseline_1366x768.png` — Main dashboard at 1366x768
- `ui_shots/before/baseline_390x844.png` — Mobile view at 390x844
- `ui_shots/before/tab2_inventory.png` — Tab 2: Multi-Echelon Network Inventory
- `ui_shots/before/tab3_supplier.png` — Tab 3: Supplier Friction & Reliability Audit
- `ui_shots/before/tab4_audit_trail.png` — Tab 4: Immutable Audit Trail

---

## Tasks
- [x] T1 Theme: Sage Green Design System & Universal Light/Dark Theme (Streamlit `st.session_state.theme_mode` + HTML SPA `data-theme` & `localStorage`). Done: Dual-mode Earthy Sage & Warm Cream (Light) ⟷ Obsidian Olive & Bioluminescent Sage (Dark) fully implemented across both Streamlit cockpit and NAVORA SPA with adaptive Plotly figures, high WCAG contrast, zero white-on-white bugs, and verified across all 4 operational tabs.
- [ ] T2 Formatting helpers (`ui/format.py` + tests) for rupees, days, plurals, dates, sentinels; replace all ad-hoc formatting. Done when: 142000 -> "₹1,42,000", 1 -> "1 day", 999 -> "No recent demand".
- [ ] T3 Numbers reconcile on screen: check every displayed figure against its formula and show the inputs used. Known examples: Hubli PUMP-GEAR-03 shows 2 units at 1.00/day but 4.0 days of stock left; revenue at risk (₹29,820 / ₹4,970) implies 6 units short but the scorecard says 3.0 averted; the approval card says Urgency: STANDARD on a CRITICAL expedite. Done when: every figure in the detail panel is traceable in "How this was calculated" and each mismatch is in `UI_NOTES.md`.
- [ ] T4 Detail panel, answer first: item header -> recommendation card (one plain sentence, cost, arrival date, revenue protected, what happens if nothing is done, runway bar, Approve / Reject / Compare options) -> options -> chart -> expanders ("How this was calculated", "Supplier history", "Draft message"). Done when: at 1366x768 the primary action is visible without scrolling and the math is collapsed by default.
- [ ] T5 Options as choosable cards: 2-3 radio-style cards with a "Recommended" badge, arrival, cost, what it protects and a one-line trade-off; selecting one updates the recommendation card, chart emphasis and approval summary; drop the "Feasibility" column unless an option is infeasible; no "N ≥ 2" in the UI. If the existing action code can only execute the recommended option, make the others compare-only and log the backend change needed in `UI_NOTES.md`. Done when: choosing another option changes the summary and chart emphasis, and the recommended one is preselected.
- [ ] T6 Chart: one line per option, same names and colours as the cards; legend below the plot; left-aligned title above it; mark the stockout day (or "Covered through day 14"); label the zero line; selected option bold, others muted; distinct dash styles; modebar hidden. Done when: no title/legend overlap at 1366 and 390 widths and legend labels equal option names.
- [ ] T7 Approve/reject flow: Approve opens a confirmation (`st.dialog` if available) showing exactly what will be sent (the draft text if one exists, otherwise supplier, quantity, cost, arrival and urgency in plain words); then a toast, and the item moves to "Done today". Reject asks for a reason (price, prefer another supplier, wrong quantity, other + note). Both write to the existing audit trail using its current schema. Done when: the audit-trail tab shows the entry with option and reason and the pending count drops.
- [ ] T8 Task list: group by urgency using existing severity and gap fields: "Decide now" (short before restock), "Review soon" (everything else needing a decision), "No action needed" (collapsed). If every item truly needs a decision, note it in `UI_NOTES.md` rather than changing logic. Filters for severity, store and search. Each card: SKU, store, plain-language reason, runway bar (red only for the shortfall, none when there is no gap). The whole card is the click target; remove the separate "Inspect evidence" buttons. Done when: zero-gap items are never styled as problems and the selected item is obvious.
- [ ] T9 KPI strip: revenue at risk (sum of existing per-item values), decisions needed now, items short before restock, decided today. Real deltas only. Done when: counts match the list and no arrow appears without a real change.
- [ ] T10 Sidebar: simulation date, then "Demo controls" (the Chaos Engine) with plain labels and a one-line explanation; after injecting a shock, show what changed (e.g. "+3 critical") and tag affected items "Changed". Persona and network collapse into one compact expander.
- [ ] T11 Other tabs (inventory, supplier reliability, audit trail; the designer has not seen them): bring them in line using the same tokens and components: searchable, sortable tables, status chips, sticky headers, empty states; audit trail filterable by action and date. Done when: no stray inline colours and no horizontal scroll at 1366.
- [ ] T12 Accessibility and responsive: text contrast >= 4.5:1, visible focus ring, severity never conveyed by colour alone (add an icon or label), tap targets >= 40px, columns stack below 900px. Check at 1440, 1366, 1024 and 390.
- [ ] T13 States and polish: empty ("All clear, nothing needs a decision"), loading, and error states that say what to do; subtle transitions on select/approve only; avoid full-page reruns when selecting an option (`st.fragment` if available). Done when: each state can be triggered and looks intentional.
- [ ] T14 Final QA: script the full path (select the critical item, read the recommendation, pick an alternative, approve, check the audit trail; inject a demand spike and confirm KPIs and list update; reject with a reason). Save before/after shots in `ui_shots/compare.md` and summarise open issues in `UI_NOTES.md`.
