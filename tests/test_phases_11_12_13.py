"""Tests for Phase 11 (richer audit trace), Phase 12 (review triggers), Phase 13 (evaluation)."""
import json

import pytest

from backend.agentic.state import SharedState, ModelOutput, ToolResult, TraceStep
from backend.agentic.review_triggers import evaluate_review_triggers
from backend.agentic.planner import classify_intent, build_plan
from backend.agentic.evaluator import list_scenarios, PREDEFINED_SCENARIOS


CLAIM = {"claimed_cause": "drought", "claimed_crop": "Rice (Paddy)", "incident_date": "2024-11-04",
         "survey_no": "293", "village_lgd": "642626"}


# ================================================================ Phase 11 — Audit Trace
class TestSharedStateEnrichment:
    def test_investigation_id_is_generated(self):
        s = SharedState("C-1", CLAIM)
        assert s.investigation_id.startswith("INV-")
        assert len(s.investigation_id) == 16  # "INV-" + 12 hex chars

    def test_started_at_is_populated(self):
        s = SharedState("C-1", CLAIM)
        assert s.started_at is not None
        assert "T" in s.started_at  # ISO format

    def test_completed_at_is_none_initially(self):
        s = SharedState("C-1", CLAIM)
        assert s.completed_at is None

    def test_complete_sets_completed_at_and_adds_trace_step(self):
        s = SharedState("C-1", CLAIM)
        s.complete(total_latency_ms=123)
        assert s.completed_at is not None
        assert any(t.step == "investigation_complete" for t in s.audit_trace)
        final = [t for t in s.audit_trace if t.step == "investigation_complete"][0]
        assert final.latency_ms == 123
        assert final.agent == "orchestrator"

    def test_to_audit_report_structure(self):
        s = SharedState("C-1", CLAIM)
        s.route("photo_analysis", "nova_lite", "primary vision model")
        s.record_model_output(ModelOutput(
            task="photo_analysis", model_key="nova_lite", model_id="amazon.nova-lite-v1:0",
            ok=True, output_summary="parsed", input_tokens=150, output_tokens=50,
            cost_estimate_usd=0.001, latency_ms=200))
        s.record_tool_result(ToolResult(
            tool="weather", input_summary={"lat": 9.25, "lon": 77.42},
            output={"rainfall_mm_30d": 10}, status="success", latency_ms=300))
        s.set_verification_result({"status": "Supported by available evidence"})
        s.set_review_status("not_required")
        s.complete(total_latency_ms=500)
        ar = s.to_audit_report()

        assert ar["investigation_id"] == s.investigation_id
        assert ar["claim_id"] == "C-1"
        assert ar["started_at"] is not None
        assert ar["completed_at"] is not None
        assert ar["total_steps"] > 0
        assert len(ar["models_invoked"]) == 1
        assert ar["models_invoked"][0]["task"] == "photo_analysis"
        assert ar["models_invoked"][0]["input_tokens"] == 150
        assert len(ar["tools_invoked"]) == 1
        assert ar["tools_invoked"][0]["tool"] == "weather"
        assert len(ar["routing_decisions"]) == 1
        assert ar["token_usage"]["total_input_tokens"] == 150
        assert ar["token_usage"]["total_output_tokens"] == 50
        assert ar["token_usage"]["total_cost_estimate_usd"] == 0.001
        assert ar["verification_status"] == "Supported by available evidence"
        assert ar["review_status"] == "not_required"
        assert isinstance(ar["steps"], list)

    def test_to_audit_report_null_tokens_when_unavailable(self):
        s = SharedState("C-1", CLAIM)
        s.record_model_output(ModelOutput(
            task="t", model_key="k", model_id=None, ok=True, output_summary="x"))
        ar = s.to_audit_report()
        assert ar["token_usage"]["total_input_tokens"] is None
        assert ar["token_usage"]["total_cost_estimate_usd"] is None

    def test_to_dict_includes_new_fields(self):
        s = SharedState("C-1", CLAIM)
        d = s.to_dict()
        assert "investigation_id" in d
        assert "started_at" in d
        assert "completed_at" in d

    def test_unique_investigation_ids(self):
        ids = {SharedState("C", CLAIM).investigation_id for _ in range(20)}
        assert len(ids) == 20


