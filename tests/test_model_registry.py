import pytest

from backend.services.model_registry import Capability, ModelType, build_registry


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # Hermetic: build_registry() reads .env via load_dotenv(); a developer's real .env (e.g. one that
    # already sets BEDROCK_VISION_MODEL_ID=apac.amazon.nova-lite-v1:0) must not change what these
    # tests assert about the built-in DEFAULTS.
    monkeypatch.setattr("backend.services.model_registry.load_dotenv", lambda *a, **k: None)
    for k in ("BEDROCK_VISION_MODEL_ID", "BEDROCK_TEXT_MODEL_ID", "MINISTRAL_3B_MODEL_ID",
             "MINISTRAL_8B_MODEL_ID", "TITAN_EMBED_MODEL_ID", "MODEL_NOVA_LITE_ENABLED",
             "MODEL_NOVA_MICRO_ENABLED", "MODEL_MINISTRAL_3B_ENABLED", "MODEL_MINISTRAL_8B_ENABLED",
             "MODEL_TITAN_EMBED_ENABLED"):
        monkeypatch.delenv(k, raising=False)


def test_default_registry_has_six_models_with_confirmed_ids():
    reg = build_registry()
    assert set(reg) == {"nova_lite", "nova_micro", "ministral_3b", "ministral_8b",
                        "titan_embed_v2", "titan_embed_image_v1"}
    assert reg["nova_lite"].model_id == "amazon.nova-lite-v1:0" and reg["nova_lite"].source == "default"
    assert reg["nova_micro"].model_id == "amazon.nova-micro-v1:0"
    assert reg["titan_embed_v2"].model_id == "amazon.titan-embed-text-v2:0"
    assert reg["titan_embed_image_v1"].model_id == "amazon.titan-embed-image-v1"


def test_ministral_models_have_confirmed_ids_from_aws_docs():
    reg = build_registry()
    assert reg["ministral_3b"].model_id == "mistral.ministral-3-3b-instruct"
    assert reg["ministral_8b"].model_id == "mistral.ministral-3-8b-instruct"
    for key in ("ministral_3b", "ministral_8b"):
        assert reg[key].configured is True and reg[key].source == "default"
        assert reg[key].enabled is True


def test_env_var_overrides_model_id_and_source(monkeypatch):
    monkeypatch.setenv("MINISTRAL_3B_MODEL_ID", "mistral.ministral-3b-2410-v1:0")
    monkeypatch.setenv("BEDROCK_VISION_MODEL_ID", "amazon.nova-lite-v2:0")
    reg = build_registry()
    assert reg["ministral_3b"].model_id == "mistral.ministral-3b-2410-v1:0"
    assert reg["ministral_3b"].source == "env" and reg["ministral_3b"].configured
    assert reg["nova_lite"].model_id == "amazon.nova-lite-v2:0" and reg["nova_lite"].source == "env"


@pytest.mark.parametrize("flag,key", [
    ("MODEL_NOVA_LITE_ENABLED", "nova_lite"),
    ("MODEL_MINISTRAL_3B_ENABLED", "ministral_3b"),
    ("MODEL_TITAN_EMBED_ENABLED", "titan_embed_v2"),
])
def test_disable_flag_turns_off_a_model(monkeypatch, flag, key):
    monkeypatch.setenv(flag, "false")
    assert build_registry()[key].enabled is False


def test_capabilities_and_types_reflect_real_modality():
    reg = build_registry()
    assert Capability.VISION in reg["nova_lite"].capabilities and reg["nova_lite"].model_type is ModelType.CHAT
    assert reg["nova_micro"].model_type is ModelType.CHAT and Capability.VISION not in reg["nova_micro"].capabilities
    assert reg["titan_embed_v2"].model_type is ModelType.EMBEDDING
    assert Capability.EMBEDDINGS in reg["titan_embed_v2"].capabilities
    assert Capability.TEXT_REASONING in reg["ministral_3b"].capabilities
