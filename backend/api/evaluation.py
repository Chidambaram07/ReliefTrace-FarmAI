"""Evaluation API endpoints (Phase 13): predefined scenarios and unseen natural-language requests.

Separate from the existing verification and agentic endpoints. These are for demonstrating and
evaluating the system's agentic capabilities.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from backend.config import Settings
from backend.deps import get_conn, get_settings_dep
from backend.agentic.evaluator import list_scenarios, list_demo_cases, run_scenario, run_unseen_request

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


class UnseenRequest(BaseModel):
    request_text: str = Field(..., min_length=1, max_length=2000,
                               description="Natural-language investigation request")
    claim_id: Optional[str] = Field(None, description="Optional: specific claim to investigate")


@router.get("/scenarios")
def get_scenarios():
    """List all predefined evaluation scenarios."""
    return {"scenarios": list_scenarios()}


@router.get("/demo-cases")
def get_demo_cases():
    """List the three reliable demonstration cases showing different system outcomes."""
    return {"demo_cases": list_demo_cases()}


@router.post("/scenarios/{scenario_id}")
def execute_scenario(scenario_id: str, request: Request,
                     conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    """Run a predefined evaluation scenario end-to-end."""
    st = request.app.state
    return run_scenario(
        conn, settings, st.bedrock, st.model_router, st.model_client,
        st.model_registry, st.geo, st.http, scenario_id,
    )


@router.post("/unseen-request")
def execute_unseen_request(body: UnseenRequest, request: Request,
                           conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    """Process an arbitrary natural-language investigation request.

    This is the key capability that demonstrates ReliefTrace is an agentic system:
    the planner dynamically determines what models, tools, and verification steps are needed
    based on the request text, rather than following a hard-coded path.
    """
    st = request.app.state
    return run_unseen_request(
        conn, settings, st.bedrock, st.model_router, st.model_client,
        st.model_registry, st.geo, st.http,
        body.request_text, body.claim_id,
    )
