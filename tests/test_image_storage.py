"""Comprehensive tests for ImageStorage abstraction: Local, S3 (mocked), and S3 integration."""
import io
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.dataset import db
from backend.dataset.builder import build_dataset
from backend.errors import AppError
from backend.main import create_app
from backend.services.image_service import (
    LocalImageStorage,
    S3ImageStorage,
    get_image_storage,
    inspect_upload,
    is_image_available,
    read_image_bytes,
)
from tests.conftest import HEX_A, HEX_B, UUID_D, row


def jpeg_bytes(color=(10, 120, 20), size=(40, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


CLAIM = {
    "survey_no": "293",
    "village_lgd": "642626",
    "claimed_cause": "drought",
    "incident_date": "2024-11-06",
    "claimed_crop": "Rice (Paddy)",
}


def test_storage_backend_selection(tmp_path):
    s_local = Settings(
        csv_path=tmp_path / "x.csv",
        images_dir=tmp_path / "imgs",
        db_path=tmp_path / "t.db",
        upload_dir=tmp_path / "uploads",
        storage_backend="local",
    )
    st_local = get_image_storage(s_local)
    assert isinstance(st_local, LocalImageStorage)

    s_s3 = Settings(
        csv_path=tmp_path / "x.csv",
        images_dir=tmp_path / "imgs",
        db_path=tmp_path / "t.db",
        upload_dir=tmp_path / "uploads",
        storage_backend="s3",
        s3_bucket="test-bucket",
        aws_region="ap-south-1",
    )
    st_s3 = get_image_storage(s_s3)
    assert isinstance(st_s3, S3ImageStorage)
    assert st_s3.bucket == "test-bucket"


def test_local_storage_lifecycle(tmp_path):
    st = LocalImageStorage(base_dir=tmp_path / "uploads")
    data = jpeg_bytes()
    meta = inspect_upload(data, "photo.jpg", 5 * 1024 * 1024)

    # Store
    uri = st.store("CLM-001", meta, data)
    assert uri.endswith(".jpg")
    assert st.exists(uri) is True

    # Read
    read_data = st.read(uri)
    assert read_data == data

    # Presigned URL (Local returns None)
    assert st.get_presigned_url(uri) is None

    # Delete
    assert st.delete(uri) is True
    assert st.exists(uri) is False

    with pytest.raises(FileNotFoundError):
        st.read(uri)


def test_s3_storage_mocked_lifecycle():
    mock_s3 = MagicMock()
    mock_body = MagicMock()
    data = jpeg_bytes()
    mock_body.read.return_value = data
    mock_s3.get_object.return_value = {"Body": mock_body}
    mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/uploads/CLM-001/abc.jpg?sig=xyz"

    st = S3ImageStorage(bucket="test-bucket", region="ap-south-1", s3_client=mock_s3)
    meta = inspect_upload(data, "test.jpg", 5 * 1024 * 1024)

    # Store (PutObject)
    uri = st.store("CLM-001", meta, data)
    assert uri.startswith("s3://test-bucket/uploads/CLM-001/")
    mock_s3.put_object.assert_called_once()
    call_kw = mock_s3.put_object.call_args.kwargs
    assert call_kw["Bucket"] == "test-bucket"
    assert call_kw["ContentType"] == "image/jpeg"
    assert call_kw["Body"] == data
    assert call_kw["Metadata"]["sha256"] == meta["sha256"]

    # Read (GetObject)
    read_data = st.read(uri)
    assert read_data == data
    mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key=call_kw["Key"])

    # Exists (HeadObject)
    assert st.exists(uri) is True
    mock_s3.head_object.assert_called_once_with(Bucket="test-bucket", Key=call_kw["Key"])

    # Presigned URL
    url = st.get_presigned_url(uri)
    assert url.startswith("https://")
    mock_s3.generate_presigned_url.assert_called_once()

    # Delete (DeleteObject)
    assert st.delete(uri) is True
    mock_s3.delete_object.assert_called_once_with(Bucket="test-bucket", Key=call_kw["Key"])


def test_s3_storage_path_sanitization():
    mock_s3 = MagicMock()
    st = S3ImageStorage(bucket="test-bucket", region="ap-south-1", s3_client=mock_s3)
    meta = {"sha256": "abcdef1234567890abcdef", "ext": ".jpg", "mime": "image/jpeg"}

    # Special characters in claim ID
    uri = st.store("CLM/../001!@#", meta, b"bytes")
    assert ".." not in uri
    assert "CLM001" in uri
    assert uri.startswith("s3://test-bucket/uploads/CLM001/abcdef1234567890.jpg")


def test_s3_storage_upload_failure():
    mock_s3 = MagicMock()
    mock_s3.put_object.side_effect = Exception("S3 Service Unavailable")

    st = S3ImageStorage(bucket="test-bucket", region="ap-south-1", s3_client=mock_s3)
    meta = {"sha256": "abcdef1234567890abcdef", "ext": ".jpg", "mime": "image/jpeg"}

    with pytest.raises(Exception, match="S3 Service Unavailable"):
        st.store("CLM-001", meta, b"test-data")


def test_s3_storage_retrieval_failure():
    mock_s3 = MagicMock()
    mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
    mock_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject",
    )

    st = S3ImageStorage(bucket="test-bucket", region="ap-south-1", s3_client=mock_s3)
    with pytest.raises(FileNotFoundError):
        st.read("s3://test-bucket/uploads/CLM-001/missing.jpg")


