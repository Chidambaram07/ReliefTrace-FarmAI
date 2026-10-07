"""Central settings, read from environment variables (never hardcode secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader (no dependency). Real environment variables always win."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _path(env: str, default: str) -> Path:
    p = Path(os.environ.get(env, default))
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Settings:
    csv_path: Path
    images_dir: Path
    db_path: Path
    upload_dir: Path
    max_upload_bytes: int = 5 * 1024 * 1024
    geo_dir: Path | None = None  # Task-3 administrative boundaries (geojson); None -> data/geo
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:5175")
    storage_backend: str = "local"  # 'local' | 'aws' | 's3'
    s3_bucket: str = "fai-tce-team56-images"
    s3_dataset_prefix: str = "dataset/"
    dynamodb_table: str = "fai-tce-team56-claims"
    aws_region: str = "ap-south-1"


def get_settings() -> Settings:
    load_dotenv()
    origins = os.environ.get("RT_CORS_ORIGINS", "http://localhost:5173,http://localhost:5175")
    storage_backend = (os.environ.get("STORAGE_BACKEND") or os.environ.get("RT_STORAGE_BACKEND") or "local").strip().lower()
    s3_bucket = (os.environ.get("S3_BUCKET") or os.environ.get("RT_S3_BUCKET") or "fai-tce-team56-images").strip()
    s3_dataset_prefix = (os.environ.get("RT_S3_DATASET_PREFIX") or "dataset/").strip()
    dynamodb_table = (os.environ.get("DYNAMODB_TABLE") or os.environ.get("RT_DYNAMODB_TABLE") or "fai-tce-team56-claims").strip()
    aws_region = (os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULTREGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-south-1").strip()
    
    db_env = os.environ.get("RT_DB_PATH")
    if db_env:
        db_path = _path("RT_DB_PATH", db_env)
    elif (storage_backend in ("aws", "dynamodb") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")) and not (ROOT / "data/processed/reliefTrace.db").exists():
        db_path = Path("/tmp/reliefTrace.db")
    else:
        db_path = _path("RT_DB_PATH", "data/processed/reliefTrace.db")

    return Settings(
        csv_path=_path("RT_CSV_PATH", "data/raw/Ground_truth_Points.csv"),
        images_dir=_path("RT_IMAGES_DIR", "data/images"),
        db_path=db_path,
        upload_dir=_path("RT_UPLOAD_DIR", "data/uploads"),
        geo_dir=_path("RT_GEO_DIR", "data/geo"),
        max_upload_bytes=int(float(os.environ.get("RT_MAX_UPLOAD_MB", "5")) * 1024 * 1024),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        storage_backend=storage_backend,
        s3_bucket=s3_bucket,
        s3_dataset_prefix=s3_dataset_prefix,
        dynamodb_table=dynamodb_table,
        aws_region=aws_region,
    )
