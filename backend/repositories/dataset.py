from __future__ import annotations

import json
import os
import sqlite3

from typing import Any

from backend.errors import AppError


import logging
from pathlib import Path

log = logging.getLogger("reliefTrace.dataset_repo")


def ensure_dataset_db(settings: Any) -> Path | None:
    if settings is None:
        return None
    db_p = getattr(settings, "db_path", None)
    if not db_p:
        return None
    p = Path(db_p)
    if p.exists() and p.is_file() and p.stat().st_size > 0:
        return p

    # In AWS / Lambda mode, try downloading from S3
    storage_backend = getattr(settings, "storage_backend", "local").strip().lower()
    is_aws = storage_backend in ("aws", "dynamodb", "s3") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not is_aws:
        return None

    bucket = getattr(settings, "s3_bucket", "fai-tce-team56-images")
    region = getattr(settings, "aws_region", "ap-south-1")
    prefix = getattr(settings, "s3_dataset_prefix", "dataset/")
    key = f"{prefix.strip('/')}/metadata/reliefTrace.db"
    alt_key = f"{prefix.strip('/')}/reliefTrace.db"

    try:
        import boto3
        s3 = boto3.client("s3", region_name=region)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp_target = p.with_suffix(".tmp_download")
        try:
            s3.download_file(bucket, key, str(tmp_target))
        except Exception:
            s3.download_file(bucket, alt_key, str(tmp_target))
        if tmp_target.exists() and tmp_target.stat().st_size > 0:
            tmp_target.replace(p)
            log.info("Downloaded dataset DB from s3://%s to %s (size=%d)", bucket, p, p.stat().st_size)
            return p
    except Exception as e:
        log.warning("Could not download dataset DB from S3 bucket=%s key=%s: %s", bucket, key, e)
    return p if (p.exists() and p.stat().st_size > 0) else None


def _resolve_conn(conn: Any):
    if hasattr(conn, "is_dynamo") or hasattr(conn, "settings"):
        from backend.dataset import db
        settings = getattr(conn, "settings", None)
        db_p = getattr(settings, "db_path", None)
        if not (db_p and os.path.exists(db_p)):
            ensure_dataset_db(settings)
        if db_p and os.path.exists(db_p):
            return db.connect(db_p)
        return None
    return conn


def _has_table(conn, name: str) -> bool:
    c = _resolve_conn(conn)
    if c is None:
        return False
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def dataset_loaded(conn: Any) -> bool:
    c = _resolve_conn(conn)
    if c is None:
        return False
    return _has_table(c, "images") and c.execute("SELECT 1 FROM images LIMIT 1").fetchone() is not None


def require_dataset(conn: Any) -> None:
    if not dataset_loaded(conn):
        raise AppError(503, "DATASET_NOT_LOADED",
                       "Dataset not built. Run: python -m scripts.build_dataset")


def _clean_filename(path_str: str | None) -> str | None:
    if not path_str:
        return None
    clean = path_str.replace("\\", "/").rstrip("/")
    name = clean.split("/")[-1] if clean else None
    return name or None


def _image_row(r: sqlite3.Row, settings: Any = None) -> dict:
    d = dict(r)
    for k in ("crop_stage_values", "classification_values", "flags", "coords"):
        d[k] = json.loads(d[k]) if d.get(k) else []
    
    raw_path = d.get("file_path")
    filename = _clean_filename(raw_path)
    
    storage_backend = getattr(settings, "storage_backend", "local").strip().lower() if settings else "local"
    is_aws = storage_backend in ("aws", "dynamodb", "s3") or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    if is_aws and filename:
        bucket = getattr(settings, "s3_bucket", "fai-tce-team56-images") if settings else "fai-tce-team56-images"
        prefix = getattr(settings, "s3_dataset_prefix", "dataset/") if settings else "dataset/"
        clean_prefix = prefix.strip("/")
        s3_uri = f"s3://{bucket}/{clean_prefix}/images/{filename}"
        d["file_path"] = s3_uri
        d["file_available"] = (d.get("file_status") == "found")
    else:
        local_exists = bool(raw_path) and os.path.exists(raw_path)
        if not local_exists and filename:
            from backend.config import ROOT
            alt_local = ROOT / "data" / "images" / filename
            if os.path.exists(alt_local):
                d["file_path"] = str(alt_local)
                d["file_available"] = True
            else:
                bucket = getattr(settings, "s3_bucket", "fai-tce-team56-images") if settings else "fai-tce-team56-images"
                prefix = getattr(settings, "s3_dataset_prefix", "dataset/") if settings else "dataset/"
                clean_prefix = prefix.strip("/")
                s3_uri = f"s3://{bucket}/{clean_prefix}/images/{filename}"
                d["file_path"] = s3_uri
                d["file_available"] = (d.get("file_status") == "found")
        else:
            d["file_available"] = local_exists
    return d


