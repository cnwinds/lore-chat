from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.auth.routes import COOKIE
from app.backup.export_kb import build_export_zip
from app.backup.import_kb import ImportResult, import_kb
from app.backup.lock import MaintenanceActiveError
from app.backup.reindex import reindex_all
from app.deps import apply_settings, dispose_container, remount_container
from app.models.candidate import model_routing_changed
from app.engine.web.search_providers import (
    DuplicateSearchProviderError,
    search_routing_changed,
)
from app.engine.imagegen.providers import (
    DuplicateImageProviderError,
    image_routing_changed,
)
from app.models.catalog import (
    capabilities_public_dict,
    get_active_models_dev_store,
    lookup_capabilities,
    normalize_catalog_kind,
    search_known_catalog,
    set_active_models_dev_store,
)
from app.models.models_dev import models_dev_cache_path_for_kb, shared_models_dev_store

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
    code = result.code or "import_failed"
    detail: dict[str, Any] = {"detail": result.message, "code": code}
    if result.backup_path is not None:
        detail["backup_path"] = str(result.backup_path)
    return HTTPException(status_code=result.http_status(), detail=detail)


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    data = request.app.state.settings_store.public_dict()
    container = getattr(request.app.state, "container", None)
    if container is not None and getattr(container, "model_cooldown", None) is not None:
        data["model_cooldown"] = container.model_cooldown.public_status()
    else:
        data["model_cooldown"] = {}
    if container is not None and getattr(container, "search_cooldown", None) is not None:
        data["search_cooldown"] = container.search_cooldown.public_status()
    else:
        data["search_cooldown"] = {}
    if container is not None and getattr(container, "image_cooldown", None) is not None:
        data["image_cooldown"] = container.image_cooldown.public_status()
    else:
        data["image_cooldown"] = {}
    return data


@router.get("/settings-attention")
def get_settings_attention(request: Request) -> dict[str, Any]:
    """主界面红点：未配模型链、记忆待确认、价目表缺单价。"""
    from app.settings_attention import (
        build_settings_attention,
        count_incomplete_prices,
    )

    settings = request.app.state.settings_store.get()
    container = getattr(request.app.state, "container", None)
    pending = 0
    incomplete_prices = 0
    if container is not None:
        mem = getattr(container, "memory_service", None)
        if mem is not None:
            try:
                pending = int(mem.count_pending_candidates())
            except Exception:
                pending = 0
        usage = getattr(container, "usage", None)
        if usage is not None:
            try:
                incomplete_prices = count_incomplete_prices(usage.prices())
            except Exception:
                incomplete_prices = 0
    return {
        "ok": True,
        "attention": build_settings_attention(
            settings=settings,
            memory_pending_count=pending,
            incomplete_price_count=incomplete_prices,
        ),
    }


@router.put("/settings")
def put_settings(body: dict[str, Any], request: Request) -> dict[str, Any]:
    store = request.app.state.settings_store
    container = request.app.state.container
    prev = container.settings
    try:
        new_settings = store.update(body)
    except DuplicateSearchProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DuplicateImageProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # 模型/密钥/端点配置实际变更 → 解除 disabled（共识：改配置可恢复）
    if model_routing_changed(prev, new_settings):
        container.model_cooldown.clear_disabled()
    if search_routing_changed(prev, new_settings):
        container.search_cooldown.clear_disabled()
    if image_routing_changed(prev, new_settings):
        container.image_cooldown.clear_disabled()
    apply_settings(container, new_settings)
    data = store.public_dict()
    data["model_cooldown"] = container.model_cooldown.public_status()
    data["search_cooldown"] = container.search_cooldown.public_status()
    data["image_cooldown"] = container.image_cooldown.public_status()
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


