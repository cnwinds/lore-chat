from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.backup.export_kb import build_export_zip
from app.deps import apply_settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    return request.app.state.settings_store.public_dict()


@router.put("/settings")
def put_settings(body: dict[str, Any], request: Request) -> dict[str, Any]:
    store = request.app.state.settings_store
    try:
        new_settings = store.update(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    apply_settings(request.app.state.container, new_settings)
    return store.public_dict()


@router.get("/export")
def export_kb(request: Request) -> StreamingResponse:
    kb_path = request.app.state.settings_store.get().kb_path
    lock = request.app.state.maintenance_lock
    lock.acquire("export")
    try:
        buf = io.BytesIO()
        build_export_zip(kb_path, buf)
        buf.seek(0)
        filename = f"lorechat-kb-{datetime.now().strftime('%Y%m%d')}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        lock.release()
