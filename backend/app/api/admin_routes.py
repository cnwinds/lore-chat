from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.backup.export_kb import build_export_zip
from app.backup.import_kb import ImportResult, import_kb
from app.backup.lock import MaintenanceActiveError
from app.backup.reindex import reindex_all
from app.deps import apply_settings, dispose_container, remount_container
from app.models.candidate import model_routing_changed

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _maintenance_http(exc: MaintenanceActiveError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "detail": str(exc),
            "code": "maintenance",
        },
    )


def _import_failure_http(result: ImportResult) -> HTTPException:
    if result.message == "knowledge base is not empty":
        status = 409
    elif "format_version" in result.message or "manifest" in result.message:
        status = 409
    else:
        status = 400
    detail: dict[str, Any] = {"detail": result.message}
    if result.backup_path is not None:
        detail["backup_path"] = str(result.backup_path)
    return HTTPException(status_code=status, detail=detail)


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    data = request.app.state.settings_store.public_dict()
    container = getattr(request.app.state, "container", None)
    if container is not None and getattr(container, "model_cooldown", None) is not None:
        data["model_cooldown"] = container.model_cooldown.public_status()
    else:
        data["model_cooldown"] = {}
    return data


@router.put("/settings")
def put_settings(body: dict[str, Any], request: Request) -> dict[str, Any]:
    store = request.app.state.settings_store
    container = request.app.state.container
    prev = container.settings
    try:
        new_settings = store.update(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # 模型/密钥/端点配置实际变更 → 解除 disabled（共识：改配置可恢复）
    if model_routing_changed(prev, new_settings):
        container.model_cooldown.clear_disabled()
    apply_settings(container, new_settings)
    data = store.public_dict()
    data["model_cooldown"] = container.model_cooldown.public_status()
    return data


@router.post("/model-cooldown/clear")
def clear_model_cooldown(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """清除冷却或重新启用候选。body: {candidate_id?: str, all?: bool}"""
    store = request.app.state.container.model_cooldown
    if body.get("all"):
        store.clear()
    else:
        cid = body.get("candidate_id")
        if not cid:
            raise HTTPException(status_code=422, detail="candidate_id or all required")
        store.reenable(str(cid))
    return {"ok": True, "model_cooldown": store.public_status()}


@router.get("/export")
def export_kb(request: Request):
    from datetime import datetime

    from fastapi.responses import StreamingResponse

    import io

    kb_path = request.app.state.settings_store.get().kb_path
    lock = request.app.state.maintenance_lock
    try:
        lock.acquire("export")
    except MaintenanceActiveError as exc:
        raise _maintenance_http(exc) from exc
    try:
        buf = io.BytesIO()
        build_export_zip(kb_path, buf)
        buf.seek(0)
        from app.time import now_display

        filename = f"lorechat-kb-{now_display().strftime('%Y%m%d')}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        lock.release()


@router.post("/import")
async def import_kb_api(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form(...),
) -> dict[str, Any]:
    if mode not in ("empty_only", "overwrite"):
        raise HTTPException(status_code=422, detail="mode must be empty_only or overwrite")

    lock = request.app.state.maintenance_lock
    try:
        lock.acquire("import")
    except MaintenanceActiveError as exc:
        raise _maintenance_http(exc) from exc

    tmp_path: Path | None = None
    try:
        settings = request.app.state.settings_store.get()
        kb_path = settings.kb_path
        suffix = Path(file.filename or "import.zip").suffix or ".zip"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        dispose_container(request.app.state.container)
        result = import_kb(
            kb_path,
            tmp_path,
            mode,  # type: ignore[arg-type]
            system_layer_dir=settings.system_layer_dir,
        )
        if not result.ok:
            remount_container(request.app)
            raise _import_failure_http(result)

        remount_container(request.app)
        payload: dict[str, Any] = {"ok": True, "message": result.message}
        if result.backup_path is not None:
            payload["backup_path"] = str(result.backup_path)
        return payload
    finally:
        lock.release()
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


@router.post("/reindex")
def reindex_api(request: Request) -> dict[str, Any]:
    lock = request.app.state.maintenance_lock
    try:
        lock.acquire("reindex")
    except MaintenanceActiveError as exc:
        raise _maintenance_http(exc) from exc
    try:
        return reindex_all(request.app.state.container)
    finally:
        lock.release()
