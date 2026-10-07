"""Build the image-level metadata layer from the ground-truth CSV.

Rules:
- One survey record per distinct CSV row (exact duplicates merged, source rows kept).
- One image record per unique image id (after splitting ';').
- Image coordinates are paired with ids by position ONLY when counts match; otherwise unpaired.
- Conflicts are flagged, never resolved by guessing. No disease/damage labels exist or are created.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
try:
    import pandas as pd
except ImportError:
    pd = None

from backend.utils.geo import haversine_m
from .parsing import (
    clean, leading_int, parse_gt_date, parse_image_date, parse_image_filename, parse_image_id,
    split_raw, to_float, valid_coord,
)

COLUMN_MAP = {
    "Village LG": "village_lgd",
    "district_1": "district_code",
    "taluk_co_1": "taluk_code",
    "village__1": "village_code",
    "survey_n_1": "survey_no",
    "sub_divi_1": "subdivision",
    "final_lat": "gt_lat",
    "final_long": "gt_lon",
    "timestamp": "gt_date_raw",
    "rabi_crop_classification": "crop_classification",
    "final_crop_name": "crop_name",
    "final_crop_stage": "crop_stage",
    "image_path": "image_path_raw",
    "image_timestamp": "image_date_raw",
    "image_latitude": "image_lat_raw",
    "image_longitude": "image_lon_raw",
}
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


class DatasetError(Exception):
    pass


@dataclass
class Issue:
    severity: str  # error | warning | info
    code: str
    subject: str
    detail: str = ""


@dataclass
class DatasetBundle:
    records: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    csv_sha256: str = ""


def read_csv(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise DatasetError(f"CSV not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise DatasetError(f"CSV missing expected columns: {missing}")
    return df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def index_image_dir(images_dir: Path | None) -> dict[str, list[Path]] | None:
    """Map CSV image_id -> image files (an id can have several photos). None = directory missing (unknown)."""
    if images_dir is None or not Path(images_dir).is_dir():
        return None
    idx: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(Path(images_dir).rglob("*")):
        if p.suffix.lower() in IMAGE_EXTS:
            idx[parse_image_filename(p.name)["image_id"]].append(p)
    return dict(idx)


def build_dataset(csv_path: Path, images_dir: Path | None = None) -> DatasetBundle:
    csv_path = Path(csv_path)
    df = read_csv(csv_path)
    b = DatasetBundle(csv_sha256=_sha256(csv_path))
    issues = b.issues

    # ---- Pass 1: survey records + record<->image links -------------------------------------
    seen: dict[tuple, dict] = {}
    img_acc: dict[str, dict] = {}
    n_multi_rows = 0

    for line_no, row in enumerate(df.itertuples(index=False), start=2):  # CSV line (header = 1)
        key = tuple(row)
        if key in seen:
            seen[key]["source_rows"].append(line_no)
            continue

        rid = f"R{len(b.records) + 1:05d}"
        gt_date = parse_gt_date(row.gt_date_raw)
        img_date = parse_image_date(row.image_date_raw)
        if gt_date is None:
            issues.append(Issue("error", "GT_DATE_UNPARSED", rid, f"{row.gt_date_raw!r}"))
        if img_date is None:
            issues.append(Issue("error", "IMAGE_DATE_UNPARSED", rid, f"{row.image_date_raw!r}"))
        if gt_date and img_date and gt_date != img_date:
            issues.append(Issue("warning", "DATE_MISMATCH", rid, f"gt={gt_date} image={img_date}"))

        raw_ids = split_raw(row.image_path_raw)
        lats, lons = split_raw(row.image_lat_raw), split_raw(row.image_lon_raw)
        paired = bool(raw_ids) and len(raw_ids) == len(lats) == len(lons)
        if len(raw_ids) > 1:
            n_multi_rows += 1
        if raw_ids and not paired:
            issues.append(Issue(
                "warning", "COORD_UNPAIRED", rid,
                f"{len(raw_ids)} ids vs {len(lats)} lat / {len(lons)} lon values"))
        if not raw_ids:
            issues.append(Issue("error", "NO_IMAGE_ID", rid, ""))

        gt_lat, gt_lon = to_float(row.gt_lat), to_float(row.gt_lon)
        rec = {
            "record_id": rid,
            "source_rows": [line_no],
            "village_lgd": clean(row.village_lgd),
            "district_code": clean(row.district_code),
            "taluk_code": clean(row.taluk_code),
            "village_code": clean(row.village_code),
            "survey_no": clean(row.survey_no),
            "subdivision": clean(row.subdivision),
            "gt_lat": gt_lat, "gt_lon": gt_lon,
            "gt_date": gt_date.isoformat() if gt_date else None,
            "crop_classification": clean(row.crop_classification),
            "crop_name": clean(row.crop_name),
            "crop_stage": clean(row.crop_stage),
            "image_date": img_date.isoformat() if img_date else None,
            "n_images": len(raw_ids),
            "coord_pairing": "paired" if paired else "unpaired",
        }
        seen[key] = rec
        b.records.append(rec)

        for pos, raw in enumerate(raw_ids):
            info = parse_image_id(raw)
            iid = info["image_id"]
            lat = lon = None
            pairing = "unpaired"
            if paired:
                lat, lon = to_float(lats[pos]), to_float(lons[pos])
                if valid_coord(lat, lon):
                    pairing = "paired"
                else:
                    lat = lon = None
                    pairing = "invalid"
            dist = None
            if lat is not None and gt_lat is not None and gt_lon is not None:
                dist = round(haversine_m(gt_lat, gt_lon, lat, lon), 1)
            b.links.append({
                "record_id": rid, "image_id": iid, "position": pos,
                "image_lat": lat, "image_lon": lon,
                "coord_pairing": pairing, "gt_to_image_m": dist,
            })
            a = img_acc.setdefault(iid, {
                "info": info, "records": [], "crops": set(), "stages": set(), "classes": set(),
                "dates": set(), "villages": set(), "surveys": set(), "coords": set(),
                "invalid": False, "unpaired": False,
            })
            a["records"].append(rid)
            a["crops"].add(rec["crop_name"])
            a["stages"].add(rec["crop_stage"])
            a["classes"].add(rec["crop_classification"])
            a["dates"].add(rec["image_date"])
            a["villages"].add(rec["village_lgd"])
            a["surveys"].add((rec["village_lgd"], rec["survey_no"], rec["subdivision"]))
            if pairing == "paired":
                a["coords"].add((round(lat, 5), round(lon, 5)))
            elif pairing == "invalid":
                a["invalid"] = True
            else:
                a["unpaired"] = True
            a["survey_leads"] = a.get("survey_leads", set()) | {leading_int(rec["survey_no"])}

    # ---- Pass 2: image-level records ---------------------------------------------------------
    file_index = index_image_dir(images_dir)
    for iid, a in sorted(img_acc.items()):
        info = a["info"]
        flags: list[str] = []
        crops = sorted(x for x in a["crops"] if x)
        stages = sorted(x for x in a["stages"] if x)
        classes = sorted(x for x in a["classes"] if x)
        dates = sorted(x for x in a["dates"] if x)
        villages = sorted(x for x in a["villages"] if x)

        def flag(code, severity, detail):
            flags.append(code)
            issues.append(Issue(severity, code, iid, detail))

        if info["id_format"] == "unknown":
            flag("UNKNOWN_ID_FORMAT", "warning", info["raw_id"])
        if len(crops) > 1:
            flag("CROP_CONFLICT", "warning", ",".join(crops))
        if len(stages) > 1:
            flag("STAGE_CONFLICT", "warning", ",".join(stages))
        if len(classes) > 1:
            flag("CLASSIFICATION_CONFLICT", "info", " | ".join(classes))
        if len(dates) > 1:
            flag("IMAGE_DATE_CONFLICT", "warning", ",".join(dates))
        if len(villages) > 1:
            flag("VILLAGE_CONFLICT", "warning", ",".join(villages))
        fv, fs = info["filename_village_lgd"], info["filename_survey_no"]
        if fv and fv not in villages:
            flag("FILENAME_VILLAGE_MISMATCH", "warning", f"filename={fv} csv={villages}")
        if fs and leading_int(fs) not in a["survey_leads"]:
            flag("FILENAME_SURVEY_MISMATCH", "info", f"filename={fs} csv={sorted(x for x in a['survey_leads'] if x)}")

        coords = sorted(a["coords"])
        lat = lon = None
        if len(coords) == 1:
            coord_status, (lat, lon) = "ok", coords[0]
        elif len(coords) > 1:
            coord_status = "conflict"
            flag("COORD_CONFLICT", "warning", f"{len(coords)} distinct coordinates")
        elif a["invalid"]:
            coord_status = "invalid"
            flag("INVALID_COORD", "warning", "zero/out-of-range image coordinate")
        else:
            coord_status = "unpaired"
            flag("COORD_UNAVAILABLE", "warning", "no id/coordinate pairing possible")

        file_path, file_status, n_files, file_cap = None, "unchecked", 0, None
        if file_index is not None:
            files = file_index.get(iid, [])
            n_files = len(files)
            if files:
                file_path, file_status = str(files[0]), "found"
                finfo = parse_image_filename(files[0].name)
                file_cap = finfo["captured_at"]
                if n_files > 1:
                    flag("MULTIPLE_FILES", "info", f"{n_files} photo files share this image id")
                if finfo["village_lgd"] and finfo["village_lgd"] not in villages:
                    flag("FILE_VILLAGE_MISMATCH", "warning", f"file={finfo['village_lgd']} csv={villages}")
                if file_cap and dates and file_cap[:10] != dates[0]:
                    flag("FILE_DATE_MISMATCH", "warning", f"file={file_cap[:10]} csv={dates}")
            else:
                file_status = "missing"

        b.images.append({
            "image_id": iid, "raw_id": info["raw_id"], "id_format": info["id_format"],
            "filename_village_lgd": fv, "filename_survey_no": fs,
            "crop_name": crops[0] if len(crops) == 1 else None,
            "crop_stage": stages[0] if len(stages) == 1 else None,
            "crop_stage_values": stages,
            "classification_values": classes,
            "image_date": dates[0] if len(dates) == 1 else None,
            "image_lat": lat, "image_lon": lon,
            "coord_status": coord_status, "coords": [list(c) for c in coords],
            "village_lgd": villages[0] if len(villages) == 1 else None,
            "n_records": len(set(a["records"])), "n_parcels": len(a["surveys"]),
            "flags": flags, "file_path": file_path, "file_status": file_status,
            "n_files": n_files, "file_captured_at": file_cap,
        })

    # ---- Orphan files (in directory but not in CSV) ------------------------------------------
    orphans: list[str] = []
    if file_index is not None:
        known = {i["image_id"] for i in b.images}
        orphans = sorted(s for s in file_index if s not in known)
        for s in orphans:
            issues.append(Issue("warning", "ORPHAN_IMAGE_FILE", s, str(file_index[s][0])))

    fs_ = [i["file_status"] for i in b.images]
    b.stats = {
        "csv_rows": len(df),
        "distinct_records": len(b.records),
        "exact_duplicate_rows_merged": len(df) - len(b.records),
        "multi_image_rows": n_multi_rows,
        "image_references": len(b.links),
        "unique_images": len(b.images),
        "images_by_id_format": _count(i["id_format"] for i in b.images),
        "images_by_coord_status": _count(i["coord_status"] for i in b.images),
        "images_dir_checked": file_index is not None,
        "images_found": fs_.count("found"),
        "images_missing": fs_.count("missing"),
        "orphan_image_files": len(orphans),
        "issue_counts": _count(f"{i.severity}:{i.code}" for i in issues),
    }
    return b


def _count(it) -> dict:
    d: dict = defaultdict(int)
    for x in it:
        d[x] += 1
    return dict(sorted(d.items()))


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
