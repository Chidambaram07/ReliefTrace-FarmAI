"""Build the SQLite dataset layer.  Usage: python -m scripts.build_dataset [--csv ..] [--images-dir ..] [--db ..]"""
from __future__ import annotations

import argparse
import json
import sys

from backend.config import get_settings
from backend.dataset import db
from backend.dataset.builder import DatasetError, build_dataset
from backend.dataset.validation import build_report, format_report


def main() -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(s.csv_path))
    ap.add_argument("--images-dir", default=str(s.images_dir))
    ap.add_argument("--db", default=str(s.db_path))
    a = ap.parse_args()
    try:
        bundle = build_dataset(a.csv, a.images_dir)
    except DatasetError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    conn = db.connect(a.db)
    db.load_bundle(conn, bundle, csv_path=a.csv)
    conn.close()
    print(format_report(build_report(bundle)))
    print(f"\nDB written: {a.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
