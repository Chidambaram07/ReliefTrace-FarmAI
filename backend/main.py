from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from backend import __version__
from backend.api import agentic, analysis, claims, dataset, evaluation, health, verification
from backend.config import Settings, get_settings
from backend.dataset import db
from backend.errors import register_error_handlers
from backend.logging_config import configure_logging
from backend.evidence.geo import AdminLayers
from backend.evidence.weather import HttpClient
from backend.services.bedrock_service import BedrockService
from backend.services.model_client import ClientSettings, ModelClient
from backend.services.model_registry import build_registry
from backend.agentic.router import ModelRouter
from backend.storage.schema import (
    init_ai_schema, init_claims_schema, init_image_index_schema, init_model_health_schema, init_verify_schema,
)

log = logging.getLogger("reliefTrace.http")


def create_app(settings: Settings | None = None, bedrock: BedrockService | None = None, geo=None, http=None,
              model_client: ModelClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import os
        if getattr(settings, "storage_backend", "local").lower() not in ("aws", "dynamodb") and not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
            conn = db.connect(settings.db_path)
            init_claims_schema(conn)
            init_ai_schema(conn)
            init_verify_schema(conn)
            init_model_health_schema(conn)
            init_image_index_schema(conn)

        # Auto-build dataset on startup if raw CSV exists but dataset tables are empty.
        # This eliminates the DATASET_NOT_LOADED error during the normal demo flow:
        # build once, reuse the generated index, do not rebuild on every request.
            from backend.repositories import dataset as ds_repo
            if not ds_repo.dataset_loaded(conn) and settings.csv_path.exists():
                log.info("Dataset not loaded but CSV found at %s — building automatically…", settings.csv_path)
                from backend.dataset.builder import DatasetError, build_dataset
                try:
                    images_dir = settings.images_dir if settings.images_dir.is_dir() else None
                    bundle = build_dataset(settings.csv_path, images_dir)
                    db.load_bundle(conn, bundle, csv_path=str(settings.csv_path))
                    log.info("Dataset auto-built: %d records, %d images",
                             len(bundle.records), len(bundle.images))
                except DatasetError as e:
                    log.warning("Dataset auto-build failed: %s — run 'python -m scripts.build_dataset' manually", e)
            elif ds_repo.dataset_loaded(conn):
                log.info("Dataset already loaded in %s", settings.db_path)

            conn.close()
            log.info("ReliefTrace API started (local SQLite db=%s)", settings.db_path)
        else:
            log.info("ReliefTrace API started in AWS mode (DynamoDB=%s, S3=%s)", settings.dynamodb_table, settings.s3_bucket)
            from backend.repositories.dataset import ensure_dataset_db
            try:
                ensure_dataset_db(settings)
            except Exception as e:
                log.warning("Initial ensure_dataset_db failed: %s", e)
        yield

    app = FastAPI(title="ReliefTrace API", version=__version__, lifespan=lifespan,
                  description="Independent-evidence verification for agricultural relief claims.")
    app.state.settings = settings
    app.state.bedrock = bedrock or BedrockService()  # boto3 client is created lazily on first call
    app.state.geo = geo if geo is not None else AdminLayers(settings.geo_dir)
    app.state.http = http or HttpClient()
    # Agentic layer (Phases 2-9): separate from `bedrock` above, which stays dedicated to the
    # proven MVP claim-analysis path (image observation JSON schema + narrative). The model
    # client here backs the router (Ministral independent review) and the image-retrieval tool.
    app.state.model_registry = build_registry()
    app.state.model_client = model_client or ModelClient(ClientSettings(region="ap-south-1"))
    app.state.model_router = ModelRouter(app.state.model_client, app.state.model_registry)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])
    register_error_handlers(app)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        log.info("%s %s -> %s %.0fms rid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - t0) * 1000, request.state.request_id)
        return response

    for r in (health.router, dataset.router, claims.router, analysis.router, verification.router, agentic.router, evaluation.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()
handler = Mangum(app)
