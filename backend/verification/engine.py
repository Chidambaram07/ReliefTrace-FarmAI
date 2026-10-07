"""Deterministic verification: compares CLAIM vs IMAGE vs GPS vs DATE vs CROP/STAGE vs independent evidence.

No model is used here, so the same evidence always yields the same verdicts. AI observations are inputs, never verdicts.
"""
from __future__ import annotations

from datetime import date, datetime

from backend.evidence.models import QUALITY_SCORE, EvidenceItem
from backend.schemas.verification import (
    S_CONTRA, S_FURTHER, S_INSUFF, S_PARTIAL, S_SUPPORTED, Finding, Routing, Scores,
)
from .rules import (
    CAUSE_TO_INDICATOR, LOW_RELIABILITY_CAUSES, STAGE_ORDER, THRESHOLDS as T, conf_ok, normalize_crop,
)

TITLES = {"claim_vs_image": "Claimed damage vs. photo evidence", "weather": "Weather record vs. claimed cause",
          "location": "Location vs. claimed parcel", "timing": "Photo/survey timing vs. reported incident",
          "crop": "Crop: claim vs. reference vs. photo", "stage": "Growth stage: claim vs. reference vs. photo",
          "parcel": "Parcel presence in reference data"}
RULE_TEXT = {
    "claim_vs_image": "AI-listed visible damage matching the claimed cause supports; explicit 'none visible' contradicts (high); a different visible cause contradicts (medium).",
    "weather": "Percentile of observed 30-day window vs same window in previous 10 years; thresholds in rules_applied.",
    "location": "Point-in-polygon vs claimed village/taluk; distance to claimed village; image-to-GT distance vs dataset p95.",
    "timing": "Photo dated before the incident contradicts (high); within N days after supports; later is inconclusive.",
    "crop": "Claimed crop compared with reference label and (medium+ confidence) AI reading.",
    "stage": "Claimed stage compared with reference and AI reading; adjacent stages are compatible.",
    "parcel": "Parcel (village + survey [+ subdivision]) exists in FarmwiseAI reference points.",
}


def _of(ev, typ):
    return [e for e in ev if e.evidence_type == typ]


def _ok(items):
    return [e for e in items if e.status == "available"]


def _ids(items):
    return [e.evidence_id for e in items]


def _mk(cid, plan, verdict, detail, items=(), severity=None, independent=True, limitations=()):
    w = plan["checks"][cid]["weight"]
    return Finding(check_id=cid, title=TITLES[cid], verdict=verdict, severity=severity, detail=detail,
                   evidence_ids=_ids(items), weight=w, independent=independent, rule=RULE_TEXT[cid], limitations=list(limitations))


def _na(cid, plan):
    return _mk(cid, plan, "inconclusive", f"Not applicable: {plan['checks'][cid]['reason']}.")


# ------------------------------------------------------------------ checks
def check_parcel(claim, ev, plan):
    its = [e for e in _of(ev, "crop_metadata") if e.data.get("scope") != "image"]
    st = its[0].data.get("parcel_status") if its else None
    if st in ("found", "found_ignoring_subdivision"):
        return _mk("parcel", plan, "supports", f"Survey {claim['survey_no']} found in reference data ({its[0].data['n_records']} record(s)).", its)
    if st == "ambiguous":
        return _mk("parcel", plan, "inconclusive", "Survey number exists in several villages and no village was given.", its)
    return _mk("parcel", plan, "missing", "Parcel not present in the reference points (they cover sampled points only, so absence is not a contradiction).", its)


def _gt_values(ev, key):
    out, its = set(), []
    for e in _ok(_of(ev, "crop_metadata")):
        vals = e.data.get(key) or []
        if vals:
            its.append(e)
            out.update(vals)
    return out, its


def _ai_obs(ev):
    return [(e, e.data["analysis"]) for e in _ok(_of(ev, "ai_image_observation")) if e.data.get("analysis")]


