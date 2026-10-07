"""Shared state for the agentic verification workflow (Phase 2 of the Task-1 agentic build-out).

This is the one object that flows: claim -> planner -> router -> models -> tools -> evidence
aggregator -> verifier -> human reviewer. Every step appends to it rather than returning its own
disconnected result, so the whole reasoning chain is inspectable and replayable from one place -
this is what makes the system's reasoning auditable rather than a black box.

This module defines the STATE SHAPE only. It does not yet decide what runs (that is the planner,
Phase 3) or which model handles a task (that is the router, Phase 4). It is additive: nothing in
the existing claim-processing pipeline (backend/verification/pipeline.py) is changed or removed by
introducing this module, so the current working MVP flow is untouched until the planner/router are
wired in on top of it in the next phase.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

TraceStatus = Literal["success", "failed", "fallback", "skipped"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _investigation_id() -> str:
    return f"INV-{uuid.uuid4().hex[:12].upper()}"


@dataclass
class ModelSelection:
    """One routing decision: which model was chosen for a task, and why."""
    task: str
    model_key: str                      # matches ModelSpec.key in model_registry.py
    reason: str
    fallback_of: Optional[str] = None   # model_key of the model this replaced, if any
    decided_at: str = field(default_factory=_now)


@dataclass
class ToolResult:
    """One independently-callable tool invocation and its structured result."""
    tool: str
    input_summary: dict
    output: Optional[dict]
    status: TraceStatus
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    source_type: Literal["challenge_dataset", "public_dataset", "demo_data", "claimant_input", "derived"] = "derived"
    source_name: str = ""
    called_at: str = field(default_factory=_now)


@dataclass
class ModelOutput:
    """One model call's result, independent of which tool/router step triggered it."""
    task: str
    model_key: str
    model_id: Optional[str]
    ok: bool
    output_summary: str
    confidence: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_estimate_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    called_at: str = field(default_factory=_now)


@dataclass
class TraceStep:
    """One row of the audit trail, in the shape the reviewer-facing trail is built from.
    `status` distinguishes an outright failure from a recorded fallback, so recovery is visible
    rather than silently absorbed."""
    step: str
    agent: str
    task: str = ""
    model: Optional[str] = None
    tool: Optional[str] = None
    routing_reason: Optional[str] = None
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    status: TraceStatus = "success"
    latency_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_estimate_usd: Optional[float] = None
    confidence: Optional[str] = None
    fallback_of: Optional[str] = None
    error: Optional[str] = None
    evidence_source: Optional[str] = None
    human_review_decision: Optional[str] = None
    timestamp: str = field(default_factory=_now)


