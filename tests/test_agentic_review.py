import json

import pytest

from backend.agentic.review import (
    IndependentReview, build_user_prompt, compare_stances, run_independent_review, stance_from_observation,
)
from backend.agentic.router import ModelRouter
from backend.agentic.state import SharedState
from backend.services.model_client import ClientSettings, ModelClient
from tests.test_agentic_router import REGISTRY, ok_resp
from tests.test_model_client import FakeRuntime, client_error

CLAIM = {"claimed_cause": "drought", "claimed_crop": "Rice (Paddy)", "incident_date": "2024-11-04",
         "description": "Paddy dried up."}


def evidence():
    return [
        {"evidence_id": "EV-WEAT-1", "source_kind": "external_evidence", "evidence_type": "weather", "status": "available",
         "observation": "30 days rainfall 255 mm, percentile 60", "quality": "medium", "data": {}},
        {"evidence_id": "EV-IMAG-1", "source_kind": "ai_observation", "evidence_type": "ai_image_observation",
         "status": "available", "observation": "crop guess rice", "quality": "medium",
         "data": {"analysis": {"observations": ["green tall vegetation"], "crop": {"name_guess": "rice"},
                               "damage_indicators": [{"type": "none_visible", "visible": True}],
                               "missing_information": ["date"],
                               "claim_assessment": {"contradicts": ["SECRET_FIRST_MODEL_VERDICT"]},
                               "inferences": [{"statement": "SECRET_INFERENCE", "basis": "x"}]}}},
    ]


def first_obs(stance):
    ca = {"contradicts": ["x"]} if stance == "contradicts" else {"supports": ["x"]} if stance == "supports" else {}
    return {"image_usable": True, "claim_assessment": ca}


def review_json(verdict="contradicts", cited=("EV-WEAT-1",), **kw):
    d = {"evidence_against": ["weather is normal"], "evidence_for": [], "missing": [],
         "concerns_about_other_readings": [], "cited_evidence_ids": list(cited), "verdict": verdict, "confidence": "medium"}
    d.update(kw)
    return json.dumps(d)


def make(rt):
    return ModelRouter(ModelClient(ClientSettings(region="ap-south-1"), runtime_client=rt), REGISTRY)


def test_stance_derivation():
    assert stance_from_observation(first_obs("contradicts")) == "contradicts"
    assert stance_from_observation(first_obs("supports")) == "supports"
    assert stance_from_observation(first_obs("none")) == "insufficient"
    assert stance_from_observation({"image_usable": False, "claim_assessment": {"supports": ["x"]}}) == "insufficient"
    assert stance_from_observation({"claim_assessment": {"supports": ["a"], "contradicts": ["b"]}}) == "insufficient"
    assert stance_from_observation(None) == "insufficient"


@pytest.mark.parametrize("a,b,rel,esc", [
    ("contradicts", "contradicts", "agree", False), ("supports", "supports", "agree", False),
    ("supports", "contradicts", "disagree", True), ("contradicts", "supports", "disagree", True),
    ("supports", "insufficient", "partial", False), ("insufficient", "contradicts", "partial", False),
])
def test_compare_stances(a, b, rel, esc):
    r = compare_stances("nova_lite", a, "ministral_8b", b)
    assert r["relation"] == rel and r["escalate_to_human"] is esc


def test_verdict_is_normalised_and_unknown_becomes_insufficient():
    assert IndependentReview.model_validate({"verdict": "Supported"}).verdict == "supports"
    assert IndependentReview.model_validate({"verdict": "CONTRADICTED"}).verdict == "contradicts"
    assert IndependentReview.model_validate({"verdict": "maybe"}).verdict == "insufficient"
    assert IndependentReview.model_validate({}).confidence == "low"


def test_reviewer_does_not_see_first_model_verdict_or_inferences():
    rt = FakeRuntime(ok_resp(review_json()))
    s = SharedState("CLM-1", CLAIM)
    run_independent_review(s, make(rt), claim=CLAIM, evidence=evidence(), first_observation=first_obs("contradicts"))
    sent = json.dumps(rt.calls[0][1])
    assert "SECRET_FIRST_MODEL_VERDICT" not in sent and "SECRET_INFERENCE" not in sent
    assert "green tall vegetation" in sent and "EV-WEAT-1" in sent          # raw facts are provided
    assert "Look for evidence AGAINST" in sent                             # contradiction-first instruction
    assert rt.calls[0][1]["modelId"] == "mistral.ministral-3-8b-instruct"


