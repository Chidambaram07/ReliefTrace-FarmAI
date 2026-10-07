"""Orchestrator: claim -> validation -> plan -> image analysis -> evidence (parallel) -> verification -> report -> queue."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from backend.dataset import db
from backend.errors import AppError
from backend.evidence.adapters import collect_points, default_adapters
from backend.evidence.base import EvidenceContext, run_adapters
from backend.evidence.parcel import resolve_parcel
from backend.repositories import ai as ai_repo
from backend.repositories import claims as claims_repo
from backend.repositories import dataset as ds
from backend.repositories import verification as vrepo
from backend.schemas.verification import AuditStep, Narrative, VerificationReport
from backend.services import image_service, prompts
from . import engine, report
from .planner import plan_verification
from .rules import THRESHOLDS

log = logging.getLogger("reliefTrace.pipeline")
MAX_AI_IMAGES = 3  # cost control: at most 3 photos analysed per claim


def _audit_ai(name, r: dict, dt_ms: int) -> AuditStep:
    u = r.get("usage") or {}
    return AuditStep(step=name, agent="vision" if r["role"] == "vision" else "report", model=r.get("model_id"),
                     status=("cached" if r.get("cached") else "ok") if r["ok"] else f"failed:{(r.get('error') or {}).get('code')}",
                     duration_ms=dt_ms, input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                     cost_estimate_usd=u.get("cost_estimate_usd"), detail=None if r["ok"] else (r.get("error") or {}).get("message"))


def run_verification(conn, settings, bedrock, http, geo, claim_id: str, *, analyze: bool = True, narrative: str = "auto",
                     simulate_failure: frozenset = frozenset()) -> dict:
    t_all = time.perf_counter()
    audit: list[AuditStep] = []
    claim = claims_repo.get_claim(conn, claim_id)
    if not claim:
        raise AppError(404, "CLAIM_NOT_FOUND", f"No claim '{claim_id}'")
    images = claims_repo.list_claim_images(conn, claim_id)

    # 1. claim validation against reference data
    t = time.perf_counter()
    parcel = resolve_parcel(conn, claim)
    audit.append(AuditStep(step="claim_validation", agent="planner", status="ok", duration_ms=int((time.perf_counter() - t) * 1000),
                           detail=f"parcel: {parcel['status']} ({len(parcel['records'])} record(s))"))
    dataset_images = {}
    if ds.dataset_loaded(conn):
        for im in images:
            if im["dataset_image_id"]:
                d = ds.get_image(conn, im["dataset_image_id"])
                if d:
                    dataset_images[im["image_key"]] = {"image": d, "records": ds.linked_records(conn, d["image_id"])}

    # 2. plan
    plan = plan_verification(claim, len(images))
    audit.append(AuditStep(step="plan", agent="planner", status="ok", detail=f"{sum(1 for c in plan['checks'].values() if c['applicable'])} applicable checks"))

    # 3. image analysis (Nova Lite): reuse stored result, else analyse (cached), at most MAX_AI_IMAGES
    analyses: dict[int, dict | None] = {}
    ai_failures = 0
    for im in images[:MAX_AI_IMAGES]:
        key = im["image_key"]
        prior = ai_repo.latest_analysis(conn, claim_id, key)
        if prior and prior["result"]["ok"]:
            analyses[key] = prior["result"]
            audit.append(AuditStep(step=f"image_analysis:{key}", agent="vision", model=prior["result"].get("model_id"), status="reused"))
            continue
        path = im["file_path"]
        if not analyze or not (path and image_service.is_image_available(path, settings=settings)):
            analyses[key] = None
            audit.append(AuditStep(step=f"image_analysis:{key}", agent="vision", status="skipped",
                                   detail="analysis disabled" if not analyze else "image file not available"))
            continue
        t = time.perf_counter()
        try:
            img_bytes = image_service.read_image_bytes(path, settings=settings)
            res = bedrock.analyze_image(img_bytes, prompts.claim_context(claim), cache=ai_repo.SqliteAICache(conn))
        except Exception as e:
            log.warning("Image read for verification analysis failed key=%s: %s", key, e)
            analyses[key] = None
            audit.append(AuditStep(step=f"image_analysis:{key}", agent="vision", status="skipped",
                                   detail=f"image file read failed: {e}"))
            continue
        r = res.model_dump()
        ai_repo.add_analysis(conn, claim_id, key, r)
        analyses[key] = r
        ai_failures += 0 if res.ok else 1
        audit.append(_audit_ai(f"image_analysis:{key}", r, int((time.perf_counter() - t) * 1000)))

    # 4. independent evidence, adapters in parallel
    ctx = EvidenceContext(claim=claim, images=images, dataset_images=dataset_images, parcel=parcel, analyses=analyses, geo=geo,
                          http=http, open_conn=lambda: db.connect(settings.db_path),
                          gt_tolerance=ds.gt_image_distance_percentiles(conn) if ds.dataset_loaded(conn) else {},
                          simulate_failure=simulate_failure)
    lgd_map = ds.village_code_map(conn)
    recs = parcel.get("records") or []
    ctx.village_code = (recs[0].get("village_code") if recs and len(parcel.get("villages", [])) == 1
                        else geo.resolve_code(claim.get("village_lgd"), lgd_map)) if geo.available else None
    ctx.points = collect_points(ctx)
    evidence, ev_audit = run_adapters(ctx, default_adapters())
    audit += [AuditStep(**a) for a in ev_audit]

    # 5. verification (deterministic)
    t = time.perf_counter()
    core = engine.verify(claim, evidence, plan, ai_failures)
    audit.append(AuditStep(step="verification", agent="verification_engine", status="ok", duration_ms=int((time.perf_counter() - t) * 1000),
                           detail="deterministic rules; no model"))

    # 6. narrative: template always; Nova Micro rephrase optionally, guarded against invented numbers
    narr = report.template_narrative(core)
    if narrative == "off":
        narr = Narrative(source="off", summary=core["status"] + ". " + core["status_reason"], key_points=[], recommended_actions=[])
    elif narrative == "auto":
        t = time.perf_counter()
        ai_n, res = report.ai_narrative(bedrock, core)
        audit.append(_audit_ai("report_narrative", res.model_dump(), int((time.perf_counter() - t) * 1000)))
        if ai_n:
            ai_n.recommended_actions = ai_n.recommended_actions or narr.recommended_actions
            narr = ai_n
    audit.append(AuditStep(step="total", agent="pipeline", status="ok", duration_ms=int((time.perf_counter() - t_all) * 1000)))

    rep = VerificationReport(
        claim_id=claim_id, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), status=core["status"],
        status_reason=core["status_reason"], claim={k: claim[k] for k in claims_repo.CLAIM_COLS}, plan=plan, evidence=evidence,
        findings=core["findings"], supporting=core["supporting"], contradictions=core["contradictions"],
        missing_evidence=core["missing_evidence"], limitations=core["limitations"], scores=core["scores"], routing=core["routing"],
        timeline=core["timeline"], narrative=narr, audit=audit, rules_applied=THRESHOLDS)
    d = rep.model_dump()
    rep.routing.queue_status = vrepo.sync_queue(conn, claim_id, rep.routing.human_review_required, rep.routing.reasons)
    d["routing"]["queue_status"] = rep.routing.queue_status
    vrepo.save_report(conn, claim_id, d)
    log.info("verified claim=%s status=%s eci=%s ci=%s review=%s", claim_id, rep.status, rep.scores.evidence_consistency_index, rep.scores.confidence_index, rep.routing.human_review_required)
    return d
