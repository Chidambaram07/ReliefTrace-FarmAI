"""Validate and inspect uploaded images. Metadata is read from the file only; nothing is inferred."""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from backend.errors import AppError

ALLOWED = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png")}
MAX_PIXELS = 40_000_000
GPS_IFD, EXIF_IFD = 0x8825, 0x8769


def dms_to_deg(dms, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    deg = d + m / 60 + s / 3600
    if isinstance(ref, bytes):
        ref = ref.decode(errors="ignore")
    return -deg if str(ref).upper() in ("S", "W") else deg


def _exif_datetime(v) -> str | None:
    try:
        return datetime.strptime(str(v).strip(), "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        return None


def read_exif(img: Image.Image) -> dict:
    out = {"exif_gps_lat": None, "exif_gps_lon": None, "exif_captured_at": None}
    try:
        exif = img.getexif()
        if not exif:
            return out
        gps = exif.get_ifd(GPS_IFD)
        if gps and 2 in gps and 4 in gps:
            out["exif_gps_lat"] = dms_to_deg(gps[2], gps.get(1))
            out["exif_gps_lon"] = dms_to_deg(gps[4], gps.get(3))
        raw = exif.get_ifd(EXIF_IFD).get(36867) or exif.get(306)
        out["exif_captured_at"] = _exif_datetime(raw) if raw else None
    except Exception:  # malformed EXIF must never block an upload
        pass
    return out


def inspect_upload(data: bytes, filename: str | None, max_bytes: int) -> dict:
    if not data:
        raise AppError(422, "EMPTY_FILE", "Uploaded file is empty")
    if len(data) > max_bytes:
        raise AppError(413, "FILE_TOO_LARGE", "File exceeds the maximum upload size",
                       {"max_bytes": max_bytes, "size_bytes": len(data)})
    try:
        img = Image.open(io.BytesIO(data))
        fmt, (w, h) = img.format, img.size
        if fmt not in ALLOWED:
            raise AppError(415, "UNSUPPORTED_IMAGE", "Only JPEG and PNG images are accepted", {"format": fmt})
        if w * h > MAX_PIXELS:
            raise AppError(413, "IMAGE_TOO_LARGE", "Image dimensions too large", {"width": w, "height": h})
        img.verify()
        img = Image.open(io.BytesIO(data))  # verify() invalidates the handle
        exif = read_exif(img)
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise AppError(415, "UNSUPPORTED_IMAGE", "File is not a valid JPEG/PNG image")
    mime, ext = ALLOWED[fmt]
    return {"sha256": hashlib.sha256(data).hexdigest(), "mime": mime, "ext": ext, "width": w, "height": h,
            "size_bytes": len(data), "filename": Path(filename or "upload").name[:200], **exif}


import logging
import os
from typing import Any, Optional, Protocol

log = logging.getLogger("reliefTrace.image_service")


class ImageStorage(Protocol):
    def store(self, claim_id: str, meta: dict, data: bytes) -> str:
        """Stores image data and returns storage URI/path."""
        ...

    def read(self, uri: str) -> bytes:
        """Reads image binary data given its URI or path."""
        ...

    def exists(self, uri: str) -> bool:
        """Returns True if the image exists in storage."""
        ...

    def delete(self, uri: str) -> bool:
        """Deletes the image from storage. Returns True if deleted."""
        ...

    def get_presigned_url(self, uri: str, expires_in: int = 3600) -> Optional[str]:
        """Returns a presigned GET URL if supported, else None."""
        ...


class LocalImageStorage:
    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)

    def _path_for(self, claim_id: str, meta: dict) -> Path:
        safe_claim_id = "".join(c for c in claim_id if c.isalnum() or c in ("-", "_")) or "claim"
        d = self.base_dir / safe_claim_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{meta['sha256'][:16]}{meta['ext']}"

    def store(self, claim_id: str, meta: dict, data: bytes) -> str:
        p = self._path_for(claim_id, meta)
        p.write_bytes(data)
        return str(p)

    def read(self, uri: str) -> bytes:
        p = Path(uri)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Local image file not found: {uri}")
        return p.read_bytes()

    def exists(self, uri: str) -> bool:
        if not uri:
            return False
        return Path(uri).exists() and Path(uri).is_file()

    def delete(self, uri: str) -> bool:
        if not uri:
            return False
        p = Path(uri)
        if p.exists():
            try:
                p.unlink()
                return True
            except OSError as e:
                log.warning("Failed to delete local file %s: %s", uri, e)
                return False
        return False

    def get_presigned_url(self, uri: str, expires_in: int = 3600) -> Optional[str]:
        return None


class S3ImageStorage:
    def __init__(self, bucket: str = "fai-tce-team56-images", region: str = "ap-south-1", s3_client: Any = None):
        self.bucket = bucket
        self.region = region
        self._s3_client = s3_client

    @property
    def client(self):
        if self._s3_client is None:
            import boto3
            # Use ambient credentials / profile / IAM role with ap-south-1 default
            self._s3_client = boto3.client("s3", region_name=self.region)
        return self._s3_client

    def _key_for(self, claim_id: str, meta: dict) -> str:
        safe_claim_id = "".join(c for c in claim_id if c.isalnum() or c in ("-", "_")) or "claim"
        filename = f"{meta['sha256'][:16]}{meta['ext']}"
        return f"uploads/{safe_claim_id}/{filename}"

    def _parse_key(self, uri: str) -> str:
        if uri.startswith(f"s3://{self.bucket}/"):
            return uri[len(f"s3://{self.bucket}/"):]
        elif uri.startswith("s3://"):
            parts = uri[5:].split("/", 1)
            return parts[1] if len(parts) > 1 else parts[0]
        return uri

    def store(self, claim_id: str, meta: dict, data: bytes) -> str:
        key = self._key_for(claim_id, meta)
        content_type = meta.get("mime", "image/jpeg")
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                Metadata={
                    "claim_id": str(claim_id),
                    "sha256": str(meta.get("sha256", "")),
                    "width": str(meta.get("width", "")),
                    "height": str(meta.get("height", "")),
                },
            )
            uri = f"s3://{self.bucket}/{key}"
            log.info("S3 PutObject success bucket=%s key=%s sha=%s", self.bucket, key, meta.get("sha256", "")[:12])
            return uri
        except Exception as e:
            log.error("S3 PutObject failed bucket=%s key=%s: %s", self.bucket, key, e)
            raise

    def read(self, uri: str) -> bytes:
        key = self._parse_key(uri)
        try:
            res = self.client.get_object(Bucket=self.bucket, Key=key)
            return res["Body"].read()
        except self.client.exceptions.NoSuchKey:
            log.warning("S3 NoSuchKey bucket=%s key=%s", self.bucket, key)
            raise FileNotFoundError(f"S3 object not found: {uri}")
        except Exception as e:
            if hasattr(e, "response") and e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
                raise FileNotFoundError(f"S3 object not found: {uri}")
            log.error("S3 GetObject failed bucket=%s key=%s: %s", self.bucket, key, e)
            raise

    def exists(self, uri: str) -> bool:
        if not uri:
            return False
        key = self._parse_key(uri)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, uri: str) -> bool:
        if not uri:
            return False
        key = self._parse_key(uri)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            log.info("S3 DeleteObject success bucket=%s key=%s", self.bucket, key)
            return True
        except Exception as e:
            log.error("S3 DeleteObject failed bucket=%s key=%s: %s", self.bucket, key, e)
            return False

    def get_presigned_url(self, uri: str, expires_in: int = 3600) -> Optional[str]:
        key = self._parse_key(uri)
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except Exception as e:
            log.error("S3 generate_presigned_url failed for key %s: %s", key, e)
            return None


