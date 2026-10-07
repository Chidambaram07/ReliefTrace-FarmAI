import json
from pathlib import Path

from backend.schemas.claim import ClaimCreate

DEMO = Path(__file__).resolve().parent.parent / "demo" / "claims.json"


def test_demo_claims_are_valid_and_labelled_synthetic():
    demos = json.loads(DEMO.read_text(encoding="utf-8"))
    assert len(demos) >= 3
    for d in demos:
        c = ClaimCreate.model_validate(d["claim"])
        assert c.description.startswith("DEMO INPUT (synthetic claim") and d["image_id"]
