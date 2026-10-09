"""Central Configuration Constants for Kaveri Spares & Hydraulics Supply Chain Copilot.

Single source of truth for all operational thresholds, cost rates, and default parameters.
"""

# Simulation anchor
DEFAULT_SIMULATION_DATE: str = "2026-10-09"

# Cost & Economics Constants
DEFAULT_TRANSFER_HANDLING_COST: float = 250.0  # Flat inter-store dispatch handling / logistics cost (INR)
DEFAULT_TRANSFER_UNIT_FREIGHT: float = 15.0   # Per unit freight / transport cost (INR)
ANNUAL_HOLDING_COST_RATE: float = 0.22        # 22% annual inventory holding cost rate
DAILY_HOLDING_COST_RATE: float = ANNUAL_HOLDING_COST_RATE / 365.0

# Safety Buffers & Inventory Policies
DEFAULT_DONOR_MIN_COVER_DAYS: float = 15.0   # Mandatory post-transfer retention buffer (days)
DEFAULT_DONOR_SAFETY_DAYS: float = 5.0        # Buffer days added to donor primary lead time
DEFAULT_SAFETY_STOCK_DAYS: float = 5.0       # Target safety stock buffer days
DEFAULT_CAPITAL_TRAP_DAYS: float = 45.0       # Fallback reference (superseded by per-SKU target cover)
DEFAULT_REVIEW_PERIOD_DAYS: float = 7.0       # Standard inventory review period (days)
DEFAULT_ROUTE_TRANSIT_DAYS: int = 1           # Standard inter-store logistics transit time (days)

# Demand Velocity & Trend Thresholds
VELOCITY_RECENT_WINDOW_DAYS: int = 7
VELOCITY_BASELINE_WINDOW_DAYS: int = 30
TREND_ACCELERATING_THRESHOLD: float = 1.5
TREND_DECELERATING_THRESHOLD: float = 0.4
SURGE_EXPLOSIVE_RATIO: float = 1.8
SURGE_MIN_RECENT_VELOCITY: float = 2.0
CLIFF_DROP_RATIO: float = 0.3
MIN_VELOCITY_VOLUME_THRESHOLD: int = 3          # Minimum total sales volume required to trigger trend classification
VELOCITY_BLENDING_ALPHA: float = 0.65            # Weight assigned to recent velocity in EWMA/blended forecast

# Supplier Friction & Order Sizing
MOQ_OVERPURCHASE_RATIO_THRESHOLD: float = 3.0 # Ratio of MOQ to needed units triggering friction flag
DEFAULT_EXPEDITE_PREMIUM_PCT: float = 0.15    # 15% price surcharge for expedited vendor shipments
DEFAULT_EXPEDITED_LEAD_TIME_DAYS: int = 2     # Default expedited transit if unstated

# Severity Formula Weights (Margin at risk / time to stockout)
SEVERITY_CRITICAL_RATIO: float = 2500.0       # INR margin at risk per day to stockout (CRITICAL >= 2500)
SEVERITY_HIGH_RATIO: float = 800.0           # INR margin at risk per day to stockout (HIGH >= 800)

# Reservation Time-To-Live (seconds)
RESERVATION_TTL_SECONDS: int = 1800           # 30-minute expiry for uncommitted transfer holds
