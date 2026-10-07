"""Consolidated human-review trigger evaluation (Phase 12).

One function that evaluates ALL conditions under which an investigation should be routed to a
human officer. Used by both the MVP verification pipeline and the agentic orchestrator so the
rules live in exactly one place.

Design: the AI recommends a review state. The human makes the final decision. The triggers below
identify situations where automated confidence is insufficient and human judgment is required.
"""
from __future__ import annotations

from typing import Optional

from backend.verification.rules import THRESHOLDS as T


def evaluate_review_triggers(
    *,
    status: str,
    findings: list[dict],
    scores_dict: dict,
    ai_failures: int = 0,
    contradictions: list[str] | None = None,
    model_disagreement: bool = False,
    tool_failures: list[str] | None = None,
    independent_review: dict | None = None,
) -> dict:
    """Evaluate all human-review trigger conditions.

    Returns {"human_review_required": bool, "reasons": [...], "triggers": {...}}
    where triggers maps each trigger name to {"fired": bool, "detail": str | None}.
    """
    contradictions = contradictions or []
    tool_failures = tool_failures or []
    reasons: list[str] = []
    triggers: dict[str, dict] = {}

    # 1. Non-supported status
    fired = status != "Supported by available evidence"
    if fired:
        reasons.append(f"Status is '{status}'.")
    triggers["non_supported_status"] = {"fired": fired, "detail": status if fired else None}

    # 2. Contradictory evidence (from deterministic findings)
    active = [f for f in findings if f.get("weight", 0) > 0]
    contra_findings = [f for f in active if f.get("verdict") == "contradicts"]
    for f in contra_findings:
        reasons.append(f"Contradiction ({f.get('severity', 'unknown')}): {f.get('detail', '')}")
    triggers["contradictory_evidence"] = {
        "fired": bool(contra_findings),
        "detail": f"{len(contra_findings)} finding(s) contradict the claim" if contra_findings else None
    }

    # 3. Missing critical evidence (weight >= major_check_weight threshold)
    missing = [f for f in active if f.get("verdict") == "missing" and f.get("weight", 0) >= T["major_check_weight"]]
    for f in missing:
        reasons.append(f"Missing evidence: {f.get('title', f.get('check_id', 'unknown'))}.")
    triggers["missing_critical_evidence"] = {
        "fired": bool(missing),
        "detail": f"{len(missing)} major check(s) lack evidence" if missing else None
    }

    # 4. Low Evidence Consistency Index
    eci = scores_dict.get("evidence_consistency_index", 0.0)
    low_eci = eci < T["review_confidence_min"] and status == "Supported by available evidence"
    if low_eci:
        reasons.append(f"Evidence Consistency Index {eci} below {T['review_confidence_min']}.")
    triggers["low_evidence_consistency"] = {
        "fired": low_eci,
        "detail": f"ECI={eci}" if low_eci else None
    }

    # 5. Low legacy confidence index (kept for compatibility)
    ci = scores_dict.get("confidence_index", 0.0)
    low_ci = ci < T["review_confidence_min"] and status == "Supported by available evidence"
    if low_ci and not low_eci:  # don't double-report if ECI already triggered
        reasons.append(f"Evidence Consistency Index (legacy) {ci} below {T['review_confidence_min']}.")
    triggers["low_confidence"] = {
        "fired": low_ci,
        "detail": f"CI={ci}" if low_ci else None
    }

    # 6. AI/model failures
    if ai_failures:
        reasons.append(f"{ai_failures} photo analysis call(s) failed.")
    triggers["ai_model_failure"] = {
        "fired": ai_failures > 0,
        "detail": f"{ai_failures} failure(s)" if ai_failures else None
    }

    # 7. Model disagreement (agentic layer: independent review vs first model)
    if model_disagreement:
        reasons.append("Models disagree on the same evidence.")
    triggers["model_disagreement"] = {
        "fired": model_disagreement,
        "detail": None
    }

    # 8. Important tool failures (agentic layer)
    if tool_failures:
        for tf in tool_failures:
            reasons.append(f"Tool failure: {tf}")
    triggers["tool_failure"] = {
        "fired": bool(tool_failures),
        "detail": ", ".join(tool_failures) if tool_failures else None
    }

    # 9. Agentic-layer contradictions (e.g. independent review disagreement)
    agentic_contradictions = [c for c in contradictions if c not in
                              [f"[{f.get('severity')}] {f.get('title')}: {f.get('detail')}" for f in contra_findings]]
    for c in agentic_contradictions:
        note = f"Agentic layer: {c}"
        if note not in reasons:
            reasons.append(note)
    triggers["agentic_contradictions"] = {
        "fired": bool(agentic_contradictions),
        "detail": f"{len(agentic_contradictions)} agentic contradiction(s)" if agentic_contradictions else None
    }

    # 10. Unresolved evidence ambiguity (many inconclusive findings)
    inconclusive = [f for f in active if f.get("verdict") == "inconclusive"]
    many_inconclusive = len(inconclusive) >= 3
    if many_inconclusive:
        reasons.append(f"{len(inconclusive)} checks are inconclusive; human judgment needed.")
    triggers["unresolved_ambiguity"] = {
        "fired": many_inconclusive,
        "detail": f"{len(inconclusive)} inconclusive" if many_inconclusive else None
    }

    return {
        "human_review_required": bool(reasons),
        "reasons": reasons,
        "triggers": triggers,
    }
