"""
SQLite-based persistence for ExecFlow.

This module uses Python's built-in `sqlite3` to create and manage a local
database file `execflow.db`. It exposes simple functions to initialize the
schema and perform CRUD operations on the `actions` table.

All SQL uses parameterized queries to avoid injection risks.

Functions:
- init_db(): create the database and table if needed
- insert_action(...): insert a new action row
- get_all_actions(): return all actions
- get_actions_for_owner(owner): return actions for a specific owner
- get_actions_by_status(status): return actions filtered by status
- update_action(action_id, **fields): update fields for a given action id
- delete_action(action_id): delete an action row

The table schema stores timestamps as ISO-formatted strings.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

DB_PATH = Path(__file__).parent / "execflow.db"


def _get_conn():
    """Open a sqlite3 connection with row factory returning dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the `actions` table if it does not exist.

    The schema contains the fields requested in the exercise. Timestamps
    are stored as ISO-formatted strings (UTC naive datetime).
    """
    create_sql = """
    CREATE TABLE IF NOT EXISTS actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        owner TEXT,
        related_person TEXT,
        deadline TEXT,
        status TEXT,
        source_type TEXT,
        source_date TEXT,
        evidence TEXT,
        confidence REAL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """
    with _get_conn() as conn:
        conn.execute(create_sql)
        conn.commit()

    # create audit log table
    create_audit = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        message TEXT NOT NULL
    );
    """
    with _get_conn() as conn:
        conn.execute(create_audit)
        conn.commit()


def insert_action(
    action: str,
    owner: Optional[str] = None,
    related_person: Optional[str] = None,
    deadline: Optional[str] = None,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    source_date: Optional[str] = None,
    evidence: Optional[str] = None,
    confidence: Optional[float] = None,
) -> int:
    """Insert a new action and return its new `id`.

    Uses a parameterized `INSERT` to store the provided values. `created_at`
    and `updated_at` are set to the current time (ISO format).
    """
    now = datetime.utcnow().isoformat()
    sql = (
        "INSERT INTO actions (action, owner, related_person, deadline, status, source_type, source_date, evidence, confidence, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    params = (action, owner, related_person, deadline, status, source_type, source_date, evidence, confidence, now, now)
    with _get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def add_audit_log(message: str) -> int:
    """Insert an audit log message with the current timestamp. Returns id."""
    ts = datetime.utcnow().isoformat()
    sql = "INSERT INTO audit_log (ts, message) VALUES (?, ?)"
    with _get_conn() as conn:
        cur = conn.execute(sql, (ts, message))
        conn.commit()
        return cur.lastrowid


def get_audit_logs(limit: int = 200) -> List[Dict[str, Any]]:
    """Return recent audit logs ordered newest-first."""
    sql = "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?"
    with _get_conn() as conn:
        cur = conn.execute(sql, (limit,))
        rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]


def get_all_actions() -> List[Dict[str, Any]]:
    """Return all actions as a list of dictionaries.

    Useful for listing everything in the UI or for exports.
    """
    sql = "SELECT * FROM actions ORDER BY created_at DESC"
    with _get_conn() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        return [_row_to_dict(r) for r in rows]


def get_actions_for_owner(owner: str) -> List[Dict[str, Any]]:
    """Return actions where `owner` matches the provided value.

    Uses a parameterized query. Exact match is used; callers can normalize
    casing before calling if desired.
    """
    sql = "SELECT * FROM actions WHERE owner = ? ORDER BY created_at DESC"
    with _get_conn() as conn:
        cur = conn.execute(sql, (owner,))
        return [_row_to_dict(r) for r in cur.fetchall()]


def get_actions_by_status(status: str) -> List[Dict[str, Any]]:
    """Return actions filtered by `status`.

    Parameterized query; exact match on status.
    """
    sql = "SELECT * FROM actions WHERE status = ? ORDER BY created_at DESC"
    with _get_conn() as conn:
        cur = conn.execute(sql, (status,))
        return [_row_to_dict(r) for r in cur.fetchall()]


def update_action(action_id: int, **fields) -> bool:
    """Update fields for the action with `id == action_id`.

    - `fields` are the columns to update (e.g., status='Completed').
    - The function sets `updated_at` to the current time.
    - Returns True if a row was updated, False otherwise.

    The implementation builds a parameterized `UPDATE` statement dynamically
    but only for the provided field names.
    """
    if not fields:
        return False
    allowed = {"action", "owner", "related_person", "deadline", "status", "source_type", "source_date", "evidence", "confidence"}
    set_parts = []
    params = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        set_parts.append(f"{k} = ?")
        params.append(v)
    if not set_parts:
        return False
    # always update updated_at
    params.append(datetime.utcnow().isoformat())
    set_clause = ", ".join(set_parts) + ", updated_at = ?"
    sql = f"UPDATE actions SET {set_clause} WHERE id = ?"
    params.append(action_id)
    with _get_conn() as conn:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount > 0


def delete_action(action_id: int) -> bool:
    """Delete the action with the given id.

    Returns True if a row was deleted.
    """
    sql = "DELETE FROM actions WHERE id = ?"
    with _get_conn() as conn:
        cur = conn.execute(sql, (action_id,))
        conn.commit()
        return cur.rowcount > 0


if __name__ == "__main__":
    # Quick demo: initialize DB and insert a sample row.
    init_db()
    print(f"Database initialized at: {DB_PATH}")
    sample_id = insert_action(
        action="Send updated vendor list to Raghav",
        owner="Arjun Malhotra",
        related_person="Raghav Sethi",
        deadline="2026-09-23",
        status="open",
        source_type="email",
        source_date="2026-09-22",
        evidence="will send by tomorrow (Wednesday) morning for sure",
        confidence=0.9,
    )
    print("Inserted sample action id:", sample_id)
    print("Inserted sample action id:", sample_id)