def test_s3_mode_api_integration_mocked_s3(tmp_path, make_csv):
    """Integration test verifying POST /api/claims/{claim_id}/images in S3 mode results in S3 object + SQLite metadata."""
    imgs = tmp_path / "imgs"
    imgs.mkdir()
    (imgs / UUID_D).write_bytes(jpeg_bytes())
    csv_p = make_csv([
        row(image_path=f"{HEX_A};{UUID_D}", image_latitude="9.1;9.2", image_longitude="77.1;77.2"),
        row(survey_n_1="9", image_path=HEX_B, final_crop_name="Coconut", final_crop_stage="full_growth"),
    ])

    s = Settings(
        csv_path=tmp_path / "x.csv",
        images_dir=imgs,
        db_path=tmp_path / "t.db",
        upload_dir=tmp_path / "uploads",
        storage_backend="s3",
        s3_bucket="fai-tce-team56-images",
        aws_region="ap-south-1",
    )
    conn = db.connect(s.db_path)
    db.load_bundle(conn, build_dataset(csv_p, imgs), str(csv_p))
    conn.close()

    mock_s3_storage_dict = {}

    def mock_put_object(**kw):
        mock_s3_storage_dict[kw["Key"]] = kw["Body"]
        return {"ETag": "12345"}

    def mock_get_object(**kw):
        key = kw["Key"]
        if key not in mock_s3_storage_dict:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        body = MagicMock()
        body.read.return_value = mock_s3_storage_dict[key]
        return {"Body": body}

    def mock_head_object(**kw):
        key = kw["Key"]
        if key not in mock_s3_storage_dict:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(mock_s3_storage_dict[key])}

    mock_boto3_client = MagicMock()
    mock_boto3_client.put_object.side_effect = mock_put_object
    mock_boto3_client.get_object.side_effect = mock_get_object
    mock_boto3_client.head_object.side_effect = mock_head_object
    mock_boto3_client.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})

    app = create_app(s)
    with TestClient(app) as client:
        # Patch S3ImageStorage client
        from backend.services import image_service
        orig_get_storage = image_service.get_image_storage

        def patched_get_storage(settings=None, s3_client=None):
            return S3ImageStorage(bucket="fai-tce-team56-images", region="ap-south-1", s3_client=mock_boto3_client)

        image_service.get_image_storage = patched_get_storage
        try:
            # 1. Create claim
            claim_resp = client.post("/api/claims", json=CLAIM)
            assert claim_resp.status_code == 201
            cid = claim_resp.json()["claim_id"]

            # 2. Upload image in S3 mode
            img_data = jpeg_bytes(color=(50, 100, 150), size=(80, 80))
            upload_resp = client.post(
                f"/api/claims/{cid}/images",
                files={"file": ("farm.jpg", img_data, "image/jpeg")},
            )
            assert upload_resp.status_code == 201
            img_meta = upload_resp.json()
            assert img_meta["source"] == "upload"
            assert img_meta["file_available"] is True
            assert img_meta["width"] == 80 and img_meta["height"] == 80

            # Verify S3 object exists in mocked S3 storage
            assert len(mock_s3_storage_dict) == 1
            s3_key = list(mock_s3_storage_dict.keys())[0]
            assert s3_key.startswith(f"uploads/{cid}/")
            assert mock_s3_storage_dict[s3_key] == img_data

            # Verify SQLite metadata exists
            conn2 = db.connect(s.db_path)
            row_img = conn2.execute("SELECT * FROM claim_images WHERE claim_id=?", (cid,)).fetchone()
            assert row_img is not None
            assert row_img["file_path"] == f"s3://fai-tce-team56-images/{s3_key}"
            assert row_img["sha256"] == img_meta["sha256"]
            conn2.close()

            # 3. Retrieve image via API
            get_file_resp = client.get(f"/api/claims/{cid}/images/{img_meta['image_key']}/file")
            assert get_file_resp.status_code == 200
            assert get_file_resp.content == img_data
            assert "image/jpeg" in get_file_resp.headers["content-type"]

        finally:
            image_service.get_image_storage = orig_get_storage
