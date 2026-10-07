"""Run the model-availability health check across the full model registry
(Nova Lite, Nova Micro, Ministral 3B, Ministral 8B, Titan Text Embeddings V2).

Distinguishes: disabled / not_configured / invokable / invocation_failed. Catalog visibility
(bedrock:GetFoundationModel) is checked separately and reported as informational only - never
substituted for an actual invocation result.

Makes at most one minimal call per enabled+configured model (5 max). Never invents a result for
a model with no configured id.

    python -m scripts.check_models                 # print only
    python -m scripts.check_models --db data/processed/reliefTrace.db   # also persist to the audit table
    python -m scripts.check_models --no-catalog     # skip the (informational) catalog-visibility calls
"""
from __future__ import annotations

import argparse
import sys

from backend.services.model_client import ClientSettings, ModelClient
from backend.services.model_health import Availability, check_all
from backend.services.model_registry import build_registry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None, help="SQLite path to persist results into model_health_checks")
    ap.add_argument("--no-catalog", action="store_true", help="skip informational catalog-visibility checks")
    a = ap.parse_args()

    registry = build_registry()
    client = ModelClient(ClientSettings(region="ap-south-1"))  # region is fixed for this challenge

    try:
        import boto3
        ident = boto3.client("sts", region_name="ap-south-1").get_caller_identity()
        print(f"Identity: {ident['Arn']}")
    except Exception as e:  # noqa: BLE001
        print(f"Identity: (could not read: {type(e).__name__})")
    print("Region: ap-south-1\n")

    results = check_all(client, registry, check_catalog=not a.no_catalog)

    for spec, r in zip(registry.values(), results):
        print(f"[{spec.key}] provider={spec.provider} configured_id={spec.model_id or '(none)'} "
              f"enabled={spec.enabled}")
        print(f"   availability: {r.availability.value}"
              + (f"   catalog_visible={r.catalog_visible}" if r.catalog_visible is not None else "   catalog_visible=unknown"))
        if r.attempts:
            for at in r.attempts:
                print(f"   tried {at['model_id']}: " + ("OK" if at["ok"] else f"FAILED {at.get('code')} - {at.get('message', '')[:200]}"))
        if r.availability is Availability.INVOKABLE:
            print(f"   latency_ms={r.latency_ms}")
        elif r.availability is Availability.INVOCATION_FAILED:
            print(f"   error: {r.error_code} - {r.error_message}")
        else:
            print(f"   reason: {r.error_message}")
        print()

    if a.db:
        from backend.dataset import db
        from backend.repositories import model_health as repo
        from backend.storage.schema import init_model_health_schema
        conn = db.connect(a.db)
        init_model_health_schema(conn)
        ids = repo.record_all(conn, results)
        conn.close()
        print(f"Recorded {len(ids)} health-check rows in {a.db} (table model_health_checks)")

    invokable = [r for r in results if r.availability is Availability.INVOKABLE]
    failed = [r for r in results if r.availability is Availability.INVOCATION_FAILED]
    print(f"Summary: {len(invokable)} invokable, {len(failed)} invocation_failed, "
          f"{len(results) - len(invokable) - len(failed)} skipped (disabled/not_configured).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
