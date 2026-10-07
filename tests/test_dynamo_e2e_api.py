"""End-to-End API lifecycle test in AWS Mode (FastAPI + DynamoDB + S3 mocked)."""
import io
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.main import create_app
from backend.services.bedrock_service import BedrockService, BedrockSettings
from backend.services.image_service import S3ImageStorage
from backend.storage.dynamo import DynamoDBContext
from tests.test_bedrock_service import FakeClient, ok_response
from tests.test_dynamo_repositories import MockDynamoTable


def jpeg_bytes(color=(20, 150, 40), size=(60, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


CLAIM_DATA = {
    "farmer_name": "Murugan S",
    "village_lgd": "642626",
    "survey_no": "293",
    "subdivision": "2B",
    "claimed_cause": "drought",
    "claimed_crop": "Rice (Paddy)",
    "claimed_stage": "vegetative",
    "incident_date": "2024-11-06",
    "claimed_lat": 9.25,
    "claimed_lon": 77.42,
    "description": "Drought in survey 293",
}


def test_complete_api_lifecycle_in_aws_mode(tmp_path):
    mock_table = MockDynamoTable()
    mock_s3_storage = {}

    def mock_put_object(**kw):
        mock_s3_storage[kw["Key"]] = kw["Body"]
        return {"ETag": "abc123"}

    def mock_get_object(**kw):
        key = kw["Key"]
        if key not in mock_s3_storage:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        body = MagicMock()
        body.read.return_value = mock_s3_storage[key]
        return {"Body": body}

    def mock_head_object(**kw):
        key = kw["Key"]
        if key not in mock_s3_storage:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(mock_s3_storage[key])}

    mock_s3_client = MagicMock()
    mock_s3_client.put_object.side_effect = mock_put_object
    mock_s3_client.get_object.side_effect = mock_get_object
    mock_s3_client.head_object.side_effect = mock_head_object
    mock_s3_client.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

    settings = Settings(
        csv_path=tmp_path / "x.csv",
        images_dir=tmp_path / "imgs",
        db_path=tmp_path / "t.db",
        upload_dir=tmp_path / "uploads",
        storage_backend="aws",
        dynamodb_table="fai-tce-team56-claims",
        s3_bucket="fai-tce-team56-images",
        aws_region="ap-south-1",
    )

    fake_bedrock = FakeClient(
        ok_response({"crop_detected": "Rice (Paddy)", "damage_visible": True, "damage_cause_consistent": "drought"}),
        ok_response({"agrees_with_claim": True, "confidence": "high", "reasoning": "Consistent with drought conditions"}),
    )
    bedrock = BedrockService(BedrockSettings(), client=fake_bedrock)

    from backend.services import image_service
    orig_get_storage = image_service.get_image_storage

    def patched_get_storage(s=None, s3_client=None):
        return S3ImageStorage(bucket="fai-tce-team56-images", region="ap-south-1", s3_client=mock_s3_client)

    image_service.get_image_storage = patched_get_storage

    from backend import deps
    orig_get_conn = deps.get_conn

    def patched_get_conn(request):
        ctx = DynamoDBContext(settings, table_resource=mock_table)
        try:
            yield ctx
        finally:
            ctx.close()

    deps.get_conn = patched_get_conn

    try:
        app = create_app(settings, bedrock=bedrock)
        app.state.dynamo_table = mock_table
        app.dependency_overrides[deps.get_conn] = patched_get_conn

        with TestClient(app) as client:
            # 1. POST /api/claims
            res = client.post("/api/claims", json=CLAIM_DATA)
            assert res.status_code == 201, res.text
            claim_obj = res.json()
            cid = claim_obj["claim_id"]
            assert cid.startswith("CLM-")
            assert claim_obj["status"] == "submitted"

            # Verify in DynamoDB
            raw_claim = mock_table.get_item({"claim_id": cid})["Item"]
            assert raw_claim["farmer_name"] == "Murugan S"
            assert raw_claim["status"] == "submitted"

            # 2. POST /api/claims/{claim_id}/images
            data = jpeg_bytes()
            img_res = client.post(
                f"/api/claims/{cid}/images",
                files={"file": ("farm_field.jpg", data, "image/jpeg")},
            )
            assert img_res.status_code == 201, img_res.text
            img_meta = img_res.json()
            assert img_meta["image_key"] == 1
            assert img_meta["file_available"] is True

            # Verify S3 object & DynamoDB metadata
            assert len(mock_s3_storage) == 1
            s3_key = list(mock_s3_storage.keys())[0]
            assert s3_key.startswith(f"uploads/{cid}/")

            # 3. GET /api/claims/{claim_id}/images/{image_key}/file
            file_res = client.get(f"/api/claims/{cid}/images/1/file")
            assert file_res.status_code == 200
            assert file_res.content == data

            # 4. POST /api/claims/{claim_id}/verify
            verify_res = client.post(f"/api/claims/{cid}/verify?narrative=template")
            assert verify_res.status_code == 200, verify_res.text
            report = verify_res.json()
            assert report["claim_id"] == cid
            assert "scores" in report
            assert "evidence_consistency_index" in report["scores"]

            # Verify DynamoDB claim status updated to 'reported'
            claim_after_verify = client.get(f"/api/claims/{cid}").json()
            assert claim_after_verify["status"] == "reported"

            # 5. Review queue synchronization check
            q_list = client.get("/api/review-queue?status=open").json()
            # If human review was triggered, verify review queue
            if report["routing"]["human_review_required"]:
                assert any(item["claim_id"] == cid for item in q_list["items"])

                # 6. POST /api/review-queue/{claim_id}/decision
                dec_res = client.post(
                    f"/api/review-queue/{cid}/decision",
                    json={"decision": "approve", "note": "Verified by field officer"},
                )
                assert dec_res.status_code == 200

                # 7. Verify final claim status
                final_claim = client.get(f"/api/claims/{cid}").json()
                assert final_claim["status"] == "approved"

                # 8. Verify report timeline and audit entry
                final_rep = client.get(f"/api/claims/{cid}/report").json()
                assert final_rep["human_decision"]["decision"] == "approve"
                assert any("Human Review Decision: approve" in t.get("label", "") for t in final_rep.get("timeline", []))

    finally:
        image_service.get_image_storage = orig_get_storage
        deps.get_conn = orig_get_conn
