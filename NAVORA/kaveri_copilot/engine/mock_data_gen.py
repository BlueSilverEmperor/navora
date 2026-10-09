"""
Kaveri Spares & Hydraulics - Mock Data Generator
Generates realistic multi-echelon inventory, sales, suppliers, and PO data
for 6 stores and 2 warehouses across North Karnataka.
"""

import json
import os
from datetime import datetime, timedelta

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

CURRENT_DATE = "2026-10-09"

LOCATIONS = [
    "Gokak",
    "Belgaum",
    "Dharwad",
    "Hubli",
    "Bagalkot",
    "Nippani",
    "Belgaum Central Warehouse",
    "Hubli Regional Warehouse"
]

PRODUCTS = [
    {
        "sku": "FILTER-HYD-01",
        "name": "Return Line Hydraulic Filter",
        "machine_model": "JCB 3DX",
        "category": "Hydraulic Filtration"
    },
    {
        "sku": "VALVE-CTRL-02",
        "name": "Proportional Main Control Valve",
        "machine_model": "Komatsu PC210",
        "category": "Hydraulic Valves"
    },
    {
        "sku": "PUMP-GEAR-03",
        "name": "Main Hydraulic Gear Pump",
        "machine_model": "Tata Hitachi EX200",
        "category": "Hydraulic Pumps"
    },
    {
        "sku": "SEAL-KIT-04",
        "name": "Boom Cylinder Seal Kit",
        "machine_model": "Mahindra 575 DI",
        "category": "Seals & O-Rings"
    },
    {
        "sku": "HOSE-ASSEM-05",
        "name": "High-Pressure Wire Braid Hose 1/2\"",
        "machine_model": "CAT 424B",
        "category": "Hydraulic Hoses"
    },
    {
        "sku": "MOTOR-PIST-06",
        "name": "Axial Piston Slew Motor",
        "machine_model": "Kobelco SK210",
        "category": "Hydraulic Motors"
    }
]

SUPPLIERS = [
    # FILTER-HYD-01: Primary vs Secondary
    {
        "supplier": "Kirloskar Fluid Filters Pune",
        "sku": "FILTER-HYD-01",
        "price": 850.0,
        "lead_time_days": 7,
        "moq": 50,
        "is_primary": True
    },
    {
        "supplier": "FastTrack Spares Bengaluru",
        "sku": "FILTER-HYD-01",
        "price": 935.0,  # 10% markup
        "lead_time_days": 3,
        "moq": 20,
        "is_primary": False
    },
    # VALVE-CTRL-02
    {
        "supplier": "Komatsu India Spares Chennai",
        "sku": "VALVE-CTRL-02",
        "price": 24500.0,
        "lead_time_days": 14,
        "moq": 5,
        "is_primary": True
    },
    # PUMP-GEAR-03
    {
        "supplier": "Deccan Fluid Power Hosur",
        "sku": "PUMP-GEAR-03",
        "price": 14200.0,
        "lead_time_days": 10,
        "moq": 10,
        "is_primary": True
    },
    {
        "supplier": "Hubli Spot Hydraulics",
        "sku": "PUMP-GEAR-03",
        "price": 16500.0,
        "lead_time_days": 2,
        "moq": 2,
        "is_primary": False
    },
    # SEAL-KIT-04: Primary (long lead time) vs Secondary (fast, Belgaum based)
    {
        "supplier": "Precision Polymers Pune",
        "sku": "SEAL-KIT-04",
        "price": 650.0,
        "lead_time_days": 8,
        "moq": 50,
        "is_primary": True
    },
    {
        "supplier": "HydroSeal Belgaum Express",
        "sku": "SEAL-KIT-04",
        "price": 780.0,
        "lead_time_days": 2,
        "moq": 25,
        "is_primary": False
    },
    # HOSE-ASSEM-05
    {
        "supplier": "Gates Fluid Power India",
        "sku": "HOSE-ASSEM-05",
        "price": 1250.0,
        "lead_time_days": 5,
        "moq": 30,
        "is_primary": True
    },
    # MOTOR-PIST-06
    {
        "supplier": "Danfoss Hydraulics Pune",
        "sku": "MOTOR-PIST-06",
        "price": 38000.0,
        "lead_time_days": 15,
        "moq": 2,
        "is_primary": True
    }
]

