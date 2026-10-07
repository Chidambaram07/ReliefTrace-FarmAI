from __future__ import annotations

from fastapi import Request

from backend.config import Settings
from backend.dataset import db


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(request: Request):
    settings = request.app.state.settings
    if getattr(settings, "storage_backend", "local").lower() in ("aws", "dynamodb"):
        from backend.storage.dynamo import DynamoDBContext
        table = getattr(request.app.state, "dynamo_table", None)
        ctx = DynamoDBContext(settings, table_resource=table)
        try:
            yield ctx
        finally:
            ctx.close()
    else:
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()
