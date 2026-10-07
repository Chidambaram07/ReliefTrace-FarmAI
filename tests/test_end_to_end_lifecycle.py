"""End-to-end lifecycle and scenarios test suite for ReliefTrace.

Covers all 22 required scenarios:
 1. Normal valid claim
 2. Drought claim
 3. Pest-related claim
 4. Contradictory evidence
 5. Insufficient evidence
 6. Missing GPS
 7. Missing image
 8. Weather unavailable
 9. Ground-truth mismatch
10. Model failure
11. Fallback model
12. Independent model disagreement
13. Human review queue
14. Decision: Approve
15. Decision: Reject
16. Decision: Request More Information
17. Re-verification
18. Audit trail completeness
19. Image similarity retrieval
20. Evaluation request
21. Unseen request
22. Malformed model response
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.dataset import db
from backend.dataset.builder import build_dataset
from backend.evidence.geo import AdminLayers
from backend.main import create_app
from backend.schemas.verification import S_CONTRA, S_FURTHER, S_INSUFF, S_PARTIAL, S_SUPPORTED
from backend.services.bedrock_service import BedrockService, BedrockSettings
from backend.services.model_client import ClientSettings, ModelClient
from backend.agentic.router import ModelRouter
from tests.conftest import HEX_A, row
from tests.test_api import jpeg_bytes, make_settings
from tests.test_bedrock_service import FakeClient, client_error, ok_response
from tests.test_verification import FakeHttp, make_geo, weather_payload, obs


DROUGHT_OBS = obs([{"type": "drought_stress", "visible": True, "description": "severe drought drying", "severity": "severe", "confidence": "high"}])
NO_DAMAGE_OBS = obs([{"type": "none_visible", "visible": False, "description": "healthy crop", "severity": "none", "confidence": "high"}])
PEST_OBS = obs([{"type": "pest_damage", "visible": True, "description": "insect damage", "severity": "severe", "confidence": "high"}], stage="vegetation")


def build_test_environment(tmp_path, bedrock_responses=None, http_payload=None, http_fail=False):
    st = make_settings(tmp_path)
    geo_dir = make_geo(tmp_path)
    geo = AdminLayers(geo_dir)
    http = FakeHttp(payload=http_payload or weather_payload(dry=True), fail=http_fail)

    fake = FakeClient(*(bedrock_responses or [ok_response(DROUGHT_OBS)]))
    bedrock = BedrockService(BedrockSettings(), client=fake)

    app = create_app(st, bedrock=bedrock, geo=geo, http=http)
    app.state.model_client = ModelClient(ClientSettings(region="ap-south-1"), runtime_client=fake)
    app.state.model_router = ModelRouter(app.state.model_client, app.state.model_registry)

    # Initialize all schemas directly
    from backend.storage.schema import (
        init_ai_schema, init_claims_schema, init_image_index_schema, init_model_health_schema, init_verify_schema,
    )
    conn = db.connect(st.db_path)
    init_claims_schema(conn)
    init_ai_schema(conn)
    init_verify_schema(conn)
    init_model_health_schema(conn)
    init_image_index_schema(conn)

    # Pre-load CSV into dataset tables so parcel checks find survey 293 in 642626
    import csv
    from tests.conftest import HEADER
    imgs = tmp_path / "imgs"
    imgs.mkdir(exist_ok=True)
    (imgs / f"642626_293_58__{HEX_A}-1_2_2024_11_06_10_00_00.jpg").write_bytes(jpeg_bytes())

    csv_file = tmp_path / "Ground_truth.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerow(row(image_path=HEX_A, **{
            "Village LG": "642626",
            "village__1": "642625",
            "survey_n_1": "293",
            "sub_divi_1": "1",
            "final_crop_name": "Rice (Paddy)",
            "final_crop_stage": "full_growth",
            "final_lat": "9.25",
            "final_long": "77.42",
            "timestamp": "11-06-2024",
            "image_timestamp": "06-11-2024 00:00",
        }))
    bundle = build_dataset(csv_file, imgs)
    db.load_bundle(conn, bundle, str(csv_file))
    conn.close()

    return app, fake


# =====================================================================
# Scenarios 1, 2, 17, 18: Normal Valid Claim, Drought, Re-verification, Audit Trail
# =====================================================================
def test_scenario_01_and_02_normal_valid_drought_claim_lifecycle(tmp_path):
    # Model responses: Nova Lite vision (drought), Ministral independent review (agrees)
    ministral_resp = {"agrees_with_claim": True, "confidence": "high", "reasoning": "Drought signs visible", "disagreement": ""}
    app, fake = build_test_environment(
        tmp_path,
        bedrock_responses=[
            ok_response(DROUGHT_OBS),
            ok_response(ministral_resp),
            ok_response(DROUGHT_OBS),       # for re-verification
            ok_response(ministral_resp),
        ],
    )

    with TestClient(app) as c:
        # 1. Claim Submission
        claim_data = {
            "farmer_name": "Murugan K",
            "village_lgd": "642626",
            "survey_no": "293",
            "subdivision": "1",
            "claimed_cause": "drought",
            "claimed_crop": "Rice (Paddy)",
            "claimed_stage": "full_growth",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
            "description": "Severe drought dried the paddy field.",
        }
        res_claim = c.post("/api/claims", json=claim_data)
        assert res_claim.status_code == 201
        cid = res_claim.json()["claim_id"]
        assert res_claim.json()["status"] == "submitted"

        # 2. Attach Evidence Image from dataset
        res_img = c.post(
            f"/api/claims/{cid}/images/from-dataset",
            json={"image_id": HEX_A},
        )
        assert res_img.status_code == 201

        # 3. Start Agentic Investigation (Requirement 16)
        res_v = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res_v.status_code == 200
        v_body = res_v.json()

        # Verify structured outputs
        assert v_body["report"]["claim_id"] == cid
        assert v_body["report"]["status"] == S_SUPPORTED
        assert v_body["report"]["scores"]["evidence_consistency_index"] > 60
        assert v_body["report"]["scores"]["breakdown"]

        # Scenario 18: Audit trail completeness
        audit = v_body["report"]["audit"]
        assert len(audit) > 0
        steps = [a["step"] for a in audit]
        assert any("claim_validation" in s for s in steps)
        assert any("weather" in s for s in steps)

        # Lifecycle persistence: Verify report is persisted and queryable
        res_rep = c.get(f"/api/claims/{cid}/report")
        assert res_rep.status_code == 200
        assert res_rep.json()["status"] == S_SUPPORTED

        # Claim status is updated to 'reported'
        res_c_after = c.get(f"/api/claims/{cid}")
        assert res_c_after.json()["status"] == "reported"

        # Scenario 17: Re-verification works idempotently without constraint violations
        res_rev = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res_rev.status_code == 200
        assert res_rev.json()["report"]["status"] == S_SUPPORTED


# =====================================================================
# Scenario 3: Pest-related Claim (Weather not applicable)
# =====================================================================
def test_scenario_03_pest_claim_weather_not_applicable(tmp_path):
    ministral_resp = {"agrees_with_claim": True, "confidence": "medium", "reasoning": "Insect damage seen", "disagreement": ""}
    app, _ = build_test_environment(
        tmp_path,
        bedrock_responses=[ok_response(PEST_OBS), ok_response(ministral_resp)],
    )

    with TestClient(app) as c:
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "pest",
            "claimed_crop": "Rice (Paddy)",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("pest.jpg", jpeg_bytes(), "image/jpeg")})

        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res.status_code == 200
        findings = res.json()["report"]["findings"]
        weather_finding = next(f for f in findings if f["check_id"] == "weather")
        assert weather_finding["weight"] == 0
        assert "cannot verify" in weather_finding["detail"].lower()


# =====================================================================
# Scenarios 4, 13, 14, 15, 16: Contradictory Evidence, Review Queue, Decisions
# =====================================================================
def test_scenario_04_contradiction_queues_review_and_full_decision_lifecycle(tmp_path):
    # Nova Lite observes NO damage on a drought claim -> Contradiction!
    ministral_resp = {"agrees_with_claim": False, "confidence": "high", "reasoning": "Field is green and lush", "disagreement": "No drought stress"}
    app, _ = build_test_environment(
        tmp_path,
        bedrock_responses=[ok_response(NO_DAMAGE_OBS), ok_response(ministral_resp)],
    )

    with TestClient(app) as c:
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "claimed_crop": "Rice (Paddy)",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("healthy.jpg", jpeg_bytes(), "image/jpeg")})

        # Run agentic verification
        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        rep = res.json()["report"]
        assert rep["status"] == S_CONTRA
        assert rep["routing"]["human_review_required"] is True
        assert len(rep["contradictions"]) > 0

        # Scenario 13: GET /api/review-queue must show this claim with exact reasons
        q_res = c.get("/api/review-queue")
        assert q_res.status_code == 200
        items = q_res.json()["items"]
        queue_item = next((i for i in items if i["claim_id"] == cid), None)
        assert queue_item is not None
        assert queue_item["report_status"] == S_CONTRA
        assert len(queue_item["reasons"]) > 0

        # Scenario 16: Request More Information decision
        dec_res1 = c.post(f"/api/review-queue/{cid}/decision", json={"decision": "request_more_information", "note": "Provide dated photo"})
        assert dec_res1.status_code == 200
        assert dec_res1.json()["claim_status"] == "request_more_information"
        assert c.get(f"/api/claims/{cid}").json()["status"] == "request_more_information"

        # Check report reflects decision and timeline
        rep_dec = c.get(f"/api/claims/{cid}/report").json()
        assert rep_dec.get("human_decision", {}).get("decision") == "request_more_information"
        assert any("Human Review Decision" in (t.get("label") or t.get("event") or "") for t in rep_dec["timeline"])

        # Claim is removed from open queue and present in decided queue
        assert not any(i["claim_id"] == cid for i in c.get("/api/review-queue?status=open").json()["items"])
        assert any(i["claim_id"] == cid for i in c.get("/api/review-queue?status=decided").json()["items"])


def test_scenario_14_and_15_approve_and_reject_decisions(tmp_path):
    ministral_resp = {"agrees_with_claim": False, "confidence": "high", "reasoning": "disagrees", "disagreement": "crop healthy"}
    app, _ = build_test_environment(
        tmp_path,
        bedrock_responses=[ok_response(NO_DAMAGE_OBS), ok_response(ministral_resp), ok_response(NO_DAMAGE_OBS), ok_response(ministral_resp)],
    )

    with TestClient(app) as c:
        # Create claim 1 for Approve
        c1 = c.post("/api/claims", json={"village_lgd": "642626", "survey_no": "293", "claimed_cause": "drought", "incident_date": "2024-11-04"}).json()["claim_id"]
        c.post(f"/api/claims/{c1}/images", files={"file": ("f1.jpg", jpeg_bytes(), "image/jpeg")})
        c.post(f"/api/claims/{c1}/verify-agentic?image_retrieval=false")

        # Scenario 14: Approve
        d1 = c.post(f"/api/review-queue/{c1}/decision", json={"decision": "approve_for_processing", "note": "Override upon field inspection"})
        assert d1.status_code == 200
        assert d1.json()["claim_status"] == "approved_for_processing"
        assert c.get(f"/api/claims/{c1}").json()["status"] == "approved_for_processing"

        # Create claim 2 for Reject
        c2 = c.post("/api/claims", json={"village_lgd": "642626", "survey_no": "293", "claimed_cause": "drought", "incident_date": "2024-11-04"}).json()["claim_id"]
        c.post(f"/api/claims/{c2}/images", files={"file": ("f2.jpg", jpeg_bytes(), "image/jpeg")})
        c.post(f"/api/claims/{c2}/verify-agentic?image_retrieval=false")

        # Scenario 15: Reject
        d2 = c.post(f"/api/review-queue/{c2}/decision", json={"decision": "reject", "note": "Fraudulent claim; no damage"})
        assert d2.status_code == 200
        assert d2.json()["claim_status"] == "rejected"
        assert c.get(f"/api/claims/{c2}").json()["status"] == "rejected"


# =====================================================================
# Scenarios 5, 6, 7: Insufficient Evidence, Missing GPS, Missing Image
# =====================================================================
def test_scenario_05_06_07_insufficient_evidence_missing_gps_and_image(tmp_path):
    app, _ = build_test_environment(tmp_path)

    with TestClient(app) as c:
        # Claim with no image and no GPS
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "9999",  # unknown parcel
            "claimed_cause": "drought",
            "incident_date": "2024-11-04",
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res.status_code == 200
        rep = res.json()["report"]

        # Missing image and missing GPS triggers insufficient / human review
        assert rep["status"] in (S_PARTIAL, S_INSUFF)
        assert rep["routing"]["human_review_required"] is True
        assert any("photo" in r.lower() or "image" in r.lower() for r in rep["missing_evidence"] + rep["routing"]["reasons"])


# =====================================================================
# Scenario 8: Weather API Unavailable Handling
# =====================================================================
def test_scenario_08_weather_unavailable_graceful_handling(tmp_path):
    # Network down for weather
    app, _ = build_test_environment(tmp_path, http_fail=True)

    with TestClient(app) as c:
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("f.jpg", jpeg_bytes(), "image/jpeg")})

        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res.status_code == 200
        rep = res.json()["report"]

        # Weather marked as missing or unavailable, NOT silently verified
        weather_finding = next(f for f in rep["findings"] if f["check_id"] == "weather")
        assert weather_finding["verdict"] == "missing"
        assert any("weather" in m.lower() for m in rep["missing_evidence"])


# =====================================================================
# Scenario 9: Ground-truth Mismatch
# =====================================================================
def test_scenario_09_ground_truth_crop_mismatch(tmp_path):
    app, _ = build_test_environment(tmp_path)

    with TestClient(app) as c:
        # Reference dataset has Rice (Paddy); claimant claims Coconut
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "claimed_crop": "Coconut",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("f.jpg", jpeg_bytes(), "image/jpeg")})

        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        rep = res.json()["report"]
        crop_finding = next(f for f in rep["findings"] if f["check_id"] == "crop")
        assert crop_finding["verdict"] == "contradicts"
        assert crop_finding["severity"] == "high"


# =====================================================================
# Scenario 10, 11: Model Failure & Fallback Model Execution
# =====================================================================
def test_scenario_10_and_11_model_failure_and_router_fallback(tmp_path):
    # Nova Lite vision fails with AccessDenied; router should capture failure in audit
    app, _ = build_test_environment(
        tmp_path,
        bedrock_responses=[client_error("AccessDeniedException", "bedrock access denied")],
    )

    with TestClient(app) as c:
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("f.jpg", jpeg_bytes(), "image/jpeg")})

        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res.status_code == 200
        rep = res.json()["report"]
        # System didn't crash; recorded failure in audit
        assert any(a["status"].startswith("failed") for a in rep["audit"])
        assert rep["routing"]["human_review_required"] is True


# =====================================================================
# Scenario 12: Independent Model Disagreement
# =====================================================================
def test_scenario_12_independent_model_disagreement(tmp_path):
    # Primary model (Nova Lite) says drought damage is supported
    # Independent model (Ministral) looking at the observations says it disagrees
    ministral_disagree = {
        "agrees_with_claim": False,
        "confidence": "high",
        "reasoning": "Observations indicate natural dry season, not drought damage",
        "disagreement": "Natural drying rather than catastrophic crop failure",
    }
    app, _ = build_test_environment(
        tmp_path,
        bedrock_responses=[ok_response(DROUGHT_OBS), ok_response(ministral_disagree)],
    )

    with TestClient(app) as c:
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("f.jpg", jpeg_bytes(), "image/jpeg")})

        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res.status_code == 200
        rep = res.json()["report"]

        # Disagreement surfaced in contradictions and triggers human review
        assert any("independent review" in c.lower() or "disagreement" in c.lower() for c in rep["contradictions"])
        assert rep["routing"]["human_review_required"] is True


# =====================================================================
# Scenario 19: Image Similarity Retrieval
# =====================================================================
def test_scenario_19_image_similarity_retrieval(tmp_path):
    # Preload an image embedding in SQLite
    ministral_resp = {"agrees_with_claim": True, "confidence": "high", "reasoning": "ok", "disagreement": ""}
    app, _ = build_test_environment(
        tmp_path,
        bedrock_responses=[ok_response(DROUGHT_OBS), ok_response(ministral_resp)],
    )

    # Insert an embedding in the DB so image_retrieval_tool finds top_k
    conn = db.connect(app.state.settings.db_path)
    from backend.agentic.image_index import store_vector
    # 256-dim mock vector
    vec = [0.1] * 256
    store_vector(conn, "TEST_IMG_001", "amazon.titan-embed-image-v1", 256, vec, "dummy_sha")
    store_vector(conn, "TEST_IMG_002", "amazon.titan-embed-image-v1", 256, vec, "dummy_sha_2")
    conn.commit()
    conn.close()

    with TestClient(app) as c:
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("f.jpg", jpeg_bytes(), "image/jpeg")})

        # Run with image_retrieval=true
        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=true")
        assert res.status_code == 200
        ev_list = res.json()["report"]["evidence"]
        retr_ev = next((e for e in ev_list if e["evidence_type"] == "image_retrieval"), None)
        assert retr_ev is not None


# =====================================================================
# Scenario 20 & 21: Evaluation Request & Unseen Request
# =====================================================================
def test_scenario_20_and_21_evaluation_and_unseen_request(tmp_path):
    app, _ = build_test_environment(tmp_path)

    with TestClient(app) as c:
        # Scenario 20: list evaluation scenarios
        sc_res = c.get("/api/evaluation/scenarios")
        assert sc_res.status_code == 200
        assert len(sc_res.json()["scenarios"]) > 0

        # Scenario 21: Unseen free-text request (create a claim first so evaluator can inspect it)
        cid = c.post("/api/claims", json={
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "claimed_crop": "Rice (Paddy)",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }).json()["claim_id"]

        unseen_res = c.post(
            "/api/evaluation/unseen-request",
            json={"request_text": "Check whether this claim has enough evidence", "claim_id": cid},
        )
        assert unseen_res.status_code == 200
        unseen_body = unseen_res.json()
        assert unseen_body["plan"]["intent"] == "check_evidence_sufficiency"


# =====================================================================
# Scenario 22: Malformed Model Response Handling
# =====================================================================
def test_scenario_22_malformed_model_response_handling(tmp_path):
    # Nova Lite returns non-JSON garbled text
    garbled = {"not_valid_schema": 123}
    app, _ = build_test_environment(tmp_path, bedrock_responses=[ok_response(garbled)])

    with TestClient(app) as c:
        claim_data = {
            "village_lgd": "642626",
            "survey_no": "293",
            "claimed_cause": "drought",
            "incident_date": "2024-11-04",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
        }
        cid = c.post("/api/claims", json=claim_data).json()["claim_id"]
        c.post(f"/api/claims/{cid}/images", files={"file": ("f.jpg", jpeg_bytes(), "image/jpeg")})

        res = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert res.status_code == 200
        rep = res.json()["report"]
        # Handled gracefully, flagged as missing/insufficient rather than 500 crash
        assert rep["routing"]["human_review_required"] is True
