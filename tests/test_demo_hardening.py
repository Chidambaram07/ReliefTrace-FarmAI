"""Phase 15: Demo hardening tests — comprehensive end-to-end validation.

These tests verify the complete system behavior across all the scenarios listed in the requirements:
normal investigation, contradictory evidence, missing evidence, low confidence, model failure,
tool failure, malformed model output, fallback/recovery, human review trigger, predefined
evaluation, unseen request, audit trace, and ECI.
"""
import json

import pytest

from backend.agentic.state import SharedState, ModelOutput, ToolResult
from backend.agentic.planner import build_plan, classify_intent
from backend.agentic.review_triggers import evaluate_review_triggers
from backend.agentic.evaluator import list_scenarios, PREDEFINED_SCENARIOS
from backend.verification.engine import evidence_consistency_breakdown, verify, TITLES
from backend.verification.planner import plan_verification
from backend.schemas.verification import Finding, Scores
from backend.evidence.models import EvidenceItem


CLAIM = {"claimed_cause": "drought", "claimed_crop": "Rice (Paddy)", "incident_date": "2024-11-04",
         "survey_no": "293", "village_lgd": "642626"}


def _ev(eid, etype="weather", quality="medium", status="available", **data):
    return EvidenceItem(evidence_id=eid, source="test", source_kind="external_evidence",
                        evidence_type=etype, observation="test obs", quality=quality,
                        status=status, data=data)


def _finding(cid, verdict, weight=2.0, severity=None, evidence_ids=(), detail="test"):
    return Finding(check_id=cid, title=TITLES.get(cid, cid), verdict=verdict, severity=severity,
                   detail=detail, evidence_ids=list(evidence_ids), weight=weight,
                   independent=True, rule="r")


# ============================== 1. Normal investigation trace
class TestNormalInvestigation:
    def test_state_produces_valid_audit_report(self):
        s = SharedState("C-1", CLAIM)
        s.set_plan({"intent": "full_verification", "tasks": []})
        s.route("photo_analysis", "nova_lite", "primary vision model")
        s.record_model_output(ModelOutput(
            task="photo_analysis", model_key="nova_lite", model_id="amazon.nova-lite-v1:0",
            ok=True, output_summary="image analyzed", input_tokens=100, output_tokens=50, latency_ms=200))
        s.record_tool_result(ToolResult(tool="weather", input_summary={"lat": 9.25},
                                         output={"rainfall_mm_30d": 10}, status="success", latency_ms=300))
        s.set_verification_result({"status": "Supported"})
        s.set_review_status("not_required")
        s.complete(total_latency_ms=500)
        ar = s.to_audit_report()
        assert ar["investigation_id"].startswith("INV-")
        assert ar["completed_at"] is not None
        assert len(ar["models_invoked"]) == 1
        assert len(ar["tools_invoked"]) == 1
        assert ar["token_usage"]["total_input_tokens"] == 100

    def test_state_serializable_to_json(self):
        s = SharedState("C-1", CLAIM)
        s.route("test", "nova_lite", "reason")
        s.complete()
        json.dumps(s.to_dict())  # must not raise
        json.dumps(s.to_audit_report())  # must not raise


# ============================== 2. Contradictory evidence
class TestContradictoryEvidence:
    def test_contradiction_triggers_human_review(self):
        r = evaluate_review_triggers(
            status="Contradictory evidence found",
            findings=[_finding("weather", "contradicts", severity="high").model_dump()],
            scores_dict={"evidence_consistency_index": 0, "confidence_index": 0, "coverage": 0.8, "agreement": 0},
        )
        assert r["human_review_required"] is True
        assert r["triggers"]["contradictory_evidence"]["fired"]

    def test_contradiction_earns_zero_eci(self):
        findings = [_finding("weather", "contradicts", weight=2, severity="high", evidence_ids=["e1"])]
        ev = [_ev("e1", quality="high")]
        _, total = evidence_consistency_breakdown(findings, ev, 2)
        assert total == 0.0


