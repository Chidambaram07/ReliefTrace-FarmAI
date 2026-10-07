"""Validation report over a built dataset bundle."""
from __future__ import annotations

from .builder import DatasetBundle

EXPECTED_LABEL_COLUMNS = ("disease", "damage", "label")


def build_report(b: DatasetBundle) -> dict:
    sev: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for i in b.issues:
        sev[i.severity] += 1
    s = b.stats
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    add("all dates parsed", not any(i.code.endswith("DATE_UNPARSED") for i in b.issues),
        "explicit formats: gt=M/D/Y|D-M-Y, image=D/M/Y H:M")
    add("GT date == image date on every record", not any(i.code == "DATE_MISMATCH" for i in b.issues), "")
    add("every record has >=1 image id", not any(i.code == "NO_IMAGE_ID" for i in b.issues), "")
    add("no unknown image-id formats", not any(i.code == "UNKNOWN_ID_FORMAT" for i in b.issues), "")
    add("image-level crop_name consistent", not any(i.code == "CROP_CONFLICT" for i in b.issues), "")
    n_stage = s["issue_counts"].get("warning:STAGE_CONFLICT", 0)
    add("image-level crop_stage consistent", n_stage == 0, f"{n_stage} images with conflicting stages (left unresolved)")
    if s["images_dir_checked"]:
        add("all images found on disk", s["images_missing"] == 0,
            f"{s['images_found']} found, {s['images_missing']} missing, {s['orphan_image_files']} orphan files")
    else:
        add("image directory available", False, "directory not found; file presence UNKNOWN (not counted as missing)")

    return {
        "stats": s,
        "issue_severity_totals": sev,
        "checks": checks,
        "notes": [
            "Source CSV has no disease/damage label column; none are derived or stored.",
            "Crop/stage values are FarmwiseAI ground-truth reference points, which may contain errors (Task 3 brief).",
        ],
    }


def format_report(rep: dict) -> str:
    s = rep["stats"]
    lines = [
        "== ReliefTrace dataset validation ==",
        f"CSV rows: {s['csv_rows']}  distinct records: {s['distinct_records']}  "
        f"(exact duplicates merged: {s['exact_duplicate_rows_merged']})",
        f"Multi-image rows: {s['multi_image_rows']}  image references: {s['image_references']}  "
        f"unique images: {s['unique_images']}",
        f"Images by id format: {s['images_by_id_format']}",
        f"Images by coordinate status: {s['images_by_coord_status']}",
        f"Files: dir checked={s['images_dir_checked']} found={s['images_found']} "
        f"missing={s['images_missing']} orphan={s['orphan_image_files']}",
        f"Issues: {rep['issue_severity_totals']}",
        "Issue codes: " + ", ".join(f"{k}={v}" for k, v in s["issue_counts"].items()),
        "",
    ]
    for c in rep["checks"]:
        lines.append(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['check']}" + (f" - {c['detail']}" if c["detail"] else ""))
    lines += [""] + [f"NOTE: {n}" for n in rep["notes"]]
    return "\n".join(lines)
