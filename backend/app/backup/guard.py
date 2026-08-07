from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

MAINTENANCE_WRITE_ROUTES = frozenset(
    {
        ("POST", "/api/chat"),
        ("POST", "/api/ingest"),
        ("PUT", "/api/doc"),
        ("POST", "/api/kb/import"),
        ("POST", "/api/admin/import"),
        ("GET", "/api/admin/export"),
        ("POST", "/api/admin/reindex"),
    }
)


class MaintenanceGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        lock = request.app.state.maintenance_lock
        route = (request.method, request.url.path)
        if lock.is_active() and route in MAINTENANCE_WRITE_ROUTES:
            reason = lock.reason() or "maintenance"
            return JSONResponse(
                status_code=503,
                content={
                    "detail": f"service unavailable: {reason} in progress",
                    "code": "maintenance",
                },
            )
        return await call_next(request)
