"""Planner: decides which checks apply to THIS claim (rule-based; no model call, no cost)."""
from __future__ import annotations

from .rules import CHECK_WEIGHTS, WEATHER_CAUSES


def plan_verification(claim: dict, n_images: int) -> dict:
    cause = claim["claimed_cause"]
    steps = {}
    for cid, w in CHECK_WEIGHTS.items():
        applicable, why = True, "applies to every claim"
        if cid == "weather" and cause not in WEATHER_CAUSES:
            applicable, why = False, f"weather records cannot verify '{cause}'"
        elif cid == "crop" and not claim.get("claimed_crop"):
            applicable, why = False, "no claimed crop to compare"
        elif cid == "stage" and not claim.get("claimed_stage"):
            applicable, why = False, "no claimed growth stage to compare"
        elif cid == "claim_vs_image" and n_images == 0:
            why = "no image attached: will be reported as missing evidence"
        steps[cid] = {"applicable": applicable, "weight": w if applicable else 0.0, "reason": why}
    return {"claimed_cause": cause, "checks": steps,
            "model_routing": {"image_analysis": "Amazon Nova Lite (vision)", "report_narrative": "Amazon Nova Micro (text)",
                              "verification_rules": "deterministic code (no model), so verdicts are reproducible"}}
