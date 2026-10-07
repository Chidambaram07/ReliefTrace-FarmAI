from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SqliteAICache:
    def __init__(self, conn: Any):
        self.conn = conn

    def get(self, key: str):
        if hasattr(self.conn, "ai_cache"):
            return self.conn.ai_cache.get(key)
        r = self.conn.execute("SELECT result_json FROM ai_cache WHERE cache_key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else None

    def put(self, key: str, value: dict) -> None:
        if hasattr(self.conn, "ai_cache"):
            self.conn.ai_cache.put(key, value)
            return
        self.conn.execute("INSERT OR REPLACE INTO ai_cache VALUES (?,?,?)", (key, json.dumps(value), _now()))
        self.conn.commit()


def get_ai_cache(conn: Any):
    if hasattr(conn, "ai_cache"):
        return conn.ai_cache
    return SqliteAICache(conn)


def add_analysis(conn: Any, claim_id: str, image_key: int, result: dict) -> int:
    if hasattr(conn, "ai"):
        return conn.ai.add_analysis(claim_id, image_key, result)
    cur = conn.execute(
        "INSERT INTO image_analyses (claim_id, image_key, ok, model_id, prompt_version, cached, result_json, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (claim_id, image_key, int(result["ok"]), result.get("model_id"), result.get("prompt_version"),
         int(result.get("cached", False)), json.dumps(result), _now()))
    conn.commit()
    return cur.lastrowid


def latest_analysis(conn: Any, claim_id: str, image_key: int):
    if hasattr(conn, "ai"):
        return conn.ai.latest_analysis(claim_id, image_key)
    r = conn.execute(
        "SELECT * FROM image_analyses WHERE claim_id=? AND image_key=? ORDER BY analysis_id DESC LIMIT 1",
        (claim_id, image_key)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["result"] = json.loads(d.pop("result_json"))
    return d
