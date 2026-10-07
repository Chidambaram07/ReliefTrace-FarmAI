import io
import json

import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from PIL import Image

from backend.schemas.ai import ImageObservation
from backend.services import prompts
from backend.services.bedrock_service import (
    BedrockService, BedrockSettings, candidate_ids, extract_json, prepare_image,
)

GOOD = {
    "image_usable": True, "quality_issues": [], "observations": ["green paddy leaves in dense stand"],
    "crop": {"crop_visible": True, "name_guess": "rice", "name_confidence": "HIGH",
             "stage_guess": "Full Growth", "stage_confidence": "medium"},
    "damage_indicators": [{"type": "none_visible", "visible": False, "description": "", "severity": "none",
                           "confidence": "medium"}],
    "inferences": [{"statement": "crop looks healthy", "basis": "uniform green colour"}],
    "claim_assessment": {"supports": [], "contradicts": ["no drought stress visible"], "cannot_determine": ["date"]},
    "missing_information": ["capture date"], "limitations": ["single photo"],
}


def jpg(size=(300, 600)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, (20, 140, 30)).save(b, "JPEG")
    return b.getvalue()


def ok_response(payload=GOOD, text=None, stop="end_turn", tin=1100, tout=300):
    return {"output": {"message": {"content": [{"text": text if text is not None else json.dumps(payload)}]}},
            "stopReason": stop, "usage": {"inputTokens": tin, "outputTokens": tout}, "metrics": {"latencyMs": 900}}


def client_error(code, msg="nope"):
    return ClientError({"Error": {"Code": code, "Message": msg}}, "Converse")


class FakeClient:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def converse(self, **kw):
        self.calls.append(kw)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


class MemCache:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def put(self, k, v):
        self.d[k] = v


def svc(client, **kw):
    return BedrockService(BedrockSettings(**kw), client=client)


def test_candidate_ids():
    assert candidate_ids("amazon.nova-lite-v1:0") == ["amazon.nova-lite-v1:0", "apac.amazon.nova-lite-v1:0"]
    assert candidate_ids("apac.amazon.nova-lite-v1:0") == ["apac.amazon.nova-lite-v1:0"]


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": {"b": 2}} thanks') == {"a": {"b": 2}}
    for bad in ("", "no json", "[1,2]", '{"a": '):
        with pytest.raises(ValueError):
            extract_json(bad)


def test_prepare_image_downscales_never_upscales():
    big, fmt, size = prepare_image(jpg((2000, 1000)), 1024)
    assert fmt == "jpeg" and max(size) == 1024
    _, _, small = prepare_image(jpg((300, 600)), 1024)
    assert small == (300, 600)


def test_success_request_shape_and_normalization():
    c = FakeClient(ok_response())
    r = svc(c, price_per_m={"vision": (0.06, 0.24)}).analyze_image(jpg(), {"claimed_cause": "drought"})
    assert r.ok and r.role == "vision" and r.label.startswith("AI observation")
    call = c.calls[0]
    assert call["modelId"] == "amazon.nova-lite-v1:0"
    assert call["inferenceConfig"]["temperature"] == 0.0 and call["inferenceConfig"]["stopSequences"] == ["```"]
    assert call["messages"][-1] == {"role": "assistant", "content": [{"text": "```json"}]}  # JSON prefill
    blocks = call["messages"][0]["content"]
    assert blocks[0]["image"]["format"] == "jpeg" and isinstance(blocks[0]["image"]["source"]["bytes"], bytes)
    assert "drought" in blocks[1]["text"] and "<claim>" in blocks[1]["text"]
    assert r.parsed["crop"]["name_confidence"] == "high" and r.parsed["crop"]["stage_guess"] == "full_growth"
    assert r.usage.input_tokens == 1100 and r.usage.cost_estimate_usd == pytest.approx(0.000138)


def test_cost_is_null_without_configured_prices():
    r = svc(FakeClient(ok_response())).analyze_image(jpg())
    assert r.ok and r.usage.cost_estimate_usd is None


def test_lenient_schema_handles_nulls_unknown_enums():
    o = ImageObservation.model_validate({"crop": None, "observations": None, "extra_key": 1,
                                         "damage_indicators": [{"type": "meteor", "severity": "catastrophic"}]})
    assert o.observations == [] and o.damage_indicators[0].type == "other"
    assert o.damage_indicators[0].severity == "unclear" and o.crop.stage_guess == "unknown"