def check_crop(claim, ev, plan):
    if not plan["checks"]["crop"]["applicable"]:
        return _na("crop", plan)
    claimed = normalize_crop(claim.get("claimed_crop"))
    gt_raw, gt_items = _gt_values(ev, "crops")
    gt = {normalize_crop(c) for c in gt_raw}
    ai, ai_items, no_crop_items = [], [], []
    for e, o in _ai_obs(ev):
        c = o["crop"]
        if not o["image_usable"]:
            continue
        if not c["crop_visible"] and conf_ok(c["stage_confidence"] if c["stage_guess"] == "bare_soil_or_fallow" else "medium"):
            no_crop_items.append(e)  # AI positively reports NO crop at all (e.g. bare soil, tree, non-agri scene)
        elif c["crop_visible"] and c["name_guess"] and conf_ok(c["name_confidence"]):
            ai.append(normalize_crop(c["name_guess"]))
            ai_items.append(e)
    items = gt_items + ai_items
    ai_dis = [a for a in ai if a != claimed]
    ai_agree = [a for a in ai if a == claimed]
    gt_known = bool(gt)
    gt_agree = claimed in gt
    if no_crop_items and not ai_agree:
        return _mk("crop", plan, "contradicts", f"Claimed crop is '{claimed}', but the photo analysis reports no crop visible at all (e.g. bare soil or non-crop scene).",
                   gt_items + no_crop_items, "high", independent=False, limitations=["Photo reading is an AI observation", "A single photo may not represent the whole parcel"])
    if ai_dis and not ai_agree:
        sev = "high" if (gt_known and not gt_agree) else "medium"
        return _mk("crop", plan, "contradicts", f"Claimed '{claimed}' but the photo reading suggests {sorted(set(ai_dis))}"
                   + (f" and the reference label is {sorted(gt)}." if gt_known else "."), items, sev, independent=False,
                   limitations=["Photo reading is an AI observation"])
    if gt_known and not gt_agree:
        if ai_agree:
            return _mk("crop", plan, "inconclusive", f"Reference label {sorted(gt)} differs from claimed '{claimed}', but the photo reading agrees with the claim; reference points may be inaccurate.", items)
        return _mk("crop", plan, "contradicts", f"Claimed '{claimed}' but reference label is {sorted(gt)}; no photo reading available to arbitrate.", items, "medium")
    if gt_agree or ai_agree:
        src = " and ".join(x for x in (["reference label"] if gt_agree else []) + (["photo reading"] if ai_agree else []))
        return _mk("crop", plan, "supports", f"Claimed '{claimed}' matches {src}.", items, independent=gt_agree)
    return _mk("crop", plan, "missing", "No reference label or confident photo reading of the crop to compare.", items)


def check_stage(claim, ev, plan):
    if not plan["checks"]["stage"]["applicable"]:
        return _na("stage", plan)
    cs = STAGE_ORDER.get((claim.get("claimed_stage") or "").strip().lower().replace(" ", "_"))
    if cs is None:
        return _mk("stage", plan, "missing", f"Claimed stage '{claim.get('claimed_stage')}' is not one of {list(STAGE_ORDER)}.")
    gt_raw, gt_items = _gt_values(ev, "stages")
    votes, items = [], list(gt_items)
    if gt_raw:
        lv = [STAGE_ORDER[s] for s in gt_raw if s in STAGE_ORDER]
        if lv:
            votes.append(("reference", any(abs(l - cs) <= 1 for l in lv)))
    for e, o in _ai_obs(ev):
        c = o["crop"]
        if c["stage_guess"] in STAGE_ORDER and conf_ok(c["stage_confidence"]):
            votes.append(("photo", abs(STAGE_ORDER[c["stage_guess"]] - cs) <= 1))
            items.append(e)
    if not votes:
        return _mk("stage", plan, "missing", "No reference stage or confident photo stage to compare.", items)
    a, d = [n for n, v in votes if v], [n for n, v in votes if not v]
    if a and not d:
        return _mk("stage", plan, "supports", f"Claimed stage compatible with {', '.join(a)} (adjacent stages count as compatible).", items)
    if d and not a:
        return _mk("stage", plan, "contradicts", f"Claimed stage differs from {', '.join(d)} by 2+ stages.", items, "medium")
    return _mk("stage", plan, "inconclusive", f"Sources disagree: compatible with {a}, incompatible with {d}.", items)


