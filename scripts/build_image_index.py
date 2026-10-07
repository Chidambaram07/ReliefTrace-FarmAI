"""Build the full visual-similarity index over the challenge images with Titan Multimodal Embeddings.

    python -m scripts.build_image_index --dry-run          # count what would be embedded, no AWS calls
    python -m scripts.build_image_index --limit 20         # small real test first (20 Bedrock calls)
    python -m scripts.build_image_index                    # full index (resumable: re-run to continue)

One Bedrock call per image (about 3,273 for the full dataset). Already-indexed images are skipped, so
an interrupted run can simply be started again. Needs valid AWS credentials in this shell (ap-south-1).
"""
from __future__ import annotations

import argparse
import sys
import time

from backend.agentic import image_index
from backend.config import get_settings
from backend.dataset import db
from backend.services.model_client import ClientSettings, ModelClient
from backend.services.model_registry import build_registry
from backend.storage.schema import init_image_index_schema


def main() -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(s.db_path))
    ap.add_argument("--limit", type=int, default=None, help="embed at most N not-yet-indexed images")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    spec = build_registry()["titan_embed_image_v1"]
    if not (spec.enabled and spec.configured):
        print("titan_embed_image_v1 is disabled or not configured in the model registry")
        return 2
    dim = image_index.image_embed_dim()
    conn = db.connect(a.db)
    init_image_index_schema(conn)
    rows = conn.execute("SELECT image_id, file_path FROM images WHERE file_status='found'").fetchall()
    images = [{"image_id": r[0], "file_path": r[1]} for r in rows]
    done = image_index.indexed_ids(conn, spec.model_id, dim)
    pending = [i for i in images if i["image_id"] not in done]
    print(f"model={spec.model_id} dim={dim} images_with_files={len(images)} already_indexed={len(done)} pending={len(pending)}")
    if a.dry_run or not pending:
        print("dry run: no AWS calls made" if a.dry_run else "nothing to do")
        return 0

    client = ModelClient(ClientSettings(region="ap-south-1"))
    t0 = time.time()

    def progress(n, total, failed):
        if n % 25 == 0 or n == total:
            rate = n / max(time.time() - t0, 0.001)
            print(f"  {n}/{total} embedded (failed so far: {failed}) {rate:.1f} img/s", flush=True)

    stats = image_index.build_index(conn, client, spec.model_id, dim, images, workers=a.workers,
                                    limit=a.limit, progress=progress)
    print(f"\nembedded={stats['embedded']} failed={stats['failed']} index_size={image_index.index_size(conn, spec.model_id, dim)}")
    for f in stats["failures"][:10]:
        print(f"  FAILED {f['image_id']}: {f['error']}")
    if stats["failed"] > 10:
        print(f"  ... and {stats['failed'] - 10} more failures")
    if stats["failures"] and any("NO_CREDENTIALS" in f["error"] for f in stats["failures"]):
        print("\nCredentials look expired: paste fresh AWS keys and re-run; progress so far is kept.")
    conn.close()
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
