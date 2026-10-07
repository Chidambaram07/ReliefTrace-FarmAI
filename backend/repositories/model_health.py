from __future__ import annotations

import json
import sqlite3

from backend.services.model_health import HealthResult


def record(conn: sqlite3.Connection, r: HealthResult) -> int:
    cur = conn.execute(
        "INSERT INTO model_health_checks (task, model_key, model_id, provider, availability, catalog_visible, "
        "latency_ms, error_code, error_message, attempts_json, checked_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (r.task, r.model_key, r.model_id, r.provider, r.availability.value,
         None if r.catalog_visible is None else str(r.catalog_visible), r.latency_ms, r.error_code,
         r.error_message, json.dumps(r.attempts), r.checked_at))
    conn.commit()
    return cur.lastrowid


def record_all(conn: sqlite3.Connection, results: list[HealthResult]) -> list[int]:
    return [record(conn, r) for r in results]


def latest(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM model_health_checks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def latest_per_model(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM model_health_checks m WHERE id = (
             SELECT MAX(id) FROM model_health_checks WHERE model_key = m.model_key
           ) ORDER BY model_key""").fetchall()
    return [dict(r) for r in rows]
