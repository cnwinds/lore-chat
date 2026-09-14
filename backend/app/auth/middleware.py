from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth.routes import COOKIE

PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/auth/status"),
        ("POST", "/api/auth/setup"),
        ("POST", "/api/auth/login"),
    }
)

PUBLIC_PREFIXES = (
    ("GET", "/api/attachments/signed/"),
    ("GET", "/api/media/grant/"),
    ("GET", "/api/share/"),
    ("POST", "/api/share/"),
    ("GET", "/api/channels/"),
    ("POST", "/api/channels/"),
    ("HEAD", "/api/channels/"),
)

V1_PREFIX = "/api/v1/"


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        if (request.method, path) in PUBLIC_ROUTES:
            return await call_next(request)
        for method, prefix in PUBLIC_PREFIXES:
            if request.method == method and path.startswith(prefix):
                return await call_next(request)
        if path.startswith(V1_PREFIX):
            return await self._dispatch_v1(request, call_next)
        sid = request.cookies.get(COOKIE)
        if not request.app.state.session_store.validate(sid):
            return JSONResponse(
                status_code=401,
                content={"detail": "authentication required", "code": "auth_required"},
            )
        return await call_next(request)

    async def _dispatch_v1(self, request: Request, call_next):
        header = request.headers.get("Authorization") or ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return JSONResponse(
                status_code=401,
                content={"detail": "api key required", "code": "api_key_required"},
            )
        container = getattr(request.app.state, "container", None)
        open_api = getattr(container, "open_api", None) if container else None
        rec = open_api.resolve_bearer(token.strip()) if open_api else None
        if rec is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "invalid api key", "code": "api_key_invalid"},
            )
        request.state.api_key = rec
        return await call_next(request)
