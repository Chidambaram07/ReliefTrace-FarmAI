from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, Request

from backend import __version__
from backend.config import Settings
from backend.deps import get_conn, get_settings_dep
from backend.repositories import dataset as ds

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, conn=Depends(get_conn), settings: Settings = Depends(get_settings_dep)):
    loaded = ds.dataset_loaded(conn)
    s = ds.summary(conn) if loaded else None
    return {
        "status": "ok",
        "version": __version__,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "database": "ok",
        "dataset_loaded": loaded,
        "dataset": {"records": s["records"], "images": s["images"], "images_with_file": s["images_with_file"]} if s else None,
        "upload_dir_writable": os.access(settings.upload_dir, os.W_OK),
        "bedrock": {  # configuration only; /health never calls AWS
            "region": request.app.state.bedrock.settings.region,
            "vision_model_id": request.app.state.bedrock.settings.vision_model_id,
            "text_model_id": request.app.state.bedrock.settings.text_model_id,
        },
    }
