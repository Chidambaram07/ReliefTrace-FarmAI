from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_report(conn: Any, claim_id: str, report: dict) -> int:
    if hasattr(conn, "verification"):
        return conn.verification.save_report(claim_id, report)
    cur = conn.execute("INSERT INTO verification_reports (claim_id, created_at, status, confidence, human_review, report_json) VALUES (?,?,?,?,?,?)",
                       (claim_id, _now(), report["status"], report["scores"]["confidence_index"],
                        int(report["routing"]["human_review_required"]), json.dumps(report)))
    conn.execute("UPDATE claims SET status='reported' WHERE claim_id=?", (claim_id,))
    conn.commit()
    return cur.lastrowid


def latest_report(conn: Any, claim_id: str):
    if hasattr(conn, "verification"):
        return conn.verification.latest_report(claim_id)
    r = conn.execute("SELECT * FROM verification_reports WHERE claim_id=? ORDER BY report_id DESC LIMIT 1", (claim_id,)).fetchone()
    if not r:
        return None
    return {"report_id": r["report_id"], "created_at": r["created_at"], "report": json.loads(r["report_json"])}


def sync_queue(conn: Any, claim_id: str, needs_review: bool, reasons: list[str]) -> str | None:
    if hasattr(conn, "verification"):
        return conn.verification.sync_queue(claim_id, needs_review, reasons)
    if needs_review:
        conn.execute("INSERT OR REPLACE INTO review_queue (claim_id, created_at, reasons, status) VALUES (?,?,?, 'open')",
                     (claim_id, _now(), json.dumps(reasons)))
        conn.commit()
        return "open"
    conn.execute("DELETE FROM review_queue WHERE claim_id=? AND status='open'", (claim_id,))
    conn.commit()
    return None


def list_queue(conn: Any, status: str | None):
    if hasattr(conn, "verification"):
        return conn.verification.list_queue(status)
    q = ("SELECT q.*, c.claimed_cause, c.survey_no, c.village_lgd, c.incident_date, "
         "(SELECT status FROM verification_reports v WHERE v.claim_id=q.claim_id ORDER BY report_id DESC LIMIT 1) AS report_status, "
         "(SELECT confidence FROM verification_reports v WHERE v.claim_id=q.claim_id ORDER BY report_id DESC LIMIT 1) AS confidence "
         "FROM review_queue q JOIN claims c USING (claim_id)")
    rows = conn.execute(q + (" WHERE q.status=?" if status else "") + " ORDER BY q.created_at DESC", ([status] if status else [])).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["reasons"] = json.loads(d["reasons"])
        out.append(d)
    return out


def decide(conn: Any, claim_id: str, decision: str, note: str | None) -> bool:
    if hasattr(conn, "verification"):
        return conn.verification.decide(claim_id, decision, note)
    row = conn.execute("SELECT * FROM review_queue WHERE claim_id=?", (claim_id,)).fetchone()
    if not row:
        return False
    now_iso = _now()
    cur = conn.execute("UPDATE review_queue SET status='decided', decision=?, note=?, decided_at=? WHERE claim_id=?",
                       (decision, note, now_iso, claim_id))
    if cur.rowcount == 0:
        return False

    if decision in ("approve", "approve_for_processing"):
        final_status = "approved_for_processing" if decision == "approve_for_processing" else "approved"
    elif decision == "reject":
        final_status = "rejected"
    elif decision == "request_more_information":
        final_status = "request_more_information"
    else:
        final_status = decision

    conn.execute("UPDATE claims SET status=? WHERE claim_id=?", (final_status, claim_id))

    rep_row = conn.execute(
        "SELECT report_id, report_json FROM verification_reports WHERE claim_id=? ORDER BY report_id DESC LIMIT 1",
        (claim_id,)
    ).fetchone()
    if rep_row:
        try:
            report_data = json.loads(rep_row["report_json"])
            report_data["human_decision"] = {
                "decision": decision,
                "note": note,
                "decided_at": now_iso,
                "recorded_by": "human reviewer",
                "final_claim_status": final_status,
            }
            timeline = report_data.setdefault("timeline", [])
            timeline.append({
                "when": now_iso,
                "kind": "human_decision",
                "label": f"Human Review Decision: {decision}",
                "event": f"Human Review Decision: {decision}",
                "actor": "Human Reviewer",
                "note": note or "",
            })
            audit = report_data.setdefault("audit", [])
            audit.append({
                "step": "human_review_decision",
                "agent": "human_reviewer",
                "status": decision,
                "duration_ms": 0,
                "detail": note or f"Final human decision: {decision}",
            })
            conn.execute(
                "UPDATE verification_reports SET report_json=? WHERE report_id=?",
                (json.dumps(report_data), rep_row["report_id"])
            )
        except Exception:
            pass

    conn.commit()
    return True


def stats(conn: Any) -> dict:
    if hasattr(conn, "verification"):
        return conn.verification.stats()
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    by_status = {r[0]: r[1] for r in conn.execute(
        "SELECT status, COUNT(*) FROM verification_reports v WHERE report_id=(SELECT MAX(report_id) FROM verification_reports WHERE claim_id=v.claim_id) GROUP BY 1")}
    return {"claims": q("SELECT COUNT(*) FROM claims"), "reported": q("SELECT COUNT(DISTINCT claim_id) FROM verification_reports"),
            "by_status": by_status, "review_open": q("SELECT COUNT(*) FROM review_queue WHERE status='open'"),
            "review_decided": q("SELECT COUNT(*) FROM review_queue WHERE status='decided'"),
            "ai_calls": q("SELECT COUNT(*) FROM image_analyses WHERE cached=0")}
