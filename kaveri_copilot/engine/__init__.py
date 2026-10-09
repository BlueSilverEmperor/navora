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
    clamp_inventory_projection
)
from engine.decision_agent import (
    find_best_donor_location,
    find_best_donor_location_with_reservations,
    DecisionEngine
)


