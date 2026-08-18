from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Match

from app.demo.identity import IDENTITY_GUEST

# 访客可读路由：方法 + 路由模板。
# 白名单而非黑名单：新增接口默认对访客关闭，忘记加白名单只会让某个只读功能
# 在演示站不可用，而不会把写接口暴露到公网。
GUEST_READ_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/auth/status"),
        ("POST", "/api/auth/guest"),
        ("GET", "/api/tree"),
        ("GET", "/api/doc"),
        ("GET", "/api/download"),
        ("GET", "/api/attachments/signed/{path:path}"),
        ("GET", "/api/conversations"),
        ("GET", "/api/conversations/{cid}"),
        ("GET", "/api/conversations/{cid}/events"),
        ("GET", "/api/conversations/{cid}/turns/active/stream"),
        ("GET", "/api/questions"),
        ("GET", "/api/memory/facts"),
        ("GET", "/api/kb/discover-skills"),
        ("GET", "/api/enabled-skills"),
        ("GET", "/api/docs/merge/active"),
        ("GET", "/api/docs/merge/{merge_id}"),
        ("GET", "/api/admin/settings"),
        ("GET", "/api/admin/settings-attention"),
        ("GET", "/api/admin/model-catalog"),
        ("GET", "/api/usage/summary"),
        ("GET", "/api/usage/events"),
        ("GET", "/api/usage/prices"),
        ("GET", "/api/usage/prefs"),
        # 临时提问：guest 只能 ephemeral，由 chat 路由内断言
        ("POST", "/api/chat"),
    }
)


def resolve_route_template(app, scope) -> str | None:
    for route in app.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "path", None)
    return None


class DemoGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if getattr(request.state, "identity", None) != IDENTITY_GUEST:
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        template = resolve_route_template(request.app, request.scope)
        if template is not None and (request.method, template) in GUEST_READ_ROUTES:
            return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={"detail": "演示环境为只读", "code": "demo_read_only"},
        )
