"""组装 /api 子路由（chat / kb / merge / conversations）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import (
    channel_ingress_routes,
    channel_plugins_routes,
    chat_routes,
    conversation_routes,
    kb_routes,
    memory_routes,
    merge_routes,
    precepts_routes,
    open_api_routes,
    role_routes,
    room_routes,
    share_routes,
    v1_routes,
)

router = APIRouter(prefix="/api")
router.include_router(chat_routes.router)
router.include_router(kb_routes.router)
router.include_router(merge_routes.router)
router.include_router(precepts_routes.router)
router.include_router(conversation_routes.router)
router.include_router(role_routes.router)
router.include_router(memory_routes.router)
router.include_router(share_routes.router)
router.include_router(open_api_routes.router)
router.include_router(channel_plugins_routes.router)
router.include_router(channel_ingress_routes.router)
router.include_router(v1_routes.router)
router.include_router(room_routes.router)

# 兼容旧测试从 routes 导入的符号
from app.api.http_deps import (  # noqa: E402
    AskBody,
    ChatBody,
    DocContextItem,
    IngestBody,
    KbDeleteBody,
    KbMoveBody,
    MergeBody,
    ResolveBody,
    ResolveMergeSourcesBody,
    SummarizeBody,
    UpdateDocBody,
    container as _c,
    kb_tree_service as _kb_tree_service,
    normalize_chat_context as _normalize_chat_context,
)

__all__ = [
    "router",
    "AskBody",
    "ChatBody",
    "DocContextItem",
    "IngestBody",
    "KbDeleteBody",
    "KbMoveBody",
    "MergeBody",
    "ResolveBody",
    "ResolveMergeSourcesBody",
    "SummarizeBody",
    "UpdateDocBody",
    "_c",
    "_kb_tree_service",
    "_normalize_chat_context",
]
