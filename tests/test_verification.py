import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.dataset import db
from backend.dataset.builder import build_dataset
from backend.evidence import weather as W
from backend.evidence.geo import AdminLayers
from backend.main import create_app
from backend.schemas.verification import S_CONTRA, S_FURTHER, S_INSUFF, S_PARTIAL, S_SUPPORTED
from backend.services.bedrock_service import BedrockService, BedrockSettings
from backend.verification.rules import normalize_crop
from tests.conftest import HEX_A, row
from tests.test_api import jpeg_bytes, make_settings
from tests.test_bedrock_service import FakeClient, client_error, ok_response


# ---------------------------------------------------------------- fixtures
def sq(lon0, lat0, lon1, lat1):
    return {"type": "MultiPolygon", "coordinates": [[[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]]}


def make_geo(tmp_path):
    g = tmp_path / "geo"
    g.mkdir(exist_ok=True)
    fc = lambda props, geom: {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": props, "geometry": geom}]}
    (g / "Sivagiri_Villages.geojson").write_text(json.dumps(fc({"vill_name": "Testpuram", "lgdvcode": 642626.0, "taluk_name": "Sivagiri", "dist_name": "Tenkasi"}, sq(77.40, 9.24, 77.44, 9.27))))
    (g / "Taluk_boundary.geojson").write_text(json.dumps(fc({"talukname": "Sivagiri"}, sq(77.30, 9.10, 77.60, 9.40))))
    (g / "Tenkasi_Boundary.geojson").write_text(json.dumps(fc({"district_name": "Tenkasi"}, sq(77.0, 8.8, 77.9, 9.6))))
    return g


def weather_payload(dry=True):
    start, end, t, p, tm, gu = date(2014, 9, 1), date(2024, 11, 12), [], [], [], []
    d = start
    while d <= end:
        rain = ((d.toordinal() * 7 + d.year * 3) % 5) * 2.0
        if d.year == 2024 and d >= date(2024, 10, 1):
            rain = 0.0 if dry else 25.0
        t.append(d.isoformat()); p.append(rain); tm.append(31.0); gu.append(20.0 + (d.toordinal() % 7) * 3)
        d += timedelta(days=1)
    return {"daily": {"time": t, "precipitation_sum": p, "temperature_2m_max": tm, "wind_gusts_10m_max": gu}}


class FakeHttp:
    def __init__(self, payload=None, fail=False):
        self.payload, self.fail, self.calls = payload, fail, 0

    def get_json(self, url):
        self.calls += 1
        if self.fail or self.payload is None:
            raise TimeoutError("network down")
        return self.payload


def obs(indicators, crop="rice", stage="full_growth", usable=True, conf="high"):
    return {"image_usable": usable, "quality_issues": [], "observations": ["green paddy field"],
            "crop": {"crop_visible": True, "name_guess": crop, "name_confidence": conf, "stage_guess": stage, "stage_confidence": "medium"},
            "damage_indicators": indicators, "inferences": [], "claim_assessment": {"supports": [], "contradicts": [], "cannot_determine": []},
            "missing_information": [], "limitations": ["single photo"]}


DROUGHT = [{"type": "drought_stress", "visible": True, "description": "leaf rolling, yellow tips", "severity": "moderate", "confidence": "medium"}]
NONE = [{"type": "none_visible", "visible": False, "description": "", "severity": "none", "confidence": "high"}]
PEST = [{"type": "pest_damage", "visible": True, "description": "chewed leaves", "severity": "mild", "confidence": "high"}]

CLAIM = {"survey_no": "293", "village_lgd": "642626", "claimed_cause": "drought", "incident_date": "2024-11-05",
         "claimed_crop": "Rice (Paddy)", "claimed_stage": "full_growth"}
CSV_ROW = dict(timestamp="11-06-2024", image_timestamp="06-11-2024 00:00", final_crop_stage="full_growth")


@pytest.fixture
def env(tmp_path, make_csv):
    def _env(ai=None, http=None, csv_rows=None, bedrock_fail=None, sub=""):
        base = tmp_path / sub
        base.mkdir(exist_ok=True)
        imgs = base / "imgs"
        imgs.mkdir(exist_ok=True)
        (imgs / f"642626_293_58__{HEX_A}-1_2_2024_11_06_10_00_00.jpg").write_bytes(jpeg_bytes())
        csv_p = make_csv(csv_rows or [row(image_path=HEX_A, **CSV_ROW)], name=f"gt{sub}.csv")
        s = make_settings(base)
        conn = db.connect(s.db_path)
        db.load_bundle(conn, build_dataset(csv_p, imgs), str(csv_p))
        conn.close()
        fake = FakeClient(*(bedrock_fail or [ok_response(ai if ai is not None else obs(DROUGHT))]))
        app = create_app(s, bedrock=BedrockService(BedrockSettings(), client=fake), geo=AdminLayers(make_geo(base)),
                         http=http or FakeHttp(weather_payload(dry=True)))
        return TestClient(app), fake
    return _env


def run(c, claim=None, image=HEX_A, params="narrative=template", **over):
    cid = c.post("/api/claims", json={**CLAIM, **(claim or {}), **over}).json()["claim_id"]
    if image:
        assert c.post(f"/api/claims/{cid}/images/from-dataset", json={"image_id": image}).status_code == 201
    r = c.post(f"/api/claims/{cid}/verify?{params}")
    assert r.status_code == 200, r.text
    return cid, r.json()


def F(rep, cid):
    return next(f for f in rep["findings"] if f["check_id"] == cid)


# ---------------------------------------------------------------- weather maths
def test_weather_stats_and_percentiles():
    series = W.parse_daily(weather_payload(dry=True))
    res = W.analyse(series, date(2024, 11, 5))
    assert res["observed"]["sum_mm"] == 0.0 and res["baseline_years"] == 10
    assert res["percentile"]["sum_mm"] < 10 and res["baseline_median"]["sum_mm"] > 50
    wet = W.analyse(W.parse_daily(weather_payload(dry=False)), date(2024, 11, 5))
    assert wet["percentile"]["sum_mm"] > 90
    assert W.percentile_rank(5, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) == 45.0 and W.percentile_rank(None, [1]) is None
    assert W.window_stats({}, date(2024, 1, 1)) is None


def test_normalize_crop():
    assert normalize_crop("Rice (Paddy)") == normalize_crop("paddy") == "rice"
    assert normalize_crop("Coconut palm") == "coconut" and normalize_crop("Fodder Sorghum") == "sorghum"
    assert normalize_crop("Diploid Cotton (Paruththi)") == "cotton" and normalize_crop(None) is None


# ---------------------------------------------------------------- scenarios
def test_supported_scenario_full_evidence(env):
    c, fake = env()
    with c:
        cid, rep = run(c)
        assert rep["status"] == S_SUPPORTED, [(f["check_id"], f["verdict"], f["detail"]) for f in rep["findings"]]
        assert {f["check_id"]: f["verdict"] for f in rep["findings"]} == {
            "parcel": "supports", "crop": "supports", "stage": "supports", "location": "supports", "timing": "supports",
            "weather": "supports", "claim_vs_image": "supports"}
        assert rep["routing"]["human_review_required"] is False and rep["contradictions"] == []
        kinds = {e["source_kind"] for e in rep["evidence"]}
        assert {"source_data", "ai_observation", "external_evidence"} <= kinds
        assert all(e["evidence_id"] and e["source"] and e["observation"] and e["quality"] and "raw_reference" in e for e in rep["evidence"])
        assert len({e["evidence_id"] for e in rep["evidence"]}) == len(rep["evidence"])
        assert 0 < rep["scores"]["confidence_index"] <= 100 and "NOT a probability" in rep["scores"]["formula"]
        assert c.get(f"/api/claims/{cid}").json()["status"] == "reported"
        assert len(fake.calls) == 1                                   # exactly one model call (vision), template narrative
        assert any(a["step"].startswith("image_analysis") and a["model"] for a in rep["audit"])
        assert c.get("/api/review-queue").json()["items"] == []


def test_verification_is_deterministic(env):
    c, _ = env()
    with c:
        _, a = run(c)
        _, b = run(c)
        strip = lambda r: [(f["check_id"], f["verdict"], f["detail"]) for f in r["findings"]]
        assert strip(a) == strip(b) and a["status"] == b["status"] and a["scores"] == b["scores"]


def test_explicit_no_damage_contradicts_and_queues_review(env):
    c, _ = env(ai=obs(NONE))
    with c:
        cid, rep = run(c)
        f = F(rep, "claim_vs_image")
        assert rep["status"] == S_CONTRA and f["verdict"] == "contradicts" and f["severity"] == "high"
        assert rep["routing"]["human_review_required"] and rep["routing"]["queue_status"] == "open"
        q = c.get("/api/review-queue").json()["items"]
        assert q[0]["claim_id"] == cid and any("no visible damage" in r.lower() for r in q[0]["reasons"])
        d = c.post(f"/api/review-queue/{cid}/decision", json={"decision": "request_more_information", "note": "need dated photo"})
        assert d.status_code == 200 and c.get("/api/review-queue").json()["items"] == []
        assert c.get("/api/review-queue?status=decided").json()["items"][0]["decision"] == "request_more_information"
        st = c.get("/api/stats").json()
        assert st["claims"] == 1 and st["by_status"][S_CONTRA] == 1 and st["review_decided"] == 1
        assert c.post("/api/review-queue/CLM-NOPE/decision", json={"decision": "reject"}).status_code == 404


def test_different_cause_visible_is_medium_contradiction(env):
    c, _ = env(ai=obs(PEST))
    with c:
        _, rep = run(c)
        f = F(rep, "claim_vs_image")
        assert f["verdict"] == "contradicts" and f["severity"] == "medium" and "pest_damage" in f["detail"]
        assert rep["status"] in (S_PARTIAL, S_FURTHER)          # a single medium contradiction does not force 'contradictory'


def test_crop_mismatch_photo_and_reference_is_high(env):
    c, _ = env()
    with c:
        _, rep = run(c, claimed_crop="Coconut")
        f = F(rep, "crop")
        assert f["verdict"] == "contradicts" and f["severity"] == "high" and rep["status"] == S_CONTRA


def test_no_crop_visible_at_all_contradicts_even_when_reference_agrees_with_claim(env):
    # Regression: real Nova Lite call on a coconut/bare-soil photo mislabelled 'Rice' in the reference CSV.
    # crop_visible=false + no confident name must NOT fall back to trusting the (also wrong) reference label.
    no_crop = obs(DROUGHT, crop="none", stage="bare_soil_or_fallow", conf="none")
    no_crop["crop"]["crop_visible"] = False
    c, _ = env(ai=no_crop)
    with c:
        _, rep = run(c)
        f = F(rep, "crop")
        assert f["verdict"] == "contradicts" and f["severity"] == "high" and "no crop visible" in f["detail"]
        assert rep["status"] == S_CONTRA


def test_reference_vs_photo_disagreement_is_not_a_hard_contradiction(env):
    c, _ = env(ai=obs(DROUGHT, crop="coconut"))               # photo says coconut; claim + reference say rice
    with c:
        _, rep = run(c)
        f = F(rep, "crop")
        assert f["verdict"] == "contradicts" and f["severity"] == "medium" and f["independent"] is False
        assert "coconut" in f["detail"]


def test_photo_before_incident_contradicts_timing(env):
    c, _ = env()
    with c:
        _, rep = run(c, incident_date="2024-11-09")             # photo dated 06 Nov
        f = F(rep, "timing")
        assert f["verdict"] == "contradicts" and f["severity"] == "high" and rep["status"] == S_CONTRA


def test_photo_long_after_incident_is_inconclusive(env):
    c, _ = env()
    with c:
        _, rep = run(c, incident_date="2024-09-20")
        assert F(rep, "timing")["verdict"] == "inconclusive"


def test_wet_weather_contradicts_drought(env):
    c, _ = env(http=FakeHttp(weather_payload(dry=False)))
    with c:
        _, rep = run(c)
        f = F(rep, "weather")
        assert f["verdict"] == "contradicts" and f["severity"] == "high" and rep["status"] == S_CONTRA


def test_weather_not_applicable_for_pest(env):
    c, _ = env(ai=obs(PEST))
    with c:
        _, rep = run(c, claimed_cause="pest")
        f = F(rep, "weather")
        assert f["weight"] == 0 and "cannot verify" in f["detail"] and rep["plan"]["checks"]["weather"]["applicable"] is False
        assert any("low-reliability" in l for l in F(rep, "claim_vs_image")["limitations"])


def test_weather_outage_uses_cache_fallback_then_unavailable(env):
    http = FakeHttp(weather_payload())
    c, _ = env(http=http)
    with c:
        _, first = run(c)                                          # populates cache via network
        assert http.calls == 1 and first["evidence"] and F(first, "weather")["verdict"] == "supports"
        _, sim = run(c, params="narrative=template&simulate_failure=weather")
        w = next(e for e in sim["evidence"] if e["evidence_type"] == "weather")
        assert w["data"]["fallback_used"] is True and http.calls == 1     # no network attempt during simulated outage
        assert any("cached copy" in l for l in w["limitations"])
    http2 = FakeHttp(fail=True)
    c2, _ = env(http=http2, sub="b")
    with c2:
        _, rep = run(c2)
        f = F(rep, "weather")
        assert f["verdict"] == "missing" and rep["status"] == S_PARTIAL and rep["routing"]["human_review_required"]
        assert "major evidence is missing" in rep["status_reason"]
        assert any("Weather" in m for m in rep["missing_evidence"])
        assert next(a for a in rep["audit"] if a["step"] == "evidence:weather")["status"] == "ok"   # adapter degraded, pipeline continued


def test_bedrock_failure_degrades_gracefully(env):
    c, _ = env(bedrock_fail=[client_error("AccessDeniedException", "denied")])
    with c:
        _, rep = run(c)
        assert F(rep, "claim_vs_image")["verdict"] == "missing"
        assert any(a["status"].startswith("failed") for a in rep["audit"])
        assert rep["status"] == S_PARTIAL and rep["routing"]["human_review_required"]
        assert any("photo analysis" in r for r in rep["routing"]["reasons"])
        fail_step = next(a for a in rep["audit"] if a["step"].startswith("image_analysis"))
        assert fail_step["detail"] and "denied" in fail_step["detail"]           # real message reaches the audit trail


def test_expired_credentials_surface_actionable_reason_in_evidence(env):
    c, _ = env(bedrock_fail=[client_error("ExpiredTokenException", "token is expired")])
    with c:
        _, rep = run(c)
        img_ev = next(e for e in rep["evidence"] if e["evidence_type"] == "ai_image_observation")
        assert "BEDROCK_NO_CREDENTIALS" in img_ev["observation"] and "expired" in img_ev["observation"].lower()


def test_location_outside_taluk_is_high_contradiction(env):
    c, _ = env()
    with c:
        _, rep = run(c, claimed_lat=13.0, claimed_lon=80.2)
        f = F(rep, "location")
        assert f["verdict"] == "contradicts" and f["severity"] == "high" and "outside the study taluk" in f["detail"]


def test_no_image_no_location_is_not_supported(env):
    c, _ = env()
    with c:
        _, rep = run(c, image=None)
        assert F(rep, "claim_vs_image")["verdict"] == "missing" and F(rep, "location")["verdict"] == "missing"
        assert rep["status"] == S_PARTIAL and rep["routing"]["human_review_required"]     # never 'Supported' without a photo


def test_unknown_parcel_is_missing_not_contradiction(env):
    c, _ = env()
    with c:
        _, rep = run(c, survey_no="99999")
        assert F(rep, "parcel")["verdict"] == "missing" and "not a contradiction" in F(rep, "parcel")["detail"]


def test_ambiguous_survey_without_village(env, make_csv):
    rows = [row(image_path=HEX_A, **CSV_ROW), row(**{"Village LG": "111111"}, image_path="bbbbbbbbbbbbbbbb-1-2", **CSV_ROW)]
    c, _ = env(csv_rows=rows)
    with c:
        cid = c.post("/api/claims", json={"survey_no": "293", "claimed_cause": "drought", "incident_date": "2024-11-05"}).json()["claim_id"]
        rep = c.post(f"/api/claims/{cid}/verify?narrative=template&analyze=false").json()
        assert F(rep, "parcel")["verdict"] == "inconclusive"


def test_ai_narrative_guard_discards_invented_numbers(env):
    good = {"summary": "The claim is supported by the available checks.", "key_points": ["Photo shows drought stress"], "recommended_actions": []}
    bad = {"summary": "About 87 percent of neighbours reported the same loss.", "key_points": [], "recommended_actions": []}
    c, fake = env(bedrock_fail=[ok_response(obs(DROUGHT)), ok_response(good)])
    with c:
        _, rep = run(c, params="narrative=auto")
        assert rep["narrative"]["source"] == "ai" and len(fake.calls) == 2
        assert fake.calls[1]["modelId"] == "amazon.nova-micro-v1:0"       # text role uses Nova Micro
    c2, _ = env(bedrock_fail=[ok_response(obs(DROUGHT)), ok_response(bad)], sub="b")
    with c2:
        _, rep = run(c2, params="narrative=auto")
        assert rep["narrative"]["source"] == "template"
        assert any(a["step"] == "report_narrative" and "NARRATIVE_INVENTED_NUMBERS" in a["status"] for a in rep["audit"])


def test_report_endpoints_and_404s(env):
    c, _ = env()
    with c:
        cid = c.post("/api/claims", json=CLAIM).json()["claim_id"]
        assert c.get(f"/api/claims/{cid}/report").json()["error"]["code"] == "REPORT_NOT_FOUND"
        assert c.post("/api/claims/CLM-NOPE/verify").status_code == 404
        run_cid, rep = run(c)
        got = c.get(f"/api/claims/{run_cid}/report").json()
        assert got["status"] == rep["status"] and got["timeline"] and got["provenance_legend"]["ai_observation"]
        ev = c.get(f"/api/claims/{run_cid}/evidence").json()
        assert "legend" in ev and len(ev["evidence"]) == len(rep["evidence"])
        assert [t["when"] for t in got["timeline"]] == sorted(t["when"] for t in got["timeline"])


def test_evidence_consistency_index_present_and_reconciles_with_breakdown(env):
    c, _ = env()
    with c:
        _, rep = run(c)
        sc = rep["scores"]
        assert "evidence_consistency_index" in sc and "breakdown" in sc
        assert sc["evidence_consistency_index"] == pytest.approx(round(sum(r["awarded_points"] for r in sc["breakdown"]), 1))
        assert 0 <= sc["evidence_consistency_index"] <= 100
        assert all(r["check_id"] and r["title"] for r in sc["breakdown"])
        assert "ACCUMULATED CONSISTENT EVIDENCE" in sc["formula"]
