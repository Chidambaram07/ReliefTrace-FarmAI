"""Claim-side tables. Kept separate from dataset tables so a dataset rebuild never deletes claims."""
from __future__ import annotations

import sqlite3

CLAIMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
  claim_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
  farmer_name TEXT, village_lgd TEXT, survey_no TEXT NOT NULL, subdivision TEXT,
  claimed_cause TEXT NOT NULL, claimed_crop TEXT, claimed_stage TEXT,
  incident_date TEXT NOT NULL, claimed_lat REAL, claimed_lon REAL, description TEXT
);
CREATE TABLE IF NOT EXISTS claim_images (
  image_key INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  source TEXT NOT NULL,            -- 'upload' | 'dataset'
  dataset_image_id TEXT,           -- set when source = 'dataset'
  filename TEXT, file_path TEXT, sha256 TEXT, mime TEXT,
  width INTEGER, height INTEGER, size_bytes INTEGER,
  exif_gps_lat REAL, exif_gps_lon REAL, exif_captured_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (claim_id, sha256), UNIQUE (claim_id, dataset_image_id)
);
CREATE INDEX IF NOT EXISTS ix_claim_images_claim ON claim_images(claim_id);
"""


def init_claims_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(CLAIMS_SCHEMA)
    conn.commit()

AI_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_cache (
  cache_key TEXT PRIMARY KEY, result_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS image_analyses (
  analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  image_key INTEGER NOT NULL REFERENCES claim_images(image_key) ON DELETE CASCADE,
  ok INTEGER NOT NULL, model_id TEXT, prompt_version TEXT, cached INTEGER NOT NULL DEFAULT 0,
  result_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analyses_image ON image_analyses(claim_id, image_key);
"""


def init_ai_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(AI_SCHEMA)
    conn.commit()


MODEL_HEALTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_health_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task TEXT NOT NULL, model_key TEXT NOT NULL, model_id TEXT, provider TEXT NOT NULL,
  availability TEXT NOT NULL, catalog_visible TEXT, latency_ms INTEGER,
  error_code TEXT, error_message TEXT, attempts_json TEXT, checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_model_health_key ON model_health_checks(model_key, checked_at);
"""


def init_model_health_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(MODEL_HEALTH_SCHEMA)
    conn.commit()

VERIFY_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_cache (
  cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_reports (
  report_id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, status TEXT NOT NULL, confidence REAL, human_review INTEGER NOT NULL,
  report_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reports_claim ON verification_reports(claim_id);
CREATE TABLE IF NOT EXISTS review_queue (
  claim_id TEXT PRIMARY KEY REFERENCES claims(claim_id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, reasons TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  decision TEXT, note TEXT, decided_at TEXT
);
"""


def init_verify_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(VERIFY_SCHEMA)
    conn.commit()


IMAGE_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS image_embeddings (
  image_id TEXT NOT NULL, model_id TEXT NOT NULL, dim INTEGER NOT NULL,
  vector BLOB NOT NULL, file_sha256 TEXT, created_at TEXT NOT NULL,
  PRIMARY KEY (image_id, model_id, dim)
);
"""


def init_image_index_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(IMAGE_INDEX_SCHEMA)
    conn.commit()
