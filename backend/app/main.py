from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.models.llm import LLMClient
from app.deps import build_container
from app.api.routes import router

_PLACEHOLDER_API_KEYS = frozenset({"", "sk-none", "sk-your-key"})


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
        yield

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
