"""Visual similarity index over the FarmwiseAI challenge images, built with Amazon Titan
Multimodal Embeddings G1 (amazon.titan-embed-image-v1).

- build_index(): embeds every dataset image that has a file on disk. It is RESUMABLE (images that
  already have a vector for this model+dim are skipped), so an interrupted run costs nothing to
  continue, and re-running after the index is complete makes zero AWS calls.
- load_matrix()/top_k(): exact cosine similarity with numpy. ~3.3k vectors x 256 dims is a few MB,
  so no vector database is needed; brute-force search is instant and fully reproducible.

Vectors are stored with the model id and dimension they came from, and are only ever compared with
vectors from the same model+dim.
"""
from __future__ import annotations

import base64
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np

from backend.services.bedrock_service import prepare_image
from backend.services.model_client import BedrockError, ModelClient, candidate_ids

import os

MAX_EMBED_SIDE = 1024
RETRY_DELAYS = (1.0, 3.0, 8.0)


def embed_image_bytes(client: ModelClient, model_id: str, data: bytes, dim: int,
                      attempts: list | None = None) -> tuple[list[float], str]:
    """One real Titan Multimodal call. Raises BedrockError on failure (caller decides how to react)."""
    prepared, _, _ = prepare_image(data, MAX_EMBED_SIDE)  # normalises to JPEG and bounds the size
    body = {"inputImage": base64.b64encode(prepared).decode("ascii"),
            "embeddingConfig": {"outputEmbeddingLength": dim}}
    payload, used_id = client.invoke_json(candidate_ids(model_id), body, attempts=attempts)
    vec = payload.get("embedding")
    if not isinstance(vec, list) or not vec:
        raise BedrockError("EMBEDDING_INVALID", f"response had no 'embedding' vector (keys: {sorted(payload)})")
    return vec, used_id


def _embed_with_retry(client, model_id, data, dim):
    last: BedrockError | None = None
    for delay in (0.0, *RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return embed_image_bytes(client, model_id, data, dim)
        except BedrockError as e:
            last = e
            if not e.retryable:
                break
    raise last  # type: ignore[misc]


def store_vector(conn, image_id: str, model_id: str, dim: int, vec: list[float], sha: str | None) -> None:
    arr = np.asarray(vec, dtype=np.float32)
    conn.execute("INSERT OR REPLACE INTO image_embeddings VALUES (?,?,?,?,?,?)",
                 (image_id, model_id, dim, arr.tobytes(), sha, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def indexed_ids(conn, model_id: str, dim: int) -> set[str]:
    return {r[0] for r in conn.execute("SELECT image_id FROM image_embeddings WHERE model_id=? AND dim=?", (model_id, dim))}


def index_size(conn, model_id: str, dim: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM image_embeddings WHERE model_id=? AND dim=?", (model_id, dim)).fetchone()[0]


def load_matrix(conn, model_id: str, dim: int) -> tuple[list[str], np.ndarray]:
    """Returns (image_ids, L2-normalised float32 matrix [n, dim])."""
    rows = conn.execute("SELECT image_id, vector FROM image_embeddings WHERE model_id=? AND dim=? ORDER BY image_id",
                        (model_id, dim)).fetchall()
    if not rows:
        return [], np.zeros((0, dim), dtype=np.float32)
    ids = [r[0] for r in rows]
    m = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return ids, m / norms


def top_k(ids: list[str], matrix: np.ndarray, query: list[float], k: int,
          exclude: set[str] | None = None) -> list[tuple[str, float]]:
    q = np.asarray(query, dtype=np.float32)
    n = np.linalg.norm(q)
    if n == 0 or matrix.shape[0] == 0 or q.shape[0] != matrix.shape[1]:
        return []
    sims = matrix @ (q / n)
    order = np.argsort(-sims)
    out: list[tuple[str, float]] = []
    for idx in order:
        if exclude and ids[idx] in exclude:
            continue
        out.append((ids[idx], float(sims[idx])))
        if len(out) >= k:
            break
    return out


def build_index(conn, client: ModelClient, model_id: str, dim: int, images: list[dict], *,
                workers: int = 4, limit: Optional[int] = None,
                progress: Optional[Callable[[int, int, int], None]] = None) -> dict:
    """images: [{"image_id", "file_path"}]. Embeds those not yet indexed. Returns run statistics.
    All DB writes happen on the calling thread; worker threads only read files and call Bedrock."""
    done = indexed_ids(conn, model_id, dim)
    todo = [i for i in images if i["image_id"] not in done and i.get("file_path")]
    if limit is not None:
        todo = todo[:limit]
    stats = {"total_images": len(images), "already_indexed": len(done & {i["image_id"] for i in images}),
             "attempted": len(todo), "embedded": 0, "failed": 0, "failures": []}

    def work(item):
        with open(item["file_path"], "rb") as fh:
            data = fh.read()
        vec, _ = _embed_with_retry(client, model_id, data, dim)
        return item["image_id"], vec, hashlib.sha256(data).hexdigest()

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(work, it): it for it in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            it = futures[fut]
            try:
                image_id, vec, sha = fut.result()
                store_vector(conn, image_id, model_id, dim, vec, sha)
                stats["embedded"] += 1
            except Exception as e:  # noqa: BLE001  (one bad image must not abort the whole build)
                stats["failed"] += 1
                msg = f"{e.code}: {e.message}" if isinstance(e, BedrockError) else f"{type(e).__name__}: {e}"
                stats["failures"].append({"image_id": it["image_id"], "error": msg[:300]})
            if n % 50 == 0:
                conn.commit()
            if progress:
                progress(n, len(todo), stats["failed"])
    conn.commit()
    return stats


def image_embed_dim() -> int:
    return int(os.environ.get("TITAN_IMAGE_EMBED_DIM", "256"))
