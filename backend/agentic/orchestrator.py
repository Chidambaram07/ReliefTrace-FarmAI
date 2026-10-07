"""Agentic orchestrator (Phase 9): the first place all of Phases 2-7 actually run together against
one real claim.

This is a NEW, separate execution path - backend/verification/pipeline.py (the proven MVP flow the
dashboard already uses) is not modified or called from here, and nothing this module does can
change its behaviour. That is a deliberate choice, not a shortcut: the existing pipeline is what
judges will see working reliably throughout the demo, so this phase adds the richer agentic
behaviour alongside it rather than risking it.

Evidence aggregation strategy: the existing, already-correct evidence adapters (crop metadata, GPS/
boundary, timestamp, weather, Nova Lite imagery, disaster-feed stub) are reused UNCHANGED via
run_adapters()/default_adapters() - there is no reason to reinvent evidence this project already
produces correctly. On top of that, three genuinely NEW pieces of evidence are added: a cross-model
geo validation, an independent (Ministral) review of Nova Lite's own observations, and (best-effort)
visual similarity retrieval against the Titan-embedded challenge dataset. All of it - old and new -
is converted to the same EvidenceItem currency and passed to the SAME deterministic verification
engine (backend/verification/engine.py, untouched), so today's score/status logic still applies; the
genuinely new signal is that independent-review disagreement is now surfaced directly in
SharedState.contradictions even where the engine's own checks don't yet have a rule for it.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import time

from backend.agentic import evidence_bridge, image_index
from backend.agentic.independent_review import run_independent_review
from backend.agentic.planner import build_plan
from backend.agentic.review_triggers import evaluate_review_triggers
from backend.agentic.router import ModelRouter
from backend.agentic.state import ModelOutput, SharedState, ToolResult
from backend.agentic.tools import geo_validation_tool, image_retrieval_tool
from backend.dataset import db
from backend.errors import AppError
from backend.evidence.adapters import collect_points, default_adapters
from backend.evidence.base import EvidenceContext, run_adapters
from backend.evidence.parcel import resolve_parcel
from backend.repositories import ai as ai_repo
from backend.repositories import claims as claims_repo
from backend.repositories import dataset as ds
from backend.repositories import verification as vrepo
from backend.schemas.verification import AuditStep
from backend.verification import engine, report as report_mod
from backend.verification.planner import plan_verification
from backend.verification.rules import THRESHOLDS

log = logging.getLogger("reliefTrace.agentic.orchestrator")
MAX_AI_IMAGES = 3


def _record_bedrock_result(state: SharedState, task: str, model_key: str, result_dict: dict) -> None:
    """Bridges an already-made BedrockService call (Nova Lite vision, via the proven, schema-
    validated backend.services.bedrock_service path - not reinvented here) into the shared-state
    trace, so it shows up in the same audit trail as router-made calls."""
    state.route(task, model_key, "primary vision model for this task")
    u = result_dict.get("usage") or {}
    state.record_model_output(ModelOutput(
        task=task, model_key=model_key, model_id=result_dict.get("model_id"), ok=result_dict["ok"],
        output_summary="parsed image observation" if result_dict["ok"] else "",
        confidence=None, input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
        cost_estimate_usd=u.get("cost_estimate_usd"), latency_ms=u.get("latency_ms"),
        error=None if result_dict["ok"] else (result_dict.get("error") or {}).get("message")))


def run_agentic_verification(conn, settings, bedrock, router: ModelRouter, client, registry: dict, geo, http,
                             claim_id: str, *, analyze: bool = True, run_independent: bool = True,
                             run_retrieval: bool = True) -> dict:
    t0 = time.perf_counter()
    claim = claims_repo.get_claim(conn, claim_id)
    if not claim:
        raise AppError(404, "CLAIM_NOT_FOUND", f"No claim '{claim_id}'")
    images = claims_repo.list_claim_images(conn, claim_id)
    state = SharedState(claim_id=claim_id, claim=claim)

    # 1. plan (Phase 3) - drives which of the new tasks below are even attempted
    plan = build_plan(state, n_images=len(images))

    # 2. claim validation against reference data (existing, reused)
    parcel = resolve_parcel(conn, claim)
    state.trace(step="claim_validation", agent="planner", task="resolve_parcel",
               output_summary=f"parcel: {parcel['status']} ({len(parcel['records'])} record(s))")
    dataset_images = {}
    if ds.dataset_loaded(conn):
        for im in images:
            if im["dataset_image_id"]:
                d = ds.get_image(conn, im["dataset_image_id"])
                if d:
                    dataset_images[im["image_key"]] = {"image": d, "records": ds.linked_records(conn, d["image_id"])}

    # 3. Nova Lite vision (existing, schema-validated path; reused unchanged) - needed as INPUT to
    #    the independent review below, so it runs before that step regardless of task ordering.
    analyses: dict[int, dict | None] = {}
    ai_failures = 0
    for im in images[:MAX_AI_IMAGES]:
        key = im["image_key"]
        prior = ai_repo.latest_analysis(conn, claim_id, key)
        if prior and prior["result"]["ok"]:
            analyses[key] = prior["result"]
            state.trace(step=f"image_analysis:{key}", agent="vision", task="photo_analysis",
                       model=prior["result"].get("model_id"), status="success", output_summary="reused cached result")
            continue
        path = im["file_path"]
        from backend.services import image_service, prompts
        if not analyze or not (path and image_service.is_image_available(path, settings=settings)):
            analyses[key] = None
            state.trace(step=f"image_analysis:{key}", agent="vision", task="photo_analysis", status="skipped",
                       error="analysis disabled" if not analyze else "image file not available")
            continue
        img_bytes = image_service.read_image_bytes(path, settings=settings)
        res = bedrock.analyze_image(img_bytes, prompts.claim_context(claim), cache=ai_repo.SqliteAICache(conn))
        r = res.model_dump()
        ai_repo.add_analysis(conn, claim_id, key, r)
        analyses[key] = r
        ai_failures += 0 if res.ok else 1
        _record_bedrock_result(state, "photo_analysis", "nova_lite", r)

    # 4. existing evidence adapters (crop metadata, GPS/boundary, timestamp, weather, imagery, disaster)
    lgd_map = ds.village_code_map(conn)
    recs = parcel.get("records") or []
    village_code = ((recs[0].get("village_code") if recs and len(parcel.get("villages", [])) == 1
                    else geo.resolve_code(claim.get("village_lgd"), lgd_map)) if geo.available else None)
    ctx = EvidenceContext(claim=claim, images=images, dataset_images=dataset_images, parcel=parcel, analyses=analyses,
                          geo=geo, http=http, open_conn=lambda: db.connect(settings.db_path),
                          gt_tolerance=ds.gt_image_distance_percentiles(conn) if ds.dataset_loaded(conn) else {})
    ctx.village_code = village_code
    ctx.points = collect_points(ctx)
    evidence, ev_audit = run_adapters(ctx, default_adapters())
    for a in ev_audit:
        state.trace(step=a["step"], agent=a["agent"], task=a["agent"], status="success" if a["status"] == "ok" else "failed",
                   latency_ms=a["duration_ms"], error=a.get("detail") if a["status"] != "ok" else None)

    # 5. NEW: geo cross-check across every known point (Phase 5)
    geo_tr = geo_validation_tool(state, points=ctx.points, geo=geo, village_code=village_code)
    evidence.append(evidence_bridge.from_tool_result(geo_tr))

    # 6. NEW: independent review of Nova Lite's own observations (Phase 7) - only meaningful if a
    #    successful vision reading exists to review.
    ok_analysis = next((a for a in analyses.values() if a and a.get("ok")), None)
    if run_independent and ok_analysis:
        review = run_independent_review(state, router, claim, ok_analysis["parsed"])
        evidence.append(evidence_bridge.from_independent_review(review))
    elif run_independent:
        state.trace(step="independent_photo_review", agent="router", task="independent_photo_review",
                   status="skipped", error="no successful vision reading to review")

    # 7. NEW, best-effort: visual similarity retrieval against the Titan-embedded challenge images
    if run_retrieval and images:
        query_key = images[0]["image_key"]
        query_path = images[0].get("file_path")
        if query_path and os.path.exists(query_path):
            with open(query_path, "rb") as fh:
                qbytes = fh.read()
            exclude = (dataset_images.get(query_key, {}).get("image", {}).get("image_id"),) if query_key in dataset_images else ()
            retr_tr = image_retrieval_tool(state, client=client, registry=registry, conn=conn, image_bytes=qbytes,
                                           query_label=images[0].get("filename") or f"image_key={query_key}",
                                           exclude_image_ids=tuple(x for x in exclude if x),
                                           claimed_crop=claim.get("claimed_crop"), dim=image_index.image_embed_dim())
            evidence.append(evidence_bridge.from_tool_result(retr_tr))

    # 8. same deterministic verification engine as the MVP pipeline (unchanged)
    verification_plan = plan_verification(claim, len(images))
    core = engine.verify(claim, evidence, verification_plan, ai_failures)
    state.set_verification_result({"status": core["status"], "confidence_index": core["scores"].confidence_index})

    # merge the agentic layer's own contradictions (e.g. independent-review disagreement) into the
    # report the officer sees, even for the ones the deterministic engine has no rule for yet
    contradictions = list(core["contradictions"])
    for c in state.contradictions:
        if c not in contradictions:
            contradictions.append(c)

    # Consolidated review trigger evaluation (Phase 12)
    model_disagreement = False
    if state.independent_review and isinstance(state.independent_review, dict):
        agreement = state.independent_review.get("agreement") or {}
        model_disagreement = agreement.get("escalate_to_human", False)
    failed_tools = [tr.tool for tr in state.tool_results if tr.status == "failed"]
    review_eval = evaluate_review_triggers(
        status=core["status"],
        findings=[f.model_dump() for f in core["findings"]],
        scores_dict=core["scores"].model_dump(),
        ai_failures=ai_failures,
        contradictions=state.contradictions,
        model_disagreement=model_disagreement,
        tool_failures=failed_tools,
        independent_review=state.independent_review,
    )
    human_review_required = review_eval["human_review_required"]
    reasons = review_eval["reasons"]
    state.set_review_status("open" if human_review_required else "not_required")

    audit_steps = [
        AuditStep(
            step=t.step,
            agent=t.agent,
            model=t.model,
            status=t.status,
            duration_ms=t.latency_ms or 0,
            detail=t.error or t.output_summary,
        ).model_dump()
        for t in state.audit_trace
    ]

    report = {
        "claim_id": claim_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": core["status"],
        "status_reason": core["status_reason"],
        "claim": {k: claim[k] for k in claims_repo.CLAIM_COLS if k in claim},
        "plan": plan,
        "evidence": [e.model_dump() for e in evidence],
        "findings": [f.model_dump() for f in core["findings"]],
        "supporting": core["supporting"],
        "contradictions": contradictions,
        "missing_evidence": core["missing_evidence"],
        "limitations": core["limitations"],
        "scores": core["scores"].model_dump(),
        "routing": {
            "human_review_required": human_review_required,
            "reasons": reasons,
            "queue_status": "open" if human_review_required else None,
            "triggers": review_eval["triggers"],
        },
        "timeline": core["timeline"],
        "narrative": report_mod.template_narrative(core).model_dump(),
        "audit": audit_steps,
        "rules_applied": THRESHOLDS,
        "provenance_legend": {
            "claim": "Submitted by the claimant; unverified",
            "source_data": "FarmwiseAI reference data / file metadata; reference points may contain errors",
            "ai_observation": "Amazon Nova model reading of the photo; an observation, not ground truth",
            "external_evidence": "Independent external source (e.g. weather archive)",
            "derived": "Computed by ReliefTrace rules from the items above",
        },
        "total_latency_ms": int((time.perf_counter() - t0) * 1000),
    }
    state.complete(total_latency_ms=report["total_latency_ms"])

    # Persist into review_queue and verification_reports (Requirement 16)
    queue_status = vrepo.sync_queue(conn, claim_id, human_review_required, reasons)
    report["routing"]["queue_status"] = queue_status
    report["agentic"] = {"state": state.to_dict(), "audit_report": state.to_audit_report()}
    vrepo.save_report(conn, claim_id, report)

    log.info("agentic verification claim=%s status=%s contradictions=%d review=%s queue=%s", claim_id, core["status"],
            len(contradictions), human_review_required, queue_status)
    return {"state": state.to_dict(), "report": report, "audit_report": state.to_audit_report()}
