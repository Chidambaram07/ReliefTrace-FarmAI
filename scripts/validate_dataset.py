"""Validate the dataset without writing a DB. Exit 1 if any 'error' severity issue exists.
Usage: python -m scripts.validate_dataset [--json out.json]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.config import get_settings
from backend.dataset.builder import DatasetError, build_dataset
from backend.dataset.validation import build_report, format_report


def main() -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(s.csv_path))
    ap.add_argument("--images-dir", default=str(s.images_dir))
    ap.add_argument("--json", default=None, help="also write the report as JSON")
    a = ap.parse_args()
    try:
        bundle = build_dataset(a.csv, a.images_dir)
    except DatasetError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    rep = build_report(bundle)
    print(format_report(rep))
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(rep, indent=2))
    return 1 if rep["issue_severity_totals"]["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
