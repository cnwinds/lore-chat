from __future__ import annotations

IDENTITY_ADMIN = "admin"
IDENTITY_GUEST = "guest"
IDENTITY_NONE = "none"


def resolve_identity(request) -> str:
    """读取中间件写入的身份；未经中间件时视为无身份。"""
    return getattr(request.state, "identity", IDENTITY_NONE)