def check_damage(claim, ev, plan):
    obs = _ai_obs(ev)
    cause = claim["claimed_cause"]
    lims = ["AI reading of a single photo; not ground truth"]
    if cause in LOW_RELIABILITY_CAUSES:
        lims.append(f"Attributing '{cause}' from one RGB photo is low-reliability; field inspection is needed")
    if not obs:
        return _mk("claim_vs_image", plan, "missing", "No successful photo analysis available.", _of(ev, "ai_image_observation"), independent=False, limitations=lims)
    target = CAUSE_TO_INDICATOR.get(cause)
    sup, con_hi, con_md, unusable, used = [], [], [], 0, []
    for e, o in obs:
        if not o["image_usable"]:
            unusable += 1
            continue
        used.append(e)
        vis = [d for d in o["damage_indicators"] if d["visible"] and d["type"] != "none_visible"]
        explicit_none = any(d["type"] == "none_visible" and conf_ok(d["confidence"]) for d in o["damage_indicators"])
        match = [d for d in vis if (d["type"] == target or target is None) and (conf_ok(d["confidence"]) or d["severity"] in ("moderate", "severe"))]
        other = [d for d in vis if d["type"] != target and target is not None and conf_ok(d["confidence"])]
        if match:
            sup.append((e, match[0]))
        elif other:
            con_md.append((e, f"photo shows {sorted({d['type'] for d in other})}, not '{target}'"))
        elif explicit_none:
            con_hi.append((e, "photo analysis explicitly reports no visible damage"))
        elif not vis and o["crop"]["crop_visible"]:
            con_md.append((e, "no damage indicators listed (subtle stress may not show in one photo)"))
    items = [e for e, _ in obs]
    if sup and not (con_hi or con_md):
        d = sup[0][1]
        return _mk("claim_vs_image", plan, "supports", f"Photo shows {d['type']} ({d['severity']}, {d['confidence']} confidence): {d['description'] or 'see observation'}.", items, independent=False, limitations=lims)
    if sup:
        return _mk("claim_vs_image", plan, "inconclusive", "Photos disagree: at least one shows the claimed damage, another does not.", items, independent=False, limitations=lims)
    if con_hi:
        return _mk("claim_vs_image", plan, "contradicts", con_hi[0][1].capitalize() + ".", items, "high", independent=False, limitations=lims)
    if con_md:
        return _mk("claim_vs_image", plan, "contradicts", con_md[0][1].capitalize() + ".", items, "medium", independent=False, limitations=lims)
    return _mk("claim_vs_image", plan, "inconclusive", f"{unusable} photo(s) unusable (blur/dark/no crop); cannot judge damage.", items, independent=False, limitations=lims)