@dataclass
class SharedState:
    claim_id: str
    claim: dict
    investigation_id: str = field(default_factory=_investigation_id)
    started_at: str = field(default_factory=_now)
    completed_at: Optional[str] = None
    plan: Optional[dict] = None
    selected_models: list[ModelSelection] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)          # EvidenceItem.model_dump() shape
    contradictions: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    model_outputs: list[ModelOutput] = field(default_factory=list)
    verification_result: Optional[dict] = None
    independent_review: Optional[dict] = None   # second-model review + agreement with the first reading (Phase 7)
    review_status: Optional[str] = None
    audit_trace: list[TraceStep] = field(default_factory=list)

    # ---------------------------------------------------------- mutators (each also traces itself)
    def route(self, task: str, model_key: str, reason: str, fallback_of: str | None = None) -> ModelSelection:
        sel = ModelSelection(task=task, model_key=model_key, reason=reason, fallback_of=fallback_of)
        self.selected_models.append(sel)
        self.trace(step=f"route:{task}", agent="router", task=task, model=model_key,
                   routing_reason=reason, status="fallback" if fallback_of else "success",
                   fallback_of=fallback_of)
        return sel

    def record_model_output(self, out: ModelOutput) -> None:
        self.model_outputs.append(out)
        self.trace(step=f"model:{out.task}", agent="model", task=out.task, model=out.model_id or out.model_key,
                   output_summary=out.output_summary, status="success" if out.ok else "failed",
                   latency_ms=out.latency_ms, input_tokens=out.input_tokens, output_tokens=out.output_tokens,
                   cost_estimate_usd=out.cost_estimate_usd, confidence=out.confidence, error=out.error)

    def record_tool_result(self, tr: ToolResult) -> None:
        self.tool_results.append(tr)
        self.trace(step=f"tool:{tr.tool}", agent="tool", task=tr.tool, tool=tr.tool,
                   input_summary=str(tr.input_summary)[:300], status=tr.status, latency_ms=tr.latency_ms,
                   error=tr.error, evidence_source=tr.source_name or tr.source_type)

    def add_evidence(self, item: dict) -> None:
        self.evidence.append(item)

    def add_contradiction(self, text: str) -> None:
        if text not in self.contradictions:
            self.contradictions.append(text)

    def add_missing(self, text: str) -> None:
        if text not in self.missing_evidence:
            self.missing_evidence.append(text)

    def set_plan(self, plan: dict) -> None:
        self.plan = plan
        self.trace(step="plan", agent="planner", task="plan", output_summary=str(plan)[:300])

    def set_verification_result(self, result: dict) -> None:
        self.verification_result = result
        self.trace(step="verification", agent="verification_engine", task="verify",
                   output_summary=str(result.get("status", ""))[:120])

    def set_review_status(self, status: str, decision: str | None = None) -> None:
        self.review_status = status
        self.trace(step="human_review", agent="human", task="review", status="success",
                   human_review_decision=decision or status)

    def complete(self, total_latency_ms: int | None = None) -> None:
        """Mark the investigation as completed and record a final summary trace step."""
        self.completed_at = _now()
        self.trace(step="investigation_complete", agent="orchestrator", task="finalize",
                   status="success", latency_ms=total_latency_ms,
                   output_summary=f"claim={self.claim_id} review={self.review_status}")

    def trace(self, **kwargs) -> TraceStep:
        step = TraceStep(**kwargs)
        self.audit_trace.append(step)
        return step

    # ---------------------------------------------------------- inspection
    def to_dict(self) -> dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)

    def to_audit_report(self) -> dict[str, Any]:
        """Structured audit report suitable for judge review. Contains only REAL execution data —
        unavailable values are explicitly null, never fabricated."""
        total_input_tokens = sum(m.input_tokens or 0 for m in self.model_outputs if m.input_tokens is not None)
        total_output_tokens = sum(m.output_tokens or 0 for m in self.model_outputs if m.output_tokens is not None)
        total_cost = sum(m.cost_estimate_usd for m in self.model_outputs if m.cost_estimate_usd is not None)
        any_tokens = any(m.input_tokens is not None for m in self.model_outputs)
        any_cost = any(m.cost_estimate_usd is not None for m in self.model_outputs)

        return {
            "investigation_id": self.investigation_id,
            "claim_id": self.claim_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_steps": len(self.audit_trace),
            "models_invoked": [
                {"task": m.task, "model_key": m.model_key, "model_id": m.model_id,
                 "ok": m.ok, "input_tokens": m.input_tokens, "output_tokens": m.output_tokens,
                 "cost_estimate_usd": m.cost_estimate_usd, "latency_ms": m.latency_ms,
                 "confidence": m.confidence, "error": m.error, "called_at": m.called_at}
                for m in self.model_outputs
            ],
            "tools_invoked": [
                {"tool": t.tool, "status": t.status, "latency_ms": t.latency_ms,
                 "source_type": t.source_type, "source_name": t.source_name,
                 "error": t.error, "called_at": t.called_at}
                for t in self.tool_results
            ],
            "routing_decisions": [
                {"task": s.task, "model_key": s.model_key, "reason": s.reason,
                 "fallback_of": s.fallback_of, "decided_at": s.decided_at}
                for s in self.selected_models
            ],
            "token_usage": {
                "total_input_tokens": total_input_tokens if any_tokens else None,
                "total_output_tokens": total_output_tokens if any_tokens else None,
                "total_cost_estimate_usd": round(total_cost, 6) if any_cost else None,
            },
            "contradictions": self.contradictions,
            "missing_evidence": self.missing_evidence,
            "verification_status": (self.verification_result or {}).get("status"),
            "review_status": self.review_status,
            "steps": [
                {"step": t.step, "agent": t.agent, "task": t.task, "model": t.model,
                 "tool": t.tool, "routing_reason": t.routing_reason,
                 "input_summary": t.input_summary, "output_summary": t.output_summary,
                 "status": t.status, "latency_ms": t.latency_ms,
                 "input_tokens": t.input_tokens, "output_tokens": t.output_tokens,
                 "cost_estimate_usd": t.cost_estimate_usd, "confidence": t.confidence,
                 "fallback_of": t.fallback_of, "error": t.error,
                 "evidence_source": t.evidence_source,
                 "human_review_decision": t.human_review_decision,
                 "timestamp": t.timestamp}
                for t in self.audit_trace
            ],
        }
