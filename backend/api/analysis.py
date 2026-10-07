from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from backend.deps import get_conn, get_settings_dep
from backend.errors import AppError
from backend.repositories import ai as ai_repo
from backend.repositories import claims as repo
from backend.schemas.ai import AIResult
from backend.services import image_service, prompts

log = logging.getLogger("reliefTrace.analysis")
router = APIRouter(prefix="/claims", tags=["analysis"])

_STATUS = {"BEDROCK_NO_CREDENTIALS": 503, "BEDROCK_THROTTLED": 503, "BEDROCK_UNAVAILABLE": 503,
           "BEDROCK_NETWORK": 503, "BEDROCK_ACCESS_DENIED": 502, "BEDROCK_MODEL_NOT_FOUND": 502,
           "BEDROCK_VALIDATION": 502, "AI_OUTPUT_INVALID": 502, "AI_OUTPUT_TRUNCATED": 502}


class AnalysisOut(BaseModel):
    analysis_id: int
    claim_id: str
    image_key: int
    created_at: str
    result: AIResult


def get_bedrock(request: Request):
    return request.app.state.bedrock


def _load(conn, claim_id: str, image_key: int):
    c = repo.get_claim(conn, claim_id)
    if not c:
        raise AppError(404, "CLAIM_NOT_FOUND", f"No claim '{claim_id}'")
    img = repo.get_claim_image(conn, claim_id, image_key)
    if not img:
        raise AppError(404, "IMAGE_NOT_FOUND", "No such image on this claim")
    return c, img


@router.post("/{claim_id}/images/{image_key}/analyze", response_model=AnalysisOut)
def analyze(claim_id: str, image_key: int, force: bool = Query(False, description="skip the result cache"),
            conn=Depends(get_conn), bedrock=Depends(get_bedrock), settings=Depends(get_settings_dep)):
    claim, img = _load(conn, claim_id, image_key)
    path = img["file_path"]
    if not (path and image_service.is_image_available(path, settings=settings)):
        raise AppError(404, "IMAGE_FILE_MISSING", "Image file is not available on storage")
    try:
        data = image_service.read_image_bytes(path, settings=settings)
    except Exception as e:
        log.error("Failed to read image for analysis %s: %s", path, e)
        raise AppError(404, "IMAGE_FILE_MISSING", "Image file is not available on storage")
    result = bedrock.analyze_image(data, prompts.claim_context(claim), cache=ai_repo.SqliteAICache(conn),
                                   use_cache=not force)
    aid = ai_repo.add_analysis(conn, claim_id, image_key, result.model_dump())  # audit trail incl. failures
    log.info("analysis claim=%s image=%s ok=%s cached=%s tokens=%s/%s", claim_id, image_key, result.ok,
             result.cached, result.usage.input_tokens, result.usage.output_tokens)
    if not result.ok:
        e = result.error
        raise AppError(_STATUS.get(e.code, 502), e.code, e.message,
                       {"analysis_id": aid, "retryable": e.retryable, "raw_text": (result.raw_text or "")[:500]})
    row = ai_repo.latest_analysis(conn, claim_id, image_key)
    return AnalysisOut(analysis_id=aid, claim_id=claim_id, image_key=image_key, created_at=row["created_at"],
                       result=result)


@router.get("/{claim_id}/images/{image_key}/analysis", response_model=AnalysisOut)
def latest(claim_id: str, image_key: int, conn=Depends(get_conn)):
    _load(conn, claim_id, image_key)
    row = ai_repo.latest_analysis(conn, claim_id, image_key)
    if not row:
        raise AppError(404, "ANALYSIS_NOT_FOUND", "This image has not been analyzed yet")
    return AnalysisOut(analysis_id=row["analysis_id"], claim_id=claim_id, image_key=image_key,
                       created_at=row["created_at"], result=AIResult.model_validate(row["result"]))
