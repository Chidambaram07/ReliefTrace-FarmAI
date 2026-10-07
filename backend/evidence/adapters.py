"""Local/challenge-data evidence adapters. Add a new source by writing a class with `name` and `collect(ctx)`."""
from __future__ import annotations

from datetime import date, datetime

from .base import EvidenceContext
from .models import EvidenceItem, Location, unavailable

GT = "FarmwiseAI ground-truth reference points (Task 3/4 CSV)"
ADMIN = "FarmwiseAI administrative boundaries (Tenkasi / Sivagiri GeoJSON)"


# ------------------------------------------------------------------ points
def collect_points(ctx: EvidenceContext) -> list[dict]:
    """Every location we know about, each labelled with its origin."""
    pts: list[dict] = []
    c = ctx.claim
    if c.get("claimed_lat") is not None and c.get("claimed_lon") is not None:
        pts.append({"role": "claimed", "lat": c["claimed_lat"], "lon": c["claimed_lon"], "label": "Claimant-stated location"})
    for im in ctx.images:
        k = im["image_key"]
        if k in ctx.dataset_images:
            d = ctx.dataset_images[k]["image"]
            if d.get("image_lat") is not None:
                pts.append({"role": "image_dataset", "lat": d["image_lat"], "lon": d["image_lon"], "image_key": k,
                            "label": f"Photo location (dataset image {d['image_id'][:18]}...)",
                            "gt_to_image_m": min((r["gt_to_image_m"] for r in ctx.dataset_images[k]["records"]
                                                  if r.get("gt_to_image_m") is not None), default=None)})
        elif im.get("exif_gps_lat") is not None:
            pts.append({"role": "image_exif", "lat": im["exif_gps_lat"], "lon": im["exif_gps_lon"], "image_key": k,
                        "label": f"Photo EXIF GPS ({im.get('filename')})"})
    seen = set()
    for r in ctx.parcel.get("records", []):
        if r.get("gt_lat") is not None and (r["gt_lat"], r["gt_lon"]) not in seen:
            seen.add((r["gt_lat"], r["gt_lon"]))
            pts.append({"role": "gt_point", "lat": r["gt_lat"], "lon": r["gt_lon"], "label": f"GT survey point {r['record_id']}"})
    cen = ctx.geo.centroid(ctx.village_code) if ctx.geo.available else None
    if cen:
        pts.append({"role": "village_centroid", "lat": cen[0], "lon": cen[1], "label": f"Village {ctx.village_code} representative point"})
    return pts


# ------------------------------------------------------------------ crop metadata
class CropMetadataAdapter:
    name = "crop_metadata"

    def collect(self, ctx: EvidenceContext) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        p = ctx.parcel
        status = p["status"]
        if status in ("not_found", "dataset_unavailable"):
            items.append(unavailable(GT, "crop_metadata",
                                     "Parcel not present in the reference points (reference covers sampled points only)"
                                     if status == "not_found" else "Reference dataset not loaded", kind="source_data",
                                     data={"parcel_status": status}))
        else:
            recs = p["records"]
            crops = sorted({r["crop_name"] for r in recs if r["crop_name"]})
            stages = sorted({r["crop_stage"] for r in recs if r["crop_stage"]})
            dates = sorted({r["gt_date"] for r in recs if r["gt_date"]})
            lims = ["Ground-truth points are reference data and may contain errors (per FarmwiseAI Task 3/4 notes)",
                    "Contains no disease or damage labels"]
            q = "medium"
            if len(crops) > 1 or len(stages) > 1:
                q = "low"
                lims.append("Records for this parcel disagree on crop or stage")
            if status == "ambiguous":
                q = "low"
                lims.append(f"Survey number exists in several villages: {p['villages']}; village_lgd not given")
            if status == "found_ignoring_subdivision":
                lims.append("Claimed subdivision not found; matched on survey number only")
            items.append(EvidenceItem(
                source=GT, source_kind="source_data", evidence_type="crop_metadata", timestamp=dates[0] if dates else None,
                observation=(f"{len(recs)} reference record(s) for survey {ctx.claim['survey_no']} in village(s) {p['villages']}: "
                             f"crop {crops}, stage {stages}, surveyed {dates}."),
                data={"parcel_status": status, "crops": crops, "stages": stages, "dates": dates, "villages": p["villages"],
                      "record_ids": [r["record_id"] for r in recs], "n_records": len(recs)},
                quality=q, limitations=lims, raw_reference={"record_ids": [r["record_id"] for r in recs][:20]}))
        for k, d in ctx.dataset_images.items():
            im = d["image"]
            lims = ["Crop/stage label is FarmwiseAI reference data (may contain errors)"]
            q = "medium"
            if im["flags"]:
                lims.append(f"Dataset flags: {', '.join(im['flags'])}")
                if {"STAGE_CONFLICT", "CROP_CONFLICT"} & set(im["flags"]):
                    q = "low"
            items.append(EvidenceItem(
                source=GT, source_kind="source_data", evidence_type="crop_metadata", timestamp=im["image_date"],
                observation=f"Dataset image {im['image_id'][:24]}... labelled crop '{im['crop_name']}', stage '{im['crop_stage'] or im['crop_stage_values']}'.",
                data={"scope": "image", "image_key": k, "image_id": im["image_id"], "crops": [im["crop_name"]] if im["crop_name"] else [],
                      "stages": im["crop_stage_values"], "flags": im["flags"]},
                quality=q, limitations=lims, raw_reference={"image_id": im["image_id"]}))
        return items