@router.post("/search-cooldown/clear")
def clear_search_cooldown(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """清除搜索提供商冷却或重新启用。body: {provider_id?: str, all?: bool}"""
    store = request.app.state.container.search_cooldown
    if body.get("all"):
        store.clear()
    else:
        pid = body.get("provider_id") or body.get("candidate_id")
        if not pid:
            raise HTTPException(status_code=422, detail="provider_id or all required")
        store.reenable(str(pid))
    return {"ok": True, "search_cooldown": store.public_status()}


@router.post("/image-cooldown/clear")
def clear_image_cooldown(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """清除生图提供商冷却或重新启用。body: {provider_id?: str, all?: bool}"""
    store = request.app.state.container.image_cooldown
    if body.get("all"):
        store.clear()
    else:
        pid = body.get("provider_id") or body.get("candidate_id")
        if not pid:
            raise HTTPException(status_code=422, detail="provider_id or all required")
        store.reenable(str(pid))
    return {"ok": True, "image_cooldown": store.public_status()}


def _models_dev_for_request(request: Request):
    """与 Container.models_dev 同一实例；禁止 HTTP 旁路自建。"""
    container = getattr(request.app.state, "container", None)
    store = getattr(container, "models_dev", None) if container is not None else None
    if store is not None:
        set_active_models_dev_store(store)
        return store
    # 启动极早期兜底：与 cooldown 一样走 path 共享单例
    active = get_active_models_dev_store()
    if active is not None:
        return active
    kb = request.app.state.settings_store.get().kb_path
    store = shared_models_dev_store(models_dev_cache_path_for_kb(kb))
    set_active_models_dev_store(store)
    return store


@router.get("/model-catalog")
def get_model_catalog(
    request: Request,
    q: str = "",
    limit: int = 40,
    refresh: bool = False,
    kind: str = "all",
) -> dict[str, Any]:
    """搜索 models.dev 缓存目录，并合并本地补充；可带 refresh=1 强制拉取。

    kind: all | llm | embedding（嵌入选模时用 embedding）
    """
    store = _models_dev_for_request(request)
    # 旁路刷新（短超时后台线程）；目录查询本身不阻塞网络
    source = store.ensure_fresh(force=refresh)
    kind_n = normalize_catalog_kind(kind)
    items = [
        h.to_dict()
        for h in search_known_catalog(
            q, limit=limit, kind=kind_n, models_dev=store
        )
    ]
    return {"ok": True, "source": source, "status": store.status(), "items": items}


@router.get("/model-capabilities")
def get_model_capabilities(
    request: Request,
    model: str = "",
    base_url: str | None = None,
) -> dict[str, Any]:
    """单模型能力 lookup：与 settings enrich / 选模同源（lookup_capabilities）。"""
    mid = (model or "").strip()
    if not mid:
        raise HTTPException(status_code=422, detail="model required")
    store = _models_dev_for_request(request)
    caps = lookup_capabilities(
        mid,
        base_url if isinstance(base_url, str) else None,
        models_dev=store,
    )
    return capabilities_public_dict(caps, model=mid)


@router.post("/provider-models")
def post_provider_models(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """按候选 Base URL / API Key 拉取远端 /models，并用目录 JSON 标注能力。

    拉取失败时回退 models.dev + 本地补充（全部已知模型）。
    """
    from app.models.provider_models import list_provider_models
    from app.settings_store import resolve_api_key_from_settings

    base_url = str(body.get("base_url") or "").strip()
    if not base_url:
        raise HTTPException(status_code=422, detail="base_url required")
    settings = request.app.state.settings_store.get()
    kind_n = normalize_catalog_kind(body.get("kind") or "llm", default="llm")
    api_key = resolve_api_key_from_settings(
        settings,
        api_key=body.get("api_key") if isinstance(body.get("api_key"), str) else None,
        candidate_id=str(body.get("candidate_id") or "") or None,
        use_embed_key=kind_n == "embedding",
    )
    q = str(body.get("q") or "")
    limit = int(body.get("limit") or 100)
    store = _models_dev_for_request(request)
    store.ensure_fresh(force=False)
    return list_provider_models(
        base_url=base_url,
        api_key=api_key,
        q=q,
        kind=kind_n,
        limit=limit,
        models_dev=store,
    )


@router.post("/model-catalog/refresh")
def refresh_model_catalog(request: Request) -> dict[str, Any]:
    store = _models_dev_for_request(request)
    # 强制旁路拉取，立即返回当前状态（可能仍为 bundled/cache，refreshing=true）
    source = store.ensure_fresh(force=True)
    return {"ok": True, "source": source, "status": store.status()}


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
            skills_dir=settings.skills_dir,
        )
        if not result.ok:
            remount_container(request.app)
            raise _import_failure_http(result)

        remount_container(
            request.app,
            keep_session_id=request.cookies.get(COOKIE),
        )
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


@router.post("/migrate-media-layout")
def migrate_media_layout_api(
    request: Request, force: bool = False
) -> dict[str, Any]:
    """显式触发媒体目录迁移（与启动钩子同一实现）。"""
    from app.storage.media_layout_migration import run_media_layout_migration

    lock = request.app.state.maintenance_lock
    try:
        lock.acquire("migrate-media-layout")
    except MaintenanceActiveError as exc:
        raise _maintenance_http(exc) from exc
    try:
        result = run_media_layout_migration(
            knowledge_writer=request.app.state.container.knowledge_writer,
            conversations=request.app.state.container.conversations,
            force=force,
        )
        # 不回传完整 path_map，避免大响应
        return {
            "ok": True,
            "skipped": bool(result.get("skipped")),
            "reason": result.get("reason"),
            "moved": result.get("moved", 0),
            "path_map_size": len(result.get("path_map") or {}),
            "conversation_rows": result.get("conversation_rows", 0),
            "markdown_files": result.get("markdown_files", 0),
        }
    finally:
        lock.release()
