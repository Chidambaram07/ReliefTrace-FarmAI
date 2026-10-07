"""Load the demo claims into a RUNNING API (claims are synthetic test inputs; photos + reference data are the real challenge data).

    python -m scripts.seed_demo                       # create claims + attach photos
    python -m scripts.seed_demo --verify              # also run verification (uses Bedrock: 1 vision call per claim)
    python -m scripts.seed_demo --verify --narrative template   # no text-model calls
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo" / "claims.json"


def call(base, method, path, body=None, timeout=180):
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read() or b"{}").get("error", {"code": f"HTTP_{e.code}", "message": str(e)})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--narrative", default="auto", choices=["auto", "template", "off"])
    a = ap.parse_args()
    for d in json.loads(DEMO.read_text(encoding="utf-8")):
        c = call(a.base, "POST", "/api/claims", d["claim"])
        if "error" in c:
            print(f"! {d['label']}: {c['error']}")
            continue
        cid = c["claim_id"]
        att = call(a.base, "POST", f"/api/claims/{cid}/images/from-dataset", {"image_id": d["image_id"]})
        note = "" if "error" not in att else f" (image not attached: {att['error']['code']})"
        print(f"{cid}  {d['label']}{note}")
        if a.verify:
            r = call(a.base, "POST", f"/api/claims/{cid}/verify?narrative={a.narrative}")
            if "error" in r:
                print(f"    verify failed: {r['error']['code']} - {r['error']['message'][:160]}")
            else:
                print(f"    -> {r['status']} | ECI {r['scores'].get('evidence_consistency_index', r['scores']['confidence_index'])} | human review: {r['routing']['human_review_required']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
