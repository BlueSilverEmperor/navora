"""
SQLite Persistence & Concurrency Layer for Kaveri Copilot.
Replaces in-memory stores with SQLite transactions for:
1. Audit log trail
2. Idempotency tracking (processed action hashes)
3. Transfer stock reservations with TTL expiry and lifecycle release
"""

import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

from engine.config import RESERVATION_TTL_SECONDS, DEFAULT_SIMULATION_DATE

DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "copilot_storage.db"))


def get_db_connection(db_path: str = DB_FILE) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: str = DB_FILE):
    """Initializes schema for audit logs, idempotency tokens, and reservations."""
    with get_db_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id TEXT PRIMARY KEY,
                problem_id TEXT,
                action_type TEXT,
                status TEXT,
                payload_json TEXT,
                approved_by TEXT,
                execution_details_json TEXT,
                notes TEXT,
                timestamp TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_actions (
                action_hash TEXT PRIMARY KEY,
                problem_id TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reservation_key TEXT,
                incident_id TEXT,
                sku TEXT,
                location TEXT,
                qty INTEGER,
                created_at REAL,
                expires_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rejection_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                problem_id TEXT,
                sku TEXT,
                location TEXT,
                rejected_source TEXT,
                action_type TEXT,
                rejection_reason TEXT,
                created_at TEXT
            )
        """)


# Initialize DB on module load
init_db()


# ==============================================================================
# AUDIT LOG PERSISTENCE
# ==============================================================================

def log_audit_trail(
    problem_id: str,
    action_type: str,
    status: str,
    payload: Dict[str, Any],
    approved_by: str = "Ramesh Kulkarni (Head of Purchasing)",
    execution_details: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    db_path: str = DB_FILE
) -> Dict[str, Any]:
    """Persists an immutable audit log entry into SQLite."""
    audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
    ts = datetime.now().isoformat()

    entry = {
        "audit_id": audit_id,
        "problem_id": problem_id,
        "action_type": action_type,
        "status": status,
        "payload": payload,
        "approved_by": approved_by,
        "execution_details": execution_details or {},
        "notes": notes or "Automated execution via Copilot",
        "timestamp": ts
    }

    with get_db_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO audit_log (
                audit_id, problem_id, action_type, status,
                payload_json, approved_by, execution_details_json, notes, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                problem_id,
                action_type,
                status,
                json.dumps(payload),
                approved_by,
                json.dumps(execution_details or {}),
                notes,
                ts
            )
        )
    return entry


def get_all_audit_logs(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieves all historical audit trail entries ordered by timestamp descending."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("SELECT * FROM audit_log ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        results = []
        for r in rows:
            results.append({
                "audit_id": r["audit_id"],
                "problem_id": r["problem_id"],
                "action_type": r["action_type"],
                "status": r["status"],
                "payload": json.loads(r["payload_json"]) if r["payload_json"] else {},
                "approved_by": r["approved_by"],
                "execution_details": json.loads(r["execution_details_json"]) if r["execution_details_json"] else {},
                "notes": r["notes"],
                "timestamp": r["timestamp"]
            })
        return results


# ==============================================================================
# IDEMPOTENCY / PROCESSED ACTION TRACKING
# ==============================================================================

def is_action_already_processed(action_hash: str, db_path: str = DB_FILE) -> bool:
    """Checks whether an action hash has already been committed in SQLite."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT 1 FROM processed_actions WHERE action_hash = ?",
            (action_hash,)
        )
        return cursor.fetchone() is not None


def record_action_processed(action_hash: str, problem_id: str, db_path: str = DB_FILE):
    """Commits an action hash to guarantee idempotency across server restarts."""
    with get_db_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_actions (action_hash, problem_id, created_at) VALUES (?, ?, ?)",
            (action_hash, problem_id, datetime.now().isoformat())
        )


# ==============================================================================
# RESERVATIONS WITH TTL & LIFECYCLE MANAGEMENT
# ==============================================================================

def clean_expired_reservations(db_path: str = DB_FILE):
    """Removes reservations where expires_at < current unix time."""
    now = time.time()
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM reservations WHERE expires_at <= ?", (now,))


def create_stock_reservation(
    reservation_key: str,
    incident_id: str,
    sku: str,
    location: str,
    qty: int,
    ttl_seconds: int = RESERVATION_TTL_SECONDS,
    db_path: str = DB_FILE
) -> Dict[str, Any]:
    """Creates a temporary stock hold with a strict TTL."""
    clean_expired_reservations(db_path)
    now = time.time()
    expires_at = now + ttl_seconds

    with get_db_connection(db_path) as conn:
        # Overwrite existing hold for the same incident/key if refreshed
        conn.execute(
            "DELETE FROM reservations WHERE reservation_key = ? OR incident_id = ?",
            (reservation_key, incident_id)
        )
        conn.execute(
            """
            INSERT INTO reservations (
                reservation_key, incident_id, sku, location, qty, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (reservation_key, incident_id, sku, location, qty, now, expires_at)
        )

    return {
        "reservation_key": reservation_key,
        "incident_id": incident_id,
        "sku": sku,
        "location": location,
        "qty": qty,
        "expires_at": expires_at
    }


def release_stock_reservation(
    identifier: str,
    db_path: str = DB_FILE
) -> int:
    """
    Frees stock hold upon action approval, rejection, or manual dismissal.
    Identifier can match reservation_key or incident_id.
    """
    clean_expired_reservations(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM reservations WHERE reservation_key = ? OR incident_id = ?",
            (identifier, identifier)
        )
        return cursor.rowcount


def get_active_stock_reservations(db_path: str = DB_FILE) -> Dict[str, int]:
    """Returns mapping of 'location:sku' -> total_reserved_units, filtering expired holds."""
    clean_expired_reservations(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("SELECT location, sku, SUM(qty) as total_qty FROM reservations GROUP BY location, sku")
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            key = f"{r['location']}:{r['sku']}"
            result[key] = int(r["total_qty"] or 0)
        return result


def record_rejection_memory(
    problem_id: str,
    sku: Optional[str] = None,
    location: Optional[str] = None,
    rejected_source: Optional[str] = None,
    action_type: Optional[str] = None,
    rejection_reason: str = "Declined manual intervention",
    db_path: str = DB_FILE
) -> Dict[str, Any]:
    """Records an explicit human rejection reason to apply as soft constraint in future recommendations."""
    ts = datetime.now().isoformat()
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO rejection_memory (problem_id, sku, location, rejected_source, action_type, rejection_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (problem_id, sku, location, rejected_source, action_type, rejection_reason, ts)
        )
        return {
            "id": cursor.lastrowid,
            "problem_id": problem_id,
            "sku": sku,
            "location": location,
            "rejected_source": rejected_source,
            "action_type": action_type,
            "rejection_reason": rejection_reason,
            "created_at": ts
        }


def get_all_rejection_memories(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieves all past rejection records."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("SELECT * FROM rejection_memory ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]


def clear_all_persistence(db_path: str = DB_FILE):
    """Clears all tables for benchmark reset."""
    with get_db_connection(db_path) as conn:
        conn.execute("DELETE FROM audit_log")
        conn.execute("DELETE FROM processed_actions")
        conn.execute("DELETE FROM reservations")
        conn.execute("DELETE FROM rejection_memory")