def check_weather(claim, ev, plan):
    if not plan["checks"]["weather"]["applicable"]:
        return _na("weather", plan)
    w = _of(ev, "weather")
    okw = _ok(w)
    if not okw:
        return _mk("weather", plan, "missing", (w[0].observation if w else "No weather evidence collected."), w)
    e = okw[0]
    pc, cause = e.data["percentile"], claim["claimed_cause"]
    s, d3, g = pc.get("sum_mm"), pc.get("max_3d_mm"), pc.get("max_gust_kmh")
    lims = list(e.limitations)
    if cause == "drought" and s is not None:
        if s <= T["drought_dry_pctl_max"]:
            return _mk("weather", plan, "supports", f"30-day rainfall at percentile {s} of the 10-year same-window baseline (dry).", [e], limitations=lims)
        if s >= T["drought_wet_pctl_min"]:
            return _mk("weather", plan, "contradicts", f"30-day rainfall at percentile {s} (wetter than usual), which is unlike drought.", [e], "high" if s >= 90 else "medium", limitations=lims)
    if cause == "flood" and d3 is not None:
        if d3 >= T["flood_heavy_pctl_min"]:
            return _mk("weather", plan, "supports", f"Heaviest 3-day rainfall at percentile {d3} of baseline (unusually heavy).", [e], limitations=lims)
        if (s is not None and s <= T["flood_dry_sum_pctl_max"]) and d3 <= 50:
            return _mk("weather", plan, "contradicts", f"Dry month (rain percentile {s}) with no heavy spell (3-day percentile {d3}).", [e], "medium", limitations=lims)
    if cause == "cyclone_storm" and (g is not None or d3 is not None):
        if (g or 0) >= T["storm_gust_pctl_min"] or (d3 or 0) >= T["storm_gust_pctl_min"]:
            return _mk("weather", plan, "supports", f"Wind gust percentile {g} / 3-day rain percentile {d3}: unusually severe for the season.", [e], limitations=lims)
        if g is not None and g <= T["storm_calm_gust_pctl_max"] and (d3 or 0) <= 60:
            return _mk("weather", plan, "contradicts", f"Calm conditions: gust percentile {g}, 3-day rain percentile {d3}.", [e], "medium", limitations=lims)
    return _mk("weather", plan, "inconclusive", f"Weather is within the normal range for this season (rain pctl {s}, 3-day pctl {d3}, gust pctl {g}); it neither supports nor rules out the claim.", [e], limitations=lims)


def check_location(claim, ev, plan):
    loc = [e for e in _ok(ev) if e.evidence_type in ("gps_location", "administrative_boundary") and e.data.get("role") in ("claimed", "image_dataset", "image_exif")]
    if not loc:
        u = [e for e in ev if e.evidence_type in ("gps_location", "administrative_boundary")]
        return _mk("location", plan, "missing", u[0].observation if u else "No location evidence.", u)
    sev_rank, problems = {"medium": 1, "high": 2}, []
    for e in loc:
        d, role = e.data, e.data["role"]
        who = {"claimed": "claimed location", "image_dataset": "photo location", "image_exif": "photo EXIF location"}[role]
        if not d["in_taluk"]:
            problems.append(("high", f"{who} is outside the study taluk"))
        dv = d.get("dist_to_claimed_village_m")
        if dv is not None and dv > T["village_far_m"]:
            problems.append(("high", f"{who} is {dv:.0f} m from the claimed village"))
        elif dv is not None and dv > T["village_buffer_m"]:
            problems.append(("medium", f"{who} is {dv:.0f} m outside the claimed village polygon"))
        g, tol = d.get("gt_to_image_m"), d.get("tolerance_p95_m")
        if g is not None and tol and g > tol:
            problems.append(("medium", f"{who} is {g:.0f} m from its GT point, beyond the dataset p95 of {tol:.0f} m"))
    if problems:
        top = max(problems, key=lambda p: sev_rank[p[0]])
        return _mk("location", plan, "contradicts", "; ".join(p[1] for p in problems) + ".", loc, top[0])
    return _mk("location", plan, "supports", f"{len(loc)} location(s) inside the claimed village/taluk and within dataset tolerance.", loc)


def check_timing(claim, ev, plan):
    ts = _ok(_of(ev, "timestamp"))
    photos = [e for e in ts if e.data["role"] != "gt_survey"]
    use, kind = (photos, "photo") if photos else (ts, "reference survey")
    if not use:
        u = _of(ev, "timestamp")
        return _mk("timing", plan, "missing", u[0].observation if u else "No dated evidence.", u)
    ds = [e.data["days_from_incident"] for e in use]
    win = T["post_incident_window_days"]
    hi = "high" if kind == "photo" else "medium"
    if all(d < 0 for d in ds):
        return _mk("timing", plan, "contradicts", f"All {kind} dates are before the reported incident (earliest {min(ds):+d} day(s)); they cannot show its damage.", use, hi)
    if any(d < 0 for d in ds) and any(d >= 0 for d in ds):
        return _mk("timing", plan, "inconclusive", f"Some {kind} dates precede the incident ({ds} days relative).", use)
    if any(0 <= d <= win for d in ds):
        return _mk("timing", plan, "supports", f"{kind.capitalize()} dated {min(d for d in ds if 0 <= d <= win)} day(s) after the incident (within {win} days).", use)
    return _mk("timing", plan, "inconclusive", f"{kind.capitalize()} dated {min(ds)} days after the incident (beyond {win} days); condition may have changed.", use)


