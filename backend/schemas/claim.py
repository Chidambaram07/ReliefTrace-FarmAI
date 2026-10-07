from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ClaimedCause = Literal["drought", "flood", "cyclone_storm", "hail", "pest", "disease", "fire", "other"]
ClaimStatus = Literal["submitted", "reported", "approved_for_processing", "approved", "rejected", "request_more_information"]


class ClaimCreate(BaseModel):
    """What the farmer/officer submits. Everything here is a CLAIM, not verified fact."""
    farmer_name: Optional[str] = Field(None, max_length=120)
    village_lgd: Optional[str] = Field(None, description="6-digit LGD village code")
    survey_no: str = Field(..., min_length=1, max_length=20)
    subdivision: Optional[str] = Field(None, max_length=20)
    claimed_cause: ClaimedCause
    claimed_crop: Optional[str] = Field(None, max_length=80)
    claimed_stage: Optional[str] = Field(None, max_length=40)
    incident_date: date
    claimed_lat: Optional[float] = Field(None, ge=-90, le=90)
    claimed_lon: Optional[float] = Field(None, ge=-180, le=180)
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator("survey_no", "subdivision", "farmer_name", "claimed_crop", "claimed_stage", "description")
    @classmethod
    def _strip(cls, v):
        if v is None:
            return v
        v = v.strip()
        return v or None

    @field_validator("survey_no")
    @classmethod
    def _survey_required(cls, v):
        if not v:
            raise ValueError("survey_no must not be blank")
        return v

    @field_validator("village_lgd")
    @classmethod
    def _lgd(cls, v):
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not (v.isdigit() and len(v) == 6):
            raise ValueError("village_lgd must be a 6-digit code")
        return v

    @field_validator("incident_date")
    @classmethod
    def _not_future(cls, v: date):
        if v > date.today():
            raise ValueError("incident_date cannot be in the future")
        return v

    @model_validator(mode="after")
    def _coords_together(self):
        if (self.claimed_lat is None) != (self.claimed_lon is None):
            raise ValueError("claimed_lat and claimed_lon must be provided together")
        return self


class ExifInfo(BaseModel):
    """Read from the uploaded file itself; null when the file carries no such metadata."""
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    captured_at: Optional[str] = None


class ClaimImageOut(BaseModel):
    image_key: int
    source: Literal["upload", "dataset"]
    dataset_image_id: Optional[str] = None
    filename: Optional[str] = None
    sha256: Optional[str] = None
    mime: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    file_available: bool
    exif: ExifInfo
    created_at: str


class ClaimOut(BaseModel):
    claim_id: str
    created_at: str
    status: ClaimStatus
    provenance: str = "Claimant-submitted; unverified"
    claim: ClaimCreate
    images: list[ClaimImageOut] = []


class ClaimList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ClaimOut]


class DatasetImageLink(BaseModel):
    image_id: str = Field(..., min_length=1, max_length=200)