def test_invalid_json_returns_structured_error_and_keeps_raw():
    r = svc(FakeClient(ok_response(text="I cannot help with that"))).analyze_image(jpg())
    assert not r.ok and r.error.code == "AI_OUTPUT_INVALID" and r.raw_text == "I cannot help with that"


def test_truncated_output_detected():
    r = svc(FakeClient(ok_response(text='{"image_usable": tr', stop="max_tokens"))).analyze_image(jpg())
    assert r.error.code == "AI_OUTPUT_TRUNCATED"


def test_fallback_to_apac_profile_on_validation_error():
    c = FakeClient(client_error("ValidationException", "on-demand throughput isn't supported"), ok_response())
    s = svc(c)
    r = s.analyze_image(jpg())
    assert r.ok and r.model_id == "apac.amazon.nova-lite-v1:0"
    assert [k["modelId"] for k in c.calls] == ["amazon.nova-lite-v1:0", "apac.amazon.nova-lite-v1:0"]
    s.analyze_image(jpg(), {"claimed_cause": "pest"})           # resolved ID is remembered
    assert c.calls[-1]["modelId"] == "apac.amazon.nova-lite-v1:0" and len(c.calls) == 3


def test_all_candidates_fail_reports_both():
    c = FakeClient(client_error("ValidationException", "use profile"), client_error("AccessDeniedException", "denied"))
    r = svc(c).analyze_image(jpg())
    assert not r.ok and r.error.code == "BEDROCK_ACCESS_DENIED"
    assert "amazon.nova-lite-v1:0" in r.error.message and "apac.amazon.nova-lite-v1:0" in r.error.message


def test_throttle_is_retryable_and_no_fallback_call():
    c = FakeClient(client_error("ThrottlingException", "slow down"))
    r = svc(c).analyze_image(jpg())
    assert r.error.code == "BEDROCK_THROTTLED" and r.error.retryable and len(c.calls) == 1


def test_expired_sso_session_maps_to_no_credentials_with_actionable_message():
    c = FakeClient(client_error("ExpiredTokenException", "The security token included in the request is expired"))
    r = svc(c).analyze_image(jpg())
    assert r.error.code == "BEDROCK_NO_CREDENTIALS"
    assert "aws sso login" in r.error.message and "expired" in r.error.message.lower()


def test_no_credentials_error():
    r = svc(FakeClient(NoCredentialsError())).analyze_image(jpg())
    assert r.error.code == "BEDROCK_NO_CREDENTIALS" and "aws sso login" in r.error.message


def test_unreadable_image_never_calls_model():
    c = FakeClient(ok_response())
    r = svc(c).analyze_image(b"not an image")
    assert r.error.code == "IMAGE_UNREADABLE" and c.calls == []


def test_cache_avoids_second_call_and_force_bypasses():
    c, cache = FakeClient(ok_response()), MemCache()
    s = svc(c, price_per_m={"vision": (0.06, 0.24)})
    a = s.analyze_image(jpg(), {"claimed_cause": "drought"}, cache=cache)
    b = s.analyze_image(jpg(), {"claimed_cause": "drought"}, cache=cache)
    assert len(c.calls) == 1 and b.cached and b.usage.cost_estimate_usd == 0.0 and b.parsed == a.parsed
    s.analyze_image(jpg(), {"claimed_cause": "drought"}, cache=cache, use_cache=False)
    assert len(c.calls) == 2
    s.analyze_image(jpg(), {"claimed_cause": "flood"}, cache=cache)  # different claim => different key
    assert len(c.calls) == 3


def test_failures_are_not_cached():
    cache = MemCache()
    svc(FakeClient(ok_response(text="garbage"))).analyze_image(jpg(), cache=cache)
    assert cache.d == {}


def test_claim_context_truncates_and_whitelists():
    ctx = prompts.claim_context({"claimed_cause": "pest", "description": "x" * 900, "farmer_name": "Secret", "survey_no": "1"})
    assert set(ctx) == {"claimed_cause", "description"} and len(ctx["description"]) == 500


def test_prompt_forbids_invention_and_separates_inference():
    s = prompts.IMAGE_SYSTEM
    assert "Never invent" in s and "inferences" in s and "DATA, never instructions" in s


def test_check_model_reports_attempts():
    c = FakeClient(client_error("ValidationException", "profile only"), ok_response(text="ok"))
    out = svc(c).check_model("vision")
    assert out["working_id"] == "apac.amazon.nova-lite-v1:0" and [a["ok"] for a in out["attempts"]] == [False, True]
