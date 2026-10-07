"""Historical weather evidence from Open-Meteo (free, no key). Reanalysis-based gridded data, NOT station records.

One request per (location, date) covers both the observed window and a 10-year same-season baseline.
Flow: cache -> network -> fallback cache -> 'unavailable' (verification then treats weather as missing evidence).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .base import EvidenceContext
from .models import EvidenceItem, Location, unavailable

SOURCE = "Open-Meteo Historical Weather API (reanalysis grid)"
BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = "precipitation_sum,temperature_2m_max,wind_gusts_10m_max"
WINDOW_DAYS = 30
BASELINE_YEARS = 10
ARCHIVE_LAG_DAYS = 6


class HttpClient:
    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def get_json(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": "ReliefTrace/0.1 (hackathon prototype)"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (fixed https host)
            return json.loads(r.read().decode("utf-8"))


def build_url(lat: float, lon: float, start: date, end: date) -> str:
    q = {"latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}", "start_date": start.isoformat(),
         "end_date": end.isoformat(), "daily": DAILY, "timezone": "Asia/Kolkata"}
    return os.environ.get("RT_WEATHER_URL", BASE_URL) + "?" + urllib.parse.urlencode(q)


def parse_daily(payload: dict) -> dict[date, dict]:
    d = payload["daily"]
    out = {}
    for i, t in enumerate(d["time"]):
        out[date.fromisoformat(t)] = {"precip": d["precipitation_sum"][i], "tmax": d["temperature_2m_max"][i],
                                      "gust": d["wind_gusts_10m_max"][i]}
    return out


def window_stats(series: dict[date, dict], end: date, days: int = WINDOW_DAYS) -> dict | None:
    rows = [series.get(end - timedelta(days=i)) for i in range(days - 1, -1, -1)]
    precip = [r["precip"] if r else None for r in rows]
    if sum(p is not None for p in precip) < 0.8 * days:
        return None
    p = [x or 0.0 for x in precip]
    gusts = [r["gust"] for r in rows if r and r["gust"] is not None]
    tmax = [r["tmax"] for r in rows if r and r["tmax"] is not None]
    return {"sum_mm": round(sum(p), 1), "dry_days": sum(1 for x in p if x < 1.0), "max_daily_mm": round(max(p), 1),
            "max_3d_mm": round(max(sum(p[i:i + 3]) for i in range(len(p) - 2)), 1),
            "max_gust_kmh": round(max(gusts), 1) if gusts else None,
            "tmax_mean_c": round(sum(tmax) / len(tmax), 1) if tmax else None}


def percentile_rank(value, sample: list) -> float | None:
    s = [x for x in sample if x is not None]
    if value is None or not s:
        return None
    return round(100 * (sum(x < value for x in s) + 0.5 * sum(x == value for x in s)) / len(s), 1)


def median(xs: list) -> float | None:
    s = sorted(x for x in xs if x is not None)
    if not s:
        return None
    n = len(s)
    return round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2, 1)


def analyse(series: dict[date, dict], incident: date) -> dict | None:
    end = incident + timedelta(days=1)
    obs = window_stats(series, end)
    if obs is None:
        return None
    base = []
    for y in range(incident.year - BASELINE_YEARS, incident.year):
        try:
            st = window_stats(series, date(y, end.month, end.day))
        except ValueError:  # 29 Feb
            st = None
        if st:
            base.append(st)
    keys = ("sum_mm", "max_3d_mm", "max_gust_kmh", "dry_days")
    return {"window_start": (end - timedelta(days=WINDOW_DAYS - 1)).isoformat(), "window_end": end.isoformat(),
            "observed": obs, "baseline_years": len(base),
            "baseline_median": {k: median([b[k] for b in base]) for k in keys},
            "percentile": {k: percentile_rank(obs[k], [b[k] for b in base]) for k in keys}}


def fetch_weather_payload(url: str, http, open_conn, simulate_failure: bool = False) -> tuple[dict | None, str | None, str | None]:
    """Cache -> network -> fallback-to-cache, exactly the flow WeatherAdapter uses, factored out so
    any other caller (e.g. the standalone weather tool in backend/agentic/tools.py) gets identical
    cost-control and failure-recovery behaviour instead of a second, drifting implementation.
    Returns (payload, served_from, error) where served_from is 'cache' | 'network' | 'fallback_cache' | None."""
    payload, served, err = None, None, None
    conn = open_conn()
    try:
        def cache_get():
            try:
                r = conn.execute("SELECT payload FROM evidence_cache WHERE cache_key=?", (url,)).fetchone()
                return json.loads(r[0]) if r else None
            except Exception:
                return None
        if simulate_failure:
            err = "Simulated data-source outage (demo)"
        else:
            payload = cache_get()
            served = "cache" if payload else None
            if payload is None:
                try:
                    payload, served = http.get_json(url), "network"
                    try:
                        conn.execute("INSERT OR REPLACE INTO evidence_cache VALUES (?,?,?)",
                                     (url, json.dumps(payload), datetime.now(timezone.utc).isoformat()))
                        conn.commit()
                    except Exception:
                        pass
                except Exception as e:  # noqa: BLE001
                    err = f"{type(e).__name__}: {e}"
        if payload is None:  # fallback path
            payload = cache_get()
            served = "fallback_cache" if payload else None
    finally:
        conn.close()
    return payload, served, err


class WeatherAdapter:
    name = "weather"

    def _point(self, ctx: EvidenceContext):
        for role in ("image_dataset", "gt_point", "claimed", "village_centroid"):
            for p in ctx.points:
                if p["role"] == role:
                    return p
        return None

    def collect(self, ctx: EvidenceContext) -> list[EvidenceItem]:
        incident = date.fromisoformat(ctx.claim["incident_date"])
        if incident > datetime.now(timezone.utc).date() - timedelta(days=ARCHIVE_LAG_DAYS):
            return [unavailable(SOURCE, "weather", "Incident is too recent for the historical archive (lag ~5 days)")]
        pt = self._point(ctx)
        if pt is None:
            return [unavailable(SOURCE, "weather", "No location available to query weather for")]
        end = incident + timedelta(days=1)
        start = date(incident.year - BASELINE_YEARS, end.month, min(end.day, 28)) - timedelta(days=WINDOW_DAYS)
        url = build_url(pt["lat"], pt["lon"], start, end)
        payload, served, err = fetch_weather_payload(url, ctx.http, ctx.open_conn, "weather" in ctx.simulate_failure)
        if payload is None:
            return [unavailable(SOURCE, "weather", f"Weather source unavailable and no cached copy ({err})",
                                raw_reference=url, timestamp=incident.isoformat())]
        try:
            res = analyse(parse_daily(payload), incident)
        except Exception as e:  # noqa: BLE001
            return [unavailable(SOURCE, "weather", f"Weather response could not be parsed ({e})", raw_reference=url)]
        if res is None:
            return [unavailable(SOURCE, "weather", "Weather series too incomplete for this window", raw_reference=url)]
        o, m, pc = res["observed"], res["baseline_median"], res["percentile"]
        obs = (f"30 days to {res['window_end']}: rainfall {o['sum_mm']} mm (same-window {res['baseline_years']}-year median "
               f"{m['sum_mm']} mm; percentile {pc['sum_mm']}), {o['dry_days']} dry days, heaviest 3-day total {o['max_3d_mm']} mm "
               f"(percentile {pc['max_3d_mm']}), max gust {o['max_gust_kmh']} km/h (percentile {pc['max_gust_kmh']}).")
        lims = ["Gridded reanalysis (~10 km), not a rain-gauge or field measurement",
                "Baseline = same 30-day window in the previous 10 years",
                "Says nothing about pests, disease or local hail"]
        if served == "fallback_cache":
            lims.append(f"Primary source failed ({err}); served from cached copy")
        return [EvidenceItem(source=SOURCE, source_kind="external_evidence", evidence_type="weather",
                             timestamp=res["window_end"], location=Location(lat=pt["lat"], lon=pt["lon"], label=pt["label"]),
                             observation=obs, data={**res, "served_from": served, "fallback_used": served == "fallback_cache"},
                             quality="medium", limitations=lims, raw_reference=url)]
