"""DynamoDB Storage & Repository implementation for ReliefTrace (Team 56).
Targets table `fai-tce-team56-claims` in region `ap-south-1`.
Single-table design with `claim_id` as primary HASH key.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

log = logging.getLogger("reliefTrace.dynamo")

CLAIM_COLS = (
    "farmer_name", "village_lgd", "survey_no", "subdivision", "claimed_cause",
    "claimed_crop", "claimed_stage", "incident_date", "claimed_lat", "claimed_lon", "description"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_decimal(obj: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB serialization."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(_to_decimal(v) for v in obj)
    return obj


def _from_decimal(obj: Any) -> Any:
    """Recursively convert Decimals back to float/int for Python application usage."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: _from_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_from_decimal(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(_from_decimal(v) for v in obj)
    return obj


class DynamoClaimsRepository:
    def __init__(self, table, s3_bucket: str = "fai-tce-team56-images"):
        self.table = table
        self.s3_bucket = s3_bucket

    def create_claim(self, data: dict) -> dict:
        cid = "CLM-" + uuid.uuid4().hex[:8].upper()
        now_iso = _now()
        item = {
            "claim_id": cid,
            "PK": f"CLAIM#{cid}",
            "SK": "METADATA",
            "entity_type": "claim",
            "created_at": now_iso,
            "status": "submitted",
            "images": [],
            "image_counter": 0,
            "report_counter": 0,
        }
        for col in CLAIM_COLS:
            item[col] = data.get(col)

        self.table.put_item(Item=_to_decimal(item))
        log.info("DynamoDB claim created id=%s cause=%s survey=%s", cid, item.get("claimed_cause"), item.get("survey_no"))
        return self.get_claim(cid)

    def get_claim(self, claim_id: str) -> dict | None:
        try:
            res = self.table.get_item(Key={"claim_id": claim_id})
            item = res.get("Item")
            if not item:
                return None
            item = _from_decimal(item)
            out = {
                "claim_id": item["claim_id"],
                "created_at": item.get("created_at", ""),
                "status": item.get("status", "submitted"),
            }
            for col in CLAIM_COLS:
                out[col] = item.get(col)
            return out
        except Exception as e:
            log.error("DynamoDB get_claim failed for %s: %s", claim_id, e)
            return None

    def list_claims(self, limit: int = 50, offset: int = 0) -> tuple[int, list[dict]]:
        try:
            # Scan for claim items
            res = self.table.scan(
                FilterExpression="SK = :sk",
                ExpressionAttributeValues={":sk": "METADATA"}
            )
            items = [_from_decimal(i) for i in res.get("Items", [])]
            # Sort by created_at DESC, claim_id
            items.sort(key=lambda x: (x.get("created_at", ""), x.get("claim_id", "")), reverse=True)
            total = len(items)
            page = items[offset: offset + limit]
            out = []
            for item in page:
                c = {
                    "claim_id": item["claim_id"],
                    "created_at": item.get("created_at", ""),
                    "status": item.get("status", "submitted"),
                }
                for col in CLAIM_COLS:
                    c[col] = item.get(col)
                out.append(c)
            return total, out
        except Exception as e:
            log.error("DynamoDB list_claims failed: %s", e)
            return 0, []

    def add_claim_image(self, claim_id: str, rec: dict) -> int:
        res = self.table.get_item(Key={"claim_id": claim_id})
        claim_item = res.get("Item")
        if not claim_item:
            raise ValueError(f"No claim '{claim_id}'")
        claim_item = _from_decimal(claim_item)

        images = claim_item.get("images", [])
        # Check uniqueness: (claim_id, sha256) and (claim_id, dataset_image_id)
        for img in images:
            if rec.get("sha256") and img.get("sha256") == rec.get("sha256"):
                raise sqlite3.IntegrityError("UNIQUE constraint failed: claim_images.claim_id, claim_images.sha256")
            if rec.get("dataset_image_id") and img.get("dataset_image_id") == rec.get("dataset_image_id"):
                raise sqlite3.IntegrityError("UNIQUE constraint failed: claim_images.claim_id, claim_images.dataset_image_id")

        image_key = int(claim_item.get("image_counter", 0)) + 1
        now_iso = _now()
        img_item = {
            "claim_id": f"CLAIM#{claim_id}#IMAGE#{image_key}",
            "PK": f"CLAIM#{claim_id}",
            "SK": f"IMAGE#{image_key}",
            "entity_type": "image",
            "parent_claim_id": claim_id,
            "image_key": image_key,
            "source": rec["source"],
            "dataset_image_id": rec.get("dataset_image_id"),
            "filename": rec.get("filename"),
            "file_path": rec.get("file_path"),
            "sha256": rec.get("sha256"),
            "mime": rec.get("mime"),
            "width": rec.get("width"),
            "height": rec.get("height"),
            "size_bytes": rec.get("size_bytes"),
            "exif_gps_lat": rec.get("exif_gps_lat"),
            "exif_gps_lon": rec.get("exif_gps_lon"),
            "exif_captured_at": rec.get("exif_captured_at"),
            "created_at": now_iso,
        }

        # Put image sub-item
        self.table.put_item(Item=_to_decimal(img_item))

        # Update parent claim item
        images.append(img_item)
        claim_item["images"] = images
        claim_item["image_counter"] = image_key
        self.table.put_item(Item=_to_decimal(claim_item))
        log.info("DynamoDB image added claim=%s key=%s sha=%s", claim_id, image_key, str(rec.get("sha256"))[:12])
        return image_key

    def list_claim_images(self, claim_id: str) -> list[dict]:
        res = self.table.get_item(Key={"claim_id": claim_id})
        claim_item = res.get("Item")
        if not claim_item:
            return []
        claim_item = _from_decimal(claim_item)
        imgs = claim_item.get("images", [])
        imgs.sort(key=lambda x: x.get("image_key", 0))
        return imgs

    def get_claim_image(self, claim_id: str, image_key: int) -> dict | None:
        images = self.list_claim_images(claim_id)
        for img in images:
            if img.get("image_key") == image_key:
                return img
        return None


