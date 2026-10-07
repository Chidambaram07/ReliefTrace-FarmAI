import pytest

from backend.agentic.orchestrator import run_agentic_verification
from backend.agentic.router import ModelRouter
from backend.dataset import db
from backend.dataset.builder import build_dataset
from backend.evidence.geo import AdminLayers
from backend.repositories import claims as claims_repo
from backend.services.model_client import ClientSettings, ModelClient
from backend.services.model_registry import build_registry
from backend.services.bedrock_service import BedrockService, BedrockSettings
from backend.storage.schema import init_claims_schema, init_ai_schema, init_verify_schema, init_image_index_schema
from tests.conftest import HEX_A, row
from tests.test_api import jpeg_bytes, make_settings
from tests.test_bedrock_service import FakeClient, client_error, ok_response
from tests.test_verification import CSV_ROW, FakeHttp, make_geo, weather_payload

CLAIM = {"survey_no": "293", "village_lgd": "642626", "claimed_cause": "drought", "incident_date": "2024-11-05",
        "claimed_crop": "Rice (Paddy)", "claimed_stage": "full_growth"}


def nova_obs(damage=True, agrees_nova=True):
    return {"image_usable": True, "quality_issues": [], "observations": ["dry cracked soil", "yellowing leaves"],
           "crop": {"crop_visible": True, "name_guess": "rice", "name_confidence": "high",
                    "stage_guess": "full_growth", "stage_confidence": "medium"},
           "damage_indicators": [{"type": "drought_stress", "visible": damage, "description": "wilting",
                                  "severity": "moderate", "confidence": "medium"}] if damage else
                                [{"type": "none_visible", "visible": False, "description": "", "severity": "none",
                                  "confidence": "high"}],
           "inferences": [], "missing_information": [], "limitations": [],
           "claim_assessment": {"supports": ["visible stress"] if agrees_nova else [],
                                "contradicts": [] if agrees_nova else ["no stress visible"], "cannot_determine": []}}


@pytest.fixture
def rig(tmp_path, make_csv):
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    (imgs / f"642626_293_58__{HEX_A}-1_2_2024_11_06_10_00_00.jpg").write_bytes(jpeg_bytes())
    csv_p = make_csv([row(image_path=HEX_A, **CSV_ROW)])
    s = make_settings(tmp_path)
    conn = db.connect(s.db_path)
    db.load_bundle(conn, build_dataset(csv_p, imgs), str(csv_p))
    init_claims_schema(conn); init_ai_schema(conn); init_verify_schema(conn); init_image_index_schema(conn)
    conn.close()

    def _make(vision_response, review_response=None, *, attach_image=True, geo_dir=None, http=None):
        conn = db.connect(s.db_path)
        c = claims_repo.create_claim(conn, CLAIM)
        if attach_image:
            from backend.repositories import dataset as ds
            d = ds.get_image(conn, HEX_A)
            claims_repo.add_claim_image(conn, c["claim_id"], {"source": "dataset", "dataset_image_id": HEX_A,
                                                              "file_path": d["file_path"]})
        responses = [vision_response] + ([review_response] if review_response else [])
        fake = FakeClient(*responses) if responses else FakeClient(ok_response({}))
        bedrock = BedrockService(BedrockSettings(), client=fake)
        registry = build_registry()
        model_client = ModelClient(ClientSettings(region="ap-south-1"), runtime_client=fake)
        router = ModelRouter(model_client, registry)
        geo = AdminLayers(geo_dir or make_geo(tmp_path))
        return conn, c["claim_id"], bedrock, router, model_client, registry, geo, (http or FakeHttp(weather_payload(dry=True))), s
    return _make


def test_full_agentic_run_wires_vision_independent_review_and_geo(rig):
    conn, cid, bedrock, router, client, registry, geo, http, s = rig(
        ok_response(nova_obs(damage=True, agrees_nova=True)),
        ok_response({"agrees_with_claim": True, "confidence": "medium", "reasoning": "consistent with drought"}))
    result = run_agentic_verification(conn, s, bedrock, router, client, registry, geo, http, cid, run_retrieval=False)
    state, report = result["state"], result["report"]

    assert state["claim_id"] == cid and state["plan"]["intent"] == "full_verification"
    task_agents = {sel["task"] for sel in state["selected_models"]}
    assert {"photo_analysis", "independent_photo_review"} <= task_agents
    evidence_types = {e["evidence_type"] for e in report["evidence"]}
    assert {"ai_image_observation", "independent_model_review", "geo_validation", "weather"} <= evidence_types
    assert report["status"] in ("Supported by available evidence", "Partially supported", "Requires further verification")
    assert report["contradictions"] == []  # both models agree; nothing to surface
    import json
    json.dumps(state)  # fully serializable


