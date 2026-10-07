import pytest

from backend.verification.engine import evidence_consistency_breakdown, TITLES
from backend.schemas.verification import Finding
from backend.evidence.models import EvidenceItem


def ev(eid, quality="high"):
    return EvidenceItem(evidence_id=eid, source="s", source_kind="source_data", evidence_type="t",
                        observation="o", quality=quality, status="available")


def f(check_id, verdict, weight, evidence_ids=(), severity=None):
    return Finding(check_id=check_id, title=TITLES.get(check_id, check_id), verdict=verdict, severity=severity,
                  detail="d", evidence_ids=list(evidence_ids), weight=weight, independent=True, rule="r")


def test_titles_are_verdict_neutral_words_never_bake_in_an_outcome():
    banned = ("consistent", "found in", "visible in")
    for title in TITLES.values():
        assert not any(b in title.lower() for b in banned), title


def test_breakdown_max_points_sum_to_one_hundred():
    findings = [f("weather", "supports", 2, ["e1"]), f("location", "supports", 2, ["e2"]),
               f("crop", "inconclusive", 1, ["e3"])]
    W = sum(x.weight for x in findings)
    rows, _ = evidence_consistency_breakdown(findings, [ev("e1"), ev("e2"), ev("e3")], W)
    assert sum(r["max_points"] for r in rows) == pytest.approx(100.0)


def test_supports_with_high_quality_evidence_earns_full_max_points():
    findings = [f("weather", "supports", 2, ["e1"])]
    rows, total = evidence_consistency_breakdown(findings, [ev("e1", "high")], 2)
    assert rows[0]["awarded_points"] == pytest.approx(100.0) and total == pytest.approx(100.0)


def test_contradiction_earns_zero_points_regardless_of_evidence_quality():
    findings = [f("weather", "contradicts", 2, ["e1"], severity="high")]
    rows, total = evidence_consistency_breakdown(findings, [ev("e1", "high")], 2)
    assert rows[0]["awarded_points"] == 0.0 and total == 0.0


def test_missing_earns_zero_points():
    findings = [f("parcel", "missing", 1, [])]
    rows, total = evidence_consistency_breakdown(findings, [], 1)
    assert rows[0]["awarded_points"] == 0.0 and rows[0]["evidence_quality"] == 0.0


def test_inconclusive_earns_half_of_max_points_scaled_by_quality():
    findings = [f("timing", "inconclusive", 2, ["e1"])]
    rows, total = evidence_consistency_breakdown(findings, [ev("e1", "medium")], 2)
    # max_points=100, factor=0.5, quality(medium)=0.66 -> 33.0
    assert rows[0]["awarded_points"] == pytest.approx(33.0, abs=0.1)


def test_low_quality_evidence_reduces_awarded_points_even_when_supported():
    findings = [f("crop", "supports", 1, ["e1"])]
    rows_hi, total_hi = evidence_consistency_breakdown(findings, [ev("e1", "high")], 1)
    rows_lo, total_lo = evidence_consistency_breakdown(findings, [ev("e1", "low")], 1)
    assert total_hi > total_lo


def test_mixed_findings_breakdown_sums_exactly_to_reported_total():
    findings = [f("weather", "supports", 2, ["e1"]), f("location", "supports", 2, ["e2"]),
               f("claim_vs_image", "contradicts", 3, ["e3"], severity="high"),
               f("crop", "inconclusive", 2, ["e4"]), f("stage", "missing", 1, [])]
    ev_list = [ev("e1", "medium"), ev("e2", "high"), ev("e3", "high"), ev("e4", "medium")]
    W = sum(x.weight for x in findings)
    rows, total = evidence_consistency_breakdown(findings, ev_list, W)
    assert total == pytest.approx(round(sum(r["awarded_points"] for r in rows), 1))
    assert 0 <= total <= 100


def test_no_active_findings_gives_empty_breakdown_and_zero_total():
    rows, total = evidence_consistency_breakdown([], [], 1)
    assert rows == [] and total == 0.0
