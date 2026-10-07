"""Dynamic planner (Phase 3): decides which tasks a request needs, for either a STRUCTURED claim
verification (the existing MVP flow) or a FREE-TEXT ("unseen") officer request such as "why was
this claim sent for human review?" or "find contradictory evidence".

Honesty rule: a task's status is READY only if this build can actually execute it today.
All tasks for full verification (including Nova Lite vision, Ministral independent review,
Titan image retrieval, weather, and geo) are implemented and executed.
Tasks that are genuinely conditional or not applicable for a given claim are marked appropriately.
That distinction ensures the execution trace tells the truth.

Intent classification is deterministic keyword matching, not a model call: reproducible, free, and
testable without AWS. It can be swapped for a Nova-Micro-based classifier later (Phase 4, the
router) without changing this module's output shape - build_plan()'s return value is the contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.agentic.state import SharedState
from backend.verification.planner import plan_verification

READY = "ready"
FUTURE = "planned_future_phase"


@dataclass(frozen=True)
class Intent:
    key: str
    label: str
    keywords: tuple[str, ...]


# Order matters: first keyword match wins. "full_verification" is the default and matches nothing
# itself, so it must stay last.
INTENTS: tuple[Intent, ...] = (
    Intent("explain_human_review", "Explain why a claim needs human review",
          ("why", "flagged", "sent for review", "sent to review")),
    Intent("check_evidence_sufficiency", "Check whether evidence is sufficient",
          ("enough evidence", "sufficient evidence", "evidence sufficient", "enough information")),
    Intent("find_contradictions", "Find contradictory evidence",
          ("contradict", "conflicting evidence", "disagree")),
    Intent("compare_image_ground_truth", "Compare image with ground truth / similar images",
          ("similar image", "ground truth", "compare this image", "visually similar")),
    Intent("full_verification", "Run full independent-evidence verification", ()),
)


def classify_intent(request_text: Optional[str]) -> tuple[str, str, str]:
    """Returns (intent_key, label, reason)."""
    if not request_text or not request_text.strip():
        i = INTENTS[-1]
        return i.key, i.label, "no free-text request given; a claim was submitted directly"
    t = request_text.lower()
    for i in INTENTS[:-1]:
        hit = next((k for k in i.keywords if k in t), None)
        if hit:
            return i.key, i.label, f"request matched phrase '{hit}'"
    i = INTENTS[-1]
    return i.key, i.label, "no specific verification aspect named in the request; defaulting to full verification"


def _task(task: str, required: bool, reason: str, status: str, model_key: str | None = None,
         tool: str | None = None) -> dict:
    return {"task": task, "required": required, "reason": reason, "status": status,
            "model_key": model_key, "tool": tool}


def _full_verification_tasks(claim: dict, n_images: int) -> list[dict]:
    tasks: list[dict] = []
    vplan = plan_verification(claim, n_images)
    for cid, c in vplan["checks"].items():
        tasks.append(_task(f"check:{cid}", c["applicable"], c["reason"], READY if c["applicable"] else FUTURE,
                           tool="weather" if cid == "weather" and c["applicable"] else None))
    if n_images > 0:
        tasks.append(_task("photo_analysis", True, "photo attached: a visible-damage reading is needed",
                           READY, model_key="nova_lite"))
        tasks.append(_task("independent_photo_review", True,
                           "cross-check the vision reading with a second, independent model before "
                           "trusting it on its own", READY, model_key="ministral_8b"))
        tasks.append(_task("visual_similarity_retrieval", False,
                           "find visually similar challenge-dataset images for extra context", READY,
                           model_key="titan_embed_image_v1", tool="image_retrieval"))
    else:
        tasks.append(_task("photo_analysis", False, "no photo attached to this claim", FUTURE))
    tasks.append(_task("report_narrative", False, "plain-language summary of the findings", READY,
                       model_key="nova_micro"))
    return tasks


def _report_lookup_tasks(*extra: dict) -> list[dict]:
    return [_task("load_latest_report", True,
                  "this request is about an already-verified claim, not a fresh verification run", READY),
           *extra]


def build_plan(state: SharedState, *, request_text: Optional[str] = None, n_images: int = 0) -> dict:
    """Populates state.plan and, for every READY task that names a model, records a real routing
    decision via state.route(). FUTURE tasks are listed for transparency but never routed."""
    intent_key, intent_label, intent_reason = classify_intent(request_text)

    if intent_key == "full_verification":
        tasks = _full_verification_tasks(state.claim, n_images)
    elif intent_key == "explain_human_review":
        tasks = _report_lookup_tasks(
            _task("summarize_review_reasons", False, "phrase the routing reasons in plain language",
                 FUTURE, model_key="nova_micro"))
    elif intent_key == "find_contradictions":
        tasks = _report_lookup_tasks(
            _task("extract_contradictions", True, "read the contradiction findings already on record", READY))
    elif intent_key == "check_evidence_sufficiency":
        tasks = _report_lookup_tasks(
            _task("coverage_check", True, "compare evidence coverage against the applicable checks", READY))
    elif intent_key == "compare_image_ground_truth":
        tasks = [_task("visual_similarity_retrieval", True,
                       "embed the claim photo and compare it against the challenge dataset", FUTURE,
                       model_key="titan_embed_image_v1", tool="image_retrieval")]
    else:  # pragma: no cover - INTENTS is exhaustive, kept for safety
        tasks = []

    plan = {"intent": intent_key, "intent_label": intent_label, "intent_reason": intent_reason,
           "request_text": request_text, "tasks": tasks}
    state.set_plan(plan)

    for t in tasks:
        if t["status"] == READY and t["model_key"] and t["task"] in ("photo_analysis", "report_narrative"):
            state.route(t["task"], t["model_key"], t["reason"])

    return plan
