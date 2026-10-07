"""Schemas for AI output. Everything produced by a model is an OBSERVATION, never ground truth."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIDENCE = ("none", "low", "medium", "high")
SEVERITY = ("none", "mild", "moderate", "severe", "unclear")
STAGES = ("bare_soil_or_fallow", "sown", "vegetation", "flowering", "full_growth", "harvesting", "unknown")
DAMAGE_TYPES = ("drought_stress", "flooding_waterlogging", "lodging_storm_damage", "pest_damage",
                "disease_symptoms", "hail_damage", "fire_burn", "nutrient_deficiency", "none_visible", "other")


def _norm(v: Any) -> str:
    return str(v).strip().lower().replace(" ", "_").replace("-", "_") if v is not None else ""


class Lenient(BaseModel):
    """Model output is imperfect: nulls become defaults and unknown keys are ignored."""
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data):
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class CropObservation(Lenient):
    crop_visible: bool = False
    name_guess: Optional[str] = None
    name_confidence: str = "none"
    stage_guess: str = "unknown"
    stage_confidence: str = "none"

    @field_validator("name_confidence", "stage_confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        v = _norm(v)
        return v if v in CONFIDENCE else "low"

    @field_validator("stage_guess", mode="before")
    @classmethod
    def _stage(cls, v):
        v = _norm(v)
        return v if v in STAGES else "unknown"


class DamageIndicator(Lenient):
    type: str = "other"
    visible: bool = False
    description: str = ""
    severity: str = "unclear"
    confidence: str = "low"

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v):
        v = _norm(v)
        return v if v in DAMAGE_TYPES else "other"

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v):
        v = _norm(v)
        return v if v in SEVERITY else "unclear"

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        v = _norm(v)
        return v if v in CONFIDENCE else "low"


class Inference(Lenient):
    statement: str
    basis: str = ""


class ClaimAssessment(Lenient):
    supports: list[str] = []
    contradicts: list[str] = []
    cannot_determine: list[str] = []


class ImageObservation(Lenient):
    image_usable: bool = True
    quality_issues: list[str] = []
    observations: list[str] = []          # directly visible facts only
    crop: CropObservation = CropObservation()
    damage_indicators: list[DamageIndicator] = []
    inferences: list[Inference] = []      # interpretation, kept apart from observations
    claim_assessment: ClaimAssessment = ClaimAssessment()
    missing_information: list[str] = []
    limitations: list[str] = []


class AIUsage(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    cost_estimate_usd: Optional[float] = Field(None, description="Estimate from configured list prices; null if unset")


class AIError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class AIResult(BaseModel):
    ok: bool
    role: str
    model_id: Optional[str] = None
    prompt_version: str
    cached: bool = False
    parsed: Optional[dict] = None
    raw_text: Optional[str] = None
    usage: AIUsage = AIUsage()
    error: Optional[AIError] = None
    label: str = "AI observation - not ground truth"
