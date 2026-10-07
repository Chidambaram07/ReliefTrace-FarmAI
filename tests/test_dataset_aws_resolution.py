"""Tests for dataset ID lookup, S3/local reference resolution, and AWS/Lambda mode."""
from __future__ import annotations

import io
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from backend.config import ROOT, Settings
from backend.dataset import db
from backend.repositories import dataset as ds_repo
from backend.services import image_service


def test_dataset_id_lookup_existing():
    conn = db.connect(ROOT / "data" / "processed" / "reliefTrace.db")
    try:
        assert ds_repo.dataset_loaded(conn) is True
        img = ds_repo.get_image(conn, "2fec8fab4a7055ce-43514-14060200521558")
        assert img is not None
        assert img["image_id"] == "2fec8fab4a7055ce-43514-14060200521558"
        assert img["village_lgd"] == "642627"
        assert img["crop_name"] == "Rice (Paddy)"
        assert img["crop_stage"] == "full_growth"
        assert img["file_status"] == "found"
        assert img["image_date"] == "2024-11-12"
        assert img["file_captured_at"] == "2024-11-12T15:37:44"
    finally:
        conn.close()


def test_dataset_id_lookup_missing():
    conn = db.connect(ROOT / "data" / "processed" / "reliefTrace.db")
    try:
        img = ds_repo.get_image(conn, "non-existent-id-000000000000")
        assert img is None
    finally:
        conn.close()


def test_dataset_metadata_retrieval():
    conn = db.connect(ROOT / "data" / "processed" / "reliefTrace.db")
    try:
        links = ds_repo.linked_records(conn, "2fec8fab4a7055ce-43514-14060200521558")
        assert len(links) >= 1
        r = links[0]
        assert r["survey_no"] == "371"
        assert r["subdivision"] == "3B"
        assert r["village_lgd"] == "642627"
        assert r["crop_name"] == "Rice (Paddy)"
        assert r["gt_date"] == "2024-11-12"

        total, parcels = ds_repo.find_parcels(conn, village_lgd="642627", survey_no="371", subdivision="3B")
        assert total >= 1
        assert parcels[0]["record_id"] == "R09611"
    finally:
        conn.close()


def test_dataset_image_reference_resolution_local():
    conn = db.connect(ROOT / "data" / "processed" / "reliefTrace.db")
    try:
        img = ds_repo.get_image(conn, "2fec8fab4a7055ce-43514-14060200521558")
        assert img is not None
        assert img["file_available"] is True
        assert Path(img["file_path"]).exists()
    finally:
        conn.close()


def test_dataset_image_reference_resolution_aws_mode(monkeypatch):
    # Simulate environment where local image file does not exist (like Lambda container)
    settings = Settings(
        csv_path=Path("/tmp/fake.csv"),
        images_dir=Path("/tmp/empty_images"),
        db_path=ROOT / "data" / "processed" / "reliefTrace.db",
        upload_dir=Path("/tmp/uploads"),
        storage_backend="aws",
        s3_bucket="fai-tce-team56-images",
        s3_dataset_prefix="dataset/",
        dynamodb_table="fai-tce-team56-claims",
        aws_region="ap-south-1",
    )

    class FakeDynamoContext:
        is_dynamo = True
        def __init__(self, s):
            self.settings = s

    ctx = FakeDynamoContext(settings)
    
    # Mock os.path.exists to return False for image files, but True for the sqlite DB
    orig_exists = os.path.exists
    def fake_exists(p):
        if str(p).endswith(".db"):
            return orig_exists(p)
        return False

    monkeypatch.setattr(os.path, "exists", fake_exists)

    img = ds_repo.get_image(ctx, "2fec8fab4a7055ce-43514-14060200521558")
    assert img is not None
    assert img["file_available"] is True
    assert img["file_path"].startswith("s3://fai-tce-team56-images/dataset/images/")
    assert "2fec8fab4a7055ce-43514-14060200521558" in img["file_path"]


def test_ensure_dataset_db_downloads_from_s3(tmp_path, monkeypatch):
    target_db = tmp_path / "test_downloaded.db"
    settings = Settings(
        csv_path=Path("/tmp/fake.csv"),
        images_dir=Path("/tmp/empty_images"),
        db_path=target_db,
        upload_dir=Path("/tmp/uploads"),
        storage_backend="aws",
        s3_bucket="fai-tce-team56-images",
        s3_dataset_prefix="dataset/",
        dynamodb_table="fai-tce-team56-claims",
        aws_region="ap-south-1",
    )

    mock_s3 = MagicMock()
    def fake_download_file(bucket, key, target):
        Path(target).write_bytes(b"SQLite format 3\x00fake_data_for_test")
    mock_s3.download_file.side_effect = fake_download_file

    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    monkeypatch.setattr("boto3.client", mock_boto3.client)

    result_path = ds_repo.ensure_dataset_db(settings)
    assert result_path == target_db
    assert target_db.exists()
    assert target_db.read_bytes().startswith(b"SQLite format 3")


