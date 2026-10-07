"""Real, independently-callable evidence tools (Phase 5 of the Task-1 agentic build-out).

Each tool takes structured input, does real work (a live/cached weather call, geometric distance
checks against the boundary layers, a lookup against the challenge ground-truth), and returns a
ToolResult with a structured JSON output - the shape the brief asks for - plus a trace entry in
SharedState. None of these duplicate an existing call path: weather_tool reuses the exact
cache/network/fallback function the working evidence adapter uses
(backend.evidence.weather.fetch_weather_payload, factored out for this reason), and
geo_validation_tool/crop_stage_tool reuse the same boundary layer and crop-name normalization the
verification engine already relies on. This module does not replace those adapters - the MVP
verification pipeline is untouched - it exposes the same underlying capabilities as tools the
planner/router (Phase 3-4) can call independently of a full verification run.
"""
from __future__ import annotations

import hashlib
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np

from backend.agentic import image_index
from backend.agentic.state import ModelOutput, SharedState, ToolResult
from backend.repositories import dataset as ds
from backend.services.model_client import BedrockError
from backend.evidence.weather import (
    ARCHIVE_LAG_DAYS, BASELINE_YEARS, SOURCE as WEATHER_SOURCE, WINDOW_DAYS, analyse, build_url,
    fetch_weather_payload, parse_daily,
)
from backend.utils.geo import haversine_m
from backend.verification.rules import THRESHOLDS as T, normalize_crop

GEO_SOURCE = "ReliefTrace geo validation (claim vs photo vs survey vs boundary layer)"
CROP_SOURCE = "FarmwiseAI ground-truth reference points (Task 3/4 CSV)"


def _drought_indicator(rainfall_percentile: Optional[float]) -> str:
    """Reuses the SAME thresholds the deterministic verification engine uses for its drought check
    (backend/verification/rules.py), so the tool's indicator and the engine's verdict can never
    silently disagree about what counts as 'dry'."""
    if rainfall_percentile is None:
        return "unknown"
    if rainfall_percentile <= T["drought_dry_pctl_max"]:
        return "dry"
    if rainfall_percentile >= T["drought_wet_pctl_min"]:
        return "wet"
    return "normal"


def weather_tool(state: SharedState, *, lat: float, lon: float, incident_date: str | date, http, open_conn,
                 simulate_failure: bool = False) -> ToolResult:
    """{"source", "location", "date", "rainfall_mm_30d", "temperature_max_mean_c", "humidity",
    "drought_indicator", "data_quality", ...} - "humidity" is honestly null: relative humidity is
    not among the daily variables this tool currently requests from Open-Meteo, so it is left
    unset rather than guessed."""
    incident = incident_date if isinstance(incident_date, date) else date.fromisoformat(incident_date)
    inp = {"lat": lat, "lon": lon, "date": incident.isoformat()}
    t0 = time.perf_counter()

    def fail(msg: str, latency: Optional[int] = None) -> ToolResult:
        tr = ToolResult(tool="weather", input_summary=inp, output=None, status="failed", error=msg,
                        latency_ms=latency, source_type="public_dataset", source_name=WEATHER_SOURCE)
        state.record_tool_result(tr)
        return tr

    if incident > datetime.now(timezone.utc).date() - timedelta(days=ARCHIVE_LAG_DAYS):
        return fail("incident is too recent for the historical archive (~5 day publication lag)")

    end = incident + timedelta(days=1)
    start = date(incident.year - BASELINE_YEARS, end.month, min(end.day, 28)) - timedelta(days=WINDOW_DAYS)
    url = build_url(lat, lon, start, end)
    payload, served, err = fetch_weather_payload(url, http, open_conn, simulate_failure)
    latency = int((time.perf_counter() - t0) * 1000)
    if payload is None:
        return fail(f"weather source unavailable and no cached copy ({err})", latency)
    try:
        res = analyse(parse_daily(payload), incident)
    except Exception as e:  # noqa: BLE001
        return fail(f"weather response could not be parsed ({e})", latency)
    if res is None:
        return fail("weather series too incomplete for this 30-day window", latency)

    o, pct = res["observed"], res["percentile"]
    output = {
        "source": WEATHER_SOURCE, "location": {"lat": lat, "lon": lon}, "date": incident.isoformat(),
        "window": {"start": res["window_start"], "end": res["window_end"]},
        "rainfall_mm_30d": o["sum_mm"], "dry_days": o["dry_days"], "max_3day_rainfall_mm": o["max_3d_mm"],
        "temperature_max_mean_c": o["tmax_mean_c"], "max_gust_kmh": o["max_gust_kmh"],
        "humidity": None, "humidity_note": "not queried from this endpoint in the current tool version",
        "baseline_years": res["baseline_years"], "percentile_vs_10yr_baseline": pct,
        "drought_indicator": _drought_indicator(pct.get("sum_mm")),
        "data_quality": "medium" if served != "fallback_cache" else
                        "medium (live fetch failed; served from a previously cached copy)",
        "served_from": served,
    }
    tr = ToolResult(tool="weather", input_summary=inp, output=output, status="success", latency_ms=latency,
                    source_type="public_dataset", source_name=WEATHER_SOURCE)
    state.record_tool_result(tr)
    return tr


