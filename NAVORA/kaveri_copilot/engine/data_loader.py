"""
Kaveri Spares & Hydraulics - Ingestion Schemas & Robust Data Loader.
Validates multi-echelon operational data across the 5 core tables with Pydantic:
products, inventory, sales, suppliers, and purchase_orders.
Provides column case-insensitivity, column order tolerance, alias resolution,
and support for both JSON and CSV files with sensible defaults.
"""

import csv
import json
import os
from typing import Dict, List, Any, Optional, Type, Union
import pandas as pd
from pydantic import BaseModel, Field, ConfigDict


def _to_clean_dict(model_instance: BaseModel) -> Dict[str, Any]:
    if hasattr(model_instance, "model_dump"):
        return model_instance.model_dump()
    return model_instance.dict()


# ---------------------------------------------------------------------------
# Pydantic Schemas for 5 Core Datasets
# ---------------------------------------------------------------------------

class ProductRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str
    name: str = ""
    machine_model: str = "Universal"
    category: str = "General"


class InventoryRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str
    location: str
    stock: int = Field(default=0, ge=0)


class SalesRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sku: str
    location: str
    date: str
    qty_sold: int = Field(default=0, ge=0)


class SupplierRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    supplier: str
    sku: str
    price: float = Field(default=1000.0, gt=0)
    lead_time_days: int = Field(default=7, ge=1)
    moq: int = Field(default=1, ge=1)
    is_primary: bool = False
    quoted_lead_time_days: Optional[int] = None
    adjusted_lead_time_days: Optional[int] = None


class PurchaseOrderRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    po: str
    supplier: str
    sku: str
    location: str
    qty: int = Field(default=1, ge=0)
    expected_date: str
    status: str = "PENDING"
    remaining_qty: Optional[int] = None
    received_qty: int = 0
    delivered_qty: int = 0


# ---------------------------------------------------------------------------
# Field Normalization & Alias Resolution
# ---------------------------------------------------------------------------

ALIASES = {
    "current_stock": "stock",
    "gross_stock": "stock",
    "quantity": "qty",
    "units": "qty",
    "units_sold": "qty_sold",
    "quantity_sold": "qty_sold",
    "sold_qty": "qty_sold",
    "vendor": "supplier",
    "supplier_name": "supplier",
    "cost": "price",
    "unit_price": "price",
    "lead_time": "lead_time_days",
    "lt_days": "lead_time_days",
    "minimum_order_qty": "moq",
    "po_number": "po",
    "po_id": "po",
    "part_number": "sku",
    "item_code": "sku",
    "due_date": "expected_date",
    "delivery_date": "expected_date",
}


def normalize_record_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Lowercases keys, strips whitespace, and resolves known field aliases."""
    normalized: Dict[str, Any] = {}
    for k, v in raw.items():
        clean_k = str(k).strip().lower().replace(" ", "_")
        target_k = ALIASES.get(clean_k, clean_k)
        normalized[target_k] = v
    return normalized


def validate_records(
    records: List[Dict[str, Any]],
    schema_cls: Type[BaseModel]
) -> List[Dict[str, Any]]:
    """Validates and normalizes records against the specified Pydantic schema."""
    validated = []
    for r in records:
        clean_r = normalize_record_dict(r)
        # Context-sensitive alias fallback
        if schema_cls is InventoryRecord and "stock" not in clean_r:
            clean_r["stock"] = clean_r.get("qty", clean_r.get("quantity", 0))
        elif schema_cls is PurchaseOrderRecord and "qty" not in clean_r:
            clean_r["qty"] = clean_r.get("quantity", clean_r.get("stock", 1))
        elif schema_cls is SalesRecord and "qty_sold" not in clean_r:
            clean_r["qty_sold"] = clean_r.get("qty", clean_r.get("quantity", 0))

        parsed = schema_cls(**clean_r)
        validated.append(_to_clean_dict(parsed))
    return validated


# ---------------------------------------------------------------------------
# File Loaders (JSON / CSV)
# ---------------------------------------------------------------------------

def load_file_records(file_path: str) -> List[Dict[str, Any]]:
    """Reads JSON or CSV file into list of dictionaries."""
    if not os.path.exists(file_path):
        return []

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return [data]
    elif ext == ".csv":
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    else:
        raise ValueError(f"Unsupported file format '{ext}' for file {file_path}")


def load_dataset_from_dir(
    data_dir: str,
    table_name: str,
    schema_cls: Type[BaseModel]
) -> List[Dict[str, Any]]:
    """Loads a table from data_dir trying both .json and .csv extensions."""
    json_path = os.path.join(data_dir, f"{table_name}.json")
    csv_path = os.path.join(data_dir, f"{table_name}.csv")

    target_path = None
    if os.path.exists(json_path):
        target_path = json_path
    elif os.path.exists(csv_path):
        target_path = csv_path

    if not target_path:
        return []

    raw = load_file_records(target_path)
    return validate_records(raw, schema_cls)


def load_validated_datasets(data_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    """Loads and validates all 5 core datasets from data_dir."""
    return {
        "products": load_dataset_from_dir(data_dir, "products", ProductRecord),
        "inventory": load_dataset_from_dir(data_dir, "inventory", InventoryRecord),
        "sales": load_dataset_from_dir(data_dir, "sales", SalesRecord),
        "suppliers": load_dataset_from_dir(data_dir, "suppliers", SupplierRecord),
        "purchase_orders": load_dataset_from_dir(data_dir, "purchase_orders", PurchaseOrderRecord),
    }


def load_products(source: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    records = load_file_records(source) if isinstance(source, str) else source
    return validate_records(records, ProductRecord)


def load_inventory(source: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    records = load_file_records(source) if isinstance(source, str) else source
    return validate_records(records, InventoryRecord)


def load_sales(source: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    records = load_file_records(source) if isinstance(source, str) else source
    return validate_records(records, SalesRecord)


def load_suppliers(source: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    records = load_file_records(source) if isinstance(source, str) else source
    return validate_records(records, SupplierRecord)


def load_purchase_orders(source: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    records = load_file_records(source) if isinstance(source, str) else source
    return validate_records(records, PurchaseOrderRecord)