class DynamoVerificationRepository:
    def __init__(self, table):
        self.table = table

    def save_report(self, claim_id: str, report: dict) -> int:
        now_iso = _now()
        res = self.table.get_item(Key={"claim_id": claim_id})
        claim_item = res.get("Item")
        report_counter = 0
        if claim_item:
            claim_item = _from_decimal(claim_item)
            report_counter = int(claim_item.get("report_counter", 0))

        report_id = report_counter + 1
        confidence = report.get("scores", {}).get("confidence_index", 0.0)
        human_review = 1 if report.get("routing", {}).get("human_review_required") else 0
        status = report.get("status", "reported")

        report_item = {
            "claim_id": f"CLAIM#{claim_id}#REPORT#{report_id}",
            "PK": f"CLAIM#{claim_id}",
            "SK": f"REPORT#{report_id}",
            "entity_type": "report",
            "parent_claim_id": claim_id,
            "report_id": report_id,
            "created_at": now_iso,
            "status": status,
            "confidence": confidence,
            "human_review": human_review,
            "report_json": json.dumps(report),
        }
        self.table.put_item(Item=_to_decimal(report_item))

        # Update claim status to 'reported' and store latest report pointer
        if claim_item:
            claim_item["status"] = "reported"
            claim_item["report_counter"] = report_id
            claim_item["latest_report_id"] = report_id
            claim_item["latest_report_json"] = json.dumps(report)
            claim_item["latest_report_created_at"] = now_iso
            self.table.put_item(Item=_to_decimal(claim_item))

        log.info("DynamoDB report saved claim=%s report_id=%s status=%s", claim_id, report_id, status)
        return report_id

    def latest_report(self, claim_id: str) -> dict | None:
        try:
            res = self.table.get_item(Key={"claim_id": claim_id})
            claim_item = res.get("Item")
            if not claim_item:
                return None
            claim_item = _from_decimal(claim_item)
            if "latest_report_json" in claim_item:
                return {
                    "report_id": claim_item.get("latest_report_id", 1),
                    "created_at": claim_item.get("latest_report_created_at", _now()),
                    "report": json.loads(claim_item["latest_report_json"]),
                }
            return None
        except Exception as e:
            log.error("DynamoDB latest_report failed for %s: %s", claim_id, e)
            return None

    def sync_queue(self, claim_id: str, needs_review: bool, reasons: list[str]) -> str | None:
        queue_key = f"QUEUE#{claim_id}"
        if needs_review:
            now_iso = _now()
            # Fetch claim for snapshot
            claim_res = self.table.get_item(Key={"claim_id": claim_id})
            claim_item = _from_decimal(claim_res.get("Item", {}))

            # Fetch latest report for snapshot
            rep_status, rep_conf = "reported", None
            if "latest_report_json" in claim_item:
                try:
                    rep_obj = json.loads(claim_item["latest_report_json"])
                    rep_status = rep_obj.get("status", "reported")
                    rep_conf = rep_obj.get("scores", {}).get("confidence_index")
                except Exception:
                    pass

            item = {
                "claim_id": queue_key,
                "PK": "QUEUE#open",
                "SK": f"CLAIM#{claim_id}",
                "entity_type": "queue_item",
                "parent_claim_id": claim_id,
                "created_at": now_iso,
                "reasons": reasons,
                "status": "open",
                "claimed_cause": claim_item.get("claimed_cause", ""),
                "survey_no": claim_item.get("survey_no", ""),
                "village_lgd": claim_item.get("village_lgd", ""),
                "incident_date": claim_item.get("incident_date", ""),
                "report_status": rep_status,
                "confidence": rep_conf,
            }
            self.table.put_item(Item=_to_decimal(item))
            log.info("DynamoDB review_queue sync claim=%s status=open reasons=%s", claim_id, reasons)
            return "open"
        else:
            try:
                res = self.table.get_item(Key={"claim_id": queue_key})
                if res.get("Item") and res["Item"].get("status") == "open":
                    self.table.delete_item(Key={"claim_id": queue_key})
            except Exception as e:
                log.warning("Failed to delete queue item %s: %s", queue_key, e)
            return None

    def list_queue(self, status: str | None = None) -> list[dict]:
        try:
            res = self.table.scan(
                FilterExpression="entity_type = :et",
                ExpressionAttributeValues={":et": "queue_item"}
            )
            items = [_from_decimal(i) for i in res.get("Items", [])]
            if status:
                items = [i for i in items if i.get("status") == status]
            items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            out = []
            for i in items:
                out.append({
                    "claim_id": i.get("parent_claim_id") or i["claim_id"].replace("QUEUE#", ""),
                    "created_at": i.get("created_at", ""),
                    "reasons": i.get("reasons", []),
                    "status": i.get("status", "open"),
                    "decision": i.get("decision"),
                    "note": i.get("note"),
                    "decided_at": i.get("decided_at"),
                    "claimed_cause": i.get("claimed_cause"),
                    "survey_no": i.get("survey_no"),
                    "village_lgd": i.get("village_lgd"),
                    "incident_date": i.get("incident_date"),
                    "report_status": i.get("report_status"),
                    "confidence": i.get("confidence"),
                })
            return out
        except Exception as e:
            log.error("DynamoDB list_queue failed: %s", e)
            return []

    def decide(self, claim_id: str, decision: str, note: str | None) -> bool:
        queue_key = f"QUEUE#{claim_id}"
        res = self.table.get_item(Key={"claim_id": queue_key})
        queue_item = res.get("Item")
        if not queue_item:
            return False
        queue_item = _from_decimal(queue_item)
        now_iso = _now()

        if decision in ("approve", "approve_for_processing"):
            final_status = "approved_for_processing" if decision == "approve_for_processing" else "approved"
        elif decision == "reject":
            final_status = "rejected"
        elif decision == "request_more_information":
            final_status = "request_more_information"
        else:
            final_status = decision

        # Update review queue item
        queue_item["PK"] = "QUEUE#decided"
        queue_item["status"] = "decided"
        queue_item["decision"] = decision
        queue_item["note"] = note
        queue_item["decided_at"] = now_iso
        self.table.put_item(Item=_to_decimal(queue_item))

        # Update claim status
        claim_res = self.table.get_item(Key={"claim_id": claim_id})
        claim_item = claim_res.get("Item")
        if claim_item:
            claim_item = _from_decimal(claim_item)
            claim_item["status"] = final_status
            claim_item["review_decision"] = decision
            claim_item["review_note"] = note
            claim_item["review_decided_at"] = now_iso

            # Update latest verification report JSON with audit & decision
            if "latest_report_json" in claim_item:
                try:
                    report_data = json.loads(claim_item["latest_report_json"])
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
                    claim_item["latest_report_json"] = json.dumps(report_data)

                    # Also update report sub-item
                    report_id = claim_item.get("latest_report_id", 1)
                    report_item_key = f"CLAIM#{claim_id}#REPORT#{report_id}"
                    rep_sub = self.table.get_item(Key={"claim_id": report_item_key}).get("Item")
                    if rep_sub:
                        rep_sub = _from_decimal(rep_sub)
                        rep_sub["report_json"] = json.dumps(report_data)
                        self.table.put_item(Item=_to_decimal(rep_sub))
                except Exception as e:
                    log.warning("Failed to update report audit in DynamoDB: %s", e)

            self.table.put_item(Item=_to_decimal(claim_item))

        log.info("DynamoDB review decide claim=%s decision=%s status=%s", claim_id, decision, final_status)
        return True

    def stats(self) -> dict:
        try:
            # Query all items
            res = self.table.scan()
            items = [_from_decimal(i) for i in res.get("Items", [])]
            claims = [i for i in items if i.get("SK") == "METADATA"]
            reports = [i for i in items if i.get("entity_type") == "report"]
            queue_items = [i for i in items if i.get("entity_type") == "queue_item"]
            analyses = [i for i in items if i.get("entity_type") == "image_analysis"]

            by_status = {}
            for c in claims:
                st = c.get("status", "unknown")
                by_status[st] = by_status.get(st, 0) + 1

            return {
                "claims": len(claims),
                "reported": len(set(r.get("parent_claim_id") for r in reports if r.get("parent_claim_id"))),
                "by_status": by_status,
                "review_open": sum(1 for q in queue_items if q.get("status") == "open"),
                "review_decided": sum(1 for q in queue_items if q.get("status") == "decided"),
                "ai_calls": len(analyses),
            }
        except Exception as e:
            log.error("DynamoDB stats failed: %s", e)
            return {"claims": 0, "reported": 0, "by_status": {}, "review_open": 0, "review_decided": 0, "ai_calls": 0}


