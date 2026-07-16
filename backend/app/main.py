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
from app.api.routes import router
from app.settings_store import SettingsStore

_PLACEHOLDER_API_KEYS = frozenset({"", "sk-none", "sk-your-key"})
_DERIVATION_WORKER_INTERVAL_SECONDS = 0.5
_DERIVATION_WORKER_BATCH_SIZE = 20
_MEMORY_MAINTENANCE_INTERVAL_SECONDS = 24 * 3600


def _under_pytest() -> bool:
    return "pytest" in sys.modules


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    base_settings = settings or get_settings()
    _llm = llm

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        effective = app.state.settings_store.get()
        key = effective.openai_api_key.strip()
        if key in _PLACEHOLDER_API_KEYS:
            logging.getLogger("uvicorn.error").warning(
                "OPENAI_API_KEY 未配置（仍为占位符）。录入与问答将失败，请编辑 backend/.env"
            )
        app.state.container = build_container(effective, llm=_llm)

        stop_event = threading.Event()
        worker_thread: threading.Thread | None = None
        maintenance_thread: threading.Thread | None = None
        if not _under_pytest():
            worker = app.state.container.derivation_worker

            def _run_derivation_worker() -> None:
                while not stop_event.is_set():
                    try:
                        worker.drain(_DERIVATION_WORKER_BATCH_SIZE)
                        app.state.container.memory_worker.drain(_DERIVATION_WORKER_BATCH_SIZE)
                    except Exception:
                        logging.getLogger("uvicorn.error").exception(
                            "derivation worker 执行失败"
                        )
                    stop_event.wait(_DERIVATION_WORKER_INTERVAL_SECONDS)

            worker_thread = threading.Thread(
                target=_run_derivation_worker, name="derivation-worker", daemon=True
            )
            worker_thread.start()

            maintenance = app.state.container.memory_maintenance

            def _run_memory_maintenance() -> None:
                while not stop_event.is_set():
                    try:
                        maintenance.run()
                    except Exception:
                        logging.getLogger("uvicorn.error").exception(
                            "memory maintenance 执行失败"
                        )
                    stop_event.wait(_MEMORY_MAINTENANCE_INTERVAL_SECONDS)

            maintenance_thread = threading.Thread(
                target=_run_memory_maintenance, name="memory-maintenance", daemon=True
            )
            maintenance_thread.start()

        try:
            yield
        finally:
            stop_event.set()
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
    def health():
        return {"status": "ok"}

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
    app.include_router(router)
    return app


app = create_app()
