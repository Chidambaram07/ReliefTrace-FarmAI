"""Pure parsing helpers for the FarmwiseAI ground-truth CSV. No labels are invented here."""
from __future__ import annotations

import re
from datetime import date, datetime

# Image IDs come in two observed shapes:
#   1) "<hex16>-<n>-<n>"                                   (no extension)
#   2) "<uuid><6-digit village LGD>_<survey[+letter]>_<n or empty>_.jpg"  (real filename)
ID_HEX = re.compile(r"^[0-9a-f]{16}-\d+-\d+$", re.I)
ID_UUID_FILE = re.compile(
    r"^(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?P<village>\d{6})_(?P<survey>\d+[A-Za-z]*)_(?P<suffix>\d*)_\.(?P<ext>jpe?g|png)$",
    re.I,
)

# Observed in the OFFICIAL CSV: timestamp = MM-DD-YYYY (39 rows are DD-MM-YYYY, e.g. 13-11-2024);
# image_timestamp = DD-MM-YYYY HH:MM. Slash variants appear in Excel-resaved copies.
# Order matters: month-first is tried first, day-first only if month-first is impossible (e.g. 13-11-2024).
GT_DATE_FORMATS = ("%m-%d-%Y", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y")
IMG_DATE_FORMATS = ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y")

# Image FILE names in the Task-4 package. Shape A embeds the CSV id: <village>_<survey>_<n>__<hex16-n-n>-<q>_<q>_<Y_M_D_H_M_S>.jpg
FILE_A = re.compile(
    r"^(?P<village>\d{6})_(?P<survey>\d+[A-Za-z]*)_(?P<suffix>\d*)__(?P<id>[0-9a-f]{16}-\d+-\d+)-\d+_\d+_"
    r"(?P<y>\d{4})_(?P<mo>\d{2})_(?P<d>\d{2})_(?P<h>\d{2})_(?P<mi>\d{2})_(?P<s>\d{2})\.(?:jpe?g|png)$", re.I)


def clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def split_raw(value) -> list[str]:
    """Split on ';' preserving order and duplicates (needed to pair ids with coordinates)."""
    s = clean(value)
    if s is None:
        return []
    return [p.strip() for p in s.split(";") if p.strip()]


def parse_image_id(raw: str) -> dict:
    """Return canonical id + structural info. Unknown shapes are kept, flagged 'unknown'."""
    raw = raw.strip()
    m = ID_UUID_FILE.match(raw)
    if m:
        stem = raw[: raw.rfind(".")]
        return {
            "image_id": stem,
            "raw_id": raw,
            "id_format": "uuid_file",
            "filename_village_lgd": m["village"],
            "filename_survey_no": m["survey"],
        }
    if ID_HEX.match(raw):
        return {"image_id": raw, "raw_id": raw, "id_format": "hex_triplet",
                "filename_village_lgd": None, "filename_survey_no": None}
    stem = re.sub(r"\.(jpe?g|png)$", "", raw, flags=re.I)
    return {"image_id": stem, "raw_id": raw, "id_format": "unknown",
            "filename_village_lgd": None, "filename_survey_no": None}


def _parse_date(s: str | None, formats: tuple[str, ...]) -> date | None:
    s = clean(s)
    if s is None:
        return None
    for f in formats:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def parse_gt_date(s) -> date | None:
    return _parse_date(s, GT_DATE_FORMATS)


def parse_image_date(s) -> date | None:
    return _parse_date(s, IMG_DATE_FORMATS)


def to_float(s) -> float | None:
    s = clean(s)
    if s is None:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v == v else None  # reject NaN


def valid_coord(lat: float | None, lon: float | None) -> bool:
    """Plausible location in/near India; (0,0) and out-of-range values are treated as missing."""
    if lat is None or lon is None:
        return False
    if lat == 0 and lon == 0:
        return False
    return 6.0 <= lat <= 38.0 and 68.0 <= lon <= 98.0


def leading_int(s: str | None) -> str | None:
    """'399/1' -> '399' (for comparing survey numbers with filename-derived ones)."""
    if s is None:
        return None
    m = re.match(r"\s*(\d+)", s)
    return m.group(1) if m else None


def parse_image_filename(name: str) -> dict:
    """Map an image FILE name to the CSV image_id it belongs to (+ capture time when encoded)."""
    m = FILE_A.match(name)
    if m:
        try:
            cap = datetime(int(m["y"]), int(m["mo"]), int(m["d"]), int(m["h"]), int(m["mi"]), int(m["s"])).isoformat()
        except ValueError:
            cap = None
        return {"image_id": m["id"], "captured_at": cap, "village_lgd": m["village"], "survey_no": m["survey"]}
    stem = re.sub(r"\.(jpe?g|png)$", "", name, flags=re.I)
    u = ID_UUID_FILE.match(name)
    return {"image_id": stem, "captured_at": None,
            "village_lgd": u["village"] if u else None, "survey_no": u["survey"] if u else None}
