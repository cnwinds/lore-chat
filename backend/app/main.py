from __future__ import annotations

import logging
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import AuthStore, SessionStore
from app.backup import MaintenanceLock
from app.backup.guard import MaintenanceGuardMiddleware
from app.auth.middleware import AuthMiddleware
from app.auth.routes import router as auth_router
from app.config import Settings, get_settings
from app.models.llm import LLMClient
from app.deps import build_container
from app.api.admin_routes import router as admin_router
from app.api.usage_routes import router as usage_router
from app.api.routes import router
from app.engine.sandbox.mirrors import normalize_mirror_region
from app.settings_store import SettingsStore, settings_have_llm_api_key

_DERIVATION_WORKER_INTERVAL_SECONDS = 0.5
_DERIVATION_WORKER_BATCH_SIZE = 20
_MEMORY_MAINTENANCE_INTERVAL_SECONDS = 24 * 3600


def _under_pytest() -> bool:
    return "pytest" in sys.modules


def _run_while_idle(app: FastAPI, stop_event: threading.Event, interval: float, name: str, fn) -> None:
    """Run ``fn`` once per interval, only when maintenance is idle."""
    while not stop_event.is_set():
        with app.state.maintenance_lock.try_idle_slot() as allowed:
            if allowed:
                try:
                    fn()
                except Exception:
                    logging.getLogger("uvicorn.error").exception("%s 执行失败", name)
        stop_event.wait(interval)


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    base_settings = settings or get_settings()
    _llm = llm

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        effective = app.state.settings_store.get()
        if not settings_have_llm_api_key(effective):
            logging.getLogger("uvicorn.error").warning(
                "尚未配置有效的模型 API Key。"
                "请在网页「设置 → 模型」为对话/辅助候选填写 API Key"
            )
        app.state.container = build_container(effective, llm=_llm)
        try:
            n = app.state.container.chat_runner.turn_hub.recover_orphan_turns()
            if n:
                logging.getLogger("uvicorn.error").warning(
                    "recovered %d orphan running turn(s) as interrupted", n
                )
        except Exception:
            logging.getLogger("uvicorn.error").exception(
                "orphan turn recovery failed"
            )

        if not _under_pytest():
            try:
                from app.storage.media_layout_migration import (
                    run_media_layout_migration,
                )

                run_media_layout_migration(
                    knowledge_writer=app.state.container.knowledge_writer,
                    conversations=app.state.container.conversations,
                )
            except Exception:
                logging.getLogger("uvicorn.error").exception(
                    "media layout migration failed"
                )

        from app.models.models_dev import DEFAULT_TTL_SEC

        models_dev = app.state.container.models_dev

        stop_event = threading.Event()
        worker_thread: threading.Thread | None = None
        maintenance_thread: threading.Thread | None = None
        catalog_thread: threading.Thread | None = None
        if not _under_pytest():
            def _run_models_dev_refresh() -> None:
                while not stop_event.is_set():
                    try:
                        # 已在旁路维护线程内同步拉取，避免再套一层 daemon
                        models_dev.refresh_now(force=models_dev.is_stale())
                    except Exception:
                        logging.getLogger("uvicorn.error").exception(
                            "models.dev refresh failed"
                        )
                    stop_event.wait(max(3600.0, DEFAULT_TTL_SEC / 2))

            catalog_thread = threading.Thread(
                target=_run_models_dev_refresh, name="models-dev-refresh", daemon=True
            )
            catalog_thread.start()

            def _drain_derivation() -> None:
                container = app.state.container
                container.derivation_worker.drain(_DERIVATION_WORKER_BATCH_SIZE)
                container.memory_worker.drain(_DERIVATION_WORKER_BATCH_SIZE)

            worker_thread = threading.Thread(
                target=_run_while_idle,
                args=(
                    app,
                    stop_event,
                    _DERIVATION_WORKER_INTERVAL_SECONDS,
                    "derivation worker",
                    _drain_derivation,
                ),
                name="derivation-worker",
                daemon=True,
            )
            worker_thread.start()

            maintenance_thread = threading.Thread(
                target=_run_while_idle,
                args=(
                    app,
                    stop_event,
                    _MEMORY_MAINTENANCE_INTERVAL_SECONDS,
                    "memory maintenance",
                    lambda: app.state.container.memory_maintenance.run(),
                ),
                name="memory-maintenance",
                daemon=True,
            )
            maintenance_thread.start()

        try:
            yield
        finally:
            stop_event.set()
            if catalog_thread is not None:
                catalog_thread.join(timeout=2)
            if worker_thread is not None:
                worker_thread.join(timeout=2)
            if maintenance_thread is not None:
                maintenance_thread.join(timeout=2)

    app = FastAPI(title="Lore Chat", lifespan=lifespan)
    app.state.settings_store = SettingsStore(base_settings.kb_path, base_settings)
    app.state.auth_store = AuthStore(base_settings.kb_path)
    app.state.session_store = SessionStore(base_settings.kb_path)
    app.state.maintenance_lock = MaintenanceLock()

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 返回 JSON 错误，避免浏览器把 500 误报为 CORS 问题
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.get("/api/health")
    def health(request: Request):
        settings = request.app.state.settings_store.get()
        return {
            "status": "ok",
            "capabilities": {
                "sandbox": bool(settings.sandbox_enabled),
                "sandbox_trust_mode": bool(
                    settings.sandbox_enabled and settings.sandbox_trust_mode
                ),
                "sandbox_mirror_region": (
                    normalize_mirror_region(settings.sandbox_mirror_region)
                    if settings.sandbox_enabled
                    else None
                ),
            },
        }

    cors_origins = [
        origin.strip()
        for origin in base_settings.cors_origins.split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuthMiddleware)
    app.add_middleware(MaintenanceGuardMiddleware)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(usage_router)
    app.include_router(router)
    return app


app = create_app()