# ================================================================ Phase 12 — Review Triggers
class TestReviewTriggers:
    def _finding(self, check_id, verdict, weight=2.0, severity=None, detail="test"):
        return {"check_id": check_id, "verdict": verdict, "weight": weight,
                "severity": severity, "detail": detail, "title": check_id}

    def _scores(self, eci=70.0, ci=70.0, coverage=0.8, agreement=0.9):
        return {"evidence_consistency_index": eci, "confidence_index": ci,
                "coverage": coverage, "agreement": agreement}

    def test_supported_status_no_issues(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[self._finding("weather", "supports"), self._finding("crop", "supports")],
            scores_dict=self._scores(),
        )
        assert r["human_review_required"] is False
        assert len(r["reasons"]) == 0

    def test_non_supported_status_triggers_review(self):
        r = evaluate_review_triggers(
            status="Contradictory evidence found",
            findings=[self._finding("weather", "contradicts", severity="high")],
            scores_dict=self._scores(),
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["non_supported_status"]["fired"] is True
        assert r["triggers"]["contradictory_evidence"]["fired"] is True

    def test_model_disagreement_triggers_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[self._finding("weather", "supports")],
            scores_dict=self._scores(),
            model_disagreement=True,
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["model_disagreement"]["fired"] is True
        assert any("disagree" in reason.lower() for reason in r["reasons"])

    def test_tool_failure_triggers_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[self._finding("weather", "supports")],
            scores_dict=self._scores(),
            tool_failures=["weather"],
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["tool_failure"]["fired"] is True

    def test_low_eci_triggers_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[self._finding("weather", "supports")],
            scores_dict=self._scores(eci=30.0),
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["low_evidence_consistency"]["fired"] is True

    def test_missing_critical_evidence_triggers_review(self):
        r = evaluate_review_triggers(
            status="Partially supported",
            findings=[self._finding("weather", "missing", weight=2.0)],
            scores_dict=self._scores(),
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["missing_critical_evidence"]["fired"] is True

    def test_ai_failure_triggers_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[],
            scores_dict=self._scores(),
            ai_failures=2,
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["ai_model_failure"]["fired"] is True

    def test_agentic_contradictions_trigger_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[],
            scores_dict=self._scores(),
            contradictions=["Models disagree on photo evidence"],
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["agentic_contradictions"]["fired"] is True

    def test_unresolved_ambiguity_triggers_review(self):
        r = evaluate_review_triggers(
            status="Requires further verification",
            findings=[
                self._finding("weather", "inconclusive"),
                self._finding("crop", "inconclusive"),
                self._finding("timing", "inconclusive"),
            ],
            scores_dict=self._scores(),
        )
        assert r["triggers"]["unresolved_ambiguity"]["fired"] is True

    def test_all_triggers_present_in_output(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[], scores_dict=self._scores(),
        )
        expected_triggers = [
            "non_supported_status", "contradictory_evidence", "missing_critical_evidence",
            "low_evidence_consistency", "low_confidence", "ai_model_failure",
            "model_disagreement", "tool_failure", "agentic_contradictions",
            "unresolved_ambiguity",
        ]
        for t in expected_triggers:
            assert t in r["triggers"], f"Missing trigger: {t}"
            assert "fired" in r["triggers"][t]


# ================================================================ Phase 13 — Evaluation
class TestIntentClassification:
    def test_empty_request_defaults_to_full_verification(self):
        key, label, reason = classify_intent(None)
        assert key == "full_verification"

    def test_contradiction_intent(self):
        key, _, _ = classify_intent("Are there any contradictions in this claim?")
        assert key == "find_contradictions"

    def test_evidence_sufficiency_intent(self):
        key, _, _ = classify_intent("Is there enough evidence to decide?")
        assert key == "check_evidence_sufficiency"

    def test_human_review_intent(self):
        key, _, _ = classify_intent("Why was this claim flagged for review?")
        assert key == "explain_human_review"

    def test_image_comparison_intent(self):
        key, _, _ = classify_intent("Show me visually similar images from ground truth")
        assert key == "compare_image_ground_truth"

    def test_unknown_request_defaults_to_full(self):
        key, _, _ = classify_intent("Tell me about crop health in this region")
        assert key == "full_verification"


class TestPredefinedScenarios:
    def test_scenarios_list_is_not_empty(self):
        scenarios = list_scenarios()
        assert len(scenarios) >= 5

    def test_all_scenarios_have_required_fields(self):
        for s in list_scenarios():
            assert "id" in s
            assert "name" in s
            assert "description" in s

    def test_scenario_ids_are_unique(self):
        ids = [s["id"] for s in list_scenarios()]
        assert len(ids) == len(set(ids))

    def test_predefined_scenarios_reference_valid_demo_indices(self):
        for s in PREDEFINED_SCENARIOS:
            assert isinstance(s.get("demo_claim_index", 0), int)
            assert s["demo_claim_index"] >= 0


class TestBuildPlanForUnseenRequest:
    def test_free_text_produces_plan_with_intent(self):
        s = SharedState("C-1", CLAIM)
        plan = build_plan(s, request_text="Check if the weather supports this drought claim", n_images=1)
        assert "intent" in plan
        assert "tasks" in plan
        assert plan["request_text"] is not None

    def test_unseen_request_routes_models_for_ready_tasks(self):
        s = SharedState("C-1", CLAIM)
        plan = build_plan(s, request_text=None, n_images=1)
        # full_verification should route nova_lite for photo_analysis
        routed = [m.model_key for m in s.selected_models]
        assert "nova_lite" in routed

    def test_plan_records_trace_step(self):
        s = SharedState("C-1", CLAIM)
        build_plan(s, request_text="find contradictions", n_images=0)
        assert any(t.step == "plan" for t in s.audit_trace)