def geo_validation_tool(state: SharedState, *, points: list[dict], geo, village_code: Optional[str]) -> ToolResult:
    """Cross-checks every known location for the claim (claimant-stated, photo GPS/EXIF, dataset
    photo coordinates, survey/village boundary) against each other and against the claimed village
    polygon. `points` uses the same {"role", "lat", "lon", "label"} shape produced by
    backend.evidence.adapters.collect_points() - reused, not reinvented."""
    t0 = time.perf_counter()
    inp = {"n_points": len(points), "claimed_village_code": village_code}
    if not points:
        tr = ToolResult(tool="geo_validation", input_summary=inp, output=None, status="failed",
                        error="no coordinates available to validate", source_type="derived", source_name=GEO_SOURCE)
        state.record_tool_result(tr)
        return tr

    rows = []
    for p in points:
        if geo.available:
            loc = geo.locate(p["lat"], p["lon"])
            dist = geo.distance_to_village_m(p["lat"], p["lon"], village_code)
        else:
            loc, dist = {"in_taluk": None, "in_district": None, "village_code": None, "village_name": None}, None
        rows.append({"role": p["role"], "label": p.get("label"), "lat": p["lat"], "lon": p["lon"],
                    "in_taluk": loc.get("in_taluk"), "village_code_found": loc.get("village_code"),
                    "village_name_found": loc.get("village_name"), "distance_to_claimed_village_m": dist})

    coords = [(r["lat"], r["lon"]) for r in rows]
    max_pair_m = max((haversine_m(*a, *b) for i, a in enumerate(coords) for b in coords[i + 1:]), default=0.0)
    outside_taluk = [r for r in rows if r["in_taluk"] is False]
    consistent = not outside_taluk and max_pair_m <= T["village_far_m"]
    output = {"points": rows, "max_pairwise_distance_m": round(max_pair_m, 1),
             "points_outside_taluk": [r["role"] for r in outside_taluk],
             "consistent": consistent, "boundary_layer_available": geo.available}
    latency = int((time.perf_counter() - t0) * 1000)
    tr = ToolResult(tool="geo_validation", input_summary=inp, output=output, status="success", latency_ms=latency,
                    source_type="derived", source_name=GEO_SOURCE)
    state.record_tool_result(tr)
    return tr


def crop_stage_tool(state: SharedState, *, claim: dict, ground_truth_crops: list[str],
                    ground_truth_stages: list[str], observed_crop: Optional[str] = None,
                    observed_stage: Optional[str] = None) -> ToolResult:
    """{"observed_crop", "observed_stage", "ground_truth_crop", "ground_truth_stage", "...consistency"}.
    `observed_crop`/`observed_stage` are optional AI readings from an already-completed image
    analysis (Nova Lite) - this tool does not call a model itself, only compares whatever it is
    given against the challenge dataset's reference labels."""
    t0 = time.perf_counter()
    claimed_crop = normalize_crop(claim.get("claimed_crop"))
    claimed_stage = (claim.get("claimed_stage") or "").strip().lower().replace(" ", "_") or None
    gt_crops = sorted({c for c in ground_truth_crops if c})
    gt_crops_n = {normalize_crop(c) for c in gt_crops}
    gt_stages = sorted({s for s in ground_truth_stages if s})

    def verdict(value, reference_set):
        if not reference_set:
            return "no_reference"
        if value is None:
            return "no_reference"
        return "consistent" if value in reference_set else "inconsistent"

    crop_consistency = verdict(claimed_crop, gt_crops_n) if claimed_crop else "no_claim"
    stage_consistency = verdict(claimed_stage, set(gt_stages)) if claimed_stage else "no_claim"
    photo_crop_consistency = (verdict(normalize_crop(observed_crop), gt_crops_n | ({claimed_crop} if claimed_crop else set()))
                              if observed_crop else "not_analyzed")

    output = {
        "claimed_crop": claim.get("claimed_crop"), "claimed_stage": claim.get("claimed_stage"),
        "ground_truth_crop": gt_crops or None, "ground_truth_stage": gt_stages or None,
        "observed_crop": observed_crop, "observed_stage": observed_stage,
        "crop_consistency": crop_consistency, "stage_consistency": stage_consistency,
        "photo_vs_reference_crop_consistency": photo_crop_consistency,
    }
    latency = int((time.perf_counter() - t0) * 1000)
    tr = ToolResult(tool="crop_stage_evidence", input_summary={"claimed_crop": claim.get("claimed_crop")},
                    output=output, status="success", latency_ms=latency,
                    source_type="challenge_dataset" if gt_crops or gt_stages else "derived", source_name=CROP_SOURCE)
    state.record_tool_result(tr)
    return tr


