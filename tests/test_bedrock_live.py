"""LIVE Bedrock test. Skipped unless RT_LIVE_BEDROCK=1 (makes 2 tiny real calls, fractions of a cent).
PowerShell:  $env:RT_LIVE_BEDROCK="1"; python -m pytest tests/test_bedrock_live.py -s"""
import os
from pathlib import Path

import pytest

from backend.config import get_settings
from backend.services.bedrock_service import BedrockService

pytestmark = pytest.mark.skipif(os.environ.get("RT_LIVE_BEDROCK") != "1", reason="set RT_LIVE_BEDROCK=1 to run")


def _sample_image():
    imgs = sorted(Path(get_settings().images_dir).rglob("*.jpg"), key=lambda p: p.stat().st_size)
    return imgs[0].read_bytes() if imgs else None


def test_text_model_reachable():
    out = BedrockService().check_model("text")
    assert out["working_id"], out


def test_vision_model_returns_valid_observation():
    img = _sample_image()
    if img is None:
        pytest.skip("no sample image in data/images")
    r = BedrockService().analyze_image(img, {"claimed_cause": "drought", "claimed_crop": "Rice (Paddy)"}, use_cache=False)
    print(r.model_dump_json(indent=2))
    assert r.ok, r.error
    assert r.parsed["observations"] and r.usage.input_tokens
