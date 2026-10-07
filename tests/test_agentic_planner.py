import pytest

from backend.agentic.planner import FUTURE, READY, build_plan, classify_intent
from backend.agentic.state import SharedState


def test_classify_intent_defaults_to_full_verification_with_no_text():
    key, label, reason = classify_intent(None)
    assert key == "full_verification" and "no free-text request" in reason


@pytest.mark.parametrize("text,expected", [
    ("Why was this claim sent for human review?", "explain_human_review"),
    ("Check whether this claim has enough evidence", "check_evidence_sufficiency"),
    ("Find contradictory evidence in this claim", "find_contradictions"),
    ("Compare this image with the available ground truth", "compare_image_ground_truth"),
    ("My rice field was damaged by drought", "full_verification"),
])
def test_classify_intent_matches_expected_examples_from_the_brief(text, expected):
    key, _, reason = classify_intent(text)
    assert key == expected and reason


def claim(**over):
    base = {"claimed_cause": "drought", "claimed_crop": "Rice (Paddy)", "claimed_stage": "full_growth"}
    return {**base, **over}


def test_full_verification_plan_with_image_routes_all_ready_models():
    s = SharedState(claim_id="CLM-1", claim=claim())
    plan = build_plan(s, n_images=1)
    assert plan["intent"] == "full_verification"
    ready_models = {t["task"]: t["model_key"] for t in plan["tasks"] if t["status"] == READY and t["model_key"]}
    assert ready_models == {
        "photo_analysis": "nova_lite",
        "independent_photo_review": "ministral_8b",
        "visual_similarity_retrieval": "titan_embed_image_v1",
        "report_narrative": "nova_micro",
    }
    routed = {sel.task: sel.model_key for sel in s.selected_models}
    assert routed == {"photo_analysis": "nova_lite", "report_narrative": "nova_micro"}


def test_unapplicable_checks_are_future_not_routed():
    s = SharedState(claim_id="CLM-1", claim=claim(claimed_cause="pest"))
    plan = build_plan(s, n_images=0)
    future = [t for t in plan["tasks"] if t["status"] == FUTURE]
    assert any(t["task"] == "check:weather" for t in future)
    assert not any(sel.task == "check:weather" for sel in s.selected_models)


def test_no_image_marks_photo_analysis_future_not_ready():
    s = SharedState(claim_id="CLM-1", claim=claim())
    plan = build_plan(s, n_images=0)
    photo = next(t for t in plan["tasks"] if t["task"] == "photo_analysis")
    assert photo["status"] == FUTURE and photo["model_key"] is None
    assert not any(sel.task == "photo_analysis" for sel in s.selected_models)


def test_weather_task_reflects_check_applicability_by_cause():
    s = SharedState(claim_id="CLM-1", claim=claim(claimed_cause="pest"))
    plan = build_plan(s, n_images=0)
    weather = next(t for t in plan["tasks"] if t["task"] == "check:weather")
    assert weather["status"] == FUTURE and not weather["required"]

    s2 = SharedState(claim_id="CLM-2", claim=claim(claimed_cause="drought"))
    plan2 = build_plan(s2, n_images=0)
    weather2 = next(t for t in plan2["tasks"] if t["task"] == "check:weather")
    assert weather2["status"] == READY and weather2["required"] and weather2["tool"] == "weather"


def test_explain_human_review_plan_reads_existing_report_and_does_not_route_a_model():
    s = SharedState(claim_id="CLM-1", claim=claim())
    plan = build_plan(s, request_text="Why was this claim sent for human review?")
    assert plan["intent"] == "explain_human_review"
    assert [t["task"] for t in plan["tasks"]] == ["load_latest_report", "summarize_review_reasons"]
    assert s.selected_models == []  # narrative task is FUTURE, so nothing is actually routed yet


def test_find_contradictions_and_evidence_sufficiency_plans_need_no_model():
    s1 = SharedState(claim_id="CLM-1", claim=claim())
    build_plan(s1, request_text="find contradictory evidence")
    assert all(t["status"] == READY for t in s1.plan["tasks"])
    assert s1.selected_models == []

    s2 = SharedState(claim_id="CLM-2", claim=claim())
    build_plan(s2, request_text="does this claim have enough evidence")
    assert [t["task"] for t in s2.plan["tasks"]] == ["load_latest_report", "coverage_check"]


def test_compare_image_ground_truth_plans_a_future_retrieval_task_only():
    s = SharedState(claim_id="CLM-1", claim=claim())
    plan = build_plan(s, request_text="compare this image with the ground truth")
    assert len(plan["tasks"]) == 1
    t = plan["tasks"][0]
    assert t["status"] == FUTURE and t["tool"] == "image_retrieval" and t["model_key"] == "titan_embed_image_v1"
    assert s.selected_models == []


def test_build_plan_sets_state_plan_and_traces_it():
    s = SharedState(claim_id="CLM-1", claim=claim())
    plan = build_plan(s, n_images=0)
    assert s.plan == plan
    assert s.audit_trace[0].step == "plan" and s.audit_trace[0].agent == "planner"


def test_plan_is_json_serializable_end_to_end():
    import json
    s = SharedState(claim_id="CLM-1", claim=claim())
    build_plan(s, n_images=1)
    json.dumps(s.to_dict())
