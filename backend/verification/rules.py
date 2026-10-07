"""All thresholds and mappings in one place so reviewers can see (and change) exactly what the verdicts rest on."""
from __future__ import annotations

import re

CHECK_WEIGHTS = {"claim_vs_image": 3.0, "weather": 2.0, "location": 2.0, "timing": 2.0, "crop": 2.0, "stage": 1.0, "parcel": 1.0}
WEATHER_CAUSES = ("drought", "flood", "cyclone_storm")

THRESHOLDS = {
    "village_buffer_m": 250,             # real data: 92% of photos inside own village polygon, p99 = 27 m outside, max 70 m
    "village_far_m": 2000,               # beyond this from claimed village -> high-severity contradiction
    "post_incident_window_days": 30,     # photo within N days after incident supports timing
    "drought_dry_pctl_max": 25,          # 30-day rainfall percentile <= this supports drought
    "drought_wet_pctl_min": 75,          # ... >= this contradicts drought
    "flood_heavy_pctl_min": 90,          # heaviest 3-day rain percentile >= this supports flood
    "flood_dry_sum_pctl_max": 25,        # dry month AND not heavy contradicts flood
    "storm_gust_pctl_min": 90,           # max gust percentile >= this supports storm
    "storm_calm_gust_pctl_max": 40,      # calm gusts AND modest rain contradicts storm
    "ai_min_confidence": "medium",
    "support_agreement_min": 0.75, "support_coverage_min": 0.6, "partial_agreement_min": 0.4,
    "insufficient_coverage_max": 0.35, "min_findings": 2,
    "major_check_weight": 2,             # a missing check at/above this weight prevents "Supported"
    "review_confidence_min": 60,
}

CAUSE_TO_INDICATOR = {"drought": "drought_stress", "flood": "flooding_waterlogging", "cyclone_storm": "lodging_storm_damage",
                      "hail": "hail_damage", "pest": "pest_damage", "disease": "disease_symptoms", "fire": "fire_burn"}
LOW_RELIABILITY_CAUSES = ("pest", "disease")  # single RGB photo attribution is weak

STAGE_ORDER = {"bare_soil_or_fallow": 0, "sown": 1, "vegetation": 2, "flowering": 3, "full_growth": 4, "harvesting": 5}
CONF_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}

_ALIASES = {
    "rice": ("rice", "paddy"), "coconut": ("coconut",), "maize": ("maize", "corn"), "banana": ("banana", "plantain"),
    "sugarcane": ("sugarcane", "sugar cane"), "marigold": ("marigold",), "sorghum": ("sorghum", "jowar", "cholam"),
    "cassava": ("cassava", "tapioca"), "cotton": ("cotton", "paruththi"), "groundnut": ("groundnut", "peanut"), "mango": ("mango",),
}


def normalize_crop(name: str | None) -> str | None:
    if not name:
        return None
    n = name.lower()
    for canon, aliases in _ALIASES.items():
        if any(re.search(rf"\b{re.escape(a)}\b", n) for a in aliases):
            return canon
    return re.sub(r"\s+", " ", re.sub(r"\(.*?\)", "", n)).strip() or None


def conf_ok(c: str | None) -> bool:
    return CONF_ORDER.get(c or "none", 0) >= CONF_ORDER[THRESHOLDS["ai_min_confidence"]]
