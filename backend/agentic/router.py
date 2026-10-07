"""Model router (Phase 4): given a task and a primary model, actually invokes it and, if it is
unavailable or fails, falls back to ONE registered secondary model - recording every attempt
(including skips) into SharedState so recovery is visible, not silently absorbed.

This is the layer that turns a planner task's `model_key` (Phase 3, which only ever plans - it
never calls anything) into a REAL Bedrock call. It reuses ModelClient (Phase 1) for the actual
boto3 invocation and error mapping, and model_registry.py (Phase 1) as the single source of truth
for which model ids exist and whether they are enabled/configured - the router never invents an id
or invokes a model the registry says is disabled or unconfigured.

Fallback chains are explicit and short (one hop), matching the brief's own example:
    "Nova Lite fails -> route to Ministral 8B"
A model with no registered fallback (e.g. Ministral 8B itself) simply reports failure honestly
rather than guessing a third option.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from backend.agentic.state import ModelOutput, SharedState
from backend.services.model_client import BedrockError, ModelClient, candidate_ids
from backend.services.model_registry import ModelSpec

# One-hop fallback chains. None = no fallback registered; report failure rather than guess one.
# ministral_8b -> ministral_3b is a deliberate downgrade (smaller model), always recorded as a
# fallback in the trace so a reviewer can see which model actually produced an answer.
FALLBACK_CHAIN: dict[str, Optional[str]] = {
    "nova_lite": "ministral_8b",
    "nova_micro": "ministral_3b",
    "ministral_8b": "ministral_3b",
    "ministral_3b": None,
}


@dataclass
class RouterAttempt:
    model_key: str
    model_id: Optional[str]
    outcome: str    # "invoked" | "skipped_not_configured" | "skipped_disabled" | "failed"
    error: Optional[str] = None


@dataclass
class RouterResult:
    ok: bool
    task: str
    model_key: Optional[str]     # the model_key that actually served the task, if any
    model_id: Optional[str]
    text: Optional[str]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    fallback_used: bool = False
    attempts: list[RouterAttempt] = field(default_factory=list)
    error: Optional[str] = None


class ModelRouter:
    def __init__(self, client: ModelClient, registry: dict[str, ModelSpec]):
        self.client = client
        self.registry = registry

    def chain_for(self, primary_key: str) -> list[str]:
        nxt = FALLBACK_CHAIN.get(primary_key)
        return [primary_key, nxt] if nxt else [primary_key]

    def invoke(self, state: SharedState, *, task: str, primary_key: str, system: str, user_text: str,
              image: bytes | None = None, max_tokens: int = 400) -> RouterResult:
        chain = self.chain_for(primary_key)
        attempts: list[RouterAttempt] = []

        for i, key in enumerate(chain):
            is_fallback = i > 0
            spec = self.registry.get(key)
            if spec is None or not spec.enabled or not spec.configured:
                reason = ("model key not in registry" if spec is None
                         else "disabled by configuration" if not spec.enabled else "no model id configured")
                outcome = "skipped_disabled" if (spec and not spec.enabled) else "skipped_not_configured"
                attempts.append(RouterAttempt(key, spec.model_id if spec else None, outcome, reason))
                state.trace(step=f"router_skip:{task}:{key}", agent="router", task=task, model=key,
                           status="skipped", error=reason,
                           routing_reason=f"considered as {'fallback' if is_fallback else 'primary'}; not invoked")
                continue

            content: list[dict] = []
            if image is not None:
                content.append({"image": {"format": "jpeg", "source": {"bytes": image}}})
            content.append({"text": user_text})
            request = {"system": [{"text": system}], "messages": [{"role": "user", "content": content}],
                      "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.0}}
            t0 = time.perf_counter()
            try:
                resp, used_id = self.client.converse(candidate_ids(spec.model_id), request)
                latency = int((time.perf_counter() - t0) * 1000)
                usage = resp.get("usage", {}) or {}
                parts = (resp.get("output", {}).get("message", {}) or {}).get("content", []) or []
                text = "".join(p.get("text", "") for p in parts)
                reason = ("primary model for this task" if not is_fallback
                         else f"{chain[0]} unavailable or failed; using the registered fallback")
                state.route(task, key, reason, fallback_of=chain[0] if is_fallback else None)
                state.record_model_output(ModelOutput(
                    task=task, model_key=key, model_id=used_id, ok=True, output_summary=text[:300],
                    input_tokens=usage.get("inputTokens"), output_tokens=usage.get("outputTokens"),
                    latency_ms=latency))
                attempts.append(RouterAttempt(key, used_id, "invoked"))
                return RouterResult(ok=True, task=task, model_key=key, model_id=used_id, text=text,
                                    input_tokens=usage.get("inputTokens"), output_tokens=usage.get("outputTokens"),
                                    latency_ms=latency, fallback_used=is_fallback, attempts=attempts)
            except BedrockError as e:
                latency = int((time.perf_counter() - t0) * 1000)
                err = f"{e.code}: {e.message}"
                reason = "primary model for this task" if not is_fallback else "attempted as fallback"
                state.route(task, key, reason, fallback_of=chain[0] if is_fallback else None)
                state.record_model_output(ModelOutput(task=task, model_key=key, model_id=spec.model_id, ok=False,
                                                       output_summary="", error=err, latency_ms=latency))
                attempts.append(RouterAttempt(key, spec.model_id, "failed", err))
                continue

        summary = "; ".join(f"{a.model_key}={a.outcome}" + (f" ({a.error})" if a.error else "") for a in attempts)
        return RouterResult(ok=False, task=task, model_key=None, model_id=None, text=None,
                            fallback_used=len(attempts) > 1, attempts=attempts,
                            error=f"no model in the chain for '{task}' could be used: {summary}")
