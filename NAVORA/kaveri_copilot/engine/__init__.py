"""
Kaveri Spares & Hydraulics - Supply Chain Copilot Engine
Domain Mathematics & Agentic Decision Matrix
"""

from engine.domain_math import (
    compute_adaptive_velocity,
    calculate_donor_transfer_safety,
    generate_14day_projections,
    validate_and_recalculate_transfer,
    calculate_daily_burn_rate,
    calculate_days_of_cover,
    calculate_stockout_gap,
    evaluate_sku_location,
    check_is_po_overdue,
    clamp_inventory_projection,
    compute_sku_target_cover,
    compute_severity,
    compute_option_expected_cost,
    compute_incident_scorecard,
    simulate_monte_carlo_projections
)
from engine.decision_agent import (
    find_best_donor_location,
    find_best_donor_location_with_reservations,
    DecisionEngine
)
from engine.llm_layer import (
    LLMLayer,
    NumberGuard,
    HallucinatedNumberError,
    UserIntentAction,
)
from engine.global_optimizer import solve_global_transfer_network
from engine.data_loader import (
    ProductRecord,
    InventoryRecord,
    SalesRecord,
    SupplierRecord,
    PurchaseOrderRecord,
    load_validated_datasets,
    load_products,
    load_inventory,
    load_sales,
    load_suppliers,
    load_purchase_orders,
)


