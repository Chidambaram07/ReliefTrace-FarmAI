"""Amazon Bedrock (Nova) access for the claim-analysis pipeline. Region ap-south-1 only;
credentials come from the standard AWS chain.

Design goals: few calls, low cost, predictable failure modes.
- Converse API, temperature 0, small max tokens, JSON via assistant prefill + stop sequence.
- Images are downscaled before sending; results are cached by content hash.
- If a base model ID is rejected (on-demand not supported / access denied) a cross-region profile
  id is tried once (see backend.services.model_client.candidate_ids).
- Failures are returned as structured errors so the pipeline can degrade gracefully.

The actual boto3 call, AWS error mapping and candidate-id fallback live in
backend.services.model_client.ModelClient - this module only adds the claim-analysis-specific
concerns (image prep, JSON-schema extraction/validation, caching) on top of it, so that logic is
not duplicated between this file and the model-health checks in model_health.py.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from PIL import Image
from pydantic import BaseModel, ValidationError

from backend.config import load_dotenv
from backend.schemas.ai import AIError, AIResult, AIUsage, ImageObservation
from backend.services import prompts
from backend.services.model_client import BedrockError, ClientSettings, ModelClient, candidate_ids

log = logging.getLogger("reliefTrace.bedrock")

ALLOWED_REGION = "ap-south-1"

__all__ = ["BedrockService", "BedrockSettings", "BedrockError", "AICache", "candidate_ids",
          "extract_json", "prepare_image", "ALLOWED_REGION"]


class AICache(Protocol):
    def get(self, key: str) -> Optional[dict]: ...
    def put(self, key: str, value: dict) -> None: ...


def _f(env: str) -> Optional[float]:
    v = os.environ.get(env)
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


@dataclass(frozen=True)
class BedrockSettings:
    region: str = ALLOWED_REGION
    vision_model_id: str = "amazon.nova-lite-v1:0"
    text_model_id: str = "amazon.nova-micro-v1:0"
    max_image_side: int = 1024
    max_tokens_vision: int = 1200
    max_tokens_text: int = 800
    connect_timeout: int = 10
    read_timeout: int = 60
    max_attempts: int = 3
    price_per_m: dict = field(default_factory=dict)  # role -> (input, output) USD per 1M tokens

    @classmethod
    def from_env(cls) -> "BedrockSettings":
        load_dotenv()
        prices = {}
        for role, pre in (("vision", "RT_PRICE_VISION"), ("text", "RT_PRICE_TEXT")):
            pin, pout = _f(f"{pre}_IN_PER_M"), _f(f"{pre}_OUT_PER_M")
            if pin is not None and pout is not None:
                prices[role] = (pin, pout)
        return cls(
            region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or ALLOWED_REGION,
            vision_model_id=os.environ.get("BEDROCK_VISION_MODEL_ID", cls.vision_model_id),
            text_model_id=os.environ.get("BEDROCK_TEXT_MODEL_ID", cls.text_model_id),
            max_image_side=int(os.environ.get("BEDROCK_MAX_IMAGE_SIDE", "1024")),
            price_per_m=prices,
        )


# ---------------------------------------------------------------- helpers (claim-analysis specific)
def prepare_image(data: bytes, max_side: int) -> tuple[bytes, str, tuple[int, int]]:
    """Downscale (never upscale) and re-encode as JPEG to cut image tokens. Returns (bytes, 'jpeg', size)."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001
        raise BedrockError("IMAGE_UNREADABLE", f"Cannot read image: {e}")
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue(), "jpeg", img.size


