import json

import pytest
from botocore.exceptions import ClientError

from backend.dataset import db
from backend.repositories import model_health as repo
from backend.services.model_client import ClientSettings, ModelClient
from backend.services.model_health import Availability, check_all, check_model
from backend.services.model_registry import ModelSpec, Modality, Capability, ModelType
from backend.storage.schema import init_model_health_schema
from tests.test_model_client import FakeBody, FakeRuntime, client_error


def chat_spec(key="nova_lite", model_id="amazon.nova-lite-v1:0", enabled=True):
    return ModelSpec(key=key, provider="amazon", model_id=model_id, modality=Modality.TEXT_AND_IMAGE,
                     capabilities=(Capability.VISION,), model_type=ModelType.CHAT, enabled=enabled,
                     source="default" if model_id else "unset")


def embed_spec(model_id="amazon.titan-embed-text-v2:0", enabled=True):
    return ModelSpec(key="titan_embed_v2", provider="amazon", model_id=model_id, modality=Modality.EMBEDDING,
                     capabilities=(Capability.EMBEDDINGS,), model_type=ModelType.EMBEDDING, enabled=enabled,
                     source="default" if model_id else "unset")


class NoOpControl:
    def get_foundation_model(self, modelIdentifier):
        raise client_error("AccessDeniedException", "no list permission")


def client(runtime):
    return ModelClient(ClientSettings(region="ap-south-1"), runtime_client=runtime, control_client=NoOpControl())


def test_disabled_model_is_never_invoked():
    r = check_model(client(FakeRuntime({"output": {"message": {"content": []}}})), chat_spec(enabled=False))
    assert r.availability is Availability.DISABLED and r.attempts == []


def test_not_configured_model_is_never_invoked():
    spec = chat_spec(model_id=None)
    r = check_model(client(FakeRuntime({"output": {"message": {"content": []}}})), spec)
    assert r.availability is Availability.NOT_CONFIGURED and r.attempts == []


def test_invokable_chat_model_records_latency_and_resolved_id():
    rt = FakeRuntime({"output": {"message": {"content": [{"text": '{"ok": true}'}]}}})
    r = check_model(client(rt), chat_spec())
    assert r.availability is Availability.INVOKABLE and r.model_id == "amazon.nova-lite-v1:0"
    assert r.latency_ms is not None and r.latency_ms >= 0
    assert r.error_code is None and r.catalog_visible is None  # control client denies -> unknown, not False


def test_invocation_failed_records_real_error_not_generic():
    rt = FakeRuntime(client_error("AccessDeniedException", "model not entitled"))
    r = check_model(client(rt), chat_spec(key="ministral_8b", model_id="mistral.ministral-8b-2410-v1:0"))
    assert r.availability is Availability.INVOCATION_FAILED
    assert r.error_code == "BEDROCK_ACCESS_DENIED" and "not entitled" in r.error_message


def test_catalog_not_configured_never_reported_as_invocation_failed():
    r = check_model(client(FakeRuntime({})), chat_spec(model_id=None))
    assert r.availability is Availability.NOT_CONFIGURED
    assert r.availability is not Availability.INVOCATION_FAILED


def test_embedding_model_uses_invoke_model_not_converse():
    rt = FakeRuntime({"body": FakeBody({"embedding": [0.1, 0.2]})})
    r = check_model(client(rt), embed_spec())
    assert r.availability is Availability.INVOKABLE
    assert rt.calls[0][0] == "invoke_model"


def test_check_all_covers_every_registry_entry_in_order():
    registry = {"nova_lite": chat_spec(), "titan_embed_v2": embed_spec(model_id=None)}
    rt = FakeRuntime({"output": {"message": {"content": [{"text": "ok"}]}}})
    results = check_all(client(rt), registry)
    assert [r.model_key for r in results] == ["nova_lite", "titan_embed_v2"]
    assert results[0].availability is Availability.INVOKABLE
    assert results[1].availability is Availability.NOT_CONFIGURED


def test_health_results_persist_with_task_model_status_latency_error_timestamp():
    rt = FakeRuntime(client_error("ValidationException", "bad request"))
    results = [check_model(client(rt), chat_spec(model_id="mistral.ministral-3b-2410-v1:0"))]
    conn = db.connect(":memory:")
    init_model_health_schema(conn)
    ids = repo.record_all(conn, results)
    assert len(ids) == 1
    row = repo.latest(conn, limit=1)[0]
    assert row["task"] == "model_health:nova_lite" and row["model_id"]
    assert row["availability"] == "invocation_failed" and row["error_code"] == "BEDROCK_VALIDATION"
    assert row["latency_ms"] is not None and row["checked_at"]
    assert json.loads(row["attempts_json"])[0]["ok"] is False


def test_latest_per_model_keeps_only_the_newest_row_per_key():
    conn = db.connect(":memory:")
    init_model_health_schema(conn)
    rt_fail = FakeRuntime(client_error("AccessDeniedException", "no"))
    rt_ok = FakeRuntime({"output": {"message": {"content": [{"text": "ok"}]}}})
    repo.record(conn, check_model(client(rt_fail), chat_spec()))
    repo.record(conn, check_model(client(rt_ok), chat_spec()))
    latest = repo.latest_per_model(conn)
    assert len(latest) == 1 and latest[0]["availability"] == "invokable"