RETRIEVAL_SOURCE = "Titan Multimodal Embeddings G1 similarity over the FarmwiseAI challenge images"
RETRIEVAL_LIMITATIONS = [
    "Visual similarity is not proof of crop, stage or damage: similar-looking photos can show different crops",
    "Neighbour labels are FarmwiseAI reference labels, which may contain errors",
    "Only images in the challenge dataset can be retrieved",
]


def image_retrieval_tool(state: SharedState, *, client, registry: dict, conn, image_bytes: bytes,
                         query_label: str, exclude_image_ids: tuple = (), top_k: int = 5,
                         claimed_crop: Optional[str] = None, dim: Optional[int] = None) -> ToolResult:
    """Embeds the claim photo with Titan Multimodal Embeddings and returns the most visually similar
    challenge-dataset images with their reference crop/stage/location/date. Also reports how many of
    the neighbours share the claimed crop - a contextual signal, not a verdict."""
    task, model_key = "visual_similarity_retrieval", "titan_embed_image_v1"
    inp = {"query_image": query_label, "top_k": top_k}
    t0 = time.perf_counter()

    def fail(msg: str) -> ToolResult:
        tr = ToolResult(tool="image_retrieval", input_summary=inp, output=None, status="failed", error=msg,
                        latency_ms=int((time.perf_counter() - t0) * 1000), source_type="challenge_dataset",
                        source_name=RETRIEVAL_SOURCE)
        state.record_tool_result(tr)
        return tr

    spec = registry.get(model_key)
    if spec is None or not spec.enabled or not spec.configured:
        return fail(f"{model_key} is not enabled/configured in the model registry")
    dim = dim or image_index.image_embed_dim()
    ids, matrix = image_index.load_matrix(conn, spec.model_id, dim)
    if not ids:
        return fail("image index is empty; build it first with: python -m scripts.build_image_index")

    state.route(task, model_key, "embed the claim photo to retrieve visually similar challenge evidence")
    t1 = time.perf_counter()
    sha = hashlib.sha256(image_bytes).hexdigest()

    cached_vec_row = conn.execute(
        "SELECT vector, model_id FROM image_embeddings WHERE (file_sha256=? OR image_id=?) AND dim=?",
        (sha, query_label, dim)
    ).fetchone()

    if cached_vec_row:
        vec = list(np.frombuffer(cached_vec_row[0], dtype=np.float32))
        used_id = cached_vec_row[1] or spec.model_id
        state.record_model_output(ModelOutput(task=task, model_key=model_key, model_id=used_id, ok=True,
                                              output_summary=f"{len(vec)}-dim image embedding (cached)",
                                              latency_ms=int((time.perf_counter() - t1) * 1000)))
    else:
        try:
            vec, used_id = image_index.embed_image_bytes(client, spec.model_id, image_bytes, dim)
            image_index.store_vector(conn, sha[:32], used_id, dim, vec, sha)
            conn.commit()
            state.record_model_output(ModelOutput(task=task, model_key=model_key, model_id=used_id, ok=True,
                                                  output_summary=f"{len(vec)}-dim image embedding",
                                                  latency_ms=int((time.perf_counter() - t1) * 1000)))
        except BedrockError as e:
            state.record_model_output(ModelOutput(task=task, model_key=model_key, model_id=spec.model_id, ok=False,
                                                  output_summary="", error=f"{e.code}: {e.message}",
                                                  latency_ms=int((time.perf_counter() - t1) * 1000)))
            return fail(f"query image could not be embedded ({e.code}: {e.message})")

    exclude = set(exclude_image_ids)
    exclude |= {r[0] for r in conn.execute("SELECT image_id FROM image_embeddings WHERE file_sha256=?", (sha,))}
    hits = image_index.top_k(ids, matrix, vec, top_k, exclude=exclude)

    similar, crops = [], {}
    for image_id, sim in hits:
        d = ds.get_image(conn, image_id) or {}
        crop = d.get("crop_name")
        crops[crop or "unknown"] = crops.get(crop or "unknown", 0) + 1
        similar.append({"image_id": image_id, "similarity": round(sim, 4), "crop": crop, "stage": d.get("crop_stage"),
                        "location": {"lat": d.get("image_lat"), "lon": d.get("image_lon")} if d.get("image_lat") is not None else None,
                        "timestamp": d.get("image_date")})
    agreement = None
    if claimed_crop and similar:
        want = normalize_crop(claimed_crop)
        agreement = round(sum(1 for x in similar if normalize_crop(x["crop"]) == want) / len(similar), 2)
    output = {"query_image": query_label, "embedding_model": used_id, "embedding_dim": len(vec),
              "index_size": len(ids), "similar_images": similar, "neighbour_crop_counts": crops,
              "claimed_crop_agreement_fraction": agreement, "limitations": RETRIEVAL_LIMITATIONS}
    tr = ToolResult(tool="image_retrieval", input_summary=inp, output=output, status="success",
                    latency_ms=int((time.perf_counter() - t0) * 1000), source_type="challenge_dataset",
                    source_name=RETRIEVAL_SOURCE)
    state.record_tool_result(tr)
    return tr
