"""Model capability registry.

Declares every model ReliefTrace knows how to call and what it's for. This is metadata only -
it says nothing about whether a model can ACTUALLY be invoked on this AWS account; that is what
model_health.py determines by making a real (minimal) call. Catalog presence, an env var being
set, and a successful invocation are three different, explicitly distinguished things (see
Availability below) - a model appearing in the Bedrock console is not permission to use it.

Model ids for Nova and Titan are fixed (well-documented, stable Bedrock ids). The two Ministral
models have NO default id: their exact Bedrock model id was not confirmed in this project, only
the mentor's statement that the family is available. Leaving MINISTRAL_*_MODEL_ID unset keeps
them correctly reported as "not_configured" rather than guessing an id and reporting a fabricated
result either way.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from backend.config import load_dotenv

ALLOWED_REGION = "ap-south-1"


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    TEXT_AND_IMAGE = "text+image"
    EMBEDDING = "embedding"


class Capability(str, Enum):
    VISION = "vision"
    TEXT_REASONING = "text_reasoning"
    CLASSIFICATION = "classification"
    EMBEDDINGS = "embeddings"
    NARRATIVE_GENERATION = "narrative_generation"


class ModelType(str, Enum):
    CHAT = "chat"          # invoked via the Converse API
    EMBEDDING = "embedding"  # invoked via InvokeModel


@dataclass(frozen=True)
class ModelSpec:
    key: str                       # stable internal name, e.g. "nova_lite"
    provider: str                  # "amazon" | "mistral" | ...
    model_id: str | None           # Bedrock model id, or None if not configured
    modality: Modality
    capabilities: tuple[Capability, ...]
    model_type: ModelType
    enabled: bool                  # operator opt-out, independent of whether it's configured
    source: str                    # where model_id came from: "default" | "env" | "unset"
    notes: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.model_id)


def _env_bool(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() not in ("0", "false", "no", "off")


def _model_id(env: str, default: str | None) -> tuple[str | None, str]:
    v = os.environ.get(env)
    if v is not None and v.strip():
        return v.strip(), "env"
    if default:
        return default, "default"
    return None, "unset"


def build_registry() -> dict[str, ModelSpec]:
    load_dotenv()
    specs: list[ModelSpec] = []

    vlid, vsrc = _model_id("BEDROCK_VISION_MODEL_ID", "amazon.nova-lite-v1:0")
    specs.append(ModelSpec(
        key="nova_lite", provider="amazon", model_id=vlid, modality=Modality.TEXT_AND_IMAGE,
        capabilities=(Capability.VISION, Capability.TEXT_REASONING), model_type=ModelType.CHAT,
        enabled=_env_bool("MODEL_NOVA_LITE_ENABLED", True), source=vsrc,
        notes="Confirmed invokable in this account via the 'apac.' cross-region profile "
              "(on-demand throughput for the base id is not supported in ap-south-1)."))

    tlid, tsrc = _model_id("BEDROCK_TEXT_MODEL_ID", "amazon.nova-micro-v1:0")
    specs.append(ModelSpec(
        key="nova_micro", provider="amazon", model_id=tlid, modality=Modality.TEXT,
        capabilities=(Capability.TEXT_REASONING, Capability.NARRATIVE_GENERATION), model_type=ModelType.CHAT,
        enabled=_env_bool("MODEL_NOVA_MICRO_ENABLED", True), source=tsrc,
        notes="Confirmed invokable in this account via the 'apac.' cross-region profile."))

    # Ids below are copied verbatim from AWS's own "Programmatic Access" table for each model in
    # the Bedrock User Guide (not guessed). Both models' docs state Geo/Global inference profile =
    # "Not supported", so unlike Nova there is no "apac." cross-region id to fall back to - the
    # base id is invoked directly. That is a documentation fact, not an invocation result: neither
    # id has been health-checked against this account yet (see model_health.py for that).
    m3id, m3src = _model_id("MINISTRAL_3B_MODEL_ID", "mistral.ministral-3-3b-instruct")
    specs.append(ModelSpec(
        key="ministral_3b", provider="mistral", model_id=m3id, modality=Modality.TEXT,
        capabilities=(Capability.TEXT_REASONING, Capability.CLASSIFICATION), model_type=ModelType.CHAT,
        enabled=_env_bool("MODEL_MINISTRAL_3B_ENABLED", True), source=m3src,
        notes="Model id from AWS Bedrock User Guide (Programmatic Access table); no cross-region "
              "inference profile exists for this model. NOT YET invocation-confirmed for this "
              "account - run scripts/check_models.py to get a real invokable/invocation_failed result."))

    m8id, m8src = _model_id("MINISTRAL_8B_MODEL_ID", "mistral.ministral-3-8b-instruct")
    specs.append(ModelSpec(
        key="ministral_8b", provider="mistral", model_id=m8id, modality=Modality.TEXT,
        capabilities=(Capability.TEXT_REASONING, Capability.CLASSIFICATION), model_type=ModelType.CHAT,
        enabled=_env_bool("MODEL_MINISTRAL_8B_ENABLED", True), source=m8src,
        notes="Model id from AWS Bedrock User Guide (Programmatic Access table); no cross-region "
              "inference profile exists for this model. NOT YET invocation-confirmed for this "
              "account - run scripts/check_models.py to get a real invokable/invocation_failed result."))

    teid, tesrc = _model_id("TITAN_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
    specs.append(ModelSpec(
        key="titan_embed_v2", provider="amazon", model_id=teid, modality=Modality.EMBEDDING,
        capabilities=(Capability.EMBEDDINGS,), model_type=ModelType.EMBEDDING,
        enabled=_env_bool("MODEL_TITAN_EMBED_ENABLED", True), source=tesrc,
        notes="Confirmed invokable in this account (base id, no cross-region profile needed)."))

    tmid, tmsrc = _model_id("TITAN_MULTIMODAL_EMBED_MODEL_ID", "amazon.titan-embed-image-v1")
    specs.append(ModelSpec(
        key="titan_embed_image_v1", provider="amazon", model_id=tmid, modality=Modality.TEXT_AND_IMAGE,
        capabilities=(Capability.EMBEDDINGS,), model_type=ModelType.EMBEDDING,
        enabled=_env_bool("MODEL_TITAN_MULTIMODAL_EMBED_ENABLED", True), source=tmsrc,
        notes="Confirmed invokable in this account; returned a 256-dim image embedding for a real "
              "crop photo. Not yet used by any pipeline step (registered for the image-retrieval tool)."))

    return {s.key: s for s in specs}
