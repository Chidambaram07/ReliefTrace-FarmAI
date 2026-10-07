from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services.bedrock_service import BedrockService, BedrockSettings
from tests.test_api import CLAIM as SIMPLE_CLAIM
from tests.test_api import jpeg_bytes, make_settings
from tests.test_bedrock_service import FakeClient, ok_response
from tests.test_agentic_orchestrator import nova_obs


def test_verify_agentic_endpoint_end_to_end(tmp_path):
    fake = FakeClient(ok_response(nova_obs(damage=True, agrees_nova=True)),
                      ok_response({"agrees_with_claim": True, "confidence": "medium", "reasoning": "consistent"}))
    bedrock = BedrockService(BedrockSettings(), client=fake)
    app = create_app(make_settings(tmp_path), bedrock=bedrock, model_client=None)
    # inject the SAME fake runtime the router/model_client will use, without a second BedrockService
    from backend.services.model_client import ClientSettings, ModelClient
    app.state.model_client = ModelClient(ClientSettings(region="ap-south-1"), runtime_client=fake)
    from backend.agentic.router import ModelRouter
    app.state.model_router = ModelRouter(app.state.model_client, app.state.model_registry)

    with TestClient(app) as c:
        cid = c.post("/api/claims", json=SIMPLE_CLAIM).json()["claim_id"]
        key = c.post(f"/api/claims/{cid}/images",
                     files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}).json()["image_key"]
        r = c.post(f"/api/claims/{cid}/verify-agentic?image_retrieval=false")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["report"]["claim_id"] == cid and body["state"]["claim_id"] == cid
        assert body["state"]["plan"]["intent"] == "full_verification"
        # Lifecycle integration: report is persisted, claim status updated, retrievable via GET /report
        rep = c.get(f"/api/claims/{cid}/report")
        assert rep.status_code == 200
        rep_json = rep.json()
        assert rep_json["claim_id"] == cid
        assert rep_json["status"] == body["report"]["status"]
        assert c.get(f"/api/claims/{cid}").json()["status"] == "reported"