# ------------------------------------------------------------------ location + administrative
class LocationAdapter:
    name = "location"

    def collect(self, ctx: EvidenceContext) -> list[EvidenceItem]:
        pts = [p for p in ctx.points if p["role"] in ("claimed", "image_dataset", "image_exif")]
        if not pts:
            return [unavailable("claim/image metadata", "gps_location",
                                "No coordinates available (no claimed location, no photo GPS/EXIF, no dataset coordinates)",
                                kind="source_data")]
        if not ctx.geo.available:
            return [unavailable(ADMIN, "administrative_boundary", f"Boundary layers unavailable: {ctx.geo.error}", kind="source_data")]
        lgd = ctx.parcel.get("village_lgd") or ctx.claim.get("village_lgd")
        vcode = ctx.village_code
        poly_ok = ctx.geo.village(vcode) is not None
        tol = ctx.gt_tolerance
        items = []
        for p in pts:
            loc = ctx.geo.locate(p["lat"], p["lon"])
            dist = ctx.geo.distance_to_village_m(p["lat"], p["lon"], vcode)
            bits = [f"{'inside' if loc['in_taluk'] else 'OUTSIDE'} {ctx.geo.taluk_name} taluk",
                    f"village polygon: {loc['village_name']} (code {loc['village_code']})" if loc["village_code"] else "not inside any village polygon"]
            if dist is not None:
                bits.append(f"{dist:.0f} m from claimed village {lgd}")
            lims = ["Point-in-polygon against provided boundary layers; boundary accuracy unknown"]
            if not poly_ok:
                lims.append(f"No village polygon found for the claimed village (LGD {lgd}); only taluk-level check possible")
            if p["role"] == "image_exif":
                lims.append("EXIF GPS can be absent, imprecise or edited")
            if p["role"] == "claimed":
                lims.append("Claimant-stated coordinates are unverified")
            data = {"role": p["role"], "lat": p["lat"], "lon": p["lon"], "image_key": p.get("image_key"), **loc,
                    "claimed_village_lgd": lgd, "claimed_village_code": vcode, "village_polygon_available": poly_ok,
                    "dist_to_claimed_village_m": dist}
            if p.get("gt_to_image_m") is not None:
                data["gt_to_image_m"] = p["gt_to_image_m"]
                data["tolerance_p95_m"] = tol.get("p95")
                bits.append(f"{p['gt_to_image_m']:.0f} m from its GT survey point (dataset p95 {tol.get('p95', '?')} m)")
            items.append(EvidenceItem(
                source=ADMIN if p["role"] != "image_dataset" else f"{ADMIN}; {GT}", source_kind="source_data",
                evidence_type="administrative_boundary" if p["role"] == "claimed" else "gps_location",
                location=Location(lat=p["lat"], lon=p["lon"], label=p["label"]),
                observation=f"{p['label']}: " + "; ".join(bits) + ".", data=data,
                quality="medium" if p["role"] != "claimed" else "low", limitations=lims,
                raw_reference={"lat": p["lat"], "lon": p["lon"], "image_key": p.get("image_key")}))
        return items


# ------------------------------------------------------------------ timestamps
def _d(s: str | None) -> date | None:
    try:
        return datetime.fromisoformat(s).date() if s else None
    except ValueError:
        return None