class DynamoAIRepository:
    def __init__(self, table):
        self.table = table

    def add_analysis(self, claim_id: str, image_key: int, result: dict) -> int:
        now_iso = _now()
        aid = int(time.time() * 1000) % 1_000_000_000
        item = {
            "claim_id": f"CLAIM#{claim_id}#ANALYSIS#{image_key}#{aid}",
            "PK": f"CLAIM#{claim_id}",
            "SK": f"ANALYSIS#{image_key}",
            "entity_type": "image_analysis",
            "analysis_id": aid,
            "parent_claim_id": claim_id,
            "image_key": image_key,
            "ok": 1 if result.get("ok") else 0,
            "model_id": result.get("model_id"),
            "prompt_version": result.get("prompt_version"),
            "cached": 1 if result.get("cached") else 0,
            "result_json": json.dumps(result),
            "created_at": now_iso,
        }
        self.table.put_item(Item=_to_decimal(item))
        return aid

    def latest_analysis(self, claim_id: str, image_key: int) -> dict | None:
        try:
            res = self.table.scan(
                FilterExpression="parent_claim_id = :cid AND image_key = :ik AND entity_type = :et",
                ExpressionAttributeValues={":cid": claim_id, ":ik": image_key, ":et": "image_analysis"}
            )
            items = [_from_decimal(i) for i in res.get("Items", [])]
            if not items:
                return None
            items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            top = items[0]
            return {
                "analysis_id": top.get("analysis_id", 1),
                "claim_id": top.get("parent_claim_id", claim_id),
                "image_key": top.get("image_key", image_key),
                "ok": bool(top.get("ok")),
                "model_id": top.get("model_id"),
                "prompt_version": top.get("prompt_version"),
                "cached": bool(top.get("cached")),
                "result": json.loads(top["result_json"]),
                "created_at": top.get("created_at", ""),
            }
        except Exception as e:
            log.error("DynamoDB latest_analysis failed: %s", e)
            return None


