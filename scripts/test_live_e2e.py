"""End-to-end verification against the live AWS API Gateway."""
import json
import urllib.request
import urllib.error

BASE_URL = "https://5ydc54f4c2.execute-api.ap-south-1.amazonaws.com"

def request_json(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if payload else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}

def main():
    print(f"Testing live API Gateway at {BASE_URL}...")

    # 1. Health check
    status, health = request_json("GET", "/api/health")
    print(f"\n1. Health Check -> HTTP {status}")
    print(f"   dataset_loaded: {health.get('dataset_loaded')}")
    print(f"   dataset summary: {health.get('dataset')}")
    assert health.get("dataset_loaded") is True, f"Dataset not loaded: {health}"

    # 2. Create Claim
    claim_payload = {
        "farmer_name": "Test Farmer",
        "village_lgd": "642627",
        "survey_no": "371",
        "subdivision": "3B",
        "claimed_cause": "flood",
        "incident_date": "2024-11-14",
        "claimed_crop": "Rice (Paddy)",
        "description": "Field flooded."
    }
    status, claim_resp = request_json("POST", "/api/claims", claim_payload)
    print(f"\n2. Create Claim -> HTTP {status}")
    print(f"   Response: {json.dumps(claim_resp, indent=2)}")
    assert status == 201, f"Create claim failed: {claim_resp}"
    claim_id = claim_resp["claim_id"]
    print(f"   Claim ID created: {claim_id}")

    # 3. Attach Challenge Dataset Image
    attach_payload = {
        "image_id": "2fec8fab4a7055ce-43514-14060200521558"
    }
    status, attach_resp = request_json("POST", f"/api/claims/{claim_id}/images/from-dataset", attach_payload)
    print(f"\n3. Attach Challenge Dataset Image -> HTTP {status}")
    print(f"   Response: {json.dumps(attach_resp, indent=2)}")
    assert status == 201, f"Attach dataset image failed: {attach_resp}"
    assert attach_resp.get("source") == "dataset"
    assert attach_resp.get("dataset_image_id") == "2fec8fab4a7055ce-43514-14060200521558"
    assert attach_resp.get("file_available") is True
    image_key = attach_resp["image_key"]
    print(f"   Attached image_key: {image_key}")

    # 4. Fetch Attached Image Binary
    img_url = f"{BASE_URL}/api/claims/{claim_id}/images/{image_key}/file"
    print(f"\n4. Fetch Image Binary from S3 via API -> GET {img_url}")
    with urllib.request.urlopen(img_url, timeout=30) as resp:
        img_bytes = resp.read()
        print(f"   HTTP {resp.status}, Content-Type: {resp.headers.get('Content-Type')}, Bytes: {len(img_bytes)}")
        assert resp.status == 200
        assert len(img_bytes) > 0

    # 5. Run Verification Pipeline
    verify_url = f"/api/claims/{claim_id}/verify"
    print(f"\n5. Run Verification Pipeline -> POST {verify_url} (with Bedrock vision & timing analysis)...")
    status, verify_resp = request_json("POST", verify_url)
    print(f"   HTTP {status}")
    print(f"   Verification Summary:")
    print(f"     Status: {verify_resp.get('status')}")
    print(f"     Scores: {verify_resp.get('scores')}")
    print(f"     Human review required: {verify_resp.get('routing', {}).get('human_review_required')}")
    print(f"     Human review reasons: {verify_resp.get('routing', {}).get('reasons')}")
    print(f"\n   Findings:")
    for f in verify_resp.get("findings", []):
        print(f"     - [{f.get('check_name')}] verdict={f.get('verdict')} reason={f.get('reason')}")
    
    timing_finding = next((f for f in verify_resp.get("findings", []) if f.get("check_name") == "timing"), None)
    print(f"\n   Timing Finding: {timing_finding}")
    assert timing_finding is not None
    assert timing_finding.get("verdict") == "contradicts"
    assert "before the reported incident" in timing_finding.get("reason", "")

    assert verify_resp.get("routing", {}).get("human_review_required") is True
    assert any("timing" in r.lower() for r in verify_resp.get("routing", {}).get("reasons", []))

    print(f"\n6. Audit Steps:")
    for s in verify_resp.get("audit", []):
        print(f"     - step={s.get('step')} agent={s.get('agent')} status={s.get('status')}")

    print("\nALL LIVE END-TO-END VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