def extract_json(text: str) -> dict:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t.lstrip("`")
    t = t.replace("```", "").strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    obj = json.loads(t[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("JSON root is not an object")
    return obj


class BedrockService:
    def __init__(self, settings: BedrockSettings | None = None, client: Any = None):
        self.settings = settings or BedrockSettings.from_env()
        self._resolved: dict[str, str] = {}
        cs = ClientSettings(region=self.settings.region, connect_timeout=self.settings.connect_timeout,
                            read_timeout=self.settings.read_timeout, max_attempts=self.settings.max_attempts)
        # `client` here is the injected fake/real bedrock-runtime client used by the Converse calls
        # this service makes; ModelClient owns the actual boto3 call.
        self._mc = ModelClient(cs, runtime_client=client)
        if self.settings.region != ALLOWED_REGION:
            log.warning("Region %s is not %s; the challenge only permits ap-south-1",
                        self.settings.region, ALLOWED_REGION)

    def configured_model(self, role: str) -> str:
        return self.settings.vision_model_id if role == "vision" else self.settings.text_model_id

    # ------------------------------------------------------------ low level (delegates to ModelClient)
    def _call_with_fallback(self, role: str, request: dict, attempts: list | None = None) -> tuple[dict, str]:
        configured = self.configured_model(role)
        ids = [self._resolved[role]] if role in self._resolved else candidate_ids(configured)
        resp, used_id = self._mc.converse(ids, request, attempts=attempts)
        self._resolved[role] = used_id
        return resp, used_id

    def _cost(self, role: str, tin: Optional[int], tout: Optional[int]) -> Optional[float]:
        p = self.settings.price_per_m.get(role)
        if not p or tin is None or tout is None:
            return None
        return round((tin * p[0] + tout * p[1]) / 1_000_000, 6)

    # ------------------------------------------------------------ public
    def converse_json(self, *, role: str, system: str, user_text: str, prompt_version: str,
                      schema: type[BaseModel], image: bytes | None = None, max_tokens: int | None = None,
                      cache: AICache | None = None, use_cache: bool = True) -> AIResult:
        """One model call that must return a JSON object validated against `schema`. Never raises."""
        s = self.settings
        max_tokens = max_tokens or (s.max_tokens_vision if role == "vision" else s.max_tokens_text)
        image_sha = None
        content: list[dict] = []
        try:
            if image is not None:
                prepared, fmt, _ = prepare_image(image, s.max_image_side)
                image_sha = hashlib.sha256(prepared).hexdigest()
                content.append({"image": {"format": fmt, "source": {"bytes": prepared}}})
            content.append({"text": user_text})
        except BedrockError as e:
            return self._fail(role, prompt_version, e)

        key = hashlib.sha256(json.dumps(
            [role, self.configured_model(role), prompt_version, image_sha, system, user_text, max_tokens]).encode()).hexdigest()
        if cache and use_cache:
            hit = cache.get(key)
            if hit:
                r = AIResult.model_validate(hit)
                r.cached = True
                r.usage = AIUsage(input_tokens=0, output_tokens=0, latency_ms=0,
                                  cost_estimate_usd=0.0 if s.price_per_m.get(role) else None)
                return r

        request = {
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": content},
                         {"role": "assistant", "content": [{"text": "```json"}]}],  # JSON prefill
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.0, "stopSequences": ["```"]},
        }
        t0 = time.perf_counter()
        try:
            resp, used_id = self._call_with_fallback(role, request)
        except BedrockError as e:
            return self._fail(role, prompt_version, e)
        latency = int((time.perf_counter() - t0) * 1000)

        usage_raw = resp.get("usage", {}) or {}
        tin, tout = usage_raw.get("inputTokens"), usage_raw.get("outputTokens")
        usage = AIUsage(input_tokens=tin, output_tokens=tout,
                        latency_ms=(resp.get("metrics", {}) or {}).get("latencyMs", latency),
                        cost_estimate_usd=self._cost(role, tin, tout))
        parts = (resp.get("output", {}).get("message", {}) or {}).get("content", []) or []
        text = "".join(p.get("text", "") for p in parts)

        def bad(code: str, msg: str) -> AIResult:
            return AIResult(ok=False, role=role, model_id=used_id, prompt_version=prompt_version,
                            raw_text=text[:4000], usage=usage, error=AIError(code=code, message=msg))

        if resp.get("stopReason") == "max_tokens":
            return bad("AI_OUTPUT_TRUNCATED", "Model hit the token limit before finishing the JSON")
        try:
            obj = extract_json(text)
            parsed = schema.model_validate(obj).model_dump()
        except (ValueError, ValidationError) as e:
            return bad("AI_OUTPUT_INVALID", f"Model output was not valid for the schema: {str(e)[:300]}")
        result = AIResult(ok=True, role=role, model_id=used_id, prompt_version=prompt_version,
                          parsed=parsed, raw_text=text[:4000], usage=usage)
        if cache:
            cache.put(key, result.model_dump())
        return result

    def analyze_image(self, image: bytes, claim: dict | None = None, *, cache: AICache | None = None,
                      use_cache: bool = True) -> AIResult:
        return self.converse_json(
            role="vision", system=prompts.IMAGE_SYSTEM, user_text=prompts.image_user_prompt(claim),
            prompt_version=prompts.IMAGE_PROMPT_VERSION, schema=ImageObservation, image=image,
            cache=cache, use_cache=use_cache)

    def check_model(self, role: str, image: bytes | None = None) -> dict:
        """Minimal, cheap call used by scripts/check_bedrock.py to discover which model ID works."""
        content: list[dict] = []
        if image is not None:
            prepared, fmt, _ = prepare_image(image, self.settings.max_image_side)
            content.append({"image": {"format": fmt, "source": {"bytes": prepared}}})
            content.append({"text": "In one short sentence, what is in this image?"})
        else:
            content.append({"text": 'Reply with exactly: {"ok": true}'})
        request = {"messages": [{"role": "user", "content": content}],
                   "inferenceConfig": {"maxTokens": 40, "temperature": 0.0}}
        attempts: list[dict] = []
        out = {"role": role, "configured": self.configured_model(role), "attempts": attempts, "working_id": None}
        try:
            resp, mid = self._call_with_fallback(role, request, attempts)
            parts = resp.get("output", {}).get("message", {}).get("content", [])
            out.update(working_id=mid, sample="".join(p.get("text", "") for p in parts)[:120],
                       usage=resp.get("usage"))
        except BedrockError as e:
            out["error"] = {"code": e.code, "message": e.message}
        return out

    def _fail(self, role: str, version: str, e: BedrockError) -> AIResult:
        log.warning("bedrock call failed role=%s code=%s", role, e.code)
        return AIResult(ok=False, role=role, prompt_version=version,
                        error=AIError(code=e.code, message=e.message, retryable=e.retryable))