def test_agreement_is_recorded_and_traced():
    s = SharedState("CLM-1", CLAIM)
    r = run_independent_review(s, make(FakeRuntime(ok_resp(review_json("contradicts")))), claim=CLAIM,
                               evidence=evidence(), first_observation=first_obs("contradicts"))
    assert r["status"] == "completed" and r["reviewer_model"] == "ministral_8b"
    assert r["agreement"]["relation"] == "agree" and r["agreement"]["escalate_to_human"] is False
    assert s.independent_review is r
    assert any(t.step == "model_agreement" for t in s.audit_trace)
    assert [m.model_key for m in s.selected_models] == ["ministral_8b"]


def test_disagreement_is_preserved_and_flagged_for_human_review():
    s = SharedState("CLM-1", CLAIM)
    r = run_independent_review(s, make(FakeRuntime(ok_resp(review_json("supports", cited=("EV-IMAG-1",))))),
                               claim=CLAIM, evidence=evidence(), first_observation=first_obs("contradicts"))
    a = r["agreement"]
    assert a["relation"] == "disagree" and a["escalate_to_human"] is True
    assert a["first_stance"] == "contradicts" and a["second_stance"] == "supports"


def test_invented_citations_are_flagged_not_trusted():
    r = run_independent_review(SharedState("C", CLAIM), make(FakeRuntime(ok_resp(review_json(cited=("EV-WEAT-1", "EV-999"))))),
                               claim=CLAIM, evidence=evidence(), first_observation=first_obs("contradicts"))
    assert r["valid_citations"] == ["EV-WEAT-1"] and r["invalid_citations"] == ["EV-999"]


def test_falls_back_to_ministral_3b_when_8b_fails_and_says_so():
    rt = FakeRuntime(client_error("ThrottlingException", "busy"), ok_resp(review_json()))
    s = SharedState("C", CLAIM)
    r = run_independent_review(s, make(rt), claim=CLAIM, evidence=evidence(), first_observation=first_obs("contradicts"))
    assert r["status"] == "completed" and r["reviewer_model"] == "ministral_3b" and r["fallback_used"] is True
    assert [(x.model_key, x.fallback_of) for x in s.selected_models] == [("ministral_8b", None), ("ministral_3b", "ministral_8b")]


def test_both_reviewers_failing_reports_failed_without_crash():
    rt = FakeRuntime(client_error("ThrottlingException", "a"), client_error("ThrottlingException", "b"))
    r = run_independent_review(SharedState("C", CLAIM), make(rt), claim=CLAIM, evidence=evidence(),
                               first_observation=first_obs("contradicts"))
    assert r["status"] == "failed" and r["review"] is None and "ministral_3b=failed" in r["error"]


def test_malformed_output_is_reported_not_guessed():
    r = run_independent_review(SharedState("C", CLAIM), make(FakeRuntime(ok_resp("I think the claim is fine."))),
                               claim=CLAIM, evidence=evidence(), first_observation=first_obs("contradicts"))
    assert r["status"] == "invalid_output" and r["agreement"] is None and "I think" in r["raw_text"]


def test_no_first_opinion_is_labelled_and_not_escalated():
    r = run_independent_review(SharedState("C", CLAIM), make(FakeRuntime(ok_resp(review_json()))), claim=CLAIM,
                               evidence=evidence(), first_observation=None)
    assert r["agreement"]["relation"] == "no_first_opinion" and r["agreement"]["escalate_to_human"] is False


def test_limitations_always_state_the_reviewer_is_text_only():
    r = run_independent_review(SharedState("C", CLAIM), make(FakeRuntime(ok_resp(review_json()))), claim=CLAIM,
                               evidence=evidence(), first_observation=first_obs("contradicts"))
    assert any("text-only" in l for l in r["limitations"])


def test_prompt_treats_claim_text_as_data_and_truncates_it():
    p = build_user_prompt({**CLAIM, "description": "x" * 900}, evidence())
    assert "<claim>" in p and len(p) < 4000
    assert "x" * 301 not in p
    json.dumps(SharedState("C", CLAIM).to_dict())