# ============================== 3. Missing evidence
class TestMissingEvidence:
    def test_missing_critical_triggers_review(self):
        r = evaluate_review_triggers(
            status="Partially supported",
            findings=[_finding("weather", "missing", weight=2.0).model_dump()],
            scores_dict={"evidence_consistency_index": 30, "confidence_index": 30, "coverage": 0.3, "agreement": 1.0},
        )
        assert r["triggers"]["missing_critical_evidence"]["fired"]


# ============================== 4. Low-confidence result
class TestLowConfidence:
    def test_low_eci_triggers_review_for_supported_status(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[_finding("weather", "supports").model_dump()],
            scores_dict={"evidence_consistency_index": 25, "confidence_index": 25, "coverage": 0.5, "agreement": 0.5},
        )
        assert r["triggers"]["low_evidence_consistency"]["fired"]

    def test_low_eci_does_not_trigger_for_non_supported(self):
        r = evaluate_review_triggers(
            status="Contradictory evidence found",
            findings=[_finding("weather", "contradicts", severity="high").model_dump()],
            scores_dict={"evidence_consistency_index": 25, "confidence_index": 25, "coverage": 0.5, "agreement": 0.5},
        )
        assert not r["triggers"]["low_evidence_consistency"]["fired"]


# ============================== 5. Model failure
class TestModelFailure:
    def test_ai_failure_triggers_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[], scores_dict={"evidence_consistency_index": 70, "confidence_index": 70, "coverage": 0.8, "agreement": 0.9},
            ai_failures=1,
        )
        assert r["triggers"]["ai_model_failure"]["fired"]


# ============================== 6. Tool failure
class TestToolFailure:
    def test_tool_failure_triggers_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[], scores_dict={"evidence_consistency_index": 70, "confidence_index": 70, "coverage": 0.8, "agreement": 0.9},
            tool_failures=["weather"],
        )
        assert r["triggers"]["tool_failure"]["fired"]
        assert any("weather" in reason for reason in r["reasons"])


# ============================== 7. Malformed model output
class TestMalformedModelOutput:
    def test_state_records_failed_model_output(self):
        s = SharedState("C-1", CLAIM)
        s.record_model_output(ModelOutput(
            task="photo_analysis", model_key="nova_lite", model_id="test",
            ok=False, output_summary="", error="AI_OUTPUT_INVALID: garbage response"))
        assert s.model_outputs[0].ok is False
        assert "AI_OUTPUT_INVALID" in s.model_outputs[0].error
        trace = [t for t in s.audit_trace if t.step == "model:photo_analysis"]
        assert trace[0].status == "failed"


# ============================== 8. Fallback/recovery
class TestFallbackRecovery:
    def test_fallback_is_visible_in_trace(self):
        s = SharedState("C-1", CLAIM)
        s.route("photo_analysis", "nova_lite", "primary", fallback_of=None)
        s.route("photo_analysis", "ministral_8b", "fallback", fallback_of="nova_lite")
        assert s.selected_models[-1].fallback_of == "nova_lite"
        fallback_trace = [t for t in s.audit_trace if t.fallback_of == "nova_lite"]
        assert len(fallback_trace) == 1
        assert fallback_trace[0].status == "fallback"


# ============================== 9. Human review trigger
class TestHumanReviewTrigger:
    def test_model_disagreement_triggers_review(self):
        r = evaluate_review_triggers(
            status="Supported by available evidence",
            findings=[_finding("weather", "supports").model_dump()],
            scores_dict={"evidence_consistency_index": 70, "confidence_index": 70, "coverage": 0.8, "agreement": 0.9},
            model_disagreement=True,
        )
        assert r["human_review_required"]
        assert r["triggers"]["model_disagreement"]["fired"]

    def test_unresolved_ambiguity_triggers_review(self):
        r = evaluate_review_triggers(
            status="Requires further verification",
            findings=[
                _finding("weather", "inconclusive").model_dump(),
                _finding("crop", "inconclusive").model_dump(),
                _finding("timing", "inconclusive").model_dump(),
            ],
            scores_dict={"evidence_consistency_index": 40, "confidence_index": 40, "coverage": 0.8, "agreement": 0.3},
        )
        assert r["triggers"]["unresolved_ambiguity"]["fired"]