class TimestampAdapter:
    name = "timestamp"

    def collect(self, ctx: EvidenceContext) -> list[EvidenceItem]:
        inc = date.fromisoformat(ctx.claim["incident_date"])
        items = []

        def add(role, when, src, q, note, ref, lims=()):
            d = _d(when)
            items.append(EvidenceItem(
                source=src, source_kind="source_data", evidence_type="timestamp", timestamp=when,
                observation=f"{note} {when} ({(d - inc).days:+d} day(s) relative to the reported incident {inc}).",
                data={"role": role, "when": when, "days_from_incident": (d - inc).days}, quality=q,
                limitations=list(lims), raw_reference=ref))
        for r in ctx.parcel.get("records", [])[:1]:
            if r.get("gt_date"):
                add("gt_survey", r["gt_date"], GT, "medium", "Ground-truth survey date for the parcel:", {"record_id": r["record_id"]},
                    ["Survey date only; no time of day"])
        for k, d in ctx.dataset_images.items():
            im = d["image"]
            if im.get("file_captured_at"):
                add("file_capture", im["file_captured_at"], "Image file name (Task 4 package)", "medium",
                    "Photo capture time encoded in the file name:", {"image_id": im["image_id"]},
                    ["Derived from file name, not embedded EXIF; could be renamed"])
            elif im.get("image_date"):
                add("csv_image_date", im["image_date"], GT, "medium", "Photo date recorded in the reference CSV:", {"image_id": im["image_id"]})
        for im in ctx.images:
            if im["source"] == "upload" and im.get("exif_captured_at"):
                add("exif_capture", im["exif_captured_at"], "Uploaded photo EXIF", "medium", "Photo EXIF capture time:",
                    {"image_key": im["image_key"], "sha256": (im.get("sha256") or "")[:12]}, ["EXIF can be edited or missing"])
        if not items:
            return [unavailable("claim/image metadata", "timestamp", "No photo or survey date available to compare with the incident date",
                                kind="source_data")]
        return items


# ------------------------------------------------------------------ AI image observations
class ImageryAdapter:
    name = "imagery"

    def collect(self, ctx: EvidenceContext) -> list[EvidenceItem]:
        if not ctx.images:
            return [unavailable("Amazon Nova Lite", "ai_image_observation", "No image attached to the claim", kind="ai_observation")]
        items = []
        for im in ctx.images:
            r = ctx.analyses.get(im["image_key"])
            if r is None:
                items.append(unavailable("Amazon Nova Lite", "ai_image_observation",
                                         f"Image {im['image_key']} not analysed (analysis skipped or file unavailable)",
                                         kind="ai_observation", data={"image_key": im["image_key"]}))
                continue
            if not r["ok"]:
                err = r.get("error") or {}
                items.append(unavailable("Amazon Nova Lite", "ai_image_observation",
                                         f"Image {im['image_key']} analysis failed: {err.get('code')} — {err.get('message', '')[:220]}",
                                         kind="ai_observation", data={"image_key": im["image_key"], "error_code": err.get("code")}))
                continue
            o = r["parsed"]
            vis = [f"{d['type']} ({d['severity']}, {d['confidence']})" for d in o["damage_indicators"] if d["visible"]]
            crop = o["crop"]
            q = "low" if not o["image_usable"] else ("medium" if crop["name_confidence"] in ("medium", "high") else "low")
            items.append(EvidenceItem(
                source=f"Amazon Bedrock {r.get('model_id')}", source_kind="ai_observation", evidence_type="ai_image_observation",
                observation=(f"Image {im['image_key']}: crop guess '{crop['name_guess']}' ({crop['name_confidence']}), stage "
                             f"'{crop['stage_guess']}'; visible damage: {vis or 'none reported'}; usable={o['image_usable']}."),
                data={"image_key": im["image_key"], "analysis": o, "model_id": r.get("model_id"), "prompt_version": r.get("prompt_version")},
                quality=q, limitations=["AI observation, not ground truth", *o["limitations"][:3]],
                raw_reference={"image_key": im["image_key"], "prompt_version": r.get("prompt_version")}))
        return items


# ------------------------------------------------------------------ disaster feed (placeholder)
class DisasterEventAdapter:
    """No approved disaster/warning feed is configured. Add an adapter here (e.g. IMD warnings, state declarations)."""
    name = "disaster"

    def collect(self, ctx: EvidenceContext) -> list[EvidenceItem]:
        return [unavailable("Disaster/warning feed", "disaster_event",
                            "No approved disaster-event feed is configured (e.g. IMD warnings, state disaster declarations)",
                            data={"claimed_cause": ctx.claim["claimed_cause"]})]


def default_adapters():
    from .weather import WeatherAdapter
    return [CropMetadataAdapter(), LocationAdapter(), TimestampAdapter(), WeatherAdapter(), ImageryAdapter(), DisasterEventAdapter()]
