import json

from backend.agentic.independent_review import build_user_prompt, run_independent_review
from backend.agentic.router import ModelRouter
from backend.agentic.state import SharedState
from backend.services.model_client import ClientSettings, ModelClient
from tests.test_agentic_router import REGISTRY
from tests.test_model_client import FakeRuntime, client_error

CLAIM = {"claimed_cause": "drought", "claimed_crop": "Rice (Paddy)", "farmer_name": "Should Not Leak"}

NOVA_NO_DAMAGE = {
    "observations": ["green paddy field", "no visible stress"],
    "damage_indicators": [{"type": "none_visible", "visible": False}],
    "claim_assessment": {"supports": [], "contradicts": ["no drought stress visible"], "cannot_determine": []},
}
NOVA_SUPPORTS = {
    "observations": ["yellowing leaves", "cracked dry soil"],
    "damage_indicators": [{"type": "drought_stress", "visible": True}],
    "claim_assessment": {"supports": ["visible drought stress"], "contradicts": [], "cannot_determine": []},
}
NOVA_SPARSE = {"observations": ["a field"], "damage_indicators": [],
              "claim_assessment": {"supports": [], "contradicts": [], "cannot_determine": ["everything"]}}


def resp(obj):
    return {"output": {"message": {"content": [{"text": json.dumps(obj)}]}}, "usage": {"inputTokens": 1, "outputTokens": 1}}


def router(rt):
    return ModelRouter(ModelClient(ClientSettings(region="ap-south-1"), runtime_client=rt), REGISTRY)


def test_prompt_carries_only_the_claim_fields_the_reviewer_needs():
    text = build_user_prompt(CLAIM, NOVA_SUPPORTS)
    assert "drought" in text and "Rice (Paddy)" in text and "Should Not Leak" not in text
    assert "yellowing leaves" in text


def test_reviewer_disagrees_records_a_contradiction():
    r = resp({"agrees_with_claim": False, "confidence": "high", "reasoning": "no stress mentioned",
             "disagreement": "observations list green healthy paddy"})
    s = SharedState("C", CLAIM)
    out = run_independent_review(s, router(FakeRuntime(r)), CLAIM, NOVA_NO_DAMAGE)
    assert out["ok"] and out["output"]["agrees_with_claim"] is False
    assert any("does not support the claim" in c for c in s.contradictions)


def test_reviewer_agrees_and_vision_model_also_supports_no_contradiction_recorded():
    r = resp({"agrees_with_claim": True, "confidence": "medium", "reasoning": "consistent with drought"})
    s = SharedState("C", CLAIM)
    out = run_independent_review(s, router(FakeRuntime(r)), CLAIM, NOVA_SUPPORTS)
    assert out["ok"] and out["output"]["agrees_with_claim"] is True
    assert s.contradictions == []


def test_cross_model_disagreement_recorded_even_when_reviewer_agrees_with_claim():
    # Nova's OWN assessment contradicts the claim, but the independent reviewer says it agrees:
    # this is a genuine model-vs-model disagreement, distinct from "reviewer vs claim".
    r = resp({"agrees_with_claim": True, "confidence": "low", "reasoning": "plausible"})
    s = SharedState("C", CLAIM)
    out = run_independent_review(s, router(FakeRuntime(r)), CLAIM, NOVA_NO_DAMAGE)
    assert out["ok"]
    assert any("Model disagreement" in c and "ministral" in c.lower() for c in s.contradictions)


def test_sparse_observations_undecided_is_not_reported_as_disagreement():
    r = resp({"agrees_with_claim": None, "confidence": "low", "reasoning": "not enough information"})
    s = SharedState("C", CLAIM)
    out = run_independent_review(s, router(FakeRuntime(r)), CLAIM, NOVA_SPARSE)
    assert out["ok"] and out["output"]["agrees_with_claim"] is None
    assert s.contradictions == []


def test_malformed_model_output_is_handled_without_crashing():
    r = resp("not even json")  # resp() wraps a string, not a dict -> json.dumps("not even json") = '"not even json"'
    s = SharedState("C", CLAIM)
    out = run_independent_review(s, router(FakeRuntime(r)), CLAIM, NOVA_SUPPORTS)
    assert out["ok"] is False and "AI_OUTPUT_INVALID" in out["error"] and s.contradictions == []


def test_ministral_8b_fails_falls_back_to_ministral_3b_and_still_reviews():
    rt = FakeRuntime(client_error("AccessDeniedException", "no entitlement 8b"),
                     client_error("AccessDeniedException", "still no entitlement 8b"),
                     resp({"agrees_with_claim": False, "reasoning": "no stress mentioned"}))
    s = SharedState("C", CLAIM)
    out = run_independent_review(s, router(rt), CLAIM, NOVA_NO_DAMAGE)
    assert out["ok"] and out["model_key"] == "ministral_3b" and out["fallback_used"] is True
    assert any("does not support the claim" in c for c in s.contradictions)


def test_both_ministral_models_fail_reports_failure_without_fabricating_a_review():
    rt = FakeRuntime(client_error("AccessDeniedException", "a"), client_error("AccessDeniedException", "b"),
                     client_error("ThrottlingException", "c"))
    s = SharedState("C", CLAIM)
    out = run_independent_review(s, router(rt), CLAIM, NOVA_SUPPORTS)
    assert out["ok"] is False and out["output"] is None and s.contradictions == []
    # 2 model_keys attempted (ministral_8b, ministral_3b); each internally also tried its "apac."
    # candidate id before giving up, but that inner retry is ModelClient's job and stays invisible here.
    assert len(s.model_outputs) == 2 and all(not o.ok for o in s.model_outputs)


def test_review_is_traced_in_shared_state_audit_trail():
    r = resp({"agrees_with_claim": True, "reasoning": "ok"})
    s = SharedState("C", CLAIM)
    run_independent_review(s, router(FakeRuntime(r)), CLAIM, NOVA_SUPPORTS)
    assert any(t.task == "independent_photo_review" for t in s.audit_trace)