def get_image_storage(settings: Any | None = None, s3_client: Any = None) -> ImageStorage:
    if settings is None:
        from backend.config import get_settings
        settings = get_settings()
    backend = getattr(settings, "storage_backend", "local").strip().lower()
    if backend in ("s3", "aws", "dynamodb") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        bucket = getattr(settings, "s3_bucket", "fai-tce-team56-images")
        region = getattr(settings, "aws_region", "ap-south-1")
        return S3ImageStorage(bucket=bucket, region=region, s3_client=s3_client)
    return LocalImageStorage(base_dir=getattr(settings, "upload_dir", "data/uploads"))


def is_image_available(path_or_uri: str | None, settings: Any | None = None,
                       storage: ImageStorage | None = None) -> bool:
    if not path_or_uri:
        return False
    if path_or_uri.startswith("s3://"):
        st = storage or get_image_storage(settings)
        return st.exists(path_or_uri)
    return os.path.exists(path_or_uri)


def read_image_bytes(path_or_uri: str, settings: Any | None = None,
                     storage: ImageStorage | None = None) -> bytes:
    if not path_or_uri:
        raise FileNotFoundError("Empty image path or URI")
    if path_or_uri.startswith("s3://"):
        st = storage or get_image_storage(settings)
        return st.read(path_or_uri)
    p = Path(path_or_uri)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Local file not found: {path_or_uri}")
    return p.read_bytes()


def store_upload(upload_dir_or_storage: Path | str | ImageStorage, claim_id: str, meta: dict, data: bytes) -> Path | str:
    if hasattr(upload_dir_or_storage, "store"):
        return upload_dir_or_storage.store(claim_id, meta, data)
    storage = LocalImageStorage(base_dir=upload_dir_or_storage)
    return Path(storage.store(claim_id, meta, data))