CHECKS = (check_parcel, check_crop, check_stage, check_location, check_timing, check_weather, check_damage)


# ------------------------------------------------------------------ scoring
def score(findings: list[Finding], evidence: list[EvidenceItem]):
    active = [f for f in findings if f.weight > 0]
    seen = [f for f in active if f.verdict != "missing"]
    W = sum(f.weight for f in active) or 1.0
    Wseen = sum(f.weight for f in seen)
    Ws = sum(f.weight for f in seen if f.verdict == "supports")
    coverage = Wseen / W
    agreement = Ws / Wseen if Wseen else 0.0
    cited = {i for f in seen for i in f.evidence_ids}
    q = [QUALITY_SCORE[e.quality] for e in evidence if e.evidence_id in cited and e.quality in QUALITY_SCORE]
    eq = sum(q) / len(q) if q else 0.0
    breakdown, eci = evidence_consistency_breakdown(active, evidence, W)
    return Scores(confidence_index=round(100 * coverage * agreement * eq, 1), evidence_quality=round(eq, 2),
                  coverage=round(coverage, 2), agreement=round(agreement, 2),
                  evidence_consistency_index=eci, breakdown=breakdown)


# verdict -> how much of a check's max points it earns. A contradiction earns 0 here (it is not
# "negative points": its cost is already visible as a listed contradiction and, via decide(), as
# the overall status), so the index measures ACCUMULATED SUPPORTING/CONSISTENT EVIDENCE, never a
# probability of anything.
_VERDICT_FACTOR = {"supports": 1.0, "inconclusive": 0.5, "missing": 0.0, "contradicts": 0.0}


def evidence_consistency_breakdown(active: list[Finding], evidence: list[EvidenceItem], total_weight: float):
    """Additive, per-check breakdown that SUMS EXACTLY to the returned total - unlike the legacy
    confidence_index (a single multiplicative figure using one dataset-wide evidence-quality
    average), this is built check by check so each line is independently checkable:
        max_points_i  = 100 * weight_i / total_weight        (every active check's ceiling; sums to 100)
        awarded_i     = max_points_i * verdict_factor_i * evidence_quality_i
    where evidence_quality_i is the mean QUALITY_SCORE of THAT check's own cited evidence (0 if none
    cited, e.g. for a 'missing' verdict). Rounding is applied once at the end so the displayed lines
    always sum to the displayed total."""
    by_evidence_id = {e.evidence_id: e for e in evidence}
    rows = []
    for f in active:
        max_points = 100.0 * f.weight / total_weight
        cited = [by_evidence_id[i] for i in f.evidence_ids if i in by_evidence_id]
        qvals = [QUALITY_SCORE[e.quality] for e in cited if e.quality in QUALITY_SCORE]
        eq_i = sum(qvals) / len(qvals) if qvals else 0.0
        factor = _VERDICT_FACTOR.get(f.verdict, 0.0)
        awarded = max_points * factor * eq_i
        rows.append({"check_id": f.check_id, "title": f.title, "verdict": f.verdict,
                    "max_points": round(max_points, 1), "evidence_quality": round(eq_i, 2),
                    "awarded_points": round(awarded, 1)})
    total = round(sum(r["awarded_points"] for r in rows), 1)
    return rows, total


