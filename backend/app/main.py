from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.models.llm import LLMClient
from app.deps import build_container
from app.api.routes import router


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    _settings = settings
    _llm = llm

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = build_container(_settings, llm=_llm)
        yield

    app = FastAPI(title="对话式知识管家", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
