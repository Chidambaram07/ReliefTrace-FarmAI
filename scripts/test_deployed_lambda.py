"""Live verification of deployed AWS Lambda function fai-tce-team56-backend."""
from __future__ import annotations

import base64
import json
import uuid
import boto3

REGION = "ap-south-1"
FUNCTION_NAME = "fai-tce-team56-backend"
PROFILE = "FAI-TCE-Builder-AI-314240411685"


def make_apigw_v2_payload(method: str, path: str, body: dict | str | None = None, headers: dict | None = None) -> dict:
    body_str = None
    if isinstance(body, dict):
        body_str = json.dumps(body)
    elif isinstance(body, str):
        body_str = body

    hdrs = {
        "host": "test.execute-api.ap-south-1.amazonaws.com",
        "user-agent": "lambda-live-smoke-test",
        "content-type": "application/json",
    }
    if headers:
        hdrs.update(headers)

    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": hdrs,
        "queryStringParameters": {},
        "requestContext": {
            "accountId": "314240411685",
            "apiId": "relieftrace-lambda",
            "domainName": "test.execute-api.ap-south-1.amazonaws.com",
            "domainPrefix": "test",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "lambda-live-smoke-test"
            },
            "requestId": f"req-{uuid.uuid4().hex[:8]}",
            "routeKey": f"{method} {path}",
            "stage": "$default",
            "time": "06/Oct/2026:17:00:00 +0000",
            "timeEpoch": 1791306000000
        },
        "body": body_str,
        "isBase64Encoded": False
    }


def run_live_tests():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    lam = session.client("lambda", region_name=REGION)
    ddb = session.resource("dynamodb", region_name=REGION)
    table = ddb.Table("fai-tce-team56-claims")

    print(f"1. Testing GET /api/health on {FUNCTION_NAME}...")
    payload = make_apigw_v2_payload("GET", "/api/health")
    resp = lam.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )

    res_payload = json.loads(resp["Payload"].read().decode("utf-8"))
    print(f"Health response status: {res_payload.get('statusCode')}")
    body = json.loads(res_payload.get("body", "{}"))
    print(f"Health response body: {body}")
    assert res_payload.get("statusCode") == 200, f"Health check failed: {res_payload}"
    assert body.get("status") == "ok", f"Expected status ok, got {body}"

    print("\n2. Testing POST /api/claims with smoke test claim...")
    smoke_id = f"AWS-LAMBDA-SMOKE-{uuid.uuid4().hex[:6].upper()}"
    claim_payload = {
        "farmer_name": "R. Murugesan (Lambda Smoke)",
        "survey_no": "142/2A",
        "claimed_cause": "flood",
        "claimed_crop": "Paddy",
        "claimed_stage": "Flowering",
        "incident_date": "2026-09-10",
        "claimed_lat": 9.9252,
        "claimed_lon": 78.1198,
        "description": "Heavy flooding due to seasonal monsoon rain",
    }

    claim_req = make_apigw_v2_payload("POST", "/api/claims", body=claim_payload)
    resp = lam.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(claim_req),
    )

    res_payload = json.loads(resp["Payload"].read().decode("utf-8"))
    print(f"Claim creation status: {res_payload.get('statusCode')}")
    claim_body = json.loads(res_payload.get("body", "{}"))
    print(f"Claim created: {claim_body}")
    assert res_payload.get("statusCode") in (200, 201), f"Claim creation failed: {res_payload}"
    created_id = claim_body.get("claim_id") or smoke_id

    print(f"\n3. Verifying claim {created_id} directly in DynamoDB table fai-tce-team56-claims...")
    item = table.get_item(Key={"claim_id": created_id}).get("Item")
    assert item is not None, f"Claim {created_id} not found in DynamoDB!"
    print(f"Found DynamoDB item for {created_id}: {item.get('farmer_name')}")

    print("\n4. Testing GET /api/claims/{created_id} through Lambda...")
    get_claim_req = make_apigw_v2_payload("GET", f"/api/claims/{created_id}")
    resp = lam.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(get_claim_req),
    )
    res_payload = json.loads(resp["Payload"].read().decode("utf-8"))
    assert res_payload.get("statusCode") == 200
    print(f"Retrieved claim via Lambda GET: {json.loads(res_payload.get('body', '{}')).get('claim_id')}")

    print("\n5. Cleaning up temporary smoke test item from DynamoDB...")
    table.delete_item(Key={"claim_id": created_id})
    print(f"Deleted DynamoDB item: {created_id}")

    print("\n========================================")
    print("ALL LIVE LAMBDA INVOCATION TESTS PASSED!")
    print("========================================")


if __name__ == "__main__":
    run_live_tests()