INVENTORY = [
    # Benchmark scenario: FILTER-HYD-01 at Gokak (8) vs Belgaum (40)
    {"sku": "FILTER-HYD-01", "location": "Gokak", "stock": 8},
    {"sku": "FILTER-HYD-01", "location": "Belgaum", "stock": 40},
    {"sku": "FILTER-HYD-01", "location": "Dharwad", "stock": 14},
    {"sku": "FILTER-HYD-01", "location": "Hubli", "stock": 18},
    {"sku": "FILTER-HYD-01", "location": "Bagalkot", "stock": 10},
    {"sku": "FILTER-HYD-01", "location": "Nippani", "stock": 12},
    {"sku": "FILTER-HYD-01", "location": "Belgaum Central Warehouse", "stock": 65},
    {"sku": "FILTER-HYD-01", "location": "Hubli Regional Warehouse", "stock": 8},

    # Capital trap: VALVE-CTRL-02 at Bagalkot (15, dead stock) vs Dharwad (1, starved)
    {"sku": "VALVE-CTRL-02", "location": "Gokak", "stock": 2},
    {"sku": "VALVE-CTRL-02", "location": "Belgaum", "stock": 3},
    {"sku": "VALVE-CTRL-02", "location": "Dharwad", "stock": 1},
    {"sku": "VALVE-CTRL-02", "location": "Hubli", "stock": 4},
    {"sku": "VALVE-CTRL-02", "location": "Bagalkot", "stock": 15},
    {"sku": "VALVE-CTRL-02", "location": "Nippani", "stock": 1},
    {"sku": "VALVE-CTRL-02", "location": "Belgaum Central Warehouse", "stock": 6},
    {"sku": "VALVE-CTRL-02", "location": "Hubli Regional Warehouse", "stock": 8},

    # Overdue PO: PUMP-GEAR-03 at Hubli (2)
    {"sku": "PUMP-GEAR-03", "location": "Gokak", "stock": 3},
    {"sku": "PUMP-GEAR-03", "location": "Belgaum", "stock": 4},
    {"sku": "PUMP-GEAR-03", "location": "Dharwad", "stock": 2},
    {"sku": "PUMP-GEAR-03", "location": "Hubli", "stock": 2},
    {"sku": "PUMP-GEAR-03", "location": "Bagalkot", "stock": 2},
    {"sku": "PUMP-GEAR-03", "location": "Nippani", "stock": 1},
    {"sku": "PUMP-GEAR-03", "location": "Belgaum Central Warehouse", "stock": 5},
    {"sku": "PUMP-GEAR-03", "location": "Hubli Regional Warehouse", "stock": 4},

    # Stockout with no network surplus: SEAL-KIT-04 at Nippani (0)
    {"sku": "SEAL-KIT-04", "location": "Gokak", "stock": 3},
    {"sku": "SEAL-KIT-04", "location": "Belgaum", "stock": 4},
    {"sku": "SEAL-KIT-04", "location": "Dharwad", "stock": 2},
    {"sku": "SEAL-KIT-04", "location": "Hubli", "stock": 3},
    {"sku": "SEAL-KIT-04", "location": "Bagalkot", "stock": 2},
    {"sku": "SEAL-KIT-04", "location": "Nippani", "stock": 0},
    {"sku": "SEAL-KIT-04", "location": "Belgaum Central Warehouse", "stock": 5},
    {"sku": "SEAL-KIT-04", "location": "Hubli Regional Warehouse", "stock": 4},

    # Healthy lines: HOSE-ASSEM-05
    {"sku": "HOSE-ASSEM-05", "location": "Gokak", "stock": 25},
    {"sku": "HOSE-ASSEM-05", "location": "Belgaum", "stock": 35},
    {"sku": "HOSE-ASSEM-05", "location": "Dharwad", "stock": 20},
    {"sku": "HOSE-ASSEM-05", "location": "Hubli", "stock": 40},
    {"sku": "HOSE-ASSEM-05", "location": "Bagalkot", "stock": 18},
    {"sku": "HOSE-ASSEM-05", "location": "Nippani", "stock": 22},
    {"sku": "HOSE-ASSEM-05", "location": "Belgaum Central Warehouse", "stock": 110},
    {"sku": "HOSE-ASSEM-05", "location": "Hubli Regional Warehouse", "stock": 95},

    # MOTOR-PIST-06
    {"sku": "MOTOR-PIST-06", "location": "Gokak", "stock": 2},
    {"sku": "MOTOR-PIST-06", "location": "Belgaum", "stock": 4},
    {"sku": "MOTOR-PIST-06", "location": "Dharwad", "stock": 3},
    {"sku": "MOTOR-PIST-06", "location": "Hubli", "stock": 5},
    {"sku": "MOTOR-PIST-06", "location": "Bagalkot", "stock": 2},
    {"sku": "MOTOR-PIST-06", "location": "Nippani", "stock": 1},
    {"sku": "MOTOR-PIST-06", "location": "Belgaum Central Warehouse", "stock": 8},
    {"sku": "MOTOR-PIST-06", "location": "Hubli Regional Warehouse", "stock": 7}
]

