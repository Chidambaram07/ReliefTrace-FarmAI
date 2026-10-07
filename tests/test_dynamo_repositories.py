"""Unit tests for DynamoDB repositories and lifecycle abstraction (mocked DynamoDB)."""
import json
import sqlite3
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.config import Settings
from backend.storage.dynamo import (
    CLAIM_COLS,
    DynamoAICache,
    DynamoAIRepository,
    DynamoClaimsRepository,
    DynamoDBContext,
    DynamoVerificationRepository,
    _from_decimal,
    _to_decimal,
)


class MockDynamoTable:
    """In-memory mock of a boto3 DynamoDB Table supporting get_item, put_item, delete_item, scan."""
    def __init__(self):
        self.items: dict[str, dict] = {}

    def get_item(self, Key: dict) -> dict:
        key_val = Key["claim_id"]
        item = self.items.get(key_val)
        return {"Item": dict(item)} if item else {}

    def put_item(self, Item: dict) -> dict:
        key_val = Item["claim_id"]
        self.items[key_val] = dict(Item)
        return {}

    def delete_item(self, Key: dict) -> dict:
        key_val = Key["claim_id"]
        self.items.pop(key_val, None)
        return {}

    def scan(self, FilterExpression: str = "", ExpressionAttributeValues: dict = None) -> dict:
        out = []
        for item in self.items.values():
            if ExpressionAttributeValues:
                match = True
                for placeholder, val in ExpressionAttributeValues.items():
                    attr_name = placeholder.lstrip(":")
                    if attr_name == "sk" and item.get("SK") != val:
                        match = False
                    elif attr_name == "et" and item.get("entity_type") != val:
                        match = False
                    elif attr_name == "cid" and item.get("parent_claim_id") != val:
                        match = False
                    elif attr_name == "ik" and item.get("image_key") != val:
                        match = False
                if match:
                    out.append(dict(item))
            else:
                out.append(dict(item))
        return {"Items": out}


@pytest.fixture
def mock_table():
    return MockDynamoTable()


@pytest.fixture
def dynamo_claims(mock_table):
    return DynamoClaimsRepository(mock_table)


@pytest.fixture
def dynamo_verify(mock_table):
    return DynamoVerificationRepository(mock_table)


@pytest.fixture
def dynamo_ai(mock_table):
    return DynamoAIRepository(mock_table)


@pytest.fixture
def dynamo_cache(mock_table):
    return DynamoAICache(mock_table)


CLAIM_INPUT = {
    "farmer_name": "Ramesh Kumar",
    "village_lgd": "642626",
    "survey_no": "293",
    "subdivision": "1A",
    "claimed_cause": "drought",
    "claimed_crop": "Rice (Paddy)",
    "claimed_stage": "vegetative",
    "incident_date": "2024-11-06",
    "claimed_lat": 9.25,
    "claimed_lon": 77.42,
    "description": "Severe lack of rain damaged crops.",
}


def test_dynamo_claim_crud(dynamo_claims):
    # 1. Create
    c = dynamo_claims.create_claim(CLAIM_INPUT)
    cid = c["claim_id"]
    assert cid.startswith("CLM-")
    assert c["status"] == "submitted"
    assert c["farmer_name"] == "Ramesh Kumar"
    assert c["claimed_lat"] == 9.25

    # 2. Get
    fetched = dynamo_claims.get_claim(cid)
    assert fetched is not None
    assert fetched["claim_id"] == cid
    assert fetched["survey_no"] == "293"

    # Non-existent
    assert dynamo_claims.get_claim("NON_EXISTENT") is None

    # 3. List
    total, items = dynamo_claims.list_claims(limit=10, offset=0)
    assert total == 1
    assert items[0]["claim_id"] == cid


def test_dynamo_image_metadata_and_duplicates(dynamo_claims):
    c = dynamo_claims.create_claim(CLAIM_INPUT)
    cid = c["claim_id"]

    img1 = {
        "source": "upload",
        "filename": "field1.jpg",
        "file_path": f"s3://fai-tce-team56-images/uploads/{cid}/img1.jpg",
        "sha256": "hash_aaa_111",
        "mime": "image/jpeg",
        "width": 1920,
        "height": 1080,
        "size_bytes": 102400,
        "exif_gps_lat": 9.25,
        "exif_gps_lon": 77.42,
        "exif_captured_at": "2024-11-06T10:00:00",
    }
    k1 = dynamo_claims.add_claim_image(cid, img1)
    assert k1 == 1

    img2 = dict(img1, filename="field2.jpg", sha256="hash_bbb_222")
    k2 = dynamo_claims.add_claim_image(cid, img2)
    assert k2 == 2

    # Duplicate SHA256 prevention
    with pytest.raises(sqlite3.IntegrityError):
        dynamo_claims.add_claim_image(cid, img1)

    # List images
    imgs = dynamo_claims.list_claim_images(cid)
    assert len(imgs) == 2
    assert imgs[0]["image_key"] == 1
    assert imgs[1]["image_key"] == 2

    # Get single image
    single = dynamo_claims.get_claim_image(cid, 1)
    assert single["sha256"] == "hash_aaa_111"
    assert dynamo_claims.get_claim_image(cid, 999) is None


