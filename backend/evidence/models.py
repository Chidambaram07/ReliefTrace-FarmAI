"""Uniform evidence record. Every evidence item states who said it, when, where, how good it is, and how to trace it."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SourceKind = Literal["claim", "source_data", "ai_observation", "external_evidence", "derived"]
Quality = Literal["high", "medium", "low", "unavailable"]
QUALITY_SCORE = {"high": 1.0, "medium": 0.66, "low": 0.33}


class Location(BaseModel):
    lat: float
    lon: float
    label: Optional[str] = None


class EvidenceItem(BaseModel):
    evidence_id: str = ""
    source: str = Field(..., description="Who/what produced this, e.g. 'FarmwiseAI ground-truth CSV'")
    source_kind: SourceKind
    evidence_type: str              # crop_metadata | gps_location | administrative_boundary | timestamp | weather | ai_image_observation | disaster_event
    timestamp: Optional[str] = None  # when the evidence refers to (ISO) - not when it was collected
    location: Optional[Location] = None
    observation: str                # plain-language fact
    data: dict[str, Any] = {}       # machine-readable values used by the verification rules
    quality: Quality = "medium"
    status: Literal["available", "unavailable"] = "available"
    limitations: list[str] = []
    raw_reference: Any = None       # record ids / URL / file name so a reviewer can trace it


def unavailable(source: str, evidence_type: str, reason: str, kind: SourceKind = "external_evidence", **kw) -> EvidenceItem:
    return EvidenceItem(source=source, source_kind=kind, evidence_type=evidence_type, observation=reason,
                        quality="unavailable", status="unavailable", limitations=[reason], **kw)
