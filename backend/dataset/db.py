"""SQLite persistence (plain SQL, portable to PostgreSQL)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .builder import DatasetBundle, to_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS survey_records (
  record_id TEXT PRIMARY KEY, source_rows TEXT, village_lgd TEXT, district_code TEXT,
  taluk_code TEXT, village_code TEXT, survey_no TEXT, subdivision TEXT,
  gt_lat REAL, gt_lon REAL, gt_date TEXT, crop_classification TEXT,
  crop_name TEXT, crop_stage TEXT, image_date TEXT, n_images INTEGER, coord_pairing TEXT
);
CREATE TABLE IF NOT EXISTS images (
  image_id TEXT PRIMARY KEY, raw_id TEXT, id_format TEXT,
  filename_village_lgd TEXT, filename_survey_no TEXT,
  crop_name TEXT, crop_stage TEXT, crop_stage_values TEXT, classification_values TEXT,
  image_date TEXT, image_lat REAL, image_lon REAL, coord_status TEXT, coords TEXT,
  village_lgd TEXT, n_records INTEGER, n_parcels INTEGER, flags TEXT,
  file_path TEXT, file_status TEXT, n_files INTEGER, file_captured_at TEXT
);
CREATE TABLE IF NOT EXISTS image_record_links (
  record_id TEXT NOT NULL, image_id TEXT NOT NULL, position INTEGER,
  image_lat REAL, image_lon REAL, coord_pairing TEXT, gt_to_image_m REAL,
  PRIMARY KEY (record_id, image_id, position)
);
CREATE TABLE IF NOT EXISTS dataset_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT, severity TEXT, code TEXT, subject TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_links_image ON image_record_links(image_id);
CREATE INDEX IF NOT EXISTS ix_records_survey ON survey_records(village_lgd, survey_no);
CREATE INDEX IF NOT EXISTS ix_issues_code ON dataset_issues(code);
"""

_TABLES = ("dataset_meta", "survey_records", "images", "image_record_links", "dataset_issues")


def connect(db_path: Path | str) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        try:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    try:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
    except sqlite3.OperationalError:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        except sqlite3.OperationalError:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except sqlite3.OperationalError:
        pass
    return conn



def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def load_bundle(conn: sqlite3.Connection, b: DatasetBundle, csv_path: str = "") -> None:
    """Replace dataset tables with the bundle contents (idempotent rebuild)."""
    for t in _TABLES:  # drop + recreate so schema changes between versions never break a rebuild
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    init_schema(conn)
    conn.executemany(
        "INSERT INTO survey_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(r["record_id"], to_json(r["source_rows"]), r["village_lgd"], r["district_code"],
          r["taluk_code"], r["village_code"], r["survey_no"], r["subdivision"], r["gt_lat"],
          r["gt_lon"], r["gt_date"], r["crop_classification"], r["crop_name"], r["crop_stage"],
          r["image_date"], r["n_images"], r["coord_pairing"]) for r in b.records])
    conn.executemany(
        "INSERT INTO images VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(i["image_id"], i["raw_id"], i["id_format"], i["filename_village_lgd"],
          i["filename_survey_no"], i["crop_name"], i["crop_stage"], to_json(i["crop_stage_values"]),
          to_json(i["classification_values"]), i["image_date"], i["image_lat"], i["image_lon"],
          i["coord_status"], to_json(i["coords"]), i["village_lgd"], i["n_records"],
          i["n_parcels"], to_json(i["flags"]), i["file_path"], i["file_status"], i["n_files"],
          i["file_captured_at"]) for i in b.images])
    conn.executemany(
        "INSERT INTO image_record_links VALUES (?,?,?,?,?,?,?)",
        [(l["record_id"], l["image_id"], l["position"], l["image_lat"], l["image_lon"],
          l["coord_pairing"], l["gt_to_image_m"]) for l in b.links])
    conn.executemany(
        "INSERT INTO dataset_issues (severity, code, subject, detail) VALUES (?,?,?,?)",
        [(i.severity, i.code, i.subject, i.detail) for i in b.issues])
    meta = {"csv_path": csv_path, "csv_sha256": b.csv_sha256,
            "built_at": datetime.now(timezone.utc).isoformat(), "stats": to_json(b.stats),
            "label_note": "Source CSV has NO disease/damage label. None are stored."}
    conn.executemany("INSERT INTO dataset_meta VALUES (?,?)", meta.items())
    conn.commit()
