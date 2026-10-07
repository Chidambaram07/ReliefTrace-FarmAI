"""Evaluation engine (Phase 13): predefined scenarios + unseen natural-language requests.

Predefined scenarios use REAL demo claims from demo/claims.json and the challenge dataset.
The unseen-request capability accepts arbitrary natural-language investigation requests and
dynamically plans which models, tools, and verification steps are needed — demonstrating that
ReliefTrace is an agentic system, not a collection of hard-coded scenarios.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from backend.agentic.orchestrator import run_agentic_verification
from backend.agentic.planner import build_plan, classify_intent
from backend.agentic.review_triggers import evaluate_review_triggers
from backend.agentic.router import ModelRouter
from backend.agentic.state import SharedState
from backend.dataset import db
from backend.errors import AppError
from backend.repositories import claims as claims_repo

log = logging.getLogger("reliefTrace.agentic.evaluator")

# Location of demo/claims.json relative to the project root
DEMO_CLAIMS_PATH = Path(__file__).resolve().parent.parent.parent / "demo" / "claims.json"


def _load_demo_claims() -> list[dict]:
    if DEMO_CLAIMS_PATH.exists():
        with open(DEMO_CLAIMS_PATH) as f:
            return json.load(f)
    return []


# ------------------------------------------------------------------ predefined scenarios
PREDEFINED_SCENARIOS = [
    {
        "id": "drought_on_healthy_paddy",
        "name": "Drought claim on a healthy-looking paddy (contradictory)",
        "description": "A drought claim on a known paddy parcel, but the photo shows healthy-looking "
                       "vegetation. Weather, photo evidence, and independent review are expected to "
                       "contradict the claim.",
        "demo_claim_index": 0,
        "expected_checks": ["weather", "crop", "claim_vs_image", "location", "timing"],
    },
    {
        "id": "contradictory_weather",
        "name": "Contradictory weather evidence",
        "description": "A drought claim where the weather record may show normal or wet conditions, "
                       "producing a contradiction.",
        "demo_claim_index": 0,  # same claim — weather might contradict depending on actual data
        "expected_checks": ["weather"],
    },
    {
        "id": "crop_mismatch",
        "name": "Crop mismatch",
        "description": "Claim says rice, but the photo shows coconut palm and tilled soil. The crop "
                       "check should flag a mismatch.",
        "demo_claim_index": 2,
        "expected_checks": ["crop", "claim_vs_image"],
    },
    {
        "id": "timing_conflict",
        "name": "Timing conflict (photo before incident)",
        "description": "The photo is dated before the reported incident date. The timing check should "
                       "flag a contradiction.",
        "demo_claim_index": 3,
        "expected_checks": ["timing"],
    },
    {
        "id": "pest_claim",
        "name": "Pest claim (weather cannot verify)",
        "description": "Pest damage cannot be verified by weather records. The weather check should be "
                       "marked not applicable. Photo evidence is key.",
        "demo_claim_index": 1,
        "expected_checks": ["claim_vs_image", "crop"],
    },
    {
        "id": "model_failure_recovery",
        "name": "Model/tool failure recovery",
        "description": "Simulates how the system handles model or tool unavailability by running "
                       "the first demo claim with retrieval disabled (simulating a tool failure).",
        "demo_claim_index": 0,
        "run_options": {"run_retrieval": False},
    },
]

# Three reliable demonstration cases showing different system outcomes.
# Each maps to a predefined scenario and uses real challenge data.
DEMO_CASES = [
    {
        "case": "contradictory",
        "label": "Evidence contradicts the claim",
        "description": "Drought claim on a healthy-looking paddy field. The photo shows green "
                       "vegetation inconsistent with drought, weather data may show normal rainfall, "
                       "and independent review disagrees with the claim.",
        "scenario_id": "drought_on_healthy_paddy",
        "expected_outcome": "Contradictory evidence found",
    },
    {
        "case": "insufficient",
        "label": "Evidence is insufficient or missing",
        "description": "Pest damage claim where weather records cannot verify pest presence. "
                       "Key evidence checks are not applicable, producing low coverage and "
                       "requiring human review.",
        "scenario_id": "pest_claim",
        "expected_outcome": "Insufficient evidence or requires further verification",
    },
    {
        "case": "crop_mismatch",
        "label": "Evidence contradicts (crop mismatch)",
        "description": "Claim says rice crop, but the photo shows a coconut palm and tilled soil. "
                       "The crop check flags an inconsistency. This demonstrates the system catching "
                       "a factual discrepancy between claimed and observed crop type.",
        "scenario_id": "crop_mismatch",
        "expected_outcome": "Contradictory evidence found",
    },
]


def list_scenarios() -> list[dict]:
    """Return the predefined scenario list (metadata only, no execution)."""
    return [
        {"id": s["id"], "name": s["name"], "description": s["description"]}
        for s in PREDEFINED_SCENARIOS
    ]


def list_demo_cases() -> list[dict]:
    """Return the three reliable demonstration cases (metadata only)."""
    return DEMO_CASES


def run_scenario(
    conn, settings, bedrock, router: ModelRouter, client, registry, geo, http,
    scenario_id: str,
) -> dict:
    """Run a predefined evaluation scenario end-to-end using real data."""
    scenario = next((s for s in PREDEFINED_SCENARIOS if s["id"] == scenario_id), None)
    if not scenario:
        raise AppError(404, "SCENARIO_NOT_FOUND", f"No predefined scenario '{scenario_id}'")

    demo_claims = _load_demo_claims()
    idx = scenario.get("demo_claim_index", 0)
    if idx >= len(demo_claims):
        raise AppError(500, "DEMO_DATA_MISSING", f"Demo claim index {idx} not found in demo/claims.json")
    dc = demo_claims[idx]

    # Ensure the demo claim exists in the database
    claim_id = _ensure_demo_claim(conn, dc)

    run_opts = scenario.get("run_options", {})
    result = run_agentic_verification(
        conn, settings, bedrock, router, client, registry, geo, http,
        claim_id, analyze=True, run_independent=True,
        run_retrieval=run_opts.get("run_retrieval", True),
    )

    return {
        "scenario": {"id": scenario["id"], "name": scenario["name"],
                      "description": scenario["description"]},
        "claim_id": claim_id,
        "report": result["report"],
        "audit_report": result["audit_report"],
    }


def run_unseen_request(
    conn, settings, bedrock, router: ModelRouter, client, registry, geo, http,
    request_text: str,
    claim_id: Optional[str] = None,
) -> dict:
    """Process an arbitrary natural-language investigation request.

    If claim_id is provided, the request is about that specific claim.
    If not provided, the planner decides what to do based on the request text alone.
    """
    if not request_text or not request_text.strip():
        raise AppError(400, "EMPTY_REQUEST", "The investigation request text cannot be empty")

    t0 = time.perf_counter()

    # If no specific claim, try to find one or create a synthetic investigation
    if claim_id:
        claim = claims_repo.get_claim(conn, claim_id)
        if not claim:
            raise AppError(404, "CLAIM_NOT_FOUND", f"No claim '{claim_id}'")
    else:
        # Use the first available claim for demonstration, or report that no claim exists
        total, all_claims = claims_repo.list_claims(conn, limit=1, offset=0)
        if all_claims:
            claim_id = all_claims[0]["claim_id"]
            claim = claims_repo.get_claim(conn, claim_id)
        else:
            raise AppError(404, "NO_CLAIMS", "No claims exist in the system. Submit a claim first.")

    # Build a dynamic plan from the free-text request
    state = SharedState(claim_id=claim_id, claim=claim)
    plan = build_plan(state, request_text=request_text, n_images=len(claims_repo.list_claim_images(conn, claim_id)))

    # For full-verification intents, run the complete agentic pipeline
    intent = plan["intent"]
    if intent == "full_verification":
        result = run_agentic_verification(
            conn, settings, bedrock, router, client, registry, geo, http,
            claim_id, analyze=True, run_independent=True, run_retrieval=True,
        )
        return {
            "request_text": request_text,
            "intent": {"key": intent, "label": plan["intent_label"], "reason": plan["intent_reason"]},
            "claim_id": claim_id,
            "report": result["report"],
            "audit_report": result["audit_report"],
        }

    # For focused intents, run a targeted investigation
    images = claims_repo.list_claim_images(conn, claim_id)

    # Load existing report if available (for query intents like explain_human_review)
    from backend.repositories import verification as vrepo
    existing = vrepo.latest_report(conn, claim_id)
    existing_report = existing["report"] if existing else None

    response_data = {
        "request_text": request_text,
        "intent": {"key": intent, "label": plan["intent_label"], "reason": plan["intent_reason"]},
        "claim_id": claim_id,
        "plan": plan,
    }

    if intent == "find_contradictions":
        if existing_report:
            response_data["contradictions"] = existing_report.get("contradictions", [])
            response_data["findings"] = [
                f for f in existing_report.get("findings", [])
                if f.get("verdict") == "contradicts"
            ]
        else:
            response_data["contradictions"] = []
            response_data["note"] = "No verification report exists yet. Run verification first."

    elif intent == "check_evidence_sufficiency":
        if existing_report:
            response_data["missing_evidence"] = existing_report.get("missing_evidence", [])
            response_data["coverage"] = existing_report.get("scores", {}).get("coverage")
            response_data["evidence_consistency_index"] = existing_report.get("scores", {}).get("evidence_consistency_index")
        else:
            response_data["note"] = "No verification report exists yet. Run verification first."

    elif intent == "explain_human_review":
        if existing_report:
            routing = existing_report.get("routing", {})
            response_data["human_review_required"] = routing.get("human_review_required")
            response_data["reasons"] = routing.get("reasons", [])
            response_data["triggers"] = routing.get("triggers", {})
        else:
            response_data["note"] = "No verification report exists yet. Run verification first."

    elif intent == "compare_image_ground_truth":
        response_data["note"] = ("Image comparison requires Titan Multimodal Embeddings. "
                                  "Run full verification (with image retrieval enabled) "
                                  "to see visual similarity results.")

    state.complete(total_latency_ms=int((time.perf_counter() - t0) * 1000))
    response_data["audit_report"] = state.to_audit_report()
    return response_data


def _ensure_demo_claim(conn, dc: dict) -> str:
    """Ensure a demo claim exists in the database and return its claim_id."""
    claim_data = dc["claim"]
    # Check if a claim with the same survey_no and village already exists
    existing = conn.execute(
        "SELECT claim_id FROM claims WHERE survey_no=? AND village_lgd=? LIMIT 1",
        (claim_data["survey_no"], claim_data.get("village_lgd", ""))
    ).fetchone()
    if existing:
        return existing["claim_id"]

    # Create it
    claim_id = claims_repo.add_claim(conn, claim_data)

    # Attach dataset image if specified
    if dc.get("image_id"):
        from backend.repositories import dataset as ds
        img = ds.get_image(conn, dc["image_id"])
        if img and img.get("file_path") and os.path.exists(img["file_path"]):
            claims_repo.add_image(conn, claim_id, img["file_path"],
                                  os.path.basename(img["file_path"]),
                                  dataset_image_id=dc["image_id"])
    return claim_id