class DynamoAICache:
    """AICache Protocol backed by DynamoDB with optional TTL."""
    def __init__(self, table, ttl_seconds: int = 86400 * 30):
        self.table = table
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> Optional[dict]:
        try:
            res = self.table.get_item(Key={"claim_id": f"CACHE#AI#{key}"})
            item = res.get("Item")
            if item and "result_json" in item:
                return json.loads(item["result_json"])
            return None
        except Exception as e:
            log.warning("DynamoDB AICache get failed for key %s: %s", key, e)
            return None

    def put(self, key: str, value: dict) -> None:
        try:
            item = {
                "claim_id": f"CACHE#AI#{key}",
                "PK": f"CACHE#{key}",
                "SK": "AI",
                "entity_type": "ai_cache",
                "result_json": json.dumps(value),
                "created_at": _now(),
                "ttl": int(time.time()) + self.ttl_seconds,
            }
            self.table.put_item(Item=_to_decimal(item))
        except Exception as e:
            log.warning("DynamoDB AICache put failed for key %s: %s", key, e)


class DynamoDBContext:
    """Encapsulates the DynamoDB connection and repositories for dependency injection."""
    is_dynamo = True

    def __init__(self, settings: Any, table_resource: Any = None):
        self.settings = settings
        self._table = table_resource
        self.table_name = getattr(settings, "dynamodb_table", "fai-tce-team56-claims")
        self.region = getattr(settings, "aws_region", "ap-south-1")
        self.s3_bucket = getattr(settings, "s3_bucket", "fai-tce-team56-images")

    @property
    def table(self):
        if self._table is None:
            import boto3
            session = boto3.Session(region_name=self.region)
            ddb = session.resource("dynamodb")
            self._table = ddb.Table(self.table_name)
        return self._table

    @property
    def claims(self) -> DynamoClaimsRepository:
        return DynamoClaimsRepository(self.table, s3_bucket=self.s3_bucket)

    @property
    def verification(self) -> DynamoVerificationRepository:
        return DynamoVerificationRepository(self.table)

    @property
    def ai(self) -> DynamoAIRepository:
        return DynamoAIRepository(self.table)

    @property
    def ai_cache(self) -> DynamoAICache:
        return DynamoAICache(self.table)

    def close(self):
        pass