def test_no_aws_credentials_exposed():
    # Check that .env and python code do not hardcode AWS secrets
    env_file = ROOT / ".env"
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        assert "aws_secret_access_key" not in content.lower()
        assert "aws_access_key_id" not in content.lower()
        assert "akia" not in content.lower()

    # Search in backend/*.py for hardcoded keys
    for py_file in (ROOT / "backend").rglob("*.py"):
        code = py_file.read_text(encoding="utf-8", errors="ignore")
        assert "aws_secret_access_key" not in code.lower()
        assert "AKIA" not in code


def test_api_attach_dataset_image_in_aws_mode(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.services.bedrock_service import BedrockService, BedrockSettings
    from backend.services.image_service import S3ImageStorage
    from backend.storage.dynamo import DynamoDBContext
    from tests.test_dynamo_repositories import MockDynamoTable
    from tests.test_bedrock_service import FakeClient, ok_response

    mock_table = MockDynamoTable()
    settings = Settings(
        csv_path=ROOT / "data" / "raw" / "Ground_truth_Points.csv",
        images_dir=ROOT / "data" / "images",
        db_path=ROOT / "data" / "processed" / "reliefTrace.db",
        upload_dir=ROOT / "data" / "uploads",
        storage_backend="aws",
        s3_bucket="fai-tce-team56-images",
        s3_dataset_prefix="dataset/",
        dynamodb_table="fai-tce-team56-claims",
        aws_region="ap-south-1",
    )

    # Provide sample image bytes when S3 read is called
    target_img_bytes = (ROOT / "data" / "images" / "642627_371___2fec8fab4a7055ce-43514-14060200521558-5596_318379_2024_11_12_15_37_44.jpg").read_bytes()
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": io.BytesIO(target_img_bytes)}
    mock_s3.head_object.return_value = {"ContentLength": len(target_img_bytes)}

    def fake_get_storage(s=None, s3_client=None):
        return S3ImageStorage(bucket="fai-tce-team56-images", region="ap-south-1", s3_client=mock_s3)

    monkeypatch.setattr(image_service, "get_image_storage", fake_get_storage)

    from backend import deps
    def fake_get_conn():
        ctx = DynamoDBContext(settings, table_resource=mock_table)
        try:
            yield ctx
        finally:
            ctx.close()

    app = create_app(settings=settings)
    app.dependency_overrides[deps.get_conn] = fake_get_conn

    client = TestClient(app)

    # 1. Create a claim
    res = client.post("/api/claims", json={
        "farmer_name": "Test Farmer",
        "village_lgd": "642627",
        "survey_no": "371",
        "subdivision": "3B",
        "claimed_cause": "flood",
        "incident_date": "2024-11-14",
        "claimed_crop": "Rice (Paddy)",
        "description": "Field flooded.",
    })
    assert res.status_code == 201, res.text
    claim_id = res.json()["claim_id"]

    # 2. Attach existing dataset image
    res_attach = client.post(f"/api/claims/{claim_id}/images/from-dataset", json={
        "image_id": "2fec8fab4a7055ce-43514-14060200521558"
    })
    assert res_attach.status_code == 201
    img_data = res_attach.json()
    assert img_data["source"] == "dataset"
    assert img_data["dataset_image_id"] == "2fec8fab4a7055ce-43514-14060200521558"
    assert img_data["file_available"] is True
    assert img_data["sha256"] is not None

    # Check stored DynamoDB item contains S3 path
    stored_img = mock_table.get_item(Key={"claim_id": f"CLAIM#{claim_id}#IMAGE#1"})["Item"]
    assert stored_img["file_path"].startswith("s3://fai-tce-team56-images/dataset/images/")

    # 3. Attach missing dataset image -> 404
    res_missing = client.post(f"/api/claims/{claim_id}/images/from-dataset", json={
        "image_id": "unknown-nonexistent-id-99999"
    })
    assert res_missing.status_code == 404
    assert res_missing.json()["error"]["code"] == "IMAGE_NOT_FOUND"


def test_clean_filename_windows_and_posix():
    from backend.repositories.dataset import _clean_filename, _image_row

    assert _clean_filename(r"E:\Downloads\foo\bar\image.jpg") == "image.jpg"
    assert _clean_filename("/var/task/data/images/image.jpg") == "image.jpg"
    assert _clean_filename("image.jpg") == "image.jpg"
    assert _clean_filename(None) is None

    dummy_row = {
        "crop_stage_values": "[]",
        "classification_values": "[]",
        "flags": "[]",
        "coords": "[]",
        "file_path": r"E:\Downloads\reliefTrace\data\images\642627_371___test.jpg",
        "file_status": "found",
    }

    class FakeSettings:
        storage_backend = "aws"
        s3_bucket = "test-bucket"
        s3_dataset_prefix = "dataset/"

    out = _image_row(dummy_row, FakeSettings())
    assert out["file_path"] == "s3://test-bucket/dataset/images/642627_371___test.jpg"
    assert "\\" not in out["file_path"]