# ============================== 10. Predefined evaluation scenarios
class TestPredefinedEvaluation:
    def test_scenarios_exist(self):
        assert len(list_scenarios()) >= 5

    def test_scenario_ids_unique(self):
        ids = [s["id"] for s in list_scenarios()]
        assert len(ids) == len(set(ids))

    def test_all_scenarios_have_valid_demo_indices(self):
        for s in PREDEFINED_SCENARIOS:
            assert s["demo_claim_index"] >= 0
            assert s["demo_claim_index"] < 4  # we have 4 demo claims


# ============================== 11. Unseen natural-language request
class TestUnseenRequest:
    def test_classify_various_intents(self):
        assert classify_intent("Why was this flagged for review?")[0] == "explain_human_review"
        assert classify_intent("Are there contradictions?")[0] == "find_contradictions"
        assert classify_intent("Is there enough evidence?")[0] == "check_evidence_sufficiency"
        assert classify_intent("Compare this image to ground truth")[0] == "compare_image_ground_truth"
        assert classify_intent("Tell me about this farm")[0] == "full_verification"
        assert classify_intent(None)[0] == "full_verification"
        assert classify_intent("")[0] == "full_verification"

    def test_build_plan_produces_tasks(self):
        s = SharedState("C-1", CLAIM)
        plan = build_plan(s, request_text="find contradictions", n_images=0)
        assert plan["intent"] == "find_contradictions"
        assert len(plan["tasks"]) > 0

    def test_build_plan_full_verification_with_images(self):
        s = SharedState("C-1", CLAIM)
        plan = build_plan(s, request_text=None, n_images=2)
        assert plan["intent"] == "full_verification"
        has_photo = any(t["task"] == "photo_analysis" for t in plan["tasks"])
        assert has_photo


# ============================== 12. Audit trace
class TestAuditTrace:
    def test_trace_step_fields_are_complete(self):
        s = SharedState("C-1", CLAIM)
        s.route("test", "nova_lite", "reason")
        t = s.audit_trace[-1]
        assert t.step == "route:test"
        assert t.agent == "router"
        assert t.model == "nova_lite"
        assert t.routing_reason == "reason"
        assert t.timestamp is not None

    def test_audit_report_steps_match_trace(self):
        s = SharedState("C-1", CLAIM)
        s.route("t1", "nova_lite", "r1")
        s.route("t2", "ministral_8b", "r2")
        s.complete()
        ar = s.to_audit_report()
        assert len(ar["steps"]) == len(s.audit_trace)


# ============================== 13. Evidence Consistency Index
class TestECIHardening:
    def test_eci_breakdown_sums_to_total(self):
        findings = [
            _finding("weather", "supports", 2, evidence_ids=["e1"]),
            _finding("location", "supports", 2, evidence_ids=["e2"]),
            _finding("crop", "inconclusive", 2, evidence_ids=["e3"]),
            _finding("claim_vs_image", "contradicts", 3, severity="high", evidence_ids=["e4"]),
            _finding("stage", "missing", 1),
        ]
        ev = [_ev("e1", quality="medium"), _ev("e2", quality="high"),
              _ev("e3", quality="medium"), _ev("e4", quality="high")]
        W = sum(f.weight for f in findings)
        rows, total = evidence_consistency_breakdown(findings, ev, W)
        assert total == pytest.approx(round(sum(r["awarded_points"] for r in rows), 1))
        assert 0 <= total <= 100

    def test_all_supported_high_quality_gives_100(self):
        findings = [_finding("weather", "supports", 2, evidence_ids=["e1"])]
        ev = [_ev("e1", quality="high")]
        _, total = evidence_consistency_breakdown(findings, ev, 2)
        assert total == pytest.approx(100.0)

    def test_titles_are_verdict_neutral(self):
        banned = ("consistent", "found in", "visible in")
        for title in TITLES.values():
            assert not any(b in title.lower() for b in banned), f"Title bakes in outcome: {title}"
