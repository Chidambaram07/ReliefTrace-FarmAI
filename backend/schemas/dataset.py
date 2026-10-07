from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

PROVENANCE = ("FarmwiseAI ground-truth reference CSV. Reference data that may contain errors; "
              "contains NO disease/damage labels.")


class ParcelRecord(BaseModel):
    record_id: str
    village_lgd: Optional[str] = None
    village_code: Optional[str] = None
    survey_no: Optional[str] = None
    subdivision: Optional[str] = None
    gt_lat: Optional[float] = None
    gt_lon: Optional[float] = None
    gt_date: Optional[str] = None
    crop_classification: Optional[str] = None
    crop_name: Optional[str] = None
    crop_stage: Optional[str] = None
    gt_to_image_m: Optional[float] = None


class DatasetImage(BaseModel):
    image_id: str
    id_format: str
    crop_name: Optional[str] = None
    crop_stage: Optional[str] = None
    crop_stage_values: list[str] = []
    classification_values: list[str] = []
    image_date: Optional[str] = None
    image_lat: Optional[float] = None
    image_lon: Optional[float] = None
    coord_status: str
    village_lgd: Optional[str] = None
    n_records: int
    n_parcels: int
    flags: list[str] = []
    file_status: str
    file_available: bool
    n_files: int = 0
    file_captured_at: Optional[str] = None


class DatasetImageDetail(BaseModel):
    provenance: str = PROVENANCE
    image: DatasetImage
    records: list[ParcelRecord]


class DatasetImageList(BaseModel):
    provenance: str = PROVENANCE
    total: int
    limit: int
    offset: int
    items: list[DatasetImage]


class ParcelList(BaseModel):
    provenance: str = PROVENANCE
    total: int
    items: list[ParcelRecord]


class DatasetSummary(BaseModel):
    provenance: str = PROVENANCE
    records: int
    images: int
    images_with_file: int
    images_by_coord_status: dict[str, int]
    flagged_images: dict[str, int]
