# Kaveri Spares Copilot — UI Notes & Observations

## Initial Setup Notes (Run 1)
- **Branch Created**: `ui-refresh`
- **Streamlit Version**: 1.52.1 (supports native `st.dialog`, `st.fragment`, `st.toast`, and minimal toolbar).
- **Baseline Viewports Captured**:
  - Desktop wide: 1440x900 (`ui_shots/before/baseline_1440x900.png`)
  - Standard laptop: 1366x768 (`ui_shots/before/baseline_1366x768.png`)
  - Mobile: 390x844 (`ui_shots/before/baseline_390x844.png`)
  - Tabs 2, 3, 4 captured (`ui_shots/before/tab2_inventory.png`, `tab3_supplier.png`, `tab4_audit_trail.png`)

## Discrepancies & Backend Observations (To be addressed in T3/T5)
1. **Category Codes Mapping**:
   - `CATEGORY_A`: Critical hydraulic components / functional mission-critical spares.
   - `CATEGORY_B`: Maintenance wear items / intermediate components.
   - `CATEGORY_C`: General hardware and consumable parts.
2. **Numbers & Math (For T3 reconciliation)**:
   - Hubli PUMP-GEAR-03 stock vs cover: Currently displays 2 units stock and 4.0d cover at burn rate 1.0 (reconciliation inputs will be rendered explicitly in "How this was calculated").
   - Revenue at risk vs scorecard averted units.
   - Urgency label alignment: Ensure CRITICAL expedite displays high urgency rather than standard draft default.
