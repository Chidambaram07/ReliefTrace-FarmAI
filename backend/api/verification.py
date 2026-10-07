from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from backend.config import Settings
from backend.deps import get_conn, get_settings_dep
from backend.errors import AppError
from backend.repositories import claims as claims_repo
from backend.repositories import verification as vrepo
from backend.schemas.verification import VerificationReport
from backend.verification.pipeline import run_verification

router = APIRouter(tags=["verification"])


class Decision(BaseModel):
    decision: Literal["approve_for_processing", "reject", "request_more_information", "approve"]
    note: Optional[str] = Field(None, max_length=1000)


@router.post("/claims/{claim_id}/verify", response_model=VerificationReport)
def verify(claim_id: str, request: Request, analyze: bool = Query(True, description="run Nova Lite on photos not yet analysed"),
           narrative: Literal["auto", "template", "off"] = Query("auto", description="auto = Nova Micro rephrase (guarded), template = no model call"),
           simulate_failure: str = Query("", description="demo: comma list of sources to fail, e.g. 'weather'"),
           conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    sim = frozenset(s.strip() for s in simulate_failure.split(",") if s.strip())
    st = request.app.state
    return run_verification(conn, settings, st.bedrock, st.http, st.geo, claim_id, analyze=analyze, narrative=narrative, simulate_failure=sim)


def _latest(conn, claim_id):
    if not claims_repo.get_claim(conn, claim_id):
        raise AppError(404, "CLAIM_NOT_FOUND", f"No claim '{claim_id}'")
    r = vrepo.latest_report(conn, claim_id)
    if not r:
        raise AppError(404, "REPORT_NOT_FOUND", "Claim has not been verified yet")
    return r


@router.get("/claims/{claim_id}/report", response_model=VerificationReport)
def get_report(claim_id: str, conn=Depends(get_conn)):
    return _latest(conn, claim_id)["report"]


@router.get("/claims/{claim_id}/evidence")
def get_evidence(claim_id: str, conn=Depends(get_conn)):
    rep = _latest(conn, claim_id)["report"]
    return {"claim_id": claim_id, "legend": rep["provenance_legend"], "evidence": rep["evidence"]}


@router.get("/review-queue")
def review_queue(status: Optional[Literal["open", "decided"]] = "open", conn=Depends(get_conn)):
    return {"items": vrepo.list_queue(conn, status)}


@router.post("/review-queue/{claim_id}/decision")
def decide(claim_id: str, body: Decision, conn=Depends(get_conn)):
    if not vrepo.decide(conn, claim_id, body.decision, body.note):
        raise AppError(404, "NOT_IN_QUEUE", "Claim is not in the review queue")
    claim = claims_repo.get_claim(conn, claim_id)
    return {
        "claim_id": claim_id,
        "decision": body.decision,
        "note": body.note,
        "recorded_by": "human reviewer",
        "claim_status": claim["status"] if claim else None,
    }


@router.get("/stats")
def stats(conn=Depends(get_conn)):
    return vrepo.stats(conn)
