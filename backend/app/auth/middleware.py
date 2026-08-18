from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth.routes import COOKIE, GUEST_COOKIE
from app.demo.identity import IDENTITY_ADMIN, IDENTITY_GUEST, IDENTITY_NONE

PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/auth/status"),
        ("POST", "/api/auth/setup"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/guest"),
    }
)

PUBLIC_PREFIXES = (
    ("GET", "/api/attachments/signed/"),
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.identity = IDENTITY_NONE
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        if request.app.state.session_store.validate(request.cookies.get(COOKIE)):
            request.state.identity = IDENTITY_ADMIN
        elif bool(request.app.state.settings_store.get().demo_mode):
            guests = request.app.state.guest_sessions
            if guests.validate(request.cookies.get(GUEST_COOKIE)):
                request.state.identity = IDENTITY_GUEST

        if (request.method, path) in PUBLIC_ROUTES:
            return await call_next(request)
        for method, prefix in PUBLIC_PREFIXES:
            if request.method == method and path.startswith(prefix):
                return await call_next(request)

        if request.state.identity == IDENTITY_NONE:
            return JSONResponse(
                status_code=401,
                content={"detail": "authentication required", "code": "auth_required"},
            )
        return await call_next(request)
