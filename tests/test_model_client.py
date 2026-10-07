import io
import json

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from backend.services.model_client import (
    BedrockError, ClientSettings, ModelClient, candidate_ids, translate_exception,
)


def client_error(code, msg="nope"):
    return ClientError({"Error": {"Code": code, "Message": msg}}, "Converse")


class FakeRuntime:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def converse(self, **kw):
        self.calls.append(("converse", kw))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r

    def invoke_model(self, **kw):
        self.calls.append(("invoke_model", kw))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


class FakeBody:
    def __init__(self, obj):
        self._obj = obj

    def read(self):
        return json.dumps(self._obj).encode()


def mc(runtime):
    return ModelClient(ClientSettings(region="ap-south-1"), runtime_client=runtime)


def test_candidate_ids_adds_apac_profile_generically():
    assert candidate_ids("amazon.nova-lite-v1:0") == ["amazon.nova-lite-v1:0", "apac.amazon.nova-lite-v1:0"]
    assert candidate_ids("mistral.ministral-3b-2410-v1:0") == [
        "mistral.ministral-3b-2410-v1:0", "apac.mistral.ministral-3b-2410-v1:0"]
    assert candidate_ids("apac.amazon.nova-lite-v1:0") == ["apac.amazon.nova-lite-v1:0"]


def test_converse_success_returns_response_and_resolved_id():
    rt = FakeRuntime({"output": {"message": {"content": [{"text": "hi"}]}}})
    resp, used = mc(rt).converse(["amazon.nova-micro-v1:0"], {"messages": []})
    assert used == "amazon.nova-micro-v1:0" and resp["output"]["message"]["content"][0]["text"] == "hi"
    assert rt.calls[0] == ("converse", {"modelId": "amazon.nova-micro-v1:0", "messages": []})


def test_converse_falls_back_on_validation_exception_only():
    rt = FakeRuntime(client_error("ValidationException", "use profile"),
                     {"output": {"message": {"content": []}}})
    attempts = []
    resp, used = mc(rt).converse(candidate_ids("amazon.nova-lite-v1:0"), {"messages": []}, attempts=attempts)
    assert used == "apac.amazon.nova-lite-v1:0"
    assert [a["ok"] for a in attempts] == [False, True]


def test_converse_does_not_fall_back_on_throttling():
    rt = FakeRuntime(client_error("ThrottlingException", "slow down"))
    with pytest.raises(BedrockError) as ei:
        mc(rt).converse(candidate_ids("amazon.nova-lite-v1:0"), {"messages": []})
    assert ei.value.code == "BEDROCK_THROTTLED" and len(rt.calls) == 1  # never tried the apac. id


def test_converse_all_candidates_fail_merges_messages():
    rt = FakeRuntime(client_error("ValidationException", "a"), client_error("AccessDeniedException", "b"))
    with pytest.raises(BedrockError) as ei:
        mc(rt).converse(candidate_ids("amazon.nova-lite-v1:0"), {"messages": []})
    assert ei.value.code == "BEDROCK_ACCESS_DENIED"
    assert "amazon.nova-lite-v1:0" in ei.value.message and "apac.amazon.nova-lite-v1:0" in ei.value.message


def test_invoke_embedding_success_parses_body():
    rt = FakeRuntime({"body": FakeBody({"embedding": [0.1, 0.2, 0.3], "inputTextTokenCount": 4})})
    payload, used = mc(rt).invoke_embedding(["amazon.titan-embed-text-v2:0"], "hello")
    assert used == "amazon.titan-embed-text-v2:0" and len(payload["embedding"]) == 3
    call = rt.calls[0]
    assert call[0] == "invoke_model" and json.loads(call[1]["body"]) == {"inputText": "hello"}


def test_invoke_embedding_failure_maps_error():
    rt = FakeRuntime(client_error("AccessDeniedException", "no entitlement"))
    with pytest.raises(BedrockError) as ei:
        mc(rt).invoke_embedding(["amazon.titan-embed-text-v2:0"], "hello")
    assert ei.value.code == "BEDROCK_ACCESS_DENIED"


def test_translate_exception_covers_no_credentials_and_network():
    assert translate_exception(NoCredentialsError()).code == "BEDROCK_NO_CREDENTIALS"

    class FakeTimeout(Exception):
        pass
    FakeTimeout.__name__ = "ReadTimeoutError"
    err = translate_exception(FakeTimeout("slow"))
    assert err.code == "BEDROCK_NETWORK" and err.retryable


def test_translate_exception_expired_token_is_actionable():
    err = translate_exception(client_error("ExpiredTokenException", "token is expired"))
    assert err.code == "BEDROCK_NO_CREDENTIALS" and "aws sso login" in err.message.lower()


def test_is_catalog_visible_true_false_and_unknown():
    class Control:
        def __init__(self, behavior):
            self.behavior = behavior

        def get_foundation_model(self, modelIdentifier):
            if self.behavior == "found":
                return {"modelDetails": {}}
            if self.behavior == "not_found":
                raise client_error("ResourceNotFoundException", "no such model")
            raise client_error("AccessDeniedException", "no list permission")

    c1 = ModelClient(ClientSettings(region="ap-south-1"), control_client=Control("found"))
    c2 = ModelClient(ClientSettings(region="ap-south-1"), control_client=Control("not_found"))
    c3 = ModelClient(ClientSettings(region="ap-south-1"), control_client=Control("denied"))
    assert c1.is_catalog_visible("x") is True
    assert c2.is_catalog_visible("x") is False
    assert c3.is_catalog_visible("x") is None  # denial to LIST must not be read as "unavailable to invoke"
