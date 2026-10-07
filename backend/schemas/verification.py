from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel

from backend.evidence.models import EvidenceItem

S_SUPPORTED = "Supported by available evidence"
S_PARTIAL = "Partially supported"
S_CONTRA = "Contradictory evidence found"
S_INSUFF = "Insufficient evidence"
S_FURTHER = "Requires further verification"
STATUSES = (S_SUPPORTED, S_PARTIAL, S_CONTRA, S_INSUFF, S_FURTHER)

Verdict = Literal["supports", "contradicts", "inconclusive", "missing"]


class Finding(BaseModel):
    check_id: str
    title: str
    verdict: Verdict
    severity: Optional[Literal["medium", "high"]] = None   # only for contradictions
    detail: str
    evidence_ids: list[str] = []
    weight: float                                        # 0 = not applicable to this claim
    independent: bool                                    # False if it rests only on the claimant or on AI reading
    rule: str
    limitations: list[str] = []


class Scores(BaseModel):
    confidence_index: float
    evidence_quality: float
    coverage: float
    agreement: float
    evidence_consistency_index: float = 0.0
    breakdown: list[dict] = []
    formula: str = (
        "confidence_index (legacy) = 100 x coverage x agreement x evidence_quality, kept for compatibility. "
        "evidence_consistency_index is the additive, per-check figure to prefer: each applicable check has "
        "max_points = 100 x its weight / total weight (so max points sum to 100), and earns "
        "max_points x verdict_factor x evidence_quality where verdict_factor is 1.0 supports / 0.5 inconclusive "
        "/ 0.0 missing or contradicts (a contradiction earns no points here; it is shown separately in "
        "'contradictions' and already drives 'status'). See 'breakdown' for the per-check figures. This is a "
        "transparent measure of ACCUMULATED CONSISTENT EVIDENCE, NOT a probability of fraud, of damage, or of anything else.")


class Routing(BaseModel):
    human_review_required: bool
    reasons: list[str]
    queue_status: Optional[str] = None


class AuditStep(BaseModel):
    step: str
    agent: str
    model: Optional[str] = None
    status: str
    duration_ms: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_estimate_usd: Optional[float] = None
    detail: Optional[str] = None


class Narrative(BaseModel):
    source: Literal["template", "ai", "off"]
    summary: str
    key_points: list[str] = []
    recommended_actions: list[str] = []


class VerificationReport(BaseModel):
    claim_id: str
    generated_at: str
    status: str
    status_reason: str
    claim: dict
    plan: dict
    evidence: list[EvidenceItem]
    findings: list[Finding]
    supporting: list[str]
    contradictions: list[str]
    missing_evidence: list[str]
    limitations: list[str]
    scores: Scores
    routing: Routing
    timeline: list[dict]
    narrative: Narrative
    audit: list[AuditStep]
    rules_applied: dict[str, Any]
    provenance_legend: dict[str, str] = {
        "claim": "Submitted by the claimant; unverified",
        "source_data": "FarmwiseAI reference data / file metadata; reference points may contain errors",
        "ai_observation": "Amazon Nova model reading of the photo; an observation, not ground truth",
        "external_evidence": "Independent external source (e.g. weather archive)",
        "derived": "Computed by ReliefTrace rules from the items above",
    }
    agentic: Optional[dict] = None
    human_decision: Optional[dict] = None
    total_latency_ms: Optional[int] = None
    model_config = {"extra": "allow"}
