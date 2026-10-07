from __future__ import annotations

import logging
import os
import sqlite3

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from backend.config import Settings
from backend.deps import get_conn, get_settings_dep
from backend.errors import AppError
from backend.repositories import claims as repo
from backend.repositories import dataset as ds
from backend.schemas.claim import ClaimCreate, ClaimImageOut, ClaimList, ClaimOut, DatasetImageLink, ExifInfo
from backend.services import image_service

log = logging.getLogger("reliefTrace.claims")
router = APIRouter(prefix="/claims", tags=["claims"])


def _image_out(r: dict, settings: Settings | None = None) -> ClaimImageOut:
    return ClaimImageOut(
        image_key=r["image_key"], source=r["source"], dataset_image_id=r["dataset_image_id"],
        filename=r["filename"], sha256=r["sha256"], mime=r["mime"], width=r["width"], height=r["height"],
        size_bytes=r["size_bytes"], file_available=image_service.is_image_available(r.get("file_path"), settings=settings),
        exif=ExifInfo(gps_lat=r["exif_gps_lat"], gps_lon=r["exif_gps_lon"], captured_at=r["exif_captured_at"]),
        created_at=r["created_at"])


def _claim_out(conn, c: dict, settings: Settings | None = None) -> ClaimOut:
    fields = {k: c[k] for k in ClaimCreate.model_fields}
    return ClaimOut(claim_id=c["claim_id"], created_at=c["created_at"], status=c["status"],
                    claim=ClaimCreate.model_validate(fields),
                    images=[_image_out(i, settings=settings) for i in repo.list_claim_images(conn, c["claim_id"])])


def _require_claim(conn, claim_id: str) -> dict:
    c = repo.get_claim(conn, claim_id)
    if not c:
        raise AppError(404, "CLAIM_NOT_FOUND", f"No claim '{claim_id}'")
    return c


@router.post("", response_model=ClaimOut, status_code=201)
def create_claim(body: ClaimCreate, conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    c = repo.create_claim(conn, body.model_dump(mode="json"))
    log.info("claim created id=%s cause=%s survey=%s", c["claim_id"], c["claimed_cause"], c["survey_no"])
    return _claim_out(conn, c, settings=settings)


@router.get("", response_model=ClaimList)
def list_claims(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), conn=Depends(get_conn),
                settings: Settings = Depends(get_settings_dep)):
    total, rows = repo.list_claims(conn, limit, offset)
    return ClaimList(total=total, limit=limit, offset=offset, items=[_claim_out(conn, r, settings=settings) for r in rows])


@router.get("/{claim_id}", response_model=ClaimOut)
def get_claim(claim_id: str, conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    return _claim_out(conn, _require_claim(conn, claim_id), settings=settings)


@router.post("/{claim_id}/images", response_model=ClaimImageOut, status_code=201)
async def upload_image(claim_id: str, file: UploadFile = File(...), conn=Depends(get_conn),
                       settings: Settings = Depends(get_settings_dep)):
    _require_claim(conn, claim_id)
    data = await file.read(settings.max_upload_bytes + 1)  # bounded read
    meta = image_service.inspect_upload(data, file.filename, settings.max_upload_bytes)
    storage = image_service.get_image_storage(settings)
    try:
        stored_uri = storage.store(claim_id, meta, data)
    except Exception as e:
        log.error("Image store failed claim=%s: %s", claim_id, e)
        raise AppError(500, "STORAGE_ERROR", f"Failed to store image: {str(e)}")
    try:
        key = repo.add_claim_image(conn, claim_id, {"source": "upload", "file_path": str(stored_uri), **meta})
    except sqlite3.IntegrityError:
        raise AppError(409, "DUPLICATE_IMAGE", "This image is already attached to the claim")
    log.info("image uploaded claim=%s key=%s sha=%s path=%s", claim_id, key, meta["sha256"][:12], stored_uri)
    return _image_out(repo.get_claim_image(conn, claim_id, key), settings=settings)


@router.post("/{claim_id}/images/from-dataset", response_model=ClaimImageOut, status_code=201)
def attach_dataset_image(claim_id: str, body: DatasetImageLink, conn=Depends(get_conn),
                         settings: Settings = Depends(get_settings_dep)):
    _require_claim(conn, claim_id)
    ds.require_dataset(conn)
    d = ds.get_image(conn, body.image_id)
    if not d:
        raise AppError(404, "IMAGE_NOT_FOUND", f"No dataset image '{body.image_id}'")
    raw_fname = d["file_path"].replace("\\", "/").rstrip("/").split("/")[-1] if d.get("file_path") else None
    rec = {"source": "dataset", "dataset_image_id": d["image_id"], "file_path": d["file_path"],
           "filename": raw_fname}
    if d.get("file_available") and d.get("file_path"):  # fill file facts (hash, size, EXIF)
        try:
            img_bytes = image_service.read_image_bytes(d["file_path"], settings=settings)
            meta = image_service.inspect_upload(img_bytes, rec["filename"], 50 * 1024 * 1024)
            rec.update({k: meta[k] for k in ("sha256", "mime", "width", "height", "size_bytes",
                                             "exif_gps_lat", "exif_gps_lon", "exif_captured_at")})
        except AppError:
            log.warning("dataset image %s present but unreadable as JPEG/PNG", d["image_id"])
        except Exception as e:
            log.warning("dataset image %s read/inspect failed: %s", d["image_id"], e)
    if not rec.get("exif_captured_at") and d.get("file_captured_at"):
        rec["exif_captured_at"] = d["file_captured_at"]
    if rec.get("exif_gps_lat") is None and d.get("image_lat") is not None:
        rec["exif_gps_lat"] = d["image_lat"]
        rec["exif_gps_lon"] = d.get("image_lon")
    try:
        key = repo.add_claim_image(conn, claim_id, rec)
    except sqlite3.IntegrityError:
        raise AppError(409, "DUPLICATE_IMAGE", "This dataset image is already attached to the claim")
    return _image_out(repo.get_claim_image(conn, claim_id, key), settings=settings)


@router.get("/{claim_id}/images/{image_key}/file")
def image_file(claim_id: str, image_key: int, conn=Depends(get_conn),
               settings: Settings = Depends(get_settings_dep)):
    _require_claim(conn, claim_id)
    r = repo.get_claim_image(conn, claim_id, image_key)
    if not r:
        raise AppError(404, "IMAGE_NOT_FOUND", "No such image on this claim")
    path = r["file_path"]
    if not path or not image_service.is_image_available(path, settings=settings):
        raise AppError(404, "IMAGE_FILE_MISSING", "Image file is not available on storage")
    try:
        data = image_service.read_image_bytes(path, settings=settings)
    except FileNotFoundError:
        raise AppError(404, "IMAGE_FILE_MISSING", "Image file is not available on storage")
    except Exception as e:
        log.error("Failed to read image %s: %s", path, e)
        raise AppError(500, "STORAGE_ERROR", f"Failed to retrieve image: {str(e)}")
    return Response(content=data, media_type=r["mime"] or "image/jpeg")
