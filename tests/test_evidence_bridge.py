from backend.agentic.evidence_bridge import from_independent_review, from_tool_result
from backend.agentic.state import ToolResult


def test_failed_tool_result_becomes_unavailable_evidence():
    tr = ToolResult(tool="weather", input_summary={}, output=None, status="failed", error="no cached copy",
                    source_type="public_dataset", source_name="Open-Meteo")
    e = from_tool_result(tr)
    assert e.status == "unavailable" and e.quality == "unavailable" and e.evidence_type == "weather"
    assert "no cached copy" in e.observation


def test_weather_tool_result_carries_location_and_indicator():
    tr = ToolResult(tool="weather", input_summary={}, source_type="public_dataset", source_name="Open-Meteo",
                    status="success", output={"location": {"lat": 9.25, "lon": 77.42}, "date": "2024-11-05",
                                              "rainfall_mm_30d": 5.0, "drought_indicator": "dry",
                                              "percentile_vs_10yr_baseline": {"sum_mm": 10}, "limitations": ["gridded data"]})
    e = from_tool_result(tr)
    assert e.location.lat == 9.25 and e.location.lon == 77.42 and e.timestamp == "2024-11-05"
    assert "drought indicator: dry" in e.observation and e.limitations == ["gridded data"]
    assert e.source_kind == "external_evidence"


def test_geo_validation_tool_result_summarizes_consistency():
    tr = ToolResult(tool="geo_validation", input_summary={}, source_type="derived", source_name="geo check",
                    status="success", output={"points": [{"role": "claimed"}, {"role": "photo"}],
                                              "max_pairwise_distance_m": 12.3, "points_outside_taluk": [],
                                              "consistent": True})
    e = from_tool_result(tr)
    assert "2 location(s)" in e.observation and "consistent=True" in e.observation and e.source_kind == "derived"


def test_image_retrieval_tool_result_with_hits():
    tr = ToolResult(tool="image_retrieval", input_summary={}, source_type="challenge_dataset", source_name="titan",
                    status="success", output={"similar_images": [{"image_id": "abc123def456ghi789xyz", "similarity": 0.9,
                                                                  "crop": "Rice (Paddy)"}],
                                              "claimed_crop_agreement_fraction": 0.5})
    e = from_tool_result(tr)
    assert "1 visually similar" in e.observation and "50%" in e.observation and "abc123" in e.observation


def test_image_retrieval_tool_result_with_no_hits_does_not_crash():
    tr = ToolResult(tool="image_retrieval", input_summary={}, source_type="challenge_dataset", source_name="titan",
                    status="success", output={"similar_images": [], "claimed_crop_agreement_fraction": None})
    e = from_tool_result(tr)
    assert "0 visually similar" in e.observation


def test_crop_stage_tool_result_summary():
    tr = ToolResult(tool="crop_stage_evidence", input_summary={}, source_type="challenge_dataset", source_name="gt",
                    status="success", output={"crop_consistency": "consistent", "stage_consistency": "no_reference",
                                              "photo_vs_reference_crop_consistency": "not_analyzed"})
    e = from_tool_result(tr)
    assert "crop consistency: consistent" in e.observation and "stage consistency: no_reference" in e.observation


def test_independent_review_failure_is_unavailable_ai_observation():
    e = from_independent_review({"ok": False, "error": "BEDROCK_ACCESS_DENIED: denied", "model_key": None,
                                 "fallback_used": False, "output": None})
    assert e.status == "unavailable" and e.source_kind == "ai_observation"
    assert e.evidence_type == "independent_model_review" and "denied" in e.observation


def test_independent_review_success_reflects_agreement_and_confidence():
    review = {"ok": True, "model_key": "ministral_8b", "fallback_used": False,
             "output": {"agrees_with_claim": False, "confidence": "high", "reasoning": "no stress mentioned",
                        "disagreement": "healthy crop"}}
    e = from_independent_review(review)
    assert "does not support" in e.observation and e.quality == "high" and e.source_kind == "ai_observation"
    assert "text observations only" in " ".join(e.limitations)


def test_independent_review_fallback_used_notes_it_in_limitations():
    review = {"ok": True, "model_key": "ministral_3b", "fallback_used": True,
             "output": {"agrees_with_claim": True, "confidence": "low", "reasoning": "plausible", "disagreement": ""}}
    e = from_independent_review(review)
    assert any("fallback model" in l for l in e.limitations)
