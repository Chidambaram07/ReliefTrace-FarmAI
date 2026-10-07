from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

CLAIM_COLS = ("farmer_name", "village_lgd", "survey_no", "subdivision", "claimed_cause", "claimed_crop",
              "claimed_stage", "incident_date", "claimed_lat", "claimed_lon", "description")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_claim(conn: Any, data: dict) -> dict:
    if hasattr(conn, "claims"):
        return conn.claims.create_claim(data)
    cid = "CLM-" + uuid.uuid4().hex[:8].upper()
    vals = [data.get(c) for c in CLAIM_COLS]
    conn.execute(
        f"INSERT INTO claims (claim_id, created_at, status, {','.join(CLAIM_COLS)}) "
        f"VALUES (?,?,?,{','.join('?' * len(CLAIM_COLS))})", [cid, _now(), "submitted", *vals])
    conn.commit()
    return get_claim(conn, cid)


def get_claim(conn: Any, claim_id: str) -> dict | None:
    if hasattr(conn, "claims"):
        return conn.claims.get_claim(claim_id)
    r = conn.execute("SELECT * FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
    return dict(r) if r else None


def list_claims(conn: Any, limit: int, offset: int) -> tuple[int, list[dict]]:
    if hasattr(conn, "claims"):
        return conn.claims.list_claims(limit, offset)
    total = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    rows = conn.execute("SELECT * FROM claims ORDER BY created_at DESC, claim_id LIMIT ? OFFSET ?",
                        (limit, offset)).fetchall()
    return total, [dict(r) for r in rows]


def add_claim_image(conn: Any, claim_id: str, rec: dict) -> int:
    if hasattr(conn, "claims"):
        return conn.claims.add_claim_image(claim_id, rec)
    cur = conn.execute(
        """INSERT INTO claim_images (claim_id, source, dataset_image_id, filename, file_path, sha256, mime,
             width, height, size_bytes, exif_gps_lat, exif_gps_lon, exif_captured_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (claim_id, rec["source"], rec.get("dataset_image_id"), rec.get("filename"), rec.get("file_path"),
         rec.get("sha256"), rec.get("mime"), rec.get("width"), rec.get("height"), rec.get("size_bytes"),
         rec.get("exif_gps_lat"), rec.get("exif_gps_lon"), rec.get("exif_captured_at"), _now()))
    conn.commit()
    return cur.lastrowid


def list_claim_images(conn: Any, claim_id: str) -> list[dict]:
    if hasattr(conn, "claims"):
        return conn.claims.list_claim_images(claim_id)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM claim_images WHERE claim_id=? ORDER BY image_key", (claim_id,)).fetchall()]


def get_claim_image(conn: Any, claim_id: str, image_key: int) -> dict | None:
    if hasattr(conn, "claims"):
        return conn.claims.get_claim_image(claim_id, image_key)
    r = conn.execute("SELECT * FROM claim_images WHERE claim_id=? AND image_key=?", (claim_id, image_key)).fetchone()
    return dict(r) if r else None
