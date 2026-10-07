"""Claim validation against the reference data: which parcel (village + survey [+ subdivision]) is claimed?"""
from __future__ import annotations

from backend.repositories import dataset as ds


def resolve_parcel(conn, claim: dict) -> dict:
    if not ds.dataset_loaded(conn):
        return {"status": "dataset_unavailable", "records": [], "villages": [], "village_lgd": claim.get("village_lgd")}
    total, rows = ds.find_parcels(conn, village_lgd=claim.get("village_lgd"), survey_no=claim.get("survey_no"),
                                  subdivision=claim.get("subdivision"), limit=500)
    villages = sorted({r["village_lgd"] for r in rows if r["village_lgd"]})
    if not rows and claim.get("subdivision"):  # subdivision may be mistyped: retry without it, but say so
        total, rows = ds.find_parcels(conn, village_lgd=claim.get("village_lgd"), survey_no=claim.get("survey_no"), limit=500)
        villages = sorted({r["village_lgd"] for r in rows if r["village_lgd"]})
        if rows:
            return {"status": "found_ignoring_subdivision", "records": rows, "villages": villages,
                    "village_lgd": villages[0] if len(villages) == 1 else claim.get("village_lgd")}
    if not rows:
        return {"status": "not_found", "records": [], "villages": [], "village_lgd": claim.get("village_lgd")}
    if len(villages) > 1:  # survey number only, exists in several villages
        return {"status": "ambiguous", "records": rows, "villages": villages, "village_lgd": None}
    return {"status": "found", "records": rows, "villages": villages, "village_lgd": villages[0]}