def test_dynamo_verification_report_and_eci(dynamo_claims, dynamo_verify):
    c = dynamo_claims.create_claim(CLAIM_INPUT)
    cid = c["claim_id"]

    report_payload = {
        "claim_id": cid,
        "status": "auto_approved",
        "status_reason": "Evidence consistent with claim",
        "scores": {
            "evidence_consistency_index": 0.88,
            "confidence_index": 0.92,
        },
        "routing": {
            "human_review_required": False,
            "reasons": [],
        },
        "findings": [],
        "timeline": [],
        "audit": [],
    }

    rep_id = dynamo_verify.save_report(cid, report_payload)
    assert rep_id == 1

    # Check updated claim status
    updated_c = dynamo_claims.get_claim(cid)
    assert updated_c["status"] == "reported"

    # Latest report
    latest = dynamo_verify.latest_report(cid)
    assert latest is not None
    assert latest["report_id"] == 1
    assert latest["report"]["scores"]["evidence_consistency_index"] == 0.88
    assert latest["report"]["scores"]["confidence_index"] == 0.92


def test_dynamo_review_queue_and_human_decision(dynamo_claims, dynamo_verify):
    c = dynamo_claims.create_claim(CLAIM_INPUT)
    cid = c["claim_id"]

    # 1. Sync review queue with human_review_required = True
    q_res = dynamo_verify.sync_queue(cid, True, ["GPS location outside boundary", "Crop stage mismatch"])
    assert q_res == "open"

    # 2. List review queue
    open_items = dynamo_verify.list_queue(status="open")
    assert len(open_items) == 1
    assert open_items[0]["claim_id"] == cid
    assert len(open_items[0]["reasons"]) == 2

    # 3. Save report
    rep = {
        "status": "needs_human_review",
        "scores": {"confidence_index": 0.45, "evidence_consistency_index": 0.30},
        "routing": {"human_review_required": True, "reasons": ["GPS location outside boundary"]},
        "timeline": [],
        "audit": [],
    }
    dynamo_verify.save_report(cid, rep)

    # 4. Human Decision: approve_for_processing
    ok = dynamo_verify.decide(cid, "approve_for_processing", "Inspected by district officer on-site.")
    assert ok is True

    # 5. Verify queue status updated to decided
    open_after = dynamo_verify.list_queue(status="open")
    assert len(open_after) == 0

    decided_items = dynamo_verify.list_queue(status="decided")
    assert len(decided_items) == 1
    assert decided_items[0]["decision"] == "approve_for_processing"
    assert decided_items[0]["note"] == "Inspected by district officer on-site."

    # 6. Verify claim status updated
    final_claim = dynamo_claims.get_claim(cid)
    assert final_claim["status"] == "approved_for_processing"

    # 7. Verify audit entry in latest report
    latest_rep = dynamo_verify.latest_report(cid)
    assert latest_rep["report"]["human_decision"]["decision"] == "approve_for_processing"
    assert any(a["step"] == "human_review_decision" for a in latest_rep["report"]["audit"])


def test_dynamo_ai_repo_and_cache(dynamo_ai, dynamo_cache):
    # Analysis log
    aid = dynamo_ai.add_analysis("CLM-TEST", 1, {"ok": True, "model_id": "nova-lite", "result": {"crop": "Paddy"}})
    assert aid > 0
    latest = dynamo_ai.latest_analysis("CLM-TEST", 1)
    assert latest is not None
    assert latest["ok"] is True
    assert latest["model_id"] == "nova-lite"

    # AI Cache
    dynamo_cache.put("cache_key_xyz", {"observation": "healthy crop"})
    cached_val = dynamo_cache.get("cache_key_xyz")
    assert cached_val == {"observation": "healthy crop"}
    assert dynamo_cache.get("missing_key") is None


def test_dynamodb_context_factory(mock_table):
    s = Settings(
        csv_path="/tmp/x.csv",
        images_dir="/tmp/imgs",
        db_path="/tmp/t.db",
        upload_dir="/tmp/uploads",
        storage_backend="aws",
        dynamodb_table="fai-tce-team56-claims",
        s3_bucket="fai-tce-team56-images",
        aws_region="ap-south-1",
    )
    ctx = DynamoDBContext(s, table_resource=mock_table)
    assert ctx.is_dynamo is True
    assert isinstance(ctx.claims, DynamoClaimsRepository)
    assert isinstance(ctx.verification, DynamoVerificationRepository)
    assert isinstance(ctx.ai, DynamoAIRepository)
    assert isinstance(ctx.ai_cache, DynamoAICache)
