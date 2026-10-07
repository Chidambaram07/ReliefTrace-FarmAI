"""Test live Amazon API Gateway HTTP API v2 endpoint for ReliefTrace."""
from __future__ import annotations

import io
import json
import uuid
import httpx
import boto3
from PIL import Image

API_BASE = "https://5ydc54f4c2.execute-api.ap-south-1.amazonaws.com"
REGION = "ap-south-1"
PROFILE = "FAI-TCE-Builder-AI-314240411685"


def create_test_image_bytes() -> bytes:
    """Generate a valid small JPEG test image."""
    img = Image.new("RGB", (120, 120), color=(50, 150, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def run_live_apigw_tests():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    ddb = session.resource("dynamodb", region_name=REGION)
    s3 = session.client("s3", region_name=REGION)
    table = ddb.Table("fai-tce-team56-claims")

    print(f"Testing API Gateway URL: {API_BASE}\n")

    # 1. Health check
    print("1. Testing GET /api/health via HTTPS...")
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{API_BASE}/api/health")
        print(f"Health Status: {r.status_code}")
        print(f"Health Response: {r.text}")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "ok", f"Expected status ok, got {data}"

        # 2. Create Claim
        print("\n2. Testing POST /api/claims via HTTPS...")
        smoke_ref = f"AWS-APIGW-SMOKE-{uuid.uuid4().hex[:6].upper()}"
        claim_payload = {
            "farmer_name": "S. Pandian (API Gateway Smoke)",
            "survey_no": "88/3B",
            "claimed_cause": "flood",
            "claimed_crop": "Paddy",
            "claimed_stage": "Tillering",
            "incident_date": "2026-09-12",
            "claimed_lat": 9.9320,
            "claimed_lon": 78.1250,
            "description": f"Inundated crop field after severe rain ({smoke_ref})",
        }

        r = client.post(f"{API_BASE}/api/claims", json=claim_payload)
        print(f"Claim Creation Status: {r.status_code}")
        print(f"Claim Creation Response: {r.text}")
        assert r.status_code in (200, 201), f"Expected 201, got {r.status_code}: {r.text}"
        claim_data = r.json()
        claim_id = claim_data["claim_id"]
        print(f"Created claim ID: {claim_id}")

        # 3. Get Claim
        print(f"\n3. Testing GET /api/claims/{claim_id} via HTTPS...")
        r = client.get(f"{API_BASE}/api/claims/{claim_id}")
        print(f"Get Claim Status: {r.status_code}")
        assert r.status_code == 200
        assert r.json()["claim_id"] == claim_id

        # 4. Upload Image via Multipart/form-data
        print(f"\n4. Testing POST /api/claims/{claim_id}/images (multipart) via HTTPS...")
        img_bytes = create_test_image_bytes()
        files = {"file": ("flood_photo.jpg", img_bytes, "image/jpeg")}
        r = client.post(f"{API_BASE}/api/claims/{claim_id}/images", files=files)
        print(f"Image Upload Status: {r.status_code}")
        print(f"Image Upload Response: {r.text}")
        assert r.status_code in (200, 201), f"Expected 200/201, got {r.status_code}: {r.text}"
        img_data = r.json()
        image_key = img_data.get("image_key", 1)
        s3_path = img_data.get("file_path", "")
        print(f"Attached image_key: {image_key}, s3_path: {s3_path}")

        # 5. Retrieve Image File via HTTPS
        print(f"\n5. Testing GET /api/claims/{claim_id}/images/{image_key}/file via HTTPS...")
        r = client.get(f"{API_BASE}/api/claims/{claim_id}/images/{image_key}/file")
        print(f"Image Download Status: {r.status_code}")
        print(f"Content-Type: {r.headers.get('content-type')}")
        print(f"Content-Length: {len(r.content)} bytes")
        assert r.status_code == 200
        assert "image/" in r.headers.get("content-type", "")
        assert len(r.content) == len(img_bytes)

        # 6. Test 404 Error Handling
        print("\n6. Testing 404 error handling on nonexistent claim...")
        r = client.get(f"{API_BASE}/api/claims/nonexistent-claim-xyz")
        print(f"404 Test Status: {r.status_code}")
        assert r.status_code == 404
        assert r.json().get("error", {}).get("code") == "CLAIM_NOT_FOUND"

        # 7. Verification pipeline test
        print(f"\n7. Testing POST /api/claims/{claim_id}/verify?narrative=off via HTTPS...")
        r = client.post(f"{API_BASE}/api/claims/{claim_id}/verify?narrative=off&analyze=false")
        print(f"Verify Status: {r.status_code}")
        assert r.status_code == 200
        rep = r.json()
        print(f"Verification Verdict: {rep.get('status')} | Reason: {rep.get('status_reason')}")
        print(f"Evidence Consistency Index (ECI): {rep.get('scores', {}).get('evidence_consistency_index')}")

        # 8. Verify S3 Object & DynamoDB persistence directly
        print(f"\n8. Verifying S3 object and DynamoDB items directly...")
        if s3_path.startswith("s3://"):
            _, _, rel = s3_path[5:].partition("/")
            s3_obj = s3.head_object(Bucket="fai-tce-team56-images", Key=rel)
            assert s3_obj["ContentLength"] == len(img_bytes)
            print(f"S3 Object confirmed: s3://fai-tce-team56-images/{rel} ({s3_obj['ContentLength']} bytes)")

        item = table.get_item(Key={"claim_id": claim_id}).get("Item")
        assert item is not None
        print(f"DynamoDB item confirmed: {item.get('farmer_name')}")

        # 9. Cleanup temporary test items
        print("\n9. Cleaning up temporary smoke test data...")
        table.delete_item(Key={"claim_id": claim_id})
        table.delete_item(Key={"claim_id": f"CLAIM#{claim_id}#IMAGE#{image_key}"})
        table.delete_item(Key={"claim_id": f"CLAIM#{claim_id}#REPORT#1"})
        table.delete_item(Key={"claim_id": f"QUEUE#{claim_id}"})
        if s3_path.startswith("s3://"):
            _, _, rel = s3_path[5:].partition("/")
            s3.delete_object(Bucket="fai-tce-team56-images", Key=rel)
        print("All temporary test data successfully cleaned up from DynamoDB and S3.")

        print("\n=======================================================")
        print("ALL API GATEWAY HTTP API v2 LIVE HTTPS TESTS PASSED 100%!")
        print("=======================================================")


if __name__ == "__main__":
    run_live_apigw_tests()
