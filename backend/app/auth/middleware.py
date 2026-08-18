from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth.routes import COOKIE, GUEST_COOKIE, set_guest_cookie
from app.demo.identity import IDENTITY_ADMIN, IDENTITY_GUEST, IDENTITY_NONE
from app.demo.runtime import bind_demo_guest, reset_demo_guest


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

        demo = bool(request.app.state.settings_store.get().demo_mode)
        if request.app.state.session_store.validate(request.cookies.get(COOKIE)):
            request.state.identity = IDENTITY_ADMIN
        elif demo:
            guests = request.app.state.guest_sessions
            if guests.validate(request.cookies.get(GUEST_COOKIE)):
                request.state.identity = IDENTITY_GUEST

        if (request.method, path) in PUBLIC_ROUTES:
            token = bind_demo_guest(request.state.identity == IDENTITY_GUEST)
            try:
                return await call_next(request)
            finally:
                reset_demo_guest(token)
        for method, prefix in PUBLIC_PREFIXES:
            if request.method == method and path.startswith(prefix):
                token = bind_demo_guest(request.state.identity == IDENTITY_GUEST)
                try:
                    return await call_next(request)
                finally:
                    reset_demo_guest(token)

        issued_guest_sid: str | None = None
        if request.state.identity == IDENTITY_NONE:
            if demo:
                guests = request.app.state.guest_sessions
                client = request.client
                issued_guest_sid = guests.create(
                    ip=client.host if client else None
                )
                request.state.identity = IDENTITY_GUEST
            else:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "authentication required",
                        "code": "auth_required",
                    },
                )

        token = bind_demo_guest(request.state.identity == IDENTITY_GUEST)
        try:
            response = await call_next(request)
            if issued_guest_sid:
                set_guest_cookie(response, issued_guest_sid)
            return response
        finally:
            reset_demo_guest(token)
