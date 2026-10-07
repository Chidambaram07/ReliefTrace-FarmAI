from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .models import EvidenceItem, unavailable

log = logging.getLogger("reliefTrace.evidence")


@dataclass
class EvidenceContext:
    claim: dict
    images: list[dict]                 # claim_images rows
    dataset_images: dict[int, dict]    # image_key -> {"image": dataset row, "records": [...]}
    parcel: dict                       # from resolve_parcel()
    analyses: dict[int, dict | None]   # image_key -> AIResult dict (ok or failed) | None
    geo: Any                           # AdminLayers
    http: Any                          # HttpClient
    open_conn: Callable                # opens a private DB connection (thread safety)
    gt_tolerance: dict = field(default_factory=dict)   # percentiles of image->GT distance in the dataset
    village_code: str | None = None                      # claimed parcel's village code (boundary-layer join key)
    points: list = field(default_factory=list)          # located points, see adapters.collect_points()
    simulate_failure: frozenset = frozenset()


class EvidenceAdapter(Protocol):
    name: str

    def collect(self, ctx: EvidenceContext) -> list[EvidenceItem]: ...


def run_adapters(ctx: EvidenceContext, adapters: list[EvidenceAdapter]) -> tuple[list[EvidenceItem], list[dict]]:
    """Run adapters in parallel; one adapter failing never stops the others (fallback = 'unavailable')."""
    def _one(a: EvidenceAdapter):
        t0 = time.perf_counter()
        try:
            items = a.collect(ctx)
            status, err = "ok", None
        except Exception as e:  # noqa: BLE001
            log.exception("adapter %s failed", a.name)
            items = [unavailable(f"adapter:{a.name}", a.name, f"{a.name} adapter failed: {type(e).__name__}: {e}")]
            status, err = "failed", str(e)
        return a.name, items, {"step": f"evidence:{a.name}", "agent": a.name, "model": None, "status": status,
                               "duration_ms": int((time.perf_counter() - t0) * 1000), "detail": err}
    with ThreadPoolExecutor(max_workers=max(1, len(adapters))) as ex:
        results = list(ex.map(_one, adapters))
    items: list[EvidenceItem] = []
    audit = []
    for name, its, a in results:  # deterministic ordering
        for n, it in enumerate(its, 1):
            it.evidence_id = f"EV-{name[:4].upper()}-{n}"
        items += its
        a["detail"] = a["detail"] or f"{len(its)} item(s)"
        audit.append(a)
    return items, audit