def get_image(conn, image_id: str) -> dict | None:
    c = _resolve_conn(conn)
    if c is None:
        return None
    r = c.execute("SELECT * FROM images WHERE image_id=?", (image_id,)).fetchone()
    settings = getattr(conn, "settings", None)
    return _image_row(r, settings=settings) if r else None


def linked_records(conn, image_id: str) -> list[dict]:
    conn = _resolve_conn(conn)
    if conn is None:
        return []
    rows = conn.execute(
        """SELECT s.record_id, s.village_lgd, s.village_code, s.survey_no, s.subdivision, s.gt_lat, s.gt_lon, s.gt_date,
                  s.crop_classification, s.crop_name, s.crop_stage, MIN(l.gt_to_image_m) AS gt_to_image_m
           FROM image_record_links l JOIN survey_records s USING (record_id)
           WHERE l.image_id=? GROUP BY s.record_id ORDER BY s.record_id""", (image_id,)).fetchall()
    return [dict(r) for r in rows]


def list_images(conn, *, village_lgd=None, crop_name=None, crop_stage=None, file_status=None,
                flag=None, limit=50, offset=0) -> tuple[int, list[dict]]:
    c = _resolve_conn(conn)
    if c is None:
        return 0, []
    where, args = [], []
    for col, val in (("village_lgd", village_lgd), ("crop_name", crop_name),
                     ("crop_stage", crop_stage), ("file_status", file_status)):
        if val:
            where.append(f"{col}=?")
            args.append(val)
    if flag:
        where.append("flags LIKE ?")
        args.append(f'%"{flag}"%')
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = c.execute(f"SELECT COUNT(*) FROM images {w}", args).fetchone()[0]
    rows = c.execute(f"SELECT * FROM images {w} ORDER BY image_id LIMIT ? OFFSET ?",
                        [*args, limit, offset]).fetchall()
    settings = getattr(conn, "settings", None)
    return total, [_image_row(r, settings=settings) for r in rows]


def find_parcels(conn, *, village_lgd=None, survey_no=None, subdivision=None, limit=200) -> tuple[int, list[dict]]:
    conn = _resolve_conn(conn)
    if conn is None:
        return 0, []
    where, args = [], []
    for col, val in (("village_lgd", village_lgd), ("survey_no", survey_no), ("subdivision", subdivision)):
        if val:
            where.append(f"{col}=?")
            args.append(val)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM survey_records {w}", args).fetchone()[0]
    rows = conn.execute(
        f"""SELECT record_id, village_lgd, village_code, survey_no, subdivision, gt_lat, gt_lon, gt_date,
                   crop_classification, crop_name, crop_stage, NULL AS gt_to_image_m
            FROM survey_records {w} ORDER BY record_id LIMIT ?""", [*args, limit]).fetchall()
    return total, [dict(r) for r in rows]


def summary(conn) -> dict:
    conn = _resolve_conn(conn)
    if conn is None:
        return {"records": 0, "images": 0, "images_with_file": 0, "images_by_coord_status": {}, "flagged_images": {}}
    q = lambda sql: conn.execute(sql).fetchone()[0]
    coord = {r[0]: r[1] for r in conn.execute("SELECT coord_status, COUNT(*) FROM images GROUP BY 1")}
    flagged = {r[0]: r[1] for r in conn.execute(
        "SELECT code, COUNT(*) FROM dataset_issues WHERE severity != 'info' GROUP BY code ORDER BY code")}
    return {
        "records": q("SELECT COUNT(*) FROM survey_records"),
        "images": q("SELECT COUNT(*) FROM images"),
        "images_with_file": q("SELECT COUNT(*) FROM images WHERE file_status='found'"),
        "images_by_coord_status": coord,
        "flagged_images": flagged,
    }


def gt_image_distance_percentiles(conn) -> dict:
    """How far a photo's location typically is from its GT survey point in THIS dataset (calibrates the GPS check)."""
    conn = _resolve_conn(conn)
    if conn is None:
        return {}
    vals = sorted(r[0] for r in conn.execute("SELECT gt_to_image_m FROM image_record_links WHERE gt_to_image_m IS NOT NULL"))
    if not vals:
        return {}
    q = lambda p: round(vals[min(len(vals) - 1, int(p * len(vals)))], 1)
    return {"n": len(vals), "p50": q(0.5), "p90": q(0.9), "p95": q(0.95)}


def village_code_map(conn) -> dict:
    """CSV Village LG -> village code (the join key to the boundary layer)."""
    if not dataset_loaded(conn):
        return {}
    conn = _resolve_conn(conn)
    if conn is None:
        return {}
    return {r[0]: r[1] for r in conn.execute("SELECT DISTINCT village_lgd, village_code FROM survey_records WHERE village_code IS NOT NULL")}
