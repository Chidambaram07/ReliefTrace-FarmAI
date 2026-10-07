"""Availability / health-check mechanism for registered models.

Distinguishes, explicitly, the states the task called out:
- DISABLED            operator turned it off; never invoked
- NOT_CONFIGURED       no model id known (e.g. Ministral ids not yet supplied) - never invoked
- CATALOG_VISIBLE      informational only: bedrock:GetFoundationModel says the id exists in this
                       region. This is NEVER used to decide invokability and is allowed to be
                       "unknown" (permission to list can be denied independently of permission to
                       invoke - and vice versa).
- INVOKABLE            an actual minimal Converse/InvokeModel call succeeded just now
- INVOCATION_FAILED    an actual call was attempted and failed; `error_code`/`error_message` hold
                       the real reason (e.g. AccessDenied, ValidationException)

Every check that ATTEMPTS a real call (i.e. not DISABLED/NOT_CONFIGURED) is recorded through the
same audit trail shape as pipeline model calls: task, model, status, latency, error, timestamp.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from backend.services.model_client import BedrockError, ModelClient, candidate_ids
from backend.services.model_registry import Capability, ModelSpec, ModelType

MINIMAL_PROMPT = 'Reply with exactly: {"ok": true}'
MINIMAL_MAX_TOKENS = 20


class Availability(str, Enum):
    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    INVOKABLE = "invokable"
    INVOCATION_FAILED = "invocation_failed"


@dataclass
class HealthResult:
    task: str                      # what kind of check this was, e.g. "model_health:text_minimal"
    model_key: str
    model_id: Optional[str]
    provider: str
    availability: Availability
    catalog_visible: Optional[bool]  # True/False/None(unknown) - informational, see module docstring
    latency_ms: Optional[int]
    error_code: Optional[str]
    error_message: Optional[str]
    attempts: list = field(default_factory=list)
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _skip(spec: ModelSpec, availability: Availability, reason: str) -> HealthResult:
    return HealthResult(task=f"model_health:{spec.key}", model_key=spec.key, model_id=spec.model_id,
                        provider=spec.provider, availability=availability, catalog_visible=None,
                        latency_ms=None, error_code=None, error_message=reason)


def check_model(client: ModelClient, spec: ModelSpec, *, check_catalog: bool = True) -> HealthResult:
    """Run the cheapest possible real request for this model's type. Never raises."""
    if not spec.enabled:
        return _skip(spec, Availability.DISABLED, "disabled by MODEL_*_ENABLED configuration")
    if not spec.configured:
        return _skip(spec, Availability.NOT_CONFIGURED, "no model id configured (see registry notes)")

    catalog_visible = client.is_catalog_visible(spec.model_id) if check_catalog else None
    ids = candidate_ids(spec.model_id)
    attempts: list = []
    t0 = time.perf_counter()
    try:
        if spec.model_type is ModelType.EMBEDDING:
            _, used_id = client.invoke_embedding(ids, "reliefTrace health check", attempts=attempts)
        else:
            request = {"messages": [{"role": "user", "content": [{"text": MINIMAL_PROMPT}]}],
                      "inferenceConfig": {"maxTokens": MINIMAL_MAX_TOKENS, "temperature": 0.0}}
            _, used_id = client.converse(ids, request, attempts=attempts)
        latency = int((time.perf_counter() - t0) * 1000)
        return HealthResult(task=f"model_health:{spec.key}", model_key=spec.key, model_id=used_id,
                            provider=spec.provider, availability=Availability.INVOKABLE,
                            catalog_visible=catalog_visible, latency_ms=latency, error_code=None,
                            error_message=None, attempts=attempts)
    except BedrockError as e:
        latency = int((time.perf_counter() - t0) * 1000)
        return HealthResult(task=f"model_health:{spec.key}", model_key=spec.key, model_id=spec.model_id,
                            provider=spec.provider, availability=Availability.INVOCATION_FAILED,
                            catalog_visible=catalog_visible, latency_ms=latency, error_code=e.code,
                            error_message=e.message, attempts=attempts)


def check_all(client: ModelClient, registry: dict[str, ModelSpec], *, check_catalog: bool = True) -> list[HealthResult]:
    return [check_model(client, spec, check_catalog=check_catalog) for spec in registry.values()]