def decide(findings: list[Finding], scores: Scores):
    active = [f for f in findings if f.weight > 0]
    seen = [f for f in active if f.verdict != "missing"]
    contra = [f for f in seen if f.verdict == "contradicts"]
    hi = [f for f in contra if f.severity == "high"]
    md = [f for f in contra if f.severity != "high"]
    dmg_support = any(f.verdict == "supports" and f.check_id in ("claim_vs_image", "weather") for f in seen)
    if hi:
        return S_CONTRA, f"High-severity contradiction: {hi[0].title}."
    if len(md) >= 2:
        return S_CONTRA, f"{len(md)} independent medium-severity contradictions."
    if len(seen) < T["min_findings"] or scores.coverage < T["insufficient_coverage_max"]:
        return S_INSUFF, f"Only {len(seen)} applicable check(s) had evidence (coverage {scores.coverage})."
    if not dmg_support:
        return S_FURTHER, "Identity/consistency checks alone do not establish the claimed damage (no supporting photo or weather evidence)."
    major_missing = [f for f in active if f.verdict == "missing" and f.weight >= T["major_check_weight"]]
    if scores.agreement >= T["support_agreement_min"] and not contra and scores.coverage >= T["support_coverage_min"] and not major_missing:
        return S_SUPPORTED, "Weighted checks agree, no contradictions, adequate coverage, no major check missing."
    if major_missing and not contra and scores.agreement >= T["support_agreement_min"]:
        return S_PARTIAL, f"Available checks agree, but major evidence is missing: {', '.join(f.title for f in major_missing)}."
    if scores.agreement >= T["partial_agreement_min"]:
        return S_PARTIAL, "Some checks support the claim; others are inconclusive, missing or mildly conflicting."
    return S_FURTHER, "Too few checks support the claim."


def route(status: str, findings: list[Finding], scores: Scores, ai_failures: int) -> Routing:
    reasons = []
    if status != S_SUPPORTED:
        reasons.append(f"Status is '{status}'.")
    reasons += [f"Contradiction ({f.severity}): {f.detail}" for f in findings if f.weight > 0 and f.verdict == "contradicts"]
    reasons += [f"Missing evidence: {f.title}." for f in findings if f.weight > 0 and f.verdict == "missing"]
    if ai_failures:
        reasons.append(f"{ai_failures} photo analysis call(s) failed.")
    if scores.confidence_index < T["review_confidence_min"] and status == S_SUPPORTED:
        reasons.append(f"Evidence Consistency Index {scores.evidence_consistency_index} below {T['review_confidence_min']}.")
    return Routing(human_review_required=bool(reasons), reasons=reasons)


def build_timeline(claim: dict, evidence: list[EvidenceItem]) -> list[dict]:
    ev = [{"when": claim["incident_date"], "kind": "claim", "label": f"Reported incident ({claim['claimed_cause']})", "evidence_id": None}]
    for e in evidence:
        if e.status != "available":
            continue
        if e.evidence_type == "timestamp":
            ev.append({"when": e.data["when"], "kind": "source_data", "label": e.observation.split(" (")[0].rstrip(":"), "evidence_id": e.evidence_id})
        elif e.evidence_type == "weather":
            ev.append({"when": e.data["window_start"], "kind": "external_evidence", "label": "Weather window starts (30 days)", "evidence_id": e.evidence_id})
            ev.append({"when": e.data["window_end"], "kind": "external_evidence", "label": "Weather window ends", "evidence_id": e.evidence_id})
    return sorted(ev, key=lambda x: x["when"] or "")


def verify(claim: dict, evidence: list[EvidenceItem], plan: dict, ai_failures: int = 0) -> dict:
    findings = [c(claim, evidence, plan) for c in CHECKS]
    scores = score(findings, evidence)
    status, reason = decide(findings, scores)
    active = [f for f in findings if f.weight > 0]
    return {
        "findings": findings, "scores": scores, "status": status, "status_reason": reason,
        "routing": route(status, findings, scores, ai_failures),
        "supporting": [f"{f.title}: {f.detail}" for f in active if f.verdict == "supports"],
        "contradictions": [f"[{f.severity}] {f.title}: {f.detail}" for f in active if f.verdict == "contradicts"],
        "missing_evidence": [f"{f.title}: {f.detail}" for f in active if f.verdict == "missing"],
        "limitations": sorted({l for f in active for l in f.limitations} | {"Reference (ground-truth) points are not guaranteed accurate",
                                                                             "AI photo readings are observations, not ground truth"}),
        "timeline": build_timeline(claim, evidence),
    }
