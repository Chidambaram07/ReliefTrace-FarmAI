"""Generic Amazon Bedrock invocation primitives.

This is the ONE place that actually calls boto3 for Bedrock. Anything that needs to invoke a
model (the claim-analysis pipeline in bedrock_service.py, or the model-health checks in
model_health.py) goes through ModelClient instead of building its own boto3 call, so the
error-mapping, region handling, credential handling and cross-region-profile fallback logic
exist exactly once.

Two invocation shapes are supported, matching what Bedrock actually offers:
- converse(...)        -> chat/text/vision models via the Converse API (Nova, Mistral/Ministral, ...)
- invoke_embedding(...) -> embedding models via InvokeModel (Titan Text Embeddings), which has no
  Converse API equivalent.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("reliefTrace.model_client")

# AWS error codes that mean "this exact model id can't be invoked this way here" as opposed to a
# real outage/credentials problem - worth trying the next candidate id (e.g. a cross-region
# inference profile) before giving up. Confirmed from this account: on-demand throughput for
# amazon.nova-lite-v1:0 / amazon.nova-micro-v1:0 in ap-south-1 returns ValidationException and
# requires the "apac." inference-profile id instead.
FALLBACK_CODES = {"ValidationException", "AccessDeniedException", "ResourceNotFoundException"}

CREDENTIAL_ERROR_CODES = {
    "ExpiredTokenException", "ExpiredToken", "UnrecognizedClientException",
    "InvalidClientTokenId", "InvalidSignatureException", "AuthFailure",
}


class BedrockError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False, aws_code: str = ""):
        super().__init__(message)
        self.code, self.message, self.retryable, self.aws_code = code, message, retryable, aws_code


def candidate_ids(model_id: str) -> list[str]:
    """Model ids to try, in order. We only have EVIDENCE that "amazon." ids need an "apac." cross-region
    profile in this account/region; for every other provider we still offer the profile-prefixed id as a
    second attempt (Bedrock's on-demand-vs-profile restriction is a general ap-south-1 behaviour, not
    Nova-specific), but we never claim it works until an actual call succeeds."""
    ids = [model_id]
    if "." in model_id and not model_id.startswith("apac."):
        ids.append("apac." + model_id)
    return ids


def map_client_error(e: Exception) -> BedrockError:
    resp = getattr(e, "response", {}) or {}
    code = resp.get("Error", {}).get("Code", "")
    msg = resp.get("Error", {}).get("Message", str(e))
    table = {
        "AccessDeniedException": ("BEDROCK_ACCESS_DENIED", False),
        "ThrottlingException": ("BEDROCK_THROTTLED", True),
        "TooManyRequestsException": ("BEDROCK_THROTTLED", True),
        "ModelTimeoutException": ("BEDROCK_UNAVAILABLE", True),
        "ServiceUnavailableException": ("BEDROCK_UNAVAILABLE", True),
        "InternalServerException": ("BEDROCK_UNAVAILABLE", True),
        "ModelNotReadyException": ("BEDROCK_UNAVAILABLE", True),
        "ValidationException": ("BEDROCK_VALIDATION", False),
        "ResourceNotFoundException": ("BEDROCK_MODEL_NOT_FOUND", False),
        # An SSO/temporary-credential session expired mid-run (~1 hour lifetime is typical). Same
        # remedy as having no credentials at all, so it gets the same actionable code and message.
        "ExpiredTokenException": ("BEDROCK_NO_CREDENTIALS", False),
        "ExpiredToken": ("BEDROCK_NO_CREDENTIALS", False),
        "UnrecognizedClientException": ("BEDROCK_NO_CREDENTIALS", False),
        "InvalidClientTokenId": ("BEDROCK_NO_CREDENTIALS", False),
        "InvalidSignatureException": ("BEDROCK_NO_CREDENTIALS", False),
        "AuthFailure": ("BEDROCK_NO_CREDENTIALS", False),
    }
    if code in CREDENTIAL_ERROR_CODES:
        msg = (f"AWS credentials expired or invalid ({code}). Get a fresh session (e.g. re-run "
               f"`aws sso login` or paste new temporary keys) and retry. Original: {msg}")
    c, retry = table.get(code, ("BEDROCK_ERROR", False))
    return BedrockError(c, f"{code}: {msg}" if code else msg, retry, aws_code=code)


def translate_exception(e: Exception) -> BedrockError:
    """Turn ANY exception from a boto3 call into a BedrockError. Never lets a raw SDK exception escape."""
    if isinstance(e, BedrockError):
        return e
    if hasattr(e, "response"):
        return map_client_error(e)
    name = type(e).__name__
    if name in ("NoCredentialsError", "PartialCredentialsError", "NoRegionError"):
        return BedrockError("BEDROCK_NO_CREDENTIALS",
                            "No AWS credentials/region found. Set AWS_PROFILE (e.g. after `aws sso login`) "
                            "or standard AWS_* environment variables.")
    if name in ("EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError", "ConnectionClosedError"):
        return BedrockError("BEDROCK_NETWORK", f"{name}: {e}", retryable=True)
    if name in ("TokenRetrievalError", "SSOTokenLoadError", "UnauthorizedSSOTokenError"):
        return BedrockError("BEDROCK_NO_CREDENTIALS", f"AWS SSO session expired or invalid ({name}). "
                            "Run `aws sso login`.")
    return BedrockError("BEDROCK_ERROR", f"{name}: {e}")


@dataclass
class ClientSettings:
    region: str
    connect_timeout: int = 10
    read_timeout: int = 60
    max_attempts: int = 3


class ModelClient:
    """Thin wrapper around the two boto3 Bedrock runtime calls actually used in this project.

    `runtime_client` / `control_client` can be injected for tests; otherwise real boto3 clients
    are created lazily (never at import time, never before the first real call)."""

    def __init__(self, settings: ClientSettings, runtime_client: Any = None, control_client: Any = None):
        self.settings = settings
        self._runtime = runtime_client
        self._control = control_client

    def runtime(self):
        if self._runtime is None:
            import boto3
            from botocore.config import Config
            self._runtime = boto3.client(
                "bedrock-runtime", region_name=self.settings.region,
                config=Config(retries={"max_attempts": self.settings.max_attempts, "mode": "standard"},
                              connect_timeout=self.settings.connect_timeout, read_timeout=self.settings.read_timeout))
        return self._runtime

    def control(self):
        """The control-plane `bedrock` client (list/describe models) - separate from `bedrock-runtime`
        (invoke). Only used for catalog-visibility checks, which are informational and may legitimately
        be denied without affecting invocation."""
        if self._control is None:
            import boto3
            from botocore.config import Config
            self._control = boto3.client(
                "bedrock", region_name=self.settings.region,
                config=Config(connect_timeout=self.settings.connect_timeout, read_timeout=self.settings.read_timeout))
        return self._control

    # -------------------------------------------------------- converse (chat/text/vision)
    def converse(self, ids: list[str], request: dict, attempts: list | None = None) -> tuple[dict, str]:
        """Try each candidate model id in order; stop at the first that actually invokes.
        Only advances past an id when the error is one of FALLBACK_CODES (wrong id shape for this
        account/region), never on throttling/outage/credential errors, since retrying those against a
        *different* model id would misreport which id is actually the problem."""
        errors: list[tuple[str, BedrockError]] = []
        for i, mid in enumerate(ids):
            try:
                resp = self.runtime().converse(modelId=mid, **request)
                if attempts is not None:
                    attempts.append({"model_id": mid, "ok": True})
                return resp, mid
            except Exception as e:  # noqa: BLE001
                err = translate_exception(e)
                if attempts is not None:
                    attempts.append({"model_id": mid, "ok": False, "code": err.code, "message": err.message})
                errors.append((mid, err))
                if err.aws_code in FALLBACK_CODES and i + 1 < len(ids):
                    log.info("model %s rejected (%s); trying %s", mid, err.aws_code, ids[i + 1])
                    continue
                break
        last = errors[-1][1] if errors else BedrockError("BEDROCK_ERROR", "no model candidates")
        if len(errors) > 1:
            detail = " | ".join(f"{m}: {e.message}" for m, e in errors)
            raise BedrockError(last.code, f"All model ids failed. {detail}", last.retryable, last.aws_code)
        raise last

    # -------------------------------------------------------- InvokeModel (embeddings)
    def invoke_json(self, ids: list[str], body: dict, attempts: list | None = None) -> tuple[dict, str]:
        """Generic InvokeModel call with a JSON body and JSON response. Embedding models have no
        Converse API equivalent, so text embeddings ({"inputText": ...}) and image embeddings
        ({"inputImage": <base64>, ...}) both go through here - one code path, one error mapping."""
        payload_body = json.dumps(body)
        errors: list[tuple[str, BedrockError]] = []
        for i, mid in enumerate(ids):
            try:
                resp = self.runtime().invoke_model(modelId=mid, body=payload_body, contentType="application/json",
                                                   accept="application/json")
                payload = json.loads(resp["body"].read())
                if attempts is not None:
                    attempts.append({"model_id": mid, "ok": True})
                return payload, mid
            except Exception as e:  # noqa: BLE001
                err = translate_exception(e)
                if attempts is not None:
                    attempts.append({"model_id": mid, "ok": False, "code": err.code, "message": err.message})
                errors.append((mid, err))
                if err.aws_code in FALLBACK_CODES and i + 1 < len(ids):
                    continue
                break
        last = errors[-1][1] if errors else BedrockError("BEDROCK_ERROR", "no model candidates")
        if len(errors) > 1:
            detail = " | ".join(f"{m}: {e.message}" for m, e in errors)
            raise BedrockError(last.code, f"All model ids failed. {detail}", last.retryable, last.aws_code)
        raise last

    def invoke_embedding(self, ids: list[str], text: str, attempts: list | None = None) -> tuple[dict, str]:
        return self.invoke_json(ids, {"inputText": text}, attempts)

    # -------------------------------------------------------- catalog visibility (informational only)
    def is_catalog_visible(self, model_id: str) -> Optional[bool]:
        """True/False if we could check, None if the check itself failed (e.g. no bedrock:GetFoundationModel
        permission) - a None here must never be read as "unavailable"; it just means unknown."""
        try:
            self.control().get_foundation_model(modelIdentifier=model_id)
            return True
        except Exception as e:  # noqa: BLE001
            code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
            if code == "ResourceNotFoundException":
                return False
            log.info("catalog visibility check inconclusive for %s: %s", model_id, e)
            return None