def test_independent_review_disagreement_surfaces_even_when_engine_status_is_otherwise_fine(rig):
    conn, cid, bedrock, router, client, registry, geo, http, s = rig(
        ok_response(nova_obs(damage=True, agrees_nova=True)),
        ok_response({"agrees_with_claim": False, "confidence": "high", "reasoning": "insufficient evidence",
                    "disagreement": "described symptoms are ambiguous"}))
    result = run_agentic_verification(conn, s, bedrock, router, client, registry, geo, http, cid, run_retrieval=False)
    report = result["report"]
    assert any("does not support the claim" in c for c in report["contradictions"])
    assert report["routing"]["human_review_required"] is True
    assert any("Agentic layer:" in r for r in report["routing"]["reasons"])


def test_no_image_skips_independent_review_without_crashing(rig):
    conn, cid, bedrock, router, client, registry, geo, http, s = rig(ok_response({}), attach_image=False)
    result = run_agentic_verification(conn, s, bedrock, router, client, registry, geo, http, cid, run_retrieval=False)
    state = result["state"]
    skip_step = next(t for t in state["audit_trace"] if t["task"] == "independent_photo_review")
    assert skip_step["status"] == "skipped" and "no successful vision reading" in skip_step["error"]
    assert not any(sel["task"] == "independent_photo_review" for sel in state["selected_models"])


def test_retrieval_disabled_flag_produces_no_retrieval_evidence(rig):
    conn, cid, bedrock, router, client, registry, geo, http, s = rig(
        ok_response(nova_obs()), ok_response({"agrees_with_claim": True, "reasoning": "ok"}))
    result = run_agentic_verification(conn, s, bedrock, router, client, registry, geo, http, cid,
                                      run_retrieval=False, run_independent=False)
    evidence_types = {e["evidence_type"] for e in result["report"]["evidence"]}
    assert "image_retrieval" not in evidence_types and "independent_model_review" not in evidence_types


def test_empty_image_index_reports_unavailable_retrieval_evidence_not_a_crash(rig):
    conn, cid, bedrock, router, client, registry, geo, http, s = rig(
        ok_response(nova_obs()), ok_response({"agrees_with_claim": True, "reasoning": "ok"}))
    result = run_agentic_verification(conn, s, bedrock, router, client, registry, geo, http, cid, run_retrieval=True)
    retr = next(e for e in result["report"]["evidence"] if e["evidence_type"] == "image_retrieval")
    assert retr["status"] == "unavailable" and "build it first" in retr["observation"]


def test_vision_failure_does_not_break_the_rest_of_the_pipeline(rig):
    conn, cid, bedrock, router, client, registry, geo, http, s = rig(
        client_error("AccessDeniedException", "no entitlement"), attach_image=True)
    result = run_agentic_verification(conn, s, bedrock, router, client, registry, geo, http, cid, run_retrieval=False)
    report, state = result["report"], result["state"]
    assert report is not None
    assert any(e["evidence_type"] == "weather" and e["status"] == "available" for e in report["evidence"])
    img_ev = next(e for e in report["evidence"] if e["evidence_type"] == "ai_image_observation")
    assert img_ev["status"] == "unavailable"
    skip_step = next(t for t in state["audit_trace"] if t["task"] == "independent_photo_review")
    assert skip_step["status"] == "skipped"


def test_uses_the_same_deterministic_engine_as_the_mvp_pipeline(rig):
    """Same evidence-derived status logic: an explicit no-damage reading from Nova Lite that both
    models agree on should be reported as a contradiction by the SAME engine rule as the existing
    MVP flow, not a new/different one."""
    conn, cid, bedrock, router, client, registry, geo, http, s = rig(
        ok_response(nova_obs(damage=False, agrees_nova=False)),
        ok_response({"agrees_with_claim": False, "reasoning": "no damage indicators reported"}))
    result = run_agentic_verification(conn, s, bedrock, router, client, registry, geo, http, cid, run_retrieval=False)
    f = next(f for f in result["report"]["findings"] if f["check_id"] == "claim_vs_image")
    assert f["verdict"] == "contradicts" and f["severity"] == "high"
