from datetime import date

import pytest

from backend.agentic.state import SharedState
from backend.agentic.tools import crop_stage_tool, geo_validation_tool, weather_tool
from backend.dataset import db
from backend.storage.schema import init_verify_schema
from tests.test_verification import FakeHttp, make_geo, weather_payload


def state():
    return SharedState(claim_id="CLM-1", claim={"claimed_cause": "drought"})


def open_conn_factory(tmp_path):
    p = tmp_path / "cache.db"

    def _open():
        conn = db.connect(p)
        init_verify_schema(conn)
        return conn
    return _open


# ---------------------------------------------------------------- weather_tool
def test_weather_tool_success_computes_drought_indicator_and_leaves_humidity_honestly_null(tmp_path):
    s = state()
    tr = weather_tool(s, lat=9.25, lon=77.42, incident_date="2024-11-05", http=FakeHttp(weather_payload(dry=True)),
                      open_conn=open_conn_factory(tmp_path))
    assert tr.status == "success" and tr.output["drought_indicator"] == "dry"
    assert tr.output["humidity"] is None and "humidity_note" in tr.output
    assert tr.output["source"] and tr.output["rainfall_mm_30d"] == 0.0
    assert s.tool_results[0] is tr
    step = next(t for t in s.audit_trace if t.tool == "weather")
    assert step.status == "success" and step.evidence_source == tr.source_name


def test_weather_tool_wet_conditions_flip_indicator(tmp_path):
    tr = weather_tool(state(), lat=9.25, lon=77.42, incident_date="2024-11-05",
                      http=FakeHttp(weather_payload(dry=False)), open_conn=open_conn_factory(tmp_path))
    assert tr.status == "success" and tr.output["drought_indicator"] == "wet"


def test_weather_tool_too_recent_incident_fails_without_any_network_call(tmp_path):
    http = FakeHttp(weather_payload())
    tr = weather_tool(state(), lat=9.25, lon=77.42, incident_date=date.today().isoformat(),
                      http=http, open_conn=open_conn_factory(tmp_path))
    assert tr.status == "failed" and "too recent" in tr.error and http.calls == 0


def test_weather_tool_network_failure_with_no_cache_fails_honestly(tmp_path):
    tr = weather_tool(state(), lat=9.25, lon=77.42, incident_date="2024-11-05", http=FakeHttp(fail=True),
                      open_conn=open_conn_factory(tmp_path))
    assert tr.status == "failed" and "unavailable" in tr.error


def test_weather_tool_simulated_failure_falls_back_to_cache(tmp_path):
    factory = open_conn_factory(tmp_path)
    first = weather_tool(state(), lat=9.25, lon=77.42, incident_date="2024-11-05",
                         http=FakeHttp(weather_payload(dry=True)), open_conn=factory)
    assert first.status == "success"
    second = weather_tool(state(), lat=9.25, lon=77.42, incident_date="2024-11-05",
                          http=FakeHttp(fail=True), open_conn=factory, simulate_failure=True)
    assert second.status == "success" and "cache" in second.output["data_quality"]


# ---------------------------------------------------------------- geo_validation_tool
def test_geo_validation_no_points_fails():
    tr = geo_validation_tool(state(), points=[], geo=None, village_code="101")
    assert tr.status == "failed" and "no coordinates" in tr.error


def test_geo_validation_points_close_together_and_inside_taluk_are_consistent(tmp_path):
    from backend.evidence.geo import AdminLayers
    geo = AdminLayers(make_geo(tmp_path))
    points = [{"role": "claimed", "lat": 9.25, "lon": 77.42, "label": "claim"},
             {"role": "image_dataset", "lat": 9.2501, "lon": 77.4201, "label": "photo"}]
    tr = geo_validation_tool(state(), points=points, geo=geo, village_code="101")
    assert tr.status == "success" and tr.output["consistent"] is True
    assert tr.output["max_pairwise_distance_m"] < 50
    assert all(r["in_taluk"] is True for r in tr.output["points"])


def test_geo_validation_point_far_outside_taluk_is_inconsistent(tmp_path):
    from backend.evidence.geo import AdminLayers
    geo = AdminLayers(make_geo(tmp_path))
    points = [{"role": "claimed", "lat": 9.25, "lon": 77.42, "label": "claim"},
             {"role": "image_dataset", "lat": 13.0, "lon": 80.2, "label": "photo far away"}]
    s = state()
    tr = geo_validation_tool(s, points=points, geo=geo, village_code="101")
    assert tr.output["consistent"] is False and "image_dataset" in tr.output["points_outside_taluk"]
    assert tr.output["max_pairwise_distance_m"] > 100_000


def test_geo_validation_without_boundary_layer_still_reports_distance(tmp_path):
    from backend.evidence.geo import AdminLayers
    geo = AdminLayers(None)  # not available
    points = [{"role": "claimed", "lat": 9.25, "lon": 77.42}, {"role": "image_dataset", "lat": 9.30, "lon": 77.50}]
    tr = geo_validation_tool(state(), points=points, geo=geo, village_code="101")
    assert tr.output["boundary_layer_available"] is False
    assert tr.output["max_pairwise_distance_m"] > 0
    assert all(r["in_taluk"] is None for r in tr.output["points"])


# ---------------------------------------------------------------- crop_stage_tool
def test_crop_stage_consistent_with_reference():
    s = state()
    s.claim.update(claimed_crop="Rice (Paddy)", claimed_stage="full_growth")
    tr = crop_stage_tool(s, claim=s.claim, ground_truth_crops=["Rice (Paddy)"], ground_truth_stages=["full_growth"])
    assert tr.output["crop_consistency"] == "consistent" and tr.output["stage_consistency"] == "consistent"


def test_crop_stage_inconsistent_with_reference():
    claim = {"claimed_crop": "Coconut", "claimed_stage": "sown"}
    tr = crop_stage_tool(state(), claim=claim, ground_truth_crops=["Rice (Paddy)"], ground_truth_stages=["full_growth"])
    assert tr.output["crop_consistency"] == "inconsistent" and tr.output["stage_consistency"] == "inconsistent"


def test_crop_stage_no_reference_available_is_not_reported_as_inconsistent():
    claim = {"claimed_crop": "Rice (Paddy)", "claimed_stage": "full_growth"}
    tr = crop_stage_tool(state(), claim=claim, ground_truth_crops=[], ground_truth_stages=[])
    assert tr.output["crop_consistency"] == "no_reference" and tr.output["stage_consistency"] == "no_reference"


def test_crop_stage_photo_reading_compared_separately_from_reference():
    claim = {"claimed_crop": "Rice (Paddy)"}
    tr = crop_stage_tool(state(), claim=claim, ground_truth_crops=["Rice (Paddy)"], ground_truth_stages=[],
                         observed_crop="coconut palm")
    assert tr.output["photo_vs_reference_crop_consistency"] == "inconsistent"
    assert tr.output["observed_crop"] == "coconut palm"

    tr2 = crop_stage_tool(state(), claim=claim, ground_truth_crops=["Rice (Paddy)"], ground_truth_stages=[],
                          observed_crop="paddy")
    assert tr2.output["photo_vs_reference_crop_consistency"] == "consistent"


def test_crop_stage_tool_traces_into_shared_state():
    s = state()
    crop_stage_tool(s, claim={"claimed_crop": "Rice (Paddy)"}, ground_truth_crops=["Rice (Paddy)"],
                    ground_truth_stages=[])
    assert s.tool_results and s.audit_trace[-1].tool == "crop_stage_evidence"
