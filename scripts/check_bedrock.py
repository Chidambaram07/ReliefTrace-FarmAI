"""Find out which Nova model IDs your AWS account can actually call (no IAM changes, ~2-3 tiny calls).

    python -m scripts.check_bedrock            # text + vision (uses the smallest image in data/images)
    python -m scripts.check_bedrock --no-image # text calls only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.config import get_settings
from backend.services.bedrock_service import BedrockService, BedrockSettings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-image", action="store_true")
    a = ap.parse_args()
    cfg = BedrockSettings.from_env()
    svc = BedrockService(cfg)
    print(f"Region: {cfg.region}   vision: {cfg.vision_model_id}   text: {cfg.text_model_id}")
    try:
        import boto3
        ident = boto3.client("sts", region_name=cfg.region).get_caller_identity()
        print(f"Identity: {ident['Arn']}")
    except Exception as e:  # noqa: BLE001  (sts may be denied; not required)
        print(f"Identity: (could not read: {type(e).__name__})")

    image = None
    if not a.no_image:
        imgs = sorted(Path(get_settings().images_dir).rglob("*.jpg"), key=lambda p: p.stat().st_size)
        image = imgs[0].read_bytes() if imgs else None
        if image is None:
            print("No sample image found in data/images; vision check will be text-only.")

    exit_code = 0
    env_lines = []
    for role, img in (("text", None), ("vision", image)):
        res = svc.check_model(role, img)
        print(f"\n[{role}] configured: {res['configured']}")
        for at in res["attempts"]:
            print(f"   tried {at['model_id']}: " + ("OK" if at["ok"] else f"FAILED {at.get('code')} - {at.get('message', '')[:200]}"))
        if res["working_id"]:
            print(f"   => WORKS: {res['working_id']}   sample reply: {res.get('sample')!r}")
            env_lines.append(f"BEDROCK_{role.upper()}_MODEL_ID={res['working_id']}")
        else:
            exit_code = 1
            print(f"   => NOT USABLE: {res['error']['code']}")
    if env_lines:
        print("\nPut this in your .env:\n  " + "\n  ".join(env_lines))
    if exit_code:
        print("\nIf you see AccessDenied on every ID, tell your organisers which model ID/profile your role is allowed to invoke. Do not change IAM yourself.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
