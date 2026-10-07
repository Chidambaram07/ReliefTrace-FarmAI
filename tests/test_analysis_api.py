import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.bedrock_service import BedrockService, BedrockSettings
from tests.test_api import CLAIM, jpeg_bytes, make_settings
from tests.test_bedrock_service import GOOD, FakeClient, client_error, ok_response


@pytest.fixture
def make_client(tmp_path):
    def _make(*responses):
        fake = FakeClient(*responses)
        app = create_app(make_settings(tmp_path), bedrock=BedrockService(BedrockSettings(), client=fake))
        return TestClient(app), fake
    return _make


def _claim_with_image(c):
    cid = c.post("/api/claims", json=CLAIM).json()["claim_id"]
    key = c.post(f"/api/claims/{cid}/images", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}).json()["image_key"]
    return cid, key


def test_analyze_stores_result_and_uses_cache(make_client):
    c, fake = make_client(ok_response())
    with c:
        cid, key = _claim_with_image(c)
        r = c.post(f"/api/claims/{cid}/images/{key}/analyze")
        assert r.status_code == 200
        j = r.json()
        assert j["result"]["ok"] and j["result"]["label"].startswith("AI observation")
        assert j["result"]["parsed"]["crop"]["name_guess"] == "rice"
        assert "drought" in fake.calls[0]["messages"][0]["content"][1]["text"]   # claim context reached the prompt
        again = c.post(f"/api/claims/{cid}/images/{key}/analyze").json()
        assert again["result"]["cached"] and len(fake.calls) == 1
        c.post(f"/api/claims/{cid}/images/{key}/analyze?force=true")
        assert len(fake.calls) == 2
        latest = c.get(f"/api/claims/{cid}/images/{key}/analysis").json()
        assert latest["analysis_id"] == again["analysis_id"] + 1


def test_analysis_get_404_before_analyze(make_client):
    c, _ = make_client(ok_response())
    with c:
        cid, key = _claim_with_image(c)
        assert c.get(f"/api/claims/{cid}/images/{key}/analysis").json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


@pytest.mark.parametrize("err,status,code", [
    (client_error("AccessDeniedException", "denied"), 502, "BEDROCK_ACCESS_DENIED"),
    (client_error("ThrottlingException", "slow"), 503, "BEDROCK_THROTTLED"),
])
def test_bedrock_failures_map_to_error_envelope(make_client, err, status, code):
    c, _ = make_client(err)
    with c:
        cid, key = _claim_with_image(c)
        r = c.post(f"/api/claims/{cid}/images/{key}/analyze")
        assert r.status_code == status and r.json()["error"]["code"] == code
        assert "analysis_id" in r.json()["error"]["details"]   # failure is still audit-logged


def test_invalid_model_output_is_502_with_raw_text(make_client):
    c, _ = make_client(ok_response(text="sorry, cannot"))
    with c:
        cid, key = _claim_with_image(c)
        j = c.post(f"/api/claims/{cid}/images/{key}/analyze").json()
        assert j["error"]["code"] == "AI_OUTPUT_INVALID" and j["error"]["details"]["raw_text"] == "sorry, cannot"


def test_analyze_unknown_claim_image_and_missing_file(make_client):
    c, fake = make_client(ok_response())
    with c:
        assert c.post("/api/claims/CLM-NOPE/images/1/analyze").status_code == 404
        cid = c.post("/api/claims", json=CLAIM).json()["claim_id"]
        assert c.post(f"/api/claims/{cid}/images/99/analyze").json()["error"]["code"] == "IMAGE_NOT_FOUND"
        assert fake.calls == []


def test_health_shows_bedrock_config_without_calling_aws(make_client):
    c, fake = make_client(ok_response())
    with c:
        j = c.get("/api/health").json()
        assert j["bedrock"]["region"] == "ap-south-1" and j["bedrock"]["vision_model_id"] == "amazon.nova-lite-v1:0"
        assert fake.calls == []