PURCHASE_ORDERS = [
    # Overdue PO for PUMP-GEAR-03 at Hubli
    {
        "po": "PO-2026-0892",
        "supplier": "Deccan Fluid Power Hosur",
        "sku": "PUMP-GEAR-03",
        "location": "Hubli",
        "qty": 10,
        "expected_date": "2026-10-04",  # 5 days overdue relative to 2026-10-09
        "status": "DELAYED"
    },
    # Healthy PO for HOSE-ASSEM-05
    {
        "po": "PO-2026-0901",
        "supplier": "Gates Fluid Power India",
        "sku": "HOSE-ASSEM-05",
        "location": "Belgaum Central Warehouse",
        "qty": 50,
        "expected_date": "2026-10-14",
        "status": "IN_TRANSIT"
    }
]


def generate_sales_history():
    """Generates 30 days of sales history matching required burn rates."""
    sales = []
    base_date = datetime.strptime(CURRENT_DATE, "%Y-%m-%d")

    # Defined 30-day totals:
    # FILTER-HYD-01:
    # Gokak: 120 total -> 4.0/day
    # Belgaum: 15 total -> 0.5/day
    # VALVE-CTRL-02:
    # Bagalkot: 0 total -> 0.0/day (Dead stock)
    # Dharwad: 12 total -> 0.4/day
    # PUMP-GEAR-03:
    # Hubli: 15 total -> 0.5/day
    # SEAL-KIT-04:
    # Nippani: 45 total -> 1.5/day

    pattern_map = {
        ("FILTER-HYD-01", "Gokak"): 120,
        ("FILTER-HYD-01", "Belgaum"): 15,
        ("FILTER-HYD-01", "Dharwad"): 30,
        ("FILTER-HYD-01", "Hubli"): 35,
        ("FILTER-HYD-01", "Bagalkot"): 20,
        ("FILTER-HYD-01", "Nippani"): 24,
        ("FILTER-HYD-01", "Belgaum Central Warehouse"): 15,
        ("FILTER-HYD-01", "Hubli Regional Warehouse"): 20,

        ("VALVE-CTRL-02", "Bagalkot"): 0,  # DEAD STOCK!
        ("VALVE-CTRL-02", "Dharwad"): 12,
        ("VALVE-CTRL-02", "Gokak"): 3,
        ("VALVE-CTRL-02", "Belgaum"): 6,
        ("VALVE-CTRL-02", "Hubli"): 6,
        ("VALVE-CTRL-02", "Nippani"): 3,
        ("VALVE-CTRL-02", "Belgaum Central Warehouse"): 3,
        ("VALVE-CTRL-02", "Hubli Regional Warehouse"): 6,

        ("PUMP-GEAR-03", "Hubli"): 15,
        ("PUMP-GEAR-03", "Gokak"): 6,
        ("PUMP-GEAR-03", "Belgaum"): 9,
        ("PUMP-GEAR-03", "Dharwad"): 6,
        ("PUMP-GEAR-03", "Bagalkot"): 6,
        ("PUMP-GEAR-03", "Nippani"): 3,
        ("PUMP-GEAR-03", "Belgaum Central Warehouse"): 6,
        ("PUMP-GEAR-03", "Hubli Regional Warehouse"): 6,

        ("SEAL-KIT-04", "Nippani"): 45,
        ("SEAL-KIT-04", "Gokak"): 15,
        ("SEAL-KIT-04", "Belgaum"): 20,
        ("SEAL-KIT-04", "Dharwad"): 18,
        ("SEAL-KIT-04", "Hubli"): 25,
        ("SEAL-KIT-04", "Bagalkot"): 15,
        ("SEAL-KIT-04", "Belgaum Central Warehouse"): 15,
        ("SEAL-KIT-04", "Hubli Regional Warehouse"): 12,

        ("HOSE-ASSEM-05", "Gokak"): 30,
        ("HOSE-ASSEM-05", "Belgaum"): 45,
        ("HOSE-ASSEM-05", "Dharwad"): 30,
        ("HOSE-ASSEM-05", "Hubli"): 60,
        ("HOSE-ASSEM-05", "Bagalkot"): 24,
        ("HOSE-ASSEM-05", "Nippani"): 30,
        ("HOSE-ASSEM-05", "Belgaum Central Warehouse"): 30,
        ("HOSE-ASSEM-05", "Hubli Regional Warehouse"): 30,

        ("MOTOR-PIST-06", "Gokak"): 3,
        ("MOTOR-PIST-06", "Belgaum"): 6,
        ("MOTOR-PIST-06", "Dharwad"): 3,
        ("MOTOR-PIST-06", "Hubli"): 6,
        ("MOTOR-PIST-06", "Bagalkot"): 3,
        ("MOTOR-PIST-06", "Nippani"): 0,
        ("MOTOR-PIST-06", "Belgaum Central Warehouse"): 3,
        ("MOTOR-PIST-06", "Hubli Regional Warehouse"): 3
    }

    for (sku, loc), target_total in pattern_map.items():
        if target_total == 0:
            continue
        # Distribute target_total across 30 days
        base_per_day = target_total // 30
        remainder = target_total % 30
        for day_offset in range(30):
            d = base_date - timedelta(days=29 - day_offset)
            qty = base_per_day + (1 if day_offset < remainder else 0)
            if qty > 0:
                sales.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "sku": sku,
                    "location": loc,
                    "qty_sold": qty
                })

    return sales


def seed_all_data(target_dir=DATA_DIR):
    os.makedirs(target_dir, exist_ok=True)

    sales = generate_sales_history()

    with open(os.path.join(target_dir, "products.json"), "w", encoding="utf-8") as f:
        json.dump(PRODUCTS, f, indent=2)

    with open(os.path.join(target_dir, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(INVENTORY, f, indent=2)

    with open(os.path.join(target_dir, "sales.json"), "w", encoding="utf-8") as f:
        json.dump(sales, f, indent=2)

    with open(os.path.join(target_dir, "suppliers.json"), "w", encoding="utf-8") as f:
        json.dump(SUPPLIERS, f, indent=2)

    with open(os.path.join(target_dir, "purchase_orders.json"), "w", encoding="utf-8") as f:
        json.dump(PURCHASE_ORDERS, f, indent=2)

    print(f"[OK] Seeded Kaveri Spares & Hydraulics data to {target_dir}")


if __name__ == "__main__":
    seed_all_data()
