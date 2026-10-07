"""Bridges the agentic layer's own result shapes (ToolResult from tools.py, the independent-review
dict from independent_review.py) into EvidenceItem - the ONE evidence currency the deterministic
verification engine, the API and the dashboard already understand. Nothing here invents a new
evidence representation; it normalises what Phase 5-7 already produced so it can sit in the same
evidence list as the existing (unchanged) evidence adapters.
"""
from __future__ import annotations

from typing import Optional

from backend.agentic.state import ToolResult
from backend.evidence.models import EvidenceItem, Location, unavailable

_SOURCE_KIND = {"challenge_dataset": "source_data", "public_dataset": "external_evidence",
               "demo_data": "external_evidence", "claimant_input": "claim", "derived": "derived"}


def _summarize(tr: ToolResult) -> str:
    o = tr.output or {}
    if tr.tool == "weather":
        return (f"30-day rainfall {o.get('rainfall_mm_30d')} mm, drought indicator: {o.get('drought_indicator')} "
                f"(percentile {o.get('percentile_vs_10yr_baseline', {}).get('sum_mm')} vs the 10-year baseline).")
    if tr.tool == "geo_validation":
        pts = o.get("points", [])
        return (f"{len(pts)} location(s) checked; max separation {o.get('max_pairwise_distance_m')} m; "
                f"{'all inside the study taluk' if not o.get('points_outside_taluk') else o['points_outside_taluk']}; "
                f"consistent={o.get('consistent')}.")
    if tr.tool == "image_retrieval":
        sim = o.get("similar_images", [])
        top = sim[0] if sim else None
        agree = o.get("claimed_crop_agreement_fraction")
        return (f"{len(sim)} visually similar challenge image(s) found" +
               (f"; closest match {top['image_id'][:20]}... (similarity {top['similarity']}, crop {top['crop']})" if top else "") +
               (f"; {round(agree * 100)}% of neighbours share the claimed crop." if agree is not None else "."))
    if tr.tool == "crop_stage_evidence":
        return (f"crop consistency: {o.get('crop_consistency')}, stage consistency: {o.get('stage_consistency')}, "
               f"photo-vs-reference: {o.get('photo_vs_reference_crop_consistency')}.")
    return str(o)[:300]


def from_tool_result(tr: ToolResult) -> EvidenceItem:
    kind = _SOURCE_KIND.get(tr.source_type, "derived")
    if tr.status != "success" or tr.output is None:
        return unavailable(tr.source_name or tr.tool, tr.tool, tr.error or "tool returned no output", kind=kind)
    loc = None
    if tr.tool == "weather" and isinstance(tr.output.get("location"), dict):
        loc = Location(lat=tr.output["location"]["lat"], lon=tr.output["location"]["lon"], label="weather query point")
    limitations = list(tr.output.get("limitations", [])) if isinstance(tr.output.get("limitations"), list) else []
    return EvidenceItem(source=tr.source_name or tr.tool, source_kind=kind, evidence_type=tr.tool,
                        timestamp=tr.output.get("date") if isinstance(tr.output.get("date"), str) else None,
                        location=loc, observation=_summarize(tr), data=tr.output, quality="medium",
                        status="available", limitations=limitations,
                        raw_reference={"tool": tr.tool, "called_at": tr.called_at})


def from_independent_review(review: dict) -> EvidenceItem:
    source = f"Amazon Bedrock {review.get('model_key') or 'ministral'} (independent review)"
    if not review["ok"]:
        return unavailable(source, "independent_model_review", review["error"] or "independent review failed",
                           kind="ai_observation")
    o = review["output"]
    verb = {True: "supports", False: "does not support", None: "is undecided about"}[o["agrees_with_claim"]]
    obs = f"Independent reviewer ({review['model_key']}) {verb} the claim ({o['confidence']} confidence): {o['reasoning']}"
    quality = o["confidence"] if o["confidence"] in ("low", "medium", "high") else "low"
    lims = ["Independent AI review of the FIRST model's text observations only, not the photo itself",
           "AI observation, not ground truth"]
    if review.get("fallback_used"):
        lims.append("Primary reviewer model was unavailable; a fallback model performed this review")
    return EvidenceItem(source=source, source_kind="ai_observation", evidence_type="independent_model_review",
                        observation=obs, data=o, quality=quality, status="available", limitations=lims,
                        raw_reference={"model_key": review["model_key"], "fallback_used": review.get("fallback_used", False)})
