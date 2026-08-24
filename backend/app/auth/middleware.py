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
)


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
        sid = request.cookies.get(COOKIE)
        if not request.app.state.session_store.validate(sid):
            return JSONResponse(
                status_code=401,
                content={"detail": "authentication required", "code": "auth_required"},
            )
        return await call_next(request)
