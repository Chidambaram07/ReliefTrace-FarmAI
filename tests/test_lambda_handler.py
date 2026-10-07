"""Tests for the AWS Lambda entry point (Mangum handler) with API Gateway v2 events."""
from __future__ import annotations

import json
import pytest
from backend.main import handler, app


def make_apigw_v2_event(method: str, path: str, query_params: dict | None = None, body: str | None = None, headers: dict | None = None) -> dict:
    """Construct a mock API Gateway HTTP API v2 payload format event."""
    hdrs = {
        "host": "test.execute-api.ap-south-1.amazonaws.com",
        "user-agent": "pytest-lambda-test",
        "content-type": "application/json",
    }
    if headers:
        hdrs.update(headers)

    qs = ""
    if query_params:
        qs = "&".join(f"{k}={v}" for k, v in query_params.items())

    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": qs,
        "headers": hdrs,
        "queryStringParameters": query_params or {},
        "requestContext": {
            "accountId": "314240411685",
            "apiId": "relieftrace-api",
            "domainName": "test.execute-api.ap-south-1.amazonaws.com",
            "domainPrefix": "test",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest-lambda-test"
            },
            "requestId": "lambda-req-test-12345",
            "routeKey": f"{method} {path}",
            "stage": "$default",
            "time": "06/Oct/2026:17:00:00 +0000",
            "timeEpoch": 1791306000000
        },
        "body": body,
        "isBase64Encoded": False
    }


class LambdaMockContext:
    def __init__(self):
        self.function_name = "relieftrace-backend"
        self.function_version = "$LATEST"
        self.invoked_function_arn = "arn:aws:lambda:ap-south-1:314240411685:function:relieftrace-backend"
        self.memory_limit_in_mb = "512"
        self.aws_request_id = "test-request-id-123"
        self.log_group_name = "/aws/lambda/relieftrace-backend"
        self.log_stream_name = "2026/10/06/[$LATEST]teststream"

    def get_remaining_time_in_millis(self):
        return 30000


def test_lambda_handler_health():
    """Verify that Mangum Lambda handler receives APIGW v2 event and returns 200 OK for /api/health."""
    event = make_apigw_v2_event("GET", "/api/health")
    context = LambdaMockContext()
    response = handler(event, context)

    assert response["statusCode"] == 200, f"Expected 200, got {response}"
    body = json.loads(response["body"])
    assert body.get("status") == "ok"
    assert "version" in body


def test_lambda_handler_claims_list():
    """Verify that Mangum Lambda handler processes GET /api/claims correctly."""
    event = make_apigw_v2_event("GET", "/api/claims")
    context = LambdaMockContext()
    response = handler(event, context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "claims" in body or isinstance(body, list) or "total" in body


def test_lambda_handler_aws_mode(monkeypatch):
    """Verify that Lambda handler functions with STORAGE_BACKEND=aws."""
    monkeypatch.setenv("STORAGE_BACKEND", "aws")
    monkeypatch.setenv("RT_S3_BUCKET", "fai-tce-team56-images")
    monkeypatch.setenv("RT_DYNAMODB_TABLE", "fai-tce-team56-claims")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")

    event = make_apigw_v2_event("GET", "/api/health")
    context = LambdaMockContext()
    response = handler(event, context)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body.get("status") == "ok"

