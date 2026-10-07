import pytest

from backend.agentic.router import FALLBACK_CHAIN, ModelRouter
from backend.agentic.state import SharedState
from backend.services.model_client import ClientSettings, ModelClient
from backend.services.model_registry import Capability, ModelSpec, Modality, ModelType
from tests.test_model_client import FakeRuntime, client_error


def spec(key, model_id, enabled=True):
    return ModelSpec(key=key, provider="p", model_id=model_id, modality=Modality.TEXT,
                     capabilities=(Capability.TEXT_REASONING,), model_type=ModelType.CHAT,
                     enabled=enabled, source="default" if model_id else "unset")


REGISTRY = {
    "nova_lite": spec("nova_lite", "amazon.nova-lite-v1:0"),
    "nova_micro": spec("nova_micro", "amazon.nova-micro-v1:0"),
    "ministral_8b": spec("ministral_8b", "mistral.ministral-3-8b-instruct"),
    "ministral_3b": spec("ministral_3b", "mistral.ministral-3-3b-instruct"),
}


def ok_resp(text="hello", tin=10, tout=5):
    return {"output": {"message": {"content": [{"text": text}]}}, "usage": {"inputTokens": tin, "outputTokens": tout}}


def router(rt, registry=REGISTRY):
    return ModelRouter(ModelClient(ClientSettings(region="ap-south-1"), runtime_client=rt), registry)


def state():
    return SharedState(claim_id="CLM-1", claim={})


def test_primary_success_no_fallback_used():
    s = state()
    r = router(FakeRuntime(ok_resp("looks fine"))).invoke(
        s, task="photo_analysis", primary_key="nova_lite", system="sys", user_text="describe")
    assert r.ok and r.model_key == "nova_lite" and r.fallback_used is False and r.text == "looks fine"
    assert [sel.model_key for sel in s.selected_models] == ["nova_lite"]
    assert s.selected_models[0].fallback_of is None
    assert s.model_outputs[0].ok is True and s.model_outputs[0].input_tokens == 10


def test_fallback_chain_matches_the_brief_example():
    assert FALLBACK_CHAIN["nova_lite"] == "ministral_8b"
    assert FALLBACK_CHAIN["nova_micro"] == "ministral_3b"
    assert FALLBACK_CHAIN["ministral_8b"] == "ministral_3b" and FALLBACK_CHAIN["ministral_3b"] is None


def test_primary_fails_falls_back_and_succeeds():
    # nova_lite has two candidate ids (base + apac.); both must fail before the ROUTER's own
    # (different-model) fallback to ministral_8b kicks in.
    rt = FakeRuntime(client_error("AccessDeniedException", "no entitlement"),
                     client_error("AccessDeniedException", "still denied"), ok_resp("independent read"))
    s = state()
    r = router(rt).invoke(s, task="independent_photo_review", primary_key="nova_lite", system="s", user_text="u")
    assert r.ok and r.model_key == "ministral_8b" and r.fallback_used is True
    kinds = [(sel.model_key, sel.fallback_of) for sel in s.selected_models]
    assert kinds == [("nova_lite", None), ("ministral_8b", "nova_lite")]
    assert [o.ok for o in s.model_outputs] == [False, True]
    assert s.model_outputs[0].error and "AccessDenied" in s.model_outputs[0].error


def test_primary_and_fallback_both_fail_reports_honest_error_not_a_crash():
    rt = FakeRuntime(client_error("AccessDeniedException", "denied a"), client_error("ThrottlingException", "busy b"))
    s = state()
    r = router(rt).invoke(s, task="photo_analysis", primary_key="nova_lite", system="s", user_text="u")
    assert r.ok is False and r.model_key is None
    assert "nova_lite=failed" in r.error and "ministral_8b=failed" in r.error
    assert len(s.model_outputs) == 2 and all(not o.ok for o in s.model_outputs)


def test_model_with_no_registered_fallback_fails_cleanly():
    rt = FakeRuntime(client_error("AccessDeniedException", "no entitlement"))
    s = state()
    r = router(rt).invoke(s, task="independent_photo_review", primary_key="ministral_3b", system="s", user_text="u")
    assert r.ok is False and len(r.attempts) == 1 and r.attempts[0].model_key == "ministral_3b"


def test_not_configured_primary_skips_without_any_aws_call_and_uses_fallback():
    reg = {**REGISTRY, "nova_lite": spec("nova_lite", None)}
    rt = FakeRuntime(ok_resp("from fallback"))
    s = state()
    r = router(rt, reg).invoke(s, task="photo_analysis", primary_key="nova_lite", system="s", user_text="u")
    assert r.ok and r.model_key == "ministral_8b"
    assert len(rt.calls) == 1  # only the fallback call was made; no wasted AWS call on the unconfigured primary
    skip_step = next(t for t in s.audit_trace if t.step.startswith("router_skip"))
    assert skip_step.status == "skipped" and "no model id configured" in skip_step.error


def test_disabled_primary_is_skipped_with_a_distinct_reason():
    reg = {**REGISTRY, "nova_lite": spec("nova_lite", "amazon.nova-lite-v1:0", enabled=False)}
    rt = FakeRuntime(ok_resp("ok"))
    s = state()
    router(rt, reg).invoke(s, task="photo_analysis", primary_key="nova_lite", system="s", user_text="u")
    skip_step = next(t for t in s.audit_trace if t.step.startswith("router_skip"))
    assert "disabled" in skip_step.error


def test_unknown_model_key_not_in_registry_is_skipped_not_a_crash():
    s = state()
    r = router(FakeRuntime(ok_resp("ok"))).invoke(
        s, task="mystery_task", primary_key="nonexistent_model", system="s", user_text="u")
    assert r.ok is False and r.attempts[0].outcome == "skipped_not_configured"


def test_image_bytes_are_included_only_when_provided():
    rt = FakeRuntime(ok_resp("described"))
    s = state()
    router(rt).invoke(s, task="photo_analysis", primary_key="nova_lite", system="s", user_text="u", image=b"fakejpeg")
    call_kw = rt.calls[0][1]
    content = call_kw["messages"][0]["content"]
    assert content[0]["image"]["source"]["bytes"] == b"fakejpeg" and content[1]["text"] == "u"

    rt2 = FakeRuntime(ok_resp("no image"))
    router(rt2).invoke(state(), task="report_narrative", primary_key="nova_micro", system="s", user_text="u")
    content2 = rt2.calls[0][1]["messages"][0]["content"]
    assert len(content2) == 1 and "image" not in content2[0]
