"""Agentic verification endpoint (Phase 9) - separate from /api/claims/{id}/verify (the proven MVP
route in backend/api/verification.py, unchanged). This exposes the new planner/router/tools/
independent-review pipeline for side-by-side testing and demonstration without risking the route
the existing dashboard already depends on.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from backend.config import Settings
from backend.deps import get_conn, get_settings_dep
from backend.agentic.orchestrator import run_agentic_verification

router = APIRouter(prefix="/claims", tags=["agentic"])


@router.post("/{claim_id}/verify-agentic")
def verify_agentic(claim_id: str, request: Request,
                   analyze: bool = Query(True, description="run Nova Lite on photos not yet analysed"),
                   independent_review: bool = Query(True, description="run the Ministral independent review"),
                   image_retrieval: bool = Query(True, description="run Titan visual-similarity retrieval"),
                   conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    st = request.app.state
    return run_agentic_verification(
        conn, settings, st.bedrock, st.model_router, st.model_client, st.model_registry, st.geo, st.http, claim_id,
        analyze=analyze, run_independent=independent_review, run_retrieval=image_retrieval)
