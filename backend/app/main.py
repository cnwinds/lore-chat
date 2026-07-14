from __future__ import annotations

import logging
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.models.llm import LLMClient
from app.deps import build_container
from app.api.routes import router

_PLACEHOLDER_API_KEYS = frozenset({"", "sk-none", "sk-your-key"})
_DERIVATION_WORKER_INTERVAL_SECONDS = 0.5
_DERIVATION_WORKER_BATCH_SIZE = 20


def _under_pytest() -> bool:
    return "pytest" in sys.modules


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    _settings = settings
    _llm = llm

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        key = _settings.openai_api_key.strip()
        if key in _PLACEHOLDER_API_KEYS:
            logging.getLogger("uvicorn.error").warning(
                "OPENAI_API_KEY 未配置（仍为占位符）。录入与问答将失败，请编辑 backend/.env"
            )
        app.state.container = build_container(_settings, llm=_llm)

        stop_event = threading.Event()
        worker_thread: threading.Thread | None = None
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

        try:
            yield
        finally:
            stop_event.set()
            if worker_thread is not None:
                worker_thread.join(timeout=2)

    app = FastAPI(title="Lore Chat", lifespan=lifespan)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # 返回 JSON 错误，避免浏览器把 500 误报为 CORS 问题
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
