from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from backend.config import Settings
from backend.deps import get_conn, get_settings_dep
from backend.errors import AppError
from backend.repositories import dataset as ds
from backend.services import image_service
from backend.schemas.dataset import (
    DatasetImage, DatasetImageDetail, DatasetImageList, DatasetSummary, ParcelList, ParcelRecord,
)

router = APIRouter(prefix="/dataset", tags=["dataset"])


def _img(d: dict) -> DatasetImage:
    return DatasetImage(**{k: d[k] for k in DatasetImage.model_fields})


@router.get("/summary", response_model=DatasetSummary)
def summary(conn=Depends(get_conn)):
    ds.require_dataset(conn)
    return DatasetSummary(**ds.summary(conn))


@router.get("/images", response_model=DatasetImageList)
def list_images(village_lgd: Optional[str] = None, crop_name: Optional[str] = None,
                crop_stage: Optional[str] = None, file_status: Optional[str] = Query(None, pattern="^(found|missing|unchecked)$"),
                flag: Optional[str] = Query(None, description="e.g. STAGE_CONFLICT, INVALID_COORD"),
                limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), conn=Depends(get_conn)):
    ds.require_dataset(conn)
    total, rows = ds.list_images(conn, village_lgd=village_lgd, crop_name=crop_name, crop_stage=crop_stage,
                                 file_status=file_status, flag=flag, limit=limit, offset=offset)
    return DatasetImageList(total=total, limit=limit, offset=offset, items=[_img(r) for r in rows])


@router.get("/images/{image_id}", response_model=DatasetImageDetail)
def image_detail(image_id: str, conn=Depends(get_conn)):
    ds.require_dataset(conn)
    d = ds.get_image(conn, image_id)
    if not d:
        raise AppError(404, "IMAGE_NOT_FOUND", f"No dataset image '{image_id}'")
    return DatasetImageDetail(image=_img(d), records=[ParcelRecord(**r) for r in ds.linked_records(conn, image_id)])


@router.get("/images/{image_id}/file")
def image_file(image_id: str, conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    ds.require_dataset(conn)
    d = ds.get_image(conn, image_id)
    if not d:
        raise AppError(404, "IMAGE_NOT_FOUND", f"No dataset image '{image_id}'")
    path = d.get("file_path")
    if not path or not image_service.is_image_available(path, settings=settings):
        raise AppError(404, "IMAGE_FILE_MISSING", "Image is in the dataset but its file is not available")
    try:
        data = image_service.read_image_bytes(path, settings=settings)
    except Exception as e:
        raise AppError(404, "IMAGE_FILE_MISSING", f"Image file cannot be read: {e}")
    return Response(content=data, media_type="image/jpeg")


@router.get("/parcels", response_model=ParcelList)
def parcels(village_lgd: Optional[str] = None, survey_no: Optional[str] = None,
            subdivision: Optional[str] = None, limit: int = Query(200, ge=1, le=1000), conn=Depends(get_conn)):
    ds.require_dataset(conn)
    if not (village_lgd or survey_no):
        raise AppError(422, "FILTER_REQUIRED", "Provide village_lgd and/or survey_no")
    total, rows = ds.find_parcels(conn, village_lgd=village_lgd, survey_no=survey_no, subdivision=subdivision, limit=limit)
    return ParcelList(total=total, items=[ParcelRecord(**r) for r in rows])
