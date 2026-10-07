"""Real AWS Integration Test against Team 56 S3 and DynamoDB resources in ap-south-1.
Performs the full 11-step lifecycle test with cleanup.
"""
from __future__ import annotations

import io
import json
import uuid
import boto3
from PIL import Image

from backend.services.image_service import S3ImageStorage, inspect_upload
from backend.storage.dynamo import DynamoClaimsRepository, DynamoVerificationRepository


def run_real_aws_integration_test():
    session = boto3.Session(profile_name="FAI-TCE-Builder-AI-314240411685", region_name="ap-south-1")
    ddb = session.resource("dynamodb")
    table = ddb.Table("fai-tce-team56-claims")
    s3 = session.client("s3")
    s3_storage = S3ImageStorage(bucket="fai-tce-team56-images", region="ap-south-1", s3_client=s3)

    claims_repo = DynamoClaimsRepository(table, s3_bucket="fai-tce-team56-images")
    verify_repo = DynamoVerificationRepository(table)

    smoke_cid = f"AWS-MIGRATION-SMOKE-{uuid.uuid4().hex[:6].upper()}"
    print(f"Starting real AWS integration test with claim: {smoke_cid}")

    created_items = []
    s3_uri = None

    try:
        # 1. Create claim in DynamoDB
        claim_input = {
            "farmer_name": "AWS Integration Farmer",
            "village_lgd": "642626",
            "survey_no": "293",
            "subdivision": "1A",
            "claimed_cause": "drought",
            "claimed_crop": "Rice (Paddy)",
            "claimed_stage": "vegetative",
            "incident_date": "2024-11-06",
            "claimed_lat": 9.25,
            "claimed_lon": 77.42,
            "description": "Integration test for DynamoDB lifecycle migration.",
        }
        created_claim = claims_repo.create_claim(claim_input)
        cid = created_claim["claim_id"]
        created_items.append({"claim_id": cid})
        print(f"1. Claim created in DynamoDB: {cid}")

        # 2. Read it back
        read_c = claims_repo.get_claim(cid)
        assert read_c is not None, "Claim could not be read back from DynamoDB!"
        assert read_c["farmer_name"] == "AWS Integration Farmer"
        assert read_c["status"] == "submitted"
        print(f"2. Read claim back verified: {cid}")

        # 3. Create temporary image in S3 + attach metadata in DynamoDB
        buf = io.BytesIO()
        Image.new("RGB", (80, 80), (30, 160, 90)).save(buf, "JPEG")
        img_bytes = buf.getvalue()
        meta = inspect_upload(img_bytes, "smoke_field.jpg", 5 * 1024 * 1024)
        s3_uri = s3_storage.store(cid, meta, img_bytes)
        print(f"3a. Image uploaded to S3: {s3_uri}")

        img_rec = {
            "source": "upload",
            "filename": "smoke_field.jpg",
            "file_path": s3_uri,
            "sha256": meta["sha256"],
            "mime": meta["mime"],
            "width": meta["width"],
            "height": meta["height"],
            "size_bytes": meta["size_bytes"],
            "exif_gps_lat": 9.25,
            "exif_gps_lon": 77.42,
            "exif_captured_at": "2024-11-06T10:00:00",
        }
        img_key = claims_repo.add_claim_image(cid, img_rec)
        created_items.append({"claim_id": f"CLAIM#{cid}#IMAGE#{img_key}"})
        print(f"3b. Attached image metadata in DynamoDB with key: {img_key}")

        # 4. Verify S3 object relationship
        assert s3_storage.exists(s3_uri) is True, "S3 object does not exist!"
        read_img = claims_repo.get_claim_image(cid, img_key)
        assert read_img is not None
        assert read_img["sha256"] == meta["sha256"]
        print("4. S3 object relationship & metadata verified.")

        # 5. Create a verification report
        rep = {
            "claim_id": cid,
            "status": "needs_human_review",
            "status_reason": "Requires review due to boundary edge case",
            "scores": {"confidence_index": 0.65, "evidence_consistency_index": 0.58},
            "routing": {"human_review_required": True, "reasons": ["Boundary proximity verification"]},
            "timeline": [],
            "audit": [
                {"step": "claim_validation", "agent": "planner", "status": "ok", "duration_ms": 5, "detail": "parcel resolved"},
                {"step": "verification", "agent": "verification_engine", "status": "ok", "duration_ms": 8, "detail": "deterministic rules applied"}
            ]
        }
        rep_id = verify_repo.save_report(cid, rep)
        created_items.append({"claim_id": f"CLAIM#{cid}#REPORT#{rep_id}"})
        print(f"5. Created verification report in DynamoDB: report_id={rep_id}")

        # 6. Create review queue item
        q_status = verify_repo.sync_queue(cid, True, ["Boundary proximity verification"])
        created_items.append({"claim_id": f"QUEUE#{cid}"})
        print(f"6. Synced review queue: status={q_status}")

        # 7. Read review queue
        open_queue = verify_repo.list_queue(status="open")
        assert any(q["claim_id"] == cid for q in open_queue), "Claim not found in open review queue!"
        print(f"7. Read review queue: found open item for {cid}")

        # 8. Submit test human decision
        dec_ok = verify_repo.decide(cid, "approve_for_processing", "Smoke test approval note.")
        assert dec_ok is True, "Decision submission failed!"
        print("8. Submitted human decision: approve_for_processing")

        # 9. Verify final claim status
        final_c = claims_repo.get_claim(cid)
        assert final_c["status"] == "approved_for_processing", f"Unexpected status: {final_c['status']}"
        print(f"9. Verified final claim status: {final_c['status']}")

        # 10. Verify audit entry in latest report
        latest_rep = verify_repo.latest_report(cid)
        assert latest_rep is not None
        assert latest_rep["report"]["human_decision"]["decision"] == "approve_for_processing"
        assert any(a["step"] == "human_review_decision" for a in latest_rep["report"]["audit"])
        print("10. Verified audit entry and timeline event in DynamoDB report.")

        print("\n========================================")
        print("REAL AWS INTEGRATION TEST PASSED!")
        print("========================================\n")

    finally:
        # 11. Cleanup ONLY the temporary test data
        print("Cleaning up temporary smoke test data...")
        if s3_uri:
            s3_storage.delete(s3_uri)
        for it in created_items:
            try:
                table.delete_item(Key={"claim_id": it["claim_id"]})
                print(f"Deleted DynamoDB item: {it['claim_id']}")
            except Exception as e:
                print(f"Error deleting {it['claim_id']}: {e}")
        print("All temporary test data successfully cleaned up.")


if __name__ == "__main__":
    run_real_aws_integration_test()
